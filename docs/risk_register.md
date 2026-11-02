# Risk Register RCIP

Skala: Kemungkinan (K) dan Dampak (D) 1–5; Skor = K × D. Status per akhir pengembangan MVP. Pemilik mengacu peran tim capstone.

| ID | Risiko | Kategori | K | D | Skor | Mitigasi yang sudah diterapkan | Risiko residual / tindak lanjut | Pemilik | Status |
|---|---|---|---|---|---|---|---|---|---|
| R-01 | Draf AI keliru (halusinasi, salah tenggat) diperlakukan sebagai kewajiban resmi | AI | 4 | 5 | 20 | Status AI_DRAFT diblokir di DB dari pemetaan & angka; grounding verbatim; validasi skema; keyakinan rendah wajib ditinjau; maker-checker titik 3 | Ekstraktor aturan masih salah pada definisi tertentu (held-out 90%); evaluasi ulang saat LLM dipakai | Group B AI | Termitigasi |
| R-02 | Satu orang membuat dan menyetujui keputusannya sendiri | Tata kelola | 3 | 5 | 15 | SoD di aplikasi + CHECK DB pada 6 titik; uji negatif ≥ 12 percobaan (SM-13) | Satu akun multi-peran belum didukung (BLOCKED_SOD belum ada) | Arsitek | Termitigasi |
| R-03 | Rekaman diubah/dihapus setelah diputuskan sehingga audit tidak dapat dipercaya | Integritas | 2 | 5 | 10 | Trigger append-only (audit, approval), imutabel (versi, pasal, bukti ACCEPTED, laporan ISSUED); FK RESTRICT | Superuser DB tetap dapat menonaktifkan trigger → batasi akses DB di produksi | Arsitek | Termitigasi |
| R-04 | Laporan memuat angka yang tidak dapat ditelusuri | Pelaporan | 2 | 4 | 8 | Pemeriksaan ketertelusuran memblokir pembuatan/penerbitan; laporan menyimpan `referenced_object_versions`; drill dasbor | — | Group B | Termitigasi |
| R-05 | Perubahan regulasi terlewat atau salah dinilai materialitasnya | Regulasi | 3 | 4 | 12 | Diff deterministik (recall 100% di ground truth); reviu analis + konfirmasi Manajer; SLA reviu & hitungan lewat SLA di dasbor | Penomoran ulang massal (E5.1) & artefak OCR (E5.2) belum ditangani | Group A | Sebagian |
| R-06 | Korpus dianggap lengkap padahal terkurasi kecil | Produk | 3 | 4 | 12 | Penafian berversi dengan jumlah dokumen & sumber di setiap laporan dan copilot; peringatan kualitas korpus | Korpus demo sintetis; korpus resmi 30–50 dokumen perlu dikurasi | Group A | Termitigasi |
| R-07 | Copilot memberi jawaban tanpa dasar atau dianggap nasihat hukum | AI | 3 | 4 | 12 | Retrieval-only dengan sitasi; ambang cakupan berbobot IDF → INSUFFICIENT_BASIS; deteksi permintaan nasihat hukum; penolakan 100% di set uji | Set uji disusun tim sendiri; tambah pertanyaan dari mentor | Joint | Termitigasi |
| R-08 | Akses tidak sah ke bukti / data | Keamanan | 2 | 4 | 8 | JWT + RBAC server; lingkup pemilik (R-05 FRD); unduhan bukti diaudit; rate limit login; header keamanan | Belum ada MFA, refresh token, enkripsi berkas at-rest | Arsitek | Sebagian |
| R-09 | Unggahan berkas berbahaya | Keamanan | 2 | 3 | 6 | Pemeriksaan ekstensi, tanda tangan executable, EICAR; batas ukuran | Bukan antivirus penuh — pasang ClamAV di produksi | Arsitek | Sebagian |
| R-10 | Data pribadi/klien masuk ke sistem atau ke LLM | Privasi | 1 | 5 | 5 | Seluruh data sintetis; hanya teks peraturan publik dikirim ke LLM; penafian data sintetis di UI & laporan | Prosedur jika data nyata dipakai: lihat checklist privasi | Product Owner | Termitigasi |
| R-11 | Kegagalan integrasi Group A ↔ B | Proyek | 2 | 4 | 8 | Kontrak `citations/resolve` + kosakata tertutup di `app/shared`; satu repo, satu skema; test end-to-end | — | Arsitek | Tertutup |
| R-12 | Data warisan sebelum tahap 2/3 tidak sesuai aturan baru | Migrasi | 3 | 2 | 6 | Migrasi additive + backfill; validator menandai asesmen warisan | Pengguna perlu mengulang asesmen warisan | Group B | Sebagian |
| R-13 | LLM tidak tersedia / biaya | Operasional | 3 | 2 | 6 | Moda tanpa LLM terdokumentasi (rule-based-v2, copilot retrieval-only) | — | Group B AI | Termitigasi |
| R-14 | Ketergantungan pada satu orang yang memahami sistem | Proyek | 3 | 3 | 9 | Dokumentasi teknis, data dictionary & API dibangkitkan dari kode, handover, CI | Sesi walkthrough serah terima | Product Owner | Sebagian |
| R-15 | Demo gagal karena lingkungan | Proyek | 2 | 4 | 8 | Dataset demo reproducible (`seed.generate --seed 42`); skenario demo tertulis; backup DB | Gladi bersih di mesin demo | Product Owner | Sebagian |
