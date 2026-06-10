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


SELLER_EMAIL = "vendedor.flow@wulkan.test"
SELLER_PASSWORD = "Vendedor2026"
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

    audit_events = state["audit_events"]
    assert any(event["action"] == "credit_decision" for event in audit_events)
    credit_event = next(event for event in audit_events if event["action"] == "credit_decision")
    assert "creditLimitUsd" in credit_event["metadata"]["changedFields"]
    assert any(event["action"] == "create" and event["entityType"] == "order" for event in audit_events)

    print("Graphify smoke comercial")
    print("------------------------")
    print("OK vendedor crea cliente y queda asignado")
    print("OK gerente aprueba credito B2B con auditoria before/after")
    print("OK ferretero cambia clave temporal")
    print("OK ferretero crea orden con linea de credito")
    print("OK orden registra vendedor, comision, stock reservado y credito restante")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
