"""Utilitas bersama modul kepatuhan."""
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.platform.models import AppUser
from app.shared.errors import AppError


def get_or_404(db: Session, model, id_):
    try:
        obj = db.get(model, id_)
    except Exception:  # id bukan UUID valid
        db.rollback()
        obj = None
    if obj is None:
        raise AppError(404, "NOT_FOUND", f"{model.__name__} tidak ditemukan")
    return obj


def now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return date.today()


def user_names(db: Session) -> dict[str, str]:
    return {str(u.id): u.username for u in db.scalars(select(AppUser))}


def sid(v) -> str | None:
    return str(v) if v is not None else None


def iso(v) -> str | None:
    return v.isoformat() if v is not None else None


def require_text(value: str | None, field: str, code: str = "REASON_REQUIRED") -> str:
    if not value or not value.strip():
        raise AppError(422, code, f"Field '{field}' wajib diisi")
    return value.strip()
