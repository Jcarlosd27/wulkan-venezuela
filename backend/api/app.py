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
    ("payment_under_review", "Pago por validar"),
    ("approved_with_credit", "Aprobada con credito"),
    ("preparing", "Preparando"),
    ("rejected", "Rechazada"),
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
SALES_CHANNEL_LABELS = {
    "mobile": "App ferretero",
    "seller_mobile": "App vendedor",
    "seller_assisted": "Pedido asistido",
    "admin": "Admin",
    "phone": "Telefono",
}
DISPATCH_STATUS_LABELS = {
    "pending": "Pendiente",
    "preparing": "Preparando",
    "ready": "Listo para despacho",
    "dispatched": "Despachado",
    "delivered": "Entregado",
    "cancelled": "Cancelado",
}
PAYMENT_TERM_OPTIONS = [0, 10, 15, 20, 30, 40]
CLIENT_STATUS_OPTIONS = [
    ("prospect", "Prospecto"),
    ("active", "Activo"),
    ("inactive", "Inactivo"),
    ("review", "En revision"),
    ("blocked_debt", "Bloqueado por deuda"),
    ("blocked_credit", "Bloqueado por credito"),
    ("blocked_manual", "Bloqueado manual"),
    ("suspended", "Suspendido"),
]
PRODUCT_STATUS_OPTIONS = [
    ("active", "Activo"),
    ("inactive", "Inactivo"),
    ("out", "Agotado"),
    ("replenishment", "En reposicion"),
    ("hidden", "Oculto en app"),
    ("discontinued", "Descontinuado"),
]
STOCK_MOVEMENT_OPTIONS = [
    ("entry", "Entrada"),
    ("exit", "Salida"),
    ("sale", "Salida / venta"),
    ("adjustment_positive", "Ajuste positivo"),
    ("adjustment_negative", "Ajuste negativo"),
    ("adjustment", "Ajuste a cantidad final"),
    ("bulk_set", "Carga masiva"),
    ("bulk_excel_set", "Carga Excel/CSV"),
    ("reserved", "Reserva por orden"),
    ("released", "Liberacion"),
    ("commit", "Compromiso por orden"),
    ("delivered", "Descuento por entrega"),
    ("annulment", "Anulacion"),
    ("return", "Devolucion"),
]
STOCK_MOVEMENT_LABELS = dict(STOCK_MOVEMENT_OPTIONS)
STOCK_STATUS_OPTIONS = [
    ("available", "Disponible"),
    ("low", "Bajo minimo"),
    ("replenishment", "Reposicion"),
    ("out", "Agotado"),
    ("overstock", "Sobre maximo"),
    ("without_movement", "Sin movimiento"),
]
STOCK_STATUS_LABELS = dict(STOCK_STATUS_OPTIONS)
PRODUCT_TYPE_OPTIONS = [
    ("machine", "Maquina"),
    ("spare_part", "Repuesto"),
    ("accessory", "Accesorio"),
    ("service", "Servicio"),
    ("consumable", "Consumible"),
]
CATEGORY_STATUS_OPTIONS = [
    ("active", "Activa"),
    ("inactive", "Inactiva"),
    ("hidden", "Oculta en app"),
]
CLIENT_TYPE_OPTIONS = [
    ("ferretero", "Ferretero"),
    ("distribuidor", "Distribuidor"),
    ("cliente_especial", "Cliente especial"),
]
CLIENT_CATEGORY_OPTIONS = [
    ("standard", "Estandar"),
    ("preferential", "Preferencial"),
    ("strategic", "Estrategico"),
    ("wholesale", "Mayorista"),
]
PRICE_LIST_OPTIONS = [
    ("b2b", "B2B"),
    ("retail", "Retail"),
    ("wholesale", "Mayorista"),
    ("special", "Especial"),
]
COLLECTION_STATUS_OPTIONS = [
    ("current", "Al dia"),
    ("due_soon", "Por vencer"),
    ("overdue", "Vencido"),
    ("promise", "Promesa de pago"),
    ("blocked", "Bloqueado por cobranza"),
    ("without_debt", "Sin deuda"),
]
ORDER_COLLECTION_STATUS_OPTIONS = [
    ("current", "Al dia"),
    ("due_soon", "Por vencer"),
    ("overdue", "Vencido"),
    ("in_management", "En gestion"),
    ("promise", "Promesa de pago"),
    ("partial_paid", "Pago parcial"),
    ("critical", "Critico"),
    ("uncollectible", "Incobrable"),
    ("closed", "Cerrado"),
]
CREDIT_RISK_OPTIONS = [
    ("low", "Bajo"),
    ("medium", "Medio"),
    ("high", "Alto"),
    ("critical", "Critico"),
]
CREDIT_REQUEST_STATUS_OPTIONS = [
    ("none", "Sin credito"),
    ("pending", "Credito solicitado"),
    ("review", "En evaluacion"),
    ("approved", "Aprobado"),
    ("rejected", "Rechazado"),
    ("suspended", "Suspendido"),
    ("blocked_debt", "Bloqueado por mora"),
    ("blocked_limit", "Bloqueado por exceso de cupo"),
]
CREDIT_DECISION_OPTIONS = [
    ("review", "Pasar a evaluacion"),
    ("approved", "Aprobar credito"),
    ("rejected", "Rechazar solicitud"),
    ("suspended", "Suspender credito"),
    ("blocked_debt", "Bloquear por mora"),
    ("blocked_limit", "Bloquear por exceso de cupo"),
    ("reactivate", "Reactivar linea"),
    ("adjust", "Ajustar cupo/condicion"),
]
SELLER_STATUS_OPTIONS = [
    ("active", "Activo"),
    ("inactive", "Inactivo"),
    ("blocked", "Bloqueado"),
    ("suspended", "Suspendido"),
]
ROLE_LABELS = {
    "super_admin": "Super admin",
    "general_manager": "Gerente general",
    "commercial_manager": "Gerente comercial",
    "operator": "Operador",
    "collections": "Cobranza",
    "dispatch": "Despacho",
    "auditor": "Auditor",
    "sales": "Vendedor app movil",
    "inventory": "Inventario",
    "readonly": "Solo lectura",
}
LOGIN_ATTEMPTS: dict[str, list[float]] = {}
PASSWORD_MIN_LENGTH = 10
IMPORT_DRAFT_TTL_SECONDS = 60 * 60
WEB_ADMIN_ROLES = {"super_admin", "general_manager", "commercial_manager", "operator", "inventory", "collections", "dispatch", "auditor", "readonly"}
WEB_ADMIN_ROLE_ORDER = ["super_admin", "general_manager", "commercial_manager", "operator", "inventory", "collections", "dispatch", "auditor", "readonly"]
WRITE_ROLES = {"super_admin", "general_manager", "commercial_manager", "operator"}
SALES_ROLES = {"super_admin", "commercial_manager", "operator"}
INVENTORY_ROLES = {"super_admin", "commercial_manager", "operator", "inventory"}
CREDIT_APPROVAL_ROLES = {"super_admin", "general_manager", "commercial_manager"}
ORDER_MANAGEMENT_ROLES = {"super_admin", "general_manager", "commercial_manager", "operator"}
COMMISSION_MANAGEMENT_ROLES = {"super_admin", "general_manager", "commercial_manager"}
MOBILE_SALES_ROLES = {"super_admin", "commercial_manager", "sales"}
ADMIN_ONLY_ROLES = {"super_admin"}
DELETE_ROLES = {"super_admin"}
PERMISSION_ACTIONS = [
    ("view", "Ver", "bi-eye"),
    ("create", "Crear", "bi-plus-circle"),
    ("edit", "Editar", "bi-pencil-square"),
    ("annul", "Anular", "bi-x-octagon"),
    ("approve", "Aprobar", "bi-check2-circle"),
    ("reject", "Rechazar", "bi-slash-circle"),
    ("export", "Exportar", "bi-download"),
    ("import", "Importar", "bi-upload"),
    ("delete", "Eliminar logico", "bi-trash"),
    ("audit", "Ver auditoria", "bi-shield-check"),
]
PERMISSION_MODULES = [
    ("dashboard", "Dashboard", "bi-grid-1x2", "KPIs ejecutivos y graficos Graphify."),
    ("sellers", "Vendedores", "bi-person-badge", "Fuerza comercial, cartera y metas."),
    ("clients", "Clientes", "bi-shop", "Ferreteros, datos comerciales y credito."),
    ("credit", "Credito B2B", "bi-credit-card-2-front", "Lineas, cupos, vencimientos y riesgo."),
    ("orders", "Ordenes", "bi-receipt", "Pedidos, saldo, estado comercial y despacho."),
    ("commissions", "Comisiones", "bi-percent", "Liquidacion comercial por vendedor."),
    ("products", "Productos", "bi-box-seam", "Catalogo, precios, imagenes y PDFs."),
    ("categories", "Categorias", "bi-tags", "Familias visibles en app movil."),
    ("media_library", "Biblioteca tecnica", "bi-folder2-open", "Imagenes, fichas y recursos asociados."),
    ("stock", "Stock", "bi-boxes", "Inventario fisico, reservado y movimientos."),
    ("announcements", "Anuncios app", "bi-megaphone", "Banners y carrusel comercial movil."),
    ("service_technicians", "Servicios tecnicos", "bi-tools", "Directorio publico de soporte."),
    ("quotes", "Cotizaciones", "bi-file-earmark-text", "Preventas, versiones y conversion a orden."),
    ("collections", "Cobranza", "bi-cash-coin", "Cuentas por cobrar, abonos y mora."),
    ("dispatch", "Despacho", "bi-truck", "Preparacion, ruta y evidencia de entrega."),
    ("reports", "Reportes", "bi-file-bar-graph", "Exportables comerciales, inventario y finanzas."),
    ("admin_users", "Usuarios admin", "bi-people", "Accesos internos al panel."),
    ("permissions", "Roles y permisos", "bi-shield-lock", "Matriz granular por rol y accion."),
    ("settings", "Configuracion", "bi-gear", "Parametros generales del negocio."),
    ("audit", "Auditoria", "bi-shield-check", "Trazabilidad de cambios sensibles."),
    ("import_templates", "Plantillas", "bi-file-earmark-spreadsheet", "Formatos Excel/CSV oficiales."),
    ("documents", "Documentos", "bi-folder2", "Contratos, estados de cuenta y evidencias."),
]
ACTION_VIEW = {"view"}
ACTION_READ = {"view", "export"}
ACTION_AUDIT = {"view", "export", "audit"}
ACTION_WORK = {"view", "create", "edit", "export", "import", "audit"}
ACTION_APPROVE = {"view", "create", "edit", "approve", "reject", "export", "audit"}
ACTION_FULL_NO_DELETE = {"view", "create", "edit", "annul", "approve", "reject", "export", "import", "audit"}
ALL_ACTION_KEYS = {key for key, _label, _icon in PERMISSION_ACTIONS}
ACTION_ORDER = [key for key, _label, _icon in PERMISSION_ACTIONS]
ALL_MODULE_KEYS = [key for key, _label, _icon, _description in PERMISSION_MODULES]
ROLE_MODULE_PERMISSIONS = {
    "super_admin": {module: set(ALL_ACTION_KEYS) for module in ALL_MODULE_KEYS},
    "general_manager": {
        module: set(ACTION_AUDIT) for module in ALL_MODULE_KEYS if module not in {"admin_users", "permissions", "settings"}
    },
    "commercial_manager": {
        "dashboard": set(ACTION_AUDIT),
        "sellers": set(ACTION_WORK),
        "clients": set(ACTION_WORK | {"approve", "reject"}),
        "credit": set(ACTION_APPROVE),
        "orders": set(ACTION_FULL_NO_DELETE),
        "commissions": set(ACTION_APPROVE),
        "products": set(ACTION_READ),
        "categories": set(ACTION_READ),
        "media_library": set(ACTION_READ),
        "stock": set(ACTION_READ),
        "announcements": set(ACTION_WORK),
        "service_technicians": set(ACTION_WORK),
        "quotes": set(ACTION_FULL_NO_DELETE),
        "collections": set(ACTION_READ | {"edit"}),
        "dispatch": set(ACTION_READ),
        "reports": set(ACTION_AUDIT),
        "import_templates": set(ACTION_READ),
        "audit": set(ACTION_AUDIT),
        "documents": set(ACTION_READ),
    },
    "operator": {
        "dashboard": set(ACTION_READ),
        "sellers": set(ACTION_WORK),
        "clients": set(ACTION_WORK),
        "credit": {"view", "export", "audit"},
        "orders": {"view", "create", "edit", "annul", "export", "audit"},
        "commissions": set(ACTION_READ),
        "products": set(ACTION_WORK),
        "categories": set(ACTION_WORK),
        "media_library": set(ACTION_WORK),
        "stock": {"view", "create", "edit", "export", "import", "audit"},
        "announcements": set(ACTION_WORK),
        "service_technicians": set(ACTION_WORK),
        "quotes": {"view", "create", "edit", "export", "audit"},
        "collections": set(ACTION_READ),
        "dispatch": set(ACTION_READ | {"edit"}),
        "reports": set(ACTION_READ),
        "import_templates": set(ACTION_READ),
        "documents": set(ACTION_WORK),
    },
    "inventory": {
        "dashboard": set(ACTION_READ),
        "products": set(ACTION_WORK),
        "categories": set(ACTION_WORK),
        "media_library": set(ACTION_WORK),
        "stock": {"view", "create", "edit", "annul", "export", "import", "audit"},
        "orders": set(ACTION_READ),
        "dispatch": set(ACTION_READ),
        "import_templates": set(ACTION_READ),
        "documents": set(ACTION_WORK),
    },
    "collections": {
        "dashboard": set(ACTION_READ),
        "clients": set(ACTION_READ),
        "credit": set(ACTION_READ | {"edit"}),
        "orders": set(ACTION_READ | {"edit"}),
        "collections": {"view", "create", "edit", "export", "audit"},
        "reports": set(ACTION_READ),
        "import_templates": set(ACTION_READ),
        "documents": set(ACTION_READ),
    },
    "dispatch": {
        "dashboard": set(ACTION_READ),
        "orders": set(ACTION_READ | {"edit"}),
        "stock": set(ACTION_READ),
        "dispatch": {"view", "create", "edit", "annul", "export", "audit"},
        "service_technicians": set(ACTION_READ),
        "reports": set(ACTION_READ),
        "documents": set(ACTION_READ),
    },
    "auditor": {
        module: set(ACTION_AUDIT) for module in ALL_MODULE_KEYS if module not in {"admin_users", "permissions", "settings"}
    },
    "readonly": {
        module: set(ACTION_VIEW) for module in [
            "dashboard",
            "sellers",
            "clients",
            "credit",
            "orders",
            "commissions",
            "products",
            "categories",
            "media_library",
            "stock",
            "announcements",
            "service_technicians",
            "quotes",
            "collections",
            "dispatch",
            "reports",
            "import_templates",
            "documents",
        ]
    },
}
ROLE_MODULE_PERMISSIONS["general_manager"].update({
    "credit": set(ACTION_APPROVE),
    "orders": set(ACTION_FULL_NO_DELETE),
    "commissions": set(ACTION_APPROVE),
})
MODULE_ACCESS = {
    module: {
        role
        for role, permissions in ROLE_MODULE_PERMISSIONS.items()
        if "view" in permissions.get(module, set())
    }
    for module in ALL_MODULE_KEYS
}
ADMIN_MENU_GROUPS = [
    {
        "label": "Comercial",
        "icon": "bi-briefcase",
        "items": [
            {"module": "sellers", "endpoint": "sellers", "label": "Vendedores", "icon": "bi-person-badge", "active": ["sellers", "seller_edit", "sellers_import", "seller_delete"]},
            {"module": "clients", "endpoint": "clients", "label": "Clientes", "icon": "bi-shop", "active": ["clients", "client_edit", "client_status_update", "clients_import", "client_delete"]},
            {"module": "credit", "endpoint": "credit", "label": "Credito B2B", "icon": "bi-credit-card-2-front", "active": ["credit", "credit_decision", "credit_due", "credit_history"]},
            {"module": "collections", "endpoint": "collections", "label": "Cobranza", "icon": "bi-cash-coin", "active": ["collections", "collections_export", "collection_action", "collection_statement"]},
            {"module": "orders", "endpoint": "orders", "label": "Ordenes", "icon": "bi-receipt", "active": ["orders", "orders_export", "order_new", "order_status_update", "order_payment_create"]},
            {"module": "commissions", "endpoint": "commissions", "label": "Comisiones", "icon": "bi-percent", "active": ["commissions", "commission_status_update"]},
        ],
    },
    {
        "label": "Catalogo",
        "icon": "bi-box-seam",
        "items": [
            {"module": "products", "endpoint": "products", "label": "Productos", "icon": "bi-box-seam", "active": ["products", "product_new", "product_edit", "products_import", "products_export", "product_duplicate", "product_delete"]},
            {"module": "categories", "endpoint": "categories", "label": "Categorias", "icon": "bi-tags", "active": ["categories", "category_edit", "categories_import", "categories_export", "category_status", "category_delete"]},
            {"module": "media_library", "endpoint": "media_library", "label": "Biblioteca tecnica", "icon": "bi-folder2-open", "active": ["media_library", "media_library_import", "media_asset_delete"]},
            {"module": "stock", "endpoint": "stock", "label": "Stock masivo", "icon": "bi-boxes", "active": ["stock", "stock_import", "stock_export"]},
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
            {"module": "permissions", "endpoint": "permissions", "label": "Roles y permisos", "icon": "bi-shield-lock", "active": ["permissions"]},
            {"module": "admin_users", "endpoint": "admin_users", "label": "Usuarios admin", "icon": "bi-people", "active": ["admin_users", "admin_user_edit", "admin_user_delete", "admin_user_status", "admin_user_reset_password", "admin_user_revoke_sessions"]},
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
                    {"name": "nombre_completo", "required": True, "example": "Carlos Perez", "help": "Nombre visible del vendedor."},
                    {"name": "email", "required": True, "example": "carlos@wulkanvenezuela.com", "help": "Correo unico para login movil."},
                    {"name": "telefono", "required": False, "example": "+584120000000", "help": "Telefono o WhatsApp."},
                    {"name": "codigo_vendedor", "required": False, "example": "VEN-CAR-01", "help": "Codigo interno comercial."},
                    {"name": "zona", "required": False, "example": "Caracas", "help": "Zona o cartera principal."},
                    {"name": "territorio", "required": False, "example": "Centro - Ruta A", "help": "Ruta, territorio o cobertura."},
                    {"name": "supervisor", "required": False, "example": "Gerente Comercial", "help": "Responsable interno del vendedor."},
                    {"name": "comision", "required": False, "example": "5", "help": "Porcentaje de comision."},
                    {"name": "meta_mensual_usd", "required": False, "example": "2500", "help": "Meta comercial mensual."},
                    {"name": "fecha_ingreso", "required": False, "example": "2026-06-01", "help": "Fecha de ingreso comercial."},
                    {"name": "acceso_movil", "required": False, "example": "si", "help": "si/no para permitir ingreso desde la app."},
                    {"name": "estado", "required": False, "example": "active", "help": "active, inactive, blocked o suspended."},
                    {"name": "clave", "required": False, "example": "Temporal2026", "help": "Si viene vacia se genera clave temporal."},
                    {"name": "observacion", "required": False, "example": "Cartera inicial zona centro", "help": "Notas internas comerciales."},
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
                    {"name": "razon_social", "required": False, "example": "Ferreteria Principal C.A.", "help": "Nombre legal para documentos fiscales."},
                    {"name": "nombre_comercial", "required": False, "example": "Ferreteria Principal", "help": "Nombre visible en app y cartera."},
                    {"name": "email", "required": True, "example": "compras@ferreteriaprincipal.com", "help": "Correo unico para acceso movil."},
                    {"name": "rif", "required": False, "example": "J-12345678-9", "help": "Identificacion fiscal."},
                    {"name": "contacto", "required": False, "example": "Maria Gonzalez", "help": "Responsable de compras."},
                    {"name": "contacto_administrativo", "required": False, "example": "Luis Perez", "help": "Responsable de pagos o administracion."},
                    {"name": "contacto_recepcion", "required": False, "example": "Ana Torres", "help": "Responsable de recibir mercancia."},
                    {"name": "telefono", "required": False, "example": "+584140000000", "help": "Telefono o WhatsApp."},
                    {"name": "whatsapp", "required": False, "example": "+584120000000", "help": "WhatsApp principal si es distinto al telefono."},
                    {"name": "direccion", "required": False, "example": "Av. Bolivar, local 12", "help": "Direccion fiscal o despacho."},
                    {"name": "direccion_fiscal", "required": False, "example": "Av. Bolivar, local 12", "help": "Direccion fiscal."},
                    {"name": "direccion_despacho", "required": False, "example": "Galpon 4, Zona Industrial", "help": "Direccion de entrega."},
                    {"name": "ciudad", "required": False, "example": "Valencia", "help": "Ciudad del cliente."},
                    {"name": "estado_ubicacion", "required": False, "example": "Carabobo", "help": "Estado o region."},
                    {"name": "pais", "required": False, "example": "VE", "help": "Pais del cliente."},
                    {"name": "zona", "required": False, "example": "Centro", "help": "Zona de despacho o cartera."},
                    {"name": "vendedor_email", "required": False, "example": "carlos@wulkanvenezuela.com", "help": "Asigna cartera por email del vendedor."},
                    {"name": "tipo_cliente", "required": False, "example": "ferretero", "help": "ferretero, distribuidor o cliente_especial."},
                    {"name": "categoria_comercial", "required": False, "example": "preferential", "help": "standard, preferential, strategic o wholesale."},
                    {"name": "lista_precios", "required": False, "example": "b2b", "help": "b2b, retail, wholesale o special."},
                    {"name": "descuento_autorizado", "required": False, "example": "5", "help": "Descuento comercial maximo autorizado."},
                    {"name": "estado", "required": False, "example": "active", "help": "active, prospect, review, inactive, suspended o bloqueos."},
                    {"name": "estado_cobranza", "required": False, "example": "without_debt", "help": "without_debt, current, due_soon, overdue, promise o blocked."},
                    {"name": "riesgo_credito", "required": False, "example": "low", "help": "low, medium, high o critical."},
                    {"name": "score_credito", "required": False, "example": "82", "help": "Score interno de 0 a 100. Si viene vacio se calcula."},
                    {"name": "observacion_gerencia", "required": False, "example": "Cupo inicial sujeto a revision mensual.", "help": "Nota privada para decisiones de credito."},
                    {"name": "estado_credito", "required": False, "example": "pending", "help": "none, pending, review, approved, rejected, suspended, blocked_debt o blocked_limit."},
                    {"name": "credito_solicitado_usd", "required": False, "example": "1500", "help": "Monto solicitado por el cliente o vendedor."},
                    {"name": "deuda_manual_usd", "required": False, "example": "0", "help": "Deuda externa anterior a la plataforma."},
                    {"name": "tipo_venta_default", "required": False, "example": "credit_line", "help": "cash, term_credit o credit_line."},
                    {"name": "cupo_usd", "required": False, "example": "1000", "help": "Linea aprobada si el rol puede aprobar."},
                    {"name": "credito_aprobado", "required": False, "example": "si", "help": "si/no. Solo gerente o super admin aprueba."},
                    {"name": "dias_credito", "required": False, "example": "15", "help": "Plazo aprobado por defecto."},
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
                    {"name": "codigo_interno", "required": False, "example": "MOT-45-2026", "help": "Codigo interno administrativo o ERP."},
                    {"name": "nombre", "required": True, "example": "Motosierra Wulkan 45cc", "help": "Nombre visible comercial."},
                    {"name": "categoria", "required": True, "example": "Maquinaria y jardin", "help": "Familia del catalogo."},
                    {"name": "subcategoria", "required": False, "example": "Motosierras", "help": "Linea interna dentro de la categoria."},
                    {"name": "marca", "required": False, "example": "Wulkan", "help": "Marca comercial."},
                    {"name": "modelo", "required": False, "example": "45CC", "help": "Modelo o referencia visible."},
                    {"name": "unidad_venta", "required": False, "example": "unidad", "help": "Unidad, kit, caja, metro, litro, etc."},
                    {"name": "descripcion_corta", "required": False, "example": "Equipo de corte para jardin y finca.", "help": "Resumen corto para listados."},
                    {"name": "descripcion_larga", "required": False, "example": "Incluye espada, cadena y garantia Wulkan.", "help": "Detalle ampliado para ficha de producto."},
                    {"name": "precio_publico_usd", "required": True, "example": "185", "help": "Precio PVP en dolares."},
                    {"name": "precio_b2b_usd", "required": False, "example": "162", "help": "Precio ferretero."},
                    {"name": "costo_referencial_usd", "required": False, "example": "120", "help": "Costo interno referencial. No se publica en app."},
                    {"name": "margen_porcentaje", "required": False, "example": "25", "help": "Margen estimado administrativo."},
                    {"name": "stock", "required": False, "example": "12", "help": "Stock fisico inicial."},
                    {"name": "stock_minimo", "required": False, "example": "3", "help": "Punto de alerta de reposicion."},
                    {"name": "stock_maximo", "required": False, "example": "30", "help": "Stock objetivo o maximo."},
                    {"name": "descripcion", "required": False, "example": "Equipo para uso tecnico y jardin.", "help": "Descripcion app movil."},
                    {"name": "tipo_producto", "required": False, "example": "machine", "help": "machine, spare_part, accessory, service o consumable."},
                    {"name": "precio_anterior_usd", "required": False, "example": "210", "help": "Precio antes del descuento."},
                    {"name": "descuento_porcentaje", "required": False, "example": "12", "help": "Descuento visible."},
                    {"name": "tasa_usd_ves", "required": False, "example": "38.5", "help": "Referencia VES."},
                    {"name": "imagen_principal", "required": False, "example": "https://cdn.wulkan/producto.jpg", "help": "Imagen principal."},
                    {"name": "imagenes", "required": False, "example": "https://cdn.wulkan/1.jpg|https://cdn.wulkan/2.jpg", "help": "Galeria separada por |, coma o salto de linea."},
                    {"name": "pdf_tecnicos", "required": False, "example": "https://cdn.wulkan/ficha.pdf", "help": "Fichas tecnicas."},
                    {"name": "variantes", "required": False, "example": "18 pulgadas|20 pulgadas", "help": "Opciones visibles."},
                    {"name": "especificaciones", "required": False, "example": "Motor:45cc|Garantia:6 meses", "help": "Formato clave:valor."},
                    {"name": "skus_relacionados", "required": False, "example": "WUL-REP-CAD18|WUL-ACE-2T", "help": "Productos relacionados por SKU."},
                    {"name": "requiere_cotizacion", "required": False, "example": "no", "help": "si/no."},
                    {"name": "requiere_validacion_tecnica", "required": False, "example": "si", "help": "si/no."},
                    {"name": "visible_app", "required": False, "example": "si", "help": "si/no para publicar en app movil."},
                    {"name": "destacado", "required": False, "example": "si", "help": "si/no para destacar en app."},
                    {"name": "oferta", "required": False, "example": "si", "help": "si/no para marcar como oferta."},
                    {"name": "estado", "required": False, "example": "active", "help": "active, inactive, out, replenishment, hidden o discontinued."},
                ],
            },
            {
                "key": "categorias",
                "module": "categories",
                "endpoint": "categories",
                "title": "Categorias",
                "description": "Familias del catalogo con imagen, icono, orden y visibilidad para app movil.",
                "columns": [
                    {"name": "nombre", "required": True, "example": "Repuestos", "help": "Nombre de categoria."},
                    {"name": "slug", "required": False, "example": "repuestos", "help": "Identificador publico. Si viene vacio se genera desde el nombre."},
                    {"name": "descripcion", "required": False, "example": "Piezas y consumibles compatibles por SKU.", "help": "Texto visible."},
                    {"name": "imagen_url", "required": False, "example": "https://cdn.wulkan/categorias/repuestos.jpg", "help": "Imagen de categoria."},
                    {"name": "icono", "required": False, "example": "bi-tools", "help": "Icono Bootstrap opcional para panel/app."},
                    {"name": "orden", "required": False, "example": "20", "help": "Orden de aparicion en app movil."},
                    {"name": "categoria_padre", "required": False, "example": "Maquinaria", "help": "Nombre, slug o id de categoria padre."},
                    {"name": "visible_app", "required": False, "example": "si", "help": "si/no para publicar en app movil."},
                    {"name": "estado", "required": False, "example": "active", "help": "active, inactive o hidden."},
                ],
            },
            {
                "key": "stock",
                "module": "stock",
                "endpoint": "stock",
                "title": "Stock",
                "description": "Actualizacion masiva de inventario fisico, minimo, maximo, ubicacion y observacion por SKU.",
                "columns": [
                    {"name": "sku", "required": True, "example": "WUL-MOT-45CC", "help": "Debe existir en productos."},
                    {"name": "cantidad", "required": True, "example": "25", "help": "Stock fisico final."},
                    {"name": "stock_minimo", "required": False, "example": "3", "help": "Punto de alerta operativa."},
                    {"name": "stock_maximo", "required": False, "example": "40", "help": "Stock objetivo o maximo sugerido."},
                    {"name": "stock_reposicion", "required": False, "example": "15", "help": "Cantidad sugerida para reposicion."},
                    {"name": "ubicacion", "required": False, "example": "Almacen Valencia A-02", "help": "Ubicacion fisica o bodega."},
                    {"name": "tipo", "required": False, "example": "bulk_excel_set", "help": "entry, exit, adjustment, bulk_excel_set o return."},
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
            if user.get("role") != "sales" and user.get("status") != "deleted"
        ],
        key=lambda user: user.get("name", ""),
    )


def current_admin_user(store: dict) -> dict | None:
    return find_by_id(store.get("admin_users", []), session.get("admin_user_id", ""))


def user_session_version(user: dict | None) -> int:
    return safe_int((user or {}).get("sessionVersion"), 0)


def bump_user_session_version(user: dict) -> None:
    user["sessionVersion"] = user_session_version(user) + 1
    user["updatedAt"] = utc_now()


def admin_user_by_email(store: dict, email: str) -> dict | None:
    normalized = email.strip().lower()
    return next(
        (
            user
            for user in store.get("admin_users", [])
            if user.get("email", "").lower() == normalized
        ),
        None,
    )


def register_admin_user_failed_attempt(store: dict, email: str) -> None:
    user = admin_user_by_email(store, email)
    if not user:
        return
    user["failedLoginAttempts"] = safe_int(user.get("failedLoginAttempts")) + 1
    user["lastFailedLoginAt"] = utc_now()
    user["lastLoginIp"] = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    if user["failedLoginAttempts"] >= int(app.config.get("LOGIN_MAX_ATTEMPTS", 5)):
        user["status"] = "blocked"
        bump_user_session_version(user)
    else:
        user["updatedAt"] = utc_now()


def reset_admin_user_failed_attempts(user: dict) -> None:
    user["failedLoginAttempts"] = 0
    user["lastFailedLoginAt"] = ""
    user["lastLoginIp"] = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    user["updatedAt"] = utc_now()


def temporary_admin_password() -> str:
    return f"Wulkan{secrets.randbelow(900000) + 100000}"


def current_seller_assignment(store: dict) -> tuple[str, str]:
    if current_admin_role() != "sales":
        return "", ""
    user = current_admin_user(store)
    if not user:
        return "", ""
    return user.get("id", ""), user.get("name", "")


def sale_type_label(value: str) -> str:
    return dict(SALE_TYPE_OPTIONS).get(value, value or "Sin definir")


def client_status_label(value: str) -> str:
    return dict(CLIENT_STATUS_OPTIONS).get(value, value or "Sin estado")


def collection_status_label(value: str) -> str:
    labels = {**dict(COLLECTION_STATUS_OPTIONS), **dict(ORDER_COLLECTION_STATUS_OPTIONS)}
    return labels.get(value, value or "Sin cobranza")


def client_type_label(value: str) -> str:
    return dict(CLIENT_TYPE_OPTIONS).get(value, value or "Sin tipo")


def seller_status_label(value: str) -> str:
    return dict(SELLER_STATUS_OPTIONS).get(value, value or "Sin estado")


def product_status_label(value: str) -> str:
    return dict(PRODUCT_STATUS_OPTIONS).get(value, value or "Sin estado")


def category_status_label(value: str) -> str:
    return dict(CATEGORY_STATUS_OPTIONS).get(value, value or "Sin estado")


def order_status_label(value: str) -> str:
    return dict(ORDER_STATUS_OPTIONS).get(value, value or "Sin estado")


def sales_channel_label(value: str) -> str:
    return SALES_CHANNEL_LABELS.get(value, value or "Sin canal")


def dispatch_status_label(value: str) -> str:
    return DISPATCH_STATUS_LABELS.get(value, value or "Sin despacho")


def due_status_label(value: str) -> str:
    return {
        "paid": "Pagado",
        "current": "Al dia",
        "due_soon": "Por vencer",
        "overdue": "Vencido",
        "without_due_date": "Sin fecha",
    }.get(value, value or "Sin vencimiento")


def credit_status_label(value: str) -> str:
    labels = {
        **dict(CREDIT_REQUEST_STATUS_OPTIONS),
        "approved": "Aprobado",
        "available": "Disponible",
        "in_use": "En uso",
        "exhausted": "Cupo agotado",
        "pending": "Solicitado",
        "review": "En evaluacion",
        "suspended": "Suspendido",
        "blocked_debt": "Bloqueado por mora",
        "blocked_limit": "Bloqueado por cupo",
        "manual_review": "Revision manual",
        "without_credit": "Sin linea",
        "client_not_active": "Cliente inactivo",
        "cancelled": "Cancelado",
        "released": "Liberado",
    }
    return labels.get(value, value or "Sin credito")


def credit_risk_label(value: str) -> str:
    return dict(CREDIT_RISK_OPTIONS).get(value, value or "Sin riesgo")


def payment_status_label(value: str) -> str:
    labels = {
        "pending": "Pendiente",
        "partial": "Pago parcial",
        "paid": "Pagado",
    }
    return labels.get(value, value or "Sin pago")


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


def parse_filter_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def safe_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def safe_float(value, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def date_value_is_today(value: str | None) -> bool:
    if not value:
        return False
    return parse_utc_datetime(value).date() == datetime.now(timezone.utc).date()


def dashboard_filters_from_request() -> dict[str, str]:
    return {
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
        "seller": request.args.get("seller", "").strip(),
        "client": request.args.get("client", "").strip(),
        "category": request.args.get("category", "").strip(),
        "product": request.args.get("product", "").strip(),
        "order_status": request.args.get("order_status", "").strip(),
        "credit_status": request.args.get("credit_status", "").strip(),
        "collection_status": request.args.get("collection_status", "").strip(),
        "dispatch_status": request.args.get("dispatch_status", "").strip(),
        "sale_type": request.args.get("sale_type", "").strip(),
        "branch": request.args.get("branch", "").strip(),
    }


def product_lookup_maps(products: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    by_id = {product.get("id", ""): product for product in products if product.get("id")}
    by_sku = {product.get("sku", ""): product for product in products if product.get("sku")}
    return by_id, by_sku


def order_products(order: dict, products_by_id: dict[str, dict], products_by_sku: dict[str, dict]) -> list[dict]:
    products: list[dict] = []
    for item in order.get("items") or []:
        product = products_by_id.get(item.get("productId", "")) or products_by_sku.get(item.get("sku", ""))
        if product:
            products.append(product)
    return products


def order_matches_dashboard_filters(
    order: dict,
    filters: dict[str, str],
    products_by_id: dict[str, dict],
    products_by_sku: dict[str, dict],
) -> bool:
    created_at = parse_utc_datetime(order.get("createdAt", ""))
    date_from = parse_filter_date(filters.get("date_from"))
    date_to = parse_filter_date(filters.get("date_to"))
    if date_from and created_at < date_from:
        return False
    if date_to and created_at >= date_to + timedelta(days=1):
        return False
    if filters.get("seller") and order.get("sellerId", "") != filters["seller"]:
        return False
    if filters.get("client") and order.get("customerId", "") != filters["client"]:
        return False
    if filters.get("order_status") and order.get("status", "") != filters["order_status"]:
        return False
    if filters.get("credit_status") and order.get("creditStatus", "") != filters["credit_status"]:
        return False
    if filters.get("collection_status") and order.get("dueStatus", "") != filters["collection_status"]:
        return False
    if filters.get("dispatch_status") and order.get("dispatchStatus", "") != filters["dispatch_status"]:
        return False
    if filters.get("sale_type") and order.get("saleType", "") != filters["sale_type"]:
        return False
    if filters.get("branch") and order.get("branch", "") != filters["branch"]:
        return False

    if not filters.get("category") and not filters.get("product"):
        return True

    products = order_products(order, products_by_id, products_by_sku)
    if filters.get("product"):
        return any(product.get("id", "") == filters["product"] for product in products)
    return any(product.get("categoryId", "") == filters["category"] for product in products)


def graphify_from_pairs(pairs: list[tuple[str, float]], limit: int = 6) -> dict:
    sorted_pairs = sorted(pairs, key=lambda item: item[1], reverse=True)[:limit]
    return {
        "labels": [label for label, _value in sorted_pairs],
        "values": [round(float(value), 2) for _label, value in sorted_pairs],
    }


def dashboard_order_metrics(
    orders: list[dict],
    clients: list[dict],
    products: list[dict],
    sellers: list[dict],
) -> dict:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    pending_statuses = {"credit_review", "payment_under_review"}
    approved_statuses = {"approved_with_credit", "preparing", "delivered", "partial_paid", "paid"}
    rejected_statuses = {"rejected"}
    open_balances = [float(order.get("balanceUsd") or 0) for order in orders if order.get("status") != "cancelled"]
    overdue_orders = [
        order
        for order in orders
        if order.get("dueStatus") == "overdue" and float(order.get("balanceUsd") or 0) > 0
    ]
    client_ids_with_overdue = {order.get("customerId", "") for order in overdue_orders}
    return {
        "sales_today": round(sum(float(order.get("totalUsd") or 0) for order in orders if date_value_is_today(order.get("createdAt", ""))), 2),
        "sales_month": round(
            sum(float(order.get("totalUsd") or 0) for order in orders if parse_utc_datetime(order.get("createdAt", "")) >= month_start),
            2,
        ),
        "sales_total": round(sum(float(order.get("totalUsd") or 0) for order in orders), 2),
        "orders_new": sum(1 for order in orders if date_value_is_today(order.get("createdAt", ""))),
        "orders_pending": sum(1 for order in orders if order.get("status") in pending_statuses),
        "orders_approved": sum(1 for order in orders if order.get("status") in approved_statuses),
        "orders_rejected": sum(1 for order in orders if order.get("status") in rejected_statuses),
        "orders_cancelled": sum(1 for order in orders if order.get("status") == "cancelled"),
        "orders_delivered": sum(1 for order in orders if order.get("status") == "delivered"),
        "clients_active": sum(1 for client in clients if client.get("status") == "active"),
        "clients_inactive": sum(1 for client in clients if client.get("status") == "inactive"),
        "clients_new": sum(1 for client in clients if date_value_is_today(client.get("createdAt", ""))),
        "clients_blocked": sum(1 for client in clients if "blocked" in str(client.get("status", "")).lower()),
        "clients_overdue": len(client_ids_with_overdue),
        "credit_approved": round(sum(float(client.get("creditLimitUsd") or 0) for client in clients if client.get("creditEnabled")), 2),
        "credit_used": round(sum(float(client.get("creditExposureUsd") or 0) for client in clients), 2),
        "credit_available": round(sum(float(client.get("creditAvailableUsd") or 0) for client in clients), 2),
        "accounts_receivable": round(sum(open_balances), 2),
        "overdue_debt": round(sum(float(order.get("balanceUsd") or 0) for order in overdue_orders), 2),
        "stock_critical": sum(
            1
            for product in products
            if safe_int(product.get("availableStock")) > 0
            and safe_int(product.get("availableStock")) <= safe_int(product.get("minimumStock") or product.get("stockMin") or product.get("minStock"), 5)
        ),
        "products_out": sum(1 for product in products if safe_int(product.get("availableStock")) <= 0),
        "top_products": len({item.get("productId", "") or item.get("sku", "") for order in orders for item in order.get("items") or []}),
        "sellers_active": sum(1 for seller in sellers if seller.get("status") == "active"),
        "commission_pending": round(sum(float(order.get("commissionUsd") or 0) for order in orders if order.get("commissionStatus") == "commission_pending"), 2),
        "commission_approved": round(sum(float(order.get("commissionUsd") or 0) for order in orders if order.get("commissionStatus") == "commission_approved"), 2),
        "commission_paid": round(sum(float(order.get("commissionUsd") or 0) for order in orders if order.get("commissionStatus") == "commission_paid"), 2),
    }


def dashboard_charts(
    orders: list[dict],
    clients: list[dict],
    products_by_id: dict[str, dict],
    products_by_sku: dict[str, dict],
) -> dict:
    sales_by_day: dict[str, float] = {}
    sales_by_month: dict[str, float] = {}
    sales_by_seller: dict[str, float] = {}
    sales_by_category: dict[str, float] = {}
    products_sold: dict[str, int] = {}
    clients_purchase: dict[str, float] = {}
    overdue_by_client: dict[str, float] = {}
    commissions_by_seller: dict[str, float] = {}
    client_names = {client.get("id", ""): client.get("businessName", "Cliente Wulkan") for client in clients}

    for order in orders:
        created_at = parse_utc_datetime(order.get("createdAt", ""))
        day_key = created_at.strftime("%d/%m")
        month_key = created_at.strftime("%Y-%m")
        total = float(order.get("totalUsd") or 0)
        sales_by_day[day_key] = sales_by_day.get(day_key, 0) + total
        sales_by_month[month_key] = sales_by_month.get(month_key, 0) + total
        seller_name = order.get("sellerName") or "Sin vendedor"
        sales_by_seller[seller_name] = sales_by_seller.get(seller_name, 0) + total
        commissions_by_seller[seller_name] = commissions_by_seller.get(seller_name, 0) + float(order.get("commissionUsd") or 0)
        client_name = client_names.get(order.get("customerId", ""), order.get("customer", {}).get("name", "Cliente Wulkan"))
        clients_purchase[client_name] = clients_purchase.get(client_name, 0) + total
        if order.get("dueStatus") == "overdue":
            overdue_by_client[client_name] = overdue_by_client.get(client_name, 0) + float(order.get("balanceUsd") or 0)
        for item in order.get("items") or []:
            quantity = int(item.get("quantity") or 0)
            product = products_by_id.get(item.get("productId", "")) or products_by_sku.get(item.get("sku", ""))
            product_label = (product or {}).get("sku") or item.get("sku") or item.get("title", "Producto")
            products_sold[product_label] = products_sold.get(product_label, 0) + quantity
            category_label = (product or {}).get("categoryName") or "Sin categoria"
            sales_by_category[category_label] = sales_by_category.get(category_label, 0) + float(item.get("lineTotalUsd") or 0)

    return {
        "sales_by_day": graphify_from_pairs(list(sales_by_day.items()), 8),
        "sales_by_month": graphify_from_pairs(list(sales_by_month.items()), 6),
        "sales_by_seller": graphify_from_pairs(list(sales_by_seller.items()), 6),
        "sales_by_category": graphify_from_pairs(list(sales_by_category.items()), 6),
        "products_sold": graphify_from_pairs(list(products_sold.items()), 6),
        "clients_purchase": graphify_from_pairs(list(clients_purchase.items()), 6),
        "overdue_by_client": graphify_from_pairs(list(overdue_by_client.items()), 6),
        "commissions_by_seller": graphify_from_pairs(list(commissions_by_seller.items()), 6),
    }


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


def product_has_commercial_history(store: dict, product: dict | None) -> bool:
    if not product:
        return False
    product_id = product.get("id", "")
    sku = product.get("sku", "")
    for order in store.get("orders", []):
        for item in order.get("items", []):
            if item.get("productId") == product_id or item.get("sku") == sku:
                return True
    return any(
        movement.get("productId") == product_id or movement.get("sku") == sku
        for movement in store.get("stock_movements", [])
    )


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


def role_permission_actions(role: str, module: str) -> set[str]:
    return set(ROLE_MODULE_PERMISSIONS.get(role, {}).get(module, set()))


def role_can(role: str, module: str, action: str = "view") -> bool:
    return action in role_permission_actions(role, module)


def roles_for_action(module: str, action: str = "view") -> tuple[str, ...]:
    return tuple(role for role in WEB_ADMIN_ROLE_ORDER if role_can(role, module, action))


def can_module_action(module: str, action: str = "view") -> bool:
    return role_can(current_admin_role(), module, action)


def can_access_module(module: str) -> bool:
    return can_module_action(module, "view")


def can_delete_data() -> bool:
    return any(role_can(current_admin_role(), module, "delete") for module in ALL_MODULE_KEYS)


def permission_matrix_rows() -> list[dict]:
    rows: list[dict] = []
    for module, label, icon, description in PERMISSION_MODULES:
        roles = {}
        for role in WEB_ADMIN_ROLE_ORDER:
            roles[role] = sorted(
                role_permission_actions(role, module),
                key=lambda action: ACTION_ORDER.index(action) if action in ACTION_ORDER else 999,
            )
        rows.append({
            "module": module,
            "label": label,
            "icon": icon,
            "description": description,
            "roles": roles,
        })
    return rows


def permission_metrics(rows: list[dict]) -> dict:
    protected_modules = [row for row in rows if any(row["roles"].get(role) for role in WEB_ADMIN_ROLE_ORDER)]
    write_roles = {
        role
        for row in rows
        for role in WEB_ADMIN_ROLE_ORDER
        if any(action in {"create", "edit", "annul", "approve", "reject", "import", "delete"} for action in row["roles"].get(role, []))
    }
    admin_only_modules = [
        row for row in rows
        if row["roles"].get("super_admin") and not any(row["roles"].get(role) for role in WEB_ADMIN_ROLE_ORDER if role != "super_admin")
    ]
    return {
        "roles": len(WEB_ADMIN_ROLE_ORDER),
        "modules": len(protected_modules),
        "write_roles": len(write_roles),
        "admin_only": len(admin_only_modules),
    }


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
        "can_module_action": can_module_action,
        "can_delete_data": can_delete_data,
        "current_admin_role": current_admin_role,
        "admin_menu_groups": admin_menu_groups,
        "permission_actions": PERMISSION_ACTIONS,
        "role_labels": ROLE_LABELS,
        "sale_type_label": sale_type_label,
        "client_status_label": client_status_label,
        "collection_status_label": collection_status_label,
        "credit_status_label": credit_status_label,
        "credit_risk_label": credit_risk_label,
        "client_type_label": client_type_label,
        "seller_status_label": seller_status_label,
        "product_status_label": product_status_label,
        "commission_status_label": commission_status_label,
        "sales_channel_label": sales_channel_label,
        "dispatch_status_label": dispatch_status_label,
        "due_status_label": due_status_label,
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

    if safe_int(session.get("admin_session_version")) != user_session_version(admin_user):
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
            register_admin_user_failed_attempt(store, email)
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
            register_admin_user_failed_attempt(store, email)
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
            session["admin_session_version"] = user_session_version(admin_user)
            admin_user["lastLoginAt"] = utc_now()
            reset_admin_user_failed_attempts(admin_user)
            record_audit_event(
                store,
                "login",
                "admin_user",
                admin_user["id"],
                "Inicio de sesion admin.",
                metadata={"ipAddress": admin_user.get("lastLoginIp", "")},
            )
            save_store(store)
            if session.get("must_change_password"):
                return redirect(url_for("account_password"))
            return redirect(request.args.get("next") or url_for("dashboard"))

        register_login_failure("admin", email)
        register_admin_user_failed_attempt(store, email)
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
    if session.get("admin_authenticated"):
        store = load_store()
        admin_user = current_admin_user(store)
        if admin_user:
            record_audit_event(
                store,
                "logout",
                "admin_user",
                admin_user["id"],
                "Cierre de sesion admin.",
                actor={"id": admin_user["id"], "name": admin_user.get("name", ""), "role": admin_user.get("role", "")},
            )
            save_store(store)
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
            bump_user_session_version(admin_user)
            session["must_change_password"] = False
            session["admin_session_version"] = user_session_version(admin_user)
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
    if (
        not user
        or user.get("status") != "active"
        or user.get("role") not in MOBILE_SALES_ROLES
        or user.get("mobileAccessEnabled", True) is False
    ):
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
        if (
            user
            and user.get("status") == "active"
            and user.get("role") in MOBILE_SALES_ROLES
            and user.get("mobileAccessEnabled", True) is not False
        ):
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
            "legalName": enriched.get("legalName", ""),
            "commercialName": enriched.get("commercialName", ""),
            "email": enriched["email"],
            "clientType": enriched["clientType"],
            "clientCategory": enriched.get("clientCategory", "standard"),
            "priceList": enriched.get("priceList", "b2b"),
            "authorizedDiscountPercent": enriched.get("authorizedDiscountPercent", 0),
            "status": enriched.get("status", ""),
            "statusLabel": enriched.get("statusLabel", ""),
            "taxId": enriched.get("taxId", ""),
            "phone": enriched.get("phone", ""),
            "whatsapp": enriched.get("whatsapp", ""),
            "address": enriched.get("address", ""),
            "fiscalAddress": enriched.get("fiscalAddress", ""),
            "shippingAddress": enriched.get("shippingAddress", ""),
            "city": enriched.get("city", ""),
            "state": enriched.get("state", ""),
            "country": enriched.get("country", "VE"),
            "deliveryZone": enriched.get("deliveryZone", ""),
            "contactName": enriched.get("contactName", ""),
            "administrativeContact": enriched.get("administrativeContact", ""),
            "receivingContact": enriched.get("receivingContact", ""),
            "accountRole": "client",
            "roleLabel": "Ferretero B2B",
            "creditEnabled": enriched["creditEnabled"],
            "creditLimitUsd": enriched["creditLimitUsd"],
            "creditUsedUsd": enriched["creditUsedUsd"],
            "creditOrdersUsd": enriched["creditOrdersUsd"],
            "creditExposureUsd": enriched["creditExposureUsd"],
            "creditAvailableUsd": enriched["creditAvailableUsd"],
            "currentDebtUsd": enriched.get("currentDebtUsd", 0.0),
            "creditStatus": enriched.get("creditStatus", "without_credit"),
            "creditStatusLabel": enriched.get("creditStatusLabel", ""),
            "creditRequestStatus": enriched.get("creditRequestStatus", "none"),
            "creditRequestStatusLabel": enriched.get("creditRequestStatusLabel", ""),
            "creditScore": enriched.get("creditScore", 0),
            "paymentTermsDays": enriched["paymentTermsDays"],
            "allowedPaymentTermsDays": enriched.get("allowedPaymentTermsDays", [0]),
            "defaultSaleType": enriched.get("defaultSaleType", "cash"),
            "collectionStatus": enriched.get("collectionStatus", "without_debt"),
            "collectionStatusLabel": enriched.get("collectionStatusLabel", ""),
            "creditRiskLevel": enriched.get("creditRiskLevel", "low"),
            "creditRiskLabel": enriched.get("creditRiskLabel", ""),
            "openBalanceUsd": enriched.get("openBalanceUsd", 0.0),
            "overdueBalanceUsd": enriched.get("overdueBalanceUsd", 0.0),
            "averagePaymentDays": enriched.get("averagePaymentDays", 0),
            "lastPaymentAt": enriched.get("lastPaymentAt", ""),
            "lastPaymentUsd": enriched.get("lastPaymentUsd", 0.0),
            "lastPurchaseAt": enriched.get("lastPurchaseAt", ""),
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
            "sellerCode": user.get("sellerCode", ""),
            "sellerZone": user.get("sellerZone", ""),
            "sellerTerritory": user.get("sellerTerritory", ""),
            "commissionRatePercent": safe_float(user.get("commissionRatePercent"), 0),
            "salesGoalUsd": safe_float(user.get("salesGoalUsd"), 0),
            "mobileAccessEnabled": bool(user.get("mobileAccessEnabled", True)),
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
        "legalName": enriched.get("legalName", ""),
        "commercialName": enriched.get("commercialName", ""),
        "email": enriched.get("email", ""),
        "phone": enriched.get("phone", ""),
        "whatsapp": enriched.get("whatsapp", ""),
        "contactName": enriched.get("contactName", ""),
        "administrativeContact": enriched.get("administrativeContact", ""),
        "receivingContact": enriched.get("receivingContact", ""),
        "taxId": enriched.get("taxId", ""),
        "state": enriched.get("state", ""),
        "city": enriched.get("city", ""),
        "address": enriched.get("address", ""),
        "fiscalAddress": enriched.get("fiscalAddress", ""),
        "shippingAddress": enriched.get("shippingAddress", ""),
        "country": enriched.get("country", "VE"),
        "deliveryZone": enriched.get("deliveryZone", ""),
        "clientType": enriched.get("clientType", "ferretero"),
        "clientCategory": enriched.get("clientCategory", "standard"),
        "priceList": enriched.get("priceList", "b2b"),
        "authorizedDiscountPercent": enriched.get("authorizedDiscountPercent", 0),
        "status": enriched.get("status", ""),
        "statusLabel": enriched.get("statusLabel", ""),
        "creditEnabled": bool(enriched.get("creditEnabled")),
        "creditStatus": enriched.get("creditStatus", "without_credit"),
        "creditStatusLabel": enriched.get("creditStatusLabel", ""),
        "creditLimitUsd": enriched.get("creditLimitUsd", 0.0),
        "creditAvailableUsd": enriched.get("creditAvailableUsd", 0.0),
        "creditExposureUsd": enriched.get("creditExposureUsd", 0.0),
        "creditRequestStatus": enriched.get("creditRequestStatus", "none"),
        "creditRequestStatusLabel": enriched.get("creditRequestStatusLabel", ""),
        "creditRiskLevel": enriched.get("creditRiskLevel", "low"),
        "creditRiskLabel": enriched.get("creditRiskLabel", ""),
        "creditScore": enriched.get("creditScore", 0),
        "collectionStatus": enriched.get("collectionStatus", "without_debt"),
        "collectionStatusLabel": enriched.get("collectionStatusLabel", ""),
        "currentDebtUsd": enriched.get("currentDebtUsd", 0.0),
        "openBalanceUsd": enriched.get("openBalanceUsd", 0.0),
        "overdueBalanceUsd": enriched.get("overdueBalanceUsd", 0.0),
        "averagePaymentDays": enriched.get("averagePaymentDays", 0),
        "lastPaymentAt": enriched.get("lastPaymentAt", ""),
        "lastPaymentUsd": enriched.get("lastPaymentUsd", 0.0),
        "lastPurchaseAt": enriched.get("lastPurchaseAt", ""),
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
    rate = safe_float(product.get("exchangeRateUsdVes"), current_rate())
    price = safe_float(product.get("publicPriceUsd"), 0)
    original_price = safe_float(product.get("originalPriceUsd"), price)
    discount = safe_float(product.get("discountPercent"), 0)
    enriched = dict(product)
    image_urls = list(enriched.get("imageUrls") or [])
    pdf_urls = list(enriched.get("pdfUrls") or [])
    primary_image = enriched.get("imageUrl") or (image_urls[0] if image_urls else "")
    if primary_image and primary_image not in image_urls:
        image_urls.insert(0, primary_image)
    description = (
        enriched.get("description")
        or enriched.get("shortDescription")
        or enriched.get("longDescription")
        or ""
    )
    cost = safe_float(enriched.get("costReferenceUsd"), 0)
    enriched["publicPriceVes"] = round(price * rate, 2)
    enriched["originalPriceUsd"] = original_price
    enriched["discountPercent"] = max(0.0, min(discount, 100.0))
    enriched["hasDiscount"] = enriched["discountPercent"] > 0 or original_price > price
    enriched["exchangeRateUsdVes"] = rate
    enriched["description"] = description
    enriched["shortDescription"] = enriched.get("shortDescription") or description[:140]
    enriched["longDescription"] = enriched.get("longDescription") or description
    enriched["brand"] = enriched.get("brand") or "Wulkan"
    enriched["unitOfSale"] = enriched.get("unitOfSale") or "unidad"
    enriched["imageUrl"] = primary_image
    enriched["imageUrls"] = image_urls
    enriched["pdfUrls"] = pdf_urls
    enriched["galleryCount"] = len(image_urls)
    enriched["pdfCount"] = len(pdf_urls)
    enriched["mediaCount"] = len(image_urls) + len(pdf_urls)
    enriched["statusLabel"] = product_status_label(enriched.get("status", "active"))
    enriched["visibleInApp"] = bool(enriched.get("visibleInApp", enriched.get("status") == "active"))
    if enriched.get("status") in {"inactive", "hidden", "discontinued"}:
        enriched["visibleInApp"] = False
    enriched["featured"] = bool(enriched.get("featured", False))
    enriched["onSale"] = bool(enriched.get("onSale", enriched["hasDiscount"]))
    enriched["requiresQuote"] = bool(enriched.get("requiresQuote", False))
    enriched["requiresTechnicalValidation"] = bool(enriched.get("requiresTechnicalValidation", False))
    if cost > 0 and price > 0 and not safe_float(enriched.get("marginPercent"), 0):
        enriched["marginPercent"] = round(((price - cost) / price) * 100, 1)
    else:
        enriched["marginPercent"] = safe_float(enriched.get("marginPercent"), 0)
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


def category_slug(value: str) -> str:
    return normalize_import_key(value).replace("_", "-")


def find_category_by_slug(store: dict, slug: str) -> dict | None:
    normalized = category_slug(slug)
    if not normalized:
        return None
    return next(
        (
            category
            for category in store.get("categories", [])
            if category_slug(category.get("slug", "") or category.get("id", "")) == normalized
            or category_slug(category.get("name", "")) == normalized
        ),
        None,
    )


def find_category_reference(store: dict, value: str) -> dict | None:
    if not value:
        return None
    return find_by_id(store.get("categories", []), value) or find_category_by_slug(store, value) or find_category_by_name(store, value)


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
            "slug": category_slug(category_name),
            "description": "Categoria creada automaticamente por carga masiva.",
            "imageUrl": "",
            "icon": "bi-tags",
            "sortOrder": len(store.get("categories", [])) + 1,
            "status": "active",
            "visibleInApp": True,
            "parentId": "",
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
    seen_slugs: dict[str, int] = {}
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
        slug = category_slug(row_value(row, "slug", "url_slug", default=name))
        duplicate_slug_message = duplicate_in_upload(seen_slugs, slug, row_number)
        if duplicate_slug_message:
            bulk_error(result, row_number, f"categoria {name}: slug {duplicate_slug_message}")
            continue
        category = (
            find_by_id(store.get("categories", []), category_id)
            if category_id
            else find_category_by_slug(store, slug) or find_category_by_name(store, name)
        )
        if any(item.get("id") != (category or {}).get("id") and category_slug(item.get("slug", "")) == slug for item in store.get("categories", [])):
            bulk_error(result, row_number, f"categoria {name}: slug ya existe.")
            continue
        status = row_value(row, "status", "estado", default=(category or {}).get("status", "active")) or "active"
        if status not in {key for key, _label in CATEGORY_STATUS_OPTIONS}:
            bulk_error(result, row_number, f"categoria {name}: estado no valido.")
            continue
        sort_order = parse_import_int(
            row_value(row, "sortOrder", "orden", "orden_visual", default=(category or {}).get("sortOrder", 0)),
            int((category or {}).get("sortOrder") or 0),
        )
        if sort_order < 0:
            bulk_error(result, row_number, f"categoria {name}: orden no puede ser negativo.")
            continue
        parent_reference = row_value(row, "parentId", "categoria_padre", "padre", "parent", default=(category or {}).get("parentId", ""))
        parent = find_category_reference(store, parent_reference) if parent_reference else None
        if parent_reference and not parent:
            bulk_warning(result, row_number, f"{name}: categoria padre no encontrada, quedara como raiz.")
        visible_default = bool((category or {}).get("visibleInApp", True))
        visible_in_app = parse_import_bool(row_value(row, "visibleInApp", "visible_app", "publicar_app"), visible_default)
        if status != "active":
            visible_in_app = False
        payload = {
            "name": name,
            "slug": slug,
            "description": row_value(row, "description", "descripcion", default=(category or {}).get("description", "")),
            "imageUrl": row_value(row, "imageUrl", "imagen", "imagen_url", "url_imagen", default=(category or {}).get("imageUrl", "")),
            "icon": row_value(row, "icon", "icono", default=(category or {}).get("icon", "bi-tags")) or "bi-tags",
            "sortOrder": sort_order,
            "status": status,
            "visibleInApp": visible_in_app,
            "parentId": parent.get("id", "") if parent and parent.get("id") != (category or {}).get("id") else "",
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
        if original_price < 0 or b2b_price < 0:
            bulk_error(result, row_number, f"SKU {sku}: precio anterior y precio B2B no pueden ser negativos.")
            continue
        discount = max(0.0, min(discount, 100.0))
        status = row_value(row, "status", "estado", default=current.get("status", "active")) or "active"
        if status not in {key for key, _label in PRODUCT_STATUS_OPTIONS}:
            bulk_error(result, row_number, f"SKU {sku}: estado de producto no valido.")
            continue
        product_type = row_value(row, "productType", "tipo", "tipo_producto", default=current.get("productType", "machine")) or "machine"
        if product_type not in {key for key, _label in PRODUCT_TYPE_OPTIONS}:
            bulk_error(result, row_number, f"SKU {sku}: tipo de producto no valido.")
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

        stock_quantity = parse_import_int(row_value(row, "stock", "stock_inicial", "cantidad"), int(current.get("stock") or 0))
        minimum_stock = parse_import_int(
            row_value(row, "minimumStock", "stock_minimo", "stock_min"),
            int(current.get("minimumStock") or 0),
        )
        maximum_stock = parse_import_int(
            row_value(row, "maximumStock", "stock_maximo", "stock_max"),
            int(current.get("maximumStock") or 0),
        )
        cost_reference = parse_import_float(
            row_value(row, "costReferenceUsd", "costo_referencial_usd", "costo_usd"),
            float(current.get("costReferenceUsd") or 0),
        )
        margin_percent = parse_import_float(
            row_value(row, "marginPercent", "margen", "margen_porcentaje"),
            float(current.get("marginPercent") or 0),
        )
        if min(stock_quantity, minimum_stock, maximum_stock) < 0:
            bulk_error(result, row_number, f"SKU {sku}: stock, stock_minimo y stock_maximo no pueden ser negativos.")
            continue
        if maximum_stock and minimum_stock and maximum_stock < minimum_stock:
            bulk_error(result, row_number, f"SKU {sku}: stock_maximo no puede ser menor que stock_minimo.")
            continue
        if cost_reference < 0 or margin_percent < 0:
            bulk_error(result, row_number, f"SKU {sku}: costo o margen no pueden ser negativos.")
            continue

        payload = {
            "sku": sku,
            "internalCode": row_value(row, "internalCode", "codigo_interno", default=current.get("internalCode", "")),
            "title": title,
            "brand": row_value(row, "brand", "marca", default=current.get("brand", "Wulkan")) or "Wulkan",
            "model": row_value(row, "model", "modelo", default=current.get("model", "")),
            "unitOfSale": row_value(row, "unitOfSale", "unidad_venta", "unidad", default=current.get("unitOfSale", "unidad")) or "unidad",
            "shortDescription": row_value(row, "shortDescription", "descripcion_corta", default=current.get("shortDescription", "")),
            "longDescription": row_value(row, "longDescription", "descripcion_larga", default=current.get("longDescription", "")),
            "description": row_value(row, "description", "descripcion", default=current.get("description", "")),
            "productType": product_type,
            "categoryId": category["id"],
            "categoryName": category["name"],
            "subCategory": row_value(row, "subCategory", "subcategoria", "sub_categoria", default=current.get("subCategory", "")),
            "publicPriceUsd": public_price,
            "originalPriceUsd": original_price or public_price,
            "discountPercent": discount,
            "b2bPriceUsd": b2b_price,
            "costReferenceUsd": cost_reference,
            "marginPercent": margin_percent,
            "exchangeRateUsdVes": parse_import_float(
                row_value(row, "exchangeRateUsdVes", "tasa_usd_ves", "tasa"),
                float(current.get("exchangeRateUsdVes") or current_rate()),
            ),
            "stock": stock_quantity,
            "minimumStock": minimum_stock,
            "maximumStock": maximum_stock,
            "reserved": int(current.get("reserved") or 0),
            "status": status,
            "imageUrl": primary_image,
            "imageUrls": gallery_images,
            "pdfUrls": pdf_urls,
            "variants": parse_import_list(row_value(row, "variants", "variantes", "tallas", "opciones")) or list(current.get("variants") or []),
            "specifications": parse_import_specs(row_value(row, "specifications", "especificaciones")) or dict(current.get("specifications") or {}),
            "relatedSkus": parse_import_list(row_value(row, "relatedSkus", "skus_relacionados", "relacionados")) or list(current.get("relatedSkus") or []),
            "requiresQuote": parse_import_bool(row_value(row, "requiresQuote", "requiere_cotizacion"), bool(current.get("requiresQuote", False))),
            "requiresTechnicalValidation": parse_import_bool(
                row_value(row, "requiresTechnicalValidation", "requiere_validacion_tecnica"),
                bool(current.get("requiresTechnicalValidation", False)),
            ),
            "visibleInApp": parse_import_bool(
                row_value(row, "visibleInApp", "visible_app", "visible"),
                bool(current.get("visibleInApp", status == "active")),
            ),
            "featured": parse_import_bool(row_value(row, "featured", "destacado"), bool(current.get("featured", False))),
            "onSale": parse_import_bool(row_value(row, "onSale", "oferta"), bool(current.get("onSale", discount > 0))),
            "rotationLast30Days": parse_import_int(
                row_value(row, "rotationLast30Days", "rotacion_30_dias", "rotacion"),
                int(current.get("rotationLast30Days") or 0),
            ),
            "updatedAt": utc_now(),
        }
        if payload["status"] in {"inactive", "hidden", "discontinued"}:
            payload["visibleInApp"] = False
        if not payload["description"]:
            payload["description"] = payload["shortDescription"] or payload["longDescription"]
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
        requested_quantity = parse_import_int(raw_quantity)
        if requested_quantity < 0:
            bulk_error(result, row_number, f"SKU {sku}: cantidad no puede ser negativa.")
            continue
        reserved = reserved_by_product.get(product["id"], 0)
        quantity = requested_quantity
        if quantity < reserved:
            quantity = reserved
            bulk_warning(result, row_number, f"SKU {sku}: cantidad ajustada a {reserved} porque hay stock reservado.")
        minimum_stock = parse_import_int(
            row_value(row, "stock_minimo", "minimumStock", "stock_min"),
            int(product.get("minimumStock") or 0),
        )
        maximum_stock = parse_import_int(
            row_value(row, "stock_maximo", "maximumStock", "stock_max"),
            int(product.get("maximumStock") or 0),
        )
        replenishment_qty = parse_import_int(
            row_value(row, "stock_reposicion", "replenishmentQty", "reposicion"),
            int(product.get("replenishmentQty") or 0),
        )
        if min(minimum_stock, maximum_stock, replenishment_qty) < 0:
            bulk_error(result, row_number, f"SKU {sku}: minimo, maximo o reposicion no pueden ser negativos.")
            continue
        if maximum_stock and minimum_stock and maximum_stock < minimum_stock:
            bulk_error(result, row_number, f"SKU {sku}: stock_maximo no puede ser menor que stock_minimo.")
            continue
        movement_type = normalize_stock_movement_type(row_value(row, "type", "tipo", default="bulk_excel_set") or "bulk_excel_set")
        note = row_value(row, "note", "nota", "motivo", "observacion", default="Carga masiva Excel/CSV.")
        location = row_value(row, "ubicacion", "location", "bodega", "almacen", default=product.get("stockLocation", ""))
        before = int(product.get("stock") or 0)
        before_snapshot = {
            "stock": before,
            "minimumStock": int(product.get("minimumStock") or 0),
            "maximumStock": int(product.get("maximumStock") or 0),
            "replenishmentQty": int(product.get("replenishmentQty") or 0),
            "stockLocation": product.get("stockLocation", ""),
            "stockNotes": product.get("stockNotes", ""),
        }
        product["stock"] = quantity
        product["minimumStock"] = minimum_stock
        product["maximumStock"] = maximum_stock
        product["replenishmentQty"] = replenishment_qty
        product["stockLocation"] = location
        if row_value(row, "observacion", "stockNotes", "nota_stock"):
            product["stockNotes"] = row_value(row, "observacion", "stockNotes", "nota_stock")
        after_snapshot = {
            "stock": product.get("stock"),
            "minimumStock": product.get("minimumStock"),
            "maximumStock": product.get("maximumStock"),
            "replenishmentQty": product.get("replenishmentQty"),
            "stockLocation": product.get("stockLocation", ""),
            "stockNotes": product.get("stockNotes", ""),
        }
        action = "updated" if before_snapshot != after_snapshot else "skipped"
        if action == "updated":
            append_stock_movement(
                store,
                product,
                movement_type,
                quantity,
                note=note,
                before_stock=before,
                after_stock=quantity,
                location=location,
            )
        result[action] += 1
        bulk_row(result, action, row_number, f"{sku}: fisico {before} -> {quantity}, ubicacion {location or 'sin ubicacion'}")
    return result


def import_sellers_rows(store: dict, rows: list[dict]) -> dict:
    result = blank_bulk_result()
    seen_emails: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=2):
        email = row_value(row, "email", "correo").lower()
        first_name = row_value(row, "firstName", "nombre")
        last_name = row_value(row, "lastName", "apellido")
        name = row_value(row, "name", "nombre_completo", "vendedor") or f"{first_name} {last_name}".strip()
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
        status = row_value(row, "status", "estado", default=(user or {}).get("status", "active")) or "active"
        if status not in {key for key, _label in SELLER_STATUS_OPTIONS}:
            bulk_error(result, row_number, f"{status}: estado de vendedor no valido.")
            continue
        commission = parse_import_float(
            row_value(row, "commissionRatePercent", "comision", "porcentaje_comision"),
            float((user or {}).get("commissionRatePercent") or 0),
        )
        if commission < 0 or commission > 100:
            bulk_error(result, row_number, "la comision debe estar entre 0 y 100%.")
            continue
        payload = {
            "firstName": first_name or (user or {}).get("firstName", ""),
            "lastName": last_name or (user or {}).get("lastName", ""),
            "name": name,
            "email": email,
            "role": "sales",
            "status": status,
            "sellerCode": row_value(row, "sellerCode", "codigo_vendedor", default=(user or {}).get("sellerCode", "")).upper(),
            "sellerZone": row_value(row, "sellerZone", "zona", default=(user or {}).get("sellerZone", "")),
            "sellerTerritory": row_value(row, "sellerTerritory", "territorio", "ruta", default=(user or {}).get("sellerTerritory", "")),
            "sellerSupervisor": row_value(row, "sellerSupervisor", "supervisor", default=(user or {}).get("sellerSupervisor", "")),
            "phone": row_value(row, "phone", "telefono", "whatsapp", default=(user or {}).get("phone", "")),
            "commissionRatePercent": commission,
            "salesGoalUsd": parse_import_float(
                row_value(row, "salesGoalUsd", "meta_usd", "meta_mensual_usd", "meta_ventas_usd"),
                float((user or {}).get("salesGoalUsd") or 0),
            ),
            "hiredAt": row_value(row, "hiredAt", "fecha_ingreso", default=(user or {}).get("hiredAt", "")),
            "mobileAccessEnabled": parse_import_bool(
                row_value(row, "mobileAccessEnabled", "acceso_movil", "usuario_movil"),
                bool((user or {}).get("mobileAccessEnabled", True)),
            ),
            "internalNotes": row_value(row, "internalNotes", "observacion", "notas", default=(user or {}).get("internalNotes", "")),
            "updatedAt": utc_now(),
        }
        if payload["status"] != "active":
            payload["mobileAccessEnabled"] = False
        if user:
            payload["id"] = user["id"]
            payload["createdAt"] = user.get("createdAt", utc_now())
            payload["passwordHash"] = generate_password_hash(password) if password else user.get("passwordHash", "")
            payload["mustChangePassword"] = True if password else bool(user.get("mustChangePassword"))
            payload["failedLoginAttempts"] = safe_int(user.get("failedLoginAttempts"))
            payload["lastFailedLoginAt"] = user.get("lastFailedLoginAt", "")
            payload["lastLoginAt"] = user.get("lastLoginAt", "")
            payload["lastLoginIp"] = user.get("lastLoginIp", "")
            payload["lastMobileLoginAt"] = user.get("lastMobileLoginAt", "")
            payload["sessionVersion"] = user_session_version(user)
            store["admin_users"] = [payload if item["id"] == user["id"] else item for item in store.get("admin_users", [])]
            result["updated"] += 1
            bulk_row(result, "updated", row_number, f"{name} - {email}")
        else:
            payload["id"] = next_id("admin", email)
            payload["createdAt"] = utc_now()
            payload["passwordHash"] = generate_password_hash(password)
            payload["mustChangePassword"] = True
            payload["failedLoginAttempts"] = 0
            payload["lastFailedLoginAt"] = ""
            payload["lastLoginAt"] = ""
            payload["lastLoginIp"] = ""
            payload["lastMobileLoginAt"] = ""
            payload["sessionVersion"] = 0
            store.setdefault("admin_users", []).append(payload)
            result["created"] += 1
            bulk_row(result, "created", row_number, f"{name} - {email}")
    return result


def import_clients_rows(store: dict, rows: list[dict]) -> dict:
    result = blank_bulk_result()
    can_approve = role_allowed(CREDIT_APPROVAL_ROLES)
    seen_emails: dict[str, int] = {}
    seen_tax_ids: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=2):
        email = row_value(row, "email", "correo").lower()
        business_name = row_value(row, "businessName", "razon_social", "nombre_comercial", "cliente")
        tax_id = row_value(row, "taxId", "rif", "rut")
        if not email or not business_name:
            bulk_error(result, row_number, "cliente requiere nombre comercial y email.")
            continue
        duplicate_message = duplicate_in_upload(seen_emails, email, row_number)
        if duplicate_message:
            bulk_error(result, row_number, f"{email}: {duplicate_message}")
            continue
        if tax_id:
            duplicate_tax = duplicate_in_upload(seen_tax_ids, tax_id.lower(), row_number)
            if duplicate_tax:
                bulk_error(result, row_number, f"{tax_id}: {duplicate_tax}")
                continue
        client = next((item for item in store.get("clients", []) if item.get("email", "").lower() == email), None)
        if not client and tax_id:
            client = next((item for item in store.get("clients", []) if item.get("taxId", "").lower() == tax_id.lower()), None)
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
        if credit_status not in dict(CREDIT_REQUEST_STATUS_OPTIONS):
            bulk_error(result, row_number, f"{business_name}: estado_credito no valido.")
            continue
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
            "legalName": row_value(row, "legalName", "razon_social", default=(client or {}).get("legalName", business_name)) or business_name,
            "commercialName": row_value(row, "commercialName", "nombre_comercial", default=(client or {}).get("commercialName", business_name)) or business_name,
            "businessName": business_name,
            "taxId": tax_id or (client or {}).get("taxId", ""),
            "contactName": row_value(row, "contactName", "contacto", "responsable", default=(client or {}).get("contactName", "")),
            "administrativeContact": row_value(row, "administrativeContact", "contacto_administrativo", "admin_contacto", default=(client or {}).get("administrativeContact", "")),
            "receivingContact": row_value(row, "receivingContact", "contacto_recepcion", "recepcion_contacto", default=(client or {}).get("receivingContact", "")),
            "phone": row_value(row, "phone", "telefono", "whatsapp", default=(client or {}).get("phone", "")),
            "whatsapp": row_value(row, "whatsapp", "telefono_whatsapp", default=(client or {}).get("whatsapp", "")),
            "email": email,
            "clientType": row_value(row, "clientType", "tipo_cliente", default=(client or {}).get("clientType", "ferretero")) or "ferretero",
            "clientCategory": row_value(row, "clientCategory", "categoria_comercial", default=(client or {}).get("clientCategory", "standard")) or "standard",
            "priceList": row_value(row, "priceList", "lista_precios", default=(client or {}).get("priceList", "b2b")) or "b2b",
            "authorizedDiscountPercent": parse_import_float(row_value(row, "authorizedDiscountPercent", "descuento_autorizado"), float((client or {}).get("authorizedDiscountPercent") or 0)),
            "status": row_value(row, "status", "estado", default=(client or {}).get("status", "active")) or "active",
            "address": row_value(row, "address", "direccion", default=(client or {}).get("address", "")),
            "fiscalAddress": row_value(row, "fiscalAddress", "direccion_fiscal", default=(client or {}).get("fiscalAddress", "")),
            "shippingAddress": row_value(row, "shippingAddress", "direccion_despacho", "direccion_entrega", default=(client or {}).get("shippingAddress", "")),
            "country": row_value(row, "country", "pais", default=(client or {}).get("country", "VE")) or "VE",
            "state": row_value(row, "state", "estado_ubicacion", "provincia", default=(client or {}).get("state", "")),
            "city": row_value(row, "city", "ciudad", default=(client or {}).get("city", "")),
            "deliveryZone": row_value(row, "deliveryZone", "zona", default=(client or {}).get("deliveryZone", "")),
            "assignedSellerId": (seller or {}).get("id", (client or {}).get("assignedSellerId", "")),
            "assignedSellerName": (seller or {}).get("name", (client or {}).get("assignedSellerName", "")),
            "defaultSaleType": row_value(row, "defaultSaleType", "tipo_venta_default", default=(client or {}).get("defaultSaleType", "cash")) or "cash",
            "allowedPaymentTermsDays": sorted(set(terms)),
            "collectionStatus": row_value(row, "collectionStatus", "estado_cobranza", default=(client or {}).get("collectionStatus", "without_debt")) or "without_debt",
            "creditRiskLevel": row_value(row, "creditRiskLevel", "riesgo_credito", default=(client or {}).get("creditRiskLevel", "low")) or "low",
            "creditScore": parse_import_int(row_value(row, "creditScore", "score_credito"), int((client or {}).get("creditScore") or 0)),
            "creditManagerNote": row_value(row, "creditManagerNote", "observacion_gerencia", "nota_credito", default=(client or {}).get("creditManagerNote", "")),
            "creditReviewedBy": (client or {}).get("creditReviewedBy", ""),
            "creditReviewedAt": (client or {}).get("creditReviewedAt", ""),
            "creditRequestStatus": credit_status,
            "creditRequestedUsd": credit_requested,
            "creditEnabled": credit_enabled and credit_status == "approved",
            "creditLimitUsd": credit_limit if credit_enabled and credit_status == "approved" else float((client or {}).get("creditLimitUsd") or 0),
            "creditUsedUsd": parse_import_float(row_value(row, "creditUsedUsd", "credito_usado_usd", "deuda_manual_usd"), float((client or {}).get("creditUsedUsd") or 0)),
            "paymentTermsDays": payment_term if credit_status == "approved" else int((client or {}).get("paymentTermsDays") or 0),
            "notes": row_value(row, "notes", "notas", default=(client or {}).get("notes", "")),
            "updatedAt": utc_now(),
        }
        payload["whatsapp"] = payload["whatsapp"] or payload["phone"]
        payload["fiscalAddress"] = payload["fiscalAddress"] or payload["address"]
        payload["shippingAddress"] = payload["shippingAddress"] or payload["address"]
        payload["address"] = payload["address"] or payload["shippingAddress"] or payload["fiscalAddress"]
        if not payload.get("taxId"):
            bulk_warning(result, row_number, f"{business_name} no tiene RIF/taxId.")
        if not payload.get("contactName"):
            bulk_warning(result, row_number, f"{business_name} no tiene contacto principal.")
        if not payload.get("phone"):
            bulk_warning(result, row_number, f"{business_name} no tiene telefono/WhatsApp.")
        if credit_status == "approved" and can_approve:
            payload["creditApprovedBy"] = session.get("admin_name", "Admin")
            payload["creditApprovedAt"] = utc_now()
            payload["creditReviewedBy"] = session.get("admin_name", "Admin")
            payload["creditReviewedAt"] = payload["creditApprovedAt"]
        elif client:
            payload["creditApprovedBy"] = client.get("creditApprovedBy", "")
            payload["creditApprovedAt"] = client.get("creditApprovedAt", "")
            payload["creditReviewedBy"] = client.get("creditReviewedBy", "")
            payload["creditReviewedAt"] = client.get("creditReviewedAt", "")
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
    gross_usd = float(preview.get("grossUsd") or preview.get("subtotalUsd") or calculated_total_usd)
    discount_usd = max(0.0, float(preview.get("discountUsd") or max(gross_usd - total_usd, 0)))
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
    raw_payment_term_days = payload.get("paymentTermDays")
    if raw_payment_term_days in (None, ""):
        payment_term_days = int(client.get("paymentTermsDays") or 0)
    else:
        payment_term_days = int(raw_payment_term_days or 0)
    if sale_type == "cash":
        payment_term_days = 0
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
    if can_use_credit and not requires_operator_review:
        status = "approved_with_credit"
    elif sale_type == "cash" and not requires_operator_review:
        status = "payment_under_review"
    else:
        status = "credit_review"
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
        "grossUsd": gross_usd,
        "discountUsd": discount_usd,
        "netUsd": total_usd,
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
        "dispatchStatus": "pending",
        "invoiceStatus": "pending",
        "shippingAddress": str(payload.get("shippingAddress") or client.get("shippingAddress") or client.get("address") or "").strip(),
        "customerComment": str(payload.get("customerComment") or "").strip(),
        "internalComment": str(payload.get("internalComment") or payload.get("notes") or "").strip(),
        "currentOwner": "Comercial",
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
            and order.get("saleType") == "credit_line"
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
    enriched["legalName"] = enriched.get("legalName") or enriched.get("businessName", "")
    enriched["commercialName"] = enriched.get("commercialName") or enriched.get("businessName", "")
    enriched["whatsapp"] = enriched.get("whatsapp") or enriched.get("phone", "")
    enriched["fiscalAddress"] = enriched.get("fiscalAddress") or enriched.get("address", "")
    enriched["shippingAddress"] = enriched.get("shippingAddress") or enriched.get("address", "")
    enriched["address"] = enriched.get("address") or enriched["shippingAddress"] or enriched["fiscalAddress"]
    enriched["country"] = enriched.get("country") or "VE"
    enriched["administrativeContact"] = enriched.get("administrativeContact", "")
    enriched["receivingContact"] = enriched.get("receivingContact", "")
    enriched["clientCategory"] = enriched.get("clientCategory") or "standard"
    enriched["priceList"] = enriched.get("priceList") or "b2b"
    enriched["authorizedDiscountPercent"] = float(enriched.get("authorizedDiscountPercent") or 0)
    enriched["creditRiskLevel"] = enriched.get("creditRiskLevel") or "low"
    enriched["creditManagerNote"] = enriched.get("creditManagerNote", "")
    enriched["creditReviewedBy"] = enriched.get("creditReviewedBy", "")
    enriched["creditReviewedAt"] = enriched.get("creditReviewedAt", "")
    enriched["creditLimitUsd"] = float(enriched.get("creditLimitUsd") or 0)
    enriched["creditUsedUsd"] = float(enriched.get("creditUsedUsd") or 0)
    enriched["creditRequestedUsd"] = float(enriched.get("creditRequestedUsd") or 0)
    enriched["creditScore"] = int(float(enriched.get("creditScore") or 0))
    if enriched.get("creditRequestStatus") not in dict(CREDIT_REQUEST_STATUS_OPTIONS):
        enriched["creditRequestStatus"] = "none"
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
    client_orders = [
        enrich_order(order, movements)
        for order in orders or []
        if order.get("customerId") == enriched.get("id", "")
    ]
    enriched["ordersCount"] = len(client_orders)
    enriched["totalPurchasedUsd"] = round(sum(float(order.get("totalUsd") or 0) for order in client_orders), 2)
    open_orders = [
        order for order in client_orders
        if float(order.get("balanceUsd") or 0) > 0 and order.get("status") != "cancelled"
    ]
    enriched["openBalanceUsd"] = round(sum(float(order.get("balanceUsd") or 0) for order in open_orders), 2)
    enriched["overdueBalanceUsd"] = round(
        sum(float(order.get("balanceUsd") or 0) for order in open_orders if order.get("dueStatus") == "overdue"),
        2,
    )
    enriched["currentDebtUsd"] = max(0.0, round(enriched["openBalanceUsd"] - enriched["overdueBalanceUsd"], 2))
    enriched["openOrdersCount"] = len(open_orders)
    enriched["overdueOrdersCount"] = sum(1 for order in open_orders if order.get("dueStatus") == "overdue")
    client_payments = sorted(
        [
            movement for movement in movements or []
            if movement.get("movementType") == "payment"
            and movement.get("clientId") == enriched.get("id", "")
        ],
        key=lambda item: item.get("createdAt", ""),
        reverse=True,
    )
    latest_payment = client_payments[0] if client_payments else {}
    enriched["lastPaymentAt"] = latest_payment.get("createdAt", "")
    enriched["lastPaymentUsd"] = float(latest_payment.get("amountUsd") or 0)
    payment_days: list[int] = []
    for order in client_orders:
        payments_for_order = order.get("payments") or []
        if not payments_for_order:
            continue
        latest_order_payment = max(payments_for_order, key=lambda item: item.get("createdAt", ""))
        paid_at = parse_utc_datetime(latest_order_payment.get("createdAt"))
        created_at = parse_utc_datetime(order.get("createdAt"))
        payment_days.append(max(0, (paid_at.date() - created_at.date()).days))
    enriched["averagePaymentDays"] = round(sum(payment_days) / len(payment_days), 1) if payment_days else 0
    delivered_or_paid_orders = [
        order for order in client_orders
        if order.get("status") in {"delivered", "paid", "partial_paid", "approved_with_credit", "preparing"}
    ]
    latest_order = max(delivered_or_paid_orders or client_orders, key=lambda order: order.get("createdAt", ""), default={})
    enriched["lastPurchaseAt"] = enriched.get("lastPurchaseAt") or latest_order.get("createdAt", "")
    enriched["lastOrderId"] = latest_order.get("orderId") or latest_order.get("id", "")
    explicit_collection = enriched.get("collectionStatus", "")
    if enriched.get("status") == "blocked_debt":
        enriched["collectionStatus"] = "blocked"
    elif enriched["overdueBalanceUsd"] > 0:
        enriched["collectionStatus"] = "overdue"
    elif any(order.get("dueStatus") == "due_soon" for order in open_orders):
        enriched["collectionStatus"] = "due_soon"
    elif enriched["openBalanceUsd"] > 0:
        enriched["collectionStatus"] = explicit_collection if explicit_collection in {"promise", "current"} else "current"
    else:
        enriched["collectionStatus"] = explicit_collection if explicit_collection == "promise" else "without_debt"
    request_status = enriched.get("creditRequestStatus") or "none"
    enriched["creditStatus"] = "without_credit"
    if request_status in {"suspended", "blocked_debt", "blocked_limit", "rejected", "review"}:
        enriched["creditStatus"] = request_status
    elif request_status == "pending":
        enriched["creditStatus"] = "credit_requested"
    elif enriched.get("creditEnabled"):
        if enriched["creditExposureUsd"] > enriched["creditLimitUsd"] > 0:
            enriched["creditStatus"] = "blocked_limit"
        elif enriched["overdueBalanceUsd"] > 0 and enriched.get("collectionStatus") == "blocked":
            enriched["creditStatus"] = "blocked_debt"
        elif enriched["creditAvailableUsd"] <= 0:
            enriched["creditStatus"] = "exhausted"
        elif enriched["creditExposureUsd"] > 0:
            enriched["creditStatus"] = "in_use"
        else:
            enriched["creditStatus"] = "available"
    if not enriched["creditScore"]:
        risk_penalty = {"low": 0, "medium": 12, "high": 25, "critical": 40}.get(enriched["creditRiskLevel"], 10)
        exposure_penalty = 10 if enriched["creditStatus"] in {"exhausted", "blocked_limit"} else 0
        overdue_penalty = 25 if enriched["overdueBalanceUsd"] > 0 else 0
        status_penalty = 15 if enriched["creditStatus"] in {"suspended", "blocked_debt", "rejected"} else 0
        enriched["creditScore"] = max(0, min(100, 85 - risk_penalty - exposure_penalty - overdue_penalty - status_penalty))
    enriched["statusLabel"] = client_status_label(enriched.get("status", ""))
    enriched["collectionStatusLabel"] = collection_status_label(enriched.get("collectionStatus", ""))
    enriched["creditStatusLabel"] = credit_status_label(enriched.get("creditStatus", ""))
    enriched["creditRequestStatusLabel"] = credit_status_label(enriched.get("creditRequestStatus", ""))
    enriched["creditRiskLabel"] = credit_risk_label(enriched.get("creditRiskLevel", ""))
    enriched["clientTypeLabel"] = client_type_label(enriched.get("clientType", ""))
    return enriched


def enrich_order(order: dict, movements: list[dict] | None = None) -> dict:
    enriched = dict(order)
    order_id = enriched.get("orderId") or enriched.get("id", "")
    paid = order_paid_usd(enriched, movements)
    balance = order_balance_usd(enriched, movements)
    total_usd = float(enriched.get("totalUsd") or enriched.get("netUsd") or 0)
    gross_usd = float(enriched.get("grossUsd") or total_usd)
    discount_usd = max(0.0, float(enriched.get("discountUsd") or max(gross_usd - total_usd, 0)))
    enriched["grossUsd"] = gross_usd
    enriched["discountUsd"] = discount_usd
    enriched["netUsd"] = total_usd
    enriched["totalUsd"] = total_usd
    enriched["paidUsd"] = paid
    enriched["balanceUsd"] = balance
    enriched["paymentStatus"] = "paid" if balance <= 0 else ("partial" if paid > 0 else "pending")
    enriched["creditReservedUsd"] = (
        balance
        if enriched.get("saleType") == "credit_line"
        and enriched.get("status") in ORDER_CREDIT_RESERVING_STATUSES
        else 0.0
    )
    enriched["payments"] = order_payments(movements, order_id)
    enriched["inventoryStatus"] = enriched.get("inventoryStatus", "pending")
    enriched["stockStatus"] = enriched.get("stockStatus", "pending")
    enriched["saleType"] = enriched.get("saleType", "cash")
    enriched["saleTypeLabel"] = sale_type_label(enriched["saleType"])
    enriched["paymentTermDays"] = int(enriched.get("paymentTermDays") or 0)
    enriched["statusLabel"] = order_status_label(enriched.get("status", ""))
    enriched["creditStatusLabel"] = credit_status_label(enriched.get("creditStatus", ""))
    enriched["paymentStatusLabel"] = payment_status_label(enriched.get("paymentStatus", ""))
    enriched["salesChannel"] = enriched.get("salesChannel") or "mobile"
    enriched["salesChannelLabel"] = sales_channel_label(enriched["salesChannel"])
    enriched["dispatchStatus"] = enriched.get("dispatchStatus", "pending")
    enriched["dispatchStatusLabel"] = dispatch_status_label(enriched["dispatchStatus"])
    enriched["invoiceStatus"] = enriched.get("invoiceStatus", "pending")
    enriched["currentOwner"] = enriched.get("currentOwner") or "Comercial"
    if not enriched.get("dueDate") and enriched["paymentTermDays"] > 0:
        enriched["dueDate"] = add_days_iso(enriched.get("createdAt"), enriched["paymentTermDays"])
    due_status, due_days = order_due_status(enriched)
    enriched["dueStatus"] = due_status
    enriched["dueDays"] = due_days
    explicit_collection = enriched.get("collectionStatus", "")
    if balance <= 0 or enriched.get("status") in {"paid", "cancelled"}:
        collection_status = "closed"
    elif explicit_collection in {"in_management", "promise", "critical", "uncollectible"}:
        collection_status = explicit_collection
    elif paid > 0:
        collection_status = "partial_paid"
    elif due_status == "overdue" and due_days >= 15:
        collection_status = "critical"
    elif due_status in {"overdue", "due_soon", "current"}:
        collection_status = due_status
    else:
        collection_status = "in_management" if balance > 0 else "closed"
    enriched["collectionStatus"] = collection_status
    enriched["collectionStatusLabel"] = collection_status_label(collection_status)
    enriched["collectionOwner"] = enriched.get("collectionOwner") or ("Cobranza" if balance > 0 else "Comercial")
    enriched["lastCollectionActionAt"] = enriched.get("lastCollectionActionAt", "")
    enriched["nextCollectionActionAt"] = enriched.get("nextCollectionActionAt", "")
    enriched["paymentPromiseAt"] = enriched.get("paymentPromiseAt", "")
    enriched["collectionComment"] = enriched.get("collectionComment", "")
    enriched["sellerName"] = enriched.get("sellerName") or "Sin vendedor"
    enriched["commissionRatePercent"] = float(enriched.get("commissionRatePercent") or 0)
    enriched["commissionUsd"] = float(enriched.get("commissionUsd") or 0)
    enriched["commissionStatus"] = enriched.get("commissionStatus") or "commission_pending"
    enriched["commissionStatusLabel"] = commission_status_label(enriched["commissionStatus"])
    customer = enriched.get("customer") or {}
    enriched["customerName"] = customer.get("name") or customer.get("businessName") or "Cliente Wulkan"
    enriched["itemsCount"] = len(enriched.get("items") or [])
    enriched["statusHistory"] = sorted(enriched.get("statusHistory") or [], key=lambda item: item.get("createdAt", ""), reverse=True)
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


def stock_movement_label(value: str) -> str:
    return STOCK_MOVEMENT_LABELS.get(value, str(value or "Movimiento").replace("_", " ").title())


def stock_status_label(value: str) -> str:
    return STOCK_STATUS_LABELS.get(value, "Disponible")


def normalize_stock_movement_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "entrada": "entry",
        "ingreso": "entry",
        "salida": "exit",
        "venta": "sale",
        "ajuste": "adjustment",
        "ajuste_final": "adjustment",
        "ajuste_positivo": "adjustment_positive",
        "ajuste_negativo": "adjustment_negative",
        "devolucion": "return",
        "carga": "bulk_excel_set",
        "carga_masiva": "bulk_excel_set",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in STOCK_MOVEMENT_LABELS else "bulk_excel_set"


def latest_stock_movement_for(product_id: str, movements: list[dict]) -> dict:
    related = [
        movement
        for movement in movements or []
        if movement.get("productId") == product_id
    ]
    if not related:
        return {}
    return sorted(related, key=lambda item: item.get("createdAt", ""), reverse=True)[0]


def enrich_stock_movement(movement: dict) -> dict:
    enriched = dict(movement)
    movement_type = enriched.get("type") or enriched.get("movementType") or ""
    enriched["type"] = movement_type
    enriched["typeLabel"] = stock_movement_label(movement_type)
    enriched["quantity"] = safe_int(enriched.get("quantity"), 0)
    enriched["beforeStock"] = "" if enriched.get("beforeStock") in {None, ""} else safe_int(enriched.get("beforeStock"), 0)
    enriched["afterStock"] = "" if enriched.get("afterStock") in {None, ""} else safe_int(enriched.get("afterStock"), 0)
    return enriched


def touch_product_stock_metadata(
    product: dict,
    movement_type: str,
    note: str = "",
    location: str = "",
) -> None:
    product["lastStockMovementAt"] = utc_now()
    product["lastStockMovementBy"] = session.get("admin_name", "Sistema")
    product["lastStockMovementType"] = movement_type
    product["lastStockMovementNote"] = note
    if location:
        product["stockLocation"] = location
    product["updatedAt"] = utc_now()


def append_stock_movement(
    store: dict,
    product: dict,
    movement_type: str,
    quantity: int,
    order: dict | None = None,
    note: str = "",
    before_stock: int | None = None,
    after_stock: int | None = None,
    location: str = "",
) -> None:
    normalized_type = normalize_stock_movement_type(movement_type)
    movement = {
        "id": next_id("mov", f"{product.get('sku', '')}-{normalized_type}"),
        "productId": product.get("id", ""),
        "sku": product.get("sku", ""),
        "type": normalized_type,
        "quantity": safe_int(quantity, 0),
        "beforeStock": "" if before_stock is None else safe_int(before_stock, 0),
        "afterStock": "" if after_stock is None else safe_int(after_stock, 0),
        "location": location or product.get("stockLocation", ""),
        "orderId": (order or {}).get("orderId", ""),
        "note": note,
        "createdBy": session.get("admin_name", "Sistema"),
        "createdAt": utc_now(),
    }
    store.setdefault("stock_movements", []).append(movement)
    touch_product_stock_metadata(product, normalized_type, note, location)


def enrich_inventory_product(product: dict, orders: list[dict], movements: list[dict] | None = None) -> dict:
    reserved_by_product = stock_reserved_quantities(orders)
    enriched = enrich_product(product)
    physical_stock = int(enriched.get("stock") or 0)
    committed = int(reserved_by_product.get(enriched["id"], 0))
    available = max(0, physical_stock - committed)
    minimum_stock = max(0, safe_int(enriched.get("minimumStock"), 0))
    maximum_stock = max(0, safe_int(enriched.get("maximumStock"), 0))
    replenishment_qty = max(0, safe_int(enriched.get("replenishmentQty"), 0))
    last_movement = latest_stock_movement_for(enriched["id"], movements or [])
    if last_movement:
        last_movement = enrich_stock_movement(last_movement)
    enriched["physicalStock"] = physical_stock
    enriched["reserved"] = committed
    enriched["availableStock"] = available
    enriched["committedStock"] = committed
    enriched["minimumStock"] = minimum_stock
    enriched["maximumStock"] = maximum_stock
    enriched["replenishmentQty"] = replenishment_qty
    enriched["stockLocation"] = enriched.get("stockLocation", "")
    enriched["stockNotes"] = enriched.get("stockNotes", "")
    enriched["lastMovement"] = last_movement
    enriched["lastMovementAt"] = last_movement.get("createdAt") or enriched.get("lastStockMovementAt", "")
    enriched["lastMovementBy"] = last_movement.get("createdBy") or enriched.get("lastStockMovementBy", "")
    enriched["lastMovementType"] = last_movement.get("type") or enriched.get("lastStockMovementType", "")
    enriched["lastMovementTypeLabel"] = stock_movement_label(enriched["lastMovementType"]) if enriched["lastMovementType"] else "Sin movimiento"
    enriched["stockCoveragePercent"] = round((available / maximum_stock) * 100, 1) if maximum_stock else 0
    enriched["stockStatus"] = "available"
    if available <= 0 or enriched.get("status") == "out":
        enriched["stockStatus"] = "out"
    elif minimum_stock and available <= minimum_stock:
        enriched["stockStatus"] = "low"
    elif maximum_stock and physical_stock > maximum_stock:
        enriched["stockStatus"] = "overstock"
    if enriched.get("status") == "replenishment":
        enriched["stockStatus"] = "replenishment"
    enriched["stockStatusLabel"] = stock_status_label(enriched["stockStatus"])
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
    categories = product_category_options(store) or [{"id": "uncategorized", "name": "Sin categoria"}]
    category = find_by_id(categories, category_id) or categories[0]
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
    visible_values = request.form.getlist("visibleInApp")
    payload = {
        "sku": sku,
        "internalCode": request.form.get("internalCode", "").strip().upper(),
        "title": title,
        "brand": request.form.get("brand", "Wulkan").strip() or "Wulkan",
        "model": request.form.get("model", "").strip(),
        "unitOfSale": request.form.get("unitOfSale", "unidad").strip() or "unidad",
        "shortDescription": request.form.get("shortDescription", "").strip(),
        "longDescription": request.form.get("longDescription", "").strip(),
        "description": request.form.get("description", "").strip(),
        "productType": request.form.get("productType", "machine"),
        "categoryId": category["id"],
        "categoryName": category["name"],
        "subCategory": request.form.get("subCategory", "").strip(),
        "publicPriceUsd": safe_float(request.form.get("publicPriceUsd"), 0),
        "originalPriceUsd": safe_float(
            request.form.get("originalPriceUsd") or request.form.get("publicPriceUsd"),
            0,
        ),
        "discountPercent": max(0.0, min(safe_float(request.form.get("discountPercent"), 0), 100.0)),
        "b2bPriceUsd": safe_float(request.form.get("b2bPriceUsd"), 0),
        "costReferenceUsd": safe_float(request.form.get("costReferenceUsd"), 0),
        "marginPercent": safe_float(request.form.get("marginPercent"), 0),
        "exchangeRateUsdVes": safe_float(request.form.get("exchangeRateUsdVes"), current_rate()),
        "stock": safe_int(request.form.get("stock"), 0),
        "minimumStock": safe_int(request.form.get("minimumStock"), 0),
        "maximumStock": safe_int(request.form.get("maximumStock"), 0),
        "reserved": safe_int(request.form.get("reserved") or (existing or {}).get("reserved"), 0),
        "status": request.form.get("status", "active"),
        "imageUrl": primary_image,
        "imageUrls": image_urls,
        "pdfUrls": pdf_urls,
        "variants": split_lines(request.form.get("variants", "")),
        "specifications": parse_specs(request.form.get("specifications", "")),
        "relatedSkus": split_lines(request.form.get("relatedSkus", "")),
        "requiresQuote": request.form.get("requiresQuote") == "on",
        "requiresTechnicalValidation": request.form.get("requiresTechnicalValidation") == "on",
        "visibleInApp": "on" in visible_values if visible_values else bool((existing or {}).get("visibleInApp", True)),
        "featured": request.form.get("featured") == "on",
        "onSale": request.form.get("onSale") == "on",
        "rotationLast30Days": safe_int(request.form.get("rotationLast30Days") or (existing or {}).get("rotationLast30Days"), 0),
        "updatedAt": now,
    }
    if not payload["description"]:
        payload["description"] = payload["shortDescription"] or payload["longDescription"]
    if payload["status"] in {"inactive", "hidden", "discontinued"}:
        payload["visibleInApp"] = False
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
        "internalCode": request.form.get("internalCode", "").strip().upper(),
        "title": request.form.get("title", "").strip(),
        "brand": request.form.get("brand", "Wulkan").strip(),
        "model": request.form.get("model", "").strip(),
        "unitOfSale": request.form.get("unitOfSale", "unidad").strip(),
        "shortDescription": request.form.get("shortDescription", "").strip(),
        "longDescription": request.form.get("longDescription", "").strip(),
        "description": request.form.get("description", "").strip(),
        "productType": request.form.get("productType", "machine"),
        "categoryId": request.form.get("categoryId", "machinery-garden"),
        "subCategory": request.form.get("subCategory", "").strip(),
        "status": request.form.get("status", "active"),
        "publicPriceUsd": request.form.get("publicPriceUsd", ""),
        "originalPriceUsd": request.form.get("originalPriceUsd", ""),
        "discountPercent": request.form.get("discountPercent", 0),
        "b2bPriceUsd": request.form.get("b2bPriceUsd", ""),
        "costReferenceUsd": request.form.get("costReferenceUsd", ""),
        "marginPercent": request.form.get("marginPercent", ""),
        "exchangeRateUsdVes": request.form.get("exchangeRateUsdVes", current_rate()),
        "stock": request.form.get("stock", 0),
        "minimumStock": request.form.get("minimumStock", 0),
        "maximumStock": request.form.get("maximumStock", 0),
        "imageUrl": request.form.get("imageUrl", "").strip(),
        "imageUrls": split_lines(request.form.get("imageUrls", "")),
        "pdfUrls": split_lines(request.form.get("pdfUrls", "")),
        "variants": split_lines(request.form.get("variants", "")),
        "specifications": parse_specs(request.form.get("specifications", "")),
        "relatedSkus": split_lines(request.form.get("relatedSkus", "")),
        "requiresQuote": request.form.get("requiresQuote") == "on",
        "requiresTechnicalValidation": request.form.get("requiresTechnicalValidation") == "on",
        "visibleInApp": "on" in request.form.getlist("visibleInApp"),
        "featured": request.form.get("featured") == "on",
        "onSale": request.form.get("onSale") == "on",
    }


def product_form_error(store: dict, existing: dict | None = None) -> str:
    sku = request.form.get("sku", "").strip().upper()
    status = request.form.get("status", "active")
    product_type = request.form.get("productType", "machine")
    public_price = safe_float(request.form.get("publicPriceUsd"), 0)
    b2b_price = safe_float(request.form.get("b2bPriceUsd"), 0)
    original_price = safe_float(request.form.get("originalPriceUsd") or request.form.get("publicPriceUsd"), 0)
    discount = safe_float(request.form.get("discountPercent"), 0)
    stock = safe_int(request.form.get("stock"), 0)
    minimum_stock = safe_int(request.form.get("minimumStock"), 0)
    maximum_stock = safe_int(request.form.get("maximumStock"), 0)
    cost = safe_float(request.form.get("costReferenceUsd"), 0)
    margin = safe_float(request.form.get("marginPercent"), 0)
    available_categories = product_category_options(store)
    if not available_categories:
        return "Debes crear al menos una categoria antes de crear productos."
    if not find_by_id(available_categories, request.form.get("categoryId", "")):
        return "Selecciona una categoria valida para el producto."
    if not sku:
        return "El SKU es obligatorio para crear o editar productos."
    if not request.form.get("title", "").strip():
        return "El nombre comercial del producto es obligatorio."

    duplicated = any(
        product.get("sku", "").upper() == sku
        and (existing is None or product.get("id") != existing.get("id"))
        for product in store["products"]
    )
    if duplicated:
        return f"El SKU {sku} ya existe en el catalogo."
    if status not in {key for key, _label in PRODUCT_STATUS_OPTIONS}:
        return "El estado del producto no es valido."
    if product_type not in {key for key, _label in PRODUCT_TYPE_OPTIONS}:
        return "El tipo de producto no es valido."
    if public_price <= 0:
        return "El precio publico USD debe ser mayor a 0."
    if original_price < 0:
        return "El precio anterior USD no puede ser negativo."
    if b2b_price < 0:
        return "El precio B2B no puede ser negativo."
    if cost < 0:
        return "El costo referencial no puede ser negativo."
    if margin < 0:
        return "El margen estimado no puede ser negativo."
    if discount < 0 or discount > 100:
        return "El descuento debe estar entre 0 y 100%."
    if stock < 0:
        return "El stock no puede ser negativo."
    if minimum_stock < 0 or maximum_stock < 0:
        return "El stock minimo o maximo no puede ser negativo."
    if maximum_stock and minimum_stock and maximum_stock < minimum_stock:
        return "El stock maximo no puede ser menor que el stock minimo."

    return ""


def enrich_category(category: dict, store: dict) -> dict:
    enriched = dict(category)
    products = [
        product
        for product in store.get("products", [])
        if product.get("categoryId") == category.get("id")
        and product.get("status") != "deleted"
    ]
    children = [
        item
        for item in store.get("categories", [])
        if item.get("parentId") == category.get("id")
        and item.get("status") != "deleted"
    ]
    parent = find_by_id(store.get("categories", []), category.get("parentId", ""))
    enriched["slug"] = category_slug(enriched.get("slug") or enriched.get("name", ""))
    enriched["icon"] = enriched.get("icon") or "bi-tags"
    enriched["sortOrder"] = safe_int(enriched.get("sortOrder"), 0)
    enriched["status"] = enriched.get("status") or "active"
    enriched["statusLabel"] = category_status_label(enriched["status"])
    enriched["visibleInApp"] = bool(enriched.get("visibleInApp", enriched["status"] == "active")) and enriched["status"] == "active"
    enriched["parentId"] = enriched.get("parentId", "")
    enriched["parentName"] = parent.get("name", "") if parent else ""
    enriched["productsCount"] = len(products)
    enriched["visibleProductsCount"] = sum(
        1 for product in products if product.get("status") == "active" and product.get("visibleInApp", True)
    )
    enriched["childrenCount"] = len(children)
    enriched["imageStatus"] = "Completa" if enriched.get("imageUrl") else "Pendiente"
    return enriched


def category_payload(store: dict, existing: dict | None = None) -> dict:
    name = request.form.get("name", "").strip()
    uploaded_image = save_upload(request.files.get("imageFile"), "categories")
    image_url = uploaded_image or request.form.get("imageUrl", "").strip() or (existing or {}).get("imageUrl", "")
    status = request.form.get("status", "active")
    visible_in_app = request.form.get("visibleInApp") == "on"
    if status != "active":
        visible_in_app = False
    parent_id = request.form.get("parentId", "").strip()
    if existing and parent_id == existing.get("id"):
        parent_id = ""
    now = utc_now()
    payload = {
        "name": name,
        "slug": category_slug(request.form.get("slug", "").strip() or name),
        "description": request.form.get("description", "").strip(),
        "imageUrl": image_url,
        "icon": request.form.get("icon", "bi-tags").strip() or "bi-tags",
        "sortOrder": max(0, safe_int(request.form.get("sortOrder"), 0)),
        "status": status,
        "visibleInApp": visible_in_app,
        "parentId": parent_id if find_by_id(store.get("categories", []), parent_id) else "",
        "updatedAt": now,
    }
    if existing is None:
        payload["id"] = next_id("cat", payload["slug"] or name)
        payload["createdAt"] = now
    else:
        payload["id"] = existing["id"]
        payload["createdAt"] = existing.get("createdAt", now)
    return payload


def category_form_snapshot() -> dict:
    name = request.form.get("name", "").strip()
    status = request.form.get("status", "active")
    return {
        "name": name,
        "slug": category_slug(request.form.get("slug", "").strip() or name),
        "description": request.form.get("description", "").strip(),
        "imageUrl": request.form.get("imageUrl", "").strip(),
        "icon": request.form.get("icon", "bi-tags").strip() or "bi-tags",
        "sortOrder": request.form.get("sortOrder", "0"),
        "status": status,
        "visibleInApp": request.form.get("visibleInApp") == "on" and status == "active",
        "parentId": request.form.get("parentId", "").strip(),
    }


def category_descendant_ids(store: dict, category_id: str) -> set[str]:
    descendants: set[str] = set()
    pending = [category_id]
    while pending:
        parent_id = pending.pop()
        for category in store.get("categories", []):
            if category.get("parentId") == parent_id and category.get("id") not in descendants:
                descendants.add(category.get("id", ""))
                pending.append(category.get("id", ""))
    return descendants


def category_form_error(store: dict, existing: dict | None = None) -> str:
    name = request.form.get("name", "").strip()
    slug = category_slug(request.form.get("slug", "").strip() or name)
    status = request.form.get("status", "active")
    sort_order = safe_int(request.form.get("sortOrder"), 0)
    parent_id = request.form.get("parentId", "").strip()
    if not name:
        return "El nombre de la categoria es obligatorio."
    if not slug:
        return "El slug de la categoria no es valido."
    duplicated = any(
        category_slug(category.get("slug", "") or category.get("name", "")) == slug
        and (existing is None or category.get("id") != existing.get("id"))
        for category in store.get("categories", [])
    )
    if duplicated:
        return f"El slug {slug} ya existe en categorias."
    if status not in {key for key, _label in CATEGORY_STATUS_OPTIONS}:
        return "El estado de la categoria no es valido."
    if sort_order < 0:
        return "El orden de visualizacion no puede ser negativo."
    if parent_id:
        if existing and parent_id == existing.get("id"):
            return "Una categoria no puede ser su propia categoria padre."
        if existing and parent_id in category_descendant_ids(store, existing.get("id", "")):
            return "La categoria padre seleccionada generaria una jerarquia circular."
        if not find_by_id(store.get("categories", []), parent_id):
            return "Selecciona una categoria padre valida."
    return ""


def category_page_context(store: dict, error: str = "") -> dict:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "status": request.args.get("status", "").strip(),
        "visibility": request.args.get("visibility", "").strip(),
        "parent": request.args.get("parent", "").strip(),
    }
    categories = [
        enrich_category(category, store)
        for category in store.get("categories", [])
        if category.get("status") != "deleted"
    ]
    filtered = categories
    if filters["q"]:
        filtered = [
            category
            for category in filtered
            if filters["q"] in " ".join(
                [
                    category.get("name", ""),
                    category.get("slug", ""),
                    category.get("description", ""),
                    category.get("parentName", ""),
                ]
            ).lower()
        ]
    if filters["status"]:
        filtered = [category for category in filtered if category.get("status") == filters["status"]]
    if filters["visibility"] == "visible":
        filtered = [category for category in filtered if category.get("visibleInApp")]
    elif filters["visibility"] == "hidden":
        filtered = [category for category in filtered if not category.get("visibleInApp")]
    elif filters["visibility"] == "missing_image":
        filtered = [category for category in filtered if not category.get("imageUrl")]
    if filters["parent"] == "root":
        filtered = [category for category in filtered if not category.get("parentId")]
    elif filters["parent"]:
        filtered = [category for category in filtered if category.get("parentId") == filters["parent"]]
    metrics = {
        "total": len(categories),
        "active": sum(1 for category in categories if category.get("status") == "active"),
        "visible": sum(1 for category in categories if category.get("visibleInApp")),
        "with_image": sum(1 for category in categories if category.get("imageUrl")),
        "root": sum(1 for category in categories if not category.get("parentId")),
        "children": sum(1 for category in categories if category.get("parentId")),
    }
    return {
        "categories": sorted(filtered, key=lambda item: (safe_int(item.get("sortOrder"), 0), item.get("name", ""))),
        "all_categories": sorted(categories, key=lambda item: (safe_int(item.get("sortOrder"), 0), item.get("name", ""))),
        "filters": filters,
        "metrics": metrics,
        "category_status_options": CATEGORY_STATUS_OPTIONS,
        "category_charts": {
            "products": graphify_from_pairs(
                [(category.get("name", ""), float(category.get("productsCount") or 0)) for category in categories],
                6,
            ),
            "visibility": graphify_from_pairs(
                [
                    ("Visibles app", metrics["visible"]),
                    ("Ocultas", metrics["total"] - metrics["visible"]),
                    ("Con imagen", metrics["with_image"]),
                    ("Raiz", metrics["root"]),
                ],
                4,
            ),
        },
        "can_create_categories": can_module_action("categories", "create"),
        "can_edit_categories": can_module_action("categories", "edit"),
        "error": error,
        "bulk_result": consume_bulk_result("categories") if not error else None,
    }


def product_category_options(store: dict) -> list[dict]:
    return sorted(
        [
            enrich_category(category, store)
            for category in store.get("categories", [])
            if category.get("status") != "deleted"
        ],
        key=lambda item: (safe_int(item.get("sortOrder"), 0), item.get("name", "")),
    )


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
    name = request.form.get("name", "").strip()
    status = request.form.get("status", "active")
    commission = safe_float(request.form.get("commissionRatePercent"), 0)
    goal = safe_float(request.form.get("salesGoalUsd"), 0)
    if not name:
        return "El nombre del vendedor es obligatorio."
    if not email:
        return "El email del vendedor es obligatorio."
    if status not in {key for key, _label in SELLER_STATUS_OPTIONS}:
        return "El estado del vendedor no es valido."
    if commission < 0 or commission > 100:
        return "La comision debe estar entre 0 y 100%."
    if goal < 0:
        return "La meta mensual no puede ser negativa."
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
    business_name = (
        request.form.get("businessName", "").strip()
        or request.form.get("commercialName", "").strip()
        or request.form.get("legalName", "").strip()
    )
    tax_id = request.form.get("taxId", "").strip().lower()
    if not business_name:
        return "La razon social o nombre comercial del cliente es obligatoria."
    if not email:
        return "El email del cliente ferretero es obligatorio."
    duplicated = any(
        client.get("email", "").lower() == email
        and (existing is None or client.get("id") != existing.get("id"))
        for client in store["clients"]
    )
    if duplicated:
        return f"Ya existe un cliente con el email {email}."
    duplicated_tax_id = bool(tax_id) and any(
        client.get("taxId", "").strip().lower() == tax_id
        and (existing is None or client.get("id") != existing.get("id"))
        for client in store["clients"]
    )
    if duplicated_tax_id:
        return f"Ya existe un cliente con el RIF {request.form.get('taxId', '').strip()}."
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
    first_name = request.form.get("firstName", "").strip()
    last_name = request.form.get("lastName", "").strip()
    display_name = request.form.get("name", "").strip()
    if first_name or last_name:
        display_name = f"{first_name} {last_name}".strip()
    mobile_access_values = request.form.getlist("mobileAccessEnabled")
    payload = {
        "firstName": first_name or (existing or {}).get("firstName", ""),
        "lastName": last_name or (existing or {}).get("lastName", ""),
        "name": display_name,
        "email": email,
        "role": request.form.get("role", "operator"),
        "status": request.form.get("status", "active"),
        "sellerCode": request.form.get("sellerCode", "").strip().upper(),
        "sellerZone": request.form.get("sellerZone", "").strip(),
        "sellerTerritory": request.form.get("sellerTerritory", "").strip(),
        "sellerSupervisor": request.form.get("sellerSupervisor", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "hiredAt": request.form.get("hiredAt", "").strip(),
        "mobileAccessEnabled": "on" in mobile_access_values if mobile_access_values else bool((existing or {}).get("mobileAccessEnabled", True)),
        "internalNotes": request.form.get("internalNotes", "").strip(),
        "commissionRatePercent": safe_float(
            request.form.get("commissionRatePercent"),
            safe_float((existing or {}).get("commissionRatePercent"), 0),
        ),
        "salesGoalUsd": safe_float(
            request.form.get("salesGoalUsd"),
            safe_float((existing or {}).get("salesGoalUsd"), 0),
        ),
        "updatedAt": now,
    }
    if payload["status"] != "active":
        payload["mobileAccessEnabled"] = False
    if existing is None:
        payload["id"] = next_id("admin", email)
        payload["createdAt"] = now
        payload["passwordHash"] = generate_password_hash(password)
        payload["mustChangePassword"] = True
        payload["failedLoginAttempts"] = 0
        payload["lastFailedLoginAt"] = ""
        payload["lastLoginAt"] = ""
        payload["lastLoginIp"] = ""
        payload["sessionVersion"] = 0
    else:
        payload["id"] = existing["id"]
        payload["createdAt"] = existing.get("createdAt", now)
        payload["passwordHash"] = (
            generate_password_hash(password) if password else existing.get("passwordHash", "")
        )
        payload["mustChangePassword"] = True if password else bool(existing.get("mustChangePassword"))
        payload["failedLoginAttempts"] = safe_int(existing.get("failedLoginAttempts"))
        payload["lastFailedLoginAt"] = existing.get("lastFailedLoginAt", "")
        payload["lastLoginAt"] = existing.get("lastLoginAt", "")
        payload["lastLoginIp"] = existing.get("lastLoginIp", "")
        payload["sessionVersion"] = user_session_version(existing)
        payload["deletedAt"] = existing.get("deletedAt", "")
    return payload


def admin_users_page_context(store: dict, error: str = "") -> dict:
    users = web_admin_users(store)
    audit_events = store.get("audit_events", [])
    access_events_by_user: dict[str, list[dict]] = {}
    for event in audit_events:
        if event.get("entityType") != "admin_user":
            continue
        if event.get("action") not in {"login", "logout", "login_failed", "login_limited", "password_change", "password_reset", "session_revoke"}:
            continue
        access_events_by_user.setdefault(event.get("entityId", ""), []).append(event)
    for events in access_events_by_user.values():
        events.sort(key=lambda item: item.get("createdAt", ""), reverse=True)
    metrics = {
        "total": len(users),
        "active": sum(1 for user in users if user.get("status") == "active"),
        "blocked": sum(1 for user in users if user.get("status") == "blocked"),
        "temporary": sum(1 for user in users if user.get("mustChangePassword")),
    }
    return {
        "users": users,
        "metrics": metrics,
        "error": error,
        "notice": session.pop("admin_user_notice", None),
        "access_events_by_user": access_events_by_user,
    }


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
    if requested_credit_status not in dict(CREDIT_REQUEST_STATUS_OPTIONS):
        requested_credit_status = "none"
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
        "legalName": request.form.get("legalName", "").strip(),
        "commercialName": request.form.get("commercialName", "").strip(),
        "businessName": request.form.get("businessName", "").strip(),
        "taxId": request.form.get("taxId", "").strip(),
        "contactName": request.form.get("contactName", "").strip(),
        "administrativeContact": request.form.get("administrativeContact", "").strip(),
        "receivingContact": request.form.get("receivingContact", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "whatsapp": request.form.get("whatsapp", "").strip(),
        "email": email,
        "clientType": request.form.get("clientType", "ferretero"),
        "clientCategory": request.form.get("clientCategory", "standard"),
        "priceList": request.form.get("priceList", "b2b"),
        "authorizedDiscountPercent": float(request.form.get("authorizedDiscountPercent") or 0),
        "status": request.form.get("status", "active"),
        "address": request.form.get("address", "").strip(),
        "fiscalAddress": request.form.get("fiscalAddress", "").strip(),
        "shippingAddress": request.form.get("shippingAddress", "").strip(),
        "country": request.form.get("country", "VE").strip() or "VE",
        "state": request.form.get("state", "").strip(),
        "city": request.form.get("city", "").strip(),
        "deliveryZone": request.form.get("deliveryZone", "").strip(),
        "assignedSellerId": seller_id,
        "assignedSellerName": seller_name,
        "defaultSaleType": request.form.get("defaultSaleType", "cash"),
        "allowedPaymentTermsDays": selected_payment_terms(),
        "collectionStatus": request.form.get("collectionStatus", "without_debt"),
        "creditRiskLevel": request.form.get("creditRiskLevel", "low"),
        "creditScore": int(float(request.form.get("creditScore") or (existing or {}).get("creditScore") or 0)),
        "creditManagerNote": request.form.get("creditManagerNote", (existing or {}).get("creditManagerNote", "")).strip(),
        "creditReviewedBy": (existing or {}).get("creditReviewedBy", ""),
        "creditReviewedAt": (existing or {}).get("creditReviewedAt", ""),
        "creditRequestStatus": requested_credit_status,
        "creditRequestedUsd": credit_requested,
        "creditEnabled": credit_enabled,
        "creditLimitUsd": credit_limit,
        "creditUsedUsd": float(request.form.get("creditUsedUsd") or (existing or {}).get("creditUsedUsd") or 0),
        "paymentTermsDays": payment_terms_days,
        "notes": request.form.get("notes", "").strip(),
        "updatedAt": now,
    }
    payload["businessName"] = payload["businessName"] or payload["commercialName"] or payload["legalName"]
    payload["commercialName"] = payload["commercialName"] or payload["businessName"]
    payload["legalName"] = payload["legalName"] or payload["businessName"]
    payload["whatsapp"] = payload["whatsapp"] or payload["phone"]
    payload["fiscalAddress"] = payload["fiscalAddress"] or payload["address"]
    payload["shippingAddress"] = payload["shippingAddress"] or payload["address"]
    payload["address"] = payload["address"] or payload["shippingAddress"] or payload["fiscalAddress"]
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
    filters = {
        "q": request.args.get("q", "").strip(),
        "status": request.args.get("status", "").strip(),
        "seller": request.args.get("seller", "").strip(),
        "collection": request.args.get("collection", "").strip(),
        "credit": request.args.get("credit", "").strip(),
    }
    if filters["q"]:
        query = filters["q"].lower()
        clients_list = [
            client for client in clients_list
            if query in " ".join(
                [
                    client.get("businessName", ""),
                    client.get("legalName", ""),
                    client.get("commercialName", ""),
                    client.get("taxId", ""),
                    client.get("email", ""),
                    client.get("phone", ""),
                    client.get("whatsapp", ""),
                    client.get("city", ""),
                    client.get("deliveryZone", ""),
                ]
            ).lower()
        ]
    if filters["status"]:
        clients_list = [client for client in clients_list if client.get("status") == filters["status"]]
    if filters["seller"]:
        clients_list = [client for client in clients_list if client.get("assignedSellerId") == filters["seller"]]
    if filters["collection"]:
        clients_list = [client for client in clients_list if client.get("collectionStatus") == filters["collection"]]
    if filters["credit"]:
        clients_list = [client for client in clients_list if client.get("creditStatus") == filters["credit"] or client.get("creditRequestStatus") == filters["credit"]]
    client_ids = {client.get("id", "") for client in clients_list}
    orders_by_client: dict[str, list[dict]] = {}
    for order in sorted(store.get("orders", []), key=lambda item: item.get("createdAt", ""), reverse=True):
        if order.get("customerId") not in client_ids:
            continue
        orders_by_client.setdefault(order.get("customerId", ""), []).append(enrich_order(order, store.get("credit_movements", [])))
    metrics = {
        "clients": len(clients_list),
        "active": sum(1 for client in clients_list if client.get("status") == "active"),
        "prospects": sum(1 for client in clients_list if client.get("status") == "prospect"),
        "blocked": sum(1 for client in clients_list if str(client.get("status", "")).startswith("blocked")),
        "credit_enabled": sum(1 for client in clients_list if client.get("creditEnabled")),
        "credit_requested": sum(1 for client in clients_list if client.get("creditRequestStatus") == "pending"),
        "credit_available": sum(float(client.get("creditAvailableUsd") or 0) for client in clients_list),
        "credit_exposure": sum(float(client.get("creditExposureUsd") or 0) for client in clients_list),
        "open_balance": sum(float(client.get("openBalanceUsd") or 0) for client in clients_list),
        "overdue_balance": sum(float(client.get("overdueBalanceUsd") or 0) for client in clients_list),
    }
    return {
        "clients": sorted(clients_list, key=lambda item: item.get("businessName", "")),
        "sellers": sales_users(store),
        "payment_terms": PAYMENT_TERM_OPTIONS,
        "sale_type_options": SALE_TYPE_OPTIONS,
        "client_status_options": CLIENT_STATUS_OPTIONS,
        "client_type_options": CLIENT_TYPE_OPTIONS,
        "client_category_options": CLIENT_CATEGORY_OPTIONS,
        "price_list_options": PRICE_LIST_OPTIONS,
        "collection_status_options": COLLECTION_STATUS_OPTIONS,
        "credit_status_options": CREDIT_REQUEST_STATUS_OPTIONS,
        "credit_risk_options": CREDIT_RISK_OPTIONS,
        "can_approve_credit": can_module_action("credit", "approve"),
        "can_edit_clients": can_module_action("clients", "edit"),
        "can_create_clients": can_module_action("clients", "create"),
        "metrics": metrics,
        "filters": filters,
        "orders_by_client": orders_by_client,
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
    seller_clients = [
        enrich_client(client, store.get("orders", []), movements)
        for client in store.get("clients", [])
        if client.get("assignedSellerId") == seller_id
    ]
    now = datetime.now(timezone.utc)

    def is_current_month(value: str | None) -> bool:
        if not value:
            return False
        parsed = parse_utc_datetime(value)
        return parsed.year == now.year and parsed.month == now.month

    month_orders = [order for order in seller_orders if is_current_month(order.get("createdAt"))]
    closed_month_orders = [
        order for order in month_orders if order.get("status") not in {"cancelled", "rejected"}
    ]
    active_clients = [client for client in seller_clients if client.get("status") == "active"]
    sales_goal = safe_float(enriched.get("salesGoalUsd"), 0)
    month_sales = round(sum(float(order.get("totalUsd") or 0) for order in closed_month_orders), 2)
    orders_count = len(seller_orders)
    enriched["ordersCount"] = len(seller_orders)
    enriched["clientsCount"] = len(seller_clients)
    enriched["activeClientsCount"] = len(active_clients)
    enriched["newClientsMonth"] = sum(1 for client in seller_clients if is_current_month(client.get("createdAt")))
    enriched["salesUsd"] = round(sum(float(order.get("totalUsd") or 0) for order in seller_orders), 2)
    enriched["salesMonthUsd"] = month_sales
    enriched["salesGoalUsd"] = sales_goal
    enriched["goalProgressPercent"] = round((month_sales / sales_goal) * 100, 1) if sales_goal > 0 else 0
    enriched["ticketAverageUsd"] = round(enriched["salesUsd"] / orders_count, 2) if orders_count else 0.0
    enriched["openOrders"] = sum(1 for order in seller_orders if order.get("balanceUsd", 0) > 0)
    enriched["openBalanceUsd"] = round(sum(float(order.get("balanceUsd") or 0) for order in seller_orders), 2)
    enriched["overdueBalanceUsd"] = round(
        sum(float(order.get("balanceUsd") or 0) for order in seller_orders if order.get("dueStatus") == "overdue"),
        2,
    )
    enriched["pendingCreditRequests"] = sum(
        1 for client in seller_clients if client.get("creditRequestStatus") == "pending"
    )
    enriched["commissionUsd"] = round(sum(float(order.get("commissionUsd") or 0) for order in seller_orders), 2)
    enriched["commissionPendingUsd"] = round(
        sum(
            float(order.get("commissionUsd") or 0)
            for order in seller_orders
            if order.get("commissionStatus") == "commission_pending"
        ),
        2,
    )
    enriched["commissionApprovedUsd"] = round(
        sum(
            float(order.get("commissionUsd") or 0)
            for order in seller_orders
            if order.get("commissionStatus") == "commission_approved"
        ),
        2,
    )
    enriched["commissionPaidUsd"] = round(
        sum(
            float(order.get("commissionUsd") or 0)
            for order in seller_orders
            if order.get("commissionStatus") == "commission_paid"
        ),
        2,
    )
    enriched["lastOrderAt"] = max((order.get("createdAt", "") for order in seller_orders), default="")
    enriched["statusLabel"] = seller_status_label(enriched.get("status", "active"))
    enriched["mobileAccessEnabled"] = bool(enriched.get("mobileAccessEnabled", True))
    enriched["mobileAccessLabel"] = "Activo" if enriched["mobileAccessEnabled"] else "Desactivado"
    enriched["clientsPreview"] = sorted(seller_clients, key=lambda item: item.get("businessName", ""))[:5]
    enriched["ordersPreview"] = sorted(seller_orders, key=lambda item: item.get("createdAt", ""), reverse=True)[:5]
    return enriched


def sellers_page_context(store: dict, error: str = "") -> dict:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "status": request.args.get("status", "").strip(),
        "zone": request.args.get("zone", "").strip(),
    }
    all_sellers = [
        enrich_seller(store, seller)
        for seller in store.get("admin_users", [])
        if seller.get("role") == "sales" and seller.get("status") != "deleted"
    ]
    sellers = all_sellers
    if filters["q"]:
        sellers = [
            seller
            for seller in sellers
            if filters["q"] in " ".join(
                [
                    seller.get("name", ""),
                    seller.get("email", ""),
                    seller.get("sellerCode", ""),
                    seller.get("sellerZone", ""),
                    seller.get("phone", ""),
                ]
            ).lower()
        ]
    if filters["status"]:
        sellers = [seller for seller in sellers if seller.get("status") == filters["status"]]
    if filters["zone"]:
        sellers = [seller for seller in sellers if seller.get("sellerZone") == filters["zone"]]
    sellers = sorted(sellers, key=lambda item: (-float(item.get("salesMonthUsd") or 0), item.get("name", "")))
    for index, seller in enumerate(sellers, start=1):
        seller["ranking"] = index
    total_goal = sum(float(seller.get("salesGoalUsd") or 0) for seller in sellers)
    total_month = sum(float(seller.get("salesMonthUsd") or 0) for seller in sellers)
    metrics = {
        "sellers": len(sellers),
        "active": sum(1 for seller in sellers if seller.get("status") == "active"),
        "clients": sum(int(seller.get("clientsCount") or 0) for seller in sellers),
        "sales": sum(float(seller.get("salesUsd") or 0) for seller in sellers),
        "sales_month": total_month,
        "goal_total": total_goal,
        "goal_progress": round((total_month / total_goal) * 100, 1) if total_goal > 0 else 0,
        "ticket_average": round(
            sum(float(seller.get("salesUsd") or 0) for seller in sellers)
            / max(sum(int(seller.get("ordersCount") or 0) for seller in sellers), 1),
            2,
        ),
        "pending_credit": sum(int(seller.get("pendingCreditRequests") or 0) for seller in sellers),
        "commission_pending": sum(float(seller.get("commissionPendingUsd") or 0) for seller in sellers),
    }
    return {
        "sellers": sellers,
        "metrics": metrics,
        "filters": filters,
        "seller_status_options": SELLER_STATUS_OPTIONS,
        "zones": sorted({seller.get("sellerZone", "") for seller in all_sellers if seller.get("sellerZone")}),
        "seller_charts": {
            "sales_month": graphify_from_pairs(
                [(seller.get("name", "Vendedor"), float(seller.get("salesMonthUsd") or 0)) for seller in sellers],
                6,
            ),
            "clients": graphify_from_pairs(
                [(seller.get("name", "Vendedor"), float(seller.get("clientsCount") or 0)) for seller in sellers],
                6,
            ),
        },
        "can_edit_sellers": can_module_action("sellers", "edit"),
        "can_create_sellers": can_module_action("sellers", "create"),
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


def products_page_context(store: dict, error: str = "", include_bulk: bool = True) -> dict:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "category": request.args.get("category", "").strip(),
        "status": request.args.get("status", "").strip(),
        "stock": request.args.get("stock", "").strip(),
        "visibility": request.args.get("visibility", "").strip(),
    }
    all_products = [
        enrich_inventory_product(product, store.get("orders", []), store.get("stock_movements", []))
        for product in store.get("products", [])
    ]
    products = all_products
    if filters["q"]:
        products = [
            product
            for product in products
            if filters["q"] in " ".join(
                [
                    product.get("sku", ""),
                    product.get("internalCode", ""),
                    product.get("title", ""),
                    product.get("brand", ""),
                    product.get("model", ""),
                    product.get("categoryName", ""),
                    product.get("subCategory", ""),
                    product.get("description", ""),
                ]
            ).lower()
        ]
    if filters["category"]:
        products = [product for product in products if product.get("categoryId") == filters["category"]]
    if filters["status"]:
        products = [product for product in products if product.get("status") == filters["status"]]
    if filters["stock"]:
        products = [product for product in products if product.get("stockStatus") == filters["stock"]]
    if filters["visibility"] == "visible":
        products = [product for product in products if product.get("visibleInApp")]
    elif filters["visibility"] == "hidden":
        products = [product for product in products if not product.get("visibleInApp")]
    elif filters["visibility"] == "featured":
        products = [product for product in products if product.get("featured")]
    elif filters["visibility"] == "offer":
        products = [product for product in products if product.get("onSale") or product.get("hasDiscount")]
    elif filters["visibility"] == "missing_media":
        products = [product for product in products if not product.get("imageUrl") and not product.get("imageUrls")]

    metrics = {
        "products": len(all_products),
        "active": sum(1 for product in all_products if product.get("status") == "active"),
        "visible": sum(1 for product in all_products if product.get("visibleInApp")),
        "featured": sum(1 for product in all_products if product.get("featured")),
        "offers": sum(1 for product in all_products if product.get("onSale") or product.get("hasDiscount")),
        "low_stock": sum(1 for product in all_products if product.get("stockStatus") in {"low", "out", "replenishment"}),
        "missing_media": sum(1 for product in all_products if not product.get("imageUrl") and not product.get("imageUrls")),
        "catalog_value": round(sum(float(product.get("publicPriceUsd") or 0) * int(product.get("availableStock") or 0) for product in all_products), 2),
    }
    return {
        "products": sorted(products, key=lambda item: (item.get("categoryName", ""), item.get("title", ""))),
        "all_products": all_products,
        "categories": product_category_options(store),
        "filters": filters,
        "metrics": metrics,
        "product_status_options": PRODUCT_STATUS_OPTIONS,
        "product_type_options": PRODUCT_TYPE_OPTIONS,
        "stock_status_options": [
            ("available", "Disponible"),
            ("low", "Bajo"),
            ("out", "Agotado"),
            ("replenishment", "Reposicion"),
        ],
        "product_charts": {
            "stock": graphify_from_pairs(
                [(product.get("sku", ""), float(product.get("availableStock") or 0)) for product in products],
                6,
            ),
            "media": graphify_from_pairs(
                [(product.get("sku", ""), float(product.get("mediaCount") or 0)) for product in products],
                6,
            ),
        },
        "can_create_products": can_module_action("products", "create"),
        "can_edit_products": can_module_action("products", "edit"),
        "error": error,
        "bulk_result": consume_bulk_result("products") if include_bulk and not error else None,
    }


def stock_page_context(store: dict, error: str = "", include_bulk: bool = True) -> dict:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "status": request.args.get("status", "").strip(),
        "location": request.args.get("location", "").strip(),
        "movement": request.args.get("movement", "").strip(),
    }
    movements = [enrich_stock_movement(movement) for movement in store.get("stock_movements", [])]
    all_products = [
        enrich_inventory_product(product, store.get("orders", []), movements)
        for product in store.get("products", [])
    ]
    products = all_products
    if filters["q"]:
        products = [
            product
            for product in products
            if filters["q"] in " ".join(
                [
                    product.get("sku", ""),
                    product.get("title", ""),
                    product.get("categoryName", ""),
                    product.get("stockLocation", ""),
                    product.get("stockNotes", ""),
                    product.get("lastMovementTypeLabel", ""),
                ]
            ).lower()
        ]
    if filters["status"]:
        if filters["status"] == "without_movement":
            products = [product for product in products if not product.get("lastMovementAt")]
        else:
            products = [product for product in products if product.get("stockStatus") == filters["status"]]
    if filters["location"]:
        products = [product for product in products if product.get("stockLocation") == filters["location"]]
    if filters["movement"]:
        products = [product for product in products if product.get("lastMovementType") == filters["movement"]]

    sorted_movements = sorted(movements, key=lambda item: item.get("createdAt", ""), reverse=True)
    movement_counts: dict[str, int] = {}
    for movement in movements:
        label = movement.get("typeLabel", "Movimiento")
        movement_counts[label] = movement_counts.get(label, 0) + 1
    locations = sorted(
        {
            product.get("stockLocation", "")
            for product in all_products
            if product.get("stockLocation")
        }
    )
    metrics = {
        "sku": len(all_products),
        "physical": sum(int(product.get("physicalStock") or 0) for product in all_products),
        "reserved": sum(int(product.get("committedStock") or 0) for product in all_products),
        "available": sum(int(product.get("availableStock") or 0) for product in all_products),
        "low": sum(1 for product in all_products if product.get("stockStatus") in {"low", "replenishment"}),
        "out": sum(1 for product in all_products if product.get("stockStatus") == "out"),
        "without_movement": sum(1 for product in all_products if not product.get("lastMovementAt")),
        "overstock": sum(1 for product in all_products if product.get("stockStatus") == "overstock"),
    }
    return {
        "products": sorted(products, key=lambda item: (item.get("stockStatus", ""), item.get("sku", ""))),
        "all_products": all_products,
        "movements": sorted_movements,
        "filters": filters,
        "locations": locations,
        "metrics": metrics,
        "stock_status_options": STOCK_STATUS_OPTIONS,
        "stock_movement_options": STOCK_MOVEMENT_OPTIONS,
        "manual_movement_options": [
            ("entry", "Entrada"),
            ("exit", "Salida"),
            ("adjustment_positive", "Ajuste positivo"),
            ("adjustment_negative", "Ajuste negativo"),
            ("adjustment", "Ajuste a cantidad final"),
            ("return", "Devolucion"),
        ],
        "stock_charts": {
            "available": graphify_from_pairs(
                [(product.get("sku", ""), float(product.get("availableStock") or 0)) for product in products],
                8,
            ),
            "movement_types": graphify_from_pairs(list(movement_counts.items()), 6),
            "critical": graphify_from_pairs(
                [
                    (product.get("sku", ""), float(product.get("minimumStock") or 0) - float(product.get("availableStock") or 0))
                    for product in all_products
                    if product.get("stockStatus") in {"low", "out", "replenishment"}
                ],
                6,
            ),
        },
        "rotation_chart": rotation_chart(products),
        "can_edit_stock": can_module_action("stock", "edit"),
        "can_import_stock": can_module_action("stock", "import"),
        "can_export_stock": can_module_action("stock", "export"),
        "error": error,
        "bulk_result": consume_bulk_result("stock") if include_bulk and not error else None,
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
        "shippingAddress": request.form.get("shippingAddress", "").strip(),
        "customerComment": request.form.get("customerComment", "").strip(),
        "internalComment": request.form.get("internalComment", "").strip(),
        "notes": (request.form.get("notes", "") or request.form.get("internalComment", "")).strip(),
        "preview": {"exchangeRateUsdVes": current_rate()},
    }


def orders_page_context(store: dict, error: str = "") -> dict:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "status": request.args.get("status", "").strip(),
        "sale_type": request.args.get("sale_type", "").strip(),
        "credit_status": request.args.get("credit_status", "").strip(),
        "inventory_status": request.args.get("inventory_status", "").strip(),
        "payment_status": request.args.get("payment_status", "").strip(),
        "seller": request.args.get("seller", "").strip(),
        "channel": request.args.get("channel", "").strip(),
        "due": request.args.get("due", "").strip(),
    }
    movements = store.get("credit_movements", [])
    all_orders = [
        enrich_order(order, movements)
        for order in sorted(visible_orders_for_current_user(store), key=lambda item: item.get("createdAt", ""), reverse=True)
    ]
    orders_list = all_orders
    if filters["q"]:
        orders_list = [
            order
            for order in orders_list
            if filters["q"] in " ".join(
                [
                    order.get("orderId", ""),
                    order.get("customerName", ""),
                    order.get("customerId", ""),
                    order.get("sellerName", ""),
                    order.get("saleTypeLabel", ""),
                    order.get("shippingAddress", ""),
                    order.get("internalComment", ""),
                    " ".join(item.get("sku", "") for item in order.get("items") or []),
                ]
            ).lower()
        ]
    if filters["status"]:
        orders_list = [order for order in orders_list if order.get("status") == filters["status"]]
    if filters["sale_type"]:
        orders_list = [order for order in orders_list if order.get("saleType") == filters["sale_type"]]
    if filters["credit_status"]:
        orders_list = [order for order in orders_list if order.get("creditStatus") == filters["credit_status"]]
    if filters["inventory_status"]:
        orders_list = [order for order in orders_list if order.get("inventoryStatus") == filters["inventory_status"]]
    if filters["payment_status"]:
        orders_list = [order for order in orders_list if order.get("paymentStatus") == filters["payment_status"]]
    if filters["seller"]:
        orders_list = [order for order in orders_list if order.get("sellerId") == filters["seller"]]
    if filters["channel"]:
        orders_list = [order for order in orders_list if order.get("salesChannel") == filters["channel"]]
    if filters["due"]:
        orders_list = [order for order in orders_list if order.get("dueStatus") == filters["due"]]

    status_counts: dict[str, int] = {}
    sale_type_totals: dict[str, float] = {}
    seller_totals: dict[str, float] = {}
    for order in all_orders:
        status_counts[order.get("statusLabel", "Sin estado")] = status_counts.get(order.get("statusLabel", "Sin estado"), 0) + 1
        sale_label = order.get("saleTypeLabel", "Sin tipo")
        sale_type_totals[sale_label] = sale_type_totals.get(sale_label, 0.0) + float(order.get("totalUsd") or 0)
        seller = order.get("sellerName") or "Sin vendedor"
        seller_totals[seller] = seller_totals.get(seller, 0.0) + float(order.get("totalUsd") or 0)

    sellers = [
        seller
        for seller in store.get("admin_users", [])
        if seller.get("role") == "sales" and seller.get("status") != "deleted"
    ]
    metrics = {
        "orders": len(all_orders),
        "filtered": len(orders_list),
        "total": round(sum(float(order.get("totalUsd") or 0) for order in orders_list), 2),
        "balance": round(sum(float(order.get("balanceUsd") or 0) for order in orders_list), 2),
        "review": sum(1 for order in orders_list if order.get("status") in {"credit_review", "payment_under_review"}),
        "overdue": sum(1 for order in orders_list if order.get("dueStatus") == "overdue"),
        "commission_pending": round(
            sum(
                float(order.get("commissionUsd") or 0)
                for order in orders_list
                if order.get("commissionStatus") == "commission_pending"
            ),
            2,
        ),
    }
    return {
        "orders": orders_list,
        "all_orders": all_orders,
        "metrics": metrics,
        "filters": filters,
        "status_options": ORDER_STATUS_OPTIONS,
        "payment_methods": PAYMENT_METHOD_OPTIONS,
        "sale_type_options": SALE_TYPE_OPTIONS,
        "seller_options": sorted(sellers, key=lambda item: item.get("name", "")),
        "channel_options": sorted(SALES_CHANNEL_LABELS.items(), key=lambda item: item[1]),
        "credit_status_options": sorted({(order.get("creditStatus", ""), order.get("creditStatusLabel", "")) for order in all_orders if order.get("creditStatus")}),
        "inventory_status_options": sorted({order.get("inventoryStatus", "") for order in all_orders if order.get("inventoryStatus")}),
        "payment_status_options": [("pending", "Pendiente"), ("partial", "Pago parcial"), ("paid", "Pagado")],
        "due_status_options": [
            ("without_due_date", "Sin plazo"),
            ("current", "Vigente"),
            ("due_soon", "Por vencer"),
            ("overdue", "Vencida"),
            ("paid", "Pagada"),
        ],
        "order_charts": {
            "status": graphify_from_pairs([(label, float(value)) for label, value in status_counts.items()], 6),
            "sale_type": graphify_from_pairs(list(sale_type_totals.items()), 6),
            "seller": graphify_from_pairs(list(seller_totals.items()), 6),
        },
        "can_manage_orders": role_allowed(ORDER_MANAGEMENT_ROLES),
        "can_create_assisted_order": role_allowed(SALES_ROLES),
        "can_export_orders": can_module_action("orders", "export"),
        "error": error,
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
    products_by_id, products_by_sku = product_lookup_maps(store.get("products", []))
    movements = store.get("credit_movements", [])
    enriched_orders = [enrich_order(order, movements) for order in orders]
    clients_list = [enrich_client(client, orders, movements) for client in store.get("clients", [])]
    filters = dashboard_filters_from_request()
    filtered_orders = [
        order
        for order in enriched_orders
        if order_matches_dashboard_filters(order, filters, products_by_id, products_by_sku)
    ]
    sellers = sales_users(store)
    metrics = dashboard_order_metrics(filtered_orders, clients_list, products, sellers)
    metrics.update(
        {
            "products": len(products),
            "active_products": sum(1 for product in products if product.get("status") == "active"),
            "clients": len(clients_list),
            "sellers": len(sellers),
            "credit_requested": sum(1 for client in clients_list if client.get("creditRequestStatus") == "pending"),
            "low_stock": metrics["stock_critical"],
            "orders": len(filtered_orders),
            "announcements": len(store["announcements"]),
        }
    )
    filter_options = {
        "sellers": sellers,
        "clients": sorted(clients_list, key=lambda item: item.get("businessName", "")),
        "categories": sorted(store.get("categories", []), key=lambda item: item.get("name", "")),
        "products": sorted(store.get("products", []), key=lambda item: item.get("title", "")),
        "order_statuses": ORDER_STATUS_OPTIONS + [("rejected", "Rechazada")],
        "credit_statuses": [
            ("approved", "Aprobado"),
            ("manual_review", "Revision manual"),
            ("without_credit", "Sin linea"),
            ("client_not_active", "Cliente inactivo"),
            ("released", "Liberado"),
            ("cancelled", "Cancelado"),
        ],
        "collection_statuses": [
            ("current", "Al dia"),
            ("due_soon", "Por vencer"),
            ("overdue", "Vencido"),
            ("paid", "Pagado"),
            ("without_due_date", "Sin plazo"),
        ],
        "dispatch_statuses": sorted(
            {
                order.get("dispatchStatus", "")
                for order in enriched_orders
                if order.get("dispatchStatus", "")
            }
        ),
        "branches": sorted({order.get("branch", "") for order in enriched_orders if order.get("branch", "")}),
    }
    return render_template(
        "dashboard.html",
        metrics=metrics,
        filters=filters,
        filter_options=filter_options,
        sale_type_options=SALE_TYPE_OPTIONS,
        stock_health=stock_health(products),
        rotation_chart=rotation_chart(products),
        dashboard_charts=dashboard_charts(filtered_orders, clients_list, products_by_id, products_by_sku),
        recent_orders=sorted(filtered_orders, key=lambda item: item.get("createdAt", ""), reverse=True)[:8],
    )


@app.get("/plantillas")
@require_roles(*roles_for_action("import_templates", "view"))
def import_templates():
    template_groups = visible_import_template_groups()
    return render_template(
        "import_templates.html",
        template_groups=template_groups,
        total_templates=sum(len(group["items"]) for group in template_groups),
    )


@app.get("/plantillas/<template_key>.<file_format>")
@require_roles(*roles_for_action("import_templates", "view"))
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


@app.get("/permissions")
@require_roles("super_admin")
def permissions():
    rows = permission_matrix_rows()
    action_index = {key: {"key": key, "label": label, "icon": icon} for key, label, icon in PERMISSION_ACTIONS}
    return render_template(
        "permissions.html",
        roles=WEB_ADMIN_ROLE_ORDER,
        rows=rows,
        actions=PERMISSION_ACTIONS,
        action_index=action_index,
        metrics=permission_metrics(rows),
    )


@app.route("/admin-users", methods=["GET", "POST"])
@require_roles("super_admin")
def admin_users():
    store = load_store()
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        error = admin_user_form_error(store)
        if error:
            return render_template("admin_users.html", **admin_users_page_context(store, error))
        user = admin_user_payload()
        store["admin_users"].append(user)
        record_audit_event(store, "create", "admin_user", user["id"], f"Usuario admin creado: {email}.")
        save_store(store)
        return redirect(url_for("admin_users"))

    return render_template("admin_users.html", **admin_users_page_context(store))


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
            return render_template("admin_users.html", **admin_users_page_context(store, error))
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
    user["status"] = "deleted"
    user["deletedAt"] = utc_now()
    bump_user_session_version(user)
    record_change_event(
        store,
        "logical_delete",
        "admin_user",
        user_id,
        f"Usuario admin eliminado logicamente: {user.get('email', user_id)}.",
        before,
        user,
    )
    save_store(store)
    return redirect(url_for("admin_users"))


@app.post("/admin-users/<user_id>/status")
@require_roles("super_admin")
def admin_user_status(user_id: str):
    store = load_store()
    user = find_by_id(store.get("admin_users", []), user_id)
    target_status = request.form.get("status", "").strip()
    if not user or user.get("role") == "sales" or target_status not in {"active", "inactive", "blocked"}:
        return redirect(url_for("admin_users"))
    if user_id == session.get("admin_user_id") and target_status != "active":
        return redirect(url_for("admin_users"))
    before = copy.deepcopy(user)
    user["status"] = target_status
    if target_status == "active":
        user["failedLoginAttempts"] = 0
        user["lastFailedLoginAt"] = ""
    bump_user_session_version(user)
    record_change_event(
        store,
        "status_update",
        "admin_user",
        user_id,
        f"Usuario admin marcado como {target_status}: {user.get('email', user_id)}.",
        before,
        user,
    )
    save_store(store)
    return redirect(url_for("admin_users"))


@app.post("/admin-users/<user_id>/reset-password")
@require_roles("super_admin")
def admin_user_reset_password(user_id: str):
    store = load_store()
    user = find_by_id(store.get("admin_users", []), user_id)
    if not user or user.get("role") == "sales" or user.get("status") == "deleted":
        return redirect(url_for("admin_users"))
    before = copy.deepcopy(user)
    password = temporary_admin_password()
    user["passwordHash"] = generate_password_hash(password)
    user["mustChangePassword"] = True
    user["failedLoginAttempts"] = 0
    user["lastFailedLoginAt"] = ""
    if user.get("status") == "blocked":
        user["status"] = "active"
    bump_user_session_version(user)
    record_change_event(
        store,
        "password_reset",
        "admin_user",
        user_id,
        f"Clave temporal generada para {user.get('email', user_id)}.",
        before,
        user,
    )
    session["admin_user_notice"] = {
        "title": "Clave temporal generada",
        "message": f"Entrega esta clave a {user.get('email', user_id)} y solicita cambio al ingresar.",
        "password": password,
    }
    save_store(store)
    return redirect(url_for("admin_users"))


@app.post("/admin-users/<user_id>/revoke-sessions")
@require_roles("super_admin")
def admin_user_revoke_sessions(user_id: str):
    store = load_store()
    user = find_by_id(store.get("admin_users", []), user_id)
    if not user or user.get("role") == "sales" or user.get("status") == "deleted":
        return redirect(url_for("admin_users"))
    before = copy.deepcopy(user)
    bump_user_session_version(user)
    record_change_event(
        store,
        "session_revoke",
        "admin_user",
        user_id,
        f"Sesiones activas cerradas para {user.get('email', user_id)}.",
        before,
        user,
    )
    save_store(store)
    return redirect(url_for("admin_users"))


@app.route("/sellers", methods=["GET", "POST"])
@require_roles(*roles_for_action("sellers", "view"))
def sellers():
    store = load_store()
    if request.method == "POST":
        if not can_module_action("sellers", "create"):
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
@require_roles(*roles_for_action("sellers", "import"))
def sellers_import():
    return handle_bulk_import("sellers", "seller", import_sellers_rows, "sellers")


@app.post("/sellers/<seller_id>/edit")
@require_roles(*roles_for_action("sellers", "edit"))
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
@require_roles(*roles_for_action("sellers", "delete"))
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
        seller["mobileAccessEnabled"] = False
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
@require_roles(*roles_for_action("clients", "view"))
def clients():
    store = load_store()
    if request.method == "POST":
        if not can_module_action("clients", "create"):
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
@require_roles(*roles_for_action("clients", "import"))
def clients_import():
    return handle_bulk_import("clients", "client", import_clients_rows, "clients")


@app.post("/clients/<client_id>/edit")
@require_roles(*roles_for_action("clients", "edit"))
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


@app.post("/clients/<client_id>/status")
@require_roles(*roles_for_action("clients", "edit"))
def client_status_update(client_id: str):
    store = load_store()
    client = find_by_id(store.get("clients", []), client_id)
    if not can_access_client_record(client):
        return forbidden_response()
    target_status = request.form.get("status", "").strip()
    allowed_statuses = {status for status, _label in CLIENT_STATUS_OPTIONS}
    if not client or target_status not in allowed_statuses:
        return redirect(url_for("clients"))
    before = copy.deepcopy(client)
    client["status"] = target_status
    client["updatedAt"] = utc_now()
    if target_status == "blocked_debt":
        client["collectionStatus"] = "blocked"
    elif target_status == "active" and client.get("collectionStatus") == "blocked":
        client["collectionStatus"] = "without_debt"
    record_change_event(
        store,
        "status_update",
        "client",
        client_id,
        f"Cliente marcado como {client_status_label(target_status)}: {client.get('businessName', client_id)}.",
        before,
        client,
    )
    save_store(store)
    return redirect(url_for("clients"))


@app.post("/clients/<client_id>/delete")
@require_roles(*roles_for_action("clients", "delete"))
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
@require_roles(*roles_for_action("products", "view"))
def products():
    store = load_store()
    return render_template("products.html", **products_page_context(store))


@app.get("/products/export")
@require_roles(*roles_for_action("products", "export"))
def products_export():
    store = load_store()
    context = products_page_context(store, include_bulk=False)
    output = io.StringIO()
    fieldnames = [
        "sku",
        "codigo_interno",
        "nombre",
        "categoria",
        "subcategoria",
        "marca",
        "modelo",
        "tipo_producto",
        "unidad_venta",
        "precio_publico_usd",
        "precio_b2b_usd",
        "precio_anterior_usd",
        "descuento_porcentaje",
        "stock_fisico",
        "stock_disponible",
        "stock_minimo",
        "estado",
        "visible_app",
        "destacado",
        "oferta",
        "imagenes",
        "pdfs",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for product in context["products"]:
        writer.writerow(
            {
                "sku": product.get("sku", ""),
                "codigo_interno": product.get("internalCode", ""),
                "nombre": product.get("title", ""),
                "categoria": product.get("categoryName", ""),
                "subcategoria": product.get("subCategory", ""),
                "marca": product.get("brand", ""),
                "modelo": product.get("model", ""),
                "tipo_producto": product.get("productType", ""),
                "unidad_venta": product.get("unitOfSale", ""),
                "precio_publico_usd": product.get("publicPriceUsd", 0),
                "precio_b2b_usd": product.get("b2bPriceUsd", 0),
                "precio_anterior_usd": product.get("originalPriceUsd", 0),
                "descuento_porcentaje": product.get("discountPercent", 0),
                "stock_fisico": product.get("physicalStock", 0),
                "stock_disponible": product.get("availableStock", 0),
                "stock_minimo": product.get("minimumStock", 0),
                "estado": product.get("status", ""),
                "visible_app": "si" if product.get("visibleInApp") else "no",
                "destacado": "si" if product.get("featured") else "no",
                "oferta": "si" if product.get("onSale") or product.get("hasDiscount") else "no",
                "imagenes": "|".join(product.get("imageUrls") or []),
                "pdfs": "|".join(product.get("pdfUrls") or []),
            }
        )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=productos_wulkan.csv"},
    )


@app.post("/products/import")
@require_roles(*roles_for_action("products", "import"))
def products_import():
    return handle_bulk_import("products", "product", import_products_rows, "products")


@app.route("/products/new", methods=["GET", "POST"])
@require_roles(*roles_for_action("products", "create"))
def product_new():
    store = load_store()
    if request.method == "POST":
        error = product_form_error(store)
        if error:
            return render_template(
                "product_form.html",
                categories=product_category_options(store),
                product_status_options=PRODUCT_STATUS_OPTIONS,
                product_type_options=PRODUCT_TYPE_OPTIONS,
                rate=current_rate(),
                product=product_form_snapshot(),
                mode="Crear",
                error=error,
            )

        product = product_payload(store)
        store["products"].append(product)
        record_change_event(
            store,
            "create",
            "product",
            product["id"],
            f"Producto creado: {product['sku']}.",
            None,
            product,
        )
        save_store(store)
        return redirect(url_for("products"))

    return render_template(
        "product_form.html",
        categories=product_category_options(store),
        product_status_options=PRODUCT_STATUS_OPTIONS,
        product_type_options=PRODUCT_TYPE_OPTIONS,
        rate=current_rate(),
        product=None,
        mode="Crear",
        error="",
    )


@app.route("/products/<product_id>/edit", methods=["GET", "POST"])
@require_roles(*roles_for_action("products", "edit"))
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
                categories=product_category_options(store),
                product_status_options=PRODUCT_STATUS_OPTIONS,
                product_type_options=PRODUCT_TYPE_OPTIONS,
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
        categories=product_category_options(store),
        product_status_options=PRODUCT_STATUS_OPTIONS,
        product_type_options=PRODUCT_TYPE_OPTIONS,
        rate=current_rate(),
        product=enrich_product(product),
        mode="Editar",
        error="",
    )


@app.post("/products/<product_id>/duplicate")
@require_roles(*roles_for_action("products", "create"))
def product_duplicate(product_id: str):
    store = load_store()
    product = find_by_id(store.get("products", []), product_id)
    if not product:
        return redirect(url_for("products"))
    existing_skus = {item.get("sku", "").upper() for item in store.get("products", [])}
    base_sku = f"{product.get('sku', 'WUL-PROD').upper()}-COPY"
    new_sku = base_sku
    suffix = 2
    while new_sku in existing_skus:
        new_sku = f"{base_sku}-{suffix}"
        suffix += 1
    now = utc_now()
    duplicate = copy.deepcopy(product)
    duplicate.update(
        {
            "id": next_id("prod", new_sku),
            "sku": new_sku,
            "internalCode": "",
            "title": f"{product.get('title', 'Producto')} copia",
            "status": "hidden",
            "visibleInApp": False,
            "featured": False,
            "onSale": bool(product.get("onSale", False)),
            "stock": 0,
            "reserved": 0,
            "rotationLast30Days": 0,
            "createdAt": now,
            "updatedAt": now,
        }
    )
    store.setdefault("products", []).append(duplicate)
    record_change_event(
        store,
        "duplicate",
        "product",
        duplicate["id"],
        f"Producto duplicado desde {product.get('sku', product_id)} hacia {new_sku}.",
        product,
        duplicate,
    )
    save_store(store)
    return redirect(url_for("product_edit", product_id=duplicate["id"]))


@app.post("/products/<product_id>/delete")
@require_roles(*roles_for_action("products", "delete"))
def product_delete(product_id: str):
    store = load_store()
    product = find_by_id(store["products"], product_id)
    if not product:
        return redirect(url_for("products"))
    before = copy.deepcopy(product)
    has_history = product_has_commercial_history(store, product)
    if has_history:
        product["status"] = "inactive"
        product["updatedAt"] = utc_now()
        after = product
    else:
        store["products"] = [item for item in store["products"] if item["id"] != product_id]
        store["media_assets"] = [
            item for item in store.get("media_assets", []) if item.get("productId") != product_id
        ]
        after = None
    record_change_event(
        store,
        "delete",
        "product",
        product_id,
        f"Producto {'desactivado por historial comercial' if has_history else 'eliminado'}: {before.get('sku', product_id)}.",
        before,
        after,
    )
    save_store(store)
    return redirect(url_for("products"))


@app.route("/stock", methods=["GET", "POST"])
@require_roles(*roles_for_action("stock", "view"))
def stock():
    store = load_store()
    if request.method == "POST":
        if not can_module_action("stock", "edit"):
            return forbidden_response()
        stock_before = {
            product["id"]: {
                "sku": product.get("sku", ""),
                "stock": int(product.get("stock") or 0),
                "minimumStock": int(product.get("minimumStock") or 0),
                "maximumStock": int(product.get("maximumStock") or 0),
                "stockLocation": product.get("stockLocation", ""),
                "stockNotes": product.get("stockNotes", ""),
            }
            for product in store.get("products", [])
        }
        bulk_payload = request.form.get("bulkStock", "").strip()
        movement_type = normalize_stock_movement_type(request.form.get("type", "entry"))
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
                stock_by_sku[sku.strip().upper()] = safe_int(quantity.strip(), 0)
            for product in store.get("products", []):
                if product["sku"] in stock_by_sku:
                    reserved = reserved_by_product.get(product["id"], 0)
                    before = int(product.get("stock") or 0)
                    quantity = max(stock_by_sku[product["sku"]], reserved)
                    if quantity == before:
                        continue
                    product["stock"] = quantity
                    append_stock_movement(
                        store,
                        product,
                        "bulk_set",
                        quantity,
                        note="Carga rapida de stock fisico.",
                        before_stock=before,
                        after_stock=quantity,
                    )
        else:
            product_id = request.form.get("productId")
            product = find_by_id(store.get("products", []), product_id)
            quantity = safe_int(request.form.get("quantity"), 0)
            location = request.form.get("location", "").strip()
            note = request.form.get("note", "").strip()
            stock_notes = request.form.get("stockNotes", "").strip()
            if not product:
                return render_template("stock.html", **stock_page_context(store, "Producto no encontrado.")), 400
            if quantity < 0:
                return render_template("stock.html", **stock_page_context(store, "La cantidad no puede ser negativa.")), 400
            current_stock = int(product.get("stock") or 0)
            reserved = reserved_by_product.get(product["id"], 0)
            if movement_type in {"entry", "adjustment_positive", "return"}:
                target_stock = current_stock + quantity
            elif movement_type in {"exit", "sale", "adjustment_negative"}:
                target_stock = current_stock - quantity
            else:
                target_stock = quantity
            if target_stock < reserved:
                return render_template(
                    "stock.html",
                    **stock_page_context(
                        store,
                        f"No puedes dejar {product.get('sku', 'SKU')} en {target_stock}; tiene {reserved} unidades reservadas.",
                    ),
                ), 400
            product["stock"] = target_stock
            if location:
                product["stockLocation"] = location
            if stock_notes:
                product["stockNotes"] = stock_notes
            append_stock_movement(
                store,
                product,
                movement_type,
                quantity,
                note=note,
                before_stock=current_stock,
                after_stock=target_stock,
                location=location,
            )
        stock_after = {
            product["id"]: {
                "sku": product.get("sku", ""),
                "stock": int(product.get("stock") or 0),
                "minimumStock": int(product.get("minimumStock") or 0),
                "maximumStock": int(product.get("maximumStock") or 0),
                "stockLocation": product.get("stockLocation", ""),
                "stockNotes": product.get("stockNotes", ""),
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

    return render_template("stock.html", **stock_page_context(store))


@app.get("/stock/export")
@require_roles(*roles_for_action("stock", "export"))
def stock_export():
    store = load_store()
    context = stock_page_context(store, include_bulk=False)
    output = io.StringIO()
    fieldnames = [
        "sku",
        "nombre",
        "categoria",
        "stock_fisico",
        "reservado",
        "disponible_real",
        "stock_minimo",
        "stock_maximo",
        "stock_reposicion",
        "ubicacion",
        "estado_stock",
        "ultimo_movimiento",
        "responsable",
        "observacion",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for product in context["products"]:
        writer.writerow(
            {
                "sku": product.get("sku", ""),
                "nombre": product.get("title", ""),
                "categoria": product.get("categoryName", ""),
                "stock_fisico": product.get("physicalStock", 0),
                "reservado": product.get("committedStock", 0),
                "disponible_real": product.get("availableStock", 0),
                "stock_minimo": product.get("minimumStock", 0),
                "stock_maximo": product.get("maximumStock", 0),
                "stock_reposicion": product.get("replenishmentQty", 0),
                "ubicacion": product.get("stockLocation", ""),
                "estado_stock": product.get("stockStatusLabel", ""),
                "ultimo_movimiento": product.get("lastMovementAt", ""),
                "responsable": product.get("lastMovementBy", ""),
                "observacion": product.get("stockNotes", ""),
            }
        )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=stock_wulkan.csv"},
    )


@app.post("/stock/import")
@require_roles(*roles_for_action("stock", "import"))
def stock_import():
    return handle_bulk_import("stock", "stock", import_stock_rows, "stock")


@app.route("/categories", methods=["GET", "POST"])
@require_roles(*roles_for_action("categories", "view"))
def categories():
    store = load_store()
    if request.method == "POST":
        if not can_module_action("categories", "create"):
            return forbidden_response()
        error = category_form_error(store)
        if error:
            return render_template("categories.html", **category_page_context(store, error))
        category = category_payload(store)
        store["categories"].append(category)
        record_change_event(
            store,
            "create",
            "category",
            category["id"],
            f"Categoria creada: {category['name']}.",
            None,
            category,
        )
        save_store(store)
        return redirect(url_for("categories"))

    return render_template("categories.html", **category_page_context(store))


@app.get("/categories/export")
@require_roles(*roles_for_action("categories", "export"))
def categories_export():
    store = load_store()
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "status": request.args.get("status", "").strip(),
        "visibility": request.args.get("visibility", "").strip(),
        "parent": request.args.get("parent", "").strip(),
    }
    categories_list = [
        enrich_category(category, store)
        for category in store.get("categories", [])
        if category.get("status") != "deleted"
    ]
    if filters["q"]:
        categories_list = [
            category
            for category in categories_list
            if filters["q"] in " ".join([category.get("name", ""), category.get("slug", ""), category.get("description", "")]).lower()
        ]
    if filters["status"]:
        categories_list = [category for category in categories_list if category.get("status") == filters["status"]]
    if filters["visibility"] == "visible":
        categories_list = [category for category in categories_list if category.get("visibleInApp")]
    elif filters["visibility"] == "hidden":
        categories_list = [category for category in categories_list if not category.get("visibleInApp")]
    elif filters["visibility"] == "missing_image":
        categories_list = [category for category in categories_list if not category.get("imageUrl")]
    if filters["parent"] == "root":
        categories_list = [category for category in categories_list if not category.get("parentId")]
    elif filters["parent"]:
        categories_list = [category for category in categories_list if category.get("parentId") == filters["parent"]]

    output = io.StringIO()
    fieldnames = [
        "id",
        "nombre",
        "slug",
        "descripcion",
        "imagen_url",
        "icono",
        "orden",
        "categoria_padre",
        "visible_app",
        "estado",
        "productos",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for category in sorted(categories_list, key=lambda item: (safe_int(item.get("sortOrder"), 0), item.get("name", ""))):
        writer.writerow(
            {
                "id": category.get("id", ""),
                "nombre": category.get("name", ""),
                "slug": category.get("slug", ""),
                "descripcion": category.get("description", ""),
                "imagen_url": category.get("imageUrl", ""),
                "icono": category.get("icon", ""),
                "orden": category.get("sortOrder", 0),
                "categoria_padre": category.get("parentName", ""),
                "visible_app": "si" if category.get("visibleInApp") else "no",
                "estado": category.get("status", ""),
                "productos": category.get("productsCount", 0),
            }
        )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=categorias_wulkan.csv"},
    )


@app.post("/categories/import")
@require_roles(*roles_for_action("categories", "import"))
def categories_import():
    return handle_bulk_import("categories", "category", import_categories_rows, "categories")


@app.route("/categories/<category_id>/edit", methods=["POST"])
@require_roles(*roles_for_action("categories", "edit"))
def category_edit(category_id: str):
    store = load_store()
    category = find_by_id(store["categories"], category_id)
    if category:
        error = category_form_error(store, category)
        if error:
            return render_template("categories.html", **category_page_context(store, error))
        before = copy.deepcopy(category)
        category.update(category_payload(store, category))
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


@app.post("/categories/<category_id>/status")
@require_roles(*roles_for_action("categories", "edit"))
def category_status(category_id: str):
    store = load_store()
    category = find_by_id(store.get("categories", []), category_id)
    target_status = request.form.get("status", "").strip()
    if category and target_status in {key for key, _label in CATEGORY_STATUS_OPTIONS}:
        before = copy.deepcopy(category)
        category["status"] = target_status
        category["visibleInApp"] = request.form.get("visibleInApp") == "on" and target_status == "active"
        category["updatedAt"] = utc_now()
        record_change_event(
            store,
            "status_update",
            "category",
            category_id,
            f"Categoria marcada como {category_status_label(target_status)}: {category.get('name', category_id)}.",
            before,
            category,
        )
        save_store(store)
    return redirect(url_for("categories"))


@app.post("/categories/<category_id>/delete")
@require_roles(*roles_for_action("categories", "delete"))
def category_delete(category_id: str):
    store = load_store()
    category = find_by_id(store["categories"], category_id)
    if not category:
        return redirect(url_for("categories"))
    before = copy.deepcopy(category)
    is_referenced = any(product.get("categoryId") == category_id for product in store["products"]) or any(
        item.get("parentId") == category_id for item in store["categories"]
    )
    if is_referenced:
        category["status"] = "deleted"
        category["visibleInApp"] = False
        category["deletedAt"] = utc_now()
        record_change_event(
            store,
            "logical_delete",
            "category",
            category_id,
            f"Categoria eliminada logicamente: {category.get('name', category_id)}.",
            before,
            category,
        )
    else:
        store["categories"] = [category for category in store["categories"] if category["id"] != category_id]
        record_change_event(
            store,
            "delete",
            "category",
            category_id,
            f"Categoria eliminada: {category.get('name', category_id)}.",
            before,
            None,
        )
    save_store(store)
    return redirect(url_for("categories"))


@app.route("/media-library", methods=["GET", "POST"])
@require_roles(*roles_for_action("media_library", "view"))
def media_library():
    store = load_store()
    if request.method == "POST":
        if not can_module_action("media_library", "create"):
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
@require_roles(*roles_for_action("media_library", "import"))
def media_library_import():
    return handle_bulk_import("media_library", "media_asset", import_media_assets_rows, "media_library")


@app.post("/media-library/<asset_id>/delete")
@require_roles(*roles_for_action("media_library", "delete"))
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
@require_roles(*roles_for_action("service_technicians", "view"))
def service_technicians():
    store = load_store()
    if request.method == "POST":
        if not can_module_action("service_technicians", "create"):
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
@require_roles(*roles_for_action("service_technicians", "import"))
def service_technicians_import():
    return handle_bulk_import("service_technicians", "service_technician", import_service_technicians_rows, "service_technicians")


@app.post("/service-technicians/<technician_id>/edit")
@require_roles(*roles_for_action("service_technicians", "edit"))
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
@require_roles(*roles_for_action("service_technicians", "delete"))
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
    visible_orders = visible_orders_for_current_user(store)
    filters = {
        "q": request.args.get("q", "").strip(),
        "status": request.args.get("status", "").strip(),
        "risk": request.args.get("risk", "").strip(),
        "seller": request.args.get("seller", "").strip(),
        "collection": request.args.get("collection", "").strip(),
        "due": request.args.get("due", "").strip(),
    }
    clients_list = [
        enrich_client(client, store.get("orders", []), movements)
        for client in visible_clients
    ]
    if filters["q"]:
        query = filters["q"].lower()
        clients_list = [
            client for client in clients_list
            if query in " ".join(
                [
                    client.get("businessName", ""),
                    client.get("legalName", ""),
                    client.get("commercialName", ""),
                    client.get("taxId", ""),
                    client.get("email", ""),
                    client.get("assignedSellerName", ""),
                    client.get("city", ""),
                    client.get("deliveryZone", ""),
                ]
            ).lower()
        ]
    if filters["status"]:
        clients_list = [
            client for client in clients_list
            if client.get("creditStatus") == filters["status"]
            or client.get("creditRequestStatus") == filters["status"]
        ]
    if filters["risk"]:
        clients_list = [client for client in clients_list if client.get("creditRiskLevel") == filters["risk"]]
    if filters["seller"]:
        clients_list = [client for client in clients_list if client.get("assignedSellerId") == filters["seller"]]
    if filters["collection"]:
        clients_list = [client for client in clients_list if client.get("collectionStatus") == filters["collection"]]
    visible_client_ids = {client.get("id", "") for client in clients_list}
    client_lookup = {client["id"]: client for client in clients_list}
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
        and order.get("customerId", "") in visible_client_ids
    ]
    if filters["due"]:
        due_orders = [order for order in due_orders if order.get("dueStatus") == filters["due"]]
    status_graph = {
        "title": "Estado crediticio",
        "items": [
            {"label": label, "value": sum(1 for client in clients_list if client.get("creditStatus") == status or client.get("creditRequestStatus") == status)}
            for status, label in CREDIT_REQUEST_STATUS_OPTIONS
            if sum(1 for client in clients_list if client.get("creditStatus") == status or client.get("creditRequestStatus") == status)
        ],
    }
    risk_graph = {
        "title": "Riesgo comercial",
        "items": [
            {"label": label, "value": sum(1 for client in clients_list if client.get("creditRiskLevel") == risk)}
            for risk, label in CREDIT_RISK_OPTIONS
            if sum(1 for client in clients_list if client.get("creditRiskLevel") == risk)
        ],
    }
    status_graph["max"] = max([item["value"] for item in status_graph["items"]] or [1])
    risk_graph["max"] = max([item["value"] for item in risk_graph["items"]] or [1])
    metrics = {
        "limit": sum(float(client.get("creditLimitUsd") or 0) for client in clients_list if client.get("creditEnabled")),
        "exposure": sum(float(client.get("creditExposureUsd") or 0) for client in clients_list),
        "available": sum(float(client.get("creditAvailableUsd") or 0) for client in clients_list),
        "current_debt": sum(float(client.get("currentDebtUsd") or 0) for client in clients_list),
        "payments": sum(float(payment.get("amountUsd") or 0) for payment in payments),
        "overdue": sum(float(order.get("balanceUsd") or 0) for order in due_orders if order.get("dueStatus") == "overdue"),
        "requested": sum(float(client.get("creditRequestedUsd") or 0) for client in clients_list if client.get("creditRequestStatus") in {"pending", "review"}),
        "open_orders": len(due_orders),
        "average_score": round(sum(int(client.get("creditScore") or 0) for client in clients_list) / len(clients_list), 1) if clients_list else 0,
    }
    return {
        "clients": sorted(clients_list, key=lambda item: item.get("businessName", "")),
        "payments": sorted(payments, key=lambda item: item.get("createdAt", ""), reverse=True),
        "due_orders": sorted(due_orders, key=lambda item: item.get("dueDate", "")),
        "metrics": metrics,
        "filters": filters,
        "status_graph": status_graph,
        "risk_graph": risk_graph,
        "sellers": sales_users(store),
        "credit_status_options": CREDIT_REQUEST_STATUS_OPTIONS,
        "credit_decision_options": CREDIT_DECISION_OPTIONS,
        "credit_risk_options": CREDIT_RISK_OPTIONS,
        "collection_status_options": COLLECTION_STATUS_OPTIONS,
        "due_status_options": [
            ("overdue", "Vencido"),
            ("due_soon", "Por vencer"),
            ("current", "Al dia"),
            ("without_due_date", "Sin fecha"),
        ],
    }


@app.get("/credit")
@require_roles(*roles_for_action("credit", "view"))
def credit():
    store = load_store()
    context = credit_dashboard_context(store)
    return render_template(
        "credit.html",
        clients=context["clients"],
        metrics=context["metrics"],
        filters=context["filters"],
        status_graph=context["status_graph"],
        risk_graph=context["risk_graph"],
        sellers=context["sellers"],
        credit_status_options=context["credit_status_options"],
        credit_decision_options=context["credit_decision_options"],
        credit_risk_options=context["credit_risk_options"],
        collection_status_options=context["collection_status_options"],
        payment_terms=PAYMENT_TERM_OPTIONS,
        can_approve_credit=role_allowed(CREDIT_APPROVAL_ROLES),
        can_export_credit=can_module_action("credit", "export"),
        error=session.pop("credit_error", ""),
    )


@app.get("/credit/vencimientos")
@require_roles(*roles_for_action("credit", "view"))
def credit_due():
    store = load_store()
    context = credit_dashboard_context(store)
    return render_template(
        "credit_due.html",
        due_orders=context["due_orders"],
        metrics=context["metrics"],
        filters=context["filters"],
        due_status_options=context["due_status_options"],
        can_export_credit=can_module_action("credit", "export"),
    )


@app.get("/credit/historial")
@require_roles(*roles_for_action("credit", "view"))
def credit_history():
    store = load_store()
    context = credit_dashboard_context(store)
    return render_template(
        "credit_history.html",
        payments=context["payments"],
        metrics=context["metrics"],
        filters=context["filters"],
        can_export_credit=can_module_action("credit", "export"),
    )


@app.get("/credit/export")
@require_roles(*roles_for_action("credit", "export"))
def credit_export():
    store = load_store()
    context = credit_dashboard_context(store)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "cliente",
            "rif",
            "email",
            "vendedor",
            "estado_credito",
            "riesgo",
            "score",
            "solicitado_usd",
            "limite_usd",
            "deuda_vigente_usd",
            "deuda_vencida_usd",
            "ordenes_abiertas_usd",
            "disponible_usd",
            "dias_credito",
            "promedio_pago_dias",
            "ultimo_pago_usd",
            "ultimo_pago_fecha",
            "observacion_gerencia",
        ],
        lineterminator="\n",
    )
    writer.writeheader()
    for client in context["clients"]:
        writer.writerow(
            {
                "cliente": client.get("businessName", ""),
                "rif": client.get("taxId", ""),
                "email": client.get("email", ""),
                "vendedor": client.get("assignedSellerName", ""),
                "estado_credito": client.get("creditStatusLabel", ""),
                "riesgo": client.get("creditRiskLabel", ""),
                "score": client.get("creditScore", 0),
                "solicitado_usd": client.get("creditRequestedUsd", 0),
                "limite_usd": client.get("creditLimitUsd", 0),
                "deuda_vigente_usd": client.get("currentDebtUsd", 0),
                "deuda_vencida_usd": client.get("overdueBalanceUsd", 0),
                "ordenes_abiertas_usd": client.get("creditOrdersUsd", 0),
                "disponible_usd": client.get("creditAvailableUsd", 0),
                "dias_credito": client.get("paymentTermsDays", 0),
                "promedio_pago_dias": client.get("averagePaymentDays", 0),
                "ultimo_pago_usd": client.get("lastPaymentUsd", 0),
                "ultimo_pago_fecha": client.get("lastPaymentAt", ""),
                "observacion_gerencia": client.get("creditManagerNote", ""),
            }
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=credito_b2b_wulkan.csv"},
    )


@app.get("/credit/vencimientos/export")
@require_roles(*roles_for_action("credit", "export"))
def credit_due_export():
    store = load_store()
    context = credit_dashboard_context(store)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["vence", "orden", "cliente", "vendedor", "condicion", "saldo_usd", "dias", "estado"],
        lineterminator="\n",
    )
    writer.writeheader()
    for order in context["due_orders"]:
        writer.writerow(
            {
                "vence": order.get("dueDate", ""),
                "orden": order.get("orderId", ""),
                "cliente": order.get("customerName", ""),
                "vendedor": order.get("sellerName", ""),
                "condicion": order.get("saleTypeLabel", ""),
                "saldo_usd": order.get("balanceUsd", 0),
                "dias": order.get("dueDays", 0),
                "estado": order.get("dueStatus", ""),
            }
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=vencimientos_credito_wulkan.csv"},
    )


@app.get("/credit/historial/export")
@require_roles(*roles_for_action("credit", "export"))
def credit_history_export():
    store = load_store()
    context = credit_dashboard_context(store)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["fecha", "orden", "cliente", "metodo", "referencia", "monto_usd", "monto_ves", "usuario", "nota"],
        lineterminator="\n",
    )
    writer.writeheader()
    for payment in context["payments"]:
        writer.writerow(
            {
                "fecha": payment.get("createdAt", ""),
                "orden": payment.get("orderId", ""),
                "cliente": payment.get("clientName", ""),
                "metodo": payment.get("method", ""),
                "referencia": payment.get("reference", ""),
                "monto_usd": payment.get("amountUsd", 0),
                "monto_ves": payment.get("amountVes", 0),
                "usuario": payment.get("createdBy", ""),
                "nota": payment.get("note", ""),
            }
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=historial_credito_wulkan.csv"},
    )


@app.post("/credit/<client_id>/decision")
@require_roles(*roles_for_action("credit", "approve"))
def credit_decision(client_id: str):
    store = load_store()
    client = find_by_id(store.get("clients", []), client_id)
    if not client:
        return redirect(url_for("credit"))

    before = copy.deepcopy(client)
    decision = request.form.get("decision", "review")
    if decision not in {value for value, _label in CREDIT_DECISION_OPTIONS}:
        decision = "review"
    note = request.form.get("creditManagerNote", "").strip()
    if decision in {"rejected", "suspended", "blocked_debt", "blocked_limit"} and not note:
        session["credit_error"] = "Las decisiones de rechazo, suspension o bloqueo requieren observacion de gerencia."
        return redirect(url_for("credit"))

    now = utc_now()
    credit_limit = safe_float(request.form.get("creditLimitUsd"), safe_float(client.get("creditLimitUsd"), 0))
    if credit_limit <= 0 and decision in {"approved", "reactivate"}:
        credit_limit = safe_float(client.get("creditRequestedUsd"), 0)
    payment_terms = safe_int(request.form.get("paymentTermsDays"), safe_int(client.get("paymentTermsDays"), 0))
    if payment_terms not in PAYMENT_TERM_OPTIONS:
        payment_terms = 0
    requested = safe_float(request.form.get("creditRequestedUsd"), safe_float(client.get("creditRequestedUsd"), 0))
    score = max(0, min(100, safe_int(request.form.get("creditScore"), safe_int(client.get("creditScore"), 0))))
    risk = request.form.get("creditRiskLevel", client.get("creditRiskLevel", "low"))
    if risk not in dict(CREDIT_RISK_OPTIONS):
        risk = "low"

    client["creditRequestedUsd"] = requested
    client["creditRiskLevel"] = risk
    client["creditScore"] = score
    client["creditManagerNote"] = note or client.get("creditManagerNote", "")
    client["creditReviewedBy"] = session.get("admin_name", "Admin")
    client["creditReviewedAt"] = now

    if decision in {"approved", "reactivate", "adjust"}:
        client["creditEnabled"] = credit_limit > 0
        client["creditLimitUsd"] = max(0.0, credit_limit)
        client["paymentTermsDays"] = payment_terms
        client["creditRequestStatus"] = "approved" if credit_limit > 0 else "review"
        if credit_limit > 0:
            client["creditApprovedBy"] = session.get("admin_name", "Admin")
            client["creditApprovedAt"] = now
        allowed_terms = set(int(term) for term in client.get("allowedPaymentTermsDays", [0]) if str(term).isdigit())
        allowed_terms.add(payment_terms)
        client["allowedPaymentTermsDays"] = sorted(allowed_terms)
        if client.get("status") in {"blocked_debt", "blocked_credit", "suspended", "review"}:
            client["status"] = "active"
        if client.get("collectionStatus") == "blocked":
            client["collectionStatus"] = "current"
        detail = f"Credito {credit_status_label(client['creditRequestStatus']).lower()} por {money_usd(client['creditLimitUsd'])} a {payment_terms} dias."
    elif decision == "review":
        client["creditEnabled"] = False
        client["creditRequestStatus"] = "review"
        client["creditLimitUsd"] = max(0.0, credit_limit)
        client["paymentTermsDays"] = payment_terms
        detail = "Credito marcado en evaluacion comercial."
    elif decision == "rejected":
        client["creditEnabled"] = False
        client["creditLimitUsd"] = 0.0
        client["paymentTermsDays"] = 0
        client["creditRequestStatus"] = "rejected"
        detail = "Solicitud de credito rechazada."
    elif decision == "suspended":
        client["creditEnabled"] = False
        client["creditRequestStatus"] = "suspended"
        client["creditLimitUsd"] = max(0.0, credit_limit)
        client["paymentTermsDays"] = payment_terms
        detail = "Credito suspendido por gerencia comercial."
    elif decision == "blocked_debt":
        client["creditEnabled"] = False
        client["creditRequestStatus"] = "blocked_debt"
        client["collectionStatus"] = "blocked"
        client["status"] = "blocked_debt"
        client["creditLimitUsd"] = max(0.0, credit_limit)
        detail = "Credito bloqueado por mora."
    else:
        client["creditEnabled"] = False
        client["creditRequestStatus"] = "blocked_limit"
        client["status"] = "blocked_credit"
        client["creditLimitUsd"] = max(0.0, credit_limit)
        client["paymentTermsDays"] = payment_terms
        detail = "Credito bloqueado por exceso de cupo."

    if decision not in {"approved", "reactivate", "adjust"}:
        client["creditEnabled"] = False

    client["updatedAt"] = now
    record_change_event(
        store,
        "credit_decision",
        "client",
        client_id,
        f"{detail} {note}".strip(),
        before,
        client,
    )
    save_store(store)
    return redirect(url_for("credit"))


def audit_event_matches_filters(event: dict, filters: dict[str, str]) -> bool:
    if filters["action"] and event.get("action", "") != filters["action"]:
        return False
    if filters["entity_type"] and event.get("entityType", "") != filters["entity_type"]:
        return False
    actor_haystack = f"{event.get('actorName', '')} {event.get('actorRole', '')}".lower()
    if filters["actor"] and filters["actor"].lower() not in actor_haystack:
        return False
    query = filters["q"].lower()
    if query:
        searchable = " ".join(
            str(event.get(key, ""))
            for key in (
                "action",
                "entityType",
                "entityId",
                "actorName",
                "actorRole",
                "detail",
                "path",
                "method",
            )
        ).lower()
        if query not in searchable:
            return False
    return True


@app.get("/audit")
@require_roles(*roles_for_action("audit", "view"))
def audit():
    store = load_store()
    all_events = sorted(store.get("audit_events", []), key=lambda item: item.get("createdAt", ""), reverse=True)
    filters = {
        "q": request.args.get("q", "").strip(),
        "action": request.args.get("action", "").strip(),
        "entity_type": request.args.get("entity_type", "").strip(),
        "actor": request.args.get("actor", "").strip(),
    }
    filtered_events = [
        event for event in all_events
        if audit_event_matches_filters(event, filters)
    ]
    events = filtered_events[:1000]
    write_actions = {
        "create",
        "update",
        "delete",
        "payment",
        "update_status",
        "credit_decision",
        "commission_update",
        "collection_update",
        "password_change",
        "bulk_import",
    }
    metrics = {
        "total": len(all_events),
        "filtered": len(filtered_events),
        "actors": len({event.get("actorId") or event.get("actorName") for event in filtered_events}),
        "writes": sum(1 for event in filtered_events if event.get("action") in write_actions),
    }
    graphify_summary = f"{metrics['writes']} cambios / {metrics['actors']} actores"
    return render_template(
        "audit.html",
        events=events,
        metrics=metrics,
        graphify_summary=graphify_summary,
        filters=filters,
        action_options=sorted({event.get("action", "") for event in all_events if event.get("action")}),
        entity_options=sorted({event.get("entityType", "") for event in all_events if event.get("entityType")}),
        actor_options=sorted({event.get("actorName", "") for event in all_events if event.get("actorName")}),
    )


@app.get("/orders")
@require_roles(*roles_for_action("orders", "view"))
def orders():
    store = load_store()
    return render_template("orders.html", **orders_page_context(store))


@app.get("/orders/export")
@require_roles(*roles_for_action("orders", "export"))
def orders_export():
    store = load_store()
    context = orders_page_context(store)
    output = io.StringIO()
    fieldnames = [
        "orden",
        "fecha",
        "cliente",
        "vendedor",
        "canal",
        "tipo_venta",
        "plazo_dias",
        "estado",
        "estado_credito",
        "estado_inventario",
        "estado_pago",
        "estado_despacho",
        "total_usd",
        "abonado_usd",
        "saldo_usd",
        "vence",
        "items",
        "direccion_despacho",
        "comision_usd",
        "estado_comision",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for order in context["orders"]:
        writer.writerow(
            {
                "orden": order.get("orderId", ""),
                "fecha": order.get("createdAt", ""),
                "cliente": order.get("customerName", ""),
                "vendedor": order.get("sellerName", ""),
                "canal": order.get("salesChannelLabel", ""),
                "tipo_venta": order.get("saleTypeLabel", ""),
                "plazo_dias": order.get("paymentTermDays", 0),
                "estado": order.get("statusLabel", ""),
                "estado_credito": order.get("creditStatusLabel", ""),
                "estado_inventario": order.get("stockStatus", ""),
                "estado_pago": order.get("paymentStatusLabel", ""),
                "estado_despacho": order.get("dispatchStatusLabel", ""),
                "total_usd": order.get("totalUsd", 0),
                "abonado_usd": order.get("paidUsd", 0),
                "saldo_usd": order.get("balanceUsd", 0),
                "vence": order.get("dueDate", ""),
                "items": "|".join(
                    f"{item.get('sku', '')}:{item.get('quantity', 0)}"
                    for item in order.get("items") or []
                ),
                "direccion_despacho": order.get("shippingAddress", ""),
                "comision_usd": order.get("commissionUsd", 0),
                "estado_comision": order.get("commissionStatusLabel", ""),
            }
        )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=ordenes_wulkan.csv"},
    )


@app.route("/orders/new", methods=["GET", "POST"])
@require_roles(*roles_for_action("orders", "create"))
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
@require_roles(*ORDER_MANAGEMENT_ROLES)
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
    if target_status in {"cancelled", "rejected"} and not note:
        return render_template(
            "orders.html",
            **orders_page_context(store, "Motivo obligatorio para rechazar o anular una orden."),
        ), 400

    sale_type = order.get("saleType", "cash")
    if target_status in ORDER_CREDIT_RESERVING_STATUSES and sale_type == "credit_line":
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
    elif target_status in ORDER_CREDIT_RESERVING_STATUSES:
        order["creditStatus"] = "approved" if sale_type == "term_credit" else "without_credit"

    if target_status in {"cancelled", "rejected"}:
        release_stock_for_order(store, order)
    elif target_status != "credit_review" and not apply_inventory_transition(store, order, target_status):
        target_status = "credit_review"
        if sale_type == "credit_line":
            order["creditStatus"] = "manual_review"
        note = note or "Stock insuficiente para reservar o entregar esta orden."

    if target_status in {"cancelled", "rejected"}:
        order["creditStatus"] = "cancelled"
        order["commissionStatus"] = "commission_cancelled"
        order["dispatchStatus"] = "cancelled"
    elif target_status == "paid" and balance > 0:
        target_status = "partial_paid"
        note = note or "La orden tiene saldo pendiente; registra el abono para cerrarla como pagada."
    elif target_status in {"delivered", "paid"} and float(order.get("commissionUsd") or 0) > 0:
        order["commissionStatus"] = "commission_approved"
    if target_status == "preparing":
        order["dispatchStatus"] = "preparing"
        order["currentOwner"] = "Inventario"
    elif target_status == "delivered":
        order["dispatchStatus"] = "delivered"
        order["currentOwner"] = "Cobranza" if balance > 0 else "Comercial"
    elif target_status in {"paid", "cancelled", "rejected"}:
        order["currentOwner"] = "Cierre"

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
@require_roles("super_admin", "general_manager", "commercial_manager", "operator", "collections")
def order_payment_create(order_id: str):
    store = load_store()
    next_url = request.form.get("next") or url_for("orders")
    order = find_order(store["orders"], order_id)
    if not order or not can_access_order_record(order, store):
        return redirect(next_url)

    before = copy.deepcopy(order)
    movements = store.setdefault("credit_movements", [])
    balance_before = order_balance_usd(order, movements)
    amount_usd = min(float(request.form.get("amountUsd") or 0), balance_before)
    if amount_usd <= 0:
        return redirect(next_url)

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
    order["collectionStatus"] = "closed" if balance_after <= 0 else "partial_paid"
    order["lastCollectionActionAt"] = utc_now()
    order["collectionOwner"] = "Cobranza" if balance_after > 0 else "Cierre"
    order["status"] = "paid" if balance_after <= 0 else "partial_paid"
    if balance_after <= 0:
        order["creditStatus"] = "without_credit" if order.get("saleType") == "cash" else "released"
    else:
        order["creditStatus"] = order.get("creditStatus", "approved")
    if balance_after <= 0 and float(order.get("commissionUsd") or 0) > 0:
        order["commissionStatus"] = "commission_approved"
    apply_inventory_transition(store, order, order["status"])
    if balance_after <= 0:
        order["currentOwner"] = "Cierre" if order.get("status") == "delivered" else "Despacho"
    else:
        order["currentOwner"] = "Cobranza"
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
    return redirect(next_url)


def collections_page_context(store: dict) -> dict:
    movements = store.get("credit_movements", [])
    filters = {
        "q": request.args.get("q", "").strip(),
        "status": request.args.get("status", "").strip(),
        "seller": request.args.get("seller", "").strip(),
        "view": request.args.get("view", "open").strip() or "open",
    }
    client_lookup = {
        client.get("id", ""): enrich_client(client, store.get("orders", []), movements)
        for client in visible_clients_for_current_user(store)
    }
    orders = [
        enrich_order(order, movements)
        for order in visible_orders_for_current_user(store)
        if order.get("customerId", "") in client_lookup
        and order.get("status") not in {"cancelled", "rejected"}
        and order.get("saleType") in {"term_credit", "credit_line", "cash"}
    ]
    if filters["view"] == "open":
        orders = [order for order in orders if float(order.get("balanceUsd") or 0) > 0]
    elif filters["view"] == "paid":
        orders = [order for order in orders if float(order.get("balanceUsd") or 0) <= 0]
    elif filters["view"] == "overdue":
        orders = [order for order in orders if order.get("collectionStatus") in {"overdue", "critical"}]
    elif filters["view"] == "promise":
        orders = [order for order in orders if order.get("collectionStatus") == "promise"]
    if filters["q"]:
        query = filters["q"].lower()
        orders = [
            order for order in orders
            if query in " ".join(
                [
                    order.get("orderId", ""),
                    order.get("customerName", ""),
                    order.get("sellerName", ""),
                    order.get("collectionComment", ""),
                ]
            ).lower()
        ]
    if filters["status"]:
        orders = [order for order in orders if order.get("collectionStatus") == filters["status"]]
    if filters["seller"]:
        orders = [order for order in orders if order.get("sellerId") == filters["seller"]]
    metrics = {
        "receivable": round(sum(float(order.get("balanceUsd") or 0) for order in orders), 2),
        "due_soon": round(sum(float(order.get("balanceUsd") or 0) for order in orders if order.get("collectionStatus") == "due_soon"), 2),
        "overdue": round(sum(float(order.get("balanceUsd") or 0) for order in orders if order.get("collectionStatus") == "overdue"), 2),
        "critical": round(sum(float(order.get("balanceUsd") or 0) for order in orders if order.get("collectionStatus") == "critical"), 2),
        "promises": sum(1 for order in orders if order.get("collectionStatus") == "promise"),
        "payments": round(sum(float(payment.get("amountUsd") or 0) for payment in movements if payment.get("movementType") == "payment"), 2),
    }
    status_graph = {
        "title": "Cobranza por estado",
        "items": [
            {"label": label, "value": sum(1 for order in orders if order.get("collectionStatus") == status)}
            for status, label in ORDER_COLLECTION_STATUS_OPTIONS
            if sum(1 for order in orders if order.get("collectionStatus") == status)
        ],
    }
    status_graph["max"] = max([item["value"] for item in status_graph["items"]] or [1])
    return {
        "orders": sorted(orders, key=lambda item: (item.get("dueDate", ""), item.get("createdAt", ""))),
        "clients": sorted(client_lookup.values(), key=lambda item: item.get("businessName", "")),
        "metrics": metrics,
        "filters": filters,
        "status_graph": status_graph,
        "sellers": sales_users(store),
        "collection_status_options": ORDER_COLLECTION_STATUS_OPTIONS,
        "payment_methods": PAYMENT_METHOD_OPTIONS,
        "can_edit_collections": can_module_action("collections", "edit"),
        "can_export_collections": can_module_action("collections", "export"),
    }


@app.get("/collections")
@require_roles(*roles_for_action("collections", "view"))
def collections():
    store = load_store()
    return render_template("collections.html", **collections_page_context(store))


@app.get("/collections/export")
@require_roles(*roles_for_action("collections", "export"))
def collections_export():
    store = load_store()
    context = collections_page_context(store)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "orden",
            "cliente",
            "vendedor",
            "total_usd",
            "abonado_usd",
            "saldo_usd",
            "fecha_emision",
            "fecha_vencimiento",
            "dias_atraso",
            "estado_cobranza",
            "responsable",
            "ultima_gestion",
            "proxima_gestion",
            "promesa_pago",
            "comentario",
        ],
        lineterminator="\n",
    )
    writer.writeheader()
    for order in context["orders"]:
        writer.writerow(
            {
                "orden": order.get("orderId", ""),
                "cliente": order.get("customerName", ""),
                "vendedor": order.get("sellerName", ""),
                "total_usd": order.get("totalUsd", 0),
                "abonado_usd": order.get("paidUsd", 0),
                "saldo_usd": order.get("balanceUsd", 0),
                "fecha_emision": order.get("createdAt", ""),
                "fecha_vencimiento": order.get("dueDate", ""),
                "dias_atraso": order.get("dueDays", 0) if order.get("dueStatus") == "overdue" else 0,
                "estado_cobranza": order.get("collectionStatusLabel", ""),
                "responsable": order.get("collectionOwner", ""),
                "ultima_gestion": order.get("lastCollectionActionAt", ""),
                "proxima_gestion": order.get("nextCollectionActionAt", ""),
                "promesa_pago": order.get("paymentPromiseAt", ""),
                "comentario": order.get("collectionComment", ""),
            }
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=cobranza_wulkan.csv"},
    )


@app.get("/collections/client/<client_id>/statement.csv")
@require_roles(*roles_for_action("collections", "export"))
def collection_statement(client_id: str):
    store = load_store()
    client = find_by_id(store.get("clients", []), client_id)
    if not client:
        return redirect(url_for("collections"))
    movements = store.get("credit_movements", [])
    orders = [
        enrich_order(order, movements)
        for order in store.get("orders", [])
        if order.get("customerId") == client_id and order.get("status") not in {"cancelled", "rejected"}
    ]
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["fecha", "tipo", "documento", "debe_usd", "haber_usd", "saldo_usd", "detalle"],
        lineterminator="\n",
    )
    writer.writeheader()
    running_balance = 0.0
    for order in sorted(orders, key=lambda item: item.get("createdAt", "")):
        running_balance += float(order.get("totalUsd") or 0)
        writer.writerow(
            {
                "fecha": order.get("createdAt", ""),
                "tipo": "orden",
                "documento": order.get("orderId", ""),
                "debe_usd": order.get("totalUsd", 0),
                "haber_usd": 0,
                "saldo_usd": round(running_balance, 2),
                "detalle": order.get("saleTypeLabel", ""),
            }
        )
        for payment in sorted(order.get("payments") or [], key=lambda item: item.get("createdAt", "")):
            running_balance -= float(payment.get("amountUsd") or 0)
            writer.writerow(
                {
                    "fecha": payment.get("createdAt", ""),
                    "tipo": "abono",
                    "documento": payment.get("orderId", ""),
                    "debe_usd": 0,
                    "haber_usd": payment.get("amountUsd", 0),
                    "saldo_usd": round(running_balance, 2),
                    "detalle": payment.get("reference") or payment.get("method", ""),
                }
            )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=estado_cuenta_{client_id}.csv"},
    )


@app.post("/collections/<order_id>/action")
@require_roles(*roles_for_action("collections", "edit"))
def collection_action(order_id: str):
    store = load_store()
    order = find_order(store.get("orders", []), order_id)
    if not order or not can_access_order_record(order, store):
        return redirect(url_for("collections"))
    client = find_by_id(store.get("clients", []), order.get("customerId", ""))
    before = copy.deepcopy({"order": order, "client": client})
    action = request.form.get("action", "in_management")
    note = request.form.get("collectionComment", "").strip()
    owner = request.form.get("collectionOwner", "").strip() or session.get("admin_name", "Cobranza")
    now = utc_now()
    order["collectionOwner"] = owner
    order["collectionComment"] = note or order.get("collectionComment", "")
    order["nextCollectionActionAt"] = request.form.get("nextCollectionActionAt", "").strip()
    order["paymentPromiseAt"] = request.form.get("paymentPromiseAt", "").strip()
    order["lastCollectionActionAt"] = now
    if action in dict(ORDER_COLLECTION_STATUS_OPTIONS):
        order["collectionStatus"] = action
    if action == "promise":
        order["collectionStatus"] = "promise"
        if not order["paymentPromiseAt"]:
            order["paymentPromiseAt"] = order["nextCollectionActionAt"]
    elif action == "block_client" and client:
        order["collectionStatus"] = "critical"
        client["status"] = "blocked_debt"
        client["collectionStatus"] = "blocked"
        client["creditRequestStatus"] = "blocked_debt"
        client["creditEnabled"] = False
        client["updatedAt"] = now
    elif action == "release_client" and client:
        client["status"] = "active"
        client["collectionStatus"] = "current" if order_balance_usd(order, store.get("credit_movements", [])) > 0 else "without_debt"
        if client.get("creditLimitUsd", 0) > 0 and client.get("creditRequestStatus") == "blocked_debt":
            client["creditRequestStatus"] = "approved"
            client["creditEnabled"] = True
        client["updatedAt"] = now
    elif action == "close" and order_balance_usd(order, store.get("credit_movements", [])) <= 0:
        order["collectionStatus"] = "closed"
        order["currentOwner"] = "Cierre"
    order["currentOwner"] = "Cobranza" if order_balance_usd(order, store.get("credit_movements", [])) > 0 else order.get("currentOwner", "Cierre")
    order["updatedAt"] = now
    append_order_history(order, order.get("status", "partial_paid"), f"Cobranza: {collection_status_label(order.get('collectionStatus', ''))}. {note}".strip())
    record_change_event(
        store,
        "collection_update",
        "order",
        order_id,
        f"Cobranza actualizada: {collection_status_label(order.get('collectionStatus', ''))}.",
        before,
        {"order": order, "client": client},
    )
    save_store(store)
    return redirect(url_for("collections"))


@app.get("/commissions")
@require_roles(*roles_for_action("commissions", "view"))
def commissions():
    store = load_store()
    return render_template("commissions.html", **commissions_page_context(store))


@app.post("/commissions/<order_id>/status")
@require_roles(*roles_for_action("commissions", "approve"))
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
@require_roles(*roles_for_action("announcements", "view"))
def announcements():
    store = load_store()
    if request.method == "POST":
        if not can_module_action("announcements", "create"):
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
@require_roles(*roles_for_action("announcements", "import"))
def announcements_import():
    return handle_bulk_import("announcements", "announcement", import_announcements_rows, "announcements")


@app.post("/announcements/<announcement_id>/edit")
@require_roles(*roles_for_action("announcements", "edit"))
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
@require_roles(*roles_for_action("announcements", "delete"))
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
    seller_snapshot = enrich_seller(store, user)
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
                "sellerCode": user.get("sellerCode", ""),
                "sellerZone": user.get("sellerZone", ""),
                "sellerTerritory": user.get("sellerTerritory", ""),
                "commissionRatePercent": safe_float(user.get("commissionRatePercent"), 0),
                "salesGoalUsd": seller_snapshot.get("salesGoalUsd", 0.0),
                "salesMonthUsd": seller_snapshot.get("salesMonthUsd", 0.0),
                "goalProgressPercent": seller_snapshot.get("goalProgressPercent", 0.0),
                "ticketAverageUsd": seller_snapshot.get("ticketAverageUsd", 0.0),
                "activeClientsCount": seller_snapshot.get("activeClientsCount", 0),
                "newClientsMonth": seller_snapshot.get("newClientsMonth", 0),
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
            "legalName": str(payload.get("legalName") or business_name).strip(),
            "commercialName": str(payload.get("commercialName") or business_name).strip(),
            "businessName": business_name,
            "taxId": str(payload.get("taxId") or "").strip(),
            "contactName": str(payload.get("contactName") or "").strip(),
            "administrativeContact": str(payload.get("administrativeContact") or "").strip(),
            "receivingContact": str(payload.get("receivingContact") or "").strip(),
            "phone": str(payload.get("phone") or "").strip(),
            "whatsapp": str(payload.get("whatsapp") or payload.get("phone") or "").strip(),
            "email": email,
            "clientType": "ferretero",
            "clientCategory": str(payload.get("clientCategory") or "standard"),
            "priceList": str(payload.get("priceList") or "b2b"),
            "authorizedDiscountPercent": float(payload.get("authorizedDiscountPercent") or 0),
            "status": "active",
            "onboardingStatus": "pending_review",
            "address": str(payload.get("address") or "").strip(),
            "fiscalAddress": str(payload.get("fiscalAddress") or payload.get("address") or "").strip(),
            "shippingAddress": str(payload.get("shippingAddress") or payload.get("address") or "").strip(),
            "country": str(payload.get("country") or "VE").strip(),
            "state": str(payload.get("state") or "").strip(),
            "city": str(payload.get("city") or "").strip(),
            "deliveryZone": str(payload.get("deliveryZone") or "").strip(),
            "assignedSellerId": seller_id,
            "assignedSellerName": seller_name,
            "defaultSaleType": str(payload.get("defaultSaleType") or "cash"),
            "allowedPaymentTermsDays": terms,
            "collectionStatus": "without_debt",
            "creditRiskLevel": "low",
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
                "collectionStatus": enriched.get("collectionStatus", "without_debt"),
                "collectionStatusLabel": enriched.get("collectionStatusLabel", ""),
                "creditRiskLevel": enriched.get("creditRiskLevel", "low"),
                "openBalanceUsd": enriched.get("openBalanceUsd", 0.0),
                "overdueBalanceUsd": enriched.get("overdueBalanceUsd", 0.0),
                "lastPurchaseAt": enriched.get("lastPurchaseAt", ""),
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
        {
            "id": category.get("id", ""),
            "name": category.get("name", ""),
            "slug": category.get("slug", ""),
            "description": category.get("description", ""),
            "imageUrl": category.get("imageUrl", ""),
            "icon": category.get("icon", "bi-tags"),
            "sortOrder": category.get("sortOrder", 0),
            "parentId": category.get("parentId", ""),
            "productsCount": category.get("productsCount", 0),
        }
        for category in sorted(
            [enrich_category(item, store) for item in store["categories"] if item.get("status", "active") == "active"],
            key=lambda item: (safe_int(item.get("sortOrder"), 0), item.get("name", "")),
        )
        if category.get("visibleInApp")
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
            and user.get("mobileAccessEnabled", True) is not False
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
        if (
            not subject
            or subject.get("status") != "active"
            or subject.get("role") not in MOBILE_SALES_ROLES
            or subject.get("mobileAccessEnabled", True) is False
        ):
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
            "internalCode": product.get("internalCode", ""),
            "name": product["title"],
            "title": product["title"],
            "description": product.get("description", ""),
            "shortDescription": product.get("shortDescription", ""),
            "longDescription": product.get("longDescription", ""),
            "brand": product.get("brand", "Wulkan"),
            "model": product.get("model", ""),
            "unitOfSale": product.get("unitOfSale", "unidad"),
            "productType": product.get("productType", "machine"),
            "categoryId": product.get("categoryId", ""),
            "verticalName": product.get("categoryName", ""),
            "categoryName": product.get("categoryName", ""),
            "subCategory": product.get("subCategory", ""),
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
            "relatedSkus": product.get("relatedSkus", []),
            "featured": bool(product.get("featured")),
            "onSale": bool(product.get("onSale") or product.get("hasDiscount")),
            "visibleInApp": bool(product.get("visibleInApp")),
        }
        for product in [enrich_inventory_product(item, store.get("orders", [])) for item in store["products"]]
        if product.get("status") == "active" and product.get("visibleInApp")
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
