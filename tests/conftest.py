# ======================================================================================================
# DATABASE KHUSUS TES
# Tes otomatis membuat dokumen, kewajiban, laporan, dst. Agar data itu TIDAK ikut tampil di website demo,
# semua tes selalu dijalankan di database terpisah (bawaan: "rcip_test"), bukan di database website (rcip_db).
# Database tes dibuat, dimigrasi (alembic upgrade head), dan diisi akun demo (seed.run) secara otomatis.
# Nama lain bisa dipilih lewat variabel lingkungan TEST_DATABASE_NAME.
# Bagian ini HARUS berada sebelum `from app.main import app`, karena koneksi database dibuat saat app di-import.
# ======================================================================================================
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.shared.config import settings

_main_url = make_url(settings.DATABASE_URL)                          # database website, mis. .../rcip_db
_test_db = os.environ.get("TEST_DATABASE_NAME", "rcip_test")        # nama database tes
if _main_url.database == _test_db:
    raise RuntimeError("Database tes tidak boleh sama dengan database website")
_test_url = _main_url.set(database=_test_db)


def _prepare_test_database() -> None:
    """Buat database tes bila belum ada, lalu jalankan migrasi terbaru dan seed akun demo."""
    # 1) sambung ke database bawaan "postgres" untuk mengecek / membuat database tes
    admin = create_engine(_main_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": _test_db})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{_test_db}"'))
    admin.dispose()

    # 2) arahkan seluruh aplikasi (dan alembic) ke database tes
    settings.DATABASE_URL = _test_url.render_as_string(hide_password=False)
    os.environ["DATABASE_URL"] = settings.DATABASE_URL
    # data tes tidak boleh ikut terekspor ke folder data/korpus milik tim
    settings.CORPUS_SYNC_AUTO = False

    # 3) migrasi ke versi terbaru; aman dijalankan berulang (migrasi yang sudah ada dilewati)
    from alembic import command
    from alembic.config import Config
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    command.upgrade(cfg, "head")

    # 4) akun demo (analyst, officer, ...) yang dipakai tes untuk login; seed.run aman dijalankan berulang
    #    (fungsi seed() dipanggil langsung, bukan main(), agar argumen pytest seperti -q tidak ikut terbaca)
    from app.shared.database import SessionLocal as _Session
    from seed.run import seed
    db = _Session()
    try:
        seed(db)
        db.commit()
    finally:
        db.close()


_prepare_test_database()

# ---- setelah titik ini semua koneksi aplikasi sudah memakai database tes ----
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.shared.database import SessionLocal  # noqa: E402

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
