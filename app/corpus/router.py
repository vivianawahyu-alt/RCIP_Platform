from datetime import date
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.corpus import services
from app.corpus.models import ChangeSet, Document, DocumentVersion, Provision, ProvisionVersion, TaxonomyLabel
from app.platform.auth import current_user, require_roles
from app.platform.governance import audit
from app.platform.models import AppUser
from app.shared.database import get_db
from app.shared.errors import AppError
from app.shared.schemas import CitationResolveRequest, CitationResolveResponse, ResponseWrapper
from app.shared.storage import put_object
from app.shared.vocabularies import AppRole, VersionState

router = APIRouter(tags=["corpus"])
ANALYST = require_roles(AppRole.REGULATORY_ANALYST)


class DocumentCreate(BaseModel):
    canonical_number: str
    instrument_type: str = "POJK"
    issuer: str = "Otoritas Jasa Keuangan"
    title_id: str
    source_category: str = "OJK"
    base_url: str = "https://www.ojk.go.id"


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


@router.post("/api/v1/citations/resolve", response_model=ResponseWrapper[CitationResolveResponse])
def resolve(payload: CitationResolveRequest, db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    """KONTRAK ANTAR-MODUL (dibekukan Minggu 4)."""
    return ResponseWrapper(data=services.resolve_citations(db, payload.provision_version_ids))


@router.post("/api/v1/corpus/documents", response_model=ResponseWrapper[dict])
def create_document(body: DocumentCreate, db: Session = Depends(get_db), user: AppUser = Depends(ANALYST)):
    if db.scalar(select(Document).where(Document.canonical_number == body.canonical_number)):
        raise AppError(409, "DUPLICATE", "Nomor regulasi sudah terdaftar")
    src = services.get_or_create_source(db, body.source_category, body.source_category, body.issuer, body.base_url)
    doc = Document(source_id=src.id, canonical_number=body.canonical_number, instrument_type=body.instrument_type,
                   issuer=body.issuer, title_id=body.title_id)
    db.add(doc)
    db.flush()
    from app.corpus.review import suggest_labels
    suggest_labels(db, doc)
    audit(db, user.id, "DOCUMENT_CREATED", "document", doc.id)
    db.commit()
    return ResponseWrapper(data={"id": str(doc.id)})


@router.get("/api/v1/corpus/documents", response_model=ResponseWrapper[list])
def list_documents(db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    out = []
    for d in db.scalars(select(Document).order_by(Document.canonical_number)):
        vs = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == d.id)
                        .order_by(DocumentVersion.version_number)).all()
        labels = [{"dimension": lb.dimension, "value": lb.value, "state": lb.state}
                  for lb in db.scalars(select(TaxonomyLabel).where(TaxonomyLabel.document_id == d.id,
                                                                   TaxonomyLabel.state != "REMOVED"))]
        out.append({"id": str(d.id), "canonical_number": d.canonical_number, "title_id": d.title_id,
                    "status": d.status, "instrument_type": d.instrument_type, "issuer": d.issuer, "labels": labels,
                    "versions": [{"id": str(v.id), "version_number": v.version_number, "state": v.state,
                                  "effective_date": str(v.effective_date)} for v in vs]})
    return ResponseWrapper(data=out)


@router.post("/api/v1/corpus/documents/{doc_id}/versions", response_model=ResponseWrapper[dict])
async def upload_version(doc_id: str, file: UploadFile = File(...), effective_date: date = Form(...),
                         origin_url: str = Form("upload://manual"), db: Session = Depends(get_db),
                         user: AppUser = Depends(ANALYST)):
    doc = _get(db, Document, doc_id)
    data = await file.read()
    key = f"{doc.canonical_number.replace('/', '_').replace(' ', '_')}/{file.filename}"
    put_object(key, data)
    dv, n = services.ingest_version(db, doc, file.filename or "", data, effective_date, origin_url, key)
    audit(db, user.id, "VERSION_INGESTED", "document_version", dv.id, after={"provisions": n})
    db.commit()
    return ResponseWrapper(data={"version_id": str(dv.id), "version_number": dv.version_number,
                                 "provisions_created": n, "state": dv.state})


@router.get("/api/v1/corpus/versions/{version_id}/provisions", response_model=ResponseWrapper[list])
def list_provisions(version_id: str, db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    _get(db, DocumentVersion, version_id)
    rows = db.execute(select(ProvisionVersion, Provision)
                      .join(Provision, Provision.id == ProvisionVersion.provision_id)
                      .where(ProvisionVersion.document_version_id == version_id)
                      .order_by(ProvisionVersion.sequence)).all()
    return ResponseWrapper(data=[{"provision_version_id": str(pv.id), "number_label": p.number_label,
                                  "path": p.hierarchical_path, "text": pv.text,
                                  "confidence": float(pv.segmentation_confidence),
                                  "corrected_by_human": pv.corrected_by_human} for pv, p in rows])


@router.patch("/api/v1/corpus/provision-versions/{pv_id}", response_model=ResponseWrapper[dict])
def correct_provision(pv_id: str, body: ProvisionCorrection, db: Session = Depends(get_db),
                      user: AppUser = Depends(ANALYST)):
    pv = _get(db, ProvisionVersion, pv_id)
    dv = db.get(DocumentVersion, pv.document_version_id)
    if dv.state not in (VersionState.SEGMENTED_DRAFT.value, VersionState.UNDER_CORRECTION.value):
        raise AppError(409, "VERSION_IMMUTABLE", "Versi yang sudah dipublikasikan tidak dapat diubah")
    before = {"text": pv.text}
    pv.text, pv.corrected_by_human, dv.state = body.text, True, VersionState.UNDER_CORRECTION.value
    audit(db, user.id, "PROVISION_CORRECTED", "provision_version", pv.id, before=before, after={"text": body.text})
    db.commit()
    return ResponseWrapper(data={"id": str(pv.id)})


@router.post("/api/v1/corpus/versions/{version_id}/publish", response_model=ResponseWrapper[dict])
def publish(version_id: str, db: Session = Depends(get_db), user: AppUser = Depends(ANALYST)):
    dv = _get(db, DocumentVersion, version_id)
    services.publish_version(db, dv)
    audit(db, user.id, "VERSION_PUBLISHED", "document_version", dv.id)
    db.commit()
    return ResponseWrapper(data={"version_id": str(dv.id), "state": dv.state})


@router.get("/api/v1/corpus/search", response_model=ResponseWrapper[list])
def search(q: str, limit: int = 10, db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    return ResponseWrapper(data=services.search_provisions(db, q, min(limit, 50)))


@router.post("/api/v1/corpus/changes", response_model=ResponseWrapper[dict])
def compute(body: ChangeRequest, db: Session = Depends(get_db), user: AppUser = Depends(ANALYST)):
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
