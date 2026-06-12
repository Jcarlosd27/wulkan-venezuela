from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260608_0002"
down_revision = "20260608_0001"
branch_labels = None
depends_on = None


def table_exists(table_name: str) -> bool:
    return inspect(op.get_bind()).has_table(table_name)


def create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    column_sql = ", ".join(columns)
    op.execute(sa.text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({column_sql})"))


def upgrade() -> None:
    if not table_exists("audit_events"):
        op.create_table(
            "audit_events",
            sa.Column("id", sa.String(length=100), primary_key=True),
            sa.Column("actor_id", sa.String(length=80), nullable=False),
            sa.Column("actor_name", sa.String(length=160), nullable=False),
            sa.Column("actor_role", sa.String(length=50), nullable=False),
            sa.Column("action", sa.String(length=80), nullable=False),
            sa.Column("entity_type", sa.String(length=80), nullable=False),
            sa.Column("entity_id", sa.String(length=100), nullable=False),
            sa.Column("detail", sa.Text(), nullable=False),
            sa.Column("ip_address", sa.String(length=80), nullable=False),
            sa.Column("path", sa.String(length=300), nullable=False),
            sa.Column("method", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
        )
    create_index_if_missing("ix_audit_events_created_at", "audit_events", ["created_at"])
    create_index_if_missing("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_audit_events_entity"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_audit_events_created_at"))
    op.execute(sa.text("DROP TABLE IF EXISTS audit_events"))
