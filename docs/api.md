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
| GET | `/api/v1/compliance/obligations` | List Obligations |
| POST | `/api/v1/compliance/obligations/extract` | Extract |
| POST | `/api/v1/compliance/obligations/{ob_id}/controls/{control_id}` | Map Control |
| POST | `/api/v1/compliance/obligations/{ob_id}/decision` | Decide |
| POST | `/api/v1/compliance/obligations/{ob_id}/reopen` | W8: REVIEW_REQUIRED → IN_VALIDATION. Opsional: arahkan sitasi ke ketentuan yang sama pada versi terbit terbaru. |
| POST | `/api/v1/compliance/obligations/{ob_id}/validate` | Validate |
| POST | `/api/v1/compliance/profiles` | Create Profile |
| GET | `/api/v1/compliance/risks` | List Risks |
| POST | `/api/v1/compliance/risks` | Create Risk |

## copilot

| Metode | Path | Keterangan |
|---|---|---|
| POST | `/api/v1/copilot/query` | Query |

## corpus

| Metode | Path | Keterangan |
|---|---|---|
| POST | `/api/v1/citations/resolve` | KONTRAK ANTAR-MODUL (dibekukan Minggu 4). |
| POST | `/api/v1/corpus/changes` | Compute |
| GET | `/api/v1/corpus/documents` | List Documents |
| POST | `/api/v1/corpus/documents` | Create Document |
| POST | `/api/v1/corpus/documents/{doc_id}/versions` | Upload Version |
| PATCH | `/api/v1/corpus/provision-versions/{pv_id}` | Correct Provision |
| GET | `/api/v1/corpus/search` | Search |
| GET | `/api/v1/corpus/versions/{version_id}/provisions` | List Provisions |
| POST | `/api/v1/corpus/versions/{version_id}/publish` | Publish |

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
| POST | `/api/v1/corpus/relationships/{rid}/confirm` | Confirm Relationship |

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

## platform

| Metode | Path | Keterangan |
|---|---|---|
| GET | `/api/v1/audit` | Audit Log |
| GET | `/api/v1/audit/export` | Audit Export |
| POST | `/api/v1/auth/login` | Pembatasan laju: percobaan gagal per (akun, IP) per 60 detik (auth.max_failed_logins_per_minute). |
| GET | `/api/v1/auth/me` | Me |
| GET | `/api/v1/config` | List Config |
| PUT | `/api/v1/config/{key}` | Update Config |
| GET | `/api/v1/metrics` | Metrics |
| GET | `/api/v1/users` | List Users |

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
