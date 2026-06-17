from __future__ import annotations

import json
import secrets
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import Config


DATA_DIR = Path(__file__).resolve().parent / "data"
STORE_PATH = DATA_DIR / "fventas_store.json"
SQL_BACKEND_NAMES = {"sql", "database", "db"}
PRODUCTION_ENV_NAME = "production"
INSECURE_PRODUCTION_ADMIN_EMAILS = {"admin@fventas.local"}
INSECURE_PRODUCTION_CLIENT_IDS = {"client-demo-b2b"}
INSECURE_PRODUCTION_CLIENT_EMAILS = {"cliente@fventas.local"}
INSECURE_PRODUCTION_ORDER_PREFIXES = ("ord-mobile-checkout-",)
INSECURE_PRODUCTION_CATEGORY_IDS = {"categoria-demo-1", "categoria-demo-2", "categoria-demo-3"}
INSECURE_PRODUCTION_PRODUCT_IDS = {"producto-demo-1", "producto-demo-2", "producto-demo-3"}
INSECURE_PRODUCTION_ANNOUNCEMENT_IDS = {"ann-home-launch", "ann-checkout-payment"}
INSECURE_PRODUCTION_SERVICE_TECHNICIAN_IDS = {"svc-demo-central"}
INSECURE_PRODUCTION_STOCK_MOVEMENT_IDS = {"mov-001", "mov-002", "mov-003"}
INSECURE_PRODUCTION_TEXT_MARKERS = (
    "demo",
    "@fventas.local",
)


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
        or email.endswith("@fventas.local")
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


DEFAULT_COMPANY_ID = "company-fventas-chile"
SAAS_PLAN_ID = "fventas-pro-monthly"
SAAS_PLAN_NAME = "FVENTAS Pro Mensual"
SAAS_PLAN_PRICE_CLP = 69990
TENANT_COLLECTIONS = (
    "categories",
    "products",
    "announcements",
    "orders",
    "quotes",
    "crm_records",
    "admin_users",
    "clients",
    "credit_movements",
    "notifications",
    "service_technicians",
    "audit_events",
    "media_assets",
    "stock_movements",
)


DEFAULT_STORE: dict[str, list[dict[str, Any]]] = {
    "companies": [],
    "subscriptions": [],
    "categories": [],
    "products": [],
    "announcements": [],
    "orders": [],
    "quotes": [],
    "crm_records": [],
    "admin_users": [],
    "clients": [],
    "credit_movements": [],
    "notifications": [],
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
            if not is_production() and not store.get("admin_users") and not store.get("products"):
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
    settings = store.setdefault("business_settings", {})
    settings.setdefault("companyName", "FVENTAS")
    settings.setdefault("companyLegalName", "FVENTAS")
    settings.setdefault("taxId", "")
    settings.setdefault("supportEmail", "soporte@fventas.cl")
    settings.setdefault("supportPhone", "")
    settings.setdefault("logoUrl", "")
    settings.setdefault("marketCountry", "CL")
    settings.setdefault("salesCurrency", settings.get("primaryCurrency") or "USD")
    settings.setdefault("localCurrency", settings.get("referenceCurrency") or "CLP")
    settings["salesCurrency"] = str(settings.get("salesCurrency") or "USD").upper()
    settings["localCurrency"] = str(settings.get("localCurrency") or "CLP").upper()
    settings.setdefault("primaryCurrency", settings["salesCurrency"])
    settings.setdefault("referenceCurrency", settings["localCurrency"])
    settings.setdefault("exchangeRateBaseToLocal", settings.get("exchangeRateUsdClp") or settings.get("exchangeRateUsdVes") or 950.0)
    settings.setdefault("exchangeRateUsdVes", settings.get("exchangeRateBaseToLocal", 950.0))
    settings.setdefault("exchangeRateUsdClp", settings.get("exchangeRateBaseToLocal", 950.0))
    settings.setdefault("defaultPaymentTermsDays", [0, 10, 15, 20, 30, 40])
    settings.setdefault("creditApprovalThresholdUsd", 0.0)
    settings.setdefault("overdueBlockDays", 15)
    settings.setdefault("defaultCommissionRule", "sale_generated")
    settings.setdefault("defaultCommissionPercent", 0.0)
    settings.setdefault("stockMinDefault", 1)
    settings.setdefault("maxUploadMb", 10)
    settings.setdefault("quoteFooterText", "Precios sujetos a disponibilidad y validacion comercial FVENTAS.")
    settings.setdefault("orderTermsText", "Pedidos sujetos a validacion de stock, credito y despacho.")
    settings.setdefault("notificationEmails", [])
    settings.setdefault("createdAt", utc_now())
    settings.setdefault("updatedAt", utc_now())
    store.setdefault("companies", [])
    store.setdefault("subscriptions", [])
    if not store["companies"]:
        store["companies"].append(
            {
                "id": DEFAULT_COMPANY_ID,
                "name": settings["companyName"],
                "legalName": settings.get("companyLegalName", ""),
                "taxId": settings.get("taxId", ""),
                "country": settings.get("marketCountry", "CL"),
                "status": "active",
                "ownerEmail": settings.get("supportEmail", "soporte@fventas.cl"),
                "supportEmail": settings.get("supportEmail", ""),
                "supportPhone": settings.get("supportPhone", ""),
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )
    for company in store["companies"]:
        company.setdefault("id", DEFAULT_COMPANY_ID)
        company.setdefault("name", company.get("companyName") or "Empresa FVENTAS")
        company.setdefault("legalName", company.get("name", "Empresa FVENTAS"))
        company.setdefault("taxId", "")
        company.setdefault("country", "CL")
        company.setdefault("status", "active")
        company.setdefault("ownerEmail", "")
        company.setdefault("supportEmail", company.get("ownerEmail", ""))
        company.setdefault("supportPhone", "")
        company.setdefault("createdAt", utc_now())
        company.setdefault("updatedAt", utc_now())
    default_company_id = store["companies"][0].get("id") or DEFAULT_COMPANY_ID
    if not any(subscription.get("companyId") == default_company_id for subscription in store["subscriptions"]):
        store["subscriptions"].append(
            {
                "id": f"sub-{default_company_id}",
                "companyId": default_company_id,
                "planId": SAAS_PLAN_ID,
                "planName": SAAS_PLAN_NAME,
                "priceClp": SAAS_PLAN_PRICE_CLP,
                "billingCycle": "monthly",
                "status": "active",
                "currentPeriodStart": utc_now(),
                "currentPeriodEnd": "",
                "paymentMethod": "external",
                "lastPaymentAt": "",
                "nextBillingAt": "",
                "notes": "Cuenta base FVENTAS habilitada.",
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )
    for subscription in store["subscriptions"]:
        subscription.setdefault("id", next_id("sub", subscription.get("companyId", default_company_id)))
        subscription.setdefault("companyId", default_company_id)
        subscription.setdefault("planId", SAAS_PLAN_ID)
        subscription.setdefault("planName", SAAS_PLAN_NAME)
        subscription.setdefault("priceClp", SAAS_PLAN_PRICE_CLP)
        subscription.setdefault("billingCycle", "monthly")
        subscription.setdefault("status", "pending_payment")
        subscription.setdefault("currentPeriodStart", "")
        subscription.setdefault("currentPeriodEnd", "")
        subscription.setdefault("paymentMethod", "external")
        subscription.setdefault("lastPaymentAt", "")
        subscription.setdefault("nextBillingAt", "")
        subscription.setdefault("notes", "")
        subscription.setdefault("createdAt", utc_now())
        subscription.setdefault("updatedAt", utc_now())
    store.setdefault("media_assets", [])
    for asset in store.get("media_assets", []):
        asset.setdefault("title", "Activo FVENTAS")
        asset.setdefault("assetType", asset.get("type", "image"))
        asset.setdefault("type", asset.get("assetType", "image"))
        asset.setdefault("productId", "")
        asset.setdefault("url", asset.get("fileUrl", ""))
        asset.setdefault("filePath", "")
        asset.setdefault("status", "active")
        asset.setdefault("documentType", "")
        asset.setdefault("subjectType", "product" if asset.get("productId") else "")
        asset.setdefault("subjectId", asset.get("productId", ""))
        asset.setdefault("subjectLabel", "")
        asset.setdefault("visibility", "internal")
        asset.setdefault("expiresAt", "")
        asset.setdefault("notes", "")
        asset.setdefault("createdById", "")
        asset.setdefault("createdByName", "")
        asset.setdefault("createdAt", utc_now())
        asset.setdefault("updatedAt", asset.get("createdAt", utc_now()))
    store.setdefault("admin_users", default_collection("admin_users"))
    store.setdefault("clients", default_collection("clients"))
    store.setdefault("credit_movements", [])
    store.setdefault("notifications", [])
    for notification in store.get("notifications", []):
        notification.setdefault("title", "Notificacion FVENTAS")
        notification.setdefault("body", "")
        notification.setdefault("type", notification.get("notificationType", "info"))
        notification.setdefault("notificationType", notification.get("type", "info"))
        notification.setdefault("channel", "web")
        notification.setdefault("priority", "normal")
        notification.setdefault("status", "unread")
        notification.setdefault("recipientType", "admin")
        notification.setdefault("recipientId", "")
        notification.setdefault("recipientRole", "")
        notification.setdefault("module", "dashboard")
        notification.setdefault("entityType", "")
        notification.setdefault("entityId", "")
        notification.setdefault("href", "")
        notification.setdefault("deepLink", "")
        notification.setdefault("readAt", "")
        notification.setdefault("expiresAt", "")
        notification.setdefault("metadata", {})
        notification.setdefault("createdAt", utc_now())
        notification.setdefault("updatedAt", notification.get("createdAt", utc_now()))
    store.setdefault("service_technicians", [])
    store.setdefault("audit_events", [])
    for admin_user in store.get("admin_users", []):
        admin_user.setdefault("companyId", default_company_id)
        admin_user.setdefault("name", admin_user.get("email", "Usuario admin"))
        admin_user.setdefault("role", "operator")
        admin_user.setdefault("status", "active")
        admin_user.setdefault("mustChangePassword", False)
        admin_user.setdefault("sellerCode", "")
        admin_user.setdefault("sellerZone", "")
        admin_user.setdefault("sellerTerritory", "")
        admin_user.setdefault("sellerSupervisor", "")
        admin_user.setdefault("phone", "")
        admin_user.setdefault("commissionRatePercent", 0.0)
        admin_user.setdefault("salesGoalUsd", 0.0)
        admin_user.setdefault("hiredAt", "")
        admin_user.setdefault("mobileAccessEnabled", True)
        admin_user.setdefault("lastMobileLoginAt", "")
        admin_user.setdefault("createdAt", utc_now())
        admin_user.setdefault("updatedAt", utc_now())
    for client in store.get("clients", []):
        client.setdefault("companyId", default_company_id)
        client.setdefault("businessName", "Cliente B2B")
        client.setdefault("taxId", "")
        client.setdefault("contactName", "")
        client.setdefault("phone", "")
        client.setdefault("email", "")
        client.setdefault("mustChangePassword", False)
        client.setdefault("clientType", "b2b")
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
        client.setdefault("creditReviewedBy", "")
        client.setdefault("creditReviewedAt", "")
        client.setdefault("creditManagerNote", "")
        client.setdefault("creditScore", 0)
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
        order.setdefault("customer", {"name": "Cliente FVENTAS"})
        order.setdefault("items", [])
        order.setdefault("grossUsd", order.get("totalUsd", 0.0))
        order.setdefault("discountUsd", 0.0)
        order.setdefault("netUsd", order.get("totalUsd", 0.0))
        order.setdefault("totalUsd", 0.0)
        order.setdefault("totalVes", 0.0)
        order.setdefault("exchangeRateUsdVes", 950.0)
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
        order.setdefault("commissionBaseUsd", order.get("netUsd", order.get("totalUsd", 0.0)))
        order.setdefault("commissionUsd", 0.0)
        order.setdefault("commissionStatus", "commission_pending")
        order.setdefault("commissionRule", "sale_generated")
        order.setdefault("commissionGeneratedAt", order.get("createdAt", ""))
        order.setdefault("commissionApprovedAt", "")
        order.setdefault("commissionApprovedBy", "")
        order.setdefault("commissionPaidAt", "")
        order.setdefault("commissionPaidBy", "")
        order.setdefault("commissionObservation", "")
        order.setdefault("commissionHoldReason", "")
        order.setdefault("creditBeforeUsd", 0.0)
        order.setdefault("creditAfterUsd", 0.0)
        order.setdefault("creditStatus", "manual_review")
        order.setdefault("paidUsd", 0.0)
        order.setdefault("balanceUsd", order.get("totalUsd", 0.0))
        order.setdefault("paymentStatus", "pending")
        order.setdefault("collectionStatus", "")
        order.setdefault("collectionOwner", "")
        order.setdefault("lastCollectionActionAt", "")
        order.setdefault("nextCollectionActionAt", "")
        order.setdefault("paymentPromiseAt", "")
        order.setdefault("collectionComment", "")
        order.setdefault("dispatchStatus", "pending")
        order.setdefault("receiverName", "")
        order.setdefault("receiverPhone", "")
        order.setdefault("carrierName", "")
        order.setdefault("trackingNumber", "")
        order.setdefault("estimatedDispatchAt", "")
        order.setdefault("dispatchedAt", "")
        order.setdefault("estimatedDeliveryAt", "")
        order.setdefault("deliveredAt", "")
        order.setdefault("deliveryEvidenceUrl", "")
        order.setdefault("logisticsNote", "")
        order.setdefault("logisticsOwner", "")
        order.setdefault("dispatchHistory", [])
        order.setdefault("invoiceStatus", "pending")
        order.setdefault("shippingAddress", "")
        order.setdefault("customerComment", "")
        order.setdefault("internalComment", order.get("notes", ""))
        order.setdefault("currentOwner", "Comercial")
        order.setdefault("status", "credit_review")
        if "inventoryStatus" not in order:
            order["inventoryStatus"] = "reserved" if order.get("status") in {"approved_with_credit", "preparing", "partial_paid", "paid"} else "pending"
        if "stockStatus" not in order:
            order["stockStatus"] = "reserved" if order.get("inventoryStatus") == "reserved" else order.get("inventoryStatus", "pending")
        order.setdefault("statusHistory", [])
        order.setdefault("createdAt", utc_now())
        order.setdefault("updatedAt", order.get("createdAt", utc_now()))
    store.setdefault("quotes", [])
    for quote in store.get("quotes", []):
        quote.setdefault("id", quote.get("quoteNumber", ""))
        quote.setdefault("quoteNumber", quote.get("id", ""))
        quote.setdefault("clientId", "")
        quote.setdefault("client", {"name": "Cliente FVENTAS"})
        quote.setdefault("sellerId", "")
        quote.setdefault("sellerName", "")
        quote.setdefault("items", [])
        quote.setdefault("grossUsd", quote.get("totalUsd", 0.0))
        quote.setdefault("discountUsd", 0.0)
        quote.setdefault("totalUsd", 0.0)
        quote.setdefault("totalVes", 0.0)
        quote.setdefault("exchangeRateUsdVes", 950.0)
        quote.setdefault("saleType", "cash")
        quote.setdefault("paymentTermDays", 0)
        quote.setdefault("validUntil", "")
        quote.setdefault("status", "draft")
        quote.setdefault("comment", "")
        quote.setdefault("internalComment", "")
        quote.setdefault("version", 1)
        quote.setdefault("versions", [])
        quote.setdefault("history", [])
        quote.setdefault("convertedOrderId", "")
        quote.setdefault("sentAt", "")
        quote.setdefault("viewedAt", "")
        quote.setdefault("acceptedAt", "")
        quote.setdefault("rejectedAt", "")
        quote.setdefault("createdById", "")
        quote.setdefault("createdByName", "")
        quote.setdefault("createdAt", utc_now())
        quote.setdefault("updatedAt", quote.get("createdAt", utc_now()))
    store.setdefault("crm_records", [])
    for record in store.get("crm_records", []):
        record.setdefault("id", "")
        record.setdefault("title", "Oportunidad comercial")
        record.setdefault("recordType", "lead")
        record.setdefault("pipelineStage", "new_lead")
        record.setdefault("status", "active")
        record.setdefault("clientId", "")
        record.setdefault("clientName", "")
        record.setdefault("sellerId", "")
        record.setdefault("sellerName", "")
        record.setdefault("contactName", "")
        record.setdefault("phone", "")
        record.setdefault("email", "")
        record.setdefault("state", "")
        record.setdefault("city", "")
        record.setdefault("source", "")
        record.setdefault("estimatedValueUsd", 0.0)
        record.setdefault("probabilityPercent", 0)
        record.setdefault("expectedCloseAt", "")
        record.setdefault("nextActionAt", "")
        record.setdefault("lastActivityAt", "")
        record.setdefault("description", "")
        record.setdefault("lossReason", "")
        record.setdefault("activities", [])
        record.setdefault("createdById", "")
        record.setdefault("createdByName", "")
        record.setdefault("createdAt", utc_now())
        record.setdefault("updatedAt", record.get("createdAt", utc_now()))
    for movement in store.get("credit_movements", []):
        movement.setdefault("movementType", "payment")
        movement.setdefault("clientId", "")
        movement.setdefault("orderId", "")
        movement.setdefault("amountUsd", 0.0)
        movement.setdefault("amountVes", 0.0)
        movement.setdefault("exchangeRateUsdVes", 950.0)
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
        product.setdefault("internalCode", "")
        product.setdefault("brand", "FVENTAS")
        product.setdefault("model", "")
        product.setdefault("subCategory", "")
        product.setdefault("unitOfSale", "unidad")
        product.setdefault("shortDescription", product.get("description", ""))
        product.setdefault("longDescription", product.get("description", ""))
        product.setdefault("productType", "machine")
        product.setdefault("originalPriceUsd", product.get("publicPriceUsd", 0))
        product.setdefault("discountPercent", 0)
        product.setdefault("costReferenceUsd", 0.0)
        product.setdefault("marginPercent", 0.0)
        product.setdefault("minimumStock", 0)
        product.setdefault("maximumStock", 0)
        product.setdefault("replenishmentQty", 0)
        product.setdefault("stockLocation", "")
        product.setdefault("stockNotes", "")
        product.setdefault("lastStockMovementAt", "")
        product.setdefault("lastStockMovementBy", "")
        product.setdefault("lastStockMovementType", "")
        product.setdefault("lastStockMovementNote", "")
        product.setdefault("imageUrls", [product["imageUrl"]] if product.get("imageUrl") else [])
        product.setdefault("pdfUrls", [])
        product.setdefault("variants", [])
        product.setdefault("specifications", {})
        product.setdefault("relatedSkus", [])
        product.setdefault("visibleInApp", product.get("status", "active") == "active")
        product.setdefault("featured", False)
        product.setdefault("onSale", bool(product.get("discountPercent", 0)))
        product.setdefault("reserved", 0)
    for movement in store.get("stock_movements", []):
        movement.setdefault("productId", "")
        movement.setdefault("sku", "")
        movement.setdefault("type", movement.get("movementType", "adjustment"))
        movement.setdefault("quantity", 0)
        movement.setdefault("beforeStock", "")
        movement.setdefault("afterStock", "")
        movement.setdefault("location", "")
        movement.setdefault("orderId", "")
        movement.setdefault("note", "")
        movement.setdefault("createdBy", "Sistema")
        movement.setdefault("createdAt", utc_now())
    for category in store.get("categories", []):
        category.setdefault("imageUrl", "")
        category.setdefault("slug", str(category.get("id") or category.get("name", "")).strip().lower().replace(" ", "-"))
        category.setdefault("description", "")
        category.setdefault("icon", "bi-tags")
        category.setdefault("sortOrder", 0)
        category.setdefault("status", "active")
        category.setdefault("visibleInApp", category.get("status", "active") == "active")
        category.setdefault("parentId", "")
        category.setdefault("createdAt", utc_now())
        category.setdefault("updatedAt", utc_now())
        if category.get("status") != "active":
            category["visibleInApp"] = False

    for collection_name in TENANT_COLLECTIONS:
        for item in store.get(collection_name, []):
            if isinstance(item, dict):
                item.setdefault("companyId", default_company_id)


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
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}-{slugify(seed)}-{timestamp}-{secrets.token_hex(3)}"
