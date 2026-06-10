from __future__ import annotations

import hmac
import csv
import copy
import io
import re
import secrets
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, Response, jsonify, redirect, render_template, request, send_file, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from markupsafe import Markup
from werkzeug.exceptions import BadRequest
from werkzeug.security import check_password_hash, generate_password_hash

from config import get_config
from graphify import rotation_chart, stock_health
from storage import save_uploaded_file
from store import (
    INSECURE_PRODUCTION_ADMIN_EMAILS,
    INSECURE_PRODUCTION_CLIENT_EMAILS,
    load_store,
    next_id,
    save_store,
    utc_now,
)
from uix import badge_class, money_usd, usd_to_ves


app = Flask(__name__)
app.config.from_object(get_config())
app.jinja_env.filters["badge_class"] = badge_class
app.jinja_env.filters["money_usd"] = money_usd


def validate_runtime_config() -> None:
    if app.config.get("ENV") != "production":
        return
    database_url = str(app.config.get("DATABASE_URL", ""))
    if app.config.get("SECRET_KEY") == "wulkan-dev":
        raise RuntimeError("WULKAN_SECRET_KEY real es obligatorio en produccion.")
    if app.config.get("DATA_BACKEND") != "sql":
        raise RuntimeError("WULKAN_DATA_BACKEND=sql es obligatorio en produccion.")
    if database_url.startswith("sqlite"):
        raise RuntimeError("WULKAN_DATABASE_URL debe apuntar a PostgreSQL en produccion.")
    if app.config.get("SQL_FALLBACK_TO_JSON"):
        raise RuntimeError("WULKAN_SQL_FALLBACK_TO_JSON debe estar desactivado en produccion.")
    storage_backend = str(app.config.get("STORAGE_BACKEND", "")).strip().lower()
    if storage_backend != "s3":
        raise RuntimeError("WULKAN_STORAGE_BACKEND=s3 es obligatorio en produccion.")
    if not app.config.get("S3_BUCKET"):
        raise RuntimeError("WULKAN_S3_BUCKET es obligatorio en produccion.")


validate_runtime_config()


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if app.config.get("ENV") == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

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
SALE_TYPE_OPTIONS = [
    ("cash", "Contado / efectivo"),
    ("term_credit", "Credito por dias"),
    ("credit_line", "Linea de credito"),
    ("phone_request", "Solicitud telefonica"),
]
PAYMENT_TERM_OPTIONS = [0, 10, 15, 20, 30, 40]
ROLE_LABELS = {
    "super_admin": "Super admin",
    "commercial_manager": "Gerente comercial",
    "operator": "Operador",
    "sales": "Vendedor app movil",
    "inventory": "Inventario",
    "readonly": "Solo lectura",
}
LOGIN_ATTEMPTS: dict[str, list[float]] = {}
PASSWORD_MIN_LENGTH = 10
IMPORT_DRAFT_TTL_SECONDS = 60 * 60
WEB_ADMIN_ROLES = {"super_admin", "commercial_manager", "operator", "inventory", "readonly"}
WRITE_ROLES = {"super_admin", "commercial_manager", "operator"}
SALES_ROLES = {"super_admin", "commercial_manager", "operator"}
INVENTORY_ROLES = {"super_admin", "commercial_manager", "operator", "inventory"}
CREDIT_APPROVAL_ROLES = {"super_admin", "commercial_manager"}
ORDER_MANAGEMENT_ROLES = {"super_admin", "commercial_manager", "operator"}
COMMISSION_MANAGEMENT_ROLES = {"super_admin", "commercial_manager"}
MOBILE_SALES_ROLES = {"super_admin", "commercial_manager", "sales"}
ADMIN_ONLY_ROLES = {"super_admin"}
DELETE_ROLES = {"super_admin"}
MODULE_ACCESS = {
    "admin_users": ADMIN_ONLY_ROLES,
    "audit": ADMIN_ONLY_ROLES,
    "import_templates": WEB_ADMIN_ROLES,
    "sellers": {"super_admin", "commercial_manager", "operator", "readonly"},
    "clients": {"super_admin", "commercial_manager", "operator", "readonly"},
    "credit": {"super_admin", "commercial_manager"},
    "orders": {"super_admin", "commercial_manager", "operator", "readonly"},
    "commissions": {"super_admin", "commercial_manager"},
    "products": {"super_admin", "commercial_manager", "operator", "inventory", "readonly"},
    "media_library": {"super_admin", "operator", "inventory", "readonly"},
    "categories": {"super_admin", "operator", "inventory", "readonly"},
    "stock": {"super_admin", "operator", "inventory", "readonly"},
    "announcements": {"super_admin", "commercial_manager", "operator", "readonly"},
    "service_technicians": {"super_admin", "commercial_manager", "operator", "readonly"},
}
ADMIN_MENU_GROUPS = [
    {
        "label": "Comercial",
        "icon": "bi-briefcase",
        "items": [
            {"module": "sellers", "endpoint": "sellers", "label": "Vendedores", "icon": "bi-person-badge", "active": ["sellers", "seller_edit", "sellers_import", "seller_delete"]},
            {"module": "clients", "endpoint": "clients", "label": "Clientes", "icon": "bi-shop", "active": ["clients", "client_edit", "clients_import", "client_delete"]},
            {"module": "credit", "endpoint": "credit", "label": "Credito B2B", "icon": "bi-credit-card-2-front", "active": ["credit", "credit_decision", "credit_due", "credit_history"]},
            {"module": "orders", "endpoint": "orders", "label": "Ordenes", "icon": "bi-receipt", "active": ["orders", "order_new", "order_status_update", "order_payment_create"]},
            {"module": "commissions", "endpoint": "commissions", "label": "Comisiones", "icon": "bi-percent", "active": ["commissions", "commission_status_update"]},
        ],
    },
    {
        "label": "Catalogo",
        "icon": "bi-box-seam",
        "items": [
            {"module": "products", "endpoint": "products", "label": "Productos", "icon": "bi-box-seam", "active": ["products", "product_new", "product_edit", "products_import", "product_delete"]},
            {"module": "categories", "endpoint": "categories", "label": "Categorias", "icon": "bi-tags", "active": ["categories", "category_edit", "categories_import", "category_delete"]},
            {"module": "media_library", "endpoint": "media_library", "label": "Biblioteca tecnica", "icon": "bi-folder2-open", "active": ["media_library", "media_library_import", "media_asset_delete"]},
            {"module": "stock", "endpoint": "stock", "label": "Stock masivo", "icon": "bi-boxes", "active": ["stock", "stock_import"]},
        ],
    },
    {
        "label": "App movil",
        "icon": "bi-phone",
        "items": [
            {"module": "announcements", "endpoint": "announcements", "label": "Anuncios app", "icon": "bi-megaphone", "active": ["announcements", "announcements_import", "announcement_edit", "announcement_delete"]},
            {"module": "service_technicians", "endpoint": "service_technicians", "label": "Servicios tecnicos", "icon": "bi-tools", "active": ["service_technicians", "service_technicians_import", "service_technician_edit", "service_technician_delete"]},
        ],
    },
    {
        "label": "Sistema",
        "icon": "bi-shield-lock",
        "items": [
            {"module": "import_templates", "endpoint": "import_templates", "label": "Plantillas", "icon": "bi-file-earmark-spreadsheet", "active": ["import_templates", "download_import_template"]},
            {"module": "audit", "endpoint": "audit", "label": "Auditoria", "icon": "bi-shield-check", "active": ["audit"]},
            {"module": "admin_users", "endpoint": "admin_users", "label": "Usuarios admin", "icon": "bi-people", "active": ["admin_users", "admin_user_edit", "admin_user_delete"]},
        ],
    },
]

IMPORT_TEMPLATE_GROUPS = [
    {
        "label": "Comercial",
        "items": [
            {
                "key": "vendedores",
                "module": "sellers",
                "endpoint": "sellers",
                "title": "Vendedores",
                "description": "Usuarios de venta para app movil, zonas, metas y comision.",
                "columns": [
                    {"name": "nombre", "required": True, "example": "Carlos Perez", "help": "Nombre visible del vendedor."},
                    {"name": "email", "required": True, "example": "carlos@wulkanvenezuela.com", "help": "Correo unico para login movil."},
                    {"name": "telefono", "required": False, "example": "+584120000000", "help": "Telefono o WhatsApp."},
                    {"name": "codigo_vendedor", "required": False, "example": "VEN-CAR-01", "help": "Codigo interno comercial."},
                    {"name": "zona", "required": False, "example": "Caracas", "help": "Zona o cartera principal."},
                    {"name": "comision", "required": False, "example": "5", "help": "Porcentaje de comision."},
                    {"name": "meta_usd", "required": False, "example": "2500", "help": "Meta comercial mensual."},
                    {"name": "estado", "required": False, "example": "active", "help": "active o inactive."},
                    {"name": "clave", "required": False, "example": "Temporal2026", "help": "Si viene vacia se genera clave temporal."},
                ],
            },
            {
                "key": "clientes",
                "module": "clients",
                "endpoint": "clients",
                "title": "Clientes ferreteros",
                "description": "Cartera B2B con datos fiscales, direccion, vendedor y credito.",
                "columns": [
                    {"name": "cliente", "required": True, "example": "Ferreteria Principal C.A.", "help": "Razon social o nombre comercial."},
                    {"name": "email", "required": True, "example": "compras@ferreteriaprincipal.com", "help": "Correo unico para acceso movil."},
                    {"name": "rif", "required": False, "example": "J-12345678-9", "help": "Identificacion fiscal."},
                    {"name": "contacto", "required": False, "example": "Maria Gonzalez", "help": "Responsable de compras."},
                    {"name": "telefono", "required": False, "example": "+584140000000", "help": "Telefono o WhatsApp."},
                    {"name": "direccion", "required": False, "example": "Av. Bolivar, local 12", "help": "Direccion fiscal o despacho."},
                    {"name": "ciudad", "required": False, "example": "Valencia", "help": "Ciudad del cliente."},
                    {"name": "estado_ubicacion", "required": False, "example": "Carabobo", "help": "Estado o region."},
                    {"name": "zona", "required": False, "example": "Centro", "help": "Zona de despacho o cartera."},
                    {"name": "vendedor_email", "required": False, "example": "carlos@wulkanvenezuela.com", "help": "Asigna cartera por email del vendedor."},
                    {"name": "tipo_venta_default", "required": False, "example": "credit_line", "help": "cash, term_credit o credit_line."},
                    {"name": "cupo_usd", "required": False, "example": "1000", "help": "Linea aprobada si el rol puede aprobar."},
                    {"name": "credito_aprobado", "required": False, "example": "si", "help": "si/no. Solo gerente o super admin aprueba."},
                    {"name": "plazos", "required": False, "example": "0,15,30", "help": "Dias permitidos separados por coma."},
                    {"name": "clave", "required": False, "example": "Temporal2026", "help": "Si viene vacia se genera clave temporal."},
                ],
            },
        ],
    },
    {
        "label": "Catalogo",
        "items": [
            {
                "key": "productos",
                "module": "products",
                "endpoint": "products",
                "title": "Productos",
                "description": "Catalogo con SKU, precios, stock, galeria movil, PDFs y variantes.",
                "columns": [
                    {"name": "sku", "required": True, "example": "WUL-MOT-45CC", "help": "Codigo unico del producto."},
                    {"name": "nombre", "required": True, "example": "Motosierra Wulkan 45cc", "help": "Nombre visible comercial."},
                    {"name": "categoria", "required": True, "example": "Maquinaria y jardin", "help": "Familia del catalogo."},
                    {"name": "precio_publico_usd", "required": True, "example": "185", "help": "Precio PVP en dolares."},
                    {"name": "precio_b2b_usd", "required": False, "example": "162", "help": "Precio ferretero."},
                    {"name": "stock", "required": False, "example": "12", "help": "Stock fisico inicial."},
                    {"name": "descripcion", "required": False, "example": "Equipo para uso tecnico y jardin.", "help": "Descripcion app movil."},
                    {"name": "tipo_producto", "required": False, "example": "machine", "help": "machine, spare_part, accessory."},
                    {"name": "precio_anterior_usd", "required": False, "example": "210", "help": "Precio antes del descuento."},
                    {"name": "descuento_porcentaje", "required": False, "example": "12", "help": "Descuento visible."},
                    {"name": "tasa_usd_ves", "required": False, "example": "38.5", "help": "Referencia VES."},
                    {"name": "imagen_principal", "required": False, "example": "https://cdn.wulkan/producto.jpg", "help": "Imagen principal."},
                    {"name": "imagenes", "required": False, "example": "https://cdn.wulkan/1.jpg|https://cdn.wulkan/2.jpg", "help": "Galeria separada por |, coma o salto de linea."},
                    {"name": "pdf_tecnicos", "required": False, "example": "https://cdn.wulkan/ficha.pdf", "help": "Fichas tecnicas."},
                    {"name": "variantes", "required": False, "example": "18 pulgadas|20 pulgadas", "help": "Opciones visibles."},
                    {"name": "especificaciones", "required": False, "example": "Motor:45cc|Garantia:6 meses", "help": "Formato clave:valor."},
                    {"name": "requiere_cotizacion", "required": False, "example": "no", "help": "si/no."},
                    {"name": "requiere_validacion_tecnica", "required": False, "example": "si", "help": "si/no."},
                    {"name": "estado", "required": False, "example": "active", "help": "active, inactive o deleted."},
                ],
            },
            {
                "key": "categorias",
                "module": "categories",
                "endpoint": "categories",
                "title": "Categorias",
                "description": "Familias del catalogo con imagen para app movil.",
                "columns": [
                    {"name": "nombre", "required": True, "example": "Repuestos", "help": "Nombre de categoria."},
                    {"name": "descripcion", "required": False, "example": "Piezas y consumibles compatibles por SKU.", "help": "Texto visible."},
                    {"name": "imagen_url", "required": False, "example": "https://cdn.wulkan/categorias/repuestos.jpg", "help": "Imagen de categoria."},
                    {"name": "estado", "required": False, "example": "active", "help": "active o inactive."},
                ],
            },
            {
                "key": "stock",
                "module": "stock",
                "endpoint": "stock",
                "title": "Stock",
                "description": "Actualizacion masiva de inventario final por SKU.",
                "columns": [
                    {"name": "sku", "required": True, "example": "WUL-MOT-45CC", "help": "Debe existir en productos."},
                    {"name": "cantidad", "required": True, "example": "25", "help": "Stock fisico final."},
                    {"name": "tipo", "required": False, "example": "bulk_excel_set", "help": "Tipo de movimiento."},
                    {"name": "nota", "required": False, "example": "Inventario inicial junio", "help": "Comentario operativo."},
                ],
            },
            {
                "key": "biblioteca_tecnica",
                "module": "media_library",
                "endpoint": "media_library",
                "title": "Biblioteca tecnica",
                "description": "Imagenes y PDFs asociados a productos por SKU.",
                "columns": [
                    {"name": "sku", "required": True, "example": "WUL-MOT-45CC", "help": "Producto asociado."},
                    {"name": "titulo", "required": False, "example": "Ficha tecnica motosierra", "help": "Nombre interno."},
                    {"name": "tipo", "required": True, "example": "pdf", "help": "image o pdf."},
                    {"name": "url", "required": True, "example": "https://cdn.wulkan/ficha.pdf", "help": "URL publica del recurso."},
                ],
            },
        ],
    },
    {
        "label": "App movil",
        "items": [
            {
                "key": "anuncios_app",
                "module": "announcements",
                "endpoint": "announcements",
                "title": "Anuncios app",
                "description": "Banners para carrusel, campanas, vigencia y accion movil.",
                "columns": [
                    {"name": "titulo", "required": True, "example": "Oferta repuestos", "help": "Titulo interno y visible."},
                    {"name": "mensaje", "required": False, "example": "Descuentos especiales por temporada.", "help": "Texto de apoyo."},
                    {"name": "ubicacion", "required": False, "example": "home", "help": "home, catalog o checkout."},
                    {"name": "prioridad", "required": False, "example": "80", "help": "Mayor numero aparece primero."},
                    {"name": "imagen_url", "required": False, "example": "https://cdn.wulkan/banners/oferta.jpg", "help": "Imagen del carrusel."},
                    {"name": "boton", "required": False, "example": "Ver catalogo", "help": "Texto del CTA."},
                    {"name": "url_accion", "required": False, "example": "wulkan://catalogo", "help": "Accion o enlace."},
                    {"name": "inicio", "required": False, "example": "2026-06-10T00:00:00Z", "help": "Fecha inicio opcional."},
                    {"name": "cierre", "required": False, "example": "2026-06-30T23:59:59Z", "help": "Fecha cierre opcional."},
                    {"name": "estado", "required": False, "example": "active", "help": "active o inactive."},
                ],
            },
            {
                "key": "servicios_tecnicos",
                "module": "service_technicians",
                "endpoint": "service_technicians",
                "title": "Servicios tecnicos",
                "description": "Directorio publico/app de soporte tecnico autorizado.",
                "columns": [
                    {"name": "nombre", "required": True, "example": "Servicio Tecnico Caracas", "help": "Nombre comercial."},
                    {"name": "empresa", "required": False, "example": "Taller Central C.A.", "help": "Empresa asociada."},
                    {"name": "contacto", "required": False, "example": "Luis Martinez", "help": "Persona responsable."},
                    {"name": "telefono", "required": False, "example": "+584120000000", "help": "Telefono principal."},
                    {"name": "whatsapp", "required": False, "example": "+584120000000", "help": "WhatsApp."},
                    {"name": "email", "required": False, "example": "servicio@wulkanvenezuela.com", "help": "Correo de contacto."},
                    {"name": "estado_ubicacion", "required": False, "example": "Distrito Capital", "help": "Estado o region."},
                    {"name": "ciudad", "required": False, "example": "Caracas", "help": "Ciudad."},
                    {"name": "direccion", "required": False, "example": "Zona industrial, local 8", "help": "Direccion visible."},
                    {"name": "especialidades", "required": False, "example": "Motosierras|Motobombas", "help": "Separadas por |, coma o salto."},
                    {"name": "cobertura", "required": False, "example": "Caracas y Miranda", "help": "Zona cubierta."},
                    {"name": "visible_app", "required": False, "example": "si", "help": "si/no."},
                    {"name": "estado", "required": False, "example": "active", "help": "active o inactive."},
                ],
            },
        ],
    },
]
IMPORT_TEMPLATE_INDEX = {
    item["key"]: item
    for group in IMPORT_TEMPLATE_GROUPS
    for item in group["items"]
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


def is_production_runtime() -> bool:
    return str(app.config.get("ENV", "")).strip().lower() == "production"


def is_blocked_default_login(email: str, *, mobile: bool = False) -> bool:
    normalized = email.strip().lower()
    blocked = set(INSECURE_PRODUCTION_ADMIN_EMAILS)
    if mobile:
        blocked.update(INSECURE_PRODUCTION_CLIENT_EMAILS)
    return is_production_runtime() and normalized in blocked


def sales_users(store: dict) -> list[dict]:
    return sorted(
        [
            user
            for user in store.get("admin_users", [])
            if user.get("role") == "sales" and user.get("status") == "active"
        ],
        key=lambda user: user.get("name", ""),
    )


def web_admin_users(store: dict) -> list[dict]:
    return sorted(
        [
            user
            for user in store.get("admin_users", [])
            if user.get("role") != "sales"
        ],
        key=lambda user: user.get("name", ""),
    )


def current_admin_user(store: dict) -> dict | None:
    return find_by_id(store.get("admin_users", []), session.get("admin_user_id", ""))


def current_seller_assignment(store: dict) -> tuple[str, str]:
    if current_admin_role() != "sales":
        return "", ""
    user = current_admin_user(store)
    if not user:
        return "", ""
    return user.get("id", ""), user.get("name", "")


def sale_type_label(value: str) -> str:
    return dict(SALE_TYPE_OPTIONS).get(value, value or "Sin definir")


def commission_status_label(value: str) -> str:
    return {
        "commission_pending": "Pendiente",
        "commission_approved": "Aprobada",
        "commission_paid": "Pagada",
        "commission_cancelled": "Anulada",
    }.get(value, value or "Sin definir")


def parse_utc_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def add_days_iso(value: str | None, days: int) -> str:
    base = parse_utc_datetime(value)
    return (base + timedelta(days=max(0, int(days or 0)))).isoformat().replace("+00:00", "Z")


def order_due_status(order: dict) -> tuple[str, int]:
    due_date = order.get("dueDate", "")
    if order.get("balanceUsd", 0) <= 0:
        return "paid", 0
    if not due_date:
        return "without_due_date", 0
    due_at = parse_utc_datetime(due_date)
    today = datetime.now(timezone.utc)
    delta = (due_at.date() - today.date()).days
    if delta < 0:
        return "overdue", abs(delta)
    if delta <= 3:
        return "due_soon", delta
    return "current", delta


def seller_commission_rate(store: dict, seller_id: str) -> float:
    seller = find_by_id(store.get("admin_users", []), seller_id)
    return float((seller or {}).get("commissionRatePercent") or 0)


def seller_name_for(store: dict, seller_id: str) -> str:
    seller = find_by_id(store.get("admin_users", []), seller_id)
    return (seller or {}).get("name", "")


def visible_clients_for_current_user(store: dict) -> list[dict]:
    clients = store.get("clients", [])
    if current_admin_role() != "sales":
        return clients
    seller_id = session.get("admin_user_id", "")
    return [client for client in clients if client.get("assignedSellerId") == seller_id]


def can_access_client_record(client: dict | None) -> bool:
    if not client:
        return False
    if current_admin_role() != "sales":
        return True
    return client.get("assignedSellerId") == session.get("admin_user_id", "")


def visible_orders_for_current_user(store: dict) -> list[dict]:
    orders = store.get("orders", [])
    if current_admin_role() != "sales":
        return orders
    seller_id = session.get("admin_user_id", "")
    assigned_client_ids = {
        client.get("id", "")
        for client in store.get("clients", [])
        if client.get("assignedSellerId") == seller_id
    }
    return [
        order
        for order in orders
        if order.get("sellerId") == seller_id or order.get("customerId") in assigned_client_ids
    ]


def can_access_order_record(order: dict | None, store: dict) -> bool:
    if not order:
        return False
    if current_admin_role() != "sales":
        return True
    seller_id = session.get("admin_user_id", "")
    if order.get("sellerId") == seller_id:
        return True
    client = find_by_id(store.get("clients", []), order.get("customerId", ""))
    return bool(client and client.get("assignedSellerId") == seller_id)


def login_attempt_key(scope: str, email: str) -> str:
    ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "local").split(",")[0].strip()
    return f"{scope}:{ip_address}:{email.lower()}"


def is_login_limited(scope: str, email: str) -> bool:
    key = login_attempt_key(scope, email)
    now = time.time()
    window = int(app.config.get("LOGIN_WINDOW_SECONDS", 300))
    attempts = [timestamp for timestamp in LOGIN_ATTEMPTS.get(key, []) if now - timestamp < window]
    LOGIN_ATTEMPTS[key] = attempts
    return len(attempts) >= int(app.config.get("LOGIN_MAX_ATTEMPTS", 5))


def register_login_failure(scope: str, email: str) -> None:
    key = login_attempt_key(scope, email)
    LOGIN_ATTEMPTS.setdefault(key, []).append(time.time())


def reset_login_attempts(scope: str, email: str) -> None:
    LOGIN_ATTEMPTS.pop(login_attempt_key(scope, email), None)


def password_errors(password: str) -> list[str]:
    errors: list[str] = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"Debe tener al menos {PASSWORD_MIN_LENGTH} caracteres.")
    if not any(char.isalpha() for char in password):
        errors.append("Debe incluir letras.")
    if not any(char.isdigit() for char in password):
        errors.append("Debe incluir numeros.")
    return errors


def can_access_module(module: str) -> bool:
    return role_allowed(MODULE_ACCESS.get(module, WEB_ADMIN_ROLES))


def can_delete_data() -> bool:
    return role_allowed(DELETE_ROLES)


def visible_import_template_groups() -> list[dict]:
    groups: list[dict] = []
    for group in IMPORT_TEMPLATE_GROUPS:
        visible_items = [
            item for item in group["items"]
            if can_access_module(item["module"])
        ]
        if visible_items:
            groups.append({"label": group["label"], "items": visible_items})
    return groups


def import_template_filename(spec: dict, file_format: str) -> str:
    return f"plantilla_wulkan_{spec['key']}.{file_format}"


def build_csv_template(spec: dict) -> Response:
    headers = [column["name"] for column in spec["columns"]]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    payload = "\ufeff" + output.getvalue()
    return Response(
        payload,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={import_template_filename(spec, 'csv')}"
        },
    )


def build_xlsx_template(spec: dict):
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Alignment, Font, PatternFill

    workbook = Workbook()
    data_sheet = workbook.active
    data_sheet.title = "Carga"
    headers = [column["name"] for column in spec["columns"]]
    data_sheet.append(headers)
    data_sheet.freeze_panes = "A2"
    data_sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"

    required_fill = PatternFill("solid", fgColor="DDEBFF")
    optional_fill = PatternFill("solid", fgColor="F8F9FA")
    header_font = Font(bold=True, color="202224")
    for index, column in enumerate(spec["columns"], start=1):
        cell = data_sheet.cell(row=1, column=index)
        cell.font = header_font
        cell.fill = required_fill if column["required"] else optional_fill
        cell.alignment = Alignment(horizontal="center")
        cell.comment = Comment(
            f"{'Obligatorio' if column['required'] else 'Opcional'} - {column['help']}",
            "Wulkan",
        )
        data_sheet.column_dimensions[cell.column_letter].width = min(max(len(column["name"]) + 4, 16), 36)

    guide_sheet = workbook.create_sheet("Guia")
    guide_sheet.append(["Campo", "Obligatorio", "Ejemplo", "Descripcion"])
    for column in spec["columns"]:
        guide_sheet.append([
            column["name"],
            "SI" if column["required"] else "NO",
            column["example"],
            column["help"],
        ])
    for cell in guide_sheet[1]:
        cell.font = header_font
        cell.fill = required_fill
    guide_sheet.column_dimensions["A"].width = 28
    guide_sheet.column_dimensions["B"].width = 14
    guide_sheet.column_dimensions["C"].width = 38
    guide_sheet.column_dimensions["D"].width = 70

    example_sheet = workbook.create_sheet("Ejemplo")
    example_sheet.append(headers)
    example_sheet.append([column["example"] for column in spec["columns"]])
    for cell in example_sheet[1]:
        cell.font = header_font
        cell.fill = optional_fill
    for index, column in enumerate(spec["columns"], start=1):
        example_sheet.column_dimensions[example_sheet.cell(row=1, column=index).column_letter].width = min(max(len(column["name"]) + 4, 16), 36)

    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=import_template_filename(spec, "xlsx"),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def admin_menu_groups() -> list[dict]:
    current_endpoint = request.endpoint or ""
    groups: list[dict] = []
    for group in ADMIN_MENU_GROUPS:
        visible_items = []
        for item in group["items"]:
            if not can_access_module(item["module"]):
                continue
            visible_item = dict(item)
            visible_item["active"] = current_endpoint in item["active"]
            visible_items.append(visible_item)
        if visible_items:
            visible_group = dict(group)
            visible_group["items"] = visible_items
            visible_group["active"] = any(item["active"] for item in visible_items)
            groups.append(visible_group)
    return groups


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
        "can_delete_data": can_delete_data,
        "current_admin_role": current_admin_role,
        "admin_menu_groups": admin_menu_groups,
        "role_labels": ROLE_LABELS,
        "sale_type_label": sale_type_label,
        "commission_status_label": commission_status_label,
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
    public_endpoints = {"login", "healthz", "readyz"}

    if request.path.startswith(public_prefixes) or request.endpoint in public_endpoints:
        return None

    if not session.get("admin_authenticated"):
        return redirect(url_for("login", next=request.path))

    store = load_store()
    admin_user = current_admin_user(store)
    if not admin_user or admin_user.get("status") != "active":
        session.clear()
        return redirect(url_for("login", next=request.path))

    session["admin_name"] = admin_user.get("name", "Admin Wulkan")
    session["admin_role"] = admin_user.get("role", "operator")
    session["must_change_password"] = bool(admin_user.get("mustChangePassword"))

    if admin_user.get("role") == "sales":
        session.clear()
        return redirect(url_for("login", mobile_only="1"))

    allowed_password_endpoints = {"account_password", "logout"}
    if session.get("must_change_password") and request.endpoint not in allowed_password_endpoints:
        return redirect(url_for("account_password"))

    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.args.get("mobile_only") == "1":
        error = "Los vendedores ingresan desde la app movil. El panel web es solo administrativo."

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        store = load_store()
        if is_blocked_default_login(email):
            register_login_failure("admin", email)
            record_audit_event(
                store,
                "login_failed",
                "admin_user",
                email,
                "Intento de inicio con cuenta demo bloqueada en produccion.",
                actor={"id": email, "name": email or "desconocido", "role": "anonymous"},
            )
            save_store(store)
            error = "Credenciales invalidas."
            return render_template("login.html", error=error)
        if is_login_limited("admin", email):
            error = "Demasiados intentos. Espera unos minutos e intentalo nuevamente."
            record_audit_event(
                store,
                "login_limited",
                "admin_user",
                email,
                "Login admin bloqueado temporalmente por intentos fallidos.",
                actor={"id": email, "name": email or "desconocido", "role": "anonymous"},
            )
            save_store(store)
            return render_template("login.html", error=error)

        admin_user = next(
            (
                user
                for user in store.get("admin_users", [])
                if user.get("email", "").lower() == email and user.get("status") == "active"
            ),
            None,
        )

        if admin_user and check_password_hash(admin_user.get("passwordHash", ""), password):
            if admin_user.get("role") == "sales":
                reset_login_attempts("admin", email)
                record_audit_event(
                    store,
                    "login_blocked",
                    "admin_user",
                    admin_user["id"],
                    "Intento de acceso web con rol vendedor; debe usar app movil.",
                    actor={"id": admin_user["id"], "name": admin_user.get("name", email), "role": "sales"},
                )
                save_store(store)
                error = "Los vendedores ingresan desde la app movil. El panel web es solo administrativo."
                return render_template("login.html", error=error)
            reset_login_attempts("admin", email)
            session["admin_authenticated"] = True
            session["admin_user_id"] = admin_user["id"]
            session["admin_name"] = admin_user.get("name", "Admin Wulkan")
            session["admin_role"] = admin_user.get("role", "operator")
            session["must_change_password"] = bool(admin_user.get("mustChangePassword"))
            admin_user["lastLoginAt"] = utc_now()
            record_audit_event(store, "login", "admin_user", admin_user["id"], "Inicio de sesion admin.")
            save_store(store)
            if session.get("must_change_password"):
                return redirect(url_for("account_password"))
            return redirect(request.args.get("next") or url_for("dashboard"))

        register_login_failure("admin", email)
        record_audit_event(
            store,
            "login_failed",
            "admin_user",
            email,
            "Intento fallido de inicio de sesion admin.",
            actor={"id": email, "name": email or "desconocido", "role": "anonymous"},
        )
        save_store(store)
        error = "Credenciales invalidas."

    return render_template("login.html", error=error)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/account/password", methods=["GET", "POST"])
def account_password():
    store = load_store()
    admin_user = find_by_id(store.get("admin_users", []), session.get("admin_user_id", ""))
    if not admin_user:
        session.clear()
        return redirect(url_for("login"))

    error = ""
    success = ""
    if request.method == "POST":
        current_password = request.form.get("currentPassword", "")
        new_password = request.form.get("newPassword", "")
        confirm_password = request.form.get("confirmPassword", "")
        if not check_password_hash(admin_user.get("passwordHash", ""), current_password):
            error = "La contrasena actual no coincide."
        elif new_password != confirm_password:
            error = "La confirmacion de contrasena no coincide."
        elif password_errors(new_password):
            error = " ".join(password_errors(new_password))
        else:
            admin_user["passwordHash"] = generate_password_hash(new_password)
            admin_user["mustChangePassword"] = False
            admin_user["updatedAt"] = utc_now()
            session["must_change_password"] = False
            record_audit_event(
                store,
                "password_change",
                "admin_user",
                admin_user["id"],
                "Contrasena admin actualizada por el usuario.",
            )
            save_store(store)
            success = "Contrasena actualizada correctamente."

    return render_template(
        "account_password.html",
        error=error,
        success=success,
        must_change=bool(session.get("must_change_password")),
    )


def current_rate() -> float:
    return 38.5


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "wulkan-admin"})


@app.get("/readyz")
def readyz():
    try:
        store = load_store()
        return jsonify(
            {
                "status": "ready",
                "dataBackend": app.config.get("DATA_BACKEND"),
                "storageBackend": app.config.get("STORAGE_BACKEND"),
                "mobileTokenRequired": bool(app.config.get("REQUIRE_MOBILE_TOKEN")),
                "products": len(store.get("products", [])),
                "clients": len(store.get("clients", [])),
                "orders": len(store.get("orders", [])),
            }
        )
    except Exception as exc:
        return jsonify({"status": "not_ready", "error": str(exc)}), 503


def mobile_token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="wulkan-mobile-client")


def issue_mobile_token(client: dict) -> str:
    return mobile_token_serializer().dumps(
        {"type": "client", "clientId": client["id"], "id": client["id"], "role": "client"}
    )


def issue_mobile_admin_token(user: dict) -> str:
    return mobile_token_serializer().dumps(
        {"type": "admin", "adminUserId": user["id"], "id": user["id"], "role": user.get("role", "")}
    )


def mobile_token_payload() -> dict:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return {}

    token = header.removeprefix("Bearer ").strip()
    if not token:
        return {}

    try:
        payload = mobile_token_serializer().loads(token, max_age=60 * 60 * 24 * 7)
    except (BadSignature, SignatureExpired):
        return {}

    return payload if isinstance(payload, dict) else {}


def mobile_token_client_id() -> str:
    payload = mobile_token_payload()
    if payload.get("type", "client") not in {"client", ""}:
        return ""
    return payload.get("clientId") or payload.get("id", "")


def mobile_token_admin_id() -> str:
    payload = mobile_token_payload()
    if payload.get("type") != "admin":
        return ""
    return payload.get("adminUserId") or payload.get("id", "")


def require_mobile_sales_user(store: dict) -> tuple[dict | None, object | None]:
    admin_id = mobile_token_admin_id()
    user = find_by_id(store.get("admin_users", []), admin_id)
    if not user or user.get("status") != "active" or user.get("role") not in MOBILE_SALES_ROLES:
        return None, jsonify({"error": "Token de vendedor requerido."})
    return user, None


def require_mobile_client_id() -> tuple[str, object | None]:
    customer_id = mobile_token_client_id() or request.args.get("customerId", "").strip()
    require_token = bool(app.config.get("REQUIRE_MOBILE_TOKEN"))
    if require_token and not mobile_token_client_id():
        return "", jsonify({"error": "Token movil requerido."})
    return customer_id, None


def require_mobile_catalog_access(store: dict) -> tuple[dict | None, object | None]:
    if not app.config.get("REQUIRE_MOBILE_TOKEN"):
        return None, None

    payload = mobile_token_payload()
    if not payload:
        return None, jsonify({"error": "Token movil requerido."})

    if payload.get("type") == "admin":
        user = find_by_id(store.get("admin_users", []), payload.get("adminUserId") or payload.get("id", ""))
        if user and user.get("status") == "active" and user.get("role") in MOBILE_SALES_ROLES:
            return user, None
        return None, jsonify({"error": "Token movil invalido."})

    client = find_by_id(store.get("clients", []), payload.get("clientId") or payload.get("id", ""))
    if client and client.get("status") == "active":
        return client, None
    return None, jsonify({"error": "Token movil invalido."})


def mobile_customer_payload(client: dict, store: dict, access_token: str) -> dict:
    enriched = enrich_client(client, store.get("orders", []), store.get("credit_movements", []))
    return {
        "accessToken": access_token,
        "tokenType": "Bearer",
        "customer": {
            "id": enriched["id"],
            "businessName": enriched["businessName"],
            "email": enriched["email"],
            "clientType": enriched["clientType"],
            "accountRole": "client",
            "roleLabel": "Ferretero B2B",
            "creditEnabled": enriched["creditEnabled"],
            "creditLimitUsd": enriched["creditLimitUsd"],
            "creditUsedUsd": enriched["creditUsedUsd"],
            "creditOrdersUsd": enriched["creditOrdersUsd"],
            "creditExposureUsd": enriched["creditExposureUsd"],
            "creditAvailableUsd": enriched["creditAvailableUsd"],
            "paymentTermsDays": enriched["paymentTermsDays"],
            "allowedPaymentTermsDays": enriched.get("allowedPaymentTermsDays", [0]),
            "defaultSaleType": enriched.get("defaultSaleType", "cash"),
            "assignedSeller": {
                "id": enriched.get("assignedSellerId", ""),
                "name": enriched.get("assignedSellerName", ""),
            },
            "mustChangePassword": bool(enriched.get("mustChangePassword")),
        },
    }


def mobile_admin_payload(user: dict, access_token: str) -> dict:
    role = user.get("role", "sales")
    return {
        "accessToken": access_token,
        "tokenType": "Bearer",
        "customer": {
            "id": user["id"],
            "businessName": user.get("name", "Vendedor Wulkan"),
            "email": user.get("email", ""),
            "clientType": role,
            "accountRole": role,
            "roleLabel": ROLE_LABELS.get(role, "Vendedor"),
            "creditEnabled": False,
            "creditLimitUsd": 0.0,
            "creditUsedUsd": 0.0,
            "creditOrdersUsd": 0.0,
            "creditExposureUsd": 0.0,
            "creditAvailableUsd": 0.0,
            "paymentTermsDays": 0,
            "allowedPaymentTermsDays": [0],
            "defaultSaleType": "cash",
            "assignedSeller": {
                "id": user["id"] if role == "sales" else "",
                "name": user.get("name", "") if role == "sales" else "",
            },
            "mustChangePassword": bool(user.get("mustChangePassword")),
        },
    }


def seller_scope_clients(store: dict, user: dict) -> list[dict]:
    if user.get("role") != "sales":
        return store.get("clients", [])
    return [client for client in store.get("clients", []) if client.get("assignedSellerId") == user.get("id")]


def seller_scope_orders(store: dict, user: dict) -> list[dict]:
    orders = store.get("orders", [])
    if user.get("role") != "sales":
        return orders
    seller_id = user.get("id", "")
    client_ids = {client.get("id", "") for client in seller_scope_clients(store, user)}
    return [
        order
        for order in orders
        if order.get("sellerId") == seller_id or order.get("customerId") in client_ids
    ]


def can_mobile_seller_access_client(store: dict, user: dict, client_id: str) -> bool:
    client = find_by_id(store.get("clients", []), client_id)
    if not client:
        return False
    if user.get("role") != "sales":
        return True
    return client.get("assignedSellerId") == user.get("id")


def mobile_seller_client_payload(client: dict, store: dict) -> dict:
    enriched = enrich_client(client, store.get("orders", []), store.get("credit_movements", []))
    return {
        "id": enriched.get("id", ""),
        "businessName": enriched.get("businessName", ""),
        "email": enriched.get("email", ""),
        "phone": enriched.get("phone", ""),
        "contactName": enriched.get("contactName", ""),
        "taxId": enriched.get("taxId", ""),
        "state": enriched.get("state", ""),
        "city": enriched.get("city", ""),
        "address": enriched.get("address", ""),
        "creditEnabled": bool(enriched.get("creditEnabled")),
        "creditStatus": enriched.get("creditStatus", "without_credit"),
        "creditLimitUsd": enriched.get("creditLimitUsd", 0.0),
        "creditAvailableUsd": enriched.get("creditAvailableUsd", 0.0),
        "creditExposureUsd": enriched.get("creditExposureUsd", 0.0),
        "creditRequestStatus": enriched.get("creditRequestStatus", "none"),
        "assignedSeller": {
            "id": enriched.get("assignedSellerId", ""),
            "name": enriched.get("assignedSellerName", ""),
        },
    }


def mobile_seller_order_payload(order: dict, store: dict) -> dict:
    enriched = enrich_order(order, store.get("credit_movements", []))
    return {
        "id": enriched.get("orderId") or enriched.get("id", ""),
        "orderId": enriched.get("orderId") or enriched.get("id", ""),
        "customerId": enriched.get("customerId", ""),
        "customerName": enriched.get("customerName", ""),
        "sellerId": enriched.get("sellerId", ""),
        "sellerName": enriched.get("sellerName", ""),
        "status": enriched.get("status", ""),
        "saleType": enriched.get("saleType", "cash"),
        "saleTypeLabel": enriched.get("saleTypeLabel", ""),
        "paymentTermDays": enriched.get("paymentTermDays", 0),
        "dueDate": enriched.get("dueDate", ""),
        "dueStatus": enriched.get("dueStatus", "without_due_date"),
        "totalUsd": enriched.get("totalUsd", 0.0),
        "paidUsd": enriched.get("paidUsd", 0.0),
        "balanceUsd": enriched.get("balanceUsd", 0.0),
        "itemsCount": enriched.get("itemsCount", 0),
        "paymentStatus": enriched.get("paymentStatus", "pending"),
        "stockStatus": enriched.get("stockStatus", "pending"),
        "commissionUsd": enriched.get("commissionUsd", 0.0),
        "commissionStatus": enriched.get("commissionStatus", "commission_pending"),
        "commissionStatusLabel": enriched.get("commissionStatusLabel", "Pendiente"),
        "createdAt": enriched.get("createdAt", ""),
    }


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


def normalize_import_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", normalized.strip().lower())
    return normalized.strip("_")


def row_value(row: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        value = row.get(normalize_import_key(key))
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


def parse_import_float(value, default: float = 0.0) -> float:
    if value is None or str(value).strip() == "":
        return default
    cleaned = str(value).strip().replace("USD", "").replace("$", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(",", "")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return default


def parse_import_int(value, default: int = 0) -> int:
    try:
        return int(round(parse_import_float(value, default)))
    except (TypeError, ValueError):
        return default


def parse_import_bool(value, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    normalized = normalize_import_key(str(value))
    if normalized in {"1", "si", "s", "true", "activo", "activa", "yes", "y", "visible"}:
        return True
    if normalized in {"0", "no", "false", "inactivo", "inactiva", "oculto", "hidden"}:
        return False
    return default


def parse_import_list(value) -> list[str]:
    if value is None:
        return []
    return [
        item.strip()
        for item in re.split(r"[\n\r|;,]+", str(value))
        if item and item.strip()
    ]


def parse_import_specs(value) -> dict[str, str]:
    specs: dict[str, str] = {}
    for item in parse_import_list(value):
        if ":" in item:
            key, spec_value = item.split(":", 1)
            specs[key.strip()] = spec_value.strip()
    return specs


def import_cell_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value).strip()


def read_tabular_upload(file_storage) -> list[dict]:
    if not file_storage or not file_storage.filename:
        raise BadRequest("Selecciona un archivo .xlsx, .xlsm o .csv para la carga masiva.")

    filename = file_storage.filename.lower()
    rows: list[dict] = []
    if filename.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        file_storage.stream.seek(0)
        workbook = load_workbook(filename=file_storage.stream, read_only=True, data_only=True)
        worksheet = workbook.active
        raw_rows = list(worksheet.iter_rows(values_only=True))
        if not raw_rows:
            return []
        headers = [normalize_import_key(header) for header in raw_rows[0]]
        for raw_row in raw_rows[1:]:
            row = {
                headers[index]: import_cell_value(raw_row[index])
                for index in range(min(len(headers), len(raw_row)))
                if headers[index]
            }
            if any(str(value).strip() for value in row.values() if value is not None):
                rows.append(row)
        return rows

    if filename.endswith(".csv"):
        file_storage.stream.seek(0)
        payload = file_storage.read()
        text = payload.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        for raw_row in reader:
            row = {
                normalize_import_key(key): import_cell_value(value)
                for key, value in (raw_row or {}).items()
                if key
            }
            if any(str(value).strip() for value in row.values() if value is not None):
                rows.append(row)
        return rows

    raise BadRequest("Formato no soportado. Usa .xlsx, .xlsm o .csv.")


def blank_bulk_result() -> dict:
    return {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "warnings": [],
        "errors": [],
        "createdRows": [],
        "updatedRows": [],
        "skippedRows": [],
        "warningRows": [],
        "errorRows": [],
    }


def remember_bulk_result(module: str, result: dict) -> None:
    result["errors"] = result.get("errors", [])[:8]
    result["warnings"] = result.get("warnings", [])[:8]
    for key in ("createdRows", "updatedRows", "skippedRows", "warningRows", "errorRows"):
        result[key] = result.get(key, [])[:12]
    session[f"bulk_import_{module}"] = result


def consume_bulk_result(module: str) -> dict | None:
    return session.pop(f"bulk_import_{module}", None)


def bulk_error(result: dict, row_number: int, message: str) -> None:
    result.setdefault("errors", []).append(f"Fila {row_number}: {message}")
    result.setdefault("errorRows", []).append({"row": row_number, "label": message})
    result["skipped"] = int(result.get("skipped", 0)) + 1


def bulk_warning(result: dict, row_number: int, message: str) -> None:
    result.setdefault("warnings", []).append(f"Fila {row_number}: {message}")
    result.setdefault("warningRows", []).append({"row": row_number, "label": message})


def bulk_row(result: dict, action: str, row_number: int, label: str) -> None:
    bucket = {
        "created": "createdRows",
        "updated": "updatedRows",
        "skipped": "skippedRows",
    }.get(action)
    if bucket:
        result.setdefault(bucket, []).append({"row": row_number, "label": label})


def is_public_url(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized.startswith("https://") or normalized.startswith("http://")


def warn_invalid_urls(result: dict, row_number: int, label: str, urls: list[str]) -> None:
    invalid_urls = [url for url in urls if url and not is_public_url(url)]
    if invalid_urls:
        bulk_warning(result, row_number, f"{label} con URL no publica o invalida: {', '.join(invalid_urls[:3])}.")


def duplicate_in_upload(seen: dict[str, int], value: str, row_number: int) -> str:
    normalized = normalize_import_key(value)
    if not normalized:
        return ""
    first_row = seen.get(normalized)
    if first_row:
        return f"valor duplicado en el archivo; ya aparece en fila {first_row}."
    seen[normalized] = row_number
    return ""


def purge_expired_import_drafts() -> None:
    from db import SessionLocal, init_database
    from models import ImportDraft

    init_database()
    with SessionLocal() as db_session:
        db_session.query(ImportDraft).filter(ImportDraft.expires_at < datetime.now(timezone.utc)).delete()
        db_session.commit()


def create_import_draft(module: str, entity_type: str, rows: list[dict], result: dict) -> str:
    from db import SessionLocal, init_database
    from models import ImportDraft

    init_database()
    purge_expired_import_drafts()
    draft_id = f"import-{secrets.token_urlsafe(18)}"
    now = datetime.now(timezone.utc)
    with SessionLocal() as db_session:
        db_session.add(
            ImportDraft(
                id=draft_id,
                module=module,
                entity_type=entity_type,
                status="preview",
                created_by_id=session.get("admin_user_id", ""),
                created_by_name=session.get("admin_name", "Admin"),
                rows=rows,
                result=result,
                created_at=now,
                expires_at=now + timedelta(seconds=IMPORT_DRAFT_TTL_SECONDS),
            )
        )
        db_session.commit()
    return draft_id


def load_import_draft(module: str, draft_id: str):
    from db import SessionLocal, init_database
    from models import ImportDraft

    init_database()
    purge_expired_import_drafts()
    with SessionLocal() as db_session:
        draft = db_session.get(ImportDraft, draft_id)
        if not draft or draft.module != module or draft.status != "preview":
            return None
        return {
            "id": draft.id,
            "module": draft.module,
            "entityType": draft.entity_type,
            "rows": list(draft.rows or []),
            "result": dict(draft.result or {}),
        }


def finish_import_draft(module: str, draft_id: str, status: str) -> bool:
    from db import SessionLocal, init_database
    from models import ImportDraft

    init_database()
    with SessionLocal() as db_session:
        draft = db_session.get(ImportDraft, draft_id)
        if not draft or draft.module != module:
            return False
        if status == "discarded":
            db_session.delete(draft)
        else:
            draft.status = status
        db_session.commit()
        return True


def find_product_by_sku(store: dict, sku: str) -> dict | None:
    normalized = sku.strip().upper()
    return next((product for product in store.get("products", []) if product.get("sku", "").upper() == normalized), None)


def find_category_by_name(store: dict, name: str) -> dict | None:
    normalized = normalize_import_key(name)
    return next(
        (
            category
            for category in store.get("categories", [])
            if normalize_import_key(category.get("name", "")) == normalized
            or normalize_import_key(category.get("id", "")) == normalized
        ),
        None,
    )


def ensure_import_category(store: dict, category_id: str = "", category_name: str = "") -> dict:
    category = find_by_id(store.get("categories", []), category_id) if category_id else None
    if category:
        return category
    category = find_category_by_name(store, category_name) if category_name else None
    if category:
        return category
    if category_name:
        category = {
            "id": next_id("cat", category_name),
            "name": category_name,
            "description": "Categoria creada automaticamente por carga masiva.",
            "imageUrl": "",
            "status": "active",
            "updatedAt": utc_now(),
        }
        store.setdefault("categories", []).append(category)
        return category
    return (store.get("categories") or [{"id": "uncategorized", "name": "Sin categoria"}])[0]


def find_seller_for_import(store: dict, row: dict) -> dict | None:
    seller_id = row_value(row, "assignedSellerId", "sellerId", "vendedor_id", "id_vendedor")
    if seller_id:
        seller = find_by_id(store.get("admin_users", []), seller_id)
        if seller:
            return seller
    seller_email = row_value(row, "sellerEmail", "vendedor_email", "email_vendedor")
    if seller_email:
        return next(
            (
                user
                for user in store.get("admin_users", [])
                if user.get("role") == "sales" and user.get("email", "").lower() == seller_email.lower()
            ),
            None,
        )
    seller_name = row_value(row, "sellerName", "vendedor", "vendedor_nombre")
    if seller_name:
        normalized = normalize_import_key(seller_name)
        return next(
            (
                user
                for user in store.get("admin_users", [])
                if user.get("role") == "sales" and normalize_import_key(user.get("name", "")) == normalized
            ),
            None,
        )
    return None


def append_unique(target: list, values: list[str]) -> None:
    for value in values:
        if value and value not in target:
            target.append(value)


def import_categories_rows(store: dict, rows: list[dict]) -> dict:
    result = blank_bulk_result()
    seen_categories: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=2):
        name = row_value(row, "name", "nombre", "categoria", "category")
        if not name:
            bulk_error(result, row_number, "la categoria requiere nombre.")
            continue
        duplicate_message = duplicate_in_upload(seen_categories, name, row_number)
        if duplicate_message:
            bulk_error(result, row_number, f"categoria {name}: {duplicate_message}")
            continue
        category_id = row_value(row, "id", "category_id", "categoria_id")
        category = find_by_id(store.get("categories", []), category_id) if category_id else find_category_by_name(store, name)
        payload = {
            "name": name,
            "description": row_value(row, "description", "descripcion", default=(category or {}).get("description", "")),
            "imageUrl": row_value(row, "imageUrl", "imagen", "imagen_url", "url_imagen", default=(category or {}).get("imageUrl", "")),
            "status": row_value(row, "status", "estado", default=(category or {}).get("status", "active")) or "active",
            "updatedAt": utc_now(),
        }
        if category:
            before_name = category.get("name", "")
            category.update(payload)
            for product in store.get("products", []):
                if product.get("categoryId") == category.get("id"):
                    product["categoryName"] = category["name"]
            result["updated"] += 1
            bulk_row(result, "updated", row_number, name)
            if before_name != category["name"]:
                bulk_warning(result, row_number, "categoria renombrada.")
        else:
            payload["id"] = next_id("cat", name)
            store.setdefault("categories", []).append(payload)
            result["created"] += 1
            bulk_row(result, "created", row_number, name)
        warn_invalid_urls(result, row_number, "imagen de categoria", [payload.get("imageUrl", "")])
    return result


def import_products_rows(store: dict, rows: list[dict]) -> dict:
    result = blank_bulk_result()
    seen_skus: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=2):
        sku = row_value(row, "sku", "codigo", "codigo_sku").upper()
        title = row_value(row, "title", "nombre", "producto", "nombre_comercial")
        if not sku or not title:
            bulk_error(result, row_number, "producto requiere SKU y nombre.")
            continue
        duplicate_message = duplicate_in_upload(seen_skus, sku, row_number)
        if duplicate_message:
            bulk_error(result, row_number, f"SKU {sku}: {duplicate_message}")
            continue

        existing = find_product_by_sku(store, sku)
        current = existing or {}
        public_price = parse_import_float(
            row_value(row, "publicPriceUsd", "precio_publico_usd", "precio_usd", "precio"),
            float(current.get("publicPriceUsd") or 0),
        )
        original_price = parse_import_float(
            row_value(row, "originalPriceUsd", "precio_anterior_usd", "precio_lista_usd"),
            float(current.get("originalPriceUsd") or public_price),
        )
        b2b_price = parse_import_float(
            row_value(row, "b2bPriceUsd", "precio_b2b_usd", "precio_ferretero_usd"),
            float(current.get("b2bPriceUsd") or public_price),
        )
        discount = parse_import_float(
            row_value(row, "discountPercent", "descuento", "descuento_porcentaje"),
            float(current.get("discountPercent") or 0),
        )
        if public_price <= 0:
            bulk_error(result, row_number, f"SKU {sku} requiere precio_publico_usd mayor a 0.")
            continue
        category = ensure_import_category(
            store,
            row_value(row, "categoryId", "categoria_id", "id_categoria"),
            row_value(row, "categoryName", "category", "categoria", "familia"),
        )
        primary_image = row_value(
            row,
            "imageUrl",
            "imagen_principal",
            "imagen",
            "url_imagen",
            default=current.get("imageUrl", ""),
        )
        gallery_images = parse_import_list(
            row_value(row, "imageUrls", "imagenes", "galeria", "galeria_imagenes")
        )
        if primary_image and primary_image not in gallery_images:
            gallery_images.insert(0, primary_image)
        if not gallery_images:
            gallery_images = list(current.get("imageUrls") or [])
        if not primary_image and gallery_images:
            primary_image = gallery_images[0]
        pdf_urls = parse_import_list(row_value(row, "pdfUrls", "pdfs", "fichas_pdf", "pdf_tecnicos"))
        if not pdf_urls:
            pdf_urls = list(current.get("pdfUrls") or [])
        if not primary_image and not gallery_images:
            bulk_warning(result, row_number, f"SKU {sku} no tiene imagen principal ni galeria.")
        warn_invalid_urls(result, row_number, f"SKU {sku} imagen principal", [primary_image])
        warn_invalid_urls(result, row_number, f"SKU {sku} galeria", gallery_images)
        warn_invalid_urls(result, row_number, f"SKU {sku} PDF tecnico", pdf_urls)

        payload = {
            "sku": sku,
            "title": title,
            "description": row_value(row, "description", "descripcion", default=current.get("description", "")),
            "productType": row_value(row, "productType", "tipo", "tipo_producto", default=current.get("productType", "machine")) or "machine",
            "categoryId": category["id"],
            "categoryName": category["name"],
            "publicPriceUsd": public_price,
            "originalPriceUsd": original_price or public_price,
            "discountPercent": discount,
            "b2bPriceUsd": b2b_price,
            "exchangeRateUsdVes": parse_import_float(
                row_value(row, "exchangeRateUsdVes", "tasa_usd_ves", "tasa"),
                float(current.get("exchangeRateUsdVes") or current_rate()),
            ),
            "stock": parse_import_int(row_value(row, "stock", "stock_inicial", "cantidad"), int(current.get("stock") or 0)),
            "reserved": int(current.get("reserved") or 0),
            "status": row_value(row, "status", "estado", default=current.get("status", "active")) or "active",
            "imageUrl": primary_image,
            "imageUrls": gallery_images,
            "pdfUrls": pdf_urls,
            "variants": parse_import_list(row_value(row, "variants", "variantes", "tallas", "opciones")) or list(current.get("variants") or []),
            "specifications": parse_import_specs(row_value(row, "specifications", "especificaciones")) or dict(current.get("specifications") or {}),
            "requiresQuote": parse_import_bool(row_value(row, "requiresQuote", "requiere_cotizacion"), bool(current.get("requiresQuote", False))),
            "requiresTechnicalValidation": parse_import_bool(
                row_value(row, "requiresTechnicalValidation", "requiere_validacion_tecnica"),
                bool(current.get("requiresTechnicalValidation", False)),
            ),
            "rotationLast30Days": parse_import_int(
                row_value(row, "rotationLast30Days", "rotacion_30_dias", "rotacion"),
                int(current.get("rotationLast30Days") or 0),
            ),
            "updatedAt": utc_now(),
        }
        if existing:
            payload["id"] = existing["id"]
            payload["createdAt"] = existing.get("createdAt", utc_now())
            store["products"] = [payload if item["id"] == existing["id"] else item for item in store.get("products", [])]
            result["updated"] += 1
            bulk_row(result, "updated", row_number, f"{sku} - {title}")
        else:
            payload["id"] = next_id("prod", sku)
            payload["createdAt"] = utc_now()
            store.setdefault("products", []).append(payload)
            result["created"] += 1
            bulk_row(result, "created", row_number, f"{sku} - {title}")
    return result


def import_stock_rows(store: dict, rows: list[dict]) -> dict:
    result = blank_bulk_result()
    reserved_by_product = stock_reserved_quantities(store.get("orders", []))
    seen_skus: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=2):
        sku = row_value(row, "sku", "codigo", "codigo_sku").upper()
        duplicate_message = duplicate_in_upload(seen_skus, sku, row_number)
        if duplicate_message:
            bulk_error(result, row_number, f"SKU {sku}: {duplicate_message}")
            continue
        product = find_product_by_sku(store, sku)
        if not product:
            bulk_error(result, row_number, f"SKU {sku or 'vacio'} no existe.")
            continue
        raw_quantity = row_value(row, "cantidad", "stock", "stock_fisico", "disponible")
        if raw_quantity == "":
            bulk_error(result, row_number, f"SKU {sku} sin cantidad.")
            continue
        quantity = max(parse_import_int(raw_quantity), reserved_by_product.get(product["id"], 0))
        before = int(product.get("stock") or 0)
        product["stock"] = quantity
        product["updatedAt"] = utc_now()
        store.setdefault("stock_movements", []).append(
            {
                "id": next_id("mov", product["sku"]),
                "productId": product["id"],
                "sku": product["sku"],
                "type": row_value(row, "type", "tipo", default="bulk_excel_set") or "bulk_excel_set",
                "quantity": quantity,
                "note": row_value(row, "note", "nota", "motivo", default="Carga masiva Excel/CSV."),
                "createdBy": session.get("admin_name", "Admin"),
                "createdAt": utc_now(),
            }
        )
        action = "updated" if before != quantity else "skipped"
        result[action] += 1
        bulk_row(result, action, row_number, f"{sku}: {before} -> {quantity}")
    return result


def import_sellers_rows(store: dict, rows: list[dict]) -> dict:
    result = blank_bulk_result()
    seen_emails: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=2):
        email = row_value(row, "email", "correo").lower()
        name = row_value(row, "name", "nombre", "vendedor")
        if not email or not name:
            bulk_error(result, row_number, "vendedor requiere nombre y email.")
            continue
        duplicate_message = duplicate_in_upload(seen_emails, email, row_number)
        if duplicate_message:
            bulk_error(result, row_number, f"{email}: {duplicate_message}")
            continue
        user = next((item for item in store.get("admin_users", []) if item.get("email", "").lower() == email), None)
        if user and user.get("role") != "sales":
            bulk_error(result, row_number, f"{email} ya existe con rol administrativo.")
            continue
        password = row_value(row, "password", "contrasena", "clave")
        if password and password_errors(password):
            bulk_error(result, row_number, "la clave no cumple la politica de seguridad.")
            continue
        if not password and not user:
            password = secrets.token_urlsafe(12)
        payload = {
            "name": name,
            "email": email,
            "role": "sales",
            "status": row_value(row, "status", "estado", default=(user or {}).get("status", "active")) or "active",
            "sellerCode": row_value(row, "sellerCode", "codigo_vendedor", default=(user or {}).get("sellerCode", "")).upper(),
            "sellerZone": row_value(row, "sellerZone", "zona", default=(user or {}).get("sellerZone", "")),
            "phone": row_value(row, "phone", "telefono", "whatsapp", default=(user or {}).get("phone", "")),
            "commissionRatePercent": parse_import_float(
                row_value(row, "commissionRatePercent", "comision", "porcentaje_comision"),
                float((user or {}).get("commissionRatePercent") or 0),
            ),
            "salesGoalUsd": parse_import_float(
                row_value(row, "salesGoalUsd", "meta_usd", "meta_ventas_usd"),
                float((user or {}).get("salesGoalUsd") or 0),
            ),
            "updatedAt": utc_now(),
        }
        if user:
            payload["id"] = user["id"]
            payload["createdAt"] = user.get("createdAt", utc_now())
            payload["passwordHash"] = generate_password_hash(password) if password else user.get("passwordHash", "")
            payload["mustChangePassword"] = True if password else bool(user.get("mustChangePassword"))
            store["admin_users"] = [payload if item["id"] == user["id"] else item for item in store.get("admin_users", [])]
            result["updated"] += 1
            bulk_row(result, "updated", row_number, f"{name} - {email}")
        else:
            payload["id"] = next_id("admin", email)
            payload["createdAt"] = utc_now()
            payload["passwordHash"] = generate_password_hash(password)
            payload["mustChangePassword"] = True
            store.setdefault("admin_users", []).append(payload)
            result["created"] += 1
            bulk_row(result, "created", row_number, f"{name} - {email}")
    return result


def import_clients_rows(store: dict, rows: list[dict]) -> dict:
    result = blank_bulk_result()
    can_approve = role_allowed(CREDIT_APPROVAL_ROLES)
    seen_emails: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=2):
        email = row_value(row, "email", "correo").lower()
        business_name = row_value(row, "businessName", "razon_social", "nombre_comercial", "cliente")
        if not email or not business_name:
            bulk_error(result, row_number, "cliente requiere nombre comercial y email.")
            continue
        duplicate_message = duplicate_in_upload(seen_emails, email, row_number)
        if duplicate_message:
            bulk_error(result, row_number, f"{email}: {duplicate_message}")
            continue
        client = next((item for item in store.get("clients", []) if item.get("email", "").lower() == email), None)
        password = row_value(row, "password", "contrasena", "clave")
        if password and password_errors(password):
            bulk_error(result, row_number, "la clave no cumple la politica de seguridad.")
            continue
        if not password and not client:
            password = secrets.token_urlsafe(12)
        seller = find_seller_for_import(store, row)
        credit_requested = parse_import_float(row_value(row, "creditRequestedUsd", "credito_solicitado_usd", "solicitud_credito_usd"), float((client or {}).get("creditRequestedUsd") or 0))
        credit_limit = parse_import_float(row_value(row, "creditLimitUsd", "credito_limite_usd", "cupo_usd", "linea_credito_usd"), float((client or {}).get("creditLimitUsd") or 0))
        credit_status = row_value(row, "creditRequestStatus", "estado_credito", default=(client or {}).get("creditRequestStatus", "none")) or "none"
        credit_enabled = parse_import_bool(row_value(row, "creditEnabled", "credito_aprobado", "linea_activa"), bool((client or {}).get("creditEnabled", False)))
        if credit_limit > 0 and can_approve and credit_enabled:
            credit_status = "approved"
        elif credit_limit > 0 and not can_approve:
            bulk_error(result, row_number, "solo gerente comercial o super admin puede importar cupos de credito aprobados.")
            continue
        terms = [
            int(term)
            for term in re.split(r"[\s,;|/]+", row_value(row, "allowedPaymentTermsDays", "plazos", "plazos_pago", default="0"))
            if term.strip().isdigit() and int(term) in PAYMENT_TERM_OPTIONS
        ] or list((client or {}).get("allowedPaymentTermsDays") or [0])
        payment_term = parse_import_int(row_value(row, "paymentTermsDays", "plazo_default", "dias_credito"), int((client or {}).get("paymentTermsDays") or 0))
        payload = {
            "businessName": business_name,
            "taxId": row_value(row, "taxId", "rif", "rut", default=(client or {}).get("taxId", "")),
            "contactName": row_value(row, "contactName", "contacto", "responsable", default=(client or {}).get("contactName", "")),
            "phone": row_value(row, "phone", "telefono", "whatsapp", default=(client or {}).get("phone", "")),
            "email": email,
            "clientType": row_value(row, "clientType", "tipo_cliente", default=(client or {}).get("clientType", "ferretero")) or "ferretero",
            "status": row_value(row, "status", "estado", default=(client or {}).get("status", "active")) or "active",
            "address": row_value(row, "address", "direccion", default=(client or {}).get("address", "")),
            "state": row_value(row, "state", "estado_ubicacion", "provincia", default=(client or {}).get("state", "")),
            "city": row_value(row, "city", "ciudad", default=(client or {}).get("city", "")),
            "deliveryZone": row_value(row, "deliveryZone", "zona", default=(client or {}).get("deliveryZone", "")),
            "assignedSellerId": (seller or {}).get("id", (client or {}).get("assignedSellerId", "")),
            "assignedSellerName": (seller or {}).get("name", (client or {}).get("assignedSellerName", "")),
            "defaultSaleType": row_value(row, "defaultSaleType", "tipo_venta_default", default=(client or {}).get("defaultSaleType", "cash")) or "cash",
            "allowedPaymentTermsDays": sorted(set(terms)),
            "creditRequestStatus": credit_status,
            "creditRequestedUsd": credit_requested,
            "creditEnabled": credit_enabled and credit_status == "approved",
            "creditLimitUsd": credit_limit if credit_enabled and credit_status == "approved" else float((client or {}).get("creditLimitUsd") or 0),
            "creditUsedUsd": parse_import_float(row_value(row, "creditUsedUsd", "credito_usado_usd"), float((client or {}).get("creditUsedUsd") or 0)),
            "paymentTermsDays": payment_term if credit_status == "approved" else int((client or {}).get("paymentTermsDays") or 0),
            "notes": row_value(row, "notes", "notas", default=(client or {}).get("notes", "")),
            "updatedAt": utc_now(),
        }
        if not payload.get("taxId"):
            bulk_warning(result, row_number, f"{business_name} no tiene RIF/taxId.")
        if not payload.get("contactName"):
            bulk_warning(result, row_number, f"{business_name} no tiene contacto principal.")
        if not payload.get("phone"):
            bulk_warning(result, row_number, f"{business_name} no tiene telefono/WhatsApp.")
        if credit_status == "approved" and can_approve:
            payload["creditApprovedBy"] = session.get("admin_name", "Admin")
            payload["creditApprovedAt"] = utc_now()
        elif client:
            payload["creditApprovedBy"] = client.get("creditApprovedBy", "")
            payload["creditApprovedAt"] = client.get("creditApprovedAt", "")
        if client:
            payload["id"] = client["id"]
            payload["createdAt"] = client.get("createdAt", utc_now())
            payload["passwordHash"] = generate_password_hash(password) if password else client.get("passwordHash", "")
            payload["mustChangePassword"] = True if password else bool(client.get("mustChangePassword"))
            store["clients"] = [payload if item["id"] == client["id"] else item for item in store.get("clients", [])]
            result["updated"] += 1
            bulk_row(result, "updated", row_number, f"{business_name} - {email}")
        else:
            payload["id"] = next_id("client", email)
            payload["createdAt"] = utc_now()
            payload["passwordHash"] = generate_password_hash(password)
            payload["mustChangePassword"] = True
            store.setdefault("clients", []).append(payload)
            result["created"] += 1
            bulk_row(result, "created", row_number, f"{business_name} - {email}")
    return result


def import_announcements_rows(store: dict, rows: list[dict]) -> dict:
    result = blank_bulk_result()
    seen_titles: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=2):
        title = row_value(row, "title", "titulo", "banner")
        if not title:
            bulk_error(result, row_number, "banner requiere titulo.")
            continue
        duplicate_message = duplicate_in_upload(seen_titles, title, row_number)
        if duplicate_message:
            bulk_error(result, row_number, f"banner {title}: {duplicate_message}")
            continue
        announcement_id = row_value(row, "id", "announcement_id", "banner_id")
        announcement = find_by_id(store.get("announcements", []), announcement_id) if announcement_id else next(
            (
                item
                for item in store.get("announcements", [])
                if normalize_import_key(item.get("title", "")) == normalize_import_key(title)
            ),
            None,
        )
        payload = {
            "title": title,
            "body": row_value(row, "body", "mensaje", "descripcion", default=(announcement or {}).get("body", "")),
            "placement": row_value(row, "placement", "ubicacion", default=(announcement or {}).get("placement", "home")) or "home",
            "priority": parse_import_int(row_value(row, "priority", "prioridad"), int((announcement or {}).get("priority") or 50)),
            "ctaLabel": row_value(row, "ctaLabel", "boton", "texto_boton", default=(announcement or {}).get("ctaLabel", "")),
            "ctaUrl": row_value(row, "ctaUrl", "accion", "url_accion", default=(announcement or {}).get("ctaUrl", "")),
            "imageUrl": row_value(row, "imageUrl", "imagen", "imagen_url", default=(announcement or {}).get("imageUrl", "")),
            "startsAt": row_value(row, "startsAt", "inicio", default=(announcement or {}).get("startsAt", utc_now())) or utc_now(),
            "endsAt": row_value(row, "endsAt", "cierre", "fin", default=(announcement or {}).get("endsAt", "")),
            "status": row_value(row, "status", "estado", default=(announcement or {}).get("status", "active")) or "active",
            "updatedAt": utc_now(),
        }
        if not payload.get("imageUrl"):
            bulk_warning(result, row_number, f"banner {title} no tiene imagen de carrusel.")
        warn_invalid_urls(result, row_number, f"banner {title}", [payload.get("imageUrl", "")])
        if announcement:
            payload["id"] = announcement["id"]
            store["announcements"] = [payload if item["id"] == announcement["id"] else item for item in store.get("announcements", [])]
            result["updated"] += 1
            bulk_row(result, "updated", row_number, title)
        else:
            payload["id"] = next_id("ann", title)
            store.setdefault("announcements", []).append(payload)
            result["created"] += 1
            bulk_row(result, "created", row_number, title)
    return result


def import_media_assets_rows(store: dict, rows: list[dict]) -> dict:
    result = blank_bulk_result()
    seen_assets: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=2):
        title = row_value(row, "title", "titulo", "recurso", default="Activo Wulkan")
        asset_url = row_value(row, "url", "assetUrl", "archivo_url", "imagen_url", "pdf_url")
        if not asset_url:
            bulk_error(result, row_number, "recurso requiere URL de imagen o PDF.")
            continue
        duplicate_key = f"{row_value(row, 'sku', 'producto_sku', 'sku_producto')}|{asset_url}"
        duplicate_message = duplicate_in_upload(seen_assets, duplicate_key, row_number)
        if duplicate_message:
            bulk_error(result, row_number, f"recurso {title}: {duplicate_message}")
            continue
        warn_invalid_urls(result, row_number, f"recurso {title}", [asset_url])
        product_id = row_value(row, "productId", "producto_id", "id_producto")
        product = find_by_id(store.get("products", []), product_id) if product_id else find_product_by_sku(
            store,
            row_value(row, "sku", "producto_sku", "sku_producto"),
        )
        asset_type = normalize_import_key(row_value(row, "assetType", "tipo", default="image"))
        asset_type = "pdf" if asset_type in {"pdf", "ficha", "ficha_pdf"} else "image"
        duplicate = next(
            (
                item
                for item in store.get("media_assets", [])
                if item.get("url") == asset_url and item.get("productId", "") == (product or {}).get("id", product_id)
            ),
            None,
        )
        if duplicate:
            duplicate.update({"title": title, "assetType": asset_type, "createdAt": duplicate.get("createdAt", utc_now())})
            result["updated"] += 1
            bulk_row(result, "updated", row_number, f"{title} - {asset_type}")
        else:
            asset = {
                "id": next_id("asset", title),
                "title": title,
                "assetType": asset_type,
                "productId": (product or {}).get("id", product_id),
                "url": asset_url,
                "createdAt": utc_now(),
            }
            store.setdefault("media_assets", []).append(asset)
            result["created"] += 1
            bulk_row(result, "created", row_number, f"{title} - {asset_type}")
        if product:
            if asset_type == "pdf":
                append_unique(product.setdefault("pdfUrls", []), [asset_url])
            else:
                append_unique(product.setdefault("imageUrls", []), [asset_url])
                if not product.get("imageUrl"):
                    product["imageUrl"] = asset_url
            product["updatedAt"] = utc_now()
    return result


def import_service_technicians_rows(store: dict, rows: list[dict]) -> dict:
    result = blank_bulk_result()
    seen_services: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=2):
        name = row_value(row, "name", "nombre", "servicio")
        if not name:
            bulk_error(result, row_number, "servicio tecnico requiere nombre.")
            continue
        duplicate_message = duplicate_in_upload(seen_services, name, row_number)
        if duplicate_message:
            bulk_error(result, row_number, f"servicio tecnico {name}: {duplicate_message}")
            continue
        technician_id = row_value(row, "id", "technician_id", "servicio_id")
        technician = find_by_id(store.get("service_technicians", []), technician_id) if technician_id else next(
            (
                item
                for item in store.get("service_technicians", [])
                if normalize_import_key(item.get("name", "")) == normalize_import_key(name)
            ),
            None,
        )
        payload = {
            "name": name,
            "companyName": row_value(row, "companyName", "empresa", default=(technician or {}).get("companyName", "")),
            "contactName": row_value(row, "contactName", "contacto", default=(technician or {}).get("contactName", "")),
            "phone": row_value(row, "phone", "telefono", default=(technician or {}).get("phone", "")),
            "whatsapp": row_value(row, "whatsapp", default=(technician or {}).get("whatsapp", "")),
            "email": row_value(row, "email", "correo", default=(technician or {}).get("email", "")).lower(),
            "state": row_value(row, "state", "estado_ubicacion", default=(technician or {}).get("state", "")),
            "city": row_value(row, "city", "ciudad", default=(technician or {}).get("city", "")),
            "address": row_value(row, "address", "direccion", default=(technician or {}).get("address", "")),
            "specialties": parse_import_list(row_value(row, "specialties", "especialidades")) or list((technician or {}).get("specialties", [])),
            "coverage": row_value(row, "coverage", "cobertura", "zona", default=(technician or {}).get("coverage", "")),
            "status": row_value(row, "status", "estado", default=(technician or {}).get("status", "active")) or "active",
            "visibleInApp": parse_import_bool(row_value(row, "visibleInApp", "visible_app", "visible"), bool((technician or {}).get("visibleInApp", True))),
            "notes": row_value(row, "notes", "notas", default=(technician or {}).get("notes", "")),
            "updatedAt": utc_now(),
        }
        if not payload.get("phone") and not payload.get("whatsapp"):
            bulk_warning(result, row_number, f"{name} no tiene telefono ni WhatsApp.")
        if payload.get("visibleInApp") and not payload.get("city"):
            bulk_warning(result, row_number, f"{name} visible en app sin ciudad/zona definida.")
        if technician:
            payload["id"] = technician["id"]
            payload["createdAt"] = technician.get("createdAt", utc_now())
            store["service_technicians"] = [
                payload if item["id"] == technician["id"] else item
                for item in store.get("service_technicians", [])
            ]
            result["updated"] += 1
            bulk_row(result, "updated", row_number, name)
        else:
            payload["id"] = next_id("svc", name)
            payload["createdAt"] = utc_now()
            store.setdefault("service_technicians", []).append(payload)
            result["created"] += 1
            bulk_row(result, "created", row_number, name)
    return result


def handle_bulk_import(module: str, entity_type: str, importer, redirect_endpoint: str):
    import_mode = request.form.get("importMode", "import")
    store = load_store()

    if import_mode == "discard":
        draft_id = request.form.get("draftId", "")
        result = blank_bulk_result()
        if finish_import_draft(module, draft_id, "discarded"):
            result["discarded"] = True
            result["message"] = "Previsualizacion descartada."
        else:
            result["errors"] = ["No se pudo descartar la previsualizacion."]
        remember_bulk_result(module, result)
        return redirect(url_for(redirect_endpoint))

    if import_mode == "confirm":
        draft_id = request.form.get("draftId", "")
        draft = load_import_draft(module, draft_id)
        if not draft:
            result = blank_bulk_result()
            result["errors"] = ["La previsualizacion ya expiro o no existe. Vuelve a subir el archivo."]
            remember_bulk_result(module, result)
            return redirect(url_for(redirect_endpoint))

        rows = draft["rows"]
        result = importer(store, rows)
        record_audit_event(
            store,
            "bulk_import_confirm",
            entity_type,
            draft_id,
            f"Carga confirmada {module}: {result['created']} creados, {result['updated']} actualizados.",
            metadata={
                "module": module,
                "draftId": draft_id,
                "created": result.get("created", 0),
                "updated": result.get("updated", 0),
                "skipped": result.get("skipped", 0),
                "errors": result.get("errors", [])[:8],
            },
        )
        save_store(store)
        finish_import_draft(module, draft_id, "confirmed")
        result["confirmed"] = True
        remember_bulk_result(module, result)
        return redirect(url_for(redirect_endpoint))

    try:
        rows = read_tabular_upload(request.files.get("importFile"))
        if import_mode == "preview":
            preview_store = copy.deepcopy(store)
            result = importer(preview_store, rows)
            result["preview"] = True
            result["draftId"] = create_import_draft(module, entity_type, rows, result)
            result["confirmEndpoint"] = request.endpoint
            result["discardEndpoint"] = request.endpoint
            result["expiresInMinutes"] = max(1, IMPORT_DRAFT_TTL_SECONDS // 60)
            remember_bulk_result(module, result)
            return redirect(url_for(redirect_endpoint))

        result = importer(store, rows)
        record_audit_event(
            store,
            "bulk_import",
            entity_type,
            "",
            f"Carga masiva {module}: {result['created']} creados, {result['updated']} actualizados.",
            metadata={
                "module": module,
                "created": result.get("created", 0),
                "updated": result.get("updated", 0),
                "skipped": result.get("skipped", 0),
                "errors": result.get("errors", [])[:8],
            },
        )
        save_store(store)
    except BadRequest as exc:
        result = blank_bulk_result()
        result["errors"] = [exc.description or str(exc)]
    remember_bulk_result(module, result)
    return redirect(url_for(redirect_endpoint))


def order_actor() -> dict:
    return {
        "id": session.get("admin_user_id", ""),
        "name": session.get("admin_name", "Sistema"),
        "role": session.get("admin_role", "system"),
    }


def normalize_order_items(store: dict, raw_items: list[dict]) -> tuple[list[dict], float, bool]:
    items: list[dict] = []
    total_usd = 0.0
    requires_operator_review = False
    for raw_item in raw_items:
        product_id = str(raw_item.get("productId") or "").strip()
        sku = str(raw_item.get("sku") or "").strip()
        product = find_by_id(store.get("products", []), product_id) if product_id else None
        if not product and sku:
            product = next((item for item in store.get("products", []) if item.get("sku") == sku), None)
        quantity = int(raw_item.get("quantity") or 0)
        if quantity <= 0:
            continue
        if product:
            product_id = product.get("id", product_id)
            sku = product.get("sku", sku)
            title = product.get("title", raw_item.get("title", sku))
            unit_price = float(raw_item.get("unitPriceUsd") or product.get("b2bPriceUsd") or product.get("publicPriceUsd") or 0)
            image_url = raw_item.get("imageUrl") or product.get("imageUrl", "")
            requires_quote = bool(product.get("requiresQuote"))
            requires_validation = bool(product.get("requiresTechnicalValidation"))
        else:
            title = str(raw_item.get("title") or sku or product_id or "Producto Wulkan")
            unit_price = float(raw_item.get("unitPriceUsd") or 0)
            image_url = raw_item.get("imageUrl", "")
            requires_quote = bool(raw_item.get("requiresQuote"))
            requires_validation = bool(raw_item.get("requiresTechnicalValidation"))
        line_total = round(unit_price * quantity, 2)
        total_usd += line_total
        requires_operator_review = requires_operator_review or requires_quote or requires_validation
        items.append(
            {
                "productId": product_id,
                "sku": sku,
                "title": title,
                "quantity": quantity,
                "unitPriceUsd": unit_price,
                "lineTotalUsd": line_total,
                "imageUrl": image_url,
                "requiresQuote": requires_quote,
                "requiresTechnicalValidation": requires_validation,
            }
        )
    return items, round(total_usd, 2), requires_operator_review


def build_commercial_order(
    store: dict,
    payload: dict,
    *,
    actor: dict | None = None,
    default_channel: str = "mobile",
) -> tuple[dict | None, str]:
    actor = actor or {"id": "", "name": "Sistema", "role": "system"}
    preview = payload.get("preview") or {}
    customer_payload = payload.get("customer") or {}
    customer_id = str(payload.get("customerId") or customer_payload.get("id") or "").strip()
    client = find_by_id(store.get("clients", []), customer_id)
    if not client:
        return None, "Cliente no encontrado."
    if client.get("mustChangePassword") and actor.get("role") == "client":
        return None, "Debes cambiar la contrasena temporal antes de crear ordenes."

    items, calculated_total_usd, requires_operator_review = normalize_order_items(
        store,
        payload.get("items") or [],
    )
    if not items:
        return None, "La orden no tiene productos validos."

    total_usd = float(preview.get("totalUsd") or preview.get("subtotalUsd") or calculated_total_usd)
    exchange_rate = float(preview.get("exchangeRateUsdVes") or current_rate())
    total_ves = float(preview.get("totalVes") or round(total_usd * exchange_rate, 2))
    movements = store.get("credit_movements", [])
    credit_before = credit_available(client, store.get("orders", []), movements)

    requested_sale_type = (
        payload.get("saleType")
        or payload.get("paymentMethod")
        or client.get("defaultSaleType")
        or "cash"
    )
    sale_type = requested_sale_type if requested_sale_type in dict(SALE_TYPE_OPTIONS) else "cash"
    allowed_terms = [
        int(term)
        for term in client.get("allowedPaymentTermsDays", [0])
        if str(term).isdigit()
    ] or [0]
    payment_term_days = int(payload.get("paymentTermDays") or client.get("paymentTermsDays") or 0)
    if sale_type == "term_credit" and payment_term_days not in allowed_terms:
        return None, "El plazo solicitado no esta autorizado para este cliente."
    if sale_type == "credit_line" and payment_term_days == 0:
        payment_term_days = int(client.get("paymentTermsDays") or 0)
    due_date = add_days_iso(utc_now(), payment_term_days) if payment_term_days > 0 else ""

    seller_id = client.get("assignedSellerId", "")
    seller_name = client.get("assignedSellerName", "") or seller_name_for(store, seller_id)
    commission_rate = seller_commission_rate(store, seller_id) if seller_id else 0.0
    commission_usd = round(total_usd * commission_rate / 100, 2)
    can_use_credit = (
        sale_type == "credit_line"
        and client.get("status") == "active"
        and client.get("creditEnabled")
        and credit_before >= total_usd
    )
    credit_after = max(0.0, round(credit_before - total_usd, 2)) if can_use_credit else credit_before
    credit_status = "approved" if can_use_credit else "manual_review"
    if client.get("status") != "active":
        credit_status = "client_not_active"
    elif sale_type == "cash":
        credit_status = "without_credit"
    elif not client.get("creditEnabled"):
        credit_status = "without_credit"

    order_id = next_id("ord-mobile" if default_channel == "mobile" else "ord-assisted", client.get("businessName", "orden"))
    status = "approved_with_credit" if can_use_credit and not requires_operator_review else "credit_review"
    order = {
        "id": order_id,
        "orderId": order_id,
        "customerId": client["id"],
        "customer": {
            "id": client["id"],
            "name": client.get("businessName", "Cliente Wulkan"),
            "businessName": client.get("businessName", "Cliente Wulkan"),
            "taxId": client.get("taxId", ""),
            "phone": client.get("phone", ""),
            "sellerId": seller_id,
            "sellerName": seller_name,
        },
        "items": items,
        "totalUsd": total_usd,
        "totalVes": total_ves,
        "exchangeRateUsdVes": exchange_rate,
        "saleType": sale_type,
        "paymentTermDays": payment_term_days,
        "dueDate": due_date,
        "sellerId": seller_id,
        "sellerName": seller_name,
        "salesChannel": payload.get("salesChannel", default_channel),
        "createdById": actor.get("id", ""),
        "createdByName": actor.get("name", "Sistema"),
        "createdByRole": actor.get("role", "system"),
        "commissionRatePercent": commission_rate,
        "commissionUsd": commission_usd,
        "commissionStatus": "commission_pending" if commission_usd else "commission_cancelled",
        "commissionPaidAt": "",
        "commissionPaidBy": "",
        "creditBeforeUsd": credit_before,
        "creditAfterUsd": credit_after,
        "creditStatus": credit_status,
        "paidUsd": 0.0,
        "balanceUsd": total_usd,
        "paymentStatus": "pending",
        "status": status,
        "statusHistory": [
            {
                "status": status,
                "note": f"Orden creada por {actor.get('name', 'Sistema')} con venta {sale_type_label(sale_type)}.",
                "adminUserId": actor.get("id", ""),
                "adminName": actor.get("name", "Sistema"),
                "createdAt": utc_now(),
            }
        ],
        "notes": str(payload.get("notes") or "").strip(),
        "createdAt": utc_now(),
        "updatedAt": utc_now(),
    }
    if status == "approved_with_credit" and not reserve_stock_for_order(store, order):
        order["status"] = "credit_review"
        order["creditStatus"] = "manual_review"
        order["statusHistory"][0]["status"] = "credit_review"
        order["statusHistory"][0]["note"] = "Orden creada; stock requiere revision operativa."
    return order, ""


def record_audit_event(
    store: dict,
    action: str,
    entity_type: str,
    entity_id: str = "",
    detail: str = "",
    metadata: dict | None = None,
    actor: dict | None = None,
) -> None:
    actor_payload = actor or {}
    actor_name = actor_payload.get("name") or session.get("admin_name", "Sistema")
    event = {
        "id": next_id("audit", f"{action}-{entity_type}-{entity_id or actor_name}"),
        "actorId": actor_payload.get("id") or session.get("admin_user_id", ""),
        "actorName": actor_name,
        "actorRole": actor_payload.get("role") or session.get("admin_role", ""),
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


AUDIT_REDACTED_KEYS = {
    "password",
    "passwordHash",
    "currentPassword",
    "newPassword",
    "accessToken",
    "secret",
    "token",
}


def audit_snapshot(value):
    if isinstance(value, dict):
        snapshot = {}
        for key, item in value.items():
            if key in AUDIT_REDACTED_KEYS or key.lower().endswith("secret"):
                snapshot[key] = "[redacted]"
            else:
                snapshot[key] = audit_snapshot(item)
        return snapshot
    if isinstance(value, list):
        return [audit_snapshot(item) for item in value[:50]]
    return value


def changed_fields(before: dict | None, after: dict | None) -> list[str]:
    before_snapshot = audit_snapshot(before or {})
    after_snapshot = audit_snapshot(after or {})
    keys = set(before_snapshot) | set(after_snapshot)
    return sorted(key for key in keys if before_snapshot.get(key) != after_snapshot.get(key))


def record_change_event(
    store: dict,
    action: str,
    entity_type: str,
    entity_id: str,
    detail: str,
    before: dict | None,
    after: dict | None,
    actor: dict | None = None,
) -> None:
    record_audit_event(
        store,
        action,
        entity_type,
        entity_id,
        detail,
        metadata={
            "changedFields": changed_fields(before, after),
            "before": audit_snapshot(before or {}),
            "after": audit_snapshot(after or {}),
        },
        actor=actor,
    )


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
    enriched["creditRequestedUsd"] = float(enriched.get("creditRequestedUsd") or 0)
    enriched["allowedPaymentTermsDays"] = [
        int(term)
        for term in enriched.get("allowedPaymentTermsDays", [0])
        if str(term).strip().isdigit()
    ] or [0]
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
    elif enriched.get("creditRequestStatus") == "pending":
        enriched["creditStatus"] = "credit_requested"
    elif enriched.get("creditRequestStatus") == "rejected":
        enriched["creditStatus"] = "rejected"
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
    enriched["saleType"] = enriched.get("saleType", "cash")
    enriched["saleTypeLabel"] = sale_type_label(enriched["saleType"])
    enriched["paymentTermDays"] = int(enriched.get("paymentTermDays") or 0)
    if not enriched.get("dueDate") and enriched["paymentTermDays"] > 0:
        enriched["dueDate"] = add_days_iso(enriched.get("createdAt"), enriched["paymentTermDays"])
    due_status, due_days = order_due_status(enriched)
    enriched["dueStatus"] = due_status
    enriched["dueDays"] = due_days
    enriched["sellerName"] = enriched.get("sellerName") or "Sin vendedor"
    enriched["commissionRatePercent"] = float(enriched.get("commissionRatePercent") or 0)
    enriched["commissionUsd"] = float(enriched.get("commissionUsd") or 0)
    enriched["commissionStatus"] = enriched.get("commissionStatus") or "commission_pending"
    enriched["commissionStatusLabel"] = commission_status_label(enriched["commissionStatus"])
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

    try:
        return save_uploaded_file(
            file_storage=file_storage,
            folder=folder,
            upload_folder=Path(app.config["UPLOAD_FOLDER"]),
            storage_backend=app.config.get("STORAGE_BACKEND", "local"),
            public_base_url=app.config.get("STORAGE_PUBLIC_BASE_URL", ""),
            s3_bucket=app.config.get("S3_BUCKET", ""),
            s3_region=app.config.get("S3_REGION", "us-east-1"),
            s3_endpoint_url=app.config.get("S3_ENDPOINT_URL", ""),
            s3_prefix=app.config.get("S3_PREFIX", "wulkan"),
            s3_acl=app.config.get("S3_ACL", ""),
        )
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


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
    uploaded_gallery = [
        save_upload(file_storage, "products")
        for file_storage in request.files.getlist("galleryFiles")
        if file_storage and file_storage.filename
    ]

    if uploaded_image:
        primary_image = uploaded_image
    if primary_image and primary_image not in image_urls:
        image_urls.insert(0, primary_image)
    append_unique(image_urls, [url for url in uploaded_gallery if url])
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


def credential_form_error(password: str, existing: dict | None = None) -> str:
    if existing is None and not password:
        return "Debes definir una contrasena temporal segura."
    if not password:
        return ""
    errors = password_errors(password)
    if errors:
        return " ".join(errors)
    return ""


def admin_user_form_error(store: dict, existing: dict | None = None) -> str:
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    if not email:
        return "El email del usuario admin es obligatorio."
    duplicated = any(
        user.get("email", "").lower() == email
        and (existing is None or user.get("id") != existing.get("id"))
        for user in store["admin_users"]
    )
    if duplicated:
        return f"Ya existe un usuario admin con el email {email}."
    return credential_form_error(password, existing)


def seller_form_error(store: dict, existing: dict | None = None) -> str:
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    if not email:
        return "El email del vendedor es obligatorio."
    duplicated = any(
        user.get("email", "").lower() == email
        and (existing is None or user.get("id") != existing.get("id"))
        for user in store["admin_users"]
    )
    if duplicated:
        return f"Ya existe un usuario con el email {email}."
    return credential_form_error(password, existing)


def client_form_error(store: dict, existing: dict | None = None) -> str:
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    if not email:
        return "El email del cliente ferretero es obligatorio."
    duplicated = any(
        client.get("email", "").lower() == email
        and (existing is None or client.get("id") != existing.get("id"))
        for client in store["clients"]
    )
    if duplicated:
        return f"Ya existe un cliente con el email {email}."
    return credential_form_error(password, existing)


def selected_payment_terms() -> list[int]:
    terms = []
    for raw_value in request.form.getlist("allowedPaymentTermsDays"):
        try:
            value = int(raw_value)
        except ValueError:
            continue
        if value in PAYMENT_TERM_OPTIONS and value not in terms:
            terms.append(value)
    return terms or [0]


def admin_user_payload(existing: dict | None = None) -> dict:
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    now = utc_now()
    payload = {
        "name": request.form.get("name", "").strip(),
        "email": email,
        "role": request.form.get("role", "operator"),
        "status": request.form.get("status", "active"),
        "sellerCode": request.form.get("sellerCode", "").strip().upper(),
        "sellerZone": request.form.get("sellerZone", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "commissionRatePercent": float(request.form.get("commissionRatePercent") or (existing or {}).get("commissionRatePercent") or 0),
        "salesGoalUsd": float(request.form.get("salesGoalUsd") or (existing or {}).get("salesGoalUsd") or 0),
        "updatedAt": now,
    }
    if existing is None:
        payload["id"] = next_id("admin", email)
        payload["createdAt"] = now
        payload["passwordHash"] = generate_password_hash(password)
        payload["mustChangePassword"] = True
    else:
        payload["id"] = existing["id"]
        payload["createdAt"] = existing.get("createdAt", now)
        payload["passwordHash"] = (
            generate_password_hash(password) if password else existing.get("passwordHash", "")
        )
        payload["mustChangePassword"] = True if password else bool(existing.get("mustChangePassword"))
    return payload


def client_payload(existing: dict | None = None) -> dict:
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    now = utc_now()
    active_store = load_store()
    seller_id = request.form.get("assignedSellerId", "").strip()
    current_seller_id, current_seller_name = current_seller_assignment(active_store)
    if current_seller_id:
        seller_id = current_seller_id
    seller_name = seller_name_for(active_store, seller_id) if seller_id else current_seller_name

    approval_allowed = role_allowed(CREDIT_APPROVAL_ROLES)
    requested_credit_status = request.form.get("creditRequestStatus", "none")
    existing_credit_status = (existing or {}).get("creditRequestStatus", "none")
    credit_enabled = (existing or {}).get("creditEnabled", False)
    credit_limit = float((existing or {}).get("creditLimitUsd") or 0)
    payment_terms_days = int((existing or {}).get("paymentTermsDays") or 0)
    credit_requested = float(request.form.get("creditRequestedUsd") or (existing or {}).get("creditRequestedUsd") or 0)

    if approval_allowed:
        credit_enabled = request.form.get("creditEnabled") == "on" and requested_credit_status == "approved"
        credit_limit = float(request.form.get("creditLimitUsd") or 0)
        payment_terms_days = int(request.form.get("paymentTermsDays") or 0)
        if credit_enabled:
            requested_credit_status = "approved"
    else:
        if existing is None:
            requested_credit_status = "pending" if request.form.get("requestCredit") == "on" else "none"
            credit_enabled = False
            credit_limit = 0.0
            payment_terms_days = 0
        else:
            requested_credit_status = existing_credit_status

    payload = {
        "businessName": request.form.get("businessName", "").strip(),
        "taxId": request.form.get("taxId", "").strip(),
        "contactName": request.form.get("contactName", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "email": email,
        "clientType": request.form.get("clientType", "ferretero"),
        "status": request.form.get("status", "active"),
        "address": request.form.get("address", "").strip(),
        "state": request.form.get("state", "").strip(),
        "city": request.form.get("city", "").strip(),
        "deliveryZone": request.form.get("deliveryZone", "").strip(),
        "assignedSellerId": seller_id,
        "assignedSellerName": seller_name,
        "defaultSaleType": request.form.get("defaultSaleType", "cash"),
        "allowedPaymentTermsDays": selected_payment_terms(),
        "creditRequestStatus": requested_credit_status,
        "creditRequestedUsd": credit_requested,
        "creditEnabled": credit_enabled,
        "creditLimitUsd": credit_limit,
        "creditUsedUsd": float(request.form.get("creditUsedUsd") or (existing or {}).get("creditUsedUsd") or 0),
        "paymentTermsDays": payment_terms_days,
        "notes": request.form.get("notes", "").strip(),
        "updatedAt": now,
    }
    if approval_allowed and requested_credit_status == "approved":
        payload["creditApprovedBy"] = session.get("admin_name", "Admin")
        payload["creditApprovedAt"] = now
    elif existing:
        payload["creditApprovedBy"] = existing.get("creditApprovedBy", "")
        payload["creditApprovedAt"] = existing.get("creditApprovedAt", "")
    if existing is None:
        payload["id"] = next_id("client", email or payload["businessName"])
        payload["createdAt"] = now
        payload["passwordHash"] = generate_password_hash(password)
        payload["mustChangePassword"] = True
    else:
        payload["id"] = existing["id"]
        payload["createdAt"] = existing.get("createdAt", now)
        payload["passwordHash"] = (
            generate_password_hash(password) if password else existing.get("passwordHash", "")
        )
        payload["mustChangePassword"] = True if password else bool(existing.get("mustChangePassword"))
    return payload


def clients_page_context(store: dict, error: str = "") -> dict:
    clients_list = [
        enrich_client(client, store["orders"], store.get("credit_movements", []))
        for client in visible_clients_for_current_user(store)
    ]
    metrics = {
        "clients": len(clients_list),
        "active": sum(1 for client in clients_list if client.get("status") == "active"),
        "credit_enabled": sum(1 for client in clients_list if client.get("creditEnabled")),
        "credit_requested": sum(1 for client in clients_list if client.get("creditRequestStatus") == "pending"),
        "credit_available": sum(float(client.get("creditAvailableUsd") or 0) for client in clients_list),
        "credit_exposure": sum(float(client.get("creditExposureUsd") or 0) for client in clients_list),
    }
    return {
        "clients": sorted(clients_list, key=lambda item: item.get("businessName", "")),
        "sellers": sales_users(store),
        "payment_terms": PAYMENT_TERM_OPTIONS,
        "sale_type_options": SALE_TYPE_OPTIONS,
        "can_approve_credit": role_allowed(CREDIT_APPROVAL_ROLES),
        "metrics": metrics,
        "error": error,
        "bulk_result": consume_bulk_result("clients") if not error else None,
    }


def enrich_seller(store: dict, seller: dict) -> dict:
    enriched = dict(seller)
    seller_id = enriched.get("id", "")
    movements = store.get("credit_movements", [])
    seller_orders = [
        enrich_order(order, movements)
        for order in store.get("orders", [])
        if order.get("sellerId") == seller_id
    ]
    enriched["clientsCount"] = sum(
        1
        for client in store.get("clients", [])
        if client.get("assignedSellerId") == seller_id
    )
    enriched["ordersCount"] = len(seller_orders)
    enriched["salesUsd"] = round(sum(float(order.get("totalUsd") or 0) for order in seller_orders), 2)
    enriched["openOrders"] = sum(1 for order in seller_orders if order.get("balanceUsd", 0) > 0)
    enriched["commissionUsd"] = round(sum(float(order.get("commissionUsd") or 0) for order in seller_orders), 2)
    enriched["commissionPendingUsd"] = round(
        sum(
            float(order.get("commissionUsd") or 0)
            for order in seller_orders
            if order.get("commissionStatus") == "commission_pending"
        ),
        2,
    )
    return enriched


def sellers_page_context(store: dict, error: str = "") -> dict:
    sellers = [enrich_seller(store, seller) for seller in sales_users(store)]
    metrics = {
        "sellers": len(sellers),
        "clients": sum(int(seller.get("clientsCount") or 0) for seller in sellers),
        "sales": sum(float(seller.get("salesUsd") or 0) for seller in sellers),
        "commission_pending": sum(float(seller.get("commissionPendingUsd") or 0) for seller in sellers),
    }
    return {
        "sellers": sellers,
        "metrics": metrics,
        "error": error,
        "bulk_result": consume_bulk_result("sellers") if not error else None,
    }


def assisted_order_page_context(store: dict, error: str = "") -> dict:
    clients_list = [
        enrich_client(client, store.get("orders", []), store.get("credit_movements", []))
        for client in visible_clients_for_current_user(store)
        if client.get("status") == "active"
    ]
    products = [
        enrich_inventory_product(product, store.get("orders", []))
        for product in store.get("products", [])
        if product.get("status") == "active"
    ]
    return {
        "clients": sorted(clients_list, key=lambda item: item.get("businessName", "")),
        "products": sorted(products, key=lambda item: item.get("title", "")),
        "sale_type_options": SALE_TYPE_OPTIONS,
        "payment_terms": PAYMENT_TERM_OPTIONS,
        "error": error,
    }


def assisted_order_payload_from_form() -> dict:
    raw_items: list[dict] = []
    for index in range(1, 7):
        product_id = request.form.get(f"productId{index}", "").strip()
        quantity = request.form.get(f"quantity{index}", "").strip()
        if not product_id or not quantity:
            continue
        raw_items.append({"productId": product_id, "quantity": quantity})
    return {
        "customerId": request.form.get("customerId", "").strip(),
        "items": raw_items,
        "saleType": request.form.get("saleType", "cash"),
        "paymentTermDays": request.form.get("paymentTermDays", "0"),
        "salesChannel": "seller_assisted",
        "notes": request.form.get("notes", "").strip(),
        "preview": {"exchangeRateUsdVes": current_rate()},
    }


def commissions_page_context(store: dict) -> dict:
    movements = store.get("credit_movements", [])
    orders = [
        enrich_order(order, movements)
        for order in sorted(visible_orders_for_current_user(store), key=lambda item: item.get("createdAt", ""), reverse=True)
        if float(order.get("commissionUsd") or 0) > 0
    ]
    metrics = {
        "pending": sum(float(order.get("commissionUsd") or 0) for order in orders if order.get("commissionStatus") == "commission_pending"),
        "approved": sum(float(order.get("commissionUsd") or 0) for order in orders if order.get("commissionStatus") == "commission_approved"),
        "paid": sum(float(order.get("commissionUsd") or 0) for order in orders if order.get("commissionStatus") == "commission_paid"),
        "cancelled": sum(float(order.get("commissionUsd") or 0) for order in orders if order.get("commissionStatus") == "commission_cancelled"),
    }
    return {
        "orders": orders,
        "metrics": metrics,
        "can_manage_commissions": role_allowed(COMMISSION_MANAGEMENT_ROLES),
    }


def service_technician_payload(existing: dict | None = None) -> dict:
    name = request.form.get("name", "").strip()
    now = utc_now()
    payload = {
        "name": name,
        "companyName": request.form.get("companyName", "").strip(),
        "contactName": request.form.get("contactName", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "whatsapp": request.form.get("whatsapp", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "state": request.form.get("state", "").strip(),
        "city": request.form.get("city", "").strip(),
        "address": request.form.get("address", "").strip(),
        "specialties": split_lines(request.form.get("specialties", "")),
        "coverage": request.form.get("coverage", "").strip(),
        "status": request.form.get("status", "active"),
        "visibleInApp": request.form.get("visibleInApp") == "on",
        "notes": request.form.get("notes", "").strip(),
        "updatedAt": now,
    }
    if existing is None:
        payload["id"] = next_id("svc", name)
        payload["createdAt"] = now
    else:
        payload["id"] = existing["id"]
        payload["createdAt"] = existing.get("createdAt", now)
    return payload


def service_technicians_page_context(store: dict, error: str = "") -> dict:
    technicians = sorted(
        [item for item in store.get("service_technicians", []) if item.get("status") != "deleted"],
        key=lambda item: (item.get("state", ""), item.get("city", ""), item.get("name", "")),
    )
    metrics = {
        "technicians": len(technicians),
        "visible": sum(1 for item in technicians if item.get("visibleInApp")),
        "active": sum(1 for item in technicians if item.get("status") == "active"),
        "states": len({item.get("state", "") for item in technicians if item.get("state")}),
    }
    return {
        "technicians": technicians,
        "metrics": metrics,
        "error": error,
        "bulk_result": consume_bulk_result("service_technicians") if not error else None,
    }


def active_announcements(placement: str | None = None, store: dict | None = None) -> list[dict]:
    store = store or load_store()
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
        "sellers": len(sales_users(store)),
        "credit_requested": sum(1 for client in clients_list if client.get("creditRequestStatus") == "pending"),
        "credit_available": sum(float(client.get("creditAvailableUsd") or 0) for client in clients_list),
        "credit_exposure": sum(float(client.get("creditExposureUsd") or 0) for client in clients_list),
        "low_stock": sum(1 for product in products if int(product.get("availableStock") or 0) <= 5),
        "orders": len(orders),
        "gross_revenue": gross_revenue,
        "commission_pending": sum(
            float(order.get("commissionUsd") or 0)
            for order in enriched_orders
            if order.get("commissionStatus") == "commission_pending"
        ),
        "announcements": len(store["announcements"]),
    }
    return render_template(
        "dashboard.html",
        metrics=metrics,
        stock_health=stock_health(products),
        rotation_chart=rotation_chart(products),
        recent_orders=sorted(enriched_orders, key=lambda item: item.get("createdAt", ""), reverse=True)[:6],
    )


@app.get("/plantillas")
@require_roles(*WEB_ADMIN_ROLES)
def import_templates():
    template_groups = visible_import_template_groups()
    return render_template(
        "import_templates.html",
        template_groups=template_groups,
        total_templates=sum(len(group["items"]) for group in template_groups),
    )


@app.get("/plantillas/<template_key>.<file_format>")
@require_roles(*WEB_ADMIN_ROLES)
def download_import_template(template_key: str, file_format: str):
    spec = IMPORT_TEMPLATE_INDEX.get(template_key)
    if not spec:
        raise BadRequest("Plantilla no encontrada.")
    if not can_access_module(spec["module"]):
        return forbidden_response()

    normalized_format = file_format.strip().lower()
    if normalized_format == "csv":
        return build_csv_template(spec)
    if normalized_format == "xlsx":
        return build_xlsx_template(spec)
    raise BadRequest("Formato no soportado. Descarga xlsx o csv.")


@app.route("/admin-users", methods=["GET", "POST"])
@require_roles("super_admin")
def admin_users():
    store = load_store()
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        error = admin_user_form_error(store)
        if error:
            return render_template(
                "admin_users.html",
                users=web_admin_users(store),
                error=error,
            )
        user = admin_user_payload()
        store["admin_users"].append(user)
        record_audit_event(store, "create", "admin_user", user["id"], f"Usuario admin creado: {email}.")
        save_store(store)
        return redirect(url_for("admin_users"))

    return render_template(
        "admin_users.html",
        users=web_admin_users(store),
    )


@app.post("/admin-users/<user_id>/edit")
@require_roles("super_admin")
def admin_user_edit(user_id: str):
    store = load_store()
    user = find_by_id(store["admin_users"], user_id)
    if user and user.get("role") == "sales":
        return forbidden_response()
    if user:
        error = admin_user_form_error(store, user)
        if error:
            return render_template(
                "admin_users.html",
                users=web_admin_users(store),
                error=error,
            )
        before = copy.deepcopy(user)
        updated = admin_user_payload(user)
        store["admin_users"] = [updated if item["id"] == user_id else item for item in store["admin_users"]]
        record_change_event(
            store,
            "update",
            "admin_user",
            user_id,
            f"Usuario admin actualizado: {updated['email']}.",
            before,
            updated,
        )
        save_store(store)
    return redirect(url_for("admin_users"))


@app.post("/admin-users/<user_id>/delete")
@require_roles("super_admin")
def admin_user_delete(user_id: str):
    store = load_store()
    user = find_by_id(store.get("admin_users", []), user_id)
    if not user or user.get("role") == "sales" or user_id == session.get("admin_user_id"):
        return redirect(url_for("admin_users"))
    before = copy.deepcopy(user)
    store["admin_users"] = [item for item in store.get("admin_users", []) if item.get("id") != user_id]
    record_change_event(
        store,
        "delete",
        "admin_user",
        user_id,
        f"Usuario admin eliminado: {user.get('email', user_id)}.",
        before,
        None,
    )
    save_store(store)
    return redirect(url_for("admin_users"))


@app.route("/sellers", methods=["GET", "POST"])
@require_roles("super_admin", "commercial_manager", "operator", "readonly")
def sellers():
    store = load_store()
    if request.method == "POST":
        if not role_allowed(WRITE_ROLES):
            return forbidden_response()
        error = seller_form_error(store)
        if error:
            return render_template("sellers.html", **sellers_page_context(store, error))
        seller = admin_user_payload()
        seller["role"] = "sales"
        if not seller.get("sellerCode"):
            seller["sellerCode"] = seller["id"].replace("admin-", "VEN-").upper()[:24]
        store["admin_users"].append(seller)
        record_audit_event(store, "create", "seller", seller["id"], f"Vendedor creado: {seller['name']}.")
        save_store(store)
        return redirect(url_for("sellers"))

    return render_template("sellers.html", **sellers_page_context(store))


@app.post("/sellers/import")
@require_roles("super_admin", "commercial_manager", "operator")
def sellers_import():
    return handle_bulk_import("sellers", "seller", import_sellers_rows, "sellers")


@app.post("/sellers/<seller_id>/edit")
@require_roles("super_admin", "commercial_manager", "operator")
def seller_edit(seller_id: str):
    store = load_store()
    seller = find_by_id(store["admin_users"], seller_id)
    if seller and seller.get("role") == "sales":
        error = seller_form_error(store, seller)
        if error:
            return render_template("sellers.html", **sellers_page_context(store, error))
        before = copy.deepcopy(seller)
        updated = admin_user_payload(seller)
        updated["role"] = "sales"
        store["admin_users"] = [
            updated if item["id"] == seller_id else item
            for item in store["admin_users"]
        ]
        for client in store.get("clients", []):
            if client.get("assignedSellerId") == seller_id:
                client["assignedSellerName"] = updated.get("name", "")
        for order in store.get("orders", []):
            if order.get("sellerId") == seller_id:
                order["sellerName"] = updated.get("name", "")
        record_change_event(
            store,
            "update",
            "seller",
            seller_id,
            f"Vendedor actualizado: {updated['name']}.",
            before,
            updated,
        )
        save_store(store)
    return redirect(url_for("sellers"))


@app.post("/sellers/<seller_id>/delete")
@require_roles("super_admin")
def seller_delete(seller_id: str):
    store = load_store()
    seller = find_by_id(store.get("admin_users", []), seller_id)
    if not seller or seller.get("role") != "sales":
        return redirect(url_for("sellers"))
    before = copy.deepcopy(seller)
    has_clients = any(client.get("assignedSellerId") == seller_id for client in store.get("clients", []))
    has_orders = any(order.get("sellerId") == seller_id for order in store.get("orders", []))
    if has_clients or has_orders:
        seller["status"] = "inactive"
        seller["updatedAt"] = utc_now()
        after = seller
    else:
        store["admin_users"] = [item for item in store.get("admin_users", []) if item.get("id") != seller_id]
        after = None
    record_change_event(
        store,
        "delete",
        "seller",
        seller_id,
        f"Vendedor {'desactivado' if after else 'eliminado'}: {before.get('name', seller_id)}.",
        before,
        after,
    )
    save_store(store)
    return redirect(url_for("sellers"))


@app.route("/clients", methods=["GET", "POST"])
@require_roles("super_admin", "commercial_manager", "operator", "readonly")
def clients():
    store = load_store()
    if request.method == "POST":
        if not role_allowed(SALES_ROLES):
            return forbidden_response()
        email = request.form.get("email", "").strip().lower()
        error = client_form_error(store)
        if error:
            return render_template("clients.html", **clients_page_context(store, error))
        client = client_payload()
        store["clients"].append(client)
        record_audit_event(store, "create", "client", client["id"], f"Cliente creado: {client['businessName']}.")
        save_store(store)
        return redirect(url_for("clients"))

    return render_template("clients.html", **clients_page_context(store))


@app.post("/clients/import")
@require_roles("super_admin", "commercial_manager", "operator")
def clients_import():
    return handle_bulk_import("clients", "client", import_clients_rows, "clients")


@app.post("/clients/<client_id>/edit")
@require_roles("super_admin", "commercial_manager", "operator")
def client_edit(client_id: str):
    store = load_store()
    client = find_by_id(store["clients"], client_id)
    if not can_access_client_record(client):
        return forbidden_response()
    if client:
        error = client_form_error(store, client)
        if error:
            return render_template("clients.html", **clients_page_context(store, error))
        before = copy.deepcopy(client)
        updated = client_payload(client)
        store["clients"] = [updated if item["id"] == client_id else item for item in store["clients"]]
        record_change_event(
            store,
            "update",
            "client",
            client_id,
            f"Cliente actualizado: {updated['businessName']}.",
            before,
            updated,
        )
        save_store(store)
    return redirect(url_for("clients"))


@app.post("/clients/<client_id>/delete")
@require_roles("super_admin")
def client_delete(client_id: str):
    store = load_store()
    client = find_by_id(store.get("clients", []), client_id)
    if not client:
        return redirect(url_for("clients"))
    before = copy.deepcopy(client)
    has_orders = any(order.get("customerId") == client_id for order in store.get("orders", []))
    if has_orders:
        client["status"] = "inactive"
        client["updatedAt"] = utc_now()
        after = client
    else:
        store["clients"] = [item for item in store.get("clients", []) if item.get("id") != client_id]
        after = None
    record_change_event(
        store,
        "delete",
        "client",
        client_id,
        f"Cliente {'desactivado' if after else 'eliminado'}: {before.get('businessName', client_id)}.",
        before,
        after,
    )
    save_store(store)
    return redirect(url_for("clients"))


@app.get("/products")
@require_roles("super_admin", "commercial_manager", "operator", "inventory", "readonly")
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
    return render_template("products.html", products=products, query=query, bulk_result=consume_bulk_result("products"))


@app.post("/products/import")
@require_roles("super_admin", "operator", "inventory")
def products_import():
    return handle_bulk_import("products", "product", import_products_rows, "products")


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

        before = copy.deepcopy(product)
        updated = product_payload(store, product)
        store["products"] = [updated if item["id"] == product_id else item for item in store["products"]]
        record_change_event(
            store,
            "update",
            "product",
            product_id,
            f"Producto actualizado: {updated['sku']}.",
            before,
            updated,
        )
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
@require_roles("super_admin")
def product_delete(product_id: str):
    store = load_store()
    product = find_by_id(store["products"], product_id)
    store["products"] = [product for product in store["products"] if product["id"] != product_id]
    record_change_event(
        store,
        "delete",
        "product",
        product_id,
        f"Producto eliminado: {(product or {}).get('sku', product_id)}.",
        product,
        None,
    )
    save_store(store)
    return redirect(url_for("products"))


@app.route("/stock", methods=["GET", "POST"])
@require_roles("super_admin", "operator", "inventory", "readonly")
def stock():
    store = load_store()
    if request.method == "POST":
        if not role_allowed(INVENTORY_ROLES):
            return forbidden_response()
        stock_before = {
            product["id"]: {
                "sku": product.get("sku", ""),
                "stock": int(product.get("stock") or 0),
            }
            for product in store.get("products", [])
        }
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
        stock_after = {
            product["id"]: {
                "sku": product.get("sku", ""),
                "stock": int(product.get("stock") or 0),
            }
            for product in store.get("products", [])
        }
        record_change_event(
            store,
            "update",
            "stock",
            "",
            "Stock actualizado desde panel.",
            stock_before,
            stock_after,
        )
        save_store(store)
        return redirect(url_for("stock"))

    products = [enrich_inventory_product(product, store["orders"]) for product in store["products"]]
    return render_template(
        "stock.html",
        products=products,
        movements=list(reversed(store["stock_movements"][-20:])),
        rotation_chart=rotation_chart(products),
        bulk_result=consume_bulk_result("stock"),
    )


@app.post("/stock/import")
@require_roles("super_admin", "operator", "inventory")
def stock_import():
    return handle_bulk_import("stock", "stock", import_stock_rows, "stock")


@app.route("/categories", methods=["GET", "POST"])
@require_roles("super_admin", "operator", "inventory", "readonly")
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

    return render_template("categories.html", categories=store["categories"], bulk_result=consume_bulk_result("categories"))


@app.post("/categories/import")
@require_roles("super_admin", "operator", "inventory")
def categories_import():
    return handle_bulk_import("categories", "category", import_categories_rows, "categories")


@app.route("/categories/<category_id>/edit", methods=["POST"])
@require_roles("super_admin", "operator", "inventory")
def category_edit(category_id: str):
    store = load_store()
    category = find_by_id(store["categories"], category_id)
    if category:
        before = copy.deepcopy(category)
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
        record_change_event(
            store,
            "update",
            "category",
            category_id,
            f"Categoria actualizada: {category['name']}.",
            before,
            category,
        )
        save_store(store)
    return redirect(url_for("categories"))


@app.post("/categories/<category_id>/delete")
@require_roles("super_admin")
def category_delete(category_id: str):
    store = load_store()
    if not any(product.get("categoryId") == category_id for product in store["products"]):
        category = find_by_id(store["categories"], category_id)
        store["categories"] = [category for category in store["categories"] if category["id"] != category_id]
        record_change_event(
            store,
            "delete",
            "category",
            category_id,
            f"Categoria eliminada: {(category or {}).get('name', category_id)}.",
            category,
            None,
        )
        save_store(store)
    return redirect(url_for("categories"))


@app.route("/media-library", methods=["GET", "POST"])
@require_roles("super_admin", "operator", "inventory", "readonly")
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
        bulk_result=consume_bulk_result("media_library"),
    )


@app.post("/media-library/import")
@require_roles("super_admin", "operator", "inventory")
def media_library_import():
    return handle_bulk_import("media_library", "media_asset", import_media_assets_rows, "media_library")


@app.post("/media-library/<asset_id>/delete")
@require_roles("super_admin")
def media_asset_delete(asset_id: str):
    store = load_store()
    asset = find_by_id(store.get("media_assets", []), asset_id)
    if asset:
        before = copy.deepcopy(asset)
        store["media_assets"] = [item for item in store.get("media_assets", []) if item.get("id") != asset_id]
        product = find_by_id(store.get("products", []), asset.get("productId", ""))
        if product:
            url = asset.get("url", "")
            if asset.get("assetType") == "pdf":
                product["pdfUrls"] = [item for item in product.get("pdfUrls", []) if item != url]
            else:
                product["imageUrls"] = [item for item in product.get("imageUrls", []) if item != url]
                if product.get("imageUrl") == url:
                    product["imageUrl"] = (product.get("imageUrls") or [""])[0]
            product["updatedAt"] = utc_now()
        record_change_event(
            store,
            "delete",
            "media_asset",
            asset_id,
            f"Recurso tecnico eliminado: {asset.get('title', asset_id)}.",
            before,
            None,
        )
        save_store(store)
    return redirect(url_for("media_library"))


@app.route("/service-technicians", methods=["GET", "POST"])
@require_roles("super_admin", "commercial_manager", "operator", "readonly")
def service_technicians():
    store = load_store()
    if request.method == "POST":
        if not role_allowed(WRITE_ROLES):
            return forbidden_response()
        name = request.form.get("name", "").strip()
        if not name:
            return render_template(
                "service_technicians.html",
                **service_technicians_page_context(store, "El nombre del servicio tecnico es obligatorio."),
            )
        technician = service_technician_payload()
        store.setdefault("service_technicians", []).append(technician)
        record_audit_event(
            store,
            "create",
            "service_technician",
            technician["id"],
            f"Servicio tecnico creado: {technician['name']}.",
        )
        save_store(store)
        return redirect(url_for("service_technicians"))

    return render_template("service_technicians.html", **service_technicians_page_context(store))


@app.post("/service-technicians/import")
@require_roles("super_admin", "commercial_manager", "operator")
def service_technicians_import():
    return handle_bulk_import("service_technicians", "service_technician", import_service_technicians_rows, "service_technicians")


@app.post("/service-technicians/<technician_id>/edit")
@require_roles("super_admin", "commercial_manager", "operator")
def service_technician_edit(technician_id: str):
    store = load_store()
    technician = find_by_id(store.get("service_technicians", []), technician_id)
    if technician:
        before = copy.deepcopy(technician)
        updated = service_technician_payload(technician)
        store["service_technicians"] = [
            updated if item["id"] == technician_id else item
            for item in store.get("service_technicians", [])
        ]
        record_change_event(
            store,
            "update",
            "service_technician",
            technician_id,
            f"Servicio tecnico actualizado: {updated['name']}.",
            before,
            updated,
        )
        save_store(store)
    return redirect(url_for("service_technicians"))


@app.post("/service-technicians/<technician_id>/delete")
@require_roles("super_admin")
def service_technician_delete(technician_id: str):
    store = load_store()
    technician = find_by_id(store.get("service_technicians", []), technician_id)
    if technician:
        before = copy.deepcopy(technician)
        technician["status"] = "deleted"
        technician["visibleInApp"] = False
        technician["updatedAt"] = utc_now()
        record_change_event(
            store,
            "delete",
            "service_technician",
            technician_id,
            f"Servicio tecnico eliminado: {technician.get('name', technician_id)}.",
            before,
            technician,
        )
        save_store(store)
    return redirect(url_for("service_technicians"))


def credit_dashboard_context(store: dict) -> dict:
    movements = store.get("credit_movements", [])
    visible_clients = visible_clients_for_current_user(store)
    visible_client_ids = {client.get("id", "") for client in visible_clients}
    visible_orders = visible_orders_for_current_user(store)
    clients_list = [
        enrich_client(client, store.get("orders", []), movements)
        for client in visible_clients
    ]
    client_lookup = {client["id"]: client for client in visible_clients}
    payments = []
    for movement in movements:
        if movement.get("movementType") != "payment":
            continue
        if movement.get("clientId", "") not in visible_client_ids:
            continue
        enriched_movement = dict(movement)
        client = client_lookup.get(enriched_movement.get("clientId", ""))
        enriched_movement["clientName"] = client.get("businessName", "Cliente Wulkan") if client else "Cliente Wulkan"
        payments.append(enriched_movement)
    due_orders = [
        order
        for order in [enrich_order(order, movements) for order in visible_orders]
        if order.get("balanceUsd", 0) > 0
        and order.get("saleType") in {"term_credit", "credit_line"}
        and order.get("status") != "cancelled"
    ]
    metrics = {
        "limit": sum(float(client.get("creditLimitUsd") or 0) for client in clients_list if client.get("creditEnabled")),
        "exposure": sum(float(client.get("creditExposureUsd") or 0) for client in clients_list),
        "available": sum(float(client.get("creditAvailableUsd") or 0) for client in clients_list),
        "payments": sum(float(payment.get("amountUsd") or 0) for payment in payments),
        "overdue": sum(float(order.get("balanceUsd") or 0) for order in due_orders if order.get("dueStatus") == "overdue"),
    }
    return {
        "clients": sorted(clients_list, key=lambda item: item.get("businessName", "")),
        "payments": sorted(payments, key=lambda item: item.get("createdAt", ""), reverse=True),
        "due_orders": sorted(due_orders, key=lambda item: item.get("dueDate", "")),
        "metrics": metrics,
    }


@app.get("/credit")
@require_roles("super_admin", "commercial_manager")
def credit():
    store = load_store()
    context = credit_dashboard_context(store)
    return render_template(
        "credit.html",
        clients=context["clients"],
        metrics=context["metrics"],
        payment_terms=PAYMENT_TERM_OPTIONS,
        can_approve_credit=role_allowed(CREDIT_APPROVAL_ROLES),
    )


@app.get("/credit/vencimientos")
@require_roles("super_admin", "commercial_manager")
def credit_due():
    store = load_store()
    context = credit_dashboard_context(store)
    return render_template(
        "credit_due.html",
        due_orders=context["due_orders"],
        metrics=context["metrics"],
    )


@app.get("/credit/historial")
@require_roles("super_admin", "commercial_manager")
def credit_history():
    store = load_store()
    context = credit_dashboard_context(store)
    return render_template(
        "credit_history.html",
        payments=context["payments"],
        metrics=context["metrics"],
    )


@app.post("/credit/<client_id>/decision")
@require_roles("super_admin", "commercial_manager")
def credit_decision(client_id: str):
    store = load_store()
    client = find_by_id(store.get("clients", []), client_id)
    if not client:
        return redirect(url_for("credit"))

    before = copy.deepcopy(client)
    decision = request.form.get("decision", "approved")
    now = utc_now()
    if decision == "approved":
        credit_limit = float(request.form.get("creditLimitUsd") or client.get("creditRequestedUsd") or 0)
        payment_terms = int(request.form.get("paymentTermsDays") or client.get("paymentTermsDays") or 0)
        client["creditEnabled"] = credit_limit > 0
        client["creditLimitUsd"] = credit_limit
        client["paymentTermsDays"] = payment_terms
        client["creditRequestStatus"] = "approved"
        client["creditApprovedBy"] = session.get("admin_name", "Admin")
        client["creditApprovedAt"] = now
        allowed_terms = set(int(term) for term in client.get("allowedPaymentTermsDays", [0]) if str(term).isdigit())
        allowed_terms.add(payment_terms)
        client["allowedPaymentTermsDays"] = sorted(allowed_terms)
        detail = f"Credito aprobado por {money_usd(credit_limit)} a {payment_terms} dias."
    else:
        client["creditEnabled"] = False
        client["creditLimitUsd"] = 0.0
        client["paymentTermsDays"] = 0
        client["creditRequestStatus"] = "rejected"
        client["creditApprovedBy"] = session.get("admin_name", "Admin")
        client["creditApprovedAt"] = now
        detail = "Solicitud de credito rechazada."

    client["updatedAt"] = now
    record_change_event(
        store,
        "credit_decision",
        "client",
        client_id,
        detail,
        before,
        client,
    )
    save_store(store)
    return redirect(url_for("credit"))


@app.get("/audit")
@require_roles("super_admin")
def audit():
    store = load_store()
    events = sorted(store.get("audit_events", []), key=lambda item: item.get("createdAt", ""), reverse=True)[:200]
    write_actions = {
        "create",
        "update",
        "delete",
        "payment",
        "update_status",
        "credit_decision",
        "commission_update",
        "password_change",
        "bulk_import",
    }
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
@require_roles("super_admin", "commercial_manager", "operator", "readonly")
def orders():
    store = load_store()
    movements = store.get("credit_movements", [])
    enriched_orders = [
        enrich_order(order, movements)
        for order in sorted(visible_orders_for_current_user(store), key=lambda item: item.get("createdAt", ""), reverse=True)
    ]
    metrics = {
        "orders": len(enriched_orders),
        "total": sum(float(order.get("totalUsd") or 0) for order in enriched_orders),
        "balance": sum(float(order.get("balanceUsd") or 0) for order in enriched_orders),
        "review": sum(1 for order in enriched_orders if order.get("status") == "credit_review"),
        "commission_pending": sum(
            float(order.get("commissionUsd") or 0)
            for order in enriched_orders
            if order.get("commissionStatus") == "commission_pending"
        ),
    }
    return render_template(
        "orders.html",
        orders=enriched_orders,
        status_options=ORDER_STATUS_OPTIONS,
        payment_methods=PAYMENT_METHOD_OPTIONS,
        sale_type_options=SALE_TYPE_OPTIONS,
        can_manage_orders=role_allowed(ORDER_MANAGEMENT_ROLES),
        can_create_assisted_order=role_allowed(SALES_ROLES),
        metrics=metrics,
    )


@app.route("/orders/new", methods=["GET", "POST"])
@require_roles("super_admin", "commercial_manager", "operator")
def order_new():
    store = load_store()
    if request.method == "POST":
        payload = assisted_order_payload_from_form()
        client = find_by_id(store.get("clients", []), payload.get("customerId", ""))
        if not can_access_client_record(client):
            return forbidden_response()
        order, error = build_commercial_order(
            store,
            payload,
            actor=order_actor(),
            default_channel="seller_assisted",
        )
        if error:
            return render_template("order_form.html", **assisted_order_page_context(store, error))
        store["orders"].append(order)
        record_audit_event(
            store,
            "create",
            "order",
            order["orderId"],
            f"Pedido asistido creado para {order['customer'].get('name', 'Cliente Wulkan')}.",
        )
        save_store(store)
        return redirect(url_for("orders"))

    return render_template("order_form.html", **assisted_order_page_context(store))


@app.post("/orders/<order_id>/status")
@require_roles("super_admin", "commercial_manager", "operator")
def order_status_update(order_id: str):
    store = load_store()
    order = find_order(store["orders"], order_id)
    if not order or not can_access_order_record(order, store):
        return redirect(url_for("orders"))

    before = copy.deepcopy(order)
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
        order["commissionStatus"] = "commission_cancelled"
    elif target_status == "paid" and balance > 0:
        target_status = "partial_paid"
        note = note or "La orden tiene saldo pendiente; registra el abono para cerrarla como pagada."
    elif target_status in {"delivered", "paid"} and float(order.get("commissionUsd") or 0) > 0:
        order["commissionStatus"] = "commission_approved"

    order["status"] = target_status
    order["managedBy"] = session.get("admin_name", "Admin")
    order["managedAt"] = utc_now()
    order["updatedAt"] = utc_now()
    order["balanceUsd"] = order_balance_usd(order, movements)
    order["paidUsd"] = order_paid_usd(order, movements)
    append_order_history(order, target_status, note)
    record_change_event(
        store,
        "update_status",
        "order",
        order_id,
        f"Orden movida a {target_status}.",
        before,
        order,
    )
    save_store(store)
    return redirect(url_for("orders"))


@app.post("/orders/<order_id>/payments")
@require_roles("super_admin", "commercial_manager", "operator")
def order_payment_create(order_id: str):
    store = load_store()
    order = find_order(store["orders"], order_id)
    if not order or not can_access_order_record(order, store):
        return redirect(url_for("orders"))

    before = copy.deepcopy(order)
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
    if balance_after <= 0 and float(order.get("commissionUsd") or 0) > 0:
        order["commissionStatus"] = "commission_approved"
    apply_inventory_transition(store, order, order["status"])
    order["managedBy"] = session.get("admin_name", "Admin")
    order["managedAt"] = utc_now()
    order["updatedAt"] = utc_now()
    append_order_history(order, order["status"], f"Abono externo registrado por {money_usd(amount_usd)}.")
    record_change_event(
        store,
        "payment",
        "order",
        order_id,
        f"Abono registrado por {money_usd(amount_usd)}.",
        before,
        order,
    )
    save_store(store)
    return redirect(url_for("orders"))


@app.get("/commissions")
@require_roles("super_admin", "commercial_manager")
def commissions():
    store = load_store()
    return render_template("commissions.html", **commissions_page_context(store))


@app.post("/commissions/<order_id>/status")
@require_roles("super_admin", "commercial_manager")
def commission_status_update(order_id: str):
    store = load_store()
    order = find_order(store.get("orders", []), order_id)
    if not order:
        return redirect(url_for("commissions"))
    before = copy.deepcopy(order)
    status = request.form.get("commissionStatus", order.get("commissionStatus", "commission_pending"))
    if status not in {"commission_pending", "commission_approved", "commission_paid", "commission_cancelled"}:
        return redirect(url_for("commissions"))
    order["commissionStatus"] = status
    order["updatedAt"] = utc_now()
    if status == "commission_paid":
        order["commissionPaidAt"] = utc_now()
        order["commissionPaidBy"] = session.get("admin_name", "Admin")
    elif status != "commission_paid":
        order["commissionPaidAt"] = ""
        order["commissionPaidBy"] = ""
    append_order_history(order, order.get("status", "credit_review"), f"Comision marcada como {commission_status_label(status)}.")
    record_change_event(
        store,
        "commission_update",
        "order",
        order_id,
        f"Comision actualizada a {commission_status_label(status)} por {session.get('admin_name', 'Admin')}.",
        before,
        order,
    )
    save_store(store)
    return redirect(url_for("commissions"))


@app.route("/announcements", methods=["GET", "POST"])
@require_roles("super_admin", "commercial_manager", "operator", "readonly")
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
        bulk_result=consume_bulk_result("announcements"),
    )


@app.post("/announcements/import")
@require_roles("super_admin", "commercial_manager", "operator")
def announcements_import():
    return handle_bulk_import("announcements", "announcement", import_announcements_rows, "announcements")


@app.post("/announcements/<announcement_id>/edit")
@require_roles("super_admin", "commercial_manager", "operator")
def announcement_edit(announcement_id: str):
    store = load_store()
    announcement = find_by_id(store["announcements"], announcement_id)
    if announcement:
        before = copy.deepcopy(announcement)
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
        record_change_event(
            store,
            "update",
            "announcement",
            announcement_id,
            f"Anuncio actualizado: {announcement['title']}.",
            before,
            announcement,
        )
        save_store(store)
    return redirect(url_for("announcements"))


@app.post("/announcements/<announcement_id>/delete")
@require_roles("super_admin")
def announcement_delete(announcement_id: str):
    store = load_store()
    announcement = find_by_id(store["announcements"], announcement_id)
    store["announcements"] = [
        announcement for announcement in store["announcements"] if announcement["id"] != announcement_id
    ]
    record_change_event(
        store,
        "delete",
        "announcement",
        announcement_id,
        f"Anuncio eliminado: {(announcement or {}).get('title', announcement_id)}.",
        announcement,
        None,
    )
    save_store(store)
    return redirect(url_for("announcements"))


@app.post("/api/mobile/orders")
def api_create_order():
    store = load_store()
    payload = request.get_json(silent=True) or {}
    customer_payload = payload.get("customer") or {}
    customer_id = mobile_token_client_id() or customer_payload.get("id", "")
    if app.config.get("REQUIRE_MOBILE_TOKEN") and not mobile_token_client_id():
        return jsonify({"error": "Token movil requerido."}), 401
    payload["customerId"] = customer_id
    order, error = build_commercial_order(
        store,
        payload,
        actor={"id": customer_id, "name": customer_payload.get("name", "Cliente Wulkan"), "role": "client"},
        default_channel="mobile",
    )
    if error:
        return jsonify({"error": error}), 400
    store["orders"].append(order)
    record_audit_event(
        store,
        "create",
        "order",
        order["orderId"],
        f"Orden movil creada por {order['customer'].get('name', 'Cliente Wulkan')}.",
        actor={"id": customer_id, "name": order["customer"].get("name", ""), "role": "client"},
    )
    save_store(store)
    return jsonify(
        {
            "orderId": order["orderId"],
            "status": order["status"],
            "creditBeforeUsd": order["creditBeforeUsd"],
            "creditAfterUsd": order["creditAfterUsd"],
            "balanceUsd": order["balanceUsd"],
            "saleType": order["saleType"],
            "paymentTermDays": order["paymentTermDays"],
            "dueDate": order["dueDate"],
            "sellerId": order["sellerId"],
            "sellerName": order["sellerName"],
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


@app.get("/api/mobile/seller/summary")
def api_mobile_seller_summary():
    store = load_store()
    user, auth_error = require_mobile_sales_user(store)
    if auth_error:
        return auth_error, 401

    clients = seller_scope_clients(store, user)
    orders = [enrich_order(order, store.get("credit_movements", [])) for order in seller_scope_orders(store, user)]
    pending_credit = [
        client for client in clients if client.get("creditRequestStatus") == "pending"
    ]
    return jsonify(
        {
            "summary": {
                "sellerId": user["id"],
                "sellerName": user.get("name", "Vendedor Wulkan"),
                "role": user.get("role", ""),
                "roleLabel": ROLE_LABELS.get(user.get("role", ""), "Vendedor"),
                "clientsCount": len(clients),
                "ordersCount": len(orders),
                "pendingCreditRequests": len(pending_credit),
                "salesUsd": round(sum(float(order.get("totalUsd") or 0) for order in orders), 2),
                "openBalanceUsd": round(sum(float(order.get("balanceUsd") or 0) for order in orders), 2),
                "pendingCommissionUsd": round(
                    sum(
                        float(order.get("commissionUsd") or 0)
                        for order in orders
                        if order.get("commissionStatus") == "commission_pending"
                    ),
                    2,
                ),
                "approvedCommissionUsd": round(
                    sum(
                        float(order.get("commissionUsd") or 0)
                        for order in orders
                        if order.get("commissionStatus") == "commission_approved"
                    ),
                    2,
                ),
                "paidCommissionUsd": round(
                    sum(
                        float(order.get("commissionUsd") or 0)
                        for order in orders
                        if order.get("commissionStatus") == "commission_paid"
                    ),
                    2,
                ),
            }
        }
    )


@app.route("/api/mobile/seller/clients", methods=["GET", "POST"])
def api_mobile_seller_clients():
    store = load_store()
    user, auth_error = require_mobile_sales_user(store)
    if auth_error:
        return auth_error, 401

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email") or "").strip().lower()
        business_name = str(payload.get("businessName") or payload.get("name") or "").strip()
        if not email or not business_name:
            return jsonify({"error": "Nombre comercial y email son obligatorios."}), 400
        duplicated = any(client.get("email", "").lower() == email for client in store.get("clients", []))
        if duplicated:
            return jsonify({"error": f"Ya existe un cliente con el email {email}."}), 409

        seller_id = user["id"] if user.get("role") == "sales" else str(payload.get("assignedSellerId") or "").strip()
        seller_name = user.get("name", "") if user.get("role") == "sales" else seller_name_for(store, seller_id)
        requested_credit = float(payload.get("creditRequestedUsd") or 0)
        raw_terms = payload.get("allowedPaymentTermsDays") or [0]
        terms = [
            int(term)
            for term in raw_terms
            if str(term).strip().isdigit() and int(term) in PAYMENT_TERM_OPTIONS
        ] or [0]
        temporary_password = str(payload.get("password") or secrets.token_urlsafe(10))
        client = {
            "id": next_id("client", email or business_name),
            "businessName": business_name,
            "taxId": str(payload.get("taxId") or "").strip(),
            "contactName": str(payload.get("contactName") or "").strip(),
            "phone": str(payload.get("phone") or "").strip(),
            "email": email,
            "clientType": "ferretero",
            "status": "active",
            "address": str(payload.get("address") or "").strip(),
            "state": str(payload.get("state") or "").strip(),
            "city": str(payload.get("city") or "").strip(),
            "deliveryZone": str(payload.get("deliveryZone") or "").strip(),
            "assignedSellerId": seller_id,
            "assignedSellerName": seller_name,
            "defaultSaleType": str(payload.get("defaultSaleType") or "cash"),
            "allowedPaymentTermsDays": terms,
            "creditRequestStatus": "pending" if requested_credit > 0 else "none",
            "creditRequestedUsd": requested_credit,
            "creditEnabled": False,
            "creditLimitUsd": 0.0,
            "creditUsedUsd": 0.0,
            "paymentTermsDays": 0,
            "notes": str(payload.get("notes") or "").strip(),
            "passwordHash": generate_password_hash(temporary_password),
            "mustChangePassword": True,
            "createdAt": utc_now(),
            "updatedAt": utc_now(),
        }
        store["clients"].append(client)
        record_audit_event(
            store,
            "create",
            "client",
            client["id"],
            f"Cliente creado desde app movil vendedor: {client['businessName']}.",
            actor={"id": user["id"], "name": user.get("name", ""), "role": user.get("role", "")},
        )
        save_store(store)
        response = mobile_seller_client_payload(client, store)
        response["temporaryPassword"] = temporary_password
        return jsonify({"client": response}), 201

    clients = [
        mobile_seller_client_payload(client, store)
        for client in sorted(seller_scope_clients(store, user), key=lambda item: item.get("businessName", ""))
    ]
    return jsonify({"items": clients})


@app.route("/api/mobile/seller/orders", methods=["GET", "POST"])
def api_mobile_seller_orders():
    store = load_store()
    user, auth_error = require_mobile_sales_user(store)
    if auth_error:
        return auth_error, 401

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        customer_id = str(payload.get("customerId") or (payload.get("customer") or {}).get("id") or "").strip()
        if not can_mobile_seller_access_client(store, user, customer_id):
            return jsonify({"error": "Cliente fuera de tu cartera."}), 403
        payload["customerId"] = customer_id
        order, error = build_commercial_order(
            store,
            payload,
            actor={"id": user["id"], "name": user.get("name", "Vendedor Wulkan"), "role": user.get("role", "sales")},
            default_channel="seller_mobile",
        )
        if error:
            return jsonify({"error": error}), 400
        store["orders"].append(order)
        record_audit_event(
            store,
            "create",
            "order",
            order["orderId"],
            f"Pedido asistido movil creado por {user.get('name', 'Vendedor Wulkan')}.",
            actor={"id": user["id"], "name": user.get("name", ""), "role": user.get("role", "")},
        )
        save_store(store)
        return jsonify({"order": mobile_seller_order_payload(order, store), "orderId": order["orderId"]}), 201

    orders = [
        mobile_seller_order_payload(order, store)
        for order in sorted(seller_scope_orders(store, user), key=lambda item: item.get("createdAt", ""), reverse=True)
    ]
    return jsonify({"items": orders})


@app.get("/api/mobile/seller/commissions")
def api_mobile_seller_commissions():
    store = load_store()
    user, auth_error = require_mobile_sales_user(store)
    if auth_error:
        return auth_error, 401
    orders = [
        mobile_seller_order_payload(order, store)
        for order in sorted(seller_scope_orders(store, user), key=lambda item: item.get("createdAt", ""), reverse=True)
        if float(order.get("commissionUsd") or 0) > 0
    ]
    return jsonify({"items": orders})


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
                "allowedPaymentTermsDays": enriched.get("allowedPaymentTermsDays", [0]),
                "defaultSaleType": enriched.get("defaultSaleType", "cash"),
                "assignedSeller": {
                    "id": enriched.get("assignedSellerId", ""),
                    "name": enriched.get("assignedSellerName", ""),
                },
                "status": enriched["creditStatus"],
                "mustChangePassword": bool(enriched.get("mustChangePassword")),
            }
        }
    )


@app.get("/api/mobile/categories")
def api_categories():
    store = load_store()
    _, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    categories = [
        category
        for category in store["categories"]
        if category.get("status", "active") == "active"
    ]
    return jsonify({"items": categories})


@app.post("/api/mobile/auth/login")
def api_client_login():
    store = load_store()
    payload = request.get_json(silent=True) or {}
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")
    if is_blocked_default_login(email, mobile=True):
        register_login_failure("mobile", email)
        record_audit_event(
            store,
            "login_failed",
            "mobile_user",
            email,
            "Intento de inicio movil con cuenta demo bloqueada en produccion.",
            actor={"id": email, "name": email or "desconocido", "role": "mobile"},
        )
        save_store(store)
        return jsonify({"error": "Credenciales invalidas."}), 401
    if is_login_limited("mobile", email):
        record_audit_event(
            store,
            "login_limited",
            "client",
            email,
            "Login movil bloqueado temporalmente por intentos fallidos.",
            actor={"id": email, "name": email or "desconocido", "role": "mobile"},
        )
        save_store(store)
        return jsonify({"error": "Demasiados intentos. Espera unos minutos."}), 429

    client = next(
        (
            item
            for item in store.get("clients", [])
            if item.get("email", "").lower() == email and item.get("status") == "active"
        ),
        None,
    )
    if client and check_password_hash(client.get("passwordHash", ""), password):
        reset_login_attempts("mobile", email)
        client["lastLoginAt"] = utc_now()
        access_token = issue_mobile_token(client)
        record_audit_event(
            store,
            "login",
            "client",
            client["id"],
            "Inicio de sesion movil.",
            actor={"id": client["id"], "name": client.get("businessName", email), "role": "client"},
        )
        save_store(store)
        return jsonify(mobile_customer_payload(client, store, access_token))

    admin_user = next(
        (
            user
            for user in store.get("admin_users", [])
            if user.get("email", "").lower() == email
            and user.get("status") == "active"
            and user.get("role") in MOBILE_SALES_ROLES
        ),
        None,
    )
    if admin_user and check_password_hash(admin_user.get("passwordHash", ""), password):
        reset_login_attempts("mobile", email)
        admin_user["lastMobileLoginAt"] = utc_now()
        access_token = issue_mobile_admin_token(admin_user)
        record_audit_event(
            store,
            "login",
            "admin_user",
            admin_user["id"],
            "Inicio de sesion movil operativo.",
            actor={"id": admin_user["id"], "name": admin_user.get("name", email), "role": admin_user.get("role", "")},
        )
        save_store(store)
        return jsonify(mobile_admin_payload(admin_user, access_token))

    register_login_failure("mobile", email)
    record_audit_event(
        store,
        "login_failed",
        "mobile_user",
        email,
        "Intento fallido de inicio de sesion movil.",
        actor={"id": email, "name": email or "desconocido", "role": "mobile"},
    )
    save_store(store)
    return jsonify({"error": "Credenciales invalidas."}), 401


@app.post("/api/mobile/auth/change-password")
def api_client_change_password():
    store = load_store()
    token_payload = mobile_token_payload()
    if not token_payload:
        return jsonify({"error": "Token movil requerido."}), 401

    subject_type = "client"
    subject = find_by_id(store.get("clients", []), token_payload.get("clientId") or token_payload.get("id", ""))
    subject_name_key = "businessName"
    if token_payload.get("type") == "admin":
        subject_type = "admin_user"
        subject = find_by_id(store.get("admin_users", []), token_payload.get("adminUserId") or token_payload.get("id", ""))
        subject_name_key = "name"
        if not subject or subject.get("status") != "active" or subject.get("role") not in MOBILE_SALES_ROLES:
            return jsonify({"error": "Token movil invalido."}), 401
    elif not subject or subject.get("status") != "active":
        return jsonify({"error": "Cliente no encontrado."}), 404

    payload = request.get_json(silent=True) or {}
    current_password = payload.get("currentPassword", "")
    new_password = payload.get("newPassword", "")
    if not check_password_hash(subject.get("passwordHash", ""), current_password):
        record_audit_event(
            store,
            "password_change_failed",
            subject_type,
            subject["id"],
            "Cambio de contrasena movil fallido por clave actual invalida.",
            actor={
                "id": subject["id"],
                "name": subject.get(subject_name_key, ""),
                "role": subject.get("role", "client"),
            },
        )
        save_store(store)
        return jsonify({"error": "La contrasena actual no coincide."}), 400
    errors = password_errors(new_password)
    if errors:
        return jsonify({"error": " ".join(errors)}), 400

    subject["passwordHash"] = generate_password_hash(new_password)
    subject["mustChangePassword"] = False
    subject["updatedAt"] = utc_now()
    record_audit_event(
        store,
        "password_change",
        subject_type,
        subject["id"],
        "Contrasena movil actualizada por el usuario.",
        actor={
            "id": subject["id"],
            "name": subject.get(subject_name_key, ""),
            "role": subject.get("role", "client"),
        },
    )
    save_store(store)
    return jsonify({"status": "updated", "mustChangePassword": False})


@app.get("/api/mobile/products")
def api_products():
    store = load_store()
    _, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
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
    store = load_store()
    _, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    placement = request.args.get("placement")
    return jsonify({"items": active_announcements(placement, store)})


@app.get("/api/mobile/service-technicians")
def api_service_technicians():
    store = load_store()
    _, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    technicians = [
        technician
        for technician in store.get("service_technicians", [])
        if technician.get("status") == "active" and technician.get("visibleInApp")
    ]
    return jsonify({"items": technicians})


@app.get("/api/mobile/locations")
def api_locations():
    store = load_store()
    _, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    technicians = [
        technician
        for technician in store.get("service_technicians", [])
        if technician.get("status") == "active" and technician.get("visibleInApp")
    ]
    return jsonify(
        {
            "items": [
                {
                    "id": technician.get("id", ""),
                    "name": technician.get("name", ""),
                    "subtitle": " - ".join(
                        part
                        for part in [technician.get("city", ""), technician.get("coverage", "")]
                        if part
                    ),
                    "phone": technician.get("phone", ""),
                    "whatsapp": technician.get("whatsapp", ""),
                    "address": technician.get("address", ""),
                    "specialties": technician.get("specialties", []),
                }
                for technician in technicians
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
    app.run(host="0.0.0.0", port=5000, debug=app.config.get("ENV") != "production")
