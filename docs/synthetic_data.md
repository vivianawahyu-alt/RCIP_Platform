# Data Sintetis RCIP — Spesifikasi & Generator

Memenuhi prinsip proposal V-TEKI hal. 20 dan TRD §10. **Tidak ada data pribadi, data klien, atau teks resmi peraturan.** Nomor peraturan sintetis memakai awalan `S-` (kecuali POJK 11/POJK.03/2022 dari seed awal, yang teksnya juga sintetis).

## Menjalankan

Generator membutuhkan database **kosong** (sudah dimigrasi, belum di-seed) agar tidak mencampur data demo dengan data kerja Anda.

```bash
# opsi A — database demo terpisah (data kerja di rcip_db tidak tersentuh)
docker exec rcip_postgres createdb -U rcip rcip_demo
docker compose exec -e DATABASE_URL=postgresql+psycopg://rcip:rcip_dev_password@postgres:5432/rcip_demo api alembic upgrade head
docker compose exec -e DATABASE_URL=postgresql+psycopg://rcip:rcip_dev_password@postgres:5432/rcip_demo api python -m seed.generate --seed 42
docker compose exec -e DATABASE_URL=postgresql+psycopg://rcip:rcip_dev_password@postgres:5432/rcip_demo api python -m seed.validate
# lalu ubah DATABASE_URL di .env ke .../rcip_demo dan `docker compose restart api worker`

# opsi B — tanpa Docker
alembic upgrade head && python -m seed.generate --seed 42 --anchor 2026-10-27 && python -m seed.validate
```

- `--seed` mengendalikan RNG; `--anchor` adalah tanggal acuan "hari ini". **Seed + anchor sama → ID, teks, status, tanggal identik** (diuji `tests/test_synthetic_data.py` dengan membandingkan digest dua database).
- Idempoten: bila data sintetis sudah ada, generator berhenti tanpa mengubah apa pun.
- `python -m seed.validate` memeriksa 15 invarian (ketertelusuran, SoD, bukti, persetujuan) dan keluar dengan kode 1 bila ada pelanggaran; juga menampilkan peringatan anomali.

## Isi dataset (seed 42)

| Entitas | Jumlah | Catatan |
|---|---|---|
| Dokumen regulasi | 30 | OJK 14 · Bank Indonesia 8 · JDIH 8 (SM-01) |
| Versi dokumen | 36 | 5 rantai perubahan (SM-04), satu dengan 3 versi |
| Pasal (versi) | ±110 | jenis: kewajiban, larangan, definisi, kewenangan ("dapat") |
| Relasi | 1 | POJK S-12/2024 **mencabut** POJK S-09/2016 (status REVOKED) |
| Label taksonomi | ±39 | ±70% terkonfirmasi, sisanya saran aturan |
| Perubahan | 8 | MATERIAL_CONFIRMED, VALIDATED (menunggu Manajer), DETECTED (lewat SLA), REJECTED (redaksional) |
| Keputusan keberlakuan | ±21 | APPROVED, NOT_APPLICABLE (BPR, pinjam-meminjam), REQUIRES_FURTHER_REVIEW (PDP) menunggu persetujuan, SUPERSEDED |
| Kewajiban | ±48 | ≥40 tervalidasi (SM-06); AI_DRAFT, PENDING_APPROVAL, REVIEW_REQUIRED |
| Risiko / kontrol | ±36 / ±36 | ~20% kewajiban sengaja tanpa kontrol (kesenjangan) |
| Bukti | ±62 | ACCEPTED / SUBMITTED / REJECTED (PERIOD_MISMATCH) |
| Asesmen | ±22 | SIGNED_OFF, PENDING_SIGNOFF, CONCLUDED; sebagian tidak/sebagian efektif |
| Temuan | 15 | semua status W12; ≥3 CLOSED, 1 dibuka kembali (SM-08) |
| Laporan | 2 | satu SUPERSEDED (terbit), satu DRAFT |
| Pengguna | 13 | 8 persona + `owner_it`, `owner_ops`, `owner_fin`, `officer2`, `manager2` (password `demo1234`) |

Angka pasti dicetak generator dan `seed.validate`.

## Pola yang sengaja disertakan

| Kategori | Contoh |
|---|---|
| Normal | kewajiban aktif bertuan dengan kontrol efektif bersign-off |
| Anomali | tindakan remediasi lewat tenggat; risiko diterima yang tanggal tinjaunya lewat; perubahan melewati SLA reviu; kontrol tanpa pemilik |
| Edge case | dokumen dicabut; dokumen status `UNKNOWN` (memblokir laporan bila dipakai); NOT_APPLICABLE dipertahankan sebagai jawaban audit; keputusan berbeda dari saran aturan; perubahan redaksional yang diindikasikan material oleh diff tetapi ditolak analis |
| Data kosong | ±15% kewajiban tanpa frekuensi; pasal tanpa kewajiban |
| Urutan historis | tanggal berlaku ±4 tahun ke belakang; temuan berumur 15–140 hari; audit & persetujuan bertanggal sesuai urutan |
| Integritas | seluruh FK + trigger aktif; SoD dijaga (maker ≠ checker di setiap persetujuan) |

## Kunci jawaban & dataset evaluasi

| Berkas | Isi |
|---|---|
| `seed/ground_truth/changes.yaml` | perubahan yang diharapkan per pasangan versi + materialitas menurut manusia |
| `tests/ai/adversarial_extraction.yaml` | 16 jebakan ekstraksi (TRD §13.5) |
| `tests/ai/heldout_extraction.yaml` | 10 kasus held-out (tidak dipakai menyetel) |
| `tests/ai/questions_grounded.yaml` | 30 pertanyaan copilot + sitasi yang benar |
| `tests/ai/questions_out_of_corpus.yaml` | 10 pertanyaan yang wajib ditolak |

## Data dictionary

[data_dictionary.md](data_dictionary.md) dan [erd.md](erd.md) dibangkitkan dari skema database: `python -m seed.data_dictionary`.
