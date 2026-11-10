# [8] FILE BARU — tes otomatis fitur OCR; dijalankan bersama tes lain lewat `pytest -q`
"""FR-RKM-004: PDF hasil pindaian dibaca lewat OCR, pasalnya ditandai, dan publikasi diblokir sampai analis
mengonfirmasi atau mengoreksi teksnya."""
import shutil
import uuid
from datetime import date

import pymupdf
import pytest

from tests.conftest import ORIGIN, P, login


def _doc(client, h):
    r = client.post(f"{P}/corpus/documents", headers=h, json={
        "canonical_number": f"POJK OCR/{uuid.uuid4().hex[:6]}", "title_id": "Uji OCR"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _scanned_pdf(lines: list[str]) -> bytes:
    """Buat PDF 'hasil pindaian': teks digambar ke halaman, lalu halamannya dijadikan gambar (tanpa lapisan teks)."""
    src = pymupdf.open()
    page = src.new_page()
    for i, ln in enumerate(lines):
        page.insert_text((72, 100 + 30 * i), ln, fontsize=16)
    png = page.get_pixmap(dpi=150).tobytes("png")
    scan = pymupdf.open()
    scan.new_page(width=page.rect.width, height=page.rect.height).insert_image(page.rect, stream=png)
    return scan.tobytes()


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract tidak terpasang")
def test_scanned_pdf_goes_through_ocr_and_requires_confirmation(client):
    a, auditor = login(client, "analyst"), login(client, "auditor")
    doc = _doc(client, a)
    pdf = _scanned_pdf(["Pasal 1", "Bank wajib menyampaikan laporan bulanan.", "Pasal 2",
                        f"Laporan disampaikan paling lambat tanggal {uuid.uuid4().int % 28 + 1}.", f"Kode {uuid.uuid4().hex[:8]}"])
    r = client.post(f"{P}/corpus/documents/{doc}/versions", headers=a, files={"file": ("pindaian.pdf", pdf)},
                    data={"effective_date": str(date.today()), "origin_url": ORIGIN})
    assert r.status_code == 200, r.text
    up = r.json()["data"]
    assert up["extraction_method"] == "OCR" and up["ocr_pages"] == [1]
    vid = up["version_id"]
    provs = client.get(f"{P}/corpus/versions/{vid}/provisions", headers=a).json()["data"]
    assert len(provs) == 2 and all(p["low_confidence_text"] for p in provs)

    # publikasi diblokir selama masih ada teks OCR yang belum diperiksa
    blocked = client.post(f"{P}/corpus/versions/{vid}/publish", headers=a)
    assert blocked.status_code == 409 and blocked.json()["error_code"] == "LOW_CONFIDENCE_UNCONFIRMED"

    # pasal 1 dikonfirmasi apa adanya; pasal 2 dikoreksi manual (koreksi juga menghapus tanda OCR)
    p1, p2 = provs
    assert client.post(f"{P}/corpus/provision-versions/{p1['provision_version_id']}/confirm-text", headers=a).status_code == 200
    assert client.post(f"{P}/corpus/provision-versions/{p1['provision_version_id']}/confirm-text", headers=a).status_code == 409
    assert client.patch(f"{P}/corpus/provision-versions/{p2['provision_version_id']}", headers=a,
                        json={"text": "   "}).status_code == 422
    assert client.patch(f"{P}/corpus/provision-versions/{p2['provision_version_id']}", headers=a,
                        json={"text": "Laporan disampaikan paling lambat tanggal 10."}).status_code == 200
    # peran lain tidak boleh mengonfirmasi
    assert client.post(f"{P}/corpus/provision-versions/{p1['provision_version_id']}/confirm-text",
                       headers=login(client, "officer")).status_code == 403

    assert client.post(f"{P}/corpus/versions/{vid}/publish", headers=a).status_code == 200
    after = client.get(f"{P}/corpus/versions/{vid}/provisions", headers=a).json()["data"]
    assert not any(p["low_confidence_text"] for p in after) and all(p["corrected_by_human"] for p in after)
    # setelah terbit teks beku: konfirmasi/koreksi ditolak
    assert client.post(f"{P}/corpus/provision-versions/{p1['provision_version_id']}/confirm-text", headers=a).status_code == 409

    acts = {e["action"] for e in client.get(f"{P}/audit?object_id={vid}", headers=auditor).json()["data"]}
    assert {"VERSION_INGESTED", "OCR_INVOKED", "VERSION_PUBLISHED"} <= acts
    pv_acts = {e["action"] for e in client.get(f"{P}/audit?object_id={p1['provision_version_id']}", headers=auditor).json()["data"]}
    assert "TEXT_CONFIRMED_BY_ANALYST" in pv_acts


def test_text_layer_pdf_is_not_flagged(client):
    """PDF biasa (punya lapisan teks) tidak lewat OCR dan tidak perlu konfirmasi."""
    a = login(client, "analyst")
    doc = _doc(client, a)
    src = pymupdf.open()
    page = src.new_page()
    page.insert_text((72, 100), "Pasal 1", fontsize=12)
    page.insert_text((72, 120), f"Bank wajib memelihara rasio likuiditas yang memadai setiap saat {uuid.uuid4().hex}.", fontsize=10)
    r = client.post(f"{P}/corpus/documents/{doc}/versions", headers=a, files={"file": ("teks.pdf", src.tobytes())},
                    data={"effective_date": str(date.today()), "origin_url": ORIGIN})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["extraction_method"] == "TEXT_LAYER" and r.json()["data"]["ocr_pages"] == []
    vid = r.json()["data"]["version_id"]
    provs = client.get(f"{P}/corpus/versions/{vid}/provisions", headers=a).json()["data"]
    assert provs and not any(p["low_confidence_text"] for p in provs)
    assert client.post(f"{P}/corpus/versions/{vid}/publish", headers=a).status_code == 200