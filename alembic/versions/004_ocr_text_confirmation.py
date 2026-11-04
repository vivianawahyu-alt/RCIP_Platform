"""004_ocr_text_confirmation — FR-RKM-004: OCR untuk PDF hasil pindaian + konfirmasi teks oleh analis.

- document_version.extraction_method : cara teks diperoleh (TEXT_LAYER | OCR | PLAIN_TEXT)
- document_version.ocr_pages         : nomor halaman yang dibaca lewat OCR (untuk jejak & tampilan)
- provision_version.low_confidence_text : pasal hasil OCR yang belum dikonfirmasi analis (memblokir publikasi)

Aman di atas data yang ada: hanya ADD COLUMN dengan nilai bawaan.

Revision ID: 004_ocr_text_confirmation
Revises: 003_governance_completion
"""
from alembic import op

revision = "004_ocr_text_confirmation"       # nama migrasi ini
down_revision = "003_governance_completion"  # migrasi sebelumnya (urutan berantai)
branch_labels = None
depends_on = None

STATEMENTS = [
    # 1) cara teks versi diperoleh + daftar halaman OCR; data lama otomatis TEXT_LAYER dan []
    """ALTER TABLE corpus.document_version
        ADD COLUMN IF NOT EXISTS extraction_method text NOT NULL DEFAULT 'TEXT_LAYER',
        ADD COLUMN IF NOT EXISTS ocr_pages jsonb NOT NULL DEFAULT '[]'""",
    # 2) hanya tiga nilai yang sah untuk extraction_method
    """ALTER TABLE corpus.document_version ADD CONSTRAINT ck_dv_extraction_method
        CHECK (extraction_method IN ('TEXT_LAYER','OCR','PLAIN_TEXT'))""",
    # 3) tanda per pasal: true = teks OCR belum diperiksa analis; data lama otomatis false
    """ALTER TABLE corpus.provision_version
        ADD COLUMN IF NOT EXISTS low_confidence_text boolean NOT NULL DEFAULT false""",
    # 4) Pertahanan di DB: versi tidak boleh berstatus PUBLISHED bila masih ada pasal OCR yang belum dikonfirmasi
    """CREATE FUNCTION corpus.forbid_publish_unconfirmed_ocr() RETURNS trigger AS $$
    BEGIN
        IF NEW.state = 'PUBLISHED' AND OLD.state <> 'PUBLISHED' AND EXISTS (
            SELECT 1 FROM corpus.provision_version
            WHERE document_version_id = NEW.id AND low_confidence_text) THEN
            RAISE EXCEPTION 'Versi % masih memiliki pasal OCR yang belum dikonfirmasi', NEW.id;
        END IF;
        RETURN NEW;
    END $$ LANGUAGE plpgsql""",
    # 5) pasang fungsi di atas sebagai trigger: dijalankan setiap kali baris document_version di-UPDATE
    """CREATE TRIGGER trg_dv_unconfirmed_ocr BEFORE UPDATE ON corpus.document_version
        FOR EACH ROW EXECUTE FUNCTION corpus.forbid_publish_unconfirmed_ocr()""",
]


def upgrade() -> None:
    # jalankan setiap perintah SQL di atas secara berurutan
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    # kebalikan upgrade (urutan terbalik): hapus trigger, fungsi, lalu kolom
    op.execute("DROP TRIGGER IF EXISTS trg_dv_unconfirmed_ocr ON corpus.document_version")
    op.execute("DROP FUNCTION IF EXISTS corpus.forbid_publish_unconfirmed_ocr()")
    op.execute("ALTER TABLE corpus.provision_version DROP COLUMN IF EXISTS low_confidence_text")
    op.execute("ALTER TABLE corpus.document_version DROP CONSTRAINT IF EXISTS ck_dv_extraction_method")
    op.execute("ALTER TABLE corpus.document_version DROP COLUMN IF EXISTS ocr_pages, "
               "DROP COLUMN IF EXISTS extraction_method")