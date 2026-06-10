from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import get_config
from store import (
    INSECURE_PRODUCTION_ADMIN_EMAILS,
    INSECURE_PRODUCTION_CLIENT_EMAILS,
    load_store,
)


Config = get_config()


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
        if Config.SECRET_KEY == "wulkan-dev":
            add(findings, "error", "secret", "WULKAN_SECRET_KEY usa el valor de desarrollo.")
        if str(Config.DATA_BACKEND).lower() != "sql":
            add(findings, "error", "data-backend", "Produccion debe usar WULKAN_DATA_BACKEND=sql.")
        if Config.SQL_FALLBACK_TO_JSON:
            add(findings, "error", "sql-fallback", "Produccion debe tener WULKAN_SQL_FALLBACK_TO_JSON=0.")
        if not Config.REQUIRE_MOBILE_TOKEN:
            add(findings, "error", "mobile-token", "Produccion debe exigir token movil.")
        if str(Config.STORAGE_BACKEND).lower() != "s3":
            add(findings, "error", "storage", "Produccion debe usar storage S3/Spaces.")
    else:
        add(findings, "info", "environment", f"Entorno actual: {Config.ENV}.")

    if strict and not Config.S3_BUCKET:
        add(findings, expected, "s3-bucket", "WULKAN_S3_BUCKET no esta configurado.")
    if strict and not Config.STORAGE_PUBLIC_BASE_URL:
        add(findings, expected, "storage-public-url", "WULKAN_STORAGE_PUBLIC_BASE_URL no esta configurado.")
    if strict and "sqlite" in Config.DATABASE_URL:
        add(findings, expected, "database-url", "La base configurada parece SQLite, no PostgreSQL.")


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
    ]
    if insecure_admins:
        add(findings, "error" if strict else "warn", "demo-admin", f"Cuentas admin demo activas: {', '.join(insecure_admins)}.")
    if insecure_clients:
        add(findings, "error" if strict else "warn", "demo-client", f"Clientes demo activos: {', '.join(insecure_clients)}.")

    if not any(user.get("role") == "sales" for user in active_admins):
        add(findings, "warn", "seller", "No hay vendedores activos para cartera/comisiones.")
    if not active_clients:
        add(findings, "warn", "clients", "No hay clientes ferreteros activos.")
    if not active_products:
        add(findings, "error", "products", "No hay productos activos para la app movil.")
    if not active_categories:
        add(findings, "error", "categories", "No hay categorias activas.")

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


def print_report(findings: list[Finding]) -> None:
    print("Graphify readiness Wulkan")
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
    parser = argparse.ArgumentParser(description="Audita si Wulkan esta listo para produccion comercial.")
    parser.add_argument("--strict", action="store_true", help="Trata cuentas demo y assets faltantes como riesgos productivos.")
    args = parser.parse_args()

    findings: list[Finding] = []
    strict = args.strict or str(Config.ENV).lower() == "production"

    audit_config(findings, strict=strict)
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
