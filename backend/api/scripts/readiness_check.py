from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import get_config
from store import (
    INSECURE_PRODUCTION_ADMIN_EMAILS,
    INSECURE_PRODUCTION_ANNOUNCEMENT_IDS,
    INSECURE_PRODUCTION_CATEGORY_IDS,
    INSECURE_PRODUCTION_CLIENT_IDS,
    INSECURE_PRODUCTION_CLIENT_EMAILS,
    INSECURE_PRODUCTION_ORDER_PREFIXES,
    INSECURE_PRODUCTION_PRODUCT_IDS,
    INSECURE_PRODUCTION_SERVICE_TECHNICIAN_IDS,
    load_store,
)


Config = get_config()


LEGAL_TEMPLATE_REQUIREMENTS = {
    "privacy_policy.html": [
        "Politica de privacidad",
        "Solicitud de eliminacion",
        "Terminos del servicio",
    ],
    "terms_of_service.html": [
        "Terminos del servicio",
        "Politica de privacidad",
        "Eliminar cuenta",
    ],
    "account_deletion.html": [
        "Solicitud de eliminacion de cuenta",
        "politica de privacidad",
    ],
}


@dataclass
class Finding:
    severity: str
    label: str
    detail: str


def add(findings: list[Finding], severity: str, label: str, detail: str) -> None:
    findings.append(Finding(severity=severity, label=label, detail=detail))


def collection_duplicates(items: list[dict[str, Any]], key: str) -> list[str]:
    seen: set[str] = set()
    duplicated: set[str] = set()
    for item in items:
        value = str(item.get(key) or "").strip().lower()
        if not value:
            continue
        if value in seen:
            duplicated.add(value)
        seen.add(value)
    return sorted(duplicated)


def active_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in items if str(item.get("status", "active")).lower() == "active"]


def audit_config(findings: list[Finding], strict: bool) -> None:
    is_production = str(Config.ENV).lower() == "production"
    expected = "error" if strict or is_production else "warn"

    if is_production:
        if Config.SECRET_KEY == "fventas-dev":
            add(findings, "error", "secret", "FVENTAS_SECRET_KEY usa el valor de desarrollo.")
        if str(Config.DATA_BACKEND).lower() != "sql":
            add(findings, "error", "data-backend", "Produccion debe usar FVENTAS_DATA_BACKEND=sql.")
        if Config.SQL_FALLBACK_TO_JSON:
            add(findings, "error", "sql-fallback", "Produccion debe tener FVENTAS_SQL_FALLBACK_TO_JSON=0.")
        if not Config.REQUIRE_MOBILE_TOKEN:
            add(findings, "error", "mobile-token", "Produccion debe exigir token movil.")
        if not getattr(Config, "REQUIRE_MOBILE_DEVICE_HEADER", False):
            add(findings, "error", "mobile-device", "Produccion debe exigir X-FVENTAS-Device-Id en tokens moviles.")
        if getattr(Config, "ALLOW_LEGACY_MOBILE_API", True):
            add(findings, "error", "mobile-legacy-api", "Produccion debe desactivar /api/mobile/* legacy.")
        if str(Config.STORAGE_BACKEND).lower() != "s3":
            add(findings, "error", "storage", "Produccion debe usar storage S3/Spaces.")
        if not Config.SESSION_COOKIE_SECURE:
            add(findings, "error", "session-secure", "Produccion debe marcar cookies de sesion como Secure.")
        if not Config.SESSION_COOKIE_HTTPONLY:
            add(findings, "error", "session-httponly", "Produccion debe marcar cookies de sesion como HttpOnly.")
        if str(Config.SESSION_COOKIE_SAMESITE).lower() not in {"lax", "strict"}:
            add(findings, "error", "session-samesite", "Produccion debe usar SameSite=Lax o Strict.")
        if getattr(Config, "CONTENT_SECURITY_POLICY_REPORT_ONLY", True):
            add(findings, "error", "csp-enforcement", "Produccion debe aplicar Content-Security-Policy en modo bloqueo.")
        if not getattr(Config, "TRUST_PROXY_HEADERS", False):
            add(
                findings,
                "warn",
                "proxy-headers",
                "Si el backend queda detras de DigitalOcean/Caddy, configura FVENTAS_TRUST_PROXY_HEADERS=1 para auditoria y rate limit por IP real.",
            )
    else:
        add(findings, "info", "environment", f"Entorno actual: {Config.ENV}.")

    if strict and not Config.S3_BUCKET:
        add(findings, expected, "s3-bucket", "FVENTAS_S3_BUCKET no esta configurado.")
    if strict and not Config.STORAGE_PUBLIC_BASE_URL:
        add(findings, expected, "storage-public-url", "FVENTAS_STORAGE_PUBLIC_BASE_URL no esta configurado.")
    if strict and "sqlite" in Config.DATABASE_URL:
        add(findings, expected, "database-url", "La base configurada parece SQLite, no PostgreSQL.")


def audit_legal_templates(findings: list[Finding], strict: bool) -> None:
    templates_dir = ROOT_DIR / "templates"
    severity = "error" if strict else "warn"
    for template_name, required_fragments in LEGAL_TEMPLATE_REQUIREMENTS.items():
        template_path = templates_dir / template_name
        if not template_path.exists():
            add(findings, severity, "legal-template", f"Falta template legal: {template_name}.")
            continue
        content = template_path.read_text(encoding="utf-8", errors="ignore").lower()
        missing = [
            fragment
            for fragment in required_fragments
            if fragment.lower() not in content
        ]
        if missing:
            add(
                findings,
                severity,
                "legal-template",
                f"{template_name} no contiene: {', '.join(missing)}.",
            )


def audit_store(findings: list[Finding], store: dict[str, list[dict[str, Any]]], strict: bool) -> None:
    for collection in [
        "admin_users",
        "clients",
        "categories",
        "products",
        "orders",
        "announcements",
        "service_technicians",
    ]:
        duplicated = collection_duplicates(store.get(collection, []), "id")
        if duplicated:
            add(findings, "error", f"{collection}-ids", f"IDs duplicados: {', '.join(duplicated[:8])}.")

    admin_users = store.get("admin_users", [])
    clients = store.get("clients", [])
    companies = store.get("companies", [])
    active_admins = active_items(admin_users)
    active_clients = active_items(clients)
    active_products = active_items(store.get("products", []))
    active_categories = active_items(store.get("categories", []))

    admin_emails = collection_duplicates(admin_users, "email")
    client_emails = collection_duplicates(clients, "email")
    product_skus = collection_duplicates(store.get("products", []), "sku")
    if admin_emails:
        add(findings, "error", "admin-email", f"Emails admin duplicados: {', '.join(admin_emails[:8])}.")
    if client_emails:
        add(findings, "error", "client-email", f"Emails cliente duplicados: {', '.join(client_emails[:8])}.")
    if product_skus:
        add(findings, "error", "product-sku", f"SKUs duplicados: {', '.join(product_skus[:8])}.")
    mobile_admin_emails = {
        str(user.get("email") or "").strip().lower()
        for user in active_admins
        if user.get("role") in {"sales", "commercial_manager", "super_admin"}
        and user.get("mobileAccessEnabled", True) is not False
    }
    mobile_client_emails = {
        str(client.get("email") or "").strip().lower()
        for client in active_clients
    }
    duplicated_mobile_identities = sorted((mobile_admin_emails & mobile_client_emails) - {""})
    if duplicated_mobile_identities:
        add(
            findings,
            "error",
            "mobile-identity-email",
            f"Correos usados por cliente y usuario movil: {', '.join(duplicated_mobile_identities[:8])}.",
        )

    real_super_admins = [
        user
        for user in active_admins
        if user.get("role") == "super_admin"
        and user.get("email", "").lower() not in INSECURE_PRODUCTION_ADMIN_EMAILS
    ]
    if not real_super_admins:
        add(findings, "error" if strict else "warn", "super-admin", "No existe super admin real activo.")

    insecure_admins = [
        user.get("email", "")
        for user in active_admins
        if user.get("email", "").lower() in INSECURE_PRODUCTION_ADMIN_EMAILS
    ]
    insecure_clients = [
        client.get("email", "")
        for client in active_clients
        if client.get("email", "").lower() in INSECURE_PRODUCTION_CLIENT_EMAILS
        or client.get("id", "").lower() in INSECURE_PRODUCTION_CLIENT_IDS
    ]
    demo_orders = [
        order.get("orderId") or order.get("id", "")
        for order in store.get("orders", [])
        if order.get("customerId", "").lower() in INSECURE_PRODUCTION_CLIENT_IDS
        or any(
            (order.get("orderId") or order.get("id", "")).startswith(prefix)
            for prefix in INSECURE_PRODUCTION_ORDER_PREFIXES
        )
    ]
    demo_products = [
        product.get("sku") or product.get("id", "")
        for product in active_products
        if product.get("id", "").lower() in INSECURE_PRODUCTION_PRODUCT_IDS
    ]
    demo_categories = [
        category.get("name") or category.get("id", "")
        for category in active_categories
        if category.get("id", "").lower() in INSECURE_PRODUCTION_CATEGORY_IDS
    ]
    demo_announcements = [
        announcement.get("title") or announcement.get("id", "")
        for announcement in active_items(store.get("announcements", []))
        if announcement.get("id", "").lower() in INSECURE_PRODUCTION_ANNOUNCEMENT_IDS
    ]
    demo_technicians = [
        technician.get("name") or technician.get("id", "")
        for technician in active_items(store.get("service_technicians", []))
        if technician.get("id", "").lower() in INSECURE_PRODUCTION_SERVICE_TECHNICIAN_IDS
        and technician.get("visibleInApp", True)
    ]
    if insecure_admins:
        add(findings, "error" if strict else "warn", "demo-admin", f"Cuentas admin demo activas: {', '.join(insecure_admins)}.")
    if insecure_clients:
        add(findings, "error" if strict else "warn", "demo-client", f"Clientes demo activos: {', '.join(insecure_clients)}.")
    if demo_orders:
        add(findings, "error" if strict else "warn", "demo-orders", f"Ordenes demo presentes: {', '.join(demo_orders)}.")
    if demo_products:
        add(findings, "error" if strict else "warn", "demo-products", f"Productos demo activos: {', '.join(demo_products)}.")
    if demo_categories:
        add(findings, "error" if strict else "warn", "demo-categories", f"Categorias demo activas: {', '.join(demo_categories)}.")
    if demo_announcements:
        add(findings, "error" if strict else "warn", "demo-announcements", f"Anuncios demo activos: {', '.join(demo_announcements)}.")
    if demo_technicians:
        add(findings, "error" if strict else "warn", "demo-technicians", f"Servicios tecnicos demo visibles: {', '.join(demo_technicians)}.")

    if not any(user.get("role") == "sales" for user in active_admins):
        add(findings, "warn", "seller", "No hay vendedores activos para cartera/comisiones.")
    if not active_clients:
        add(findings, "warn", "clients", "No hay clientes B2B activos.")
    commercial_data_severity = "error" if strict else "warn"
    if not active_products:
        add(findings, commercial_data_severity, "products", "No hay productos activos para la app movil.")
    if not active_categories:
        add(findings, commercial_data_severity, "categories", "No hay categorias activas.")

    category_ids = {category.get("id") for category in store.get("categories", [])}
    for product in active_products:
        if not product.get("sku") or not product.get("title"):
            add(findings, "error", "product-required", f"Producto incompleto: {product.get('id', 'sin-id')}.")
        if float(product.get("publicPriceUsd") or 0) <= 0:
            add(findings, "error", "product-price", f"Producto sin precio USD publico: {product.get('sku', product.get('id'))}.")
        if product.get("categoryId") not in category_ids:
            add(findings, "error", "product-category", f"Producto con categoria inexistente: {product.get('sku', product.get('id'))}.")
        if strict and not (product.get("imageUrl") or product.get("imageUrls")):
            add(findings, "warn", "product-image", f"Producto sin imagen: {product.get('sku', product.get('id'))}.")

    for category in active_categories:
        if strict and not category.get("imageUrl"):
            add(findings, "warn", "category-image", f"Categoria sin imagen: {category.get('name', category.get('id'))}.")

    if not active_items(store.get("announcements", [])):
        add(findings, "warn", "announcements", "No hay anuncios activos para el carrusel movil.")
    if not active_items(store.get("service_technicians", [])):
        add(findings, "warn", "service-technicians", "No hay servicios tecnicos activos visibles.")

    companies_without_legal_acceptance = [
        company.get("name") or company.get("id", "sin-id")
        for company in companies
        if not (company.get("legalAcceptance") or {}).get("accepted")
    ]
    if companies_without_legal_acceptance:
        add(
            findings,
            "error" if strict else "warn",
            "legal-acceptance",
            "Empresas sin version legal aceptada: "
            f"{', '.join(companies_without_legal_acceptance[:8])}.",
        )


def print_report(findings: list[Finding]) -> None:
    print("FVENTAS Insights readiness")
    print("-------------------------")
    if not findings:
        print("OK Sin hallazgos. Plataforma lista para operacion.")
        return

    for finding in findings:
        marker = {
            "error": "FAIL",
            "warn": "WARN",
            "info": "INFO",
        }.get(finding.severity, finding.severity.upper())
        print(f"{marker:<4} {finding.label:<22} {finding.detail}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audita si FVENTAS esta listo para produccion comercial.")
    parser.add_argument("--strict", action="store_true", help="Trata cuentas demo y assets faltantes como riesgos productivos.")
    args = parser.parse_args()

    findings: list[Finding] = []
    strict = args.strict or str(Config.ENV).lower() == "production"

    audit_config(findings, strict=strict)
    audit_legal_templates(findings, strict=strict)
    try:
        store = load_store()
    except Exception as exc:
        add(findings, "error", "store", f"No se pudo cargar el store: {exc}")
        print_report(findings)
        raise SystemExit(1) from exc

    audit_store(findings, store, strict=strict)
    print_report(findings)

    if any(finding.severity == "error" for finding in findings):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
