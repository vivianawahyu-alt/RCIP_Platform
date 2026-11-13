"""009_obligation_legal_position — jalur eskalasi kewajiban ke Peninjau Hukum (FRD Eksibit 33, TRD §7.6).

Menambah kolom pertanyaan, posisi hukum, dan peninjau pada kewajiban; polanya sama dengan
applicability_decision dan change (legal_question / legal_answer / legal_reviewer_id).
Trigger pemetaan kontrol juga memblokir kewajiban PENDING_LEGAL (belum divalidasi manusia).
Aman di atas data yang ada: hanya ADD COLUMN IF NOT EXISTS dan CREATE OR REPLACE FUNCTION.

Revision ID: 009_obligation_legal_position
Revises: 008_document_metadata
"""
from alembic import op

revision = "009_obligation_legal_position"
down_revision = "008_document_metadata"
branch_labels = None
depends_on = None

STATEMENTS = [
    """ALTER TABLE compliance.obligation
        ADD COLUMN IF NOT EXISTS legal_question text,
        ADD COLUMN IF NOT EXISTS legal_answer text,
        ADD COLUMN IF NOT EXISTS legal_reviewer_id uuid REFERENCES platform.app_user(id)""",
    # pertahanan berlapis: kewajiban yang menunggu Peninjau Hukum tidak boleh dipetakan ke kontrol
    """CREATE OR REPLACE FUNCTION compliance.block_ai_draft_mapping() RETURNS trigger AS $$
    DECLARE ob_state text;
    BEGIN
        SELECT state INTO ob_state FROM compliance.obligation WHERE id = NEW.obligation_id;
        IF ob_state IN ('AI_DRAFT','IN_VALIDATION','PENDING_LEGAL') THEN
            RAISE EXCEPTION 'AI_DRAFT_BLOCKED: obligation % belum divalidasi manusia', NEW.obligation_id USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("""CREATE OR REPLACE FUNCTION compliance.block_ai_draft_mapping() RETURNS trigger AS $$
    DECLARE ob_state text;
    BEGIN
        SELECT state INTO ob_state FROM compliance.obligation WHERE id = NEW.obligation_id;
        IF ob_state IN ('AI_DRAFT','IN_VALIDATION') THEN
            RAISE EXCEPTION 'AI_DRAFT_BLOCKED: obligation % belum divalidasi manusia', NEW.obligation_id USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""")
    op.execute("""ALTER TABLE compliance.obligation
        DROP COLUMN IF EXISTS legal_reviewer_id,
        DROP COLUMN IF EXISTS legal_answer,
        DROP COLUMN IF EXISTS legal_question""")