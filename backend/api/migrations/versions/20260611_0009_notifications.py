from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260611_0009"
down_revision = "20260611_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("notification_type", sa.String(length=60), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("priority", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("recipient_type", sa.String(length=40), nullable=False),
        sa.Column("recipient_id", sa.String(length=100), nullable=False),
        sa.Column("recipient_role", sa.String(length=80), nullable=False),
        sa.Column("module", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("href", sa.String(length=500), nullable=False),
        sa.Column("deep_link", sa.String(length=500), nullable=False),
        sa.Column("read_at", sa.String(length=60), nullable=False),
        sa.Column("expires_at", sa.String(length=60), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_status", "notifications", ["status"])
    op.create_index("ix_notifications_recipient", "notifications", ["recipient_type", "recipient_id"])
    op.create_index("ix_notifications_module", "notifications", ["module"])


def downgrade() -> None:
    op.drop_index("ix_notifications_module", table_name="notifications")
    op.drop_index("ix_notifications_recipient", table_name="notifications")
    op.drop_index("ix_notifications_status", table_name="notifications")
    op.drop_table("notifications")
