from datetime import date, timedelta

import pytest

from tests.conftest import P, login, make_active_obligation, uid

D = lambda n: str(date.today() + timedelta(days=n))  # noqa: E731


@pytest.fixture(scope="module")
def H(client):
    return {n: login(client, n) for n in ("officer", "manager", "owner", "executive", "auditor")}


def test_executive_posture_shape(client, H):
    r = client.get(f"{P}/compliance/executive/posture", headers=H["executive"])
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert set(d["kpis"]) >= {"active_obligations", "regulations_in_force", "effective_percent", "open_findings",
                              "overdue_findings", "reports_issued", "last_report"}
    assert 0 <= d["kpis"]["effective_percent"] <= 100
    for a in d["by_area"]:
        assert a["effective"] <= a["obligations"]


@pytest.mark.parametrize("who", ["officer", "manager", "owner", "auditor"])
def test_executive_posture_is_executive_only(client, H, who):
    assert client.get(f"{P}/compliance/executive/posture", headers=H[who]).status_code == 403


def _finding_owned_by_owner(client, H, severity="HIGH"):
    ob = make_active_obligation(client)
    r = client.post(f"{P}/compliance/findings", headers=H["officer"], json={
        "obligation_id": ob, "title": "Kontrol belum punya bukti periode Q4", "description": "Uji ruang kerja pemilik",
        "severity": severity, "owner_id": uid(client, H["officer"], "owner")})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_owner_workspace_shape(client, H):
    fid = _finding_owned_by_owner(client, H)
    r = client.get(f"{P}/compliance/owner/workspace", headers=H["owner"])
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert set(d) == {"controls", "findings"}
    assert any(f["id"] == fid and f["needs_plan"] for f in d["findings"])


@pytest.mark.parametrize("who", ["officer", "manager", "executive", "auditor"])
def test_owner_workspace_is_owner_only(client, H, who):
    assert client.get(f"{P}/compliance/owner/workspace", headers=H[who]).status_code == 403


def test_owner_saves_plan_within_window(client, H):
    fid = _finding_owned_by_owner(client, H, severity="HIGH")  # jendela HIGH = 60 hari
    late = client.post(f"{P}/compliance/owner/findings/{fid}/plan", headers=H["owner"],
                       json={"description": "Pasang pengingat otomatis", "due_date": D(200)})
    assert late.status_code == 422 and late.json()["error_code"] == "DUE_DATE_EXCEEDS_WINDOW"
    ok = client.post(f"{P}/compliance/owner/findings/{fid}/plan", headers=H["owner"],
                     json={"description": "Pasang pengingat otomatis", "due_date": D(20)})
    assert ok.status_code == 200 and ok.json()["data"]["finding_state"] == "ACTION_PLANNED"