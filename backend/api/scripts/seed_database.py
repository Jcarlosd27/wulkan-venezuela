from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config as AlembicConfig


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.db import SessionLocal, drop_database, init_database
from models import (
    AdminUser,
    Announcement,
    AuditEvent,
    Category,
    Client,
    CreditMovement,
    MediaAsset,
    Order,
    Product,
    StockMovement,
)
from store import load_store


def parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def upsert(session, model, object_id: str, values: dict[str, Any]) -> None:
    dialect_name = session.get_bind().dialect.name
    table = model.__table__
    update_values = {key: value for key, value in values.items() if key != "id"}

    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        statement = pg_insert(table).values(**values)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[table.c.id],
                set_=update_values,
            )
        )
        return

    if dialect_name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        statement = sqlite_insert(table).values(**values)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[table.c.id],
                set_=update_values,
            )
        )
        return

    instance = session.get(model, object_id)
    if instance is None:
        session.add(model(**values))
        return

    for key, value in values.items():
        setattr(instance, key, value)


def seed_admin_users(session, store: dict[str, Any]) -> None:
    for user in store.get("admin_users", []):
        values = {
            "id": user["id"],
            "name": user.get("name", ""),
            "email": user.get("email", "").lower(),
            "password_hash": user.get("passwordHash", ""),
            "role": user.get("role", "operator"),
            "status": user.get("status", "active"),
            "must_change_password": bool(user.get("mustChangePassword")),
            "last_login_at": parse_dt(user.get("lastLoginAt")) if user.get("lastLoginAt") else None,
            "created_at": parse_dt(user.get("createdAt")),
            "updated_at": parse_dt(user.get("updatedAt")),
            "payload": user,
        }
        upsert(session, AdminUser, values["id"], values)


def seed_clients(session, store: dict[str, Any]) -> None:
    for client in store.get("clients", []):
        values = {
            "id": client["id"],
            "business_name": client.get("businessName", ""),
            "tax_id": client.get("taxId", ""),
            "contact_name": client.get("contactName", ""),
            "phone": client.get("phone", ""),
            "email": client.get("email", "").lower(),
            "password_hash": client.get("passwordHash", ""),
            "must_change_password": bool(client.get("mustChangePassword")),
            "client_type": client.get("clientType", "b2b"),
            "status": client.get("status", "active"),
            "credit_enabled": bool(client.get("creditEnabled")),
            "credit_limit_usd": float(client.get("creditLimitUsd") or 0),
            "credit_used_usd": float(client.get("creditUsedUsd") or 0),
            "payment_terms_days": int(client.get("paymentTermsDays") or 0),
            "notes": client.get("notes", ""),
            "created_at": parse_dt(client.get("createdAt")),
            "updated_at": parse_dt(client.get("updatedAt")),
            "payload": client,
        }
        upsert(session, Client, values["id"], values)


def seed_categories(session, store: dict[str, Any]) -> None:
    for category in store.get("categories", []):
        values = {
            "id": category["id"],
            "name": category.get("name", ""),
            "description": category.get("description", ""),
            "image_url": category.get("imageUrl", ""),
            "status": category.get("status", "active"),
            "created_at": parse_dt(category.get("createdAt")),
            "updated_at": parse_dt(category.get("updatedAt")),
            "payload": category,
        }
        upsert(session, Category, values["id"], values)


def seed_products(session, store: dict[str, Any]) -> None:
    for product in store.get("products", []):
        values = {
            "id": product["id"],
            "sku": product.get("sku", ""),
            "title": product.get("title", ""),
            "description": product.get("description", ""),
            "product_type": product.get("productType", "machine"),
            "category_id": product.get("categoryId", ""),
            "category_name": product.get("categoryName", ""),
            "public_price_usd": float(product.get("publicPriceUsd") or 0),
            "original_price_usd": float(product.get("originalPriceUsd") or product.get("publicPriceUsd") or 0),
            "discount_percent": float(product.get("discountPercent") or 0),
            "b2b_price_usd": float(product.get("b2bPriceUsd") or 0),
            "exchange_rate_usd_ves": float(product.get("exchangeRateUsdVes") or 38.5),
            "stock": int(product.get("stock") or 0),
            "reserved": int(product.get("reserved") or 0),
            "status": product.get("status", "active"),
            "image_url": product.get("imageUrl", ""),
            "image_urls": product.get("imageUrls") or [],
            "pdf_urls": product.get("pdfUrls") or [],
            "variants": product.get("variants") or [],
            "specifications": product.get("specifications") or {},
            "requires_quote": bool(product.get("requiresQuote")),
            "requires_technical_validation": bool(product.get("requiresTechnicalValidation")),
            "rotation_last_30_days": int(product.get("rotationLast30Days") or 0),
            "created_at": parse_dt(product.get("createdAt")),
            "updated_at": parse_dt(product.get("updatedAt")),
            "payload": product,
        }
        upsert(session, Product, values["id"], values)


def seed_media_assets(session, store: dict[str, Any]) -> None:
    for asset in store.get("media_assets", []):
        values = {
            "id": asset["id"],
            "title": asset.get("title", ""),
            "product_id": asset.get("productId") or None,
            "asset_type": asset.get("type", asset.get("assetType", "image")),
            "url": asset.get("url", asset.get("fileUrl", "")),
            "file_path": asset.get("filePath", ""),
            "status": asset.get("status", "active"),
            "created_at": parse_dt(asset.get("createdAt")),
            "updated_at": parse_dt(asset.get("updatedAt")),
            "payload": asset,
        }
        upsert(session, MediaAsset, values["id"], values)


def seed_announcements(session, store: dict[str, Any]) -> None:
    for announcement in store.get("announcements", []):
        values = {
            "id": announcement["id"],
            "title": announcement.get("title", ""),
            "body": announcement.get("body", ""),
            "placement": announcement.get("placement", "home"),
            "priority": int(announcement.get("priority") or 50),
            "cta_label": announcement.get("ctaLabel", ""),
            "cta_url": announcement.get("ctaUrl", ""),
            "image_url": announcement.get("imageUrl", ""),
            "starts_at": announcement.get("startsAt", ""),
            "ends_at": announcement.get("endsAt", ""),
            "status": announcement.get("status", "active"),
            "created_at": parse_dt(announcement.get("createdAt")),
            "updated_at": parse_dt(announcement.get("updatedAt")),
            "payload": announcement,
        }
        upsert(session, Announcement, values["id"], values)


def seed_stock_movements(session, store: dict[str, Any]) -> None:
    for movement in store.get("stock_movements", []):
        values = {
            "id": movement["id"],
            "product_id": movement.get("productId", ""),
            "sku": movement.get("sku", ""),
            "movement_type": movement.get("type", movement.get("movementType", "adjustment")),
            "quantity": int(movement.get("quantity") or 0),
            "note": movement.get("note", ""),
            "created_by": movement.get("createdBy", ""),
            "created_at": parse_dt(movement.get("createdAt")),
            "payload": movement,
        }
        upsert(session, StockMovement, values["id"], values)


def seed_orders(session, store: dict[str, Any]) -> None:
    for order in store.get("orders", []):
        values = {
            "id": order["id"],
            "order_number": order.get("orderId", order["id"]),
            "customer_id": order.get("customerId", ""),
            "status": order.get("status", "credit_review"),
            "credit_status": order.get("creditStatus", "manual_review"),
            "payment_status": order.get("paymentStatus", "pending"),
            "total_usd": float(order.get("totalUsd") or 0),
            "total_ves": float(order.get("totalVes") or 0),
            "exchange_rate_usd_ves": float(order.get("exchangeRateUsdVes") or 38.5),
            "paid_usd": float(order.get("paidUsd") or 0),
            "balance_usd": float(order.get("balanceUsd") or order.get("totalUsd") or 0),
            "credit_before_usd": float(order.get("creditBeforeUsd") or 0),
            "credit_after_usd": float(order.get("creditAfterUsd") or 0),
            "inventory_status": order.get("inventoryStatus", ""),
            "stock_status": order.get("stockStatus", ""),
            "managed_by": order.get("managedBy", ""),
            "managed_at": order.get("managedAt", ""),
            "items": order.get("items") or [],
            "customer_snapshot": order.get("customer") or {},
            "status_history": order.get("statusHistory") or [],
            "created_at": parse_dt(order.get("createdAt")),
            "updated_at": parse_dt(order.get("updatedAt")),
            "payload": order,
        }
        upsert(session, Order, values["id"], values)


def seed_credit_movements(session, store: dict[str, Any]) -> None:
    for movement in store.get("credit_movements", []):
        values = {
            "id": movement["id"],
            "movement_type": movement.get("movementType", "payment"),
            "client_id": movement.get("clientId", ""),
            "order_id": movement.get("orderId", ""),
            "amount_usd": float(movement.get("amountUsd") or 0),
            "amount_ves": float(movement.get("amountVes") or 0),
            "exchange_rate_usd_ves": float(movement.get("exchangeRateUsdVes") or 38.5),
            "method": movement.get("method", "other"),
            "reference": movement.get("reference", ""),
            "note": movement.get("note", ""),
            "created_by": movement.get("createdBy", ""),
            "created_at": parse_dt(movement.get("createdAt")),
            "payload": movement,
        }
        upsert(session, CreditMovement, values["id"], values)


def seed_audit_events(session, store: dict[str, Any]) -> None:
    for event in store.get("audit_events", []):
        values = {
            "id": event["id"],
            "actor_id": event.get("actorId", ""),
            "actor_name": event.get("actorName", ""),
            "actor_role": event.get("actorRole", ""),
            "action": event.get("action", ""),
            "entity_type": event.get("entityType", ""),
            "entity_id": event.get("entityId", ""),
            "detail": event.get("detail", ""),
            "ip_address": event.get("ipAddress", ""),
            "path": event.get("path", ""),
            "method": event.get("method", ""),
            "created_at": parse_dt(event.get("createdAt")),
            "payload": event,
        }
        upsert(session, AuditEvent, values["id"], values)


def seed_database(reset: bool = False) -> None:
    if reset:
        drop_database()
    init_database()
    alembic_config = AlembicConfig(str(ROOT_DIR / "alembic.ini"))
    command.stamp(alembic_config, "head")
    store = load_store()

    with SessionLocal() as session:
        seed_admin_users(session, store)
        seed_clients(session, store)
        seed_categories(session, store)
        seed_products(session, store)
        seed_media_assets(session, store)
        seed_announcements(session, store)
        seed_stock_movements(session, store)
        seed_orders(session, store)
        seed_credit_movements(session, store)
        seed_audit_events(session, store)
        session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed FVENTAS SQL database from the JSON store.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables before seeding.")
    args = parser.parse_args()
    seed_database(reset=args.reset)
    print("FVENTAS database seeded.")


if __name__ == "__main__":
    main()
