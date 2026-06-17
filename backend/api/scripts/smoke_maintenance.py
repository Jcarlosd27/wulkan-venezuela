from __future__ import annotations

import copy
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app as FVENTAS_app
from store import utc_now
from werkzeug.security import generate_password_hash


def base_store() -> dict:
    now = utc_now()
    company_id = "company-fventas-chile"
    return {
        "companies": [
            {
                "id": company_id,
                "name": "FVENTAS",
                "country": "CL",
                "currency": "CLP",
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "subscriptions": [
            {
                "id": "sub-maintenance",
                "companyId": company_id,
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
        "admin_users": [
            {
                "id": "admin-maintenance",
                "companyId": company_id,
                "name": "Admin Mantenimiento",
                "email": "admin.maintenance@FVENTAS.test",
                "passwordHash": generate_password_hash("AdminMaintenance2026"),
                "role": "super_admin",
                "status": "active",
                "sessionVersion": 0,
                "mustChangePassword": False,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "clients": [],
        "categories": [],
        "products": [],
        "orders": [],
        "quotes": [],
        "crm_records": [],
        "announcements": [],
        "media_assets": [],
        "credit_movements": [],
        "stock_movements": [],
        "notifications": [],
        "service_technicians": [],
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
        SECRET_KEY="maintenance-smoke-secret",
        APP_VERSION="9.0.0-test",
        BUILD_SHA="smoke-maintenance",
        DATA_BACKEND="sql",
        STORAGE_BACKEND="s3",
        REQUIRE_MOBILE_TOKEN=True,
        SQL_FALLBACK_TO_JSON=False,
        WTF_CSRF_ENABLED=False,
    )

    with FVENTAS_app.app.test_client() as client:
        with client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["admin_user_id"] = "admin-maintenance"
            session["admin_name"] = "Admin Mantenimiento"
            session["admin_role"] = "super_admin"
            session["_csrf_token"] = "csrf-maintenance"

        page = assert_status(client.get("/maintenance"), 200, "modulo mantenimiento")
        page_html = page.get_data(as_text=True)
        assert "Mantenimiento" in page_html
        assert "Checklist de produccion" in page_html
        assert "20260615_0011_tenant_scoped_client_product_indexes" in page_html

        export = assert_status(client.get("/maintenance/export"), 200, "export mantenimiento")
        assert "text/csv" in export.mimetype
        assert "Indices SQL" in export.get_data(as_text=True)

        meta = assert_status(client.get("/api/v1/mobile/meta"), 200, "meta movil")
        assert meta["meta"]["appVersion"] == "9.0.0-test"
        assert meta["meta"]["buildSha"] == "smoke-maintenance"
        assert meta["capabilities"]["tokenRequired"] is True

    print("Smoke maintenance OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
