"""Posisi hukum Peninjau Hukum disimpan di tabel sendiri (compliance.legal_position), berversi.

Objek yang dieskalasi (keputusan keberlakuan, kewajiban, tinjauan perubahan) hanya menyimpan
legal_position_id + legal_position_version. Jejak audit tetap memakai audit log umum di endpoint masing-masing.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance.common import require_citations, require_text, sid
from app.compliance.models import LegalPosition, LegalPositionCitation
from app.corpus.models import Document, DocumentVersion, Provision, ProvisionVersion


def record_legal_position(db: Session, subject, subject_type: str, answer: str,
                          citation_ids: list[str], reviewer_id) -> LegalPosition:
    """Buat versi baru posisi hukum untuk subject, lalu tautkan ke subject (legal_position_id + versi)."""
    answer = require_text(answer, "answer")
    require_citations(db, citation_ids)                       # sitasi wajib, teresolusi, dan terbit
    last = db.scalar(select(func.max(LegalPosition.version)).where(
        LegalPosition.subject_type == subject_type, LegalPosition.subject_id == subject.id)) or 0
    lp = LegalPosition(subject_type=subject_type, subject_id=subject.id, version=last + 1,
                       question=subject.legal_question, position_text=answer, reviewer_id=reviewer_id)
    db.add(lp)
    db.flush()
    for pv_id in dict.fromkeys(i for i in citation_ids if i):  # buang duplikat, urutan tetap
        db.add(LegalPositionCitation(legal_position_id=lp.id, provision_version_id=pv_id))
    subject.legal_position_id, subject.legal_position_version = lp.id, lp.version
    return lp


def legal_position_view(db: Session, legal_position_id, names: dict) -> dict:
    """Field posisi hukum untuk respons API (bentuknya sama dengan sebelumnya agar tampilan web tetap jalan)."""
    lp = db.get(LegalPosition, legal_position_id) if legal_position_id else None
    if lp is None:
        return {"legal_position_id": None, "legal_position_version": None, "legal_answer": None, "legal_reviewer": None}
    rows = db.execute(select(Document.canonical_number, Provision.number_label, DocumentVersion.version_number)
                      .select_from(LegalPositionCitation)
                      .join(ProvisionVersion, ProvisionVersion.id == LegalPositionCitation.provision_version_id)
                      .join(Provision, Provision.id == ProvisionVersion.provision_id)
                      .join(DocumentVersion, DocumentVersion.id == ProvisionVersion.document_version_id)
                      .join(Document, Document.id == DocumentVersion.document_id)
                      .where(LegalPositionCitation.legal_position_id == lp.id)).all()
    cites = "; ".join(f"{doc} {label} (v{ver})" for doc, label, ver in rows)
    return {"legal_position_id": str(lp.id), "legal_position_version": lp.version,
            "legal_answer": f"{lp.position_text}\n\nSitasi: {cites}" if cites else lp.position_text,
            "legal_reviewer": names.get(sid(lp.reviewer_id))}