"""Utilitas bersama modul kepatuhan."""
from datetime import date, datetime, timezone
from typing import Optional

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


def require_citations(db: Session, ids: Optional[list[str]]) -> list[str]:
    """Posisi hukum wajib menyitasi ProvisionVersion yang dapat diresolusi dan terbit.
    FRD Eksibit 26 / AOR-10, BR-AOM-005-5, TRD guard legal_position_cited; kode error: TRD Eksibit 25."""
    from app.corpus.services import resolve_citations  # impor lokal: hindari impor melingkar
    ids = [i for i in (ids or []) if i]
    if not ids:
        raise AppError(422, "CITATION_REQUIRED", "Posisi hukum wajib disertai sitasi ke ketentuan")
    res = resolve_citations(db, ids)
    if res.unresolved:
        raise AppError(422, "CITATION_UNRESOLVED", "Sitasi tidak dapat diresolusi ke versi ketentuan yang tersimpan",
                       {"field": "citation_provision_version_ids", "value": res.unresolved})
    for c in res.resolved:
        if c.document_version.state == "WITHDRAWN":
            raise AppError(409, "VERSION_WITHDRAWN", f"{c.document.canonical_number} {c.number_label}: versi telah ditarik")
        if c.document_version.state != "PUBLISHED":
            raise AppError(409, "VERSION_NOT_PUBLISHED", f"{c.document.canonical_number} {c.number_label}: versi belum terbit")
    return [f"{c.document.canonical_number} {c.number_label}" for c in res.resolved]