from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260609_0004"
down_revision = "20260608_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_technicians",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("company_name", sa.String(length=180), nullable=False, server_default=""),
        sa.Column("contact_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("phone", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("whatsapp", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("email", sa.String(length=180), nullable=False, server_default=""),
        sa.Column("state", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("city", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("address", sa.Text(), nullable=False, server_default=""),
        sa.Column("specialties", sa.JSON(), nullable=False),
        sa.Column("coverage", sa.String(length=220), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("visible_in_app", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("service_technicians")
