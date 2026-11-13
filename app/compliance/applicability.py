"""W7 keberlakuan (titik kendali #2) dan profil organisasi berversi (E7.1).

IN_ASSESSMENT → (PENDING_LEGAL ↔ IN_ASSESSMENT) → PENDING_APPROVAL → APPROVED | REJECTED_TO_MAKER
APPROVED → REVIEW_REQUIRED (perubahan material / profil berubah) → reopen = draf baru; yang lama SUPERSEDED saat draf baru disetujui.
Aturan berbasis kata kunci hanya menghasilkan SARAN — AI/aturan tidak pernah memutuskan keberlakuan.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.common import get_or_404, iso, now, require_text, sid, user_names 
from app.compliance.common import get_or_404, iso, now, require_citations, require_text, sid, user_names
from app.compliance.models import ApplicabilityDecision, OrganisationProfile
from app.corpus.models import Document, DocumentVersion, ProvisionVersion, Provision, TaxonomyLabel
from app.platform.governance import audit, record_approval
from app.platform.models import AppUser
from app.platform.permissions import require
from app.shared.database import get_db
from app.shared.errors import AppError
from app.shared.schemas import ResponseWrapper
from app.shared.vocabularies import AppRole, ApplicabilityValue, ControlPoint

router = APIRouter(prefix="/api/v1/compliance", tags=["applicability"])
R = AppRole
# Otorisasi = matriks RBAC (app/shared/rbac_matrix.py): "Organization Profile" & "Applicability Decision".
OFFICER_CREATE = require("applicability", "C")                                  # Pejabat Kepatuhan
OFFICER_UPDATE = require("applicability", "U", only=[R.COMPLIANCE_OFFICER])     # eskalasi/ajukan/buka ulang = alur Pejabat
LEGAL = require("applicability", "U", only=[R.LEGAL_REVIEWER])                  # Peninjau Hukum: RU → memberi posisi hukum
MANAGER = require("applicability", "A")                                         # Manajer Kepatuhan (titik kendali #2)

ENTITY_RULES = {"bank umum": {"BANK_UMUM"}, "perbankan syariah": {"BANK_SYARIAH"}, "bpr": {"BPR"},
                "penyelenggara jasa pembayaran": {"PJP"}, "lembaga jasa keuangan": {"BANK_UMUM", "BPR", "PJP", "BANK_SYARIAH"}}
POPULATION_TO_ENTITY = {"Bank umum": {"BANK_UMUM"}, "BPR/BPRS": {"BPR", "BANK_SYARIAH"},
                        "Penyedia jasa pembayaran": {"PJP"}, "Lembaga jasa keuangan (umum)": {"BANK_UMUM", "BPR", "PJP", "BANK_SYARIAH"}}
VALUES = {v.value for v in ApplicabilityValue}


class SuggestIn(BaseModel):
    version_id: str
    profile_id: Optional[str] = None


class DecisionDraftIn(BaseModel):
    version_id: str
    profile_id: Optional[str] = None
    decision_value: str
    reason: str
    cited_provision_version_ids: list[str] = []
    scope_provision_version_ids: list[str] = []
    review_owner_id: Optional[str] = None
    review_target_date: Optional[date] = None


class QuestionIn(BaseModel):
    question: str


class AnswerIn(BaseModel):
    answer: str
    citation_provision_version_ids: list[str] = []  # AOR-10: posisi hukum beserta sitasinya sendiri

class DecisionIn(BaseModel):
    outcome: str
    reason: Optional[str] = None


class ProfileUpdateIn(BaseModel):
    entity_type: Optional[str] = None
    licenses: Optional[list[str]] = None
    business_lines: Optional[list[str]] = None
    justification: str


def _profile(db: Session, profile_id: Optional[str]) -> OrganisationProfile:
    p = get_or_404(db, OrganisationProfile, profile_id) if profile_id else db.scalar(select(OrganisationProfile).limit(1))
    if p is None:
        raise AppError(422, "NO_PROFILE", "Buat profil organisasi terlebih dahulu")
    return p


def suggest_applicability(db: Session, profile: OrganisationProfile, dv: DocumentVersion) -> tuple[str, str, list[str]]:
    """Saran transparan dengan reason code. Label POPULATION terkonfirmasi mengungguli kata kunci judul."""
    doc = db.get(Document, dv.document_id)
    codes: list[str] = []
    pops = db.scalars(select(TaxonomyLabel.value).where(TaxonomyLabel.document_id == doc.id,
                                                        TaxonomyLabel.dimension == "POPULATION",
                                                        TaxonomyLabel.state == "CONFIRMED")).all()
    targets: set[str] = set()
    if pops:
        for p in pops:
            targets |= POPULATION_TO_ENTITY.get(p, set())
        codes.append(f"LABEL_POPULATION:{','.join(pops)}")
    else:
        title = doc.title_id.lower()
        for kw, ents in ENTITY_RULES.items():
            if kw in title:
                targets |= ents
                codes.append(f"TITLE_KEYWORD:{kw}")
    if doc.status in ("REVOKED",):
        return ApplicabilityValue.NOT_APPLICABLE.value, "Dokumen berstatus dicabut", codes + ["DOC_REVOKED"]
    if not targets:
        return (ApplicabilityValue.REQUIRES_FURTHER_REVIEW.value,
                "Populasi teregulasi tidak dapat ditentukan dari label maupun judul", codes + ["NO_POPULATION_MATCH"])
    if profile.entity_type in targets:
        return (ApplicabilityValue.APPLICABLE.value,
                f"Entitas {profile.entity_type} termasuk populasi teregulasi", codes + [f"ENTITY_MATCH:{profile.entity_type}"])
    return (ApplicabilityValue.NOT_APPLICABLE.value,
            f"Entitas {profile.entity_type} bukan populasi teregulasi ({', '.join(sorted(targets))})",
            codes + [f"ENTITY_MISMATCH:{profile.entity_type}"])


def decision_dto(db: Session, d: ApplicabilityDecision, names: dict) -> dict:
    dv = db.get(DocumentVersion, d.target_version_id)
    doc = db.get(Document, dv.document_id)
    cites = []
    for pid in d.cited_provision_version_ids or []:
        lbl = db.scalar(select(Provision.number_label).join(ProvisionVersion, ProvisionVersion.provision_id == Provision.id)
                        .where(ProvisionVersion.id == pid))
        cites.append({"provision_version_id": pid, "number_label": lbl, "canonical_number": doc.canonical_number})
    return {"id": str(d.id), "state": d.state, "decision_value": d.decision_value, "reason": d.reason_text,
            "suggested_value": d.suggested_value, "document": doc.canonical_number, "title": doc.title_id,
            "document_id": str(doc.id), "version_id": str(dv.id), "version_number": dv.version_number,
            "citations": cites, "scope_provision_version_ids": d.scope_provision_version_ids or [],
            "relied_upon_attributes": d.relied_upon_attributes, "maker": names.get(sid(d.maker_id)),
            "maker_id": sid(d.maker_id), "approver": names.get(sid(d.approver_id)),
            "legal_question": d.legal_question, "legal_answer": d.legal_answer,
            "legal_reviewer": names.get(sid(d.legal_reviewer_id)), "return_reason": d.return_reason,
            "review_owner": names.get(sid(d.review_owner_id)), "review_target_date": iso(d.review_target_date),
            "created_at": iso(d.created_at), "submitted_at": iso(d.submitted_at), "decided_at": iso(d.decided_at),
            "superseded_by": sid(d.superseded_by)}


def approved_decision_for(db: Session, dv_id, profile_id, pv_id=None) -> Optional[ApplicabilityDecision]:
    d = db.scalar(select(ApplicabilityDecision).where(ApplicabilityDecision.target_version_id == dv_id,
                                                      ApplicabilityDecision.profile_id == profile_id,
                                                      ApplicabilityDecision.state == "APPROVED")
                  .order_by(ApplicabilityDecision.decided_at.desc().nullslast()))
    return d


@router.get("/profiles", response_model=ResponseWrapper[list])
def list_profiles(db: Session = Depends(get_db), _: AppUser = Depends(require("org_profile", "R"))):
    return ResponseWrapper(data=[{"id": str(p.id), "organisation_name": p.organisation_name, "entity_type": p.entity_type,
                                  "licenses": p.licenses, "business_lines": p.business_lines, "version": p.version}
                                 for p in db.scalars(select(OrganisationProfile))])


@router.put("/profiles/{pid}", response_model=ResponseWrapper[dict])
def update_profile(pid: str, body: ProfileUpdateIn, db: Session = Depends(get_db),
                   user: AppUser = Depends(require("org_profile", "U"))):
    """E7.1: perubahan atribut profil → keputusan APPROVED yang bersandar padanya menjadi REVIEW_REQUIRED."""
    p = get_or_404(db, OrganisationProfile, pid)
    just = require_text(body.justification, "justification")
    before = {"entity_type": p.entity_type, "licenses": p.licenses, "business_lines": p.business_lines, "version": p.version}
    changed = set()
    for k in ("entity_type", "licenses", "business_lines"):
        v = getattr(body, k)
        if v is not None and v != getattr(p, k):
            setattr(p, k, v)
            changed.add(k)
    if not changed:
        raise AppError(422, "NO_CHANGE", "Tidak ada atribut profil yang berubah")
    p.version = (p.version or 1) + 1
    flagged = []
    for d in db.scalars(select(ApplicabilityDecision).where(ApplicabilityDecision.profile_id == p.id,
                                                            ApplicabilityDecision.state == "APPROVED")):
        if changed & set((d.relied_upon_attributes or {}).keys()):
            d.state = "REVIEW_REQUIRED"
            flagged.append(str(d.id))
            audit(db, user.id, "APPLICABILITY_REVIEW_REQUIRED", "applicability_decision", d.id,
                  after={"reason": "PROFILE_CHANGED", "attributes": sorted(changed)})
    audit(db, user.id, "PROFILE_UPDATED", "organisation_profile", p.id, before=before,
          after={"changed": sorted(changed), "version": p.version, "justification": just, "flagged": flagged})
    db.commit()
    return ResponseWrapper(data={"id": str(p.id), "version": p.version, "flagged_decisions": flagged})


@router.get("/applicability", response_model=ResponseWrapper[list])
def list_decisions(state: Optional[str] = None, db: Session = Depends(get_db),
                   _: AppUser = Depends(require("applicability", "R"))):
    names = user_names(db)
    stmt = select(ApplicabilityDecision).order_by(ApplicabilityDecision.created_at.desc())
    if state:
        stmt = stmt.where(ApplicabilityDecision.state == state)
    return ResponseWrapper(data=[decision_dto(db, d, names) for d in db.scalars(stmt)])


@router.post("/applicability/suggest", response_model=ResponseWrapper[dict])
def suggest(body: SuggestIn, db: Session = Depends(get_db), _: AppUser = Depends(OFFICER_CREATE)):
    p, dv = _profile(db, body.profile_id), get_or_404(db, DocumentVersion, body.version_id)
    value, reason, codes = suggest_applicability(db, p, dv)
    return ResponseWrapper(data={"suggested_value": value, "reason": reason, "reason_codes": codes,
                                 "note": "Saran berbasis aturan; keputusan tetap dibuat dan disetujui manusia."})


def _validate_payload(db: Session, dv: DocumentVersion, body: DecisionDraftIn) -> None:
    if body.decision_value not in VALUES:
        raise AppError(422, "BAD_DECISION_VALUE", f"decision_value harus salah satu: {', '.join(sorted(VALUES))}")
    pv_ids = {str(x) for x in db.scalars(select(ProvisionVersion.id).where(ProvisionVersion.document_version_id == dv.id))}
    for pid in body.cited_provision_version_ids + body.scope_provision_version_ids:
        if pid not in pv_ids:
            raise AppError(422, "CITATION_UNRESOLVED", f"provision_version_id {pid} bukan bagian dari versi ini")


@router.post("/applicability", response_model=ResponseWrapper[dict])
def create_decision(body: DecisionDraftIn, db: Session = Depends(get_db), user: AppUser = Depends(OFFICER_CREATE)):
    p, dv = _profile(db, body.profile_id), get_or_404(db, DocumentVersion, body.version_id)
    if dv.state != "PUBLISHED":
        raise AppError(409, "VERSION_NOT_PUBLISHED", "Keberlakuan hanya untuk versi berstatus PUBLISHED")
    _validate_payload(db, dv, body)
    suggested, _, codes = suggest_applicability(db, p, dv)
    d = ApplicabilityDecision(target_version_id=dv.id, profile_id=p.id, decision_value=body.decision_value,
                              reason_text=require_text(body.reason, "reason"), maker_id=user.id, state="IN_ASSESSMENT",
                              relied_upon_attributes={"entity_type": p.entity_type, "licenses": p.licenses,
                                                      "business_lines": p.business_lines, "profile_version": p.version},
                              cited_provision_version_ids=body.cited_provision_version_ids,
                              scope_provision_version_ids=body.scope_provision_version_ids,
                              review_owner_id=body.review_owner_id, review_target_date=body.review_target_date,
                              suggested_value=suggested)
    db.add(d)
    db.flush()
    audit(db, user.id, "APPLICABILITY_DRAFTED", "applicability_decision", d.id,
          after={"value": d.decision_value, "suggested": suggested, "reason_codes": codes})
    db.commit()
    return ResponseWrapper(data={"id": str(d.id), "state": d.state, "suggested_value": suggested})


def _decision(db: Session, did: str, states: set[str]) -> ApplicabilityDecision:
    d = get_or_404(db, ApplicabilityDecision, did)
    if d.state not in states:
        raise AppError(409, "INVALID_STATE", f"Keputusan berstatus {d.state}")
    return d


@router.post("/applicability/{did}/escalate", response_model=ResponseWrapper[dict])
def escalate(did: str, body: QuestionIn, db: Session = Depends(get_db), user: AppUser = Depends(OFFICER_UPDATE)):
    d = _decision(db, did, {"IN_ASSESSMENT", "REJECTED_TO_MAKER"})
    d.legal_question, d.state = require_text(body.question, "question"), "PENDING_LEGAL"
    audit(db, user.id, "APPLICABILITY_ESCALATED", "applicability_decision", d.id, after={"question": d.legal_question})
    db.commit()
    return ResponseWrapper(data={"id": str(d.id), "state": d.state})


@router.post("/applicability/{did}/legal-answer", response_model=ResponseWrapper[dict])
def legal_answer(did: str, body: AnswerIn, db: Session = Depends(get_db), user: AppUser = Depends(LEGAL)):
    d = _decision(db, did, {"PENDING_LEGAL"})
    answer = require_text(body.answer, "answer")
    labels = require_citations(db, body.citation_provision_version_ids)
    d.legal_answer, d.legal_reviewer_id, d.state = f"{answer}\n\nSitasi: {'; '.join(labels)}", user.id, "IN_ASSESSMENT"
    audit(db, user.id, "APPLICABILITY_LEGAL_POSITION", "applicability_decision", d.id,
          after={"answer": answer, "citation_provision_version_ids": body.citation_provision_version_ids})
    db.commit()
    return ResponseWrapper(data={"id": str(d.id), "state": d.state})


@router.post("/applicability/{did}/submit", response_model=ResponseWrapper[dict])
def submit(did: str, db: Session = Depends(get_db), user: AppUser = Depends(OFFICER_UPDATE)):
    d = _decision(db, did, {"IN_ASSESSMENT", "REJECTED_TO_MAKER"})
    if not d.cited_provision_version_ids:
        raise AppError(422, "CITATION_REQUIRED", "Keputusan wajib memuat minimal satu sitasi ketentuan")
    if d.decision_value == "PARTIALLY_APPLICABLE" and not d.scope_provision_version_ids:
        raise AppError(422, "SCOPE_REQUIRED", "PARTIALLY_APPLICABLE mensyaratkan daftar ketentuan yang berlaku")
    if d.decision_value == "REQUIRES_FURTHER_REVIEW" and not (d.review_owner_id and d.review_target_date):
        raise AppError(422, "REVIEW_OWNER_REQUIRED", "REQUIRES_FURTHER_REVIEW mensyaratkan pemilik dan tanggal target")
    d.state, d.submitted_at = "PENDING_APPROVAL", now()
    audit(db, user.id, "APPLICABILITY_SUBMITTED", "applicability_decision", d.id, after={"state": d.state})
    db.commit()
    return ResponseWrapper(data={"id": str(d.id), "state": d.state})


@router.post("/applicability/{did}/decision", response_model=ResponseWrapper[dict])
def decide(did: str, body: DecisionIn, db: Session = Depends(get_db), user: AppUser = Depends(MANAGER)):
    """Titik kendali #2: penyetuju ≠ pembuat keputusan (juga CHECK di DB)."""
    d = _decision(db, did, {"PENDING_APPROVAL"})
    if body.outcome not in ("APPROVED", "REJECTED"):
        raise AppError(422, "BAD_OUTCOME", "outcome harus APPROVED atau REJECTED")
    if body.outcome == "REJECTED":
        require_text(body.reason, "reason")
    record_approval(db, object_type="applicability_decision", object_id=d.id, control_point=ControlPoint.APPLICABILITY,
                    maker_id=d.maker_id, last_editor_id=d.maker_id, checker_id=user.id, outcome=body.outcome,
                    reason=body.reason, snapshot={"value": d.decision_value, "reason": d.reason_text,
                                                  "relied_upon": d.relied_upon_attributes})
    if body.outcome == "APPROVED":
        d.state, d.approver_id, d.decided_at = "APPROVED", user.id, now()
        for old in db.scalars(select(ApplicabilityDecision).where(
                ApplicabilityDecision.target_version_id == d.target_version_id,
                ApplicabilityDecision.profile_id == d.profile_id, ApplicabilityDecision.id != d.id,
                ApplicabilityDecision.state.in_(("APPROVED", "REVIEW_REQUIRED")))):
            old.state, old.superseded_by = "SUPERSEDED", d.id
            audit(db, user.id, "APPLICABILITY_SUPERSEDED", "applicability_decision", old.id, after={"by": str(d.id)})
    else:
        d.state, d.return_reason = "REJECTED_TO_MAKER", body.reason
    audit(db, user.id, f"APPLICABILITY_{body.outcome}", "applicability_decision", d.id, after={"state": d.state})
    db.commit()
    return ResponseWrapper(data={"id": str(d.id), "state": d.state})


@router.post("/applicability/{did}/reopen", response_model=ResponseWrapper[dict])
def reopen(did: str, db: Session = Depends(get_db), user: AppUser = Depends(OFFICER_UPDATE)):
    """REVIEW_REQUIRED → draf baru IN_ASSESSMENT. Keputusan lama tetap catatan resmi sampai draf baru disetujui."""
    old = _decision(db, did, {"REVIEW_REQUIRED"})
    p = db.get(OrganisationProfile, old.profile_id)
    d = ApplicabilityDecision(target_version_id=old.target_version_id, profile_id=old.profile_id,
                              decision_value=old.decision_value, reason_text=old.reason_text, maker_id=user.id,
                              state="IN_ASSESSMENT", cited_provision_version_ids=old.cited_provision_version_ids,
                              scope_provision_version_ids=old.scope_provision_version_ids, suggested_value=old.suggested_value,
                              relied_upon_attributes={"entity_type": p.entity_type, "licenses": p.licenses,
                                                      "business_lines": p.business_lines, "profile_version": p.version})
    db.add(d)
    db.flush()
    audit(db, user.id, "APPLICABILITY_REOPENED", "applicability_decision", d.id, after={"from": str(old.id)})
    db.commit()
    return ResponseWrapper(data={"id": str(d.id), "state": d.state})