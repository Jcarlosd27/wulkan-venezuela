from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Any

from werkzeug.security import generate_password_hash as werkzeug_generate_password_hash


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from store import DEFAULT_COMPANY_ID, SAAS_PLAN_ID, SAAS_PLAN_NAME, SAAS_PLAN_PRICE_CLP, load_store, save_store, utc_now


LEGAL_TERMS_VERSION = "2026-06-17"
LEGAL_PRIVACY_VERSION = "2026-06-17"
PASSWORD_MIN_LENGTH = 10
ALLOWED_MARKET_COUNTRIES = {"CL", "VE"}

STARTER_CATEGORY_IMAGES = {
    "machinery-garden": "/static/uploads/catalog/fventas-product.svg",
    "spare-parts": "/static/uploads/catalog/fventas-product.svg",
    "services": "/static/uploads/catalog/fventas-product.svg",
}
STARTER_CATEGORIES = [
    {
        "id": "cat-machinery-garden",
        "name": "Maquinaria y jardin",
        "slug": "maquinaria-y-jardin",
        "description": "Equipos, accesorios y maquinaria comercial para terreno, obra y mantenimiento.",
        "icon": "bi-tools",
    },
    {
        "id": "cat-spare-parts",
        "name": "Repuestos",
        "slug": "repuestos",
        "description": "Piezas por SKU, modelo o compatibilidad para reposicion B2B.",
        "icon": "bi-gear",
    },
    {
        "id": "cat-services",
        "name": "Servicios tecnicos",
        "slug": "servicios-tecnicos",
        "description": "Soporte tecnico autorizado, mantenciones y validacion operativa.",
        "icon": "bi-wrench-adjustable",
    },
]
STARTER_PRODUCTS = [
    {
        "id": "prod-fvt-mot-45cc",
        "sku": "FVT-MOT-45CC",
        "title": "Motosierra FVENTAS 45cc",
        "categoryId": "cat-machinery-garden",
        "categoryName": "Maquinaria y jardin",
        "productType": "machine",
        "publicPriceUsd": 175750.0,
        "b2bPriceUsd": 153900.0,
        "originalPriceUsd": 175750.0,
        "discountPercent": 12.0,
        "stock": 12,
        "description": "Motosierra profesional para venta asistida, despacho y reposicion comercial.",
    },
    {
        "id": "prod-fvt-chain-18",
        "sku": "FVT-CHAIN-18",
        "title": "Cadena 18 pulgadas compatible",
        "categoryId": "cat-spare-parts",
        "categoryName": "Repuestos",
        "productType": "spare_part",
        "publicPriceUsd": 17100.0,
        "b2bPriceUsd": 14250.0,
        "originalPriceUsd": 17100.0,
        "discountPercent": 17.0,
        "stock": 24,
        "description": "Repuesto de alta rotacion para venta B2B por SKU y compatibilidad.",
    },
    {
        "id": "prod-fvt-pump-3x3",
        "sku": "FVT-PUMP-3X3",
        "title": "Motobomba 3x3 alta presion FVENTAS",
        "categoryId": "cat-machinery-garden",
        "categoryName": "Maquinaria y jardin",
        "productType": "machine",
        "publicPriceUsd": 508250.0,
        "b2bPriceUsd": 473100.0,
        "originalPriceUsd": 508250.0,
        "discountPercent": 7.0,
        "stock": 7,
        "description": "Equipo comercial para riego, drenaje y faena con stock visible en app.",
    },
]


def env_value(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    raw = env_value(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "fventas"


def password_errors(password: str) -> list[str]:
    errors: list[str] = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"Debe tener al menos {PASSWORD_MIN_LENGTH} caracteres.")
    if not any(char.isalpha() for char in password):
        errors.append("Debe incluir letras.")
    if not any(char.isdigit() for char in password):
        errors.append("Debe incluir numeros.")
    return errors


def generate_password_hash(password: str) -> str:
    method = "scrypt" if hasattr(hashlib, "scrypt") else "pbkdf2:sha256:1000000"
    return werkzeug_generate_password_hash(password, method=method)


def password_for_record(email: str, password: str, *, is_new: bool, reset_passwords: bool, no_input: bool) -> str:
    if is_new or reset_passwords:
        if not password:
            if no_input:
                raise SystemExit(f"{email}: falta password temporal para bootstrap no interactivo.")
            password = getpass.getpass(f"Contrasena temporal para {email}: ")
        errors = password_errors(password)
        if errors:
            raise SystemExit(f"{email}: {' '.join(errors)}")
        return password
    return ""


def find_by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    return next((item for item in items if item.get("id") == item_id), None)


def active_company_id(store: dict[str, Any]) -> str:
    company_id = env_value("FVENTAS_BOOTSTRAP_COMPANY_ID", DEFAULT_COMPANY_ID)
    if find_by_id(store.get("companies", []), company_id):
        return company_id
    if store.get("companies"):
        return store["companies"][0].get("id") or company_id
    return company_id


def normalize_bootstrap_country(value: str | None, default: str = "CL") -> str:
    code = str(value or "").strip().upper()
    return code if code in ALLOWED_MARKET_COUNTRIES else default


def ensure_company(store: dict[str, Any]) -> str:
    now = utc_now()
    company_id = active_company_id(store)
    company = find_by_id(store.setdefault("companies", []), company_id)
    if company is None:
        company = {"id": company_id, "createdAt": now}
        store["companies"].append(company)

    company_name = env_value("FVENTAS_BOOTSTRAP_COMPANY_NAME", company.get("name") or "FVENTAS")
    legal_name = env_value("FVENTAS_BOOTSTRAP_COMPANY_LEGAL_NAME", company.get("legalName") or company_name)
    owner_email = env_value("FVENTAS_BOOTSTRAP_OWNER_EMAIL", company.get("ownerEmail") or "")
    company_country = normalize_bootstrap_country(
        env_value("FVENTAS_BOOTSTRAP_COUNTRY", company.get("country") or "CL")
    )
    company.update(
        {
            "name": company_name,
            "slug": company.get("slug") or slugify(company_name),
            "legalName": legal_name,
            "taxId": env_value("FVENTAS_BOOTSTRAP_COMPANY_TAX_ID", company.get("taxId") or ""),
            "country": company_country,
            "status": env_value("FVENTAS_BOOTSTRAP_COMPANY_STATUS", company.get("status") or "active"),
            "ownerName": env_value("FVENTAS_BOOTSTRAP_OWNER_NAME", company.get("ownerName") or ""),
            "ownerEmail": owner_email,
            "supportEmail": env_value("FVENTAS_BOOTSTRAP_SUPPORT_EMAIL", company.get("supportEmail") or owner_email),
            "supportPhone": env_value("FVENTAS_BOOTSTRAP_SUPPORT_PHONE", company.get("supportPhone") or ""),
            "updatedAt": now,
        }
    )
    company["legalAcceptance"] = {
        "accepted": True,
        "termsVersion": LEGAL_TERMS_VERSION,
        "privacyVersion": LEGAL_PRIVACY_VERSION,
        "acceptedAt": company.get("legalAcceptance", {}).get("acceptedAt") or now,
        "acceptedByEmail": owner_email,
        "ipAddress": "bootstrap",
        "userAgent": "scripts/bootstrap_production.py",
    }

    subscription = next(
        (item for item in store.setdefault("subscriptions", []) if item.get("companyId") == company_id),
        None,
    )
    if subscription is None:
        subscription = {"id": f"sub-{company_id}", "companyId": company_id, "createdAt": now}
        store["subscriptions"].append(subscription)
    subscription.update(
        {
            "planId": SAAS_PLAN_ID,
            "planName": SAAS_PLAN_NAME,
            "status": env_value("FVENTAS_BOOTSTRAP_SUBSCRIPTION_STATUS", subscription.get("status") or "active"),
            "billingPeriod": "monthly",
            "priceClp": SAAS_PLAN_PRICE_CLP,
            "currency": env_value("FVENTAS_BOOTSTRAP_PLAN_CURRENCY", subscription.get("currency") or "CLP"),
            "updatedAt": now,
        }
    )
    return company_id


def upsert_admin(
    store: dict[str, Any],
    company_id: str,
    *,
    role: str,
    prefix: str,
    required: bool = False,
    reset_passwords: bool = False,
    no_input: bool = False,
) -> bool:
    email = env_value(f"{prefix}_EMAIL")
    name = env_value(f"{prefix}_NAME")
    password = env_value(f"{prefix}_PASSWORD")
    if not email:
        if required:
            raise SystemExit(f"Falta {prefix}_EMAIL para crear el usuario requerido.")
        return False
    if not name:
        name = email.split("@", 1)[0].replace(".", " ").title()
    if any(client.get("email", "").lower() == email.lower() for client in store.get("clients", [])):
        raise SystemExit(f"{email}: ya existe como cliente movil. Usa correos distintos por identidad.")

    now = utc_now()
    users = store.setdefault("admin_users", [])
    user = next((item for item in users if item.get("email", "").lower() == email.lower()), None)
    is_new = user is None
    password_to_store = password_for_record(
        email,
        password,
        is_new=is_new,
        reset_passwords=reset_passwords,
        no_input=no_input,
    )
    if user is None:
        user = {
            "id": f"admin-{slugify(email)}-{secrets.token_hex(3)}",
            "createdAt": now,
            "failedLoginAttempts": 0,
            "lastFailedLoginAt": "",
            "lastLoginAt": "",
            "lastLoginIp": "",
            "activeSessions": [],
            "sessionVersion": 0,
        }
        users.append(user)
    user.update(
        {
            "companyId": company_id,
            "name": name,
            "firstName": name,
            "lastName": "",
            "email": email.lower(),
            "role": role,
            "status": "active",
            "mobileAccessEnabled": role in {"sales", "commercial_manager", "super_admin"},
            "commissionRatePercent": float(env_value(f"{prefix}_COMMISSION_PERCENT", "0") or 0),
            "salesGoalUsd": float(env_value(f"{prefix}_SALES_GOAL_USD", "0") or 0),
            "sellerCode": env_value(f"{prefix}_SELLER_CODE", user.get("sellerCode", "")),
            "phone": env_value(f"{prefix}_PHONE", user.get("phone", "")),
            "updatedAt": now,
        }
    )
    if password_to_store:
        user["passwordHash"] = generate_password_hash(password_to_store)
        user["mustChangePassword"] = True
        user["sessionVersion"] = int(user.get("sessionVersion") or 0) + 1
    else:
        user.setdefault("passwordHash", "")
        user.setdefault("mustChangePassword", False)
        user.setdefault("sessionVersion", 0)
    return True


def ensure_catalog(store: dict[str, Any], company_id: str) -> tuple[int, int]:
    now = utc_now()
    created_categories = 0
    created_products = 0
    categories = store.setdefault("categories", [])
    products = store.setdefault("products", [])

    for index, category_seed in enumerate(STARTER_CATEGORIES, start=1):
        category = find_by_id(categories, category_seed["id"])
        if category is None:
            category = {"id": category_seed["id"], "createdAt": now}
            categories.append(category)
            created_categories += 1
        category.update(
            {
                "companyId": company_id,
                "name": category_seed["name"],
                "slug": category_seed["slug"],
                "description": category_seed["description"],
                "imageUrl": STARTER_CATEGORY_IMAGES.get(category_seed["id"].replace("cat-", ""), "/static/uploads/catalog/fventas-product.svg"),
                "icon": category_seed["icon"],
                "sortOrder": index * 10,
                "status": "active",
                "visibleInApp": True,
                "parentId": "",
                "updatedAt": now,
            }
        )

    for index, product_seed in enumerate(STARTER_PRODUCTS, start=1):
        product = find_by_id(products, product_seed["id"])
        if product is None:
            product = {"id": product_seed["id"], "createdAt": now}
            products.append(product)
            created_products += 1
        stock = int(product_seed["stock"])
        image_url = "/static/uploads/catalog/fventas-product.svg"
        product.update(
            {
                "companyId": company_id,
                "sku": product_seed["sku"],
                "internalCode": product_seed["sku"],
                "title": product_seed["title"],
                "brand": "FVENTAS",
                "model": product_seed["sku"],
                "description": product_seed["description"],
                "shortDescription": product_seed["description"],
                "longDescription": product_seed["description"],
                "productType": product_seed["productType"],
                "categoryId": product_seed["categoryId"],
                "categoryName": product_seed["categoryName"],
                "subCategory": product_seed["categoryName"],
                "unitOfSale": "unidad",
                "publicPriceUsd": product_seed["publicPriceUsd"],
                "b2bPriceUsd": product_seed["b2bPriceUsd"],
                "originalPriceUsd": product_seed["originalPriceUsd"],
                "discountPercent": product_seed["discountPercent"],
                "costReferenceUsd": 0.0,
                "marginPercent": 0.0,
                "stock": stock,
                "physicalStock": stock,
                "availableStock": stock,
                "reservedStock": 0,
                "committedStock": 0,
                "minimumStock": 1,
                "maximumStock": max(10, stock * 3),
                "reserved": 0,
                "status": "active",
                "visibleInApp": True,
                "publishedInApp": True,
                "featured": index <= 3,
                "onSale": product_seed["discountPercent"] > 0,
                "requiresQuote": False,
                "requiresTechnicalValidation": product_seed["productType"] == "machine" and product_seed["publicPriceUsd"] >= 500,
                "imageUrl": image_url,
                "imageUrls": [image_url],
                "pdfUrls": [],
                "variants": [],
                "specifications": {"Origen": "Bootstrap comercial FVENTAS"},
                "relatedSkus": [],
                "rotationLast30Days": 0,
                "sourceName": "Bootstrap comercial FVENTAS",
                "sourceUrl": "",
                "updatedAt": now,
            }
        )
    return created_categories, created_products


def upsert_client(
    store: dict[str, Any],
    company_id: str,
    *,
    reset_passwords: bool = False,
    no_input: bool = False,
) -> bool:
    email = env_value("FVENTAS_BOOTSTRAP_CLIENT_EMAIL")
    if not email:
        return False
    password = env_value("FVENTAS_BOOTSTRAP_CLIENT_PASSWORD")
    if any(user.get("email", "").lower() == email.lower() for user in store.get("admin_users", [])):
        raise SystemExit(f"{email}: ya existe como usuario operativo/admin. Usa correos distintos por identidad.")

    now = utc_now()
    clients = store.setdefault("clients", [])
    client = next((item for item in clients if item.get("email", "").lower() == email.lower()), None)
    is_new = client is None
    password_to_store = password_for_record(
        email,
        password,
        is_new=is_new,
        reset_passwords=reset_passwords,
        no_input=no_input,
    )
    if client is None:
        client = {
            "id": f"client-{slugify(email)}-{secrets.token_hex(3)}",
            "createdAt": now,
            "mobileSessionVersion": 0,
        }
        clients.append(client)
    seller_email = env_value("FVENTAS_BOOTSTRAP_SELLER_EMAIL")
    seller = next(
        (
            user
            for user in store.get("admin_users", [])
            if seller_email and user.get("email", "").lower() == seller_email.lower()
        ),
        None,
    )
    business_name = env_value("FVENTAS_BOOTSTRAP_CLIENT_BUSINESS_NAME", client.get("businessName") or "Cliente B2B FVENTAS")
    requested_credit = float(env_value("FVENTAS_BOOTSTRAP_CLIENT_CREDIT_REQUESTED_USD", "0") or 0)
    client_country = normalize_bootstrap_country(
        env_value("FVENTAS_BOOTSTRAP_COUNTRY", client.get("country") or company.get("country") or "CL"),
        company.get("country") or "CL",
    )
    client.update(
        {
            "companyId": company_id,
            "legalName": env_value("FVENTAS_BOOTSTRAP_CLIENT_LEGAL_NAME", client.get("legalName") or business_name),
            "commercialName": env_value("FVENTAS_BOOTSTRAP_CLIENT_COMMERCIAL_NAME", client.get("commercialName") or business_name),
            "businessName": business_name,
            "taxId": env_value("FVENTAS_BOOTSTRAP_CLIENT_TAX_ID", client.get("taxId") or ""),
            "contactName": env_value("FVENTAS_BOOTSTRAP_CLIENT_CONTACT_NAME", client.get("contactName") or ""),
            "administrativeContact": env_value("FVENTAS_BOOTSTRAP_CLIENT_CONTACT_NAME", client.get("administrativeContact") or ""),
            "receivingContact": env_value("FVENTAS_BOOTSTRAP_CLIENT_CONTACT_NAME", client.get("receivingContact") or ""),
            "phone": env_value("FVENTAS_BOOTSTRAP_CLIENT_PHONE", client.get("phone") or ""),
            "whatsapp": env_value("FVENTAS_BOOTSTRAP_CLIENT_WHATSAPP", client.get("whatsapp") or client.get("phone") or ""),
            "email": email.lower(),
            "clientType": "b2b",
            "clientCategory": env_value("FVENTAS_BOOTSTRAP_CLIENT_CATEGORY", client.get("clientCategory") or "standard"),
            "priceList": "b2b",
            "status": "active",
            "address": env_value("FVENTAS_BOOTSTRAP_CLIENT_ADDRESS", client.get("address") or ""),
            "fiscalAddress": env_value("FVENTAS_BOOTSTRAP_CLIENT_ADDRESS", client.get("fiscalAddress") or ""),
            "shippingAddress": env_value("FVENTAS_BOOTSTRAP_CLIENT_ADDRESS", client.get("shippingAddress") or ""),
            "country": client_country,
            "state": env_value("FVENTAS_BOOTSTRAP_CLIENT_STATE", client.get("state") or ""),
            "city": env_value("FVENTAS_BOOTSTRAP_CLIENT_CITY", client.get("city") or ""),
            "deliveryZone": env_value("FVENTAS_BOOTSTRAP_CLIENT_DELIVERY_ZONE", client.get("deliveryZone") or ""),
            "assignedSellerId": (seller or {}).get("id", client.get("assignedSellerId", "")),
            "assignedSellerName": (seller or {}).get("name", client.get("assignedSellerName", "")),
            "defaultSaleType": env_value("FVENTAS_BOOTSTRAP_CLIENT_DEFAULT_SALE_TYPE", client.get("defaultSaleType") or "cash"),
            "allowedPaymentTermsDays": [0, 15, 30],
            "collectionStatus": "without_debt",
            "creditRiskLevel": "low",
            "creditScore": 0,
            "creditRequestStatus": "pending" if requested_credit > 0 else "none",
            "creditRequestedUsd": requested_credit,
            "creditEnabled": False,
            "creditLimitUsd": float(env_value("FVENTAS_BOOTSTRAP_CLIENT_CREDIT_LIMIT_USD", "0") or 0),
            "creditUsedUsd": 0.0,
            "paymentTermsDays": 0,
            "notes": "Cliente inicial creado por bootstrap productivo.",
            "updatedAt": now,
        }
    )
    if password_to_store:
        client["passwordHash"] = generate_password_hash(password_to_store)
        client["mustChangePassword"] = True
        client["mobileSessionVersion"] = int(client.get("mobileSessionVersion") or 0) + 1
    else:
        client.setdefault("passwordHash", "")
        client.setdefault("mustChangePassword", False)
        client.setdefault("mobileSessionVersion", 0)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a FVENTAS production tenant without demo data.")
    parser.add_argument("--skip-catalog", action="store_true", help="Do not create starter categories/products.")
    parser.add_argument("--skip-seller", action="store_true", help="Do not create optional seller from env.")
    parser.add_argument("--reset-passwords", action="store_true", help="Reset bootstrap admin/seller/client passwords when they already exist.")
    parser.add_argument("--no-input", action="store_true", help="Fail instead of prompting for missing passwords.")
    args = parser.parse_args()

    reset_passwords = args.reset_passwords or env_bool("FVENTAS_BOOTSTRAP_RESET_PASSWORDS", default=False)
    no_input = args.no_input or env_bool("FVENTAS_BOOTSTRAP_NO_INPUT", default=False)
    admin_email = env_value("FVENTAS_BOOTSTRAP_ADMIN_EMAIL").lower()
    seller_email = env_value("FVENTAS_BOOTSTRAP_SELLER_EMAIL").lower()
    client_email = env_value("FVENTAS_BOOTSTRAP_CLIENT_EMAIL").lower()
    configured_emails = [value for value in [admin_email, seller_email, client_email] if value]
    if len(configured_emails) != len(set(configured_emails)):
        raise SystemExit("Bootstrap requiere correos distintos para admin, vendedor y cliente movil.")

    store = load_store()
    company_id = ensure_company(store)
    admin_created = upsert_admin(
        store,
        company_id,
        role="super_admin",
        prefix="FVENTAS_BOOTSTRAP_ADMIN",
        required=True,
        reset_passwords=reset_passwords,
        no_input=no_input,
    )
    seller_created = False
    if not args.skip_seller:
        seller_created = upsert_admin(
            store,
            company_id,
            role="sales",
            prefix="FVENTAS_BOOTSTRAP_SELLER",
            required=False,
            reset_passwords=reset_passwords,
            no_input=no_input,
        )
    created_categories = 0
    created_products = 0
    if not args.skip_catalog:
        created_categories, created_products = ensure_catalog(store, company_id)
    client_created = upsert_client(store, company_id, reset_passwords=reset_passwords, no_input=no_input)

    save_store(store)
    print("Bootstrap FVENTAS listo.")
    print(f"Empresa: {company_id}")
    print(f"Super admin {'creado/actualizado' if admin_created else 'omitido'}")
    print(f"Vendedor {'creado/actualizado' if seller_created else 'omitido'}")
    print(f"Cliente B2B {'creado/actualizado' if client_created else 'omitido'}")
    print(f"Categorias creadas: {created_categories}")
    print(f"Productos creados: {created_products}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
