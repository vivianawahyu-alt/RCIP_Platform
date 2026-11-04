"""005_document_created_at — catat waktu dokumen didaftarkan agar daftar korpus bisa diurutkan dari yang terbaru.

Dokumen lama diisi dari jejak audit DOCUMENT_CREATED (waktu pendaftaran sebenarnya). Dokumen seed yang
tidak punya jejak audit dianggap paling lama.

Revision ID: 005_document_created_at
Revises: 004_ocr_text_confirmation
"""
from alembic import op

revision = "005_document_created_at"         # nama migrasi ini
down_revision = "004_ocr_text_confirmation"  # migrasi sebelumnya (OCR)
branch_labels = None
depends_on = None

STATEMENTS = [
    # 1) tambah kolom waktu pendaftaran (sementara boleh kosong agar bisa diisi ulang)
    "ALTER TABLE corpus.document ADD COLUMN IF NOT EXISTS created_at timestamptz",
    # 2) dokumen yang didaftarkan lewat aplikasi: ambil waktunya dari jejak audit DOCUMENT_CREATED
    """UPDATE corpus.document d SET created_at = a.first_at
        FROM (SELECT object_id, min(occurred_at) AS first_at FROM platform.audit_event
              WHERE action = 'DOCUMENT_CREATED' GROUP BY object_id) a
        WHERE a.object_id = d.id AND d.created_at IS NULL""",
    # 3) dokumen seed (tanpa jejak audit): dianggap paling lama, sedikit sebelum aktivitas pertama di audit,
    #    supaya dokumen yang kalian tambahkan sendiri tetap tampil di atas
    """UPDATE corpus.document SET created_at =
        (SELECT coalesce(min(occurred_at), now()) FROM platform.audit_event) - interval '1 minute'
        WHERE created_at IS NULL""",
    # 4) mulai sekarang wajib terisi; dokumen baru otomatis memakai waktu saat didaftarkan
    "ALTER TABLE corpus.document ALTER COLUMN created_at SET DEFAULT now(), ALTER COLUMN created_at SET NOT NULL",
    # 5) indeks agar pengurutan terbaru-dulu tetap cepat
    "CREATE INDEX IF NOT EXISTS ix_document_created_at ON corpus.document(created_at DESC)",
]


def upgrade() -> None:
    # jalankan setiap perintah SQL di atas secara berurutan
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    # kebalikan upgrade: hapus indeks lalu kolom
    op.execute("DROP INDEX IF EXISTS corpus.ix_document_created_at")
    op.execute("ALTER TABLE corpus.document DROP COLUMN IF EXISTS created_at")