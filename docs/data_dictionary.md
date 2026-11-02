# Data Dictionary RCIP

_Dibangkitkan otomatis oleh `python -m seed.data_dictionary` dari skema database (migrasi 001–003). Jangan disunting manual; jalankan ulang setelah migrasi baru._

Konvensi: semua ID UUID v4; waktu `timestamptz` (UTC); tanggal hukum `date`. Kolom berlabel **PK**/**FK** menunjukkan kunci; FK memakai `ON DELETE RESTRICT` sehingga rantai tidak dapat terputus.

| Tabel | Deskripsi | Baris (DB saat dibangkitkan) |
|---|---|---|
| `compliance.applicability_decision` | Keputusan keberlakuan W7 (titik kendali #2) dengan sitasi & snapshot profil. | 21 |
| `compliance.assessment` | Kesimpulan efektivitas desain & operasional; sign-off (titik kendali #4). | 22 |
| `compliance.compliance_report` | Laporan W14; ISSUED imutabel (trigger), penerbit ≠ pembangkit (titik kendali #6). | 2 |
| `compliance.control` | Kontrol mitigasi beserta pemiliknya. | 36 |
| `compliance.evidence` | Bukti kontrol / bukti penutupan tindakan; ACCEPTED imutabel (trigger). | 62 |
| `compliance.finding` | Temuan W12 dengan severity, pemilik, target, penutupan (titik kendali #5). | 15 |
| `compliance.obligation` | Kewajiban terstruktur; AI_DRAFT tidak pernah dihitung/dipetakan (ditegakkan DB). | 48 |
| `compliance.obligation_control_map` | Pemetaan banyak-ke-banyak kewajiban ↔ kontrol (trigger memblokir draf AI). | 36 |
| `compliance.organisation_profile` | Profil organisasi sintetis berversi; dasar keputusan keberlakuan. | 1 |
| `compliance.remediation_action` | Tindakan remediasi dengan tenggat asli + riwayat perpanjangan. | 12 |
| `compliance.risk` | Risiko ketidakpatuhan per kewajiban. | 36 |
| `corpus.change` | Perubahan per ketentuan + status reviu W5 (titik kendali #1) dan permukaan dampak. | 8 |
| `corpus.change_set` | Perbandingan dua versi dokumen. | 6 |
| `corpus.document` | Identitas peraturan (nomor kanonik unik) dan status keberlakuannya. | 30 |
| `corpus.document_version` | Versi imutabel sebuah dokumen setelah PUBLISHED (trigger). | 36 |
| `corpus.provision` | Identitas ketentuan (Pasal) lintas versi. | 83 |
| `corpus.provision_version` | Teks ketentuan pada versi tertentu; target semua sitasi; imutabel bila versinya terbit. | 110 |
| `corpus.regulatory_source` | Otoritas/portal asal dokumen (OJK, BI, JDIH). | 3 |
| `corpus.relationship` | Silsilah antardokumen (mengubah/mencabut/merujuk) dengan sitasi penetap. | 1 |
| `corpus.taxonomy_label` | Label taksonomi terkendali (tema, populasi) — saran aturan dikonfirmasi manusia. | 39 |
| `platform.ai_call_log` | Setiap panggilan AI: templat+versi, model, prompt, respons mentah, validasi skema, grounding. | 55 |
| `platform.app_user` | Akun pengguna dan perannya (8 persona + tambahan sintetis). Password PBKDF2. | 13 |
| `platform.approval` | Keputusan maker-checker pada 6 titik kendali; append-only; snapshot status objek. | 94 |
| `platform.audit_event` | Jejak audit append-only (trigger menolak UPDATE/DELETE). Setiap transisi status. | 114 |
| `platform.config` | Parameter runtime teraudit (FR-GOV-007) dengan batas min/maks. | 9 |
| `platform.outbox` | Event domain (transactional outbox) untuk pemrosesan asinkron oleh worker. | 0 |

## `compliance.applicability_decision`

Keputusan keberlakuan W7 (titik kendali #2) dengan sitasi & snapshot profil.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `target_version_id` | uuid | tidak | FK → `corpus.document_version` |  |
| `profile_id` | uuid | tidak | FK → `compliance.organisation_profile` |  |
| `decision_value` | text | tidak |  |  |
| `reason_text` | text | tidak |  |  |
| `relied_upon_attributes` | jsonb | tidak |  | Snapshot atribut profil yang dijadikan dasar keputusan. Default: `'{}'::jsonb`. |
| `maker_id` | uuid | tidak | FK → `platform.app_user` |  |
| `approver_id` | uuid | ya | FK → `platform.app_user` |  |
| `created_at` | timestamp with time zone | tidak |  | Default: `now()`. |
| `state` | text | tidak |  | Status siklus hidup (kosakata tertutup, lihat CHECK). Default: `'IN_ASSESSMENT'::text`. |
| `cited_provision_version_ids` | jsonb | tidak |  | Default: `'[]'::jsonb`. |
| `scope_provision_version_ids` | jsonb | tidak |  | Default: `'[]'::jsonb`. |
| `legal_question` | text | ya |  |  |
| `legal_answer` | text | ya |  |  |
| `legal_reviewer_id` | uuid | ya | FK → `platform.app_user` |  |
| `submitted_at` | timestamp with time zone | ya |  |  |
| `decided_at` | timestamp with time zone | ya |  |  |
| `return_reason` | text | ya |  |  |
| `review_owner_id` | uuid | ya | FK → `platform.app_user` |  |
| `review_target_date` | date | ya |  |  |
| `suggested_value` | text | ya |  |  |
| `superseded_by` | uuid | ya | FK → `compliance.applicability_decision` |  |

Aturan (CHECK):
- `ck_applicability_sod`: `CHECK (((approver_id IS NULL) OR (approver_id <> maker_id)))`
- `ck_applicability_state`: `CHECK ((state = ANY (ARRAY['IN_ASSESSMENT'::text, 'PENDING_LEGAL'::text, 'PENDING_APPROVAL'::text, 'APPROVED'::text, 'REJECTED_TO_MAKER'::text, 'REVIEW_REQUIRED'::text, 'SUPERSEDED'::text])))`

## `compliance.assessment`

Kesimpulan efektivitas desain & operasional; sign-off (titik kendali #4).

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `control_id` | uuid | tidak | FK → `compliance.control` |  |
| `result` | text | tidak |  |  |
| `notes` | text | ya |  |  |
| `assessed_by` | uuid | ya | FK → `platform.app_user` |  |
| `assessed_at` | timestamp with time zone | tidak |  | Default: `now()`. |
| `design_result` | text | ya |  |  |
| `operating_result` | text | ya |  |  |
| `design_rationale` | text | ya |  |  |
| `operating_rationale` | text | ya |  |  |
| `state` | text | tidak |  | Status siklus hidup (kosakata tertutup, lihat CHECK). Default: `'CONCLUDED'::text`. |
| `submitted_by` | uuid | ya | FK → `platform.app_user` |  |
| `submitted_at` | timestamp with time zone | ya |  |  |
| `signed_off_by` | uuid | ya | FK → `platform.app_user` |  |
| `signed_off_at` | timestamp with time zone | ya |  |  |
| `return_reason` | text | ya |  |  |

Aturan (CHECK):
- `ck_assessment_design_operating`: `CHECK ((NOT ((design_result = 'INEFFECTIVE'::text) AND (operating_result = 'EFFECTIVE'::text))))`
- `ck_assessment_signoff_sod`: `CHECK (((signed_off_by IS NULL) OR (signed_off_by <> assessed_by)))`
- `ck_assessment_state`: `CHECK ((state = ANY (ARRAY['CONCLUDED'::text, 'PENDING_SIGNOFF'::text, 'SIGNED_OFF'::text])))`

## `compliance.compliance_report`

Laporan W14; ISSUED imutabel (trigger), penerbit ≠ pembangkit (titik kendali #6).

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `title` | text | tidak |  |  |
| `payload` | jsonb | tidak |  | Isi laporan yang dibekukan saat terbit (DRR-07). |
| `state` | text | tidak |  | Status siklus hidup (kosakata tertutup, lihat CHECK). Default: `'DRAFT'::text`. |
| `created_by` | uuid | ya | FK → `platform.app_user` |  |
| `created_at` | timestamp with time zone | tidak |  | Default: `now()`. |
| `generated_by` | uuid | ya | FK → `platform.app_user` |  |
| `submitted_at` | timestamp with time zone | ya |  |  |
| `issued_by` | uuid | ya | FK → `platform.app_user` |  |
| `issued_at` | timestamp with time zone | ya |  |  |
| `return_reason` | text | ya |  |  |
| `withdrawn_reason` | text | ya |  |  |
| `withdrawn_at` | timestamp with time zone | ya |  |  |
| `superseded_by` | uuid | ya | FK → `compliance.compliance_report` |  |
| `disclaimer_version` | text | ya |  |  |

Aturan (CHECK):
- `ck_report_issue_sod`: `CHECK (((issued_by IS NULL) OR (generated_by IS NULL) OR (issued_by <> generated_by) OR (disclaimer_version = 'legacy'::text)))`
- `ck_report_state`: `CHECK ((state = ANY (ARRAY['DRAFT'::text, 'PENDING_APPROVAL'::text, 'ISSUED'::text, 'SUPERSEDED'::text, 'WITHDRAWN'::text])))`

Trigger:
- `trg_report_immutable` (UPDATE/DELETE)

## `compliance.control`

Kontrol mitigasi beserta pemiliknya.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `risk_id` | uuid | ya | FK → `compliance.risk` |  |
| `title` | text | tidak |  |  |
| `owner_id` | uuid | ya | FK → `platform.app_user` |  |
| `source_changed` | boolean | tidak |  | Default: `false`. |

## `compliance.evidence`

Bukti kontrol / bukti penutupan tindakan; ACCEPTED imutabel (trigger).

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `control_id` | uuid | ya | FK → `compliance.control` |  |
| `filename` | text | tidak |  |  |
| `object_key` | text | tidak |  |  |
| `sha256` | character varying | tidak |  | Checksum isi berkas/teks. |
| `uploaded_by` | uuid | ya | FK → `platform.app_user` |  |
| `uploaded_at` | timestamp with time zone | tidak |  | Default: `now()`. |
| `remediation_action_id` | uuid | ya | FK → `compliance.remediation_action` |  |
| `description` | text | ya |  |  |
| `size_bytes` | bigint | ya |  |  |
| `state` | text | tidak |  | Status siklus hidup (kosakata tertutup, lihat CHECK). Default: `'SUBMITTED'::text`. |
| `reviewed_by` | uuid | ya | FK → `platform.app_user` |  |
| `reviewed_at` | timestamp with time zone | ya |  |  |
| `review_rationale` | text | ya |  |  |

Aturan (CHECK):
- `ck_evidence_state`: `CHECK ((state = ANY (ARRAY['SUBMITTED'::text, 'ACCEPTED'::text, 'REJECTED'::text, 'SUPERSEDED'::text, 'EXPIRED'::text])))`
- `ck_evidence_target`: `CHECK (((control_id IS NOT NULL) OR (remediation_action_id IS NOT NULL)))`

Trigger:
- `trg_evidence_immutable` (DELETE/UPDATE)

## `compliance.finding`

Temuan W12 dengan severity, pemilik, target, penutupan (titik kendali #5).

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `obligation_id` | uuid | tidak | FK → `compliance.obligation` |  |
| `kind` | text | tidak |  |  |
| `description` | text | tidak |  |  |
| `state` | text | tidak |  | Status siklus hidup (kosakata tertutup, lihat CHECK). Default: `'OPEN'::text`. |
| `created_at` | timestamp with time zone | tidak |  | Default: `now()`. |
| `title` | text | ya |  |  |
| `severity` | text | tidak |  | Default: `'MEDIUM'::text`. |
| `source_type` | text | tidak |  | Default: `'MANUAL'::text`. |
| `control_id` | uuid | ya | FK → `compliance.control` |  |
| `assessment_id` | uuid | ya | FK → `compliance.assessment` |  |
| `owner_id` | uuid | ya | FK → `platform.app_user` |  |
| `raised_by` | uuid | ya | FK → `platform.app_user` |  |
| `target_closure_date` | date | ya |  |  |
| `closure_submitted_by` | uuid | ya | FK → `platform.app_user` |  |
| `closure_submitted_at` | timestamp with time zone | ya |  |  |
| `closed_by` | uuid | ya | FK → `platform.app_user` |  |
| `closed_at` | timestamp with time zone | ya |  |  |
| `closure_rationale` | text | ya |  |  |
| `risk_acceptance_rationale` | text | ya |  |  |
| `risk_accepted_by` | uuid | ya | FK → `platform.app_user` |  |
| `risk_review_date` | date | ya |  |  |
| `reopened_count` | integer | tidak |  | Default: `0`. |
| `updated_at` | timestamp with time zone | tidak |  | Default: `now()`. |

Aturan (CHECK):
- `ck_finding_closure_sod`: `CHECK (((closed_by IS NULL) OR (raised_by IS NULL) OR (closed_by <> raised_by)))`
- `ck_finding_severity`: `CHECK ((severity = ANY (ARRAY['CRITICAL'::text, 'HIGH'::text, 'MEDIUM'::text, 'LOW'::text])))`
- `ck_finding_state`: `CHECK ((state = ANY (ARRAY['OPEN'::text, 'ACTION_PLANNED'::text, 'IN_REMEDIATION'::text, 'PENDING_CLOSURE_VALIDATION'::text, 'CLOSED'::text, 'RISK_ACCEPTED'::text, 'REVIEW_REQUIRED'::text])))`

## `compliance.obligation`

Kewajiban terstruktur; AI_DRAFT tidak pernah dihitung/dipetakan (ditegakkan DB).

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `applicability_decision_id` | uuid | tidak | FK → `compliance.applicability_decision` |  |
| `primary_citation_id` | uuid | tidak | FK → `corpus.provision_version` | Sitasi wajib ke provision_version — inti ketertelusuran. |
| `original_text` | text | tidak |  |  |
| `plain_language_summary` | text | ya |  |  |
| `required_actions` | jsonb | tidak |  | Default: `'[]'::jsonb`. |
| `frequency` | text | ya |  |  |
| `deadline_expression` | text | ya |  |  |
| `required_evidence` | text | ya |  |  |
| `confidence` | numeric | ya |  |  |
| `derived_from_ai` | boolean | tidak |  | True bila dibuat dari draf AI. Default: `true`. |
| `owner_id` | uuid | ya | FK → `platform.app_user` |  |
| `validator_id` | uuid | ya | FK → `platform.app_user` |  |
| `approver_id` | uuid | ya | FK → `platform.app_user` |  |
| `state` | text | tidak |  | Status siklus hidup (kosakata tertutup, lihat CHECK). Default: `'AI_DRAFT'::text`. |
| `created_at` | timestamp with time zone | tidak |  | Default: `now()`. |
| `supporting_phrases` | jsonb | tidak |  | Kutipan verbatim dari teks pasal yang mendasari draf AI (explainability). Default: `'[]'::jsonb`. |
| `ai_call_id` | uuid | ya | FK → `platform.ai_call_log` |  |
| `model_id` | text | ya |  |  |
| `low_confidence` | boolean | tidak |  | Keyakinan AI di bawah ai.confidence_floor; wajib konfirmasi tinjauan manual. Default: `false`. |
| `low_confidence_reviewed_by` | uuid | ya | FK → `platform.app_user` |  |
| `reopen_reason` | text | ya |  |  |

Aturan (CHECK):
- `ck_active_needs_owner`: `CHECK (((state <> ALL (ARRAY['ACTIVE'::text, 'PENDING_APPROVAL'::text])) OR (owner_id IS NOT NULL)))`
- `ck_obligation_sod`: `CHECK (((approver_id IS NULL) OR (approver_id <> validator_id)))`

## `compliance.obligation_control_map`

Pemetaan banyak-ke-banyak kewajiban ↔ kontrol (trigger memblokir draf AI).

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `obligation_id` | uuid | tidak | PK |  |
| `control_id` | uuid | tidak | PK |  |

Trigger:
- `trg_block_ai_draft` (INSERT)

## `compliance.organisation_profile`

Profil organisasi sintetis berversi; dasar keputusan keberlakuan.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `organisation_name` | text | tidak |  |  |
| `entity_type` | text | tidak |  |  |
| `licenses` | jsonb | tidak |  | Default: `'[]'::jsonb`. |
| `business_lines` | jsonb | tidak |  | Default: `'[]'::jsonb`. |
| `version` | integer | tidak |  | Default: `1`. |

## `compliance.remediation_action`

Tindakan remediasi dengan tenggat asli + riwayat perpanjangan.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `finding_id` | uuid | tidak | FK → `compliance.finding` |  |
| `description` | text | tidak |  |  |
| `due_date` | date | tidak |  |  |
| `owner_id` | uuid | ya | FK → `platform.app_user` |  |
| `state` | text | tidak |  | Status siklus hidup (kosakata tertutup, lihat CHECK). Default: `'OPEN'::text`. |
| `expected_outcome` | text | ya |  |  |
| `original_due_date` | date | tidak |  |  |
| `extension_history` | jsonb | tidak |  | Riwayat perpanjangan tenggat (tanggal asli dipertahankan). Default: `'[]'::jsonb`. |
| `created_by` | uuid | ya | FK → `platform.app_user` |  |
| `created_at` | timestamp with time zone | tidak |  | Default: `now()`. |
| `started_at` | timestamp with time zone | ya |  |  |
| `completed_at` | timestamp with time zone | ya |  |  |
| `completion_note` | text | ya |  |  |
| `cancelled_reason` | text | ya |  |  |

Aturan (CHECK):
- `ck_action_state`: `CHECK ((state = ANY (ARRAY['OPEN'::text, 'IN_PROGRESS'::text, 'DONE'::text, 'CANCELLED'::text])))`

## `compliance.risk`

Risiko ketidakpatuhan per kewajiban.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `obligation_id` | uuid | tidak | FK → `compliance.obligation` |  |
| `title` | text | tidak |  |  |
| `severity` | text | tidak |  | Default: `'MEDIUM'::text`. |

## `corpus.change`

Perubahan per ketentuan + status reviu W5 (titik kendali #1) dan permukaan dampak.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `change_set_id` | uuid | tidak | FK → `corpus.change_set` |  |
| `provision_id` | uuid | tidak | FK → `corpus.provision` |  |
| `base_pv_id` | uuid | ya | FK → `corpus.provision_version` |  |
| `new_pv_id` | uuid | ya | FK → `corpus.provision_version` |  |
| `change_type` | text | tidak |  |  |
| `similarity` | numeric | ya |  |  |
| `is_material` | boolean | tidak |  | Default: `false`. |
| `diff_html` | text | ya |  |  |
| `review_state` | text | tidak |  | Default: `'DETECTED'::text`. |
| `semantic_type` | text | ya |  |  |
| `analyst_material` | boolean | ya |  |  |
| `review_reason` | text | ya |  |  |
| `legal_question` | text | ya |  |  |
| `legal_answer` | text | ya |  |  |
| `validated_by` | uuid | ya | FK → `platform.app_user` |  |
| `validated_at` | timestamp with time zone | ya |  |  |
| `confirmed_by` | uuid | ya | FK → `platform.app_user` |  |
| `confirmed_at` | timestamp with time zone | ya |  |  |
| `return_reason` | text | ya |  |  |
| `impact` | jsonb | tidak |  | Daftar objek hilir yang ditandai saat perubahan material dikonfirmasi. Default: `'{}'::jsonb`. |

Aturan (CHECK):
- `ck_change_confirm_sod`: `CHECK (((confirmed_by IS NULL) OR (validated_by IS NULL) OR (confirmed_by <> validated_by)))`
- `ck_change_review_state`: `CHECK ((review_state = ANY (ARRAY['DETECTED'::text, 'IN_REVIEW'::text, 'VALIDATED'::text, 'REJECTED'::text, 'ESCALATED'::text, 'MATERIAL_CONFIRMED'::text])))`

## `corpus.change_set`

Perbandingan dua versi dokumen.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `base_version_id` | uuid | tidak | FK → `corpus.document_version` |  |
| `new_version_id` | uuid | tidak | FK → `corpus.document_version` |  |
| `created_at` | timestamp with time zone | tidak |  | Default: `now()`. |
| `created_by` | uuid | ya | FK → `platform.app_user` |  |

## `corpus.document`

Identitas peraturan (nomor kanonik unik) dan status keberlakuannya.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `source_id` | uuid | tidak | FK → `corpus.regulatory_source` |  |
| `canonical_number` | text | tidak |  |  |
| `instrument_type` | text | tidak |  |  |
| `issuer` | text | tidak |  |  |
| `title_id` | text | tidak |  |  |
| `status` | text | tidak |  | Default: `'DRAFT'::text`. |

## `corpus.document_version`

Versi imutabel sebuah dokumen setelah PUBLISHED (trigger).

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `document_id` | uuid | tidak | FK → `corpus.document` |  |
| `version_number` | integer | tidak |  |  |
| `sha256` | character varying | tidak |  | Checksum isi berkas/teks. |
| `origin_url` | text | tidak |  |  |
| `canonical_text_ref` | text | tidak |  |  |
| `effective_date` | date | tidak |  |  |
| `state` | text | tidak |  | Status siklus hidup (kosakata tertutup, lihat CHECK). Default: `'PARSING'::text`. |
| `is_partial` | boolean | tidak |  | Default: `false`. |

Trigger:
- `trg_dv_frozen` (DELETE/UPDATE)

## `corpus.provision`

Identitas ketentuan (Pasal) lintas versi.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `document_id` | uuid | tidak | FK → `corpus.document` |  |
| `provision_key` | text | tidak |  |  |
| `provision_type` | text | tidak |  |  |
| `number_label` | text | tidak |  |  |
| `hierarchical_path` | text | tidak |  |  |

## `corpus.provision_version`

Teks ketentuan pada versi tertentu; target semua sitasi; imutabel bila versinya terbit.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `provision_id` | uuid | tidak | FK → `corpus.provision` |  |
| `document_version_id` | uuid | tidak | FK → `corpus.document_version` |  |
| `sequence` | integer | tidak |  |  |
| `text` | text | tidak |  |  |
| `segmentation_confidence` | numeric | tidak |  | Default: `0.85`. |
| `corrected_by_human` | boolean | tidak |  | Default: `false`. |
| `text_search` | tsvector | ya |  | Vektor pencarian full-text bahasa Indonesia (kolom terhitung). |

Trigger:
- `trg_pv_frozen` (DELETE/UPDATE)

## `corpus.regulatory_source`

Otoritas/portal asal dokumen (OJK, BI, JDIH).

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `name` | text | tidak |  |  |
| `category` | text | tidak |  |  |
| `issuer_name` | text | tidak |  |  |
| `base_url` | text | tidak |  |  |
| `permitted_use_statement` | text | ya |  |  |
| `status` | text | tidak |  | Default: `'DRAFT'::text`. |

## `corpus.relationship`

Silsilah antardokumen (mengubah/mencabut/merujuk) dengan sitasi penetap.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `source_document_id` | uuid | tidak | FK → `corpus.document` |  |
| `target_document_id` | uuid | tidak | FK → `corpus.document` |  |
| `relation_type` | text | tidak |  |  |
| `citing_provision_version_id` | uuid | ya | FK → `corpus.provision_version` |  |
| `state` | text | tidak |  | Status siklus hidup (kosakata tertutup, lihat CHECK). Default: `'PROPOSED'::text`. |
| `note` | text | ya |  |  |
| `proposed_by` | uuid | ya | FK → `platform.app_user` |  |
| `confirmed_by` | uuid | ya | FK → `platform.app_user` |  |
| `created_at` | timestamp with time zone | tidak |  | Default: `now()`. |

Aturan (CHECK):
- `ck_relationship_not_self`: `CHECK ((source_document_id <> target_document_id))`
- `relationship_relation_type_check`: `CHECK ((relation_type = ANY (ARRAY['AMENDS'::text, 'REVOKES'::text, 'PARTIALLY_REVOKES'::text, 'REFERS_TO'::text, 'IMPLEMENTS'::text])))`
- `relationship_state_check`: `CHECK ((state = ANY (ARRAY['PROPOSED'::text, 'CONFIRMED'::text, 'REJECTED'::text])))`

## `corpus.taxonomy_label`

Label taksonomi terkendali (tema, populasi) — saran aturan dikonfirmasi manusia.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `document_id` | uuid | tidak | FK → `corpus.document` |  |
| `dimension` | text | tidak |  |  |
| `value` | text | tidak |  |  |
| `state` | text | tidak |  | Status siklus hidup (kosakata tertutup, lihat CHECK). Default: `'SUGGESTED'::text`. |
| `source` | text | tidak |  | Default: `'RULE'::text`. |
| `reason` | text | ya |  |  |
| `decided_by` | uuid | ya | FK → `platform.app_user` |  |
| `created_at` | timestamp with time zone | tidak |  | Default: `now()`. |

Aturan (CHECK):
- `taxonomy_label_dimension_check`: `CHECK ((dimension = ANY (ARRAY['THEME'::text, 'POPULATION'::text, 'OBLIGATION_CHARACTER'::text, 'MATERIALITY'::text])))`
- `taxonomy_label_state_check`: `CHECK ((state = ANY (ARRAY['SUGGESTED'::text, 'CONFIRMED'::text, 'REMOVED'::text])))`

## `platform.ai_call_log`

Setiap panggilan AI: templat+versi, model, prompt, respons mentah, validasi skema, grounding.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `template_name` | text | tidak |  |  |
| `template_version` | text | tidak |  |  |
| `model_id` | text | tidak |  |  |
| `prompt_rendered` | text | tidak |  |  |
| `raw_response` | text | ya |  |  |
| `schema_valid` | boolean | tidak |  |  |
| `grounding_passed` | boolean | tidak |  |  |
| `confidence` | numeric | ya |  |  |
| `created_at` | timestamp with time zone | tidak |  | Default: `now()`. |

## `platform.app_user`

Akun pengguna dan perannya (8 persona + tambahan sintetis). Password PBKDF2.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `username` | text | tidak |  |  |
| `email` | text | tidak |  |  |
| `hashed_password` | text | tidak |  |  |
| `role` | text | tidak |  |  |
| `created_at` | timestamp with time zone | tidak |  | Default: `now()`. |

## `platform.approval`

Keputusan maker-checker pada 6 titik kendali; append-only; snapshot status objek.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `object_type` | text | tidak |  |  |
| `object_id` | uuid | tidak |  |  |
| `control_point` | smallint | tidak |  |  |
| `maker_id` | uuid | tidak | FK → `platform.app_user` |  |
| `last_editor_id` | uuid | tidak | FK → `platform.app_user` |  |
| `checker_id` | uuid | tidak | FK → `platform.app_user` |  |
| `outcome` | text | tidak |  |  |
| `reason` | text | ya |  |  |
| `object_state_snapshot` | jsonb | tidak |  | Salinan status objek saat keputusan diambil. |
| `decided_at` | timestamp with time zone | tidak |  | Default: `now()`. |

Aturan (CHECK):
- `ck_sod_editor`: `CHECK ((checker_id <> last_editor_id))`
- `ck_sod_maker`: `CHECK ((checker_id <> maker_id))`

Trigger:
- `trg_approval_append_only` (UPDATE/DELETE)

## `platform.audit_event`

Jejak audit append-only (trigger menolak UPDATE/DELETE). Setiap transisi status.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | bigint | tidak | PK |  |
| `actor_type` | text | tidak |  |  |
| `actor_id` | uuid | ya | FK → `platform.app_user` |  |
| `action` | text | tidak |  |  |
| `object_type` | text | tidak |  |  |
| `object_id` | uuid | ya |  |  |
| `before_state` | jsonb | ya |  |  |
| `after_state` | jsonb | ya |  |  |
| `correlation_id` | uuid | tidak |  | ID korelasi permintaan (X-Correlation-Id). |
| `occurred_at` | timestamp with time zone | tidak |  | Default: `now()`. |

Trigger:
- `trg_audit_append_only` (UPDATE/DELETE)

## `platform.config`

Parameter runtime teraudit (FR-GOV-007) dengan batas min/maks.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `key` | text | tidak | PK |  |
| `value` | numeric | tidak |  |  |
| `default_value` | numeric | tidak |  |  |
| `min_value` | numeric | tidak |  |  |
| `max_value` | numeric | tidak |  |  |
| `description` | text | tidak |  |  |
| `updated_by` | uuid | ya | FK → `platform.app_user` |  |
| `updated_at` | timestamp with time zone | tidak |  | Default: `now()`. |

Aturan (CHECK):
- `ck_config_bounds`: `CHECK (((value >= min_value) AND (value <= max_value)))`

## `platform.outbox`

Event domain (transactional outbox) untuk pemrosesan asinkron oleh worker.

| Kolom | Tipe | Null | Kunci | Keterangan |
|---|---|---|---|---|
| `id` | uuid | tidak | PK |  |
| `event_type` | text | tidak |  |  |
| `payload` | jsonb | tidak |  | Isi laporan yang dibekukan saat terbit (DRR-07). |
| `correlation_id` | uuid | tidak |  | ID korelasi permintaan (X-Correlation-Id). |
| `occurred_at` | timestamp with time zone | tidak |  | Default: `now()`. |
| `delivered_at` | timestamp with time zone | ya |  |  |
| `attempts` | integer | tidak |  | Default: `0`. |
