"""012_relation_supersedes — tambah jenis relasi SUPERSEDES (menggantikan) sesuai FRD BR-RKM-009-5.

Relasi SUPERSEDES yang dikonfirmasi Manajer mengubah status dokumen target menjadi SUPERSEDED (digantikan).

Revision ID: 012_relation_supersedes
Revises: 011_origin_url_backfill
"""
from alembic import op

revision = "012_relation_supersedes"
down_revision = "011_origin_url_backfill"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE corpus.relationship DROP CONSTRAINT IF EXISTS relationship_relation_type_check")
    op.execute("""ALTER TABLE corpus.relationship ADD CONSTRAINT relationship_relation_type_check
        CHECK (relation_type IN ('AMENDS','REVOKES','PARTIALLY_REVOKES','SUPERSEDES','REFERS_TO','IMPLEMENTS'))""")


def downgrade():
    op.execute("DELETE FROM corpus.relationship WHERE relation_type = 'SUPERSEDES'")
    op.execute("ALTER TABLE corpus.relationship DROP CONSTRAINT IF EXISTS relationship_relation_type_check")
    op.execute("""ALTER TABLE corpus.relationship ADD CONSTRAINT relationship_relation_type_check
        CHECK (relation_type IN ('AMENDS','REVOKES','PARTIALLY_REVOKES','REFERS_TO','IMPLEMENTS'))""")