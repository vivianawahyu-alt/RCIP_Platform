"""Sinkronisasi korpus regulasi antar-laptop lewat Git, termasuk versi DRAF.

    python -m app.corpus.sync export   # tulis seluruh korpus laptop ini ke folder data/korpus
    python -m app.corpus.sync import   # terapkan perubahan dari data/korpus ke database laptop ini

Biasanya kedua perintah itu TIDAK perlu diketik:
  - ekspor berjalan otomatis setiap kali korpus berubah lewat aplikasi (daftar dokumen, unggah versi,
    koreksi/konfirmasi teks, publikasi, tarik, hapus) → tinggal Commit & Push di GitHub Desktop;
  - impor berjalan otomatis setiap kali container api menyala → teman cukup Pull lalu
    `docker compose restart api`.
  Matikan dengan CORPUS_SYNC_AUTO=false di .env.

Tata letak folder (satu dokumen = satu folder, satu versi = satu file → jarang bentrok di Git):
    data/korpus/<nomor-regulasi>/dokumen.json          data dokumen, sumber, label
    data/korpus/<nomor-regulasi>/versi/<sha12>.json    satu versi: status, teks pasal, tanda OCR
    data/korpus/<nomor-regulasi>/berkas/<sha12>.pdf    berkas asli (PDF/TXT)

Aturan penggabungan:
  - versi dikenali dari sidik jari (sha256) berkas aslinya, sama di semua laptop;
  - setiap versi membawa `updated_at` (waktu perubahan terakhir, dari jejak audit). Bila versi yang sama
    diubah di dua laptop, perubahan yang LEBIH BARU yang dipakai;
  - versi yang sudah terbit tetap imutabel: impor hanya boleh meneruskan penarikan (PUBLISHED → WITHDRAWN);
  - penghapusan versi draf / dokumen draf ikut diteruskan lewat penanda `deleted_at`.
Data kepatuhan (kewajiban, kontrol, bukti, dst.) TIDAK ikut disinkronkan.
"""
import argparse
import hashlib
import json
import logging
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.corpus.models import (Document, DocumentVersion, Provision, ProvisionVersion, RegulatorySource,
                               TaxonomyLabel)
from app.platform.governance import audit
from app.platform.models import AuditEvent
from app.shared.config import settings
from app.shared.database import SessionLocal
from app.shared.storage import get_object, put_object

log = logging.getLogger("rcip.corpus_sync")
ROOT = Path(__file__).resolve().parents[2] / "data" / "korpus"
FORMAT = 2
EPOCH = "1970-01-01T00:00:00+00:00"
DRAFT_STATES = ("PARSING", "SEGMENTED_DRAFT", "UNDER_CORRECTION")
FROZEN_STATES = ("PUBLISHED", "WITHDRAWN")
TEST_DOC_RE = re.compile(r"^(POJK TEST|POJK GOV|POJK OCR|ZZZ UJI)/[0-9a-f]{6}(/|$)")  # dokumen buatan tes
SYNC_ACTION = "CORPUS_SYNCED"


# ------------------------------------------------------------------------------------------------------
# utilitas
# ------------------------------------------------------------------------------------------------------
def _slug(canonical_number: str) -> str:
    """Nama folder: nomor regulasi yang aman untuk nama file + 6 karakter hash agar tidak bentrok
    (mis. "1 /POJK.04/2021" dan "1/POJK.04/2021" tetap beda folder)."""
    base = re.sub(r"[^A-Za-z0-9]+", "_", canonical_number).strip("_")[:60] or "dokumen"
    return f"{base}-{hashlib.sha1(canonical_number.encode()).hexdigest()[:6]}"


def _ts(value) -> datetime:
    """Ubah teks/datetime menjadi datetime UTC agar bisa dibandingkan."""
    if isinstance(value, datetime):
        d = value
    else:
        d = datetime.fromisoformat(value or EPOCH)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _iso(value: datetime) -> str:
    return _ts(value).astimezone(timezone.utc).isoformat(timespec="microseconds")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != text:  # tidak menulis bila isinya sama
        path.write_text(text, encoding="utf-8")


def _meta_revision(db, doc: Document) -> str:
    """Waktu perubahan terakhir data dokumen (nomor, judul, jenis, penerbit) dari jejak audit."""
    best = _ts(doc.created_at) if doc.created_at else _ts(EPOCH)
    for action, at, after in db.execute(select(AuditEvent.action, AuditEvent.occurred_at, AuditEvent.after_state)
                                        .where(AuditEvent.object_id == doc.id,
                                               AuditEvent.action.in_(("DOCUMENT_UPDATED", SYNC_ACTION)))):
        if action == SYNC_ACTION:
            t = (after or {}).get("meta_updated_at")
            if not t:
                continue
            best = max(best, _ts(t))
        else:
            best = max(best, _ts(at))
    return _iso(best)


def _revision(db, dv: DocumentVersion) -> str:
    """Waktu perubahan terakhir sebuah versi, diambil dari jejak audit versi & pasal-pasalnya.
    Peristiwa sinkronisasi memakai waktu ASAL perubahan (dari laptop lain), bukan waktu impornya."""
    ids = [dv.id] + list(db.scalars(select(ProvisionVersion.id).where(ProvisionVersion.document_version_id == dv.id)))
    best = _ts(EPOCH)
    for action, at, after in db.execute(select(AuditEvent.action, AuditEvent.occurred_at, AuditEvent.after_state)
                                        .where(AuditEvent.object_id.in_(ids))):
        t = _ts((after or {}).get("updated_at")) if action == SYNC_ACTION else _ts(at)
        best = max(best, t)
    return _iso(best)


# ------------------------------------------------------------------------------------------------------
# EKSPOR
# ------------------------------------------------------------------------------------------------------
def _version_payload(db, dv: DocumentVersion, folder: Path, prev: dict) -> dict:
    rows = db.execute(select(ProvisionVersion, Provision)
                      .join(Provision, Provision.id == ProvisionVersion.provision_id)
                      .where(ProvisionVersion.document_version_id == dv.id)
                      .order_by(ProvisionVersion.sequence)).all()
    ext = Path(dv.canonical_text_ref or "").suffix.lower() or ".bin"
    fname = prev.get("file") or f"{dv.sha256[:12]}{ext}"
    if not (folder / "berkas" / fname).exists():
        raw = get_object(dv.canonical_text_ref) if dv.canonical_text_ref else None
        if raw is not None:
            (folder / "berkas").mkdir(parents=True, exist_ok=True)
            (folder / "berkas" / fname).write_bytes(raw)  # salinan berkas asli agar bisa diunduh di laptop lain
    prev_ids = {x["provision_key"]: x["id"] for x in prev.get("provisions", [])}
    return {
        # id & kunci berkas yang sudah tercatat dipertahankan → ekspor dari laptop mana pun menghasilkan isi sama
        "id": prev.get("id", str(dv.id)), "storage_key": prev.get("storage_key", dv.canonical_text_ref),
        "sha256": dv.sha256, "effective_date": str(dv.effective_date), "state": dv.state,
        "origin_url": dv.origin_url, "is_partial": dv.is_partial,
        "extraction_method": dv.extraction_method, "ocr_pages": dv.ocr_pages or [],
        "file": fname if (folder / "berkas" / fname).exists() else None,
        "updated_at": _revision(db, dv),
        "provisions": [{"id": prev_ids.get(p.provision_key, str(pv.id)), "provision_key": p.provision_key,
                        "provision_type": p.provision_type, "number_label": p.number_label,
                        "hierarchical_path": p.hierarchical_path, "sequence": pv.sequence, "text": pv.text,
                        "segmentation_confidence": float(pv.segmentation_confidence),
                        "corrected_by_human": pv.corrected_by_human,
                        "low_confidence_text": pv.low_confidence_text} for pv, p in rows],
    }


def export_document(db, doc: Document) -> int:
    """Tulis satu dokumen (semua versinya, termasuk draf) ke foldernya. Mengembalikan jumlah versi."""
    folder = ROOT / _slug(doc.canonical_number)
    meta_path = folder / "dokumen.json"
    old = _read(meta_path)

    # label: gabungkan dengan yang sudah tercatat; hanya peningkatan menjadi CONFIRMED yang menimpa
    labels = {(lb["dimension"], lb["value"]): lb for lb in old.get("labels", [])}
    for lb in db.scalars(select(TaxonomyLabel).where(TaxonomyLabel.document_id == doc.id,
                                                     TaxonomyLabel.state != "REMOVED")):
        prev = labels.get((lb.dimension, lb.value))
        if not prev or (lb.state == "CONFIRMED" and prev["state"] != "CONFIRMED"):
            labels[(lb.dimension, lb.value)] = {"dimension": lb.dimension, "value": lb.value, "state": lb.state,
                                                "source": lb.source, "reason": lb.reason}
    src = db.get(RegulatorySource, doc.source_id)
    if old and old.get("meta_updated_at") and _ts(old["meta_updated_at"]) > _ts(_meta_revision(db, doc)):
        # data dokumen di folder lebih baru (diubah di laptop lain, belum diimpor di sini) → pertahankan
        doc_fields = {k: old[k] for k in ("instrument_type", "issuer", "title_id", "meta_updated_at")}
    else:
        doc_fields = {}
    _write(meta_path, {
        "format": FORMAT, "id": old.get("id", str(doc.id)),
        "canonical_number": doc.canonical_number, "instrument_type": doc.instrument_type, "issuer": doc.issuer,
        "title_id": doc.title_id, "created_at": old.get("created_at", _iso(doc.created_at)),
        "meta_updated_at": _meta_revision(db, doc),  # perubahan judul/jenis/penerbit terbaru menang di laptop lain
        "deleted_at": None,  # dokumen ada di laptop ini → bukan penanda hapus
        "source": {"name": src.name, "category": src.category, "issuer_name": src.issuer_name,
                   "base_url": src.base_url, "permitted_use_statement": src.permitted_use_statement,
                   "status": src.status},
        "labels": sorted(labels.values(), key=lambda x: (x["dimension"], x["value"])),
        **doc_fields,
    })

    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)).all()
    for dv in versions:
        path = folder / "versi" / f"{dv.sha256[:12]}.json"
        prev = _read(path)
        entry = _version_payload(db, dv, folder, prev)
        # file yang ada lebih baru (diubah di laptop lain & belum diimpor di sini) → jangan ditimpa
        if prev and _ts(prev.get("updated_at")) > _ts(entry["updated_at"]):
            continue
        _write(path, entry)

    # versi draf yang dihapus di laptop ini → penanda hapus agar laptop lain ikut menghapus
    for at, before in db.execute(select(AuditEvent.occurred_at, AuditEvent.before_state).where(
            AuditEvent.action == "VERSION_DELETED")):
        before = before or {}
        if before.get("document_id") != str(doc.id) or not before.get("sha256"):
            continue
        if any(v.sha256 == before["sha256"] for v in versions):
            continue  # berkas yang sama diunggah ulang setelah dihapus → versinya hidup lagi
        path = folder / "versi" / f"{before['sha256'][:12]}.json"
        prev = _read(path)
        if prev and _ts(prev.get("updated_at")) >= _ts(at):
            continue
        _write(path, {"sha256": before["sha256"], "deleted_at": _iso(at), "updated_at": _iso(at)})
    return len(versions)


def export_deleted_documents(db) -> None:
    """Dokumen yang dihapus — atau nomornya diganti — di laptop ini → tandai folder nomor LAMA dengan deleted_at,
    agar laptop lain ikut menghapus dokumen bernomor lama (folder bernomor baru dibuat oleh export_document)."""
    for action, at, before, after in db.execute(
            select(AuditEvent.action, AuditEvent.occurred_at, AuditEvent.before_state, AuditEvent.after_state)
            .where(AuditEvent.action.in_(("DOCUMENT_DELETED", "DOCUMENT_UPDATED")))):
        number = (before or {}).get("canonical_number")
        if action == "DOCUMENT_UPDATED" and number == (after or {}).get("canonical_number"):
            continue  # hanya judul/jenis yang berubah, bukan nomornya
        if not number or TEST_DOC_RE.match(number):
            continue
        if db.scalar(select(Document.id).where(Document.canonical_number == number)):
            continue  # sudah didaftarkan lagi
        meta_path = ROOT / _slug(number) / "dokumen.json"
        meta = _read(meta_path)
        if meta and (not meta.get("deleted_at") or _ts(meta["deleted_at"]) < _ts(at)):
            meta["deleted_at"] = _iso(at)
            _write(meta_path, meta)


def export_all() -> int:
    db = SessionLocal()
    try:
        n = 0
        for doc in db.scalars(select(Document).order_by(Document.canonical_number)):
            if not TEST_DOC_RE.match(doc.canonical_number):
                export_document(db, doc)
                n += 1
        export_deleted_documents(db)
        return n
    finally:
        db.close()


def auto_export(db, doc_id=None) -> None:
    """Dipanggil endpoint korpus setelah commit. Tidak pernah menggagalkan permintaan pengguna."""
    if not settings.CORPUS_SYNC_AUTO:
        return
    try:
        doc = db.get(Document, uuid.UUID(str(doc_id))) if doc_id else None
        if doc is not None and not TEST_DOC_RE.match(doc.canonical_number):
            export_document(db, doc)
        export_deleted_documents(db)  # penanda hapus / ganti nomor (murah: hanya membaca jejak audit)
    except Exception:  # noqa: BLE001 — sinkronisasi gagal tidak boleh menggagalkan unggahan/publikasi
        log.exception("Ekspor otomatis korpus gagal (data di database tetap tersimpan)")


# ------------------------------------------------------------------------------------------------------
# IMPOR
# ------------------------------------------------------------------------------------------------------
def _free_id(db, model, wanted):
    """Pakai id dari laptop asal bila belum terpakai (agar id sama di semua laptop); bila terpakai, buat baru."""
    try:
        u = uuid.UUID(str(wanted))
    except (TypeError, ValueError):
        return uuid.uuid4()
    return uuid.uuid4() if db.get(model, u) is not None else u


def _get_source(db, s: dict) -> RegulatorySource:
    src = db.scalar(select(RegulatorySource).where(RegulatorySource.name == s["name"]))
    if not src:
        from app.corpus.services import DEFAULT_PERMITTED_USE
        # sumber ACTIVE wajib punya pernyataan penggunaan (aturan DB migrasi 006)
        src = RegulatorySource(name=s["name"], category=s["category"], issuer_name=s["issuer_name"],
                               base_url=s["base_url"], url_allow_list=[s["base_url"]],
                               permitted_use_statement=s.get("permitted_use_statement") or DEFAULT_PERMITTED_USE,
                               status="ACTIVE")
        db.add(src)
        db.flush()
    return src


def _write_provisions(db, doc: Document, dv: DocumentVersion, provisions: list[dict]) -> None:
    for pv in sorted(provisions, key=lambda x: x["sequence"]):
        prov = db.scalar(select(Provision).where(Provision.document_id == doc.id,
                                                 Provision.provision_key == pv["provision_key"]))
        if prov is None:
            prov = Provision(document_id=doc.id, provision_key=pv["provision_key"],
                             provision_type=pv.get("provision_type") or "PASAL", number_label=pv["number_label"],
                             hierarchical_path=pv["hierarchical_path"])
            db.add(prov)
            db.flush()
        db.add(ProvisionVersion(id=_free_id(db, ProvisionVersion, pv.get("id")), provision_id=prov.id,
                                document_version_id=dv.id, sequence=pv["sequence"], text=pv["text"],
                                segmentation_confidence=pv["segmentation_confidence"],
                                corrected_by_human=pv.get("corrected_by_human", False),
                                low_confidence_text=pv.get("low_confidence_text", False)))
    db.flush()


def _referenced(db, dv: DocumentVersion) -> int:
    from app.corpus.router import _version_refs
    return sum(_version_refs(db, dv).values())


def _sync_audit(db, dv_id, v: dict, folder: Path, **extra) -> None:
    audit(db, None, SYNC_ACTION, "document_version", dv_id,
          after={"from": folder.name, "sha256": v["sha256"], "updated_at": v["updated_at"], **extra})


def _import_version(db, doc: Document, folder: Path, v: dict, local: dict, stats: dict) -> None:
    from app.corpus.router import _delete_draft_version
    dv = local.get(v["sha256"])

    if v.get("deleted_at"):  # ---- penanda hapus dari laptop lain
        if dv is None or dv.state in FROZEN_STATES or _ts(_revision(db, dv)) >= _ts(v["deleted_at"]):
            return  # tidak ada / sudah terbit / diubah lagi di sini setelah dihapus di sana
        if _referenced(db, dv):
            stats["peringatan"].append(f"{doc.canonical_number} v{dv.version_number}: dihapus di laptop lain, "
                                       "tetapi di sini masih dirujuk → tidak dihapus")
            return
        number = dv.version_number
        _delete_draft_version(db, dv)
        audit(db, None, SYNC_ACTION, "document", doc.id, after={"from": folder.name, "sha256": v["sha256"],
                                                                "deleted_version": number})
        local.pop(v["sha256"], None)
        stats["versi_dihapus"] += 1
        return

    if dv is None:  # ---- versi baru
        next_no = (db.scalar(select(func.max(DocumentVersion.version_number))
                             .where(DocumentVersion.document_id == doc.id)) or 0) + 1
        key = v.get("storage_key") or f"korpus/{folder.name}/{v.get('file') or v['sha256']}"
        dv = DocumentVersion(id=_free_id(db, DocumentVersion, v.get("id")), document_id=doc.id,
                             version_number=next_no, sha256=v["sha256"], origin_url=v["origin_url"],
                             canonical_text_ref=key, effective_date=date.fromisoformat(v["effective_date"]),
                             state="SEGMENTED_DRAFT", is_partial=v.get("is_partial", False),
                             extraction_method=v.get("extraction_method") or "TEXT_LAYER",
                             ocr_pages=v.get("ocr_pages") or [])
        db.add(dv)
        db.flush()
        _write_provisions(db, doc, dv, v["provisions"])
        dv.state = v["state"]  # status diset setelah pasal masuk (trigger OCR memeriksa saat menjadi PUBLISHED)
        berkas = folder / "berkas" / (v.get("file") or "")
        if v.get("file") and berkas.exists() and get_object(key) is None:
            put_object(key, berkas.read_bytes())  # berkas asli ikut tersedia untuk diunduh
        db.flush()
        _sync_audit(db, dv.id, v, folder, created=True)
        local[v["sha256"]] = dv
        stats["versi_baru"] += 1
        return

    # ---- versi sudah ada: terapkan hanya bila file lebih baru daripada perubahan terakhir di sini
    if _ts(v["updated_at"]) <= _ts(_revision(db, dv)):
        return
    if dv.state in FROZEN_STATES:  # versi terbit imutabel: hanya penarikan yang diteruskan
        if dv.state == "PUBLISHED" and v["state"] == "WITHDRAWN":
            from app.compliance.models import Obligation
            cited = db.scalar(select(func.count()).select_from(Obligation).join(
                ProvisionVersion, ProvisionVersion.id == Obligation.primary_citation_id).where(
                ProvisionVersion.document_version_id == dv.id))
            if cited:
                stats["peringatan"].append(f"{doc.canonical_number} v{dv.version_number}: ditarik di laptop lain, "
                                           f"tetapi di sini masih dirujuk {cited} kewajiban → tidak ditarik")
                return
            dv.state = "WITHDRAWN"
            db.flush()
            _sync_audit(db, dv.id, v, folder)
            stats["versi_diperbarui"] += 1
        return
    # versi draf di sini → ganti isinya dengan versi yang lebih baru (koreksi, konfirmasi OCR, publikasi)
    for pv in db.scalars(select(ProvisionVersion).where(ProvisionVersion.document_version_id == dv.id)):
        db.delete(pv)
    db.flush()
    _write_provisions(db, doc, dv, v["provisions"])
    dv.effective_date, dv.origin_url = date.fromisoformat(v["effective_date"]), v["origin_url"]
    dv.extraction_method, dv.ocr_pages = v.get("extraction_method") or dv.extraction_method, v.get("ocr_pages") or []
    dv.state = v["state"]
    db.flush()
    _sync_audit(db, dv.id, v, folder)
    stats["versi_diperbarui"] += 1


def _import_deleted_document(db, doc: Document, meta: dict, folder: Path, stats: dict) -> None:
    from app.corpus.models import Relationship
    from app.corpus.router import _delete_draft_version
    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)).all()
    newest_here = max([_ts(doc.created_at)] + [_ts(_revision(db, v)) for v in versions])
    if newest_here >= _ts(meta["deleted_at"]):
        return  # didaftarkan / diubah lagi di sini setelah dihapus di laptop lain
    rels = db.scalars(select(Relationship).where((Relationship.source_document_id == doc.id)
                                                 | (Relationship.target_document_id == doc.id))).all()
    if any(v.state in FROZEN_STATES for v in versions) or any(r.state == "CONFIRMED" for r in rels) \
            or any(_referenced(db, v) for v in versions):
        stats["peringatan"].append(f"{doc.canonical_number}: dihapus di laptop lain, tetapi di sini sudah terbit "
                                   "atau masih dirujuk → tidak dihapus")
        return
    for r in rels:
        db.delete(r)
    for lb in db.scalars(select(TaxonomyLabel).where(TaxonomyLabel.document_id == doc.id)):
        db.delete(lb)
    for v in versions:
        _delete_draft_version(db, v)
    for p in db.scalars(select(Provision).where(Provision.document_id == doc.id)):
        db.delete(p)
    db.flush()
    audit(db, None, SYNC_ACTION, "document", doc.id, after={"from": folder.name, "deleted": True,
                                                            "canonical_number": doc.canonical_number})
    db.delete(doc)
    db.flush()
    stats["dokumen_dihapus"] += 1


def _import_document(db, folder: Path, stats: dict) -> None:
    meta = _read(folder / "dokumen.json")
    doc = db.scalar(select(Document).where(Document.canonical_number == meta["canonical_number"]))
    if meta.get("deleted_at"):
        if doc is not None:
            _import_deleted_document(db, doc, meta, folder, stats)
        return
    if doc is None:  # dokumen belum ada di laptop ini → buat
        doc = Document(id=_free_id(db, Document, meta.get("id")), source_id=_get_source(db, meta["source"]).id,
                       canonical_number=meta["canonical_number"], instrument_type=meta["instrument_type"],
                       issuer=meta["issuer"], title_id=meta["title_id"], status="DRAFT",
                       created_at=_ts(meta["created_at"]))
        db.add(doc)
        db.flush()
        audit(db, None, SYNC_ACTION, "document", doc.id, after={"from": folder.name, "created": True,
                                                                "meta_updated_at": meta.get("meta_updated_at")})
        stats["dokumen_baru"] += 1
    elif meta.get("meta_updated_at") and _ts(meta["meta_updated_at"]) > _ts(_meta_revision(db, doc)):
        # judul / jenis / penerbit diubah di laptop lain lebih baru → terapkan di sini
        doc.title_id, doc.instrument_type, doc.issuer = meta["title_id"], meta["instrument_type"], meta["issuer"]
        audit(db, None, SYNC_ACTION, "document", doc.id, after={"from": folder.name,
                                                                "meta_updated_at": meta["meta_updated_at"]})
        stats["dokumen_diperbarui"] += 1

    have = {(lb.dimension, lb.value): lb for lb in db.scalars(
        select(TaxonomyLabel).where(TaxonomyLabel.document_id == doc.id))}
    for lb in meta.get("labels", []):
        cur = have.get((lb["dimension"], lb["value"]))
        if cur is None:
            db.add(TaxonomyLabel(document_id=doc.id, dimension=lb["dimension"], value=lb["value"],
                                 state=lb["state"], source=lb.get("source") or "RULE", reason=lb.get("reason")))
        elif lb["state"] == "CONFIRMED" and cur.state != "CONFIRMED":
            cur.state = "CONFIRMED"

    local = {dv.sha256: dv for dv in db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id))}
    files = [_read(p) for p in sorted((folder / "versi").glob("*.json"))] if (folder / "versi").exists() else []
    # urutan sama di semua laptop: tanggal berlaku lalu sidik jari (penanda hapus di akhir)
    for v in sorted(files, key=lambda x: (x.get("effective_date", "9999"), x["sha256"])):
        _import_version(db, doc, folder, v, local, stats)

    # status dokumen mengikuti versinya (sama seperti aplikasi)
    states = {dv.state for dv in local.values()}
    if "PUBLISHED" in states:
        doc.status = "IN_FORCE"
    elif doc.status == "IN_FORCE":
        doc.status = "DRAFT"


def import_all() -> dict:
    stats = {"dokumen_baru": 0, "dokumen_diperbarui": 0, "dokumen_dihapus": 0, "versi_baru": 0,
             "versi_diperbarui": 0, "versi_dihapus": 0, "peringatan": []}
    if not ROOT.exists():
        return stats
    db = SessionLocal()
    try:
        for folder in sorted(p for p in ROOT.iterdir() if (p / "dokumen.json").exists()):
            _import_document(db, folder, stats)
        db.commit()
        return stats
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("aksi", choices=["export", "import"])
    args = ap.parse_args()
    if args.aksi == "export":
        n = export_all()
        print(f"EKSPOR SELESAI: {n} dokumen → {ROOT}")
        print("Langkah berikutnya: GitHub Desktop → centang folder data/korpus → Commit → Push origin.")
    else:
        s = import_all()
        print(f"IMPOR SELESAI: {s['dokumen_baru']} dokumen baru, {s['dokumen_diperbarui']} dokumen diperbarui, "
              f"{s['dokumen_dihapus']} dokumen dihapus, "
              f"{s['versi_baru']} versi baru, {s['versi_diperbarui']} versi diperbarui, "
              f"{s['versi_dihapus']} versi dihapus.")
        for w in s["peringatan"]:
            print("  PERINGATAN:", w)


if __name__ == "__main__":
    main()