# Arsitektur RCIP

Dokumen ini menjelaskan arsitektur solusi sebagaimana diimplementasikan (bukan rencana). Acuan: TRD RCIP-TRD-001 §3–§5, ADR-01…ADR-04.

## 1. Konteks sistem (C4 level 1)

```mermaid
flowchart LR
    subgraph Pengguna["Delapan persona (FRD §4.1)"]
      A[Analis Regulasi]
      O[Pejabat Kepatuhan]
      M[Manajer Kepatuhan]
      BO[Pemilik Bisnis/Kontrol]
      L[Peninjau Hukum]
      AU[Auditor Internal]
      EX[Eksekutif]
      AD[Administrator Sistem]
    end
    RCIP["RCIP<br/>Regulatory & Compliance Intelligence Platform"]
    SRC["Sumber regulasi publik<br/>OJK · Bank Indonesia · JDIH<br/>(unggah manual PDF/TXT)"]
    LLM["Penyedia LLM (opsional)<br/>melalui AI Gateway"]
    Pengguna -->|browser, HTTPS| RCIP
    SRC -->|dokumen diunggah analis| RCIP
    RCIP -->|hanya teks pasal publik| LLM
```

RCIP tidak mengirim apa pun ke regulator (A-09) dan tidak menerima data klien nyata (A-01, A-06). Tanpa `OPENAI_API_KEY`, ekstraksi memakai ekstraktor aturan `rule-based-v2` (moda terdokumentasi, NFR-13).

## 2. Container (C4 level 2)

```mermaid
flowchart TB
    Browser["Web app<br/>React 18 + TypeScript (Vite)<br/>web/"]
    API["API<br/>FastAPI (Python 3.11)<br/>app/"]
    Worker["Worker<br/>Celery + beat<br/>app/worker.py"]
    PG[("PostgreSQL 16<br/>skema platform · corpus · compliance<br/>trigger imutabilitas + CHECK SoD")]
    Redis[("Redis 7<br/>broker Celery")]
    Store[("Penyimpanan berkas<br/>MinIO (opsional) atau folder ./storage")]
    Browser -->|"/api/v1 (JWT)"| API
    API --> PG
    API --> Store
    API -->|outbox| PG
    Worker -->|"publish_outbox_events tiap 10 dtk"| PG
    Worker --- Redis
```

| Container | Teknologi | Tanggung jawab |
|---|---|---|
| Web app | React 18, TypeScript, Vite | Antarmuka per peran; tidak menyimpan logika otorisasi (hanya cermin) |
| API | FastAPI, SQLAlchemy 2, Pydantic 2 | Semua aturan bisnis, state machine, RBAC, SoD, audit |
| Worker | Celery + beat | Pemrosesan outbox (event lama `DOCUMENT_CHANGE_MATERIAL`); siap untuk job terjadwal |
| Database | PostgreSQL 16 | Satu basis data, tiga skema (ADR-02); integritas dan imutabilitas ditegakkan di DB |
| Penyimpanan | MinIO / filesystem | Berkas bukti & dokumen; checksum SHA-256 dicatat di DB |

## 3. Komponen di dalam API (C4 level 3)

```mermaid
flowchart LR
    subgraph platform["app/platform"]
      AUTH[auth: JWT + PBKDF2]
      GOV[governance: audit + maker-checker]
      CFG[config_service: parameter runtime]
      PR[router: login, users, audit, config, metrics]
    end
    subgraph corpus["app/corpus — Group A"]
      SEG[segmenter: BAB→Pasal]
      DIFF[diff_engine: deterministik]
      CR[router: dokumen, versi, pasal, pencarian]
      REV[review: W4 relasi · W5 reviu perubahan · W6 taksonomi]
    end
    subgraph compliance["app/compliance — Group B"]
      APP[applicability: W7]
      OBL[router: kewajiban W8, risiko/kontrol W9, asesmen W10]
      FND[findings: bukti W11, temuan & remediasi W12]
      RPT[reporting: dasbor, laporan W14, drill-through]
    end
    AI[app/ai/gateway: satu-satunya pintu LLM<br/>validasi skema + grounding verbatim]
    COP[app/copilot: retrieval bersitasi W15]
    SH[app/shared: errors, observability, storage, filescan]
    CR --> SEG
    REV --> DIFF
    OBL --> AI
    OBL --> APP
    FND --> GOV
    RPT --> GOV
    COP --> CR
    platform --- SH
```

Batas kontrak antarkelompok (FRD §15): Group B membaca korpus hanya melalui sitasi `provision_version_id` dan `POST /citations/resolve`.

## 4. Satu permintaan ujung ke ujung — penutupan temuan (titik kendali #5)

```mermaid
sequenceDiagram
    participant M as Manajer (browser)
    participant MW as RequestContextMiddleware
    participant R as findings.decide_closure
    participant G as governance.record_approval
    participant DB as PostgreSQL
    M->>MW: POST /api/v1/compliance/findings/{id}/close (JWT, X-Correlation-Id)
    MW->>R: correlation_id disimpan di contextvar
    R->>R: require_roles(COMPLIANCE_MANAGER)
    R->>DB: baca temuan + pemilik tindakan
    R->>R: tolak bila manajer = pemilik tindakan / pencatat (403 SOD_VIOLATION)
    R->>G: record_approval(control_point=5, maker, checker)
    G->>DB: INSERT approval (append-only)
    R->>DB: UPDATE finding state=CLOSED (CHECK closed_by ≠ raised_by)
    R->>DB: INSERT audit_event (before/after, correlation_id)
    DB-->>R: COMMIT (atomik)
    R-->>M: 200 {state: CLOSED} + header X-Correlation-Id
```

## 5. Rantai kepatuhan sebagai foreign key

`regulatory_source → document → document_version → provision_version → (change) → applicability_decision → obligation → risk/control (obligation_control_map) → evidence → assessment → finding → remediation_action → approval → compliance_report → audit_event`

Semua FK `ON DELETE RESTRICT`; tidak ada penghapusan berantai. ERD lengkap: [erd.md](erd.md).

## 6. Pagar pengaman yang ditegakkan di database (bukan hanya UI)

| Aturan | Mekanisme |
|---|---|
| Versi terbit & teks pasalnya imutabel | trigger `trg_dv_frozen`, `trg_pv_frozen` |
| Audit & persetujuan append-only | trigger `trg_audit_append_only`, `trg_approval_append_only` |
| Draf AI tidak bisa dipetakan ke kontrol | trigger `trg_block_ai_draft` |
| Bukti ACCEPTED dan laporan ISSUED imutabel | trigger `trg_evidence_immutable`, `trg_report_immutable` |
| Pemisahan tugas | CHECK `ck_obligation_sod`, `ck_applicability_sod`, `ck_assessment_signoff_sod`, `ck_finding_closure_sod`, `ck_report_issue_sod`, `ck_change_confirm_sod` |
| Kewajiban aktif wajib bertuan | CHECK `ck_active_needs_owner` |
| Operasional EFFECTIVE dilarang bila desain INEFFECTIVE | CHECK `ck_assessment_design_operating` |
| Parameter runtime dalam batas | CHECK `ck_config_bounds` |

## 7. Keputusan arsitektur (ringkas)

| ADR | Keputusan | Alasan |
|---|---|---|
| ADR-01 | Monorepo FastAPI + React | Satu basis kode untuk dua kelompok (A-10) |
| ADR-02 | Satu PostgreSQL, tiga skema | FK lintas domain menjaga rantai; satu transaksi untuk keputusan + audit |
| ADR-03 | Transactional outbox | Event tidak hilang bila worker mati; propagasi materialitas juga dijalankan sinkron saat konfirmasi |
| ADR-04 | AI Gateway tunggal | Log prompt/model/versi, validasi skema, grounding verbatim, degradasi tanpa LLM |

## 8. Observabilitas

Setiap respons membawa `X-Correlation-Id` yang juga ditulis ke `audit_event.correlation_id`; log permintaan berbentuk JSON (metode, path, status, durasi). `GET /api/v1/metrics` (Admin/Auditor) memberi hitungan per endpoint, latensi rata-rata, error 5xx, login gagal, pembatasan laju, dan percobaan SoD yang diblokir.
