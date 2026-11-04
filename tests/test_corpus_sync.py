"""Sinkronisasi korpus tim (app/corpus/sync.py): draf ikut dibagikan, perubahan terbaru menang,
penghapusan diteruskan, impor idempoten, dan ekspor otomatis dari endpoint."""
import json
import uuid
from datetime import date

import pytest

from app.corpus import sync
from tests.conftest import P, login


@pytest.fixture()
def korpus(tmp_path, monkeypatch):
    monkeypatch.setattr(sync, "ROOT", tmp_path)            # folder data/korpus sementara khusus tes
    monkeypatch.setattr(sync, "TEST_DOC_RE", __import__("re").compile(r"^$"))  # izinkan dokumen tes diekspor
    monkeypatch.setattr(sync.settings, "CORPUS_SYNC_AUTO", True)  # ekspor otomatis aktif selama tes ini
    return tmp_path


def _docs(client, h):
    return {x["canonical_number"]: x for x in client.get(f"{P}/corpus/documents", headers=h).json()["data"]}


def _as_other_laptop(folder, new_number):
    """Tiru laptop teman: dokumen yang sama dengan nomor yang belum ada di sini."""
    meta = json.loads((folder / "dokumen.json").read_text(encoding="utf-8"))
    meta["canonical_number"] = new_number
    (folder / "dokumen.json").write_text(json.dumps(meta), encoding="utf-8")


def test_draft_is_shared_then_updates_and_deletions_follow(client, korpus):
    a = login(client, "analyst")
    tag = uuid.uuid4().hex[:6]
    doc = client.post(f"{P}/corpus/documents", headers=a, json={
        "canonical_number": f"POJK TEST/{tag}/Sinkron", "title_id": "Uji sinkron"}).json()["data"]["id"]
    body = f"Pasal 1\nBank wajib melaporkan {tag} setiap bulan.\nPasal 2\nPelanggaran dikenai sanksi."
    up = client.post(f"{P}/corpus/documents/{doc}/versions", headers=a, files={"file": ("s.txt", body.encode())},
                     data={"effective_date": str(date.today())}).json()["data"]

    # 1) ekspor otomatis: unggahan DRAF langsung tertulis ke data/korpus
    folder = next(korpus.iterdir())
    vfile = next((folder / "versi").glob("*.json"))
    v = json.loads(vfile.read_text(encoding="utf-8"))
    assert v["state"] == "SEGMENTED_DRAFT" and len(v["provisions"]) == 2
    assert next((folder / "berkas").iterdir()).read_bytes() == body.encode()

    # 2) "laptop lain" mengimpor → draf terlihat dengan teks yang sama
    other = f"ZZZ UJI/{tag}"
    _as_other_laptop(folder, other)
    assert sync.import_all()["dokumen_baru"] == 1
    copy = _docs(client, a)[other]
    assert copy["versions"][0]["state"] == "SEGMENTED_DRAFT"
    provs = client.get(f"{P}/corpus/versions/{copy['versions'][0]['id']}/provisions", headers=a).json()["data"]
    assert tag in provs[0]["text"]
    assert sync.import_all()["versi_baru"] == 0  # impor ulang tidak menambah apa pun

    # 3) dokumen asal dikoreksi & dipublikasikan (ekspor otomatis) → laptop lain ikut terbarui
    pv1 = client.get(f"{P}/corpus/versions/{up['version_id']}/provisions", headers=a).json()["data"][0]["provision_version_id"]
    assert client.patch(f"{P}/corpus/provision-versions/{pv1}", headers=a, json={"text": f"Teks koreksi {tag}."}).status_code == 200
    assert client.post(f"{P}/corpus/versions/{up['version_id']}/publish", headers=a).status_code == 200
    _as_other_laptop(folder, other)
    assert sync.import_all()["versi_diperbarui"] == 1
    copy = _docs(client, a)[other]
    assert copy["status"] == "IN_FORCE" and copy["versions"][0]["state"] == "PUBLISHED"
    provs = client.get(f"{P}/corpus/versions/{copy['versions'][0]['id']}/provisions", headers=a).json()["data"]
    assert provs[0]["text"] == f"Teks koreksi {tag}."

    # 4) versi draf kedua dihapus di laptop asal → penanda hapus → laptop lain ikut menghapus
    up2 = client.post(f"{P}/corpus/documents/{doc}/versions", headers=a,
                      files={"file": ("s2.txt", (body + " v2").encode())},
                      data={"effective_date": str(date.today())}).json()["data"]
    _as_other_laptop(folder, other)
    assert sync.import_all()["versi_baru"] == 1
    assert len(_docs(client, a)[other]["versions"]) == 2
    assert client.delete(f"{P}/corpus/versions/{up2['version_id']}", headers=a).status_code == 200
    _as_other_laptop(folder, other)
    assert sync.import_all()["versi_dihapus"] == 1
    assert len(_docs(client, a)[other]["versions"]) == 1


def test_deleted_draft_document_is_removed_elsewhere(client, korpus):
    a = login(client, "analyst")
    tag = uuid.uuid4().hex[:6]
    doc = client.post(f"{P}/corpus/documents", headers=a, json={
        "canonical_number": f"POJK TEST/{tag}/Hapus", "title_id": "Uji hapus"}).json()["data"]["id"]
    client.post(f"{P}/corpus/documents/{doc}/versions", headers=a,
                files={"file": ("h.txt", f"Pasal 1\nIsi pasal {tag} cukup panjang.".encode())},
                data={"effective_date": str(date.today())})
    folder = next(korpus.iterdir())
    other = f"ZZZ UJI/{tag}"
    _as_other_laptop(folder, other)
    sync.import_all()
    assert other in _docs(client, a)
    # dokumen asal dihapus → dokumen.json ditandai deleted_at (folder dikembalikan ke nomor asal agar cocok)
    meta = json.loads((folder / "dokumen.json").read_text(encoding="utf-8"))
    meta["canonical_number"] = f"POJK TEST/{tag}/Hapus"
    (folder / "dokumen.json").write_text(json.dumps(meta), encoding="utf-8")
    assert client.delete(f"{P}/corpus/documents/{doc}", headers=a).status_code == 200
    meta = json.loads((folder / "dokumen.json").read_text(encoding="utf-8"))
    assert meta["deleted_at"]
    _as_other_laptop(folder, other)
    assert sync.import_all()["dokumen_dihapus"] == 1
    assert other not in _docs(client, a)