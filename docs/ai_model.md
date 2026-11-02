# Dokumentasi AI / Model — RCIP

Prinsip (FRD §13): **AI mengusulkan, orang yang bernama memutuskan.** AI tidak pernah menetapkan keberlakuan, materialitas, atau status bermakna kepatuhan. Semua komponen AI melewati satu pintu, `app/ai/gateway.py` (ADR-04).

## 1. Komponen

| Komponen | Lokasi | Peran AI | Keputusan manusia |
|---|---|---|---|
| Ekstraksi kewajiban (W8) | `gateway.extract_obligations` | Draf kewajiban terstruktur dari teks pasal | Validasi Pejabat Kepatuhan + persetujuan Manajer (titik 3) |
| Saran keberlakuan (W7) | `applicability.suggest_applicability` | Saran berbasis aturan + kode alasan | Keputusan Pejabat + persetujuan Manajer (titik 2) |
| Deteksi perubahan (W5) | `corpus/diff_engine.py` | **Tanpa AI** — diff deterministik + indikasi material | Validasi analis + konfirmasi Manajer (titik 1) |
| Copilot (W15) | `copilot/services.py` | Retrieval pasal bersitasi; menolak bila dasar tidak memadai | Tidak dapat menulis ke objek domain |

## 2. Ekstraksi kewajiban

**Penyedia.** Bila `OPENAI_API_KEY` diisi: LLM (`LLM_MODEL_NAME`, default `gpt-4o-mini`, `temperature=0`, keluaran JSON) dengan templat `app/ai/templates/obligation_v1.txt`. Bila kosong: `rule-based-v2` (deterministik).

**rule-based-v2** (setelah evaluasi G4):
- penanda kewajiban `wajib | diwajibkan | harus`, larangan `dilarang` (dicatat sebagai `prohibited_actions`);
- mengabaikan negasi (`tidak wajib`, `tidak diwajibkan`), kalimat definisi (`… adalah …` sebelum penanda), dan subjek regulator (OJK, Bank Indonesia, PPATK, Menteri);
- satu kalimat = satu draf (E8.1); tenggat dari frasa `paling lambat|lama|sedikit|singkat …`; frekuensi `EVENT_DRIVEN` / `PERIODIC` dari kata kunci;
- keyakinan tetap **0,60**.

**Skema keluaran** (`ObligationDraft`, Pydantic): `plain_language_summary, regulated_entity, required_actions[], prohibited_actions[], condition, frequency, deadline_expression, required_evidence, supporting_phrases[], confidence∈[0,1]`.

**Gerbang validasi (urut):**
1. Validasi skema Pydantic → gagal: `422 AI_SCHEMA_VIOLATION`, tidak ada yang disimpan.
2. Grounding: setiap `supporting_phrases` wajib muncul verbatim (normalisasi spasi/huruf) di teks pasal → gagal: `422 AI_GROUNDING_FAILED`.
3. Keberlakuan: harus ada keputusan **APPROVED** bernilai APPLICABLE / PARTIALLY_APPLICABLE (pasal dalam lingkup) → bila tidak: `409`.
4. Keyakinan < `ai.confidence_floor` (default 0,70, dapat disetel admin) → `low_confidence=true`; validasi mewajibkan centang "telah ditinjau manual" (E8.3).
5. Status awal selalu `AI_DRAFT`, `derived_from_ai=true`; trigger DB memblokir pemetaan kontrol; dasbor & laporan mengecualikannya.

**Log.** Setiap panggilan menulis `platform.ai_call_log`: templat & versi, `model_id`, prompt lengkap, respons mentah, `schema_valid`, `grounding_passed`, keyakinan. Kewajiban menyimpan `ai_call_id`, `model_id`, dan `supporting_phrases`.

**Explainability di UI.** Tombol "Mengapa AI mengusulkan ini?" menampilkan teks pasal dengan frasa pendukung disorot, model, templat, hasil validasi skema/grounding, dan keyakinan.

## 3. Saran keberlakuan

Aturan transparan: label taksonomi `POPULATION` yang terkonfirmasi mengungguli kata kunci judul; kode alasan dikembalikan (`LABEL_POPULATION:…`, `TITLE_KEYWORD:…`, `ENTITY_MATCH:…`, `ENTITY_MISMATCH:…`, `NO_POPULATION_MATCH`, `DOC_REVOKED`). Keputusan yang berbeda dari saran ditandai di UI ("Berbeda dari saran aturan") — contoh di data demo: PBI Penyelenggara Jasa Pembayaran disarankan *Tidak berlaku* (entitas bank umum) tetapi diputuskan *Berlaku* karena organisasi memegang izin PJP.

## 4. Copilot

Retrieval full-text bahasa Indonesia (Postgres `indonesian`) hanya atas versi **PUBLISHED terbaru** dari dokumen yang tidak dicabut. Kandidat diambil dengan OR atas lexeme pertanyaan (kata tanya/fungsi dibuang), lalu diberi **skor cakupan berbobot IDF**; di bawah 0,5 → `INSUFFICIENT_BASIS` dengan daftar istilah yang ditelusuri (SM-10). Moda saat ini *retrieval-only* (E15.1): jawaban = kutipan pasal, sehingga tidak ada pernyataan faktual tanpa sitasi (SM-09). Pertanyaan bernada nasihat hukum memunculkan pernyataan bahwa copilot tidak memberi nasihat hukum (E15.2). Setiap interaksi dicatat di `ai_call_log` (`copilot_retrieval/v1`). Promosi jawaban menjadi draf rekaman belum diimplementasikan.

## 5. Hasil evaluasi

Lihat [ai_evaluation_report.md](ai_evaluation_report.md) (dibangkitkan `python -m app.ai.evaluate`). Ringkasan saat dokumen ini ditulis: recall diff 100% (target ≥95%), grounding menangkap 100% halusinasi sisipan, copilot hit@3 96,7%, sitasi 100%, penolakan di luar korpus 100%; ekstraksi `rule-based-v2` akurasi held-out 90% (v1: 40%).

## 6. Aturan data AI

- Hanya teks peraturan publik yang dikirim ke LLM; tidak ada data pribadi/klien (A-08). Bukti, temuan, dan profil organisasi tidak pernah dikirim.
- Tidak ada kunci konfigurasi yang dapat mematikan pelabelan AI, grounding, audit, atau SoD (TC-GOV-11).
- Bila LLM tidak tersedia: `503 AI_UNAVAILABLE` dengan anjuran jalur manual; copilot tetap berjalan (retrieval-only).

## 7. Mengganti / menambah model

1. Implementasikan pemanggilan di `gateway.call_extractor` (kembalikan `model_id, prompt, raw`).
2. Jangan mengubah gerbang skema & grounding.
3. Jalankan `python -m app.ai.evaluate` dan bandingkan dengan baseline di laporan; tambahkan kasus ke `tests/ai/*.yaml` bila menemukan pola gagal baru (jangan menyetel pada set held-out).
