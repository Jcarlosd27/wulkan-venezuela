from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app as wulkan_app
from store import utc_now
from werkzeug.security import generate_password_hash


def base_store() -> dict:
    now = utc_now()
    return {
        "categories": [
            {
                "id": "cat-rules",
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
                "sku": "WUL-RULE-01",
                "title": "Producto Reglas",
                "description": "Producto para reglas criticas.",
                "productType": "machine",
                "categoryId": "cat-rules",
                "categoryName": "Reglas",
                "publicPriceUsd": 100,
                "originalPriceUsd": 120,
                "discountPercent": 0,
                "b2bPriceUsd": 90,
                "exchangeRateUsdVes": 38.5,
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
                "businessName": "Ferreteria Reglas",
                "email": "cliente.rules@wulkan.test",
                "passwordHash": generate_password_hash("ClienteRules2026"),
                "status": "active",
                "clientType": "ferretero",
                "taxId": "J-11111111-1",
                "phone": "+580000000000",
                "address": "Direccion reglas",
                "city": "Valencia",
                "state": "Carabobo",
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
            }
        ],
        "orders": [
            {
                "id": "order-cancelled-rules",
                "orderId": "order-cancelled-rules",
                "customerId": "client-rules",
                "customer": {"id": "client-rules", "name": "Ferreteria Reglas"},
                "items": [{"productId": "prod-rules", "sku": "WUL-RULE-01", "quantity": 1, "unitPriceUsd": 90}],
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
                "orderId": "order-no-stock-rules",
                "customerId": "client-rules",
                "customer": {"id": "client-rules", "name": "Ferreteria Reglas"},
                "items": [{"productId": "prod-rules", "sku": "WUL-RULE-01", "quantity": 10, "unitPriceUsd": 90}],
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
                "name": "Admin Reglas",
                "email": "admin.rules@wulkan.test",
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
                "name": "Operador Reglas",
                "email": "operador.rules@wulkan.test",
                "passwordHash": generate_password_hash("OperadorRules2026"),
                "role": "operator",
                "status": "active",
                "sessionVersion": 0,
                "mustChangePassword": False,
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

    wulkan_app.load_store = lambda: state
    wulkan_app.save_store = save_store_override
    wulkan_app.app.config.update(
        TESTING=True,
        SECRET_KEY="business-rules-smoke-secret",
        REQUIRE_MOBILE_TOKEN=True,
        WTF_CSRF_ENABLED=False,
    )

    with wulkan_app.app.test_client() as client:
        with client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["admin_user_id"] = "admin-rules"
            session["admin_name"] = "Admin Reglas"
            session["admin_role"] = "super_admin"
            session["_csrf_token"] = "csrf-rules"

        rules_page = assert_status(client.get("/business-rules"), 200, "modulo reglas negocio")
        assert "Reglas negocio" in rules_page.get_data(as_text=True)

        _, error = wulkan_app.build_commercial_order(state, {"customerId": "", "items": []})
        assert "Cliente" in error
        _, error = wulkan_app.build_commercial_order(state, {"customerId": "client-rules", "items": []})
        assert "productos" in error
        _, error = wulkan_app.build_commercial_order(
            state,
            {
                "customerId": "client-rules",
                "saleType": "cash",
                "items": [{"productId": "prod-rules", "sku": "WUL-RULE-01", "quantity": 1}],
            },
        )
        assert "cobranza" in error

        before_products = len(state["products"])
        assert_status(
            client.post(
                "/products/new",
                data={
                    "_csrf_token": "csrf-rules",
                    "sku": "WUL-RULE-01",
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
                    "sku": "WUL-RULE-02",
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
                    "businessName": "Ferreteria RIF Duplicado",
                    "email": "duplicado.rules@wulkan.test",
                    "password": "DuplicadoRules2026",
                    "taxId": "J-11111111-1",
                    "status": "active",
                    "clientType": "ferretero",
                    "collectionStatus": "without_debt",
                    "creditRequestStatus": "none",
                },
            ),
            200,
            "bloquea RIF duplicado",
        )
        assert len(state["clients"]) == before_clients

        login = assert_status(
            client.post(
                "/api/mobile/auth/login",
                json={"email": "cliente.rules@wulkan.test", "password": "ClienteRules2026"},
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
                    "items": [{"productId": "prod-rules", "sku": "WUL-RULE-01", "quantity": 1}],
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
