from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260611_0010"
down_revision = "20260611_0009"
branch_labels = None
depends_on = None


INDEXES = [
    ("ix_clients_tax_id", "clients", ["tax_id"]),
    ("ix_clients_status", "clients", ["status"]),
    ("ix_clients_client_type", "clients", ["client_type"]),
    ("ix_categories_status", "categories", ["status"]),
    ("ix_products_category_id", "products", ["category_id"]),
    ("ix_products_status", "products", ["status"]),
    ("ix_products_product_type", "products", ["product_type"]),
    ("ix_media_assets_product_id", "media_assets", ["product_id"]),
    ("ix_media_assets_asset_type", "media_assets", ["asset_type"]),
    ("ix_media_assets_status", "media_assets", ["status"]),
    ("ix_announcements_placement", "announcements", ["placement"]),
    ("ix_announcements_status", "announcements", ["status"]),
    ("ix_announcements_priority", "announcements", ["priority"]),
    ("ix_stock_movements_product_id", "stock_movements", ["product_id"]),
    ("ix_stock_movements_movement_type", "stock_movements", ["movement_type"]),
    ("ix_stock_movements_created_at", "stock_movements", ["created_at"]),
    ("ix_orders_customer_id", "orders", ["customer_id"]),
    ("ix_orders_status", "orders", ["status"]),
    ("ix_orders_credit_status", "orders", ["credit_status"]),
    ("ix_orders_payment_status", "orders", ["payment_status"]),
    ("ix_orders_created_at", "orders", ["created_at"]),
    ("ix_credit_movements_client_id", "credit_movements", ["client_id"]),
    ("ix_credit_movements_order_id", "credit_movements", ["order_id"]),
    ("ix_credit_movements_movement_type", "credit_movements", ["movement_type"]),
    ("ix_credit_movements_created_at", "credit_movements", ["created_at"]),
    ("ix_quotes_client_id", "quotes", ["client_id"]),
    ("ix_quotes_seller_id", "quotes", ["seller_id"]),
    ("ix_quotes_status", "quotes", ["status"]),
    ("ix_quotes_created_at", "quotes", ["created_at"]),
    ("ix_crm_records_record_type", "crm_records", ["record_type"]),
    ("ix_crm_records_status", "crm_records", ["status"]),
    ("ix_crm_records_client_id", "crm_records", ["client_id"]),
    ("ix_crm_records_next_action_at", "crm_records", ["next_action_at"]),
    ("ix_notifications_priority", "notifications", ["priority"]),
    ("ix_notifications_created_at", "notifications", ["created_at"]),
    ("ix_notifications_module_created_at", "notifications", ["module", "created_at"]),
    ("ix_notifications_recipient_status", "notifications", ["recipient_type", "recipient_id", "status"]),
    ("ix_service_technicians_state_city", "service_technicians", ["state", "city"]),
    ("ix_service_technicians_status", "service_technicians", ["status"]),
    ("ix_service_technicians_visible_in_app", "service_technicians", ["visible_in_app"]),
    ("ix_audit_events_created_at", "audit_events", ["created_at"]),
    ("ix_audit_events_actor_created_at", "audit_events", ["actor_id", "created_at"]),
    ("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"]),
    ("ix_audit_events_action", "audit_events", ["action"]),
    ("ix_import_drafts_status", "import_drafts", ["status"]),
    ("ix_import_drafts_expires_at", "import_drafts", ["expires_at"]),
    ("ix_import_drafts_created_by_id", "import_drafts", ["created_by_id"]),
]


def upgrade() -> None:
    for name, table, columns in INDEXES:
        column_sql = ", ".join(columns)
        op.execute(
            sa.text(
                f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column_sql})"
            )
        )


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.execute(sa.text(f"DROP INDEX IF EXISTS {name}"))
