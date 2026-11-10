import hashlib  # sidik jari berkas untuk pemeriksaan duplikat
from datetime import date
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
import uuid  # untuk object_id audit dokumen/versi yang dihapus

from sqlalchemy import func, select  # func.count() untuk menghitung rujukan
from sqlalchemy.exc import DBAPIError  # menangkap penolakan foreign key / trigger DB
from sqlalchemy.orm import Session
from pathlib import Path
from uuid import uuid4

from app.corpus import services
from app.corpus.models import (ChangeSet, Document, DocumentVersion, Provision, ProvisionVersion, RegulatorySource,
                               TaxonomyLabel)
from app.corpus.sources import get_source, normalise_url, require_active, url_allowed
from app.platform.auth import current_user
from app.platform.governance import audit
from app.platform.models import AppUser
from app.platform.permissions import allows, require, require_any
from app.shared.database import get_db
from app.shared.errors import AppError
from app.shared.schemas import CitationResolveRequest, CitationResolveResponse, ResponseWrapper
from app.shared.storage import get_object, put_object
from app.shared.vocabularies import AppRole, VersionState

router = APIRouter(tags=["corpus"])
# Otorisasi memakai matriks RBAC (app/shared/rbac_matrix.py): tiap endpoint menyebut kapabilitas + huruf aksi tabel.


class DocumentCreate(BaseModel):
    canonical_number: str
    instrument_type: str = "POJK"
    issuer: str = "Otoritas Jasa Keuangan"
    title_id: str
    source_id: Optional[str] = None  # sumber terdaftar (menu Sumber regulasi); wajib ACTIVE
    source_category: str = "OJK"     # kompatibilitas lama: dipakai bila source_id kosong
    base_url: str = "https://www.ojk.go.id"


class DocumentUpdate(BaseModel):
    """Ubah data dokumen. Nomor regulasi hanya boleh diubah selama belum ada versi yang pernah terbit."""
    canonical_number: Optional[str] = None
    title_id: Optional[str] = None
    instrument_type: Optional[str] = None
    issuer: Optional[str] = None


class ProvisionCorrection(BaseModel):
    text: str


class ChangeRequest(BaseModel):
    base_version_id: str
    new_version_id: str


def _get(db: Session, model, id_):
    try:
        obj = db.get(model, id_)
    except Exception:  # id bukan UUID valid
        db.rollback()
        obj = None
    if obj is None:
        raise AppError(404, "NOT_FOUND", f"{model.__name__} tidak ditemukan")
    return obj


def _share(db: Session, doc_id=None) -> None:
    """Ekspor otomatis dokumen ke data/korpus setelah perubahan tersimpan, agar bisa dibagikan ke tim lewat Git.
    doc_id kosong = dokumen baru saja dihapus (tulis penanda hapus)."""
    from app.corpus.sync import auto_export
    auto_export(db, doc_id)


@router.post("/api/v1/citations/resolve", response_model=ResponseWrapper[CitationResolveResponse])
def resolve(payload: CitationResolveRequest, db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    """KONTRAK ANTAR-MODUL (dibekukan Minggu 4)."""
    return ResponseWrapper(data=services.resolve_citations(db, payload.provision_version_ids))


@router.post("/api/v1/corpus/documents", response_model=ResponseWrapper[dict])
def create_document(body: DocumentCreate, db: Session = Depends(get_db),
                    user: AppUser = Depends(require("source_registry", "C"))):  # Registri Regulatory Source: C = RA, Admin
    if not body.canonical_number.strip() or not body.title_id.strip():
        raise AppError(422, "VALIDATION_ERROR", "Nomor regulasi dan judul wajib diisi", {"field": "canonical_number"})
    if db.scalar(select(Document).where(Document.canonical_number == body.canonical_number.strip())):
        raise AppError(409, "DUPLICATE", "Nomor regulasi sudah terdaftar")
    if body.source_id:  # FR-RKM-001: dokumen terikat ke sumber terdaftar yang ACTIVE
        src = get_source(db, body.source_id)
    else:  # kompatibilitas lama (seed, tes): sumber dicari/dibuat dari kategori
        src = services.get_or_create_source(db, body.source_category, body.source_category, body.issuer, body.base_url)
    require_active(src)
    doc = Document(source_id=src.id, canonical_number=body.canonical_number.strip(), instrument_type=body.instrument_type,
                   issuer=body.issuer, title_id=body.title_id.strip())
    db.add(doc)
    db.flush()
    from app.corpus.review import suggest_labels
    suggest_labels(db, doc)
    audit(db, user.id, "DOCUMENT_CREATED", "document", doc.id, after={"source": src.name})
    db.commit()
    _share(db, doc.id)  # dokumen baru langsung terlihat oleh tim setelah di-push
    return ResponseWrapper(data={"id": str(doc.id)})


@router.get("/api/v1/corpus/documents", response_model=ResponseWrapper[list])
def list_documents(db: Session = Depends(get_db),
                   user: AppUser = Depends(require_any(("source_registry", "R"), ("document_version", "R")))):
    # Registri sumber + Document Version: dapat dibaca semua peran kecuali Pemilik Bisnis/Kontrol (yang memakai Pencarian korpus)
    out = []
    sources = {s.id: s for s in db.scalars(select(RegulatorySource))}
    # urutkan dari dokumen yang paling baru didaftarkan; bila waktunya sama, urut nomor regulasi
    for d in db.scalars(select(Document).order_by(Document.created_at.desc(), Document.canonical_number)):
        vs = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == d.id)
                        .order_by(DocumentVersion.version_number)).all()
        labels = [{"dimension": lb.dimension, "value": lb.value, "state": lb.state}
                  for lb in db.scalars(select(TaxonomyLabel).where(TaxonomyLabel.document_id == d.id,
                                                                   TaxonomyLabel.state != "REMOVED"))
                  ] if allows(user, "taxonomy", "R") else []  # label hanya untuk peran yang berhak membaca Taxonomy
        src = sources.get(d.source_id)
        out.append({"id": str(d.id), "canonical_number": d.canonical_number, "title_id": d.title_id,
                    "status": d.status, "instrument_type": d.instrument_type, "issuer": d.issuer, "labels": labels,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                    "source": {"id": str(src.id), "name": src.name, "status": src.status} if src else None,
                    "versions": [{"id": str(v.id), "version_number": v.version_number, "state": v.state,
                                  "effective_date": str(v.effective_date),
                                  # [6a] cara teks versi diperoleh → UI menampilkan "teks via OCR"
                                  "extraction_method": v.extraction_method,
                                  # provenans (FR-RKM-002): asal & berkas aslinya
                                  "origin_url": v.origin_url, "file_name": v.file_name,
                                  "size_bytes": v.size_bytes, "has_file": bool(v.canonical_text_ref)} for v in vs]})
    return ResponseWrapper(data=out)


@router.post("/api/v1/corpus/documents/{doc_id}/versions",
             response_model=ResponseWrapper[dict])
async def upload_version(
    doc_id: str,
    file: UploadFile = File(...),
    effective_date: date = Form(...),
    origin_url: str = Form(...),  # FR-RKM-002: URL asal wajib, juga untuk unggahan manual
    db: Session = Depends(get_db),
    user: AppUser = Depends(require("ingestion", "X"))  # Ingestion dokumen: X = Analis Regulasi, Administrator Sistem
):
    doc = _get(db, Document, doc_id)

    # 0. Provenans: URL asal wajib berformat http(s); sumber dokumen harus ACTIVE
    if not origin_url.strip():
        raise AppError(422, "ORIGIN_URL_REQUIRED", "URL asal wajib diisi, juga untuk unggahan manual",
                       {"field": "origin_url"})
    origin_url = normalise_url(origin_url)
    source = db.get(RegulatorySource, doc.source_id)
    require_active(source)

    # 1. Validasi nama dan ekstensi file
    original_name = (file.filename or "").replace("\\", "/")
    filename = Path(original_name).name
    suffix = Path(filename).suffix.lower()

    if suffix not in {".pdf", ".txt"}:
        raise AppError(
            415,
            "UNSUPPORTED_FILE",
            "Format unggahan harus PDF atau TXT"
        )

    # 2. Membaca isi file
    data = await file.read()

    if not data:
        raise AppError(
            422,
            "EMPTY_FILE",
            "Berkas yang diunggah kosong"
        )

    # 3. Membatasi ukuran file maksimal 30 MB
    if len(data) > 30 * 1024 * 1024:
        raise AppError(
            413,
            "FILE_TOO_LARGE",
            "Ukuran berkas maksimum adalah 30 MB"
        )

    # 4. Memeriksa signature PDF
    if suffix == ".pdf" and b"%PDF-" not in data[:1024]:
        raise AppError(
            422,
            "INVALID_PDF",
            "Berkas tidak memiliki signature PDF yang valid"
        )

    # 4b. FR-RKM-002: berkas yang identik byte-per-byte sudah ada di korpus → tolak sebagai duplikat
    digest = hashlib.sha256(data).hexdigest()
    twin = db.execute(select(DocumentVersion, Document).join(Document, Document.id == DocumentVersion.document_id)
                      .where(DocumentVersion.sha256 == digest)).first()
    if twin:
        tv, td = twin
        audit(db, user.id, "DUPLICATE_SUSPECTED", "document", doc.id,
              after={"sha256": digest, "existing_document": td.canonical_number, "existing_version": tv.version_number})
        db.commit()
        raise AppError(409, "DUPLICATE_SUSPECTED",
                       f"Berkas yang sama persis sudah ada: {td.canonical_number} versi {tv.version_number}",
                       {"existing_document_id": str(td.id), "existing_version_id": str(tv.id),
                        "existing_document": td.canonical_number, "existing_version": tv.version_number})

    # 5. Membuat nama objek penyimpanan yang unik
    safe_doc = "".join(
        c if c.isalnum() or c in "-_" else "_"
        for c in doc.canonical_number
    )

    key = f"{safe_doc}/{uuid4().hex}{suffix}"

    content_type = (
        "application/pdf"
        if suffix == ".pdf"
        else "text/plain; charset=utf-8"
    )

    # 6. Ekstraksi teks dan segmentasi pasal
    dv, n = services.ingest_version(
        db,
        doc,
        filename,
        data,
        effective_date,
        origin_url,
        key
    )

    # 6b. Provenans berkas (FR-RKM-002)
    dv.file_name, dv.mime_type, dv.size_bytes, dv.uploaded_by = filename, content_type, len(data), user.id

    # 7. Menyimpan file ke storage
    if not put_object(key, data, content_type=content_type):
        db.rollback()
        raise AppError(
            503,
            "STORAGE_UNAVAILABLE",
            "Berkas gagal disimpan. Periksa konfigurasi "
            "dan hak akses storage."
        )

    # 8. Mencatat aktivitas upload
    audit(
        db,
        user.id,
        "VERSION_INGESTED",
        "document_version",
        dv.id,
        after={"provisions": n, "method": dv.extraction_method,  # [6b] catat juga cara teks diperoleh
               "origin_url": origin_url, "file": filename, "sha256": digest, "size_bytes": len(data)}
    )
    # [6b] FR-RKM-004: catat di jejak audit bahwa OCR dipakai dan di halaman mana
    if dv.ocr_pages:
        audit(db, user.id, "OCR_INVOKED", "document_version", dv.id, after={"pages": dv.ocr_pages})

        # 9. Menyimpan transaksi database
    db.commit()
    _share(db, doc.id)  # versi draf ikut dibagikan ke tim (data/korpus)

    return ResponseWrapper(
        data={
            "version_id": str(dv.id),
            "version_number": dv.version_number,
            "provisions_created": n,
            "state": dv.state,
            "extraction_method": dv.extraction_method,  # [6c] dipakai UI untuk menampilkan notifikasi OCR
            "ocr_pages": dv.ocr_pages,
            # URL asal di luar awalan yang diizinkan sumber → diterima, tetapi UI memberi peringatan
            "origin_outside_source": not url_allowed(source, origin_url)
        }
    )


@router.get("/api/v1/corpus/versions/{version_id}/file")
def version_file(version_id: str, db: Session = Depends(get_db),
                 _: AppUser = Depends(require("document_version", "R"))):  # Document Version: R = semua kecuali Pemilik
    """Berkas asli (PDF/TXT) sebuah versi, untuk dibandingkan dengan teks pasal (mis. memeriksa hasil OCR)."""
    dv = _get(db, DocumentVersion, version_id)
    data = get_object(dv.canonical_text_ref) if dv.canonical_text_ref else None
    if data is None:
        raise AppError(404, "FILE_NOT_STORED", "Berkas asli versi ini tidak tersimpan (mis. data sintetis)")
    name = dv.file_name or Path(dv.canonical_text_ref).name
    media = dv.mime_type or ("application/pdf" if name.lower().endswith(".pdf") else "text/plain; charset=utf-8")
    # inline: dibuka di tab browser, bukan langsung diunduh
    return Response(content=data, media_type=media,
                    headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(name)}"})


@router.patch("/api/v1/corpus/documents/{doc_id}", response_model=ResponseWrapper[dict])
def update_document(doc_id: str, body: DocumentUpdate, db: Session = Depends(get_db),
                    user: AppUser = Depends(require("doc_status", "U"))):  # data dokumen: U = Analis Regulasi
    """Perbaiki judul/jenis/penerbit kapan saja; nomor regulasi hanya selama belum pernah terbit
    (versi terbit sudah disitasi kewajiban & laporan dengan nomor itu)."""
    doc = _get(db, Document, doc_id)
    before = {"canonical_number": doc.canonical_number, "title_id": doc.title_id,
              "instrument_type": doc.instrument_type, "issuer": doc.issuer}
    changes = {k: v.strip() for k, v in body.model_dump(exclude_none=True).items()}
    if any(not v for v in changes.values()):
        raise AppError(422, "VALIDATION_ERROR", "Isian tidak boleh kosong", {"fields": [k for k, v in changes.items() if not v]})
    new_number = changes.get("canonical_number")
    if new_number and new_number != doc.canonical_number:
        frozen = db.scalar(select(func.count()).select_from(DocumentVersion).where(
            DocumentVersion.document_id == doc.id, DocumentVersion.state.in_(("PUBLISHED", "WITHDRAWN"))))
        if frozen:
            raise AppError(409, "NUMBER_FROZEN", "Nomor regulasi tidak dapat diubah karena dokumen pernah terbit")
        if db.scalar(select(Document.id).where(Document.canonical_number == new_number)):
            raise AppError(409, "DUPLICATE", "Nomor regulasi sudah terdaftar")
    for k, v in changes.items():
        setattr(doc, k, v)
    after = {k: getattr(doc, k) for k in before}
    if after == before:
        return ResponseWrapper(data={"id": str(doc.id), "changed": False})
    audit(db, user.id, "DOCUMENT_UPDATED", "document", doc.id, before=before, after=after)
    db.commit()
    _share(db, doc.id)  # perubahan (termasuk ganti nomor) ikut dibagikan ke tim
    return ResponseWrapper(data={"id": str(doc.id), "changed": True})


@router.get("/api/v1/corpus/versions/{version_id}/provisions", response_model=ResponseWrapper[list])
def list_provisions(version_id: str, db: Session = Depends(get_db),
                    _: AppUser = Depends(require("document_version", "R"))):
    _get(db, DocumentVersion, version_id)
    rows = db.execute(select(ProvisionVersion, Provision)
                      .join(Provision, Provision.id == ProvisionVersion.provision_id)
                      .where(ProvisionVersion.document_version_id == version_id)
                      .order_by(ProvisionVersion.sequence)).all()
    return ResponseWrapper(data=[{"provision_version_id": str(pv.id), "number_label": p.number_label,
                                  "path": p.hierarchical_path, "text": pv.text,
                                  "confidence": float(pv.segmentation_confidence),
                                  "corrected_by_human": pv.corrected_by_human,
                                  "low_confidence_text": pv.low_confidence_text  # [6d] true → badge "Teks OCR" di UI
                                  } for pv, p in rows])


@router.patch("/api/v1/corpus/provision-versions/{pv_id}", response_model=ResponseWrapper[dict])
def correct_provision(pv_id: str, body: ProvisionCorrection, db: Session = Depends(get_db),
                      user: AppUser = Depends(require("provision_correction", "U"))):  # Koreksi segmentasi: U = Analis
    pv = _get(db, ProvisionVersion, pv_id)
    dv = db.get(DocumentVersion, pv.document_version_id)
    if dv.state not in (VersionState.SEGMENTED_DRAFT.value, VersionState.UNDER_CORRECTION.value):
        raise AppError(409, "VERSION_IMMUTABLE", "Versi yang sudah dipublikasikan tidak dapat diubah")
    # [6e] validasi + koreksi sekaligus menghapus tanda OCR
    if not body.text.strip():  # cegah pasal tersimpan kosong
        raise AppError(422, "EMPTY_TEXT", "Teks pasal tidak boleh kosong")
    before = {"text": pv.text, "low_confidence_text": pv.low_confidence_text}  # nilai lama untuk jejak audit
    # koreksi manual sekaligus menandai teks OCR sudah diperiksa analis
    pv.text, pv.corrected_by_human, pv.low_confidence_text = body.text, True, False
    dv.state = VersionState.UNDER_CORRECTION.value  # versi berstatus "sedang dikoreksi" (masih draf)
    audit(db, user.id, "PROVISION_CORRECTED", "provision_version", pv.id, before=before, after={"text": body.text})
    db.commit()
    _share(db, dv.document_id)  # koreksi teks ikut dibagikan ke tim
    return ResponseWrapper(data={"id": str(pv.id)})


# [6e] ENDPOINT BARU: tombol "Konfirmasi teks" di UI memanggil endpoint ini (khusus Analis)
@router.post("/api/v1/corpus/provision-versions/{pv_id}/confirm-text", response_model=ResponseWrapper[dict])
def confirm_text(pv_id: str, db: Session = Depends(get_db),
                 user: AppUser = Depends(require("provision_correction", "U"))):
    """FR-RKM-004: analis menyatakan teks hasil OCR sudah sesuai PDF aslinya (tanpa mengubah teks)."""
    pv = _get(db, ProvisionVersion, pv_id)              # pasal yang dikonfirmasi (404 bila tidak ada)
    dv = db.get(DocumentVersion, pv.document_version_id)  # versi dokumennya
    # hanya versi draf yang boleh diubah; versi terbit sudah beku
    if dv.state not in (VersionState.SEGMENTED_DRAFT.value, VersionState.UNDER_CORRECTION.value):
        raise AppError(409, "VERSION_IMMUTABLE", "Versi yang sudah dipublikasikan tidak dapat diubah")
    # pasal yang bukan dari OCR (atau sudah dikonfirmasi) tidak perlu dikonfirmasi lagi
    if not pv.low_confidence_text:
        raise AppError(409, "NOTHING_TO_CONFIRM", "Pasal ini bukan teks OCR yang menunggu konfirmasi")
    # hapus tanda OCR + tandai sudah diperiksa manusia; teks pasal tidak diubah
    pv.low_confidence_text, pv.corrected_by_human = False, True
    audit(db, user.id, "TEXT_CONFIRMED_BY_ANALYST", "provision_version", pv.id)  # siapa mengonfirmasi, kapan
    db.commit()
    _share(db, dv.document_id)  # konfirmasi OCR ikut dibagikan ke tim
    return ResponseWrapper(data={"id": str(pv.id), "low_confidence_text": False})


@router.post("/api/v1/corpus/versions/{version_id}/publish", response_model=ResponseWrapper[dict])
def publish(version_id: str, db: Session = Depends(get_db),
            user: AppUser = Depends(require("document_version", "C"))):  # menerbitkan = membuat Document Version imutabel
    dv = _get(db, DocumentVersion, version_id)
    services.publish_version(db, dv)
    audit(db, user.id, "VERSION_PUBLISHED", "document_version", dv.id)
    db.commit()
    _share(db, dv.document_id)  # status terbit ikut dibagikan ke tim
    return ResponseWrapper(data={"version_id": str(dv.id), "state": dv.state})


@router.get("/api/v1/corpus/search", response_model=ResponseWrapper[list])
def search(q: str, limit: int = 10, db: Session = Depends(get_db),
           _: AppUser = Depends(require("corpus_search", "R"))):  # Pencarian korpus: semua peran
    return ResponseWrapper(data=services.search_provisions(db, q, min(limit, 50)))


@router.post("/api/v1/corpus/changes", response_model=ResponseWrapper[dict])
def compute(body: ChangeRequest, db: Session = Depends(get_db),
            user: AppUser = Depends(require("change_detection", "X"))):  # Eksekusi deteksi perubahan: X = Analis, Admin
    base, new = _get(db, DocumentVersion, body.base_version_id), _get(db, DocumentVersion, body.new_version_id)
    if base.state != "PUBLISHED" or new.state != "PUBLISHED":
        raise AppError(409, "VERSION_NOT_PUBLISHED", "Kedua versi harus berstatus PUBLISHED (W5)")
    existing = db.scalar(select(ChangeSet).where(ChangeSet.base_version_id == base.id, ChangeSet.new_version_id == new.id))
    if existing:  # idempoten: tampilkan changeset yang sudah ada beserta status reviunya
        from app.corpus.review import get_changeset
        data = get_changeset(str(existing.id), db, user).data
        return ResponseWrapper(data={"change_set_id": str(existing.id), "changes": data["changes"], "existing": True})
    cs, changes = services.compute_changes(db, base, new)
    cs.created_by = user.id
    audit(db, user.id, "CHANGESET_COMPUTED", "change_set", cs.id, after={"changes": len(changes)})
    prov = {p.id: p for p in db.scalars(select(Provision).where(Provision.document_id == base.document_id))}
    out = [{"id": str(c.id), "review_state": c.review_state or "DETECTED", "provision": prov[c.provision_id].number_label, "change_type": c.change_type,
            "similarity": float(c.similarity or 0), "is_material": c.is_material, "diff_html": c.diff_html}
           for c in changes]
    db.commit()
    return ResponseWrapper(data={"change_set_id": str(cs.id), "changes": sorted(out, key=lambda x: x["provision"])})


# ---------- hapus & tarik (korpus dan versi korpus) ----------
class WithdrawRequest(BaseModel):
    """Isi body untuk tarik versi: alasan wajib (dicatat di jejak audit)."""
    reason: str


def _version_refs(db: Session, dv: DocumentVersion) -> dict:
    """Hitung rekaman kepatuhan yang menyitasi versi ini; selama masih ada, versi tidak boleh hilang dari korpus."""
    from app.compliance.models import ApplicabilityDecision, Obligation
    pv_ids = select(ProvisionVersion.id).where(ProvisionVersion.document_version_id == dv.id)
    return {
        "kewajiban": db.scalar(select(func.count()).select_from(Obligation)
                               .where(Obligation.primary_citation_id.in_(pv_ids))) or 0,
        "keputusan_keberlakuan": db.scalar(select(func.count()).select_from(ApplicabilityDecision)
                                           .where(ApplicabilityDecision.target_version_id == dv.id)) or 0,
        "perbandingan_versi": db.scalar(select(func.count()).select_from(ChangeSet).where(
            (ChangeSet.base_version_id == dv.id) | (ChangeSet.new_version_id == dv.id))) or 0,
    }


def _block_if_referenced(refs: dict, what: str) -> None:
    used = {k: v for k, v in refs.items() if v}
    if used:
        detail = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in used.items())
        raise AppError(409, "STILL_REFERENCED", f"{what} masih dirujuk oleh {detail}", used)


def _delete_draft_version(db: Session, dv: DocumentVersion) -> int:
    # Urutan: hapus teks pasal versi ini → hapus identitas pasal yatim → hapus versinya (urutan FK)
    """Hapus versi draf beserta pasalnya; identitas pasal (Provision) yang tidak dipakai versi lain ikut dihapus."""
    pvs = db.scalars(select(ProvisionVersion).where(ProvisionVersion.document_version_id == dv.id)).all()
    prov_ids = {pv.provision_id for pv in pvs}
    for pv in pvs:
        db.delete(pv)
    db.flush()
    for pid in prov_ids:
        if not db.scalar(select(ProvisionVersion.id).where(ProvisionVersion.provision_id == pid).limit(1)):
            db.delete(db.get(Provision, pid))
    db.delete(dv)
    db.flush()
    return len(pvs)


@router.delete("/api/v1/corpus/versions/{version_id}", response_model=ResponseWrapper[dict])
def delete_version(version_id: str, db: Session = Depends(get_db),
                   user: AppUser = Depends(require("ingestion", "X"))):  # membatalkan ingestion draf = aksi X pada Ingestion
    """Hanya versi DRAF yang dapat dihapus. Versi terbit imutabel (trigger DB) → gunakan 'tarik versi'."""
    dv = _get(db, DocumentVersion, version_id)
    # 1) versi terbit/ditarik dikunci trigger DB → tolak
    if dv.state in (VersionState.PUBLISHED.value, VersionState.WITHDRAWN.value):
        raise AppError(409, "VERSION_IMMUTABLE",
                       "Versi yang sudah terbit tidak dapat dihapus; gunakan 'Tarik versi' agar riwayatnya tetap dapat diaudit")
    # 2) tolak bila masih dipakai keputusan keberlakuan/kewajiban/perbandingan
    _block_if_referenced(_version_refs(db, dv), f"Versi {dv.version_number}")
    # 3) simpan ringkasan sebelum dihapus untuk jejak audit
    snapshot = {"document_id": str(dv.document_id), "version_number": dv.version_number, "sha256": dv.sha256,
                "state": dv.state, "origin_url": dv.origin_url}
    try:
        n = _delete_draft_version(db, dv)
    except DBAPIError as e:
        db.rollback()
        raise AppError(409, "STILL_REFERENCED", f"Versi masih dirujuk data lain: {str(e.orig).splitlines()[0]}")
    audit(db, user.id, "VERSION_DELETED", "document_version", uuid.UUID(version_id), before={**snapshot, "provisions": n})
    db.commit()
    _share(db, snapshot["document_id"])  # penanda hapus agar laptop lain ikut menghapus draf ini
    return ResponseWrapper(data={"deleted_version_id": version_id, "provisions_deleted": n})


@router.post("/api/v1/corpus/versions/{version_id}/withdraw", response_model=ResponseWrapper[dict])
def withdraw_version(version_id: str, body: WithdrawRequest, db: Session = Depends(get_db),
                     user: AppUser = Depends(require("doc_status", "U"))):  # Perubahan status dokumen: U = Analis
    """Versi terbit ditarik (WITHDRAWN), bukan dihapus: tidak lagi dipakai pencarian/copilot/ekstraksi,
    tetapi teks dan jejaknya tetap tersimpan. Diblokir bila masih ada kewajiban yang menyitasinya."""
    dv = _get(db, DocumentVersion, version_id)
    if dv.state != VersionState.PUBLISHED.value:
        raise AppError(409, "INVALID_STATE", f"Hanya versi terbit yang dapat ditarik (status sekarang {dv.state})")
    if not body.reason.strip():
        raise AppError(422, "REASON_REQUIRED", "Alasan penarikan wajib diisi", {"field": "reason"})
    # kewajiban yang menyitasi versi ini akan kehilangan dasar → tolak
    refs = _version_refs(db, dv)
    _block_if_referenced({"kewajiban": refs["kewajiban"]}, f"Versi {dv.version_number}")
    # trigger DB hanya mengizinkan PUBLISHED → WITHDRAWN (teks pasal tidak berubah)
    dv.state = VersionState.WITHDRAWN.value
    db.flush()
    doc = db.get(Document, dv.document_id)
    if not db.scalar(select(DocumentVersion.id).where(DocumentVersion.document_id == doc.id,
                                                      DocumentVersion.state == VersionState.PUBLISHED.value).limit(1)):
        doc.status = "DRAFT"  # tidak ada lagi versi berlaku di korpus
    audit(db, user.id, "VERSION_WITHDRAWN", "document_version", dv.id,
          before={"state": "PUBLISHED"}, after={"state": dv.state, "reason": body.reason.strip()})
    db.commit()
    _share(db, dv.document_id)  # penarikan ikut dibagikan ke tim
    return ResponseWrapper(data={"version_id": str(dv.id), "state": dv.state, "document_status": doc.status})


@router.delete("/api/v1/corpus/documents/{doc_id}", response_model=ResponseWrapper[dict])
def delete_document(doc_id: str, db: Session = Depends(get_db),
                    user: AppUser = Depends(require("source_registry", "D"))):  # D hanya Administrator Sistem
    """Dokumen hanya dapat dihapus bila belum pernah terbit (semua versinya draf) dan tidak dirujuk relasi."""
    from app.corpus.models import Relationship
    doc = _get(db, Document, doc_id)
    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)).all()
    # 1) dokumen yang pernah terbit tidak boleh hilang dari riwayat
    if any(v.state in (VersionState.PUBLISHED.value, VersionState.WITHDRAWN.value) for v in versions):
        raise AppError(409, "DOCUMENT_HAS_PUBLISHED_VERSION",
                       "Dokumen yang pernah terbit tidak dapat dihapus karena teksnya bisa sudah disitasi; tarik versinya saja")
    rels = db.scalars(select(Relationship).where((Relationship.source_document_id == doc.id)
                                                 | (Relationship.target_document_id == doc.id))).all()
    # 2) relasi terkonfirmasi (mis. mencabut dokumen lain) tidak boleh putus
    if any(r.state == "CONFIRMED" for r in rels):
        raise AppError(409, "STILL_REFERENCED", "Dokumen masih memiliki relasi terkonfirmasi dengan dokumen lain")
    for v in versions:
        _block_if_referenced(_version_refs(db, v), f"Versi {v.version_number}")
    snapshot = {"canonical_number": doc.canonical_number, "title_id": doc.title_id, "versions": len(versions)}
    # 3) hapus berurutan: relasi usulan → label → versi draf & pasalnya → identitas pasal → dokumen
    try:
        for r in rels:
            db.delete(r)
        for lb in db.scalars(select(TaxonomyLabel).where(TaxonomyLabel.document_id == doc.id)):
            db.delete(lb)
        for v in versions:
            _delete_draft_version(db, v)
        for p in db.scalars(select(Provision).where(Provision.document_id == doc.id)):
            db.delete(p)
        db.flush()
        db.delete(doc)
        db.flush()
    except DBAPIError as e:
        db.rollback()
        raise AppError(409, "STILL_REFERENCED", f"Dokumen masih dirujuk data lain: {str(e.orig).splitlines()[0]}")
    audit(db, user.id, "DOCUMENT_DELETED", "document", uuid.UUID(doc_id), before=snapshot)
    db.commit()
    _share(db)  # penanda hapus dokumen untuk laptop lain
    return ResponseWrapper(data={"deleted_document_id": doc_id})