from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

db_file = Path(tempfile.gettempdir()) / "wulkan_sql_integrity_smoke.db"
if db_file.exists():
    db_file.unlink()

os.environ["WULKAN_DATA_BACKEND"] = "sql"
os.environ["WULKAN_DATABASE_URL"] = f"sqlite:///{db_file.as_posix()}"
os.environ["WULKAN_SQL_FALLBACK_TO_JSON"] = "0"

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app as wulkan_app
from db import drop_database, init_database
from sql_store import load_sql_store, sync_admin_user_records, sync_client_records, sync_store_to_sql
from store import normalize_store, utc_now
from werkzeug.security import generate_password_hash


ADMIN_ID = "admin-sql-smoke"
CSRF = "csrf-sql"


def base_store() -> dict:
    now = utc_now()
    store = {
        "admin_users": [
            {
                "id": ADMIN_ID,
                "name": "Admin SQL Smoke",
                "email": "admin.sql@wulkan.test",
                "passwordHash": generate_password_hash("AdminSql2026"),
                "role": "super_admin",
                "status": "active",
                "sessionVersion": 0,
                "mustChangePassword": False,
                "activeSessions": [],
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "admin-seller-deleted",
                "name": "Vendedor SQL Eliminado",
                "email": "vendedor.eliminado.sql@wulkan.test",
                "passwordHash": generate_password_hash("SellerSql2026"),
                "role": "sales",
                "status": "deleted",
                "sessionVersion": 0,
                "mustChangePassword": True,
                "activeSessions": [],
                "sellerCode": "VEN-SQL-DEL",
                "zone": "Carabobo",
                "commissionRate": 3.0,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "categories": [
            {
                "id": "cat-sql-root",
                "name": "Categoria SQL",
                "slug": "categoria-sql",
                "status": "active",
                "visibleInApp": True,
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "cat-sql-empty",
                "name": "Categoria sin historial",
                "slug": "categoria-sin-historial",
                "status": "active",
                "visibleInApp": True,
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "cat-sql-parent-delete",
                "name": "Categoria padre eliminable",
                "slug": "categoria-padre-eliminable",
                "status": "active",
                "visibleInApp": True,
                "parentId": "",
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "cat-sql-child-preserved",
                "name": "Subcategoria conservada",
                "slug": "subcategoria-conservada",
                "status": "active",
                "visibleInApp": True,
                "parentId": "cat-sql-parent-delete",
                "createdAt": now,
                "updatedAt": now,
            },
        ],
        "products": [
            {
                "id": "prod-sql",
                "sku": "WUL-SQL-01",
                "title": "Producto SQL",
                "description": "Producto para integridad SQL.",
                "productType": "machine",
                "categoryId": "cat-sql-root",
                "categoryName": "Categoria SQL",
                "publicPriceUsd": 100,
                "b2bPriceUsd": 90,
                "stock": 5,
                "reserved": 1,
                "status": "active",
                "visibleInApp": True,
                "imageUrls": [],
                "pdfUrls": [],
                "variants": [],
                "specifications": {},
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "prod-sql-free",
                "sku": "WUL-SQL-FREE",
                "title": "Producto SQL sin historial",
                "description": "Producto eliminable.",
                "productType": "part",
                "categoryId": "cat-sql-empty",
                "categoryName": "Categoria sin historial",
                "publicPriceUsd": 10,
                "b2bPriceUsd": 8,
                "stock": 1,
                "reserved": 0,
                "status": "active",
                "visibleInApp": True,
                "imageUrls": [],
                "pdfUrls": [],
                "variants": [],
                "specifications": {},
                "createdAt": now,
                "updatedAt": now,
            },
        ],
        "clients": [
            {
                "id": "client-sql",
                "businessName": "Ferreteria SQL",
                "contactName": "Comprador SQL",
                "email": "client.sql@wulkan.test",
                "passwordHash": generate_password_hash("ClientSql2026"),
                "status": "active",
                "clientType": "ferretero",
                "taxId": "J-33333333-3",
                "phone": "+580000000003",
                "address": "Av SQL",
                "city": "Valencia",
                "state": "Carabobo",
                "creditEnabled": True,
                "creditLimitUsd": 500,
                "creditUsedUsd": 90,
                "creditRequestStatus": "approved",
                "paymentTermsDays": 15,
                "allowedPaymentTermsDays": [0, 15],
                "defaultSaleType": "credit_line",
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "client-sql-deleted",
                "businessName": "Ferreteria SQL Eliminada",
                "contactName": "Comprador Eliminado",
                "email": "deleted.sql@wulkan.test",
                "passwordHash": generate_password_hash("DeletedSql2026"),
                "status": "deleted",
                "clientType": "ferretero",
                "taxId": "J-44444444-4",
                "phone": "+580000000005",
                "address": "Av SQL Eliminada",
                "city": "Valencia",
                "state": "Carabobo",
                "creditEnabled": False,
                "creditLimitUsd": 0,
                "creditUsedUsd": 0,
                "creditRequestStatus": "none",
                "paymentTermsDays": 0,
                "allowedPaymentTermsDays": [0],
                "defaultSaleType": "cash",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "orders": [
            {
                "id": "order-sql",
                "orderId": "order-sql",
                "customerId": "client-sql",
                "customer": {"id": "client-sql", "name": "Ferreteria SQL"},
                "items": [
                    {
                        "productId": "prod-sql",
                        "sku": "WUL-SQL-01",
                        "title": "Producto SQL",
                        "quantity": 1,
                        "unitPriceUsd": 90,
                        "subtotalUsd": 90,
                    }
                ],
                "totalUsd": 90,
                "netUsd": 90,
                "paidUsd": 0,
                "balanceUsd": 90,
                "saleType": "credit_line",
                "paymentTermDays": 15,
                "status": "pending",
                "creditStatus": "approved",
                "inventoryStatus": "reserved",
                "dispatchStatus": "pending",
                "commissionStatus": "commission_pending",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "announcements": [
            {
                "id": "ann-sql",
                "title": "Anuncio SQL",
                "body": "Anuncio temporal.",
                "placement": "home",
                "priority": 10,
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "media_assets": [
            {
                "id": "media-sql",
                "title": "Documento SQL",
                "assetType": "pdf",
                "type": "document",
                "documentType": "technical_sheet",
                "subjectType": "product",
                "subjectId": "prod-sql",
                "subjectLabel": "Producto SQL",
                "productId": "prod-sql",
                "url": "https://example.com/sql.pdf",
                "visibility": "public",
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "service_technicians": [
            {
                "id": "svc-sql",
                "name": "Servicio SQL",
                "companyName": "Servicio SQL",
                "contactName": "Tecnico SQL",
                "phone": "+580000000004",
                "whatsapp": "+580000000004",
                "email": "svc.sql@wulkan.test",
                "state": "Carabobo",
                "city": "Valencia",
                "address": "Zona SQL",
                "specialties": ["Motosierras"],
                "coverage": "Centro",
                "status": "active",
                "visibleInApp": True,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "credit_movements": [],
        "stock_movements": [],
        "notifications": [],
        "audit_events": [],
    }
    normalize_store(store)
    return store


def authenticate(client) -> None:
    with client.session_transaction() as session:
        session["admin_authenticated"] = True
        session["admin_user_id"] = ADMIN_ID
        session["admin_name"] = "Admin SQL Smoke"
        session["admin_role"] = "super_admin"
        session["admin_session_version"] = 0
        session["_csrf_token"] = CSRF


def post(client, path: str, data: dict | None = None):
    payload = {"_csrf_token": CSRF}
    if data:
        payload.update(data)
    response = client.post(path, data=payload, follow_redirects=False)
    if response.status_code >= 500:
        raise AssertionError(f"{path}: HTTP {response.status_code} {response.get_data(as_text=True)[:200]}")
    return response


def main() -> int:
    drop_database()
    init_database()
    sync_store_to_sql(base_store())
    now = utc_now()
    sync_admin_user_records(
        [
            {
                "id": "admin-seller-new-id",
                "name": "Vendedor SQL Reactivado",
                "email": "vendedor.eliminado.sql@wulkan.test",
                "passwordHash": generate_password_hash("SellerSql2026"),
                "role": "sales",
                "status": "active",
                "sessionVersion": 0,
                "mustChangePassword": True,
                "activeSessions": [],
                "sellerCode": "VEN-SQL-REACT",
                "zone": "Carabobo",
                "commissionRate": 4.0,
                "createdAt": now,
                "updatedAt": now,
            }
        ]
    )
    sync_client_records(
        [
            {
                "id": "client-sql-new-id",
                "businessName": "Ferreteria SQL Reactivada",
                "contactName": "Comprador Reactivado SQL",
                "email": "deleted.sql@wulkan.test",
                "passwordHash": generate_password_hash("ClientSql2026"),
                "status": "active",
                "clientType": "ferretero",
                "taxId": "J-44444444-4",
                "phone": "+580000000005",
                "address": "Av SQL Reactivada",
                "city": "Valencia",
                "state": "Carabobo",
                "creditEnabled": False,
                "creditLimitUsd": 0,
                "creditUsedUsd": 0,
                "creditRequestStatus": "none",
                "paymentTermsDays": 0,
                "allowedPaymentTermsDays": [0],
                "defaultSaleType": "cash",
                "createdAt": now,
                "updatedAt": now,
            }
        ]
    )
    app = wulkan_app.app
    app.config.update(TESTING=True, SECRET_KEY="sql-integrity-smoke-secret", REQUIRE_MOBILE_TOKEN=True)

    with app.test_client() as client:
        mobile_login = client.post(
            "/api/mobile/auth/login",
            json={"email": "admin.sql@wulkan.test", "password": "AdminSql2026"},
        )
        assert mobile_login.status_code == 200, mobile_login.get_data(as_text=True)
        duplicate_mobile_client = client.post(
            "/api/mobile/seller/clients",
            headers={"Authorization": f"Bearer {mobile_login.get_json()['accessToken']}"},
            json={
                "businessName": "Ferreteria Reutilizada SQL",
                "email": "deleted.sql@wulkan.test",
                "taxId": "J-55555555-5",
                "contactName": "Comprador Reutilizado SQL",
                "phone": "+58 412-5555555",
                "address": "Av SQL Reutilizada",
                "state": "Carabobo",
                "city": "Valencia",
                "creditRequestedUsd": 0,
                "allowedPaymentTermsDays": "0,15,30",
            },
        )
        assert duplicate_mobile_client.status_code == 200, duplicate_mobile_client.get_data(as_text=True)
        assert duplicate_mobile_client.get_json()["alreadyExists"] is True
        assert duplicate_mobile_client.is_json
        created_mobile_client = client.post(
            "/api/mobile/seller/clients",
            headers={
                "Authorization": f"Bearer {mobile_login.get_json()['accessToken']}",
                "Idempotency-Key": "sql-smoke-client-001",
            },
            json={
                "businessName": "Ferreteria SQL Nueva",
                "email": "ferreteria.sql.nueva@wulkan.test",
                "taxId": "J-55555555-6",
                "contactName": "Comprador SQL Nuevo",
                "phone": "+58 412-5555556",
                "address": "Av SQL Nueva",
                "state": "Carabobo",
                "city": "Valencia",
                "creditRequestedUsd": 250,
                "allowedPaymentTermsDays": [0, 15],
                "defaultSaleType": "credit_line",
                "password": "ClienteSql2026",
            },
        )
        assert created_mobile_client.status_code == 201, created_mobile_client.get_data(as_text=True)
        assert created_mobile_client.is_json
        authenticate(client)
        checks = [
            ("/clients/client-sql/delete", None),
            ("/products/prod-sql/delete", None),
            ("/products/prod-sql-free/delete", None),
            ("/categories/cat-sql-root/status", {"status": "inactive"}),
            ("/categories/cat-sql-root/delete", None),
            ("/categories/cat-sql-empty/delete", None),
            ("/categories/cat-sql-parent-delete/delete", None),
            ("/media-library/media-sql/delete", None),
            ("/documents/media-sql/delete", None),
            ("/announcements/ann-sql/delete", None),
            ("/service-technicians/svc-sql/delete", None),
        ]
        for path, data in checks:
            post(client, path, data)

    store = load_sql_store()
    client_record = next(item for item in store["clients"] if item["id"] == "client-sql")
    mobile_client_record = next(
        item for item in store["clients"] if item["email"] == "ferreteria.sql.nueva@wulkan.test"
    )
    reactivated_client = next(item for item in store["clients"] if item["email"] == "deleted.sql@wulkan.test")
    reactivated_seller = next(
        item for item in store["admin_users"] if item["email"] == "vendedor.eliminado.sql@wulkan.test"
    )
    product_record = next(item for item in store["products"] if item["id"] == "prod-sql")
    category_record = next(item for item in store["categories"] if item["id"] == "cat-sql-root")
    child_category = next(item for item in store["categories"] if item["id"] == "cat-sql-child-preserved")
    assert client_record["status"] == "inactive", "cliente con orden debe quedar inactivo, no borrado fisico"
    assert mobile_client_record["assignedSellerId"] == ADMIN_ID, "cliente movil debe quedar asignado al usuario que lo creo"
    assert mobile_client_record["creditRequestStatus"] == "pending", "credito solicitado desde movil debe quedar pendiente"
    assert mobile_client_record["idempotencyKey"] == "sql-smoke-client-001", "cliente movil debe conservar llave idempotente"
    assert reactivated_client["id"] == "client-sql-deleted", "cliente con email historico debe reutilizar el registro SQL"
    assert reactivated_client["status"] == "active", "cliente historico debe poder reactivarse sin 500"
    assert reactivated_client["businessName"] == "Ferreteria SQL Reactivada", "cliente reactivado debe guardar datos nuevos"
    assert reactivated_seller["id"] == "admin-seller-deleted", "vendedor con email historico debe reutilizar el registro SQL"
    assert reactivated_seller["status"] == "active", "vendedor historico debe poder reactivarse sin 500"
    assert reactivated_seller["sellerCode"] == "VEN-SQL-REACT", "vendedor reactivado debe guardar los nuevos datos"
    assert product_record["status"] == "inactive", "producto con orden debe quedar inactivo, no borrado fisico"
    assert category_record["status"] == "inactive", "categoria con producto debe quedar inactiva"
    assert child_category.get("parentId") == "", "eliminar categoria padre debe conservar y promover la subcategoria"
    print("Graphify SQL integrity smoke")
    print("----------------------------")
    print("OK: acciones destructivas no rompen integridad SQL ni generan 500.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
