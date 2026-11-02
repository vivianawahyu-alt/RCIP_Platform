"""002_findings_assessment_reports — Tahap lanjutan rantai kepatuhan (FRD W10, W11, W12, W14)

- Temuan (W12): severity, pemilik, tenggat, sumber, tautan kontrol/asesmen, catatan penutupan & risk acceptance.
- Tindakan remediasi (FR-EVR-005): pemilik, tenggat asli + riwayat perpanjangan, mulai/selesai.
- Bukti (W11): status SUBMITTED/ACCEPTED/REJECTED, rasional review, bukti penutupan tindakan.
- Asesmen (W10): kesimpulan desain & operasional, status CONCLUDED -> PENDING_SIGNOFF -> SIGNED_OFF.
- Laporan (W14): DRAFT -> PENDING_APPROVAL -> ISSUED -> SUPERSEDED | WITHDRAWN, penafian berversi.
- Trigger: bukti ACCEPTED dan laporan ISSUED tidak dapat diubah/dihapus.

Aman dijalankan di atas database yang sudah berisi data (hanya ADD COLUMN + backfill).

Revision ID: 002_findings_assessment_reports
Revises: 001_initial_schema
"""
from alembic import op

revision = "002_findings_assessment_reports"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None

STATEMENTS = [
    # ---------------- temuan ----------------
    """ALTER TABLE compliance.finding
        ADD COLUMN IF NOT EXISTS title text,
        ADD COLUMN IF NOT EXISTS severity text NOT NULL DEFAULT 'MEDIUM',
        ADD COLUMN IF NOT EXISTS source_type text NOT NULL DEFAULT 'MANUAL',
        ADD COLUMN IF NOT EXISTS control_id uuid REFERENCES compliance.control(id) ON DELETE RESTRICT,
        ADD COLUMN IF NOT EXISTS assessment_id uuid REFERENCES compliance.assessment(id) ON DELETE RESTRICT,
        ADD COLUMN IF NOT EXISTS owner_id uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS raised_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS target_closure_date date,
        ADD COLUMN IF NOT EXISTS closure_submitted_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS closure_submitted_at timestamptz,
        ADD COLUMN IF NOT EXISTS closed_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS closed_at timestamptz,
        ADD COLUMN IF NOT EXISTS closure_rationale text,
        ADD COLUMN IF NOT EXISTS risk_acceptance_rationale text,
        ADD COLUMN IF NOT EXISTS risk_accepted_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS risk_review_date date,
        ADD COLUMN IF NOT EXISTS reopened_count int NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()""",
    # gap lama = kesenjangan cakupan; tetapkan sumber & severity yang konsisten
    """UPDATE compliance.finding SET source_type = 'COVERAGE_GAP', severity = 'HIGH'
        WHERE kind = 'COMPLIANCE_GAP' AND source_type = 'MANUAL'""",
    """UPDATE compliance.finding f SET owner_id = o.owner_id
        FROM compliance.obligation o WHERE o.id = f.obligation_id AND f.owner_id IS NULL""",
    """UPDATE compliance.finding SET title = left(description, 120) WHERE title IS NULL""",
    # temuan yang sudah memiliki tindakan berpindah ke ACTION_PLANNED
    """UPDATE compliance.finding f SET state = 'ACTION_PLANNED'
        WHERE f.state = 'OPEN' AND EXISTS (SELECT 1 FROM compliance.remediation_action r WHERE r.finding_id = f.id)""",
    """ALTER TABLE compliance.finding ADD CONSTRAINT ck_finding_severity
        CHECK (severity IN ('CRITICAL','HIGH','MEDIUM','LOW'))""",
    """ALTER TABLE compliance.finding ADD CONSTRAINT ck_finding_state
        CHECK (state IN ('OPEN','ACTION_PLANNED','IN_REMEDIATION','PENDING_CLOSURE_VALIDATION',
                         'CLOSED','RISK_ACCEPTED','REVIEW_REQUIRED'))""",
    # BR-EVR-006-1 di lapisan data: penutup ≠ pemunculan temuan
    """ALTER TABLE compliance.finding ADD CONSTRAINT ck_finding_closure_sod
        CHECK (closed_by IS NULL OR raised_by IS NULL OR closed_by <> raised_by)""",

    # ---------------- tindakan remediasi ----------------
    """ALTER TABLE compliance.remediation_action
        ADD COLUMN IF NOT EXISTS expected_outcome text,
        ADD COLUMN IF NOT EXISTS original_due_date date,
        ADD COLUMN IF NOT EXISTS extension_history jsonb NOT NULL DEFAULT '[]',
        ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
        ADD COLUMN IF NOT EXISTS started_at timestamptz,
        ADD COLUMN IF NOT EXISTS completed_at timestamptz,
        ADD COLUMN IF NOT EXISTS completion_note text,
        ADD COLUMN IF NOT EXISTS cancelled_reason text""",
    "UPDATE compliance.remediation_action SET original_due_date = due_date WHERE original_due_date IS NULL",
    "ALTER TABLE compliance.remediation_action ALTER COLUMN original_due_date SET NOT NULL",
    """ALTER TABLE compliance.remediation_action ADD CONSTRAINT ck_action_state
        CHECK (state IN ('OPEN','IN_PROGRESS','DONE','CANCELLED'))""",

    # ---------------- bukti ----------------
    """ALTER TABLE compliance.evidence
        ADD COLUMN IF NOT EXISTS remediation_action_id uuid REFERENCES compliance.remediation_action(id) ON DELETE RESTRICT,
        ADD COLUMN IF NOT EXISTS description text,
        ADD COLUMN IF NOT EXISTS size_bytes bigint,
        ADD COLUMN IF NOT EXISTS state text NOT NULL DEFAULT 'SUBMITTED',
        ADD COLUMN IF NOT EXISTS reviewed_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS reviewed_at timestamptz,
        ADD COLUMN IF NOT EXISTS review_rationale text""",
    "ALTER TABLE compliance.evidence ALTER COLUMN control_id DROP NOT NULL",
    """ALTER TABLE compliance.evidence ADD CONSTRAINT ck_evidence_target
        CHECK (control_id IS NOT NULL OR remediation_action_id IS NOT NULL)""",
    """ALTER TABLE compliance.evidence ADD CONSTRAINT ck_evidence_state
        CHECK (state IN ('SUBMITTED','ACCEPTED','REJECTED','SUPERSEDED','EXPIRED'))""",
    # BR-EVR-003-1: bukti ACCEPTED imutabel (hanya boleh berpindah ke SUPERSEDED/EXPIRED)
    """CREATE FUNCTION compliance.forbid_accepted_evidence_change() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'EVIDENCE_IMMUTABLE: evidence % cannot be deleted', OLD.id USING ERRCODE = '23514';
        END IF;
        IF OLD.state = 'ACCEPTED' AND (
             NEW.state NOT IN ('ACCEPTED','SUPERSEDED','EXPIRED')
             OR NEW.sha256 IS DISTINCT FROM OLD.sha256 OR NEW.filename IS DISTINCT FROM OLD.filename
             OR NEW.object_key IS DISTINCT FROM OLD.object_key OR NEW.description IS DISTINCT FROM OLD.description
             OR NEW.review_rationale IS DISTINCT FROM OLD.review_rationale) THEN
            RAISE EXCEPTION 'EVIDENCE_IMMUTABLE: accepted evidence % cannot be modified', OLD.id USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""",
    """CREATE TRIGGER trg_evidence_immutable BEFORE UPDATE OR DELETE ON compliance.evidence
        FOR EACH ROW EXECUTE FUNCTION compliance.forbid_accepted_evidence_change()""",

    # ---------------- asesmen ----------------
    """ALTER TABLE compliance.assessment
        ADD COLUMN IF NOT EXISTS design_result text,
        ADD COLUMN IF NOT EXISTS operating_result text,
        ADD COLUMN IF NOT EXISTS design_rationale text,
        ADD COLUMN IF NOT EXISTS operating_rationale text,
        ADD COLUMN IF NOT EXISTS state text NOT NULL DEFAULT 'CONCLUDED',
        ADD COLUMN IF NOT EXISTS submitted_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS submitted_at timestamptz,
        ADD COLUMN IF NOT EXISTS signed_off_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS signed_off_at timestamptz,
        ADD COLUMN IF NOT EXISTS return_reason text""",
    """UPDATE compliance.assessment SET design_result = result, operating_result = result,
           design_rationale = COALESCE(notes, 'Dimigrasikan dari asesmen satu hasil'),
           operating_rationale = COALESCE(notes, 'Dimigrasikan dari asesmen satu hasil')
        WHERE design_result IS NULL""",
    """ALTER TABLE compliance.assessment ADD CONSTRAINT ck_assessment_state
        CHECK (state IN ('CONCLUDED','PENDING_SIGNOFF','SIGNED_OFF'))""",
    # W10: operasional EFFECTIVE tidak boleh bila desain INEFFECTIVE
    """ALTER TABLE compliance.assessment ADD CONSTRAINT ck_assessment_design_operating
        CHECK (NOT (design_result = 'INEFFECTIVE' AND operating_result = 'EFFECTIVE'))""",
    """ALTER TABLE compliance.assessment ADD CONSTRAINT ck_assessment_signoff_sod
        CHECK (signed_off_by IS NULL OR signed_off_by <> assessed_by)""",

    # ---------------- laporan ----------------
    """ALTER TABLE compliance.compliance_report
        ADD COLUMN IF NOT EXISTS generated_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS submitted_at timestamptz,
        ADD COLUMN IF NOT EXISTS issued_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS issued_at timestamptz,
        ADD COLUMN IF NOT EXISTS return_reason text,
        ADD COLUMN IF NOT EXISTS withdrawn_reason text,
        ADD COLUMN IF NOT EXISTS withdrawn_at timestamptz,
        ADD COLUMN IF NOT EXISTS superseded_by uuid REFERENCES compliance.compliance_report(id),
        ADD COLUMN IF NOT EXISTS disclaimer_version text""",
    """UPDATE compliance.compliance_report SET generated_by = created_by, issued_by = created_by,
           issued_at = created_at, disclaimer_version = 'legacy'
        WHERE generated_by IS NULL""",
    """ALTER TABLE compliance.compliance_report ALTER COLUMN state SET DEFAULT 'DRAFT'""",
    """ALTER TABLE compliance.compliance_report ADD CONSTRAINT ck_report_state
        CHECK (state IN ('DRAFT','PENDING_APPROVAL','ISSUED','SUPERSEDED','WITHDRAWN'))""",
    # DRR-10: penerbit ≠ pembangkit. Baris legacy (issued_by = generated_by) dikecualikan lewat disclaimer_version.
    """ALTER TABLE compliance.compliance_report ADD CONSTRAINT ck_report_issue_sod
        CHECK (issued_by IS NULL OR generated_by IS NULL OR issued_by <> generated_by
               OR disclaimer_version = 'legacy')""",
    # DRR-09: laporan terbit imutabel; hanya transisi ke SUPERSEDED / WITHDRAWN yang sah
    """CREATE FUNCTION compliance.forbid_issued_report_change() RETURNS trigger AS $$
    BEGIN
        IF TG_OP = 'DELETE' THEN
            IF OLD.state <> 'DRAFT' THEN
                RAISE EXCEPTION 'REPORT_IMMUTABLE: report % cannot be deleted', OLD.id USING ERRCODE = '23514';
            END IF;
            RETURN OLD;
        END IF;
        IF OLD.state IN ('ISSUED','SUPERSEDED','WITHDRAWN') AND (
             NEW.payload IS DISTINCT FROM OLD.payload OR NEW.title IS DISTINCT FROM OLD.title
             OR NEW.issued_by IS DISTINCT FROM OLD.issued_by OR NEW.issued_at IS DISTINCT FROM OLD.issued_at
             OR NOT (NEW.state = OLD.state OR (OLD.state = 'ISSUED' AND NEW.state IN ('SUPERSEDED','WITHDRAWN')))) THEN
            RAISE EXCEPTION 'REPORT_IMMUTABLE: issued report % cannot be modified', OLD.id USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""",
    """CREATE TRIGGER trg_report_immutable BEFORE UPDATE OR DELETE ON compliance.compliance_report
        FOR EACH ROW EXECUTE FUNCTION compliance.forbid_issued_report_change()""",

    "CREATE INDEX IF NOT EXISTS ix_finding_state ON compliance.finding(state)",
    "CREATE INDEX IF NOT EXISTS ix_action_finding ON compliance.remediation_action(finding_id)",
    "CREATE INDEX IF NOT EXISTS ix_evidence_action ON compliance.evidence(remediation_action_id)",
    "CREATE INDEX IF NOT EXISTS ix_audit_object ON platform.audit_event(object_id)",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    raise NotImplementedError("Migrasi tata kelola tidak dapat di-downgrade; pulihkan dari backup.")
