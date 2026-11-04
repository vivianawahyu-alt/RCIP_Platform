from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.ai import gateway
from app.compliance.models import (Assessment, Control, Evidence, Finding, Obligation,
                                   ObligationControlMap, OrganisationProfile, Risk)
from app.corpus.models import Document, DocumentVersion, Provision, ProvisionVersion
from app.platform.auth import current_user, require_roles
from app.platform.governance import audit, record_approval
from app.platform.models import AiCallLog, AppUser
from app.shared.database import get_db
from app.shared.errors import AppError
from app.shared.schemas import ResponseWrapper
from app.compliance.common import iso, now, sid, user_names
from app.platform.config_service import get_value, window_days
from app.shared.vocabularies import (AppRole, ApplicabilityValue, AssessmentState,
                                     ControlPoint, ControlResult, DesignResult, EvidenceState, FindingSource,
                                     ObligationState, OperatingResult, Severity)

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])
OFFICER = require_roles(AppRole.COMPLIANCE_OFFICER)
MANAGER = require_roles(AppRole.COMPLIANCE_MANAGER)


def _get(db: Session, model, id_):
    try:
        obj = db.get(model, id_)
    except Exception:
        db.rollback()
        obj = None
    if obj is None:
        raise AppError(404, "NOT_FOUND", f"{model.__name__} tidak ditemukan")
    return obj


class ProfileIn(BaseModel):
    organisation_name: str
    entity_type: str
    licenses: list[str] = []
    business_lines: list[str] = []


class ExtractIn(BaseModel):
    provision_version_id: str
    profile_id: Optional[str] = None


class ValidateIn(BaseModel):
    owner_id: str
    plain_language_summary: Optional[str] = None
    low_confidence_reviewed: bool = False


class ReopenIn(BaseModel):
    reason: str
    new_provision_version_id: Optional[str] = None


class DecisionIn(BaseModel):
    outcome: str  # APPROVED | REJECTED
    reason: Optional[str] = None


class RiskIn(BaseModel):
    obligation_id: str
    title: str
    severity: str = "MEDIUM"


class ControlIn(BaseModel):
    risk_id: Optional[str] = None
    title: str
    owner_id: Optional[str] = None


# ---------- profil & keberlakuan ----------
@router.post("/profiles", response_model=ResponseWrapper[dict])
def create_profile(body: ProfileIn, db: Session = Depends(get_db), user: AppUser = Depends(OFFICER)):
    p = OrganisationProfile(**body.model_dump())
    db.add(p)
    db.flush()
    audit(db, user.id, "PROFILE_CREATED", "organisation_profile", p.id)
    db.commit()
    return ResponseWrapper(data={"id": str(p.id)})


# ---------- kewajiban ----------
@router.post("/obligations/extract", response_model=ResponseWrapper[dict])
def extract(body: ExtractIn, db: Session = Depends(get_db), user: AppUser = Depends(OFFICER)):
    pv = _get(db, ProvisionVersion, body.provision_version_id)
    dv = db.get(DocumentVersion, pv.document_version_id)
    if dv.state != "PUBLISHED":
        raise AppError(409, "VERSION_NOT_PUBLISHED", "Ekstraksi hanya untuk versi yang sudah terbit")
    # [7] FR-RKM-004 lapis kedua: AI tidak boleh menyusun kewajiban dari teks OCR yang belum diperiksa
    # (normalnya tidak terjadi karena publikasi sudah diblokir; ini pengaman tambahan)
    if pv.low_confidence_text:
        raise AppError(422, "LOW_CONFIDENCE_TEXT_BLOCKED", "Teks pasal hasil OCR belum dikonfirmasi analis")
    from app.compliance.applicability import _profile, approved_decision_for
    profile = _profile(db, body.profile_id)
    decision = approved_decision_for(db, dv.id, profile.id)
    if decision is None:
        raise AppError(409, "APPLICABILITY_NOT_APPROVED",
                       "Belum ada keputusan keberlakuan yang DISETUJUI untuk versi ini (W7). Buat di halaman Keberlakuan.")
    if decision.decision_value not in (ApplicabilityValue.APPLICABLE.value, ApplicabilityValue.PARTIALLY_APPLICABLE.value):
        raise AppError(409, "NOT_APPLICABLE", f"Keberlakuan: {decision.decision_value}. {decision.reason_text}")
    if (decision.decision_value == ApplicabilityValue.PARTIALLY_APPLICABLE.value
            and str(pv.id) not in (decision.scope_provision_version_ids or [])):
        raise AppError(409, "OUT_OF_APPLICABILITY_SCOPE", "Ketentuan ini tidak termasuk daftar ketentuan yang berlaku")
    try:
        res = gateway.extract_obligations(db, pv.text)
    except gateway.AIUnavailableException as e:
        raise AppError(503, "AI_UNAVAILABLE", f"AI tidak tersedia, gunakan jalur manual: {e}")
    if not res.schema_valid:
        db.commit()
        raise AppError(422, "AI_SCHEMA_VIOLATION", "Keluaran AI tidak sesuai skema")
    if not res.grounding_passed:
        db.commit()
        raise AppError(422, "AI_GROUNDING_FAILED", "Frasa pendukung AI tidak ditemukan verbatim pada teks pasal")
    created = []
    floor = get_value(db, "ai.confidence_floor")  # E8.3: di bawah ambang → LOW_CONFIDENCE, wajib ditinjau eksplisit
    for o in res.parsed.obligations:
        ob = Obligation(applicability_decision_id=decision.id, primary_citation_id=pv.id, original_text=pv.text,
                        plain_language_summary=o.plain_language_summary, required_actions=o.required_actions,
                        frequency=o.frequency, deadline_expression=o.deadline_expression,
                        required_evidence=o.required_evidence, confidence=o.confidence,
                        derived_from_ai=True, state=ObligationState.AI_DRAFT.value,
                        supporting_phrases=o.supporting_phrases, ai_call_id=res.log_id, model_id=res.model_id,
                        low_confidence=o.confidence < floor)
        db.add(ob)
        db.flush()
        created.append(str(ob.id))
        audit(db, user.id, "OBLIGATION_AI_DRAFTED", "obligation", ob.id, after={"ai_call": res.log_id})
    db.commit()
    return ResponseWrapper(data={"obligation_ids": created, "model": res.model_id, "ai_label": "AI_DRAFT"})


@router.get("/obligations", response_model=ResponseWrapper[list])
def list_obligations(db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    names = user_names(db)
    rows = db.execute(select(Obligation, Provision, Document)
                      .join(ProvisionVersion, ProvisionVersion.id == Obligation.primary_citation_id)
                      .join(Provision, Provision.id == ProvisionVersion.provision_id)
                      .join(DocumentVersion, DocumentVersion.id == ProvisionVersion.document_version_id)
                      .join(Document, Document.id == DocumentVersion.document_id)
                      .order_by(Obligation.created_at.desc())).all()
    return ResponseWrapper(data=[{
        "id": str(o.id), "state": o.state, "summary": o.plain_language_summary, "deadline": o.deadline_expression,
        "confidence": float(o.confidence) if o.confidence is not None else None, "derived_from_ai": o.derived_from_ai,
        "owner_id": str(o.owner_id) if o.owner_id else None, "validator_id": str(o.validator_id) if o.validator_id else None,
        "owner": names.get(sid(o.owner_id)), "validator": names.get(sid(o.validator_id)),
        "approver": names.get(sid(o.approver_id)), "frequency": o.frequency, "original_text": o.original_text,
        "created_at": iso(o.created_at), "supporting_phrases": o.supporting_phrases or [], "model_id": o.model_id,
        "low_confidence": o.low_confidence, "reopen_reason": o.reopen_reason,
        "required_actions": o.required_actions or [], "required_evidence": o.required_evidence,
        "ai": _ai_meta(db, o.ai_call_id),
        "citation": {"provision_version_id": str(o.primary_citation_id), "canonical_number": d.canonical_number,
                     "number_label": p.number_label}} for o, p, d in rows])


def _ai_meta(db: Session, call_id):
    if not call_id:
        return None
    log = db.get(AiCallLog, call_id)
    return {"template": f"{log.template_name}/{log.template_version}", "model_id": log.model_id,
            "schema_valid": log.schema_valid, "grounding_passed": log.grounding_passed,
            "confidence": float(log.confidence) if log.confidence is not None else None,
            "created_at": iso(log.created_at)} if log else None


@router.post("/obligations/{ob_id}/reopen", response_model=ResponseWrapper[dict])
def reopen_obligation(ob_id: str, body: ReopenIn, db: Session = Depends(get_db), user: AppUser = Depends(OFFICER)):
    """W8: REVIEW_REQUIRED → IN_VALIDATION. Opsional: arahkan sitasi ke ketentuan yang sama pada versi terbit terbaru."""
    ob = _get(db, Obligation, ob_id)
    if ob.state != ObligationState.REVIEW_REQUIRED.value:
        raise AppError(409, "INVALID_STATE", f"Kewajiban berstatus {ob.state}, bukan REVIEW_REQUIRED")
    reason = (body.reason or "").strip()
    if not reason:
        raise AppError(422, "REASON_REQUIRED", "Alasan wajib diisi")
    before = {"state": ob.state, "primary_citation_id": str(ob.primary_citation_id)}
    if body.new_provision_version_id:
        old_pv, new_pv = _get(db, ProvisionVersion, str(ob.primary_citation_id)), _get(db, ProvisionVersion, body.new_provision_version_id)
        if new_pv.provision_id != old_pv.provision_id:
            raise AppError(422, "CITATION_MISMATCH", "Sitasi baru harus ketentuan (pasal) yang sama pada versi lain")
        if db.get(DocumentVersion, new_pv.document_version_id).state != "PUBLISHED":
            raise AppError(409, "VERSION_NOT_PUBLISHED", "Sitasi baru harus pada versi berstatus PUBLISHED")
        ob.primary_citation_id, ob.original_text = new_pv.id, new_pv.text
    ob.state, ob.reopen_reason, ob.approver_id = ObligationState.IN_VALIDATION.value, reason, None
    audit(db, user.id, "OBLIGATION_REOPENED", "obligation", ob.id, before=before,
          after={"state": ob.state, "reason": reason, "primary_citation_id": str(ob.primary_citation_id)})
    db.commit()
    return ResponseWrapper(data={"id": str(ob.id), "state": ob.state})


@router.post("/obligations/{ob_id}/validate", response_model=ResponseWrapper[dict])
def validate(ob_id: str, body: ValidateIn, db: Session = Depends(get_db), user: AppUser = Depends(OFFICER)):
    ob = _get(db, Obligation, ob_id)
    if ob.state not in (ObligationState.AI_DRAFT.value, ObligationState.IN_VALIDATION.value):
        raise AppError(409, "INVALID_STATE", f"Kewajiban berstatus {ob.state}")
    _get(db, AppUser, body.owner_id)
    if ob.low_confidence and not body.low_confidence_reviewed:
        raise AppError(422, "LOW_CONFIDENCE_REVIEW_REQUIRED",
                       "Draf berkeyakinan rendah: centang konfirmasi bahwa Anda telah meninjau teks pasal secara manual")
    if ob.low_confidence:
        ob.low_confidence_reviewed_by = user.id
    before = {"state": ob.state}
    if body.plain_language_summary:
        ob.plain_language_summary = body.plain_language_summary
    ob.owner_id, ob.validator_id, ob.state = body.owner_id, user.id, ObligationState.PENDING_APPROVAL.value
    audit(db, user.id, "OBLIGATION_VALIDATED", "obligation", ob.id, before=before, after={"state": ob.state})
    db.commit()
    return ResponseWrapper(data={"id": str(ob.id), "state": ob.state})


@router.post("/obligations/{ob_id}/decision", response_model=ResponseWrapper[dict])
def decide(ob_id: str, body: DecisionIn, db: Session = Depends(get_db), user: AppUser = Depends(MANAGER)):
    ob = _get(db, Obligation, ob_id)
    if ob.state != ObligationState.PENDING_APPROVAL.value:
        raise AppError(409, "INVALID_STATE", f"Kewajiban berstatus {ob.state}, bukan PENDING_APPROVAL")
    if body.outcome not in ("APPROVED", "REJECTED"):
        raise AppError(422, "BAD_OUTCOME", "outcome harus APPROVED atau REJECTED")
    record_approval(db, object_type="obligation", object_id=ob.id, control_point=ControlPoint.OBLIGATION, maker_id=ob.validator_id,
                    last_editor_id=ob.validator_id, checker_id=user.id, outcome=body.outcome, reason=body.reason,
                    snapshot={"state": ob.state, "summary": ob.plain_language_summary})
    if body.outcome == "APPROVED":
        ob.approver_id, ob.state = user.id, ObligationState.ACTIVE.value
    else:
        ob.state = ObligationState.IN_VALIDATION.value
    audit(db, user.id, f"OBLIGATION_{body.outcome}", "obligation", ob.id, after={"state": ob.state})
    db.commit()
    return ResponseWrapper(data={"id": str(ob.id), "state": ob.state})


# ---------- risiko, kontrol, bukti, asesmen ----------
class AssessmentIn(BaseModel):
    """W10: kesimpulan desain & operasional. `result`/`notes` diterima demi kompatibilitas klien lama."""
    design_result: Optional[DesignResult] = None
    operating_result: Optional[OperatingResult] = None
    design_rationale: Optional[str] = None
    operating_rationale: Optional[str] = None
    result: Optional[ControlResult] = None
    notes: Optional[str] = None


class SignoffIn(BaseModel):
    outcome: str  # APPROVED | REJECTED
    reason: Optional[str] = None


class ControlOwnerIn(BaseModel):
    owner_id: str


def _control_dto(db: Session, c: Control, names: dict) -> dict:
    mapped = db.scalars(select(ObligationControlMap.obligation_id).where(ObligationControlMap.control_id == c.id)).all()
    ev = db.execute(select(Evidence.state, func.count()).where(Evidence.control_id == c.id).group_by(Evidence.state)).all()
    ev = {k: v for k, v in ev}
    latest = db.scalars(select(Assessment).where(Assessment.control_id == c.id)
                        .order_by(Assessment.assessed_at.desc()).limit(1)).first()
    risk = db.get(Risk, c.risk_id) if c.risk_id else None
    return {
        "id": str(c.id), "risk_id": sid(c.risk_id), "risk_title": risk.title if risk else None, "title": c.title,
        "owner_id": sid(c.owner_id), "owner": names.get(sid(c.owner_id)),
        "obligation_id": str(mapped[0]) if mapped else None, "obligation_ids": [str(m) for m in mapped],
        "evidence_count": int(sum(ev.values())), "evidence_accepted": int(ev.get("ACCEPTED", 0)),
        "evidence_pending": int(ev.get("SUBMITTED", 0)),
        "latest_assessment": latest.operating_result or latest.result if latest else None,
        "latest_assessment_state": latest.state if latest else None,
        "latest_assessment_id": sid(latest.id) if latest else None,
        "source_changed": bool(c.source_changed),
    }


def _assessment_dto(a: Assessment, names: dict, control: Optional[Control] = None) -> dict:
    return {"id": str(a.id), "control_id": str(a.control_id), "control": control.title if control else None,
            "state": a.state, "result": a.result, "design_result": a.design_result,
            "operating_result": a.operating_result, "design_rationale": a.design_rationale,
            "operating_rationale": a.operating_rationale, "notes": a.notes,
            "assessed_by": names.get(sid(a.assessed_by)), "assessed_by_id": sid(a.assessed_by),
            "assessed_at": iso(a.assessed_at), "submitted_by": names.get(sid(a.submitted_by)),
            "submitted_at": iso(a.submitted_at), "signed_off_by": names.get(sid(a.signed_off_by)),
            "signed_off_at": iso(a.signed_off_at), "return_reason": a.return_reason}


@router.get("/risks", response_model=ResponseWrapper[list])
def list_risks(db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    rows = db.execute(select(Risk, Obligation).join(Obligation, Obligation.id == Risk.obligation_id)
                      .order_by(Risk.id.desc())).all()
    return ResponseWrapper(data=[{
        "id": str(r.id), "obligation_id": str(r.obligation_id), "title": r.title,
        "severity": r.severity, "obligation_summary": o.plain_language_summary,
    } for r, o in rows])


@router.get("/controls", response_model=ResponseWrapper[list])
def list_controls(db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    names = user_names(db)
    return ResponseWrapper(data=[_control_dto(db, c, names) for c in db.scalars(select(Control).order_by(Control.title))])


@router.get("/controls/{control_id}", response_model=ResponseWrapper[dict])
def control_detail(control_id: str, db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    from app.compliance.findings import _evidence_dto

    c = _get(db, Control, control_id)
    names = user_names(db)
    data = _control_dto(db, c, names)
    data["evidence"] = [_evidence_dto(e, names) for e in
                        db.scalars(select(Evidence).where(Evidence.control_id == c.id).order_by(Evidence.uploaded_at.desc()))]
    data["assessments"] = [_assessment_dto(a, names, c) for a in
                           db.scalars(select(Assessment).where(Assessment.control_id == c.id)
                                      .order_by(Assessment.assessed_at.desc()))]
    return ResponseWrapper(data=data)


@router.post("/risks", response_model=ResponseWrapper[dict])
def create_risk(body: RiskIn, db: Session = Depends(get_db), user: AppUser = Depends(OFFICER)):
    ob = _get(db, Obligation, body.obligation_id)
    if ob.state in (ObligationState.AI_DRAFT.value, ObligationState.IN_VALIDATION.value):
        raise AppError(409, "AI_DRAFT_BLOCKED", "Risiko tidak dapat ditautkan ke kewajiban yang belum divalidasi")
    if body.severity not in {s.value for s in Severity}:
        raise AppError(422, "BAD_SEVERITY", "severity harus CRITICAL, HIGH, MEDIUM, atau LOW")
    r = Risk(**body.model_dump())
    db.add(r)
    db.flush()
    audit(db, user.id, "RISK_CREATED", "risk", r.id, after={"title": r.title, "severity": r.severity})
    db.commit()
    return ResponseWrapper(data={"id": str(r.id)})


@router.post("/controls", response_model=ResponseWrapper[dict])
def create_control(body: ControlIn, db: Session = Depends(get_db), user: AppUser = Depends(OFFICER)):
    if body.owner_id:
        _get(db, AppUser, body.owner_id)
    if body.risk_id:
        _get(db, Risk, body.risk_id)
    c = Control(title=body.title, risk_id=body.risk_id or None, owner_id=body.owner_id or None)
    db.add(c)
    db.flush()
    audit(db, user.id, "CONTROL_CREATED", "control", c.id, after={"title": c.title, "owner_id": sid(c.owner_id)})
    db.commit()
    return ResponseWrapper(data={"id": str(c.id)})


@router.post("/controls/{control_id}/owner", response_model=ResponseWrapper[dict])
def set_control_owner(control_id: str, body: ControlOwnerIn, db: Session = Depends(get_db), user: AppUser = Depends(OFFICER)):
    c = _get(db, Control, control_id)
    _get(db, AppUser, body.owner_id)
    before = {"owner_id": sid(c.owner_id)}
    c.owner_id = body.owner_id
    audit(db, user.id, "CONTROL_OWNER_ASSIGNED", "control", c.id, before=before, after={"owner_id": body.owner_id})
    db.commit()
    return ResponseWrapper(data={"id": str(c.id), "owner_id": body.owner_id})


@router.post("/obligations/{ob_id}/controls/{control_id}", response_model=ResponseWrapper[dict])
def map_control(ob_id: str, control_id: str, db: Session = Depends(get_db), user: AppUser = Depends(OFFICER)):
    ob, ctl = _get(db, Obligation, ob_id), _get(db, Control, control_id)
    if ob.state in (ObligationState.AI_DRAFT.value, ObligationState.IN_VALIDATION.value):
        raise AppError(409, "AI_DRAFT_BLOCKED", "Kewajiban belum divalidasi manusia; pemetaan kontrol diblokir")
    if db.get(ObligationControlMap, (ob.id, ctl.id)):
        raise AppError(409, "MAPPING_EXISTS", "Kontrol sudah dipetakan ke kewajiban ini")
    db.add(ObligationControlMap(obligation_id=ob.id, control_id=ctl.id))
    try:
        db.flush()
    except DBAPIError as e:
        db.rollback()
        raise AppError(409, "MAPPING_REJECTED", str(e.orig).splitlines()[0])
    audit(db, user.id, "CONTROL_MAPPED", "obligation", ob.id, after={"control_id": str(ctl.id)})
    db.commit()
    return ResponseWrapper(data={"obligation_id": str(ob.id), "control_id": str(ctl.id)})


@router.post("/controls/{control_id}/evidence", response_model=ResponseWrapper[dict])
async def upload_evidence(control_id: str, file: UploadFile = File(...), description: str = Form(""),
                          db: Session = Depends(get_db),
                          user: AppUser = Depends(require_roles(AppRole.BUSINESS_CONTROL_OWNER, AppRole.COMPLIANCE_OFFICER))):
    from app.compliance.findings import store_evidence

    ctl = _get(db, Control, control_id)
    # R-05: Pemilik Bisnis/Kontrol hanya untuk kontrol miliknya
    if user.role == AppRole.BUSINESS_CONTROL_OWNER.value and str(ctl.owner_id) != str(user.id):
        raise AppError(403, "OUT_OF_SCOPE", "Anda bukan pemilik kontrol ini")
    ev = await store_evidence(db, file, user, description=description, control_id=ctl.id)
    db.commit()
    return ResponseWrapper(data={"id": str(ev.id), "sha256": ev.sha256, "state": ev.state})


@router.get("/assessments", response_model=ResponseWrapper[list])
def list_assessments(state: Optional[str] = None, db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    names = user_names(db)
    stmt = select(Assessment, Control).join(Control, Control.id == Assessment.control_id).order_by(Assessment.assessed_at.desc())
    if state:
        stmt = stmt.where(Assessment.state == state)
    return ResponseWrapper(data=[_assessment_dto(a, names, c) for a, c in db.execute(stmt).all()])


@router.post("/controls/{control_id}/assessments", response_model=ResponseWrapper[dict])
def assess(control_id: str, body: AssessmentIn, db: Session = Depends(get_db), user: AppUser = Depends(OFFICER)):
    ctl = _get(db, Control, control_id)
    design = body.design_result.value if body.design_result else (body.result.value if body.result else None)
    operating = body.operating_result.value if body.operating_result else (body.result.value if body.result else None)
    if not design or not operating:
        raise AppError(422, "CONCLUSION_REQUIRED", "Kesimpulan desain dan operasional wajib diisi")
    d_rat = (body.design_rationale or body.notes or "").strip()
    o_rat = (body.operating_rationale or body.notes or "").strip()
    if body.design_result and not d_rat:
        raise AppError(422, "RATIONALE_REQUIRED", "Rasional efektivitas desain wajib diisi")
    if body.operating_result and not o_rat:
        raise AppError(422, "RATIONALE_REQUIRED", "Rasional efektivitas operasional wajib diisi")
    if design == "INEFFECTIVE" and operating == "EFFECTIVE":
        raise AppError(422, "INCONSISTENT_CONCLUSION",
                       "Efektivitas operasional tidak boleh EFFECTIVE bila desain INEFFECTIVE")
    if not db.scalar(select(Evidence.id).where(Evidence.control_id == ctl.id,
                                               Evidence.state == EvidenceState.ACCEPTED.value).limit(1)):
        has_any = db.scalar(select(Evidence.id).where(Evidence.control_id == ctl.id).limit(1))
        raise AppError(409, "EVIDENCE_REQUIRED",
                       "Asesmen memerlukan minimal satu bukti yang sudah DITERIMA" if has_any
                       else "Asesmen memerlukan minimal satu bukti")
    a = Assessment(control_id=ctl.id, result=operating if operating in {r.value for r in ControlResult} else design,
                   notes=body.notes, design_result=design, operating_result=operating,
                   design_rationale=d_rat or "-", operating_rationale=o_rat or "-",
                   state=AssessmentState.CONCLUDED.value, assessed_by=user.id)
    db.add(a)
    db.flush()
    audit(db, user.id, "CONTROL_ASSESSED", "assessment", a.id,
          after={"design_result": design, "operating_result": operating, "state": a.state})
    finding_id = None
    # FR-EVR-004 AC3: kesimpulan INEFFECTIVE/PARTIALLY_EFFECTIVE → tepat satu temuan otomatis tertaut ke asesmen
    weak = {"INEFFECTIVE", "PARTIALLY_EFFECTIVE"}
    if design in weak or operating in weak:
        ob_id = db.scalar(select(ObligationControlMap.obligation_id).where(ObligationControlMap.control_id == ctl.id).limit(1))
        if ob_id:
            sev = "HIGH" if "INEFFECTIVE" in (design, operating) else "MEDIUM"
            f = Finding(obligation_id=ob_id, control_id=ctl.id, assessment_id=a.id, kind="CONTROL_DEFICIENCY",
                        source_type=FindingSource.ASSESSMENT.value, severity=sev,
                        title=f"Kontrol '{ctl.title}' {operating if operating in weak else design}",
                        description=f"Asesmen: desain {design}, operasional {operating}. {o_rat or d_rat}".strip(),
                        owner_id=ctl.owner_id, raised_by=user.id,
                        target_closure_date=date.today() + timedelta(days=window_days(db, sev)))
            db.add(f)
            db.flush()
            finding_id = str(f.id)
            audit(db, user.id, "FINDING_AUTO_RAISED", "finding", f.id, after={"assessment_id": str(a.id), "severity": sev})
    db.commit()
    return ResponseWrapper(data={"id": str(a.id), "result": a.result, "state": a.state, "finding_id": finding_id})


@router.post("/assessments/{aid}/submit", response_model=ResponseWrapper[dict])
def submit_assessment(aid: str, db: Session = Depends(get_db), user: AppUser = Depends(OFFICER)):
    a = _get(db, Assessment, aid)
    if a.state != AssessmentState.CONCLUDED.value:
        raise AppError(409, "INVALID_STATE", f"Asesmen berstatus {a.state}, bukan CONCLUDED")
    a.state, a.submitted_by, a.submitted_at = AssessmentState.PENDING_SIGNOFF.value, user.id, now()
    audit(db, user.id, "ASSESSMENT_SUBMITTED", "assessment", a.id, before={"state": "CONCLUDED"}, after={"state": a.state})
    db.commit()
    return ResponseWrapper(data={"id": str(a.id), "state": a.state})


@router.post("/assessments/{aid}/signoff", response_model=ResponseWrapper[dict])
def signoff_assessment(aid: str, body: SignoffIn, db: Session = Depends(get_db), user: AppUser = Depends(MANAGER)):
    """Titik kendali #4: pemberi sign-off ≠ asesor dan ≠ pengaju."""
    a = _get(db, Assessment, aid)
    if a.state != AssessmentState.PENDING_SIGNOFF.value:
        raise AppError(409, "INVALID_STATE", f"Asesmen berstatus {a.state}, bukan PENDING_SIGNOFF")
    if body.outcome not in ("APPROVED", "REJECTED"):
        raise AppError(422, "BAD_OUTCOME", "outcome harus APPROVED atau REJECTED")
    if body.outcome == "REJECTED" and not (body.reason or "").strip():
        raise AppError(422, "REASON_REQUIRED", "Pengembalian asesmen wajib disertai alasan")
    record_approval(db, object_type="assessment", object_id=a.id, control_point=ControlPoint.ASSESSMENT_SIGNOFF,
                    maker_id=a.assessed_by, last_editor_id=a.submitted_by or a.assessed_by, checker_id=user.id,
                    outcome=body.outcome, reason=body.reason,
                    snapshot={"design_result": a.design_result, "operating_result": a.operating_result})
    if body.outcome == "APPROVED":
        a.state, a.signed_off_by, a.signed_off_at = AssessmentState.SIGNED_OFF.value, user.id, now()
        ctl = db.get(Control, a.control_id)
        if ctl.source_changed:  # asesmen baru bersign-off atas sumber terbaru menghapus penanda SOURCE_CHANGED
            ctl.source_changed = False
    else:
        a.state, a.return_reason = AssessmentState.CONCLUDED.value, body.reason
    audit(db, user.id, f"ASSESSMENT_{'SIGNED_OFF' if body.outcome == 'APPROVED' else 'RETURNED'}", "assessment", a.id,
          before={"state": "PENDING_SIGNOFF"}, after={"state": a.state, "reason": body.reason})
    db.commit()
    return ResponseWrapper(data={"id": str(a.id), "state": a.state})