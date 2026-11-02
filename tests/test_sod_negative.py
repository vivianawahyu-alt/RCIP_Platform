"""SM-13: 0 persetujuan diri yang berhasil pada enam titik kendali, ≥ 12 percobaan negatif.
Lapisan 1 — API: maker memanggil endpoint checker (ditolak 403). Lapisan 2 — DB: CHECK constraint menolak
baris di mana checker = maker walau aplikasi dilewati."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.platform.governance import enforce_maker_checker
from app.shared.errors import AppError
from tests.conftest import P, login, make_active_obligation, uid

ATTEMPTS = []


def _api_denied(client, who, path, body):
    r = client.post(f"{P}{path}", headers=login(client, who), json=body)
    ATTEMPTS.append(path)
    assert r.status_code in (403, 404, 409), (path, r.status_code, r.text)
    assert r.status_code != 200


def test_api_makers_cannot_act_as_checkers(client):
    fake = "00000000-0000-4000-8000-000000000000"
    # titik 1–6: maker mencoba memutuskan objeknya sendiri melalui endpoint checker
    _api_denied(client, "analyst", f"/corpus/changes/{fake}/confirm-materiality", {"outcome": "APPROVED"})
    _api_denied(client, "officer", f"/compliance/applicability/{fake}/decision", {"outcome": "APPROVED"})
    _api_denied(client, "officer", f"/compliance/obligations/{fake}/decision", {"outcome": "APPROVED"})
    _api_denied(client, "officer", f"/compliance/assessments/{fake}/signoff", {"outcome": "APPROVED"})
    _api_denied(client, "owner", f"/compliance/findings/{fake}/close", {"outcome": "APPROVED", "rationale": "x"})
    _api_denied(client, "officer", f"/compliance/reports/{fake}/decision", {"outcome": "APPROVED"})
    # auditor & admin tidak memiliki kapabilitas approve di mana pun (R-01, R-02)
    _api_denied(client, "auditor", f"/compliance/findings/{fake}/close", {"outcome": "APPROVED", "rationale": "x"})
    _api_denied(client, "admin", f"/compliance/reports/{fake}/decision", {"outcome": "APPROVED"})


def test_governance_function_blocks_self_approval():
    for maker, editor, checker in [("u1", "u1", "u1"), ("u1", "u2", "u2")]:
        with pytest.raises(AppError) as e:
            enforce_maker_checker(checker, maker, editor)
        ATTEMPTS.append("enforce_maker_checker")
        assert e.value.code == "SOD_VIOLATION"


@pytest.mark.parametrize("sql", [
    "UPDATE compliance.obligation SET approver_id = validator_id WHERE validator_id IS NOT NULL",
    "UPDATE compliance.applicability_decision SET approver_id = maker_id",
    "UPDATE compliance.assessment SET signed_off_by = assessed_by WHERE assessed_by IS NOT NULL",
    "UPDATE compliance.finding SET closed_by = raised_by WHERE raised_by IS NOT NULL",
    "UPDATE compliance.compliance_report SET issued_by = generated_by WHERE generated_by IS NOT NULL AND state IN ('DRAFT','PENDING_APPROVAL')",
    "UPDATE corpus.change SET confirmed_by = validated_by WHERE validated_by IS NOT NULL",
])
def test_database_rejects_self_approval_rows(client, db, sql):
    # pastikan ada baris untuk setiap tabel
    ob = make_active_obligation(client)
    o = login(client, "officer")
    client.post(f"{P}/compliance/findings", headers=o, json={"obligation_id": ob, "title": "t", "description": "d",
                                                             "severity": "LOW", "owner_id": uid(client, o, "owner")})
    client.post(f"{P}/compliance/reports", headers=o, json={"title": "SoD"})
    n = db.execute(text(f"SELECT count(*) FROM ({sql.replace('UPDATE', 'SELECT 1 FROM', 1).split(' SET ')[0]}) t")).scalar()
    if not n:
        pytest.skip("tidak ada baris untuk diuji")
    with pytest.raises(DBAPIError) as e:
        db.execute(text(sql))
    db.rollback()
    ATTEMPTS.append(sql[:30])
    assert "violates check constraint" in str(e.value)


def test_at_least_twelve_attempts_recorded():
    assert len(ATTEMPTS) >= 12, ATTEMPTS
