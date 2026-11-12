"""Katalog peraturan ala database hukum (Hukumonline/JDIH) di atas korpus RCIP."""
import re
from datetime import date

from sqlalchemy import distinct, exists, func, or_, select, text
from sqlalchemy.orm import Session

from app.corpus.models import (Document, DocumentVersion, Provision, ProvisionVersion, RegulatorySource, Relationship,
                               TaxonomyLabel)
# ---------------------------------------------------------------- normalisasi input
_WS = re.compile(r"\s+")
_YEAR = re.compile(r"((?:19|20)\d{2})\s*$")


def normalise_title(raw: str | None) -> str:
    """Judul: buang spasi di pinggir dan spasi ganda."""
    return _WS.sub(" ", (raw or "").strip())


def normalise_number(raw: str | None) -> str:
    """'1 /POJK.04/2021' → '1/POJK.04/2021'. Huruf dan angka TIDAK diubah."""
    return re.sub(r"\s*/\s*", "/", normalise_title(raw))


def extract_year(canonical_number: str | None) -> int | None:
    """Tahun dari akhir nomor ('.../2022', 'NOMOR 10 TAHUN 2026'); None bila tidak ada."""
    m = _YEAR.search(canonical_number or "")
    return int(m.group(1)) if m else None


def _like(term: str) -> str:
    """Pola ILIKE aman: tanda % _ \\ dari pengguna diperlakukan sebagai huruf biasa."""
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# ---------------------------------------------------------------- pencarian pasal berfilter
def search_provisions(db: Session, q: str, limit: int = 10, *, instrument_type: str | None = None,
                      status: str | None = None, year: int | None = None, issuer: str | None = None,
                      as_of: date | None = None) -> list[dict]:
    """Hanya pasal dari versi TERBIT. as_of = hanya versi yang berlaku pada tanggal itu."""
    where = ["dv.state = 'PUBLISHED'", "pv.text_search @@ plainto_tsquery('indonesian', :q)"]
    params: dict = {"q": q, "n": limit}
    if instrument_type:
        where.append("d.instrument_type = :itype")
        params["itype"] = instrument_type
    if status:
        where.append("d.status = :status")
        params["status"] = status
    if year:
        where.append("d.year = :year")
        params["year"] = year
    if issuer:
        where.append("d.issuer = :issuer")
        params["issuer"] = issuer
    if as_of:
        where.append("""dv.effective_date = (SELECT max(x.effective_date) FROM corpus.document_version x
                        WHERE x.document_id = d.id AND x.state = 'PUBLISHED' AND x.effective_date <= :as_of)""")
        params["as_of"] = as_of
    rows = db.execute(text(f"""
        SELECT pv.id, pv.text, p.number_label, d.id AS document_id, d.canonical_number, d.title_id,
               d.instrument_type, d.status, d.year, dv.version_number, dv.effective_date,
               ts_rank(pv.text_search, plainto_tsquery('indonesian', :q)) AS rank,
               ts_headline('indonesian', pv.text, plainto_tsquery('indonesian', :q),
                           'StartSel="[[", StopSel="]]", MaxWords=45, MinWords=20') AS snippet
        FROM corpus.provision_version pv
        JOIN corpus.provision p ON p.id = pv.provision_id
        JOIN corpus.document_version dv ON dv.id = pv.document_version_id
        JOIN corpus.document d ON d.id = dv.document_id
        WHERE {' AND '.join(where)}
        ORDER BY rank DESC, d.canonical_number, pv.sequence LIMIT :n"""), params).all()
    return [{"provision_version_id": str(r.id), "text": r.text, "snippet": r.snippet, "number_label": r.number_label,
             "document_id": str(r.document_id), "canonical_number": r.canonical_number, "title_id": r.title_id,
             "instrument_type": r.instrument_type, "status": r.status, "year": r.year,
             "version_number": r.version_number, "effective_date": str(r.effective_date),
             "rank": float(r.rank)} for r in rows]


# ---------------------------------------------------------------- katalog peraturan
def _doc_filter(stmt, q, instrument_type, status, year, issuer, label):
    for term in (q or "").split():
        pat = _like(term)
        stmt = stmt.where(or_(Document.canonical_number.ilike(pat, escape="\\"),
                              Document.title_id.ilike(pat, escape="\\")))
    if instrument_type:
        stmt = stmt.where(Document.instrument_type == instrument_type)
    if status:
        stmt = stmt.where(Document.status == status)
    if year:
        stmt = stmt.where(Document.year == year)
    if issuer:
        stmt = stmt.where(Document.issuer == issuer)
    if label:
        stmt = stmt.where(exists().where(TaxonomyLabel.document_id == Document.id, TaxonomyLabel.value == label,
                                         TaxonomyLabel.state != "REMOVED"))
    return stmt


def search_documents(db: Session, q: str | None = None, *, instrument_type: str | None = None,
                     status: str | None = None, year: int | None = None, issuer: str | None = None,
                     label: str | None = None, sort: str = "newest", limit: int = 20, offset: int = 0) -> dict:
    """Cari peraturan lewat nomor/judul (setiap kata harus cocok) + filter. Mengembalikan {total, items}."""
    base = _doc_filter(select(Document), q, instrument_type, status, year, issuer, label)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    if sort == "oldest":
        order = (Document.year.asc().nulls_last(), Document.canonical_number)
    elif sort == "title":
        order = (func.lower(Document.title_id), Document.canonical_number)
    else:
        order = (Document.year.desc().nulls_last(), Document.canonical_number)
    docs = db.scalars(base.order_by(*order).limit(limit).offset(offset)).all()
    ids = [d.id for d in docs]
    versions: dict = {}
    labels: dict = {}
    if ids:
        for dv in db.scalars(select(DocumentVersion).where(DocumentVersion.document_id.in_(ids))):
            versions.setdefault(dv.document_id, []).append(dv)
        for lb in db.scalars(select(TaxonomyLabel).where(TaxonomyLabel.document_id.in_(ids),
                                                         TaxonomyLabel.state != "REMOVED")):
            labels.setdefault(lb.document_id, []).append({"dimension": lb.dimension, "value": lb.value,
                                                          "state": lb.state})
    items = []
    for d in docs:
        vs = versions.get(d.id, [])
        pub = [v for v in vs if v.state == "PUBLISHED"]
        items.append({
            "id": str(d.id), "canonical_number": d.canonical_number, "number_display": normalise_number(d.canonical_number),
            "title_id": normalise_title(d.title_id), "instrument_type": d.instrument_type, "issuer": d.issuer,
            "status": d.status, "year": d.year, "enacted_date": str(d.enacted_date) if d.enacted_date else None,
            "promulgated_date": str(d.promulgated_date) if d.promulgated_date else None, "gazette_ref": d.gazette_ref,
            "labels": labels.get(d.id, []), "version_count": len(vs), "published_count": len(pub),
            "latest_effective_date": str(max(v.effective_date for v in pub)) if pub else None})
    return {"total": total, "limit": limit, "offset": offset, "items": items}


def facets(db: Session) -> dict:
    """Isi dropdown filter katalog + jumlah dokumen per nilai."""
    def counts(col, desc=False):
        order = col.desc() if desc else func.count().desc()
        return [{"value": v, "count": c} for v, c in
                db.execute(select(col, func.count()).where(col.is_not(None)).group_by(col).order_by(order, col))]
    lab = [{"dimension": dim, "value": val, "count": c} for dim, val, c in db.execute(
        select(TaxonomyLabel.dimension, TaxonomyLabel.value, func.count(distinct(TaxonomyLabel.document_id)))
        .where(TaxonomyLabel.state != "REMOVED").group_by(TaxonomyLabel.dimension, TaxonomyLabel.value)
        .order_by(TaxonomyLabel.dimension, TaxonomyLabel.value))]
    return {"instrument_type": counts(Document.instrument_type), "status": counts(Document.status),
            "issuer": counts(Document.issuer), "year": counts(Document.year, desc=True), "label": lab}


# ---------------------------------------------------------------- tampilan "berlaku per tanggal"
def provisions_as_of(db: Session, doc: Document, as_of: date) -> dict:
    """Pasal yang berlaku pada tanggal as_of = versi TERBIT dengan tanggal berlaku <= as_of yang paling baru."""
    dv = db.scalar(select(DocumentVersion).where(
        DocumentVersion.document_id == doc.id, DocumentVersion.state == "PUBLISHED",
        DocumentVersion.effective_date <= as_of).order_by(DocumentVersion.effective_date.desc(),
                                                          DocumentVersion.version_number.desc()).limit(1))
    if dv is None:
        first = db.scalar(select(func.min(DocumentVersion.effective_date)).where(
            DocumentVersion.document_id == doc.id, DocumentVersion.state == "PUBLISHED"))
        return {"as_of": str(as_of), "version": None, "later_version": None,
                "earliest_effective_date": str(first) if first else None, "provisions": []}
    later = db.scalar(select(func.min(DocumentVersion.effective_date)).where(
        DocumentVersion.document_id == doc.id, DocumentVersion.state == "PUBLISHED",
        DocumentVersion.effective_date > as_of))
    rows = db.execute(select(ProvisionVersion, Provision).join(Provision, Provision.id == ProvisionVersion.provision_id)
                      .where(ProvisionVersion.document_version_id == dv.id)
                      .order_by(ProvisionVersion.sequence)).all()
    return {"as_of": str(as_of),
            "version": {"id": str(dv.id), "version_number": dv.version_number, "effective_date": str(dv.effective_date)},
            "later_version": str(later) if later else None, "earliest_effective_date": None,
            "provisions": [{"provision_version_id": str(pv.id), "number_label": p.number_label,
                            "path": p.hierarchical_path, "text": pv.text} for pv, p in rows]}


# ---------------------------------------------------------------- detail peraturan + relasi
REL_OUT = {"AMENDS": "mengubah", "REVOKES": "mencabut", "PARTIALLY_REVOKES": "mencabut sebagian",
           "REFERS_TO": "merujuk", "IMPLEMENTS": "melaksanakan"}
REL_IN = {"AMENDS": "diubah oleh", "REVOKES": "dicabut oleh", "PARTIALLY_REVOKES": "dicabut sebagian oleh",
          "REFERS_TO": "dikutip oleh", "IMPLEMENTS": "dilaksanakan oleh"}


def document_detail(db: Session, doc: Document) -> dict:
    vs = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
                    .order_by(DocumentVersion.version_number)).all()
    counts = dict(db.execute(select(ProvisionVersion.document_version_id, func.count())
                             .where(ProvisionVersion.document_version_id.in_([v.id for v in vs]))
                             .group_by(ProvisionVersion.document_version_id)).all()) if vs else {}
    labels = [{"dimension": lb.dimension, "value": lb.value, "state": lb.state} for lb in db.scalars(
        select(TaxonomyLabel).where(TaxonomyLabel.document_id == doc.id, TaxonomyLabel.state != "REMOVED"))]
    rels = db.scalars(select(Relationship).where(or_(Relationship.source_document_id == doc.id,
                                                     Relationship.target_document_id == doc.id))
                      .order_by(Relationship.created_at.desc())).all()
    other_ids = {r.target_document_id if r.source_document_id == doc.id else r.source_document_id for r in rels}
    others = {d.id: d for d in db.scalars(select(Document).where(Document.id.in_(other_ids)))} if other_ids else {}
    relations = []
    for r in rels:
        out = r.source_document_id == doc.id
        o = others.get(r.target_document_id if out else r.source_document_id)
        if o is None:
            continue
        relations.append({"id": str(r.id), "relation_type": r.relation_type, "direction": "out" if out else "in",
                          "label": (REL_OUT if out else REL_IN).get(r.relation_type, r.relation_type),
                          "state": r.state, "note": r.note,
                          "other": {"id": str(o.id), "canonical_number": normalise_number(o.canonical_number),
                                    "title_id": normalise_title(o.title_id), "status": o.status}})
    return {
        "id": str(doc.id), "canonical_number": doc.canonical_number, "number_display": normalise_number(doc.canonical_number),
        "title_id": normalise_title(doc.title_id), "instrument_type": doc.instrument_type, "issuer": doc.issuer,
        "status": doc.status, "year": doc.year, "enacted_date": str(doc.enacted_date) if doc.enacted_date else None,
        "promulgated_date": str(doc.promulgated_date) if doc.promulgated_date else None, "gazette_ref": doc.gazette_ref,
        "labels": labels,
                "source": ({"id": str(src.id), "name": src.name, "status": src.status}
                   if (src := db.get(RegulatorySource, doc.source_id)) else None),
        "versions": [{"id": str(v.id), "version_number": v.version_number, "state": v.state,
                      "effective_date": str(v.effective_date), "extraction_method": v.extraction_method,
                      "provision_count": counts.get(v.id, 0), "origin_url": v.origin_url, "file_name": v.file_name,
                      "size_bytes": v.size_bytes, "has_file": bool(v.canonical_text_ref)} for v in vs],
        "relations": relations,
        "cited_by": [r for r in relations if r["direction"] == "in" and r["relation_type"] == "REFERS_TO"],
    }