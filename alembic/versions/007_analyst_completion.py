"""007_analyst_completion — melengkapi pekerjaan Regulatory Analyst.

FR-RKM-001  registri sumber regulasi: DRAFT → PENDING_USE_REVIEW → (Administrator, orang berbeda) ACTIVE ⇄ SUSPENDED → RETIRED
FR-RKM-002  provenans versi: nama berkas, jenis, ukuran, pengunggah (URL asal kini wajib di API)
FR-COP-004  log interaksi copilot per pengguna, tidak dapat disunting
FR-COP-005  antrean tinjauan jawaban copilot berkeyakinan rendah (diputus Analis/Pejabat/Peninjau Hukum, bukan peminta)

Aman di atas data yang ada: hanya ADD COLUMN / CREATE TABLE; sumber lama tetap ACTIVE dan dilengkapi
pernyataan penggunaan bawaan agar memenuhi aturan baru.

Revision ID: 007_analyst_completion
Revises: 006_user_is_active
"""
from alembic import op

revision = "007_analyst_completion"
down_revision = "006_user_is_active"  # setelah migrasi fitur role (soft delete akun)
branch_labels = None
depends_on = None

STATEMENTS = [
    # ---------- FR-RKM-001: registri sumber ----------
    # 1) kolom tata kelola sumber: siapa membuat / mengajukan / menyetujui, alasan pengembalian
    """ALTER TABLE corpus.regulatory_source
        ADD COLUMN IF NOT EXISTS url_allow_list jsonb NOT NULL DEFAULT '[]',
        ADD COLUMN IF NOT EXISTS citation_requirement_text text,
        ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
        ADD COLUMN IF NOT EXISTS submitted_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS approved_by uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS approved_at timestamptz,
        ADD COLUMN IF NOT EXISTS return_reason text""",
    # 2) sumber lama: lengkapi pernyataan penggunaan & daftar URL yang diizinkan (base_url)
    """UPDATE corpus.regulatory_source SET
        permitted_use_statement = COALESCE(NULLIF(btrim(permitted_use_statement), ''),
            'Dokumen regulasi publik; dipakai untuk keperluan akademik capstone dengan sitasi sumber resmi.'),
        url_allow_list = CASE WHEN url_allow_list = '[]'::jsonb THEN jsonb_build_array(base_url) ELSE url_allow_list END""",
    # 3) aturan di DB: status sah, sumber ACTIVE wajib punya pernyataan penggunaan, penyetuju ≠ pengaju (SoD)
    """ALTER TABLE corpus.regulatory_source ADD CONSTRAINT ck_source_status
        CHECK (status IN ('DRAFT','PENDING_USE_REVIEW','ACTIVE','SUSPENDED','RETIRED'))""",
    """ALTER TABLE corpus.regulatory_source ADD CONSTRAINT ck_source_active_has_use
        CHECK (status <> 'ACTIVE' OR coalesce(btrim(permitted_use_statement), '') <> '')""",
    """ALTER TABLE corpus.regulatory_source ADD CONSTRAINT ck_source_approval_sod
        CHECK (approved_by IS NULL OR submitted_by IS NULL OR approved_by <> submitted_by)""",

    # ---------- FR-RKM-002: provenans versi ----------
    """ALTER TABLE corpus.document_version
        ADD COLUMN IF NOT EXISTS file_name text,
        ADD COLUMN IF NOT EXISTS mime_type text,
        ADD COLUMN IF NOT EXISTS size_bytes bigint,
        ADD COLUMN IF NOT EXISTS uploaded_by uuid REFERENCES platform.app_user(id)""",
    # indeks sidik jari berkas → pemeriksaan duplikat cepat
    "CREATE INDEX IF NOT EXISTS ix_document_version_sha256 ON corpus.document_version(sha256)",

    # ---------- FR-COP-004: log interaksi copilot ----------
    """ALTER TABLE platform.ai_call_log
        ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES platform.app_user(id),
        ADD COLUMN IF NOT EXISTS presented_state text""",
    # log AI tidak boleh diubah / dihapus (append-only)
    """CREATE OR REPLACE FUNCTION platform.forbid_ai_log_change() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'APPEND_ONLY: ai_call_log % cannot be modified', OLD.id USING ERRCODE = '23514';
    END $$ LANGUAGE plpgsql""",
    "DROP TRIGGER IF EXISTS trg_ai_log_append_only ON platform.ai_call_log",
    """CREATE TRIGGER trg_ai_log_append_only BEFORE UPDATE OR DELETE ON platform.ai_call_log
        FOR EACH ROW EXECUTE FUNCTION platform.forbid_ai_log_change()""",

    # ---------- FR-COP-005: tinjauan jawaban berkeyakinan rendah ----------
    """CREATE TABLE IF NOT EXISTS platform.copilot_review (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        interaction_id uuid NOT NULL REFERENCES platform.ai_call_log(id) ON DELETE RESTRICT,
        state text NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','COMPLETED')),
        requested_by uuid NOT NULL REFERENCES platform.app_user(id),
        requested_at timestamptz NOT NULL DEFAULT now(),
        request_note text,
        reviewer_id uuid REFERENCES platform.app_user(id),
        verdict text CHECK (verdict IN ('CONFIRMED','CORRECTED','REJECTED')),
        corrected_text text,
        reviewed_at timestamptz,
        CONSTRAINT ck_copilot_review_sod CHECK (reviewer_id IS NULL OR reviewer_id <> requested_by),
        CONSTRAINT ck_copilot_corrected_text CHECK (verdict IS DISTINCT FROM 'CORRECTED' OR coalesce(btrim(corrected_text), '') <> ''),
        CONSTRAINT uq_copilot_review_interaction UNIQUE (interaction_id))""",
    # ambang keyakinan copilot, dapat diubah admin di menu Administrasi (perubahan tercatat di audit)
    """INSERT INTO platform.config (key, value, default_value, min_value, max_value, description)
        VALUES ('copilot.review_threshold', 0.70, 0.70, 0.50, 1.00,
                'Jawaban copilot dengan keyakinan di bawah nilai ini ditandai dan dapat dikirim untuk ditinjau (FR-COP-005)')
        ON CONFLICT (key) DO NOTHING""",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DELETE FROM platform.config WHERE key = 'copilot.review_threshold'")
    op.execute("DROP TABLE IF EXISTS platform.copilot_review")
    op.execute("DROP TRIGGER IF EXISTS trg_ai_log_append_only ON platform.ai_call_log")
    op.execute("DROP FUNCTION IF EXISTS platform.forbid_ai_log_change()")
    op.execute("ALTER TABLE platform.ai_call_log DROP COLUMN IF EXISTS presented_state, DROP COLUMN IF EXISTS user_id")
    op.execute("DROP INDEX IF EXISTS corpus.ix_document_version_sha256")
    op.execute("ALTER TABLE corpus.document_version DROP COLUMN IF EXISTS uploaded_by, DROP COLUMN IF EXISTS size_bytes, "
               "DROP COLUMN IF EXISTS mime_type, DROP COLUMN IF EXISTS file_name")
    for c in ("ck_source_approval_sod", "ck_source_active_has_use", "ck_source_status"):
        op.execute(f"ALTER TABLE corpus.regulatory_source DROP CONSTRAINT IF EXISTS {c}")
    op.execute("ALTER TABLE corpus.regulatory_source DROP COLUMN IF EXISTS return_reason, DROP COLUMN IF EXISTS approved_at, "
               "DROP COLUMN IF EXISTS approved_by, DROP COLUMN IF EXISTS submitted_by, DROP COLUMN IF EXISTS created_at, "
               "DROP COLUMN IF EXISTS created_by, DROP COLUMN IF EXISTS citation_requirement_text, "
               "DROP COLUMN IF EXISTS url_allow_list")
