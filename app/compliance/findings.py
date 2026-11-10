"""W11–W12: bukti, temuan, remediasi, dan validasi penutupan (titik kendali maker-checker #5).

Alur temuan (FRD EKSIBIT 37):
OPEN → ACTION_PLANNED → IN_REMEDIATION → PENDING_CLOSURE_VALIDATION → CLOSED
CLOSED → (reopen) IN_REMEDIATION · OPEN/ACTION_PLANNED → RISK_ACCEPTED
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.compliance.common import get_or_404, iso, now, require_text, sid, today, user_names
from app.compliance.models import Control, Evidence, Finding, Obligation, RemediationAction
from app.corpus.models import Document, DocumentVersion, Provision, ProvisionVersion
from app.platform.governance import audit, record_approval
from app.platform.models import AppUser, Approval, AuditEvent
from app.platform.permissions import own_only, require
from app.shared.database import get_db
from app.shared.errors import AppError
from app.shared.schemas import ResponseWrapper
from app.shared.storage import get_object, put_object
from app.shared import vocabularies as V
from app.compliance import services
from app.platform.config_service import get_value, window_days

router = APIRouter(prefix="/api/v1/compliance", tags=["findings"])
R = V.AppRole
# Otorisasi = matriks RBAC (app/shared/rbac_matrix.py). Pemilik Bisnis/Kontrol hanya "RUX (own)" pada Tindakan remediasi:
# ia TIDAK boleh membuat tindakan, mengajukan penutupan, atau memindai kesenjangan — itu milik Pejabat Kepatuhan.
FINDING_READ = require("finding", "R")                       # CO, BCO(own), CM, IA, EX
FINDING_CREATE = require("finding", "C")                     # Pejabat Kepatuhan (termasuk pindai kesenjangan)
FINDING_APPROVE = require("finding", "A")                    # Manajer: terima risiko
ACTION_CREATE = require("remediation", "C")                  # Pejabat Kepatuhan
# Mulai/selesaikan tindakan = perubahan status → huruf U (dimiliki Pejabat "CRU" dan Pemilik "RUX/own"). Huruf X milik Pemilik
# tidak dipakai sendirian di sini karena Pejabat (tanpa X) tetap harus bisa menjalankan tindakan yang ia miliki sendiri.
ACTION_EXECUTE = require("remediation", "U")
ACTION_UPDATE = require("remediation", "U")                  # Pejabat; Pemilik (own): perpanjang tenggat
ACTION_CANCEL = require("remediation", "U", only=[R.COMPLIANCE_OFFICER])
EVIDENCE_UPLOAD = require("evidence_upload", "C")            # Pejabat; Pemilik (own)
EVIDENCE_REVIEW = require("evidence_request", "U")           # Pejabat menerima/menolak bukti
EVIDENCE_READ = require("evidence_access", "R")              # RA, CO, BCO(own), LR, CM, IA
CLOSURE_PROPOSE = require("finding_closure", "C")            # Pejabat: C/propose (hanya mengusulkan)
CLOSURE_DECIDE = require("finding_closure", "A")             # Manajer Kepatuhan (titik kendali #5)
FINDING_REOPEN = require("finding_reopen", "X")              # Manajer Kepatuhan
TERMINAL = {V.FindingState.CLOSED.value, V.FindingState.RISK_ACCEPTED.value}


# ---------- skema ----------
class FindingIn(BaseModel):
    obligation_id: str
    title: str
    description: str
    severity: V.Severity = V.Severity.MEDIUM
    owner_id: str
    control_id: Optional[str] = None
    target_closure_date: Optional[date] = None


class RemediationIn(BaseModel):
    description: str
    due_date: date
    owner_id: Optional[str] = None
    expected_outcome: Optional[str] = None


class ExtendIn(BaseModel):
    new_due_date: date
    reason: str


class NoteIn(BaseModel):
    note: Optional[str] = None


class ReasonIn(BaseModel):
    reason: str


class EvidenceReviewIn(BaseModel):
    outcome: str  # ACCEPTED | REJECTED
    rationale: str


class ClosureDecisionIn(BaseModel):
    outcome: str  # APPROVED | REJECTED
    rationale: str
    new_due_date: Optional[date] = None
    late_justification: Optional[str] = None


class RiskAcceptIn(BaseModel):
    rationale: str
    review_date: date


# ---------- aturan ----------
def validate_due_date(db: Session, severity: str, due: date, base: Optional[date] = None) -> None:
    """BR-EVR-004-2: severity menentukan jendela remediasi maksimum (dapat disetel: remediation.window_days.*)."""
    base = base or today()
    if due < today():
        raise AppError(422, "DUE_DATE_IN_PAST", "Tanggal jatuh tempo tidak boleh di masa lalu")
    window = window_days(db, severity)
    limit = base + timedelta(days=window)
    if due > limit:
        raise AppError(422, "DUE_DATE_EXCEEDS_WINDOW",
                       f"Severity {severity} memiliki jendela remediasi maksimum {window} hari "
                       f"(paling lambat {limit.isoformat()})")


def _is_owner_scope(user: AppUser) -> bool:
    """True bila peran ini dibatasi 'R (own)' pada Finding (Pemilik Bisnis/Kontrol) — dibaca dari matriks RBAC."""
    return own_only(user, "finding", "R")


def _owns_finding(db: Session, f: Finding, user: AppUser) -> bool:
    if str(f.owner_id) == str(user.id):
        return True
    return bool(db.scalar(select(RemediationAction.id).where(RemediationAction.finding_id == f.id,
                                                             RemediationAction.owner_id == user.id).limit(1)))


def _check_scope(db: Session, f: Finding, user: AppUser) -> None:
    """R-05: Pemilik Bisnis/Kontrol dibatasi pada objek miliknya."""
    if _is_owner_scope(user) and not _owns_finding(db, f, user):
        raise AppError(403, "OUT_OF_SCOPE", "Temuan ini bukan milik Anda")


def _action_actor(db: Session, a: RemediationAction, user: AppUser) -> None:
    """Peran sudah lolos matriks di dependency endpoint; di sini hanya lingkup 'own' (RUX/own) yang diperiksa."""
    if own_only(user, "remediation", "X") and str(a.owner_id) != str(user.id):
        raise AppError(403, "FORBIDDEN", "Hanya pemilik tindakan atau Pejabat Kepatuhan yang dapat melakukan aksi ini")


def _set_state(db: Session, f: Finding, new: str, user: AppUser, action: str, extra: Optional[dict] = None) -> None:
    before = {"state": f.state}
    f.state = new
    f.updated_at = now()
    audit(db, user.id, action, "finding", f.id, before=before, after={"state": new, **(extra or {})})


def _citation(db: Session, ob: Obligation) -> dict:
    row = db.execute(select(Provision.number_label, Document.canonical_number)
                     .select_from(ProvisionVersion)
                     .join(Provision, Provision.id == ProvisionVersion.provision_id)
                     .join(DocumentVersion, DocumentVersion.id == ProvisionVersion.document_version_id)
                     .join(Document, Document.id == DocumentVersion.document_id)
                     .where(ProvisionVersion.id == ob.primary_citation_id)).first()
    return {"provision_version_id": str(ob.primary_citation_id),
            "canonical_number": row.canonical_number if row else None,
            "number_label": row.number_label if row else None}


def _action_dto(a: RemediationAction, names: dict, evidence: list[Evidence]) -> dict:
    overdue = a.state in (V.ActionState.OPEN.value, V.ActionState.IN_PROGRESS.value) and a.due_date < today()
    return {"id": str(a.id), "description": a.description, "expected_outcome": a.expected_outcome,
            "owner_id": sid(a.owner_id), "owner": names.get(sid(a.owner_id)), "state": a.state,
            "due_date": iso(a.due_date), "original_due_date": iso(a.original_due_date),
            "extension_history": a.extension_history or [], "overdue": overdue,
            "started_at": iso(a.started_at), "completed_at": iso(a.completed_at),
            "completion_note": a.completion_note, "cancelled_reason": a.cancelled_reason,
            "evidence": [_evidence_dto(e, names) for e in evidence]}


def _evidence_dto(e: Evidence, names: dict) -> dict:
    return {"id": str(e.id), "filename": e.filename, "description": e.description, "sha256": e.sha256,
            "size_bytes": e.size_bytes, "state": e.state, "uploaded_by": names.get(sid(e.uploaded_by)),
            "uploaded_at": iso(e.uploaded_at), "reviewed_by": names.get(sid(e.reviewed_by)),
            "reviewed_at": iso(e.reviewed_at), "review_rationale": e.review_rationale,
            "control_id": sid(e.control_id), "remediation_action_id": sid(e.remediation_action_id)}


def finding_dto(db: Session, f: Finding, names: dict, with_actions: bool = True) -> dict:
    ob = db.get(Obligation, f.obligation_id)
    ctl = db.get(Control, f.control_id) if f.control_id else None
    actions = db.scalars(select(RemediationAction).where(RemediationAction.finding_id == f.id)
                         .order_by(RemediationAction.created_at)).all()
    ev_by_action: dict = {}
    if with_actions and actions:
        for e in db.scalars(select(Evidence).where(Evidence.remediation_action_id.in_([a.id for a in actions]))
                            .order_by(Evidence.uploaded_at)):
            ev_by_action.setdefault(e.remediation_action_id, []).append(e)
    overdue_actions = sum(1 for a in actions if a.state in ("OPEN", "IN_PROGRESS") and a.due_date < today())
    finding_overdue = (f.state not in TERMINAL and f.target_closure_date is not None
                       and f.target_closure_date < today())
    return {
        "id": str(f.id), "title": f.title or f.description[:120], "description": f.description,
        "kind": f.kind, "source_type": f.source_type, "severity": f.severity, "state": f.state,
        "owner_id": sid(f.owner_id), "owner": names.get(sid(f.owner_id)),
        "raised_by": names.get(sid(f.raised_by)), "raised_by_id": sid(f.raised_by),
        "created_at": iso(f.created_at), "age_days": (today() - f.created_at.date()).days if f.created_at else 0,
        "target_closure_date": iso(f.target_closure_date), "overdue": finding_overdue,
        "overdue_actions": overdue_actions,
        "obligation": {"id": str(ob.id), "summary": ob.plain_language_summary, "state": ob.state,
                       "citation": _citation(db, ob)} if ob else None,
        "obligation_id": str(f.obligation_id),
        "control": {"id": str(ctl.id), "title": ctl.title} if ctl else None,
        "assessment_id": sid(f.assessment_id),
        "closure": {"submitted_by": names.get(sid(f.closure_submitted_by)), "submitted_at": iso(f.closure_submitted_at),
                    "closed_by": names.get(sid(f.closed_by)), "closed_at": iso(f.closed_at),
                    "rationale": f.closure_rationale},
        "risk_acceptance": {"rationale": f.risk_acceptance_rationale, "accepted_by": names.get(sid(f.risk_accepted_by)),
                            "review_date": iso(f.risk_review_date)} if f.risk_acceptance_rationale else None,
        "reopened_count": f.reopened_count,
        "actions": [_action_dto(a, names, ev_by_action.get(a.id, [])) for a in actions] if with_actions else [],
        "action_count": len(actions),
    }


# ---------- register & detail ----------
@router.get("/findings", response_model=ResponseWrapper[list])
def list_findings(severity: Optional[str] = None, state: Optional[str] = None, owner_id: Optional[str] = None,
                  overdue: Optional[bool] = None, db: Session = Depends(get_db), user: AppUser = Depends(FINDING_READ)):
    stmt = select(Finding).order_by(Finding.created_at.desc())
    if severity:
        stmt = stmt.where(Finding.severity == severity)
    if state:
        stmt = stmt.where(Finding.state == state)
    if owner_id:
        stmt = stmt.where(Finding.owner_id == owner_id)
    if _is_owner_scope(user):
        own_actions = select(RemediationAction.finding_id).where(RemediationAction.owner_id == user.id)
        stmt = stmt.where(or_(Finding.owner_id == user.id, Finding.id.in_(own_actions)))
    names = user_names(db)
    rows = [finding_dto(db, f, names) for f in db.scalars(stmt)]
    if overdue is not None:
        rows = [r for r in rows if (r["overdue"] or r["overdue_actions"] > 0) == overdue]
    return ResponseWrapper(data=rows)


@router.get("/findings/{fid}", response_model=ResponseWrapper[dict])
def finding_detail(fid: str, db: Session = Depends(get_db), user: AppUser = Depends(FINDING_READ)):
    f = get_or_404(db, Finding, fid)
    _check_scope(db, f, user)
    names = user_names(db)
    data = finding_dto(db, f, names)
    action_ids = [a["id"] for a in data["actions"]]
    evidence_ids = [e["id"] for a in data["actions"] for e in a["evidence"]]
    object_ids = [f.id] + action_ids + evidence_ids
    approvals = db.scalars(select(Approval).where(Approval.object_id == f.id).order_by(Approval.decided_at)).all()
    events = db.scalars(select(AuditEvent).where(AuditEvent.object_id.in_(object_ids))
                        .order_by(AuditEvent.occurred_at)).all()
    data["approvals"] = [{"outcome": a.outcome, "control_point": a.control_point, "maker": names.get(sid(a.maker_id)),
                          "checker": names.get(sid(a.checker_id)), "reason": a.reason,
                          "decided_at": iso(a.decided_at)} for a in approvals]
    data["timeline"] = [{"action": e.action, "actor": names.get(sid(e.actor_id), "SYSTEM"), "object_type": e.object_type,
                         "before": e.before_state, "after": e.after_state, "occurred_at": iso(e.occurred_at)}
                        for e in events]
    return ResponseWrapper(data=data)


@router.post("/findings", response_model=ResponseWrapper[dict])
def create_finding(body: FindingIn, db: Session = Depends(get_db), user: AppUser = Depends(FINDING_CREATE)):
    """FR-EVR-004: temuan manual wajib tertaut ke kewajiban, memiliki severity dan pemilik."""
    ob = get_or_404(db, Obligation, body.obligation_id)
    if ob.state in (V.ObligationState.AI_DRAFT.value, V.ObligationState.IN_VALIDATION.value):
        raise AppError(409, "AI_DRAFT_BLOCKED", "Temuan tidak dapat ditautkan ke kewajiban yang belum divalidasi")
    get_or_404(db, AppUser, body.owner_id)
    if body.control_id:
        get_or_404(db, Control, body.control_id)
    target = body.target_closure_date or today() + timedelta(days=window_days(db, body.severity.value))
    validate_due_date(db, body.severity.value, target)
    f = Finding(obligation_id=ob.id, kind="MANUAL", source_type=V.FindingSource.MANUAL.value,
                title=require_text(body.title, "title"), description=require_text(body.description, "description"),
                severity=body.severity.value, owner_id=body.owner_id, control_id=body.control_id,
                raised_by=user.id, target_closure_date=target)
    db.add(f)
    db.flush()
    audit(db, user.id, "FINDING_RAISED", "finding", f.id, after={"severity": f.severity, "state": f.state})
    db.commit()
    return ResponseWrapper(data={"id": str(f.id), "state": f.state})


@router.post("/gaps/scan", response_model=ResponseWrapper[dict])
def scan(db: Session = Depends(get_db), user: AppUser = Depends(FINDING_CREATE)):  # membuat Finding = C → hanya Pejabat
    created = services.scan_gaps_create_findings(db, user.id)
    for f in created:
        audit(db, user.id, "FINDING_AUTO_RAISED", "finding", f.id, after={"source_type": f.source_type})
    db.commit()
    return ResponseWrapper(data={"findings_created": [str(f.id) for f in created]})


# ---------- remediasi ----------
@router.post("/findings/{fid}/remediation", response_model=ResponseWrapper[dict])
def create_action(fid: str, body: RemediationIn, db: Session = Depends(get_db), user: AppUser = Depends(ACTION_CREATE)):
    f = get_or_404(db, Finding, fid)
    _check_scope(db, f, user)
    if f.state in TERMINAL or f.state == V.FindingState.PENDING_CLOSURE_VALIDATION.value:
        raise AppError(409, "INVALID_STATE", f"Tindakan tidak dapat ditambahkan pada temuan berstatus {f.state}")
    validate_due_date(db, f.severity, body.due_date)
    owner_id = body.owner_id or f.owner_id or user.id
    get_or_404(db, AppUser, owner_id)
    a = RemediationAction(finding_id=f.id, description=require_text(body.description, "description"),
                          expected_outcome=body.expected_outcome, due_date=body.due_date,
                          original_due_date=body.due_date, owner_id=owner_id, created_by=user.id)
    db.add(a)
    db.flush()
    audit(db, user.id, "ACTION_CREATED", "remediation_action", a.id,
          after={"finding_id": str(f.id), "owner_id": str(owner_id), "due_date": body.due_date.isoformat()})
    if f.state in (V.FindingState.OPEN.value, V.FindingState.REVIEW_REQUIRED.value):
        _set_state(db, f, V.FindingState.ACTION_PLANNED.value, user, "FINDING_ACTION_PLANNED")
    db.commit()
    return ResponseWrapper(data={"id": str(a.id), "finding_state": f.state})


@router.post("/actions/{aid}/start", response_model=ResponseWrapper[dict])
def start_action(aid: str, db: Session = Depends(get_db), user: AppUser = Depends(ACTION_EXECUTE)):
    a = get_or_404(db, RemediationAction, aid)
    _action_actor(db, a, user)
    if a.state != V.ActionState.OPEN.value:
        raise AppError(409, "INVALID_STATE", f"Tindakan berstatus {a.state}")
    a.state, a.started_at = V.ActionState.IN_PROGRESS.value, now()
    audit(db, user.id, "ACTION_STARTED", "remediation_action", a.id, before={"state": "OPEN"}, after={"state": a.state})
    f = db.get(Finding, a.finding_id)
    if f.state == V.FindingState.ACTION_PLANNED.value:
        _set_state(db, f, V.FindingState.IN_REMEDIATION.value, user, "FINDING_IN_REMEDIATION")
    db.commit()
    return ResponseWrapper(data={"id": str(a.id), "state": a.state, "finding_state": f.state})


@router.post("/actions/{aid}/extend", response_model=ResponseWrapper[dict])
def extend_action(aid: str, body: ExtendIn, db: Session = Depends(get_db), user: AppUser = Depends(ACTION_UPDATE)):
    """BR-EVR-005-3: perpanjangan tidak menimpa tanggal asli; riwayat dipertahankan."""
    a = get_or_404(db, RemediationAction, aid)
    _action_actor(db, a, user)
    if a.state not in (V.ActionState.OPEN.value, V.ActionState.IN_PROGRESS.value):
        raise AppError(409, "INVALID_STATE", f"Tindakan berstatus {a.state}")
    reason = require_text(body.reason, "reason")
    if body.new_due_date <= a.due_date:
        raise AppError(422, "INVALID_EXTENSION", "Tanggal baru harus setelah tanggal jatuh tempo saat ini")
    history = list(a.extension_history or [])
    history.append({"from": a.due_date.isoformat(), "to": body.new_due_date.isoformat(), "reason": reason,
                    "by": str(user.id), "at": now().isoformat()})
    before = {"due_date": a.due_date.isoformat()}
    a.due_date, a.extension_history = body.new_due_date, history
    audit(db, user.id, "ACTION_EXTENDED", "remediation_action", a.id, before=before,
          after={"due_date": body.new_due_date.isoformat(), "reason": reason})
    db.commit()
    return ResponseWrapper(data={"id": str(a.id), "due_date": a.due_date.isoformat(),
                                 "original_due_date": a.original_due_date.isoformat()})


@router.post("/actions/{aid}/evidence", response_model=ResponseWrapper[dict])
async def upload_action_evidence(aid: str, file: UploadFile = File(...), description: str = Form(""),
                                 db: Session = Depends(get_db), user: AppUser = Depends(EVIDENCE_UPLOAD)):
    a = get_or_404(db, RemediationAction, aid)
    _action_actor(db, a, user)
    if a.state in (V.ActionState.DONE.value, V.ActionState.CANCELLED.value):
        raise AppError(409, "INVALID_STATE", f"Tindakan berstatus {a.state}")
    ev = await store_evidence(db, file, user, description=description, remediation_action_id=a.id)
    db.commit()
    return ResponseWrapper(data={"id": str(ev.id), "sha256": ev.sha256, "state": ev.state})


async def store_evidence(db: Session, file: UploadFile, user: AppUser, *, description: str = "",
                         control_id=None, remediation_action_id=None) -> Evidence:
    data = await file.read()
    if not data:
        raise AppError(422, "EMPTY_FILE", "Berkas bukti kosong")
    max_mb = int(get_value(db, "evidence.max_file_mb"))
    if len(data) > max_mb * 1024 * 1024:
        raise AppError(413, "FILE_TOO_LARGE", f"Ukuran maksimum bukti {max_mb} MB")
    from app.shared.filescan import scan_upload
    scan_upload(file.filename or "", data)
    sha = services.sha256_hex(data)
    target = control_id or remediation_action_id
    key = f"evidence/{target}/{sha[:12]}_{file.filename}"
    put_object(key, data, file.content_type or "application/octet-stream")
    ev = Evidence(control_id=control_id, remediation_action_id=remediation_action_id,
                  filename=file.filename or "evidence", object_key=key, sha256=sha, size_bytes=len(data),
                  description=description or None, uploaded_by=user.id, state=V.EvidenceState.SUBMITTED.value)
    db.add(ev)
    db.flush()
    audit(db, user.id, "EVIDENCE_SUBMITTED", "evidence", ev.id,
          after={"sha256": sha, "control_id": sid(control_id), "remediation_action_id": sid(remediation_action_id)})
    return ev


@router.post("/evidence/{eid}/review", response_model=ResponseWrapper[dict])
def review_evidence(eid: str, body: EvidenceReviewIn, db: Session = Depends(get_db), user: AppUser = Depends(EVIDENCE_REVIEW)):
    """FR-EVR-003: penerimaan/penolakan wajib rasional; bukti ACCEPTED menjadi imutabel."""
    ev = get_or_404(db, Evidence, eid)
    if ev.state != V.EvidenceState.SUBMITTED.value:
        raise AppError(409, "EVIDENCE_IMMUTABLE" if ev.state == "ACCEPTED" else "INVALID_STATE",
                       f"Bukti berstatus {ev.state} tidak dapat ditinjau ulang")
    if body.outcome not in (V.EvidenceState.ACCEPTED.value, V.EvidenceState.REJECTED.value):
        raise AppError(422, "BAD_OUTCOME", "outcome harus ACCEPTED atau REJECTED")
    rationale = require_text(body.rationale, "rationale", "RATIONALE_REQUIRED")
    ev.state, ev.review_rationale, ev.reviewed_by, ev.reviewed_at = body.outcome, rationale, user.id, now()
    audit(db, user.id, f"EVIDENCE_{body.outcome}", "evidence", ev.id, before={"state": "SUBMITTED"},
          after={"state": body.outcome, "rationale": rationale})
    db.commit()
    return ResponseWrapper(data={"id": str(ev.id), "state": ev.state})


@router.get("/evidence/{eid}/download")
def download_evidence(eid: str, db: Session = Depends(get_db), user: AppUser = Depends(EVIDENCE_READ)):
    ev = get_or_404(db, Evidence, eid)
    if own_only(user, "evidence_access", "R"):  # Akses bukti: Pemilik hanya "own scope"
        own = str(ev.uploaded_by) == str(user.id)
        if ev.control_id:
            c = db.get(Control, ev.control_id)
            own = own or (c and str(c.owner_id) == str(user.id))
        if ev.remediation_action_id:
            a = db.get(RemediationAction, ev.remediation_action_id)
            own = own or (a and str(a.owner_id) == str(user.id))
        if not own:
            raise AppError(403, "OUT_OF_SCOPE", "Bukti ini bukan milik Anda")
    data = get_object(ev.object_key)
    if data is None:
        raise AppError(404, "OBJECT_NOT_STORED", "Berkas bukti tidak ditemukan di penyimpanan")
    audit(db, user.id, "EVIDENCE_DOWNLOADED", "evidence", ev.id)
    db.commit()
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{ev.filename}"'})


@router.post("/actions/{aid}/complete", response_model=ResponseWrapper[dict])
def complete_action(aid: str, body: NoteIn, db: Session = Depends(get_db), user: AppUser = Depends(ACTION_EXECUTE)):
    """BR-EVR-005-2: tindakan tidak dapat selesai tanpa bukti penutupan berstatus ACCEPTED."""
    a = get_or_404(db, RemediationAction, aid)
    _action_actor(db, a, user)
    if a.state not in (V.ActionState.OPEN.value, V.ActionState.IN_PROGRESS.value):
        raise AppError(409, "INVALID_STATE", f"Tindakan berstatus {a.state}")
    accepted = db.scalar(select(Evidence.id).where(Evidence.remediation_action_id == a.id,
                                                   Evidence.state == V.EvidenceState.ACCEPTED.value).limit(1))
    if not accepted:
        raise AppError(409, "CLOSURE_EVIDENCE_REQUIRED",
                       "Tindakan memerlukan minimal satu bukti penutupan yang sudah DITERIMA Pejabat Kepatuhan")
    before = {"state": a.state}
    a.state, a.completed_at, a.completion_note = V.ActionState.DONE.value, now(), body.note
    if a.started_at is None:
        a.started_at = a.completed_at
    audit(db, user.id, "ACTION_COMPLETED", "remediation_action", a.id, before=before, after={"state": a.state})
    f = db.get(Finding, a.finding_id)
    if f.state == V.FindingState.ACTION_PLANNED.value:
        _set_state(db, f, V.FindingState.IN_REMEDIATION.value, user, "FINDING_IN_REMEDIATION")
    db.commit()
    return ResponseWrapper(data={"id": str(a.id), "state": a.state})


@router.post("/actions/{aid}/cancel", response_model=ResponseWrapper[dict])
def cancel_action(aid: str, body: ReasonIn, db: Session = Depends(get_db), user: AppUser = Depends(ACTION_CANCEL)):
    a = get_or_404(db, RemediationAction, aid)
    if a.state not in (V.ActionState.OPEN.value, V.ActionState.IN_PROGRESS.value):
        raise AppError(409, "INVALID_STATE", f"Tindakan berstatus {a.state}")
    reason = require_text(body.reason, "reason")
    before = {"state": a.state}
    a.state, a.cancelled_reason = V.ActionState.CANCELLED.value, reason
    audit(db, user.id, "ACTION_CANCELLED", "remediation_action", a.id, before=before,
          after={"state": a.state, "reason": reason})
    db.commit()
    return ResponseWrapper(data={"id": str(a.id), "state": a.state})


# ---------- penutupan (titik kendali #5) ----------
@router.post("/findings/{fid}/submit-closure", response_model=ResponseWrapper[dict])
def submit_closure(fid: str, db: Session = Depends(get_db), user: AppUser = Depends(CLOSURE_PROPOSE)):
    f = get_or_404(db, Finding, fid)
    _check_scope(db, f, user)
    if f.state not in (V.FindingState.IN_REMEDIATION.value, V.FindingState.ACTION_PLANNED.value):
        raise AppError(409, "INVALID_STATE", f"Temuan berstatus {f.state}, belum dapat diajukan penutupannya")
    actions = db.scalars(select(RemediationAction).where(RemediationAction.finding_id == f.id)).all()
    live = [a for a in actions if a.state != V.ActionState.CANCELLED.value]
    pending = [a for a in live if a.state != V.ActionState.DONE.value]
    if not live or pending:
        raise AppError(409, "ACTIONS_NOT_COMPLETE",
                       f"{len(pending)} tindakan belum selesai" if live else "Temuan belum memiliki tindakan selesai")
    f.closure_submitted_by, f.closure_submitted_at = user.id, now()
    _set_state(db, f, V.FindingState.PENDING_CLOSURE_VALIDATION.value, user, "CLOSURE_SUBMITTED")
    db.commit()
    return ResponseWrapper(data={"id": str(f.id), "state": f.state})


@router.post("/findings/{fid}/close", response_model=ResponseWrapper[dict])
def decide_closure(fid: str, body: ClosureDecisionIn, db: Session = Depends(get_db), user: AppUser = Depends(CLOSURE_DECIDE)):
    """FR-EVR-006: validator ≠ pemilik tindakan mana pun, ≠ pemunculan temuan, ≠ pengaju penutupan."""
    f = get_or_404(db, Finding, fid)
    if f.state != V.FindingState.PENDING_CLOSURE_VALIDATION.value:
        raise AppError(409, "INVALID_STATE", f"Temuan berstatus {f.state}, bukan PENDING_CLOSURE_VALIDATION")
    if body.outcome not in ("APPROVED", "REJECTED"):
        raise AppError(422, "BAD_OUTCOME", "outcome harus APPROVED atau REJECTED")
    rationale = require_text(body.rationale, "rationale", "RATIONALE_REQUIRED")
    owners = {str(o) for o in db.scalars(select(RemediationAction.owner_id).where(RemediationAction.finding_id == f.id)) if o}
    if str(user.id) in owners:
        raise AppError(403, "SOD_VIOLATION", "Pemilik tindakan tidak boleh memvalidasi penutupan temuan yang sama")
    if f.raised_by and str(user.id) == str(f.raised_by):
        raise AppError(403, "SOD_VIOLATION", "Pihak yang memunculkan temuan tidak boleh memvalidasi penutupannya")
    late = f.target_closure_date is not None and today() > f.target_closure_date
    if body.outcome == "APPROVED" and late and not (body.late_justification or "").strip():
        raise AppError(422, "LATE_JUSTIFICATION_REQUIRED",
                       f"Penutupan melewati target {f.target_closure_date.isoformat()}; justifikasi keterlambatan wajib")
    maker = f.closure_submitted_by or f.raised_by or user.id
    record_approval(db, object_type="finding", object_id=f.id, control_point=V.ControlPoint.FINDING_CLOSURE,
                    maker_id=maker, last_editor_id=maker, checker_id=user.id, outcome=body.outcome,
                    reason=rationale, snapshot={"state": f.state, "severity": f.severity, "title": f.title,
                                                "late_justification": body.late_justification})
    if body.outcome == "APPROVED":
        f.closed_by, f.closed_at, f.closure_rationale = user.id, now(), rationale
        _set_state(db, f, V.FindingState.CLOSED.value, user, "FINDING_CLOSED", {"rationale": rationale})
    else:
        if not body.new_due_date:
            raise AppError(422, "NEW_DUE_DATE_REQUIRED", "Penolakan penutupan mensyaratkan tanggal jatuh tempo baru")
        validate_due_date(db, f.severity, body.new_due_date)
        f.target_closure_date = body.new_due_date
        _set_state(db, f, V.FindingState.IN_REMEDIATION.value, user, "CLOSURE_REJECTED",
                   {"reason": rationale, "new_due_date": body.new_due_date.isoformat()})
    db.commit()
    return ResponseWrapper(data={"id": str(f.id), "state": f.state})


@router.post("/findings/{fid}/accept-risk", response_model=ResponseWrapper[dict])
def accept_risk(fid: str, body: RiskAcceptIn, db: Session = Depends(get_db), user: AppUser = Depends(FINDING_APPROVE)):
    f = get_or_404(db, Finding, fid)
    if f.state not in (V.FindingState.OPEN.value, V.FindingState.ACTION_PLANNED.value):
        raise AppError(409, "INVALID_STATE", f"Risiko hanya dapat diterima dari OPEN/ACTION_PLANNED, bukan {f.state}")
    rationale = require_text(body.rationale, "rationale", "RATIONALE_REQUIRED")
    if body.review_date <= today():
        raise AppError(422, "REVIEW_DATE_REQUIRED", "Tanggal peninjauan risiko harus di masa depan")
    maker = f.raised_by or f.owner_id
    if maker:  # SoD: penerima risiko ≠ pemunculan temuan; keputusan tercatat append-only
        record_approval(db, object_type="finding", object_id=f.id, control_point=V.ControlPoint.FINDING_CLOSURE,
                        maker_id=maker, last_editor_id=maker, checker_id=user.id, outcome="RISK_ACCEPTED",
                        reason=rationale, snapshot={"state": f.state, "severity": f.severity})
    f.risk_acceptance_rationale, f.risk_accepted_by, f.risk_review_date = rationale, user.id, body.review_date
    _set_state(db, f, V.FindingState.RISK_ACCEPTED.value, user, "RISK_ACCEPTED",
               {"rationale": rationale, "review_date": body.review_date.isoformat()})
    db.commit()
    return ResponseWrapper(data={"id": str(f.id), "state": f.state})


@router.post("/findings/{fid}/reopen", response_model=ResponseWrapper[dict])
def reopen(fid: str, body: ReasonIn, db: Session = Depends(get_db), user: AppUser = Depends(FINDING_REOPEN)):
    f = get_or_404(db, Finding, fid)
    if f.state != V.FindingState.CLOSED.value:
        raise AppError(409, "INVALID_STATE", f"Hanya temuan CLOSED yang dapat dibuka kembali, bukan {f.state}")
    reason = require_text(body.reason, "reason")
    f.reopened_count = (f.reopened_count or 0) + 1
    # catatan penutupan asli tetap utuh di approval (append-only) dan audit_event
    _set_state(db, f, V.FindingState.IN_REMEDIATION.value, user, "FINDING_REOPENED",
               {"reason": reason, "previous_closed_by": sid(f.closed_by), "previous_closed_at": iso(f.closed_at)})
    db.commit()
    return ResponseWrapper(data={"id": str(f.id), "state": f.state})