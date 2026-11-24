# Dokumentasi API RCIP v1

_Dibangkitkan otomatis (`python -m app.api_docs`) dari kode. Spesifikasi lengkap: [openapi.json](openapi.json); Swagger interaktif saat aplikasi berjalan: http://localhost:8000/docs._

## Konvensi

- Base path `/api/v1`; semua endpoint kecuali `/auth/login` dan `/health` memerlukan `Authorization: Bearer <JWT>`.
- Respons sukses: `{success, message, data, timestamp}`.
- Error (RFC 7807 + field lama): `{success:false, error_code, message, type, title, status, code, detail, instance, correlation_id, offending}`.
- Kirim `X-Correlation-Id` (UUID) untuk menelusuri permintaan; server mengembalikannya di header respons dan mencatatnya di audit.
- Otorisasi ditegakkan di server per peran (matriks FRD §4.2); UI hanya cermin.

## Kode error penting

| Kode | Arti |
|---|---|
| `SOD_VIOLATION` | Checker sama dengan maker / penyunting terakhir / pemilik tindakan |
| `AI_DRAFT_BLOCKED` | Draf AI belum divalidasi tidak boleh dipetakan/ditautkan |
| `APPLICABILITY_NOT_APPROVED` | Ekstraksi butuh keputusan keberlakuan yang disetujui |
| `LOW_CONFIDENCE_REVIEW_REQUIRED` | Draf berkeyakinan rendah wajib dikonfirmasi telah ditinjau |
| `EVIDENCE_REQUIRED` / `CLOSURE_EVIDENCE_REQUIRED` | Butuh bukti berstatus ACCEPTED |
| `EVIDENCE_IMMUTABLE` / `REPORT_IMMUTABLE` / `VERSION_IMMUTABLE` | Objek terkunci setelah diterima/terbit |
| `DUE_DATE_EXCEEDS_WINDOW` | Tenggat melebihi jendela remediasi severity |
| `SCAN_FAILED` | Berkas unggahan ditolak pemeriksaan keamanan |
| `TOO_MANY_ATTEMPTS` | Pembatasan laju login |
| `VALIDATION_ERROR` | Body/parameter tidak valid; lihat `offending.field` |

## applicability

| Metode | Path | Keterangan |
|---|---|---|
| GET | `/api/v1/compliance/applicability` | List Decisions |
| POST | `/api/v1/compliance/applicability` | Create Decision |
| POST | `/api/v1/compliance/applicability/suggest` | Suggest |
| POST | `/api/v1/compliance/applicability/{did}/decision` | Titik kendali #2: penyetuju ≠ pembuat keputusan (juga CHECK di DB). |
| POST | `/api/v1/compliance/applicability/{did}/escalate` | Escalate |
| POST | `/api/v1/compliance/applicability/{did}/legal-answer` | Legal Answer |
| POST | `/api/v1/compliance/applicability/{did}/reopen` | REVIEW_REQUIRED → draf baru IN_ASSESSMENT. Keputusan lama tetap catatan resmi sampai draf baru disetujui. |
| POST | `/api/v1/compliance/applicability/{did}/submit` | Submit |
| GET | `/api/v1/compliance/profiles` | List Profiles |
| PUT | `/api/v1/compliance/profiles/{pid}` | E7.1: perubahan atribut profil → keputusan APPROVED yang bersandar padanya menjadi REVIEW_REQUIRED. |

## compliance

| Metode | Path | Keterangan |
|---|---|---|
| GET | `/api/v1/compliance/assessments` | List Assessments |
| POST | `/api/v1/compliance/assessments/{aid}/signoff` | Titik kendali #4: pemberi sign-off ≠ asesor dan ≠ pengaju. |
| POST | `/api/v1/compliance/assessments/{aid}/submit` | Submit Assessment |
| GET | `/api/v1/compliance/controls` | List Controls |
| POST | `/api/v1/compliance/controls` | Create Control |
| GET | `/api/v1/compliance/controls/{control_id}` | Control Detail |
| POST | `/api/v1/compliance/controls/{control_id}/assessments` | Assess |
| POST | `/api/v1/compliance/controls/{control_id}/evidence` | Upload Evidence |
| POST | `/api/v1/compliance/controls/{control_id}/owner` | Set Control Owner |
| GET | `/api/v1/compliance/legal-queue` | Antrian Peninjau Hukum: semua eskalasi yang menunggu posisi hukum, dikumpulkan di satu tempat |
| GET | `/api/v1/compliance/obligations` | List Obligations |
| POST | `/api/v1/compliance/obligations/extract` | Extract |
| POST | `/api/v1/compliance/obligations/{ob_id}/controls/{control_id}` | Map Control |
| POST | `/api/v1/compliance/obligations/{ob_id}/decision` | Decide |
| POST | `/api/v1/compliance/obligations/{ob_id}/escalate` | W8 (FRD Eksibit 33; TRD AOM.ESCALATED_TO_LEGAL): IN_VALIDATION → PENDING_LEGAL oleh Pejabat Kepatuhan, pertanyaan wajib. |
| POST | `/api/v1/compliance/obligations/{ob_id}/legal-answer` | W8 (FRD Eksibit 33; TRD AOM.LEGAL_POSITION_RECORDED): PENDING_LEGAL → IN_VALIDATION oleh Peninjau Hukum. |
| POST | `/api/v1/compliance/obligations/{ob_id}/reopen` | W8: REVIEW_REQUIRED → IN_VALIDATION. Opsional: arahkan sitasi ke ketentuan yang sama pada versi terbit terbaru. |
| POST | `/api/v1/compliance/obligations/{ob_id}/validate` | Validate |
| POST | `/api/v1/compliance/profiles` | Create Profile |
| GET | `/api/v1/compliance/risks` | List Risks |
| POST | `/api/v1/compliance/risks` | Create Risk |

## copilot

| Metode | Path | Keterangan |
|---|---|---|
| GET | `/api/v1/copilot/interactions` | FR-COP-004: log interaksi (pertanyaan, pasal yang diambil, model, templat). review=pending → antrean tinjauan. |
| POST | `/api/v1/copilot/interactions/{iid}/request-review` | Request Review |
| POST | `/api/v1/copilot/query` | Query |
| POST | `/api/v1/copilot/reviews/{rid}/verdict` | Verdict |

## corpus

| Metode | Path | Keterangan |
|---|---|---|
| POST | `/api/v1/citations/resolve` | KONTRAK ANTAR-MODUL (dibekukan Minggu 4). |
| GET | `/api/v1/corpus/catalog` | Catalog Search |
| POST | `/api/v1/corpus/changes` | Compute |
| GET | `/api/v1/corpus/documents` | List Documents |
| POST | `/api/v1/corpus/documents` | Create Document |
| DELETE | `/api/v1/corpus/documents/{doc_id}` | Dokumen hanya dapat dihapus bila belum pernah terbit (semua versinya draf) dan tidak dirujuk relasi. |
| GET | `/api/v1/corpus/documents/{doc_id}` | Get Document |
| PATCH | `/api/v1/corpus/documents/{doc_id}` | Perbaiki judul/jenis/penerbit kapan saja; nomor regulasi hanya selama belum pernah terbit |
| GET | `/api/v1/corpus/documents/{doc_id}/as-of` | Document As Of |
| POST | `/api/v1/corpus/documents/{doc_id}/versions` | Upload Version |
| GET | `/api/v1/corpus/facets` | Catalog Facets |
| PATCH | `/api/v1/corpus/provision-versions/{pv_id}` | Correct Provision |
| POST | `/api/v1/corpus/provision-versions/{pv_id}/confirm-text` | FR-RKM-004: analis menyatakan teks hasil OCR sudah sesuai PDF aslinya (tanpa mengubah teks). |
| GET | `/api/v1/corpus/search` | Search |
| DELETE | `/api/v1/corpus/versions/{version_id}` | Hanya versi DRAF yang dapat dihapus. Versi terbit imutabel (trigger DB) → gunakan 'tarik versi'. |
| PATCH | `/api/v1/corpus/versions/{version_id}` | Perbaiki tanggal berlaku versi yang MASIH DRAF. Versi terbit imutabel: tarik lalu unggah ulang. |
| GET | `/api/v1/corpus/versions/{version_id}/file` | Berkas asli (PDF/TXT) sebuah versi, untuk dibandingkan dengan teks pasal (mis. memeriksa hasil OCR). |
| GET | `/api/v1/corpus/versions/{version_id}/provisions` | List Provisions |
| POST | `/api/v1/corpus/versions/{version_id}/publish` | Publish |
| POST | `/api/v1/corpus/versions/{version_id}/withdraw` | Versi terbit ditarik (WITHDRAWN), bukan dihapus: tidak lagi dipakai pencarian/copilot/ekstraksi, |

## corpus-review

| Metode | Path | Keterangan |
|---|---|---|
| POST | `/api/v1/corpus/changes/{cid}/confirm-materiality` | Titik kendali #1: konfirmasi materialitas oleh Manajer Kepatuhan (≠ analis validator). |
| POST | `/api/v1/corpus/changes/{cid}/escalate` | Escalate Change |
| POST | `/api/v1/corpus/changes/{cid}/legal-answer` | Answer Change |
| POST | `/api/v1/corpus/changes/{cid}/validate` | Validate Change |
| GET | `/api/v1/corpus/changesets` | List Changesets |
| GET | `/api/v1/corpus/changesets/{cs_id}` | Get Changeset |
| GET | `/api/v1/corpus/documents/{doc_id}/labels` | List Labels |
| POST | `/api/v1/corpus/documents/{doc_id}/labels` | Add Label |
| POST | `/api/v1/corpus/documents/{doc_id}/labels/suggest` | Suggest |
| POST | `/api/v1/corpus/labels/{lid}/confirm` | Confirm Label |
| POST | `/api/v1/corpus/labels/{lid}/remove` | Remove Label |
| GET | `/api/v1/corpus/relationships` | List Relationships |
| POST | `/api/v1/corpus/relationships` | Propose Relationship |
| DELETE | `/api/v1/corpus/relationships/{rid}` | Relasi regulasi: D = Analis. Hanya usulan (PROPOSED); relasi CONFIRMED sudah mengubah status dokumen → tidak boleh hilang. |
| PATCH | `/api/v1/corpus/relationships/{rid}` | Relasi regulasi: hanya Analis yang menyunting, selama masih diajukan atau sedang direvisi. |
| POST | `/api/v1/corpus/relationships/{rid}/confirm` | Konfirmasi relasi mengubah status dokumen (mis. REVOKED) → persetujuan Manajer Kepatuhan (baris |
| POST | `/api/v1/corpus/relationships/{rid}/legal-note` | Peninjau Hukum memberi catatan hukum tanpa mengubah relasi; Manajer tetap boleh memutuskan. |
| POST | `/api/v1/corpus/relationships/{rid}/reject` | Manajer menolak usulan relasi (alasan wajib); status dokumen tidak berubah. Pengusul tidak boleh memutuskan. |
| POST | `/api/v1/corpus/relationships/{rid}/request-revision` | Peninjau Hukum minta revisi (catatan wajib): PROPOSED → REVISION_REQUESTED. Manajer menunggu revisi Analis. |
| POST | `/api/v1/corpus/relationships/{rid}/resubmit` | Analis merevisi lalu mengajukan ulang: REVISION_REQUESTED → PROPOSED (kembali menunggu Manajer). |

## corpus-sources

| Metode | Path | Keterangan |
|---|---|---|
| GET | `/api/v1/corpus/sources` | List Sources |
| POST | `/api/v1/corpus/sources` | Create Source |
| POST | `/api/v1/corpus/sources/{sid}/decision` | Decide Source |
| POST | `/api/v1/corpus/sources/{sid}/status` | Tangguhkan / aktifkan kembali / pensiunkan. RETIRED memerlukan hak D (hapus lunak) pada registri. |
| POST | `/api/v1/corpus/sources/{sid}/submit` | Ajukan ulang sumber yang dikembalikan (setelah diperbaiki). |

## executive

| Metode | Path | Keterangan |
|---|---|---|
| GET | `/api/v1/compliance/executive/posture` | Posture |

## findings

| Metode | Path | Keterangan |
|---|---|---|
| POST | `/api/v1/compliance/actions/{aid}/cancel` | Cancel Action |
| POST | `/api/v1/compliance/actions/{aid}/complete` | BR-EVR-005-2: tindakan tidak dapat selesai tanpa bukti penutupan berstatus ACCEPTED. |
| POST | `/api/v1/compliance/actions/{aid}/evidence` | Upload Action Evidence |
| POST | `/api/v1/compliance/actions/{aid}/extend` | BR-EVR-005-3: perpanjangan tidak menimpa tanggal asli; riwayat dipertahankan. |
| POST | `/api/v1/compliance/actions/{aid}/start` | Start Action |
| GET | `/api/v1/compliance/evidence/{eid}/download` | Download Evidence |
| POST | `/api/v1/compliance/evidence/{eid}/review` | FR-EVR-003: penerimaan/penolakan wajib rasional; bukti ACCEPTED menjadi imutabel. |
| GET | `/api/v1/compliance/findings` | List Findings |
| POST | `/api/v1/compliance/findings` | FR-EVR-004: temuan manual wajib tertaut ke kewajiban, memiliki severity dan pemilik. |
| GET | `/api/v1/compliance/findings/{fid}` | Finding Detail |
| POST | `/api/v1/compliance/findings/{fid}/accept-risk` | Accept Risk |
| POST | `/api/v1/compliance/findings/{fid}/close` | FR-EVR-006: validator ≠ pemilik tindakan mana pun, ≠ pemunculan temuan, ≠ pengaju penutupan. |
| POST | `/api/v1/compliance/findings/{fid}/remediation` | Create Action |
| POST | `/api/v1/compliance/findings/{fid}/reopen` | Reopen |
| POST | `/api/v1/compliance/findings/{fid}/submit-closure` | Submit Closure |
| POST | `/api/v1/compliance/gaps/scan` | Scan |

## lain

| Metode | Path | Keterangan |
|---|---|---|
| GET | `/health` | Health |

## owner

| Metode | Path | Keterangan |
|---|---|---|
| POST | `/api/v1/compliance/owner/findings/{fid}/plan` | Save Plan |
| GET | `/api/v1/compliance/owner/workspace` | Workspace |

## platform

| Metode | Path | Keterangan |
|---|---|---|
| GET | `/api/v1/admin/users` | Admin List Users |
| POST | `/api/v1/admin/users` | Admin Create User |
| DELETE | `/api/v1/admin/users/{uid}` | D (soft): menonaktifkan akun. Baris tetap ada agar audit_event/approval yang menunjuknya tetap sah. |
| PATCH | `/api/v1/admin/users/{uid}` | Admin Update User |
| GET | `/api/v1/audit` | Audit Log |
| GET | `/api/v1/audit/export` | Audit Export |
| POST | `/api/v1/auth/login` | Pembatasan laju: percobaan gagal per (akun, IP) per 60 detik (auth.max_failed_logins_per_minute). |
| GET | `/api/v1/auth/me` | Me |
| GET | `/api/v1/config` | List Config |
| PUT | `/api/v1/config/{key}` | Update Config |
| GET | `/api/v1/metrics` | Metrics |
| GET | `/api/v1/users` | Direktori ringkas (id, username, peran) untuk pemilih pemilik/penanggung jawab di formulir. |

## reporting

| Metode | Path | Keterangan |
|---|---|---|
| GET | `/api/v1/compliance/dashboard` | Dashboard |
| GET | `/api/v1/compliance/reports` | List Reports |
| POST | `/api/v1/compliance/reports` | FR-DBR-006: Pejabat Kepatuhan membangkitkan draf; gagal bila ada angka/sitasi yang tak dapat ditelusuri. |
| GET | `/api/v1/compliance/reports/{rid}` | Get Report |
| POST | `/api/v1/compliance/reports/{rid}/decision` | DRR-10: penerbit harus berbeda dari pembangkit laporan. |
| POST | `/api/v1/compliance/reports/{rid}/regenerate` | Regenerate Report |
| POST | `/api/v1/compliance/reports/{rid}/submit` | Submit Report |
| POST | `/api/v1/compliance/reports/{rid}/withdraw` | Withdraw Report |
| GET | `/api/v1/compliance/trace/obligations/{ob_id}` | Rantai: pasal → versi → dokumen → kewajiban → persetujuan → kontrol → asesmen → bukti → temuan → remediasi. |
