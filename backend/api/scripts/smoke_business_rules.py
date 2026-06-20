from __future__ import annotations

import copy
import sys
from pathlib import Path

from flask import session as flask_session

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app as FVENTAS_app
from store import utc_now


def generate_password_hash(password: str) -> str:
    return FVENTAS_app.generate_password_hash(password, method="pbkdf2:sha256:1")


def base_store() -> dict:
    now = utc_now()
    return {
        "companies": [
            {
                "id": "company-fventas-chile",
                "name": "FVENTAS",
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "subscriptions": [
            {
                "id": "sub-fventas-chile",
                "companyId": "company-fventas-chile",
                "planId": "fventas-pro-monthly",
                "status": "active",
                "priceClp": 69990,
                "currency": "CLP",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "categories": [
            {
                "id": "cat-rules",
                "companyId": "company-fventas-chile",
                "name": "Reglas",
                "slug": "reglas",
                "status": "active",
                "visibleInApp": True,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "products": [
            {
                "id": "prod-rules",
                "companyId": "company-fventas-chile",
                "sku": "FVT-RULE-01",
                "title": "Producto Reglas",
                "description": "Producto para reglas criticas.",
                "productType": "machine",
                "categoryId": "cat-rules",
                "categoryName": "Reglas",
                "publicPriceUsd": 100,
                "originalPriceUsd": 120,
                "discountPercent": 0,
                "b2bPriceUsd": 90,
                "exchangeRateUsdVes": 1.0,
                "stock": 2,
                "reserved": 0,
                "status": "active",
                "visibleInApp": True,
                "imageUrl": "",
                "imageUrls": [],
                "pdfUrls": [],
                "variants": [],
                "specifications": {},
                "requiresQuote": False,
                "requiresTechnicalValidation": False,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "clients": [
            {
                "id": "client-rules",
                "companyId": "company-fventas-chile",
                "businessName": "Cliente Reglas",
                "email": "cliente.rules@FVENTAS.test",
                "passwordHash": generate_password_hash("ClienteRules2026"),
                "status": "active",
                "clientType": "b2b",
                "taxId": "11.111.111-1",
                "phone": "+56 9 1000 0000",
                "address": "Direccion reglas",
                "city": "Santiago",
                "state": "Metropolitana",
                "creditEnabled": True,
                "creditLimitUsd": 100,
                "creditUsedUsd": 0,
                "paymentTermsDays": 15,
                "allowedPaymentTermsDays": [0, 15],
                "defaultSaleType": "credit_line",
                "collectionStatus": "blocked",
                "creditRequestStatus": "approved",
                "creditRiskLevel": "low",
                "mobileSessionVersion": 0,
                "mustChangePassword": False,
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "client-mobile-inconsistent-rules",
                "companyId": "company-fventas-chile",
                "businessName": "Cliente Movil Inconsistente",
                "email": "cliente.mobile.inconsistente@FVENTAS.test",
                "passwordHash": generate_password_hash("ClienteMobileRules2026"),
                "status": "blocked_credit",
                "clientType": "b2b",
                "taxId": "22.222.222-2",
                "phone": "+56 9 2222 2222",
                "address": "Direccion inconsistente",
                "city": "Santiago",
                "state": "Metropolitana",
                "creditEnabled": False,
                "creditLimitUsd": 0,
                "creditUsedUsd": 0,
                "paymentTermsDays": 0,
                "allowedPaymentTermsDays": [0],
                "defaultSaleType": "cash",
                "collectionStatus": "without_debt",
                "creditRequestStatus": "none",
                "creditRiskLevel": "low",
                "mobileAccessEnabled": True,
                "mobileSessionVersion": 0,
                "mustChangePassword": False,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "orders": [
            {
                "id": "order-cancelled-rules",
                "companyId": "company-fventas-chile",
                "orderId": "order-cancelled-rules",
                "customerId": "client-rules",
                "customer": {"id": "client-rules", "name": "Cliente Reglas"},
                "items": [{"productId": "prod-rules", "sku": "FVT-RULE-01", "quantity": 1, "unitPriceUsd": 90}],
                "totalUsd": 90,
                "netUsd": 90,
                "balanceUsd": 0,
                "paidUsd": 90,
                "saleType": "cash",
                "paymentTermDays": 0,
                "status": "cancelled",
                "creditStatus": "cancelled",
                "inventoryStatus": "released",
                "dispatchStatus": "cancelled",
                "commissionUsd": 5,
                "commissionStatus": "commission_pending",
                "commissionRatePercent": 5,
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "order-no-stock-rules",
                "companyId": "company-fventas-chile",
                "orderId": "order-no-stock-rules",
                "customerId": "client-rules",
                "customer": {"id": "client-rules", "name": "Cliente Reglas"},
                "items": [{"productId": "prod-rules", "sku": "FVT-RULE-01", "quantity": 10, "unitPriceUsd": 90}],
                "totalUsd": 900,
                "netUsd": 900,
                "balanceUsd": 900,
                "paidUsd": 0,
                "saleType": "cash",
                "paymentTermDays": 0,
                "status": "credit_review",
                "creditStatus": "without_credit",
                "inventoryStatus": "review",
                "dispatchStatus": "pending",
                "commissionUsd": 0,
                "commissionStatus": "commission_cancelled",
                "createdAt": now,
                "updatedAt": now,
            },
        ],
        "admin_users": [
            {
                "id": "admin-rules",
                "companyId": "company-fventas-chile",
                "name": "Admin Reglas",
                "email": "admin.rules@FVENTAS.test",
                "passwordHash": generate_password_hash("AdminRules2026"),
                "role": "super_admin",
                "status": "active",
                "sessionVersion": 0,
                "mustChangePassword": False,
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "operator-rules",
                "companyId": "company-fventas-chile",
                "name": "Operador Reglas",
                "email": "operador.rules@FVENTAS.test",
                "passwordHash": generate_password_hash("OperadorRules2026"),
                "role": "operator",
                "status": "active",
                "sessionVersion": 0,
                "mustChangePassword": False,
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "seller-mobile-inconsistent-rules",
                "companyId": "company-fventas-chile",
                "name": "Vendedor Movil Inconsistente",
                "email": "seller.mobile.inconsistent@FVENTAS.test",
                "passwordHash": generate_password_hash("SellerMobileRules2026"),
                "role": "sales",
                "status": "active",
                "sessionVersion": 0,
                "mustChangePassword": False,
                "mobileAccessEnabled": True,
                "deletionStatus": "requested",
                "createdAt": now,
                "updatedAt": now,
            },
        ],
        "announcements": [],
        "media_assets": [],
        "credit_movements": [],
        "stock_movements": [],
        "notifications": [],
        "audit_events": [],
    }


def assert_status(response, expected: int, label: str):
    if response.status_code != expected:
        raise AssertionError(f"{label}: HTTP {response.status_code} {response.get_data(as_text=True)}")
    return response.get_json() if response.is_json else response


def main() -> int:
    state = base_store()

    def save_store_override(store: dict) -> None:
        if store is state:
            return
        snapshot = copy.deepcopy(store)
        state.clear()
        state.update(snapshot)

    FVENTAS_app.load_store = lambda: state
    FVENTAS_app.save_store = save_store_override
    FVENTAS_app.app.config.update(
        TESTING=True,
        SECRET_KEY="business-rules-smoke-secret",
        REQUIRE_MOBILE_TOKEN=True,
        WTF_CSRF_ENABLED=False,
    )
    with FVENTAS_app.app.test_request_context("/sellers/import", method="POST"):
        flask_session["admin_authenticated"] = True
        flask_session["admin_user_id"] = "admin-rules"
        flask_session["admin_name"] = "Admin Reglas"
        flask_session["admin_role"] = "super_admin"
        flask_session["company_id"] = "company-fventas-chile"
        state["companies"].append(
            {
                "id": "company-rules-other",
                "name": "Empresa Reglas Ajena",
                "status": "active",
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )
        state["admin_users"].append(
            {
                "id": "seller-other-rules",
                "companyId": "company-rules-other",
                "name": "Vendedor Ajeno Reglas",
                "email": "vendedor.import.rules@FVENTAS.test",
                "passwordHash": generate_password_hash("VendedorOther2026"),
                "role": "sales",
                "status": "active",
                "sessionVersion": 0,
                "mustChangePassword": False,
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )
        state["categories"].append(
            {
                "id": "cat-other-rules",
                "companyId": "company-rules-other",
                "name": "Categoria Ajena Reglas",
                "slug": "categoria-ajena-reglas",
                "status": "active",
                "visibleInApp": True,
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )
        seller_result = FVENTAS_app.import_sellers_rows(
            state,
            [
                {
                    "name": "Vendedor Importado Reglas",
                    "email": "vendedor.nuevo.rules@FVENTAS.test",
                    "password": "VendedorNuevo2026",
                },
                {
                    "name": "Vendedor Ajeno Editado",
                    "email": "vendedor.import.rules@FVENTAS.test",
                    "password": "VendedorOther2026",
                },
            ],
        )
        assert seller_result["created"] == 1
        assert seller_result["errors"], "importar vendedor de otra empresa debe quedar bloqueado"
        imported_seller = next(item for item in state["admin_users"] if item["email"] == "vendedor.nuevo.rules@fventas.test")
        assert imported_seller["companyId"] == "company-fventas-chile"
        assert next(item for item in state["admin_users"] if item["id"] == "seller-other-rules")["name"] == "Vendedor Ajeno Reglas"
        client_result = FVENTAS_app.import_clients_rows(
            state,
            [
                {
                    "businessname": "Cliente Importado Reglas",
                    "email": "cliente.importado.rules@FVENTAS.test",
                    "taxid": "76.000.000-0",
                    "phone": "+56 9 1111 2222",
                    "state": "Metropolitana",
                    "city": "Santiago",
                    "password": "ClienteImportado2026",
                }
            ],
        )
        assert client_result["created"] == 1
        imported_client = next(item for item in state["clients"] if item["email"] == "cliente.importado.rules@fventas.test")
        assert imported_client["companyId"] == "company-fventas-chile"
        invalid_client_catalog_result = FVENTAS_app.import_clients_rows(
            state,
            [
                {
                    "businessname": "Cliente Catalogo Invalido",
                    "email": "cliente.catalogo.invalido@FVENTAS.test",
                    "taxid": "76.000.001-9",
                    "phone": "+56 9 1111 3333",
                    "state": "Metropolitana",
                    "city": "Santiago",
                    "password": "ClienteCatalogo2026",
                    "clientcategory": "vip-fuera-catalogo",
                    "pricelist": "lista-secreta",
                    "defaultsaletype": "credito-ilimitado",
                }
            ],
        )
        assert invalid_client_catalog_result["created"] == 0
        assert invalid_client_catalog_result["errors"], "importar cliente con catalogos invalidos debe fallar"

    with FVENTAS_app.app.test_client() as client:
        with client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["admin_user_id"] = "admin-rules"
            session["admin_name"] = "Admin Reglas"
            session["admin_role"] = "super_admin"
            session["company_id"] = "company-fventas-chile"
            session["_csrf_token"] = "csrf-rules"

        rules_page = assert_status(client.get("/business-rules"), 200, "modulo reglas negocio")
        rules_html = rules_page.get_data(as_text=True)
        assert "Reglas negocio" in rules_html
        assert "Acceso movil respeta bloqueos" in rules_html
        assert "Cliente Movil Inconsistente" in rules_html
        assert "Vendedor Movil Inconsistente" in rules_html
        categories_csv = assert_status(client.get("/categories/export"), 200, "exportacion categorias por empresa").get_data(as_text=True)
        assert "Reglas" in categories_csv
        assert "Categoria Ajena Reglas" not in categories_csv, "exportacion de categorias no debe filtrar otro tenant"

        _, error = FVENTAS_app.build_commercial_order(state, {"customerId": "", "items": []})
        assert "Cliente" in error
        _, error = FVENTAS_app.build_commercial_order(state, {"customerId": "client-rules", "items": []})
        assert "productos" in error
        _, error = FVENTAS_app.build_commercial_order(
            state,
            {
                "customerId": "client-rules",
                "saleType": "cash",
                "items": [{"productId": "prod-rules", "sku": "FVT-RULE-01", "quantity": 1}],
            },
        )
        assert "cobranza" in error

        priced_state = copy.deepcopy(state)
        priced_state["clients"][0]["collectionStatus"] = "without_debt"
        priced_state["clients"][0]["defaultSaleType"] = "cash"
        normal_order, error = FVENTAS_app.build_commercial_order(
            priced_state,
            {
                "customerId": "client-rules",
                "saleType": "cash",
                "items": [{"productId": "prod-rules", "quantity": 1, "unitPriceUsd": 1}],
            },
        )
        assert not error
        assert normal_order["totalUsd"] == 90, "payload no confiable debe usar precio catalogo"
        quote_order, error = FVENTAS_app.build_commercial_order(
            priced_state,
            {
                "customerId": "client-rules",
                "saleType": "cash",
                "items": [{"productId": "prod-rules", "quantity": 1, "unitPriceUsd": 81}],
                "preview": {"grossUsd": 90, "totalUsd": 81},
            },
            trusted_pricing=True,
        )
        assert not error
        assert quote_order["totalUsd"] == 81, "conversion de cotizacion debe conservar precio neto negociado"
        assert quote_order["discountUsd"] == 9, "conversion de cotizacion debe conservar descuento global"

        before_products = len(state["products"])
        assert_status(
            client.post(
                "/products/new",
                data={
                    "_csrf_token": "csrf-rules",
                    "sku": "FVT-RULE-01",
                    "title": "Producto Duplicado",
                    "categoryId": "cat-rules",
                    "productType": "machine",
                    "status": "active",
                    "publicPriceUsd": "10",
                    "b2bPriceUsd": "9",
                    "originalPriceUsd": "10",
                    "stock": "1",
                },
            ),
            200,
            "bloquea SKU duplicado",
        )
        assert len(state["products"]) == before_products

        assert_status(
            client.post(
                "/products/new",
                data={
                    "_csrf_token": "csrf-rules",
                    "sku": "FVT-RULE-02",
                    "title": "Producto Precio Malo",
                    "categoryId": "cat-rules",
                    "productType": "machine",
                    "status": "active",
                    "publicPriceUsd": "-1",
                    "b2bPriceUsd": "0",
                    "originalPriceUsd": "0",
                    "stock": "1",
                },
            ),
            200,
            "bloquea precio negativo",
        )
        assert len(state["products"]) == before_products

        before_clients = len(state["clients"])
        assert_status(
            client.post(
                "/clients",
                data={
                    "_csrf_token": "csrf-rules",
                    "businessName": "Cliente RUT Duplicado",
                    "email": "duplicado.rules@FVENTAS.test",
                    "password": "DuplicadoRules2026",
                    "taxId": "11.111.111-1",
                    "status": "active",
                    "clientType": "b2b",
                    "collectionStatus": "without_debt",
                    "creditRequestStatus": "none",
                },
            ),
            200,
            "bloquea RUT duplicado",
        )
        assert len(state["clients"]) == before_clients

        login = assert_status(
            client.post(
                "/api/mobile/auth/login",
                json={"email": "cliente.rules@FVENTAS.test", "password": "ClienteRules2026"},
            ),
            200,
            "login cliente bloqueado por cobranza",
        )
        rejected_order = assert_status(
            client.post(
                "/api/mobile/orders",
                headers={"Authorization": f"Bearer {login['accessToken']}"},
                json={
                    "saleType": "cash",
                    "items": [{"productId": "prod-rules", "sku": "FVT-RULE-01", "quantity": 1}],
                },
            ),
            400,
            "bloquea venta a cliente con cobranza bloqueada",
        )
        assert "cobranza" in rejected_order["error"]

        assert_status(
            client.post(
                "/orders/order-no-stock-rules/status",
                data={"_csrf_token": "csrf-rules", "status": "approved_with_credit"},
                follow_redirects=False,
            ),
            302,
            "no aprueba orden sin stock",
        )
        no_stock_order = next(order for order in state["orders"] if order["id"] == "order-no-stock-rules")
        assert no_stock_order["status"] == "credit_review"
        assert no_stock_order["stockStatus"] == "insufficient_stock"

        assert_status(
            client.post(
                "/commissions/order-cancelled-rules/status",
                data={"_csrf_token": "csrf-rules", "commissionStatus": "commission_approved"},
            ),
            400,
            "no aprueba comision anulada",
        )
        cancelled_order = next(order for order in state["orders"] if order["id"] == "order-cancelled-rules")
        assert cancelled_order["commissionStatus"] == "commission_pending"

        with client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["admin_user_id"] = "operator-rules"
            session["admin_name"] = "Operador Reglas"
            session["admin_role"] = "operator"
            session["_csrf_token"] = "csrf-rules"

        assert_status(
            client.post(
                "/credit/client-rules/decision",
                data={"_csrf_token": "csrf-rules", "decision": "approved", "creditLimitUsd": "500"},
            ),
            403,
            "operador no aprueba credito",
        )

    print("Smoke business rules OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
