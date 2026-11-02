# Tahap 3 — Penyelesaian sampai Gate G6 (demo, dokumentasi, serah terima)

Acuan: proposal V-TEKI × UKDW (baseline hal. 21, deliverable hal. 22, gate hal. 23), FRD §2.4 (SM-01…14), TRD §10, §12–§14.

## Fitur
- **Titik kendali #1 — konfirmasi materialitas (W5)**: reviu per perubahan (validasi analis, eskalasi hukum, konfirmasi/kembalikan oleh Manajer). Deteksi diff tidak lagi memicu apa pun; hanya MATERIAL_CONFIRMED yang menandai kewajiban & keputusan keberlakuan terdampak menjadi REVIEW_REQUIRED dan kontrol `SOURCE_CHANGED`. Permukaan dampak dicatat. Perbandingan versi idempoten.
- **Titik kendali #2 — keberlakuan (W7)**: draf bersitasi, PARTIALLY_APPLICABLE dengan daftar pasal, REQUIRES_FURTHER_REVIEW dengan pemilik & target, eskalasi hukum, persetujuan Manajer, supersede, reopen. Saran aturan dengan kode alasan. Ekstraksi kini mensyaratkan keputusan APPROVED.
- **Profil organisasi berversi** (E7.1): perubahan atribut menandai keputusan terkait.
- **Kewajiban**: explainability (frasa pendukung, model, templat, grounding, keyakinan), LOW_CONFIDENCE wajib konfirmasi tinjauan (E8.3), reopen REVIEW_REQUIRED dengan pengalihan sitasi ke versi baru.
- **W4 relasi** (mengubah/mencabut + sitasi penetap → status dokumen) dan **W6 taksonomi terkendali** (saran aturan → konfirmasi).
- **Konfigurasi runtime teraudit** (FR-GOV-007) + halaman Administrasi; tidak ada kunci untuk mematikan audit/SoD/label AI.
- Copilot: retrieval berbobot IDF dengan ambang cakupan, penolakan INSUFFICIENT_BASIS, deteksi permintaan nasihat hukum, log interaksi.
- Diff ditampilkan per kata.

## Data sintetis & evaluasi
- `seed/generate.py`: 30 dokumen (OJK 14/BI 8/JDIH 8), 5 rantai perubahan, ≥40 kewajiban tervalidasi, 15 temuan di semua status, anomali & edge case; reproducible (seed + anchor) dan idempoten. `seed/validate.py` (15 invarian), `seed/data_dictionary.py` (data dictionary + ERD dari DB).
- `app/ai/evaluate.py` + dataset berlabel (`seed/ground_truth`, `tests/ai`): recall diff 100%, grounding 100%, copilot hit@3 96,7%, sitasi 100%, penolakan 100%. Ekstraktor `rule-based-v2` setelah evaluasi: held-out 40% → 90%.

## Keamanan & observabilitas
- Correlation ID end-to-end (header ↔ audit), log JSON per permintaan, `/metrics`, header keamanan, amplop error RFC 7807 + `offending`, handler 422/500 konsisten, pembatasan laju login, pemeriksaan berkas unggahan, guard JWT secret di production. CI GitHub Actions.

## Test
39 test (sebelumnya 20): `test_governance.py`, `test_sod_negative.py` (SM-13), `test_ai_evaluation.py`, `test_synthetic_data.py` baru; helper `approve_applicability`.

## Perubahan perilaku yang perlu diketahui
- Ekstraksi butuh keputusan keberlakuan yang disetujui; keputusan lama dimigrasikan sebagai APPROVED (warisan).
- Draf `rule-based` (keyakinan 0,60 < ambang 0,70) selalu memerlukan centang tinjauan manual saat validasi.
- `GET /compliance/profiles` dan `POST /compliance/applicability` dipindah ke modul keberlakuan dengan skema baru.

## Migrasi
`003_governance_completion` — hanya ADD COLUMN / CREATE TABLE + backfill; diuji pada DB baru, backup DB tim, dan DB berisi data tahap 1.
