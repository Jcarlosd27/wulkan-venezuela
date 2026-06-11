from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260611_0007"
down_revision = "20260611_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_records",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("record_type", sa.String(length=50), nullable=False, server_default="lead"),
        sa.Column("pipeline_stage", sa.String(length=50), nullable=False, server_default="new_lead"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("client_id", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("seller_id", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("contact_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("phone", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("email", sa.String(length=180), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("estimated_value_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("probability_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expected_close_at", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("next_action_at", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("last_activity_at", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("activities", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_crm_records_pipeline_stage", "crm_records", ["pipeline_stage"])
    op.create_index("ix_crm_records_seller_id", "crm_records", ["seller_id"])


def downgrade() -> None:
    op.drop_index("ix_crm_records_seller_id", table_name="crm_records")
    op.drop_index("ix_crm_records_pipeline_stage", table_name="crm_records")
    op.drop_table("crm_records")
