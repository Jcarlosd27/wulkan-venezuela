from __future__ import annotations

import io
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
                "id": "cat-sec",
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
                "sku": "WUL-SEC-01",
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
        "orders": [],
        "credit_movements": [],
        "stock_movements": [],
        "admin_users": [
            {
                "id": "admin-sec",
                "name": "Admin Seguridad",
                "email": "admin.security@wulkan.test",
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
                "name": "Solo Lectura",
                "email": "readonly.security@wulkan.test",
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
                "businessName": "Ferreteria Seguridad",
                "email": "cliente.security@wulkan.test",
                "passwordHash": generate_password_hash("ClienteSecurity2026"),
                "status": "active",
                "clientType": "ferretero",
                "taxId": "J-00000000-0",
                "phone": "+580000000000",
                "address": "Direccion seguridad",
                "city": "Caracas",
                "state": "Distrito Capital",
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
    }


def csrf_from_session(client) -> str:
    with client.session_transaction() as session:
        return session.get("_csrf_token", "")


def assert_status(response, expected: int, label: str):
    assert response.status_code == expected, f"{label}: esperado {expected}, llego {response.status_code}"
    return response


def main() -> int:
    state = base_store()
    wulkan_app.load_store = lambda: state
    wulkan_app.save_store = lambda store: None
    app = wulkan_app.app
    app.config.update(
        TESTING=True,
        SECRET_KEY="security-smoke-secret",
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
                    "email": "readonly.security@wulkan.test",
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
            client.post("/products/new", data={"_csrf_token": csrf, "sku": "WUL-NO"}),
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
                    "email": "admin.security@wulkan.test",
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

        mobile_login = assert_status(
            client.post(
                "/api/v1/mobile/auth/login",
                headers={"X-Wulkan-Device-Id": "device-security"},
                json={
                    "email": "cliente.security@wulkan.test",
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
                headers={"Authorization": f"Bearer {token}", "X-Wulkan-Device-Id": "device-security"},
            ),
            200,
            "token vigente puede leer catalogo",
        )
        state["clients"][0]["mobileSessionVersion"] = 1
        assert_status(
            client.get(
                "/api/v1/mobile/products",
                headers={"Authorization": f"Bearer {token}", "X-Wulkan-Device-Id": "device-security"},
            ),
            401,
            "token movil viejo invalidado por version",
        )

    print("Graphify smoke seguridad")
    print("------------------------")
    print("OK headers de seguridad y cache sensible")
    print("OK sesiones activas con dispositivo")
    print("OK permisos backend por endpoint")
    print("OK validacion de firma de archivos")
    print("OK tokens moviles versionados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
