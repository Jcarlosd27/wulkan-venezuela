from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260611_0006"
down_revision = "20260610_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quotes",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("quote_number", sa.String(length=80), nullable=False),
        sa.Column("client_id", sa.String(length=80), nullable=False),
        sa.Column("seller_id", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("valid_until", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("sale_type", sa.String(length=50), nullable=False, server_default="cash"),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_ves", sa.Float(), nullable=False, server_default="0"),
        sa.Column("exchange_rate_usd_ves", sa.Float(), nullable=False, server_default="38.5"),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("client_snapshot", sa.JSON(), nullable=False),
        sa.Column("versions", sa.JSON(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("internal_comment", sa.Text(), nullable=False, server_default=""),
        sa.Column("converted_order_id", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quotes_quote_number", "quotes", ["quote_number"])


def downgrade() -> None:
    op.drop_index("ix_quotes_quote_number", table_name="quotes")
    op.drop_table("quotes")
