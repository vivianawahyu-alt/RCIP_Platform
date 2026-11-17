"""010_legal_position_table — posisi hukum di tabel sendiri + alur revisi relasi (arahan mentor).

1. compliance.legal_position (berversi) + compliance.legal_position_citation (pasal beserta versinya).
2. Keputusan keberlakuan, kewajiban, dan tinjauan perubahan menyimpan legal_position_id + legal_position_version;
   kolom teks lama legal_answer / legal_reviewer_id dipindahkan ke tabel baru lalu dihapus.
3. Relasi regulasi: catatan hukum, permintaan revisi, dan penolakan Manajer.

Revision ID: 010_legal_position_table
Revises: 009_obligation_legal_position
"""
from alembic import op

revision = "010_legal_position_table"
down_revision = "009_obligation_legal_position"
branch_labels = None
depends_on = None

# (tabel subjek, subject_type, kolom peninjau lama atau NULL)
SUBJECTS = [
    ("compliance.applicability_decision", "APPLICABILITY", "legal_reviewer_id"),
    ("compliance.obligation", "OBLIGATION", "legal_reviewer_id"),
    ("corpus.change", "CHANGE", "NULL"),
]


def upgrade() -> None:
    op.execute("""CREATE TABLE IF NOT EXISTS compliance.legal_position (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        subject_type text NOT NULL CHECK (subject_type IN ('APPLICABILITY','OBLIGATION','CHANGE')),
        subject_id uuid NOT NULL,
        version integer NOT NULL,
        question text,
        position_text text NOT NULL,
        reviewer_id uuid REFERENCES platform.app_user(id),
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_legal_position_version UNIQUE (subject_type, subject_id, version))""")
    op.execute("""CREATE TABLE IF NOT EXISTS compliance.legal_position_citation (
        legal_position_id uuid NOT NULL REFERENCES compliance.legal_position(id) ON DELETE CASCADE,
        provision_version_id uuid NOT NULL REFERENCES corpus.provision_version(id) ON DELETE RESTRICT,
        PRIMARY KEY (legal_position_id, provision_version_id))""")
    for table, subject_type, reviewer in SUBJECTS:
        op.execute(f"""ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS legal_position_id uuid REFERENCES compliance.legal_position(id),
            ADD COLUMN IF NOT EXISTS legal_position_version integer""")
        # pindahkan posisi hukum lama (teks) ke tabel baru sebagai versi 1
        op.execute(f"""WITH ins AS (
                INSERT INTO compliance.legal_position (subject_type, subject_id, version, question, position_text, reviewer_id)
                SELECT '{subject_type}', id, 1, legal_question, legal_answer, {reviewer} FROM {table}
                WHERE legal_answer IS NOT NULL
                RETURNING id, subject_id)
            UPDATE {table} t SET legal_position_id = ins.id, legal_position_version = 1
            FROM ins WHERE t.id = ins.subject_id""")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS legal_answer")
        if reviewer != "NULL":
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS legal_reviewer_id")
    op.execute("""ALTER TABLE corpus.relationship
        ADD COLUMN IF NOT EXISTS legal_note text,
        ADD COLUMN IF NOT EXISTS legal_reviewer_id uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS reject_reason text,
        ADD COLUMN IF NOT EXISTS rejected_by uuid REFERENCES platform.app_user(id)""")
    # status baru: REVISION_REQUESTED (Peninjau Hukum minta revisi, Analis sedang merevisi)
    op.execute("ALTER TABLE corpus.relationship DROP CONSTRAINT IF EXISTS relationship_state_check")
    op.execute("""ALTER TABLE corpus.relationship ADD CONSTRAINT relationship_state_check
        CHECK (state IN ('PROPOSED','REVISION_REQUESTED','CONFIRMED','REJECTED'))""")


def downgrade() -> None:
    op.execute("UPDATE corpus.relationship SET state = 'PROPOSED' WHERE state = 'REVISION_REQUESTED'")
    op.execute("ALTER TABLE corpus.relationship DROP CONSTRAINT IF EXISTS relationship_state_check")
    op.execute("""ALTER TABLE corpus.relationship ADD CONSTRAINT relationship_state_check
        CHECK (state IN ('PROPOSED','CONFIRMED','REJECTED'))""")
    op.execute("""ALTER TABLE corpus.relationship
        DROP COLUMN IF EXISTS rejected_by, DROP COLUMN IF EXISTS reject_reason,
        DROP COLUMN IF EXISTS legal_reviewer_id, DROP COLUMN IF EXISTS legal_note""")
    for table, _subject_type, reviewer in SUBJECTS:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS legal_answer text")
        if reviewer != "NULL":
            op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS legal_reviewer_id uuid REFERENCES platform.app_user(id)")
            op.execute(f"""UPDATE {table} t SET legal_answer = lp.position_text, legal_reviewer_id = lp.reviewer_id
                FROM compliance.legal_position lp WHERE lp.id = t.legal_position_id""")
        else:
            op.execute(f"""UPDATE {table} t SET legal_answer = lp.position_text
                FROM compliance.legal_position lp WHERE lp.id = t.legal_position_id""")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS legal_position_version, DROP COLUMN IF EXISTS legal_position_id")
    op.execute("DROP TABLE IF EXISTS compliance.legal_position_citation")
    op.execute("DROP TABLE IF EXISTS compliance.legal_position")