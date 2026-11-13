"""Tahap akhir: titik kendali #1 (materialitas) & #2 (keberlakuan), W4/W6, konfigurasi runtime teraudit,
pemindaian berkas, pembatasan laju login, correlation ID, dan amplop error."""
import uuid
from datetime import date

from tests.conftest import ORIGIN, P, approve_applicability, login, make_active_obligation, uid


def _doc_with_two_versions(client, v1, v2, title="Pelaporan Insiden Bank Umum"):
    a = login(client, "analyst")
    number = f"POJK GOV/{uuid.uuid4().hex[:6]}"
    doc = client.post(f"{P}/corpus/documents", headers=a, json={"canonical_number": number, "title_id": title}).json()["data"]["id"]
    vids = []
    for body in (v1, v2):
        unique = f"Dokumen uji {uuid.uuid4().hex}\n{body}"  # pembuka unik → lolos cek duplikat berkas
        vid = client.post(f"{P}/corpus/documents/{doc}/versions", headers=a, files={"file": ("t.txt", unique.encode())},
                          data={"effective_date": str(date.today()), "origin_url": ORIGIN}).json()["data"]["version_id"]
        client.post(f"{P}/corpus/versions/{vid}/publish", headers=a)
        vids.append(vid)
    return doc, vids


def test_materiality_confirmation_propagates_and_reopen(client):
    a, o, m, legal = login(client, "analyst"), login(client, "officer"), login(client, "manager"), login(client, "legal")
    doc, (v1, v2) = _doc_with_two_versions(client,
        "Pasal 1\\nBank wajib melaporkan insiden paling lambat 24 (dua puluh empat) jam.".replace("\\n", "\n"),
        "Pasal 1\\nBank wajib melaporkan insiden paling lambat 12 (dua belas) jam.".replace("\\n", "\n"))
    pv1 = client.get(f"{P}/corpus/versions/{v1}/provisions", headers=a).json()["data"][0]["provision_version_id"]
    approve_applicability(client, v1, [pv1])
    ob = client.post(f"{P}/compliance/obligations/extract", headers=o, json={"provision_version_id": pv1}).json()["data"]["obligation_ids"][0]
    client.post(f"{P}/compliance/obligations/{ob}/validate", headers=o, json={"owner_id": uid(client, o, "owner"), "low_confidence_reviewed": True})
    client.post(f"{P}/compliance/obligations/{ob}/decision", headers=m, json={"outcome": "APPROVED"})
    ctl = client.post(f"{P}/compliance/controls", headers=o, json={"title": "Eskalasi", "owner_id": uid(client, o, "owner")}).json()["data"]["id"]
    client.post(f"{P}/compliance/obligations/{ob}/controls/{ctl}", headers=o)

    cs = client.post(f"{P}/corpus/changes", headers=a, json={"base_version_id": v1, "new_version_id": v2}).json()["data"]
    again = client.post(f"{P}/corpus/changes", headers=a, json={"base_version_id": v1, "new_version_id": v2}).json()["data"]
    assert again["change_set_id"] == cs["change_set_id"], "perhitungan diff idempoten"
    ch = cs["changes"][0]
    assert ch["review_state"] == "DETECTED"
    # deteksi saja tidak mengubah apa pun di hilir
    assert next(x for x in client.get(f"{P}/compliance/obligations", headers=o).json()["data"] if x["id"] == ob)["state"] == "ACTIVE"

    assert client.post(f"{P}/corpus/changes/{ch['id']}/escalate", headers=a, json={"question": "Apakah 12 jam berlaku surut?"}).json()["data"]["review_state"] == "ESCALATED"
    assert client.post(f"{P}/corpus/changes/{ch['id']}/legal-answer", headers=legal,
                       json={"answer": "Tidak berlaku surut", "citation_provision_version_ids": [pv1]}).json()["data"]["review_state"] == "IN_REVIEW"
    assert client.post(f"{P}/corpus/changes/{ch['id']}/validate", headers=a, json={"material": True, "semantic_type": "DEADLINE_CHANGED", "reason": ""}).status_code == 422
    assert client.post(f"{P}/corpus/changes/{ch['id']}/validate", headers=a, json={"material": True, "semantic_type": "DEADLINE_CHANGED", "reason": "Tenggat dipercepat"}).json()["data"]["review_state"] == "VALIDATED"
    assert client.post(f"{P}/corpus/changes/{ch['id']}/confirm-materiality", headers=a, json={"outcome": "APPROVED"}).status_code == 403
    r = client.post(f"{P}/corpus/changes/{ch['id']}/confirm-materiality", headers=m, json={"outcome": "APPROVED"}).json()["data"]
    assert r["review_state"] == "MATERIAL_CONFIRMED" and ob in r["impact"]["obligations"] and ctl in r["impact"]["controls"]
    obs = {x["id"]: x for x in client.get(f"{P}/compliance/obligations", headers=o).json()["data"]}
    assert obs[ob]["state"] == "REVIEW_REQUIRED"
    assert next(c for c in client.get(f"{P}/compliance/controls", headers=o).json()["data"] if c["id"] == ctl)
    sets = client.get(f"{P}/corpus/changesets", headers=a).json()["data"]
    assert any(s["id"] == cs["change_set_id"] and s["states"].get("MATERIAL_CONFIRMED") for s in sets)

    # pembukaan kembali: sitasi diarahkan ke Pasal 1 versi 2, lalu siklus validasi-persetujuan diulang
    pv2 = client.get(f"{P}/corpus/versions/{v2}/provisions", headers=a).json()["data"][0]["provision_version_id"]
    re = client.post(f"{P}/compliance/obligations/{ob}/reopen", headers=o, json={"reason": "Tenggat berubah", "new_provision_version_id": pv2})
    assert re.json()["data"]["state"] == "IN_VALIDATION"
    tr = client.get(f"{P}/compliance/trace/obligations/{ob}", headers=a).json()["data"]
    assert tr["citation"]["document_version"]["version_number"] == 2 and "12" in tr["citation"]["text"]


def test_applicability_maker_checker_and_profile_change(client):
    a, o, m, legal = login(client, "analyst"), login(client, "officer"), login(client, "manager"), login(client, "legal")
    doc, (v1, _) = _doc_with_two_versions(client, "Pasal 1\nBank wajib X.\nPasal 2\nBank wajib Y.", "Pasal 1\nBank wajib X.\nPasal 2\nBank wajib Y.")
    pvs = [p["provision_version_id"] for p in client.get(f"{P}/corpus/versions/{v1}/provisions", headers=a).json()["data"]]
    sug = client.post(f"{P}/compliance/applicability/suggest", headers=o, json={"version_id": v1}).json()["data"]
    assert sug["suggested_value"] == "APPLICABLE" and any(c.startswith("TITLE_KEYWORD") for c in sug["reason_codes"])
    d = client.post(f"{P}/compliance/applicability", headers=o, json={"version_id": v1, "decision_value": "PARTIALLY_APPLICABLE",
        "reason": "Hanya Pasal 1 relevan", "cited_provision_version_ids": [pvs[0]]}).json()["data"]["id"]
    r = client.post(f"{P}/compliance/applicability/{d}/submit", headers=o)
    assert r.status_code == 422 and r.json()["error_code"] == "SCOPE_REQUIRED"
    client.post(f"{P}/compliance/applicability/{d}/escalate", headers=o, json={"question": "Apakah Pasal 2 mengikat kami?"})
    assert client.post(f"{P}/compliance/applicability/{d}/legal-answer", headers=o, json={"answer": "x"}).status_code == 403
    assert client.post(f"{P}/compliance/applicability/{d}/legal-answer", headers=legal,
                       json={"answer": "Tidak, Pasal 2 untuk BPR", "citation_provision_version_ids": [pvs[0]]}).json()["data"]["state"] == "IN_ASSESSMENT"
    d2 = client.post(f"{P}/compliance/applicability", headers=o, json={"version_id": v1, "decision_value": "PARTIALLY_APPLICABLE",
        "reason": "Hanya Pasal 1", "cited_provision_version_ids": [pvs[0]], "scope_provision_version_ids": [pvs[0]]}).json()["data"]["id"]
    client.post(f"{P}/compliance/applicability/{d2}/submit", headers=o)
    assert client.post(f"{P}/compliance/applicability/{d2}/decision", headers=o, json={"outcome": "APPROVED"}).status_code == 403
    assert client.post(f"{P}/compliance/applicability/{d2}/decision", headers=m, json={"outcome": "REJECTED"}).status_code == 422
    assert client.post(f"{P}/compliance/applicability/{d2}/decision", headers=m, json={"outcome": "APPROVED"}).json()["data"]["state"] == "APPROVED"
    # ketentuan di luar lingkup PARTIALLY_APPLICABLE tidak dapat diekstrak
    out = client.post(f"{P}/compliance/obligations/extract", headers=o, json={"provision_version_id": pvs[1]})
    assert out.status_code == 409 and out.json()["error_code"] == "OUT_OF_APPLICABILITY_SCOPE"
    assert client.post(f"{P}/compliance/obligations/extract", headers=o, json={"provision_version_id": pvs[0]}).status_code == 200

    prof = client.get(f"{P}/compliance/profiles", headers=o).json()["data"][0]
    upd = client.put(f"{P}/compliance/profiles/{prof['id']}", headers=o,
                     json={"licenses": prof["licenses"] + ["IZIN_UJI"], "justification": "Izin baru diperoleh"}).json()["data"]
    assert d2 in upd["flagged_decisions"]
    new = client.post(f"{P}/compliance/applicability/{d2}/reopen", headers=o).json()["data"]
    assert new["state"] == "IN_ASSESSMENT"
    client.put(f"{P}/compliance/profiles/{prof['id']}", headers=o, json={"licenses": prof["licenses"], "justification": "Kembalikan profil uji"})


def test_runtime_config_is_admin_only_bounded_and_audited(client):
    admin, o, auditor = login(client, "admin"), login(client, "officer"), login(client, "auditor")
    assert client.put(f"{P}/config/remediation.window_days.HIGH", headers=o, json={"value": 30, "justification": "x"}).status_code == 403
    r = client.put(f"{P}/config/remediation.window_days.HIGH", headers=admin, json={"value": 5, "justification": "uji"})
    assert r.status_code == 422 and r.json()["error_code"] == "CONFIG_OUT_OF_BOUNDS"
    assert client.put(f"{P}/config/remediation.window_days.HIGH", headers=admin, json={"value": 20, "justification": ""}).status_code == 422
    assert client.put(f"{P}/config/remediation.window_days.HIGH", headers=admin, json={"value": 20, "justification": "Kebijakan baru"}).status_code == 200
    try:
        ob = make_active_obligation(client)
        fid = client.post(f"{P}/compliance/findings", headers=o, json={"obligation_id": ob, "title": "t", "description": "d",
              "severity": "HIGH", "owner_id": uid(client, o, "owner"), "target_closure_date": str(date.fromordinal(date.today().toordinal() + 10))}).json()["data"]["id"]
        bad = client.post(f"{P}/compliance/findings/{fid}/remediation", headers=o,
                          json={"description": "x", "due_date": str(date.fromordinal(date.today().toordinal() + 40))})
        assert bad.status_code == 422 and "20 hari" in bad.json()["message"]
    finally:
        client.put(f"{P}/config/remediation.window_days.HIGH", headers=admin, json={"value": 60, "justification": "Kembalikan default"})
    ev = client.get(f"{P}/audit?action=CONFIG_CHANGED&limit=5", headers=auditor).json()["data"]
    assert ev and ev[0]["before"]["key"] == "remediation.window_days.HIGH"
    assert client.get(f"{P}/config", headers=o).status_code == 403  # Konfigurasi sistem: hanya Auditor (R) dan Administrator
    keys = [c["key"] for c in client.get(f"{P}/config", headers=auditor).json()["data"]]
    assert not any("audit" in k or "sod" in k or "ai_label" in k for k in keys), "TC-GOV-11: tidak ada kunci untuk mematikan kontrol"


def test_upload_scan_rejects_malware_and_executables(client):
    o = login(client, "officer")
    ctl = client.post(f"{P}/compliance/controls", headers=o, json={"title": "Kontrol scan"}).json()["data"]["id"]
    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    r = client.post(f"{P}/compliance/controls/{ctl}/evidence", headers=o, files={"file": ("a.txt", eicar)})
    assert r.status_code == 422 and r.json()["error_code"] == "SCAN_FAILED"
    assert client.post(f"{P}/compliance/controls/{ctl}/evidence", headers=o, files={"file": ("a.pdf", b"MZ\x90\x00")}).json()["error_code"] == "SCAN_FAILED"
    assert client.post(f"{P}/compliance/controls/{ctl}/evidence", headers=o, files={"file": ("run.exe", b"hello")}).json()["error_code"] == "SCAN_FAILED"


def test_login_rate_limit_correlation_id_and_error_envelope(client):
    user = f"nobody{uuid.uuid4().hex[:4]}"
    codes = [client.post(f"{P}/auth/login", json={"username": user, "password": "x"}).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    cid = str(uuid.uuid4())
    r = client.get(f"{P}/compliance/dashboard", headers={**login(client, "officer"), "X-Correlation-Id": cid})
    assert r.headers["x-correlation-id"] == cid and r.headers["x-content-type-options"] == "nosniff"
    bad = client.post(f"{P}/compliance/findings", headers=login(client, "officer"), json={"title": "x"})
    body = bad.json()
    assert bad.status_code == 422 and body["code"] == "VALIDATION_ERROR" and body["offending"]["field"] and body["correlation_id"]


def test_relationship_and_taxonomy(client):
    a, m = login(client, "analyst"), login(client, "manager")
    d1, (v1, _) = _doc_with_two_versions(client, "Pasal 1\nBank wajib A.", "Pasal 1\nBank wajib A.", title="Manajemen Risiko Teknologi Informasi Bank Umum")
    d2, _ = _doc_with_two_versions(client, "Pasal 1\nBank wajib B.", "Pasal 1\nBank wajib B.", title="Perubahan atas Manajemen Risiko Teknologi Informasi Bank Umum")
    labels = client.get(f"{P}/corpus/documents/{d1}/labels", headers=a).json()["data"]
    assert {"Risiko TI dan siber", "Bank umum"} <= {lb["value"] for lb in labels} and all(lb["state"] == "SUGGESTED" for lb in labels)
    assert client.post(f"{P}/corpus/documents/{d1}/labels", headers=a, json={"dimension": "THEME", "value": "teks bebas"}).status_code == 422
    assert client.post(f"{P}/corpus/labels/{labels[0]['id']}/confirm", headers=a).json()["data"]["state"] == "CONFIRMED"
    rel = client.post(f"{P}/corpus/relationships", headers=a, json={"source_document_id": d2, "target_document_id": d1, "relation_type": "AMENDS"}).json()["data"]["id"]
    assert client.post(f"{P}/corpus/relationships/{rel}/confirm", headers=m).json()["error_code"] == "CITATION_REQUIRED"
    pv = client.get(f"{P}/corpus/versions/{v1}/provisions", headers=a).json()["data"][0]["provision_version_id"]
    rel2 = client.post(f"{P}/corpus/relationships", headers=a, json={"source_document_id": d2, "target_document_id": d1,
                       "relation_type": "AMENDS", "citing_provision_version_id": pv}).json()["data"]["id"]
    assert client.post(f"{P}/corpus/relationships/{rel2}/confirm", headers=m).json()["data"]["state"] == "CONFIRMED"
    doc = next(d for d in client.get(f"{P}/corpus/documents", headers=a).json()["data"] if d["id"] == d1)
    assert doc["status"] == "AMENDED"


def test_legal_reviewer_advisory_only(client):
    """FRD §4.1.4/§4.2/Eksibit 26: legal tidak menjalankan deteksi, tidak menilai materialitas, tidak membuat relasi;
    posisi hukum wajib menyitasi ketentuan yang teresolusi (TRD Eksibit 25: CITATION_UNRESOLVED)."""
    a, legal = login(client, "analyst"), login(client, "legal")
    doc, (v1, v2) = _doc_with_two_versions(client,
        "Pasal 5\nPerusahaan Efek wajib menyampaikan laporan paling lambat 10 (sepuluh) hari kerja.",
        "Pasal 5\nPerusahaan Efek wajib menyampaikan laporan paling lambat 5 (lima) hari kerja.")
    body = {"base_version_id": v1, "new_version_id": v2}
    # legal hanya R pada deteksi perubahan
    assert client.post(f"{P}/corpus/changes", headers=legal, json=body).status_code == 403
    ch = client.post(f"{P}/corpus/changes", headers=a, json=body).json()["data"]["changes"][0]["id"]
    # legal tidak menilai materialitas
    assert client.post(f"{P}/corpus/changes/{ch}/validate", headers=legal,
                       json={"material": True, "semantic_type": "DEADLINE_CHANGED", "reason": "x"}).status_code == 403
    client.post(f"{P}/corpus/changes/{ch}/escalate", headers=a, json={"question": "Apakah berlaku surut?"})
    pv = client.get(f"{P}/corpus/versions/{v2}/provisions", headers=a).json()["data"][0]["provision_version_id"]
    # sitasi wajib
    r = client.post(f"{P}/corpus/changes/{ch}/legal-answer", headers=legal, json={"answer": "Tidak berlaku surut"})
    assert r.status_code == 422 and r.json()["error_code"] == "CITATION_REQUIRED"
    # sitasi harus teresolusi
    r = client.post(f"{P}/corpus/changes/{ch}/legal-answer", headers=legal, json={"answer": "Tidak berlaku surut",
                    "citation_provision_version_ids": ["00000000-0000-0000-0000-000000000000"]})
    assert r.status_code == 422 and r.json()["error_code"] == "CITATION_UNRESOLVED"
    # sitasi valid: kembali ke IN_REVIEW, lalu Analis yang menilai
    assert client.post(f"{P}/corpus/changes/{ch}/legal-answer", headers=legal, json={"answer": "Tidak berlaku surut",
                       "citation_provision_version_ids": [pv]}).json()["data"]["review_state"] == "IN_REVIEW"
    assert client.post(f"{P}/corpus/changes/{ch}/validate", headers=a, json={"material": True, "semantic_type": "DEADLINE_CHANGED",
                       "reason": "Tenggat 10 menjadi 5 hari"}).json()["data"]["review_state"] == "VALIDATED"
    # legal tidak membuat relasi
    target, _ = _doc_with_two_versions(client, "Pasal 1\nBank wajib A.", "Pasal 1\nBank wajib A.")
    assert client.post(f"{P}/corpus/relationships", headers=legal, json={"source_document_id": doc, "target_document_id": target,
                       "relation_type": "AMENDS", "citing_provision_version_id": pv}).status_code == 403


def test_relationship_confirmed_by_manager_not_legal(client):
    """FRD §4.2 (Relasi regulasi: Peninjau Hukum RU, Manajer RA) & FR-RKM-009: legal boleh menyunting usulan,
    tetapi hanya Manajer yang mengonfirmasi; Analis tidak dapat mengonfirmasi."""
    a, m, legal = login(client, "analyst"), login(client, "manager"), login(client, "legal")
    d1, (v1, _) = _doc_with_two_versions(client, "Pasal 1\nBank wajib A.", "Pasal 1\nBank wajib A.")
    d2, _ = _doc_with_two_versions(client, "Pasal 1\nBank wajib B.", "Pasal 1\nBank wajib B.")
    pv = client.get(f"{P}/corpus/versions/{v1}/provisions", headers=a).json()["data"][0]["provision_version_id"]
    rel = client.post(f"{P}/corpus/relationships", headers=a, json={"source_document_id": d2, "target_document_id": d1,
                      "relation_type": "AMENDS", "citing_provision_version_id": pv}).json()["data"]["id"]
    # Peninjau Hukum: U (memberi catatan posisi pada usulan relasi), bukan A
    assert client.patch(f"{P}/corpus/relationships/{rel}", headers=legal,
                        json={"note": "Pasal penutup menegaskan perubahan, bukan pencabutan"}).status_code == 200
    assert client.post(f"{P}/corpus/relationships/{rel}/confirm", headers=legal).status_code == 403
    assert client.post(f"{P}/corpus/relationships/{rel}/confirm", headers=a).status_code == 403
    assert client.post(f"{P}/corpus/relationships/{rel}/confirm", headers=m).json()["data"]["state"] == "CONFIRMED"


def test_legal_cannot_validate_obligation(client):
    """TRD §7.6: IN_VALIDATION → PENDING_APPROVAL hanya diajukan Pejabat Kepatuhan; Peninjau Hukum hanya memberi posisi."""
    a, o, legal = login(client, "analyst"), login(client, "officer"), login(client, "legal")
    doc, (v1, _) = _doc_with_two_versions(client, "Pasal 1\nBank wajib melaporkan insiden paling lambat 24 (dua puluh empat) jam.",
                                          "Pasal 1\nBank wajib melaporkan insiden paling lambat 24 (dua puluh empat) jam.")
    pv1 = client.get(f"{P}/corpus/versions/{v1}/provisions", headers=a).json()["data"][0]["provision_version_id"]
    approve_applicability(client, v1, [pv1])
    ob = client.post(f"{P}/compliance/obligations/extract", headers=o, json={"provision_version_id": pv1}).json()["data"]["obligation_ids"][0]
    r = client.post(f"{P}/compliance/obligations/{ob}/validate", headers=legal, json={"owner_id": uid(client, o, "owner"), "low_confidence_reviewed": True})
    assert r.status_code == 403


def test_obligation_escalation_to_legal(client):
    """FRD Eksibit 33 / TRD §7.6: IN_VALIDATION → PENDING_LEGAL (Pejabat, pertanyaan wajib) → IN_VALIDATION (Peninjau Hukum, sitasi wajib)."""
    a, o, m, legal = login(client, "analyst"), login(client, "officer"), login(client, "manager"), login(client, "legal")
    doc, (v1, v2) = _doc_with_two_versions(client,
        "Pasal 1\nBank wajib melaporkan insiden paling lambat 24 (dua puluh empat) jam.",
        "Pasal 1\nBank wajib melaporkan insiden paling lambat 12 (dua belas) jam.")
    pv1 = client.get(f"{P}/corpus/versions/{v1}/provisions", headers=a).json()["data"][0]["provision_version_id"]
    approve_applicability(client, v1, [pv1])
    ob = client.post(f"{P}/compliance/obligations/extract", headers=o, json={"provision_version_id": pv1}).json()["data"]["obligation_ids"][0]
    esc, ans = f"{P}/compliance/obligations/{ob}/escalate", f"{P}/compliance/obligations/{ob}/legal-answer"
    row = lambda: next(x for x in client.get(f"{P}/compliance/obligations", headers=o).json()["data"] if x["id"] == ob)

    # hanya Pejabat Kepatuhan yang mengeskalasi; pertanyaan wajib
    assert client.post(esc, headers=legal, json={"question": "x"}).status_code == 403
    assert client.post(esc, headers=a, json={"question": "x"}).status_code == 403
    assert client.post(esc, headers=o, json={"question": ""}).status_code == 422
    assert client.post(esc, headers=o, json={"question": "Apakah near-miss termasuk insiden?"}).json()["data"]["state"] == "PENDING_LEGAL"
    assert row()["legal_question"] == "Apakah near-miss termasuk insiden?"

    # selama PENDING_LEGAL: tidak dapat diajukan dan tidak dapat dipetakan ke kontrol
    owner = uid(client, o, "owner")
    assert client.post(f"{P}/compliance/obligations/{ob}/validate", headers=o, json={"owner_id": owner, "low_confidence_reviewed": True}).status_code == 409
    ctl = client.post(f"{P}/compliance/controls", headers=o, json={"title": "Eskalasi", "owner_id": owner}).json()["data"]["id"]
    r = client.post(f"{P}/compliance/obligations/{ob}/controls/{ctl}", headers=o)
    assert r.status_code == 409 and r.json()["error_code"] == "AI_DRAFT_BLOCKED"

    # hanya Peninjau Hukum yang menjawab; sitasi wajib dan harus teresolusi
    assert client.post(ans, headers=o, json={"answer": "x"}).status_code == 403
    r = client.post(ans, headers=legal, json={"answer": "Near-miss tidak termasuk"})
    assert r.status_code == 422 and r.json()["error_code"] == "CITATION_REQUIRED"
    r = client.post(ans, headers=legal, json={"answer": "Near-miss tidak termasuk",
                    "citation_provision_version_ids": ["00000000-0000-0000-0000-000000000000"]})
    assert r.status_code == 422 and r.json()["error_code"] == "CITATION_UNRESOLVED"
    assert client.post(ans, headers=legal, json={"answer": "Near-miss tidak termasuk",
                       "citation_provision_version_ids": [pv1]}).json()["data"]["state"] == "IN_VALIDATION"
    assert "Sitasi:" in row()["legal_answer"] and row()["legal_reviewer"] == "legal"

    # alur normal berlanjut: validasi → persetujuan Manajer
    assert client.post(f"{P}/compliance/obligations/{ob}/validate", headers=o, json={"owner_id": owner, "low_confidence_reviewed": True}).json()["data"]["state"] == "PENDING_APPROVAL"
    assert client.post(f"{P}/compliance/obligations/{ob}/decision", headers=m, json={"outcome": "APPROVED"}).json()["data"]["state"] == "ACTIVE"