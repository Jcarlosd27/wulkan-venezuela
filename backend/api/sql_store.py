from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db import SessionLocal, init_database
from models import (
    AdminUser,
    Announcement,
    Category,
    Client,
    CreditMovement,
    MediaAsset,
    Order,
    Product,
    StockMovement,
)


def utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def utc_now() -> str:
    return utc_now_dt().isoformat().replace("+00:00", "Z")


def parse_dt(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if not value:
        return utc_now_dt()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return utc_now_dt()


def iso_dt(value: str | datetime | None) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return utc_now()


def copy_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    return dict(payload or {})


def upsert(session, model, object_id: str, values: dict[str, Any]) -> None:
    instance = session.get(model, object_id)
    if instance is None:
        session.add(model(**values))
        return

    for key, value in values.items():
        setattr(instance, key, value)


def soft_prune(session, model, live_ids: set[str]) -> None:
    for row in session.query(model).all():
        if row.id not in live_ids and hasattr(row, "status"):
            row.status = "deleted"
            if hasattr(row, "updated_at"):
                row.updated_at = utc_now_dt()


def admin_user_to_dict(row: AdminUser) -> dict[str, Any]:
    payload = copy_payload(row.payload)
    payload.update(
        {
            "id": row.id,
            "name": row.name,
            "email": row.email,
            "passwordHash": row.password_hash,
            "role": row.role,
            "status": row.status,
            "lastLoginAt": iso_dt(row.last_login_at) if row.last_login_at else "",
            "createdAt": iso_dt(row.created_at),
            "updatedAt": iso_dt(row.updated_at),
        }
    )
    return payload


def client_to_dict(row: Client) -> dict[str, Any]:
    payload = copy_payload(row.payload)
    payload.update(
        {
            "id": row.id,
            "businessName": row.business_name,
            "taxId": row.tax_id,
            "contactName": row.contact_name,
            "phone": row.phone,
            "email": row.email,
            "passwordHash": row.password_hash,
            "clientType": row.client_type,
            "status": row.status,
            "creditEnabled": row.credit_enabled,
            "creditLimitUsd": row.credit_limit_usd,
            "creditUsedUsd": row.credit_used_usd,
            "paymentTermsDays": row.payment_terms_days,
            "notes": row.notes,
            "createdAt": iso_dt(row.created_at),
            "updatedAt": iso_dt(row.updated_at),
        }
    )
    return payload


def category_to_dict(row: Category) -> dict[str, Any]:
    payload = copy_payload(row.payload)
    payload.update(
        {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "imageUrl": row.image_url,
            "status": row.status,
            "createdAt": iso_dt(row.created_at),
            "updatedAt": iso_dt(row.updated_at),
        }
    )
    return payload


def product_to_dict(row: Product) -> dict[str, Any]:
    payload = copy_payload(row.payload)
    payload.update(
        {
            "id": row.id,
            "sku": row.sku,
            "title": row.title,
            "description": row.description,
            "productType": row.product_type,
            "categoryId": row.category_id,
            "categoryName": row.category_name,
            "publicPriceUsd": row.public_price_usd,
            "originalPriceUsd": row.original_price_usd,
            "discountPercent": row.discount_percent,
            "b2bPriceUsd": row.b2b_price_usd,
            "exchangeRateUsdVes": row.exchange_rate_usd_ves,
            "stock": row.stock,
            "reserved": row.reserved,
            "status": row.status,
            "imageUrl": row.image_url,
            "imageUrls": row.image_urls or [],
            "pdfUrls": row.pdf_urls or [],
            "variants": row.variants or [],
            "specifications": row.specifications or {},
            "requiresQuote": row.requires_quote,
            "requiresTechnicalValidation": row.requires_technical_validation,
            "rotationLast30Days": row.rotation_last_30_days,
            "createdAt": iso_dt(row.created_at),
            "updatedAt": iso_dt(row.updated_at),
        }
    )
    return payload


def media_asset_to_dict(row: MediaAsset) -> dict[str, Any]:
    payload = copy_payload(row.payload)
    payload.update(
        {
            "id": row.id,
            "title": row.title,
            "productId": row.product_id or "",
            "type": row.asset_type,
            "url": row.url,
            "filePath": row.file_path,
            "status": row.status,
            "createdAt": iso_dt(row.created_at),
            "updatedAt": iso_dt(row.updated_at),
        }
    )
    return payload


def announcement_to_dict(row: Announcement) -> dict[str, Any]:
    payload = copy_payload(row.payload)
    payload.update(
        {
            "id": row.id,
            "title": row.title,
            "body": row.body,
            "placement": row.placement,
            "priority": row.priority,
            "ctaLabel": row.cta_label,
            "ctaUrl": row.cta_url,
            "imageUrl": row.image_url,
            "startsAt": row.starts_at,
            "endsAt": row.ends_at,
            "status": row.status,
            "createdAt": iso_dt(row.created_at),
            "updatedAt": iso_dt(row.updated_at),
        }
    )
    return payload


def stock_movement_to_dict(row: StockMovement) -> dict[str, Any]:
    payload = copy_payload(row.payload)
    payload.update(
        {
            "id": row.id,
            "productId": row.product_id,
            "sku": row.sku,
            "type": row.movement_type,
            "quantity": row.quantity,
            "note": row.note,
            "createdBy": row.created_by,
            "createdAt": iso_dt(row.created_at),
        }
    )
    return payload


def order_to_dict(row: Order) -> dict[str, Any]:
    payload = copy_payload(row.payload)
    payload.update(
        {
            "id": row.id,
            "orderId": row.order_number,
            "customerId": row.customer_id,
            "customer": row.customer_snapshot or {},
            "items": row.items or [],
            "status": row.status,
            "creditStatus": row.credit_status,
            "paymentStatus": row.payment_status,
            "totalUsd": row.total_usd,
            "totalVes": row.total_ves,
            "exchangeRateUsdVes": row.exchange_rate_usd_ves,
            "paidUsd": row.paid_usd,
            "balanceUsd": row.balance_usd,
            "creditBeforeUsd": row.credit_before_usd,
            "creditAfterUsd": row.credit_after_usd,
            "inventoryStatus": row.inventory_status,
            "stockStatus": row.stock_status,
            "managedBy": row.managed_by,
            "managedAt": row.managed_at,
            "statusHistory": row.status_history or [],
            "createdAt": iso_dt(row.created_at),
            "updatedAt": iso_dt(row.updated_at),
        }
    )
    return payload


def credit_movement_to_dict(row: CreditMovement) -> dict[str, Any]:
    payload = copy_payload(row.payload)
    payload.update(
        {
            "id": row.id,
            "movementType": row.movement_type,
            "clientId": row.client_id,
            "orderId": row.order_id,
            "amountUsd": row.amount_usd,
            "amountVes": row.amount_ves,
            "exchangeRateUsdVes": row.exchange_rate_usd_ves,
            "method": row.method,
            "reference": row.reference,
            "note": row.note,
            "createdBy": row.created_by,
            "createdAt": iso_dt(row.created_at),
        }
    )
    return payload


def load_sql_store() -> dict[str, list[dict[str, Any]]]:
    init_database()
    with SessionLocal() as session:
        return {
            "admin_users": [
                admin_user_to_dict(row)
                for row in session.query(AdminUser).filter(AdminUser.status != "deleted").all()
            ],
            "clients": [
                client_to_dict(row)
                for row in session.query(Client).filter(Client.status != "deleted").all()
            ],
            "categories": [
                category_to_dict(row)
                for row in session.query(Category).filter(Category.status != "deleted").all()
            ],
            "products": [
                product_to_dict(row)
                for row in session.query(Product).filter(Product.status != "deleted").all()
            ],
            "media_assets": [
                media_asset_to_dict(row)
                for row in session.query(MediaAsset).filter(MediaAsset.status != "deleted").all()
            ],
            "announcements": [
                announcement_to_dict(row)
                for row in session.query(Announcement).filter(Announcement.status != "deleted").all()
            ],
            "stock_movements": [stock_movement_to_dict(row) for row in session.query(StockMovement).all()],
            "orders": [order_to_dict(row) for row in session.query(Order).all()],
            "credit_movements": [credit_movement_to_dict(row) for row in session.query(CreditMovement).all()],
        }


def sync_store_to_sql(store: dict[str, list[dict[str, Any]]]) -> None:
    init_database()
    with SessionLocal() as session:
        sync_admin_users(session, store)
        sync_clients(session, store)
        sync_categories(session, store)
        sync_products(session, store)
        sync_media_assets(session, store)
        sync_announcements(session, store)
        sync_stock_movements(session, store)
        sync_orders(session, store)
        sync_credit_movements(session, store)
        session.commit()


def sync_admin_users(session, store: dict[str, Any]) -> None:
    live_ids: set[str] = set()
    for user in store.get("admin_users", []):
        object_id = user["id"]
        live_ids.add(object_id)
        upsert(
            session,
            AdminUser,
            object_id,
            {
                "id": object_id,
                "name": user.get("name", ""),
                "email": user.get("email", "").lower(),
                "password_hash": user.get("passwordHash", ""),
                "role": user.get("role", "operator"),
                "status": user.get("status", "active"),
                "last_login_at": parse_dt(user.get("lastLoginAt")) if user.get("lastLoginAt") else None,
                "created_at": parse_dt(user.get("createdAt")),
                "updated_at": parse_dt(user.get("updatedAt")),
                "payload": user,
            },
        )
    soft_prune(session, AdminUser, live_ids)


def sync_clients(session, store: dict[str, Any]) -> None:
    live_ids: set[str] = set()
    for client in store.get("clients", []):
        object_id = client["id"]
        live_ids.add(object_id)
        upsert(
            session,
            Client,
            object_id,
            {
                "id": object_id,
                "business_name": client.get("businessName", ""),
                "tax_id": client.get("taxId", ""),
                "contact_name": client.get("contactName", ""),
                "phone": client.get("phone", ""),
                "email": client.get("email", "").lower(),
                "password_hash": client.get("passwordHash", ""),
                "client_type": client.get("clientType", "ferretero"),
                "status": client.get("status", "active"),
                "credit_enabled": bool(client.get("creditEnabled")),
                "credit_limit_usd": float(client.get("creditLimitUsd") or 0),
                "credit_used_usd": float(client.get("creditUsedUsd") or 0),
                "payment_terms_days": int(client.get("paymentTermsDays") or 0),
                "notes": client.get("notes", ""),
                "created_at": parse_dt(client.get("createdAt")),
                "updated_at": parse_dt(client.get("updatedAt")),
                "payload": client,
            },
        )
    soft_prune(session, Client, live_ids)


def sync_categories(session, store: dict[str, Any]) -> None:
    live_ids: set[str] = set()
    for category in store.get("categories", []):
        object_id = category["id"]
        live_ids.add(object_id)
        upsert(
            session,
            Category,
            object_id,
            {
                "id": object_id,
                "name": category.get("name", ""),
                "description": category.get("description", ""),
                "image_url": category.get("imageUrl", ""),
                "status": category.get("status", "active"),
                "created_at": parse_dt(category.get("createdAt")),
                "updated_at": parse_dt(category.get("updatedAt")),
                "payload": category,
            },
        )
    soft_prune(session, Category, live_ids)


def ensure_category_for_product(session, product: dict[str, Any]) -> None:
    category_id = product.get("categoryId", "uncategorized") or "uncategorized"
    if session.get(Category, category_id):
        return

    session.add(
        Category(
            id=category_id,
            name=product.get("categoryName") or "Sin categoria",
            description="Categoria creada automaticamente para mantener integridad de productos.",
            image_url="",
            status="active",
            payload={},
        )
    )


def sync_products(session, store: dict[str, Any]) -> None:
    live_ids: set[str] = set()
    for product in store.get("products", []):
        ensure_category_for_product(session, product)
        object_id = product["id"]
        live_ids.add(object_id)
        upsert(
            session,
            Product,
            object_id,
            {
                "id": object_id,
                "sku": product.get("sku", ""),
                "title": product.get("title", ""),
                "description": product.get("description", ""),
                "product_type": product.get("productType", "machine"),
                "category_id": product.get("categoryId", "uncategorized") or "uncategorized",
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
            },
        )
    soft_prune(session, Product, live_ids)


def sync_media_assets(session, store: dict[str, Any]) -> None:
    live_ids: set[str] = set()
    for asset in store.get("media_assets", []):
        object_id = asset["id"]
        live_ids.add(object_id)
        upsert(
            session,
            MediaAsset,
            object_id,
            {
                "id": object_id,
                "title": asset.get("title", ""),
                "product_id": asset.get("productId") or None,
                "asset_type": asset.get("type", asset.get("assetType", "image")),
                "url": asset.get("url", asset.get("fileUrl", "")),
                "file_path": asset.get("filePath", ""),
                "status": asset.get("status", "active"),
                "created_at": parse_dt(asset.get("createdAt")),
                "updated_at": parse_dt(asset.get("updatedAt")),
                "payload": asset,
            },
        )
    soft_prune(session, MediaAsset, live_ids)


def sync_announcements(session, store: dict[str, Any]) -> None:
    live_ids: set[str] = set()
    for announcement in store.get("announcements", []):
        object_id = announcement["id"]
        live_ids.add(object_id)
        upsert(
            session,
            Announcement,
            object_id,
            {
                "id": object_id,
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
            },
        )
    soft_prune(session, Announcement, live_ids)


def sync_stock_movements(session, store: dict[str, Any]) -> None:
    for movement in store.get("stock_movements", []):
        object_id = movement["id"]
        upsert(
            session,
            StockMovement,
            object_id,
            {
                "id": object_id,
                "product_id": movement.get("productId", ""),
                "sku": movement.get("sku", ""),
                "movement_type": movement.get("type", movement.get("movementType", "adjustment")),
                "quantity": int(movement.get("quantity") or 0),
                "note": movement.get("note", ""),
                "created_by": movement.get("createdBy", ""),
                "created_at": parse_dt(movement.get("createdAt")),
                "payload": movement,
            },
        )


def ensure_client_for_order(session, order: dict[str, Any]) -> str:
    customer_id = order.get("customerId") or "client-guest"
    if session.get(Client, customer_id):
        return customer_id

    customer = order.get("customer") or {}
    session.add(
        Client(
            id=customer_id,
            business_name=customer.get("name") or "Cliente invitado",
            tax_id="",
            contact_name="",
            phone="",
            email=f"{customer_id}@wulkan.local",
            password_hash="",
            client_type="guest",
            status="active",
            credit_enabled=False,
            credit_limit_usd=0.0,
            credit_used_usd=0.0,
            payment_terms_days=0,
            notes="Cliente creado automaticamente por una orden sin cuenta B2B.",
            payload=customer,
        )
    )
    return customer_id


def sync_orders(session, store: dict[str, Any]) -> None:
    for order in store.get("orders", []):
        customer_id = ensure_client_for_order(session, order)
        object_id = order["id"]
        upsert(
            session,
            Order,
            object_id,
            {
                "id": object_id,
                "order_number": order.get("orderId", object_id),
                "customer_id": customer_id,
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
            },
        )


def sync_credit_movements(session, store: dict[str, Any]) -> None:
    for movement in store.get("credit_movements", []):
        object_id = movement["id"]
        if not movement.get("clientId") or not movement.get("orderId"):
            continue
        upsert(
            session,
            CreditMovement,
            object_id,
            {
                "id": object_id,
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
            },
        )
