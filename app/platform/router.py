import csv
import io
import json
import uuid
from typing import Optional

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import datetime, timezone

from app.platform.auth import create_token, current_user, require_roles, verify_password
from app.platform.models import AppUser, AuditEvent, Config
from app.shared.database import get_db
from app.shared.errors import AppError
from app.shared.schemas import ResponseWrapper
from app.shared.vocabularies import AppRole

router = APIRouter(tags=["platform"])


class LoginRequest(BaseModel):
    username: str
    password: str


_failed: dict[str, list[float]] = {}


@router.post("/auth/login", response_model=ResponseWrapper[dict])
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Pembatasan laju: percobaan gagal per (akun, IP) per 60 detik (auth.max_failed_logins_per_minute)."""
    from app.platform.config_service import get_value
    from app.shared.observability import count_event
    key = f"{body.username.lower()}|{request.client.host if request.client else '-'}"
    now_ts = time.time()
    recent = [t for t in _failed.get(key, []) if now_ts - t < 60]
    if len(recent) >= int(get_value(db, "auth.max_failed_logins_per_minute")):
        count_event("login_rate_limited")
        raise AppError(429, "TOO_MANY_ATTEMPTS", "Terlalu banyak percobaan login gagal; coba lagi dalam 1 menit")
    user = db.scalar(select(AppUser).where(AppUser.username == body.username))
    if not user or not verify_password(body.password, user.hashed_password):
        recent.append(now_ts)
        _failed[key] = recent
        count_event("login_failed")
        db.add(AuditEvent(actor_type="SYSTEM", action="LOGIN_FAILED", object_type="auth",
                          after_state={"username": body.username[:64]}, correlation_id=uuid.uuid4()))
        db.commit()
        raise AppError(401, "BAD_CREDENTIALS", "Username atau password salah")
    _failed.pop(key, None)
    count_event("login_success")
    return ResponseWrapper(data={"access_token": create_token(user), "role": user.role,
                                 "username": user.username, "user_id": str(user.id)})


@router.get("/auth/me", response_model=ResponseWrapper[dict])
def me(user: AppUser = Depends(current_user)):
    return ResponseWrapper(data={"id": str(user.id), "username": user.username, "role": user.role})


@router.get("/users", response_model=ResponseWrapper[list])
def list_users(db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    rows = db.scalars(select(AppUser).order_by(AppUser.username)).all()
    return ResponseWrapper(data=[{"id": str(u.id), "username": u.username, "role": u.role} for u in rows])


AUDIT_ALL = {AppRole.INTERNAL_AUDITOR.value, AppRole.SYSTEM_ADMINISTRATOR.value, AppRole.COMPLIANCE_MANAGER.value,
             AppRole.LEGAL_REVIEWER.value}
AUDIT_OWN = {AppRole.REGULATORY_ANALYST.value, AppRole.COMPLIANCE_OFFICER.value}


def _audit_query(db: Session, user: AppUser, limit: int, object_type: Optional[str], object_id: Optional[str],
                 action: Optional[str], actor: Optional[str]):
    """FR-GOV-005 + matriks RBAC §4.2: Auditor/Admin/Manajer/Legal membaca semua; Analis/Pejabat hanya event miliknya."""
    if user.role not in AUDIT_ALL | AUDIT_OWN:
        raise AppError(403, "FORBIDDEN", f"Peran {user.role} tidak diizinkan membaca jejak audit")
    stmt = select(AuditEvent).order_by(AuditEvent.id.desc())
    if user.role in AUDIT_OWN:
        stmt = stmt.where(AuditEvent.actor_id == user.id)
    if object_type:
        stmt = stmt.where(AuditEvent.object_type == object_type)
    if object_id:
        try:
            stmt = stmt.where(AuditEvent.object_id == uuid.UUID(object_id))
        except ValueError:
            raise AppError(422, "BAD_ID", "object_id bukan UUID valid")
    if action:
        stmt = stmt.where(AuditEvent.action.ilike(f"%{action}%"))
    if actor:
        stmt = stmt.join(AppUser, AppUser.id == AuditEvent.actor_id).where(AppUser.username == actor)
    names = {str(u.id): u.username for u in db.scalars(select(AppUser))}
    rows = db.scalars(stmt.limit(min(limit, 1000))).all()
    return [{"id": r.id, "actor_id": str(r.actor_id) if r.actor_id else None,
             "actor": names.get(str(r.actor_id), "SYSTEM") if r.actor_id else "SYSTEM", "actor_type": r.actor_type,
             "action": r.action, "object_type": r.object_type,
             "object_id": str(r.object_id) if r.object_id else None, "before": r.before_state, "after": r.after_state,
             "correlation_id": str(r.correlation_id), "occurred_at": r.occurred_at.isoformat()} for r in rows]


@router.get("/audit", response_model=ResponseWrapper[list])
def audit_log(limit: int = 200, object_type: Optional[str] = None, object_id: Optional[str] = None,
              action: Optional[str] = None, actor: Optional[str] = None,
              db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    return ResponseWrapper(data=_audit_query(db, user, limit, object_type, object_id, action, actor))


@router.get("/audit/export")
def audit_export(limit: int = 1000, object_type: Optional[str] = None, object_id: Optional[str] = None,
                 action: Optional[str] = None, actor: Optional[str] = None,
                 db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    rows = _audit_query(db, user, limit, object_type, object_id, action, actor)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "occurred_at", "actor", "action", "object_type", "object_id", "before", "after", "correlation_id"])
    for r in rows:
        w.writerow([r["id"], r["occurred_at"], r["actor"], r["action"], r["object_type"], r["object_id"],
                    json.dumps(r["before"], ensure_ascii=False) if r["before"] else "",
                    json.dumps(r["after"], ensure_ascii=False) if r["after"] else "", r["correlation_id"]])
    db.add(AuditEvent(actor_type="USER", actor_id=user.id, action="AUDIT_EXPORTED", object_type="audit_event",
                      after_state={"rows": len(rows)}, correlation_id=uuid.uuid4()))
    db.commit()
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="rcip_audit_trail.csv"'})


# ---------- FR-GOV-007 konfigurasi runtime ----------
class ConfigIn(BaseModel):
    value: float
    justification: str


@router.get("/config", response_model=ResponseWrapper[list])
def list_config(db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    names = {str(u.id): u.username for u in db.scalars(select(AppUser))}
    return ResponseWrapper(data=[{"key": c.key, "value": float(c.value), "default": float(c.default_value),
                                  "min": float(c.min_value), "max": float(c.max_value), "description": c.description,
                                  "updated_by": names.get(str(c.updated_by)) if c.updated_by else None,
                                  "updated_at": c.updated_at.isoformat() if c.updated_at else None}
                                 for c in db.scalars(select(Config).order_by(Config.key))])


@router.put("/config/{key}", response_model=ResponseWrapper[dict])
def update_config(key: str, body: ConfigIn, db: Session = Depends(get_db),
                  user: AppUser = Depends(require_roles(AppRole.SYSTEM_ADMINISTRATOR))):
    c = db.get(Config, key)
    if c is None:
        raise AppError(404, "NOT_FOUND", f"Kunci konfigurasi {key} tidak dikenal")
    if not body.justification.strip():
        raise AppError(422, "JUSTIFICATION_REQUIRED", "Perubahan konfigurasi wajib disertai justifikasi")
    if not (float(c.min_value) <= body.value <= float(c.max_value)):
        raise AppError(422, "CONFIG_OUT_OF_BOUNDS", f"Nilai {key} harus antara {float(c.min_value)} dan {float(c.max_value)}")
    before = float(c.value)
    c.value, c.updated_by, c.updated_at = body.value, user.id, datetime.now(timezone.utc)
    db.add(AuditEvent(actor_type="USER", actor_id=user.id, action="CONFIG_CHANGED", object_type="config",
                      before_state={"key": key, "value": before},
                      after_state={"key": key, "value": body.value, "justification": body.justification.strip()},
                      correlation_id=uuid.uuid4()))
    db.commit()
    return ResponseWrapper(data={"key": key, "value": body.value})


@router.get("/metrics", response_model=ResponseWrapper[dict])
def metrics(_: AppUser = Depends(require_roles(AppRole.SYSTEM_ADMINISTRATOR, AppRole.INTERNAL_AUDITOR))):
    from app.shared.observability import snapshot
    return ResponseWrapper(data=snapshot())
