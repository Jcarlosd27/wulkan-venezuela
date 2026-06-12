from __future__ import annotations

import copy
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app as wulkan_app
from store import normalize_store, utc_now
from werkzeug.security import generate_password_hash


ADMIN_ID = "admin-actions"
CSRF = "csrf-actions"

PAGES = [
    "/",
    "/sellers",
    "/clients",
    "/credit",
    "/credit/vencimientos",
    "/credit/historial",
    "/orders",
    "/orders/new",
    "/commissions",
    "/crm",
    "/quotes",
    "/quotes/new",
    "/collections",
    "/dispatch",
    "/reports",
    "/products",
    "/products/new",
    "/categories",
    "/media-library",
    "/documents",
    "/stock",
    "/announcements",
    "/service-technicians",
    "/notifications",
    "/business-rules",
    "/maintenance",
    "/plantillas",
    "/audit",
    "/settings",
    "/permissions",
    "/admin-users",
    "/account/password",
    "/reports/print",
]


class FormParser(HTMLParser):
    def __init__(self, current_path: str):
        super().__init__()
        self.current_path = current_path
        self.forms: list[dict] = []
        self._form: dict | None = None
        self._select: dict | None = None
        self._textarea_name = ""
        self._textarea_value: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        if tag == "form":
            self._form = {
                "method": attr.get("method", "get").lower(),
                "action": attr.get("action") or self.current_path,
                "enctype": attr.get("enctype", ""),
                "fields": {},
                "file_fields": [],
            }
            return

        if self._form is None:
            return

        if tag == "input":
            name = attr.get("name", "")
            if not name:
                return
            input_type = attr.get("type", "text").lower()
            if input_type in {"submit", "button", "image", "reset"}:
                return
            if input_type == "file":
                self._form["file_fields"].append(name)
                return
            if input_type in {"checkbox", "radio"} and "checked" not in attr:
                return
            self._form["fields"][name] = attr.get("value", "")
            return

        if tag == "select":
            name = attr.get("name", "")
            if name:
                self._select = {"name": name, "first": None, "selected": None}
            return

        if tag == "option" and self._select is not None:
            value = attr.get("value", "")
            if self._select["first"] is None:
                self._select["first"] = value
            if "selected" in attr:
                self._select["selected"] = value
            return

        if tag == "textarea":
            self._textarea_name = attr.get("name", "")
            self._textarea_value = []

    def handle_data(self, data: str) -> None:
        if self._form is not None and self._textarea_name:
            self._textarea_value.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "select" and self._form is not None and self._select is not None:
            value = self._select["selected"]
            if value is None:
                value = self._select["first"] or ""
            self._form["fields"][self._select["name"]] = value
            self._select = None
            return

        if tag == "textarea" and self._form is not None and self._textarea_name:
            self._form["fields"][self._textarea_name] = "".join(self._textarea_value)
            self._textarea_name = ""
            self._textarea_value = []
            return

        if tag == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None


class ModalTargetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.targets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        if attr.get("id"):
            self.ids.add(attr["id"])
        target = attr.get("data-bs-target", "")
        if target.startswith("#"):
            self.targets.append(target[1:])


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr = {key: value or "" for key, value in attrs}
        href = attr.get("href", "").strip()
        if href:
            self.hrefs.append(href)


def base_store() -> dict:
    now = utc_now()
    store = {
        "admin_users": [
            {
                "id": ADMIN_ID,
                "name": "Admin Acciones",
                "email": "admin.actions@wulkan.test",
                "passwordHash": generate_password_hash("AdminActions2026"),
                "role": "super_admin",
                "status": "active",
                "sessionVersion": 0,
                "mustChangePassword": False,
                "activeSessions": [],
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "seller-actions",
                "name": "Vendedor Acciones",
                "email": "seller.actions@wulkan.test",
                "passwordHash": generate_password_hash("SellerActions2026"),
                "role": "sales",
                "status": "active",
                "sellerCode": "VEN-ACT",
                "sellerZone": "Centro",
                "commissionRatePercent": 5,
                "salesGoalUsd": 2000,
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "manager-actions",
                "name": "Gerente Acciones",
                "email": "manager.actions@wulkan.test",
                "passwordHash": generate_password_hash("ManagerActions2026"),
                "role": "commercial_manager",
                "status": "active",
                "sessionVersion": 0,
                "mustChangePassword": False,
                "createdAt": now,
                "updatedAt": now,
            },
        ],
        "categories": [
            {
                "id": "cat-actions-root",
                "name": "Jardin y Bosque",
                "slug": "jardin-bosque",
                "description": "Categoria temporal para smoke.",
                "imageUrl": "https://example.com/cat.jpg",
                "icon": "bi-tree",
                "sortOrder": 1,
                "parentId": "",
                "status": "active",
                "visibleInApp": True,
                "createdAt": now,
                "updatedAt": now,
            },
            {
                "id": "cat-actions-child",
                "name": "Motosierras",
                "slug": "motosierras",
                "description": "Subcategoria temporal para smoke.",
                "imageUrl": "",
                "icon": "bi-tools",
                "sortOrder": 2,
                "parentId": "cat-actions-root",
                "status": "active",
                "visibleInApp": True,
                "createdAt": now,
                "updatedAt": now,
            },
        ],
        "products": [
            {
                "id": "prod-actions",
                "sku": "WUL-ACT-45CC",
                "title": "Motosierra Acciones 45cc",
                "description": "Producto temporal para probar botones.",
                "productType": "machine",
                "categoryId": "cat-actions-child",
                "categoryName": "Motosierras",
                "publicPriceUsd": 185,
                "originalPriceUsd": 210,
                "discountPercent": 12,
                "b2bPriceUsd": 162,
                "exchangeRateUsdVes": 38.5,
                "stock": 12,
                "reserved": 1,
                "status": "active",
                "visibleInApp": True,
                "imageUrl": "https://example.com/product.jpg",
                "imageUrls": ["https://example.com/product.jpg", "https://example.com/product-2.jpg"],
                "pdfUrls": ["https://example.com/product.pdf"],
                "variants": ["18 pulgadas"],
                "specifications": {"Motor": "45cc"},
                "requiresQuote": False,
                "requiresTechnicalValidation": False,
                "rotationLast30Days": 4,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "clients": [
            {
                "id": "client-actions",
                "businessName": "Ferreteria Acciones",
                "contactName": "Comprador Acciones",
                "email": "client.actions@wulkan.test",
                "passwordHash": generate_password_hash("ClientActions2026"),
                "status": "active",
                "clientType": "ferretero",
                "taxId": "J-22222222-2",
                "phone": "+580000000001",
                "address": "Av. Acciones",
                "city": "Valencia",
                "state": "Carabobo",
                "assignedSellerId": "seller-actions",
                "assignedSellerName": "Vendedor Acciones",
                "assignedSellerZone": "Centro",
                "creditEnabled": True,
                "creditLimitUsd": 500,
                "creditUsedUsd": 100,
                "creditRequestStatus": "approved",
                "paymentTermsDays": 15,
                "allowedPaymentTermsDays": [0, 15, 30],
                "defaultSaleType": "credit_line",
                "collectionStatus": "without_debt",
                "creditRiskLevel": "low",
                "mobileSessionVersion": 0,
                "mustChangePassword": False,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "orders": [
            {
                "id": "order-actions",
                "orderId": "order-actions",
                "customerId": "client-actions",
                "customer": {
                    "id": "client-actions",
                    "name": "Ferreteria Acciones",
                    "email": "client.actions@wulkan.test",
                },
                "sellerId": "seller-actions",
                "sellerName": "Vendedor Acciones",
                "items": [
                    {
                        "productId": "prod-actions",
                        "sku": "WUL-ACT-45CC",
                        "title": "Motosierra Acciones 45cc",
                        "quantity": 1,
                        "unitPriceUsd": 162,
                        "subtotalUsd": 162,
                    }
                ],
                "totalUsd": 162,
                "netUsd": 162,
                "paidUsd": 50,
                "balanceUsd": 112,
                "saleType": "credit_line",
                "paymentTermDays": 15,
                "status": "pending",
                "creditStatus": "approved",
                "inventoryStatus": "reserved",
                "dispatchStatus": "pending",
                "commissionUsd": 8.1,
                "commissionStatus": "commission_pending",
                "commissionRatePercent": 5,
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "quotes": [
            {
                "id": "quote-actions",
                "quoteId": "quote-actions",
                "customerId": "client-actions",
                "customerName": "Ferreteria Acciones",
                "sellerId": "seller-actions",
                "sellerName": "Vendedor Acciones",
                "items": [{"productId": "prod-actions", "quantity": 1, "unitPriceUsd": 162}],
                "totalUsd": 162,
                "status": "draft",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "crm_records": [
            {
                "id": "crm-actions",
                "clientId": "client-actions",
                "clientName": "Ferreteria Acciones",
                "sellerId": "seller-actions",
                "sellerName": "Vendedor Acciones",
                "status": "open",
                "stage": "prospect",
                "priority": "medium",
                "nextActionAt": "2026-06-20",
                "lastActivityAt": now,
                "notes": "Registro temporal.",
                "activities": [],
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "announcements": [
            {
                "id": "ann-actions",
                "title": "Banner Acciones",
                "body": "Anuncio temporal para smoke.",
                "placement": "home",
                "priority": 50,
                "ctaLabel": "Ver catalogo",
                "ctaUrl": "wulkan://catalog",
                "imageUrl": "https://example.com/banner.jpg",
                "startsAt": now,
                "endsAt": "",
                "status": "active",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "media_assets": [
            {
                "id": "media-actions",
                "title": "Ficha tecnica acciones",
                "assetType": "pdf",
                "type": "document",
                "documentType": "technical_sheet",
                "subjectType": "product",
                "subjectId": "prod-actions",
                "subjectLabel": "Motosierra Acciones 45cc",
                "productId": "prod-actions",
                "resourceType": "technical_pdf",
                "url": "https://example.com/ficha.pdf",
                "visibility": "public",
                "status": "active",
                "createdByName": "Admin Acciones",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "service_technicians": [
            {
                "id": "svc-actions",
                "name": "Servicio Acciones",
                "companyName": "Servicio Acciones",
                "contactName": "Tecnico Acciones",
                "phone": "+580000000002",
                "whatsapp": "+580000000002",
                "email": "service.actions@wulkan.test",
                "state": "Carabobo",
                "city": "Valencia",
                "address": "Zona industrial",
                "specialties": ["Motosierras"],
                "coverage": "Centro",
                "status": "active",
                "visibleInApp": True,
                "notes": "",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "credit_movements": [
            {
                "id": "cred-actions",
                "clientId": "client-actions",
                "orderId": "order-actions",
                "type": "payment",
                "method": "cash",
                "reference": "REC-ACC",
                "amountUsd": 50,
                "createdByName": "Admin Acciones",
                "createdAt": now,
                "updatedAt": now,
            }
        ],
        "stock_movements": [
            {
                "id": "stock-actions",
                "productId": "prod-actions",
                "sku": "WUL-ACT-45CC",
                "type": "reserved",
                "quantity": 1,
                "note": "Orden order-actions",
                "createdBy": "Admin Acciones",
                "createdAt": now,
            }
        ],
        "notifications": [
            {
                "id": "notif-actions",
                "type": "order_created",
                "title": "Orden creada",
                "body": "Notificacion temporal.",
                "targetRole": "super_admin",
                "status": "unread",
                "createdAt": now,
            }
        ],
        "audit_events": [],
        "business_settings": {
            "companyName": "Wulkan Venezuela",
            "exchangeRateUsdVes": 38.5,
            "defaultPaymentTermsDays": [0, 10, 15, 20, 30, 40],
            "defaultCommissionPercent": 5,
        },
    }
    normalize_store(store)
    return store


def install_state(state_holder: dict) -> None:
    def load_store_override() -> dict:
        return state_holder["state"]

    def save_store_override(store: dict) -> None:
        if store is state_holder["state"]:
            return
        snapshot = copy.deepcopy(store)
        state_holder["state"].clear()
        state_holder["state"].update(snapshot)

    wulkan_app.load_store = load_store_override
    wulkan_app.save_store = save_store_override
    wulkan_app.app.config.update(
        TESTING=True,
        SECRET_KEY="admin-actions-smoke-secret",
        WTF_CSRF_ENABLED=False,
        REQUIRE_MOBILE_TOKEN=True,
        STORAGE_BACKEND="local",
    )


def authenticate(client) -> None:
    with client.session_transaction() as session:
        session["admin_authenticated"] = True
        session["admin_user_id"] = ADMIN_ID
        session["admin_name"] = "Admin Acciones"
        session["admin_role"] = "super_admin"
        session["admin_session_version"] = 0
        session["_csrf_token"] = CSRF


def html_forms(html: str, page: str) -> list[dict]:
    parser = FormParser(page)
    parser.feed(html)
    return [form for form in parser.forms if form["method"] == "post"]


def modal_target_errors(html: str) -> list[str]:
    parser = ModalTargetParser()
    parser.feed(html)
    return [target for target in parser.targets if target not in parser.ids]


def html_links(html: str) -> list[str]:
    parser = LinkParser()
    parser.feed(html)
    return parser.hrefs


def is_internal_path(action: str) -> bool:
    parsed = urlparse(action)
    return not parsed.netloc


def is_safe_internal_link(href: str) -> bool:
    if not href or href.startswith("#"):
        return False
    lowered = href.lower()
    if lowered.startswith(("javascript:", "mailto:", "tel:", "wulkan:")):
        return False
    parsed = urlparse(href)
    if parsed.netloc:
        return False
    if parsed.path in {"/logout"}:
        return False
    if parsed.path.startswith("/api/"):
        return False
    return True


def normalize_action(action: str, page: str) -> str:
    parsed_page = urlparse(page)
    base_path = parsed_page.path or "/"
    return urljoin(base_path if base_path.endswith("/") else f"{base_path}/", action)


def describe_form(page: str, form: dict) -> str:
    return f"{page} -> {form['action']}"


def safe_status_code(response) -> bool:
    return response.status_code < 500


def assert_category_delete_preserves_children(app, state_holder: dict, failures: list[str]) -> None:
    state_holder["state"] = base_store()
    with app.test_client() as client:
        authenticate(client)
        response = client.post(
            "/categories/cat-actions-root/delete",
            data={"_csrf_token": CSRF},
            follow_redirects=False,
        )
        if not safe_status_code(response):
            failures.append(f"POST /categories/cat-actions-root/delete: HTTP {response.status_code}")
            return

    categories = state_holder["state"].get("categories", [])
    root = next((item for item in categories if item.get("id") == "cat-actions-root"), None)
    child = next((item for item in categories if item.get("id") == "cat-actions-child"), None)
    if root is not None:
        failures.append("La categoria padre eliminada sigue visible en el store.")
    if child is None:
        failures.append("Eliminar una categoria padre borro indebidamente su subcategoria.")
    elif child.get("parentId"):
        failures.append("La subcategoria conservada no fue promovida a categoria raiz.")


def assert_product_seed_creates_mobile_catalog(app, state_holder: dict, failures: list[str]) -> None:
    state_holder["state"] = base_store()
    starter_skus = {item["sku"] for item in wulkan_app.WULKAN_STARTER_PRODUCTS}
    with app.test_client() as client:
        authenticate(client)
        response = client.post(
            "/products/starter-wulkan",
            data={"_csrf_token": CSRF},
            follow_redirects=False,
        )
        if not safe_status_code(response):
            failures.append(f"POST /products/starter-wulkan: HTTP {response.status_code}")
            return

    products = state_holder["state"].get("products", [])
    seeded = [product for product in products if product.get("sku") in starter_skus]
    seeded_skus = {product.get("sku") for product in seeded}
    missing = sorted(starter_skus - seeded_skus)
    if missing:
        failures.append(f"Productos base Wulkan no creados: {', '.join(missing[:5])}")
    if len(seeded) != len(seeded_skus):
        failures.append("Productos base Wulkan quedaron duplicados por SKU.")
    if any(product.get("status") != "active" or not product.get("visibleInApp") for product in seeded):
        failures.append("Productos base Wulkan no quedaron publicados para la app movil.")
    if any(not product.get("imageUrl") for product in seeded):
        failures.append("Productos base Wulkan quedaron sin imagen principal.")

    mobile_skus = {product.get("sku") for product in wulkan_app.mobile_visible_products(state_holder["state"])}
    if not starter_skus.issubset(mobile_skus):
        failures.append("La API movil no expone todos los productos base Wulkan visibles.")

    product_count = len(products)
    with app.test_client() as client:
        authenticate(client)
        response = client.post(
            "/products/starter-wulkan",
            data={"_csrf_token": CSRF},
            follow_redirects=False,
        )
        if not safe_status_code(response):
            failures.append(f"POST /products/starter-wulkan segunda ejecucion: HTTP {response.status_code}")
            return
    if len(state_holder["state"].get("products", [])) != product_count:
        failures.append("Productos base Wulkan se duplicaron al ejecutar el seed por segunda vez.")


def main() -> int:
    failures: list[str] = []
    collected_forms: list[tuple[str, dict]] = []
    collected_links: list[tuple[str, str]] = []
    state_holder = {"state": base_store()}
    install_state(state_holder)

    app = wulkan_app.app
    with app.test_client() as client:
        authenticate(client)
        for page in PAGES:
            response = client.get(page)
            if not safe_status_code(response):
                failures.append(f"GET {page}: HTTP {response.status_code}")
                continue
            html = response.get_data(as_text=True)
            for target in modal_target_errors(html):
                failures.append(f"Modal sin destino en {page}: #{target}")
            for form in html_forms(html, page):
                if is_internal_path(form["action"]):
                    collected_forms.append((page, form))
            for href in html_links(html):
                if is_safe_internal_link(href):
                    collected_links.append((page, href))

    seen: set[str] = set()
    for index, (page, form) in enumerate(collected_forms, start=1):
        action = normalize_action(form["action"], page)
        key = f"{page}|{action}|{sorted(form['fields'])}"
        if key in seen:
            continue
        seen.add(key)

        state_holder["state"] = base_store()
        with app.test_client() as client:
            authenticate(client)
            data = dict(form["fields"])
            data["_csrf_token"] = CSRF
            try:
                response = client.post(
                    action,
                    data=data,
                    content_type="multipart/form-data" if form["enctype"] == "multipart/form-data" else None,
                    follow_redirects=False,
                )
            except Exception as exc:  # pragma: no cover - smoke output matters more than traceback noise
                failures.append(f"POST {describe_form(page, form)}: exception {exc!r}")
                continue
            if not safe_status_code(response):
                body = re.sub(r"\s+", " ", response.get_data(as_text=True))[:220]
                failures.append(
                    f"POST {describe_form(page, form)}: HTTP {response.status_code} {body}"
                )

    assert_category_delete_preserves_children(app, state_holder, failures)
    assert_product_seed_creates_mobile_catalog(app, state_holder, failures)

    seen_links: set[str] = set()
    for page, href in collected_links:
        link = normalize_action(href, page)
        if link in seen_links:
            continue
        seen_links.add(link)
        state_holder["state"] = base_store()
        with app.test_client() as client:
            authenticate(client)
            try:
                response = client.get(link, follow_redirects=False)
            except Exception as exc:  # pragma: no cover - smoke output matters more than traceback noise
                failures.append(f"GET link {page} -> {href}: exception {exc!r}")
                continue
            if not safe_status_code(response):
                body = re.sub(r"\s+", " ", response.get_data(as_text=True))[:220]
                failures.append(f"GET link {page} -> {href}: HTTP {response.status_code} {body}")

    print("Graphify admin action smoke")
    print("---------------------------")
    print(f"Paginas revisadas: {len(PAGES)}")
    print(f"Formularios POST probados: {len(seen)}")
    print(f"Enlaces internos probados: {len(seen_links)}")
    if failures:
        print("FALLAS")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("OK: no hay botones/formularios del admin respondiendo con 500.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
