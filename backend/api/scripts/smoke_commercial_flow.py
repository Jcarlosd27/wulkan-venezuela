from __future__ import annotations

import copy
import io
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app as wulkan_app
from store import utc_now
from werkzeug.security import generate_password_hash


SELLER_EMAIL = "vendedor.flow@wulkan.test"
SELLER_PASSWORD = "Vendedor2026"
SUPER_ADMIN_ID = "admin-super-flow"
MANAGER_ID = "admin-manager-flow"
CLIENT_PASSWORD = "ClienteTemporal2026"
CLIENT_NEW_PASSWORD = "ClienteFinal2026"


def base_store() -> dict:
    now = utc_now()
    return {
        "categories": [
            {
                "id": "cat-maquinaria-flow",
                "name": "Maquinaria profesional",
                "description": "Equipos Wulkan para venta B2B.",
                "imageUrl": "https://cdn.example.com/categorias/maquinaria.jpg",
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "products": [
            {
                "id": "prod-flow-motosierra",
                "sku": "WUL-FLOW-45CC",
                "title": "Motosierra Wulkan 45cc Flow",
                "description": "Producto realista para smoke comercial.",
                "productType": "machine",
                "categoryId": "cat-maquinaria-flow",
                "categoryName": "Maquinaria profesional",
                "publicPriceUsd": 185.0,
                "originalPriceUsd": 215.0,
                "discountPercent": 14.0,
                "b2bPriceUsd": 162.0,
                "exchangeRateUsdVes": 38.5,
                "stock": 12,
                "reserved": 0,
                "status": "active",
                "imageUrl": "https://cdn.example.com/productos/motosierra.jpg",
                "imageUrls": ["https://cdn.example.com/productos/motosierra.jpg"],
                "pdfUrls": ["https://cdn.example.com/productos/motosierra.pdf"],
                "variants": ["18 pulgadas"],
                "specifications": {"Motor": "45cc", "Garantia": "6 meses"},
                "requiresQuote": False,
                "requiresTechnicalValidation": False,
                "rotationLast30Days": 0,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "announcements": [
            {
                "id": "ann-flow-home",
                "title": "Promocion Wulkan Flow",
                "body": "Banner cargado desde admin para carrusel.",
                "placement": "home",
                "priority": 90,
                "ctaLabel": "Ver catalogo",
                "ctaUrl": "wulkan://catalog",
                "imageUrl": "https://cdn.example.com/banners/wulkan-flow.jpg",
                "startsAt": now,
                "endsAt": "",
                "status": "active",
                "updatedAt": now,
            }
        ],
        "orders": [],
        "admin_users": [
            {
                "id": SUPER_ADMIN_ID,
                "name": "Super Admin Flow",
                "email": "super.flow@wulkan.test",
                "passwordHash": generate_password_hash("Super2026"),
                "role": "super_admin",
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": MANAGER_ID,
                "name": "Gerente Flow",
                "email": "gerente.flow@wulkan.test",
                "passwordHash": generate_password_hash("Gerente2026"),
                "role": "commercial_manager",
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "admin-seller-flow",
                "name": "Vendedor Flow",
                "email": SELLER_EMAIL,
                "passwordHash": generate_password_hash(SELLER_PASSWORD),
                "role": "sales",
                "status": "active",
                "sellerCode": "VEN-FLOW",
                "sellerZone": "Centro",
                "commissionRatePercent": 5.0,
                "salesGoalUsd": 1000.0,
                "createdAt": now,
                "updatedAt": now,
            },
        ],
        "clients": [],
        "credit_movements": [],
        "service_technicians": [
            {
                "id": "svc-flow-valencia",
                "name": "Servicio Wulkan Valencia Flow",
                "companyName": "Servicio Wulkan Valencia",
                "contactName": "Tecnico principal",
                "phone": "+58 000-0000000",
                "whatsapp": "+58 000-0000000",
                "email": "servicio.flow@wulkan.test",
                "state": "Carabobo",
                "city": "Valencia",
                "address": "Zona industrial",
                "specialties": ["Motosierras"],
                "coverage": "Centro occidente",
                "status": "active",
                "visibleInApp": True,
                "notes": "",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "audit_events": [],
        "media_assets": [],
        "stock_movements": [],
    }


def assert_status(response, expected: int, label: str) -> dict:
    if response.status_code != expected:
        raise AssertionError(f"{label}: HTTP {response.status_code} {response.get_data(as_text=True)}")
    if response.is_json:
        return response.get_json() or {}
    return {}


def main() -> int:
    state = base_store()

    def load_store_override():
        return state

    def save_store_override(store: dict) -> None:
        if store is state:
            return
        snapshot = copy.deepcopy(store)
        state.clear()
        state.update(snapshot)

    wulkan_app.load_store = load_store_override
    wulkan_app.save_store = save_store_override
    wulkan_app.app.config["REQUIRE_MOBILE_TOKEN"] = True
    wulkan_app.app.config["TESTING"] = True

    client = wulkan_app.app.test_client()

    with client.session_transaction() as session:
        session["admin_authenticated"] = True
        session["admin_user_id"] = SUPER_ADMIN_ID
        session["admin_name"] = "Super Admin Flow"
        session["admin_role"] = "super_admin"
        session["_csrf_token"] = "csrf-flow"

    assert_status(
        client.post(
            "/products/import",
            data={
                "_csrf_token": "csrf-flow",
                "importFile": (
                    io.BytesIO(
                        b"sku,nombre,categoria,precio_publico_usd,precio_b2b_usd,stock,imagenes\n"
                        b"WUL-FLOW-45CC,Motosierra Wulkan 45cc Flow,Maquinaria profesional,185,162,12,https://cdn.example.com/productos/motosierra.jpg|https://cdn.example.com/productos/motosierra-lateral.jpg\n"
                    ),
                    "products.csv",
                ),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        ),
        302,
        "importar productos",
    )
    imported_product = state["products"][0]
    assert len(imported_product["imageUrls"]) == 2
    api_meta = assert_status(client.get("/api/v1/mobile/meta"), 200, "api v1 meta")
    assert api_meta["meta"]["apiVersion"] == "v1"

    seller_login = assert_status(
        client.post(
            "/api/mobile/auth/login",
            json={"email": SELLER_EMAIL, "password": SELLER_PASSWORD},
        ),
        200,
        "login vendedor",
    )
    seller_token = seller_login["accessToken"]
    assert seller_login["customer"]["accountRole"] == "sales"
    seller_login_v1 = assert_status(
        client.post(
            "/api/v1/mobile/auth/login",
            json={"email": SELLER_EMAIL, "password": SELLER_PASSWORD},
        ),
        200,
        "login vendedor v1",
    )
    assert seller_login_v1["customer"]["accountRole"] == "sales"
    seller_refresh_v1 = assert_status(
        client.post(
            "/api/v1/mobile/auth/refresh",
            headers={"Authorization": f"Bearer {seller_login_v1['accessToken']}"},
        ),
        200,
        "refresh vendedor v1",
    )
    assert seller_refresh_v1["customer"]["accountRole"] == "sales"

    new_client = assert_status(
        client.post(
            "/api/mobile/seller/clients",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={
                "businessName": "Ferreteria Flow Valencia",
                "taxId": "J-12345678-9",
                "contactName": "Comprador Flow",
                "phone": "+58 000-1111111",
                "email": "ferreteria.flow@wulkan.test",
                "address": "Av. Industrial",
                "state": "Carabobo",
                "city": "Valencia",
                "deliveryZone": "Centro",
                "creditRequestedUsd": 500,
                "allowedPaymentTermsDays": [0, 15, 30],
                "defaultSaleType": "credit_line",
                "password": CLIENT_PASSWORD,
            },
        ),
        201,
        "crear cliente vendedor",
    )
    client_id = new_client["client"]["id"]
    assert new_client["client"]["assignedSeller"]["id"] == "admin-seller-flow"
    assert new_client["client"]["creditRequestStatus"] == "pending"
    seller_clients_paged = assert_status(
        client.get(
            "/api/v1/mobile/seller/clients?limit=1&q=Flow",
            headers={"Authorization": f"Bearer {seller_token}"},
        ),
        200,
        "clientes vendedor paginados v1",
    )
    assert seller_clients_paged["meta"]["pagination"]["limit"] == 1
    assert seller_clients_paged["items"][0]["id"] == client_id
    mobile_quote = assert_status(
        client.post(
            "/api/v1/mobile/seller/quotes",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={
                "customerId": client_id,
                "saleType": "term_credit",
                "paymentTermDays": 15,
                "items": [
                    {
                        "productId": "prod-flow-motosierra",
                        "quantity": 1,
                        "discountPercent": 5,
                    }
                ],
                "comment": "Cotizacion creada desde smoke v1.",
            },
        ),
        201,
        "crear cotizacion vendedor v1",
    )
    assert mobile_quote["quote"]["totalUsd"] == 153.9
    seller_quotes = assert_status(
        client.get(
            "/api/v1/mobile/seller/quotes",
            headers={"Authorization": f"Bearer {seller_token}"},
        ),
        200,
        "listar cotizaciones vendedor v1",
    )
    assert seller_quotes["items"]
    seller_quotes_paged = assert_status(
        client.get(
            "/api/mobile/seller/quotes?limit=1&status=draft",
            headers={"Authorization": f"Bearer {seller_token}"},
        ),
        200,
        "cotizaciones vendedor legacy paginadas",
    )
    assert seller_quotes_paged["meta"]["pagination"]["limit"] == 1
    mobile_activity = assert_status(
        client.post(
            "/api/v1/mobile/seller/activities",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={
                "clientId": client_id,
                "activityType": "call",
                "note": "Cliente contactado para validar credito y despacho.",
                "nextActionAt": "2026-06-15",
            },
        ),
        201,
        "crear actividad vendedor v1",
    )
    assert mobile_activity["activity"]["type"] == "call"
    seller_activities = assert_status(
        client.get(
            "/api/v1/mobile/seller/activities",
            headers={"Authorization": f"Bearer {seller_token}"},
        ),
        200,
        "listar actividades vendedor v1",
    )
    assert seller_activities["items"]
    seller_activities_paged = assert_status(
        client.get(
            "/api/mobile/seller/activities?limit=1&q=Flow",
            headers={"Authorization": f"Bearer {seller_token}"},
        ),
        200,
        "actividades vendedor legacy paginadas",
    )
    assert seller_activities_paged["meta"]["pagination"]["limit"] == 1
    seller_logout_v1 = assert_status(
        client.post(
            "/api/v1/mobile/auth/logout",
            headers={"Authorization": f"Bearer {seller_login_v1['accessToken']}"},
        ),
        200,
        "logout vendedor v1",
    )
    assert seller_logout_v1["status"] == "logged_out"

    with client.session_transaction() as session:
        session["admin_authenticated"] = True
        session["admin_user_id"] = MANAGER_ID
        session["admin_name"] = "Gerente Flow"
        session["admin_role"] = "commercial_manager"
        session["_csrf_token"] = "csrf-flow"

    assert_status(
        client.post(
            f"/credit/{client_id}/decision",
            data={
                "_csrf_token": "csrf-flow",
                "decision": "approved",
                "creditLimitUsd": "500",
                "paymentTermsDays": "30",
            },
            follow_redirects=False,
        ),
        302,
        "aprobar credito",
    )

    customer_login = assert_status(
        client.post(
            "/api/mobile/auth/login",
            json={"email": "ferreteria.flow@wulkan.test", "password": CLIENT_PASSWORD},
        ),
        200,
        "login ferretero temporal",
    )
    customer_token = customer_login["accessToken"]

    assert_status(
        client.post(
            "/api/mobile/auth/change-password",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={
                "currentPassword": CLIENT_PASSWORD,
                "newPassword": CLIENT_NEW_PASSWORD,
            },
        ),
        200,
        "cambio clave ferretero",
    )

    customer_login = assert_status(
        client.post(
            "/api/mobile/auth/login",
            json={"email": "ferreteria.flow@wulkan.test", "password": CLIENT_NEW_PASSWORD},
        ),
        200,
        "login ferretero final",
    )
    customer_token = customer_login["accessToken"]
    customer_profile_v1 = assert_status(
        client.get(
            "/api/v1/mobile/profile",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "perfil ferretero v1",
    )
    assert customer_profile_v1["profile"]["accountRole"] == "client"
    customer_home_v1 = assert_status(
        client.get(
            "/api/v1/mobile/home",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "home ferretero v1",
    )
    assert customer_home_v1["home"]["banners"]
    product_detail_v1 = assert_status(
        client.get(
            "/api/v1/mobile/products/prod-flow-motosierra",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "detalle producto v1",
    )
    assert product_detail_v1["product"]["sku"] == "WUL-FLOW-45CC"
    products_paged_v1 = assert_status(
        client.get(
            "/api/v1/mobile/products?limit=1&q=WUL-FLOW&sort=price_desc",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "catalogo paginado v1",
    )
    assert products_paged_v1["meta"]["pagination"]["limit"] == 1
    assert products_paged_v1["items"][0]["sku"] == "WUL-FLOW-45CC"
    cart_v1 = assert_status(
        client.get(
            "/api/v1/mobile/cart",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "carrito v1",
    )
    assert cart_v1["mode"] == "local_persistent"

    order = assert_status(
        client.post(
            "/api/mobile/orders",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={
                "saleType": "credit_line",
                "paymentTermDays": 30,
                "items": [
                    {
                        "productId": "prod-flow-motosierra",
                        "sku": "WUL-FLOW-45CC",
                        "quantity": 2,
                    }
                ],
                "preview": {
                    "exchangeRateUsdVes": 38.5,
                },
            },
        ),
        201,
        "orden ferretero",
    )

    created_order = state["orders"][0]
    assert order["sellerId"] == "admin-seller-flow"
    assert created_order["salesChannel"] == "mobile"
    assert created_order["saleType"] == "credit_line"
    assert created_order["creditBeforeUsd"] == 500
    assert created_order["creditAfterUsd"] == 176
    assert created_order["commissionUsd"] == 16.2
    assert created_order["inventoryStatus"] == "reserved"
    orders_v1 = assert_status(
        client.get(
            "/api/v1/mobile/orders",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "ordenes ferretero v1",
    )
    assert orders_v1["items"]
    orders_filtered_v1 = assert_status(
        client.get(
            "/api/v1/mobile/orders?limit=1&saleType=credit_line&sort=balance_desc",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "ordenes ferretero filtradas v1",
    )
    assert orders_filtered_v1["meta"]["filters"]["saleType"] == "credit_line"
    assert orders_filtered_v1["items"][0]["saleType"] == "credit_line"

    cash_order_response = assert_status(
        client.post(
            "/api/mobile/orders",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={
                "saleType": "cash",
                "paymentTermDays": 0,
                "items": [
                    {
                        "productId": "prod-flow-motosierra",
                        "sku": "WUL-FLOW-45CC",
                        "quantity": 1,
                    }
                ],
                "preview": {
                    "exchangeRateUsdVes": 38.5,
                },
            },
        ),
        201,
        "orden ferretero contado",
    )
    cash_order = next(item for item in state["orders"] if item["orderId"] == cash_order_response["orderId"])
    assert cash_order_response["saleType"] == "cash"
    assert cash_order["saleType"] == "cash"
    assert cash_order["status"] == "payment_under_review"
    assert cash_order["creditStatus"] == "without_credit"
    assert cash_order["paymentTermDays"] == 0
    assert cash_order["balanceUsd"] == 162

    assert_status(
        client.post(
            f"/orders/{cash_order['orderId']}/status",
            data={
                "_csrf_token": "csrf-flow",
                "status": "preparing",
                "note": "Validacion de contado para despacho.",
            },
            follow_redirects=False,
        ),
        302,
        "contado a preparacion",
    )
    cash_order = next(item for item in state["orders"] if item["orderId"] == cash_order_response["orderId"])
    assert cash_order["status"] == "preparing"
    assert cash_order["creditStatus"] == "without_credit"
    assert cash_order["inventoryStatus"] == "reserved"

    assert_status(
        client.post(
            f"/orders/{cash_order['orderId']}/payments",
            data={
                "_csrf_token": "csrf-flow",
                "amountUsd": str(cash_order["balanceUsd"]),
                "method": "cash",
                "reference": "EFECTIVO-FLOW",
                "exchangeRateUsdVes": "38.5",
            },
            follow_redirects=False,
        ),
        302,
        "pago contado",
    )
    cash_order = next(item for item in state["orders"] if item["orderId"] == cash_order_response["orderId"])
    assert cash_order["paymentStatus"] == "paid"
    assert cash_order["status"] == "paid"
    assert cash_order["creditStatus"] == "without_credit"
    assert any(
        movement["movementType"] == "payment"
        and movement["orderId"] == cash_order["orderId"]
        and movement["method"] == "cash"
        for movement in state["credit_movements"]
    )

    term_order_response = assert_status(
        client.post(
            "/api/mobile/orders",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={
                "saleType": "term_credit",
                "paymentTermDays": 15,
                "items": [
                    {
                        "productId": "prod-flow-motosierra",
                        "sku": "WUL-FLOW-45CC",
                        "quantity": 1,
                    }
                ],
                "preview": {
                    "exchangeRateUsdVes": 38.5,
                },
            },
        ),
        201,
        "orden ferretero credito por dias",
    )
    term_order = next(item for item in state["orders"] if item["orderId"] == term_order_response["orderId"])
    assert term_order_response["saleType"] == "term_credit"
    assert term_order["saleType"] == "term_credit"
    assert term_order["paymentTermDays"] == 15
    assert term_order["dueDate"]
    assert term_order["status"] == "credit_review"
    assert term_order["creditStatus"] == "manual_review"

    assert_status(
        client.post(
            f"/orders/{term_order['orderId']}/status",
            data={
                "_csrf_token": "csrf-flow",
                "status": "preparing",
                "note": "Credito por dias validado.",
            },
            follow_redirects=False,
        ),
        302,
        "credito por dias a preparacion",
    )
    term_order = next(item for item in state["orders"] if item["orderId"] == term_order_response["orderId"])
    assert term_order["status"] == "preparing"
    assert term_order["creditStatus"] == "approved"
    assert term_order["inventoryStatus"] == "reserved"

    audit_events = state["audit_events"]
    assert any(event["action"] == "bulk_import" and event["entityType"] == "product" for event in audit_events)
    assert any(event["action"] == "credit_decision" for event in audit_events)
    credit_event = next(event for event in audit_events if event["action"] == "credit_decision")
    assert "creditLimitUsd" in credit_event["metadata"]["changedFields"]
    assert any(event["action"] == "create" and event["entityType"] == "order" for event in audit_events)

    print("Graphify smoke comercial")
    print("------------------------")
    print("OK vendedor crea cliente y queda asignado")
    print("OK carga masiva actualiza producto y galeria movil")
    print("OK gerente aprueba credito B2B con auditoria before/after")
    print("OK ferretero cambia clave temporal")
    print("OK ferretero crea orden con linea de credito")
    print("OK orden registra vendedor, comision, stock reservado y credito restante")
    print("OK ferretero crea orden contado y admin ve pago externo por validar")
    print("OK orden contado registra abono efectivo sin consumir linea de credito")
    print("OK ferretero crea credito por dias y admin puede validarlo sin linea")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
