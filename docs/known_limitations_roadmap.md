# Known Limitations & Future Roadmap

Dinyatakan terbuka sesuai TRD §15.4 agar tidak ada penguji atau pengguna yang mengira cakupan MVP lebih luas dari kenyataan.

## Keterbatasan yang diketahui

### Korpus & ingestion
1. **Korpus demo sintetis** (30 dokumen, nomor berawalan `S-`). Korpus resmi 30–50 dokumen publik (A-01) belum dikurasi; unggah PDF asli lewat Korpus & pasal.
2. **Tanpa OCR**: PDF hasil pindai tidak tersegmentasi (A-04). Segmentasi hanya sampai **Pasal** (BAB → Pasal); Ayat/Huruf belum (CGR-06 mengizinkan granularitas Pasal).
3. **Tanpa pengambilan URL terjadwal / registri sumber W1** (onboarding sumber, permitted-use) — sumber dibuat otomatis saat dokumen didaftarkan.
4. **Koreksi segmentasi** hanya ubah teks pasal; pecah/gabung/ubah induk (TRD `PATCH /segmentation`) belum ada.
5. Diff tidak menangani penomoran ulang massal (E5.1) atau artefak OCR (E5.2); indikasi material berbasis ambang kemiripan menghasilkan positif palsu pada perubahan redaksional (ditangani oleh reviu manusia).

### AI
6. Ekstraktor tanpa LLM (`rule-based-v2`) berbasis pola: tidak memahami konteks, rujukan silang, atau lampiran; akurasi held-out 90% pada 10 kasus. Evaluasi LLM belum dijalankan (tidak ada API key di lingkungan pengembangan).
7. Klasifikasi semantik perubahan (AI_SUMMARISED) dan ringkasan dampak AI belum diimplementasikan; jenis semantik diisi analis.
8. Copilot **retrieval-only**: tidak menyusun narasi, tidak memahami sinonim yang tidak berbagi kata dasar ("tindak lanjut" vs "menindaklanjuti"); promosi jawaban menjadi draf rekaman (PROMOTED_TO_RECORD) belum ada.
9. Dataset evaluasi disusun oleh tim pengembang (risiko optimisme).

### Alur kerja
10. **Kampanye asesmen** (PLANNED → IN_PROGRESS → EVIDENCE_PENDING …) belum ada; asesmen dicatat per kontrol.
11. **Permintaan bukti** (FR-EVR-001, status REQUESTED) dan bukti `UNAVAILABLE` yang otomatis memunculkan temuan belum ada; bukti diunggah langsung. Masa berlaku bukti (EXPIRED otomatis) belum dijadwalkan.
12. Status pemetaan kontrol PROPOSED/CONFIRMED dan pewarisan hasil asesmen yang ditampilkan eksplisit di laporan (E9.1) belum ada; penanda `SOURCE_CHANGED` sudah ada.
13. Kewajiban: PENDING_LEGAL, VALIDATED/PENDING_EFFECTIVE (tanggal berlaku di masa depan), RETIRED, SUPERSEDED, sitasi pendukung lintas dokumen (E8.2) belum diimplementasikan.
14. **Satu akun = satu peran**; BLOCKED_SOD dan penugasan ulang administratif belum ada. Manajemen pengguna & peran (FR-GOV-002) belum ada di UI.
15. **Notifikasi & eskalasi** (email/in-app) belum ada; keterlambatan hanya tampil sebagai hitungan & penanda.
16. Laporan: ruang lingkup per unit/regulator belum dapat dipilih; ekspor via cetak/PDF browser (belum ada ekspor DOCX/PDF server-side).
17. Paginasi berbasis cursor (TRD §8.1) dan `Idempotency-Key` belum diterapkan; daftar memuat semua baris (memadai untuk volume demo).

### Platform & keamanan
18. Tanpa MFA/refresh token; JWT disimpan di sessionStorage.
19. Pemeriksaan berkas statis (bukan antivirus penuh); belum ada enkripsi berkas at-rest.
20. Metrik in-process (hilang saat restart, per proses); belum ada Prometheus/alerting.
21. Belum ada `docker-compose.prod.yml` dan pengujian beban (NFR kinerja belum diukur).

## Roadmap setelah capstone

| Prioritas | Butir | Alasan |
|---|---|---|
| 1 | Kurasi korpus resmi 30–50 dokumen + ground truth perubahan dari teks primer (SM-01, SM-04 nyata) | Klaim akurasi hanya dapat dipertahankan dengan data nyata |
| 1 | Integrasi LLM + evaluasi ulang (ekstraksi, klasifikasi perubahan) dengan dataset tambahan dari mentor | Menaikkan recall ekstraksi; tetap di balik gerbang grounding |
| 1 | Kampanye asesmen & permintaan bukti (FR-CAS, FR-EVR-001) | Melengkapi W10/W11 sesuai FRD |
| 2 | Notifikasi & eskalasi otomatis (tenggat, SLA reviu, risiko diterima lewat tinjau) | Mengurangi ketergantungan pada dasbor |
| 2 | Multi-peran per akun + BLOCKED_SOD; manajemen pengguna di UI | Realistis untuk institusi kecil (FRD §4.3) |
| 2 | OCR + segmentasi Ayat/Huruf; koreksi segmentasi struktural | Korpus nyata banyak PDF pindai |
| 3 | Ekspor laporan PDF/DOCX server-side bertanda tangan; scope laporan | Kebutuhan auditor |
| 3 | Produksi: compose prod, HTTPS, ClamAV, enkripsi at-rest, pemindaian dependensi, observabilitas terpusat | Kesiapan deployment |
| 3 | Promosi jawaban copilot menjadi draf rekaman (W15) | Sesuai FRD, setelah copilot generatif |
