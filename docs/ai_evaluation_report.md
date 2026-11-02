# Laporan Evaluasi AI — RCIP

_Dibangkitkan otomatis oleh `python -m app.ai.evaluate` pada 2026-10-27T11:16:45 UTC. Model ekstraksi: `rule-based-v2`._

## Ringkasan terhadap target

| Ukuran | Hasil | Target | Status |
|---|---|---|---|
| Recall deteksi perubahan (SM-04) | 100.0% | ≥ 95.0% | Tercapai |
| Halusinasi tertangkap grounding | 100.0% | ≥ 100.0% | Tercapai |
| Jawaban copilot bersitasi (SM-09) | 100.0% | ≥ 100.0% | Tercapai |
| Penolakan di luar korpus (SM-10) | 100.0% | ≥ 100.0% | Tercapai |
| Copilot menemukan pasal benar (hit@3) | 96.7% | ≥ 80.0% | Tercapai |

Ekstraksi kewajiban tidak diberi target lulus/gagal karena TRD menyatakan akurasi model tidak dijanjikan sebelum baseline disepakati; angka di bawah adalah baseline.

## 1. Ekstraksi kewajiban

Set standar: 81 pasal unik korpus sintetis, label jenis ditetapkan manual (OBL/PROHIB = menimbulkan kewajiban; DEF/PERM = tidak).

| Presisi | Recall | F1 | TP | FP | FN | TN | Skema tidak valid | Grounding gagal |
|---|---|---|---|---|---|---|---|---|
| 98.6% | 100.0% | 99.3% | 69 | 1 | 0 | 11 | 0 | 0 |

Kesalahan pada set standar:

- PBI S-07/2024 1 (DEF): FP

Set adversarial (16 jebakan, TRD §13.5): akurasi 93.8%; tenggat benar 4/4.

| Kasus | Jebakan | Diharapkan | Prediksi | Benar | Tenggat |
|---|---|---|---|---|---|
| `considerans_date` | tanggal di konsiderans bukan tenggat | bukan | 0 kewajiban | ya | - |
| `cross_reference_recipient` | pihak penerima dalam rujukan silang bukan penerima kewajiban | bukan | 0 kewajiban | ya | - |
| `may_not_must` | 'dapat' (boleh) bukan 'wajib' | bukan | 0 kewajiban | ya | - |
| `definition_with_keyword` | definisi istilah yang memuat kata 'Wajib' | bukan | 1 kewajiban | TIDAK | - |
| `annex_deadline` | tenggat di lampiran yang tidak diurai platform | kewajiban | 1 kewajiban | ya | ya |
| `negated_obligation` | pengecualian 'tidak wajib' | bukan | 0 kewajiban | ya | - |
| `prohibition` | larangan juga kewajiban (prohibited action) | kewajiban | 1 kewajiban | ya | - |
| `two_obligations` | satu pasal dua kewajiban (E8.1) | kewajiban | 2 kewajiban | ya | ya |
| `conditional_event` | kewajiban bersyarat (berbasis peristiwa) | kewajiban | 1 kewajiban | ya | ya |
| `sanction_clause` | ketentuan sanksi bukan kewajiban baru | bukan | 0 kewajiban | ya | - |
| `entry_into_force` | tanggal berlaku bukan tenggat | bukan | 0 kewajiban | ya | - |
| `harus_synonym` | 'harus' bermakna wajib | kewajiban | 1 kewajiban | ya | - |
| `regulator_obligation` | kewajiban milik regulator, bukan bank | bukan | 0 kewajiban | ya | - |
| `relative_deadline` | tenggat relatif tanpa angka | kewajiban | 1 kewajiban | ya | ya |
| `diwajibkan_form` | bentuk pasif 'diwajibkan' | kewajiban | 1 kewajiban | ya | - |
| `recommendation` | anjuran 'sebaiknya' bukan kewajiban | bukan | 0 kewajiban | ya | - |

Held-out: 9/10 benar; salah: h_definition_2.

**Interpretasi.** v1 hanya mengenali kata `wajib`, sehingga gagal pada larangan, sinonim (`harus`, `diwajibkan`), negasi, definisi yang memuat kata Wajib, dan kewajiban milik regulator. v2 menangani pola tersebut tetapi tetap pendekatan aturan: tidak memahami konteks, rujukan silang, atau lampiran. Karena itu setiap draf diberi keyakinan 0,60 (di bawah `ai.confidence_floor` 0,70) dan wajib ditinjau manual (E8.3); AI_DRAFT tidak pernah masuk angka kepatuhan. Bila LLM dikonfigurasi, keluarannya melewati validasi skema dan grounding yang sama; jalankan ulang evaluasi untuk membandingkan.

## 2. Guardrail grounding

24 frasa pendukung karangan disisipkan pada pasal definisi; 24 ditolak (100.0%). Draf yang frasanya tidak muncul verbatim di teks pasal ditolak dengan `AI_GROUNDING_FAILED` dan tidak pernah disimpan sebagai kewajiban.

## 3. Deteksi perubahan (deterministik, tanpa AI)

6 pasangan versi dari 5 rantai perubahan; 8/8 perubahan terdeteksi (recall 100.0%), 0 perubahan semu.

Presisi flag material otomatis: 87.5% (FP 1). Perubahan redaksional ditandai material oleh ambang kemiripan; karena itu flag diff hanya indikasi dan materialitas diputuskan analis lalu dikonfirmasi Manajer (titik kendali #1).

- `ti_v1_v2`: diharapkan Pasal 60, Pasal 61; terlewat -; semu -
- `apu_v1_v2`: diharapkan Pasal 12; terlewat -; semu -
- `konsumen_v1_v2`: diharapkan Pasal 33, Pasal 50; terlewat -; semu -
- `siber_v1_v2`: diharapkan Pasal 7; terlewat -; semu -
- `tatakelola_v1_v2`: diharapkan Pasal 26; terlewat -; semu -
- `tatakelola_v2_v3`: diharapkan Pasal 5; terlewat -; semu -

## 4. Copilot advisori

- Pertanyaan bersumber: 30; pasal benar dalam 3 teratas: 96.7%.
- Jawaban yang disajikan: 29; seluruhnya bersitasi pasal tersimpan: 100.0%.
- Pertanyaan di luar korpus: 10; ditolak INSUFFICIENT_BASIS: 100.0%.
- Meleset: "Berapa hari tindak lanjut pengaduan konsumen?" → tidak ada (diharapkan ['POJK S-22/2023|Pasal 33', 'PBI S-03/2023|Pasal 14'])

Moda saat ini: retrieval-only (E15.1) — tanpa narasi generatif, setiap pernyataan adalah kutipan pasal, sehingga pernyataan faktual tanpa sitasi = 0 secara konstruksi.

## Keterbatasan evaluasi

- Dataset disusun tim yang sama yang membangun sistem; ada risiko optimisme. Mentor dianjurkan menambah kasus.
- Korpus sintetis berbahasa baku dan rapi, ditulis dengan pola 'X wajib ...' sehingga set standar cenderung optimistis bagi ekstraktor aturan; set adversarial dan held-out adalah sinyal yang lebih bermakna.
- PDF asli (OCR, penomoran tidak konsisten) akan lebih sulit daripada korpus sintetis.
- Evaluasi LLM belum dijalankan di lingkungan ini (tanpa API key); jalankan ulang setelah key tersedia.
