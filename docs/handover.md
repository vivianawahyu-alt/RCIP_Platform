# Dokumen Serah Terima (Handover) — RCIP

Capstone 01 V-TEKI × UKDW · Regulatory & Compliance Intelligence Platform · status: siap demonstrasi akhir (Gate G6).

## 1. Ringkasan

RCIP adalah aplikasi web yang menjaga rantai bukti kepatuhan sebagai relasi basis data: *pasal pada versi tertentu → keberlakuan → kewajiban → risiko/kontrol → bukti → asesmen → temuan → remediasi → persetujuan → laporan → audit*. AI hanya menyusun draf; enam titik kendali maker-checker ditegakkan di aplikasi dan di database.

## 2. Status deliverable (proposal V-TEKI hal. 22)

| Kelompok | Deliverable | Lokasi / status |
|---|---|---|
| Produk | Working web application | `app/` (API) + `web/` (frontend) ✅ |
| Produk | Integrated end-to-end workflow | 16 langkah, `docs/demo_scenario.md`, `tests/test_flagship_flow.py` ✅ |
| Produk | Management dashboard | Beranda (FRD §14) ✅ |
| Produk | Demonstration scenario | `docs/demo_scenario.md` ✅ |
| Teknis | Source code | repositori ini ✅ |
| Teknis | Architecture diagram | `docs/architecture.md` (C4 L1–L3 + sekuens) ✅ |
| Teknis | Database schema | `alembic/versions/001–003`, `docs/erd.md`, `docs/data_dictionary.md` (dibangkitkan) ✅ |
| Teknis | API documentation | `docs/api.md` + `docs/openapi.json` (dibangkitkan), Swagger `/docs` ✅ |
| Teknis | AI/model documentation | `docs/ai_model.md` ✅ |
| Teknis | Synthetic data & data dictionary | `seed/generate.py`, `docs/synthetic_data.md`, `docs/data_dictionary.md` ✅ |
| Teknis | Automated tests | `tests/` — 39 test, CI `.github/workflows/ci.yml` ✅ |
| Teknis | Deployment guide | `docs/deployment_guide.md` ✅ |
| Bisnis | Functional Requirement Specification | RCIP-FRD-001 (dokumen tim) ✅ |
| Bisnis | Technical Requirement Specification | RCIP-TRD-001 (dokumen tim) ✅ |
| Bisnis | User manual | `docs/user_manual.md` ✅ |
| Bisnis | Product pitch deck | ✅ deck 15 slide (artifact Slides “RCIP — Pitch Deck Capstone 01”, dapat diunduh .pptx/PDF) |
| Bisnis | Final demonstration video | ⬜ direkam tim mengikuti `docs/demo_scenario.md` |
| Bisnis | Handover document | dokumen ini ✅ |
| Governance | Risk register | `docs/risk_register.md` ✅ |
| Governance | Security & privacy checklist | `docs/security_privacy_checklist.md` ✅ |
| Governance | AI evaluation report | `docs/ai_evaluation_report.md` (+ `.json`, dibangkitkan) ✅ |
| Governance | Audit-trail demonstration | halaman Jejak audit, timeline temuan, demo langkah 15 ✅ |
| Governance | Known limitations & roadmap | `docs/known_limitations_roadmap.md` ✅ |

## 3. Enterprise baseline (proposal hal. 21)

| Komponen | Implementasi |
|---|---|
| Web-based application | React 18 + FastAPI |
| Clear user roles | 8 persona (FRD §4), matriks izin di server |
| Authentication & authorization | JWT, PBKDF2, RBAC, lingkup pemilik, rate limit |
| Configurable workflow | Parameter runtime teraudit (`platform.config`): jendela remediasi, ambang AI, SLA, batas berkas & login |
| API-first integration | `/api/v1`, OpenAPI, kontrak `citations/resolve` |
| Data validation | Pydantic + CHECK/FK/trigger DB + `seed.validate` |
| Human-in-the-loop | AI_DRAFT, 6 titik kendali, konfirmasi tinjauan keyakinan rendah |
| Explainable AI / reason code | frasa pendukung disorot, model/templat/grounding/keyakinan; kode alasan keberlakuan |
| Audit trail | append-only, sebelum/sesudah, correlation ID, ekspor CSV |
| Logging & monitoring | log JSON per permintaan, `ai_call_log`, `/metrics` |
| Error handling | amplop RFC 7807 + `offending`, tanpa kebocoran stack trace |
| Security controls | lihat checklist |
| Privacy protection | data sintetis, aturan data AI |
| Automated testing | 39 test + CI |
| Deployment documentation | `deployment_guide.md` |
| User manual | `user_manual.md` |
| Technical documentation | `architecture.md`, `ai_model.md`, `api.md`, `data_dictionary.md` |
| Product demonstration | `demo_scenario.md` |

## 4. Ukuran keberhasilan (FRD §2.4) — status terukur

| ID | Target | Hasil | Bukti |
|---|---|---|---|
| SM-01 | 30–50 dokumen, ≥8 per sumber | 30 (OJK 14, BI 8, JDIH 8) — sintetis | `seed.generate`, Beranda |
| SM-02 | ≥90% batas Pasal benar | segmenter lulus uji unit; belum diuji pada 10 PDF nyata | `test_segmenter_hierarchy` |
| SM-03 | 100% relasi diketahui tercatat | 1/1 relasi pencabutan di dataset demo | `corpus.relationship` |
| SM-04 | recall diff ≥95% pada ≥4 rantai | 100% (8/8) pada 5 rantai | `ai_evaluation_report.md` §3 |
| SM-05 | keputusan keberlakuan lengkap | sitasi ≥1, alasan, pemilik, persetujuan diwajibkan | `test_applicability_maker_checker_and_profile_change` |
| SM-06 | ≥40 kewajiban tervalidasi | 45 di dataset demo | `seed.validate` |
| SM-07 | kewajiban berlaku dipetakan atau ditandai kesenjangan | kesenjangan dihitung & dipindai menjadi temuan | Beranda, `gaps/scan` |
| SM-08 | ≥10 temuan, ≥3 ditutup, ≥1 dibuka kembali | 15 / 6 / 1 | dataset demo |
| SM-09 | 100% jawaban copilot bersitasi | 100% | evaluasi §4 |
| SM-10 | 100% dari 10 pertanyaan luar korpus ditolak | 100% | evaluasi §4 |
| SM-11 | angka laporan dapat di-drill | `referenced_object_versions`, `drill` dasbor, drill-through rantai | `test_report_maker_checker_and_immutability` |
| SM-12 | 100% event audit lengkap | aktor, aksi, objek, waktu, sebelum/sesudah, correlation ID | `governance.audit` |
| SM-13 | 0 persetujuan diri dari ≥12 percobaan | 0 dari 16 | `tests/test_sod_negative.py` |
| SM-14 | kontrak stabil di CI | contract test `citations/resolve` + CI | `test_contract_citation_resolve` |

## 5. Hasil pengujian

`pytest -q` → **39 passed**, dijalankan pada tiga basis data: (1) DB baru hasil migrasi + seed, (2) backup DB tim yang di-upgrade 001→003, (3) DB berisi data lama tahap 1 yang di-upgrade. Alur UI diuji otomatis di browser (Playwright): ekstraksi → validasi → kontrol → bukti → asesmen → sign-off → remediasi → penutupan → laporan, serta reviu perubahan, keberlakuan, penjelasan AI, pembukaan kembali kewajiban, dan konfigurasi admin. `python -m seed.validate` → 15/15 invarian terpenuhi.

| Berkas test | Cakupan |
|---|---|
| `test_unit.py` | segmenter, diff, grounding, ekstraktor, SoD |
| `test_traceability.py` | invarian ketertelusuran & imutabilitas DB |
| `test_flagship_flow.py` | 16 langkah end-to-end, kontrak, RBAC |
| `test_findings_flow.py` | remediasi→penutupan, SoD penutupan, jendela severity, risk acceptance, asesmen & sign-off, laporan, audit, lingkup pemilik |
| `test_governance.py` | titik 1 & 2, propagasi dampak, reopen, profil, konfigurasi, scan berkas, rate limit, correlation ID, relasi & taksonomi |
| `test_sod_negative.py` | SM-13: 16 percobaan persetujuan diri |
| `test_ai_evaluation.py` | recall diff, guardrail grounding, regresi ekstraktor |
| `test_synthetic_data.py` | generator reproducible & idempoten, validator, evaluasi copilot |

## 6. Struktur repositori

```
app/            API: platform (auth, audit, config), corpus (Group A), compliance (Group B), ai, copilot, shared
alembic/        migrasi 001 (skema dasar) · 002 (temuan/asesmen/laporan) · 003 (titik 1–2, relasi, taksonomi, config)
seed/           seed minimal, generator data sintetis, validator, data dictionary, ground truth
tests/          test otomatis + tests/ai (dataset evaluasi)
web/            frontend React (src/pages per halaman, ui.tsx komponen bersama)
docs/           seluruh deliverable dokumen
```

## 7. Akun demo

`analyst`, `officer`, `officer2`, `owner`, `owner_it`, `owner_ops`, `owner_fin`, `legal`, `manager`, `manager2`, `auditor`, `executive`, `admin` — password `demo1234` (akun `*2` dan `owner_*` hanya ada di dataset hasil generator).

## 8. Pemeliharaan

- Setelah mengubah skema: buat migrasi baru di `alembic/versions`, lalu `python -m seed.data_dictionary`.
- Setelah mengubah endpoint: `python -m app.api_docs`.
- Setelah mengubah AI: `python -m app.ai.evaluate`; jangan menyetel pada `tests/ai/heldout_extraction.yaml`.
- Riwayat perubahan per tahap: `CHANGELOG_TAHAP2.md`, `CHANGELOG_TAHAP3.md`.

## 9. Kontak & keputusan terbuka

Keputusan yang masih perlu dikonfirmasi mentor: jendela remediasi MEDIUM (90 hari) dan LOW (180 hari) adalah asumsi tim; ambang cakupan copilot 0,5; perlakuan keputusan keberlakuan lama sebagai APPROVED (warisan) saat migrasi.
