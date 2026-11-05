"""Demo 16 langkah versi otomatis (mengubah data DB; jalankan pada DB demo)."""
import uuid
from datetime import date, timedelta

from tests.conftest import approve_applicability, login

P = "/api/v1"


def _uid(client, h, name):
    return next(u["id"] for u in client.get(f"{P}/users", headers=h).json()["data"] if u["username"] == name)


def test_end_to_end(client):
    analyst, officer = login(client, "analyst"), login(client, "officer")
    manager, owner, auditor = login(client, "manager"), login(client, "owner"), login(client, "auditor")

    # 1-3 ingest .txt -> segmentasi -> publish (nomor unik per run)
    number = f"POJK TEST/{uuid.uuid4().hex[:6]}/Bank Umum"
    doc = client.post(f"{P}/corpus/documents", headers=analyst, json={
        "canonical_number": number, "title_id": "Manajemen Risiko Bank Umum"}).json()["data"]["id"]
    body = "Pasal 1\nBank wajib menyampaikan laporan bulanan kepada regulator paling lambat 10 (sepuluh) hari kerja."
    up = client.post(f"{P}/corpus/documents/{doc}/versions", headers=analyst,
                     files={"file": ("t.txt", body.encode())}, data={"effective_date": str(date.today())})
    assert up.status_code == 200, up.text
    vid = up.json()["data"]["version_id"]
    assert client.post(f"{P}/corpus/versions/{vid}/publish", headers=analyst).status_code == 200
    pv = client.get(f"{P}/corpus/versions/{vid}/provisions", headers=analyst).json()["data"][0]["provision_version_id"]

    # 5 keberlakuan: tanpa keputusan DISETUJUI ekstraksi ditolak (W7 → W8)
    blocked_ex = client.post(f"{P}/compliance/obligations/extract", headers=officer, json={"provision_version_id": pv})
    assert blocked_ex.status_code == 409 and blocked_ex.json()["error_code"] == "APPLICABILITY_NOT_APPROVED"
    approve_applicability(client, vid, [pv])
    # 6 ekstraksi AI (draf)
    ex = client.post(f"{P}/compliance/obligations/extract", headers=officer, json={"provision_version_id": pv})
    assert ex.status_code == 200, ex.text
    ob = ex.json()["data"]["obligation_ids"][0]

    # AI_DRAFT tidak boleh dipetakan ke kontrol
    owner_id = _uid(client, officer, "owner")
    ctl = client.post(f"{P}/compliance/controls", headers=officer,
                      json={"title": "Kontrol pelaporan", "owner_id": owner_id}).json()["data"]["id"]
    blocked = client.post(f"{P}/compliance/obligations/{ob}/controls/{ctl}", headers=officer)
    assert blocked.status_code == 409 and blocked.json()["error_code"] == "AI_DRAFT_BLOCKED"

    # 7-8 validasi (officer = maker) & persetujuan; officer tidak boleh menyetujui sendiri
    # E8.3: draf berkeyakinan rendah (aturan = 0.6 < ai.confidence_floor 0.7) wajib dikonfirmasi telah ditinjau
    low = client.post(f"{P}/compliance/obligations/{ob}/validate", headers=officer, json={"owner_id": owner_id})
    assert low.status_code == 422 and low.json()["error_code"] == "LOW_CONFIDENCE_REVIEW_REQUIRED"
    assert client.post(f"{P}/compliance/obligations/{ob}/validate", headers=officer,
                       json={"owner_id": owner_id, "low_confidence_reviewed": True}).status_code == 200
    assert client.post(f"{P}/compliance/obligations/{ob}/decision", headers=officer, json={"outcome": "APPROVED"}).status_code == 403
    ok = client.post(f"{P}/compliance/obligations/{ob}/decision", headers=manager, json={"outcome": "APPROVED"})
    assert ok.json()["data"]["state"] == "ACTIVE"

    # 12 gap -> finding otomatis; 13 remediasi
    scan = client.post(f"{P}/compliance/gaps/scan", headers=officer).json()["data"]["findings_created"]
    assert scan
    # pada DB baru, pemindaian juga memunculkan kesenjangan data seed milik pemilik lain → pilih temuan kewajiban ini
    mine = next(f for f in scan if client.get(f"{P}/compliance/findings/{f}", headers=officer).json()["data"]["obligation"]["id"] == ob)
    # matriks RBAC "Tindakan remediasi": Pemilik Kontrol hanya R/U/X (own) — membuat tindakan (C) milik Pejabat Kepatuhan
    assert client.post(f"{P}/compliance/findings/{mine}/remediation", headers=owner,
                       json={"description": "Buat kontrol", "due_date": str(date.today() + timedelta(days=30))}).status_code == 403
    assert client.post(f"{P}/compliance/findings/{mine}/remediation", headers=officer,
                       json={"description": "Buat kontrol", "due_date": str(date.today() + timedelta(days=30))}).status_code == 200

    # 9-11 kontrol, bukti, asesmen
    assert client.post(f"{P}/compliance/obligations/{ob}/controls/{ctl}", headers=officer).status_code == 200
    assert client.post(f"{P}/compliance/controls/{ctl}/assessments", headers=officer,
                       json={"result": "EFFECTIVE"}).status_code == 409  # belum ada bukti
    ev = client.post(f"{P}/compliance/controls/{ctl}/evidence", headers=owner,
                     files={"file": ("bukti.pdf", b"%PDF-1.4 demo")})
    assert ev.status_code == 200
    # bukti harus DITERIMA dulu sebelum asesmen (W11 -> W10)
    assert client.post(f"{P}/compliance/controls/{ctl}/assessments", headers=officer,
                       json={"result": "EFFECTIVE"}).status_code == 409
    assert client.post(f"{P}/compliance/evidence/{ev.json()['data']['id']}/review", headers=officer,
                       json={"outcome": "ACCEPTED", "rationale": "Sesuai periode"}).status_code == 200
    asm = client.post(f"{P}/compliance/controls/{ctl}/assessments", headers=officer, json={
        "design_result": "EFFECTIVE", "operating_result": "EFFECTIVE",
        "design_rationale": "Desain memadai", "operating_rationale": "Berjalan sesuai prosedur"})
    assert asm.status_code == 200, asm.text
    aid = asm.json()["data"]["id"]
    assert client.post(f"{P}/compliance/assessments/{aid}/submit", headers=officer).status_code == 200
    assert client.post(f"{P}/compliance/assessments/{aid}/signoff", headers=manager,
                       json={"outcome": "APPROVED"}).json()["data"]["state"] == "SIGNED_OFF"

    # 15-16 laporan (maker-checker: officer membangkitkan, manager menerbitkan) + drill-through
    rep = client.post(f"{P}/compliance/reports", headers=officer, json={"title": "Laporan uji"})
    assert rep.status_code == 200 and rep.json()["data"]["traceability_verified"]
    rid = rep.json()["data"]["id"]
    assert client.post(f"{P}/compliance/reports/{rid}/submit", headers=officer).status_code == 200
    assert client.post(f"{P}/compliance/reports/{rid}/decision", headers=manager,
                       json={"outcome": "APPROVED"}).json()["data"]["state"] == "ISSUED"
    tr = client.get(f"{P}/compliance/trace/obligations/{ob}", headers=auditor).json()["data"]
    assert tr["citation"]["document"]["canonical_number"] == number
    assert tr["approvals"][0]["outcome"] == "APPROVED"


def test_contract_citation_resolve(client):
    h = login(client, "analyst")
    r = client.post(f"{P}/citations/resolve", headers=h, json={"provision_version_ids": ["bukan-uuid", str(uuid.uuid4())]})
    assert r.status_code == 200 and len(r.json()["data"]["unresolved"]) == 2


def test_rbac_server_side(client):
    h = login(client, "executive")
    assert client.post(f"{P}/corpus/documents", headers=h, json={"canonical_number": "X", "title_id": "Y"}).status_code == 403
    assert client.get(f"{P}/audit", headers=h).status_code == 403