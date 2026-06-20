from __future__ import annotations

import copy
import io
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app as FVENTAS_app
from store import DEFAULT_COMPANY_ID, SAAS_PLAN_ID, SAAS_PLAN_NAME, SAAS_PLAN_PRICE_CLP, normalize_store, utc_now

generate_password_hash = FVENTAS_app.generate_password_hash


def assert_blank_company_ids_are_normalized() -> None:
    now = utc_now()
    tenant_store = {
        "companies": [
            {
                "id": DEFAULT_COMPANY_ID,
                "name": "FVENTAS",
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "subscriptions": [],
        "categories": [{"id": "cat-blank", "companyId": "", "name": "Categoria huerfana"}],
        "products": [{"id": "prod-none", "companyId": None, "title": "Producto huerfano"}],
        "clients": [{"id": "client-space", "companyId": "   ", "businessName": "Cliente huerfano"}],
        "audit_events": [{"id": "audit-missing", "action": "legacy"}],
    }
    normalize_store(tenant_store)
    assert tenant_store["categories"][0]["companyId"] == DEFAULT_COMPANY_ID
    assert tenant_store["products"][0]["companyId"] == DEFAULT_COMPANY_ID
    assert tenant_store["clients"][0]["companyId"] == DEFAULT_COMPANY_ID
    assert tenant_store["audit_events"][0]["companyId"] == DEFAULT_COMPANY_ID


def assert_download_filenames_are_safe() -> None:
    unsafe_csv = FVENTAS_app.safe_download_filename("reporte\r\nX-Injected: yes.csv", "reporte_fventas.csv")
    assert "\r" not in unsafe_csv and "\n" not in unsafe_csv
    assert "/" not in unsafe_csv and "\\" not in unsafe_csv
    assert unsafe_csv.endswith(".csv")

    unsafe_quote = FVENTAS_app.safe_download_filename('FVT/1031 "cliente"\n.html', "cotizacion_fventas.html")
    assert "/" not in unsafe_quote and '"' not in unsafe_quote and "\n" not in unsafe_quote
    assert unsafe_quote.endswith(".html")


def assert_temporary_passwords_follow_policy() -> None:
    assert not FVENTAS_app.password_errors(FVENTAS_app.temporary_admin_password())
    assert not FVENTAS_app.password_errors(FVENTAS_app.temporary_mobile_client_password())


def assert_role_boundaries_are_enforced() -> None:
    platform_modules = set(FVENTAS_app.PLATFORM_MODULES)
    archived_modules = set(FVENTAS_app.ARCHIVED_TENANT_MODULES)
    tenant_roles = set(FVENTAS_app.WEB_ADMIN_ROLES) - {"platform_admin"}
    platform_endpoints = {
        "platform_companies": ("GET", "platform_companies", "view"),
        "company_subscription_update": ("POST", "platform_companies", "edit"),
        "platform_privacy": ("GET", "platform_privacy", "view"),
        "platform_privacy_export": ("GET", "platform_privacy", "export"),
        "platform_privacy_deletion_action": ("POST", "platform_privacy", "approve"),
    }

    assert "sales" not in FVENTAS_app.WEB_ADMIN_ROLES, "vendedor movil no debe ser rol de panel web"
    assert "client" not in FVENTAS_app.WEB_ADMIN_ROLES, "cliente B2B no debe ser rol de panel web"
    assert "collections" not in FVENTAS_app.WEB_ADMIN_ROLES, "cobranza queda archivado, no debe ser rol asignable"
    assert "dispatch" not in FVENTAS_app.WEB_ADMIN_ROLES, "despacho queda archivado, no debe ser rol asignable"
    assert "platform_admin" not in FVENTAS_app.MOBILE_SALES_ROLES, "dueno plataforma no debe entrar como vendedor movil"

    assert archived_modules, "debe existir un conjunto de modulos archivados para el lanzamiento movil"
    assert "crm" in archived_modules and "reports" in archived_modules, "CRM/reportes no son parte del panel MVP empresa"
    for module in FVENTAS_app.MOBILE_LAUNCH_TENANT_MODULES:
        assert module in FVENTAS_app.TENANT_MODULE_KEYS, f"{module} debe ser modulo de empresa"
        assert module not in archived_modules, f"{module} no debe quedar archivado"

    for module in archived_modules:
        assert FVENTAS_app.role_can("platform_admin", module, "view"), (
            f"platform_admin conserva acceso interno al modulo archivado {module}"
        )
        for role in tenant_roles:
            assert not FVENTAS_app.role_permission_actions(role, module), (
                f"{role} no debe tener permisos sobre modulo archivado {module}"
            )

    for module in platform_modules:
        assert FVENTAS_app.role_can("platform_admin", module, "view"), "platform_admin debe administrar plataforma"
        assert module not in FVENTAS_app.TENANT_MODULE_KEYS, f"{module} no debe pertenecer a modulos de empresa"
        for role in tenant_roles:
            assert not FVENTAS_app.role_permission_actions(role, module), (
                f"{role} no debe tener permisos sobre modulo de plataforma {module}"
            )

    for endpoint, (method, expected_module, expected_action) in platform_endpoints.items():
        permission = FVENTAS_app.endpoint_permission(endpoint, method)
        assert permission == (expected_module, expected_action), f"{endpoint} debe exigir permiso de plataforma"
        assert FVENTAS_app.role_can("platform_admin", expected_module, expected_action)
        for role in tenant_roles:
            assert not FVENTAS_app.role_can(role, expected_module, expected_action), (
                f"{role} no debe pasar permiso {expected_module}.{expected_action}"
            )


def assert_admin_routes_have_permission_coverage() -> None:
    public_endpoints = {
        "account_deletion_page",
        "desktop_download",
        "healthz",
        "landing",
        "landing_access_preference",
        "login",
        "privacy_policy",
        "readyz",
        "signup",
        "signup_success",
        "static",
        "terms_of_service",
    }
    expected_session_only_endpoints = {
        "account_password",
        "account_profile_alias",
        "logout",
    }
    unprotected: list[tuple[str, str, str]] = []
    post_as_view: list[tuple[str, str]] = []

    for rule in FVENTAS_app.app.url_map.iter_rules():
        endpoint = rule.endpoint
        methods = set(rule.methods or set()) - {"HEAD", "OPTIONS"}
        is_mobile_api = rule.rule.startswith(("/api/mobile/", "/api/v1/mobile/"))
        is_static = rule.rule.startswith("/static/")
        if endpoint in public_endpoints or endpoint in expected_session_only_endpoints or is_mobile_api or is_static:
            continue

        view = FVENTAS_app.app.view_functions.get(endpoint)
        has_permission_map = endpoint in FVENTAS_app.ENDPOINT_MODULE_MAP
        has_role_guard = bool(getattr(view, "_required_roles", ()))
        if not has_permission_map and not has_role_guard:
            unprotected.append((rule.rule, endpoint, ",".join(sorted(methods))))

        if "POST" in methods and has_permission_map:
            permission = FVENTAS_app.endpoint_permission(endpoint, "POST")
            if permission and permission[1] == "view":
                post_as_view.append((rule.rule, endpoint))

    assert not unprotected, f"Rutas privadas sin modulo ni rol explicito: {unprotected}"
    assert not post_as_view, f"Rutas POST administrativas no deben mapearse como solo view: {post_as_view}"


def assert_platform_routes_reject_tenant_roles(app, state: dict) -> None:
    now = utc_now()
    state["admin_users"].append(
        {
            "id": "platform-owner-sec",
            "companyId": "",
            "name": "Owner Plataforma",
            "email": "owner.platform@FVENTAS.test",
            "passwordHash": generate_password_hash("PlatformOwner2026"),
            "role": "platform_admin",
            "status": "active",
            "sessionVersion": 0,
            "mustChangePassword": False,
            "activeSessions": [],
            "createdAt": now,
            "updatedAt": now,
        }
    )

    with app.test_client() as role_client:
        with role_client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["admin_user_id"] = "admin-sec"
            session["admin_name"] = "Admin Seguridad"
            session["admin_role"] = "super_admin"
            session["company_id"] = DEFAULT_COMPANY_ID
            session["admin_session_version"] = 0
        assert_status(role_client.get("/platform/companies"), 403, "super_admin empresa no abre empresas SaaS")
        assert_status(role_client.get("/platform/privacy"), 403, "super_admin empresa no abre privacidad plataforma")
        for path in [
            "/crm",
            "/quotes",
            "/quotes/new",
            "/collections",
            "/dispatch",
            "/reports",
            "/reports/print",
            "/maintenance",
            "/permissions",
        ]:
            assert_status(role_client.get(path), 403, f"super_admin empresa no abre modulo archivado {path}")

        with role_client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["admin_user_id"] = "platform-owner-sec"
            session["admin_name"] = "Owner Plataforma"
            session["admin_role"] = "platform_admin"
            session["company_id"] = ""
            session["admin_session_version"] = 0
        assert_status(role_client.get("/platform/companies"), 200, "platform_admin abre empresas SaaS")
        assert_status(role_client.get("/platform/privacy"), 200, "platform_admin abre privacidad plataforma")
        assert_status(role_client.get("/maintenance"), 200, "platform_admin abre mantenimiento interno")


def assert_legacy_mobile_api_can_be_disabled(app) -> None:
    original_legacy_api = app.config.get("ALLOW_LEGACY_MOBILE_API", True)
    try:
        app.config["ALLOW_LEGACY_MOBILE_API"] = False
        with app.test_client() as public_client:
            response = assert_status(
                public_client.get("/api/mobile/products"),
                410,
                "api movil legacy deshabilitada",
            )
            payload = response.get_json()
            assert payload["code"] == "legacy_mobile_api_disabled"
    finally:
        app.config["ALLOW_LEGACY_MOBILE_API"] = original_legacy_api


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
            {
                "id": "seller-sec",
                "companyId": DEFAULT_COMPANY_ID,
                "name": "Vendedor Seguridad",
                "email": "seller.security@FVENTAS.test",
                "passwordHash": generate_password_hash("SellerSecurity2026"),
                "role": "sales",
                "status": "active",
                "sessionVersion": 0,
                "mustChangePassword": False,
                "mobileAccessEnabled": True,
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
        "mobile_write_rate_events": [],
        "business_settings": {
            "marketCountry": "CL",
            "salesCurrency": "USD",
            "localCurrency": "CLP",
            "exchangeRateBaseToLocal": 950,
            "defaultPaymentTermsDays": [0, 15, 30],
            "purchaseConditionsTitle": "Condiciones de compra",
            "purchaseDefaultSaleType": "cash",
            "purchaseConditionsScope": "Solo datos de tu empresa",
            "purchaseConditionsNote": "Solo se muestran datos de la empresa autenticada.",
            "orderTermsText": "Solo se muestran datos de la empresa autenticada.",
        },
    }


def csrf_from_session(client) -> str:
    with client.session_transaction() as session:
        return session.get("_csrf_token", "")


def assert_status(response, expected: int, label: str):
    assert response.status_code == expected, f"{label}: esperado {expected}, llego {response.status_code}"
    return response


def main() -> int:
    assert_blank_company_ids_are_normalized()
    assert_download_filenames_are_safe()
    assert_temporary_passwords_follow_policy()
    assert_role_boundaries_are_enforced()
    assert_admin_routes_have_permission_coverage()

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
        REQUIRE_MOBILE_DEVICE_HEADER=True,
        WTF_CSRF_ENABLED=False,
    )
    assert_platform_routes_reject_tenant_roles(app, state)
    assert_legacy_mobile_api_can_be_disabled(app)

    original_trust_proxy = app.config.get("TRUST_PROXY_HEADERS", False)
    try:
        app.config["TRUST_PROXY_HEADERS"] = False
        with app.test_request_context(
            "/",
            headers={"X-Forwarded-For": "203.0.113.99"},
            environ_base={"REMOTE_ADDR": "10.0.0.7"},
        ):
            assert FVENTAS_app.request_ip_address() == "10.0.0.7", "X-Forwarded-For no confiable no debe reemplazar REMOTE_ADDR"
        app.config["TRUST_PROXY_HEADERS"] = True
        with app.test_request_context(
            "/",
            headers={"X-Forwarded-For": "203.0.113.99, 10.0.0.7"},
            environ_base={"REMOTE_ADDR": "10.0.0.7"},
        ):
            assert FVENTAS_app.request_ip_address() == "203.0.113.99", "proxy confiable debe usar primera IP de X-Forwarded-For"
    finally:
        app.config["TRUST_PROXY_HEADERS"] = original_trust_proxy

    assert FVENTAS_app.safe_export_cell("=IMPORTXML('http://evil.test')").startswith("'=")
    assert FVENTAS_app.safe_export_cell("+SUM(1,1)").startswith("'+")
    assert FVENTAS_app.safe_export_cell(-1200) == -1200
    export_buffer = io.StringIO()
    writer = FVENTAS_app.safe_csv_dict_writer(export_buffer, fieldnames=["cliente", "nota"], lineterminator="\n")
    writer.writeheader()
    writer.writerow({"cliente": "Cliente Seguro", "nota": "@cmd"})
    assert "'@cmd" in export_buffer.getvalue(), "CSV exportado debe neutralizar formulas"
    with app.test_request_context("/"):
        assert FVENTAS_app.safe_internal_url("/notifications?status=unread", "notifications") == "/notifications?status=unread"
        assert FVENTAS_app.safe_internal_url("https://evil.test/phish", "notifications") == "/notifications"
        assert FVENTAS_app.safe_internal_url("//evil.test/phish", "notifications") == "/notifications"
    notification_store = copy.deepcopy(state)
    notification_other_company_id = "company-notification-other-sec"
    notification_duplicate_client_id = "client-notification-dup-sec"
    notification_store["companies"].append(
        {
            "id": notification_other_company_id,
            "name": "Empresa Notificacion Ajena",
            "country": "CL",
            "status": "active",
            "createdAt": utc_now(),
            "updatedAt": utc_now(),
        }
    )
    notification_store["clients"].extend(
        [
            {
                **notification_store["clients"][0],
                "id": notification_duplicate_client_id,
                "companyId": DEFAULT_COMPANY_ID,
                "businessName": "Cliente Notificacion Principal",
                "email": "notificacion.principal@fventas.test",
            },
            {
                **notification_store["clients"][0],
                "id": notification_duplicate_client_id,
                "companyId": notification_other_company_id,
                "businessName": "Cliente Notificacion Otra Empresa",
                "email": "notificacion.otra@fventas.test",
            },
        ]
    )
    with app.test_request_context("/notification-smoke"):
        FVENTAS_app.session["admin_authenticated"] = True
        FVENTAS_app.session["admin_user_id"] = "admin-sec"
        FVENTAS_app.session["admin_name"] = "Admin Seguridad"
        FVENTAS_app.session["admin_role"] = "super_admin"
        FVENTAS_app.session["company_id"] = notification_other_company_id
        scoped_notification = FVENTAS_app.create_notification(
            notification_store,
            title="Notificacion acotada",
            body="Debe quedar en la empresa de la sesion.",
            recipient_type="client",
            recipient_id=notification_duplicate_client_id,
            entity_type="client",
            entity_id=notification_duplicate_client_id,
        )
        assert scoped_notification["companyId"] == notification_other_company_id, "notificacion duplicada debe tomar empresa de sesion autenticada"
    with app.test_request_context("/notification-smoke-public"):
        unresolved_notification = FVENTAS_app.create_notification(
            notification_store,
            title="Notificacion ambigua",
            body="No debe caer al tenant por defecto.",
            recipient_type="client",
            recipient_id=notification_duplicate_client_id,
            entity_type="client",
            entity_id=notification_duplicate_client_id,
        )
        assert (
            unresolved_notification["companyId"] == FVENTAS_app.UNRESOLVED_NOTIFICATION_COMPANY_ID
        ), "notificacion ambigua sin contexto no debe asignarse a una empresa arbitraria"
    tenant_mutation_company_id = "company-mutation-other-sec"
    state["companies"].append(
        {
            "id": tenant_mutation_company_id,
            "name": "Empresa Mutacion Ajena",
            "country": "CL",
            "status": "active",
            "createdAt": utc_now(),
            "updatedAt": utc_now(),
        }
    )
    state["announcements"].extend(
        [
            {
                "id": "ann-tenant-dup-sec",
                "companyId": DEFAULT_COMPANY_ID,
                "title": "Anuncio Tenant Principal",
                "body": "Debe eliminarse solo este.",
                "placement": "home",
                "priority": 1,
                "status": "active",
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            },
            {
                "id": "ann-tenant-dup-sec",
                "companyId": tenant_mutation_company_id,
                "title": "Anuncio Tenant Ajeno",
                "body": "Debe conservarse.",
                "placement": "home",
                "priority": 1,
                "status": "active",
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            },
        ]
    )
    with app.test_client() as mutation_client:
        mutation_csrf = "tenant-mutation-csrf"
        with mutation_client.session_transaction() as session:
            session["_csrf_token"] = mutation_csrf
            session["admin_authenticated"] = True
            session["admin_user_id"] = "admin-sec"
            session["admin_name"] = "Admin Seguridad"
            session["admin_role"] = "super_admin"
            session["company_id"] = DEFAULT_COMPANY_ID
            session["admin_session_version"] = 0
        assert_status(
            mutation_client.post(
                "/announcements/ann-tenant-dup-sec/delete",
                data={"_csrf_token": mutation_csrf},
            ),
            302,
            "borrado de anuncio acotado por empresa",
        )
    assert not any(
        item.get("id") == "ann-tenant-dup-sec" and item.get("companyId") == DEFAULT_COMPANY_ID
        for item in state["announcements"]
    ), "borrado debe eliminar solo el anuncio de la empresa actual"
    assert any(
        item.get("id") == "ann-tenant-dup-sec" and item.get("companyId") == tenant_mutation_company_id
        for item in state["announcements"]
    ), "borrado no debe eliminar anuncio homonimo de otra empresa"
    state["announcements"].extend(
        [
            {
                "id": "ann-tenant-order-sec",
                "companyId": tenant_mutation_company_id,
                "title": "Anuncio Ajeno Primero",
                "body": "Debe conservarse aunque aparezca primero.",
                "placement": "home",
                "priority": 1,
                "status": "active",
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            },
            {
                "id": "ann-tenant-order-sec",
                "companyId": DEFAULT_COMPANY_ID,
                "title": "Anuncio Propio Segundo",
                "body": "Debe eliminarse desde la empresa actual.",
                "placement": "home",
                "priority": 1,
                "status": "active",
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            },
        ]
    )
    with app.test_client() as mutation_client:
        mutation_csrf = "tenant-mutation-order-csrf"
        with mutation_client.session_transaction() as session:
            session["_csrf_token"] = mutation_csrf
            session["admin_authenticated"] = True
            session["admin_user_id"] = "admin-sec"
            session["admin_name"] = "Admin Seguridad"
            session["admin_role"] = "super_admin"
            session["company_id"] = DEFAULT_COMPANY_ID
            session["admin_session_version"] = 0
        assert_status(
            mutation_client.post(
                "/announcements/ann-tenant-order-sec/delete",
                data={"_csrf_token": mutation_csrf},
            ),
            302,
            "borrado de anuncio con duplicado ajeno previo",
        )
    assert not any(
        item.get("id") == "ann-tenant-order-sec" and item.get("companyId") == DEFAULT_COMPANY_ID
        for item in state["announcements"]
    ), "borrado debe encontrar el registro propio aunque el duplicado ajeno aparezca antes"
    assert any(
        item.get("id") == "ann-tenant-order-sec" and item.get("companyId") == tenant_mutation_company_id
        for item in state["announcements"]
    ), "borrado con duplicado ajeno previo no debe tocar otra empresa"
    audit_store = copy.deepcopy(state)
    audit_other_company_id = "company-audit-other-sec"
    audit_store["companies"].append(
        {
            "id": audit_other_company_id,
            "name": "Empresa Auditoria Ajena",
            "country": "CL",
            "status": "active",
            "createdAt": utc_now(),
            "updatedAt": utc_now(),
        }
    )
    audit_store["subscriptions"].append(
        {
            "id": f"sub-{audit_other_company_id}",
            "companyId": audit_other_company_id,
            "planId": SAAS_PLAN_ID,
            "planName": SAAS_PLAN_NAME,
            "status": "past_due",
            "createdAt": utc_now(),
            "updatedAt": utc_now(),
        }
    )
    with app.test_request_context("/audit-mobile-smoke"):
        FVENTAS_app.record_audit_event(
            audit_store,
            "mobile_subscription_blocked",
            "subscription",
            audit_other_company_id,
            "Acceso movil bloqueado por suscripcion ajena al default.",
            actor={"id": "client-audit", "name": "Cliente Auditoria", "role": "client"},
        )
    audit_event = next(
        item
        for item in audit_store["audit_events"]
        if item.get("action") == "mobile_subscription_blocked"
    )
    assert audit_event["companyId"] == audit_other_company_id, "auditoria sin sesion debe inferir empresa desde la entidad"
    inventory_store = copy.deepcopy(state)
    inventory_other_company_id = "company-inventory-other-sec"
    inventory_product_id = "prod-inventory-dup-sec"
    inventory_store["companies"].append(
        {
            "id": inventory_other_company_id,
            "name": "Empresa Inventario Ajena",
            "country": "CL",
            "status": "active",
            "createdAt": utc_now(),
            "updatedAt": utc_now(),
        }
    )
    inventory_store["products"].extend(
        [
            {
                **inventory_store["products"][0],
                "id": inventory_product_id,
                "companyId": DEFAULT_COMPANY_ID,
                "sku": "FVT-STOCK-DUP-A",
                "title": "Stock duplicado principal",
                "stock": 1,
            },
            {
                **inventory_store["products"][0],
                "id": inventory_product_id,
                "companyId": inventory_other_company_id,
                "sku": "FVT-STOCK-DUP-B",
                "title": "Stock duplicado otra empresa",
                "stock": 1,
            },
        ]
    )
    inventory_store["orders"].append(
        {
            "id": "order-inventory-main-sec",
            "orderId": "order-inventory-main-sec",
            "companyId": DEFAULT_COMPANY_ID,
            "customerId": "client-sec",
            "items": [{"productId": inventory_product_id, "quantity": 1}],
            "inventoryStatus": "reserved",
            "status": "approved_with_credit",
            "createdAt": utc_now(),
            "updatedAt": utc_now(),
        }
    )
    inventory_other_order = {
        "id": "order-inventory-other-sec",
        "orderId": "order-inventory-other-sec",
        "companyId": inventory_other_company_id,
        "customerId": "client-inventory-other-sec",
        "items": [{"productId": inventory_product_id, "quantity": 1}],
        "inventoryStatus": "",
        "status": "approved_with_credit",
        "createdAt": utc_now(),
        "updatedAt": utc_now(),
    }
    with app.test_request_context("/inventory-smoke"):
        FVENTAS_app.session["admin_name"] = "Admin Seguridad"
        assert FVENTAS_app.order_has_sufficient_stock(
            inventory_store,
            inventory_other_order,
        ), "stock reservado en otra empresa no debe bloquear inventario del tenant"
        assert FVENTAS_app.reserve_stock_for_order(
            inventory_store,
            inventory_other_order,
        ), "reserva de inventario debe operar dentro de la empresa de la orden"
    inventory_movement = next(
        item
        for item in inventory_store["stock_movements"]
        if item.get("orderId") == "order-inventory-other-sec"
    )
    assert inventory_movement["companyId"] == inventory_other_company_id, "movimiento de stock debe conservar empresa de la orden"
    duplicate_admin_company_id = "company-admin-duplicate-sec"
    duplicate_admin_email = "admin.duplicado@fventas.test"
    state["companies"].append(
        {
            "id": duplicate_admin_company_id,
            "name": "Empresa Admin Duplicado",
            "country": "CL",
            "status": "active",
            "createdAt": utc_now(),
            "updatedAt": utc_now(),
        }
    )
    duplicate_admins = [
        {
            **state["admin_users"][0],
            "id": "admin-dup-a-sec",
            "companyId": DEFAULT_COMPANY_ID,
            "email": duplicate_admin_email,
            "passwordHash": generate_password_hash("AdminDuplicado2026"),
            "sessionVersion": 0,
            "failedLoginAttempts": 0,
        },
        {
            **state["admin_users"][0],
            "id": "admin-dup-b-sec",
            "companyId": duplicate_admin_company_id,
            "email": duplicate_admin_email,
            "passwordHash": generate_password_hash("AdminDuplicado2026"),
            "sessionVersion": 0,
            "failedLoginAttempts": 0,
        },
    ]
    state["admin_users"].extend(duplicate_admins)
    with app.test_client() as duplicate_admin_client:
        assert_status(duplicate_admin_client.get("/login"), 200, "pagina login admin duplicado")
        duplicate_login_csrf = csrf_from_session(duplicate_admin_client)
        duplicate_login = assert_status(
            duplicate_admin_client.post(
                "/login",
                data={
                    "_csrf_token": duplicate_login_csrf,
                    "email": duplicate_admin_email,
                    "password": "AdminDuplicado2026",
                },
            ),
            200,
            "login admin duplicado no inicia sesion arbitraria",
        )
        assert "Credenciales invalidas" in duplicate_login.get_data(as_text=True)
        with duplicate_admin_client.session_transaction() as duplicate_session:
            assert not duplicate_session.get("admin_authenticated"), "login duplicado no debe autenticar al primer usuario"
    assert any(
        event.get("action") == "login_blocked"
        and event.get("entityId") == duplicate_admin_email
        and "duplicada" in event.get("detail", "")
        for event in state["audit_events"]
    ), "login admin duplicado debe quedar auditado"
    duplicate_admin_ids = {item["id"] for item in duplicate_admins}
    state["admin_users"] = [
        item for item in state["admin_users"] if item.get("id") not in duplicate_admin_ids
    ]
    session_duplicate_admin_id = "admin-session-dup-sec"
    foreign_session_admin = {
        **state["admin_users"][0],
        "id": session_duplicate_admin_id,
        "companyId": duplicate_admin_company_id,
        "name": "Admin Sesion Ajena",
        "email": "admin.sesion.ajena@fventas.test",
        "passwordHash": generate_password_hash("AdminSesionAjena2026"),
        "sessionVersion": 0,
        "failedLoginAttempts": 0,
    }
    own_session_admin = {
        **state["admin_users"][0],
        "id": session_duplicate_admin_id,
        "companyId": DEFAULT_COMPANY_ID,
        "name": "Admin Sesion Propia",
        "email": "admin.sesion.propia@fventas.test",
        "passwordHash": generate_password_hash("AdminSesionPropia2026"),
        "sessionVersion": 0,
        "failedLoginAttempts": 0,
    }
    state["admin_users"].insert(0, foreign_session_admin)
    state["admin_users"].append(own_session_admin)
    with app.test_client() as password_client:
        password_csrf = "password-session-dup-csrf"
        with password_client.session_transaction() as session:
            session["_csrf_token"] = password_csrf
            session["admin_authenticated"] = True
            session["admin_user_id"] = session_duplicate_admin_id
            session["admin_name"] = "Admin Sesion Propia"
            session["admin_role"] = "super_admin"
            session["company_id"] = DEFAULT_COMPANY_ID
            session["admin_session_version"] = 0
        password_response = assert_status(
            password_client.post(
                "/account/password",
                data={
                    "_csrf_token": password_csrf,
                    "currentPassword": "AdminSesionPropia2026",
                    "newPassword": "AdminSesionPropia2027",
                    "confirmPassword": "AdminSesionPropia2027",
                },
            ),
            200,
            "cambio de contrasena admin usa usuario de empresa de sesion",
        )
        assert "Contrasena actualizada correctamente" in password_response.get_data(as_text=True)
    assert FVENTAS_app.check_password_hash(
        own_session_admin["passwordHash"],
        "AdminSesionPropia2027",
    ), "contrasena debe cambiar en el admin de la empresa de sesion"
    assert not FVENTAS_app.check_password_hash(
        foreign_session_admin["passwordHash"],
        "AdminSesionPropia2027",
    ), "contrasena no debe cambiar en el admin duplicado de otra empresa"
    with app.test_client() as incomplete_session_client:
        incomplete_csrf = "password-session-incomplete-csrf"
        with incomplete_session_client.session_transaction() as session:
            session["_csrf_token"] = incomplete_csrf
            session["admin_authenticated"] = True
            session["admin_user_id"] = session_duplicate_admin_id
            session["admin_name"] = "Admin Sesion Ambigua"
            session["admin_role"] = "super_admin"
            session["admin_session_version"] = 0
        assert_status(
            incomplete_session_client.post(
                "/account/password",
                data={
                    "_csrf_token": incomplete_csrf,
                    "currentPassword": "AdminSesionPropia2027",
                    "newPassword": "AdminSesionPropia2028",
                    "confirmPassword": "AdminSesionPropia2028",
                },
            ),
            302,
            "sesion admin sin empresa no debe resolver usuario duplicado",
        )
        with incomplete_session_client.session_transaction() as session:
            assert not session.get("admin_authenticated"), "sesion ambigua debe quedar cerrada"
    assert not FVENTAS_app.check_password_hash(
        own_session_admin["passwordHash"],
        "AdminSesionPropia2028",
    ), "sesion sin empresa no debe cambiar contrasena"
    state["admin_users"] = [
        item
        for item in state["admin_users"]
        if item.get("id") != session_duplicate_admin_id
    ]
    class ImportDraftStub:
        def __init__(self, result: dict, created_by_id: str = "admin-sec"):
            self.result = result
            self.created_by_id = created_by_id

    with app.test_request_context("/plantillas"):
        FVENTAS_app.session["admin_authenticated"] = True
        FVENTAS_app.session["admin_user_id"] = "admin-sec"
        FVENTAS_app.session["admin_role"] = "super_admin"
        FVENTAS_app.session["company_id"] = DEFAULT_COMPANY_ID
        assert FVENTAS_app.import_draft_is_accessible(
            ImportDraftStub({"companyId": DEFAULT_COMPANY_ID})
        ), "borrador de importacion de la empresa debe ser accesible"
        assert not FVENTAS_app.import_draft_is_accessible(
            ImportDraftStub({"companyId": "company-ajena-import-sec"})
        ), "borrador de importacion ajeno no debe ser accesible"
        assert FVENTAS_app.import_draft_is_accessible(
            ImportDraftStub({}, created_by_id="admin-sec")
        ), "borrador legacy solo debe ser accesible por su creador"
        assert not FVENTAS_app.import_draft_is_accessible(
            ImportDraftStub({}, created_by_id="otro-admin")
        ), "borrador legacy de otro usuario no debe ser accesible"
        FVENTAS_app.session["admin_role"] = "platform_admin"
        assert FVENTAS_app.import_draft_is_accessible(
            ImportDraftStub({"companyId": "company-ajena-import-sec"}, created_by_id="otro-admin")
        ), "plataforma debe poder revisar borradores de cualquier empresa"
    existing_privacy_client = {
        **state["clients"][0],
        "deletionStatus": "requested",
        "deletionRequestId": "acctdel-preserve-sec",
        "mobileAccessEnabled": False,
        "mobileSessionVersion": 7,
    }
    with app.test_request_context(
        "/clients/client-sec/edit",
        method="POST",
        data={
            "email": "cliente.security@FVENTAS.test",
            "businessName": "Cliente Seguridad Editado",
            "legalName": "Cliente Seguridad Editado",
            "taxId": "11.111.111-1",
            "phone": "+56 9 1000 0000",
            "status": "active",
            "clientType": "b2b",
            "clientCategory": "standard",
            "priceList": "b2b",
            "defaultSaleType": "cash",
            "collectionStatus": "without_debt",
            "creditRiskLevel": "low",
            "allowedPaymentTermsDays": "0",
        },
    ):
        FVENTAS_app.session["admin_user_id"] = "admin-sec"
        FVENTAS_app.session["admin_name"] = "Admin Seguridad"
        FVENTAS_app.session["admin_role"] = "super_admin"
        FVENTAS_app.session["company_id"] = DEFAULT_COMPANY_ID
        preserved_payload = FVENTAS_app.client_payload(existing_privacy_client)
        assert preserved_payload["deletionStatus"] == "requested", "edicion comercial debe preservar estado de privacidad"
        assert preserved_payload["deletionRequestId"] == "acctdel-preserve-sec", "edicion comercial debe preservar solicitud de eliminacion"
        assert preserved_payload["mobileAccessEnabled"] is False, "edicion comercial no debe reactivar acceso movil por omision"
        assert preserved_payload["mobileSessionVersion"] == 7, "edicion comercial no debe reabrir tokens viejos"
    with app.test_request_context(
        "/clients/client-sec/edit",
        method="POST",
        data={
            "email": "cliente.security@FVENTAS.test",
            "businessName": "Cliente Seguridad Editado",
            "legalName": "Cliente Seguridad Editado",
            "taxId": "11.111.111-1",
            "phone": "+56 9 1000 0000",
            "password": "ClienteSecurityReset2026",
            "status": "active",
            "clientType": "b2b",
            "clientCategory": "standard",
            "priceList": "b2b",
            "defaultSaleType": "cash",
            "collectionStatus": "without_debt",
            "creditRiskLevel": "low",
            "allowedPaymentTermsDays": "0",
        },
    ):
        FVENTAS_app.session["admin_user_id"] = "admin-sec"
        FVENTAS_app.session["admin_name"] = "Admin Seguridad"
        FVENTAS_app.session["admin_role"] = "super_admin"
        FVENTAS_app.session["company_id"] = DEFAULT_COMPANY_ID
        reset_payload = FVENTAS_app.client_payload({**state["clients"][0], "mobileSessionVersion": 4})
        assert reset_payload["mobileSessionVersion"] == 5, "reset admin de clave cliente debe revocar tokens moviles"

    original_upload_folder = app.config.get("UPLOAD_FOLDER")
    with tempfile.TemporaryDirectory() as upload_dir:
        documents_dir = Path(upload_dir) / "documents"
        documents_dir.mkdir(parents=True, exist_ok=True)
        (documents_dir / "security.pdf").write_bytes(b"%PDF-1.4\n%FVENTAS")
        app.config["UPLOAD_FOLDER"] = upload_dir
        with app.test_client() as public_client:
            assert_status(
                public_client.get("/static/uploads/documents/security.pdf"),
                404,
                "documento interno no debe servirse como upload publico",
            )
            state["media_assets"][0]["visibility"] = "public"
            assert_status(
                public_client.get("/static/uploads/documents/security.pdf"),
                200,
                "documento publico puede servirse como upload publico",
            )
            state["media_assets"][0]["visibility"] = "internal"
    app.config["UPLOAD_FOLDER"] = original_upload_folder

    captured_uploads = []
    original_save_uploaded_file = FVENTAS_app.save_uploaded_file
    original_s3_acl = app.config.get("S3_ACL")
    try:
        def fake_save_uploaded_file(**kwargs):
            captured_uploads.append(kwargs)
            return "/static/uploads/documents/mock.pdf"

        FVENTAS_app.save_uploaded_file = fake_save_uploaded_file
        app.config["S3_ACL"] = "public-read"
        FVENTAS_app.save_upload(type("Upload", (), {"filename": "mock.pdf"})(), "documents", public=False)
        assert captured_uploads[-1]["s3_acl"] == "", "documentos privados no deben heredar ACL publica"
        FVENTAS_app.save_upload(type("Upload", (), {"filename": "mock.png"})(), "products", public=True)
        assert captured_uploads[-1]["s3_acl"] == "public-read", "recursos publicos pueden usar ACL publica"
    finally:
        FVENTAS_app.save_uploaded_file = original_save_uploaded_file
        app.config["S3_ACL"] = original_s3_acl

    original_signup_window = app.config.get("SIGNUP_WINDOW_SECONDS")
    original_signup_max = app.config.get("SIGNUP_MAX_EVENTS")
    try:
        app.config["SIGNUP_WINDOW_SECONDS"] = 300
        app.config["SIGNUP_MAX_EVENTS"] = 1
        with app.test_client() as signup_client:
            assert_status(signup_client.get("/signup"), 200, "pagina publica de registro")
            signup_csrf = csrf_from_session(signup_client)
            assert_status(
                signup_client.post(
                    "/signup",
                    data={
                        "_csrf_token": signup_csrf,
                        "marketCountry": "VE",
                        "companyName": "Empresa Signup Seguridad Uno",
                        "legalName": "Empresa Signup Seguridad Uno CA",
                        "taxId": "J-12345678-9",
                        "ownerName": "Admin Signup Seguridad",
                        "supportPhone": "+58 412 1234567",
                        "ownerEmail": "signup.seguridad.uno@fventas.test",
                        "password": "SignupSeguro2026",
                        "confirmPassword": "SignupSeguro2026",
                        "legalAccepted": "on",
                    },
                ),
                302,
                "primer registro publico permitido",
            )
            assert_status(
                signup_client.post(
                    "/signup",
                    data={
                        "_csrf_token": signup_csrf,
                        "marketCountry": "VE",
                        "companyName": "Empresa Signup Seguridad Dos",
                        "legalName": "Empresa Signup Seguridad Dos CA",
                        "taxId": "J-12345679-7",
                        "ownerName": "Admin Signup Seguridad Dos",
                        "supportPhone": "+58 414 7654321",
                        "ownerEmail": "signup.seguridad.dos@fventas.test",
                        "password": "SignupSeguro2026",
                        "confirmPassword": "SignupSeguro2026",
                        "legalAccepted": "on",
                    },
                ),
                429,
                "registro publico repetido queda limitado",
            )
    finally:
        app.config["SIGNUP_WINDOW_SECONDS"] = original_signup_window
        app.config["SIGNUP_MAX_EVENTS"] = original_signup_max

    original_account_deletion_window = app.config.get("ACCOUNT_DELETION_WINDOW_SECONDS")
    original_account_deletion_max = app.config.get("ACCOUNT_DELETION_MAX_EVENTS")
    try:
        app.config["ACCOUNT_DELETION_WINDOW_SECONDS"] = 300
        app.config["ACCOUNT_DELETION_MAX_EVENTS"] = 5
        state["clients"].append(
            {
                **state["clients"][0],
                "id": "client-public-delete-sec",
                "businessName": "Cliente Eliminacion Publica",
                "email": "eliminar.publica@FVENTAS.test",
                "mobileSessionVersion": 0,
            }
        )
        with app.test_client() as public_client:
            assert_status(public_client.get("/account-deletion"), 200, "pagina publica de eliminacion")
            public_csrf = csrf_from_session(public_client)
            assert_status(
                public_client.post(
                    "/account-deletion",
                    data={
                        "_csrf_token": public_csrf,
                        "email": "eliminar.publica@FVENTAS.test",
                        "reason": "prueba cuenta existente",
                    },
                ),
                200,
                "solicitud publica de eliminacion para cuenta existente",
            )
            client_subject = next(item for item in state["clients"] if item["id"] == "client-public-delete-sec")
            assert client_subject.get("mobileAccessEnabled", True) is not False, "solicitud publica no debe bloquear acceso movil"
            assert not client_subject.get("deletionStatus"), "solicitud publica no debe marcar eliminacion sin verificacion"
            assert client_subject.get("mobileSessionVersion", 0) == 0, "solicitud publica no debe revocar sesiones sin verificacion"
            public_request = next(
                (
                    item
                    for item in state.get("account_deletion_requests", [])
                    if item.get("subjectType") == "client" and item.get("subjectId") == "client-public-delete-sec"
                ),
                None,
            )
            assert public_request, "solicitud publica conocida debe quedar en bandeja de privacidad"
            assert public_request["requiresVerification"] is True
            assert public_request["accessBlocked"] is False
        state["admin_users"].append(
            {
                **state["admin_users"][0],
                "id": "platform-sec",
                "name": "Platform Seguridad",
                "email": "platform.security@FVENTAS.test",
                "role": "platform_admin",
                "sessionVersion": 0,
                "activeSessions": [],
            }
        )
        privacy_other_company_id = "company-privacy-other-sec"
        privacy_duplicate_client_id = "client-privacy-dup-sec"
        state["companies"].append(
            {
                "id": privacy_other_company_id,
                "name": "Empresa Privacidad Ajena",
                "country": "CL",
                "status": "active",
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )
        state["clients"].extend(
            [
                {
                    **state["clients"][0],
                    "id": privacy_duplicate_client_id,
                    "companyId": DEFAULT_COMPANY_ID,
                    "businessName": "Cliente Privacidad Principal",
                    "email": "privacidad.principal@fventas.test",
                    "deletionStatus": "requested",
                    "deletionRequestId": "acctdel-privacy-main-sec",
                    "deletionRequestedAt": utc_now(),
                    "mobileAccessEnabled": False,
                    "mobileAccessBlocked": True,
                    "mobileSessionVersion": 0,
                },
                {
                    **state["clients"][0],
                    "id": privacy_duplicate_client_id,
                    "companyId": privacy_other_company_id,
                    "businessName": "Cliente Privacidad Otra Empresa",
                    "email": "privacidad.otra@fventas.test",
                    "deletionStatus": "requested",
                    "deletionRequestId": "acctdel-privacy-other-sec",
                    "deletionRequestedAt": utc_now(),
                    "mobileAccessEnabled": False,
                    "mobileAccessBlocked": True,
                    "mobileSessionVersion": 0,
                },
            ]
        )
        state["orders"].extend(
            [
                {
                    "id": "order-privacy-main-sec",
                    "orderId": "order-privacy-main-sec",
                    "companyId": DEFAULT_COMPANY_ID,
                    "customerId": privacy_duplicate_client_id,
                    "status": "pending",
                    "createdAt": utc_now(),
                    "updatedAt": utc_now(),
                },
                {
                    "id": "order-privacy-other-sec",
                    "orderId": "order-privacy-other-sec",
                    "companyId": privacy_other_company_id,
                    "customerId": privacy_duplicate_client_id,
                    "status": "pending",
                    "createdAt": utc_now(),
                    "updatedAt": utc_now(),
                },
            ]
        )
        privacy_rows_by_company = {
            row["companyId"]: row
            for row in FVENTAS_app.account_deletion_subject_rows(state)
            if row["subjectId"] == privacy_duplicate_client_id
        }
        assert privacy_rows_by_company[DEFAULT_COMPANY_ID]["openOrders"] == 1
        assert privacy_rows_by_company[privacy_other_company_id]["openOrders"] == 1
        with app.test_client() as privacy_client:
            privacy_csrf = "privacy-platform-csrf"
            with privacy_client.session_transaction() as session:
                session["_csrf_token"] = privacy_csrf
                session["admin_authenticated"] = True
                session["admin_user_id"] = "platform-sec"
                session["admin_name"] = "Platform Seguridad"
                session["admin_role"] = "platform_admin"
                session["company_id"] = DEFAULT_COMPANY_ID
                session["admin_session_version"] = 0
            assert_status(
                privacy_client.post(
                    f"/platform/privacy/account-deletion/client/{privacy_duplicate_client_id}/approve",
                    data={
                        "_csrf_token": privacy_csrf,
                        "companyId": privacy_other_company_id,
                        "resolutionNote": "empresa validada por fila",
                    },
                ),
                302,
                "privacidad plataforma resuelve cuenta duplicada por empresa",
            )
            default_privacy_subject = next(
                item
                for item in state["clients"]
                if item.get("id") == privacy_duplicate_client_id and item.get("companyId") == DEFAULT_COMPANY_ID
            )
            other_privacy_subject = next(
                item
                for item in state["clients"]
                if item.get("id") == privacy_duplicate_client_id and item.get("companyId") == privacy_other_company_id
            )
            assert default_privacy_subject["deletionStatus"] == "requested", "accion privacidad no debe tocar empresa equivocada"
            assert other_privacy_subject["deletionStatus"] == "approved", "accion privacidad debe tocar solo la empresa indicada"
            assert_status(
                privacy_client.post(
                    "/platform/privacy/account-deletion/client/client-public-delete-sec/approve",
                    data={
                        "_csrf_token": privacy_csrf,
                        "companyId": DEFAULT_COMPANY_ID,
                        "resolutionNote": "identidad validada",
                    },
                ),
                302,
                "plataforma aprueba solicitud publica conocida",
            )
            assert client_subject["deletionStatus"] == "approved", "solo plataforma debe aprobar eliminacion publica conocida"
            assert client_subject["mobileAccessEnabled"] is False, "aprobacion verificada debe bloquear acceso movil"
            assert client_subject["mobileSessionVersion"] == 1, "aprobacion verificada debe revocar tokens de la cuenta"
            assert public_request["status"] == "approved"
            assert public_request["requiresVerification"] is False
            assert public_request["accessBlocked"] is True
            state["clients"].append(
                {
                    **state["clients"][0],
                    "id": "client-reject-delete-sec",
                    "businessName": "Cliente Rechazo Eliminacion",
                    "email": "rechazo.eliminacion@FVENTAS.test",
                    "status": "active",
                    "deletionStatus": "requested",
                    "deletionRequestId": "acctdel-reject-sec",
                    "deletionRequestedAt": utc_now(),
                    "mobileAccessEnabled": False,
                    "mobileAccessBlocked": True,
                    "mobileSessionVersion": 2,
                }
            )
            assert_status(
                privacy_client.post(
                    "/platform/privacy/account-deletion/client/client-reject-delete-sec/reject",
                    data={"_csrf_token": privacy_csrf, "resolutionNote": "identidad no validada"},
                ),
                302,
                "plataforma rechaza eliminacion de cliente activo",
            )
            rejected_subject = next(item for item in state["clients"] if item["id"] == "client-reject-delete-sec")
            assert rejected_subject["deletionStatus"] == "rejected", "rechazo plataforma debe actualizar estado privacidad"
            assert rejected_subject["mobileAccessEnabled"] is True, "rechazo de eliminacion debe reactivar acceso movil de cliente activo"
            assert rejected_subject["mobileSessionVersion"] == 3, "rechazo de eliminacion debe revocar tokens previos"
            state["clients"].append(
                {
                    **state["clients"][0],
                    "id": "client-reject-inactive-sec",
                    "businessName": "Cliente Rechazo Inactivo",
                    "email": "rechazo.inactivo@FVENTAS.test",
                    "status": "inactive",
                    "deletionStatus": "requested",
                    "deletionRequestId": "acctdel-reject-inactive-sec",
                    "deletionRequestedAt": utc_now(),
                    "mobileAccessEnabled": False,
                    "mobileAccessBlocked": True,
                    "mobileSessionVersion": 4,
                }
            )
            assert_status(
                privacy_client.post(
                    "/platform/privacy/account-deletion/client/client-reject-inactive-sec/reject",
                    data={"_csrf_token": privacy_csrf, "resolutionNote": "cuenta inactiva"},
                ),
                302,
                "plataforma rechaza eliminacion de cliente inactivo",
            )
            inactive_subject = next(item for item in state["clients"] if item["id"] == "client-reject-inactive-sec")
            assert inactive_subject["deletionStatus"] == "rejected", "rechazo de cuenta inactiva actualiza privacidad"
            assert inactive_subject["mobileAccessEnabled"] is False, "rechazo no debe reactivar cuenta inactiva"
            assert inactive_subject["mobileSessionVersion"] == 5, "rechazo de cuenta inactiva tambien invalida tokens previos"
        state["account_deletion_rate_events"] = []
        app.config["ACCOUNT_DELETION_MAX_EVENTS"] = 1
        with app.test_client() as public_client:
            assert_status(public_client.get("/account-deletion"), 200, "pagina publica de eliminacion")
            public_csrf = csrf_from_session(public_client)
            assert_status(
                public_client.post(
                    "/account-deletion",
                    data={
                        "_csrf_token": public_csrf,
                        "email": "unknown.security@fventas.test",
                        "reason": "prueba rate limit",
                    },
                ),
                200,
                "primera solicitud publica de eliminacion",
            )
            assert_status(
                public_client.post(
                    "/account-deletion",
                    data={
                        "_csrf_token": public_csrf,
                        "email": "unknown.security@fventas.test",
                        "reason": "reintento inmediato",
                    },
                ),
                429,
                "solicitud publica repetida se limita",
            )
    finally:
        app.config["ACCOUNT_DELETION_WINDOW_SECONDS"] = original_account_deletion_window
        app.config["ACCOUNT_DELETION_MAX_EVENTS"] = original_account_deletion_max

    duplicate_email = "duplicado.security@fventas.test"
    state["clients"].append(
        {
            **state["clients"][0],
            "id": "client-dup-sec",
            "businessName": "Cliente Duplicado Seguridad",
            "email": duplicate_email,
            "passwordHash": generate_password_hash("DuplicadoCliente2026"),
        }
    )
    state["admin_users"].append(
        {
            **state["admin_users"][0],
            "id": "seller-dup-sec",
            "name": "Vendedor Duplicado Seguridad",
            "email": duplicate_email,
            "passwordHash": generate_password_hash("DuplicadoSeller2026"),
            "role": "sales",
            "sessionVersion": 0,
        }
    )
    state["account_deletion_rate_events"] = []
    with app.test_client() as public_client:
        assert_status(public_client.get("/account-deletion"), 200, "pagina publica de eliminacion duplicada")
        public_csrf = csrf_from_session(public_client)
        assert_status(
            public_client.post(
                "/account-deletion",
                data={
                    "_csrf_token": public_csrf,
                    "email": duplicate_email,
                    "reason": "correo duplicado requiere revision",
                },
            ),
            200,
            "solicitud publica con identidad ambigua queda para revision manual",
        )
        linked_duplicate_requests = [
            item
            for item in state.get("account_deletion_requests", [])
            if item.get("subjectId") in {"client-dup-sec", "seller-dup-sec"}
        ]
        assert not linked_duplicate_requests, "identidad publica ambigua no debe vincularse a una cuenta arbitraria"
        assert any(
            item.get("subjectType") == "unknown" and item.get("email") == duplicate_email
            for item in state.get("account_deletion_requests", [])
        ), "identidad publica ambigua debe quedar como solicitud manual"
        assert any(
            event.get("action") == "account_deletion_ambiguous_public"
            for event in state["audit_events"]
        ), "identidad publica ambigua debe auditarse como riesgo alto"

    original_recovery_window = app.config.get("MOBILE_PASSWORD_RECOVERY_WINDOW_SECONDS")
    original_recovery_max = app.config.get("MOBILE_PASSWORD_RECOVERY_MAX_EVENTS")
    try:
        app.config["MOBILE_PASSWORD_RECOVERY_WINDOW_SECONDS"] = 300
        app.config["MOBILE_PASSWORD_RECOVERY_MAX_EVENTS"] = 1
        with app.test_client() as recovery_client:
            duplicate_recovery = assert_status(
                recovery_client.post(
                    "/api/v1/mobile/auth/recover-password",
                    json={"email": duplicate_email},
                ),
                200,
                "recuperacion duplicada no enumera identidad",
            ).get_json()
            assert duplicate_recovery["status"] == "received"
            assert any(
                event.get("action") == "password_recovery_blocked"
                for event in state["audit_events"]
            ), "identidad movil duplicada debe auditarse internamente"
            assert_status(
                recovery_client.post(
                    "/api/v1/mobile/auth/recover-password",
                    json={"email": "unknown.recovery@fventas.test"},
                ),
                429,
                "recuperacion repetida queda limitada por IP",
            )
    finally:
        app.config["MOBILE_PASSWORD_RECOVERY_WINDOW_SECONDS"] = original_recovery_window
        app.config["MOBILE_PASSWORD_RECOVERY_MAX_EVENTS"] = original_recovery_max

    state["clients"].append(
        {
            **state["clients"][0],
            "id": "client-recovery-disabled-sec",
            "businessName": "Cliente Recovery Desactivado",
            "email": "recovery.desactivado@FVENTAS.test",
            "passwordHash": generate_password_hash("RecoveryDesactivado2026"),
            "mobileAccessEnabled": False,
            "mobileSessionVersion": 0,
        }
    )
    state["mobile_password_recovery_rate_events"] = []
    original_recovery_window = app.config.get("MOBILE_PASSWORD_RECOVERY_WINDOW_SECONDS")
    original_recovery_max = app.config.get("MOBILE_PASSWORD_RECOVERY_MAX_EVENTS")
    try:
        app.config["MOBILE_PASSWORD_RECOVERY_WINDOW_SECONDS"] = 300
        app.config["MOBILE_PASSWORD_RECOVERY_MAX_EVENTS"] = 2
        with app.test_client() as recovery_client:
            disabled_recovery = assert_status(
                recovery_client.post(
                    "/api/v1/mobile/auth/recover-password",
                    json={"email": "recovery.desactivado@FVENTAS.test"},
                ),
                200,
                "recuperacion de cliente desactivado no enumera cuenta",
            ).get_json()
            assert disabled_recovery["status"] == "received"
            disabled_subject = next(item for item in state["clients"] if item["id"] == "client-recovery-disabled-sec")
            assert not disabled_subject.get("passwordRecoveryStatus"), "cliente sin acceso movil no debe abrir recuperacion interna"
    finally:
        app.config["MOBILE_PASSWORD_RECOVERY_WINDOW_SECONDS"] = original_recovery_window
        app.config["MOBILE_PASSWORD_RECOVERY_MAX_EVENTS"] = original_recovery_max

    state["clients"].append(
        {
            **state["clients"][0],
            "id": "client-orphan-company-sec",
            "businessName": "Cliente Sin Empresa Seguridad",
            "email": "cliente.sin.empresa@FVENTAS.test",
            "passwordHash": generate_password_hash("ClienteSinEmpresa2026"),
            "companyId": "",
            "mobileSessionVersion": 0,
        }
    )
    state["admin_users"].append(
        {
            **state["admin_users"][0],
            "id": "seller-orphan-company-sec",
            "name": "Vendedor Sin Empresa Seguridad",
            "email": "vendedor.sin.empresa@FVENTAS.test",
            "passwordHash": generate_password_hash("VendedorSinEmpresa2026"),
            "role": "sales",
            "companyId": "",
            "sessionVersion": 0,
        }
    )
    state["clients"].append(
        {
            **state["clients"][0],
            "id": "client-mobile-disabled-sec",
            "businessName": "Cliente Movil Desactivado",
            "email": "cliente.movil.desactivado@FVENTAS.test",
            "passwordHash": generate_password_hash("ClienteMovilDesactivado2026"),
            "mobileAccessEnabled": False,
            "mobileSessionVersion": 0,
        }
    )
    with app.test_client() as orphan_client:
        assert_status(
            orphan_client.post(
                "/api/v1/mobile/auth/login",
                headers={"X-FVENTAS-Device-Id": "device-orphan-client"},
                json={
                    "email": "cliente.sin.empresa@FVENTAS.test",
                    "password": "ClienteSinEmpresa2026",
                    "deviceId": "device-orphan-client",
                },
            ),
            403,
            "cliente movil sin companyId explicito bloqueado",
        )
        assert_status(
            orphan_client.post(
                "/api/v1/mobile/auth/login",
                headers={"X-FVENTAS-Device-Id": "device-orphan-seller"},
                json={
                    "email": "vendedor.sin.empresa@FVENTAS.test",
                    "password": "VendedorSinEmpresa2026",
                    "deviceId": "device-orphan-seller",
                },
            ),
            403,
            "vendedor movil sin companyId explicito bloqueado",
        )
        assert_status(
            orphan_client.post(
                "/api/v1/mobile/auth/login",
                headers={"X-FVENTAS-Device-Id": "device-disabled-client"},
                json={
                    "email": "cliente.movil.desactivado@FVENTAS.test",
                    "password": "ClienteMovilDesactivado2026",
                    "deviceId": "device-disabled-client",
                },
            ),
            401,
            "cliente con acceso movil desactivado no puede iniciar sesion",
        )
    assert sum(
        1
        for event in state["audit_events"]
        if event.get("action") == "mobile_login_blocked"
        and "companyId explicito" in event.get("detail", "")
    ) >= 2

    with app.test_client() as client:
        login_page = assert_status(client.get("/login"), 200, "login headers")
        assert login_page.headers.get("X-Content-Type-Options") == "nosniff"
        assert login_page.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert (
            "Content-Security-Policy-Report-Only" in login_page.headers
            or "Content-Security-Policy" in login_page.headers
        )
        public_meta = assert_status(client.get("/api/v1/mobile/meta"), 200, "meta movil publico").get_json()
        assert "counts" not in public_meta, "meta publica no debe exponer conteos de empresa"

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
        state["clients"][0]["status"] = "active"
        state["clients"][0]["mobileAccessEnabled"] = True
        state["clients"][0]["mobileSessionVersion"] = 0
        assert_status(
            client.post(
                "/clients/client-sec/status",
                data={"_csrf_token": csrf, "status": "blocked_debt"},
            ),
            302,
            "bloqueo admin de cliente",
        )
        assert state["clients"][0]["mobileAccessEnabled"] is False, "bloqueo admin debe cortar acceso movil"
        assert state["clients"][0]["mobileSessionVersion"] == 1, "bloqueo admin debe revocar tokens moviles"
        assert_status(
            client.post(
                "/clients/client-sec/status",
                data={"_csrf_token": csrf, "status": "active"},
            ),
            302,
            "reactivacion admin de cliente",
        )
        assert state["clients"][0]["mobileAccessEnabled"] is True, "reactivacion admin debe permitir nuevo login movil"
        assert state["clients"][0]["mobileSessionVersion"] == 1, "reactivacion no debe rehabilitar tokens previos"
        pdf_as_image = (io.BytesIO(b"%PDF-1.4\n%FVENTAS image-slot test"), "banner.pdf")
        assert_status(
            client.post(
                "/announcements",
                data={
                    "_csrf_token": csrf,
                    "title": "PDF en campo imagen",
                    "imageFile": pdf_as_image,
                },
                content_type="multipart/form-data",
            ),
            400,
            "PDF valido no puede subirse como imagen de anuncio",
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

        state["categories"].append(
            {
                "id": "cat-orphan-mobile",
                "name": "Categoria Huerfana Movil",
                "slug": "categoria-huerfana-movil",
                "status": "active",
                "visibleInApp": True,
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )
        state["products"].append(
            {
                **state["products"][0],
                "id": "prod-orphan-mobile",
                "companyId": "",
                "sku": "FVT-ORPHAN-MOBILE",
                "title": "Producto Huerfano Movil",
                "categoryId": "cat-orphan-mobile",
                "categoryName": "Categoria Huerfana Movil",
                "stock": 20,
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )
        state["orders"].append(
            {
                "id": "order-orphan-mobile",
                "orderId": "order-orphan-mobile",
                "customerId": "client-sec",
                "customer": {"id": "client-sec", "name": "Cliente Seguridad"},
                "sellerId": "",
                "sellerName": "",
                "items": [{"productId": "prod-orphan-mobile", "quantity": 1, "unitPriceUsd": 999}],
                "totalUsd": 999,
                "netUsd": 999,
                "paidUsd": 0,
                "balanceUsd": 999,
                "saleType": "credit_line",
                "paymentTermDays": 30,
                "status": "pending",
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )
        state["credit_movements"].append(
            {
                "id": "movement-orphan-mobile",
                "clientId": "client-sec",
                "orderId": "order-orphan-mobile",
                "type": "charge",
                "amountUsd": 999,
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )
        state["announcements"].append(
            {
                "id": "ann-orphan-mobile",
                "title": "Anuncio Huerfano Movil",
                "body": "No debe aparecer en la app movil autenticada.",
                "placement": "home",
                "priority": 999,
                "status": "active",
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )

        original_require_mobile_token = app.config.get("REQUIRE_MOBILE_TOKEN", True)
        try:
            app.config["REQUIRE_MOBILE_TOKEN"] = False
            assert_status(
                client.get("/api/v1/mobile/orders?customerId=client-sec"),
                401,
                "ordenes privadas no aceptan customerId sin token aunque el catalogo sea publico",
            )
            assert_status(
                client.post(
                    "/api/v1/mobile/orders",
                    json={
                        "customerId": "client-sec",
                        "items": [{"productId": "prod-sec", "quantity": 1}],
                    },
                ),
                401,
                "crear orden movil exige token de cliente",
            )
        finally:
            app.config["REQUIRE_MOBILE_TOKEN"] = original_require_mobile_token

        assert_status(
            client.post(
                "/api/v1/mobile/auth/login",
                json={"email": "cliente.security@FVENTAS.test", "password": "ClienteSecurity2026"},
            ),
            400,
            "login movil exige identificador de dispositivo",
        )
        payload_device_login = assert_status(
            client.post(
                "/api/v1/mobile/auth/login",
                json={
                    "email": "cliente.security@FVENTAS.test",
                    "password": "ClienteSecurity2026",
                    "deviceId": "device-security-json",
                },
            ),
            200,
            "login movil acepta deviceId JSON y lo firma",
        ).get_json()
        payload_device_token = FVENTAS_app.mobile_token_serializer().loads(payload_device_login["accessToken"])
        assert payload_device_token["deviceId"] == "device-security-json"
        assert_status(
            client.get(
                "/api/v1/mobile/meta",
                headers={
                    "Authorization": f"Bearer {payload_device_login['accessToken']}",
                    "X-FVENTAS-Device-Id": "device-security-json",
                },
            ),
            200,
            "token firmado con deviceId JSON funciona al enviar header correspondiente",
        )
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
        scoped_meta = assert_status(
            client.get(
                "/api/v1/mobile/meta",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
            ),
            200,
            "meta movil autenticada",
        ).get_json()
        assert scoped_meta["counts"]["products"] == 1, "meta autenticada debe quedar acotada a la empresa"
        assert scoped_meta["counts"]["announcements"] == 1, "meta autenticada no debe contar anuncios sin companyId"
        assert scoped_meta["market"]["localCurrency"] == "CLP", "meta autenticada debe usar moneda local de la empresa"
        assert scoped_meta["purchaseConditions"]["scopeLabel"] == "Solo datos de tu empresa"
        mobile_home = assert_status(
            client.get(
                "/api/v1/mobile/home",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
            ),
            200,
            "token vigente puede leer home",
        ).get_json()
        assert all(item.get("id") != "ann-orphan-mobile" for item in mobile_home["home"]["banners"]), "home movil no debe exponer anuncios sin companyId"
        mobile_products = assert_status(
            client.get(
                "/api/v1/mobile/products",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
            ),
            200,
            "token vigente puede leer catalogo",
        ).get_json()
        assert all(item.get("id") != "prod-orphan-mobile" for item in mobile_products.get("items", [])), "catalogo movil no debe exponer productos sin companyId"
        mobile_orders = assert_status(
            client.get(
                "/api/v1/mobile/orders",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
            ),
            200,
            "token vigente puede leer ordenes",
        ).get_json()
        assert all(item.get("id") != "order-orphan-mobile" for item in mobile_orders.get("items", [])), "ordenes moviles no deben exponer registros sin companyId"
        mobile_credit = assert_status(
            client.get(
                "/api/v1/mobile/credit",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
            ),
            200,
            "token vigente puede leer credito",
        ).get_json()
        assert mobile_credit["credit"]["openBalanceUsd"] == 0, "credito movil no debe sumar ordenes sin companyId"
        other_company_id = "company-other-security"
        state["companies"].append(
            {
                "id": other_company_id,
                "name": "Empresa Seguridad Ajena",
                "country": "CL",
                "status": "active",
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )
        state.setdefault("notifications", []).insert(
            0,
            {
                "id": "notif-duplicate-mobile-sec",
                "companyId": other_company_id,
                "title": "Notificacion ajena duplicada",
                "body": "No debe marcarse desde el token FVENTAS.",
                "recipientType": "client",
                "recipientId": "client-sec",
                "status": "unread",
                "channel": "mobile",
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            },
        )
        state["notifications"].append(
            {
                "id": "notif-duplicate-mobile-sec",
                "companyId": DEFAULT_COMPANY_ID,
                "title": "Notificacion propia duplicada",
                "body": "Debe marcarse solo dentro de la empresa del token.",
                "recipientType": "client",
                "recipientId": "client-sec",
                "status": "unread",
                "channel": "mobile",
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
        )
        assert_status(
            client.post(
                "/api/v1/mobile/notifications/notif-duplicate-mobile-sec/read",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
            ),
            200,
            "lectura de notificacion movil se acota por empresa",
        )
        own_notification = next(
            item
            for item in state["notifications"]
            if item.get("id") == "notif-duplicate-mobile-sec" and item.get("companyId") == DEFAULT_COMPANY_ID
        )
        foreign_notification = next(
            item
            for item in state["notifications"]
            if item.get("id") == "notif-duplicate-mobile-sec" and item.get("companyId") == other_company_id
        )
        assert own_notification["status"] == "read", "notificacion propia duplicada debe quedar leida"
        assert foreign_notification["status"] == "unread", "notificacion ajena duplicada no debe mutarse"

        own_client_for_commission = next(
            item
            for item in state["clients"]
            if item.get("id") == "client-sec" and item.get("companyId") == DEFAULT_COMPANY_ID
        )
        own_client_for_commission["assignedSellerId"] = "seller-sec"
        own_client_for_commission["assignedSellerName"] = ""
        own_seller_for_commission = next(
            item
            for item in state["admin_users"]
            if item.get("id") == "seller-sec" and item.get("companyId") == DEFAULT_COMPANY_ID
        )
        own_seller_for_commission["commissionRatePercent"] = 10
        duplicated_foreign_seller = copy.deepcopy(own_seller_for_commission)
        duplicated_foreign_seller.update(
            {
                "companyId": other_company_id,
                "name": "Vendedor Duplicado Ajeno",
                "email": "seller.duplicado.ajeno@fventas.test",
                "commissionRatePercent": 80,
                "updatedAt": utc_now(),
            }
        )
        state["admin_users"].insert(0, duplicated_foreign_seller)
        duplicated_foreign_client = copy.deepcopy(state["clients"][0])
        duplicated_foreign_client.update(
            {
                "companyId": other_company_id,
                "businessName": "Cliente Duplicado Ajeno",
                "email": "cliente.duplicado.ajeno@fventas.test",
                "updatedAt": utc_now(),
            }
        )
        state["clients"].insert(0, duplicated_foreign_client)
        duplicate_id_order = assert_status(
            client.post(
                "/api/v1/mobile/orders",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
                json={
                    "saleType": "cash",
                    "paymentTermDays": 0,
                    "items": [{"productId": "prod-sec", "sku": "FVT-SEC-01", "quantity": 1}],
                    "deviceId": "device-security",
                },
            ),
            201,
            "orden movil usa cliente de la empresa del token aunque exista id duplicado",
        ).get_json()
        persisted_duplicate_id_order = next(
            item for item in state["orders"] if item.get("orderId") == duplicate_id_order["orderId"]
        )
        assert persisted_duplicate_id_order["companyId"] == DEFAULT_COMPANY_ID
        assert persisted_duplicate_id_order["customer"]["name"] == "Cliente Seguridad"
        assert persisted_duplicate_id_order["sellerName"] == "Vendedor Seguridad"
        assert abs(float(persisted_duplicate_id_order["commissionUsd"]) - 0.9) < 0.001
        state["clients"] = [
            item
            for item in state["clients"]
            if not (item.get("id") == "client-sec" and item.get("companyId") == other_company_id)
        ]
        state["admin_users"] = [
            item
            for item in state["admin_users"]
            if not (item.get("id") == "seller-sec" and item.get("companyId") == other_company_id)
        ]
        state["clients"][0]["mobileAccessEnabled"] = False
        assert_status(
            client.get(
                "/api/v1/mobile/products",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
            ),
            401,
            "token vigente de cliente queda bloqueado al desactivar acceso movil",
        )
        assert_status(
            client.get(
                "/api/v1/mobile/profile",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
            ),
            401,
            "perfil movil respeta acceso movil desactivado",
        )
        assert_status(
            client.post(
                "/api/v1/mobile/auth/refresh",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
            ),
            401,
            "refresh movil respeta acceso movil desactivado",
        )
        state["clients"][0]["mobileAccessEnabled"] = True

        original_mobile_write_window = app.config.get("MOBILE_WRITE_WINDOW_SECONDS")
        original_mobile_write_max = app.config.get("MOBILE_WRITE_MAX_EVENTS")
        try:
            app.config["MOBILE_WRITE_WINDOW_SECONDS"] = 300
            app.config["MOBILE_WRITE_MAX_EVENTS"] = 1
            state["mobile_write_rate_events"] = []
            assert_status(
                client.post(
                    "/api/v1/mobile/orders",
                    headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
                    json={"items": [], "deviceId": "device-security"},
                ),
                400,
                "primer intento de orden movil llega al validador comercial",
            )
            assert_status(
                client.post(
                    "/api/v1/mobile/orders",
                    headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
                    json={"items": [], "deviceId": "device-security"},
                ),
                429,
                "orden movil repetida queda limitada",
            )
            assert_status(
                client.post(
                    "/api/v1/mobile/auth/change-password",
                    headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
                    json={
                        "currentPassword": "ClaveIncorrecta2026",
                        "newPassword": "ClienteSecurityNueva2026",
                        "deviceId": "device-security",
                    },
                ),
                400,
                "primer intento de cambio de clave llega al validador de clave actual",
            )
            assert_status(
                client.post(
                    "/api/v1/mobile/auth/change-password",
                    headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
                    json={
                        "currentPassword": "ClaveIncorrecta2026",
                        "newPassword": "ClienteSecurityNueva2026",
                        "deviceId": "device-security",
                    },
                ),
                429,
                "cambio de clave movil repetido queda limitado",
            )
            seller_login = assert_status(
                client.post(
                    "/api/v1/mobile/auth/login",
                    headers={"X-FVENTAS-Device-Id": "device-seller-security"},
                    json={
                        "email": "seller.security@FVENTAS.test",
                        "password": "SellerSecurity2026",
                        "deviceId": "device-seller-security",
                    },
                ),
                200,
                "login vendedor movil para rate limit",
            ).get_json()
            seller_token = seller_login["accessToken"]
            assert_status(
                client.post(
                    "/api/v1/mobile/seller/clients",
                    headers={"Authorization": f"Bearer {seller_token}", "X-FVENTAS-Device-Id": "device-seller-security"},
                    json={"deviceId": "device-seller-security"},
                ),
                400,
                "primer intento de cliente vendedor llega al validador comercial",
            )
            assert_status(
                client.post(
                    "/api/v1/mobile/seller/clients",
                    headers={"Authorization": f"Bearer {seller_token}", "X-FVENTAS-Device-Id": "device-seller-security"},
                    json={"deviceId": "device-seller-security"},
                ),
                429,
                "cliente vendedor repetido queda limitado",
            )
            assert any(
                event.get("action") == "mobile_write_limited"
                and event.get("companyId") == DEFAULT_COMPANY_ID
                for event in state["audit_events"]
            ), "limites de escritura movil deben auditarse por empresa"
        finally:
            app.config["MOBILE_WRITE_WINDOW_SECONDS"] = original_mobile_write_window
            app.config["MOBILE_WRITE_MAX_EVENTS"] = original_mobile_write_max

        assert_status(
            client.get(
                "/api/v1/mobile/products",
                headers={"Authorization": f"Bearer {token}"},
            ),
            401,
            "token movil sin dispositivo se rechaza",
        )
        assert_status(
            client.get(
                "/api/v1/mobile/products",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-ajeno"},
            ),
            401,
            "token movil con dispositivo ajeno se rechaza",
        )
        assert_status(
            client.post(
                "/api/v1/mobile/auth/logout",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
            ),
            200,
            "logout movil revoca sesion",
        )
        assert state["clients"][0]["mobileSessionVersion"] == 2, "logout movil debe invalidar tokens vigentes"
        assert_status(
            client.get(
                "/api/v1/mobile/products",
                headers={"Authorization": f"Bearer {token}", "X-FVENTAS-Device-Id": "device-security"},
            ),
            401,
            "token movil viejo invalidado por logout",
        )

    print("FVENTAS Insights smoke seguridad")
    print("------------------------")
    print("OK headers de seguridad y cache sensible")
    print("OK sesiones activas con dispositivo")
    print("OK permisos backend por endpoint")
    print("OK validacion de firma de archivos")
    print("OK URLs firmadas para documentos privados")
    print("OK sanitizacion avanzada de inputs y URLs")
    print("OK IP confiable solo desde proxy configurado")
    print("OK exportaciones CSV/XLSX neutralizan formulas")
    print("OK documentos internos no quedan publicados por uploads directos")
    print("OK API movil legacy puede deshabilitarse para produccion")
    print("OK logout movil revoca tokens vigentes")
    print("OK eliminacion publica de cuenta no bloquea acceso sin verificacion")
    print("OK eliminacion publica de cuenta limita solicitudes repetidas")
    print("OK eliminacion publica con identidad ambigua queda en revision manual")
    print("OK rechazo plataforma de eliminacion reabre solo clientes activos")
    print("OK registro publico valida empresa y limita solicitudes repetidas")
    print("OK recuperacion movil no enumera duplicados y limita abuso")
    print("OK recuperacion movil no abre flujo interno para cuentas sin acceso movil")
    print("OK escrituras moviles autenticadas limitan abuso por empresa, usuario y dispositivo")
    print("OK cuentas moviles sin empresa explicita quedan bloqueadas")
    print("OK clientes con acceso movil desactivado no pueden usar tokens vigentes")
    print("OK bloqueo admin de cliente revoca acceso movil sin reabrir tokens viejos")
    print("OK redirecciones internas bloquean destinos externos")
    print("OK tokens moviles versionados y atados a dispositivo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
