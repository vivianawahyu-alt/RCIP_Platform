import hashlib
import uuid
from datetime import date

import pymupdf  # PyMuPDF
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.corpus.diff_engine import compare_texts
from app.corpus.models import (Change, ChangeSet, Document, DocumentVersion, Provision, ProvisionVersion,
                               RegulatorySource)
from app.corpus.segmenter import Segment, segment_text
from app.shared.errors import AppError
from app.shared.schemas import (CitationResolveResponse, DocumentDetailDTO, DocumentVersionDetailDTO,
                                ResolvedCitationDTO)
from app.shared.vocabularies import ChangeType, DocumentStatus, ProvisionType, VersionState


def extract_text(filename: str, data: bytes) -> str:
    suffix = (
        filename.lower().rsplit(".", 1)[-1]
        if "." in filename else ""
    )

    # Validasi file kosong
    if not data:
        raise AppError(
            422,
            "EMPTY_FILE",
            "Berkas yang diunggah kosong"
        )

    # Membaca PDF
    if suffix == "pdf":

        if b"%PDF-" not in data[:1024]:
            raise AppError(
                422,
                "INVALID_PDF",
                "Berkas bukan PDF yang valid"
            )

        try:
            with pymupdf.open(
                stream=data,
                filetype="pdf"
            ) as doc:

                # Memeriksa PDF yang dilindungi password
                if doc.needs_pass:
                    raise AppError(
                        422,
                        "PDF_PASSWORD_PROTECTED",
                        "PDF dilindungi kata sandi."
                    )

                # Mengekstrak teks seluruh halaman
                return "\n".join(
                    page.get_text("text")
                    for page in doc
                )

        except AppError:
            raise

        except Exception as exc:
            raise AppError(
                422,
                "INVALID_PDF",
                "PDF rusak atau tidak dapat dibaca. "
                "Coba ekspor ulang PDF lalu unggah kembali."
            ) from exc

    # Membaca file TXT
    if suffix == "txt":
        try:
            return data.decode("utf-8-sig")

        except UnicodeDecodeError as exc:
            raise AppError(
                422,
                "INVALID_TEXT_FILE",
                "File TXT harus menggunakan encoding UTF-8."
            ) from exc

    raise AppError(
        415,
        "UNSUPPORTED_FILE",
        "Hanya berkas .pdf atau .txt yang didukung"
    )


def get_or_create_source(db: Session, name: str, category: str, issuer: str, base_url: str) -> RegulatorySource:
    src = db.scalar(select(RegulatorySource).where(RegulatorySource.name == name))
    if not src:
        src = RegulatorySource(name=name, category=category, issuer_name=issuer, base_url=base_url, status="ACTIVE")
        db.add(src)
        db.flush()
    return src


def persist_segments(
    db: Session,
    dv: DocumentVersion,
    segments: list[Segment]
) -> int:

    # 1. Kelompokkan segmen berdasarkan provision_key
    grouped_segments = {}

    for seg in segments:
        key = seg.provision_key

        if not key:
            raise AppError(
                422,
                "INVALID_PROVISION_KEY",
                "Segmen memiliki identitas pasal kosong."
            )

        if key not in grouped_segments:
            grouped_segments[key] = {
                "number_label": seg.number_label,
                "hierarchical_path": seg.hierarchical_path,
                "texts": [],
                "confidence": seg.confidence
            }

        grouped_segments[key]["texts"].append(seg.text)

        grouped_segments[key]["confidence"] = max(
            grouped_segments[key]["confidence"],
            seg.confidence
        )

    # 2. Simpan satu ProvisionVersion untuk setiap pasal
    for seq, (key, item) in enumerate(
        grouped_segments.items(),
        start=1
    ):

        prov = db.scalar(
            select(Provision).where(
                Provision.document_id == dv.document_id,
                Provision.provision_key == key
            )
        )

        if not prov:
            prov = Provision(
                document_id=dv.document_id,
                provision_key=key,
                provision_type=ProvisionType.PASAL.value,
                number_label=item["number_label"],
                hierarchical_path=item["hierarchical_path"]
            )

            db.add(prov)
            db.flush()

        # Gabungkan teks jika pasal ditemukan lebih dari sekali
        combined_text = "\n\n".join(
            text.strip()
            for text in item["texts"]
            if text and text.strip()
        )

        db.add(
            ProvisionVersion(
                provision_id=prov.id,
                document_version_id=dv.id,
                sequence=seq,
                text=combined_text,
                segmentation_confidence=item["confidence"]
            )
        )

    db.flush()

    return len(grouped_segments)


def ingest_version(db: Session, document: Document, filename: str, data: bytes, effective_date: date,
                   origin_url: str, object_key: str) -> tuple[DocumentVersion, int]:
    raw = extract_text(filename, data)
    segments = segment_text(raw)
    if not segments:
        raise AppError(422, "NO_PROVISIONS_FOUND", "Tidak ada Pasal terdeteksi pada dokumen")
    next_no = (db.scalar(select(func.max(DocumentVersion.version_number))
                         .where(DocumentVersion.document_id == document.id)) or 0) + 1
    dv = DocumentVersion(document_id=document.id, version_number=next_no, sha256=hashlib.sha256(data).hexdigest(),
                         origin_url=origin_url, canonical_text_ref=object_key, effective_date=effective_date,
                         state=VersionState.PARSING.value)
    db.add(dv)
    db.flush()
    n = persist_segments(db, dv, segments)
    dv.state = VersionState.SEGMENTED_DRAFT.value
    return dv, n


def publish_version(db: Session, dv: DocumentVersion) -> None:
    if dv.state not in (VersionState.SEGMENTED_DRAFT.value, VersionState.UNDER_CORRECTION.value):
        raise AppError(409, "INVALID_STATE", f"Versi berstatus {dv.state} tidak dapat dipublikasikan")
    dv.state = VersionState.PUBLISHED.value
    doc = db.get(Document, dv.document_id)
    doc.status = DocumentStatus.IN_FORCE.value


def resolve_citations(db: Session, ids: list[str]) -> CitationResolveResponse:
    valid: dict[str, uuid.UUID] = {}
    for s in ids:
        try:
            valid[s] = uuid.UUID(s)
        except ValueError:
            pass
    rows = {}
    if valid:
        stmt = (select(ProvisionVersion, Provision, DocumentVersion, Document)
                .join(Provision, ProvisionVersion.provision_id == Provision.id)
                .join(DocumentVersion, ProvisionVersion.document_version_id == DocumentVersion.id)
                .join(Document, DocumentVersion.document_id == Document.id)
                .where(ProvisionVersion.id.in_(list(valid.values()))))
        rows = {str(r[0].id): r for r in db.execute(stmt).all()}
    resolved, unresolved = [], []
    for s in ids:
        r = rows.get(str(valid.get(s))) if s in valid else None
        if not r:
            unresolved.append(s)
            continue
        pv, p, dv, d = r
        resolved.append(ResolvedCitationDTO(
            provision_version_id=str(pv.id), text=pv.text, number_label=p.number_label,
            provision_type=p.provision_type, hierarchical_path=p.hierarchical_path,
            document_version=DocumentVersionDetailDTO(id=str(dv.id), version_number=dv.version_number,
                                                     effective_date=str(dv.effective_date),
                                                     is_partial=dv.is_partial, state=dv.state),
            document=DocumentDetailDTO(id=str(d.id), canonical_number=d.canonical_number,
                                       instrument_type=d.instrument_type, issuer=d.issuer,
                                       title_id=d.title_id, status=d.status)))
    return CitationResolveResponse(resolved=resolved, unresolved=unresolved)


def search_provisions(db: Session, q: str, limit: int = 10) -> list[dict]:
    rows = db.execute(text("""
        SELECT pv.id, pv.text, p.number_label, d.canonical_number, dv.version_number,
               ts_rank(pv.text_search, plainto_tsquery('indonesian', :q)) AS rank
        FROM corpus.provision_version pv
        JOIN corpus.provision p ON p.id = pv.provision_id
        JOIN corpus.document_version dv ON dv.id = pv.document_version_id
        JOIN corpus.document d ON d.id = dv.document_id
        WHERE dv.state = 'PUBLISHED' AND pv.text_search @@ plainto_tsquery('indonesian', :q)
        ORDER BY rank DESC LIMIT :n"""), {"q": q, "n": limit}).all()
    return [{"provision_version_id": str(r.id), "text": r.text, "number_label": r.number_label,
             "canonical_number": r.canonical_number, "version_number": r.version_number,
             "rank": float(r.rank)} for r in rows]


def compute_changes(db: Session, base: DocumentVersion, new: DocumentVersion, correlation_id=None) -> tuple[ChangeSet, list[Change]]:
    if base.document_id != new.document_id:
        raise AppError(422, "DIFFERENT_DOCUMENTS", "Kedua versi harus dari dokumen yang sama")
    cs = ChangeSet(base_version_id=base.id, new_version_id=new.id)
    db.add(cs)
    db.flush()
    bmap = {pv.provision_id: pv for pv in db.scalars(select(ProvisionVersion).where(ProvisionVersion.document_version_id == base.id))}
    nmap = {pv.provision_id: pv for pv in db.scalars(select(ProvisionVersion).where(ProvisionVersion.document_version_id == new.id))}
    changes: list[Change] = []
    for pid in bmap.keys() | nmap.keys():
        b, n = bmap.get(pid), nmap.get(pid)
        if b and n:
            r = compare_texts(b.text, n.text)
            if r["change_type"] is None:
                continue
            c = Change(change_set_id=cs.id, provision_id=pid, base_pv_id=b.id, new_pv_id=n.id,
                       change_type=ChangeType.TEXT_MODIFIED.value, similarity=r["similarity"],
                       is_material=r["is_material"], diff_html=r["diff_html"], review_state="DETECTED")
        elif n:
            c = Change(change_set_id=cs.id, provision_id=pid, new_pv_id=n.id, similarity=0,
                       change_type=ChangeType.PROVISION_ADDED.value, is_material=True, review_state="DETECTED")
        else:
            c = Change(change_set_id=cs.id, provision_id=pid, base_pv_id=b.id, similarity=0,
                       change_type=ChangeType.PROVISION_DELETED.value, is_material=True, review_state="DETECTED")
        db.add(c)
        changes.append(c)
    db.flush()
    # W5: deteksi tidak memicu apa pun di hilir; hanya MATERIAL_CONFIRMED (titik kendali #1) yang memicu.
    return cs, changes
