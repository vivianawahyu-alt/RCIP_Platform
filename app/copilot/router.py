"""W15 copilot advisori + FR-COP-004 (log interaksi untuk auditor) + FR-COP-005 (tinjauan jawaban berkeyakinan rendah).

Alur tinjauan: siapa pun yang bertanya dapat mengirim jawaban berkeyakinan rendah untuk ditinjau →
Analis Regulasi / Pejabat Kepatuhan / Peninjau Hukum yang BUKAN peminta memberi putusan:
CONFIRMED (jawaban benar) · CORRECTED (disertai teks koreksi) · REJECTED (jawaban tidak dapat dipakai)."""
import json
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.common import get_or_404, iso, now, sid, user_names
from app.copilot.services import answer_query
from app.platform.governance import audit, enforce_maker_checker
from app.platform.models import AiCallLog, AppUser, CopilotReview
from app.platform.permissions import require, require_any
from app.shared.database import get_db
from app.shared.errors import AppError
from app.shared.schemas import ResponseWrapper

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])
# Otorisasi memakai matriks RBAC (app/shared/rbac_matrix.py):
#   bertanya & minta tinjauan  → copilot_query X   (semua peran)
#   memberi putusan tinjauan   → copilot_promote C (Analis, Pejabat Kepatuhan, Peninjau Hukum): putusan = mengesahkan
#                                 / mengoreksi keluaran copilot sebelum dipakai sebagai rujukan
#   membaca log interaksi      → copilot_promote R atau audit_trail R (Analis, Pejabat, Peninjau Hukum, Manajer,
#                                 Auditor, Admin) — Pemilik Bisnis & Eksekutif tidak
REVIEWER = require("copilot_promote", "C")
LOG_READER = require_any(("copilot_promote", "R"), ("audit_trail", "R"))
VERDICTS = {"CONFIRMED", "CORRECTED", "REJECTED"}


class Query(BaseModel):
    question: str


class ReviewRequest(BaseModel):
    note: Optional[str] = None


class Verdict(BaseModel):
    verdict: str
    corrected_text: Optional[str] = None


@router.post("/query", response_model=ResponseWrapper[dict])
def query(body: Query, db: Session = Depends(get_db),
          user: AppUser = Depends(require("copilot_query", "X"))):  # Kueri copilot: X untuk semua peran
    if not body.question.strip():
        raise AppError(422, "VALIDATION_ERROR", "Pertanyaan tidak boleh kosong", {"field": "question"})
    return ResponseWrapper(data=answer_query(db, body.question.strip()[:1000], user.id))


def _review_dto(r: Optional[CopilotReview], names: dict) -> Optional[dict]:
    if r is None:
        return None
    return {"id": str(r.id), "state": r.state, "requested_by": names.get(sid(r.requested_by)),
            "requested_at": iso(r.requested_at), "request_note": r.request_note, "reviewer": names.get(sid(r.reviewer_id)),
            "verdict": r.verdict, "corrected_text": r.corrected_text, "reviewed_at": iso(r.reviewed_at)}


def _interaction_dto(log: AiCallLog, names: dict, review: Optional[CopilotReview]) -> dict:
    try:
        raw = json.loads(log.raw_response or "{}")
    except ValueError:
        raw = {}
    return {"id": str(log.id), "question": log.prompt_rendered, "user": names.get(sid(log.user_id)),
            "state": log.presented_state or raw.get("state"), "confidence": float(log.confidence or 0),
            "low_confidence": bool(raw.get("low_confidence")), "retrieved": raw.get("retrieved", []),
            "template": f"{log.template_name}/{log.template_version}", "model_id": log.model_id,
            "created_at": iso(log.created_at), "review": _review_dto(review, names)}


@router.get("/interactions", response_model=ResponseWrapper[list])
def interactions(review: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db),
                 _: AppUser = Depends(LOG_READER)):
    """FR-COP-004: log interaksi (pertanyaan, pasal yang diambil, model, templat). review=pending → antrean tinjauan."""
    names = user_names(db)
    stmt = select(AiCallLog).where(AiCallLog.template_name == "copilot_retrieval").order_by(AiCallLog.created_at.desc())
    reviews = {r.interaction_id: r for r in db.scalars(select(CopilotReview))}
    if review == "pending":
        ids = [k for k, r in reviews.items() if r.state == "PENDING"]
        if not ids:
            return ResponseWrapper(data=[])
        stmt = stmt.where(AiCallLog.id.in_(ids))
    rows = db.scalars(stmt.limit(min(max(limit, 1), 500))).all()
    return ResponseWrapper(data=[_interaction_dto(x, names, reviews.get(x.id)) for x in rows])


@router.post("/interactions/{iid}/request-review", response_model=ResponseWrapper[dict])
def request_review(iid: str, body: ReviewRequest, db: Session = Depends(get_db),
                   user: AppUser = Depends(require("copilot_query", "X"))):  # penanya mana pun boleh minta tinjauan
    log = get_or_404(db, AiCallLog, iid)
    if log.template_name != "copilot_retrieval":
        raise AppError(404, "NOT_FOUND", "Interaksi copilot tidak ditemukan")
    if db.scalar(select(CopilotReview).where(CopilotReview.interaction_id == log.id)):
        raise AppError(409, "REVIEW_EXISTS", "Interaksi ini sudah dikirim untuk ditinjau")
    r = CopilotReview(interaction_id=log.id, requested_by=user.id, request_note=(body.note or "").strip() or None)
    db.add(r)
    db.flush()
    audit(db, user.id, "COPILOT_REVIEW_REQUESTED", "ai_call_log", log.id, after={"review_id": str(r.id), "note": r.request_note})
    db.commit()
    return ResponseWrapper(data={"id": str(r.id), "state": r.state})


@router.post("/reviews/{rid}/verdict", response_model=ResponseWrapper[dict])
def verdict(rid: str, body: Verdict, db: Session = Depends(get_db), user: AppUser = Depends(REVIEWER)):
    r = get_or_404(db, CopilotReview, rid)
    if r.state != "PENDING":
        raise AppError(409, "INVALID_STATE", "Tinjauan sudah selesai")
    if body.verdict not in VERDICTS:
        raise AppError(422, "VALIDATION_ERROR", f"verdict harus salah satu dari {sorted(VERDICTS)}", {"field": "verdict"})
    if body.verdict == "CORRECTED" and not (body.corrected_text or "").strip():
        raise AppError(422, "VALIDATION_ERROR", "Teks koreksi wajib untuk putusan CORRECTED", {"field": "corrected_text"})
    enforce_maker_checker(user.id, r.requested_by)  # peminta tidak boleh meninjau sendiri
    r.state, r.verdict, r.reviewer_id, r.reviewed_at = "COMPLETED", body.verdict, user.id, now()
    r.corrected_text = (body.corrected_text or "").strip() or None
    audit(db, user.id, "COPILOT_REVIEW_COMPLETED", "ai_call_log", r.interaction_id,
          after={"review_id": str(r.id), "verdict": r.verdict, "corrected_text": r.corrected_text})
    db.commit()
    return ResponseWrapper(data=_review_dto(r, user_names(db)))
