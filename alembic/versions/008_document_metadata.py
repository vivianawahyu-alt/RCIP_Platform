"""008_document_metadata — metadata katalog peraturan + indeks untuk filter pencarian.

Revision ID: 008_document_metadata
Revises: 007_analyst_completion
"""
from alembic import op

revision = "008_document_metadata"
down_revision = "007_analyst_completion"
branch_labels = None
depends_on = None

STATEMENTS = [
    """ALTER TABLE corpus.document
        ADD COLUMN IF NOT EXISTS year integer,
        ADD COLUMN IF NOT EXISTS enacted_date date,
        ADD COLUMN IF NOT EXISTS promulgated_date date,
        ADD COLUMN IF NOT EXISTS gazette_ref text""",
    r"""UPDATE corpus.document
        SET year = substring(canonical_number from '((19|20)[0-9]{2})\s*$')::integer
        WHERE year IS NULL AND canonical_number ~ '(19|20)[0-9]{2}\s*$'""",
    """ALTER TABLE corpus.document ADD CONSTRAINT ck_document_year
        CHECK (year IS NULL OR year BETWEEN 1945 AND 2100)""",
    "CREATE INDEX IF NOT EXISTS ix_document_instrument_type ON corpus.document(instrument_type)",
    "CREATE INDEX IF NOT EXISTS ix_document_status ON corpus.document(status)",
    "CREATE INDEX IF NOT EXISTS ix_document_year ON corpus.document(year)",
    "CREATE INDEX IF NOT EXISTS ix_docversion_doc_effective ON corpus.document_version(document_id, effective_date)",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS corpus.ix_docversion_doc_effective")
    op.execute("DROP INDEX IF EXISTS corpus.ix_document_year")
    op.execute("DROP INDEX IF EXISTS corpus.ix_document_status")
    op.execute("DROP INDEX IF EXISTS corpus.ix_document_instrument_type")
    op.execute("ALTER TABLE corpus.document DROP CONSTRAINT IF EXISTS ck_document_year")
    op.execute("""ALTER TABLE corpus.document
        DROP COLUMN IF EXISTS gazette_ref, DROP COLUMN IF EXISTS promulgated_date,
        DROP COLUMN IF EXISTS enacted_date, DROP COLUMN IF EXISTS year""")