"""Kelengkapan peran Regulatory Analyst:
FR-RKM-001 registri sumber · FR-RKM-002 URL asal wajib, cek duplikat, provenans, berkas asli ·
ubah data dokumen · FR-COP-005 putusan tinjauan copilot."""
import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import ORIGIN, P, login


def _source(client, submit=True, **kw):
    tag = uuid.uuid4().hex[:6]
    body = {"name": f"Sumber Uji {tag}", "category": "OJK", "issuer_name": "Otoritas Jasa Keuangan",
            "base_url": f"https://uji-{tag}.example.id", "permitted_use_statement": "Publik; untuk uji.", "submit": submit}
    body.update(kw)
    r = client.post(f"{P}/corpus/sources", headers=login(client, "analyst"), json=body)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"], body


def _doc(client, h, **kw):
    body = {"canonical_number": f"POJK TEST/{uuid.uuid4().hex[:6]}/Analis", "title_id": "Uji analis", **kw}
    r = client.post(f"{P}/corpus/documents", headers=h, json=body)
    return r


def _upload(client, h, doc, content: bytes, origin=ORIGIN, name="u.txt"):
    data = {"effective_date": str(date.today())}
    if origin is not None:
        data["origin_url"] = origin
    return client.post(f"{P}/corpus/documents/{doc}/versions", headers=h, files={"file": (name, content)}, data=data)


def test_source_registry_lifecycle(client):
    a, m, o = login(client, "analyst"), login(client, "admin"), login(client, "officer")  # m = Administrator (penyetuju sumber)
    sid, body = _source(client)
    srcs = {s["id"]: s for s in client.get(f"{P}/corpus/sources", headers=o).json()["data"]}
    assert srcs[sid]["status"] == "PENDING_USE_REVIEW" and srcs[sid]["submitted_by"] == "analyst"
    # sumber ganda ditolak (nama sama)
    dup = client.post(f"{P}/corpus/sources", headers=a, json={**body, "base_url": "https://lain.example.id"})
    assert dup.status_code == 409 and dup.json()["error_code"] == "DUPLICATE_SOURCE"
    # dokumen tidak boleh didaftarkan dari sumber yang belum ACTIVE
    blocked = _doc(client, a, source_id=sid)
    assert blocked.status_code == 409 and blocked.json()["error_code"] == "SOURCE_NOT_ACTIVE"
    # analis (pengaju) & manajer tidak boleh memutus; penolakan wajib alasan; Administrator menyetujui
    assert client.post(f"{P}/corpus/sources/{sid}/decision", headers=a, json={"outcome": "APPROVED"}).status_code == 403
    assert client.post(f"{P}/corpus/sources/{sid}/decision", headers=login(client, "manager"),
                       json={"outcome": "APPROVED"}).status_code == 403  # matriks: Manajer hanya R pada registri sumber
    assert client.post(f"{P}/corpus/sources/{sid}/decision", headers=m, json={"outcome": "REJECTED"}).status_code == 422
    assert client.post(f"{P}/corpus/sources/{sid}/decision", headers=m, json={"outcome": "APPROVED"}).json()["data"]["status"] == "ACTIVE"
    doc = _doc(client, a, source_id=sid)
    assert doc.status_code == 200, doc.text
    doc_id = doc.json()["data"]["id"]
    # sumber ditangguhkan → unggahan ditolak dengan status sumbernya
    assert client.post(f"{P}/corpus/sources/{sid}/status", headers=m,
                       json={"status": "SUSPENDED", "reason": "uji"}).json()["data"]["status"] == "SUSPENDED"
    r = _upload(client, a, doc_id, f"Pasal 1\nIsi {uuid.uuid4().hex} cukup panjang.".encode(), origin=body["base_url"] + "/a")
    assert r.status_code == 409 and r.json()["error_code"] == "SOURCE_NOT_ACTIVE"


def test_source_without_permitted_use_cannot_be_approved(client):
    sid, _ = _source(client, permitted_use_statement="")
    r = client.post(f"{P}/corpus/sources/{sid}/decision", headers=login(client, "admin"), json={"outcome": "APPROVED"})
    assert r.status_code == 422 and r.json()["error_code"] == "PERMITTED_USE_REQUIRED"


def test_upload_provenance_duplicate_and_original_file(client):
    a, o = login(client, "analyst"), login(client, "officer")
    doc = _doc(client, a).json()["data"]["id"]
    content = f"Dokumen uji {uuid.uuid4().hex}\nPasal 1\nBank wajib menjaga data nasabah setiap saat.".encode()
    # URL asal wajib dan harus http(s)
    assert _upload(client, a, doc, content, origin=None).status_code == 422
    bad = _upload(client, a, doc, content, origin="ftp://ojk.go.id/x")
    assert bad.status_code == 422 and bad.json()["error_code"] == "INVALID_URL"
    ok = _upload(client, a, doc, content)
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["origin_outside_source"] is False
    vid = ok.json()["data"]["version_id"]
    # berkas yang sama persis ke dokumen lain → DUPLICATE_SUSPECTED + menyebut dokumen yang sudah ada
    other = _doc(client, a).json()["data"]["id"]
    dup = _upload(client, a, other, content)
    assert dup.status_code == 409 and dup.json()["error_code"] == "DUPLICATE_SUSPECTED"
    assert dup.json()["offending"]["existing_version_id"] == vid
    # URL di luar situs sumber tetap diterima, tetapi ditandai
    far = _upload(client, a, other, content + b"\n", origin="https://contoh-lain.example.com/x")
    assert far.status_code == 200 and far.json()["data"]["origin_outside_source"] is True
    # provenans tercatat & berkas asli bisa dibuka oleh peran mana pun
    v = next(d for d in client.get(f"{P}/corpus/documents", headers=o).json()["data"] if d["id"] == doc)["versions"][0]
    assert v["origin_url"] == ORIGIN and v["file_name"] == "u.txt" and v["size_bytes"] == len(content) and v["has_file"]
    f = client.get(f"{P}/corpus/versions/{vid}/file", headers=o)
    assert f.status_code == 200 and f.content == content and f.headers["content-type"].startswith("text/plain")
    assert client.get(f"{P}/corpus/versions/{uuid.uuid4()}/file", headers=o).status_code == 404


def test_update_document_number_frozen_after_publish(client):
    a = login(client, "analyst")
    doc = _doc(client, a).json()["data"]["id"]
    new_no = f"POJK TEST/{uuid.uuid4().hex[:6]}/Ganti"
    r = client.patch(f"{P}/corpus/documents/{doc}", headers=a, json={"canonical_number": new_no, "title_id": "Judul baru"})
    assert r.status_code == 200 and r.json()["data"]["changed"]
    d = next(x for x in client.get(f"{P}/corpus/documents", headers=a).json()["data"] if x["id"] == doc)
    assert d["canonical_number"] == new_no and d["title_id"] == "Judul baru"
    assert client.patch(f"{P}/corpus/documents/{doc}", headers=a, json={"title_id": "  "}).status_code == 422
    assert client.patch(f"{P}/corpus/documents/{doc}", headers=login(client, "officer"), json={"title_id": "x"}).status_code == 403
    vid = _upload(client, a, doc, f"Pasal 1\nIsi pasal {uuid.uuid4().hex} cukup panjang.".encode()).json()["data"]["version_id"]
    assert client.post(f"{P}/corpus/versions/{vid}/publish", headers=a).status_code == 200
    frozen = client.patch(f"{P}/corpus/documents/{doc}", headers=a, json={"canonical_number": new_no + "X"})
    assert frozen.status_code == 409 and frozen.json()["error_code"] == "NUMBER_FROZEN"
    # judul tetap boleh diperbaiki setelah terbit
    assert client.patch(f"{P}/corpus/documents/{doc}", headers=a, json={"title_id": "Judul final"}).status_code == 200
    acts = [e["action"] for e in client.get(f"{P}/audit?object_id={doc}", headers=login(client, "auditor")).json()["data"]]
    assert acts.count("DOCUMENT_UPDATED") == 2


def test_copilot_low_confidence_review_by_analyst(client, db):
    a, o, auditor = login(client, "analyst"), login(client, "officer"), login(client, "auditor")
    w1, w2 = f"kripto{uuid.uuid4().hex[:5]}", f"dompet{uuid.uuid4().hex[:5]}"
    doc = _doc(client, a).json()["data"]["id"]
    vid = _upload(client, a, doc, f"Pasal 1\nPenyelenggara {w1} wajib mengamankan {w2} pelanggan.".encode()).json()["data"]["version_id"]
    client.post(f"{P}/corpus/versions/{vid}/publish", headers=a)
    # dua istilah cocok, satu tidak → jawaban disajikan dengan keyakinan < 0,70 → ditandai
    ans = client.post(f"{P}/copilot/query", headers=o, json={"question": f"{w1} {w2} zzq{uuid.uuid4().hex[:5]}"}).json()["data"]
    assert ans["state"] == "PRESENTED" and ans["low_confidence"] is True and ans["confidence"] < ans["review_threshold"]
    iid = ans["interaction_id"]
    req = client.post(f"{P}/copilot/interactions/{iid}/request-review", headers=o, json={"note": "mohon cek"})
    assert req.status_code == 200
    rid = req.json()["data"]["id"]
    assert client.post(f"{P}/copilot/interactions/{iid}/request-review", headers=o, json={}).status_code == 409
    assert iid in [x["id"] for x in client.get(f"{P}/copilot/interactions?review=pending", headers=a).json()["data"]]
    # peminta tidak boleh meninjau sendiri; CORRECTED wajib teks; analis memutus
    assert client.post(f"{P}/copilot/reviews/{rid}/verdict", headers=o, json={"verdict": "CONFIRMED"}).status_code == 403
    assert client.post(f"{P}/copilot/reviews/{rid}/verdict", headers=a, json={"verdict": "CORRECTED"}).status_code == 422
    done = client.post(f"{P}/copilot/reviews/{rid}/verdict", headers=a,
                       json={"verdict": "CORRECTED", "corrected_text": "Korpus hanya mengatur pengamanan dompet pelanggan."})
    assert done.status_code == 200 and done.json()["data"]["reviewer"] == "analyst"
    log = next(x for x in client.get(f"{P}/copilot/interactions", headers=auditor).json()["data"] if x["id"] == iid)
    assert log["user"] == "officer" and log["review"]["verdict"] == "CORRECTED" and log["retrieved"]
    assert client.get(f"{P}/copilot/interactions", headers=login(client, "owner")).status_code == 403
    # log interaksi tidak dapat disunting
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE platform.ai_call_log SET prompt_rendered = 'x' WHERE id = :i"), {"i": iid})
    db.rollback()
