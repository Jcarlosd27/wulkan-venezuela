from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260611_0008"
down_revision = "20260611_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_settings",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("business_settings")
