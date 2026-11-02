"""Tahap 2: W10–W12, W14 — temuan → remediasi → penutupan (titik kendali #5), sign-off asesmen (#4),
penerbitan laporan (#6), imutabilitas bukti/laporan, dan pembatasan lingkup jejak audit."""
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import P, login, make_active_obligation, uid

D = lambda n: str(date.today() + timedelta(days=n))  # noqa: E731


@pytest.fixture(scope="module")
def H(client):
    return {n: login(client, n) for n in ("officer", "manager", "owner", "auditor", "executive", "analyst")}


def _finding_for(client, H, ob, severity="HIGH"):
    r = client.post(f"{P}/compliance/findings", headers=H["officer"], json={
        "obligation_id": ob, "title": "Laporan bulanan terlambat", "description": "Uji temuan manual",
        "severity": severity, "owner_id": uid(client, H["officer"], "owner")})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _get(client, H, fid, who="officer"):
    return client.get(f"{P}/compliance/findings/{fid}", headers=H[who]).json()["data"]


def test_remediation_to_closure_full_path(client, H):
    ob = make_active_obligation(client)
    fid = _finding_for(client, H, ob)
    assert _get(client, H, fid)["state"] == "OPEN"

    # jendela severity HIGH = 60 hari
    bad = client.post(f"{P}/compliance/findings/{fid}/remediation", headers=H["officer"],
                      json={"description": "x", "due_date": D(200)})
    assert bad.status_code == 422 and bad.json()["error_code"] == "DUE_DATE_EXCEEDS_WINDOW"

    act = client.post(f"{P}/compliance/findings/{fid}/remediation", headers=H["officer"], json={
        "description": "Otomasi pengingat laporan", "due_date": D(20), "owner_id": uid(client, H["officer"], "owner")})
    assert act.status_code == 200 and act.json()["data"]["finding_state"] == "ACTION_PLANNED"
    aid = act.json()["data"]["id"]

    # register menampilkan remediasi
    row = next(f for f in client.get(f"{P}/compliance/findings", headers=H["owner"]).json()["data"] if f["id"] == fid)
    assert row["actions"][0]["description"] == "Otomasi pengingat laporan"

    assert client.post(f"{P}/compliance/actions/{aid}/start", headers=H["owner"]).json()["data"]["finding_state"] == "IN_REMEDIATION"
    ext = client.post(f"{P}/compliance/actions/{aid}/extend", headers=H["owner"], json={"new_due_date": D(25), "reason": "Menunggu vendor"})
    assert ext.json()["data"]["original_due_date"] == D(20)

    # selesai tanpa bukti ditolak
    r = client.post(f"{P}/compliance/actions/{aid}/complete", headers=H["owner"], json={})
    assert r.status_code == 409 and r.json()["error_code"] == "CLOSURE_EVIDENCE_REQUIRED"
    ev = client.post(f"{P}/compliance/actions/{aid}/evidence", headers=H["owner"],
                     files={"file": ("bukti.txt", b"log pengingat terkirim")}, data={"description": "Log"}).json()["data"]
    assert client.post(f"{P}/compliance/actions/{aid}/complete", headers=H["owner"], json={}).status_code == 409  # belum diterima
    assert client.post(f"{P}/compliance/evidence/{ev['id']}/review", headers=H["officer"],
                       json={"outcome": "ACCEPTED", "rationale": " "}).status_code == 422
    assert client.post(f"{P}/compliance/evidence/{ev['id']}/review", headers=H["owner"],
                       json={"outcome": "ACCEPTED", "rationale": "ok"}).status_code == 403
    assert client.post(f"{P}/compliance/evidence/{ev['id']}/review", headers=H["officer"],
                       json={"outcome": "ACCEPTED", "rationale": "Log lengkap"}).status_code == 200
    again = client.post(f"{P}/compliance/evidence/{ev['id']}/review", headers=H["officer"],
                        json={"outcome": "REJECTED", "rationale": "ubah"})
    assert again.status_code == 409 and again.json()["error_code"] == "EVIDENCE_IMMUTABLE"
    dl = client.get(f"{P}/compliance/evidence/{ev['id']}/download", headers=H["auditor"])
    assert dl.status_code == 200 and dl.content == b"log pengingat terkirim"

    assert client.post(f"{P}/compliance/actions/{aid}/complete", headers=H["owner"], json={"note": "Selesai"}).status_code == 200
    assert client.post(f"{P}/compliance/findings/{fid}/submit-closure", headers=H["owner"]).json()["data"]["state"] == "PENDING_CLOSURE_VALIDATION"

    # titik kendali #5
    assert client.post(f"{P}/compliance/findings/{fid}/close", headers=H["officer"],
                       json={"outcome": "APPROVED", "rationale": "x"}).status_code == 403
    assert client.post(f"{P}/compliance/findings/{fid}/close", headers=H["manager"],
                       json={"outcome": "APPROVED", "rationale": ""}).status_code == 422
    assert client.post(f"{P}/compliance/findings/{fid}/close", headers=H["manager"],
                       json={"outcome": "REJECTED", "rationale": "Bukti kurang"}).json()["error_code"] == "NEW_DUE_DATE_REQUIRED"
    ok = client.post(f"{P}/compliance/findings/{fid}/close", headers=H["manager"],
                     json={"outcome": "APPROVED", "rationale": "Remediasi terbukti efektif"})
    assert ok.json()["data"]["state"] == "CLOSED"

    re = client.post(f"{P}/compliance/findings/{fid}/reopen", headers=H["manager"], json={"reason": "Insiden berulang"})
    assert re.json()["data"]["state"] == "IN_REMEDIATION"
    detail = _get(client, H, fid, "auditor")
    actions = [t["action"] for t in detail["timeline"]]
    for a in ("FINDING_RAISED", "ACTION_CREATED", "EVIDENCE_ACCEPTED", "CLOSURE_SUBMITTED", "FINDING_CLOSED", "FINDING_REOPENED"):
        assert a in actions, a
    assert detail["approvals"][-1]["outcome"] == "APPROVED" and detail["approvals"][-1]["control_point"] == 5


def test_closure_sod_action_owner_cannot_validate(client, H):
    ob = make_active_obligation(client)
    fid = _finding_for(client, H, ob)
    mgr = uid(client, H["officer"], "manager")
    aid = client.post(f"{P}/compliance/findings/{fid}/remediation", headers=H["officer"],
                      json={"description": "Tindakan oleh manajer", "due_date": D(10), "owner_id": mgr}).json()["data"]["id"]
    ev = client.post(f"{P}/compliance/actions/{aid}/evidence", headers=H["officer"], files={"file": ("e.txt", b"e")}).json()["data"]
    client.post(f"{P}/compliance/evidence/{ev['id']}/review", headers=H["officer"], json={"outcome": "ACCEPTED", "rationale": "ok"})
    assert client.post(f"{P}/compliance/actions/{aid}/complete", headers=H["officer"], json={}).status_code == 200
    assert client.post(f"{P}/compliance/findings/{fid}/submit-closure", headers=H["officer"]).status_code == 200
    r = client.post(f"{P}/compliance/findings/{fid}/close", headers=H["manager"], json={"outcome": "APPROVED", "rationale": "x"})
    assert r.status_code == 403 and r.json()["error_code"] == "SOD_VIOLATION"


def test_severity_window_and_risk_acceptance(client, H):
    ob = make_active_obligation(client)
    r = client.post(f"{P}/compliance/findings", headers=H["officer"], json={
        "obligation_id": ob, "title": "Kritis", "description": "x", "severity": "CRITICAL",
        "owner_id": uid(client, H["officer"], "owner"), "target_closure_date": D(45)})
    assert r.status_code == 422 and "30 hari" in r.json()["message"]
    fid = _finding_for(client, H, ob, "LOW")
    assert client.post(f"{P}/compliance/findings/{fid}/accept-risk", headers=H["manager"],
                       json={"rationale": "Toleransi risiko", "review_date": str(date.today())}).status_code == 422
    ok = client.post(f"{P}/compliance/findings/{fid}/accept-risk", headers=H["manager"],
                     json={"rationale": "Dalam selera risiko", "review_date": D(90)})
    assert ok.json()["data"]["state"] == "RISK_ACCEPTED"
    dash = client.get(f"{P}/compliance/dashboard", headers=H["executive"]).json()["data"]
    assert dash["risk_accepted"] >= 1 and fid not in dash["drill"]["open_findings"]  # bukan "terselesaikan", bukan "terbuka"


def test_assessment_signoff_and_auto_finding(client, H):
    ob = make_active_obligation(client)
    owner = uid(client, H["officer"], "owner")
    ctl = client.post(f"{P}/compliance/controls", headers=H["officer"], json={"title": "Rekonsiliasi harian", "owner_id": owner}).json()["data"]["id"]
    client.post(f"{P}/compliance/obligations/{ob}/controls/{ctl}", headers=H["officer"])
    ev = client.post(f"{P}/compliance/controls/{ctl}/evidence", headers=H["owner"], files={"file": ("r.csv", b"a,b")}).json()["data"]
    client.post(f"{P}/compliance/evidence/{ev['id']}/review", headers=H["officer"], json={"outcome": "ACCEPTED", "rationale": "ok"})
    bad = client.post(f"{P}/compliance/controls/{ctl}/assessments", headers=H["officer"], json={
        "design_result": "INEFFECTIVE", "operating_result": "EFFECTIVE", "design_rationale": "a", "operating_rationale": "b"})
    assert bad.status_code == 422 and bad.json()["error_code"] == "INCONSISTENT_CONCLUSION"
    a = client.post(f"{P}/compliance/controls/{ctl}/assessments", headers=H["officer"], json={
        "design_result": "EFFECTIVE", "operating_result": "PARTIALLY_EFFECTIVE",
        "design_rationale": "Desain tepat", "operating_rationale": "2 dari 20 sampel tanpa tanda tangan"}).json()["data"]
    assert a["finding_id"], "asesmen PARTIALLY_EFFECTIVE harus memunculkan temuan otomatis"
    f = _get(client, H, a["finding_id"])
    assert f["source_type"] == "ASSESSMENT" and f["assessment_id"] == a["id"] and f["severity"] == "MEDIUM"
    assert client.post(f"{P}/compliance/assessments/{a['id']}/signoff", headers=H["manager"], json={"outcome": "APPROVED"}).status_code == 409
    client.post(f"{P}/compliance/assessments/{a['id']}/submit", headers=H["officer"])
    assert client.post(f"{P}/compliance/assessments/{a['id']}/signoff", headers=H["officer"], json={"outcome": "APPROVED"}).status_code == 403
    assert client.post(f"{P}/compliance/assessments/{a['id']}/signoff", headers=H["manager"], json={"outcome": "REJECTED"}).status_code == 422
    s = client.post(f"{P}/compliance/assessments/{a['id']}/signoff", headers=H["manager"], json={"outcome": "APPROVED"})
    assert s.json()["data"]["state"] == "SIGNED_OFF"
    tr = client.get(f"{P}/compliance/trace/obligations/{ob}", headers=H["auditor"]).json()["data"]
    assert tr["controls"][0]["latest_assessment"]["signed_off_by"] == "manager"
    assert tr["findings"][0]["severity"] == "MEDIUM"


def test_report_maker_checker_and_immutability(client, H, db):
    make_active_obligation(client)
    assert client.post(f"{P}/compliance/reports", headers=H["manager"], json={"title": "x"}).status_code == 403
    r = client.post(f"{P}/compliance/reports", headers=H["officer"], json={"title": "Postur Q4"}).json()["data"]
    assert r["state"] == "DRAFT" and "dokumen publik" in r["disclaimer"] and "{n}" not in r["disclaimer"]
    for k in ("scope", "corpus_basis", "obligation_inventory", "control_coverage", "assessment_results",
              "findings", "regulatory_changes", "pending", "referenced_object_versions"):
        assert k in r, k
    assert r["obligation_inventory"][0]["citation"]["verbatim"]
    assert client.post(f"{P}/compliance/reports/{r['id']}/decision", headers=H["manager"], json={"outcome": "APPROVED"}).status_code == 409
    client.post(f"{P}/compliance/reports/{r['id']}/submit", headers=H["officer"])
    assert client.post(f"{P}/compliance/reports/{r['id']}/decision", headers=H["officer"], json={"outcome": "APPROVED"}).status_code == 403
    assert client.post(f"{P}/compliance/reports/{r['id']}/decision", headers=H["manager"],
                       json={"outcome": "APPROVED"}).json()["data"]["state"] == "ISSUED"
    with pytest.raises(DBAPIError) as e:
        db.execute(text("UPDATE compliance.compliance_report SET title='ubah' WHERE id=:i"), {"i": r["id"]})
    assert "REPORT_IMMUTABLE" in str(e.value)
    db.rollback()
    r2 = client.post(f"{P}/compliance/reports", headers=H["officer"], json={"title": "Postur Q4 rev"}).json()["data"]
    client.post(f"{P}/compliance/reports/{r2['id']}/submit", headers=H["officer"])
    client.post(f"{P}/compliance/reports/{r2['id']}/decision", headers=H["manager"], json={"outcome": "APPROVED"})
    old = client.get(f"{P}/compliance/reports/{r['id']}", headers=H["auditor"]).json()["data"]
    assert old["state"] == "SUPERSEDED" and old["superseded_by"] == r2["id"]
    w = client.post(f"{P}/compliance/reports/{r2['id']}/withdraw", headers=H["manager"], json={"reason": "Salah periode"})
    assert w.json()["data"]["state"] == "WITHDRAWN"


def test_accepted_evidence_is_immutable_in_db(db):
    row = db.execute(text("SELECT id FROM compliance.evidence WHERE state='ACCEPTED' LIMIT 1")).first()
    if not row:
        pytest.skip("belum ada bukti ACCEPTED")
    with pytest.raises(DBAPIError) as e:
        db.execute(text("UPDATE compliance.evidence SET sha256 = repeat('0',64) WHERE id=:i"), {"i": row[0]})
    assert "EVIDENCE_IMMUTABLE" in str(e.value)


def test_audit_scope_and_export(client, H):
    allr = client.get(f"{P}/audit?limit=50", headers=H["auditor"]).json()["data"]
    assert {r["actor"] for r in allr} - {"officer"}, "auditor melihat event semua aktor"
    own = client.get(f"{P}/audit?limit=50", headers=H["officer"]).json()["data"]
    assert own and {r["actor"] for r in own} == {"officer"}
    assert client.get(f"{P}/audit", headers=H["executive"]).status_code == 403
    csv = client.get(f"{P}/audit/export?limit=5", headers=H["auditor"])
    assert csv.status_code == 200 and csv.text.startswith("id,occurred_at,actor")


def test_owner_scope_hides_foreign_findings(client, H, db):
    from app.platform.auth import hash_password
    db.execute(text("""INSERT INTO platform.app_user (username, email, hashed_password, role)
                       VALUES ('owner2', 'owner2@bank-sinar.example', :h, 'BUSINESS_CONTROL_OWNER')
                       ON CONFLICT (username) DO NOTHING"""), {"h": hash_password("demo1234")})
    db.commit()
    h2 = login(client, "owner2")
    ob = make_active_obligation(client)
    fid = _finding_for(client, H, ob)  # milik 'owner'
    assert fid not in [f["id"] for f in client.get(f"{P}/compliance/findings", headers=h2).json()["data"]]
    assert client.get(f"{P}/compliance/findings/{fid}", headers=h2).status_code == 403
