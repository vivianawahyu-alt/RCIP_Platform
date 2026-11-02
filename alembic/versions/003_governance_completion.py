"""003_governance_completion — titik kendali #1 (materialitas, W5) & #2 (keberlakuan, W7), W4 relasi,
W6 taksonomi, FR-GOV-007 konfigurasi runtime, explainability kewajiban.

Aman di atas data yang ada: hanya ADD COLUMN / CREATE TABLE + backfill.

Revision ID: 003_governance_completion
Revises: 002_findings_assessment_reports
"""
from alembic import op

revision = "003_governance_completion"
down_revision = "002_findings_assessment_reports"
branch_labels = None
depends_on = None

STATEMENTS = [
    # ---------- W5: reviu perubahan ----------
    """ALTER TABLE corpus.change
        ADD COLUMN IF NOT EXISTS review_state text NOT NULL DEFAULT 'DETECTED',
        ADD COLUMN IF NOT EXISTS semantic_type text,
        ADD COLUMN IF NOT EXISTS analyst_material boolean,
        ADD COLUMN IF NOT EXISTS review_reason text,
        ADD COLUMN IF NOT EXISTS legal_question text,
        ADD COLUMN IF NOT EXISTS legal_answer text,
        ADD COLUMN IF NOT EXISTS validated_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS validated_at timestamptz,
        ADD COLUMN IF NOT EXISTS confirmed_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS confirmed_at timestamptz,
        ADD COLUMN IF NOT EXISTS return_reason text,
        ADD COLUMN IF NOT EXISTS impact jsonb NOT NULL DEFAULT '{}'""",
    """ALTER TABLE corpus.change ADD CONSTRAINT ck_change_review_state
        CHECK (review_state IN ('DETECTED','IN_REVIEW','VALIDATED','REJECTED','ESCALATED','MATERIAL_CONFIRMED'))""",
    """ALTER TABLE corpus.change ADD CONSTRAINT ck_change_confirm_sod
        CHECK (confirmed_by IS NULL OR validated_by IS NULL OR confirmed_by <> validated_by)""",
    "ALTER TABLE corpus.change_set ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES platform.app_user(id)",

    # ---------- W4: relasi & silsilah ----------
    """CREATE TABLE IF NOT EXISTS corpus.relationship (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        source_document_id uuid NOT NULL REFERENCES corpus.document(id) ON DELETE RESTRICT,
        target_document_id uuid NOT NULL REFERENCES corpus.document(id) ON DELETE RESTRICT,
        relation_type text NOT NULL CHECK (relation_type IN ('AMENDS','REVOKES','PARTIALLY_REVOKES','REFERS_TO','IMPLEMENTS')),
        citing_provision_version_id uuid REFERENCES corpus.provision_version(id) ON DELETE RESTRICT,
        state text NOT NULL DEFAULT 'PROPOSED' CHECK (state IN ('PROPOSED','CONFIRMED','REJECTED')),
        note text,
        proposed_by uuid REFERENCES platform.app_user(id),
        confirmed_by uuid REFERENCES platform.app_user(id),
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_relationship_not_self CHECK (source_document_id <> target_document_id))""",

    # ---------- W6: taksonomi ----------
    """CREATE TABLE IF NOT EXISTS corpus.taxonomy_label (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        document_id uuid NOT NULL REFERENCES corpus.document(id) ON DELETE RESTRICT,
        dimension text NOT NULL CHECK (dimension IN ('THEME','POPULATION','OBLIGATION_CHARACTER','MATERIALITY')),
        value text NOT NULL,
        state text NOT NULL DEFAULT 'SUGGESTED' CHECK (state IN ('SUGGESTED','CONFIRMED','REMOVED')),
        source text NOT NULL DEFAULT 'RULE',
        reason text,
        decided_by uuid REFERENCES platform.app_user(id),
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE (document_id, dimension, value))""",

    # ---------- W7: keberlakuan maker-checker ----------
    """ALTER TABLE compliance.applicability_decision
        ADD COLUMN IF NOT EXISTS state text NOT NULL DEFAULT 'IN_ASSESSMENT',
        ADD COLUMN IF NOT EXISTS cited_provision_version_ids jsonb NOT NULL DEFAULT '[]',
        ADD COLUMN IF NOT EXISTS scope_provision_version_ids jsonb NOT NULL DEFAULT '[]',
        ADD COLUMN IF NOT EXISTS legal_question text,
        ADD COLUMN IF NOT EXISTS legal_answer text,
        ADD COLUMN IF NOT EXISTS legal_reviewer_id uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS submitted_at timestamptz,
        ADD COLUMN IF NOT EXISTS decided_at timestamptz,
        ADD COLUMN IF NOT EXISTS return_reason text,
        ADD COLUMN IF NOT EXISTS review_owner_id uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS review_target_date date,
        ADD COLUMN IF NOT EXISTS suggested_value text,
        ADD COLUMN IF NOT EXISTS superseded_by uuid REFERENCES compliance.applicability_decision(id)""",
    # keputusan otomatis versi lama dianggap sudah berlaku (legacy) agar kewajiban yang ada tetap tertelusur
    "UPDATE compliance.applicability_decision SET state = 'APPROVED', decided_at = created_at WHERE state = 'IN_ASSESSMENT'",
    """ALTER TABLE compliance.applicability_decision ADD CONSTRAINT ck_applicability_state
        CHECK (state IN ('IN_ASSESSMENT','PENDING_LEGAL','PENDING_APPROVAL','APPROVED','REJECTED_TO_MAKER',
                         'REVIEW_REQUIRED','SUPERSEDED'))""",

    # ---------- explainability kewajiban & penanda sumber berubah ----------
    """ALTER TABLE compliance.obligation
        ADD COLUMN IF NOT EXISTS supporting_phrases jsonb NOT NULL DEFAULT '[]',
        ADD COLUMN IF NOT EXISTS ai_call_id uuid REFERENCES platform.ai_call_log(id),
        ADD COLUMN IF NOT EXISTS model_id text,
        ADD COLUMN IF NOT EXISTS low_confidence boolean NOT NULL DEFAULT false,
        ADD COLUMN IF NOT EXISTS low_confidence_reviewed_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS reopen_reason text""",
    "ALTER TABLE compliance.control ADD COLUMN IF NOT EXISTS source_changed boolean NOT NULL DEFAULT false",
    "ALTER TABLE compliance.organisation_profile ADD COLUMN IF NOT EXISTS version int NOT NULL DEFAULT 1",

    # ---------- FR-GOV-007: konfigurasi runtime teraudit ----------
    """CREATE TABLE IF NOT EXISTS platform.config (
        key text PRIMARY KEY,
        value numeric NOT NULL,
        default_value numeric NOT NULL,
        min_value numeric NOT NULL,
        max_value numeric NOT NULL,
        description text NOT NULL,
        updated_by uuid REFERENCES platform.app_user(id),
        updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_config_bounds CHECK (value BETWEEN min_value AND max_value))""",
    """INSERT INTO platform.config (key, value, default_value, min_value, max_value, description) VALUES
        ('ai.confidence_floor', 0.70, 0.70, 0.50, 0.95, 'Di bawah nilai ini draf AI ditandai LOW_CONFIDENCE dan wajib ditinjau eksplisit'),
        ('ai.relevance_floor', 0.05, 0.05, 0.01, 0.50, 'Ambang relevansi retrieval copilot'),
        ('change.review_sla_days', 7, 7, 1, 30, 'SLA reviu perubahan regulasi (hari)'),
        ('remediation.window_days.CRITICAL', 30, 30, 7, 90, 'Jendela remediasi maksimum temuan CRITICAL'),
        ('remediation.window_days.HIGH', 60, 60, 14, 180, 'Jendela remediasi maksimum temuan HIGH'),
        ('remediation.window_days.MEDIUM', 90, 90, 30, 270, 'Jendela remediasi maksimum temuan MEDIUM (asumsi tim)'),
        ('remediation.window_days.LOW', 180, 180, 30, 365, 'Jendela remediasi maksimum temuan LOW (asumsi tim)'),
        ('evidence.max_file_mb', 25, 25, 1, 100, 'Ukuran maksimum berkas bukti (MB)'),
        ('auth.max_failed_logins_per_minute', 5, 5, 3, 20, 'Batas percobaan login gagal per menit per akun')
        ON CONFLICT (key) DO NOTHING""",

    "CREATE INDEX IF NOT EXISTS ix_change_review_state ON corpus.change(review_state)",
    "CREATE INDEX IF NOT EXISTS ix_applicability_state ON compliance.applicability_decision(state)",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    raise NotImplementedError("Migrasi tata kelola tidak dapat di-downgrade; pulihkan dari backup.")
