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
INSECURE_PRODUCTION_CLIENT_EMAILS = {"ferreteria@wulkan.local"}
INSECURE_PRODUCTION_CATEGORY_IDS = {"machinery-garden", "spare-parts", "industrial"}
INSECURE_PRODUCTION_PRODUCT_IDS = {"prod-motosierra-45cc", "prod-cadena-18", "prod-motobomba-3x3"}
INSECURE_PRODUCTION_ANNOUNCEMENT_IDS = {"ann-home-launch", "ann-checkout-payment"}
INSECURE_PRODUCTION_SERVICE_TECHNICIAN_IDS = {"svc-caracas-central"}
INSECURE_PRODUCTION_STOCK_MOVEMENT_IDS = {"mov-001", "mov-002", "mov-003"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


DEFAULT_STORE: dict[str, list[dict[str, Any]]] = {
    "categories": [
        {
            "id": "machinery-garden",
            "name": "Maquinaria y jardin",
            "description": "Equipos Wulkan para jardin, bosque e industria.",
        },
        {
            "id": "spare-parts",
            "name": "Repuestos",
            "description": "Piezas y consumibles compatibles por SKU.",
        },
        {
            "id": "industrial",
            "name": "Industrial",
            "description": "Motobombas, compresores y soluciones de trabajo.",
        },
    ],
    "products": [
        {
            "id": "prod-motosierra-45cc",
            "sku": "WUL-MOT-45CC",
            "title": "Motosierra Wulkan 45cc",
            "description": "Equipo de corte para uso tecnico, finca y jardin.",
            "productType": "machine",
            "categoryId": "machinery-garden",
            "categoryName": "Maquinaria y jardin",
            "publicPriceUsd": 185.0,
            "originalPriceUsd": 215.0,
            "discountPercent": 14.0,
            "b2bPriceUsd": 162.0,
            "exchangeRateUsdVes": 38.5,
            "stock": 12,
            "reserved": 1,
            "status": "active",
            "imageUrl": "",
            "imageUrls": [],
            "variants": ["18 pulgadas", "20 pulgadas"],
            "specifications": {"Motor": "45cc", "Combustible": "Gasolina", "Garantia": "6 meses"},
            "requiresQuote": False,
            "requiresTechnicalValidation": False,
            "rotationLast30Days": 9,
            "createdAt": "2026-06-01T00:00:00Z",
            "updatedAt": "2026-06-01T00:00:00Z",
        },
        {
            "id": "prod-cadena-18",
            "sku": "WUL-REP-CAD18",
            "title": "Cadena 18 pulgadas compatible",
            "description": "Repuesto para motosierras seleccionadas Wulkan.",
            "productType": "spare_part",
            "categoryId": "spare-parts",
            "categoryName": "Repuestos",
            "publicPriceUsd": 18.0,
            "originalPriceUsd": 22.0,
            "discountPercent": 18.0,
            "b2bPriceUsd": 15.0,
            "exchangeRateUsdVes": 38.5,
            "stock": 4,
            "reserved": 1,
            "status": "active",
            "imageUrl": "",
            "imageUrls": [],
            "variants": ["18 pulgadas"],
            "specifications": {"Tipo": "Cadena", "Compatibilidad": "Motosierras Wulkan"},
            "requiresQuote": False,
            "requiresTechnicalValidation": True,
            "rotationLast30Days": 22,
            "createdAt": "2026-06-01T00:00:00Z",
            "updatedAt": "2026-06-01T00:00:00Z",
        },
        {
            "id": "prod-motobomba-3x3",
            "sku": "WUL-MB-3X3",
            "title": "Motobomba 3x3 alta presion Wulkan",
            "description": "Motobomba para trabajo agricola e industrial.",
            "productType": "machine",
            "categoryId": "industrial",
            "categoryName": "Industrial",
            "publicPriceUsd": 535.0,
            "originalPriceUsd": 579.0,
            "discountPercent": 8.0,
            "b2bPriceUsd": 498.0,
            "exchangeRateUsdVes": 38.5,
            "stock": 7,
            "reserved": 0,
            "status": "active",
            "imageUrl": "",
            "imageUrls": [],
            "variants": ["3x3", "Alta presion"],
            "specifications": {"Uso": "Agricola e industrial", "Categoria": "Motobombas"},
            "requiresQuote": False,
            "requiresTechnicalValidation": False,
            "rotationLast30Days": 5,
            "createdAt": "2026-06-01T00:00:00Z",
            "updatedAt": "2026-06-01T00:00:00Z",
        },
    ],
    "announcements": [
        {
            "id": "ann-home-launch",
            "title": "Wulkan Venezuela",
            "body": "Compra productos Wulkan en dolares con referencia en bolivares.",
            "placement": "home",
            "priority": 100,
            "ctaLabel": "Ver catalogo",
            "ctaUrl": "wulkan://catalog",
            "imageUrl": "",
            "startsAt": "2026-06-01T00:00:00Z",
            "endsAt": "",
            "status": "active",
            "updatedAt": "2026-06-08T00:00:00Z",
        },
        {
            "id": "ann-checkout-payment",
            "title": "Pago validado por Wulkan",
            "body": "Las ordenes pasan por revision antes del despacho.",
            "placement": "checkout",
            "priority": 70,
            "ctaLabel": "",
            "ctaUrl": "",
            "imageUrl": "",
            "startsAt": "2026-06-01T00:00:00Z",
            "endsAt": "",
            "status": "active",
            "updatedAt": "2026-06-08T00:00:00Z",
        },
    ],
    "orders": [],
    "admin_users": [
        {
            "id": "admin-wulkan",
            "name": "Admin Wulkan",
            "email": "admin@wulkan.local",
            "passwordHash": "scrypt:32768:8:1$y91vC95Hs86tuoF0$f10d66ce2f8aec290a8a47aa281794d6395bb64a67f91bebba05123a1dc2863d4fe665a3101ba5df712e037df2cbfe41169e51b986fe7f0f41d0419930e6328b",
            "role": "super_admin",
            "status": "active",
            "createdAt": "2026-06-08T00:00:00Z",
            "updatedAt": "2026-06-08T00:00:00Z",
        }
    ],
    "clients": [
        {
            "id": "client-ferreteria-valencia",
            "businessName": "Ferreteria Demo Valencia",
            "taxId": "J-00000000-1",
            "contactName": "Comprador principal",
            "phone": "+58 000-0000000",
            "email": "ferreteria@wulkan.local",
            "passwordHash": "scrypt:32768:8:1$QeRUz17axgHLtFdj$ecc66b9b14a2194d45ff972ae5a2a3b25a1813169a5d9308ea25ef0299c8662bf5c6acfaf1d98ef0b80f541fcc7627e21c49cf052f7c0dfbc24c2d9934f8e451",
            "clientType": "ferretero",
            "status": "active",
            "creditEnabled": True,
            "creditLimitUsd": 1000.0,
            "creditUsedUsd": 0.0,
            "paymentTermsDays": 15,
            "notes": "Cliente demo para flujo B2B con linea de credito.",
            "createdAt": "2026-06-08T00:00:00Z",
            "updatedAt": "2026-06-08T00:00:00Z",
        }
    ],
    "credit_movements": [],
    "service_technicians": [
        {
            "id": "svc-caracas-central",
            "name": "Servicio tecnico autorizado Caracas",
            "companyName": "Wulkan Servicio Caracas",
            "contactName": "Coordinador tecnico",
            "phone": "+58 000-0000000",
            "whatsapp": "+58 000-0000000",
            "email": "servicio.caracas@wulkan.local",
            "state": "Distrito Capital",
            "city": "Caracas",
            "address": "Direccion por confirmar",
            "specialties": ["Motosierras", "Motobombas", "Repuestos"],
            "coverage": "Caracas y zona central",
            "status": "active",
            "visibleInApp": True,
            "notes": "Registro demo para directorio de servicios tecnicos.",
            "createdAt": "2026-06-09T00:00:00Z",
            "updatedAt": "2026-06-09T00:00:00Z",
        }
    ],
    "audit_events": [],
    "media_assets": [],
    "stock_movements": [
        {
            "id": "mov-001",
            "productId": "prod-cadena-18",
            "sku": "WUL-REP-CAD18",
            "type": "sale",
            "quantity": 22,
            "createdAt": "2026-06-01T00:00:00Z",
        },
        {
            "id": "mov-002",
            "productId": "prod-motosierra-45cc",
            "sku": "WUL-MOT-45CC",
            "type": "sale",
            "quantity": 9,
            "createdAt": "2026-06-01T00:00:00Z",
        },
        {
            "id": "mov-003",
            "productId": "prod-motobomba-3x3",
            "sku": "WUL-MB-3X3",
            "type": "sale",
            "quantity": 5,
            "createdAt": "2026-06-01T00:00:00Z",
        },
    ],
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
    sanitized["clients"] = [
        client
        for client in sanitized.get("clients", [])
        if client.get("email", "").strip().lower() not in INSECURE_PRODUCTION_CLIENT_EMAILS
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
        if movement.get("id", "").strip().lower() not in INSECURE_PRODUCTION_STOCK_MOVEMENT_IDS
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
