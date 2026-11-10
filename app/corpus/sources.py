"""FR-RKM-001 — registri sumber regulasi.

Alur:  DRAFT → (Analis mengajukan) PENDING_USE_REVIEW → (Administrator Sistem, orang berbeda) ACTIVE
       ACTIVE ⇄ SUSPENDED, ACTIVE/SUSPENDED → RETIRED. Penolakan mengembalikan ke DRAFT dengan alasan wajib.

Hak akses mengikuti matriks RBAC (app/shared/rbac_matrix.py, baris "Registri Regulatory Source"):
    Analis CRU · Administrator CRUD · Pejabat/Peninjau Hukum/Manajer/Auditor R · Pemilik Bisnis & Eksekutif —
Karena tabel tidak memberi huruf A kepada siapa pun, persetujuan sumber = aksi U oleh pengelola registri
(Administrator Sistem), dan pemisahan tugas memastikan penyetuju ≠ pengaju.
Dokumen hanya boleh didaftarkan & diunggah dari sumber ACTIVE (BR-RKM-001-4), dan URL asal setiap versi
harus berada di bawah salah satu awalan URL yang diizinkan sumbernya."""
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.corpus.models import Document, RegulatorySource
from app.platform.governance import audit, enforce_maker_checker
from app.platform.models import AppUser
from app.platform.permissions import require
from app.shared.database import get_db
from app.shared.errors import AppError
from app.shared.schemas import ResponseWrapper
from app.shared.vocabularies import AppRole, SourceCategory

router = APIRouter(prefix="/api/v1/corpus", tags=["corpus-sources"])
READER = require("source_registry", "R")                    # melihat daftar sumber
MAKER = require("source_registry", "C")                     # mendaftarkan & mengajukan sumber (Analis, Admin)
# menyetujui/menolak & menangguhkan/mengaktifkan kembali: U pada registri, dipersempit ke Administrator
# (Analis juga punya U, tetapi perannya sebagai pengaju; only= hanya mempersempit, tidak menambah hak)
CHECKER = require("source_registry", "U", only=[AppRole.SYSTEM_ADMINISTRATOR])


# ------------------------------------------------------------------------------------------------------
# utilitas URL
# ------------------------------------------------------------------------------------------------------
def normalise_url(url: str) -> str:
    """Bentuk baku URL untuk dibandingkan: skema & host huruf kecil, tanpa fragmen, tanpa '/' di akhir."""
    parts = urlsplit((url or "").strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise AppError(422, "INVALID_URL", "URL harus diawali http:// atau https:// dan memuat nama situs",
                       {"field": "url", "value": url})
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def url_allowed(source: RegulatorySource, url: str) -> bool:
    """URL asal sah bila diawali salah satu awalan yang diizinkan sumber (atau base_url-nya)."""
    target = normalise_url(url)
    prefixes = [normalise_url(p) for p in (source.url_allow_list or [])] or [normalise_url(source.base_url)]
    return any(target == p or target.startswith(p + "/") or target.startswith(p + "?") for p in prefixes)


# ------------------------------------------------------------------------------------------------------
# skema permintaan
# ------------------------------------------------------------------------------------------------------
class SourceIn(BaseModel):
    name: str
    category: SourceCategory
    issuer_name: str
    base_url: str
    url_allow_list: list[str] = []
    permitted_use_statement: Optional[str] = None
    citation_requirement_text: Optional[str] = None
    submit: bool = True  # langsung ajukan ke Manajer setelah dibuat


class Decision(BaseModel):
    outcome: str  # APPROVED | REJECTED
    reason: Optional[str] = None


class StatusChange(BaseModel):
    status: str  # SUSPENDED | ACTIVE | RETIRED
    reason: str


def _now():
    return datetime.now(timezone.utc)


def _snap(s: RegulatorySource) -> dict:
    """Potret singkat untuk jejak audit (sebelum/sesudah)."""
    return {"status": s.status, "name": s.name, "base_url": s.base_url, "url_allow_list": s.url_allow_list,
            "permitted_use_statement": s.permitted_use_statement}


def to_dto(s: RegulatorySource, names: dict[str, str], doc_count: int = 0) -> dict:
    n = lambda x: names.get(str(x)) if x else None  # noqa: E731
    return {"id": str(s.id), "name": s.name, "category": s.category, "issuer_name": s.issuer_name,
            "base_url": s.base_url, "url_allow_list": s.url_allow_list or [], "status": s.status,
            "permitted_use_statement": s.permitted_use_statement,
            "citation_requirement_text": s.citation_requirement_text,
            "created_by": n(s.created_by), "submitted_by": n(s.submitted_by), "approved_by": n(s.approved_by),
            "approved_at": s.approved_at.isoformat() if s.approved_at else None, "return_reason": s.return_reason,
            "documents": doc_count}


def get_source(db: Session, sid: str) -> RegulatorySource:
    try:
        s = db.get(RegulatorySource, sid)
    except Exception:  # noqa: BLE001 — id bukan UUID valid
        db.rollback()
        s = None
    if s is None:
        raise AppError(404, "NOT_FOUND", "Sumber regulasi tidak ditemukan")
    return s


def require_active(source: RegulatorySource) -> None:
    """BR-RKM-001-4: pesan galat menyebut status sumbernya."""
    if source.status != "ACTIVE":
        raise AppError(409, "SOURCE_NOT_ACTIVE",
                       f"Sumber '{source.name}' berstatus {source.status}; dokumen hanya dapat dimasukkan dari sumber ACTIVE",
                       {"source_id": str(source.id), "status": source.status})


# ------------------------------------------------------------------------------------------------------
# endpoint
# ------------------------------------------------------------------------------------------------------
@router.get("/sources", response_model=ResponseWrapper[list])
def list_sources(db: Session = Depends(get_db), _: AppUser = Depends(READER)):
    names = {str(u.id): u.username for u in db.scalars(select(AppUser))}
    counts = dict(db.execute(select(Document.source_id, func.count()).group_by(Document.source_id)).all())
    rows = db.scalars(select(RegulatorySource).order_by(RegulatorySource.name)).all()
    return ResponseWrapper(data=[to_dto(s, names, counts.get(s.id, 0)) for s in rows])


@router.post("/sources", response_model=ResponseWrapper[dict])
def create_source(body: SourceIn, db: Session = Depends(get_db), user: AppUser = Depends(MAKER)):
    if not body.name.strip() or not body.issuer_name.strip():
        raise AppError(422, "VALIDATION_ERROR", "Nama sumber dan penerbit wajib diisi", {"field": "name"})
    base = normalise_url(body.base_url)
    for s in db.scalars(select(RegulatorySource)):  # cegah sumber ganda (nama atau situs yang sama)
        if s.name.lower() == body.name.strip().lower():
            raise AppError(409, "DUPLICATE_SOURCE", f"Nama sumber '{s.name}' sudah dipakai", {"existing_source_id": str(s.id)})
        if normalise_url(s.base_url) == base:
            raise AppError(409, "DUPLICATE_SOURCE", f"Situs ini sudah terdaftar sebagai sumber '{s.name}'",
                           {"existing_source_id": str(s.id)})
    allow = [normalise_url(u) for u in body.url_allow_list if u.strip()] or [base]
    src = RegulatorySource(name=body.name.strip(), category=body.category.value, issuer_name=body.issuer_name.strip(),
                           base_url=base, url_allow_list=allow,
                           permitted_use_statement=(body.permitted_use_statement or "").strip() or None,
                           citation_requirement_text=body.citation_requirement_text, status="DRAFT", created_by=user.id)
    db.add(src)
    db.flush()
    audit(db, user.id, "SOURCE_CREATED", "regulatory_source", src.id, after=_snap(src))
    if body.submit:
        _submit(db, src, user)
    db.commit()
    return ResponseWrapper(data={"id": str(src.id), "status": src.status})


def _submit(db: Session, src: RegulatorySource, user: AppUser) -> None:
    if src.status != "DRAFT":
        raise AppError(409, "INVALID_STATE", f"Sumber berstatus {src.status} tidak dapat diajukan")
    before = _snap(src)
    src.status, src.submitted_by, src.return_reason = "PENDING_USE_REVIEW", user.id, None
    audit(db, user.id, "SOURCE_SUBMITTED_FOR_REVIEW", "regulatory_source", src.id, before=before, after=_snap(src))


@router.post("/sources/{sid}/submit", response_model=ResponseWrapper[dict])
def submit_source(sid: str, db: Session = Depends(get_db), user: AppUser = Depends(MAKER)):
    """Ajukan ulang sumber yang dikembalikan (setelah diperbaiki)."""
    src = get_source(db, sid)
    _submit(db, src, user)
    db.commit()
    return ResponseWrapper(data={"id": str(src.id), "status": src.status})


@router.post("/sources/{sid}/decision", response_model=ResponseWrapper[dict])
def decide_source(sid: str, body: Decision, db: Session = Depends(get_db), user: AppUser = Depends(CHECKER)):
    src = get_source(db, sid)
    if src.status != "PENDING_USE_REVIEW":
        raise AppError(409, "INVALID_STATE", f"Sumber berstatus {src.status}; hanya PENDING_USE_REVIEW yang dapat diputuskan")
    enforce_maker_checker(user.id, src.submitted_by or src.created_by, src.created_by)  # BR-RKM-001-3
    before = _snap(src)
    if body.outcome == "APPROVED":
        if not (src.permitted_use_statement or "").strip():  # BR-RKM-001-2
            raise AppError(422, "PERMITTED_USE_REQUIRED", "Pernyataan penggunaan yang diizinkan wajib diisi sebelum ACTIVE",
                           {"field": "permitted_use_statement"})
        src.status, src.approved_by, src.approved_at = "ACTIVE", user.id, _now()
        action = "SOURCE_APPROVED"
    elif body.outcome == "REJECTED":
        if not (body.reason or "").strip():
            raise AppError(422, "REASON_REQUIRED", "Alasan penolakan wajib diisi", {"field": "reason"})
        src.status, src.return_reason = "DRAFT", body.reason.strip()
        action = "SOURCE_REJECTED"
    else:
        raise AppError(422, "VALIDATION_ERROR", "outcome harus APPROVED atau REJECTED", {"field": "outcome"})
    audit(db, user.id, action, "regulatory_source", src.id, before=before, after={**_snap(src), "reason": body.reason})
    db.commit()
    return ResponseWrapper(data={"id": str(src.id), "status": src.status})


@router.post("/sources/{sid}/status", response_model=ResponseWrapper[dict])
def change_status(sid: str, body: StatusChange, db: Session = Depends(get_db), user: AppUser = Depends(CHECKER)):
    """Tangguhkan / aktifkan kembali / pensiunkan. RETIRED memerlukan hak D (hapus lunak) pada registri."""
    from app.shared import rbac_matrix as M
    if body.status == "RETIRED" and not M.allows(user.role, "source_registry", "D"):
        raise AppError(403, "FORBIDDEN", "Hanya pemegang hak hapus pada registri sumber yang dapat mempensiunkan sumber")
    src = get_source(db, sid)
    allowed = {("ACTIVE", "SUSPENDED"): "SOURCE_SUSPENDED", ("SUSPENDED", "ACTIVE"): "SOURCE_REACTIVATED",
               ("ACTIVE", "RETIRED"): "SOURCE_RETIRED", ("SUSPENDED", "RETIRED"): "SOURCE_RETIRED"}
    action = allowed.get((src.status, body.status))
    if not action:
        raise AppError(409, "INVALID_TRANSITION", f"Transisi {src.status} → {body.status} tidak diizinkan")
    if not body.reason.strip():
        raise AppError(422, "REASON_REQUIRED", "Alasan wajib diisi", {"field": "reason"})
    before = _snap(src)
    src.status = body.status
    audit(db, user.id, action, "regulatory_source", src.id, before=before, after={**_snap(src), "reason": body.reason})
    db.commit()
    return ResponseWrapper(data={"id": str(src.id), "status": src.status})
