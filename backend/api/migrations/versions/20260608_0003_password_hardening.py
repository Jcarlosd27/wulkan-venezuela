from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260608_0003"
down_revision = "20260608_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "clients",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("clients", "must_change_password")
    op.drop_column("admin_users", "must_change_password")
