"""Ruang kerja Pemilik Bisnis/Kontrol ("Kontrol saya").

CATATAN RBAC: matriks memberi Pemilik 'RUX (own)' pada remediasi (tanpa C). Endpoint /plan membuat satu
tindakan milik Pemilik sendiri, jadi secara fungsi ini 'C (own)'. Sepakati dengan tim.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.compliance.common import get_or_404, require_text, user_names
from app.compliance.findings import TERMINAL, _set_state, finding_dto, validate_due_date
from app.compliance.models import Control, Finding, RemediationAction
from app.platform.governance import audit
from app.platform.models import AppUser
from app.platform.permissions import require
from app.shared import vocabularies as V
from app.shared.database import get_db
from app.shared.errors import AppError
from app.shared.schemas import ResponseWrapper

router = APIRouter(prefix="/api/v1/compliance/owner", tags=["owner"])
R = V.AppRole
MINE = require("control_library", "R", only=[R.BUSINESS_CONTROL_OWNER])
PLAN = require("remediation", "U", only=[R.BUSINESS_CONTROL_OWNER])


class PlanIn(BaseModel):
    description: str
    due_date: date
    expected_outcome: Optional[str] = None


def _evidence_status(by_state: dict, signed_result: Optional[str]) -> str:
    if signed_result == "EFFECTIVE" and by_state.get("ACCEPTED"):
        return "EFFECTIVE"
    if by_state.get("SUBMITTED"):
        return "PENDING_REVIEW"
    if by_state.get("ACCEPTED"):
        return "ACCEPTED"
    return "NEEDS_EVIDENCE"


@router.get("/workspace", response_model=ResponseWrapper[dict])
def workspace(db: Session = Depends(get_db), user: AppUser = Depends(MINE)):
    controls = []
    for c in db.scalars(select(Control).where(Control.owner_id == user.id).order_by(Control.title)):
        by_state = {k: int(v) for k, v in db.execute(text(
            "SELECT state, count(*) FROM compliance.evidence WHERE control_id = :c GROUP BY state"),
            {"c": c.id}).all()}
        signed = db.execute(text("""
            SELECT operating_result, signed_off_at::text AS signed_off_at FROM compliance.assessment
            WHERE control_id = :c AND state = 'SIGNED_OFF' ORDER BY assessed_at DESC LIMIT 1"""),
            {"c": c.id}).first()
        obligations = [dict(r._mapping) for r in db.execute(text("""
            SELECT o.id::text AS obligation_id, o.plain_language_summary AS summary,
                   pv.id::text AS provision_version_id, p.number_label, d.canonical_number, dv.version_number
            FROM compliance.obligation_control_map m
            JOIN compliance.obligation o ON o.id = m.obligation_id
            JOIN corpus.provision_version pv ON pv.id = o.primary_citation_id
            JOIN corpus.provision p ON p.id = pv.provision_id
            JOIN corpus.document_version dv ON dv.id = pv.document_version_id
            JOIN corpus.document d ON d.id = dv.document_id
            WHERE m.control_id = :c AND o.state IN ('ACTIVE','REVIEW_REQUIRED')
            ORDER BY d.canonical_number, p.number_label"""), {"c": c.id}).all()]
        controls.append({
            "id": str(c.id), "title": c.title, "source_changed": c.source_changed, "obligations": obligations,
            "evidence": {"total": sum(by_state.values()), "accepted": by_state.get("ACCEPTED", 0),
                         "pending": by_state.get("SUBMITTED", 0), "rejected": by_state.get("REJECTED", 0)},
            "status": _evidence_status(by_state, signed.operating_result if signed else None),
            "signed_off_at": signed.signed_off_at if signed else None,
        })

    names = user_names(db)
    own_actions = select(RemediationAction.finding_id).where(RemediationAction.owner_id == user.id)
    stmt = (select(Finding).where(or_(Finding.owner_id == user.id, Finding.id.in_(own_actions)))
            .order_by(Finding.created_at.desc()))
    findings = []
    for f in db.scalars(stmt):
        if f.state in TERMINAL:
            continue
        d = finding_dto(db, f, names)
        live = [a for a in d["actions"] if a["state"] != "CANCELLED"]
        d["needs_plan"] = (str(f.owner_id) == str(user.id) and not live
                           and f.state != V.FindingState.PENDING_CLOSURE_VALIDATION.value)
        findings.append(d)
    return ResponseWrapper(data={"controls": controls, "findings": findings})


@router.post("/findings/{fid}/plan", response_model=ResponseWrapper[dict])
def save_plan(fid: str, body: PlanIn, db: Session = Depends(get_db), user: AppUser = Depends(PLAN)):
    f = get_or_404(db, Finding, fid)
    if str(f.owner_id) != str(user.id):
        raise AppError(403, "OUT_OF_SCOPE", "Temuan ini bukan milik Anda")
    if f.state in TERMINAL or f.state == V.FindingState.PENDING_CLOSURE_VALIDATION.value:
        raise AppError(409, "INVALID_STATE", f"Rencana tidak dapat ditambahkan pada temuan berstatus {f.state}")
    validate_due_date(db, f.severity, body.due_date)
    a = RemediationAction(finding_id=f.id, description=require_text(body.description, "description"),
                          expected_outcome=body.expected_outcome, due_date=body.due_date,
                          original_due_date=body.due_date, owner_id=user.id, created_by=user.id)
    db.add(a)
    db.flush()
    audit(db, user.id, "ACTION_PLANNED_BY_OWNER", "remediation_action", a.id,
          after={"finding_id": str(f.id), "owner_id": str(user.id), "due_date": body.due_date.isoformat()})
    if f.state in (V.FindingState.OPEN.value, V.FindingState.REVIEW_REQUIRED.value):
        _set_state(db, f, V.FindingState.ACTION_PLANNED.value, user, "FINDING_ACTION_PLANNED")
    db.commit()
    return ResponseWrapper(data={"id": str(a.id), "finding_state": f.state})