from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import Config


DATA_DIR = Path(__file__).resolve().parent / "data"
STORE_PATH = DATA_DIR / "wulkan_store.json"
SQL_BACKEND_NAMES = {"sql", "database", "db"}
PRODUCTION_ENV_NAME = "production"
INSECURE_PRODUCTION_ADMIN_EMAILS = {"admin@wulkan.local"}
INSECURE_PRODUCTION_CLIENT_IDS = {"client-ferreteria-valencia"}
INSECURE_PRODUCTION_CLIENT_EMAILS = {"ferreteria@wulkan.local"}
INSECURE_PRODUCTION_ORDER_PREFIXES = ("ord-mobile-checkout-",)
INSECURE_PRODUCTION_CATEGORY_IDS = {"machinery-garden", "spare-parts", "industrial"}
INSECURE_PRODUCTION_PRODUCT_IDS = {"prod-motosierra-45cc", "prod-cadena-18", "prod-motobomba-3x3"}
INSECURE_PRODUCTION_ANNOUNCEMENT_IDS = {"ann-home-launch", "ann-checkout-payment"}
INSECURE_PRODUCTION_SERVICE_TECHNICIAN_IDS = {"svc-caracas-central"}
INSECURE_PRODUCTION_STOCK_MOVEMENT_IDS = {"mov-001", "mov-002", "mov-003"}
INSECURE_PRODUCTION_TEXT_MARKERS = ("demo", "@wulkan.local")


def has_insecure_production_marker(*values: Any) -> bool:
    text = " ".join(str(value or "").strip().lower() for value in values)
    return any(marker in text for marker in INSECURE_PRODUCTION_TEXT_MARKERS)


def is_insecure_production_client(client: dict[str, Any]) -> bool:
    email = client.get("email", "").strip().lower()
    client_id = client.get("id", "").strip().lower()
    business_name = client.get("businessName", "").strip().lower()
    return (
        client_id in INSECURE_PRODUCTION_CLIENT_IDS
        or email in INSECURE_PRODUCTION_CLIENT_EMAILS
        or email.endswith("@wulkan.local")
        or has_insecure_production_marker(business_name, email)
    )


def is_insecure_production_order(order: dict[str, Any], removed_client_ids: set[str]) -> bool:
    order_id = str(order.get("id", "") or "")
    order_number = str(order.get("orderId", "") or "")
    customer = order.get("customer") or {}
    customer_name = str(customer.get("name", "")).strip().lower()
    customer_email = str(customer.get("email", "")).strip().lower()
    return (
        order.get("customerId", "").strip().lower() in removed_client_ids
        or any(order_id.startswith(prefix) or order_number.startswith(prefix) for prefix in INSECURE_PRODUCTION_ORDER_PREFIXES)
        or has_insecure_production_marker(order_id, order_number, customer_name, customer_email)
    )


def is_insecure_production_stock_movement(movement: dict[str, Any]) -> bool:
    note = movement.get("note", "")
    movement_id = movement.get("id", "").strip().lower()
    product_id = movement.get("productId", "").strip().lower()
    return (
        movement_id in INSECURE_PRODUCTION_STOCK_MOVEMENT_IDS
        or product_id in INSECURE_PRODUCTION_PRODUCT_IDS
        or any(str(note).startswith(prefix) or prefix in str(note) for prefix in INSECURE_PRODUCTION_ORDER_PREFIXES)
        or has_insecure_production_marker(note, movement.get("createdBy", ""))
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


DEFAULT_STORE: dict[str, list[dict[str, Any]]] = {
    "categories": [],
    "products": [],
    "announcements": [],
    "orders": [],
    "admin_users": [],
    "clients": [],
    "credit_movements": [],
    "service_technicians": [],
    "audit_events": [],
    "media_assets": [],
    "stock_movements": [],
}


def ensure_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_PATH.exists():
        save_json_store(deepcopy(DEFAULT_STORE))


def use_sql_backend() -> bool:
    return str(Config.DATA_BACKEND).strip().lower() in SQL_BACKEND_NAMES


def is_production() -> bool:
    return str(Config.ENV).strip().lower() == PRODUCTION_ENV_NAME


def production_safe_seed(store: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    if not is_production():
        return store

    sanitized = deepcopy(store)
    sanitized["admin_users"] = [
        user
        for user in sanitized.get("admin_users", [])
        if user.get("email", "").strip().lower() not in INSECURE_PRODUCTION_ADMIN_EMAILS
    ]
    removed_client_ids = {
        client.get("id", "").strip().lower()
        for client in sanitized.get("clients", [])
        if is_insecure_production_client(client)
    }
    sanitized["clients"] = [
        client for client in sanitized.get("clients", []) if not is_insecure_production_client(client)
    ]
    sanitized["orders"] = [
        order
        for order in sanitized.get("orders", [])
        if not is_insecure_production_order(order, removed_client_ids)
    ]
    sanitized["credit_movements"] = [
        movement
        for movement in sanitized.get("credit_movements", [])
        if movement.get("clientId", "").strip().lower() not in removed_client_ids
        and not any(
            movement.get("orderId", "").startswith(prefix)
            for prefix in INSECURE_PRODUCTION_ORDER_PREFIXES
        )
    ]
    sanitized["categories"] = [
        category
        for category in sanitized.get("categories", [])
        if category.get("id", "").strip().lower() not in INSECURE_PRODUCTION_CATEGORY_IDS
    ]
    sanitized["products"] = [
        product
        for product in sanitized.get("products", [])
        if product.get("id", "").strip().lower() not in INSECURE_PRODUCTION_PRODUCT_IDS
    ]
    sanitized["announcements"] = [
        announcement
        for announcement in sanitized.get("announcements", [])
        if announcement.get("id", "").strip().lower() not in INSECURE_PRODUCTION_ANNOUNCEMENT_IDS
    ]
    sanitized["service_technicians"] = [
        technician
        for technician in sanitized.get("service_technicians", [])
        if technician.get("id", "").strip().lower() not in INSECURE_PRODUCTION_SERVICE_TECHNICIAN_IDS
    ]
    sanitized["stock_movements"] = [
        movement
        for movement in sanitized.get("stock_movements", [])
        if not is_insecure_production_stock_movement(movement)
    ]
    return sanitized


def default_collection(name: str) -> list[dict[str, Any]]:
    if is_production() and name in {"admin_users", "clients"}:
        return []
    return deepcopy(DEFAULT_STORE[name])


def load_json_store() -> dict[str, list[dict[str, Any]]]:
    ensure_store()
    with STORE_PATH.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    store = deepcopy(DEFAULT_STORE)
    store.update(payload)
    normalize_store(store)
    return store


def load_store() -> dict[str, list[dict[str, Any]]]:
    if use_sql_backend():
        try:
            from sql_store import load_sql_store, sync_store_to_sql

            store = load_sql_store()
            if not store.get("admin_users") and not store.get("products"):
                sync_store_to_sql(production_safe_seed(load_json_store()))
                store = load_sql_store()
            if is_production():
                store = production_safe_seed(store)
            normalize_store(store)
            return store
        except Exception:
            if not Config.SQL_FALLBACK_TO_JSON:
                raise

    return load_json_store()


def normalize_store(store: dict[str, list[dict[str, Any]]]) -> None:
    store.setdefault("media_assets", [])
    store.setdefault("admin_users", default_collection("admin_users"))
    store.setdefault("clients", default_collection("clients"))
    store.setdefault("credit_movements", [])
    store.setdefault("service_technicians", [])
    store.setdefault("audit_events", [])
    for admin_user in store.get("admin_users", []):
        admin_user.setdefault("name", admin_user.get("email", "Usuario admin"))
        admin_user.setdefault("role", "operator")
        admin_user.setdefault("status", "active")
        admin_user.setdefault("mustChangePassword", False)
        admin_user.setdefault("sellerCode", "")
        admin_user.setdefault("sellerZone", "")
        admin_user.setdefault("phone", "")
        admin_user.setdefault("commissionRatePercent", 0.0)
        admin_user.setdefault("salesGoalUsd", 0.0)
        admin_user.setdefault("createdAt", utc_now())
        admin_user.setdefault("updatedAt", utc_now())
    for client in store.get("clients", []):
        client.setdefault("businessName", "Cliente ferretero")
        client.setdefault("taxId", "")
        client.setdefault("contactName", "")
        client.setdefault("phone", "")
        client.setdefault("email", "")
        client.setdefault("mustChangePassword", False)
        client.setdefault("clientType", "ferretero")
        client.setdefault("status", "active")
        client.setdefault("address", "")
        client.setdefault("state", "")
        client.setdefault("city", "")
        client.setdefault("deliveryZone", "")
        client.setdefault("assignedSellerId", "")
        client.setdefault("assignedSellerName", "")
        client.setdefault("defaultSaleType", "cash")
        client.setdefault("allowedPaymentTermsDays", [0])
        client.setdefault("creditRequestStatus", "none")
        client.setdefault("creditRequestedUsd", 0.0)
        client.setdefault("creditApprovedBy", "")
        client.setdefault("creditApprovedAt", "")
        client.setdefault("creditEnabled", False)
        client.setdefault("creditLimitUsd", 0.0)
        client.setdefault("creditUsedUsd", 0.0)
        client.setdefault("paymentTermsDays", 0)
        client.setdefault("notes", "")
        client.setdefault("createdAt", utc_now())
        client.setdefault("updatedAt", utc_now())
    for order in store.get("orders", []):
        order.setdefault("id", order.get("orderId", ""))
        order.setdefault("orderId", order.get("id", ""))
        order.setdefault("customerId", "")
        order.setdefault("customer", {"name": "Cliente Wulkan"})
        order.setdefault("items", [])
        order.setdefault("totalUsd", 0.0)
        order.setdefault("totalVes", 0.0)
        order.setdefault("exchangeRateUsdVes", 38.5)
        order.setdefault("saleType", "credit_line" if order.get("creditStatus") == "approved" else "cash")
        order.setdefault("paymentTermDays", 0)
        order.setdefault("dueDate", "")
        order.setdefault("sellerId", "")
        order.setdefault("sellerName", "")
        order.setdefault("salesChannel", "mobile")
        order.setdefault("createdById", "")
        order.setdefault("createdByName", "")
        order.setdefault("createdByRole", "")
        order.setdefault("commissionRatePercent", 0.0)
        order.setdefault("commissionUsd", 0.0)
        order.setdefault("commissionStatus", "commission_pending")
        order.setdefault("commissionPaidAt", "")
        order.setdefault("commissionPaidBy", "")
        order.setdefault("creditBeforeUsd", 0.0)
        order.setdefault("creditAfterUsd", 0.0)
        order.setdefault("creditStatus", "manual_review")
        order.setdefault("paidUsd", 0.0)
        order.setdefault("balanceUsd", order.get("totalUsd", 0.0))
        order.setdefault("paymentStatus", "pending")
        order.setdefault("status", "credit_review")
        if "inventoryStatus" not in order:
            order["inventoryStatus"] = "reserved" if order.get("status") in {"approved_with_credit", "preparing", "partial_paid", "paid"} else "pending"
        if "stockStatus" not in order:
            order["stockStatus"] = "reserved" if order.get("inventoryStatus") == "reserved" else order.get("inventoryStatus", "pending")
        order.setdefault("statusHistory", [])
        order.setdefault("createdAt", utc_now())
        order.setdefault("updatedAt", order.get("createdAt", utc_now()))
    for movement in store.get("credit_movements", []):
        movement.setdefault("movementType", "payment")
        movement.setdefault("clientId", "")
        movement.setdefault("orderId", "")
        movement.setdefault("amountUsd", 0.0)
        movement.setdefault("amountVes", 0.0)
        movement.setdefault("exchangeRateUsdVes", 38.5)
        movement.setdefault("method", "cash")
        movement.setdefault("reference", "")
        movement.setdefault("note", "")
        movement.setdefault("createdBy", "Admin")
        movement.setdefault("createdAt", utc_now())
    for technician in store.get("service_technicians", []):
        technician.setdefault("name", "")
        technician.setdefault("companyName", "")
        technician.setdefault("contactName", "")
        technician.setdefault("phone", "")
        technician.setdefault("whatsapp", "")
        technician.setdefault("email", "")
        technician.setdefault("state", "")
        technician.setdefault("city", "")
        technician.setdefault("address", "")
        technician.setdefault("specialties", [])
        technician.setdefault("coverage", "")
        technician.setdefault("status", "active")
        technician.setdefault("visibleInApp", True)
        technician.setdefault("notes", "")
        technician.setdefault("createdAt", utc_now())
        technician.setdefault("updatedAt", utc_now())
    for event in store.get("audit_events", []):
        event.setdefault("actorId", "")
        event.setdefault("actorName", "Sistema")
        event.setdefault("actorRole", "")
        event.setdefault("action", "")
        event.setdefault("entityType", "")
        event.setdefault("entityId", "")
        event.setdefault("detail", "")
        event.setdefault("ipAddress", "")
        event.setdefault("path", "")
        event.setdefault("method", "")
        event.setdefault("createdAt", utc_now())
    for product in store.get("products", []):
        product.setdefault("productType", "machine")
        product.setdefault("originalPriceUsd", product.get("publicPriceUsd", 0))
        product.setdefault("discountPercent", 0)
        product.setdefault("imageUrls", [product["imageUrl"]] if product.get("imageUrl") else [])
        product.setdefault("pdfUrls", [])
        product.setdefault("variants", [])
        product.setdefault("specifications", {})
        product.setdefault("reserved", 0)
    for category in store.get("categories", []):
        category.setdefault("imageUrl", "")
        category.setdefault("status", "active")


def save_json_store(store: dict[str, list[dict[str, Any]]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with STORE_PATH.open("w", encoding="utf-8") as file:
        json.dump(store, file, ensure_ascii=True, indent=2)


def save_store(store: dict[str, list[dict[str, Any]]]) -> None:
    if is_production():
        store = production_safe_seed(store)
    normalize_store(store)
    if use_sql_backend():
        try:
            from sql_store import sync_store_to_sql

            sync_store_to_sql(store)
            return
        except Exception:
            if not Config.SQL_FALLBACK_TO_JSON:
                raise

    save_json_store(store)


def slugify(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value)
    return "-".join(part for part in normalized.split("-") if part)


def next_id(prefix: str, seed: str) -> str:
    return f"{prefix}-{slugify(seed)}-{int(datetime.now(timezone.utc).timestamp())}"
