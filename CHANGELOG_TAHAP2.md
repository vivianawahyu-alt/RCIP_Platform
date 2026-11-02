# Tahap 2 — Rantai kepatuhan lengkap (gerbang Minggu 10, TRD §14.7)

Acuan: FRD RCIP-FRD-001 v0.9 (§4.2, §5.9–5.11, §6.6, §13.6, §14) dan TRD RCIP-TRD-001 v0.9 (§8.3, §14.4).

## Backend
### Migrasi `002_findings_assessment_reports` (aman untuk DB berisi data)
- `finding`: severity, sumber (ASSESSMENT/COVERAGE_GAP/EVIDENCE_GAP/MANUAL), pemilik, pencatat, target penutupan,
  catatan penutupan, penerimaan risiko, `reopened_count`. CHECK status W12 dan SoD `closed_by ≠ raised_by`.
- `remediation_action`: hasil diharapkan, `original_due_date` + `extension_history` (BR-EVR-005-3), mulai/selesai/batal.
- `evidence`: status SUBMITTED/ACCEPTED/REJECTED/…, rasional tinjauan, bukti penutupan tindakan.
  **Trigger**: bukti ACCEPTED tidak dapat diubah/dihapus (`EVIDENCE_IMMUTABLE`).
- `assessment`: kesimpulan desain & operasional + rasional, CONCLUDED → PENDING_SIGNOFF → SIGNED_OFF.
  CHECK: operasional EFFECTIVE dilarang bila desain INEFFECTIVE; penandatangan ≠ asesor.
- `compliance_report`: DRAFT → PENDING_APPROVAL → ISSUED → SUPERSEDED/WITHDRAWN, penerbit ≠ pembangkit.
  **Trigger**: laporan terbit imutabel (`REPORT_IMMUTABLE`).

### Endpoint baru (`/api/v1/compliance/...`)
| Alur | Endpoint |
|---|---|
| Temuan | `GET /findings?severity&state&owner_id&overdue`, `GET /findings/{id}` (tindakan, bukti, persetujuan, timeline audit), `POST /findings` |
| Remediasi | `POST /findings/{id}/remediation`, `POST /actions/{id}/start · /extend · /evidence · /complete · /cancel` |
| Bukti | `POST /evidence/{id}/review`, `GET /evidence/{id}/download` (diaudit `EVIDENCE_DOWNLOADED`) |
| Penutupan (titik 5) | `POST /findings/{id}/submit-closure · /close · /accept-risk · /reopen` |
| Asesmen (titik 4) | `GET /assessments`, `POST /assessments/{id}/submit · /signoff` |
| Kontrol | `POST /controls/{id}/owner`; detail kontrol memuat bukti & riwayat asesmen |
| Laporan (titik 6) | `GET /reports/{id}`, `POST /reports/{id}/regenerate · /submit · /decision · /withdraw` |
| Audit | `GET /audit?object_type&object_id&action&actor`, `GET /audit/export` (CSV) |

### Aturan yang ditegakkan server
- Jendela remediasi per severity: CRITICAL 30, HIGH 60 (TRD), MEDIUM 90, LOW 180 hari (asumsi tim; mohon dikonfirmasi mentor).
- Tindakan tidak bisa selesai tanpa bukti penutupan ACCEPTED; penutupan wajib rasional; penolakan wajib tanggal baru.
- Validator penutupan ≠ pemilik tindakan mana pun ≠ pencatat temuan (`403 SOD_VIOLATION`).
- Asesmen memerlukan bukti ACCEPTED; hasil PARTIALLY_EFFECTIVE/INEFFECTIVE memunculkan tepat satu temuan otomatis.
- Skor dasbor kini hanya menghitung asesmen SIGNED_OFF (FRD W10). Asesmen lama berstatus CONCLUDED: ajukan & sign-off agar terhitung.
- Pemilik Bisnis/Kontrol hanya melihat temuan/tindakan/bukti miliknya (R-05).
- Jejak audit: Auditor/Admin/Manajer/Legal melihat semua; Analis/Pejabat hanya event miliknya; Eksekutif/Owner tidak.
- Penafian §13.6 berversi (`2026-10-v1`) dengan nilai korpus terisi otomatis di laporan dan copilot.
- Perbaikan: persetujuan kewajiban kini tercatat sebagai titik kendali **3** (sebelumnya keliru 2).
- Penyimpanan: bila MinIO tidak berjalan (di-comment di docker-compose), berkas disimpan di folder `storage/`.

### Laporan (DRR-07)
Isi: ruang lingkup, dasar korpus, peraturan berlaku + keputusan keberlakuan, inventaris kewajiban dengan kutipan
pasal verbatim, cakupan kontrol (penuh/sebagian/tanpa), hasil asesmen, temuan & remediasi, perubahan regulasi,
butir tertunda, `referenced_object_versions`, dan penafian.

## Frontend
- Ditulis ulang per halaman (`web/src/pages/*`), tampilan portal hukum (struktur ala Hukumonline, identitas visual sendiri).
- Register temuan: ringkasan per severity, tab status, panel detail dengan alur status, kartu tindakan, bukti,
  keputusan maker-checker, dan timeline audit.
- Kontrol: pilih pemilik dari daftar (bukan UUID), tinjau bukti, form asesmen desain/operasional.
- Laporan: dokumen 10 bagian siap cetak/PDF; Jejak audit dengan filter & ekspor CSV; pencarian berkategori.
- Ditambahkan `web/src/vite-env.d.ts` (TypeScript terbaru menolak import CSS tanpa deklarasi ini).
- Komponen lama `web/src/components/*` digantikan `ui.tsx` dan halaman baru.

## Pengujian
`pytest`: 20 lulus (12 lama, sebagian disesuaikan dengan aturan baru, + 8 baru), dijalankan pada tiga DB:
DB baru, backup DB Anda yang dimigrasi, dan DB berisi data lama yang di-upgrade 001→002.
Alur UI ekstraksi → laporan terbit diuji otomatis dengan Playwright di browser.

## Belum dikerjakan (tahap berikutnya)
- Titik kendali #1 konfirmasi materialitas perubahan dan #2 keputusan keberlakuan maker-checker (W5, W7).
- Permintaan bukti (FR-EVR-001), kampanye asesmen, status pemetaan PROPOSED/CONFIRMED, BLOCKED_SOD.
- Registri sumber (W1), relasi/silsilah dokumen (W4), promosi keluaran copilot, konfigurasi runtime (FR-GOV-007).
- Notifikasi/eskalasi otomatis keterlambatan (saat ini tampil sebagai hitungan & penanda di UI).
