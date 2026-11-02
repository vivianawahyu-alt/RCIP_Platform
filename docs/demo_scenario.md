# Skenario Demonstrasi Akhir (Gate G6)

Durasi ±20 menit. Persiapan: database demo dari `python -m seed.generate --seed 42` (lihat `synthetic_data.md`), API + frontend berjalan, satu jendela browser per akun atau gunakan tombol Keluar. Password semua akun `demo1234`.

**Pesan utama:** setiap angka dan setiap kewajiban dapat ditelusuri mundur sampai pasal pada versi peraturan yang melahirkannya — dan tidak ada satu orang pun yang dapat menyetujui pekerjaannya sendiri.

| # | Akun | Langkah | Yang ditunjukkan |
|---|---|---|---|
| 1 | `executive` | Beranda | Postur sebagai kalimat (pembilang/penyebut), draf AI tidak dihitung, kesenjangan bersitasi, tenggat & keterlambatan |
| 2 | `analyst` | Pusat Regulasi → Korpus | 30 dokumen (OJK/BI/JDIH), label taksonomi, relasi pencabutan POJK S-12/2024 → S-09/2016 |
| 3 | `analyst` | Perubahan → SEOJK S-29/2022 v1→v2 | Diff per kata (uji penetrasi 1→2 kali), indikasi material ≠ keputusan; validasi materialitas + alasan |
| 4 | `manager` | Perubahan → konfirmasi | **Titik kendali 1**; permukaan dampak dicatat; lihat juga POJK 11 (24→12 jam) yang sudah dikonfirmasi |
| 5 | `officer` | Kepatuhan → Keberlakuan → Susun | Saran aturan + kode alasan untuk PBI S-22/2020; keputusan manusia "Berlaku" (izin PJP) berbeda dari saran; sitasi pasal |
| 6 | `manager` | Keberlakuan → Setujui | **Titik kendali 2**; coba setujui sebagai penyusun → ditolak |
| 7 | `officer` | Korpus → Ekstrak Pasal 15 → Kewajiban | Draf AI, "Mengapa AI mengusulkan ini?" (frasa disorot, model, grounding), keyakinan rendah wajib dikonfirmasi |
| 8 | `manager` | Kewajiban → Setujui | **Titik kendali 3** |
| 9 | `officer` | Kewajiban → tab Perlu ditinjau | Kewajiban dari pasal yang berubah material; buka kembali & arahkan sitasi ke versi baru |
| 10 | `owner` → `officer` | Risiko & kontrol | Unggah bukti; Pejabat menerima dengan rasional (bukti jadi imutabel); asesmen desain vs operasional → temuan otomatis |
| 11 | `manager` | Asesmen & sign-off | **Titik kendali 4** |
| 12 | `owner` → `officer` → `owner` | Temuan & Remediasi | Tindakan, perpanjangan (tanggal asli tetap), bukti penutupan, ajukan penutupan |
| 13 | `manager` | Temuan → validasi | **Titik kendali 5**; tunjukkan temuan yang tindakannya dimiliki manajer → `SOD_VIOLATION`; risiko diterima ≠ terselesaikan |
| 14 | `officer` → `manager` | Laporan | Draf 10 bagian (kutipan pasal verbatim, penafian berisi angka korpus) → **titik kendali 6** → laporan lama otomatis Digantikan |
| 15 | `auditor` | Jejak audit | Saring per objek/aksi/aktor, sebelum/sesudah, correlation ID, ekspor CSV; auditor tidak punya tombol aksi |
| 16 | semua | Tanya regulasi | Pertanyaan bersumber (bersitasi) vs "tarif pajak penghasilan" → INSUFFICIENT_BASIS |
| 17 | `admin` | Administrasi | Ubah SLA reviu dengan justifikasi → muncul di jejak audit; tidak ada saklar untuk mematikan audit/SoD |

## Bukti pendukung yang disiapkan
- `pytest -q` hijau (tunjukkan jumlah test), `python -m seed.validate` → semua invarian terpenuhi.
- `docs/ai_evaluation_report.md` — hasil evaluasi AI terhadap target.
- Rencana cadangan: bila jaringan/LLM tidak tersedia, seluruh demo berjalan dengan `rule-based-v2` dan copilot retrieval-only.

## Pertanyaan yang mungkin diajukan penguji
| Pertanyaan | Jawaban singkat & bukti |
|---|---|
| Bagaimana jika AI salah? | Draf tidak pernah resmi tanpa validator & penyetuju bernama; grounding menolak frasa karangan (laporan evaluasi §2) |
| Bisakah admin mengubah data lama? | Trigger DB menolak perubahan rekaman terbit/diterima; audit append-only |
| Mengapa skor rendah? | Skor hanya menghitung kontrol yang asesmen terakhirnya *bersign-off* efektif; draf & "belum terbukti" tidak dihitung (DRR-04) |
| Data dari mana? | Sintetis dan reproducible (`--seed 42`), tidak ada data pribadi/klien |
