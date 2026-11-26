"""011_origin_url_backfill — izinkan melengkapi URL asal versi lama.

Trigger platform.forbid_frozen_version melarang UPDATE versi PUBLISHED/WITHDRAWN. Pengecualian baru:
satu-satunya perubahan yang boleh adalah origin_url dari nilai bukan-http(s) (kosong, seed://, synthetic://)
menjadi URL http(s), dengan semua kolom lain tidak berubah. Setelah berisi http(s), baris kembali beku.

Revision ID: 011_origin_url_backfill
Revises: 010_legal_position_table
"""
from alembic import op

revision = "011_origin_url_backfill"
down_revision = "010_legal_position_table"
branch_labels = None
depends_on = None

HEAD = """CREATE OR REPLACE FUNCTION platform.forbid_frozen_version() RETURNS trigger AS $$
    BEGIN
        IF current_setting('rcip.seeding', true) = 'on' THEN
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END IF;
        IF TG_OP = 'DELETE' THEN
            IF OLD.state IN ('PUBLISHED','WITHDRAWN') THEN
                RAISE EXCEPTION 'VERSION_IMMUTABLE: published version % cannot be deleted', OLD.id USING ERRCODE = '23514';
            END IF;
            RETURN OLD;
        END IF;
"""
TAIL = """        IF OLD.state IN ('PUBLISHED','WITHDRAWN') AND NEW.state IS DISTINCT FROM 'WITHDRAWN' THEN
            RAISE EXCEPTION 'VERSION_IMMUTABLE: published version % cannot be modified', OLD.id USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql"""
EXCEPTION_BLOCK = """        IF OLD.state IN ('PUBLISHED','WITHDRAWN')
           AND COALESCE(OLD.origin_url, '') !~* '^https?://'
           AND NEW.origin_url ~* '^https?://'
           AND (to_jsonb(NEW) - 'origin_url') = (to_jsonb(OLD) - 'origin_url') THEN
            RETURN NEW;
        END IF;
"""


def upgrade() -> None:
    op.execute(HEAD + EXCEPTION_BLOCK + TAIL)


def downgrade() -> None:
    op.execute(HEAD + TAIL)