import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.shared.database import SessionLocal


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        s.execute(text("SELECT 1 FROM corpus.document LIMIT 1"))
    except Exception:
        s.close()
        pytest.skip("Database belum siap (jalankan make migrate && make seed)")
    yield s
    s.rollback()
    s.close()


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def login(client, username):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": "demo1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['access_token']}"}


P = "/api/v1"


def uid(client, h, name):
    return next(u["id"] for u in client.get(f"{P}/users", headers=h).json()["data"] if u["username"] == name)


def make_active_obligation(client, text_body=None):
    """Membuat dokumen baru → publish → ekstraksi → validasi (officer) → persetujuan (manager). Mengembalikan id kewajiban."""
    import uuid as _uuid
    from datetime import date as _date

    analyst, officer, manager = login(client, "analyst"), login(client, "officer"), login(client, "manager")
    number = f"POJK TEST/{_uuid.uuid4().hex[:6]}/Bank Umum"
    doc = client.post(f"{P}/corpus/documents", headers=analyst, json={
        "canonical_number": number, "title_id": "Manajemen Risiko Bank Umum"}).json()["data"]["id"]
    body = text_body or "Pasal 1\nBank wajib menyampaikan laporan bulanan kepada regulator paling lambat 10 (sepuluh) hari kerja."
    vid = client.post(f"{P}/corpus/documents/{doc}/versions", headers=analyst,
                      files={"file": ("t.txt", body.encode())}, data={"effective_date": str(_date.today())}).json()["data"]["version_id"]
    client.post(f"{P}/corpus/versions/{vid}/publish", headers=analyst)
    pv = client.get(f"{P}/corpus/versions/{vid}/provisions", headers=analyst).json()["data"][0]["provision_version_id"]
    approve_applicability(client, vid, [pv])
    ob = client.post(f"{P}/compliance/obligations/extract", headers=officer,
                     json={"provision_version_id": pv}).json()["data"]["obligation_ids"][0]
    client.post(f"{P}/compliance/obligations/{ob}/validate", headers=officer, json={"owner_id": uid(client, officer, "owner"), "low_confidence_reviewed": True})
    r = client.post(f"{P}/compliance/obligations/{ob}/decision", headers=manager, json={"outcome": "APPROVED"})
    assert r.json()["data"]["state"] == "ACTIVE", r.text
    return ob


def approve_applicability(client, version_id, cited, value="APPLICABLE"):
    """W7: officer menyusun & mengajukan keputusan keberlakuan, manager menyetujui (titik kendali #2)."""
    officer, manager = login(client, "officer"), login(client, "manager")
    d = client.post(f"{P}/compliance/applicability", headers=officer, json={
        "version_id": version_id, "decision_value": value, "reason": "Entitas termasuk subjek regulasi",
        "cited_provision_version_ids": cited, "scope_provision_version_ids": cited if value == "PARTIALLY_APPLICABLE" else []})
    assert d.status_code == 200, d.text
    did = d.json()["data"]["id"]
    assert client.post(f"{P}/compliance/applicability/{did}/submit", headers=officer).status_code == 200
    r = client.post(f"{P}/compliance/applicability/{did}/decision", headers=manager, json={"outcome": "APPROVED"})
    assert r.json()["data"]["state"] == "APPROVED", r.text
    return did
