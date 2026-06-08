from __future__ import annotations

import hmac
import secrets
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import get_config
from graphify import rotation_chart, stock_health
from store import load_store, next_id, save_store, utc_now
from uix import badge_class, money_usd, usd_to_ves


app = Flask(__name__)
app.config.from_object(get_config())
app.jinja_env.filters["badge_class"] = badge_class
app.jinja_env.filters["money_usd"] = money_usd

ORDER_STATUS_OPTIONS = [
    ("credit_review", "En revision"),
    ("approved_with_credit", "Aprobada con credito"),
    ("preparing", "Preparando"),
    ("delivered", "Entregada"),
    ("partial_paid", "Pagada parcialmente"),
    ("paid", "Pagada"),
    ("cancelled", "Cancelada"),
]
ORDER_CREDIT_RESERVING_STATUSES = {"approved_with_credit", "preparing", "delivered", "partial_paid"}
ORDER_STOCK_RESERVING_STATUSES = {"approved_with_credit", "preparing", "partial_paid", "paid"}
PAYMENT_METHOD_OPTIONS = [
    ("cash", "Efectivo"),
    ("transfer", "Transferencia"),
    ("mobile_payment", "Pago movil"),
    ("other", "Otro"),
]
ALL_ADMIN_ROLES = {"super_admin", "operator", "sales", "inventory", "readonly"}
WRITE_ROLES = {"super_admin", "operator"}
SALES_ROLES = {"super_admin", "operator", "sales"}
INVENTORY_ROLES = {"super_admin", "operator", "inventory"}
ADMIN_ONLY_ROLES = {"super_admin"}
MODULE_ACCESS = {
    "admin_users": ADMIN_ONLY_ROLES,
    "audit": ADMIN_ONLY_ROLES,
    "clients": {"super_admin", "operator", "sales", "readonly"},
    "credit": {"super_admin", "operator", "sales"},
    "orders": {"super_admin", "operator", "sales", "readonly"},
    "products": ALL_ADMIN_ROLES,
    "media_library": ALL_ADMIN_ROLES,
    "categories": ALL_ADMIN_ROLES,
    "stock": ALL_ADMIN_ROLES,
    "announcements": ALL_ADMIN_ROLES,
}


def csrf_token() -> str:
    token = session.get("_csrf_token", "")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def csrf_field() -> Markup:
    return Markup(f'<input type="hidden" name="_csrf_token" value="{csrf_token()}">')


def current_admin_role() -> str:
    return session.get("admin_role", "readonly")


def role_allowed(roles: set[str]) -> bool:
    return current_admin_role() in roles


def can_access_module(module: str) -> bool:
    return role_allowed(MODULE_ACCESS.get(module, ALL_ADMIN_ROLES))


def forbidden_response():
    return render_template(
        "forbidden.html",
        heading="Acceso restringido",
        description="Tu rol actual no permite ejecutar esta accion.",
    ), 403


def require_roles(*roles: str):
    allowed_roles = set(roles)

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not role_allowed(allowed_roles):
                return forbidden_response()
            return view(*args, **kwargs)

        return wrapped

    return decorator


def require_write_roles(*roles: str) -> bool:
    if request.method != "POST":
        return True
    return role_allowed(set(roles))


@app.context_processor
def security_context():
    return {
        "csrf_token": csrf_token,
        "csrf_field": csrf_field,
        "can_access_module": can_access_module,
        "current_admin_role": current_admin_role,
    }


@app.before_request
def protect_admin_csrf():
    if request.method != "POST":
        return None
    if request.path.startswith("/api/mobile/"):
        return None

    stored_token = session.get("_csrf_token", "")
    submitted_token = request.form.get("_csrf_token", "") or request.headers.get("X-CSRF-Token", "")
    if stored_token and submitted_token and hmac.compare_digest(stored_token, submitted_token):
        return None

    return render_template(
        "forbidden.html",
        heading="Sesion protegida",
        description="El formulario no pudo validarse. Recarga la pagina e intentalo nuevamente.",
    ), 400


@app.before_request
def require_admin_session():
    public_prefixes = ("/api/mobile/", "/static/")
    public_endpoints = {"login"}

    if request.path.startswith(public_prefixes) or request.endpoint in public_endpoints:
        return None

    if not session.get("admin_authenticated"):
        return redirect(url_for("login", next=request.path))

    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        store = load_store()
        admin_user = next(
            (
                user
                for user in store.get("admin_users", [])
                if user.get("email", "").lower() == email and user.get("status") == "active"
            ),
            None,
        )

        if admin_user and check_password_hash(admin_user.get("passwordHash", ""), password):
            session["admin_authenticated"] = True
            session["admin_user_id"] = admin_user["id"]
            session["admin_name"] = admin_user.get("name", "Admin Wulkan")
            session["admin_role"] = admin_user.get("role", "operator")
            admin_user["lastLoginAt"] = utc_now()
            record_audit_event(store, "login", "admin_user", admin_user["id"], "Inicio de sesion admin.")
            save_store(store)
            return redirect(request.args.get("next") or url_for("dashboard"))

        error = "Credenciales invalidas."

    return render_template("login.html", error=error)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def current_rate() -> float:
    return 38.5


def mobile_token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="wulkan-mobile-client")


def issue_mobile_token(client: dict) -> str:
    return mobile_token_serializer().dumps({"clientId": client["id"]})


def mobile_token_client_id() -> str:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return ""

    token = header.removeprefix("Bearer ").strip()
    if not token:
        return ""

    try:
        payload = mobile_token_serializer().loads(token, max_age=60 * 60 * 24 * 7)
    except (BadSignature, SignatureExpired):
        return ""

    return payload.get("clientId", "") if isinstance(payload, dict) else ""


def require_mobile_client_id() -> tuple[str, object | None]:
    customer_id = mobile_token_client_id() or request.args.get("customerId", "").strip()
    require_token = bool(app.config.get("REQUIRE_MOBILE_TOKEN"))
    if require_token and not mobile_token_client_id():
        return "", jsonify({"error": "Token movil requerido."})
    return customer_id, None


def enrich_product(product: dict) -> dict:
    rate = float(product.get("exchangeRateUsdVes") or current_rate())
    price = float(product.get("publicPriceUsd") or 0)
    original_price = float(product.get("originalPriceUsd") or price)
    discount = float(product.get("discountPercent") or 0)
    enriched = dict(product)
    enriched["publicPriceVes"] = round(price * rate, 2)
    enriched["originalPriceUsd"] = original_price
    enriched["hasDiscount"] = discount > 0 or original_price > price
    enriched["exchangeRateUsdVes"] = rate
    return enriched


def split_lines(value: str) -> list[str]:
    return [line.strip() for line in value.replace(",", "\n").splitlines() if line.strip()]


def parse_specs(value: str) -> dict[str, str]:
    specs: dict[str, str] = {}
    for line in split_lines(value):
        if ":" in line:
            key, spec_value = line.split(":", 1)
            specs[key.strip()] = spec_value.strip()
    return specs


def find_by_id(items: list[dict], item_id: str) -> dict | None:
    return next((item for item in items if item.get("id") == item_id), None)


def find_order(orders: list[dict], order_id: str) -> dict | None:
    return next(
        (
            order
            for order in orders
            if order.get("id") == order_id or order.get("orderId") == order_id
        ),
        None,
    )


def record_audit_event(
    store: dict,
    action: str,
    entity_type: str,
    entity_id: str = "",
    detail: str = "",
    metadata: dict | None = None,
) -> None:
    actor_name = session.get("admin_name", "Sistema")
    event = {
        "id": next_id("audit", f"{action}-{entity_type}-{entity_id or actor_name}"),
        "actorId": session.get("admin_user_id", ""),
        "actorName": actor_name,
        "actorRole": session.get("admin_role", ""),
        "action": action,
        "entityType": entity_type,
        "entityId": entity_id,
        "detail": detail,
        "ipAddress": request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip(),
        "path": request.path,
        "method": request.method,
        "createdAt": utc_now(),
        "metadata": metadata or {},
    }
    store.setdefault("audit_events", []).append(event)
    store["audit_events"] = store["audit_events"][-1000:]


def order_payments(movements: list[dict] | None, order_id: str) -> list[dict]:
    return [
        movement
        for movement in movements or []
        if movement.get("movementType") == "payment" and movement.get("orderId") == order_id
    ]


def order_paid_usd(order: dict, movements: list[dict] | None = None) -> float:
    payments = order_payments(movements, order.get("orderId") or order.get("id", ""))
    if payments:
        return round(sum(float(payment.get("amountUsd") or 0) for payment in payments), 2)
    return round(float(order.get("paidUsd") or 0), 2)


def order_balance_usd(order: dict, movements: list[dict] | None = None) -> float:
    total = float(order.get("totalUsd") or 0)
    paid = order_paid_usd(order, movements)
    return max(0.0, round(total - paid, 2))


def client_order_credit_used(
    orders: list[dict],
    client_id: str,
    movements: list[dict] | None = None,
    exclude_order_id: str = "",
) -> float:
    return round(
        sum(
            order_balance_usd(order, movements)
            for order in orders
            if order.get("customerId") == client_id
            and order.get("status") in ORDER_CREDIT_RESERVING_STATUSES
            and order.get("id") != exclude_order_id
            and order.get("orderId") != exclude_order_id
        ),
        2,
    )


def credit_available(
    client: dict,
    orders: list[dict] | None = None,
    movements: list[dict] | None = None,
    exclude_order_id: str = "",
) -> float:
    if not client.get("creditEnabled"):
        return 0.0
    limit = float(client.get("creditLimitUsd") or 0)
    used = float(client.get("creditUsedUsd") or 0)
    if orders is not None:
        used += client_order_credit_used(orders, client.get("id", ""), movements, exclude_order_id)
    return max(0.0, round(limit - used, 2))


def enrich_client(
    client: dict,
    orders: list[dict] | None = None,
    movements: list[dict] | None = None,
) -> dict:
    enriched = dict(client)
    enriched["creditLimitUsd"] = float(enriched.get("creditLimitUsd") or 0)
    enriched["creditUsedUsd"] = float(enriched.get("creditUsedUsd") or 0)
    enriched["creditOrdersUsd"] = client_order_credit_used(
        orders or [],
        enriched.get("id", ""),
        movements,
    )
    enriched["creditExposureUsd"] = round(enriched["creditUsedUsd"] + enriched["creditOrdersUsd"], 2)
    enriched["creditAvailableUsd"] = credit_available(enriched, orders, movements)
    enriched["creditStatus"] = "without_credit"
    if enriched.get("creditEnabled"):
        if enriched["creditAvailableUsd"] <= 0:
            enriched["creditStatus"] = "exhausted"
        elif enriched["creditExposureUsd"] > 0:
            enriched["creditStatus"] = "in_use"
        else:
            enriched["creditStatus"] = "available"
    return enriched


def enrich_order(order: dict, movements: list[dict] | None = None) -> dict:
    enriched = dict(order)
    order_id = enriched.get("orderId") or enriched.get("id", "")
    paid = order_paid_usd(enriched, movements)
    balance = order_balance_usd(enriched, movements)
    enriched["paidUsd"] = paid
    enriched["balanceUsd"] = balance
    enriched["paymentStatus"] = "paid" if balance <= 0 else ("partial" if paid > 0 else "pending")
    enriched["creditReservedUsd"] = balance if enriched.get("status") in ORDER_CREDIT_RESERVING_STATUSES else 0.0
    enriched["payments"] = order_payments(movements, order_id)
    enriched["inventoryStatus"] = enriched.get("inventoryStatus", "pending")
    enriched["stockStatus"] = enriched.get("stockStatus", "pending")
    customer = enriched.get("customer") or {}
    enriched["customerName"] = customer.get("name") or customer.get("businessName") or "Cliente Wulkan"
    enriched["itemsCount"] = len(enriched.get("items") or [])
    return enriched


def append_order_history(order: dict, status: str, note: str = "") -> None:
    order.setdefault("statusHistory", []).append(
        {
            "status": status,
            "note": note,
            "adminUserId": session.get("admin_user_id", ""),
            "adminName": session.get("admin_name", "Admin"),
            "createdAt": utc_now(),
        }
    )


def order_item_quantities(order: dict) -> dict[str, int]:
    quantities: dict[str, int] = {}
    for item in order.get("items") or []:
        product_id = item.get("productId", "")
        if not product_id:
            continue
        quantities[product_id] = quantities.get(product_id, 0) + int(item.get("quantity") or 0)
    return quantities


def stock_reserved_quantities(orders: list[dict]) -> dict[str, int]:
    reserved: dict[str, int] = {}
    for order in orders:
        if order.get("inventoryStatus") != "reserved":
            continue
        for product_id, quantity in order_item_quantities(order).items():
            reserved[product_id] = reserved.get(product_id, 0) + quantity
    return reserved


def enrich_inventory_product(product: dict, orders: list[dict]) -> dict:
    reserved_by_product = stock_reserved_quantities(orders)
    enriched = enrich_product(product)
    physical_stock = int(enriched.get("stock") or 0)
    committed = int(reserved_by_product.get(enriched["id"], 0))
    available = max(0, physical_stock - committed)
    enriched["physicalStock"] = physical_stock
    enriched["reserved"] = committed
    enriched["availableStock"] = available
    enriched["committedStock"] = committed
    enriched["stockStatus"] = "out"
    if available > 5:
        enriched["stockStatus"] = "available"
    elif available > 0:
        enriched["stockStatus"] = "low"
    return enriched


def available_stock_for_product(product: dict, orders: list[dict]) -> int:
    enriched = enrich_inventory_product(product, orders)
    return int(enriched.get("availableStock") or 0)


def order_has_sufficient_stock(store: dict, order: dict) -> bool:
    products = {product["id"]: product for product in store.get("products", [])}
    for product_id, quantity in order_item_quantities(order).items():
        product = products.get(product_id)
        if not product or available_stock_for_product(product, store.get("orders", [])) < quantity:
            return False
    return True


def append_stock_movement(
    store: dict,
    product: dict,
    movement_type: str,
    quantity: int,
    order: dict | None = None,
    note: str = "",
) -> None:
    store.setdefault("stock_movements", []).append(
        {
            "id": next_id("mov", f"{product.get('sku', '')}-{movement_type}"),
            "productId": product.get("id", ""),
            "sku": product.get("sku", ""),
            "type": movement_type,
            "quantity": quantity,
            "orderId": (order or {}).get("orderId", ""),
            "note": note,
            "createdBy": session.get("admin_name", "Sistema"),
            "createdAt": utc_now(),
        }
    )


def reserve_stock_for_order(store: dict, order: dict) -> bool:
    if order.get("inventoryStatus") == "reserved":
        return True
    if order.get("inventoryStatus") == "delivered":
        return True
    if not order_has_sufficient_stock(store, order):
        order["inventoryStatus"] = "review"
        order["stockStatus"] = "insufficient_stock"
        return False

    products = {product["id"]: product for product in store.get("products", [])}
    for product_id, quantity in order_item_quantities(order).items():
        product = products.get(product_id)
        if product:
            append_stock_movement(store, product, "reserved", quantity, order, "Reserva por orden B2B.")

    order["inventoryStatus"] = "reserved"
    order["stockStatus"] = "reserved"
    order["reservedAt"] = utc_now()
    return True


def release_stock_for_order(store: dict, order: dict) -> None:
    if order.get("inventoryStatus") != "reserved":
        order["inventoryStatus"] = "released"
        order["stockStatus"] = "released"
        return

    products = {product["id"]: product for product in store.get("products", [])}
    for product_id, quantity in order_item_quantities(order).items():
        product = products.get(product_id)
        if product:
            append_stock_movement(store, product, "released", quantity, order, "Liberacion por cancelacion.")

    order["inventoryStatus"] = "released"
    order["stockStatus"] = "released"
    order["releasedAt"] = utc_now()


def deliver_stock_for_order(store: dict, order: dict) -> bool:
    if order.get("inventoryStatus") == "delivered":
        return True
    if order.get("inventoryStatus") not in {"reserved", "review", "", None} and not order_has_sufficient_stock(store, order):
        order["inventoryStatus"] = "review"
        order["stockStatus"] = "insufficient_stock"
        return False
    if order.get("inventoryStatus") != "reserved" and not reserve_stock_for_order(store, order):
        return False

    products = {product["id"]: product for product in store.get("products", [])}
    for product_id, quantity in order_item_quantities(order).items():
        product = products.get(product_id)
        if not product:
            continue
        product["stock"] = max(0, int(product.get("stock") or 0) - quantity)
        product["updatedAt"] = utc_now()
        append_stock_movement(store, product, "delivered", quantity, order, "Descuento por entrega.")

    order["inventoryStatus"] = "delivered"
    order["stockStatus"] = "delivered"
    order["deliveredAt"] = utc_now()
    return True


def apply_inventory_transition(store: dict, order: dict, target_status: str) -> bool:
    if target_status == "cancelled":
        release_stock_for_order(store, order)
        return True
    if target_status == "delivered":
        return deliver_stock_for_order(store, order)
    if target_status in ORDER_STOCK_RESERVING_STATUSES:
        return reserve_stock_for_order(store, order)
    return True


def save_upload(file_storage, folder: str = "library") -> str:
    if not file_storage or not file_storage.filename:
        return ""

    upload_root = Path(app.config["UPLOAD_FOLDER"]) / folder
    upload_root.mkdir(parents=True, exist_ok=True)
    filename = f"{int(__import__('time').time())}-{secure_filename(file_storage.filename)}"
    target = upload_root / filename
    file_storage.save(target)
    return url_for("static", filename=f"uploads/{folder}/{filename}")


def product_payload(store: dict, existing: dict | None = None) -> dict:
    category_id = request.form.get("categoryId", "machinery-garden")
    category = find_by_id(store["categories"], category_id) or store["categories"][0]
    sku = request.form.get("sku", "").strip().upper()
    title = request.form.get("title", "").strip()
    primary_image = request.form.get("imageUrl", "").strip()
    image_urls = split_lines(request.form.get("imageUrls", ""))
    pdf_urls = split_lines(request.form.get("pdfUrls", ""))
    uploaded_image = save_upload(request.files.get("imageFile"), "products")
    uploaded_pdf = save_upload(request.files.get("pdfFile"), "products")

    if uploaded_image:
        primary_image = uploaded_image
    if primary_image and primary_image not in image_urls:
        image_urls.insert(0, primary_image)
    if uploaded_pdf and uploaded_pdf not in pdf_urls:
        pdf_urls.insert(0, uploaded_pdf)

    now = utc_now()
    payload = {
        "sku": sku,
        "title": title,
        "description": request.form.get("description", "").strip(),
        "productType": request.form.get("productType", "machine"),
        "categoryId": category["id"],
        "categoryName": category["name"],
        "publicPriceUsd": float(request.form.get("publicPriceUsd") or 0),
        "originalPriceUsd": float(request.form.get("originalPriceUsd") or request.form.get("publicPriceUsd") or 0),
        "discountPercent": float(request.form.get("discountPercent") or 0),
        "b2bPriceUsd": float(request.form.get("b2bPriceUsd") or 0),
        "exchangeRateUsdVes": float(request.form.get("exchangeRateUsdVes") or current_rate()),
        "stock": int(request.form.get("stock") or 0),
        "reserved": int(request.form.get("reserved") or (existing or {}).get("reserved") or 0),
        "status": request.form.get("status", "active"),
        "imageUrl": primary_image,
        "imageUrls": image_urls,
        "pdfUrls": pdf_urls,
        "variants": split_lines(request.form.get("variants", "")),
        "specifications": parse_specs(request.form.get("specifications", "")),
        "requiresQuote": request.form.get("requiresQuote") == "on",
        "requiresTechnicalValidation": request.form.get("requiresTechnicalValidation") == "on",
        "rotationLast30Days": int(request.form.get("rotationLast30Days") or (existing or {}).get("rotationLast30Days") or 0),
        "updatedAt": now,
    }
    if existing is None:
        payload["id"] = next_id("prod", sku or title)
        payload["createdAt"] = now
    else:
        payload["id"] = existing["id"]
        payload["createdAt"] = existing.get("createdAt", now)
    return payload


def product_form_snapshot() -> dict:
    return {
        "sku": request.form.get("sku", "").strip().upper(),
        "title": request.form.get("title", "").strip(),
        "description": request.form.get("description", "").strip(),
        "productType": request.form.get("productType", "machine"),
        "categoryId": request.form.get("categoryId", "machinery-garden"),
        "status": request.form.get("status", "active"),
        "publicPriceUsd": request.form.get("publicPriceUsd", ""),
        "originalPriceUsd": request.form.get("originalPriceUsd", ""),
        "discountPercent": request.form.get("discountPercent", 0),
        "b2bPriceUsd": request.form.get("b2bPriceUsd", ""),
        "exchangeRateUsdVes": request.form.get("exchangeRateUsdVes", current_rate()),
        "stock": request.form.get("stock", 0),
        "imageUrl": request.form.get("imageUrl", "").strip(),
        "imageUrls": split_lines(request.form.get("imageUrls", "")),
        "pdfUrls": split_lines(request.form.get("pdfUrls", "")),
        "variants": split_lines(request.form.get("variants", "")),
        "specifications": parse_specs(request.form.get("specifications", "")),
        "requiresQuote": request.form.get("requiresQuote") == "on",
        "requiresTechnicalValidation": request.form.get("requiresTechnicalValidation") == "on",
    }


def product_form_error(store: dict, existing: dict | None = None) -> str:
    sku = request.form.get("sku", "").strip().upper()
    if not sku:
        return "El SKU es obligatorio para crear o editar productos."

    duplicated = any(
        product.get("sku", "").upper() == sku
        and (existing is None or product.get("id") != existing.get("id"))
        for product in store["products"]
    )
    if duplicated:
        return f"El SKU {sku} ya existe en el catalogo."

    return ""


def admin_user_payload(existing: dict | None = None) -> dict:
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    now = utc_now()
    payload = {
        "name": request.form.get("name", "").strip(),
        "email": email,
        "role": request.form.get("role", "operator"),
        "status": request.form.get("status", "active"),
        "updatedAt": now,
    }
    if existing is None:
        payload["id"] = next_id("admin", email)
        payload["createdAt"] = now
        payload["passwordHash"] = generate_password_hash(password or "wulkan2026")
    else:
        payload["id"] = existing["id"]
        payload["createdAt"] = existing.get("createdAt", now)
        payload["passwordHash"] = (
            generate_password_hash(password) if password else existing.get("passwordHash", "")
        )
    return payload


def client_payload(existing: dict | None = None) -> dict:
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    now = utc_now()
    payload = {
        "businessName": request.form.get("businessName", "").strip(),
        "taxId": request.form.get("taxId", "").strip(),
        "contactName": request.form.get("contactName", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "email": email,
        "clientType": request.form.get("clientType", "ferretero"),
        "status": request.form.get("status", "active"),
        "creditEnabled": request.form.get("creditEnabled") == "on",
        "creditLimitUsd": float(request.form.get("creditLimitUsd") or 0),
        "creditUsedUsd": float(request.form.get("creditUsedUsd") or (existing or {}).get("creditUsedUsd") or 0),
        "paymentTermsDays": int(request.form.get("paymentTermsDays") or 0),
        "notes": request.form.get("notes", "").strip(),
        "updatedAt": now,
    }
    if existing is None:
        payload["id"] = next_id("client", email or payload["businessName"])
        payload["createdAt"] = now
        payload["passwordHash"] = generate_password_hash(password or "ferretero2026")
    else:
        payload["id"] = existing["id"]
        payload["createdAt"] = existing.get("createdAt", now)
        payload["passwordHash"] = (
            generate_password_hash(password) if password else existing.get("passwordHash", "")
        )
    return payload


def active_announcements(placement: str | None = None) -> list[dict]:
    store = load_store()
    announcements = [
        announcement
        for announcement in store["announcements"]
        if announcement.get("status") == "active"
        and (placement is None or announcement.get("placement") == placement)
    ]
    return sorted(announcements, key=lambda item: int(item.get("priority") or 0), reverse=True)


@app.get("/")
def dashboard():
    store = load_store()
    orders = store["orders"]
    products = [enrich_inventory_product(product, orders) for product in store["products"]]
    movements = store.get("credit_movements", [])
    enriched_orders = [enrich_order(order, movements) for order in orders]
    clients_list = [enrich_client(client, orders, movements) for client in store.get("clients", [])]
    gross_revenue = sum(float(order.get("totalUsd") or 0) for order in orders)
    metrics = {
        "products": len(products),
        "active_products": sum(1 for product in products if product.get("status") == "active"),
        "clients": len(clients_list),
        "credit_available": sum(float(client.get("creditAvailableUsd") or 0) for client in clients_list),
        "credit_exposure": sum(float(client.get("creditExposureUsd") or 0) for client in clients_list),
        "low_stock": sum(1 for product in products if int(product.get("availableStock") or 0) <= 5),
        "orders": len(orders),
        "gross_revenue": gross_revenue,
        "announcements": len(store["announcements"]),
    }
    return render_template(
        "dashboard.html",
        metrics=metrics,
        stock_health=stock_health(products),
        rotation_chart=rotation_chart(products),
        recent_orders=sorted(enriched_orders, key=lambda item: item.get("createdAt", ""), reverse=True)[:6],
    )


@app.route("/admin-users", methods=["GET", "POST"])
@require_roles("super_admin")
def admin_users():
    store = load_store()
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        existing_email = any(user.get("email", "").lower() == email for user in store["admin_users"])
        if email and not existing_email:
            user = admin_user_payload()
            store["admin_users"].append(user)
            record_audit_event(store, "create", "admin_user", user["id"], f"Usuario admin creado: {user['email']}.")
            save_store(store)
        return redirect(url_for("admin_users"))

    return render_template(
        "admin_users.html",
        users=sorted(store["admin_users"], key=lambda item: item.get("name", "")),
    )


@app.post("/admin-users/<user_id>/edit")
@require_roles("super_admin")
def admin_user_edit(user_id: str):
    store = load_store()
    user = find_by_id(store["admin_users"], user_id)
    if user:
        updated = admin_user_payload(user)
        store["admin_users"] = [updated if item["id"] == user_id else item for item in store["admin_users"]]
        record_audit_event(store, "update", "admin_user", user_id, f"Usuario admin actualizado: {updated['email']}.")
        save_store(store)
    return redirect(url_for("admin_users"))


@app.route("/clients", methods=["GET", "POST"])
@require_roles("super_admin", "operator", "sales", "readonly")
def clients():
    store = load_store()
    if request.method == "POST":
        if not role_allowed(SALES_ROLES):
            return forbidden_response()
        email = request.form.get("email", "").strip().lower()
        existing_email = any(client.get("email", "").lower() == email for client in store["clients"])
        if email and not existing_email:
            client = client_payload()
            store["clients"].append(client)
            record_audit_event(store, "create", "client", client["id"], f"Cliente creado: {client['businessName']}.")
            save_store(store)
        return redirect(url_for("clients"))

    clients_list = [enrich_client(client, store["orders"], store.get("credit_movements", [])) for client in store["clients"]]
    metrics = {
        "clients": len(clients_list),
        "active": sum(1 for client in clients_list if client.get("status") == "active"),
        "credit_enabled": sum(1 for client in clients_list if client.get("creditEnabled")),
        "credit_available": sum(float(client.get("creditAvailableUsd") or 0) for client in clients_list),
        "credit_exposure": sum(float(client.get("creditExposureUsd") or 0) for client in clients_list),
    }
    return render_template(
        "clients.html",
        clients=sorted(clients_list, key=lambda item: item.get("businessName", "")),
        metrics=metrics,
    )


@app.post("/clients/<client_id>/edit")
@require_roles("super_admin", "operator", "sales")
def client_edit(client_id: str):
    store = load_store()
    client = find_by_id(store["clients"], client_id)
    if client:
        updated = client_payload(client)
        store["clients"] = [updated if item["id"] == client_id else item for item in store["clients"]]
        record_audit_event(store, "update", "client", client_id, f"Cliente actualizado: {updated['businessName']}.")
        save_store(store)
    return redirect(url_for("clients"))


@app.get("/products")
def products():
    store = load_store()
    query = request.args.get("q", "").strip().lower()
    products = [enrich_inventory_product(product, store["orders"]) for product in store["products"]]
    if query:
        products = [
            product
            for product in products
            if query in product.get("title", "").lower() or query in product.get("sku", "").lower()
        ]
    return render_template("products.html", products=products, query=query)


@app.route("/products/new", methods=["GET", "POST"])
@require_roles("super_admin", "operator", "inventory")
def product_new():
    store = load_store()
    if request.method == "POST":
        error = product_form_error(store)
        if error:
            return render_template(
                "product_form.html",
                categories=store["categories"],
                rate=current_rate(),
                product=product_form_snapshot(),
                mode="Crear",
                error=error,
            )

        product = product_payload(store)
        store["products"].append(product)
        record_audit_event(store, "create", "product", product["id"], f"Producto creado: {product['sku']}.")
        save_store(store)
        return redirect(url_for("products"))

    return render_template(
        "product_form.html",
        categories=store["categories"],
        rate=current_rate(),
        product=None,
        mode="Crear",
        error="",
    )


@app.route("/products/<product_id>/edit", methods=["GET", "POST"])
@require_roles("super_admin", "operator", "inventory")
def product_edit(product_id: str):
    store = load_store()
    product = find_by_id(store["products"], product_id)
    if product is None:
        return redirect(url_for("products"))

    if request.method == "POST":
        error = product_form_error(store, product)
        if error:
            snapshot = product_form_snapshot()
            snapshot["id"] = product["id"]
            snapshot["createdAt"] = product.get("createdAt")
            return render_template(
                "product_form.html",
                categories=store["categories"],
                rate=current_rate(),
                product=snapshot,
                mode="Editar",
                error=error,
            )

        updated = product_payload(store, product)
        store["products"] = [updated if item["id"] == product_id else item for item in store["products"]]
        record_audit_event(store, "update", "product", product_id, f"Producto actualizado: {updated['sku']}.")
        save_store(store)
        return redirect(url_for("products"))

    return render_template(
        "product_form.html",
        categories=store["categories"],
        rate=current_rate(),
        product=enrich_product(product),
        mode="Editar",
        error="",
    )


@app.post("/products/<product_id>/delete")
@require_roles("super_admin", "operator", "inventory")
def product_delete(product_id: str):
    store = load_store()
    product = find_by_id(store["products"], product_id)
    store["products"] = [product for product in store["products"] if product["id"] != product_id]
    record_audit_event(
        store,
        "delete",
        "product",
        product_id,
        f"Producto eliminado: {(product or {}).get('sku', product_id)}.",
    )
    save_store(store)
    return redirect(url_for("products"))


@app.route("/stock", methods=["GET", "POST"])
def stock():
    store = load_store()
    if request.method == "POST":
        if not role_allowed(INVENTORY_ROLES):
            return forbidden_response()
        bulk_payload = request.form.get("bulkStock", "").strip()
        movement_type = request.form.get("type", "entry")
        reserved_by_product = stock_reserved_quantities(store.get("orders", []))
        if bulk_payload:
            stock_by_sku = {}
            for line in split_lines(bulk_payload):
                if ":" in line:
                    sku, quantity = line.split(":", 1)
                elif "," in line:
                    sku, quantity = line.split(",", 1)
                else:
                    continue
                stock_by_sku[sku.strip().upper()] = int(quantity.strip() or 0)
            for product in store["products"]:
                if product["sku"] in stock_by_sku:
                    reserved = reserved_by_product.get(product["id"], 0)
                    quantity = max(stock_by_sku[product["sku"]], reserved)
                    product["stock"] = quantity
                    product["updatedAt"] = utc_now()
                    store["stock_movements"].append(
                        {
                            "id": next_id("mov", product["sku"]),
                            "productId": product["id"],
                            "sku": product["sku"],
                            "type": "bulk_set",
                            "quantity": quantity,
                            "note": "Carga masiva de stock fisico.",
                            "createdBy": session.get("admin_name", "Admin"),
                            "createdAt": utc_now(),
                        }
                    )
        else:
            product_id = request.form.get("productId")
            quantity = int(request.form.get("quantity") or 0)
            for product in store["products"]:
                if product["id"] == product_id:
                    current_stock = int(product.get("stock") or 0)
                    reserved = reserved_by_product.get(product["id"], 0)
                    if movement_type == "entry":
                        product["stock"] = current_stock + quantity
                    elif movement_type == "adjustment":
                        product["stock"] = max(reserved, quantity)
                    else:
                        product["stock"] = max(reserved, current_stock - quantity)
                    product["updatedAt"] = utc_now()
                    store["stock_movements"].append(
                        {
                            "id": next_id("mov", product["sku"]),
                            "productId": product["id"],
                            "sku": product["sku"],
                            "type": movement_type,
                            "quantity": quantity,
                            "note": request.form.get("note", "").strip(),
                            "createdBy": session.get("admin_name", "Admin"),
                            "createdAt": utc_now(),
                        }
                    )
                    break
        record_audit_event(store, "update", "stock", "", "Stock actualizado desde panel.")
        save_store(store)
        return redirect(url_for("stock"))

    products = [enrich_inventory_product(product, store["orders"]) for product in store["products"]]
    return render_template(
        "stock.html",
        products=products,
        movements=list(reversed(store["stock_movements"][-20:])),
        rotation_chart=rotation_chart(products),
    )


@app.route("/categories", methods=["GET", "POST"])
def categories():
    store = load_store()
    if request.method == "POST":
        if not role_allowed(INVENTORY_ROLES):
            return forbidden_response()
        name = request.form.get("name", "").strip()
        image_url = request.form.get("imageUrl", "").strip() or save_upload(request.files.get("imageFile"), "categories")
        category = {
            "id": next_id("cat", name),
            "name": name,
            "description": request.form.get("description", "").strip(),
            "imageUrl": image_url,
            "status": request.form.get("status", "active"),
            "updatedAt": utc_now(),
        }
        store["categories"].append(category)
        record_audit_event(store, "create", "category", category["id"], f"Categoria creada: {category['name']}.")
        save_store(store)
        return redirect(url_for("categories"))

    return render_template("categories.html", categories=store["categories"])


@app.route("/categories/<category_id>/edit", methods=["POST"])
@require_roles("super_admin", "operator", "inventory")
def category_edit(category_id: str):
    store = load_store()
    category = find_by_id(store["categories"], category_id)
    if category:
        image_url = request.form.get("imageUrl", "").strip() or category.get("imageUrl", "")
        uploaded = save_upload(request.files.get("imageFile"), "categories")
        category.update(
            {
                "name": request.form.get("name", "").strip(),
                "description": request.form.get("description", "").strip(),
                "imageUrl": uploaded or image_url,
                "status": request.form.get("status", "active"),
                "updatedAt": utc_now(),
            }
        )
        for product in store["products"]:
            if product.get("categoryId") == category_id:
                product["categoryName"] = category["name"]
        record_audit_event(store, "update", "category", category_id, f"Categoria actualizada: {category['name']}.")
        save_store(store)
    return redirect(url_for("categories"))


@app.post("/categories/<category_id>/delete")
@require_roles("super_admin", "operator", "inventory")
def category_delete(category_id: str):
    store = load_store()
    if not any(product.get("categoryId") == category_id for product in store["products"]):
        category = find_by_id(store["categories"], category_id)
        store["categories"] = [category for category in store["categories"] if category["id"] != category_id]
        record_audit_event(
            store,
            "delete",
            "category",
            category_id,
            f"Categoria eliminada: {(category or {}).get('name', category_id)}.",
        )
        save_store(store)
    return redirect(url_for("categories"))


@app.route("/media-library", methods=["GET", "POST"])
def media_library():
    store = load_store()
    if request.method == "POST":
        if not role_allowed(INVENTORY_ROLES):
            return forbidden_response()
        product_id = request.form.get("productId", "")
        asset_url = request.form.get("assetUrl", "").strip() or save_upload(request.files.get("assetFile"), "library")
        asset_type = request.form.get("assetType", "image")
        title = request.form.get("title", "").strip() or "Activo Wulkan"
        if asset_url:
            asset = {
                "id": next_id("asset", title),
                "title": title,
                "assetType": asset_type,
                "productId": product_id,
                "url": asset_url,
                "createdAt": utc_now(),
            }
            store["media_assets"].append(asset)
            product = find_by_id(store["products"], product_id)
            if product:
                if asset_type == "pdf":
                    product.setdefault("pdfUrls", []).append(asset_url)
                else:
                    product.setdefault("imageUrls", []).append(asset_url)
                    if not product.get("imageUrl"):
                        product["imageUrl"] = asset_url
            record_audit_event(store, "create", "media_asset", asset["id"], f"Recurso tecnico creado: {title}.")
        save_store(store)
        return redirect(url_for("media_library"))

    products = store["products"]
    product_lookup = {product["id"]: product for product in products}
    assets = []
    for asset in reversed(store.get("media_assets", [])):
        enriched_asset = dict(asset)
        product = product_lookup.get(enriched_asset.get("productId"))
        enriched_asset["productTitle"] = product["title"] if product else "Sin asociar"
        enriched_asset["productSku"] = product["sku"] if product else ""
        assets.append(enriched_asset)

    return render_template(
        "media_library.html",
        products=products,
        assets=assets,
    )


@app.get("/credit")
@require_roles("super_admin", "operator", "sales")
def credit():
    store = load_store()
    movements = store.get("credit_movements", [])
    clients_list = [
        enrich_client(client, store.get("orders", []), movements)
        for client in store.get("clients", [])
    ]
    client_lookup = {client["id"]: client for client in store.get("clients", [])}
    payments = []
    for movement in movements:
        if movement.get("movementType") != "payment":
            continue
        enriched_movement = dict(movement)
        client = client_lookup.get(enriched_movement.get("clientId", ""))
        enriched_movement["clientName"] = client.get("businessName", "Cliente Wulkan") if client else "Cliente Wulkan"
        payments.append(enriched_movement)
    metrics = {
        "limit": sum(float(client.get("creditLimitUsd") or 0) for client in clients_list if client.get("creditEnabled")),
        "exposure": sum(float(client.get("creditExposureUsd") or 0) for client in clients_list),
        "available": sum(float(client.get("creditAvailableUsd") or 0) for client in clients_list),
        "payments": sum(float(payment.get("amountUsd") or 0) for payment in payments),
    }
    return render_template(
        "credit.html",
        clients=sorted(clients_list, key=lambda item: item.get("businessName", "")),
        payments=sorted(payments, key=lambda item: item.get("createdAt", ""), reverse=True),
        metrics=metrics,
    )


@app.get("/audit")
@require_roles("super_admin")
def audit():
    store = load_store()
    events = sorted(store.get("audit_events", []), key=lambda item: item.get("createdAt", ""), reverse=True)[:200]
    write_actions = {"create", "update", "delete", "payment", "update_status"}
    metrics = {
        "total": len(store.get("audit_events", [])),
        "actors": len({event.get("actorId") or event.get("actorName") for event in store.get("audit_events", [])}),
        "writes": sum(1 for event in store.get("audit_events", []) if event.get("action") in write_actions),
    }
    graphify_summary = f"{metrics['writes']} cambios / {metrics['actors']} actores"
    return render_template(
        "audit.html",
        events=events,
        metrics=metrics,
        graphify_summary=graphify_summary,
    )


@app.get("/orders")
@require_roles("super_admin", "operator", "sales", "readonly")
def orders():
    store = load_store()
    movements = store.get("credit_movements", [])
    enriched_orders = [
        enrich_order(order, movements)
        for order in sorted(store["orders"], key=lambda item: item.get("createdAt", ""), reverse=True)
    ]
    metrics = {
        "orders": len(enriched_orders),
        "total": sum(float(order.get("totalUsd") or 0) for order in enriched_orders),
        "balance": sum(float(order.get("balanceUsd") or 0) for order in enriched_orders),
        "review": sum(1 for order in enriched_orders if order.get("status") == "credit_review"),
    }
    return render_template(
        "orders.html",
        orders=enriched_orders,
        status_options=ORDER_STATUS_OPTIONS,
        payment_methods=PAYMENT_METHOD_OPTIONS,
        metrics=metrics,
    )


@app.post("/orders/<order_id>/status")
@require_roles("super_admin", "operator", "sales")
def order_status_update(order_id: str):
    store = load_store()
    order = find_order(store["orders"], order_id)
    if not order:
        return redirect(url_for("orders"))

    target_status = request.form.get("status", order.get("status", "credit_review"))
    allowed_statuses = {status for status, _label in ORDER_STATUS_OPTIONS}
    if target_status not in allowed_statuses:
        return redirect(url_for("orders"))

    client = find_by_id(store.get("clients", []), order.get("customerId", ""))
    movements = store.get("credit_movements", [])
    balance = order_balance_usd(order, movements)
    note = request.form.get("note", "").strip()

    if target_status in ORDER_CREDIT_RESERVING_STATUSES:
        available = credit_available(
            client,
            store["orders"],
            movements,
            exclude_order_id=order.get("id") or order.get("orderId", ""),
        ) if client else 0.0
        if not client or client.get("status") != "active" or not client.get("creditEnabled") or available < balance:
            target_status = "credit_review"
            order["creditStatus"] = "manual_review"
            note = note or "Credito insuficiente o cliente no habilitado para aprobacion automatica."
        else:
            order["creditStatus"] = "approved"

    if target_status != "credit_review" and not apply_inventory_transition(store, order, target_status):
        target_status = "credit_review"
        order["creditStatus"] = "manual_review"
        note = note or "Stock insuficiente para reservar o entregar esta orden."

    if target_status == "cancelled":
        order["creditStatus"] = "cancelled"
    elif target_status == "paid" and balance > 0:
        target_status = "partial_paid"
        note = note or "La orden tiene saldo pendiente; registra el abono para cerrarla como pagada."

    order["status"] = target_status
    order["managedBy"] = session.get("admin_name", "Admin")
    order["managedAt"] = utc_now()
    order["updatedAt"] = utc_now()
    order["balanceUsd"] = order_balance_usd(order, movements)
    order["paidUsd"] = order_paid_usd(order, movements)
    append_order_history(order, target_status, note)
    record_audit_event(store, "update_status", "order", order_id, f"Orden movida a {target_status}.")
    save_store(store)
    return redirect(url_for("orders"))


@app.post("/orders/<order_id>/payments")
@require_roles("super_admin", "operator", "sales")
def order_payment_create(order_id: str):
    store = load_store()
    order = find_order(store["orders"], order_id)
    if not order:
        return redirect(url_for("orders"))

    movements = store.setdefault("credit_movements", [])
    balance_before = order_balance_usd(order, movements)
    amount_usd = min(float(request.form.get("amountUsd") or 0), balance_before)
    if amount_usd <= 0:
        return redirect(url_for("orders"))

    exchange_rate = float(request.form.get("exchangeRateUsdVes") or order.get("exchangeRateUsdVes") or current_rate())
    amount_ves = float(request.form.get("amountVes") or round(amount_usd * exchange_rate, 2))
    movement = {
        "id": next_id("credit-payment", order.get("orderId") or order.get("id", "")),
        "movementType": "payment",
        "clientId": order.get("customerId", ""),
        "orderId": order.get("orderId") or order.get("id", ""),
        "amountUsd": amount_usd,
        "amountVes": amount_ves,
        "exchangeRateUsdVes": exchange_rate,
        "method": request.form.get("method", "cash"),
        "reference": request.form.get("reference", "").strip(),
        "note": request.form.get("note", "").strip(),
        "createdBy": session.get("admin_name", "Admin"),
        "createdAt": utc_now(),
    }
    movements.append(movement)

    balance_after = order_balance_usd(order, movements)
    paid_after = order_paid_usd(order, movements)
    order["paidUsd"] = paid_after
    order["balanceUsd"] = balance_after
    order["paymentStatus"] = "paid" if balance_after <= 0 else "partial"
    order["status"] = "paid" if balance_after <= 0 else "partial_paid"
    order["creditStatus"] = "released" if balance_after <= 0 else order.get("creditStatus", "approved")
    apply_inventory_transition(store, order, order["status"])
    order["managedBy"] = session.get("admin_name", "Admin")
    order["managedAt"] = utc_now()
    order["updatedAt"] = utc_now()
    append_order_history(order, order["status"], f"Abono externo registrado por {money_usd(amount_usd)}.")
    record_audit_event(store, "payment", "order", order_id, f"Abono registrado por {money_usd(amount_usd)}.")
    save_store(store)
    return redirect(url_for("orders"))


@app.route("/announcements", methods=["GET", "POST"])
def announcements():
    store = load_store()
    if request.method == "POST":
        if not role_allowed(SALES_ROLES):
            return forbidden_response()
        title = request.form.get("title", "").strip()
        image_url = request.form.get("imageUrl", "").strip() or save_upload(request.files.get("imageFile"), "announcements")
        announcement = {
            "id": next_id("ann", title),
            "title": title,
            "body": request.form.get("body", "").strip(),
            "placement": request.form.get("placement", "home"),
            "priority": int(request.form.get("priority") or 50),
            "ctaLabel": request.form.get("ctaLabel", "").strip(),
            "ctaUrl": request.form.get("ctaUrl", "").strip(),
            "imageUrl": image_url,
            "startsAt": request.form.get("startsAt") or utc_now(),
            "endsAt": request.form.get("endsAt", "").strip(),
            "status": request.form.get("status", "active"),
            "updatedAt": utc_now(),
        }
        store["announcements"].append(announcement)
        record_audit_event(store, "create", "announcement", announcement["id"], f"Anuncio creado: {title}.")
        save_store(store)
        return redirect(url_for("announcements"))

    return render_template(
        "announcements.html",
        announcements=sorted(store["announcements"], key=lambda item: int(item.get("priority") or 0), reverse=True),
    )


@app.post("/announcements/<announcement_id>/edit")
@require_roles("super_admin", "operator", "sales")
def announcement_edit(announcement_id: str):
    store = load_store()
    announcement = find_by_id(store["announcements"], announcement_id)
    if announcement:
        image_url = request.form.get("imageUrl", "").strip() or announcement.get("imageUrl", "")
        uploaded = save_upload(request.files.get("imageFile"), "announcements")
        if uploaded:
            image_url = uploaded
        announcement.update(
            {
                "title": request.form.get("title", "").strip(),
                "body": request.form.get("body", "").strip(),
                "placement": request.form.get("placement", "home"),
                "priority": int(request.form.get("priority") or 50),
                "ctaLabel": request.form.get("ctaLabel", "").strip(),
                "ctaUrl": request.form.get("ctaUrl", "").strip(),
                "imageUrl": image_url,
                "startsAt": request.form.get("startsAt", "").strip() or announcement.get("startsAt", ""),
                "endsAt": request.form.get("endsAt", "").strip(),
                "status": request.form.get("status", "active"),
                "updatedAt": utc_now(),
            }
        )
        record_audit_event(store, "update", "announcement", announcement_id, f"Anuncio actualizado: {announcement['title']}.")
        save_store(store)
    return redirect(url_for("announcements"))


@app.post("/announcements/<announcement_id>/delete")
@require_roles("super_admin", "operator", "sales")
def announcement_delete(announcement_id: str):
    store = load_store()
    announcement = find_by_id(store["announcements"], announcement_id)
    store["announcements"] = [
        announcement for announcement in store["announcements"] if announcement["id"] != announcement_id
    ]
    record_audit_event(
        store,
        "delete",
        "announcement",
        announcement_id,
        f"Anuncio eliminado: {(announcement or {}).get('title', announcement_id)}.",
    )
    save_store(store)
    return redirect(url_for("announcements"))


@app.post("/api/mobile/orders")
def api_create_order():
    store = load_store()
    payload = request.get_json(silent=True) or {}
    preview = payload.get("preview") or {}
    customer_payload = payload.get("customer") or {}
    customer_id = mobile_token_client_id() or customer_payload.get("id", "")
    if app.config.get("REQUIRE_MOBILE_TOKEN") and not mobile_token_client_id():
        return jsonify({"error": "Token movil requerido."}), 401
    client = find_by_id(store.get("clients", []), customer_id)
    if client and not customer_payload:
        customer_payload = {"id": client["id"], "name": client.get("businessName", "Cliente Wulkan")}
    order_id = next_id("ord-mobile", "checkout")
    total_usd = float(preview.get("totalUsd") or preview.get("subtotalUsd") or 0)
    movements = store.get("credit_movements", [])
    credit_before = credit_available(client, store["orders"], movements) if client else 0.0
    credit_after = max(0.0, round(credit_before - total_usd, 2)) if client and client.get("creditEnabled") else 0.0
    can_use_credit = (
        client is not None
        and client.get("status") == "active"
        and client.get("creditEnabled")
        and credit_before >= total_usd
    )
    credit_status = "approved" if can_use_credit else "manual_review"
    if client and client.get("status") != "active":
        credit_status = "client_not_active"
    elif client and not client.get("creditEnabled"):
        credit_status = "without_credit"
    order = {
        "id": order_id,
        "orderId": order_id,
        "customerId": customer_id,
        "customer": customer_payload or {"name": "Cliente Wulkan"},
        "items": payload.get("items") or [],
        "totalUsd": total_usd,
        "totalVes": float(preview.get("totalVes") or 0),
        "exchangeRateUsdVes": float(preview.get("exchangeRateUsdVes") or current_rate()),
        "creditBeforeUsd": credit_before,
        "creditAfterUsd": credit_after,
        "creditStatus": credit_status,
        "paidUsd": 0.0,
        "balanceUsd": total_usd,
        "paymentStatus": "pending",
        "status": "approved_with_credit" if can_use_credit else "credit_review",
        "statusHistory": [
            {
                "status": "approved_with_credit" if can_use_credit else "credit_review",
                "note": "Orden creada desde app movil.",
                "adminUserId": "",
                "adminName": "Sistema",
                "createdAt": utc_now(),
            }
        ],
        "createdAt": utc_now(),
        "updatedAt": utc_now(),
    }
    if can_use_credit and not reserve_stock_for_order(store, order):
        order["status"] = "credit_review"
        order["creditStatus"] = "manual_review"
        order["statusHistory"][0]["status"] = "credit_review"
        order["statusHistory"][0]["note"] = "Orden creada desde app movil; stock requiere revision."
    store["orders"].append(order)
    save_store(store)
    return jsonify(
        {
            "orderId": order_id,
            "status": order["status"],
            "creditBeforeUsd": credit_before,
            "creditAfterUsd": credit_after,
            "balanceUsd": total_usd,
        }
    ), 201


@app.get("/api/mobile/orders")
def api_orders():
    store = load_store()
    customer_id, auth_error = require_mobile_client_id()
    if auth_error:
        return auth_error, 401
    orders = store.get("orders", [])
    if customer_id:
        orders = [order for order in orders if order.get("customerId") == customer_id]
    movements = store.get("credit_movements", [])

    return jsonify(
        {
            "items": sorted(
                [enrich_order(order, movements) for order in orders],
                key=lambda order: order.get("createdAt", ""),
                reverse=True,
            )
        }
    )


@app.get("/api/mobile/credit")
def api_client_credit():
    store = load_store()
    customer_id, auth_error = require_mobile_client_id()
    if auth_error:
        return auth_error, 401
    client = find_by_id(store.get("clients", []), customer_id)
    if not client:
        return jsonify({"error": "Cliente no encontrado."}), 404

    enriched = enrich_client(client, store.get("orders", []), store.get("credit_movements", []))
    return jsonify(
        {
            "credit": {
                "customerId": enriched["id"],
                "creditEnabled": enriched["creditEnabled"],
                "creditLimitUsd": enriched["creditLimitUsd"],
                "creditUsedUsd": enriched["creditUsedUsd"],
                "creditOrdersUsd": enriched["creditOrdersUsd"],
                "creditExposureUsd": enriched["creditExposureUsd"],
                "creditAvailableUsd": enriched["creditAvailableUsd"],
                "paymentTermsDays": enriched["paymentTermsDays"],
                "status": enriched["creditStatus"],
            }
        }
    )


@app.get("/api/mobile/categories")
def api_categories():
    return jsonify({"items": load_store()["categories"]})


@app.post("/api/mobile/auth/login")
def api_client_login():
    store = load_store()
    payload = request.get_json(silent=True) or {}
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")
    client = next(
        (
            item
            for item in store.get("clients", [])
            if item.get("email", "").lower() == email and item.get("status") == "active"
        ),
        None,
    )
    if not client or not check_password_hash(client.get("passwordHash", ""), password):
        return jsonify({"error": "Credenciales invalidas."}), 401

    enriched = enrich_client(client, store["orders"], store.get("credit_movements", []))
    access_token = issue_mobile_token(client)
    return jsonify(
        {
            "accessToken": access_token,
            "tokenType": "Bearer",
            "customer": {
                "id": enriched["id"],
                "businessName": enriched["businessName"],
                "email": enriched["email"],
                "clientType": enriched["clientType"],
                "creditEnabled": enriched["creditEnabled"],
                "creditLimitUsd": enriched["creditLimitUsd"],
                "creditUsedUsd": enriched["creditUsedUsd"],
                "creditOrdersUsd": enriched["creditOrdersUsd"],
                "creditExposureUsd": enriched["creditExposureUsd"],
                "creditAvailableUsd": enriched["creditAvailableUsd"],
                "paymentTermsDays": enriched["paymentTermsDays"],
            }
        }
    )


@app.get("/api/mobile/products")
def api_products():
    store = load_store()
    products = [
        {
            "id": product["id"],
            "sku": product["sku"],
            "name": product["title"],
            "title": product["title"],
            "description": product.get("description", ""),
            "productType": product.get("productType", "machine"),
            "verticalName": product.get("categoryName", ""),
            "categoryName": product.get("categoryName", ""),
            "publicPriceUsd": float(product.get("publicPriceUsd") or 0),
            "originalPriceUsd": float(product.get("originalPriceUsd") or product.get("publicPriceUsd") or 0),
            "discountPercent": float(product.get("discountPercent") or 0),
            "b2bPriceUsd": float(product.get("b2bPriceUsd") or 0),
            "availableStock": int(product.get("availableStock") or 0),
            "stock": int(product.get("physicalStock") or product.get("stock") or 0),
            "reservedStock": int(product.get("committedStock") or 0),
            "stockStatus": product.get("stockStatus", "available"),
            "badge": "Cotizar" if product.get("requiresQuote") else "Comprar",
            "requiresQuote": bool(product.get("requiresQuote")),
            "requiresTechnicalValidation": bool(product.get("requiresTechnicalValidation")),
            "compatibilityNotes": ["Validar compatibilidad con soporte Wulkan"],
            "imageUrl": product.get("imageUrl") or (product.get("imageUrls") or [""])[0],
            "imageUrls": product.get("imageUrls", []),
            "pdfUrls": product.get("pdfUrls", []),
            "variants": product.get("variants", []),
            "specifications": product.get("specifications", {}),
        }
        for product in [enrich_inventory_product(item, store.get("orders", [])) for item in store["products"]]
        if product.get("status") == "active"
    ]
    return jsonify({"items": products})


@app.get("/api/mobile/announcements")
def api_announcements():
    placement = request.args.get("placement")
    return jsonify({"items": active_announcements(placement)})


@app.get("/api/mobile/locations")
def api_locations():
    return jsonify(
        {
            "items": [
                {
                    "id": "loc-caracas",
                    "name": "Punto autorizado Caracas",
                    "subtitle": "Retiro, soporte tecnico y entregas Wulkan",
                },
                {
                    "id": "loc-valencia",
                    "name": "Ferreteria Demo Valencia",
                    "subtitle": "Venta retail y retiro",
                },
            ]
        }
    )


@app.context_processor
def inject_helpers():
    return {
        "money_usd": money_usd,
        "usd_to_ves": usd_to_ves,
        "brand_name": "Wulkan",
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
