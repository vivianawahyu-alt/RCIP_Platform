"""W4 relasi & silsilah, W5 reviu perubahan (titik kendali #1), W6 taksonomi.

W5: DETECTED → IN_REVIEW → VALIDATED → MATERIAL_CONFIRMED (Manajer, ≠ validator) | REJECTED | ESCALATED.
Hanya MATERIAL_CONFIRMED yang memicu evaluasi ulang hilir; sistem menandai, tidak menyunting.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance.common import get_or_404, iso, now, require_citations, require_text, sid, user_names
from app.compliance.models import ApplicabilityDecision, Control, Obligation, ObligationControlMap
from app.corpus.models import (Change, ChangeSet, Document, DocumentVersion, Provision, ProvisionVersion, Relationship,
                               TaxonomyLabel)
from app.platform.governance import audit, enforce_maker_checker, record_approval
from app.platform.models import AppUser, Outbox
from app.platform.permissions import require
from app.shared.database import get_db
from app.shared.errors import AppError
from app.shared.schemas import ResponseWrapper
from app.shared.vocabularies import AppRole, ControlPoint

router = APIRouter(prefix="/api/v1/corpus", tags=["corpus-review"])
R = AppRole
# Otorisasi = matriks RBAC (app/shared/rbac_matrix.py). Nama di bawah hanya pintasan agar baris endpoint tetap pendek.
CHANGE_READ = require("change_review", "R")              # RA, CO, LR, CM, IA   (Pemilik Kontrol, Eksekutif, Admin: tanpa akses)
# validasi/eskalasi = aksi U pada Tinjauan Change; dipersempit ke Analis & Pejabat (maker). Peninjau Hukum memakai U lewat legal-answer.
CHANGE_MAKER = require("change_review", "U", only=[R.REGULATORY_ANALYST, R.COMPLIANCE_OFFICER])
CHANGE_LEGAL = require("change_review", "U", only=[R.LEGAL_REVIEWER])
CHANGE_APPROVE = require("change_review", "A")           # Manajer Kepatuhan (titik kendali #1)
REL_READ = require("relationship", "R")
REL_CREATE = require("relationship", "C")
REL_UPDATE = require("relationship", "U")
REL_DELETE = require("relationship", "D")
STATUS_APPROVE = require("doc_status", "A")              # konfirmasi relasi = mengubah status dokumen → persetujuan Manajer
TAX_READ = require("taxonomy", "R")
TAX_WRITE = require("taxonomy", "C")                     # RA, CO, Admin
TAX_UPDATE = require("taxonomy", "U")
TAX_DELETE = require("taxonomy", "D")                    # hapus lunak label: hanya Administrator Sistem

SEMANTIC_TYPES = {"DEFINITION_CHANGED", "OBLIGATION_ADDED", "OBLIGATION_REMOVED", "OBLIGATION_MODIFIED",
                  "DEADLINE_CHANGED", "THRESHOLD_CHANGED", "SCOPE_CHANGED", "SANCTION_CHANGED",
                  "EFFECTIVE_DATE_CHANGED", "EDITORIAL_ONLY"}
REVIEWABLE = {"PENDING_EFFECTIVE", "VALIDATED", "ACTIVE"}

# W6: saran label berbasis aturan (kata kunci judul → label). Label bebas tidak diperkenankan (E6.1).
THEME_RULES = {"teknologi informasi": "Risiko TI dan siber", "siber": "Risiko TI dan siber",
               "pencucian uang": "AML/CFT", "terorisme": "AML/CFT", "konsumen": "Perlindungan konsumen",
               "pembayaran": "Sistem pembayaran", "tata kelola": "Tata kelola", "manajemen risiko": "Manajemen risiko",
               "laporan": "Pelaporan dan pengungkapan", "pelaporan": "Pelaporan dan pengungkapan",
               "data pribadi": "Pelindungan data pribadi", "keberlanjutan": "Tata kelola",
               "inovasi": "Fintech dan inovasi digital", "outsourcing": "Manajemen risiko", "alih daya": "Manajemen risiko"}
POPULATION_RULES = {"bank umum": "Bank umum", "bpr": "BPR/BPRS", "penyelenggara jasa pembayaran": "Penyedia jasa pembayaran",
                    "jasa pembayaran": "Penyedia jasa pembayaran", "lembaga jasa keuangan": "Lembaga jasa keuangan (umum)",
                    "pinjam meminjam": "Penyelenggara LPBBTI", "perusahaan pembiayaan": "Perusahaan pembiayaan"}
ALLOWED_LABELS = {"THEME": set(THEME_RULES.values()), "POPULATION": set(POPULATION_RULES.values()),
                  "OBLIGATION_CHARACTER": {"Pelaporan", "Notifikasi", "Tata kelola", "Pengendalian operasional", "Larangan",
                                           "Penatausahaan dokumen", "Pengungkapan", "Perizinan"},
                  "MATERIALITY": {"Tinggi", "Sedang", "Rendah"}}


class ValidateChangeIn(BaseModel):
    material: bool
    semantic_type: Optional[str] = None
    reason: str


class QuestionIn(BaseModel):
    question: str


class AnswerIn(BaseModel):
    answer: str
    citation_provision_version_ids: list[str] = []  # wajib ≥ 1 (FRD Eksibit 26); divalidasi require_citations


class DecisionIn(BaseModel):
    outcome: str  # APPROVED | REJECTED
    reason: Optional[str] = None


class RelationshipIn(BaseModel):
    source_document_id: str
    target_document_id: str
    relation_type: str
    citing_provision_version_id: Optional[str] = None
    note: Optional[str] = None


class LabelIn(BaseModel):
    dimension: str
    value: str


class ReasonIn(BaseModel):
    reason: str


# ---------- W5 ----------
def _change_dto(c: Change, label: str, names: dict) -> dict:
    return {"id": str(c.id), "provision": label, "change_type": c.change_type, "similarity": float(c.similarity or 0),
            "is_material": c.is_material, "diff_html": c.diff_html, "review_state": c.review_state,
            "semantic_type": c.semantic_type, "analyst_material": c.analyst_material, "review_reason": c.review_reason,
            "legal_question": c.legal_question, "legal_answer": c.legal_answer,
            "validated_by": names.get(sid(c.validated_by)), "validated_by_id": sid(c.validated_by),
            "validated_at": iso(c.validated_at), "confirmed_by": names.get(sid(c.confirmed_by)),
            "confirmed_at": iso(c.confirmed_at), "return_reason": c.return_reason, "impact": c.impact or {}}


@router.get("/changesets", response_model=ResponseWrapper[list])
def list_changesets(db: Session = Depends(get_db), _: AppUser = Depends(CHANGE_READ)):
    out = []
    for cs in db.scalars(select(ChangeSet).order_by(ChangeSet.created_at.desc())):
        bv, nv = db.get(DocumentVersion, cs.base_version_id), db.get(DocumentVersion, cs.new_version_id)
        doc = db.get(Document, nv.document_id)
        states = dict(db.execute(select(Change.review_state, func.count()).where(Change.change_set_id == cs.id)
                                 .group_by(Change.review_state)).all())
        out.append({"id": str(cs.id), "document": doc.canonical_number, "title": doc.title_id,
                    "base_version": bv.version_number, "new_version": nv.version_number,
                    "created_at": iso(cs.created_at), "states": states, "total": sum(states.values()),
                    "material_detected": db.scalar(select(func.count()).where(Change.change_set_id == cs.id,
                                                                              Change.is_material.is_(True))) or 0})
    return ResponseWrapper(data=out)


@router.get("/changesets/{cs_id}", response_model=ResponseWrapper[dict])
def get_changeset(cs_id: str, db: Session = Depends(get_db), _: AppUser = Depends(CHANGE_READ)):
    cs = get_or_404(db, ChangeSet, cs_id)
    names = user_names(db)
    nv = db.get(DocumentVersion, cs.new_version_id)
    doc = db.get(Document, nv.document_id)
    rows = db.execute(select(Change, Provision.number_label).join(Provision, Provision.id == Change.provision_id)
                      .where(Change.change_set_id == cs.id)).all()
    changes = sorted([_change_dto(c, lbl, names) for c, lbl in rows], key=lambda x: x["provision"])
    return ResponseWrapper(data={"id": str(cs.id), "document": doc.canonical_number, "title": doc.title_id,
                                 "base_version": db.get(DocumentVersion, cs.base_version_id).version_number,
                                 "new_version": nv.version_number, "changes": changes})


def _change(db: Session, cid: str, allowed: set[str]) -> Change:
    c = get_or_404(db, Change, cid)
    if c.review_state not in allowed:
        raise AppError(409, "INVALID_STATE", f"Perubahan berstatus {c.review_state}")
    return c


@router.post("/changes/{cid}/validate", response_model=ResponseWrapper[dict])
def validate_change(cid: str, body: ValidateChangeIn, db: Session = Depends(get_db), user: AppUser = Depends(CHANGE_MAKER)):
    c = _change(db, cid, {"DETECTED", "IN_REVIEW"})
    reason = require_text(body.reason, "reason")
    if body.semantic_type and body.semantic_type not in SEMANTIC_TYPES:
        raise AppError(422, "BAD_SEMANTIC_TYPE", f"semantic_type harus salah satu: {', '.join(sorted(SEMANTIC_TYPES))}")
    before = {"review_state": c.review_state}
    c.analyst_material, c.semantic_type, c.review_reason = body.material, body.semantic_type, reason
    c.validated_by, c.validated_at, c.return_reason = user.id, now(), None
    c.review_state = "VALIDATED" if body.material else "REJECTED"
    audit(db, user.id, "CHANGE_VALIDATED" if body.material else "CHANGE_REJECTED_NOT_MATERIAL", "change", c.id,
          before=before, after={"review_state": c.review_state, "material": body.material,
                                "semantic_type": body.semantic_type, "reason": reason,
                                "deterministic_is_material": c.is_material})
    db.commit()
    return ResponseWrapper(data={"id": str(c.id), "review_state": c.review_state})


@router.post("/changes/{cid}/escalate", response_model=ResponseWrapper[dict])
def escalate_change(cid: str, body: QuestionIn, db: Session = Depends(get_db), user: AppUser = Depends(CHANGE_MAKER)):
    c = _change(db, cid, {"DETECTED", "IN_REVIEW"})
    c.legal_question, c.review_state = require_text(body.question, "question"), "ESCALATED"
    audit(db, user.id, "CHANGE_ESCALATED_TO_LEGAL", "change", c.id, after={"question": c.legal_question})
    db.commit()
    return ResponseWrapper(data={"id": str(c.id), "review_state": c.review_state})


@router.post("/changes/{cid}/legal-answer", response_model=ResponseWrapper[dict])
def answer_change(cid: str, body: AnswerIn, db: Session = Depends(get_db), user: AppUser = Depends(CHANGE_LEGAL)):
    c = _change(db, cid, {"ESCALATED"})
    answer = require_text(body.answer, "answer")
    labels = require_citations(db, body.citation_provision_version_ids)
    c.legal_answer, c.review_state = f"{answer}\n\nSitasi: {'; '.join(labels)}", "IN_REVIEW"
    audit(db, user.id, "LEGAL_POSITION_RECORDED", "change", c.id,
          after={"answer": answer, "citation_provision_version_ids": body.citation_provision_version_ids})
    db.commit()
    return ResponseWrapper(data={"id": str(c.id), "review_state": c.review_state})


def propagate_material_change(db: Session, c: Change, actor_id) -> dict:
    """EKSIBIT 27: tandai objek hilir untuk ditinjau; tidak ada yang disunting. Permukaan dampak dicatat."""
    impact = {"obligations": [], "applicability_decisions": [], "controls": [], "note": None}
    if c.base_pv_id:
        obs = db.scalars(select(Obligation).where(Obligation.primary_citation_id == c.base_pv_id,
                                                  Obligation.state.in_(REVIEWABLE))).all()
        for ob in obs:
            audit(db, actor_id, "OBLIGATION_REVIEW_REQUIRED", "obligation", ob.id,
                  before={"state": ob.state}, after={"state": "REVIEW_REQUIRED", "change_id": str(c.id)})
            ob.state = "REVIEW_REQUIRED"
            impact["obligations"].append(str(ob.id))
        ob_ids = [o.id for o in obs]
        if ob_ids:
            for ctl in db.scalars(select(Control).join(ObligationControlMap, ObligationControlMap.control_id == Control.id)
                                  .where(ObligationControlMap.obligation_id.in_(ob_ids))).unique():
                ctl.source_changed = True
                impact["controls"].append(str(ctl.id))
        base_pv = str(c.base_pv_id)
        base_dv = db.get(ProvisionVersion, c.base_pv_id).document_version_id
        for d in db.scalars(select(ApplicabilityDecision).where(ApplicabilityDecision.state == "APPROVED")):
            cited = d.cited_provision_version_ids or []
            # menyitasi pasal yang berubah, atau keputusan tingkat versi (tanpa daftar sitasi) atas versi dasar
            hits = base_pv in cited or (not cited and d.target_version_id == base_dv)
            if hits:
                d.state = "REVIEW_REQUIRED"
                impact["applicability_decisions"].append(str(d.id))
                audit(db, actor_id, "APPLICABILITY_REVIEW_REQUIRED", "applicability_decision", d.id,
                      after={"change_id": str(c.id)})
    else:
        impact["note"] = "Pasal baru: jalankan keberlakuan & ekstraksi kewajiban untuk ketentuan ini."
    c.impact = impact
    db.add(Outbox(event_type="CHANGE_MATERIAL_CONFIRMED", correlation_id=uuid.uuid4(), delivered_at=now(),
                  payload={"change_id": str(c.id), "base_pv_ids": [str(c.base_pv_id)] if c.base_pv_id else [],
                           "impact": impact}))
    audit(db, actor_id, "IMPACT_PROPAGATED", "change", c.id, after=impact)
    return impact


@router.post("/changes/{cid}/confirm-materiality", response_model=ResponseWrapper[dict])
def confirm_materiality(cid: str, body: DecisionIn, db: Session = Depends(get_db), user: AppUser = Depends(CHANGE_APPROVE)):
    """Titik kendali #1: konfirmasi materialitas oleh Manajer Kepatuhan (≠ analis validator)."""
    c = _change(db, cid, {"VALIDATED"})
    if body.outcome not in ("APPROVED", "REJECTED"):
        raise AppError(422, "BAD_OUTCOME", "outcome harus APPROVED atau REJECTED")
    if body.outcome == "REJECTED":
        require_text(body.reason, "reason")
    record_approval(db, object_type="change", object_id=c.id, control_point=ControlPoint.MATERIALITY,
                    maker_id=c.validated_by, last_editor_id=c.validated_by, checker_id=user.id, outcome=body.outcome,
                    reason=body.reason, snapshot={"semantic_type": c.semantic_type, "reason": c.review_reason,
                                                  "change_type": c.change_type})
    impact = None
    if body.outcome == "APPROVED":
        c.review_state, c.confirmed_by, c.confirmed_at = "MATERIAL_CONFIRMED", user.id, now()
        audit(db, user.id, "CHANGE_MATERIAL_CONFIRMED", "change", c.id, after={"review_state": c.review_state})
        impact = propagate_material_change(db, c, user.id)
    else:
        c.review_state, c.return_reason = "IN_REVIEW", body.reason
        audit(db, user.id, "CHANGE_RETURNED", "change", c.id, after={"reason": body.reason})
    db.commit()
    return ResponseWrapper(data={"id": str(c.id), "review_state": c.review_state, "impact": impact})


# ---------- W4 ----------
@router.get("/relationships", response_model=ResponseWrapper[list])
def list_relationships(document_id: Optional[str] = None, db: Session = Depends(get_db), _: AppUser = Depends(REL_READ)):
    names = user_names(db)
    docs = {str(d.id): d.canonical_number for d in db.scalars(select(Document))}
    stmt = select(Relationship).order_by(Relationship.created_at.desc())
    if document_id:
        stmt = stmt.where((Relationship.source_document_id == document_id) | (Relationship.target_document_id == document_id))
    return ResponseWrapper(data=[{"id": str(r.id), "source": docs.get(str(r.source_document_id)),
                                  "target": docs.get(str(r.target_document_id)), "relation_type": r.relation_type,
                                  "state": r.state, "note": r.note, "proposed_by": names.get(sid(r.proposed_by)), "proposed_by_id": sid(r.proposed_by),
                                  "confirmed_by": names.get(sid(r.confirmed_by)),
                                  "source_document_id": str(r.source_document_id),
                                  "target_document_id": str(r.target_document_id),
                                  "citing_provision_version_id": sid(r.citing_provision_version_id)}
                                 for r in db.scalars(stmt)])


@router.post("/relationships", response_model=ResponseWrapper[dict])
def propose_relationship(body: RelationshipIn, db: Session = Depends(get_db), user: AppUser = Depends(REL_CREATE)):
    get_or_404(db, Document, body.source_document_id)
    get_or_404(db, Document, body.target_document_id)
    if body.relation_type not in {"AMENDS", "REVOKES", "PARTIALLY_REVOKES", "REFERS_TO", "IMPLEMENTS"}:
        raise AppError(422, "BAD_RELATION_TYPE", "relation_type tidak dikenal")
    if body.source_document_id == body.target_document_id:
        raise AppError(422, "SELF_RELATION", "Dokumen tidak dapat berelasi dengan dirinya sendiri")
    r = Relationship(source_document_id=body.source_document_id, target_document_id=body.target_document_id,
                     relation_type=body.relation_type, citing_provision_version_id=body.citing_provision_version_id,
                     note=body.note, proposed_by=user.id)
    db.add(r)
    db.flush()
    audit(db, user.id, "RELATIONSHIP_PROPOSED", "relationship", r.id, after={"type": r.relation_type})
    db.commit()
    return ResponseWrapper(data={"id": str(r.id), "state": r.state})


class RelationshipUpdateIn(BaseModel):
    relation_type: Optional[str] = None
    citing_provision_version_id: Optional[str] = None
    note: Optional[str] = None


@router.patch("/relationships/{rid}", response_model=ResponseWrapper[dict])
def update_relationship(rid: str, body: RelationshipUpdateIn, db: Session = Depends(get_db),
                        user: AppUser = Depends(REL_UPDATE)):
    """Relasi regulasi: U = Analis & Peninjau Hukum. Hanya relasi yang masih PROPOSED yang dapat disunting."""
    r = get_or_404(db, Relationship, rid)
    if r.state != "PROPOSED":
        raise AppError(409, "INVALID_STATE", f"Relasi berstatus {r.state}; hanya PROPOSED yang dapat disunting")
    before = {"relation_type": r.relation_type, "note": r.note, "citing": sid(r.citing_provision_version_id)}
    if body.relation_type is not None:
        if body.relation_type not in {"AMENDS", "REVOKES", "PARTIALLY_REVOKES", "REFERS_TO", "IMPLEMENTS"}:
            raise AppError(422, "BAD_RELATION_TYPE", "relation_type tidak dikenal")
        r.relation_type = body.relation_type
    if body.citing_provision_version_id is not None:
        r.citing_provision_version_id = body.citing_provision_version_id or None
    if body.note is not None:
        r.note = body.note
    audit(db, user.id, "RELATIONSHIP_UPDATED", "relationship", r.id, before=before,
          after={"relation_type": r.relation_type, "note": r.note, "citing": sid(r.citing_provision_version_id)})
    db.commit()
    return ResponseWrapper(data={"id": str(r.id), "state": r.state})


@router.delete("/relationships/{rid}", response_model=ResponseWrapper[dict])
def delete_relationship(rid: str, db: Session = Depends(get_db), user: AppUser = Depends(REL_DELETE)):
    """Relasi regulasi: D = Analis. Hanya usulan (PROPOSED); relasi CONFIRMED sudah mengubah status dokumen → tidak boleh hilang."""
    r = get_or_404(db, Relationship, rid)
    if r.state != "PROPOSED":
        raise AppError(409, "INVALID_STATE", f"Relasi berstatus {r.state}; hanya usulan (PROPOSED) yang dapat dihapus")
    audit(db, user.id, "RELATIONSHIP_DELETED", "relationship", r.id,
          before={"source": str(r.source_document_id), "target": str(r.target_document_id), "type": r.relation_type})
    db.delete(r)
    db.commit()
    return ResponseWrapper(data={"deleted_relationship_id": rid})


@router.post("/relationships/{rid}/confirm", response_model=ResponseWrapper[dict])
def confirm_relationship(rid: str, db: Session = Depends(get_db), user: AppUser = Depends(STATUS_APPROVE)):
    """Konfirmasi relasi mengubah status dokumen (mis. REVOKED) → persetujuan Manajer Kepatuhan (baris
    'Perubahan status dokumen': Analis C/R/U, Manajer R/A). Pengonfirmasi tidak boleh sama dengan pengusul."""
    r = get_or_404(db, Relationship, rid)
    if r.state != "PROPOSED":
        raise AppError(409, "INVALID_STATE", f"Relasi berstatus {r.state}")
    enforce_maker_checker(user.id, r.proposed_by)
    if not r.citing_provision_version_id:
        raise AppError(422, "CITATION_REQUIRED", "Konfirmasi relasi wajib menyitasi ketentuan penetap (pasal penutup)")
    r.state, r.confirmed_by = "CONFIRMED", user.id
    target = db.get(Document, r.target_document_id)
    new_status = {"REVOKES": "REVOKED", "PARTIALLY_REVOKES": "PARTIALLY_REVOKED", "AMENDS": "AMENDED"}.get(r.relation_type)
    if new_status:
        before = target.status
        target.status = new_status
        audit(db, user.id, "DOCUMENT_STATUS_CHANGED", "document", target.id, before={"status": before},
              after={"status": new_status, "relationship_id": str(r.id)})
    audit(db, user.id, "RELATIONSHIP_CONFIRMED", "relationship", r.id)
    db.commit()
    return ResponseWrapper(data={"id": str(r.id), "state": r.state})


# ---------- W6 ----------
def suggest_labels(db: Session, doc: Document) -> list[TaxonomyLabel]:
    title = doc.title_id.lower()
    created = []
    for dim, rules in (("THEME", THEME_RULES), ("POPULATION", POPULATION_RULES)):
        for kw, value in rules.items():
            if kw in title and not db.scalar(select(TaxonomyLabel.id).where(
                    TaxonomyLabel.document_id == doc.id, TaxonomyLabel.dimension == dim, TaxonomyLabel.value == value)):
                lbl = TaxonomyLabel(document_id=doc.id, dimension=dim, value=value, state="SUGGESTED", source="RULE",
                                    reason=f"Kata kunci judul: '{kw}'")
                db.add(lbl)
                db.flush()
                created.append(lbl)
    return created


@router.get("/documents/{doc_id}/labels", response_model=ResponseWrapper[list])
def list_labels(doc_id: str, db: Session = Depends(get_db), _: AppUser = Depends(TAX_READ)):
    return ResponseWrapper(data=[{"id": str(lb.id), "dimension": lb.dimension, "value": lb.value, "state": lb.state,
                                  "source": lb.source, "reason": lb.reason}
                                 for lb in db.scalars(select(TaxonomyLabel).where(TaxonomyLabel.document_id == doc_id)
                                                      .order_by(TaxonomyLabel.dimension))])


@router.post("/documents/{doc_id}/labels/suggest", response_model=ResponseWrapper[dict])
def suggest(doc_id: str, db: Session = Depends(get_db), user: AppUser = Depends(TAX_WRITE)):
    doc = get_or_404(db, Document, doc_id)
    created = suggest_labels(db, doc)
    audit(db, user.id, "LABELS_SUGGESTED", "document", doc.id, after={"count": len(created)})
    db.commit()
    return ResponseWrapper(data={"created": len(created)})


@router.post("/documents/{doc_id}/labels", response_model=ResponseWrapper[dict])
def add_label(doc_id: str, body: LabelIn, db: Session = Depends(get_db), user: AppUser = Depends(TAX_WRITE)):
    doc = get_or_404(db, Document, doc_id)
    if body.value not in ALLOWED_LABELS.get(body.dimension, set()):
        raise AppError(422, "LABEL_NOT_IN_TAXONOMY", "Label harus berasal dari taksonomi terkendali (E6.1)")
    lbl = TaxonomyLabel(document_id=doc.id, dimension=body.dimension, value=body.value, state="CONFIRMED",
                        source="HUMAN", decided_by=user.id)
    db.add(lbl)
    db.flush()
    audit(db, user.id, "LABEL_CONFIRMED", "taxonomy_label", lbl.id, after={"dimension": lbl.dimension, "value": lbl.value})
    db.commit()
    return ResponseWrapper(data={"id": str(lbl.id)})


@router.post("/labels/{lid}/confirm", response_model=ResponseWrapper[dict])
def confirm_label(lid: str, db: Session = Depends(get_db), user: AppUser = Depends(TAX_UPDATE)):
    lbl = get_or_404(db, TaxonomyLabel, lid)
    lbl.state, lbl.decided_by = "CONFIRMED", user.id
    audit(db, user.id, "LABEL_CONFIRMED", "taxonomy_label", lbl.id)
    db.commit()
    return ResponseWrapper(data={"id": str(lbl.id), "state": lbl.state})


@router.post("/labels/{lid}/remove", response_model=ResponseWrapper[dict])
def remove_label(lid: str, body: ReasonIn, db: Session = Depends(get_db), user: AppUser = Depends(TAX_DELETE)):
    lbl = get_or_404(db, TaxonomyLabel, lid)
    lbl.state, lbl.reason, lbl.decided_by = "REMOVED", require_text(body.reason, "reason"), user.id
    audit(db, user.id, "LABEL_REMOVED", "taxonomy_label", lbl.id, after={"reason": lbl.reason})
    db.commit()
    return ResponseWrapper(data={"id": str(lbl.id), "state": lbl.state})