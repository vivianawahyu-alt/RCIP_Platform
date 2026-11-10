"""006_user_is_active — hapus lunak (soft delete) akun pengguna.

Matriks RBAC baris "Administrasi pengguna dan peran": Administrator Sistem boleh C/R/U/D(soft). Akun tidak dihapus
fisik karena platform.audit_event dan platform.approval menunjuk ke app_user.id; cukup ditandai tidak aktif.

Revision ID: 006_user_is_active
Revises: 005_document_created_at
"""
from alembic import op

revision = "006_user_is_active"
down_revision = "005_document_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE platform.app_user ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true")


def downgrade() -> None:
    op.execute("ALTER TABLE platform.app_user DROP COLUMN IF EXISTS is_active")