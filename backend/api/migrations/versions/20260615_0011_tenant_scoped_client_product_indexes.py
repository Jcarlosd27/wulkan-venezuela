from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260615_0011"
down_revision = "20260611_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_clients_email"))
    op.create_index("ix_clients_email", "clients", ["email"], unique=False)
    op.execute(sa.text("DROP INDEX IF EXISTS ix_products_sku"))
    op.create_index("ix_products_sku", "products", ["sku"], unique=False)


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_products_sku"))
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)
    op.execute(sa.text("DROP INDEX IF EXISTS ix_clients_email"))
    op.create_index("ix_clients_email", "clients", ["email"], unique=True)
