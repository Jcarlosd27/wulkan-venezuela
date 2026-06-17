from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260608_0001"
down_revision = None
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=180), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("payload", sa.JSON(), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_admin_users_email", "admin_users", ["email"], unique=True)

    op.create_table(
        "clients",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("business_name", sa.String(length=180), nullable=False),
        sa.Column("tax_id", sa.String(length=80), nullable=False),
        sa.Column("contact_name", sa.String(length=160), nullable=False),
        sa.Column("phone", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=180), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("client_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("credit_enabled", sa.Boolean(), nullable=False),
        sa.Column("credit_limit_usd", sa.Float(), nullable=False),
        sa.Column("credit_used_usd", sa.Float(), nullable=False),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_clients_email", "clients", ["email"])

    op.create_table(
        "categories",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        *timestamps(),
    )

    op.create_table(
        "products",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("sku", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("product_type", sa.String(length=60), nullable=False),
        sa.Column("category_id", sa.String(length=80), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("category_name", sa.String(length=160), nullable=False),
        sa.Column("public_price_usd", sa.Float(), nullable=False),
        sa.Column("original_price_usd", sa.Float(), nullable=False),
        sa.Column("discount_percent", sa.Float(), nullable=False),
        sa.Column("b2b_price_usd", sa.Float(), nullable=False),
        sa.Column("exchange_rate_usd_ves", sa.Float(), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("reserved", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("image_urls", sa.JSON(), nullable=False),
        sa.Column("pdf_urls", sa.JSON(), nullable=False),
        sa.Column("variants", sa.JSON(), nullable=False),
        sa.Column("specifications", sa.JSON(), nullable=False),
        sa.Column("requires_quote", sa.Boolean(), nullable=False),
        sa.Column("requires_technical_validation", sa.Boolean(), nullable=False),
        sa.Column("rotation_last_30_days", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_products_sku", "products", ["sku"])

    op.create_table(
        "media_assets",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("product_id", sa.String(length=80), sa.ForeignKey("products.id")),
        sa.Column("asset_type", sa.String(length=50), nullable=False),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        *timestamps(),
    )

    op.create_table(
        "announcements",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("placement", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("cta_label", sa.String(length=120), nullable=False),
        sa.Column("cta_url", sa.String(length=500), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("starts_at", sa.String(length=60), nullable=False),
        sa.Column("ends_at", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        *timestamps(),
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("product_id", sa.String(length=80), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("sku", sa.String(length=80), nullable=False),
        sa.Column("movement_type", sa.String(length=50), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_stock_movements_sku", "stock_movements", ["sku"])

    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("order_number", sa.String(length=80), nullable=False),
        sa.Column("customer_id", sa.String(length=80), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("credit_status", sa.String(length=50), nullable=False),
        sa.Column("payment_status", sa.String(length=50), nullable=False),
        sa.Column("total_usd", sa.Float(), nullable=False),
        sa.Column("total_ves", sa.Float(), nullable=False),
        sa.Column("exchange_rate_usd_ves", sa.Float(), nullable=False),
        sa.Column("paid_usd", sa.Float(), nullable=False),
        sa.Column("balance_usd", sa.Float(), nullable=False),
        sa.Column("credit_before_usd", sa.Float(), nullable=False),
        sa.Column("credit_after_usd", sa.Float(), nullable=False),
        sa.Column("inventory_status", sa.String(length=50), nullable=False),
        sa.Column("stock_status", sa.String(length=50), nullable=False),
        sa.Column("managed_by", sa.String(length=160), nullable=False),
        sa.Column("managed_at", sa.String(length=60), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("customer_snapshot", sa.JSON(), nullable=False),
        sa.Column("status_history", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_orders_order_number", "orders", ["order_number"])

    op.create_table(
        "credit_movements",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("movement_type", sa.String(length=50), nullable=False),
        sa.Column("client_id", sa.String(length=80), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("order_id", sa.String(length=80), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("amount_ves", sa.Float(), nullable=False),
        sa.Column("exchange_rate_usd_ves", sa.Float(), nullable=False),
        sa.Column("method", sa.String(length=50), nullable=False),
        sa.Column("reference", sa.String(length=160), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("credit_movements")
    op.drop_index("ix_orders_order_number", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_stock_movements_sku", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_table("announcements")
    op.drop_table("media_assets")
    op.drop_index("ix_products_sku", table_name="products")
    op.drop_table("products")
    op.drop_table("categories")
    op.drop_index("ix_clients_email", table_name="clients")
    op.drop_table("clients")
    op.drop_index("ix_admin_users_email", table_name="admin_users")
    op.drop_table("admin_users")
