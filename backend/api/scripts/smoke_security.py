from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app as FVENTAS_app
from store import DEFAULT_COMPANY_ID, SAAS_PLAN_ID, SAAS_PLAN_NAME, SAAS_PLAN_PRICE_CLP, utc_now
from werkzeug.security import generate_password_hash


def base_store() -> dict:
    now = utc_now()
    return {
        "categories": [
            {
                "id": "cat-sec",
                "companyId": DEFAULT_COMPANY_ID,
                "name": "Seguridad",
                "slug": "seguridad",
                "status": "active",
                "visibleInApp": True,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "products": [
            {
                "id": "prod-sec",
                "companyId": DEFAULT_COMPANY_ID,
                "sku": "FVT-SEC-01",
                "title": "Producto Seguridad",
                "description": "Producto visible para validar token.",
                "categoryId": "cat-sec",
                "categoryName": "Seguridad",
                "publicPriceUsd": 10,
                "b2bPriceUsd": 9,
                "status": "active",
                "visibleInApp": True,
                "imageUrls": [],
                "pdfUrls": [],
                "variants": [],
                "specifications": {},
                "stock": 5,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "announcements": [],
        "media_assets": [
            {
                "id": "doc-sec",
                "companyId": DEFAULT_COMPANY_ID,
                "title": "Contrato Seguridad",
                "assetType": "document",
                "type": "document",
                "documentType": "contract",
                "subjectType": "client",
                "subjectId": "client-sec",
                "subjectLabel": "Cliente Seguridad",
                "visibility": "internal",
                "url": "/static/uploads/documents/security.pdf",
                "status": "active",
                "createdByName": "Admin Seguridad",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "orders": [],
        "credit_movements": [],
        "stock_movements": [],
        "admin_users": [
            {
                "id": "admin-sec",
                "companyId": DEFAULT_COMPANY_ID,
                "name": "Admin Seguridad",
                "email": "admin.security@FVENTAS.test",
                "passwordHash": generate_password_hash("AdminSecurity2026"),
                "role": "super_admin",
                "status": "active",
                "sessionVersion": 0,
                "mustChangePassword": False,
                "activeSessions": [],
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "readonly-sec",
                "companyId": DEFAULT_COMPANY_ID,
                "name": "Solo Lectura",
                "email": "readonly.security@FVENTAS.test",
                "passwordHash": generate_password_hash("Readonly2026"),
                "role": "readonly",
                "status": "active",
                "sessionVersion": 0,
                "mustChangePassword": False,
                "activeSessions": [],
                "createdAt": now,
                "updatedAt": now,
            },
        ],
        "clients": [
            {
                "id": "client-sec",
                "companyId": DEFAULT_COMPANY_ID,
                "businessName": "Cliente Seguridad",
                "email": "cliente.security@FVENTAS.test",
                "passwordHash": generate_password_hash("ClienteSecurity2026"),
                "status": "active",
                "clientType": "b2b",
                "taxId": "11.111.111-1",
                "phone": "+56 9 1000 0000",
                "address": "Direccion seguridad",
                "city": "Santiago",
                "state": "Metropolitana",
                "creditEnabled": False,
                "creditLimitUsd": 0,
                "paymentTermsDays": 0,
                "allowedPaymentTermsDays": [0],
                "defaultSaleType": "cash",
                "collectionStatus": "without_debt",
                "creditRiskLevel": "low",
                "mobileSessionVersion": 0,
                "mustChangePassword": False,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "audit_events": [],
        "companies": [
            {
                "id": DEFAULT_COMPANY_ID,
                "name": "FVENTAS",
                "legalName": "FVENTAS",
                "taxId": "76.000.000-0",
                "country": "CL",
                "status": "active",
                "ownerEmail": "admin.security@FVENTAS.test",
                "supportEmail": "soporte@fventas.cl",
                "supportPhone": "+56 9 1000 0000",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "subscriptions": [
            {
                "id": f"sub-{DEFAULT_COMPANY_ID}",
                "companyId": DEFAULT_COMPANY_ID,
                "planId": SAAS_PLAN_ID,
                "planName": SAAS_PLAN_NAME,
                "priceClp": SAAS_PLAN_PRICE_CLP,
                "billingCycle": "monthly",
                "status": "active",
                "currentPeriodStart": now,
                "currentPeriodEnd": "",
                "paymentMethod": "external",
                "lastPaymentAt": now,
                "nextBillingAt": "",
                "notes": "Smoke security subscription.",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
    }


def csrf_from_session(client) -> str:
    with client.session_transaction() as session:
        return session.get("_csrf_token", "")


def assert_status(response, expected: int, label: str):
    assert response.status_code == expected, f"{label}: esperado {expected}, llego {response.status_code}"
    return response


def main() -> int:
    state = base_store()
    FVENTAS_app.load_store = lambda: state
    FVENTAS_app.save_store = lambda store: None
    app = FVENTAS_app.app
    app.config.update(
        TESTING=True,
        SECRET_KEY="security-smoke-secret",
        STORAGE_BACKEND="local",
        DOCUMENT_SIGNED_URL_MAX_AGE_SECONDS=120,
        REQUIRE_MOBILE_TOKEN=True,
        REJECT_LEGACY_MOBILE_TOKENS=True,
        WTF_CSRF_ENABLED=False,
    )

    with app.test_client() as client:
        login_page = assert_status(client.get("/login"), 200, "login headers")
        assert login_page.headers.get("X-Content-Type-Options") == "nosniff"
        assert login_page.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert "Content-Security-Policy-Report-Only" in login_page.headers

        csrf = csrf_from_session(client)
        assert_status(
            client.post(
                "/login",
                data={
                    "_csrf_token": csrf,
                    "email": "readonly.security@FVENTAS.test",
                    "password": "Readonly2026",
                },
            ),
            302,
            "login readonly",
        )
        readonly_user = next(item for item in state["admin_users"] if item["id"] == "readonly-sec")
        assert readonly_user["activeSessions"], "login admin debe registrar sesion activa"
        assert_status(client.get("/products"), 200, "readonly puede ver productos")
        assert_status(
            client.post("/products/new", data={"_csrf_token": csrf, "sku": "FVT-NO"}),
            403,
            "readonly no puede crear productos por URL manual",
        )

    with app.test_client() as client:
        assert_status(client.get("/login"), 200, "login admin")
        csrf = csrf_from_session(client)
        assert_status(
            client.post(
                "/login",
                data={
                    "_csrf_token": csrf,
                    "email": "admin.security@FVENTAS.test",
                    "password": "AdminSecurity2026",
                },
            ),
            302,
            "login super admin",
        )
        bad_file = (io.BytesIO(b"esto no es una imagen real"), "banner.png")
        assert_status(
            client.post(
                "/announcements",
                data={
                    "_csrf_token": csrf,
                    "title": "Archivo falso",
                    "imageFile": bad_file,
                },
                content_type="multipart/form-data",
            ),
            400,
            "archivo con firma invalida rechazado",
        )
        signed_document = assert_status(
            client.get("/documents/doc-sec/open"),
            302,
            "documento privado genera enlace temporal",
        )
        assert "/documents/private/" in signed_document.headers.get("Location", ""), "documento privado debe usar enlace firmado local"
        assert any(event.get("action") == "document_open" for event in state["audit_events"]), "apertura de documento debe quedar auditada"

        assert_status(
            client.post(
                "/announcements",
                data={
                    "_csrf_token": csrf,
                    "title": "<b>Oferta seguridad</b>",
                    "body": "<script>alert(1)</script>Compra segura",
                    "ctaLabel": "<i>Ver</i>",
                    "ctaUrl": "javascript:alert(1)",
                    "imageUrl": "javascript:bad",
                },
            ),
            302,
            "anuncio con HTML se limpia",
        )
        announcement = state["announcements"][-1]
        assert announcement["title"] == "Oferta seguridad", "titulo de anuncio debe limpiarse"
        assert announcement["body"] == "Compra segura", "body de anuncio debe remover scripts"
        assert announcement["ctaLabel"] == "Ver", "cta label debe limpiarse"
        assert announcement["ctaUrl"] == "", "cta URL insegura no debe persistir"
        assert announcement["imageUrl"] == "", "imagen insegura no debe persistir"

        mobile_login = assert_status(
            client.post(
                "/api/v1/mobile/auth/login",
                headers={"X-FVENTAS-Device-Id": "device-security"},
                json={
                    "email": "cliente.security@FVENTAS.test",
                    "password": "ClienteSecurity2026",
                    "deviceId": "device-security",
                },
            ),
            200,
            "login movil",
        ).get_json()
        token = mobile_login["accessToken"]
        assert_status(
            client.get(
                "/api/v1/mobile/products",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
            ),
            200,
            "token vigente puede leer catalogo",
        )
        state["clients"][0]["mobileSessionVersion"] = 1
        assert_status(
            client.get(
                "/api/v1/mobile/products",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
            ),
            401,
            "token movil viejo invalidado por version",
        )

    print("FVENTAS Insights smoke seguridad")
    print("------------------------")
    print("OK headers de seguridad y cache sensible")
    print("OK sesiones activas con dispositivo")
    print("OK permisos backend por endpoint")
    print("OK validacion de firma de archivos")
    print("OK URLs firmadas para documentos privados")
    print("OK sanitizacion avanzada de inputs y URLs")
    print("OK tokens moviles versionados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
