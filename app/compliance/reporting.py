"""W14 pelaporan (titik kendali #6), dasbor (§14), dan drill-through rantai kepatuhan.

Laporan: DRAFT (Pejabat Kepatuhan) → PENDING_APPROVAL → ISSUED (Manajer Kepatuhan, ≠ pembangkit)
         → SUPERSEDED (otomatis) | WITHDRAWN (alasan wajib). Laporan terbit imutabel (trigger DB).
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.compliance import services
from app.compliance.common import get_or_404, iso, now, require_text, sid, user_names
from app.compliance.models import (Assessment, ComplianceReport, Control, Evidence, Finding, Obligation,
                                   ObligationControlMap, OrganisationProfile, RemediationAction)
from app.platform.governance import audit, record_approval
from app.platform.models import AppUser, Approval
from app.platform.permissions import allows, ensure_owner, own_only, require
from app.shared.database import get_db
from app.shared.errors import AppError
from app.shared.schemas import ResponseWrapper
from app.shared import vocabularies as V

router = APIRouter(prefix="/api/v1/compliance", tags=["reporting"])
R = V.AppRole
# Otorisasi = matriks RBAC (app/shared/rbac_matrix.py): "Compliance Report — hasilkan draf / terbitkan", "Laporan yang telah
# diterbitkan", "Dasbor". Draf & laporan yang belum terbit hanya terlihat oleh peran dengan R pada "hasilkan draf".
DRAFT_CREATE = require("report_draft", "C")           # Pejabat Kepatuhan
DRAFT_UPDATE = require("report_draft", "U")
ISSUE = require("report_issue", "A")                  # Manajer Kepatuhan (titik kendali #6)
PUBLISHED_STATES = {V.ReportState.ISSUED.value, V.ReportState.SUPERSEDED.value}


def _can_see_report(user: AppUser, r: ComplianceReport) -> bool:
    return r.state in PUBLISHED_STATES or allows(user, "report_draft", "R")


class ReportIn(BaseModel):
    title: str
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class DecisionIn(BaseModel):
    outcome: str  # APPROVED | REJECTED
    reason: Optional[str] = None


class ReasonIn(BaseModel):
    reason: str


# ---------- dasbor ----------
@router.get("/dashboard", response_model=ResponseWrapper[dict])
def dashboard(db: Session = Depends(get_db), user: AppUser = Depends(require("dashboard", "R"))):
    data = services.dashboard_metrics(db)
    # DRR-06: pembatasan lingkup dinyatakan di layar (MVP: angka organisasi, ditandai bila peran berlingkup)
    data["scope_note"] = ("Angka organisasi penuh. Sebagai Pemilik Bisnis/Kontrol, daftar temuan & tindakan Anda "
                          "dibatasi pada objek milik Anda." if own_only(user, "dashboard", "R") else None)
    return ResponseWrapper(data=data)


# ---------- penyusunan isi laporan (DRR-07) ----------
def build_report_payload(db: Session, title: str, period_start: Optional[date], period_end: Optional[date],
                         names: dict) -> dict:
    services.verify_report_traceability(db)
    profile = db.scalar(select(OrganisationProfile).limit(1))
    basis = services.corpus_basis(db)
    metrics = services.dashboard_metrics(db)
    regs = [dict(r._mapping) for r in db.execute(text("""
        SELECT DISTINCT ON (dv.id) d.canonical_number, d.title_id, d.status, dv.version_number,
               dv.effective_date::text AS effective_date, ad.decision_value, ad.reason_text,
               mk.username AS decided_by, ap.username AS approved_by
        FROM compliance.applicability_decision ad
        JOIN corpus.document_version dv ON dv.id = ad.target_version_id
        JOIN corpus.document d ON d.id = dv.document_id
        LEFT JOIN platform.app_user mk ON mk.id = ad.maker_id
        LEFT JOIN platform.app_user ap ON ap.id = ad.approver_id
        ORDER BY dv.id, ad.created_at DESC""")).all()]
    items = db.execute(text("""
        SELECT o.id, o.state, o.plain_language_summary, o.frequency, o.deadline_expression, o.owner_id,
               pv.id AS pv_id, pv.text AS provision_text, p.number_label, d.canonical_number, dv.version_number,
               EXISTS (SELECT 1 FROM compliance.obligation_control_map m WHERE m.obligation_id = o.id) AS has_control
        FROM compliance.obligation o
        JOIN corpus.provision_version pv ON pv.id = o.primary_citation_id
        JOIN corpus.provision p ON p.id = pv.provision_id
        JOIN corpus.document_version dv ON dv.id = pv.document_version_id
        JOIN corpus.document d ON d.id = dv.document_id
        WHERE o.state = 'ACTIVE' ORDER BY d.canonical_number, p.number_label""")).all()
    drill = metrics["drill"]
    inventory = [{
        "obligation_id": str(r.id), "summary": r.plain_language_summary, "owner": names.get(sid(r.owner_id)),
        "frequency": r.frequency, "deadline": r.deadline_expression, "has_control": r.has_control,
        "coverage": "FULL" if str(r.id) in drill["effective"] else ("PARTIAL" if r.has_control else "NONE"),
        # DRR-12: kutipan verbatim teks asli berbahasa Indonesia
        "citation": {"provision_version_id": str(r.pv_id), "canonical_number": r.canonical_number,
                     "number_label": r.number_label, "version_number": r.version_number,
                     "verbatim": r.provision_text}} for r in items]
    assessments = []
    for a, c in db.execute(select(Assessment, Control).join(Control, Control.id == Assessment.control_id)
                           .order_by(Assessment.assessed_at.desc())).all():
        ev = db.scalar(text("SELECT count(*) FROM compliance.evidence WHERE control_id=:c AND state='ACCEPTED'"),
                       {"c": c.id}) or 0
        assessments.append({"assessment_id": str(a.id), "control_id": str(c.id), "control": c.title, "state": a.state,
                            "design_result": a.design_result, "operating_result": a.operating_result,
                            "design_rationale": a.design_rationale, "operating_rationale": a.operating_rationale,
                            "assessed_by": names.get(sid(a.assessed_by)), "signed_off_by": names.get(sid(a.signed_off_by)),
                            "accepted_evidence": int(ev), "assessed_at": iso(a.assessed_at)})
    findings = []
    for f in db.scalars(select(Finding).order_by(Finding.severity, Finding.created_at)):
        acts = db.scalars(select(RemediationAction).where(RemediationAction.finding_id == f.id)).all()
        findings.append({"finding_id": str(f.id), "title": f.title, "severity": f.severity, "state": f.state,
                         "owner": names.get(sid(f.owner_id)), "target_closure_date": iso(f.target_closure_date),
                         "obligation_id": str(f.obligation_id),
                         "accepted_gap": f.state == V.FindingState.RISK_ACCEPTED.value,
                         "actions": [{"action_id": str(a.id), "description": a.description, "state": a.state,
                                      "owner": names.get(sid(a.owner_id)), "due_date": iso(a.due_date),
                                      "overdue": a.state in ("OPEN", "IN_PROGRESS") and a.due_date < date.today()}
                                     for a in acts]})
    changes = [dict(r._mapping) for r in db.execute(text("""
        SELECT cs.id::text AS change_set_id, d.canonical_number, bv.version_number AS base_version,
               nv.version_number AS new_version, cs.created_at::date::text AS computed_on,
               count(c.id) FILTER (WHERE c.is_material) AS material_changes, count(c.id) AS total_changes
        FROM corpus.change_set cs
        JOIN corpus.document_version bv ON bv.id = cs.base_version_id
        JOIN corpus.document_version nv ON nv.id = cs.new_version_id
        JOIN corpus.document d ON d.id = nv.document_id
        LEFT JOIN corpus.change c ON c.change_set_id = cs.id
        WHERE (CAST(:ps AS date) IS NULL OR cs.created_at::date >= CAST(:ps AS date))
          AND (CAST(:pe AS date) IS NULL OR cs.created_at::date <= CAST(:pe AS date))
        GROUP BY cs.id, d.canonical_number, bv.version_number, nv.version_number, cs.created_at
        ORDER BY cs.created_at DESC LIMIT 20"""), {"ps": period_start, "pe": period_end}).all()]
    pending = {
        "obligations": [dict(r._mapping) for r in db.execute(text("""
            SELECT id::text AS obligation_id, state, plain_language_summary AS summary FROM compliance.obligation
            WHERE state IN ('AI_DRAFT','IN_VALIDATION','PENDING_APPROVAL','REVIEW_REQUIRED')""")).all()],
        "assessments": [a for a in assessments if a["state"] != "SIGNED_OFF"],
        "findings_pending_closure": [f for f in findings if f["state"] == "PENDING_CLOSURE_VALIDATION"],
    }
    referenced = {"obligations": [i["obligation_id"] for i in inventory],
                  "provision_versions": [i["citation"]["provision_version_id"] for i in inventory],
                  "assessments": [a["assessment_id"] for a in assessments],
                  "findings": [f["finding_id"] for f in findings]}
    return {
        "scope": {"title": title, "as_at": metrics["as_at"], "period_start": iso(period_start),
                  "period_end": iso(period_end),
                  "organisation": profile.organisation_name if profile else None,
                  "entity_type": profile.entity_type if profile else None, "synthetic_data": True},
        "corpus_basis": basis, "applicable_regulations": regs,
        "metrics": {k: v for k, v in metrics.items() if k not in ("drill", "material_gaps", "upcoming_deadlines")},
        "obligation_inventory": inventory,
        "control_coverage": {"full": len(drill["effective"]), "partial": len(drill["partial_coverage"]),
                             "none": len(drill["gaps"]), "gaps": metrics["material_gaps"]},
        "assessment_results": assessments, "findings": findings, "regulatory_changes": changes,
        "pending": pending, "traceability_verified": True, "referenced_object_versions": referenced,
        "disclaimer": services.disclaimer(basis), "disclaimer_version": services.DISCLAIMER_VERSION,
        # kompatibilitas dengan tampilan lama
        "items": [{"obligation_id": i["obligation_id"], "summary": i["summary"], "has_control": i["has_control"],
                   "citation": i["citation"]} for i in inventory],
    }


def report_dto(r: ComplianceReport, names: dict, full: bool = False) -> dict:
    d = {"id": str(r.id), "title": r.title, "state": r.state,
         "generated_by": names.get(sid(r.generated_by or r.created_by)), "generated_by_id": sid(r.generated_by or r.created_by),
         "created_at": iso(r.created_at), "submitted_at": iso(r.submitted_at),
         "issued_by": names.get(sid(r.issued_by)), "issued_at": iso(r.issued_at), "return_reason": r.return_reason,
         "withdrawn_reason": r.withdrawn_reason, "withdrawn_at": iso(r.withdrawn_at),
         "superseded_by": sid(r.superseded_by), "disclaimer_version": r.disclaimer_version}
    p = r.payload or {}
    d["payload"] = p if full else {"metrics": p.get("metrics"), "traceability_verified": p.get("traceability_verified"),
                                   "scope": p.get("scope")}
    return d


# ---------- laporan ----------
@router.get("/reports", response_model=ResponseWrapper[list])
def list_reports(db: Session = Depends(get_db), user: AppUser = Depends(require("report_published", "R"))):
    names = user_names(db)
    stmt = select(ComplianceReport).order_by(ComplianceReport.created_at.desc())
    if not allows(user, "report_draft", "R"):  # peran lain: hanya laporan yang telah diterbitkan
        stmt = stmt.where(ComplianceReport.state.in_(PUBLISHED_STATES))
    return ResponseWrapper(data=[report_dto(r, names) for r in db.scalars(stmt)])


@router.get("/reports/{rid}", response_model=ResponseWrapper[dict])
def get_report(rid: str, db: Session = Depends(get_db), user: AppUser = Depends(require("report_published", "R"))):
    r = get_or_404(db, ComplianceReport, rid)
    if not _can_see_report(user, r):
        raise AppError(403, "FORBIDDEN", "Laporan ini belum diterbitkan; draf hanya dapat dibaca peran penyusun/peninjau")
    names = user_names(db)
    data = report_dto(r, names, full=True)
    data["approvals"] = [{"outcome": a.outcome, "checker": names.get(sid(a.checker_id)), "maker": names.get(sid(a.maker_id)),
                          "reason": a.reason, "decided_at": iso(a.decided_at)}
                         for a in db.scalars(select(Approval).where(Approval.object_id == r.id).order_by(Approval.decided_at))]
    return ResponseWrapper(data=data)


@router.post("/reports", response_model=ResponseWrapper[dict])
def create_report(body: ReportIn, db: Session = Depends(get_db), user: AppUser = Depends(DRAFT_CREATE)):
    """FR-DBR-006: Pejabat Kepatuhan membangkitkan draf; gagal bila ada angka/sitasi yang tak dapat ditelusuri."""
    title = require_text(body.title, "title")
    if body.period_start and body.period_end and body.period_start > body.period_end:
        raise AppError(422, "INVALID_PERIOD", "period_start harus sebelum period_end")
    payload = build_report_payload(db, title, body.period_start, body.period_end, user_names(db))
    rep = ComplianceReport(title=title, payload=payload, created_by=user.id, generated_by=user.id,
                           state=V.ReportState.DRAFT.value, disclaimer_version=services.DISCLAIMER_VERSION)
    db.add(rep)
    db.flush()
    audit(db, user.id, "REPORT_GENERATED", "compliance_report", rep.id, after={"state": rep.state})
    db.commit()
    return ResponseWrapper(data={"id": str(rep.id), "state": rep.state, **payload})


@router.post("/reports/{rid}/regenerate", response_model=ResponseWrapper[dict])
def regenerate_report(rid: str, db: Session = Depends(get_db), user: AppUser = Depends(DRAFT_UPDATE)):
    rep = get_or_404(db, ComplianceReport, rid)
    if rep.state != V.ReportState.DRAFT.value:
        raise AppError(409, "INVALID_STATE", f"Hanya laporan DRAFT yang dapat dibangkitkan ulang, bukan {rep.state}")
    sc = (rep.payload or {}).get("scope", {})
    rep.payload = build_report_payload(db, rep.title, date.fromisoformat(sc["period_start"]) if sc.get("period_start") else None,
                                       date.fromisoformat(sc["period_end"]) if sc.get("period_end") else None,
                                       user_names(db))
    rep.generated_by = user.id
    audit(db, user.id, "REPORT_REGENERATED", "compliance_report", rep.id)
    db.commit()
    return ResponseWrapper(data={"id": str(rep.id), "state": rep.state})


@router.post("/reports/{rid}/submit", response_model=ResponseWrapper[dict])
def submit_report(rid: str, db: Session = Depends(get_db), user: AppUser = Depends(DRAFT_UPDATE)):
    rep = get_or_404(db, ComplianceReport, rid)
    if rep.state != V.ReportState.DRAFT.value:
        raise AppError(409, "INVALID_STATE", f"Laporan berstatus {rep.state}, bukan DRAFT")
    services.verify_report_traceability(db)
    if "{" in (rep.payload or {}).get("disclaimer", "{") :
        raise AppError(422, "DISCLAIMER_INCOMPLETE", "Nilai korpus pada penafian belum terisi (CGR-20)")
    rep.state, rep.submitted_at, rep.return_reason = V.ReportState.PENDING_APPROVAL.value, now(), None
    audit(db, user.id, "REPORT_SUBMITTED", "compliance_report", rep.id, before={"state": "DRAFT"},
          after={"state": rep.state})
    db.commit()
    return ResponseWrapper(data={"id": str(rep.id), "state": rep.state})


@router.post("/reports/{rid}/decision", response_model=ResponseWrapper[dict])
def decide_report(rid: str, body: DecisionIn, db: Session = Depends(get_db), user: AppUser = Depends(ISSUE)):
    """DRR-10: penerbit harus berbeda dari pembangkit laporan."""
    rep = get_or_404(db, ComplianceReport, rid)
    if rep.state != V.ReportState.PENDING_APPROVAL.value:
        raise AppError(409, "INVALID_STATE", f"Laporan berstatus {rep.state}, bukan PENDING_APPROVAL")
    if body.outcome not in ("APPROVED", "REJECTED"):
        raise AppError(422, "BAD_OUTCOME", "outcome harus APPROVED atau REJECTED")
    if body.outcome == "REJECTED":
        require_text(body.reason, "reason")
    maker = rep.generated_by or rep.created_by
    record_approval(db, object_type="compliance_report", object_id=rep.id, control_point=V.ControlPoint.REPORT_ISSUE,
                    maker_id=maker, last_editor_id=maker, checker_id=user.id, outcome=body.outcome,
                    reason=body.reason, snapshot={"state": rep.state, "title": rep.title,
                                                  "metrics": (rep.payload or {}).get("metrics")})
    if body.outcome == "APPROVED":
        services.verify_report_traceability(db)
        for old in db.scalars(select(ComplianceReport).where(ComplianceReport.state == V.ReportState.ISSUED.value,
                                                             ComplianceReport.id != rep.id)):
            old.state, old.superseded_by = V.ReportState.SUPERSEDED.value, rep.id
            audit(db, user.id, "REPORT_SUPERSEDED", "compliance_report", old.id, after={"superseded_by": str(rep.id)})
        rep.state, rep.issued_by, rep.issued_at = V.ReportState.ISSUED.value, user.id, now()
        audit(db, user.id, "REPORT_ISSUED", "compliance_report", rep.id, after={"state": rep.state})
    else:
        rep.state, rep.return_reason = V.ReportState.DRAFT.value, body.reason
        audit(db, user.id, "REPORT_REJECTED", "compliance_report", rep.id, after={"state": rep.state, "reason": body.reason})
    db.commit()
    return ResponseWrapper(data={"id": str(rep.id), "state": rep.state})


@router.post("/reports/{rid}/withdraw", response_model=ResponseWrapper[dict])
def withdraw_report(rid: str, body: ReasonIn, db: Session = Depends(get_db), user: AppUser = Depends(ISSUE)):
    rep = get_or_404(db, ComplianceReport, rid)
    if rep.state != V.ReportState.ISSUED.value:
        raise AppError(409, "INVALID_STATE", f"Hanya laporan ISSUED yang dapat ditarik, bukan {rep.state}")
    reason = require_text(body.reason, "reason")
    rep.state, rep.withdrawn_reason, rep.withdrawn_at = V.ReportState.WITHDRAWN.value, reason, now()
    audit(db, user.id, "REPORT_WITHDRAWN", "compliance_report", rep.id, after={"reason": reason})
    db.commit()
    return ResponseWrapper(data={"id": str(rep.id), "state": rep.state})


# ---------- drill-through ----------
@router.get("/trace/obligations/{ob_id}", response_model=ResponseWrapper[dict])
def trace(ob_id: str, db: Session = Depends(get_db), user: AppUser = Depends(require("obligation", "R"))):
    """Rantai: pasal → versi → dokumen → kewajiban → persetujuan → kontrol → asesmen → bukti → temuan → remediasi.
    Mengikuti hak baca Obligation: Administrator tidak punya akses; Pemilik Bisnis/Kontrol hanya kewajiban miliknya."""
    from app.corpus.services import resolve_citations

    ob = get_or_404(db, Obligation, ob_id)
    ensure_owner(user, "obligation", "R", ob.owner_id, "kewajiban ini")
    names = user_names(db)
    cite = resolve_citations(db, [str(ob.primary_citation_id)]).resolved[0]
    aps = db.scalars(select(Approval).where(Approval.object_id == ob.id).order_by(Approval.decided_at)).all()
    ctrls = db.scalars(select(Control).join(ObligationControlMap, ObligationControlMap.control_id == Control.id)
                       .where(ObligationControlMap.obligation_id == ob.id)).all()
    controls = []
    for c in ctrls:
        last = db.scalars(select(Assessment).where(Assessment.control_id == c.id)
                          .order_by(Assessment.assessed_at.desc()).limit(1)).first()
        evs = db.scalars(select(Evidence).where(Evidence.control_id == c.id)).all()
        controls.append({"id": str(c.id), "title": c.title, "owner": names.get(sid(c.owner_id)),
                         "latest_assessment": {"state": last.state, "design_result": last.design_result,
                                               "operating_result": last.operating_result,
                                               "signed_off_by": names.get(sid(last.signed_off_by))} if last else None,
                         "evidence": {"total": len(evs), "accepted": sum(1 for e in evs if e.state == "ACCEPTED")}})
    findings = []
    for f in db.scalars(select(Finding).where(Finding.obligation_id == ob.id).order_by(Finding.created_at)):
        acts = db.scalars(select(RemediationAction).where(RemediationAction.finding_id == f.id)).all()
        findings.append({"id": str(f.id), "title": f.title, "severity": f.severity, "state": f.state,
                         "actions": [{"id": str(a.id), "state": a.state, "description": a.description} for a in acts]})
    return ResponseWrapper(data={
        "obligation": {"id": str(ob.id), "state": ob.state, "summary": ob.plain_language_summary,
                       "owner": names.get(sid(ob.owner_id)), "validator": names.get(sid(ob.validator_id)),
                       "approver": names.get(sid(ob.approver_id)), "derived_from_ai": ob.derived_from_ai},
        "citation": cite.model_dump(),
        "approvals": [{"outcome": a.outcome, "control_point": a.control_point, "checker_id": str(a.checker_id),
                       "checker": names.get(sid(a.checker_id)), "maker": names.get(sid(a.maker_id)),
                       "decided_at": iso(a.decided_at)} for a in aps],
        "controls": controls, "findings": findings})