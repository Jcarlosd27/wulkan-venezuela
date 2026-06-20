from __future__ import annotations

import copy
import io
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app as FVENTAS_app
from store import utc_now

generate_password_hash = FVENTAS_app.generate_password_hash


SELLER_EMAIL = "vendedor.flow@FVENTAS.test"
SELLER_PASSWORD = "Vendedor2026"
SUPER_ADMIN_ID = "admin-super-flow"
MANAGER_ID = "admin-manager-flow"
CLIENT_PASSWORD = "ClienteTemporal2026"
CLIENT_NEW_PASSWORD = "ClienteFinal2026"
COMPANY_ID = "company-fventas-chile"
OTHER_COMPANY_ID = "company-competidor-chile"
CLP_RATE = 950


def base_store() -> dict:
    now = utc_now()
    company_id = COMPANY_ID
    other_company_id = OTHER_COMPANY_ID
    return {
        "companies": [
            {
                "id": company_id,
                "name": "FVENTAS",
                "country": "CL",
                "currency": "CLP",
                "baseCurrency": "CLP",
                "salesCurrency": "CLP",
                "localCurrency": "CLP",
                "exchangeRateBaseToLocal": 1,
                "purchaseConditions": {
                    "title": "Condiciones de compra",
                    "defaultSaleType": "cash",
                    "allowedPaymentTermsDays": [0, 15, 30],
                    "scopeLabel": "Solo datos de tu empresa",
                    "note": "Pedidos sujetos a validacion de stock, credito y despacho.",
                },
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": other_company_id,
                "name": "Empresa Competidora",
                "country": "CL",
                "currency": "CLP",
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "subscriptions": [
            {
                "id": "sub-flow-fventas",
                "companyId": company_id,
                "planId": "plan-fventas-pro",
                "status": "active",
                "amountClp": 69990,
                "startedAt": now,
                "currentPeriodStart": now,
                "currentPeriodEnd": "2099-12-31T23:59:59Z",
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "sub-flow-competidor",
                "companyId": other_company_id,
                "planId": "plan-fventas-pro",
                "status": "active",
                "amountClp": 69990,
                "startedAt": now,
                "currentPeriodStart": now,
                "currentPeriodEnd": "2099-12-31T23:59:59Z",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "business_settings": {
            "marketCountry": "CL",
            "salesCurrency": "CLP",
            "localCurrency": "CLP",
            "exchangeRateBaseToLocal": 1,
            "defaultPaymentTermsDays": [0, 15, 30],
            "purchaseConditionsTitle": "Condiciones de compra",
            "purchaseDefaultSaleType": "cash",
            "purchaseConditionsScope": "Solo datos de tu empresa",
            "purchaseConditionsNote": "Pedidos sujetos a validacion de stock, credito y despacho.",
            "orderTermsText": "Pedidos sujetos a validacion de stock, credito y despacho.",
        },
        "categories": [
            {
                "id": "cat-maquinaria-flow",
                "companyId": company_id,
                "name": "Maquinaria profesional",
                "description": "Equipos FVENTAS para venta B2B.",
                "imageUrl": "https://cdn.example.com/categorias/maquinaria.jpg",
                "status": "active",
                "visibleInApp": True,
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "cat-ajena-flow",
                "companyId": other_company_id,
                "name": "Categoria ajena",
                "description": "No debe aparecer en la app de FVENTAS.",
                "imageUrl": "https://cdn.example.com/otra/categoria.jpg",
                "status": "active",
                "visibleInApp": True,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "products": [
            {
                "id": "prod-flow-motosierra",
                "companyId": company_id,
                "sku": "FVT-FLOW-45CC",
                "title": "Motosierra FVENTAS 45cc Flow",
                "description": "Producto realista para smoke comercial.",
                "productType": "machine",
                "categoryId": "cat-maquinaria-flow",
                "categoryName": "Maquinaria profesional",
                "publicPriceUsd": 185.0 * CLP_RATE,
                "originalPriceUsd": 215.0 * CLP_RATE,
                "discountPercent": 14.0,
                "b2bPriceUsd": 162.0 * CLP_RATE,
                "exchangeRateUsdClp": 1.0,
                "stock": 12,
                "reserved": 0,
                "status": "active",
                "imageUrl": "https://cdn.example.com/productos/motosierra.jpg",
                "imageUrls": ["https://cdn.example.com/productos/motosierra.jpg"],
                "pdfUrls": ["https://cdn.example.com/productos/motosierra.pdf"],
                "variants": ["18 pulgadas"],
                "specifications": {"Motor": "45cc", "Garantia": "6 meses"},
                "compatibilityNotes": ["Compatible con FVT-REP-CAD18", "Validar serie antes de despacho"],
                "requiresQuote": False,
                "requiresTechnicalValidation": False,
                "visibleInApp": True,
                "rotationLast30Days": 0,
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "prod-flow-oculto",
                "companyId": company_id,
                "sku": "FVT-FLOW-HIDDEN",
                "title": "Producto oculto FVENTAS Flow",
                "description": "No debe poder venderse desde la app movil.",
                "productType": "machine",
                "categoryId": "cat-maquinaria-flow",
                "categoryName": "Maquinaria profesional",
                "publicPriceUsd": 120.0 * CLP_RATE,
                "originalPriceUsd": 120.0 * CLP_RATE,
                "discountPercent": 0.0,
                "b2bPriceUsd": 100.0 * CLP_RATE,
                "exchangeRateUsdClp": 1.0,
                "stock": 8,
                "reserved": 0,
                "status": "active",
                "imageUrl": "https://cdn.example.com/productos/oculto.jpg",
                "imageUrls": ["https://cdn.example.com/productos/oculto.jpg"],
                "pdfUrls": [],
                "variants": [],
                "specifications": {},
                "requiresQuote": False,
                "requiresTechnicalValidation": False,
                "visibleInApp": False,
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "prod-ajeno-flow",
                "companyId": other_company_id,
                "sku": "OTRA-FLOW-001",
                "title": "Producto de otra empresa",
                "description": "No debe aparecer en catalogo FVENTAS.",
                "productType": "machine",
                "categoryId": "cat-ajena-flow",
                "categoryName": "Categoria ajena",
                "publicPriceUsd": 999.0 * CLP_RATE,
                "originalPriceUsd": 999.0 * CLP_RATE,
                "discountPercent": 0.0,
                "b2bPriceUsd": 900.0 * CLP_RATE,
                "exchangeRateUsdClp": 1.0,
                "stock": 99,
                "reserved": 0,
                "status": "active",
                "imageUrl": "https://cdn.example.com/otra/producto.jpg",
                "imageUrls": ["https://cdn.example.com/otra/producto.jpg"],
                "pdfUrls": [],
                "variants": [],
                "specifications": {},
                "requiresQuote": False,
                "requiresTechnicalValidation": False,
                "visibleInApp": True,
                "rotationLast30Days": 0,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "announcements": [
            {
                "id": "ann-flow-home",
                "companyId": company_id,
                "title": "Promocion FVENTAS Flow",
                "body": "Banner cargado desde admin para carrusel.",
                "placement": "home",
                "priority": 90,
                "ctaLabel": "Ver catalogo",
                "ctaUrl": "FVENTAS://catalog",
                "imageUrl": "https://cdn.example.com/banners/FVENTAS-flow.jpg",
                "startsAt": now,
                "endsAt": "",
                "status": "active",
                "updatedAt": now,
            },
            {
                "id": "ann-ajeno-home",
                "companyId": other_company_id,
                "title": "Banner ajeno",
                "body": "No debe aparecer en la app de FVENTAS.",
                "placement": "home",
                "priority": 100,
                "ctaLabel": "Ver",
                "ctaUrl": "FVENTAS://catalog",
                "imageUrl": "https://cdn.example.com/otra/banner.jpg",
                "startsAt": now,
                "endsAt": "",
                "status": "active",
                "updatedAt": now,
            }
        ],
        "orders": [
            {
                "id": "order-ajeno-flow",
                "orderId": "ORD-AJENO-FLOW",
                "companyId": other_company_id,
                "customerId": "client-ajeno-flow",
                "customerName": "Cliente Competidor Flow",
                "sellerId": "seller-ajeno-flow",
                "sellerName": "Vendedor Ajeno",
                "saleType": "credit_line",
                "salesChannel": "seller_mobile",
                "status": "delivered",
                "collectionStatus": "partial_paid",
                "dispatchStatus": "delivered",
                "paymentStatus": "partial",
                "commissionStatus": "commission_pending",
                "commissionUsd": 45.0 * CLP_RATE,
                "totalUsd": 900.0 * CLP_RATE,
                "paidUsd": 100.0 * CLP_RATE,
                "balanceUsd": 800.0 * CLP_RATE,
                "items": [
                    {
                        "productId": "prod-ajeno-flow",
                        "sku": "OTRA-FLOW-001",
                        "title": "Producto de otra empresa",
                        "quantity": 1,
                        "unitPriceUsd": 900.0 * CLP_RATE,
                        "lineTotalUsd": 900.0 * CLP_RATE,
                    }
                ],
                "createdAt": now,
                "updatedAt": now,
                "dueDate": "2099-12-31",
            }
        ],
        "admin_users": [
            {
                "id": SUPER_ADMIN_ID,
                "companyId": company_id,
                "name": "Super Admin Flow",
                "email": "super.flow@FVENTAS.test",
                "passwordHash": generate_password_hash("Super2026"),
                "role": "super_admin",
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": MANAGER_ID,
                "companyId": company_id,
                "name": "Gerente Flow",
                "email": "gerente.flow@FVENTAS.test",
                "passwordHash": generate_password_hash("Gerente2026"),
                "role": "commercial_manager",
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "admin-seller-flow",
                "companyId": company_id,
                "name": "Vendedor Flow",
                "email": SELLER_EMAIL,
                "passwordHash": generate_password_hash(SELLER_PASSWORD),
                "role": "sales",
                "status": "active",
                "sellerCode": "CL-FLOW",
                "sellerZone": "Centro",
                "commissionRatePercent": 5.0,
                "salesGoalUsd": 1000.0 * CLP_RATE,
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "seller-ajeno-flow",
                "companyId": other_company_id,
                "name": "Vendedor Ajeno",
                "email": "vendedor.ajeno@FVENTAS.test",
                "passwordHash": generate_password_hash("Ajeno2026"),
                "role": "sales",
                "status": "active",
                "sellerCode": "CL-AJENO",
                "sellerZone": "Otra zona",
                "commissionRatePercent": 5.0,
                "salesGoalUsd": 1000.0 * CLP_RATE,
                "createdAt": now,
                "updatedAt": now,
            },
        ],
        "clients": [
            {
                "id": "client-ajeno-flow",
                "companyId": other_company_id,
                "businessName": "Cliente Competidor Flow",
                "legalName": "Cliente Competidor Flow SpA",
                "email": "cliente.ajeno@FVENTAS.test",
                "phone": "+56 9 3000 0000",
                "taxId": "76.000.000-0",
                "assignedSellerId": "seller-ajeno-flow",
                "assignedSellerName": "Vendedor Ajeno",
                "status": "active",
                "creditEnabled": True,
                "creditLimitUsd": 1500.0 * CLP_RATE,
                "creditUsedUsd": 800.0 * CLP_RATE,
                "creditRequestStatus": "approved",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "credit_movements": [
            {
                "id": "payment-ajeno-flow",
                "companyId": other_company_id,
                "movementType": "payment",
                "clientId": "client-ajeno-flow",
                "orderId": "ORD-AJENO-FLOW",
                "amountUsd": 100.0 * CLP_RATE,
                "amountClp": 100.0 * CLP_RATE,
                "method": "transfer",
                "reference": "PAGO-AJENO",
                "createdBy": "Vendedor Ajeno",
                "createdAt": now,
            }
        ],
        "notifications": [],
        "service_technicians": [
            {
                "id": "svc-flow-Santiago",
                "companyId": company_id,
                "name": "Servicio FVENTAS Santiago Flow",
                "companyName": "Servicio FVENTAS Santiago",
                "contactName": "Tecnico principal",
                "phone": "+56 9 1000 0000",
                "whatsapp": "+56 9 1000 0000",
                "email": "servicio.flow@FVENTAS.test",
                "state": "Metropolitana",
                "city": "Santiago",
                "address": "Zona industrial",
                "specialties": ["Motosierras"],
                "coverage": "Centro occidente",
                "status": "active",
                "visibleInApp": True,
                "notes": "",
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "svc-ajeno-flow",
                "companyId": other_company_id,
                "name": "Servicio ajeno",
                "companyName": "Servicio ajeno",
                "contactName": "Tecnico ajeno",
                "phone": "+56 9 2000 0000",
                "whatsapp": "+56 9 2000 0000",
                "email": "servicio.ajeno@FVENTAS.test",
                "state": "Metropolitana",
                "city": "Santiago",
                "address": "Otra zona",
                "specialties": ["No visible"],
                "coverage": "Otra cartera",
                "status": "active",
                "visibleInApp": True,
                "notes": "",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "audit_events": [
            {
                "id": "audit-ajeno-flow",
                "companyId": other_company_id,
                "actorId": "seller-ajeno-flow",
                "actorName": "Vendedor Ajeno",
                "actorRole": "sales",
                "action": "update",
                "entityType": "order",
                "entityId": "ORD-AJENO-FLOW",
                "detail": "Evento ajeno no visible para FVENTAS.",
                "createdAt": now,
                "criticality": "medium",
                "metadata": {},
            }
        ],
        "media_assets": [],
        "stock_movements": [],
    }


def assert_status(response, expected: int, label: str) -> dict:
    if response.status_code != expected:
        raise AssertionError(f"{label}: HTTP {response.status_code} {response.get_data(as_text=True)}")
    if response.is_json:
        return response.get_json() or {}
    return {}


def mobile_token_payload(token: str) -> dict:
    payload = FVENTAS_app.mobile_token_serializer().loads(token)
    assert isinstance(payload, dict), "token movil debe decodificar como payload JSON"
    return payload


def assert_html_status(response, expected: int, label: str) -> str:
    if response.status_code != expected:
        raise AssertionError(f"{label}: HTTP {response.status_code} {response.get_data(as_text=True)}")
    return response.get_data(as_text=True)


def assert_mobile_catalog_is_tenant_scoped(payloads: dict[str, dict], label: str) -> None:
    products = payloads.get("products", {}).get("items", [])
    categories = payloads.get("categories", {}).get("items", [])
    announcements = payloads.get("announcements", {}).get("items", [])
    locations = payloads.get("locations", {}).get("items", [])
    home = payloads.get("home", {}).get("home", {})

    assert all(item.get("sku") != "OTRA-FLOW-001" for item in products), label
    motosierra = next((item for item in products if item.get("sku") == "FVT-FLOW-45CC"), None)
    assert motosierra, f"{label}: producto FVENTAS no visible"
    assert "Validar serie antes de despacho" in motosierra.get("compatibilityNotes", []), (
        f"{label}: notas de compatibilidad admin no llegaron a app"
    )
    assert all(item.get("id") != "cat-ajena-flow" for item in categories), label
    assert all(item.get("id") != "ann-ajeno-home" for item in announcements), label
    assert all(item.get("id") != "svc-ajeno-flow" for item in locations), label
    assert all(item.get("sku") != "OTRA-FLOW-001" for item in home.get("recentProducts", [])), label
    assert all(item.get("id") != "cat-ajena-flow" for item in home.get("categories", [])), label
    assert all(item.get("id") != "ann-ajeno-home" for item in home.get("banners", [])), label


def assert_web_admin_is_tenant_scoped(client) -> None:
    forbidden = [
        "Producto de otra empresa",
        "Categoria ajena",
        "Banner ajeno",
        "Servicio ajeno",
        "Cliente Competidor Flow",
        "Vendedor Ajeno",
        "ORD-AJENO-FLOW",
        "PAGO-AJENO",
        "Evento ajeno",
    ]
    pages = [
        ("/dashboard", "dashboard tenant scope"),
        ("/clients", "clientes tenant scope"),
        ("/credit", "credito tenant scope"),
        ("/products", "productos tenant scope"),
        ("/stock", "stock tenant scope"),
        ("/service-technicians", "servicios tenant scope"),
        ("/announcements", "anuncios tenant scope"),
        ("/business-rules", "reglas tenant scope"),
        ("/audit", "auditoria tenant scope"),
        ("/search?q=OTRA-FLOW-001", "busqueda tenant scope"),
        ("/commissions", "comisiones tenant scope"),
    ]
    for path, label in pages:
        html = assert_html_status(client.get(path), 200, label)
        leaked = [value for value in forbidden if value in html]
        if leaked:
            raise AssertionError(f"{label}: datos ajenos visibles en {path}: {', '.join(leaked)}")

    for path in ["/crm", "/quotes", "/collections", "/dispatch", "/reports", "/maintenance", "/permissions"]:
        assert_html_status(client.get(path), 403, f"modulo archivado bloqueado {path}")


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

    FVENTAS_app.load_store = load_store_override
    FVENTAS_app.save_store = save_store_override
    FVENTAS_app.app.config["REQUIRE_MOBILE_TOKEN"] = True
    FVENTAS_app.app.config["REJECT_LEGACY_MOBILE_TOKENS"] = True
    FVENTAS_app.app.config["TESTING"] = True

    client = FVENTAS_app.app.test_client()

    with client.session_transaction() as session:
        session["admin_authenticated"] = True
        session["admin_user_id"] = SUPER_ADMIN_ID
        session["admin_name"] = "Super Admin Flow"
        session["admin_role"] = "super_admin"
        session["company_id"] = COMPANY_ID
        session["_csrf_token"] = "csrf-flow"

    assert_status(
        client.post(
            "/products/import",
            data={
                "_csrf_token": "csrf-flow",
                "importFile": (
                    io.BytesIO(
                        b"sku,nombre,categoria,precio_publico,precio_b2b,stock,imagenes,notas_compatibilidad\n"
                        b"FVT-FLOW-45CC,Motosierra FVENTAS 45cc Flow,Maquinaria profesional,175750,153900,12,https://cdn.example.com/productos/motosierra.jpg|https://cdn.example.com/productos/motosierra-lateral.jpg,Compatible con FVT-REP-CAD18|Validar serie antes de despacho\n"
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
    assert "Validar serie antes de despacho" in imported_product.get("compatibilityNotes", [])
    assert_web_admin_is_tenant_scoped(client)
    api_meta = assert_status(client.get("/api/v1/mobile/meta"), 200, "api v1 meta")
    assert api_meta["meta"]["apiVersion"] == "v1"
    assert "counts" not in api_meta, "meta publica no debe exponer conteos de empresa"

    seller_login = assert_status(
        client.post(
            "/api/mobile/auth/login",
            json={"email": SELLER_EMAIL, "password": SELLER_PASSWORD},
        ),
        200,
        "login vendedor",
    )
    seller_token = seller_login["accessToken"]
    seller_token_payload = mobile_token_payload(seller_token)
    assert seller_token_payload["companyId"] == COMPANY_ID
    assert seller_login["customer"]["accountRole"] == "sales"
    seller_meta = assert_status(
        client.get(
            "/api/v1/mobile/meta",
            headers={"Authorization": f"Bearer {seller_token}"},
        ),
        200,
        "meta vendedor tenant v1",
    )
    assert seller_meta["market"]["localCurrency"] == "CLP"
    assert seller_meta["counts"]["products"] == 1
    assert seller_meta["counts"]["categories"] == 1
    assert seller_meta["purchaseConditions"]["paymentTermsLabel"] == "Contado / 15, 30 dias"
    assert seller_meta["purchaseConditions"]["scopeLabel"] == "Solo datos de tu empresa"
    assert "quotes" not in seller_meta["capabilities"]["seller"], "cotizaciones moviles archivadas no deben publicitarse"
    assert "activities" not in seller_meta["capabilities"]["seller"], "CRM movil archivado no debe publicitarse"
    assert seller_login["customer"]["purchaseConditions"]["note"].startswith("Pedidos sujetos")
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
    seller_tenant_payloads = {
        "home": assert_status(
            client.get(
                "/api/v1/mobile/home",
                headers={"Authorization": f"Bearer {seller_token}"},
            ),
            200,
            "home vendedor tenant v1",
        ),
        "products": assert_status(
            client.get(
                "/api/v1/mobile/products?limit=20",
                headers={"Authorization": f"Bearer {seller_token}"},
            ),
            200,
            "productos vendedor tenant v1",
        ),
        "categories": assert_status(
            client.get(
                "/api/v1/mobile/categories?limit=20",
                headers={"Authorization": f"Bearer {seller_token}"},
            ),
            200,
            "categorias vendedor tenant v1",
        ),
        "announcements": assert_status(
            client.get(
                "/api/v1/mobile/announcements?placement=home&limit=20",
                headers={"Authorization": f"Bearer {seller_token}"},
            ),
            200,
            "banners vendedor tenant v1",
        ),
        "locations": assert_status(
            client.get(
                "/api/v1/mobile/locations?limit=20",
                headers={"Authorization": f"Bearer {seller_token}"},
            ),
            200,
            "puntos vendedor tenant v1",
        ),
    }
    assert_mobile_catalog_is_tenant_scoped(
        seller_tenant_payloads,
        "catalogo vendedor no debe mezclar empresas",
    )

    super_mobile_login = assert_status(
        client.post(
            "/api/v1/mobile/auth/login",
            json={"email": "super.flow@FVENTAS.test", "password": "Super2026"},
        ),
        200,
        "login super admin movil",
    )
    super_token = super_mobile_login["accessToken"]
    assert super_mobile_login["customer"]["accountRole"] == "super_admin"
    assert super_mobile_login["customer"]["assignedSeller"]["id"] == SUPER_ADMIN_ID

    invalid_client = assert_status(
        client.post(
            "/api/mobile/seller/clients",
            headers={
                "Authorization": f"Bearer {seller_token}",
                "Idempotency-Key": "invalid-rut-flow",
            },
            json={
                "businessName": "Cliente Rif Incompleto Flow",
                "taxId": "76.000.000-1",
                "contactName": "Comprador Rut",
                "phone": "+56 9 1111 1112",
                "email": "cliente.rut.incompleto@FVENTAS.test",
                "address": "Av. Validacion",
                "state": "Metropolitana",
                "city": "Santiago",
                "deliveryZone": "Centro",
                "creditRequestedUsd": 0,
                "allowedPaymentTermsDays": [0],
                "defaultSaleType": "cash",
                "password": CLIENT_PASSWORD,
            },
        ),
        400,
        "rechazar cliente movil con RUT incompleto",
    )
    assert "taxId" in invalid_client.get("errors", {})

    weak_password_client = assert_status(
        client.post(
            "/api/mobile/seller/clients",
            headers={
                "Authorization": f"Bearer {seller_token}",
                "Idempotency-Key": "weak-password-client",
            },
            json={
                "businessName": "Cliente Password Debil",
                "taxId": "78.000.000-7",
                "contactName": "Comprador Password",
                "phone": "+56 9 1111 1113",
                "email": "cliente.password.debil@FVENTAS.test",
                "address": "Av. Seguridad",
                "state": "Metropolitana",
                "city": "Santiago",
                "deliveryZone": "Centro",
                "creditRequestedUsd": 0,
                "allowedPaymentTermsDays": [0],
                "defaultSaleType": "cash",
                "password": "123",
            },
        ),
        400,
        "rechazar cliente movil con password debil",
    )
    assert "password" in weak_password_client.get("errors", {})

    generated_password_client = assert_status(
        client.post(
            "/api/mobile/seller/clients",
            headers={
                "Authorization": f"Bearer {seller_token}",
                "Idempotency-Key": "generated-password-client",
            },
            json={
                "businessName": "Cliente Password Generada",
                "taxId": "78.001.111-4",
                "contactName": "Comprador Generada",
                "phone": "+56 9 1111 1114",
                "email": "cliente.password.generada@FVENTAS.test",
                "address": "Av. Seguridad",
                "state": "Metropolitana",
                "city": "Santiago",
                "deliveryZone": "Centro",
                "creditRequestedUsd": 0,
                "allowedPaymentTermsDays": [0],
                "defaultSaleType": "cash",
            },
        ),
        201,
        "crear cliente vendedor con password generada",
    )
    generated_password = generated_password_client["client"]["temporaryPassword"]
    assert not FVENTAS_app.password_errors(generated_password)
    stored_generated_client = next(
        item for item in state["clients"] if item["id"] == generated_password_client["client"]["id"]
    )
    assert stored_generated_client["mustChangePassword"] is True

    sanitized_commercial_client = assert_status(
        client.post(
            "/api/mobile/seller/clients",
            headers={
                "Authorization": f"Bearer {seller_token}",
                "Idempotency-Key": "sanitized-commercial-fields",
            },
            json={
                "businessName": "Cliente Campos Comerciales",
                "taxId": "78.002.222-1",
                "contactName": "Comprador Campos",
                "phone": "+56 9 1111 1115",
                "email": "cliente.campos.comerciales@FVENTAS.test",
                "address": "Av. Seguridad",
                "state": "Metropolitana",
                "city": "Santiago",
                "deliveryZone": "Centro",
                "creditRequestedUsd": 0,
                "allowedPaymentTermsDays": [0],
                "clientCategory": "vip-inventado",
                "priceList": "lista-secreta",
                "defaultSaleType": "credito-ilimitado",
            },
        ),
        201,
        "sanitizar campos comerciales enviados por vendedor movil",
    )
    stored_sanitized_client = next(
        item for item in state["clients"] if item["id"] == sanitized_commercial_client["client"]["id"]
    )
    assert stored_sanitized_client["clientCategory"] == "standard"
    assert stored_sanitized_client["priceList"] == "b2b"
    assert stored_sanitized_client["defaultSaleType"] == "cash"

    new_client = assert_status(
        client.post(
            "/api/mobile/seller/clients",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={
                "businessName": "Cliente Flow Santiago",
                "taxId": "76.000.000-0",
                "contactName": "Comprador Flow",
                "phone": "+56 9 1111 1111",
                "email": "cliente.flow@FVENTAS.test",
                "address": "Av. Industrial",
                "state": "Metropolitana",
                "city": "Santiago",
                "deliveryZone": "Centro",
                "creditRequestedUsd": 500,
                "authorizedDiscountPercent": 5,
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
    assert new_client["client"]["authorizedDiscountPercent"] == 0
    assert new_client["client"]["discountRequestedPercent"] == 5
    assert new_client["client"]["discountRequestStatus"] == "pending"
    stored_new_client = next(item for item in state["clients"] if item["id"] == client_id)
    assert "descuento comercial 5%" in stored_new_client.get("notes", "")
    assert stored_new_client["defaultSaleType"] == "cash"
    assert stored_new_client["allowedPaymentTermsDays"] == [0]
    assert "condiciones de compra" in stored_new_client.get("notes", "")
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
    seller_notifications = assert_status(
        client.get(
            "/api/v1/mobile/notifications",
            headers={"Authorization": f"Bearer {seller_token}"},
        ),
        200,
        "notificaciones vendedor v1",
    )
    assert any(item["type"] == "client_assigned" for item in seller_notifications["items"])
    assert any(item["type"] == "client_created_by_seller" for item in state["notifications"])
    assert any(item["type"] == "credit_requested" for item in state["notifications"])

    super_client = assert_status(
        client.post(
            "/api/v1/mobile/seller/clients",
            headers={"Authorization": f"Bearer {super_token}"},
            json={
                "businessName": "Cliente Super Admin Flow",
                "taxId": "77.777.777-7",
                "contactName": "Comprador Super",
                "phone": "+56 9 2222 2222",
                "email": "cliente.super.flow@FVENTAS.test",
                "address": "Av. Gerencia",
                "state": "Metropolitana",
                "city": "Santiago",
                "deliveryZone": "Centro",
                "allowedPaymentTermsDays": [0],
                "defaultSaleType": "cash",
                "password": CLIENT_PASSWORD,
            },
        ),
        201,
        "crear cliente super admin movil",
    )
    super_client_id = super_client["client"]["id"]
    assert super_client["client"]["assignedSeller"]["id"] == SUPER_ADMIN_ID

    super_order = assert_status(
        client.post(
            "/api/v1/mobile/seller/orders",
            headers={"Authorization": f"Bearer {super_token}"},
            json={
                "customerId": super_client_id,
                "saleType": "cash",
                "paymentTermDays": 0,
                "items": [
                    {
                        "productId": "prod-flow-motosierra",
                        "quantity": 1,
                    }
                ],
                "preview": {"totalUsd": 162 * CLP_RATE, "subtotalUsd": 162 * CLP_RATE},
            },
        ),
        201,
        "crear pedido super admin movil",
    )
    assert super_order["order"]["sellerId"] == SUPER_ADMIN_ID

    state["clients"].append(
        {
            "id": "client-unassigned-super-flow",
            "companyId": COMPANY_ID,
            "legalName": "Cliente Sin Vendedor Flow",
            "commercialName": "Cliente Sin Vendedor Flow",
            "businessName": "Cliente Sin Vendedor Flow",
            "email": "sin.vendedor.flow@FVENTAS.test",
            "clientType": "b2b",
            "clientCategory": "standard",
            "priceList": "b2b",
            "status": "active",
            "address": "Av. Libre",
            "country": "CL",
            "state": "Metropolitana",
            "city": "Santiago",
            "assignedSellerId": "",
            "assignedSellerName": "",
            "defaultSaleType": "cash",
            "allowedPaymentTermsDays": [0],
            "creditEnabled": False,
            "creditLimitUsd": 0,
            "creditUsedUsd": 0,
            "paymentTermsDays": 0,
            "mustChangePassword": False,
            "createdAt": utc_now(),
            "updatedAt": utc_now(),
        }
    )
    super_unassigned_order = assert_status(
        client.post(
            "/api/v1/mobile/seller/orders",
            headers={"Authorization": f"Bearer {super_token}"},
            json={
                "customerId": "client-unassigned-super-flow",
                "saleType": "cash",
                "paymentTermDays": 0,
                "items": [
                    {
                        "productId": "prod-flow-motosierra",
                        "quantity": 1,
                    }
                ],
                "preview": {"totalUsd": 162 * CLP_RATE, "subtotalUsd": 162 * CLP_RATE},
            },
        ),
        201,
        "crear pedido super admin para cliente sin vendedor",
    )
    assert super_unassigned_order["order"]["sellerId"] == SUPER_ADMIN_ID

    assert_status(
        client.post(
            "/api/v1/mobile/seller/orders",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={
                "customerId": client_id,
                "saleType": "cash",
                "paymentTermDays": 0,
                "items": [
                    {
                        "productId": "prod-flow-oculto",
                        "sku": "FVT-FLOW-HIDDEN",
                        "quantity": 1,
                    }
                ],
                "preview": {"totalUsd": 100 * CLP_RATE, "subtotalUsd": 100 * CLP_RATE},
            },
        ),
        400,
        "pedido vendedor con producto oculto bloqueado",
    )
    seller_quotes_archived = assert_status(
        client.get(
            "/api/v1/mobile/seller/quotes",
            headers={"Authorization": f"Bearer {seller_token}"},
        ),
        410,
        "cotizaciones vendedor v1 archivadas",
    )
    assert seller_quotes_archived["code"] == "mobile_feature_archived"
    assert seller_quotes_archived["feature"] == "seller_quotes"
    seller_quotes_create_archived = assert_status(
        client.post(
            "/api/v1/mobile/seller/quotes",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={"customerId": client_id, "items": [{"productId": "prod-flow-motosierra", "quantity": 1}]},
        ),
        410,
        "crear cotizacion vendedor v1 archivado",
    )
    assert seller_quotes_create_archived["code"] == "mobile_feature_archived"
    seller_quotes_legacy_archived = assert_status(
        client.get(
            "/api/mobile/seller/quotes?limit=1&status=draft",
            headers={"Authorization": f"Bearer {seller_token}"},
        ),
        410,
        "cotizaciones vendedor legacy archivadas",
    )
    assert seller_quotes_legacy_archived["feature"] == "seller_quotes"
    seller_clients_all = assert_status(
        client.get(
            "/api/mobile/seller/clients?limit=50",
            headers={"Authorization": f"Bearer {seller_token}"},
        ),
        200,
        "clientes vendedor sin fuga tenant",
    )
    assert all(item["id"] != "client-ajeno-flow" for item in seller_clients_all["items"])
    mobile_activity_archived = assert_status(
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
        410,
        "crear actividad CRM vendedor archivada",
    )
    assert mobile_activity_archived["code"] == "mobile_feature_archived"
    assert mobile_activity_archived["feature"] == "seller_activities"
    seller_activities_archived = assert_status(
        client.get(
            "/api/v1/mobile/seller/activities",
            headers={"Authorization": f"Bearer {seller_token}"},
        ),
        410,
        "listar actividades CRM vendedor archivadas",
    )
    assert seller_activities_archived["feature"] == "seller_activities"
    seller_activities_legacy_archived = assert_status(
        client.get(
            "/api/mobile/seller/activities?limit=1&q=Flow",
            headers={"Authorization": f"Bearer {seller_token}"},
        ),
        410,
        "actividades CRM vendedor legacy archivadas",
    )
    assert seller_activities_legacy_archived["code"] == "mobile_feature_archived"
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
                "creditLimitUsd": str(500 * CLP_RATE),
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
            json={"email": "cliente.flow@FVENTAS.test", "password": CLIENT_PASSWORD},
        ),
        200,
        "login cliente B2B temporal",
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
        "cambio clave cliente B2B",
    )

    customer_login = assert_status(
        client.post(
            "/api/mobile/auth/login",
            json={"email": "cliente.flow@FVENTAS.test", "password": CLIENT_NEW_PASSWORD},
        ),
        200,
        "login cliente B2B final",
    )
    customer_token = customer_login["accessToken"]
    customer_token_payload = mobile_token_payload(customer_token)
    assert customer_token_payload["companyId"] == COMPANY_ID
    customer_profile_v1 = assert_status(
        client.get(
            "/api/v1/mobile/profile",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "perfil cliente B2B v1",
    )
    assert customer_profile_v1["profile"]["accountRole"] == "client"
    assert customer_profile_v1["profile"]["purchaseConditions"]["paymentTermsLabel"] == "Contado / 30 dias"
    customer_notifications_credit = assert_status(
        client.get(
            "/api/v1/mobile/notifications",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "notificaciones cliente B2B credito v1",
    )
    assert any(item["type"] == "credit_approved" for item in customer_notifications_credit["items"])
    customer_home_v1 = assert_status(
        client.get(
            "/api/v1/mobile/home",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "home cliente B2B v1",
    )
    assert customer_home_v1["home"]["banners"]
    customer_tenant_payloads = {
        "home": customer_home_v1,
        "products": assert_status(
            client.get(
                "/api/v1/mobile/products?limit=20",
                headers={"Authorization": f"Bearer {customer_token}"},
            ),
            200,
            "productos cliente tenant v1",
        ),
        "categories": assert_status(
            client.get(
                "/api/v1/mobile/categories?limit=20",
                headers={"Authorization": f"Bearer {customer_token}"},
            ),
            200,
            "categorias cliente tenant v1",
        ),
        "announcements": assert_status(
            client.get(
                "/api/v1/mobile/announcements?placement=home&limit=20",
                headers={"Authorization": f"Bearer {customer_token}"},
            ),
            200,
            "banners cliente tenant v1",
        ),
        "locations": assert_status(
            client.get(
                "/api/v1/mobile/locations?limit=20",
                headers={"Authorization": f"Bearer {customer_token}"},
            ),
            200,
            "puntos cliente tenant v1",
        ),
    }
    assert_mobile_catalog_is_tenant_scoped(
        customer_tenant_payloads,
        "catalogo cliente no debe mezclar empresas",
    )
    product_detail_v1 = assert_status(
        client.get(
            "/api/v1/mobile/products/prod-flow-motosierra",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "detalle producto v1",
    )
    assert product_detail_v1["product"]["sku"] == "FVT-FLOW-45CC"
    assert_status(
        client.get(
            "/api/v1/mobile/products/prod-ajeno-flow",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        404,
        "detalle producto ajeno bloqueado",
    )
    products_paged_v1 = assert_status(
        client.get(
            "/api/v1/mobile/products?limit=1&q=FVT-FLOW&sort=price_desc",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "catalogo paginado v1",
    )
    assert products_paged_v1["meta"]["pagination"]["limit"] == 1
    assert products_paged_v1["items"][0]["sku"] == "FVT-FLOW-45CC"
    cart_v1 = assert_status(
        client.get(
            "/api/v1/mobile/cart",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "carrito v1",
    )
    assert cart_v1["mode"] == "local_persistent"
    assert_status(
        client.post(
            "/api/mobile/orders",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={
                "saleType": "cash",
                "paymentTermDays": 0,
                "items": [
                    {
                        "productId": "prod-ajeno-flow",
                        "sku": "OTRA-FLOW-001",
                        "quantity": 1,
                    }
                ],
                "preview": {"exchangeRateUsdVes": 1.0},
            },
        ),
        400,
        "orden con producto ajeno bloqueada",
    )
    assert_status(
        client.post(
            "/api/mobile/orders",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={
                "saleType": "cash",
                "paymentTermDays": 0,
                "items": [
                    {
                        "productId": "prod-flow-oculto",
                        "sku": "FVT-FLOW-HIDDEN",
                        "quantity": 1,
                    }
                ],
                "preview": {"totalUsd": 100 * CLP_RATE, "subtotalUsd": 100 * CLP_RATE},
            },
        ),
        400,
        "orden cliente con producto oculto bloqueada",
    )

    mismatched_customer_token = FVENTAS_app.mobile_token_serializer().dumps(
        {
            **customer_token_payload,
            "companyId": OTHER_COMPANY_ID,
        }
    )
    assert_status(
        client.get(
            "/api/v1/mobile/profile",
            headers={"Authorization": f"Bearer {mismatched_customer_token}"},
        ),
        401,
        "token cliente con empresa ajena bloqueado",
    )

    mismatched_seller_token = FVENTAS_app.mobile_token_serializer().dumps(
        {
            **seller_token_payload,
            "companyId": OTHER_COMPANY_ID,
        }
    )
    assert_status(
        client.get(
            "/api/v1/mobile/seller/summary",
            headers={"Authorization": f"Bearer {mismatched_seller_token}"},
        ),
        401,
        "token vendedor con empresa ajena bloqueado",
    )
    other_seller_login = assert_status(
        client.post(
            "/api/v1/mobile/auth/login",
            json={"email": "vendedor.ajeno@FVENTAS.test", "password": "Ajeno2026"},
        ),
        200,
        "login vendedor empresa secundaria",
    )
    other_seller_payload = mobile_token_payload(other_seller_login["accessToken"])
    assert other_seller_payload["companyId"] == OTHER_COMPANY_ID
    other_seller_summary = assert_status(
        client.get(
            "/api/v1/mobile/seller/summary",
            headers={"Authorization": f"Bearer {other_seller_login['accessToken']}"},
        ),
        200,
        "resumen vendedor empresa secundaria",
    )["summary"]
    assert other_seller_summary["clientsCount"] == 1
    assert other_seller_summary["activeClientsCount"] == 1
    assert other_seller_summary["ordersCount"] == 1
    assert other_seller_summary["salesMonthUsd"] == 900.0 * CLP_RATE
    assert other_seller_summary["goalProgressPercent"] == 90.0

    forged_quote = {
        "id": "quote-cross-company-flow",
        "companyId": COMPANY_ID,
        "quoteNumber": "COT-CROSS-COMPANY-FLOW",
        "clientId": "client-ajeno-flow",
        "client": {"id": "client-ajeno-flow", "name": "Cliente Competidor Flow"},
        "sellerId": "admin-seller-flow",
        "sellerName": "Vendedor Flow",
        "items": [
            {
                "productId": "prod-ajeno-flow",
                "sku": "OTRA-FLOW-001",
                "title": "Producto de otra empresa",
                "quantity": 1,
                "unitPriceUsd": 900.0,
                "lineTotalUsd": 900.0,
            }
        ],
        "grossUsd": 900.0,
        "totalUsd": 900.0,
        "saleType": "credit_line",
        "paymentTermDays": 30,
        "status": "accepted",
        "createdAt": utc_now(),
        "updatedAt": utc_now(),
    }
    state.setdefault("quotes", []).append(forged_quote)
    order_count_before = len(state.get("orders", []))
    quote_convert_response = client.post(
        "/quotes/quote-cross-company-flow/convert",
        data={"_csrf_token": "csrf-flow"},
        follow_redirects=False,
    )
    if quote_convert_response.status_code not in {400, 403}:
        raise AssertionError(
            "cotizacion con cliente de otra empresa no convierte en orden: "
            f"esperado 400/403, llego {quote_convert_response.status_code}"
        )
    assert len(state.get("orders", [])) == order_count_before
    assert not forged_quote.get("convertedOrderId")

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
                        "sku": "FVT-FLOW-45CC",
                        "quantity": 2,
                        "unitPriceUsd": 1,
                    }
                ],
                "preview": {
                    "totalUsd": 1,
                    "subtotalUsd": 1,
                    "exchangeRateUsdVes": 1.0,
                },
            },
        ),
        201,
        "orden cliente B2B",
    )

    created_order = next(item for item in state["orders"] if item["orderId"] == order["orderId"])
    assert order["sellerId"] == "admin-seller-flow"
    assert created_order["salesChannel"] == "mobile"
    assert created_order["saleType"] == "credit_line"
    assert created_order["totalUsd"] == 324 * CLP_RATE
    assert created_order["creditBeforeUsd"] == 500 * CLP_RATE
    assert created_order["creditAfterUsd"] == 176 * CLP_RATE
    assert created_order["commissionUsd"] == 16.2 * CLP_RATE
    assert created_order["inventoryStatus"] == "reserved"
    customer_notifications_order = assert_status(
        client.get(
            "/api/v1/mobile/notifications",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "notificaciones cliente B2B orden v1",
    )
    assert any(item["type"] == "order_received" for item in customer_notifications_order["items"])
    orders_v1 = assert_status(
        client.get(
            "/api/v1/mobile/orders",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "ordenes cliente B2B v1",
    )
    assert orders_v1["items"]
    assert all(item["id"] != "order-ajeno-flow" for item in orders_v1["items"])
    orders_filtered_v1 = assert_status(
        client.get(
            "/api/v1/mobile/orders?limit=1&saleType=credit_line&sort=balance_desc",
            headers={"Authorization": f"Bearer {customer_token}"},
        ),
        200,
        "ordenes cliente B2B filtradas v1",
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
                        "sku": "FVT-FLOW-45CC",
                        "quantity": 1,
                    }
                ],
                "preview": {
                    "exchangeRateUsdVes": 1.0,
                },
            },
        ),
        201,
        "orden cliente B2B contado",
    )
    cash_order = next(item for item in state["orders"] if item["orderId"] == cash_order_response["orderId"])
    assert cash_order_response["saleType"] == "cash"
    assert cash_order["saleType"] == "cash"
    assert cash_order["status"] == "payment_under_review"
    assert cash_order["creditStatus"] == "without_credit"
    assert cash_order["paymentTermDays"] == 0
    assert cash_order["balanceUsd"] == 162 * CLP_RATE

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
                "exchangeRateUsdVes": "1.0",
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
                "paymentTermDays": 30,
                "items": [
                    {
                        "productId": "prod-flow-motosierra",
                        "sku": "FVT-FLOW-45CC",
                        "quantity": 1,
                    }
                ],
                "preview": {
                    "exchangeRateUsdVes": 1.0,
                },
            },
        ),
        201,
        "orden cliente B2B credito por dias",
    )
    term_order = next(item for item in state["orders"] if item["orderId"] == term_order_response["orderId"])
    assert term_order_response["saleType"] == "term_credit"
    assert term_order["saleType"] == "term_credit"
    assert term_order["paymentTermDays"] == 30
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

    print("FVENTAS Insights smoke comercial")
    print("------------------------")
    print("OK vendedor crea cliente y queda asignado")
    print("OK carga masiva actualiza producto y galeria movil")
    print("OK gerente aprueba credito B2B con auditoria before/after")
    print("OK cliente B2B cambia clave temporal")
    print("OK cliente B2B crea orden con linea de credito")
    print("OK orden registra vendedor, comision, stock reservado y credito restante")
    print("OK cliente B2B crea orden contado y admin ve pago externo por validar")
    print("OK orden contado registra abono efectivo sin consumir linea de credito")
    print("OK cliente B2B crea credito por dias y admin puede validarlo sin linea")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
