from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260610_0005"
down_revision = "20260609_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_drafts",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("module", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="preview"),
        sa.Column("created_by_id", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("created_by_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("rows", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_drafts_module", "import_drafts", ["module"])


def downgrade() -> None:
    op.drop_index("ix_import_drafts_module", table_name="import_drafts")
    op.drop_table("import_drafts")
