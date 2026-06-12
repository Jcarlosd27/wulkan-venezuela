from __future__ import annotations

import hashlib
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

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_file, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from markupsafe import Markup
from werkzeug.exceptions import BadRequest, HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from config import get_config
from graphify import rotation_chart, stock_health
from storage import generate_s3_signed_url, key_from_public_url, save_uploaded_file, stream_size
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
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy-Report-Only",
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "font-src 'self' https://cdn.jsdelivr.net data:; "
        "img-src 'self' data: https: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'",
    )
    if response.mimetype == "text/html" and (session.get("admin_authenticated") or request.endpoint == "login"):
        response.headers.setdefault("Cache-Control", "no-store, max-age=0")
        response.headers.setdefault("Pragma", "no-cache")
    if app.config.get("ENV") == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.errorhandler(HTTPException)
def handle_api_http_exception(exc: HTTPException):
    if not request.path.startswith("/api/"):
        return exc
    app.logger.warning("API HTTP error %s on %s", exc.code, request.path)
    code = str(exc.name or "http_error").lower().replace(" ", "_")
    return jsonify({"meta": mobile_api_meta(), "error": exc.description, "code": code}), exc.code


@app.errorhandler(Exception)
def handle_api_unexpected_exception(exc: Exception):
    if not request.path.startswith("/api/"):
        raise exc
    app.logger.exception("Unexpected API error on %s", request.path)
    return jsonify({"meta": mobile_api_meta(), "error": "Error interno del servidor.", "code": "internal_server_error"}), 500

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
CLIENT_SALE_BLOCKING_STATUSES = {"inactive", "blocked_debt", "blocked_credit", "blocked_manual", "suspended"}
CLIENT_CREDIT_BLOCKING_STATUSES = {"suspended", "blocked_debt", "blocked_limit"}
CLIENT_COLLECTION_BLOCKING_STATUSES = {"blocked", "critical", "uncollectible"}
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
    "prepared": "Preparado",
    "ready": "Listo para despacho",
    "in_route": "En ruta",
    "dispatched": "Despachado",
    "delivered": "Entregado",
    "failed": "Entrega fallida",
    "rescheduled": "Reprogramado",
    "returned": "Devuelto",
    "closed": "Cerrado",
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
QUOTE_STATUS_OPTIONS = [
    ("draft", "Borrador"),
    ("sent", "Enviada"),
    ("viewed", "Vista"),
    ("negotiation", "En negociacion"),
    ("accepted", "Aceptada"),
    ("rejected", "Rechazada"),
    ("expired", "Vencida"),
    ("converted", "Convertida en orden"),
]
CRM_RECORD_TYPE_OPTIONS = [
    ("lead", "Lead"),
    ("prospect", "Prospecto"),
    ("opportunity", "Oportunidad"),
    ("follow_up", "Seguimiento"),
    ("task", "Tarea"),
    ("visit", "Visita"),
]
CRM_PIPELINE_STAGE_OPTIONS = [
    ("new_lead", "Nuevo lead"),
    ("contacted", "Contactado"),
    ("qualified", "Calificado"),
    ("interested", "Interesado"),
    ("quote_sent", "Cotizacion enviada"),
    ("negotiation", "Negociacion"),
    ("won", "Ganado"),
    ("lost", "Perdido"),
    ("inactive", "Inactivo"),
]
CRM_ACTIVITY_TYPE_OPTIONS = [
    ("call", "Llamada"),
    ("whatsapp", "WhatsApp"),
    ("email", "Correo"),
    ("visit", "Visita"),
    ("meeting", "Reunion"),
    ("follow_up", "Seguimiento"),
    ("task", "Tarea interna"),
    ("note", "Nota comercial"),
]
CRM_STATUS_OPTIONS = [
    ("active", "Activo"),
    ("pending", "Pendiente"),
    ("won", "Ganado"),
    ("lost", "Perdido"),
    ("inactive", "Inactivo"),
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
COMMISSION_STATUS_OPTIONS = [
    ("commission_pending", "Pendiente"),
    ("commission_review", "En revision"),
    ("commission_approved", "Aprobada"),
    ("commission_paid", "Pagada"),
    ("commission_withheld", "Retenida"),
    ("commission_cancelled", "Anulada"),
]
COMMISSION_RULE_OPTIONS = [
    ("sale_generated", "Venta generada"),
    ("sale_paid", "Venta pagada"),
    ("sale_delivered", "Venta entregada"),
    ("new_client", "Cliente nuevo"),
    ("manager_override", "Regla especial"),
]
REPORT_TYPE_OPTIONS = [
    ("commercial", "Comercial"),
    ("finance", "Financiero"),
    ("inventory", "Inventario"),
    ("sellers", "Vendedores"),
]
DOCUMENT_SCOPE_OPTIONS = [
    ("client", "Cliente"),
    ("product", "Producto"),
    ("order", "Orden"),
    ("admin", "Administrativo"),
]
DOCUMENT_TYPE_OPTIONS = [
    ("rif", "RIF / documento fiscal"),
    ("contract", "Contrato"),
    ("credit", "Documento de credito"),
    ("account_statement", "Estado de cuenta"),
    ("technical_sheet", "Ficha tecnica"),
    ("manual", "Manual"),
    ("warranty", "Garantia"),
    ("certificate", "Certificado"),
    ("quote", "Cotizacion"),
    ("payment_proof", "Comprobante"),
    ("dispatch_guide", "Guia de despacho"),
    ("delivery_evidence", "Evidencia de entrega"),
    ("invoice", "Factura manual"),
    ("administrative", "Administrativo"),
]
DOCUMENT_STATUS_OPTIONS = [
    ("active", "Activo"),
    ("pending_review", "Pendiente revision"),
    ("expired", "Vencido"),
    ("archived", "Archivado"),
]
DOCUMENT_VISIBILITY_OPTIONS = [
    ("internal", "Solo admin"),
    ("seller", "Visible vendedor"),
    ("client", "Visible cliente"),
    ("public", "Publico"),
]
AUDIT_WRITE_ACTIONS = {
    "create",
    "update",
    "delete",
    "payment",
    "update_status",
    "credit_decision",
    "commission_update",
    "collection_update",
    "dispatch_update",
    "quote_convert",
    "crm_activity",
    "password_change",
    "bulk_import",
}
AUDIT_SECURITY_ACTIONS = {
    "login",
    "logout",
    "login_failed",
    "login_limited",
    "login_blocked",
    "password_reset",
    "session_revoke",
}
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
    ("crm", "CRM Comercial", "bi-kanban", "Leads, oportunidades, tareas, visitas y seguimiento."),
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
    ("notifications", "Notificaciones", "bi-bell", "Alertas internas y moviles por evento comercial."),
    ("business_rules", "Reglas negocio", "bi-shield-exclamation", "Validaciones criticas de ventas, credito, stock y auditoria."),
    ("maintenance", "Mantenimiento", "bi-speedometer2", "Salud tecnica, version, backups, migraciones y readiness."),
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
        "crm": set(ACTION_WORK | {"approve", "reject"}),
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
        "notifications": set(ACTION_READ | {"edit"}),
        "business_rules": set(ACTION_AUDIT),
        "maintenance": set(ACTION_AUDIT),
        "import_templates": set(ACTION_READ),
        "audit": set(ACTION_AUDIT),
        "documents": set(ACTION_READ),
    },
    "operator": {
        "dashboard": set(ACTION_READ),
        "sellers": set(ACTION_WORK),
        "clients": set(ACTION_WORK),
        "crm": set(ACTION_WORK),
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
        "notifications": set(ACTION_READ | {"edit"}),
        "business_rules": set(ACTION_READ),
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
        "notifications": set(ACTION_READ | {"edit"}),
        "business_rules": set(ACTION_READ),
        "import_templates": set(ACTION_READ),
        "documents": set(ACTION_WORK),
    },
    "collections": {
        "dashboard": set(ACTION_READ),
        "clients": set(ACTION_READ),
        "crm": set(ACTION_READ | {"edit"}),
        "credit": set(ACTION_READ | {"edit"}),
        "orders": set(ACTION_READ | {"edit"}),
        "collections": {"view", "create", "edit", "export", "audit"},
        "reports": set(ACTION_READ),
        "notifications": set(ACTION_READ | {"edit"}),
        "business_rules": set(ACTION_READ),
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
        "notifications": set(ACTION_READ | {"edit"}),
        "business_rules": set(ACTION_READ),
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
            "crm",
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
            "notifications",
            "business_rules",
            "maintenance",
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
            {"module": "crm", "endpoint": "crm", "label": "CRM Comercial", "icon": "bi-kanban", "active": ["crm", "crm_export", "crm_update", "crm_activity_create", "crm_delete"]},
            {"module": "credit", "endpoint": "credit", "label": "Credito B2B", "icon": "bi-credit-card-2-front", "active": ["credit", "credit_decision", "credit_due", "credit_history"]},
            {"module": "collections", "endpoint": "collections", "label": "Cobranza", "icon": "bi-cash-coin", "active": ["collections", "collections_export", "collection_action", "collection_statement"]},
            {"module": "orders", "endpoint": "orders", "label": "Ordenes", "icon": "bi-receipt", "active": ["orders", "orders_export", "order_new", "order_status_update", "order_payment_create"]},
            {"module": "dispatch", "endpoint": "dispatch", "label": "Despacho", "icon": "bi-truck", "active": ["dispatch", "dispatch_export", "dispatch_update"]},
            {"module": "quotes", "endpoint": "quotes", "label": "Cotizaciones", "icon": "bi-file-earmark-text", "active": ["quotes", "quote_new", "quote_edit", "quote_status_update", "quote_duplicate", "quote_convert", "quote_download", "quotes_export"]},
            {"module": "commissions", "endpoint": "commissions", "label": "Comisiones", "icon": "bi-percent", "active": ["commissions", "commission_status_update", "commissions_export"]},
            {"module": "reports", "endpoint": "reports", "label": "Reportes", "icon": "bi-file-bar-graph", "active": ["reports", "reports_export", "reports_print"]},
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
            {"module": "documents", "endpoint": "documents", "label": "Documentos", "icon": "bi-folder2", "active": ["documents", "documents_import", "documents_export", "document_delete"]},
            {"module": "notifications", "endpoint": "notifications", "label": "Notificaciones", "icon": "bi-bell", "active": ["notifications", "notification_read", "notifications_read_all"]},
            {"module": "business_rules", "endpoint": "business_rules", "label": "Reglas negocio", "icon": "bi-shield-exclamation", "active": ["business_rules"]},
            {"module": "maintenance", "endpoint": "maintenance", "label": "Mantenimiento", "icon": "bi-speedometer2", "active": ["maintenance", "maintenance_export"]},
            {"module": "audit", "endpoint": "audit", "label": "Auditoria", "icon": "bi-shield-check", "active": ["audit", "audit_export"]},
            {"module": "settings", "endpoint": "settings", "label": "Configuracion", "icon": "bi-gear", "active": ["settings"]},
            {"module": "permissions", "endpoint": "permissions", "label": "Roles y permisos", "icon": "bi-shield-lock", "active": ["permissions"]},
            {"module": "admin_users", "endpoint": "admin_users", "label": "Usuarios admin", "icon": "bi-people", "active": ["admin_users", "admin_user_edit", "admin_user_delete", "admin_user_status", "admin_user_reset_password", "admin_user_revoke_sessions"]},
        ],
    },
]
ENDPOINT_MODULE_MAP = {
    item["endpoint"]: item["module"]
    for group in ADMIN_MENU_GROUPS
    for item in group["items"]
}
for group in ADMIN_MENU_GROUPS:
    for item in group["items"]:
        for endpoint_name in item["active"]:
            ENDPOINT_MODULE_MAP.setdefault(endpoint_name, item["module"])
ENDPOINT_MODULE_MAP["dashboard"] = "dashboard"
ENDPOINT_MODULE_MAP.update({
    "credit_export": "credit",
    "credit_due_export": "credit",
    "credit_history_export": "credit",
    "import_issues_export": "import_templates",
    "admin_search": "dashboard",
    "document_open": "documents",
    "document_private_file": "documents",
})

MODULE_NAV_INDEX = {
    item["module"]: item
    for group in ADMIN_MENU_GROUPS
    for item in group["items"]
}

ENDPOINT_UI_LABELS = {
    "dashboard": "Dashboard",
    "admin_search": "Busqueda",
    "product_new": "Crear producto",
    "product_edit": "Editar producto",
    "products_import": "Importar productos",
    "products_export": "Exportar productos",
    "category_edit": "Editar categoria",
    "categories_import": "Importar categorias",
    "categories_export": "Exportar categorias",
    "seller_edit": "Editar vendedor",
    "sellers_import": "Importar vendedores",
    "client_edit": "Editar cliente",
    "clients_import": "Importar clientes",
    "credit_due": "Vencimientos",
    "credit_history": "Historial credito",
    "order_new": "Nueva orden",
    "orders_export": "Exportar ordenes",
    "quote_new": "Nueva cotizacion",
    "quote_edit": "Editar cotizacion",
    "documents_import": "Importar documentos",
    "document_open": "Abrir documento",
    "notifications": "Notificaciones",
    "business_rules": "Reglas negocio",
    "maintenance": "Mantenimiento",
    "maintenance_export": "Exportar mantenimiento",
    "audit_export": "Exportar auditoria",
}

ENDPOINT_ACTION_OVERRIDES = {
    "dashboard": "view",
    "admin_search": "view",
    "download_import_template": "export",
    "import_issues_export": "export",
    "admin_users": {"GET": "view", "POST": "create"},
    "admin_user_edit": "edit",
    "admin_user_delete": "delete",
    "admin_user_status": "edit",
    "admin_user_reset_password": "edit",
    "admin_user_revoke_sessions": "annul",
    "sellers": {"GET": "view", "POST": "create"},
    "sellers_import": "import",
    "seller_edit": "edit",
    "seller_delete": "delete",
    "clients": {"GET": "view", "POST": "create"},
    "clients_import": "import",
    "client_edit": "edit",
    "client_status_update": "edit",
    "client_delete": "delete",
    "crm": {"GET": "view", "POST": "create"},
    "crm_export": "export",
    "crm_update": "edit",
    "crm_activity_create": "create",
    "crm_delete": "delete",
    "credit": "view",
    "credit_due": "view",
    "credit_history": "view",
    "credit_export": "export",
    "credit_due_export": "export",
    "credit_history_export": "export",
    "credit_decision": "approve",
    "collections": "view",
    "collections_export": "export",
    "collection_statement": "export",
    "collection_action": "edit",
    "orders": "view",
    "orders_export": "export",
    "order_new": "create",
    "order_status_update": "edit",
    "order_payment_create": "edit",
    "dispatch": "view",
    "dispatch_export": "export",
    "dispatch_update": "edit",
    "quotes": "view",
    "quotes_export": "export",
    "quote_new": "create",
    "quote_edit": "edit",
    "quote_status_update": "approve",
    "quote_duplicate": "create",
    "quote_convert": "create",
    "quote_download": "export",
    "commissions": "view",
    "commissions_export": "export",
    "commission_status_update": "approve",
    "reports": "view",
    "reports_export": "export",
    "reports_print": "export",
    "products": "view",
    "products_export": "export",
    "products_import": "import",
    "product_new": "create",
    "product_edit": "edit",
    "product_duplicate": "create",
    "product_delete": "delete",
    "categories": {"GET": "view", "POST": "create"},
    "categories_export": "export",
    "categories_import": "import",
    "category_edit": "edit",
    "category_status": "edit",
    "category_delete": "delete",
    "media_library": {"GET": "view", "POST": "create"},
    "media_library_import": "import",
    "media_asset_delete": "delete",
    "stock": {"GET": "view", "POST": "create"},
    "stock_export": "export",
    "stock_import": "import",
    "announcements": {"GET": "view", "POST": "create"},
    "announcements_import": "import",
    "announcement_edit": "edit",
    "announcement_delete": "delete",
    "service_technicians": {"GET": "view", "POST": "create"},
    "service_technicians_import": "import",
    "service_technician_edit": "edit",
    "service_technician_delete": "delete",
    "import_templates": "view",
    "documents": {"GET": "view", "POST": "create"},
    "documents_import": "import",
    "documents_export": "export",
    "document_open": "view",
    "document_private_file": "view",
    "document_delete": "delete",
    "notifications": "view",
    "notification_read": "edit",
    "notifications_read_all": "edit",
    "business_rules": "view",
    "maintenance": "view",
    "maintenance_export": "export",
    "audit": "view",
    "audit_export": "export",
    "settings": {"GET": "view", "POST": "edit"},
    "permissions": "view",
}

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
            {
                "key": "documentos",
                "module": "documents",
                "endpoint": "documents",
                "title": "Documentos",
                "description": "Contratos, RIF, garantias, evidencias y documentos por cliente, producto u orden.",
                "columns": [
                    {"name": "titulo", "required": True, "example": "RIF Ferreteria Principal", "help": "Nombre interno del documento."},
                    {"name": "tipo_documento", "required": True, "example": "rif", "help": "rif, contract, credit, account_statement, technical_sheet, manual, warranty, certificate, quote, payment_proof, dispatch_guide, delivery_evidence, invoice o administrative."},
                    {"name": "ambito", "required": True, "example": "cliente", "help": "cliente, producto, orden o administrativo."},
                    {"name": "referencia", "required": False, "example": "compras@ferreteriaprincipal.com", "help": "Email/RIF/nombre cliente, SKU producto u orden segun ambito."},
                    {"name": "url", "required": True, "example": "https://cdn.wulkan/documentos/rif.pdf", "help": "URL publica o privada del archivo."},
                    {"name": "visibilidad", "required": False, "example": "internal", "help": "internal, seller, client o public."},
                    {"name": "vence", "required": False, "example": "2027-06-10", "help": "Fecha de vencimiento si aplica."},
                    {"name": "estado", "required": False, "example": "active", "help": "active, pending_review, expired o archived."},
                    {"name": "nota", "required": False, "example": "Documento validado por administracion.", "help": "Observacion interna."},
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
    user["lastLoginIp"] = request_ip_address()
    if user["failedLoginAttempts"] >= int(app.config.get("LOGIN_MAX_ATTEMPTS", 5)):
        user["status"] = "blocked"
        bump_user_session_version(user)
    else:
        user["updatedAt"] = utc_now()


def reset_admin_user_failed_attempts(user: dict) -> None:
    user["failedLoginAttempts"] = 0
    user["lastFailedLoginAt"] = ""
    user["lastLoginIp"] = request_ip_address()
    user["updatedAt"] = utc_now()


def temporary_admin_password() -> str:
    return f"Wulkan{secrets.randbelow(900000) + 100000}"


def request_ip_address() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()


def request_user_agent() -> str:
    return request.headers.get("User-Agent", "").strip()[:280]


def request_device_hash() -> str:
    raw_value = f"{request_user_agent()}|{request.headers.get('Accept-Language', '').strip()[:80]}"
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()[:32]


def admin_session_record(session_id: str) -> dict:
    now = int(time.time())
    return {
        "id": session_id,
        "createdAt": utc_now(),
        "createdEpoch": now,
        "lastSeenAt": utc_now(),
        "lastSeenEpoch": now,
        "ipAddress": request_ip_address(),
        "userAgent": request_user_agent(),
        "deviceHash": request_device_hash(),
        "revokedAt": "",
    }


def start_admin_session(admin_user: dict) -> None:
    session_id = secrets.token_urlsafe(24)
    now = int(time.time())
    session["admin_authenticated"] = True
    session["admin_user_id"] = admin_user["id"]
    session["admin_name"] = admin_user.get("name", "Admin Wulkan")
    session["admin_role"] = admin_user.get("role", "operator")
    session["must_change_password"] = bool(admin_user.get("mustChangePassword"))
    session["admin_session_version"] = user_session_version(admin_user)
    session["admin_session_id"] = session_id
    session["admin_login_at"] = now
    session["admin_last_seen_at"] = now
    session["admin_device_hash"] = request_device_hash()
    session["admin_ip_address"] = request_ip_address()

    active_sessions = [
        item for item in admin_user.get("activeSessions", [])
        if not item.get("revokedAt")
    ]
    active_sessions.append(admin_session_record(session_id))
    admin_user["activeSessions"] = active_sessions[-8:]


def validate_admin_session(admin_user: dict) -> tuple[str, bool]:
    now = int(time.time())
    login_at = safe_int(session.get("admin_login_at"), now)
    last_seen_at = safe_int(session.get("admin_last_seen_at"), now)
    idle_limit = int(app.config.get("ADMIN_SESSION_IDLE_SECONDS", 3600))
    absolute_limit = int(app.config.get("ADMIN_SESSION_ABSOLUTE_SECONDS", 28800))

    if idle_limit and now - last_seen_at > idle_limit:
        return "Sesion expirada por inactividad.", False
    if absolute_limit and now - login_at > absolute_limit:
        return "Sesion expirada por tiempo maximo.", False
    if session.get("admin_device_hash") and session.get("admin_device_hash") != request_device_hash():
        return "Sesion cerrada por cambio de dispositivo.", False

    session_id = session.get("admin_session_id", "")
    active_session = None
    if session_id:
        active_session = next(
            (item for item in admin_user.get("activeSessions", []) if item.get("id") == session_id),
            None,
        )
        if active_session and active_session.get("revokedAt"):
            return "Sesion cerrada remotamente.", False
        if admin_user.get("activeSessions") and not active_session:
            return "Sesion no reconocida.", False

    session["admin_last_seen_at"] = now
    if active_session and now - safe_int(active_session.get("lastSeenEpoch"), 0) >= 300:
        active_session["lastSeenAt"] = utc_now()
        active_session["lastSeenEpoch"] = now
        active_session["ipAddress"] = request_ip_address()
        return "", True
    return "", False


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
    return dict(COMMISSION_STATUS_OPTIONS).get(value, value or "Sin definir")


def commission_rule_label(value: str) -> str:
    return dict(COMMISSION_RULE_OPTIONS).get(value, value or "Regla general")


def report_type_label(value: str) -> str:
    return dict(REPORT_TYPE_OPTIONS).get(value, "Comercial")


def document_scope_label(value: str) -> str:
    return dict(DOCUMENT_SCOPE_OPTIONS).get(value, value or "Sin ambito")


def document_type_label(value: str) -> str:
    return dict(DOCUMENT_TYPE_OPTIONS).get(value, value or "Documento")


def document_status_label(value: str) -> str:
    return dict(DOCUMENT_STATUS_OPTIONS).get(value, value or "Sin estado")


def document_visibility_label(value: str) -> str:
    return dict(DOCUMENT_VISIBILITY_OPTIONS).get(value, value or "Interno")


def quote_status_label(value: str) -> str:
    return dict(QUOTE_STATUS_OPTIONS).get(value, value or "Sin estado")


def crm_record_type_label(value: str) -> str:
    return dict(CRM_RECORD_TYPE_OPTIONS).get(value, value or "Sin tipo")


def crm_stage_label(value: str) -> str:
    return dict(CRM_PIPELINE_STAGE_OPTIONS).get(value, value or "Sin etapa")


def crm_activity_type_label(value: str) -> str:
    return dict(CRM_ACTIVITY_TYPE_OPTIONS).get(value, value or "Actividad")


def crm_status_label(value: str) -> str:
    return dict(CRM_STATUS_OPTIONS).get(value, value or "Sin estado")


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
    seller_rate = safe_float((seller or {}).get("commissionRatePercent"), 0)
    return seller_rate if seller_rate > 0 else safe_float(business_settings(store).get("defaultCommissionPercent"), 0)


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


def visible_quotes_for_current_user(store: dict) -> list[dict]:
    quotes = store.get("quotes", [])
    if current_admin_role() != "sales":
        return quotes
    seller_id = session.get("admin_user_id", "")
    assigned_client_ids = {
        client.get("id", "")
        for client in store.get("clients", [])
        if client.get("assignedSellerId") == seller_id
    }
    return [
        quote
        for quote in quotes
        if quote.get("sellerId") == seller_id or quote.get("clientId") in assigned_client_ids
    ]


def can_access_quote_record(quote: dict | None, store: dict) -> bool:
    if not quote:
        return False
    if current_admin_role() != "sales":
        return True
    seller_id = session.get("admin_user_id", "")
    if quote.get("sellerId") == seller_id:
        return True
    client = find_by_id(store.get("clients", []), quote.get("clientId", ""))
    return bool(client and client.get("assignedSellerId") == seller_id)


def visible_crm_records_for_current_user(store: dict) -> list[dict]:
    records = store.get("crm_records", [])
    if current_admin_role() != "sales":
        return records
    seller_id = session.get("admin_user_id", "")
    assigned_client_ids = {
        client.get("id", "")
        for client in store.get("clients", [])
        if client.get("assignedSellerId") == seller_id
    }
    return [
        record
        for record in records
        if record.get("sellerId") == seller_id or record.get("clientId") in assigned_client_ids
    ]


def can_access_crm_record(record: dict | None, store: dict) -> bool:
    if not record:
        return False
    if current_admin_role() != "sales":
        return True
    seller_id = session.get("admin_user_id", "")
    if record.get("sellerId") == seller_id:
        return True
    client = find_by_id(store.get("clients", []), record.get("clientId", ""))
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


def endpoint_permission(endpoint: str, method: str) -> tuple[str, str] | None:
    module = ENDPOINT_MODULE_MAP.get(endpoint)
    if not module:
        return None
    override = ENDPOINT_ACTION_OVERRIDES.get(endpoint, "view")
    if isinstance(override, dict):
        action = override.get(method, override.get("*", "view"))
    else:
        action = override
    return module, action


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


def admin_breadcrumbs() -> list[dict]:
    endpoint = request.endpoint or ""
    if not endpoint or endpoint == "dashboard":
        return []
    module = ENDPOINT_MODULE_MAP.get(endpoint, "")
    crumbs = [{"label": "Dashboard", "url": url_for("dashboard")}]
    if endpoint == "admin_search":
        crumbs.append({"label": "Busqueda", "url": ""})
        return crumbs

    item = MODULE_NAV_INDEX.get(module)
    if item and can_access_module(module):
        module_label = item["label"]
        module_endpoint = item["endpoint"]
        if endpoint != module_endpoint:
            crumbs.append({"label": module_label, "url": url_for(module_endpoint)})
        else:
            crumbs.append({"label": module_label, "url": ""})

    current_label = ENDPOINT_UI_LABELS.get(endpoint)
    if current_label and (not crumbs or crumbs[-1]["label"] != current_label):
        crumbs.append({"label": current_label, "url": ""})
    return crumbs


def push_admin_toast(message: str, level: str = "success", title: str = "Listo") -> None:
    toasts = session.setdefault("admin_toasts", [])
    toasts.append({"message": message, "level": level, "title": title})
    session["admin_toasts"] = toasts[-4:]
    session.modified = True


def consume_admin_toasts() -> list[dict]:
    return session.pop("admin_toasts", [])


def normalize_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", normalized).strip().lower()


def searchable_text(*values) -> str:
    return normalize_search_text(" ".join(str(value or "") for value in values))


def append_search_result(groups: dict[str, dict], group_key: str, item: dict) -> None:
    groups.setdefault(
        group_key,
        {
            "key": group_key,
            "label": item.pop("group_label"),
            "icon": item.pop("group_icon"),
            "items": [],
        },
    )
    if len(groups[group_key]["items"]) < 8:
        groups[group_key]["items"].append(item)


def admin_search_result_groups(store: dict, query: str) -> list[dict]:
    normalized_query = normalize_search_text(query)
    if not normalized_query:
        return []

    groups: dict[str, dict] = {}
    orders = store.get("orders", [])
    movements = store.get("credit_movements", [])
    tokens = normalized_query.split()

    def matches(*values) -> bool:
        blob = searchable_text(*values)
        return all(token in blob for token in tokens)

    if can_access_module("products"):
        for product in [enrich_inventory_product(item, orders, store.get("stock_movements", [])) for item in store.get("products", [])]:
            if matches(product.get("sku"), product.get("title"), product.get("categoryName"), product.get("brand"), product.get("model"), product.get("description")):
                href = url_for("product_edit", product_id=product["id"]) if can_module_action("products", "edit") else url_for("products", q=product.get("sku", ""))
                append_search_result(groups, "products", {
                    "group_label": "Productos",
                    "group_icon": "bi-box-seam",
                    "title": product.get("title") or product.get("sku"),
                    "subtitle": f"{product.get('sku', '')} - {product.get('categoryName') or 'Sin categoria'}",
                    "meta": f"{product.get('availableStock', 0)} disp. / {money_usd(product.get('publicPriceUsd', 0))}",
                    "badge": product.get("statusLabel", product.get("status", "")),
                    "href": href,
                    "icon": "bi-box-seam",
                })

    if can_access_module("clients"):
        for client in [enrich_client(item, orders, movements) for item in visible_clients_for_current_user(store) if item.get("status") != "deleted"]:
            if matches(client.get("businessName"), client.get("legalName"), client.get("rif"), client.get("email"), client.get("phone"), client.get("assignedSellerName")):
                append_search_result(groups, "clients", {
                    "group_label": "Clientes",
                    "group_icon": "bi-shop",
                    "title": client.get("businessName") or client.get("email"),
                    "subtitle": f"{client.get('rif') or 'Sin RIF'} - {client.get('assignedSellerName') or 'Sin vendedor'}",
                    "meta": f"Credito {money_usd(client.get('creditAvailableUsd', 0))}",
                    "badge": client.get("statusLabel", client.get("status", "")),
                    "href": url_for("clients", q=client.get("businessName", "")),
                    "icon": "bi-shop",
                })

    if can_access_module("sellers"):
        for seller in [enrich_seller(store, item) for item in store.get("admin_users", []) if item.get("role") == "sales" and item.get("status") != "deleted"]:
            if matches(seller.get("name"), seller.get("email"), seller.get("sellerCode"), seller.get("sellerZone"), seller.get("phone")):
                append_search_result(groups, "sellers", {
                    "group_label": "Vendedores",
                    "group_icon": "bi-person-badge",
                    "title": seller.get("name") or seller.get("email"),
                    "subtitle": f"{seller.get('sellerCode') or 'Sin codigo'} - {seller.get('sellerZone') or 'Sin zona'}",
                    "meta": f"Cartera {seller.get('clientsCount', 0)} clientes",
                    "badge": seller_status_label(seller.get("status", "")),
                    "href": url_for("sellers", q=seller.get("name", "")),
                    "icon": "bi-person-badge",
                })

    if can_access_module("orders"):
        for order in [enrich_order(item, movements) for item in visible_orders_for_current_user(store)]:
            if matches(order.get("orderId"), order.get("customerName"), order.get("sellerName"), order.get("saleTypeLabel"), order.get("statusLabel")):
                append_search_result(groups, "orders", {
                    "group_label": "Ordenes",
                    "group_icon": "bi-receipt",
                    "title": order.get("orderId") or order.get("id"),
                    "subtitle": f"{order.get('customerName')} - {order.get('sellerName')}",
                    "meta": f"{money_usd(order.get('totalUsd', 0))} / saldo {money_usd(order.get('balanceUsd', 0))}",
                    "badge": order.get("statusLabel", order.get("status", "")),
                    "href": url_for("orders", q=order.get("orderId", "")),
                    "icon": "bi-receipt",
                })

    if can_access_module("quotes"):
        for quote in visible_quotes_for_current_user(store):
            if matches(quote.get("quoteId"), quote.get("clientName"), quote.get("sellerName"), quote.get("status"), quote.get("title")):
                href = url_for("quote_edit", quote_id=quote["id"]) if can_module_action("quotes", "edit") else url_for("quotes", q=quote.get("quoteId", ""))
                append_search_result(groups, "quotes", {
                    "group_label": "Cotizaciones",
                    "group_icon": "bi-file-earmark-text",
                    "title": quote.get("quoteId") or quote.get("title") or quote.get("id"),
                    "subtitle": f"{quote.get('clientName') or 'Sin cliente'} - {quote.get('sellerName') or 'Sin vendedor'}",
                    "meta": money_usd(quote.get("totalUsd", 0)),
                    "badge": quote_status_label(quote.get("status", "")),
                    "href": href,
                    "icon": "bi-file-earmark-text",
                })

    if can_access_module("categories"):
        for category in store.get("categories", []):
            if category.get("status") == "deleted":
                continue
            if matches(category.get("name"), category.get("description"), category.get("slug"), category.get("status")):
                append_search_result(groups, "categories", {
                    "group_label": "Categorias",
                    "group_icon": "bi-tags",
                    "title": category.get("name") or category.get("slug"),
                    "subtitle": category.get("description") or "Familia de catalogo",
                    "meta": "Visible app" if category.get("visibleInApp") else "No visible app",
                    "badge": category_status_label(category.get("status", "")),
                    "href": url_for("categories", q=category.get("name", "")),
                    "icon": "bi-tags",
                })

    if can_access_module("documents"):
        for asset in document_assets(store):
            if matches(asset.get("title"), asset.get("subjectLabel"), asset.get("documentType"), asset.get("url")):
                append_search_result(groups, "documents", {
                    "group_label": "Documentos",
                    "group_icon": "bi-folder2",
                    "title": asset.get("title") or "Documento",
                    "subtitle": asset.get("subjectLabel") or document_scope_label(asset.get("subjectType", "")),
                    "meta": document_type_label(asset.get("documentType", "")),
                    "badge": document_status_label(asset.get("effectiveStatus", asset.get("status", ""))),
                    "href": url_for("documents", q=asset.get("title", "")),
                    "icon": "bi-folder2",
                })

    return [group for group in groups.values() if group["items"]]


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
        "admin_breadcrumbs": admin_breadcrumbs,
        "admin_notification_count": admin_notification_count,
        "admin_toasts": consume_admin_toasts,
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
        "commission_rule_label": commission_rule_label,
        "report_type_label": report_type_label,
        "document_scope_label": document_scope_label,
        "document_type_label": document_type_label,
        "document_status_label": document_status_label,
        "document_visibility_label": document_visibility_label,
        "quote_status_label": quote_status_label,
        "crm_record_type_label": crm_record_type_label,
        "crm_stage_label": crm_stage_label,
        "crm_activity_type_label": crm_activity_type_label,
        "crm_status_label": crm_status_label,
        "sales_channel_label": sales_channel_label,
        "dispatch_status_label": dispatch_status_label,
        "due_status_label": due_status_label,
        "notification_type_label": notification_type_label,
        "notification_priority_label": notification_priority_label,
        "notification_status_label": notification_status_label,
    }


@app.before_request
def protect_admin_csrf():
    if request.method != "POST":
        return None
    if request.path.startswith(("/api/mobile/", "/api/v1/mobile/")):
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
    public_prefixes = ("/api/mobile/", "/api/v1/mobile/", "/static/")
    public_endpoints = {"login", "privacy_policy", "healthz", "readyz"}

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

    session_error, session_store_changed = validate_admin_session(admin_user)
    if session_error:
        record_audit_event(
            store,
            "session_revoke",
            "admin_user",
            admin_user["id"],
            session_error,
            actor={"id": admin_user["id"], "name": admin_user.get("name", ""), "role": admin_user.get("role", "")},
            metadata={"sessionId": session.get("admin_session_id", ""), "deviceHash": session.get("admin_device_hash", "")},
        )
        save_store(store)
        session.clear()
        return redirect(url_for("login", next=request.path))
    if session_store_changed:
        save_store(store)

    session["admin_name"] = admin_user.get("name", "Admin Wulkan")
    session["admin_role"] = admin_user.get("role", "operator")
    session["must_change_password"] = bool(admin_user.get("mustChangePassword"))

    if admin_user.get("role") == "sales":
        session.clear()
        return redirect(url_for("login", mobile_only="1"))

    allowed_password_endpoints = {"account_password", "logout"}
    if session.get("must_change_password") and request.endpoint not in allowed_password_endpoints:
        return redirect(url_for("account_password"))

    required_permission = endpoint_permission(request.endpoint or "", request.method)
    if required_permission:
        module, action = required_permission
        if not can_module_action(module, action):
            record_audit_event(
                store,
                "unauthorized",
                module,
                request.endpoint or request.path,
                f"Intento no autorizado: {module}.{action}.",
                actor={"id": admin_user["id"], "name": admin_user.get("name", ""), "role": admin_user.get("role", "")},
                metadata={"path": request.path, "method": request.method, "requiredAction": action},
            )
            save_store(store)
            return forbidden_response()

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
            start_admin_session(admin_user)
            admin_user["lastLoginAt"] = utc_now()
            reset_admin_user_failed_attempts(admin_user)
            record_audit_event(
                store,
                "login",
                "admin_user",
                admin_user["id"],
                "Inicio de sesion admin.",
                metadata={
                    "ipAddress": admin_user.get("lastLoginIp", ""),
                    "sessionId": session.get("admin_session_id", ""),
                    "deviceHash": session.get("admin_device_hash", ""),
                },
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
            session_id = session.get("admin_session_id", "")
            for active_session in admin_user.get("activeSessions", []):
                if active_session.get("id") == session_id and not active_session.get("revokedAt"):
                    active_session["revokedAt"] = utc_now()
            record_audit_event(
                store,
                "logout",
                "admin_user",
                admin_user["id"],
                "Cierre de sesion admin.",
                actor={"id": admin_user["id"], "name": admin_user.get("name", ""), "role": admin_user.get("role", "")},
                metadata={"sessionId": session_id},
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


def business_settings(store: dict | None = None) -> dict:
    try:
        active_store = store if store is not None else load_store()
        return dict(active_store.get("business_settings") or {})
    except Exception:
        return {}


def current_rate() -> float:
    return safe_float(business_settings().get("exchangeRateUsdVes"), 38.5)


def payment_term_options(store: dict | None = None) -> list[int]:
    raw_terms = business_settings(store).get("defaultPaymentTermsDays") or PAYMENT_TERM_OPTIONS
    terms = []
    for term in raw_terms:
        value = safe_int(term, -1)
        if value >= 0 and value not in terms:
            terms.append(value)
    return sorted(terms) or list(PAYMENT_TERM_OPTIONS)


@app.get("/healthz")
def healthz():
    return jsonify(
        {
            "status": "ok",
            "service": "wulkan-admin",
            "appVersion": app.config.get("APP_VERSION", "0.9.0"),
            "buildSha": app.config.get("BUILD_SHA", ""),
        }
    )


@app.get("/privacy")
@app.get("/privacidad")
def privacy_policy():
    return render_template("privacy_policy.html")


@app.get("/readyz")
def readyz():
    try:
        store = load_store()
        return jsonify(
            {
                "status": "ready",
                "appVersion": app.config.get("APP_VERSION", "0.9.0"),
                "buildSha": app.config.get("BUILD_SHA", ""),
                "dataBackend": app.config.get("DATA_BACKEND"),
                "storageBackend": app.config.get("STORAGE_BACKEND"),
                "mobileTokenRequired": bool(app.config.get("REQUIRE_MOBILE_TOKEN")),
                "products": len(store.get("products", [])),
                "clients": len(store.get("clients", [])),
                "orders": len(store.get("orders", [])),
                "quotes": len(store.get("quotes", [])),
                "crm": len(store.get("crm_records", [])),
            }
        )
    except Exception as exc:
        return jsonify({"status": "not_ready", "error": str(exc)}), 503


def mobile_token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="wulkan-mobile-client")


def document_token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="wulkan-document-download")


def mobile_device_id() -> str:
    payload = request.get_json(silent=True) if request.method in {"POST", "PUT", "PATCH"} else {}
    payload = payload or {}
    return (
        request.headers.get("X-Wulkan-Device-Id")
        or request.headers.get("X-Device-Id")
        or str(payload.get("deviceId") or "")
        or request_device_hash()
    )[:120]


def issue_mobile_token(client: dict) -> str:
    return mobile_token_serializer().dumps(
        {
            "type": "client",
            "clientId": client["id"],
            "id": client["id"],
            "role": "client",
            "sessionVersion": safe_int(client.get("mobileSessionVersion"), 0),
            "deviceId": mobile_device_id(),
        }
    )


def issue_mobile_admin_token(user: dict) -> str:
    return mobile_token_serializer().dumps(
        {
            "type": "admin",
            "adminUserId": user["id"],
            "id": user["id"],
            "role": user.get("role", ""),
            "sessionVersion": user_session_version(user),
            "deviceId": mobile_device_id(),
        }
    )


def mobile_token_payload() -> dict:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return {}

    token = header.removeprefix("Bearer ").strip()
    if not token:
        return {}

    try:
        payload = mobile_token_serializer().loads(
            token,
            max_age=int(app.config.get("MOBILE_TOKEN_MAX_AGE_SECONDS", 60 * 60 * 24 * 7)),
        )
    except (BadSignature, SignatureExpired):
        return {}

    return payload if isinstance(payload, dict) else {}


def mobile_token_matches_device(payload: dict) -> bool:
    header_device = request.headers.get("X-Wulkan-Device-Id") or request.headers.get("X-Device-Id")
    return not header_device or not payload.get("deviceId") or hmac.compare_digest(str(payload.get("deviceId")), header_device[:120])


def mobile_token_version_valid(subject: dict, payload: dict, version_key: str) -> bool:
    if not mobile_token_matches_device(payload):
        return False
    if "sessionVersion" not in payload:
        return not bool(app.config.get("REJECT_LEGACY_MOBILE_TOKENS"))
    return safe_int(payload.get("sessionVersion"), -1) == safe_int(subject.get(version_key), 0)


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
    payload = mobile_token_payload()
    admin_id = payload.get("adminUserId") or payload.get("id", "") if payload.get("type") == "admin" else ""
    user = find_by_id(store.get("admin_users", []), admin_id)
    if (
        not user
        or user.get("status") != "active"
        or user.get("role") not in MOBILE_SALES_ROLES
        or user.get("mobileAccessEnabled", True) is False
        or not mobile_token_version_valid(user, payload, "sessionVersion")
    ):
        return None, jsonify({"error": "Token de vendedor requerido."})
    return user, None


def require_mobile_client_id() -> tuple[str, object | None]:
    customer_id = mobile_token_client_id() or request.args.get("customerId", "").strip()
    require_token = bool(app.config.get("REQUIRE_MOBILE_TOKEN"))
    if require_token and not mobile_token_client_id():
        return "", jsonify({"error": "Token movil requerido."})
    return customer_id, None


def require_mobile_client(store: dict) -> tuple[dict | None, object | None]:
    payload = mobile_token_payload()
    if not payload:
        if app.config.get("REQUIRE_MOBILE_TOKEN"):
            return None, jsonify({"error": "Token movil requerido."})
        return None, None
    if payload.get("type", "client") != "client":
        return None, jsonify({"error": "Token de cliente requerido."})
    client = find_by_id(store.get("clients", []), payload.get("clientId") or payload.get("id", ""))
    if not client or client.get("status") != "active" or not mobile_token_version_valid(client, payload, "mobileSessionVersion"):
        return None, jsonify({"error": "Token movil invalido."})
    return client, None


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
            and mobile_token_version_valid(user, payload, "sessionVersion")
        ):
            return user, None
        return None, jsonify({"error": "Token movil invalido."})

    client = find_by_id(store.get("clients", []), payload.get("clientId") or payload.get("id", ""))
    if client and client.get("status") == "active" and mobile_token_version_valid(client, payload, "mobileSessionVersion"):
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


def mobile_api_meta() -> dict:
    return {
        "apiVersion": "v1",
        "appVersion": app.config.get("APP_VERSION", "0.9.0"),
        "buildSha": app.config.get("BUILD_SHA", ""),
        "environment": app.config.get("ENV", "development"),
        "legacyPrefix": "/api/mobile",
        "versionedPrefix": "/api/v1/mobile",
        "service": "wulkan-mobile-api",
    }


def mobile_api_response(
    *,
    items: list[dict] | None = None,
    key: str | None = None,
    value=None,
    pagination: dict | None = None,
    filters: dict | None = None,
    sort: str | None = None,
    status: int = 200,
    **extra,
):
    payload: dict = {"meta": mobile_api_meta()}
    if pagination is not None:
        payload["meta"]["pagination"] = pagination
    if filters is not None:
        payload["meta"]["filters"] = filters
    if sort:
        payload["meta"]["sort"] = sort
    if items is not None:
        payload["items"] = items
    if key:
        payload[key] = value
    payload.update(extra)
    return jsonify(payload), status


def mobile_api_error(message: str, status: int = 400, code: str = "bad_request"):
    return jsonify({"meta": mobile_api_meta(), "error": message, "code": code}), status


def api_bool_arg(name: str) -> bool:
    return str(request.args.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def api_list_pagination(items: list[dict], default_limit: int = 0) -> tuple[list[dict], dict]:
    total = len(items)
    requested_limit = safe_int(request.args.get("limit"), default_limit)
    if requested_limit <= 0:
        return items, {
            "total": total,
            "limit": total,
            "offset": 0,
            "page": 1,
            "hasMore": False,
            "nextCursor": None,
        }

    limit = max(1, min(requested_limit, 100))
    if request.args.get("cursor"):
        offset = max(0, safe_int(request.args.get("cursor"), 0))
    else:
        page = max(1, safe_int(request.args.get("page"), 1))
        offset = (page - 1) * limit
    page = (offset // limit) + 1
    end = min(offset + limit, total)
    return items[offset:end], {
        "total": total,
        "limit": limit,
        "offset": offset,
        "page": page,
        "hasMore": end < total,
        "nextCursor": str(end) if end < total else None,
    }


def normalize_search_text(*values) -> str:
    return " ".join(str(value or "") for value in values).lower()


def filter_mobile_products(products: list[dict]) -> tuple[list[dict], dict]:
    filters = {
        "q": request.args.get("q", request.args.get("text", "")).strip().lower(),
        "category": request.args.get("category", request.args.get("categoryId", "")).strip(),
        "vertical": request.args.get("vertical", request.args.get("verticalName", "")).strip().lower(),
        "brand": request.args.get("brand", "").strip().lower(),
        "stockStatus": request.args.get("stockStatus", "").strip(),
        "onlyAvailable": api_bool_arg("onlyAvailable") or api_bool_arg("available"),
        "onlyDiscount": api_bool_arg("onlyDiscount") or api_bool_arg("discount"),
        "onlyNeedsValidation": api_bool_arg("onlyNeedsValidation") or api_bool_arg("validation"),
        "minPriceUsd": request.args.get("minPriceUsd", "").strip(),
        "maxPriceUsd": request.args.get("maxPriceUsd", "").strip(),
    }
    min_price = safe_float(filters["minPriceUsd"], -1)
    max_price = safe_float(filters["maxPriceUsd"], -1)

    def matches(product: dict) -> bool:
        if filters["q"] and filters["q"] not in normalize_search_text(
            product.get("name"),
            product.get("sku"),
            product.get("description"),
            product.get("categoryName"),
            product.get("brand"),
            product.get("model"),
        ):
            return False
        if filters["category"] and filters["category"] not in {
            product.get("categoryId", ""),
            product.get("categoryName", ""),
            product.get("verticalName", ""),
        }:
            return False
        if filters["vertical"] and filters["vertical"] not in normalize_search_text(
            product.get("verticalName"),
            product.get("categoryName"),
            product.get("productType"),
        ):
            return False
        if filters["brand"] and filters["brand"] not in str(product.get("brand", "")).lower():
            return False
        if filters["stockStatus"] and product.get("stockStatus") != filters["stockStatus"]:
            return False
        if filters["onlyAvailable"] and (safe_int(product.get("availableStock"), 0) <= 0 or product.get("requiresQuote")):
            return False
        if filters["onlyDiscount"] and not product.get("onSale"):
            return False
        if filters["onlyNeedsValidation"] and not (product.get("requiresQuote") or product.get("requiresTechnicalValidation")):
            return False
        price = safe_float(product.get("b2bPriceUsd") or product.get("publicPriceUsd"), 0)
        if min_price >= 0 and price < min_price:
            return False
        if max_price >= 0 and price > max_price:
            return False
        return True

    return [product for product in products if matches(product)], filters


def sort_mobile_products(products: list[dict]) -> tuple[list[dict], str]:
    sort = request.args.get("sort", "newest").strip() or "newest"
    sorters = {
        "name_asc": (lambda item: str(item.get("name", "")).lower(), False),
        "price_asc": (lambda item: safe_float(item.get("b2bPriceUsd") or item.get("publicPriceUsd"), 0), False),
        "price_desc": (lambda item: safe_float(item.get("b2bPriceUsd") or item.get("publicPriceUsd"), 0), True),
        "stock_desc": (lambda item: safe_int(item.get("availableStock"), 0), True),
        "discount_desc": (lambda item: safe_float(item.get("discountPercent"), 0), True),
        "newest": (lambda item: str(item.get("createdAt", item.get("id", ""))), True),
    }
    key, reverse = sorters.get(sort, sorters["newest"])
    return sorted(products, key=key, reverse=reverse), sort if sort in sorters else "newest"


def filter_mobile_orders(orders: list[dict]) -> tuple[list[dict], dict]:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "status": request.args.get("status", "").strip(),
        "saleType": request.args.get("saleType", "").strip(),
        "paymentStatus": request.args.get("paymentStatus", "").strip(),
        "stockStatus": request.args.get("stockStatus", "").strip(),
        "due": request.args.get("due", "").strip(),
    }

    def matches(order: dict) -> bool:
        if filters["q"] and filters["q"] not in normalize_search_text(
            order.get("orderId"),
            order.get("id"),
            order.get("customerName"),
            order.get("sellerName"),
            order.get("saleTypeLabel"),
        ):
            return False
        for key in ("status", "saleType", "paymentStatus", "stockStatus"):
            if filters[key] and order.get(key) != filters[key]:
                return False
        if filters["due"] and order.get("dueStatus") != filters["due"]:
            return False
        return True

    return [order for order in orders if matches(order)], filters


def sort_mobile_orders(orders: list[dict]) -> tuple[list[dict], str]:
    sort = request.args.get("sort", "created_desc").strip() or "created_desc"
    sorters = {
        "created_desc": (lambda item: str(item.get("createdAt", "")), True),
        "created_asc": (lambda item: str(item.get("createdAt", "")), False),
        "total_desc": (lambda item: safe_float(item.get("totalUsd"), 0), True),
        "balance_desc": (lambda item: safe_float(item.get("balanceUsd"), 0), True),
        "due_asc": (lambda item: str(item.get("dueDate") or "9999-12-31"), False),
    }
    key, reverse = sorters.get(sort, sorters["created_desc"])
    return sorted(orders, key=key, reverse=reverse), sort if sort in sorters else "created_desc"


def filter_mobile_clients(clients: list[dict]) -> tuple[list[dict], dict]:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "status": request.args.get("status", "").strip(),
        "creditStatus": request.args.get("creditStatus", "").strip(),
        "creditRequestStatus": request.args.get("creditRequestStatus", "").strip(),
        "zone": request.args.get("zone", "").strip().lower(),
    }

    def matches(client: dict) -> bool:
        if filters["q"] and filters["q"] not in normalize_search_text(
            client.get("businessName"),
            client.get("email"),
            client.get("phone"),
            client.get("taxId"),
            client.get("city"),
            client.get("state"),
        ):
            return False
        if filters["status"] and client.get("status") != filters["status"]:
            return False
        if filters["creditStatus"] and client.get("creditStatus") != filters["creditStatus"]:
            return False
        if filters["creditRequestStatus"] and client.get("creditRequestStatus") != filters["creditRequestStatus"]:
            return False
        if filters["zone"] and filters["zone"] not in normalize_search_text(client.get("deliveryZone"), client.get("city"), client.get("state")):
            return False
        return True

    return [client for client in clients if matches(client)], filters


def sort_mobile_clients(clients: list[dict]) -> tuple[list[dict], str]:
    sort = request.args.get("sort", "name_asc").strip() or "name_asc"
    sorters = {
        "name_asc": (lambda item: str(item.get("businessName", "")).lower(), False),
        "credit_desc": (lambda item: safe_float(item.get("creditLimitUsd"), 0), True),
        "available_desc": (lambda item: safe_float(item.get("creditAvailableUsd"), 0), True),
        "recent": (lambda item: str(item.get("updatedAt", item.get("id", ""))), True),
    }
    key, reverse = sorters.get(sort, sorters["name_asc"])
    return sorted(clients, key=key, reverse=reverse), sort if sort in sorters else "name_asc"


def filter_mobile_categories(categories: list[dict]) -> tuple[list[dict], dict]:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "parentId": request.args.get("parentId", "").strip(),
    }

    def matches(category: dict) -> bool:
        if filters["q"] and filters["q"] not in normalize_search_text(
            category.get("name"),
            category.get("slug"),
            category.get("description"),
        ):
            return False
        if filters["parentId"] and category.get("parentId", "") != filters["parentId"]:
            return False
        return True

    return [category for category in categories if matches(category)], filters


def sort_mobile_categories(categories: list[dict]) -> tuple[list[dict], str]:
    sort = request.args.get("sort", "order_asc").strip() or "order_asc"
    sorters = {
        "order_asc": (lambda item: (safe_int(item.get("sortOrder"), 0), str(item.get("name", "")).lower()), False),
        "name_asc": (lambda item: str(item.get("name", "")).lower(), False),
        "name_desc": (lambda item: str(item.get("name", "")).lower(), True),
    }
    key, reverse = sorters.get(sort, sorters["order_asc"])
    return sorted(categories, key=key, reverse=reverse), sort if sort in sorters else "order_asc"


def filter_mobile_announcements(items: list[dict]) -> tuple[list[dict], dict]:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "placement": request.args.get("placement", "").strip(),
    }

    def matches(item: dict) -> bool:
        if filters["q"] and filters["q"] not in normalize_search_text(
            item.get("title"),
            item.get("body"),
            item.get("message"),
            item.get("placement"),
        ):
            return False
        return True

    return [item for item in items if matches(item)], filters


def sort_mobile_announcements(items: list[dict]) -> tuple[list[dict], str]:
    sort = request.args.get("sort", "priority_desc").strip() or "priority_desc"
    sorters = {
        "priority_desc": (lambda item: safe_int(item.get("priority"), 0), True),
        "updated_desc": (lambda item: str(item.get("updatedAt", item.get("createdAt", ""))), True),
        "title_asc": (lambda item: str(item.get("title", "")).lower(), False),
    }
    key, reverse = sorters.get(sort, sorters["priority_desc"])
    return sorted(items, key=key, reverse=reverse), sort if sort in sorters else "priority_desc"


def filter_mobile_directory_items(items: list[dict]) -> tuple[list[dict], dict]:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "state": request.args.get("state", "").strip().lower(),
        "city": request.args.get("city", "").strip().lower(),
        "specialty": request.args.get("specialty", "").strip().lower(),
    }

    def matches(item: dict) -> bool:
        specialties = " ".join(str(value) for value in item.get("specialties", []) or [])
        if filters["q"] and filters["q"] not in normalize_search_text(
            item.get("name"),
            item.get("companyName"),
            item.get("contactName"),
            item.get("subtitle"),
            item.get("state"),
            item.get("city"),
            item.get("coverage"),
            specialties,
        ):
            return False
        if filters["state"] and filters["state"] not in normalize_search_text(item.get("state")):
            return False
        if filters["city"] and filters["city"] not in normalize_search_text(item.get("city")):
            return False
        if filters["specialty"] and filters["specialty"] not in specialties.lower():
            return False
        return True

    return [item for item in items if matches(item)], filters


def sort_mobile_directory_items(items: list[dict]) -> tuple[list[dict], str]:
    sort = request.args.get("sort", "name_asc").strip() or "name_asc"
    sorters = {
        "name_asc": (lambda item: str(item.get("name", "")).lower(), False),
        "city_asc": (lambda item: (str(item.get("city", "")).lower(), str(item.get("name", "")).lower()), False),
    }
    key, reverse = sorters.get(sort, sorters["name_asc"])
    return sorted(items, key=key, reverse=reverse), sort if sort in sorters else "name_asc"


def filter_mobile_quotes(quotes: list[dict]) -> tuple[list[dict], dict]:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "status": request.args.get("status", "").strip(),
        "saleType": request.args.get("saleType", "").strip(),
    }

    def matches(quote: dict) -> bool:
        if filters["q"] and filters["q"] not in normalize_search_text(
            quote.get("quoteNumber"),
            quote.get("clientName"),
            quote.get("sellerName"),
            quote.get("statusLabel"),
        ):
            return False
        if filters["status"] and quote.get("status") != filters["status"]:
            return False
        if filters["saleType"] and quote.get("saleType") != filters["saleType"]:
            return False
        return True

    return [quote for quote in quotes if matches(quote)], filters


def sort_mobile_quotes(quotes: list[dict]) -> tuple[list[dict], str]:
    sort = request.args.get("sort", "updated_desc").strip() or "updated_desc"
    sorters = {
        "updated_desc": (lambda item: str(item.get("updatedAt", item.get("createdAt", ""))), True),
        "created_desc": (lambda item: str(item.get("createdAt", "")), True),
        "total_desc": (lambda item: safe_float(item.get("totalUsd"), 0), True),
        "client_asc": (lambda item: str(item.get("clientName", "")).lower(), False),
    }
    key, reverse = sorters.get(sort, sorters["updated_desc"])
    return sorted(quotes, key=key, reverse=reverse), sort if sort in sorters else "updated_desc"


def filter_mobile_crm_records(records: list[dict]) -> tuple[list[dict], dict]:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "status": request.args.get("status", "").strip(),
        "recordType": request.args.get("recordType", "").strip(),
        "pipelineStage": request.args.get("pipelineStage", "").strip(),
    }

    def matches(record: dict) -> bool:
        if filters["q"] and filters["q"] not in normalize_search_text(
            record.get("title"),
            record.get("clientName"),
            record.get("sellerName"),
            record.get("recordTypeLabel"),
            record.get("pipelineStageLabel"),
        ):
            return False
        for key in ("status", "recordType", "pipelineStage"):
            if filters[key] and record.get(key) != filters[key]:
                return False
        return True

    return [record for record in records if matches(record)], filters


def sort_mobile_crm_records(records: list[dict]) -> tuple[list[dict], str]:
    sort = request.args.get("sort", "updated_desc").strip() or "updated_desc"
    sorters = {
        "updated_desc": (lambda item: str(item.get("updatedAt", "")), True),
        "next_action_asc": (lambda item: str(item.get("nextActionAt") or "9999-12-31"), False),
        "client_asc": (lambda item: str(item.get("clientName", "")).lower(), False),
    }
    key, reverse = sorters.get(sort, sorters["updated_desc"])
    return sorted(records, key=key, reverse=reverse), sort if sort in sorters else "updated_desc"


def mobile_paginated_response(items: list[dict], filters: dict | None = None, sort: str | None = None):
    page_items, pagination = api_list_pagination(items)
    return mobile_api_response(items=page_items, pagination=pagination, filters=filters, sort=sort)


def mobile_product_payload(product: dict) -> dict:
    return {
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


def mobile_visible_products(store: dict) -> list[dict]:
    return [
        enrich_inventory_product(item, store.get("orders", []))
        for item in store.get("products", [])
        if item.get("status") == "active" and item.get("visibleInApp")
    ]


def mobile_profile_from_token(store: dict) -> tuple[dict | None, object | None]:
    token_payload = mobile_token_payload()
    if not token_payload:
        return None, jsonify({"error": "Token movil requerido."})

    if token_payload and token_payload.get("type") == "admin":
        user = find_by_id(store.get("admin_users", []), token_payload.get("adminUserId") or token_payload.get("id", ""))
        if (
            not user
            or user.get("status") != "active"
            or user.get("role") not in MOBILE_SALES_ROLES
            or user.get("mobileAccessEnabled", True) is False
            or not mobile_token_version_valid(user, token_payload, "sessionVersion")
        ):
            return None, jsonify({"error": "Token movil invalido."})
        return mobile_admin_payload(user, "")["customer"], None

    client = find_by_id(store.get("clients", []), token_payload.get("clientId") or token_payload.get("id", ""))
    if not client or client.get("status") != "active" or not mobile_token_version_valid(client, token_payload, "mobileSessionVersion"):
        return None, jsonify({"error": "Cliente no encontrado."})
    return mobile_customer_payload(client, store, "")["customer"], None


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


def seller_scope_quotes(store: dict, user: dict) -> list[dict]:
    quotes = store.get("quotes", [])
    if user.get("role") != "sales":
        return quotes
    seller_id = user.get("id", "")
    client_ids = {client.get("id", "") for client in seller_scope_clients(store, user)}
    return [
        quote
        for quote in quotes
        if quote.get("sellerId") == seller_id or quote.get("clientId") in client_ids
    ]


def seller_scope_crm_records(store: dict, user: dict) -> list[dict]:
    records = store.get("crm_records", [])
    if user.get("role") != "sales":
        return records
    seller_id = user.get("id", "")
    client_ids = {client.get("id", "") for client in seller_scope_clients(store, user)}
    return [
        record
        for record in records
        if record.get("sellerId") == seller_id or record.get("clientId") in client_ids
    ]


def can_mobile_seller_access_client(store: dict, user: dict, client_id: str) -> bool:
    client = find_by_id(store.get("clients", []), client_id)
    if not client:
        return False
    if user.get("role") != "sales":
        return True
    return client.get("assignedSellerId") == user.get("id")


def mobile_quote_payload(quote: dict) -> dict:
    enriched = enrich_quote(quote)
    return {
        "id": enriched.get("id", ""),
        "quoteNumber": enriched.get("quoteNumber", ""),
        "clientId": enriched.get("clientId", ""),
        "clientName": (enriched.get("client") or {}).get("name", enriched.get("clientName", "")),
        "sellerId": enriched.get("sellerId", ""),
        "sellerName": enriched.get("sellerName", ""),
        "status": enriched.get("displayStatus", enriched.get("status", "draft")),
        "statusLabel": enriched.get("statusLabel", ""),
        "saleType": enriched.get("saleType", "cash"),
        "paymentTermDays": safe_int(enriched.get("paymentTermDays"), 0),
        "totalUsd": safe_float(enriched.get("totalUsd"), 0),
        "totalVes": safe_float(enriched.get("totalVes"), 0),
        "itemsCount": len(enriched.get("items") or []),
        "validUntil": enriched.get("validUntil", ""),
        "createdAt": enriched.get("createdAt", ""),
        "updatedAt": enriched.get("updatedAt", ""),
    }


def mobile_crm_record_payload(record: dict) -> dict:
    enriched = enrich_crm_record(record)
    return {
        "id": enriched.get("id", ""),
        "title": enriched.get("title", ""),
        "recordType": enriched.get("recordType", "lead"),
        "recordTypeLabel": enriched.get("recordTypeLabel", ""),
        "pipelineStage": enriched.get("pipelineStage", "new_lead"),
        "pipelineStageLabel": enriched.get("pipelineStageLabel", ""),
        "status": enriched.get("status", "active"),
        "statusLabel": enriched.get("statusLabel", ""),
        "clientId": enriched.get("clientId", ""),
        "clientName": enriched.get("clientName", ""),
        "sellerId": enriched.get("sellerId", ""),
        "sellerName": enriched.get("sellerName", ""),
        "nextActionAt": enriched.get("nextActionAt", ""),
        "nextActionStatus": enriched.get("nextActionStatus", "without_due_date"),
        "activitiesCount": enriched.get("activitiesCount", 0),
        "lastActivityAt": enriched.get("lastActivityAt", ""),
        "updatedAt": enriched.get("updatedAt", ""),
    }


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
    return [sanitize_text(line, max_length=500) for line in str(value or "").replace(",", "\n").splitlines() if sanitize_text(line, max_length=500)]


def parse_specs(value: str) -> dict[str, str]:
    specs: dict[str, str] = {}
    for line in split_lines(value):
        if ":" in line:
            key, spec_value = line.split(":", 1)
            specs[sanitize_text(key, max_length=80)] = sanitize_text(spec_value, max_length=500)
    return specs


def sanitize_text(value, max_length: int = 2000, allow_newlines: bool = True) -> str:
    text = str(value or "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"(?is)<\s*(script|style).*?>.*?<\s*/\s*\1\s*>", "", text)
    text = re.sub(r"(?s)<[^>]*>", "", text)
    if not allow_newlines:
        text = re.sub(r"\s+", " ", text)
    else:
        text = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
        text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:max_length]


def sanitize_url(value: str, *, allow_deeplink: bool = False, allow_local: bool = True) -> str:
    url = sanitize_text(value, max_length=1200, allow_newlines=False)
    if not url:
        return ""
    if allow_local and url.startswith("/static/uploads/"):
        return url
    if allow_deeplink and re.match(r"^wulkan://[a-zA-Z0-9/_?=&.%#:-]+$", url):
        return url
    if re.match(r"^https://[^\s<>'\"]+$", url, flags=re.IGNORECASE):
        return url
    if app.config.get("ENV") != "production" and re.match(r"^http://(localhost|127\.0\.0\.1)(:\d+)?(/[^\s<>'\"]*)?$", url, flags=re.IGNORECASE):
        return url
    return ""


def sanitize_url_list(urls: list[str], *, allow_deeplink: bool = False) -> list[str]:
    cleaned: list[str] = []
    for url in urls:
        safe_url = sanitize_url(url, allow_deeplink=allow_deeplink)
        if safe_url and safe_url not in cleaned:
            cleaned.append(safe_url)
    return cleaned


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
            return sanitize_text(value)
    return sanitize_text(default)


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
    items: list[str] = []
    for item in re.split(r"[\n\r|;,]+", str(value)):
        cleaned = sanitize_text(item, max_length=500)
        if cleaned:
            items.append(cleaned)
    return items


def parse_import_specs(value) -> dict[str, str]:
    specs: dict[str, str] = {}
    for item in parse_import_list(value):
        if ":" in item:
            key, spec_value = item.split(":", 1)
            specs[sanitize_text(key, max_length=80)] = sanitize_text(spec_value, max_length=500)
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
    if not filename.endswith((".xlsx", ".xlsm", ".csv")):
        raise BadRequest("Formato no soportado. Usa .xlsx, .xlsm o .csv.")
    max_bytes = int(app.config.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))
    if max_bytes and stream_size(file_storage) > max_bytes:
        raise BadRequest(f"Archivo demasiado grande. Maximo permitido: {max_bytes // (1024 * 1024)} MB.")

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
                if len(rows) > int(app.config.get("MAX_IMPORT_ROWS", 5000)):
                    raise BadRequest("La carga supera el maximo de filas permitido.")
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
                if len(rows) > int(app.config.get("MAX_IMPORT_ROWS", 5000)):
                    raise BadRequest("La carga supera el maximo de filas permitido.")
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


def is_public_url(value: str, *, allow_deeplink: bool = False) -> bool:
    return bool(sanitize_url(value, allow_deeplink=allow_deeplink))


def warn_invalid_urls(result: dict, row_number: int, label: str, urls: list[str], *, allow_deeplink: bool = False) -> None:
    invalid_urls = [url for url in urls if url and not is_public_url(url, allow_deeplink=allow_deeplink)]
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


def finish_import_draft(module: str, draft_id: str, status: str, result: dict | None = None) -> bool:
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
            if result is not None:
                draft.result = result
        db_session.commit()
        return True


def load_import_draft_record(module: str, draft_id: str) -> dict | None:
    from db import SessionLocal, init_database
    from models import ImportDraft

    init_database()
    with SessionLocal() as db_session:
        draft = db_session.get(ImportDraft, draft_id)
        if not draft or draft.module != module:
            return None
        return {
            "id": draft.id,
            "module": draft.module,
            "entityType": draft.entity_type,
            "status": draft.status,
            "createdByName": draft.created_by_name,
            "createdAt": draft.created_at.isoformat(),
            "expiresAt": draft.expires_at.isoformat(),
            "rows": list(draft.rows or []),
            "result": dict(draft.result or {}),
        }


def list_import_history(limit: int = 24) -> list[dict]:
    from db import SessionLocal, init_database
    from models import ImportDraft

    init_database()
    purge_expired_import_drafts()
    with SessionLocal() as db_session:
        drafts = (
            db_session.query(ImportDraft)
            .order_by(ImportDraft.created_at.desc())
            .limit(limit)
            .all()
        )
        history = []
        for draft in drafts:
            result = dict(draft.result or {})
            history.append(
                {
                    "id": draft.id,
                    "module": draft.module,
                    "entityType": draft.entity_type,
                    "status": draft.status,
                    "createdByName": draft.created_by_name,
                    "createdAt": draft.created_at.isoformat(),
                    "created": result.get("created", 0),
                    "updated": result.get("updated", 0),
                    "skipped": result.get("skipped", 0),
                    "errors": len(result.get("errors") or result.get("errorRows") or []),
                    "warnings": len(result.get("warnings") or result.get("warningRows") or []),
                }
            )
        return history


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
        raw_image_url = row_value(row, "imageUrl", "imagen", "imagen_url", "url_imagen", default=(category or {}).get("imageUrl", ""))
        payload = {
            "name": name,
            "slug": slug,
            "description": row_value(row, "description", "descripcion", default=(category or {}).get("description", "")),
            "imageUrl": sanitize_url(raw_image_url),
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
        warn_invalid_urls(result, row_number, "imagen de categoria", [raw_image_url])
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
        raw_primary_image = row_value(
            row,
            "imageUrl",
            "imagen_principal",
            "imagen",
            "url_imagen",
            default=current.get("imageUrl", ""),
        )
        primary_image = sanitize_url(raw_primary_image)
        raw_gallery_images = parse_import_list(row_value(row, "imageUrls", "imagenes", "galeria", "galeria_imagenes"))
        gallery_images = sanitize_url_list(raw_gallery_images)
        if primary_image and primary_image not in gallery_images:
            gallery_images.insert(0, primary_image)
        if not gallery_images:
            gallery_images = list(current.get("imageUrls") or [])
        if not primary_image and gallery_images:
            primary_image = gallery_images[0]
        raw_pdf_urls = parse_import_list(row_value(row, "pdfUrls", "pdfs", "fichas_pdf", "pdf_tecnicos"))
        pdf_urls = sanitize_url_list(raw_pdf_urls)
        if not pdf_urls:
            pdf_urls = list(current.get("pdfUrls") or [])
        if not primary_image and not gallery_images:
            bulk_warning(result, row_number, f"SKU {sku} no tiene imagen principal ni galeria.")
        warn_invalid_urls(result, row_number, f"SKU {sku} imagen principal", [raw_primary_image])
        warn_invalid_urls(result, row_number, f"SKU {sku} galeria", raw_gallery_images)
        warn_invalid_urls(result, row_number, f"SKU {sku} PDF tecnico", raw_pdf_urls)

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
            if term.strip().isdigit() and int(term) in payment_term_options(store)
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
        raw_cta_url = row_value(row, "ctaUrl", "accion", "url_accion", default=(announcement or {}).get("ctaUrl", ""))
        raw_image_url = row_value(row, "imageUrl", "imagen", "imagen_url", default=(announcement or {}).get("imageUrl", ""))
        payload = {
            "title": title,
            "body": row_value(row, "body", "mensaje", "descripcion", default=(announcement or {}).get("body", "")),
            "placement": row_value(row, "placement", "ubicacion", default=(announcement or {}).get("placement", "home")) or "home",
            "priority": parse_import_int(row_value(row, "priority", "prioridad"), int((announcement or {}).get("priority") or 50)),
            "ctaLabel": row_value(row, "ctaLabel", "boton", "texto_boton", default=(announcement or {}).get("ctaLabel", "")),
            "ctaUrl": sanitize_url(raw_cta_url, allow_deeplink=True),
            "imageUrl": sanitize_url(raw_image_url),
            "startsAt": row_value(row, "startsAt", "inicio", default=(announcement or {}).get("startsAt", utc_now())) or utc_now(),
            "endsAt": row_value(row, "endsAt", "cierre", "fin", default=(announcement or {}).get("endsAt", "")),
            "status": row_value(row, "status", "estado", default=(announcement or {}).get("status", "active")) or "active",
            "updatedAt": utc_now(),
        }
        if not payload.get("imageUrl"):
            bulk_warning(result, row_number, f"banner {title} no tiene imagen de carrusel.")
        warn_invalid_urls(result, row_number, f"banner {title}", [raw_image_url])
        warn_invalid_urls(result, row_number, f"accion {title}", [raw_cta_url], allow_deeplink=True)
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
        raw_asset_url = row_value(row, "url", "assetUrl", "archivo_url", "imagen_url", "pdf_url")
        asset_url = sanitize_url(raw_asset_url)
        if not asset_url:
            bulk_error(result, row_number, "recurso requiere URL de imagen o PDF.")
            continue
        duplicate_key = f"{row_value(row, 'sku', 'producto_sku', 'sku_producto')}|{asset_url}"
        duplicate_message = duplicate_in_upload(seen_assets, duplicate_key, row_number)
        if duplicate_message:
            bulk_error(result, row_number, f"recurso {title}: {duplicate_message}")
            continue
        warn_invalid_urls(result, row_number, f"recurso {title}", [raw_asset_url])
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


DOCUMENT_SCOPE_ALIASES = {
    "cliente": "client",
    "clientes": "client",
    "client": "client",
    "producto": "product",
    "productos": "product",
    "product": "product",
    "orden": "order",
    "pedido": "order",
    "order": "order",
    "administrativo": "admin",
    "admin": "admin",
}
DOCUMENT_TYPE_ALIASES = {
    "rif": "rif",
    "documento_fiscal": "rif",
    "contrato": "contract",
    "contract": "contract",
    "credito": "credit",
    "credit": "credit",
    "estado_cuenta": "account_statement",
    "account_statement": "account_statement",
    "ficha_tecnica": "technical_sheet",
    "technical_sheet": "technical_sheet",
    "manual": "manual",
    "garantia": "warranty",
    "warranty": "warranty",
    "certificado": "certificate",
    "certificate": "certificate",
    "cotizacion": "quote",
    "quote": "quote",
    "comprobante": "payment_proof",
    "payment_proof": "payment_proof",
    "guia_despacho": "dispatch_guide",
    "dispatch_guide": "dispatch_guide",
    "evidencia_entrega": "delivery_evidence",
    "delivery_evidence": "delivery_evidence",
    "factura": "invoice",
    "invoice": "invoice",
    "administrativo": "administrative",
    "administrative": "administrative",
}
DOCUMENT_VISIBILITY_ALIASES = {
    "interno": "internal",
    "internal": "internal",
    "admin": "internal",
    "vendedor": "seller",
    "seller": "seller",
    "cliente": "client",
    "client": "client",
    "publico": "public",
    "public": "public",
}


def normalize_document_scope(value: str) -> str:
    key = normalize_import_key(value or "admin")
    return DOCUMENT_SCOPE_ALIASES.get(key, key if key in dict(DOCUMENT_SCOPE_OPTIONS) else "admin")


def normalize_document_type(value: str) -> str:
    key = normalize_import_key(value or "administrative")
    return DOCUMENT_TYPE_ALIASES.get(key, key if key in dict(DOCUMENT_TYPE_OPTIONS) else "administrative")


def normalize_document_visibility(value: str) -> str:
    key = normalize_import_key(value or "internal")
    return DOCUMENT_VISIBILITY_ALIASES.get(key, key if key in dict(DOCUMENT_VISIBILITY_OPTIONS) else "internal")


def document_is_asset(asset: dict) -> bool:
    return asset.get("assetType") == "document" or asset.get("type") == "document" or bool(asset.get("documentType"))


def document_is_private(asset: dict) -> bool:
    return normalize_document_visibility(asset.get("visibility", "internal")) != "public"


def document_storage_key(url: str) -> str:
    return key_from_public_url(
        url,
        public_base_url=app.config.get("STORAGE_PUBLIC_BASE_URL", ""),
        bucket=app.config.get("S3_BUCKET", ""),
        endpoint_url=app.config.get("S3_ENDPOINT_URL", ""),
    )


def document_signed_url(asset: dict) -> str:
    raw_url = sanitize_url(asset.get("url", ""))
    if not raw_url:
        return ""
    if not document_is_private(asset):
        return raw_url

    key = document_storage_key(raw_url)
    if not key:
        return ""

    expires_in = int(app.config.get("DOCUMENT_SIGNED_URL_MAX_AGE_SECONDS", 300))
    if app.config.get("STORAGE_BACKEND") == "s3":
        return generate_s3_signed_url(
            key,
            bucket=app.config.get("S3_BUCKET", ""),
            region=app.config.get("S3_REGION", "us-east-1"),
            endpoint_url=app.config.get("S3_ENDPOINT_URL", ""),
            expires_in=expires_in,
        )

    token = document_token_serializer().dumps(
        {
            "assetId": asset.get("id", ""),
            "key": key,
            "urlHash": hashlib.sha256(raw_url.encode("utf-8")).hexdigest(),
        }
    )
    return url_for("document_private_file", token=token)


def can_open_document(asset: dict | None, store: dict) -> bool:
    if not asset or not document_is_asset(asset) or asset.get("status") == "deleted":
        return False
    if not can_module_action("documents", "view"):
        return False
    if current_admin_role() != "sales":
        return True

    scope = normalize_document_scope(asset.get("subjectType") or ("product" if asset.get("productId") else "admin"))
    subject_id = asset.get("subjectId") or asset.get("productId", "")
    if scope == "client":
        return can_access_client_record(find_by_id(store.get("clients", []), subject_id))
    if scope == "order":
        return can_access_order_record(find_order(store.get("orders", []), subject_id), store)
    return scope in {"admin", "product"}


def resolve_document_subject(store: dict, scope: str, reference: str) -> tuple[str, str]:
    reference = (reference or "").strip()
    if scope == "admin":
        return "", "Administrativo general"

    if scope == "client":
        normalized = normalize_import_key(reference)
        client = next(
            (
                item
                for item in store.get("clients", [])
                if item.get("id") == reference
                or item.get("email", "").lower() == reference.lower()
                or normalize_import_key(item.get("taxId", "")) == normalized
                or normalize_import_key(item.get("businessName", "")) == normalized
            ),
            None,
        )
        if client:
            return client.get("id", ""), client.get("businessName", "Cliente")

    if scope == "product":
        product = find_by_id(store.get("products", []), reference) or find_product_by_sku(store, reference)
        if not product and reference:
            normalized = normalize_import_key(reference)
            product = next((item for item in store.get("products", []) if normalize_import_key(item.get("title", "")) == normalized), None)
        if product:
            return product.get("id", ""), f"{product.get('sku', '')} - {product.get('title', 'Producto')}".strip(" -")

    if scope == "order":
        normalized = normalize_import_key(reference)
        order = next(
            (
                item
                for item in store.get("orders", [])
                if item.get("id") == reference
                or item.get("orderId") == reference
                or item.get("orderNumber") == reference
                or normalize_import_key(item.get("id", "")) == normalized
                or normalize_import_key(item.get("orderId", "")) == normalized
            ),
            None,
        )
        if order:
            return order.get("id", ""), order.get("orderId") or order.get("id", "Orden")

    return "", ""


def document_subject_options(store: dict) -> list[dict]:
    return [
        {
            "label": "Clientes",
            "items": [
                {"value": f"client:{client.get('id', '')}", "label": f"{client.get('businessName', 'Cliente')} - {client.get('email', '')}"}
                for client in store.get("clients", [])
            ],
        },
        {
            "label": "Productos",
            "items": [
                {"value": f"product:{product.get('id', '')}", "label": f"{product.get('sku', '')} - {product.get('title', 'Producto')}"}
                for product in store.get("products", [])
            ],
        },
        {
            "label": "Ordenes",
            "items": [
                {"value": f"order:{order.get('id', '')}", "label": f"{order.get('orderId') or order.get('id', 'Orden')} - {order.get('customer', {}).get('name', '')}"}
                for order in store.get("orders", [])
            ],
        },
    ]


def parse_document_subject_ref(value: str) -> tuple[str, str]:
    if ":" not in (value or ""):
        return "admin", ""
    scope, subject_id = value.split(":", 1)
    return normalize_document_scope(scope), subject_id


def document_assets(store: dict) -> list[dict]:
    products = {product.get("id"): product for product in store.get("products", [])}
    clients = {client.get("id"): client for client in store.get("clients", [])}
    orders = {order.get("id"): order for order in store.get("orders", [])}
    now = datetime.now(timezone.utc)
    assets = []
    for asset in reversed(store.get("media_assets", [])):
        if not document_is_asset(asset) or asset.get("status") == "deleted":
            continue
        item = dict(asset)
        scope = normalize_document_scope(item.get("subjectType") or ("product" if item.get("productId") else "admin"))
        subject_id = item.get("subjectId") or item.get("productId", "")
        label = item.get("subjectLabel", "")
        if scope == "client" and subject_id in clients:
            label = clients[subject_id].get("businessName", label)
        elif scope == "product" and subject_id in products:
            product = products[subject_id]
            label = f"{product.get('sku', '')} - {product.get('title', 'Producto')}".strip(" -")
        elif scope == "order" and subject_id in orders:
            label = orders[subject_id].get("orderId") or orders[subject_id].get("id", label)
        item["subjectType"] = scope
        item["subjectId"] = subject_id
        item["subjectLabel"] = label or "Administrativo general"
        item["documentType"] = normalize_document_type(item.get("documentType", "administrative"))
        item["visibility"] = normalize_document_visibility(item.get("visibility", "internal"))
        item["isPrivate"] = document_is_private(item)
        item["displayUrl"] = "Documento protegido" if item["isPrivate"] else sanitize_url(item.get("url", ""))
        item["effectiveStatus"] = item.get("status", "active")
        if item.get("expiresAt") and parse_utc_datetime(item.get("expiresAt")) < now and item["effectiveStatus"] == "active":
            item["effectiveStatus"] = "expired"
        assets.append(item)
    return assets


def document_metrics(assets: list[dict]) -> dict:
    return {
        "total": len(assets),
        "active": sum(1 for item in assets if item.get("effectiveStatus") == "active"),
        "review": sum(1 for item in assets if item.get("effectiveStatus") == "pending_review"),
        "expired": sum(1 for item in assets if item.get("effectiveStatus") == "expired"),
    }


def document_graph(assets: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for asset in assets:
        label = document_type_label(asset.get("documentType", "administrative"))
        counts[label] = counts.get(label, 0) + 1
    rows = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:6]
    return {"labels": [label for label, _count in rows], "values": [count for _label, count in rows]}


def import_documents_rows(store: dict, rows: list[dict]) -> dict:
    result = blank_bulk_result()
    seen_documents: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=2):
        title = row_value(row, "title", "titulo", "documento")
        raw_document_url = row_value(row, "url", "documentUrl", "archivo_url", "documento_url")
        document_url = sanitize_url(raw_document_url)
        document_type = normalize_document_type(row_value(row, "documentType", "tipo_documento", "tipo", default="administrative"))
        scope = normalize_document_scope(row_value(row, "subjectType", "ambito", "scope", default="admin"))
        reference = row_value(row, "subjectId", "referencia", "cliente", "sku", "orden", default="")
        if not title or not document_url:
            bulk_error(result, row_number, "documento requiere titulo y URL.")
            continue
        if document_type not in dict(DOCUMENT_TYPE_OPTIONS):
            bulk_error(result, row_number, f"documento {title}: tipo no valido.")
            continue
        if scope not in dict(DOCUMENT_SCOPE_OPTIONS):
            bulk_error(result, row_number, f"documento {title}: ambito no valido.")
            continue
        subject_id, subject_label = resolve_document_subject(store, scope, reference)
        if scope != "admin" and not subject_id:
            bulk_error(result, row_number, f"documento {title}: referencia no encontrada para {document_scope_label(scope).lower()}.")
            continue
        duplicate_key = f"{scope}|{subject_id}|{document_type}|{document_url}"
        duplicate_message = duplicate_in_upload(seen_documents, duplicate_key, row_number)
        if duplicate_message:
            bulk_error(result, row_number, f"documento {title}: {duplicate_message}")
            continue
        warn_invalid_urls(result, row_number, f"documento {title}", [raw_document_url])
        status = row_value(row, "status", "estado", default="active") or "active"
        if status not in dict(DOCUMENT_STATUS_OPTIONS):
            bulk_error(result, row_number, f"documento {title}: estado no valido.")
            continue
        visibility = normalize_document_visibility(row_value(row, "visibility", "visibilidad", default="internal"))
        existing = next(
            (
                item
                for item in store.get("media_assets", [])
                if document_is_asset(item)
                and item.get("subjectType") == scope
                and item.get("subjectId", "") == subject_id
                and item.get("documentType") == document_type
                and item.get("url") == document_url
            ),
            None,
        )
        payload = {
            "title": title,
            "assetType": "document",
            "type": "document",
            "productId": subject_id if scope == "product" else "",
            "url": document_url,
            "documentType": document_type,
            "subjectType": scope,
            "subjectId": subject_id,
            "subjectLabel": subject_label,
            "visibility": visibility,
            "expiresAt": row_value(row, "expiresAt", "vence", "vencimiento", default=(existing or {}).get("expiresAt", "")),
            "status": status,
            "notes": row_value(row, "notes", "nota", "observacion", default=(existing or {}).get("notes", "")),
            "updatedAt": utc_now(),
        }
        if existing:
            existing.update(payload)
            result["updated"] += 1
            bulk_row(result, "updated", row_number, title)
        else:
            payload["id"] = next_id("doc", title)
            payload["createdByName"] = "Carga masiva"
            payload["createdAt"] = utc_now()
            store.setdefault("media_assets", []).append(payload)
            result["created"] += 1
            bulk_row(result, "created", row_number, title)
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
        result["module"] = module
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
        result["confirmed"] = True
        result["draftId"] = draft_id
        finish_import_draft(module, draft_id, "confirmed", result)
        remember_bulk_result(module, result)
        return redirect(url_for(redirect_endpoint))

    try:
        rows = read_tabular_upload(request.files.get("importFile"))
        if import_mode == "preview":
            preview_store = copy.deepcopy(store)
            result = importer(preview_store, rows)
            result["module"] = module
            result["preview"] = True
            result["draftId"] = create_import_draft(module, entity_type, rows, result)
            result["confirmEndpoint"] = request.endpoint
            result["discardEndpoint"] = request.endpoint
            result["expiresInMinutes"] = max(1, IMPORT_DRAFT_TTL_SECONDS // 60)
            remember_bulk_result(module, result)
            return redirect(url_for(redirect_endpoint))

        result = importer(store, rows)
        result["module"] = module
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
    blocker = client_sales_blocker(client, sale_type)
    if blocker:
        return None, blocker
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
    commission_rule = business_settings(store).get("defaultCommissionRule") or "sale_generated"
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
        "commissionBaseUsd": total_usd,
        "commissionUsd": commission_usd,
        "commissionStatus": "commission_pending" if commission_usd else "commission_cancelled",
        "commissionRule": commission_rule if commission_rule in dict(COMMISSION_RULE_OPTIONS) else "sale_generated",
        "commissionGeneratedAt": utc_now(),
        "commissionApprovedAt": "",
        "commissionApprovedBy": "",
        "commissionPaidAt": "",
        "commissionPaidBy": "",
        "commissionObservation": "",
        "commissionHoldReason": "",
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
        "ipAddress": request_ip_address(),
        "userAgent": request_user_agent(),
        "deviceHash": request_device_hash(),
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


NOTIFICATION_TYPE_LABELS = {
    "order_created": "Nueva orden",
    "order_pending_approval": "Orden pendiente aprobacion",
    "order_received": "Orden recibida",
    "order_approved": "Orden aprobada",
    "order_rejected": "Orden rechazada",
    "order_dispatched": "Orden despachada",
    "order_delivered": "Orden entregada",
    "credit_requested": "Credito solicitado",
    "credit_approved": "Credito aprobado",
    "credit_rejected": "Credito rechazado",
    "client_blocked": "Cliente bloqueado",
    "client_assigned": "Cliente asignado",
    "client_created_by_seller": "Cliente nuevo por vendedor",
    "stock_low": "Stock critico",
    "product_out": "Producto agotado",
    "payment_registered": "Abono registrado",
    "quote_accepted": "Cotizacion aceptada",
    "commission_approved": "Comision aprobada",
    "commission_paid": "Comision pagada",
    "client_debt": "Cliente con deuda",
    "inactive_client": "Cliente sin compra reciente",
    "overdue_balance": "Saldo vencido",
    "goal_pending": "Meta pendiente",
    "info": "Informacion",
}
NOTIFICATION_PRIORITY_LABELS = {
    "low": "Baja",
    "normal": "Normal",
    "high": "Alta",
    "critical": "Critica",
}
NOTIFICATION_STATUS_LABELS = {
    "unread": "Pendiente",
    "read": "Leida",
    "archived": "Archivada",
}


def notification_type_label(value: str) -> str:
    return NOTIFICATION_TYPE_LABELS.get(value, str(value or "info").replace("_", " ").title())


def notification_priority_label(value: str) -> str:
    return NOTIFICATION_PRIORITY_LABELS.get(value, "Normal")


def notification_status_label(value: str) -> str:
    return NOTIFICATION_STATUS_LABELS.get(value, "Pendiente")


def notification_priority_class(value: str) -> str:
    return {
        "low": "text-bg-secondary",
        "normal": "text-bg-primary",
        "high": "text-bg-warning",
        "critical": "text-bg-danger",
    }.get(value, "text-bg-primary")


def notification_url(endpoint: str, **values) -> str:
    try:
        return url_for(endpoint, **values)
    except RuntimeError:
        return ""
    except Exception:
        return ""


def notification_is_expired(notification: dict) -> bool:
    expires_at = notification.get("expiresAt") or ""
    if not expires_at:
        return False
    return parse_utc_datetime(expires_at) < datetime.now(timezone.utc)


def create_notification(
    store: dict,
    *,
    title: str,
    body: str = "",
    notification_type: str = "info",
    channel: str = "web",
    priority: str = "normal",
    recipient_type: str = "admin",
    recipient_id: str = "",
    recipient_role: str = "",
    module: str = "dashboard",
    entity_type: str = "",
    entity_id: str = "",
    href: str = "",
    deep_link: str = "",
    metadata: dict | None = None,
    dedupe_key: str = "",
) -> dict:
    now = utc_now()
    metadata = dict(metadata or {})
    if dedupe_key:
        metadata["dedupeKey"] = dedupe_key
        for existing in store.setdefault("notifications", []):
            existing_payload = existing.get("payload") or existing.get("metadata") or {}
            if (
                existing.get("status", "unread") == "unread"
                and existing_payload.get("dedupeKey") == dedupe_key
            ):
                existing.update(
                    {
                        "title": title,
                        "body": body,
                        "notificationType": notification_type,
                        "type": notification_type,
                        "channel": channel,
                        "priority": priority,
                        "module": module,
                        "href": href,
                        "deepLink": deep_link,
                        "payload": metadata,
                        "metadata": metadata,
                        "updatedAt": now,
                    }
                )
                return existing

    notification = {
        "id": next_id("ntf", f"{notification_type}-{recipient_type}-{recipient_id}-{recipient_role}-{entity_id}-{now}"),
        "title": title.strip() or "Notificacion Wulkan",
        "body": body.strip(),
        "notificationType": notification_type,
        "type": notification_type,
        "channel": channel,
        "priority": priority if priority in NOTIFICATION_PRIORITY_LABELS else "normal",
        "status": "unread",
        "recipientType": recipient_type,
        "recipientId": recipient_id,
        "recipientRole": recipient_role,
        "module": module,
        "entityType": entity_type,
        "entityId": entity_id,
        "href": href,
        "deepLink": deep_link,
        "readAt": "",
        "expiresAt": "",
        "payload": metadata,
        "metadata": metadata,
        "createdAt": now,
        "updatedAt": now,
    }
    notifications = store.setdefault("notifications", [])
    notifications.append(notification)
    store["notifications"] = sorted(notifications, key=lambda item: item.get("createdAt", ""))[-1000:]
    return notification


def notify_admin(store: dict, title: str, body: str, **kwargs) -> dict:
    return create_notification(store, title=title, body=body, recipient_type="admin", channel="web", **kwargs)


def notify_role(store: dict, role: str, title: str, body: str, **kwargs) -> dict:
    return create_notification(store, title=title, body=body, recipient_type="role", recipient_role=role, channel="web", **kwargs)


def notify_seller(store: dict, seller_id: str, title: str, body: str, **kwargs) -> dict | None:
    if not seller_id:
        return None
    return create_notification(store, title=title, body=body, recipient_type="seller", recipient_id=seller_id, channel="mobile", **kwargs)


def notify_client(store: dict, client_id: str, title: str, body: str, **kwargs) -> dict | None:
    if not client_id:
        return None
    return create_notification(store, title=title, body=body, recipient_type="client", recipient_id=client_id, channel="mobile", **kwargs)


def notification_visible_to_current_admin(notification: dict) -> bool:
    if notification.get("status") == "archived" or notification_is_expired(notification):
        return False
    role = current_admin_role()
    if role == "super_admin":
        return True
    module = notification.get("module") or ""
    if module and module in ALL_MODULE_KEYS and not can_access_module(module):
        return False
    recipient_type = notification.get("recipientType", "admin")
    recipient_id = notification.get("recipientId", "")
    recipient_role = notification.get("recipientRole", "")
    if recipient_type in {"admin", "internal"}:
        return not recipient_id or recipient_id == session.get("admin_user_id", "")
    if recipient_type == "role":
        return not recipient_role or recipient_role == role
    if recipient_type in {"user", "admin_user"}:
        return recipient_id == session.get("admin_user_id", "")
    return False


def visible_admin_notifications(store: dict) -> list[dict]:
    notifications = [
        enrich_notification(notification)
        for notification in store.get("notifications", [])
        if notification_visible_to_current_admin(notification)
    ]
    return sorted(notifications, key=lambda item: item.get("createdAt", ""), reverse=True)


def admin_notification_count() -> int:
    if not session.get("admin_authenticated") or not can_access_module("notifications"):
        return 0
    try:
        store = load_store()
    except Exception:
        return 0
    return sum(1 for item in visible_admin_notifications(store) if item.get("status") == "unread")


def enrich_notification(notification: dict) -> dict:
    enriched = dict(notification)
    notification_type = enriched.get("notificationType") or enriched.get("type") or "info"
    enriched["notificationType"] = notification_type
    enriched["type"] = notification_type
    enriched["typeLabel"] = notification_type_label(notification_type)
    enriched["priorityLabel"] = notification_priority_label(enriched.get("priority", "normal"))
    enriched["priorityClass"] = notification_priority_class(enriched.get("priority", "normal"))
    enriched["statusLabel"] = notification_status_label(enriched.get("status", "unread"))
    enriched["payload"] = enriched.get("payload") or enriched.get("metadata") or {}
    return enriched


def mobile_notification_payload(notification: dict) -> dict:
    enriched = enrich_notification(notification)
    return {
        "id": enriched["id"],
        "title": enriched["title"],
        "body": enriched.get("body", ""),
        "type": enriched["notificationType"],
        "typeLabel": enriched["typeLabel"],
        "channel": enriched.get("channel", "mobile"),
        "priority": enriched.get("priority", "normal"),
        "priorityLabel": enriched["priorityLabel"],
        "status": enriched.get("status", "unread"),
        "statusLabel": enriched["statusLabel"],
        "module": enriched.get("module", ""),
        "entityType": enriched.get("entityType", ""),
        "entityId": enriched.get("entityId", ""),
        "href": enriched.get("href", ""),
        "deepLink": enriched.get("deepLink", ""),
        "createdAt": enriched.get("createdAt", ""),
        "readAt": enriched.get("readAt", ""),
        "metadata": enriched.get("payload", {}),
    }


def mobile_notifications_for_subject(store: dict, subject_type: str, subject_id: str, role: str = "") -> list[dict]:
    visible = []
    for notification in store.get("notifications", []):
        if notification.get("status") == "archived" or notification_is_expired(notification):
            continue
        recipient_type = notification.get("recipientType", "")
        recipient_id = notification.get("recipientId", "")
        recipient_role = notification.get("recipientRole", "")
        if recipient_type == subject_type and recipient_id == subject_id:
            visible.append(notification)
        elif recipient_type == "role" and role and recipient_role == role:
            visible.append(notification)
    return sorted(visible, key=lambda item: item.get("createdAt", ""), reverse=True)


def mobile_notification_subject(store: dict) -> tuple[str, str, str, object | None]:
    payload = mobile_token_payload()
    if payload.get("type") == "admin":
        user, auth_error = require_mobile_sales_user(store)
        if auth_error:
            return "", "", "", auth_error
        return "seller", user["id"], user.get("role", ""), None
    client, auth_error = require_mobile_client(store)
    if auth_error or not client:
        return "", "", "", auth_error or jsonify({"error": "Token movil requerido."})
    return "client", client["id"], "client", None


def generate_mobile_subject_notifications(store: dict, subject_type: str, subject_id: str, role: str = "") -> bool:
    before_count = len(store.setdefault("notifications", []))
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    orders = store.get("orders", [])
    movements = store.get("credit_movements", [])

    if subject_type == "seller":
        user = find_by_id(store.get("admin_users", []), subject_id)
        if not user:
            return False
        seller_snapshot = enrich_seller(store, user)
        if safe_float(seller_snapshot.get("salesGoalUsd"), 0) > 0 and safe_float(seller_snapshot.get("goalProgressPercent"), 0) < 100:
            notify_seller(
                store,
                subject_id,
                "Meta pendiente",
                f"Avance {seller_snapshot.get('goalProgressPercent', 0)}% de meta mensual {money_usd(seller_snapshot.get('salesGoalUsd', 0))}.",
                notification_type="goal_pending",
                priority="low",
                module="sellers",
                entity_type="seller",
                entity_id=subject_id,
                deep_link="wulkan://seller/home",
                metadata={"month": current_month, "goalProgressPercent": seller_snapshot.get("goalProgressPercent", 0)},
                dedupe_key=f"seller-goal-{subject_id}-{current_month}",
            )
        for client in seller_scope_clients(store, user):
            enriched = enrich_client(client, orders, movements)
            client_id = enriched.get("id", "")
            client_name = enriched.get("businessName") or enriched.get("commercialName") or "Cliente"
            overdue = safe_float(enriched.get("overdueBalanceUsd"), 0)
            if overdue > 0:
                notify_seller(
                    store,
                    subject_id,
                    "Cliente con deuda",
                    f"{client_name} mantiene {money_usd(overdue)} vencidos.",
                    notification_type="client_debt",
                    priority="high",
                    module="clients",
                    entity_type="client",
                    entity_id=client_id,
                    deep_link=f"wulkan://seller/clients/{client_id}",
                    metadata={"clientId": client_id, "overdueBalanceUsd": overdue},
                    dedupe_key=f"seller-client-debt-{subject_id}-{client_id}-{current_month}",
                )
            last_activity = enriched.get("lastOrderAt") or enriched.get("createdAt") or ""
            if last_activity:
                inactive_days = (datetime.now(timezone.utc) - parse_utc_datetime(last_activity)).days
                if inactive_days >= 45:
                    notify_seller(
                        store,
                        subject_id,
                        "Cliente sin compra reciente",
                        f"{client_name} lleva {inactive_days} dias sin compra registrada.",
                        notification_type="inactive_client",
                        priority="low",
                        module="clients",
                        entity_type="client",
                        entity_id=client_id,
                        deep_link=f"wulkan://seller/clients/{client_id}",
                        metadata={"clientId": client_id, "inactiveDays": inactive_days},
                        dedupe_key=f"seller-client-inactive-{subject_id}-{client_id}-{current_month}",
                    )

    if subject_type == "client":
        client = find_by_id(store.get("clients", []), subject_id)
        if client:
            enriched = enrich_client(client, orders, movements)
            overdue = safe_float(enriched.get("overdueBalanceUsd"), 0)
            if overdue > 0:
                notify_client(
                    store,
                    subject_id,
                    "Saldo vencido",
                    f"Tienes {money_usd(overdue)} vencidos. Contacta a tu vendedor Wulkan.",
                    notification_type="overdue_balance",
                    priority="high",
                    module="credit",
                    entity_type="client",
                    entity_id=subject_id,
                    deep_link="wulkan://credit",
                    metadata={"clientId": subject_id, "overdueBalanceUsd": overdue},
                    dedupe_key=f"client-overdue-{subject_id}-{current_month}",
                )

    return len(store.get("notifications", [])) != before_count


def notify_order_created(store: dict, order: dict) -> None:
    order_id = order.get("orderId") or order.get("id", "")
    customer = order.get("customer") or {}
    customer_name = customer.get("name") or customer.get("businessName") or "Cliente Wulkan"
    total = money_usd(order.get("totalUsd") or order.get("netUsd") or 0)
    sale_label = sale_type_label(order.get("saleType", "cash"))
    status = order.get("status", "credit_review")
    notification_type = "order_pending_approval" if status in {"credit_review", "payment_under_review"} else "order_created"
    priority = "high" if notification_type == "order_pending_approval" else "normal"
    notify_admin(
        store,
        "Nueva orden de compra",
        f"{customer_name} genero {total} bajo condicion {sale_label}.",
        notification_type=notification_type,
        priority=priority,
        module="orders",
        entity_type="order",
        entity_id=order_id,
        href=notification_url("orders", q=order_id),
        deep_link=f"wulkan://orders/{order_id}",
        metadata={"orderId": order_id, "saleType": order.get("saleType", ""), "status": status},
        dedupe_key=f"admin-order-created-{order_id}",
    )
    notify_client(
        store,
        order.get("customerId", ""),
        "Orden recibida",
        f"Wulkan recibio tu orden {order_id} por {total}.",
        notification_type="order_received",
        priority="normal",
        module="orders",
        entity_type="order",
        entity_id=order_id,
        deep_link=f"wulkan://orders/{order_id}",
        metadata={"orderId": order_id, "status": status},
        dedupe_key=f"client-order-received-{order_id}",
    )
    notify_seller(
        store,
        order.get("sellerId", ""),
        "Nueva orden de tu cartera",
        f"{customer_name} creo una orden por {total}.",
        notification_type="order_created",
        priority=priority,
        module="orders",
        entity_type="order",
        entity_id=order_id,
        deep_link=f"wulkan://seller/orders/{order_id}",
        metadata={"orderId": order_id, "customerId": order.get("customerId", "")},
        dedupe_key=f"seller-order-created-{order_id}",
    )


def notify_order_status_change(store: dict, order: dict, before_status: str) -> None:
    after_status = order.get("status", "")
    if not after_status or before_status == after_status:
        return
    order_id = order.get("orderId") or order.get("id", "")
    total = money_usd(order.get("totalUsd") or 0)
    status_label = order_status_label(after_status)
    type_by_status = {
        "approved_with_credit": "order_approved",
        "preparing": "order_approved",
        "rejected": "order_rejected",
        "cancelled": "order_rejected",
        "delivered": "order_delivered",
        "paid": "order_delivered",
        "partial_paid": "order_approved",
    }
    notification_type = type_by_status.get(after_status, "info")
    if notification_type == "info":
        return
    title_by_type = {
        "order_approved": "Orden aprobada",
        "order_rejected": "Orden rechazada",
        "order_delivered": "Orden entregada",
    }
    notify_client(
        store,
        order.get("customerId", ""),
        title_by_type.get(notification_type, "Orden actualizada"),
        f"Tu orden {order_id} ahora esta en estado {status_label}. Total {total}.",
        notification_type=notification_type,
        priority="high" if notification_type == "order_rejected" else "normal",
        module="orders",
        entity_type="order",
        entity_id=order_id,
        deep_link=f"wulkan://orders/{order_id}",
        metadata={"orderId": order_id, "beforeStatus": before_status, "status": after_status},
        dedupe_key=f"client-order-status-{order_id}-{after_status}",
    )
    notify_seller(
        store,
        order.get("sellerId", ""),
        title_by_type.get(notification_type, "Orden actualizada"),
        f"Orden {order_id} actualizada a {status_label}.",
        notification_type=notification_type,
        priority="high" if notification_type == "order_rejected" else "normal",
        module="orders",
        entity_type="order",
        entity_id=order_id,
        deep_link=f"wulkan://seller/orders/{order_id}",
        metadata={"orderId": order_id, "beforeStatus": before_status, "status": after_status},
        dedupe_key=f"seller-order-status-{order_id}-{after_status}",
    )


def notify_credit_decision(store: dict, client: dict, decision: str) -> None:
    client_id = client.get("id", "")
    approved = decision in {"approved", "reactivate", "adjust"} and safe_float(client.get("creditLimitUsd"), 0) > 0
    rejected = decision in {"rejected", "suspended", "blocked_debt", "blocked_limit"}
    if not approved and not rejected:
        return
    notification_type = "credit_approved" if approved else "credit_rejected"
    title = "Credito aprobado" if approved else "Credito no aprobado"
    body = (
        f"Linea disponible por {money_usd(client.get('creditLimitUsd', 0))} a {client.get('paymentTermsDays', 0)} dias."
        if approved
        else "La solicitud de credito requiere revision o fue rechazada por gerencia."
    )
    notify_client(
        store,
        client_id,
        title,
        body,
        notification_type=notification_type,
        priority="high",
        module="credit",
        entity_type="client",
        entity_id=client_id,
        deep_link="wulkan://credit",
        metadata={"clientId": client_id, "decision": decision},
        dedupe_key=f"client-credit-{client_id}-{client.get('creditReviewedAt', '')}",
    )
    notify_seller(
        store,
        client.get("assignedSellerId", ""),
        title,
        f"{client.get('businessName') or client.get('commercialName') or 'Cliente'}: {body}",
        notification_type=notification_type,
        priority="high",
        module="credit",
        entity_type="client",
        entity_id=client_id,
        deep_link=f"wulkan://seller/clients/{client_id}",
        metadata={"clientId": client_id, "decision": decision},
        dedupe_key=f"seller-credit-{client_id}-{client.get('creditReviewedAt', '')}",
    )
    if decision in {"suspended", "blocked_debt", "blocked_limit"}:
        notify_admin(
            store,
            "Cliente bloqueado",
            f"{client.get('businessName') or client.get('commercialName') or client_id} quedo con credito {credit_status_label(client.get('creditRequestStatus', ''))}.",
            notification_type="client_blocked",
            priority="critical",
            module="clients",
            entity_type="client",
            entity_id=client_id,
            href=notification_url("clients", q=client.get("businessName", "")),
            metadata={"clientId": client_id, "decision": decision},
            dedupe_key=f"admin-client-blocked-{client_id}-{client.get('creditReviewedAt', '')}",
        )


def notify_credit_requested(store: dict, client: dict) -> None:
    client_id = client.get("id", "")
    amount = safe_float(client.get("creditRequestedUsd"), 0)
    if amount <= 0:
        return
    title = "Credito solicitado"
    body = f"{client.get('businessName') or client.get('commercialName') or 'Cliente'} solicito {money_usd(amount)}."
    notify_admin(
        store,
        title,
        body,
        notification_type="credit_requested",
        priority="high",
        module="credit",
        entity_type="client",
        entity_id=client_id,
        href=notification_url("credit", q=client.get("businessName", "")),
        metadata={"clientId": client_id, "requestedUsd": amount},
        dedupe_key=f"admin-credit-requested-{client_id}-{client.get('updatedAt', client.get('createdAt', ''))}",
    )


def notify_payment_registered(store: dict, order: dict, movement: dict) -> None:
    order_id = order.get("orderId") or order.get("id", "")
    amount = money_usd(movement.get("amountUsd") or 0)
    notify_admin(
        store,
        "Abono registrado",
        f"Se registro {amount} para la orden {order_id}.",
        notification_type="payment_registered",
        priority="normal",
        module="collections",
        entity_type="order",
        entity_id=order_id,
        href=notification_url("collections", q=order_id),
        metadata={"orderId": order_id, "movementId": movement.get("id", "")},
        dedupe_key=f"admin-payment-{movement.get('id', '')}",
    )
    notify_client(
        store,
        order.get("customerId", ""),
        "Abono recibido",
        f"Wulkan registro {amount} en tu orden {order_id}.",
        notification_type="payment_registered",
        priority="normal",
        module="orders",
        entity_type="order",
        entity_id=order_id,
        deep_link=f"wulkan://orders/{order_id}",
        metadata={"orderId": order_id, "movementId": movement.get("id", "")},
        dedupe_key=f"client-payment-{movement.get('id', '')}",
    )


def notify_commission_status(store: dict, order: dict, status: str) -> None:
    if status not in {"commission_approved", "commission_paid"}:
        return
    order_id = order.get("orderId") or order.get("id", "")
    notification_type = "commission_paid" if status == "commission_paid" else "commission_approved"
    title = "Comision pagada" if status == "commission_paid" else "Comision aprobada"
    notify_seller(
        store,
        order.get("sellerId", ""),
        title,
        f"{commission_status_label(status)} por {money_usd(order.get('commissionUsd', 0))} en orden {order_id}.",
        notification_type=notification_type,
        priority="normal",
        module="commissions",
        entity_type="order",
        entity_id=order_id,
        deep_link=f"wulkan://seller/commissions/{order_id}",
        metadata={"orderId": order_id, "commissionStatus": status},
        dedupe_key=f"seller-commission-{order_id}-{status}",
    )


def notify_stock_state(store: dict, product: dict) -> None:
    enriched = enrich_inventory_product(product, store.get("orders", []), store.get("stock_movements", []))
    status = enriched.get("stockStatus")
    if status not in {"low", "out"}:
        return
    notification_type = "product_out" if status == "out" else "stock_low"
    priority = "critical" if status == "out" else "high"
    available = safe_int(enriched.get("availableStock"), 0)
    notify_role(
        store,
        "inventory",
        "Producto agotado" if status == "out" else "Stock critico",
        f"{enriched.get('sku', '')} - {enriched.get('title', '')}: {available} unidades disponibles.",
        notification_type=notification_type,
        priority=priority,
        module="stock",
        entity_type="product",
        entity_id=enriched.get("id", ""),
        href=notification_url("stock", q=enriched.get("sku", "")),
        metadata={"productId": enriched.get("id", ""), "sku": enriched.get("sku", ""), "stockStatus": status},
        dedupe_key=f"stock-{enriched.get('id', '')}-{status}",
    )


def notify_quote_accepted(store: dict, quote: dict, order: dict | None = None) -> None:
    quote_id = quote.get("id", "")
    order_id = (order or {}).get("orderId", "")
    notify_admin(
        store,
        "Cotizacion aceptada",
        f"{quote.get('quoteNumber', quote_id)} fue aceptada y puede continuar como orden.",
        notification_type="quote_accepted",
        priority="normal",
        module="quotes",
        entity_type="quote",
        entity_id=quote_id,
        href=notification_url("quotes", q=quote.get("quoteNumber", "")),
        metadata={"quoteId": quote_id, "orderId": order_id},
        dedupe_key=f"quote-accepted-{quote_id}-{order_id}",
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


def client_sales_blocker(client: dict | None, sale_type: str = "") -> str:
    if not client:
        return "Cliente no encontrado."
    if client.get("status") in CLIENT_SALE_BLOCKING_STATUSES:
        return f"Cliente no habilitado para comprar: {client_status_label(client.get('status', ''))}."
    if client.get("collectionStatus") in CLIENT_COLLECTION_BLOCKING_STATUSES:
        return f"Cliente no habilitado para comprar por cobranza: {collection_status_label(client.get('collectionStatus', ''))}."
    if sale_type in {"credit_line", "term_credit"} and client.get("creditRequestStatus") in CLIENT_CREDIT_BLOCKING_STATUSES:
        return f"Cliente no habilitado para comprar por credito: {credit_status_label(client.get('creditRequestStatus', ''))}."
    return ""


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
    enriched["receiverName"] = enriched.get("receiverName", "")
    enriched["receiverPhone"] = enriched.get("receiverPhone", "")
    enriched["carrierName"] = enriched.get("carrierName", "")
    enriched["trackingNumber"] = enriched.get("trackingNumber", "")
    enriched["estimatedDispatchAt"] = enriched.get("estimatedDispatchAt", "")
    enriched["dispatchedAt"] = enriched.get("dispatchedAt", "")
    enriched["estimatedDeliveryAt"] = enriched.get("estimatedDeliveryAt", "")
    enriched["deliveredAt"] = enriched.get("deliveredAt", "")
    enriched["deliveryEvidenceUrl"] = enriched.get("deliveryEvidenceUrl", "")
    enriched["logisticsNote"] = enriched.get("logisticsNote", "")
    enriched["logisticsOwner"] = enriched.get("logisticsOwner") or enriched.get("currentOwner") or "Despacho"
    enriched["dispatchHistory"] = sorted(enriched.get("dispatchHistory") or [], key=lambda item: item.get("createdAt", ""), reverse=True)
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
    enriched["commissionBaseUsd"] = float(enriched.get("commissionBaseUsd") or enriched.get("netUsd") or enriched.get("totalUsd") or 0)
    enriched["commissionUsd"] = float(enriched.get("commissionUsd") or 0)
    enriched["commissionStatus"] = enriched.get("commissionStatus") or "commission_pending"
    enriched["commissionStatusLabel"] = commission_status_label(enriched["commissionStatus"])
    enriched["commissionRule"] = enriched.get("commissionRule") or "sale_generated"
    enriched["commissionRuleLabel"] = commission_rule_label(enriched["commissionRule"])
    enriched["commissionGeneratedAt"] = enriched.get("commissionGeneratedAt") or enriched.get("createdAt", "")
    enriched["commissionApprovedAt"] = enriched.get("commissionApprovedAt", "")
    enriched["commissionApprovedBy"] = enriched.get("commissionApprovedBy", "")
    enriched["commissionPaidAt"] = enriched.get("commissionPaidAt", "")
    enriched["commissionPaidBy"] = enriched.get("commissionPaidBy", "")
    enriched["commissionObservation"] = enriched.get("commissionObservation", "")
    enriched["commissionHoldReason"] = enriched.get("commissionHoldReason", "")
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
            max_bytes=int(app.config.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)),
        )
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def product_payload(store: dict, existing: dict | None = None) -> dict:
    category_id = request.form.get("categoryId", "machinery-garden")
    categories = product_category_options(store) or [{"id": "uncategorized", "name": "Sin categoria"}]
    category = find_by_id(categories, category_id) or categories[0]
    sku = sanitize_text(request.form.get("sku", ""), max_length=80, allow_newlines=False).upper()
    title = sanitize_text(request.form.get("title", ""), max_length=180, allow_newlines=False)
    primary_image = sanitize_url(request.form.get("imageUrl", ""))
    image_urls = sanitize_url_list(split_lines(request.form.get("imageUrls", "")))
    pdf_urls = sanitize_url_list(split_lines(request.form.get("pdfUrls", "")))
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
        "internalCode": sanitize_text(request.form.get("internalCode", ""), max_length=80, allow_newlines=False).upper(),
        "title": title,
        "brand": sanitize_text(request.form.get("brand", "Wulkan"), max_length=120, allow_newlines=False) or "Wulkan",
        "model": sanitize_text(request.form.get("model", ""), max_length=120, allow_newlines=False),
        "unitOfSale": sanitize_text(request.form.get("unitOfSale", "unidad"), max_length=80, allow_newlines=False) or "unidad",
        "shortDescription": sanitize_text(request.form.get("shortDescription", ""), max_length=240, allow_newlines=False),
        "longDescription": sanitize_text(request.form.get("longDescription", ""), max_length=2000),
        "description": sanitize_text(request.form.get("description", ""), max_length=2000),
        "productType": request.form.get("productType", "machine"),
        "categoryId": category["id"],
        "categoryName": category["name"],
        "subCategory": sanitize_text(request.form.get("subCategory", ""), max_length=120, allow_newlines=False),
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
        "sku": sanitize_text(request.form.get("sku", ""), max_length=80, allow_newlines=False).upper(),
        "internalCode": sanitize_text(request.form.get("internalCode", ""), max_length=80, allow_newlines=False).upper(),
        "title": sanitize_text(request.form.get("title", ""), max_length=180, allow_newlines=False),
        "brand": sanitize_text(request.form.get("brand", "Wulkan"), max_length=120, allow_newlines=False),
        "model": sanitize_text(request.form.get("model", ""), max_length=120, allow_newlines=False),
        "unitOfSale": sanitize_text(request.form.get("unitOfSale", "unidad"), max_length=80, allow_newlines=False),
        "shortDescription": sanitize_text(request.form.get("shortDescription", ""), max_length=240, allow_newlines=False),
        "longDescription": sanitize_text(request.form.get("longDescription", ""), max_length=2000),
        "description": sanitize_text(request.form.get("description", ""), max_length=2000),
        "productType": request.form.get("productType", "machine"),
        "categoryId": request.form.get("categoryId", "machinery-garden"),
        "subCategory": sanitize_text(request.form.get("subCategory", ""), max_length=120, allow_newlines=False),
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
        "imageUrl": sanitize_url(request.form.get("imageUrl", "")),
        "imageUrls": sanitize_url_list(split_lines(request.form.get("imageUrls", ""))),
        "pdfUrls": sanitize_url_list(split_lines(request.form.get("pdfUrls", ""))),
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
    name = sanitize_text(request.form.get("name", ""), max_length=140, allow_newlines=False)
    uploaded_image = save_upload(request.files.get("imageFile"), "categories")
    image_url = uploaded_image or sanitize_url(request.form.get("imageUrl", "")) or (existing or {}).get("imageUrl", "")
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
        "description": sanitize_text(request.form.get("description", ""), max_length=500),
        "imageUrl": image_url,
        "icon": sanitize_text(request.form.get("icon", "bi-tags"), max_length=80, allow_newlines=False) or "bi-tags",
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
    name = sanitize_text(request.form.get("name", ""), max_length=140, allow_newlines=False)
    status = request.form.get("status", "active")
    return {
        "name": name,
        "slug": category_slug(request.form.get("slug", "").strip() or name),
        "description": sanitize_text(request.form.get("description", ""), max_length=500),
        "imageUrl": sanitize_url(request.form.get("imageUrl", "")),
        "icon": sanitize_text(request.form.get("icon", "bi-tags"), max_length=80, allow_newlines=False) or "bi-tags",
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
        if value in payment_term_options() and value not in terms:
            terms.append(value)
    return terms or [0]


def admin_user_payload(existing: dict | None = None) -> dict:
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    now = utc_now()
    first_name = sanitize_text(request.form.get("firstName", ""), max_length=80, allow_newlines=False)
    last_name = sanitize_text(request.form.get("lastName", ""), max_length=80, allow_newlines=False)
    display_name = sanitize_text(request.form.get("name", ""), max_length=160, allow_newlines=False)
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
        "sellerCode": sanitize_text(request.form.get("sellerCode", ""), max_length=80, allow_newlines=False).upper(),
        "sellerZone": sanitize_text(request.form.get("sellerZone", ""), max_length=120, allow_newlines=False),
        "sellerTerritory": sanitize_text(request.form.get("sellerTerritory", ""), max_length=120, allow_newlines=False),
        "sellerSupervisor": sanitize_text(request.form.get("sellerSupervisor", ""), max_length=160, allow_newlines=False),
        "phone": sanitize_text(request.form.get("phone", ""), max_length=60, allow_newlines=False),
        "hiredAt": sanitize_text(request.form.get("hiredAt", ""), max_length=32, allow_newlines=False),
        "mobileAccessEnabled": "on" in mobile_access_values if mobile_access_values else bool((existing or {}).get("mobileAccessEnabled", True)),
        "internalNotes": sanitize_text(request.form.get("internalNotes", ""), max_length=1000),
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
        "legalName": sanitize_text(request.form.get("legalName", ""), max_length=180, allow_newlines=False),
        "commercialName": sanitize_text(request.form.get("commercialName", ""), max_length=180, allow_newlines=False),
        "businessName": sanitize_text(request.form.get("businessName", ""), max_length=180, allow_newlines=False),
        "taxId": sanitize_text(request.form.get("taxId", ""), max_length=60, allow_newlines=False),
        "contactName": sanitize_text(request.form.get("contactName", ""), max_length=160, allow_newlines=False),
        "administrativeContact": sanitize_text(request.form.get("administrativeContact", ""), max_length=160, allow_newlines=False),
        "receivingContact": sanitize_text(request.form.get("receivingContact", ""), max_length=160, allow_newlines=False),
        "phone": sanitize_text(request.form.get("phone", ""), max_length=60, allow_newlines=False),
        "whatsapp": sanitize_text(request.form.get("whatsapp", ""), max_length=60, allow_newlines=False),
        "email": email,
        "clientType": request.form.get("clientType", "ferretero"),
        "clientCategory": request.form.get("clientCategory", "standard"),
        "priceList": request.form.get("priceList", "b2b"),
        "authorizedDiscountPercent": float(request.form.get("authorizedDiscountPercent") or 0),
        "status": request.form.get("status", "active"),
        "address": sanitize_text(request.form.get("address", ""), max_length=400),
        "fiscalAddress": sanitize_text(request.form.get("fiscalAddress", ""), max_length=400),
        "shippingAddress": sanitize_text(request.form.get("shippingAddress", ""), max_length=400),
        "country": sanitize_text(request.form.get("country", "VE"), max_length=4, allow_newlines=False) or "VE",
        "state": sanitize_text(request.form.get("state", ""), max_length=120, allow_newlines=False),
        "city": sanitize_text(request.form.get("city", ""), max_length=120, allow_newlines=False),
        "deliveryZone": sanitize_text(request.form.get("deliveryZone", ""), max_length=120, allow_newlines=False),
        "assignedSellerId": seller_id,
        "assignedSellerName": seller_name,
        "defaultSaleType": request.form.get("defaultSaleType", "cash"),
        "allowedPaymentTermsDays": selected_payment_terms(),
        "collectionStatus": request.form.get("collectionStatus", "without_debt"),
        "creditRiskLevel": request.form.get("creditRiskLevel", "low"),
        "creditScore": int(float(request.form.get("creditScore") or (existing or {}).get("creditScore") or 0)),
        "creditManagerNote": sanitize_text(request.form.get("creditManagerNote", (existing or {}).get("creditManagerNote", "")), max_length=1200),
        "creditReviewedBy": (existing or {}).get("creditReviewedBy", ""),
        "creditReviewedAt": (existing or {}).get("creditReviewedAt", ""),
        "creditRequestStatus": requested_credit_status,
        "creditRequestedUsd": credit_requested,
        "creditEnabled": credit_enabled,
        "creditLimitUsd": credit_limit,
        "creditUsedUsd": float(request.form.get("creditUsedUsd") or (existing or {}).get("creditUsedUsd") or 0),
        "paymentTermsDays": payment_terms_days,
        "notes": sanitize_text(request.form.get("notes", ""), max_length=1500),
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
        "payment_terms": payment_term_options(store),
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
        "payment_terms": payment_term_options(store),
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


def next_quote_number(client_name: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = secrets.token_hex(2).upper()
    seed = re.sub(r"[^A-Za-z0-9]+", "", client_name or "Wulkan")[:8].upper()
    return f"COT-{stamp}-{seed}-{suffix}"


def append_quote_history(quote: dict, status: str, note: str = "") -> None:
    quote.setdefault("history", []).append(
        {
            "status": status,
            "label": quote_status_label(status),
            "note": note,
            "adminUserId": session.get("admin_user_id", ""),
            "adminName": session.get("admin_name", "Sistema"),
            "createdAt": utc_now(),
        }
    )


def quote_version_snapshot(quote: dict, note: str = "") -> dict:
    return {
        "version": quote.get("version", 1),
        "status": quote.get("status", "draft"),
        "totalUsd": quote.get("totalUsd", 0),
        "items": copy.deepcopy(quote.get("items") or []),
        "comment": quote.get("comment", ""),
        "internalComment": quote.get("internalComment", ""),
        "note": note,
        "createdAt": utc_now(),
        "createdBy": session.get("admin_name", "Sistema"),
    }


def quote_items_from_form(store: dict) -> tuple[list[dict], float, float, str]:
    items: list[dict] = []
    gross_usd = 0.0
    total_usd = 0.0
    for index in range(1, 9):
        product_id = request.form.get(f"productId{index}", "").strip()
        quantity = safe_int(request.form.get(f"quantity{index}"), 0)
        if not product_id or quantity <= 0:
            continue
        product = find_by_id(store.get("products", []), product_id)
        if not product:
            return [], 0.0, 0.0, f"Producto {index} no encontrado."
        unit_price = safe_float(
            request.form.get(f"unitPriceUsd{index}"),
            safe_float(product.get("b2bPriceUsd"), safe_float(product.get("publicPriceUsd"), 0)),
        )
        discount_percent = max(0.0, min(100.0, safe_float(request.form.get(f"discountPercent{index}"), 0)))
        line_gross = round(unit_price * quantity, 2)
        line_discount = round(line_gross * discount_percent / 100, 2)
        line_total = round(max(0.0, line_gross - line_discount), 2)
        gross_usd += line_gross
        total_usd += line_total
        items.append(
            {
                "productId": product.get("id", ""),
                "sku": product.get("sku", ""),
                "title": product.get("title", "Producto Wulkan"),
                "quantity": quantity,
                "unitPriceUsd": unit_price,
                "discountPercent": discount_percent,
                "lineGrossUsd": line_gross,
                "lineDiscountUsd": line_discount,
                "lineTotalUsd": line_total,
                "imageUrl": product.get("imageUrl", ""),
                "requiresQuote": bool(product.get("requiresQuote")),
                "requiresTechnicalValidation": bool(product.get("requiresTechnicalValidation")),
            }
        )
    return items, round(gross_usd, 2), round(total_usd, 2), ""


def quote_payload_from_form(store: dict, existing: dict | None = None) -> tuple[dict | None, str]:
    client_id = request.form.get("clientId", "").strip()
    client = find_by_id(store.get("clients", []), client_id)
    if not can_access_client_record(client):
        return None, "Cliente no encontrado o fuera de tu alcance."
    items, gross_usd, total_usd, error = quote_items_from_form(store)
    if error:
        return None, error
    if not items:
        return None, "Agrega al menos un producto a la cotizacion."

    exchange_rate = safe_float(request.form.get("exchangeRateUsdVes"), current_rate())
    seller_id = client.get("assignedSellerId", "") if client else ""
    seller_name = client.get("assignedSellerName", "") or seller_name_for(store, seller_id)
    status = request.form.get("status", (existing or {}).get("status", "draft"))
    if status not in dict(QUOTE_STATUS_OPTIONS):
        status = "draft"
    sale_type = request.form.get("saleType", (existing or {}).get("saleType", "cash"))
    if sale_type not in dict(SALE_TYPE_OPTIONS):
        sale_type = "cash"
    payment_term_days = safe_int(request.form.get("paymentTermDays"), safe_int((existing or {}).get("paymentTermDays"), 0))
    if sale_type == "cash":
        payment_term_days = 0

    quote = copy.deepcopy(existing or {})
    now = utc_now()
    if not quote:
        quote["id"] = next_id("quote", client.get("businessName", "wulkan"))
        quote["quoteNumber"] = next_quote_number(client.get("businessName", "Wulkan"))
        quote["version"] = 1
        quote["versions"] = []
        quote["history"] = []
        quote["createdAt"] = now
        quote["createdById"] = session.get("admin_user_id", "")
        quote["createdByName"] = session.get("admin_name", "Sistema")
    quote.update(
        {
            "clientId": client["id"],
            "client": {
                "id": client["id"],
                "name": client.get("businessName", ""),
                "taxId": client.get("taxId", ""),
                "email": client.get("email", ""),
                "phone": client.get("phone", ""),
                "address": client.get("address", ""),
                "city": client.get("city", ""),
                "state": client.get("state", ""),
            },
            "sellerId": seller_id,
            "sellerName": seller_name,
            "items": items,
            "grossUsd": gross_usd,
            "discountUsd": round(max(0.0, gross_usd - total_usd), 2),
            "totalUsd": total_usd,
            "totalVes": round(total_usd * exchange_rate, 2),
            "exchangeRateUsdVes": exchange_rate,
            "saleType": sale_type,
            "paymentTermDays": payment_term_days,
            "validUntil": request.form.get("validUntil", "").strip(),
            "status": status,
            "comment": request.form.get("comment", "").strip(),
            "internalComment": request.form.get("internalComment", "").strip(),
            "updatedAt": now,
        }
    )
    return quote, ""


def enrich_quote(quote: dict) -> dict:
    enriched = dict(quote)
    status = enriched.get("status", "draft")
    valid_until = enriched.get("validUntil", "")
    if status not in {"accepted", "rejected", "converted"} and valid_until:
        try:
            if datetime.strptime(valid_until, "%Y-%m-%d").date() < datetime.now(timezone.utc).date():
                status = "expired"
        except ValueError:
            pass
    enriched["displayStatus"] = status
    enriched["statusLabel"] = quote_status_label(status)
    enriched["rawStatusLabel"] = quote_status_label(enriched.get("status", "draft"))
    enriched["saleTypeLabel"] = sale_type_label(enriched.get("saleType", "cash"))
    enriched["clientName"] = (enriched.get("client") or {}).get("name", "Cliente Wulkan")
    enriched["sellerName"] = enriched.get("sellerName") or "Sin vendedor"
    enriched["itemsCount"] = sum(int(item.get("quantity") or 0) for item in enriched.get("items") or [])
    enriched["versions"] = sorted(enriched.get("versions") or [], key=lambda item: item.get("createdAt", ""), reverse=True)
    enriched["history"] = sorted(enriched.get("history") or [], key=lambda item: item.get("createdAt", ""), reverse=True)
    return enriched


def quote_to_order_payload(quote: dict) -> dict:
    items = []
    for item in quote.get("items") or []:
        quantity = safe_int(item.get("quantity"), 0)
        if quantity <= 0:
            continue
        unit_price = safe_float(item.get("lineTotalUsd"), 0) / quantity if quantity else safe_float(item.get("unitPriceUsd"), 0)
        items.append(
            {
                "productId": item.get("productId", ""),
                "sku": item.get("sku", ""),
                "title": item.get("title", ""),
                "quantity": quantity,
                "unitPriceUsd": round(unit_price, 2),
                "imageUrl": item.get("imageUrl", ""),
            }
        )
    client = quote.get("client") or {}
    return {
        "customerId": quote.get("clientId", ""),
        "items": items,
        "saleType": quote.get("saleType", "cash"),
        "paymentTermDays": quote.get("paymentTermDays", 0),
        "salesChannel": "admin",
        "shippingAddress": client.get("address", ""),
        "customerComment": quote.get("comment", ""),
        "internalComment": f"Orden convertida desde cotizacion {quote.get('quoteNumber', '')}. {quote.get('internalComment', '')}".strip(),
        "notes": quote.get("internalComment", ""),
        "preview": {
            "grossUsd": quote.get("grossUsd", quote.get("totalUsd", 0)),
            "subtotalUsd": quote.get("totalUsd", 0),
            "totalUsd": quote.get("totalUsd", 0),
            "totalVes": quote.get("totalVes", 0),
            "exchangeRateUsdVes": quote.get("exchangeRateUsdVes", current_rate()),
        },
    }


def quote_form_context(store: dict, quote: dict | None = None, error: str = "") -> dict:
    clients_list = [
        enrich_client(client, store.get("orders", []), store.get("credit_movements", []))
        for client in visible_clients_for_current_user(store)
        if client.get("status") in {"active", "prospect", "review"}
    ]
    products = [
        enrich_inventory_product(product, store.get("orders", []))
        for product in store.get("products", [])
        if product.get("status") == "active"
    ]
    default_valid_until = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
    return {
        "quote": enrich_quote(quote) if quote else None,
        "clients": sorted(clients_list, key=lambda item: item.get("businessName", "")),
        "products": sorted(products, key=lambda item: item.get("title", "")),
        "status_options": QUOTE_STATUS_OPTIONS,
        "sale_type_options": SALE_TYPE_OPTIONS,
        "payment_terms": payment_term_options(store),
        "default_valid_until": default_valid_until,
        "error": error,
    }


def quotes_page_context(store: dict, error: str = "") -> dict:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "status": request.args.get("status", "").strip(),
        "seller": request.args.get("seller", "").strip(),
        "client": request.args.get("client", "").strip(),
    }
    all_quotes = [
        enrich_quote(quote)
        for quote in sorted(visible_quotes_for_current_user(store), key=lambda item: item.get("createdAt", ""), reverse=True)
    ]
    quotes_list = all_quotes
    if filters["q"]:
        quotes_list = [
            quote for quote in quotes_list
            if filters["q"] in " ".join(
                [
                    quote.get("quoteNumber", ""),
                    quote.get("clientName", ""),
                    quote.get("sellerName", ""),
                    quote.get("comment", ""),
                    quote.get("internalComment", ""),
                    " ".join(item.get("sku", "") for item in quote.get("items") or []),
                ]
            ).lower()
        ]
    if filters["status"]:
        quotes_list = [quote for quote in quotes_list if quote.get("displayStatus") == filters["status"] or quote.get("status") == filters["status"]]
    if filters["seller"]:
        quotes_list = [quote for quote in quotes_list if quote.get("sellerId") == filters["seller"]]
    if filters["client"]:
        quotes_list = [quote for quote in quotes_list if quote.get("clientId") == filters["client"]]

    status_counts: dict[str, int] = {}
    seller_totals: dict[str, float] = {}
    for quote in all_quotes:
        status_counts[quote.get("statusLabel", "Sin estado")] = status_counts.get(quote.get("statusLabel", "Sin estado"), 0) + 1
        seller = quote.get("sellerName") or "Sin vendedor"
        seller_totals[seller] = seller_totals.get(seller, 0.0) + float(quote.get("totalUsd") or 0)
    sellers = [
        seller
        for seller in store.get("admin_users", [])
        if seller.get("role") == "sales" and seller.get("status") != "deleted"
    ]
    metrics = {
        "quotes": len(all_quotes),
        "filtered": len(quotes_list),
        "open": sum(1 for quote in all_quotes if quote.get("displayStatus") in {"draft", "sent", "viewed", "negotiation"}),
        "accepted": sum(1 for quote in all_quotes if quote.get("displayStatus") == "accepted"),
        "converted": sum(1 for quote in all_quotes if quote.get("displayStatus") == "converted"),
        "total": round(sum(float(quote.get("totalUsd") or 0) for quote in quotes_list), 2),
    }
    return {
        "quotes": quotes_list,
        "metrics": metrics,
        "filters": filters,
        "status_options": QUOTE_STATUS_OPTIONS,
        "seller_options": sorted(sellers, key=lambda item: item.get("name", "")),
        "client_options": sorted(visible_clients_for_current_user(store), key=lambda item: item.get("businessName", "")),
        "quote_charts": {
            "status": graphify_from_pairs(list(status_counts.items()), 8),
            "seller": graphify_from_pairs(list(seller_totals.items()), 6),
        },
        "can_create_quotes": can_module_action("quotes", "create"),
        "can_edit_quotes": can_module_action("quotes", "edit"),
        "can_export_quotes": can_module_action("quotes", "export"),
        "can_convert_quotes": can_module_action("quotes", "edit") or can_module_action("orders", "create"),
        "error": error,
    }


def crm_record_payload_from_form(store: dict, existing: dict | None = None) -> tuple[dict | None, str]:
    title = request.form.get("title", "").strip()
    if not title:
        return None, "El titulo del seguimiento CRM es obligatorio."
    record_type = request.form.get("recordType", (existing or {}).get("recordType", "lead"))
    if record_type not in dict(CRM_RECORD_TYPE_OPTIONS):
        record_type = "lead"
    pipeline_stage = request.form.get("pipelineStage", (existing or {}).get("pipelineStage", "new_lead"))
    if pipeline_stage not in dict(CRM_PIPELINE_STAGE_OPTIONS):
        pipeline_stage = "new_lead"
    status = request.form.get("status", (existing or {}).get("status", "active"))
    if status not in dict(CRM_STATUS_OPTIONS):
        status = "active"

    client_id = request.form.get("clientId", "").strip()
    client = find_by_id(store.get("clients", []), client_id) if client_id else None
    if client_id and not can_access_client_record(client):
        return None, "Cliente vinculado no encontrado o fuera de tu alcance."

    seller_id = request.form.get("sellerId", "").strip()
    if client and not seller_id:
        seller_id = client.get("assignedSellerId", "")
    seller = find_by_id(store.get("admin_users", []), seller_id) if seller_id else None
    seller_name = (seller or {}).get("name", "") or (client or {}).get("assignedSellerName", "")

    record = copy.deepcopy(existing or {})
    now = utc_now()
    if not record:
        record["id"] = next_id("crm", title)
        record["activities"] = []
        record["createdAt"] = now
        record["createdById"] = session.get("admin_user_id", "")
        record["createdByName"] = session.get("admin_name", "Sistema")
    record.update(
        {
            "title": title,
            "recordType": record_type,
            "pipelineStage": pipeline_stage,
            "status": status,
            "clientId": (client or {}).get("id", ""),
            "clientName": (client or {}).get("businessName", request.form.get("clientName", "").strip()),
            "sellerId": seller_id,
            "sellerName": seller_name,
            "contactName": request.form.get("contactName", "").strip() or (client or {}).get("contactName", ""),
            "phone": request.form.get("phone", "").strip() or (client or {}).get("phone", ""),
            "email": request.form.get("email", "").strip() or (client or {}).get("email", ""),
            "state": request.form.get("state", "").strip() or (client or {}).get("state", ""),
            "city": request.form.get("city", "").strip() or (client or {}).get("city", ""),
            "source": request.form.get("source", "").strip(),
            "estimatedValueUsd": round(max(0.0, safe_float(request.form.get("estimatedValueUsd"), 0)), 2),
            "probabilityPercent": max(0, min(100, safe_int(request.form.get("probabilityPercent"), 0))),
            "expectedCloseAt": request.form.get("expectedCloseAt", "").strip(),
            "nextActionAt": request.form.get("nextActionAt", "").strip(),
            "description": request.form.get("description", "").strip(),
            "lossReason": request.form.get("lossReason", "").strip(),
            "updatedAt": now,
        }
    )
    return record, ""


def append_crm_activity(record: dict, activity_type: str, note: str, next_action_at: str = "") -> None:
    if activity_type not in dict(CRM_ACTIVITY_TYPE_OPTIONS):
        activity_type = "note"
    now = utc_now()
    record.setdefault("activities", []).append(
        {
            "id": next_id("crm-act", record.get("title", "actividad")),
            "type": activity_type,
            "typeLabel": crm_activity_type_label(activity_type),
            "note": note,
            "nextActionAt": next_action_at,
            "createdById": session.get("admin_user_id", ""),
            "createdByName": session.get("admin_name", "Sistema"),
            "createdAt": now,
        }
    )
    record["lastActivityAt"] = now
    if next_action_at:
        record["nextActionAt"] = next_action_at
    record["updatedAt"] = now


def enrich_crm_record(record: dict) -> dict:
    enriched = dict(record)
    enriched["recordTypeLabel"] = crm_record_type_label(enriched.get("recordType", "lead"))
    enriched["pipelineStageLabel"] = crm_stage_label(enriched.get("pipelineStage", "new_lead"))
    enriched["statusLabel"] = crm_status_label(enriched.get("status", "active"))
    enriched["clientName"] = enriched.get("clientName") or "Sin cliente vinculado"
    enriched["sellerName"] = enriched.get("sellerName") or "Sin vendedor"
    enriched["weightedValueUsd"] = round(
        safe_float(enriched.get("estimatedValueUsd"), 0) * safe_int(enriched.get("probabilityPercent"), 0) / 100,
        2,
    )
    enriched["activities"] = sorted(enriched.get("activities") or [], key=lambda item: item.get("createdAt", ""), reverse=True)
    enriched["activitiesCount"] = len(enriched["activities"])
    next_action = enriched.get("nextActionAt", "")
    if next_action:
        try:
            next_date = datetime.strptime(next_action[:10], "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            if next_date < today:
                enriched["nextActionStatus"] = "overdue"
            elif next_date == today:
                enriched["nextActionStatus"] = "due_soon"
            else:
                enriched["nextActionStatus"] = "current"
        except ValueError:
            enriched["nextActionStatus"] = "without_due_date"
    else:
        enriched["nextActionStatus"] = "without_due_date"
    return enriched


def crm_page_context(store: dict, error: str = "") -> dict:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "stage": request.args.get("stage", "").strip(),
        "type": request.args.get("type", "").strip(),
        "seller": request.args.get("seller", "").strip(),
        "status": request.args.get("status", "").strip(),
        "next": request.args.get("next", "").strip(),
    }
    all_records = [
        enrich_crm_record(record)
        for record in sorted(visible_crm_records_for_current_user(store), key=lambda item: item.get("updatedAt", ""), reverse=True)
        if record.get("status") != "deleted"
    ]
    records = all_records
    if filters["q"]:
        records = [
            record for record in records
            if filters["q"] in " ".join(
                [
                    record.get("title", ""),
                    record.get("clientName", ""),
                    record.get("sellerName", ""),
                    record.get("contactName", ""),
                    record.get("phone", ""),
                    record.get("email", ""),
                    record.get("description", ""),
                ]
            ).lower()
        ]
    if filters["stage"]:
        records = [record for record in records if record.get("pipelineStage") == filters["stage"]]
    if filters["type"]:
        records = [record for record in records if record.get("recordType") == filters["type"]]
    if filters["seller"]:
        records = [record for record in records if record.get("sellerId") == filters["seller"]]
    if filters["status"]:
        records = [record for record in records if record.get("status") == filters["status"]]
    if filters["next"]:
        records = [record for record in records if record.get("nextActionStatus") == filters["next"]]

    stage_counts: dict[str, int] = {}
    value_by_stage: dict[str, float] = {}
    for record in all_records:
        stage = record.get("pipelineStageLabel", "Sin etapa")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        value_by_stage[stage] = value_by_stage.get(stage, 0.0) + safe_float(record.get("weightedValueUsd"), 0)
    sellers = [
        seller for seller in store.get("admin_users", [])
        if seller.get("role") == "sales" and seller.get("status") != "deleted"
    ]
    metrics = {
        "records": len(all_records),
        "filtered": len(records),
        "open": sum(1 for record in all_records if record.get("pipelineStage") not in {"won", "lost", "inactive"}),
        "won": sum(1 for record in all_records if record.get("pipelineStage") == "won"),
        "overdue": sum(1 for record in all_records if record.get("nextActionStatus") == "overdue"),
        "weighted": round(sum(safe_float(record.get("weightedValueUsd"), 0) for record in records), 2),
    }
    return {
        "records": records,
        "metrics": metrics,
        "filters": filters,
        "record_type_options": CRM_RECORD_TYPE_OPTIONS,
        "pipeline_stage_options": CRM_PIPELINE_STAGE_OPTIONS,
        "activity_type_options": CRM_ACTIVITY_TYPE_OPTIONS,
        "crm_status_options": CRM_STATUS_OPTIONS,
        "seller_options": sorted(sellers, key=lambda item: item.get("name", "")),
        "client_options": sorted(visible_clients_for_current_user(store), key=lambda item: item.get("businessName", "")),
        "crm_charts": {
            "stage": graphify_from_pairs(list(stage_counts.items()), 8),
            "value": graphify_from_pairs(list(value_by_stage.items()), 8),
        },
        "can_create_crm": can_module_action("crm", "create"),
        "can_edit_crm": can_module_action("crm", "edit"),
        "can_export_crm": can_module_action("crm", "export"),
        "can_delete_crm": can_delete_data() and can_module_action("crm", "delete"),
        "error": error,
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


def commission_release_blockers(order: dict, client: dict | None = None) -> list[str]:
    blockers: list[str] = []
    if order.get("status") in {"cancelled", "rejected"}:
        blockers.append("Orden anulada o rechazada")
    if float(order.get("balanceUsd") or 0) > 0:
        blockers.append("Venta con saldo pendiente")
    if order.get("dispatchStatus") in {"failed", "returned"}:
        blockers.append("Despacho fallido o producto devuelto")
    if client:
        collection_status = client.get("collectionStatus", "")
        overdue_balance = float(client.get("overdueBalanceUsd") or 0)
        if collection_status in {"blocked", "critical", "uncollectible"} or overdue_balance > 0:
            blockers.append("Cliente con mora o cobranza critica")
    return blockers


def enrich_commission_order(order: dict, client_lookup: dict[str, dict]) -> dict:
    enriched = dict(order)
    client = client_lookup.get(enriched.get("customerId", ""))
    blockers = commission_release_blockers(enriched, client)
    enriched["commissionReleaseBlockers"] = blockers
    enriched["commissionCanBePaid"] = not blockers and enriched.get("commissionStatus") == "commission_approved"
    enriched["commissionBlocked"] = bool(blockers)
    return enriched


def commissions_page_context(store: dict, error: str = "") -> dict:
    movements = store.get("credit_movements", [])
    filters = {
        "q": request.args.get("q", "").strip(),
        "status": request.args.get("status", "").strip(),
        "seller": request.args.get("seller", "").strip(),
        "rule": request.args.get("rule", "").strip(),
        "release": request.args.get("release", "").strip(),
    }
    client_lookup = {
        client.get("id", ""): enrich_client(client, store.get("orders", []), movements)
        for client in store.get("clients", [])
    }
    all_orders = [
        enrich_commission_order(enrich_order(order, movements), client_lookup)
        for order in sorted(visible_orders_for_current_user(store), key=lambda item: item.get("createdAt", ""), reverse=True)
        if float(order.get("commissionUsd") or 0) > 0
    ]

    def matches(order: dict) -> bool:
        query = filters["q"].lower()
        if query:
            haystack = " ".join(
                [
                    str(order.get("orderId", "")),
                    str(order.get("sellerName", "")),
                    str(order.get("customerName", "")),
                    str(order.get("customerId", "")),
                ]
            ).lower()
            if query not in haystack:
                return False
        if filters["status"] and order.get("commissionStatus") != filters["status"]:
            return False
        if filters["seller"] and order.get("sellerId") != filters["seller"]:
            return False
        if filters["rule"] and order.get("commissionRule") != filters["rule"]:
            return False
        if filters["release"] == "blocked" and not order.get("commissionBlocked"):
            return False
        if filters["release"] == "payable" and not order.get("commissionCanBePaid"):
            return False
        return True

    orders = [order for order in all_orders if matches(order)]
    status_totals = {
        key: round(sum(float(order.get("commissionUsd") or 0) for order in orders if order.get("commissionStatus") == key), 2)
        for key, _label in COMMISSION_STATUS_OPTIONS
    }
    seller_totals: dict[str, float] = {}
    rule_totals: dict[str, float] = {}
    for order in orders:
        seller = order.get("sellerName") or "Sin vendedor"
        rule = order.get("commissionRuleLabel") or "Regla general"
        value = float(order.get("commissionUsd") or 0)
        seller_totals[seller] = seller_totals.get(seller, 0.0) + value
        rule_totals[rule] = rule_totals.get(rule, 0.0) + value
    metrics = {
        "pending": status_totals.get("commission_pending", 0),
        "review": status_totals.get("commission_review", 0),
        "approved": status_totals.get("commission_approved", 0),
        "paid": status_totals.get("commission_paid", 0),
        "withheld": status_totals.get("commission_withheld", 0),
        "cancelled": status_totals.get("commission_cancelled", 0),
        "blocked_count": sum(1 for order in orders if order.get("commissionBlocked")),
        "payable_count": sum(1 for order in orders if order.get("commissionCanBePaid")),
    }
    return {
        "orders": orders,
        "all_orders": all_orders,
        "metrics": metrics,
        "filters": filters,
        "status_options": COMMISSION_STATUS_OPTIONS,
        "rule_options": COMMISSION_RULE_OPTIONS,
        "seller_options": sorted(store.get("sellers", []), key=lambda item: item.get("name", "")),
        "commission_charts": {
            "status": graphify_from_pairs([(commission_status_label(key), value) for key, value in status_totals.items()], 8),
            "seller": graphify_from_pairs(list(seller_totals.items()), 8),
            "rule": graphify_from_pairs(list(rule_totals.items()), 8),
        },
        "can_manage_commissions": role_allowed(COMMISSION_MANAGEMENT_ROLES),
        "can_export_commissions": can_module_action("commissions", "export"),
        "error": error,
    }


def reports_filters_from_request() -> dict[str, str]:
    report_type = request.args.get("type", "commercial").strip() or "commercial"
    if report_type not in dict(REPORT_TYPE_OPTIONS):
        report_type = "commercial"
    return {
        "type": report_type,
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
        "seller": request.args.get("seller", "").strip(),
        "client": request.args.get("client", "").strip(),
        "category": request.args.get("category", "").strip(),
        "product": request.args.get("product", "").strip(),
        "order_status": request.args.get("order_status", "").strip(),
    }


def report_orders(store: dict, filters: dict[str, str]) -> list[dict]:
    movements = store.get("credit_movements", [])
    products_by_id, products_by_sku = product_lookup_maps(store.get("products", []))
    dashboard_filters = {
        "date_from": filters.get("date_from", ""),
        "date_to": filters.get("date_to", ""),
        "seller": filters.get("seller", ""),
        "client": filters.get("client", ""),
        "category": filters.get("category", ""),
        "product": filters.get("product", ""),
        "order_status": filters.get("order_status", ""),
        "credit_status": "",
        "collection_status": "",
        "dispatch_status": "",
        "sale_type": "",
        "branch": "",
    }
    orders = [
        enrich_order(order, movements)
        for order in visible_orders_for_current_user(store)
    ]
    return [
        order
        for order in orders
        if order_matches_dashboard_filters(order, dashboard_filters, products_by_id, products_by_sku)
    ]


def reports_product_lines(order: dict, products_by_id: dict[str, dict], products_by_sku: dict[str, dict]) -> list[dict]:
    lines: list[dict] = []
    for item in order.get("items") or []:
        product = products_by_id.get(item.get("productId", "")) or products_by_sku.get(item.get("sku", "")) or {}
        lines.append(
            {
                "sku": item.get("sku") or product.get("sku", ""),
                "title": item.get("title") or product.get("title", ""),
                "category": product.get("categoryName") or "Sin categoria",
                "quantity": safe_int(item.get("quantity"), 0),
                "lineTotalUsd": safe_float(item.get("lineTotalUsd"), 0),
            }
        )
    return lines


def report_columns_for(report_type: str) -> list[tuple[str, str]]:
    columns = {
        "commercial": [
            ("fecha", "Fecha"),
            ("orden", "Orden"),
            ("cliente", "Cliente"),
            ("vendedor", "Vendedor"),
            ("tipo_venta", "Tipo venta"),
            ("estado", "Estado"),
            ("items", "Items"),
            ("total_usd", "Total USD"),
            ("abonado_usd", "Abonado USD"),
            ("saldo_usd", "Saldo USD"),
        ],
        "finance": [
            ("vence", "Vence"),
            ("orden", "Orden"),
            ("cliente", "Cliente"),
            ("vendedor", "Vendedor"),
            ("condicion", "Condicion"),
            ("estado_cobranza", "Cobranza"),
            ("total_usd", "Total USD"),
            ("abonado_usd", "Abonado USD"),
            ("saldo_usd", "Saldo USD"),
            ("ultimo_abono", "Ultimo abono"),
        ],
        "inventory": [
            ("sku", "SKU"),
            ("producto", "Producto"),
            ("categoria", "Categoria"),
            ("estado", "Estado"),
            ("stock", "Stock"),
            ("reservado", "Reservado"),
            ("disponible", "Disponible"),
            ("rotacion", "Rotacion"),
            ("precio_usd", "Precio USD"),
            ("valor_stock_usd", "Valor stock USD"),
        ],
        "sellers": [
            ("vendedor", "Vendedor"),
            ("zona", "Zona"),
            ("clientes", "Clientes"),
            ("ordenes", "Ordenes"),
            ("ventas_usd", "Ventas USD"),
            ("ticket_promedio_usd", "Ticket promedio USD"),
            ("meta_usd", "Meta USD"),
            ("avance_meta", "Avance meta"),
            ("comision_pendiente_usd", "Comision pendiente USD"),
            ("comision_pagada_usd", "Comision pagada USD"),
        ],
    }
    return columns.get(report_type, columns["commercial"])


def build_report_rows(store: dict, filters: dict[str, str], orders: list[dict]) -> list[dict]:
    report_type = filters["type"]
    products_by_id, products_by_sku = product_lookup_maps(store.get("products", []))
    if report_type == "commercial":
        rows = []
        for order in sorted(orders, key=lambda item: item.get("createdAt", ""), reverse=True):
            lines = reports_product_lines(order, products_by_id, products_by_sku)
            rows.append(
                {
                    "fecha": order.get("createdAt", ""),
                    "orden": order.get("orderId", ""),
                    "cliente": order.get("customerName", ""),
                    "vendedor": order.get("sellerName", ""),
                    "tipo_venta": order.get("saleTypeLabel", ""),
                    "estado": order.get("statusLabel", ""),
                    "items": " | ".join(f"{line['sku']} x{line['quantity']}" for line in lines),
                    "total_usd": round(safe_float(order.get("totalUsd"), 0), 2),
                    "abonado_usd": round(safe_float(order.get("paidUsd"), 0), 2),
                    "saldo_usd": round(safe_float(order.get("balanceUsd"), 0), 2),
                }
            )
        return rows
    if report_type == "finance":
        return [
            {
                "vence": order.get("dueDate", "") or "Sin plazo",
                "orden": order.get("orderId", ""),
                "cliente": order.get("customerName", ""),
                "vendedor": order.get("sellerName", ""),
                "condicion": order.get("saleTypeLabel", ""),
                "estado_cobranza": order.get("collectionStatusLabel", ""),
                "total_usd": round(safe_float(order.get("totalUsd"), 0), 2),
                "abonado_usd": round(safe_float(order.get("paidUsd"), 0), 2),
                "saldo_usd": round(safe_float(order.get("balanceUsd"), 0), 2),
                "ultimo_abono": order.get("lastPaymentAt", ""),
            }
            for order in sorted(orders, key=lambda item: (item.get("dueDate", ""), item.get("createdAt", "")))
            if safe_float(order.get("balanceUsd"), 0) > 0
        ]
    if report_type == "inventory":
        products = [enrich_product(product) for product in store.get("products", [])]
        if filters.get("category"):
            products = [product for product in products if product.get("categoryId") == filters["category"]]
        if filters.get("product"):
            products = [product for product in products if product.get("id") == filters["product"]]
        return [
            {
                "sku": product.get("sku", ""),
                "producto": product.get("title", ""),
                "categoria": product.get("categoryName", ""),
                "estado": product.get("statusLabel", ""),
                "stock": safe_int(product.get("stock"), 0),
                "reservado": safe_int(product.get("reserved"), 0),
                "disponible": max(0, safe_int(product.get("stock"), 0) - safe_int(product.get("reserved"), 0)),
                "rotacion": safe_int(product.get("rotationLast30Days"), 0),
                "precio_usd": round(safe_float(product.get("publicPriceUsd"), 0), 2),
                "valor_stock_usd": round(max(0, safe_int(product.get("stock"), 0) - safe_int(product.get("reserved"), 0)) * safe_float(product.get("publicPriceUsd"), 0), 2),
            }
            for product in sorted(products, key=lambda item: (item.get("categoryName", ""), item.get("title", "")))
        ]
    sellers = [enrich_seller(store, seller) for seller in store.get("sellers", []) if seller.get("status") != "deleted"]
    if filters.get("seller"):
        sellers = [seller for seller in sellers if seller.get("id") == filters["seller"]]
    return [
        {
            "vendedor": seller.get("name", ""),
            "zona": seller.get("zone", ""),
            "clientes": seller.get("clientsCount", 0),
            "ordenes": seller.get("ordersCount", 0),
            "ventas_usd": round(safe_float(seller.get("salesUsd"), 0), 2),
            "ticket_promedio_usd": round(safe_float(seller.get("ticketAverageUsd"), 0), 2),
            "meta_usd": round(safe_float(seller.get("salesGoalUsd"), 0), 2),
            "avance_meta": f"{seller.get('goalProgressPercent', 0)}%",
            "comision_pendiente_usd": round(safe_float(seller.get("commissionPendingUsd"), 0), 2),
            "comision_pagada_usd": round(safe_float(seller.get("commissionPaidUsd"), 0), 2),
        }
        for seller in sorted(sellers, key=lambda item: safe_float(item.get("salesUsd"), 0), reverse=True)
    ]


def reports_page_context(store: dict) -> dict:
    filters = reports_filters_from_request()
    orders = report_orders(store, filters)
    products_by_id, products_by_sku = product_lookup_maps(store.get("products", []))
    rows = build_report_rows(store, filters, orders)
    payments = [
        movement
        for movement in store.get("credit_movements", [])
        if movement.get("movementType") == "payment"
    ]
    seller_totals: dict[str, float] = {}
    category_totals: dict[str, float] = {}
    sales_by_day: dict[str, float] = {}
    receivables_by_client: dict[str, float] = {}
    stock_by_category: dict[str, float] = {}
    seller_commissions: dict[str, float] = {}
    for order in orders:
        value = safe_float(order.get("totalUsd"), 0)
        seller = order.get("sellerName") or "Sin vendedor"
        seller_totals[seller] = seller_totals.get(seller, 0) + value
        sales_day = parse_utc_datetime(order.get("createdAt", "")).date().isoformat()
        sales_by_day[sales_day] = sales_by_day.get(sales_day, 0) + value
        if safe_float(order.get("balanceUsd"), 0) > 0:
            client_name = order.get("customerName") or "Cliente Wulkan"
            receivables_by_client[client_name] = receivables_by_client.get(client_name, 0) + safe_float(order.get("balanceUsd"), 0)
        seller_commissions[seller] = seller_commissions.get(seller, 0) + safe_float(order.get("commissionUsd"), 0)
        for line in reports_product_lines(order, products_by_id, products_by_sku):
            category_totals[line["category"]] = category_totals.get(line["category"], 0) + safe_float(line.get("lineTotalUsd"), 0)
    for product in store.get("products", []):
        category = product.get("categoryName") or "Sin categoria"
        available = max(0, safe_int(product.get("stock"), 0) - safe_int(product.get("reserved"), 0))
        stock_by_category[category] = stock_by_category.get(category, 0) + available
    metrics = {
        "orders": len(orders),
        "sales": round(sum(safe_float(order.get("totalUsd"), 0) for order in orders), 2),
        "receivable": round(sum(safe_float(order.get("balanceUsd"), 0) for order in orders if safe_float(order.get("balanceUsd"), 0) > 0), 2),
        "overdue": round(sum(safe_float(order.get("balanceUsd"), 0) for order in orders if order.get("dueStatus") == "overdue"), 2),
        "payments": round(sum(safe_float(payment.get("amountUsd"), 0) for payment in payments), 2),
        "commission": round(sum(safe_float(order.get("commissionUsd"), 0) for order in orders), 2),
        "stock_units": sum(max(0, safe_int(product.get("stock"), 0) - safe_int(product.get("reserved"), 0)) for product in store.get("products", [])),
    }
    return {
        "filters": filters,
        "report_type_options": REPORT_TYPE_OPTIONS,
        "report_title": report_type_label(filters["type"]),
        "columns": report_columns_for(filters["type"]),
        "rows": rows,
        "metrics": metrics,
        "now": utc_now(),
        "orders": orders,
        "seller_options": sorted(store.get("sellers", []), key=lambda item: item.get("name", "")),
        "client_options": sorted(store.get("clients", []), key=lambda item: item.get("businessName", "")),
        "category_options": product_category_options(store),
        "product_options": sorted(store.get("products", []), key=lambda item: item.get("title", "")),
        "order_status_options": ORDER_STATUS_OPTIONS,
        "charts": {
            "sales_by_day": graphify_from_pairs(list(sales_by_day.items()), 8),
            "seller_totals": graphify_from_pairs(list(seller_totals.items()), 8),
            "category_totals": graphify_from_pairs(list(category_totals.items()), 8),
            "receivables_by_client": graphify_from_pairs(list(receivables_by_client.items()), 8),
            "stock_by_category": graphify_from_pairs(list(stock_by_category.items()), 8),
            "seller_commissions": graphify_from_pairs(list(seller_commissions.items()), 8),
        },
        "can_export_reports": can_module_action("reports", "export"),
    }


def report_response_csv(context: dict) -> Response:
    output = io.StringIO()
    columns = context["columns"]
    writer = csv.DictWriter(output, fieldnames=[key for key, _label in columns], lineterminator="\n")
    writer.writeheader()
    for row in context["rows"]:
        writer.writerow({key: row.get(key, "") for key, _label in columns})
    filename = f"reporte_{context['filters']['type']}_wulkan.csv"
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def report_response_xlsx(context: dict):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Reporte"
    columns = context["columns"]
    sheet.append([f"Reporte {context['report_title']}"])
    sheet.append([f"Generado: {utc_now()}"])
    sheet.append([])
    sheet.append([label for _key, label in columns])
    header_fill = PatternFill("solid", fgColor="111827")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in sheet[4]:
        cell.fill = header_fill
        cell.font = header_font
    for row in context["rows"]:
        sheet.append([row.get(key, "") for key, _label in columns])
    for index, (_key, label) in enumerate(columns, start=1):
        sheet.column_dimensions[sheet.cell(row=4, column=index).column_letter].width = min(max(len(label) + 8, 16), 34)
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"reporte_{context['filters']['type']}_wulkan.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def service_technician_payload(existing: dict | None = None) -> dict:
    name = sanitize_text(request.form.get("name", ""), max_length=180, allow_newlines=False)
    now = utc_now()
    payload = {
        "name": name,
        "companyName": sanitize_text(request.form.get("companyName", ""), max_length=180, allow_newlines=False),
        "contactName": sanitize_text(request.form.get("contactName", ""), max_length=160, allow_newlines=False),
        "phone": sanitize_text(request.form.get("phone", ""), max_length=60, allow_newlines=False),
        "whatsapp": sanitize_text(request.form.get("whatsapp", ""), max_length=60, allow_newlines=False),
        "email": request.form.get("email", "").strip().lower(),
        "state": sanitize_text(request.form.get("state", ""), max_length=120, allow_newlines=False),
        "city": sanitize_text(request.form.get("city", ""), max_length=120, allow_newlines=False),
        "address": sanitize_text(request.form.get("address", ""), max_length=400),
        "specialties": split_lines(request.form.get("specialties", "")),
        "coverage": sanitize_text(request.form.get("coverage", ""), max_length=160, allow_newlines=False),
        "status": request.form.get("status", "active"),
        "visibleInApp": request.form.get("visibleInApp") == "on",
        "notes": sanitize_text(request.form.get("notes", ""), max_length=1200),
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


@app.get("/search")
@require_roles(*roles_for_action("dashboard", "view"))
def admin_search():
    query = request.args.get("q", "").strip()
    store = load_store()
    result_groups = admin_search_result_groups(store, query)
    return render_template(
        "admin_search.html",
        heading="Busqueda global",
        description="Consulta rapida sobre los modulos visibles para tu rol.",
        query=query,
        result_groups=result_groups,
        total_results=sum(len(group["items"]) for group in result_groups),
    )


@app.get("/plantillas")
@require_roles(*roles_for_action("import_templates", "view"))
def import_templates():
    template_groups = visible_import_template_groups()
    return render_template(
        "import_templates.html",
        template_groups=template_groups,
        total_templates=sum(len(group["items"]) for group in template_groups),
        import_history=list_import_history(),
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


@app.get("/imports/<module>/<draft_id>/issues.csv")
@require_roles(*roles_for_action("import_templates", "view"))
def import_issues_export(module: str, draft_id: str):
    draft = load_import_draft_record(module, draft_id)
    if not draft or not can_access_module(module):
        return forbidden_response()
    result = draft.get("result") or {}
    output = io.StringIO()
    fieldnames = ["tipo", "fila", "detalle"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for key, label in (
        ("errorRows", "error"),
        ("warningRows", "advertencia"),
        ("skippedRows", "omitida"),
        ("createdRows", "crear"),
        ("updatedRows", "actualizar"),
    ):
        for row in result.get(key) or []:
            writer.writerow({"tipo": label, "fila": row.get("row", ""), "detalle": row.get("label", "")})
    for message in result.get("errors") or []:
        writer.writerow({"tipo": "error", "fila": "", "detalle": message})
    for message in result.get("warnings") or []:
        writer.writerow({"tipo": "advertencia", "fila": "", "detalle": message})
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=incidencias_{module}_{draft_id}.csv"},
    )


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
    push_admin_toast("Usuario admin eliminado logicamente.", "warning", "Usuario actualizado")
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
    for active_session in user.get("activeSessions", []):
        if not active_session.get("revokedAt"):
            active_session["revokedAt"] = utc_now()
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
    push_admin_toast(
        f"Vendedor {'desactivado' if after else 'eliminado'} correctamente.",
        "warning",
        "Vendedor actualizado",
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
        notify_credit_requested(store, client)
        notify_seller(
            store,
            client.get("assignedSellerId", ""),
            "Cliente asignado",
            f"{client['businessName']} quedo asignado a tu cartera.",
            notification_type="client_assigned",
            priority="normal",
            module="clients",
            entity_type="client",
            entity_id=client["id"],
            deep_link=f"wulkan://seller/clients/{client['id']}",
            metadata={"clientId": client["id"]},
            dedupe_key=f"seller-client-assigned-{client['id']}",
        )
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
        if (
            updated.get("creditRequestStatus") == "pending"
            and (
                before.get("creditRequestStatus") != updated.get("creditRequestStatus")
                or safe_float(before.get("creditRequestedUsd"), 0) != safe_float(updated.get("creditRequestedUsd"), 0)
            )
        ):
            notify_credit_requested(store, updated)
        if updated.get("assignedSellerId") and before.get("assignedSellerId") != updated.get("assignedSellerId"):
            notify_seller(
                store,
                updated.get("assignedSellerId", ""),
                "Cliente asignado",
                f"{updated['businessName']} quedo asignado a tu cartera.",
                notification_type="client_assigned",
                priority="normal",
                module="clients",
                entity_type="client",
                entity_id=updated["id"],
                deep_link=f"wulkan://seller/clients/{updated['id']}",
                metadata={"clientId": updated["id"]},
                dedupe_key=f"seller-client-assigned-{updated['id']}-{updated.get('updatedAt', '')}",
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
    if target_status in {"blocked_debt", "blocked_credit", "suspended"}:
        notify_admin(
            store,
            "Cliente bloqueado",
            f"{client.get('businessName', client_id)} fue marcado como {client_status_label(target_status)}.",
            notification_type="client_blocked",
            priority="critical",
            module="clients",
            entity_type="client",
            entity_id=client_id,
            href=notification_url("clients", q=client.get("businessName", "")),
            metadata={"clientId": client_id, "status": target_status},
            dedupe_key=f"admin-client-status-{client_id}-{client.get('updatedAt', '')}",
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
    push_admin_toast(
        f"Cliente {'desactivado por historial' if after else 'eliminado'} correctamente.",
        "warning",
        "Cliente actualizado",
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
    push_admin_toast(
        f"Producto {'desactivado por historial comercial' if has_history else 'eliminado'} correctamente.",
        "warning",
        "Producto actualizado",
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
        for product in store.get("products", []):
            product_id = product.get("id", "")
            if product_id and stock_before.get(product_id) != stock_after.get(product_id):
                notify_stock_state(store, product)
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
        push_admin_toast("Categoria desactivada porque tiene referencias.", "warning", "Categoria actualizada")
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
        push_admin_toast("Categoria eliminada correctamente.", "warning", "Categoria eliminada")
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
        uploaded_asset = save_upload(request.files.get("assetFile"), "library")
        asset_url = uploaded_asset or sanitize_url(request.form.get("assetUrl", ""))
        asset_type = request.form.get("assetType", "image")
        title = sanitize_text(request.form.get("title", ""), max_length=180, allow_newlines=False) or "Activo Wulkan"
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
        if document_is_asset(asset) or asset.get("status") == "deleted":
            continue
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
        push_admin_toast("Recurso tecnico eliminado y desasociado del producto.", "warning", "Biblioteca actualizada")
        save_store(store)
    return redirect(url_for("media_library"))


@app.route("/documents", methods=["GET", "POST"])
@require_roles(*roles_for_action("documents", "view"))
def documents():
    store = load_store()
    if request.method == "POST":
        if not can_module_action("documents", "create"):
            return forbidden_response()
        title = sanitize_text(request.form.get("title", ""), max_length=180, allow_newlines=False)
        uploaded_document = save_upload(request.files.get("documentFile"), "documents")
        document_url = uploaded_document or sanitize_url(request.form.get("documentUrl", ""))
        document_type = normalize_document_type(request.form.get("documentType", "administrative"))
        subject_type, subject_id = parse_document_subject_ref(request.form.get("subjectRef", "admin:"))
        subject_label = "Administrativo general"
        if subject_id:
            resolved_id, resolved_label = resolve_document_subject(store, subject_type, subject_id)
            subject_id = resolved_id or subject_id
            subject_label = resolved_label or subject_label
        if title and document_url:
            asset = {
                "id": next_id("doc", title),
                "title": title,
                "assetType": "document",
                "type": "document",
                "productId": subject_id if subject_type == "product" else "",
                "url": document_url,
                "filePath": "",
                "documentType": document_type,
                "subjectType": subject_type,
                "subjectId": subject_id,
                "subjectLabel": subject_label,
                "visibility": normalize_document_visibility(request.form.get("visibility", "internal")),
                "expiresAt": sanitize_text(request.form.get("expiresAt", ""), max_length=32, allow_newlines=False),
                "status": request.form.get("status", "active") if request.form.get("status", "active") in dict(DOCUMENT_STATUS_OPTIONS) else "active",
                "notes": sanitize_text(request.form.get("notes", ""), max_length=1200),
                "createdById": session.get("admin_user_id", ""),
                "createdByName": session.get("admin_name", "Admin Wulkan"),
                "createdAt": utc_now(),
                "updatedAt": utc_now(),
            }
            store.setdefault("media_assets", []).append(asset)
            record_change_event(
                store,
                "create",
                "document",
                asset["id"],
                f"Documento creado: {title}.",
                None,
                asset,
            )
            save_store(store)
        return redirect(url_for("documents"))

    assets = document_assets(store)
    graph = document_graph(assets)
    return render_template(
        "documents.html",
        documents=assets,
        metrics=document_metrics(assets),
        graph=graph,
        subject_options=document_subject_options(store),
        document_type_options=DOCUMENT_TYPE_OPTIONS,
        document_status_options=DOCUMENT_STATUS_OPTIONS,
        document_visibility_options=DOCUMENT_VISIBILITY_OPTIONS,
        bulk_result=consume_bulk_result("documents"),
    )


@app.post("/documents/import")
@require_roles(*roles_for_action("documents", "import"))
def documents_import():
    return handle_bulk_import("documents", "document", import_documents_rows, "documents")


@app.get("/documents/<asset_id>/open")
@require_roles(*roles_for_action("documents", "view"))
def document_open(asset_id: str):
    store = load_store()
    asset = find_by_id(store.get("media_assets", []), asset_id)
    if not can_open_document(asset, store):
        abort(403)
    signed_url = document_signed_url(asset)
    if not signed_url:
        abort(404)
    record_audit_event(
        store,
        "document_open",
        "document",
        asset_id,
        f"Documento abierto: {asset.get('title', asset_id)}.",
        metadata={"visibility": normalize_document_visibility(asset.get("visibility", "internal")), "private": document_is_private(asset)},
    )
    save_store(store)
    return redirect(signed_url)


@app.get("/documents/private/<token>")
@require_roles(*roles_for_action("documents", "view"))
def document_private_file(token: str):
    try:
        payload = document_token_serializer().loads(
            token,
            max_age=int(app.config.get("DOCUMENT_SIGNED_URL_MAX_AGE_SECONDS", 300)),
        )
    except (BadSignature, SignatureExpired):
        abort(403)

    store = load_store()
    asset = find_by_id(store.get("media_assets", []), payload.get("assetId", ""))
    if not can_open_document(asset, store):
        abort(403)
    raw_url = sanitize_url(asset.get("url", ""))
    if hashlib.sha256(raw_url.encode("utf-8")).hexdigest() != payload.get("urlHash"):
        abort(403)

    key = str(payload.get("key", "")).lstrip("/\\")
    if key != document_storage_key(raw_url):
        abort(403)
    upload_root = Path(app.config["UPLOAD_FOLDER"]).resolve()
    target = (upload_root / key).resolve()
    try:
        target.relative_to(upload_root)
    except ValueError:
        abort(403)
    if not target.exists() or not target.is_file():
        abort(404)
    return send_file(target, as_attachment=False)


@app.get("/documents/export")
@require_roles(*roles_for_action("documents", "export"))
def documents_export():
    store = load_store()
    output = io.StringIO()
    fieldnames = [
        "titulo",
        "tipo_documento",
        "ambito",
        "asociado",
        "url",
        "visibilidad",
        "estado",
        "vence",
        "creado_por",
        "fecha",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for asset in document_assets(store):
        writer.writerow(
            {
                "titulo": asset.get("title", ""),
                "tipo_documento": document_type_label(asset.get("documentType", "")),
                "ambito": document_scope_label(asset.get("subjectType", "")),
                "asociado": asset.get("subjectLabel", ""),
                "url": asset.get("displayUrl", ""),
                "visibilidad": document_visibility_label(asset.get("visibility", "")),
                "estado": document_status_label(asset.get("effectiveStatus", asset.get("status", ""))),
                "vence": asset.get("expiresAt", ""),
                "creado_por": asset.get("createdByName", ""),
                "fecha": asset.get("createdAt", ""),
            }
        )
    record_audit_event(store, "export", "documents", "documents", "Exportacion CSV de documentos.")
    save_store(store)
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=documentos_wulkan.csv"},
    )


@app.post("/documents/<asset_id>/delete")
@require_roles(*roles_for_action("documents", "delete"))
def document_delete(asset_id: str):
    store = load_store()
    asset = find_by_id(store.get("media_assets", []), asset_id)
    if asset and document_is_asset(asset):
        before = copy.deepcopy(asset)
        asset["status"] = "deleted"
        asset["updatedAt"] = utc_now()
        record_change_event(
            store,
            "delete",
            "document",
            asset_id,
            f"Documento eliminado: {asset.get('title', asset_id)}.",
            before,
            asset,
        )
        push_admin_toast("Documento eliminado logicamente.", "warning", "Documento actualizado")
        save_store(store)
    return redirect(url_for("documents"))


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
        push_admin_toast("Servicio tecnico oculto de la app y eliminado logicamente.", "warning", "Servicio actualizado")
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
        payment_terms=payment_term_options(store),
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
    if payment_terms not in payment_term_options(store):
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
    notify_credit_decision(store, client, decision)
    save_store(store)
    return redirect(url_for("credit"))


def notifications_page_context(store: dict) -> dict:
    filters = {
        "q": request.args.get("q", "").strip(),
        "status": request.args.get("status", "").strip(),
        "type": request.args.get("type", "").strip(),
        "priority": request.args.get("priority", "").strip(),
        "module": request.args.get("module", "").strip(),
    }
    notifications = visible_admin_notifications(store)

    def matches(notification: dict) -> bool:
        haystack = " ".join(
            [
                notification.get("title", ""),
                notification.get("body", ""),
                notification.get("entityId", ""),
                notification.get("module", ""),
                notification.get("typeLabel", ""),
            ]
        ).lower()
        if filters["q"] and filters["q"].lower() not in haystack:
            return False
        if filters["status"] and notification.get("status") != filters["status"]:
            return False
        if filters["type"] and notification.get("notificationType") != filters["type"]:
            return False
        if filters["priority"] and notification.get("priority") != filters["priority"]:
            return False
        if filters["module"] and notification.get("module") != filters["module"]:
            return False
        return True

    filtered = [notification for notification in notifications if matches(notification)]
    metrics = {
        "total": len(notifications),
        "unread": sum(1 for item in notifications if item.get("status") == "unread"),
        "critical": sum(1 for item in notifications if item.get("priority") == "critical"),
        "mobile": sum(1 for item in notifications if item.get("channel") == "mobile"),
    }
    module_options = [
        {
            "key": key,
            "label": MODULE_NAV_INDEX.get(key, {}).get("label") or label,
        }
        for key, label, _icon, _description in PERMISSION_MODULES
        if can_access_module(key)
    ]
    return {
        "notifications": filtered,
        "filters": filters,
        "metrics": metrics,
        "status_options": NOTIFICATION_STATUS_LABELS.items(),
        "type_options": sorted(NOTIFICATION_TYPE_LABELS.items(), key=lambda item: item[1]),
        "priority_options": NOTIFICATION_PRIORITY_LABELS.items(),
        "module_options": module_options,
    }


@app.get("/notifications")
@require_roles(*roles_for_action("notifications", "view"))
def notifications():
    store = load_store()
    return render_template("notifications.html", **notifications_page_context(store))


@app.post("/notifications/<notification_id>/read")
@require_roles(*roles_for_action("notifications", "edit"))
def notification_read(notification_id: str):
    store = load_store()
    notification = find_by_id(store.get("notifications", []), notification_id)
    if not notification or not notification_visible_to_current_admin(notification):
        return redirect(url_for("notifications"))
    before = copy.deepcopy(notification)
    notification["status"] = "read"
    notification["readAt"] = utc_now()
    notification["updatedAt"] = notification["readAt"]
    record_change_event(
        store,
        "notification_read",
        "notification",
        notification_id,
        f"Notificacion marcada como leida: {notification.get('title', notification_id)}.",
        before,
        notification,
    )
    save_store(store)
    return redirect(request.form.get("next") or url_for("notifications"))


@app.post("/notifications/read-all")
@require_roles(*roles_for_action("notifications", "edit"))
def notifications_read_all():
    store = load_store()
    now = utc_now()
    updated = 0
    for notification in store.get("notifications", []):
        if notification.get("status") == "unread" and notification_visible_to_current_admin(notification):
            notification["status"] = "read"
            notification["readAt"] = now
            notification["updatedAt"] = now
            updated += 1
    if updated:
        record_audit_event(
            store,
            "notification_read_all",
            "notification",
            "",
            f"{updated} notificaciones marcadas como leidas.",
        )
        save_store(store)
    return redirect(request.form.get("next") or url_for("notifications"))


def business_rule_badge(status: str) -> str:
    return {
        "ok": "text-bg-success",
        "warning": "text-bg-warning",
        "critical": "text-bg-danger",
    }.get(status, "text-bg-secondary")


def business_rule_label(status: str) -> str:
    return {
        "ok": "OK",
        "warning": "Atencion",
        "critical": "Critico",
    }.get(status, "Revision")


def business_rule_href(module: str, endpoint: str, **kwargs) -> str:
    if not can_access_module(module):
        return ""
    return url_for(endpoint, **kwargs)


def duplicate_record_groups(records: list[dict], field: str, label_field: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for record in records:
        value = str(record.get(field, "")).strip().lower()
        if not value:
            continue
        groups.setdefault(value, []).append(str(record.get(label_field) or record.get("id") or value))
    return {key: values for key, values in groups.items() if len(values) > 1}


def add_business_rule(
    rules: list[dict],
    *,
    code: str,
    title: str,
    module: str,
    description: str,
    count: int = 0,
    examples: list[str] | None = None,
    href: str = "",
    warning: bool = False,
) -> None:
    status = "ok"
    if count > 0:
        status = "warning" if warning else "critical"
    rules.append(
        {
            "code": code,
            "title": title,
            "module": module,
            "description": description,
            "count": count,
            "examples": (examples or [])[:4],
            "href": href,
            "status": status,
            "statusLabel": business_rule_label(status),
            "statusClass": business_rule_badge(status),
        }
    )


def business_rules_page_context(store: dict) -> dict:
    products = [product for product in store.get("products", []) if product.get("status") != "deleted"]
    clients = [client for client in store.get("clients", []) if client.get("status") != "deleted"]
    orders = store.get("orders", [])
    movements = store.get("credit_movements", [])
    audit_events = store.get("audit_events", [])
    products_by_id = {product.get("id", ""): product for product in products}
    clients_by_id = {client.get("id", ""): client for client in clients}
    rules: list[dict] = []

    orders_without_client = [
        order for order in orders
        if not order.get("customerId") or order.get("customerId") not in clients_by_id
    ]
    add_business_rule(
        rules,
        code="orders.customer.required",
        title="Orden siempre con cliente",
        module="Ordenes",
        description="No se permite crear ni mantener ordenes sin cliente ferretero asociado.",
        count=len(orders_without_client),
        examples=[order.get("orderId", order.get("id", "")) for order in orders_without_client],
        href=business_rule_href("orders", "orders"),
    )

    orders_without_items = [
        order for order in orders
        if not [item for item in order.get("items") or [] if safe_int(item.get("quantity"), 0) > 0]
    ]
    invalid_item_orders = [
        order for order in orders
        if any(item.get("productId") and item.get("productId") not in products_by_id for item in order.get("items") or [])
    ]
    add_business_rule(
        rules,
        code="orders.items.required",
        title="Orden siempre con productos",
        module="Ordenes",
        description="Toda orden debe contener items validos del catalogo publicado por Wulkan.",
        count=len(orders_without_items) + len(invalid_item_orders),
        examples=[order.get("orderId", order.get("id", "")) for order in orders_without_items + invalid_item_orders],
        href=business_rule_href("orders", "orders"),
    )

    reserved_by_product = stock_reserved_quantities(orders)
    over_reserved_products = [
        f"{product.get('sku', product.get('id', ''))}: reservado {reserved_by_product.get(product.get('id', ''), 0)} / stock {safe_int(product.get('stock'), 0)}"
        for product in products
        if reserved_by_product.get(product.get("id", ""), 0) > safe_int(product.get("stock"), 0)
    ]
    stock_review_orders = [
        order for order in orders
        if order.get("status") in ORDER_STOCK_RESERVING_STATUSES
        and order.get("inventoryStatus") in {"", None, "review", "insufficient_stock"}
    ]
    add_business_rule(
        rules,
        code="orders.stock.required",
        title="Aprobacion solo con stock",
        module="Stock",
        description="Una orden aprobada, preparada o pagada debe tener reserva o entrega de inventario consistente.",
        count=len(over_reserved_products) + len(stock_review_orders),
        examples=over_reserved_products + [order.get("orderId", order.get("id", "")) for order in stock_review_orders],
        href=business_rule_href("stock", "stock"),
    )

    unauthorized_credit = [
        event for event in audit_events
        if event.get("action") == "credit_decision"
        and event.get("actorRole") not in CREDIT_APPROVAL_ROLES
    ]
    add_business_rule(
        rules,
        code="credit.approval.role",
        title="Credito aprobado por rol autorizado",
        module="Credito B2B",
        description="Las decisiones de credito solo pueden ser ejecutadas por super admin, gerente general o gerente comercial.",
        count=len(unauthorized_credit),
        examples=[f"{event.get('actorName', 'Actor')} -> {event.get('entityId', '')}" for event in unauthorized_credit],
        href=business_rule_href("audit", "audit", action="credit_decision"),
    )

    over_limit_clients = []
    for client in clients:
        limit = safe_float(client.get("creditLimitUsd"), 0)
        exposure = safe_float(client.get("creditUsedUsd"), 0) + client_order_credit_used(orders, client.get("id", ""), movements)
        if client.get("creditEnabled") and limit >= 0 and exposure > limit + 0.01:
            over_limit_clients.append(f"{client.get('businessName', client.get('id', 'Cliente'))}: {money_usd(exposure)} / {money_usd(limit)}")
    add_business_rule(
        rules,
        code="credit.limit.exceeded",
        title="Cupo no superado sin autorizacion",
        module="Credito B2B",
        description="La exposicion de linea de credito no debe superar el cupo aprobado por gerencia.",
        count=len(over_limit_clients),
        examples=over_limit_clients,
        href=business_rule_href("credit", "credit"),
    )

    blocked_client_orders = []
    for order in orders:
        if order.get("status") in {"cancelled", "rejected"}:
            continue
        client = clients_by_id.get(order.get("customerId", ""))
        blocker = client_sales_blocker(client, order.get("saleType", ""))
        if blocker:
            blocked_client_orders.append(f"{order.get('orderId', order.get('id', 'Orden'))}: {blocker}")
    add_business_rule(
        rules,
        code="clients.blocked.no_sale",
        title="Cliente bloqueado no compra",
        module="Clientes",
        description="Clientes bloqueados, suspendidos o con cobranza critica no pueden generar ventas nuevas.",
        count=len(blocked_client_orders),
        examples=blocked_client_orders,
        href=business_rule_href("clients", "clients"),
    )

    released_cancelled_commissions = [
        order for order in orders
        if order.get("status") in {"cancelled", "rejected"}
        and order.get("commissionStatus") in {"commission_approved", "commission_paid"}
    ]
    add_business_rule(
        rules,
        code="commissions.cancelled.no_release",
        title="Orden anulada no libera comision",
        module="Comisiones",
        description="Una comision no puede aprobarse ni pagarse cuando la orden esta anulada o rechazada.",
        count=len(released_cancelled_commissions),
        examples=[order.get("orderId", order.get("id", "")) for order in released_cancelled_commissions],
        href=business_rule_href("commissions", "commissions"),
    )

    product_sku_duplicates = duplicate_record_groups(products, "sku", "title")
    add_business_rule(
        rules,
        code="products.sku.unique",
        title="SKU unico",
        module="Productos",
        description="El SKU es la llave operativa entre catalogo, stock, ordenes y app movil.",
        count=len(product_sku_duplicates),
        examples=[f"{sku.upper()}: {', '.join(names)}" for sku, names in product_sku_duplicates.items()],
        href=business_rule_href("products", "products"),
    )

    client_rif_duplicates = duplicate_record_groups(clients, "taxId", "businessName")
    add_business_rule(
        rules,
        code="clients.rif.unique",
        title="RIF unico",
        module="Clientes",
        description="El RIF no debe repetirse para evitar credito duplicado, cartera mezclada o facturacion incorrecta.",
        count=len(client_rif_duplicates),
        examples=[f"{rif.upper()}: {', '.join(names)}" for rif, names in client_rif_duplicates.items()],
        href=business_rule_href("clients", "clients"),
    )

    invalid_price_products = [
        product for product in products
        if safe_float(product.get("publicPriceUsd"), 0) <= 0
        or safe_float(product.get("b2bPriceUsd"), 0) < 0
        or safe_float(product.get("originalPriceUsd"), 0) < 0
        or safe_float(product.get("costReferenceUsd"), 0) < 0
    ]
    add_business_rule(
        rules,
        code="products.price.non_negative",
        title="Precios no negativos",
        module="Productos",
        description="Los precios publico, ferretero, anterior y costo referencial deben ser validos antes de publicar.",
        count=len(invalid_price_products),
        examples=[product.get("sku", product.get("id", "")) for product in invalid_price_products],
        href=business_rule_href("products", "products"),
    )

    negative_stock_products = [
        product for product in products
        if safe_int(product.get("stock"), 0) < 0
        or safe_int(product.get("minimumStock"), 0) < 0
        or safe_int(product.get("maximumStock"), 0) < 0
    ]
    add_business_rule(
        rules,
        code="stock.non_negative",
        title="Stock no negativo",
        module="Stock",
        description="El stock fisico, minimo y maximo no pueden quedar bajo cero sin una autorizacion especial.",
        count=len(negative_stock_products),
        examples=[product.get("sku", product.get("id", "")) for product in negative_stock_products],
        href=business_rule_href("stock", "stock"),
    )

    protected_products = [
        product for product in products
        if product.get("status") == "inactive" and product_has_commercial_history(store, product)
    ]
    add_business_rule(
        rules,
        code="products.history.protected_delete",
        title="Producto con historial protegido",
        module="Productos",
        description="Los productos con ventas o movimientos se desactivan; no se eliminan fisicamente.",
        count=len(protected_products),
        examples=[product.get("sku", product.get("id", "")) for product in protected_products],
        href=business_rule_href("products", "products"),
        warning=True,
    )

    protected_clients = [
        client for client in clients
        if client.get("status") == "inactive"
        and any(order.get("customerId") == client.get("id") for order in orders)
    ]
    add_business_rule(
        rules,
        code="clients.orders.protected_delete",
        title="Cliente con ordenes protegido",
        module="Clientes",
        description="Los clientes con ordenes se desactivan; no se eliminan fisicamente.",
        count=len(protected_clients),
        examples=[client.get("businessName", client.get("id", "")) for client in protected_clients],
        href=business_rule_href("clients", "clients"),
        warning=True,
    )

    data_exists = bool(products or clients or orders)
    write_events = [
        event for event in audit_events
        if event.get("action") in AUDIT_WRITE_ACTIONS or (event.get("metadata") or {}).get("changedFields")
    ]
    add_business_rule(
        rules,
        code="audit.sensitive.changes",
        title="Cambios sensibles auditados",
        module="Auditoria",
        description="Creacion, edicion, eliminacion, pagos, estados, credito y permisos deben dejar evento de auditoria.",
        count=0 if not data_exists or write_events else 1,
        examples=[] if write_events or not data_exists else ["Hay datos operativos sin eventos de auditoria visibles."],
        href=business_rule_href("audit", "audit"),
        warning=True,
    )

    metrics = {
        "total": len(rules),
        "ok": sum(1 for rule in rules if rule["status"] == "ok"),
        "warning": sum(1 for rule in rules if rule["status"] == "warning"),
        "critical": sum(1 for rule in rules if rule["status"] == "critical"),
        "incidents": sum(rule["count"] for rule in rules if rule["status"] != "ok"),
    }
    module_counts: dict[str, float] = {}
    for rule in rules:
        if rule["status"] == "ok":
            continue
        module_counts[rule["module"]] = module_counts.get(rule["module"], 0) + rule["count"]
    return {
        "rules": rules,
        "incidents": [rule for rule in rules if rule["status"] != "ok"],
        "metrics": metrics,
        "status_graph": graphify_from_pairs(
            [
                ("OK", metrics["ok"]),
                ("Atencion", metrics["warning"]),
                ("Critico", metrics["critical"]),
            ],
            3,
        ),
        "module_graph": graphify_from_pairs(list(module_counts.items()), 8),
    }


@app.get("/business-rules")
@require_roles(*roles_for_action("business_rules", "view"))
def business_rules():
    store = load_store()
    return render_template("business_rules.html", **business_rules_page_context(store))


def maintenance_badge(status: str) -> str:
    return {
        "ok": "text-bg-success",
        "warning": "text-bg-warning",
        "critical": "text-bg-danger",
    }.get(status, "text-bg-secondary")


def maintenance_label(status: str) -> str:
    return {
        "ok": "OK",
        "warning": "Atencion",
        "critical": "Critico",
    }.get(status, "Revision")


def add_maintenance_area(
    areas: list[dict],
    *,
    key: str,
    title: str,
    module: str,
    status: str,
    detail: str,
    action: str = "",
    href: str = "",
) -> None:
    areas.append(
        {
            "key": key,
            "title": title,
            "module": module,
            "status": status,
            "statusLabel": maintenance_label(status),
            "statusClass": maintenance_badge(status),
            "detail": detail,
            "action": action,
            "href": href,
        }
    )


def maintenance_page_context(store: dict) -> dict:
    api_root = Path(__file__).resolve().parent
    project_root = api_root.parents[1]
    docs_root = project_root / "docs"
    migrations_dir = api_root / "migrations" / "versions"
    migration_files = sorted(migrations_dir.glob("*.py"))
    latest_migration = migration_files[-1].stem if migration_files else "sin-migraciones"
    database_url = str(app.config.get("DATABASE_URL", ""))
    database_engine = "PostgreSQL" if database_url.startswith("postgresql") else "SQLite" if "sqlite" in database_url else "Otro"
    is_production = app.config.get("ENV") == "production"
    storage_backend = str(app.config.get("STORAGE_BACKEND", "")).lower()
    data_backend = str(app.config.get("DATA_BACKEND", "")).lower()

    areas: list[dict] = []
    production_ready = (
        data_backend == "sql"
        and database_engine == "PostgreSQL"
        and storage_backend == "s3"
        and bool(app.config.get("REQUIRE_MOBILE_TOKEN"))
        and not bool(app.config.get("SQL_FALLBACK_TO_JSON"))
        and app.config.get("SECRET_KEY") != "wulkan-dev"
    )
    add_maintenance_area(
        areas,
        key="environment",
        title="Separacion dev/staging/prod",
        module="Runtime",
        status="ok" if production_ready else ("critical" if is_production else "warning"),
        detail=(
            "Produccion usa SQL, PostgreSQL, S3 y token movil obligatorio."
            if production_ready
            else f"Entorno {app.config.get('ENV')} con backend {data_backend}, storage {storage_backend} y base {database_engine}."
        ),
        action="Revisar variables" if not production_ready else "",
    )
    add_maintenance_area(
        areas,
        key="indexes",
        title="Indices SQL",
        module="Base de datos",
        status="ok" if latest_migration.endswith("0010_performance_indexes") else "warning",
        detail=f"{len(migration_files)} migraciones Alembic. Ultima: {latest_migration}.",
        href=url_for("maintenance_export"),
        action="Exportar estado",
    )
    add_maintenance_area(
        areas,
        key="pagination",
        title="Paginacion y consultas",
        module="API/Admin",
        status="ok",
        detail="API movil con limit/page/cursor y tablas admin paginadas para operacion comercial.",
        href=url_for("api_mobile_meta"),
        action="Ver meta API",
    )
    backup_script = api_root / "scripts" / "backup_database.py"
    restore_script = api_root / "scripts" / "restore_database.py"
    add_maintenance_area(
        areas,
        key="backups",
        title="Backups automaticos",
        module="Operaciones",
        status="ok" if backup_script.exists() and restore_script.exists() else "critical",
        detail=f"Scripts pg_dump/restore listos. Directorio configurado: {app.config.get('BACKUP_DIR')}.",
        action="Programar job externo",
    )
    add_maintenance_area(
        areas,
        key="logs",
        title="Logs de errores y actividad",
        module="Auditoria",
        status="ok",
        detail=f"Auditoria: {len(store.get('audit_events', []))} eventos. Notificaciones: {len(store.get('notifications', []))}.",
        href=url_for("audit") if can_access_module("audit") else "",
        action="Ver auditoria",
    )
    add_maintenance_area(
        areas,
        key="versions",
        title="Control de versiones",
        module="Release",
        status="ok" if app.config.get("BUILD_SHA") else ("warning" if is_production else "ok"),
        detail=f"Version {app.config.get('APP_VERSION')} - build {app.config.get('BUILD_SHA') or 'no informado'}.",
        action="Configurar WULKAN_BUILD_SHA" if not app.config.get("BUILD_SHA") else "",
    )
    if docs_root.exists():
        required_docs = [
            docs_root / "operations" / "DEPLOYMENT.md",
            docs_root / "operations" / "SECURITY.md",
            docs_root / "operations" / "MOBILE_SETUP.md",
            docs_root / "operations" / "MAINTENANCE.md",
            docs_root / "product" / "MANUAL_ADMIN.md",
            docs_root / "product" / "MANUAL_APP_MOVIL.md",
        ]
        missing_docs = [path.name for path in required_docs if not path.exists()]
        docs_detail_ok = "Manuales tecnicos y funcionales completos."
    else:
        embedded_docs = [
            api_root / "README.md",
            api_root / "scripts" / "readiness_check.py",
            api_root / "scripts" / "backup_database.py",
            api_root / "scripts" / "restore_database.py",
        ]
        missing_docs = [path.name for path in embedded_docs if not path.exists()]
        docs_detail_ok = "Documentacion operativa incluida en README y scripts; manuales completos viven en el repositorio."
    add_maintenance_area(
        areas,
        key="documentation",
        title="Documentacion tecnica y funcional",
        module="Producto",
        status="ok" if not missing_docs else "warning",
        detail=docs_detail_ok if not missing_docs else f"Faltan: {', '.join(missing_docs)}.",
        href=url_for("import_templates") if can_access_module("import_templates") else "",
        action="Ver plantillas",
    )
    add_maintenance_area(
        areas,
        key="variables",
        title="Variables de entorno",
        module="Configuracion",
        status="ok" if (not is_production or production_ready) else "critical",
        detail="Variables declaradas en .env.example y validadas al iniciar en produccion.",
        href=url_for("settings") if can_access_module("settings") else "",
        action="Ver configuracion",
    )

    counts = {
        "products": len([item for item in store.get("products", []) if item.get("status") != "deleted"]),
        "clients": len([item for item in store.get("clients", []) if item.get("status") != "deleted"]),
        "orders": len(store.get("orders", [])),
        "sellers": len([item for item in store.get("admin_users", []) if item.get("role") == "sales" and item.get("status") != "deleted"]),
        "audit": len(store.get("audit_events", [])),
        "notifications": len(store.get("notifications", [])),
    }
    metrics = {
        "areas": len(areas),
        "ok": sum(1 for area in areas if area["status"] == "ok"),
        "warning": sum(1 for area in areas if area["status"] == "warning"),
        "critical": sum(1 for area in areas if area["status"] == "critical"),
        "migrations": len(migration_files),
    }
    runtime_rows = [
        ("Entorno", app.config.get("ENV")),
        ("Version", app.config.get("APP_VERSION")),
        ("Build", app.config.get("BUILD_SHA") or "no informado"),
        ("Datos", app.config.get("DATA_BACKEND")),
        ("Base", database_engine),
        ("Storage", app.config.get("STORAGE_BACKEND")),
        ("Token movil", "Obligatorio" if app.config.get("REQUIRE_MOBILE_TOKEN") else "No obligatorio"),
        ("Fallback JSON", "Activo" if app.config.get("SQL_FALLBACK_TO_JSON") else "Desactivado"),
        ("Pool SQL", f"{app.config.get('DB_POOL_SIZE')} + {app.config.get('DB_MAX_OVERFLOW')} overflow"),
        ("Upload max", f"{int(app.config.get('MAX_CONTENT_LENGTH', 0) / 1024 / 1024)} MB"),
        ("Import max", f"{app.config.get('MAX_IMPORT_ROWS')} filas"),
        ("Log level", app.config.get("LOG_LEVEL")),
    ]
    return {
        "areas": areas,
        "findings": [area for area in areas if area["status"] != "ok"],
        "metrics": metrics,
        "runtime_rows": runtime_rows,
        "latest_migration": latest_migration,
        "counts": counts,
        "status_graph": graphify_from_pairs(
            [
                ("OK", metrics["ok"]),
                ("Atencion", metrics["warning"]),
                ("Critico", metrics["critical"]),
            ],
            3,
        ),
        "volume_graph": graphify_from_pairs(
            [
                ("Productos", counts["products"]),
                ("Clientes", counts["clients"]),
                ("Ordenes", counts["orders"]),
                ("Vendedores", counts["sellers"]),
                ("Auditoria", counts["audit"]),
                ("Notificaciones", counts["notifications"]),
            ],
            6,
        ),
    }


@app.get("/maintenance")
@require_roles(*roles_for_action("maintenance", "view"))
def maintenance():
    store = load_store()
    return render_template("maintenance.html", **maintenance_page_context(store))


@app.get("/maintenance/export")
@require_roles(*roles_for_action("maintenance", "export"))
def maintenance_export():
    store = load_store()
    context = maintenance_page_context(store)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["area", "modulo", "estado", "detalle", "accion"])
    writer.writeheader()
    for area in context["areas"]:
        writer.writerow(
            {
                "area": area["title"],
                "modulo": area["module"],
                "estado": area["statusLabel"],
                "detalle": area["detail"],
                "accion": area["action"],
            }
        )
    record_audit_event(
        store,
        "export",
        "maintenance",
        "readiness",
        "Exportacion de estado tecnico de mantenimiento.",
    )
    save_store(store)
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=wulkan_mantenimiento.csv"},
    )


def audit_event_matches_filters(event: dict, filters: dict[str, str]) -> bool:
    created_at = parse_utc_datetime(event.get("createdAt", ""))
    date_from = parse_filter_date(filters.get("date_from"))
    date_to = parse_filter_date(filters.get("date_to"))
    if date_from and created_at < date_from:
        return False
    if date_to and created_at >= date_to + timedelta(days=1):
        return False
    if filters["action"] and event.get("action", "") != filters["action"]:
        return False
    if filters["entity_type"] and event.get("entityType", "") != filters["entity_type"]:
        return False
    if filters.get("severity") and event.get("severity", "") != filters["severity"]:
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


def audit_event_severity(event: dict) -> str:
    action = event.get("action", "")
    if action in {"delete", "login_failed", "login_limited", "login_blocked"}:
        return "critical"
    if action in AUDIT_SECURITY_ACTIONS:
        return "security"
    if action in AUDIT_WRITE_ACTIONS or event.get("metadata", {}).get("changedFields"):
        return "write"
    if action == "export":
        return "export"
    return "read"


def audit_event_label(value: str) -> str:
    return {
        "critical": "Critico",
        "security": "Seguridad",
        "write": "Cambio",
        "export": "Exportacion",
        "read": "Lectura",
    }.get(value, value or "Lectura")


def audit_page_context(store: dict) -> dict:
    all_events = sorted(store.get("audit_events", []), key=lambda item: item.get("createdAt", ""), reverse=True)
    for event in all_events:
        event["severity"] = audit_event_severity(event)
        event["severityLabel"] = audit_event_label(event["severity"])
        metadata = event.get("metadata") or {}
        event["changedFieldsCount"] = len(metadata.get("changedFields") or [])
        event["hasSnapshot"] = bool(metadata.get("before") or metadata.get("after"))
    filters = {
        "q": request.args.get("q", "").strip(),
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
        "action": request.args.get("action", "").strip(),
        "entity_type": request.args.get("entity_type", "").strip(),
        "actor": request.args.get("actor", "").strip(),
        "severity": request.args.get("severity", "").strip(),
    }
    filtered_events = [event for event in all_events if audit_event_matches_filters(event, filters)]
    events = filtered_events[:1000]
    action_counts: dict[str, float] = {}
    entity_counts: dict[str, float] = {}
    actor_counts: dict[str, float] = {}
    severity_counts: dict[str, float] = {}
    for event in filtered_events:
        action = event.get("action", "sin_accion")
        entity = event.get("entityType", "sin_modulo")
        actor = event.get("actorName", "Sistema")
        severity = event.get("severityLabel", "Lectura")
        action_counts[action] = action_counts.get(action, 0) + 1
        entity_counts[entity] = entity_counts.get(entity, 0) + 1
        actor_counts[actor] = actor_counts.get(actor, 0) + 1
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    metrics = {
        "total": len(all_events),
        "filtered": len(filtered_events),
        "actors": len({event.get("actorId") or event.get("actorName") for event in filtered_events}),
        "writes": sum(1 for event in filtered_events if event.get("severity") == "write"),
        "security": sum(1 for event in filtered_events if event.get("severity") in {"security", "critical"}),
        "exports": sum(1 for event in filtered_events if event.get("severity") == "export"),
        "snapshots": sum(1 for event in filtered_events if event.get("hasSnapshot")),
    }
    graphify_summary = f"{metrics['writes']} cambios / {metrics['actors']} actores"
    return {
        "events": events,
        "metrics": metrics,
        "graphify_summary": graphify_summary,
        "filters": filters,
        "action_options": sorted({event.get("action", "") for event in all_events if event.get("action")}),
        "entity_options": sorted({event.get("entityType", "") for event in all_events if event.get("entityType")}),
        "actor_options": sorted({event.get("actorName", "") for event in all_events if event.get("actorName")}),
        "severity_options": [
            ("critical", "Critico"),
            ("security", "Seguridad"),
            ("write", "Cambio"),
            ("export", "Exportacion"),
            ("read", "Lectura"),
        ],
        "charts": {
            "actions": graphify_from_pairs(list(action_counts.items()), 8),
            "entities": graphify_from_pairs(list(entity_counts.items()), 8),
            "actors": graphify_from_pairs(list(actor_counts.items()), 8),
            "severity": graphify_from_pairs(list(severity_counts.items()), 8),
        },
        "can_export_audit": can_module_action("audit", "export"),
    }


def payment_terms_from_text(value: str) -> list[int]:
    terms = [
        safe_int(term, -1)
        for term in re.split(r"[\s,;|/]+", value or "")
        if term.strip()
    ]
    normalized = sorted({term for term in terms if term >= 0})
    return normalized or [0]


def settings_payload_from_form(existing: dict) -> dict:
    now = utc_now()
    payload = dict(existing or {})
    payload.update(
        {
            "companyName": sanitize_text(request.form.get("companyName", ""), max_length=180, allow_newlines=False) or "Wulkan Venezuela",
            "companyLegalName": sanitize_text(request.form.get("companyLegalName", ""), max_length=180, allow_newlines=False),
            "taxId": sanitize_text(request.form.get("taxId", ""), max_length=60, allow_newlines=False),
            "supportEmail": request.form.get("supportEmail", "").strip().lower(),
            "supportPhone": sanitize_text(request.form.get("supportPhone", ""), max_length=60, allow_newlines=False),
            "logoUrl": sanitize_url(request.form.get("logoUrl", "")),
            "primaryCurrency": request.form.get("primaryCurrency", "USD").strip().upper() or "USD",
            "referenceCurrency": request.form.get("referenceCurrency", "VES").strip().upper() or "VES",
            "exchangeRateUsdVes": safe_float(request.form.get("exchangeRateUsdVes"), 38.5),
            "defaultPaymentTermsDays": payment_terms_from_text(request.form.get("defaultPaymentTermsDays", "")),
            "creditApprovalThresholdUsd": safe_float(request.form.get("creditApprovalThresholdUsd"), 0),
            "overdueBlockDays": max(0, safe_int(request.form.get("overdueBlockDays"), 15)),
            "defaultCommissionRule": request.form.get("defaultCommissionRule", "sale_generated"),
            "defaultCommissionPercent": max(0.0, min(safe_float(request.form.get("defaultCommissionPercent"), 0), 100.0)),
            "stockMinDefault": max(0, safe_int(request.form.get("stockMinDefault"), 1)),
            "maxUploadMb": max(1, safe_int(request.form.get("maxUploadMb"), 10)),
            "quoteFooterText": sanitize_text(request.form.get("quoteFooterText", ""), max_length=1500),
            "orderTermsText": sanitize_text(request.form.get("orderTermsText", ""), max_length=1500),
            "notificationEmails": split_lines(request.form.get("notificationEmails", "")),
            "updatedAt": now,
        }
    )
    payload.setdefault("createdAt", existing.get("createdAt") or now)
    if payload["defaultCommissionRule"] not in dict(COMMISSION_RULE_OPTIONS):
        payload["defaultCommissionRule"] = "sale_generated"
    return payload


def settings_page_context(store: dict, error: str = "", success: str = "") -> dict:
    settings_data = business_settings(store)
    return {
        "settings": settings_data,
        "payment_terms_text": ", ".join(str(term) for term in settings_data.get("defaultPaymentTermsDays", [0])),
        "notification_emails_text": "\n".join(settings_data.get("notificationEmails", [])),
        "commission_rule_options": COMMISSION_RULE_OPTIONS,
        "error": error,
        "success": success,
        "can_edit_settings": can_module_action("settings", "edit"),
    }


@app.get("/audit")
@require_roles(*roles_for_action("audit", "view"))
def audit():
    store = load_store()
    return render_template("audit.html", **audit_page_context(store))


@app.get("/audit/export")
@require_roles(*roles_for_action("audit", "export"))
def audit_export():
    store = load_store()
    context = audit_page_context(store)
    output = io.StringIO()
    fieldnames = [
        "fecha",
        "criticidad",
        "accion",
        "actor",
        "rol",
        "entidad",
        "id_entidad",
        "detalle",
        "campos_cambiados",
        "origen",
        "ip",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for event in context["events"]:
        writer.writerow(
            {
                "fecha": event.get("createdAt", ""),
                "criticidad": event.get("severityLabel", ""),
                "accion": event.get("action", ""),
                "actor": event.get("actorName", ""),
                "rol": event.get("actorRole", ""),
                "entidad": event.get("entityType", ""),
                "id_entidad": event.get("entityId", ""),
                "detalle": event.get("detail", ""),
                "campos_cambiados": ", ".join((event.get("metadata") or {}).get("changedFields") or []),
                "origen": f"{event.get('method', '')} {event.get('path', '')}",
                "ip": event.get("ipAddress", ""),
            }
        )
    record_audit_event(
        store,
        "export",
        "audit",
        "audit_events",
        "Auditoria exportada.",
        metadata={"filters": context["filters"], "count": len(context["events"])},
    )
    save_store(store)
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=auditoria_wulkan.csv"},
    )


@app.route("/settings", methods=["GET", "POST"])
@require_roles(*roles_for_action("settings", "view"))
def settings():
    store = load_store()
    if request.method == "POST":
        if not can_module_action("settings", "edit"):
            return forbidden_response()
        before = copy.deepcopy(store.get("business_settings") or {})
        store["business_settings"] = settings_payload_from_form(before)
        record_change_event(
            store,
            "update",
            "business_settings",
            "default",
            "Configuracion general actualizada.",
            before,
            store["business_settings"],
        )
        save_store(store)
        return render_template("settings.html", **settings_page_context(store, success="Configuracion guardada correctamente."))
    return render_template("settings.html", **settings_page_context(store))


@app.route("/crm", methods=["GET", "POST"])
@require_roles(*roles_for_action("crm", "view"))
def crm():
    store = load_store()
    if request.method == "POST":
        if not can_module_action("crm", "create"):
            return forbidden_response()
        record, error = crm_record_payload_from_form(store)
        if error:
            return render_template("crm.html", **crm_page_context(store, error)), 400
        append_crm_activity(record, "note", "Registro CRM creado.")
        store.setdefault("crm_records", []).append(record)
        record_audit_event(
            store,
            "create",
            "crm_record",
            record["id"],
            f"CRM creado: {record.get('title', '')}.",
        )
        save_store(store)
        return redirect(url_for("crm"))
    return render_template("crm.html", **crm_page_context(store))


@app.get("/crm/export")
@require_roles(*roles_for_action("crm", "export"))
def crm_export():
    store = load_store()
    context = crm_page_context(store)
    output = io.StringIO()
    fieldnames = [
        "titulo",
        "tipo",
        "pipeline",
        "estado",
        "cliente",
        "vendedor",
        "contacto",
        "telefono",
        "email",
        "origen",
        "valor_estimado_usd",
        "probabilidad",
        "valor_ponderado_usd",
        "cierre_estimado",
        "proxima_accion",
        "ultima_actividad",
        "actividades",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for record in context["records"]:
        writer.writerow(
            {
                "titulo": record.get("title", ""),
                "tipo": record.get("recordTypeLabel", ""),
                "pipeline": record.get("pipelineStageLabel", ""),
                "estado": record.get("statusLabel", ""),
                "cliente": record.get("clientName", ""),
                "vendedor": record.get("sellerName", ""),
                "contacto": record.get("contactName", ""),
                "telefono": record.get("phone", ""),
                "email": record.get("email", ""),
                "origen": record.get("source", ""),
                "valor_estimado_usd": record.get("estimatedValueUsd", 0),
                "probabilidad": record.get("probabilityPercent", 0),
                "valor_ponderado_usd": record.get("weightedValueUsd", 0),
                "cierre_estimado": record.get("expectedCloseAt", ""),
                "proxima_accion": record.get("nextActionAt", ""),
                "ultima_actividad": record.get("lastActivityAt", ""),
                "actividades": record.get("activitiesCount", 0),
            }
        )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=crm_comercial_wulkan.csv"},
    )


@app.post("/crm/<record_id>/update")
@require_roles(*roles_for_action("crm", "edit"))
def crm_update(record_id: str):
    store = load_store()
    record = find_by_id(store.get("crm_records", []), record_id)
    if not record or not can_access_crm_record(record, store):
        return redirect(url_for("crm"))
    before = copy.deepcopy(record)
    updated, error = crm_record_payload_from_form(store, record)
    if error:
        return render_template("crm.html", **crm_page_context(store, error)), 400
    record.clear()
    record.update(updated)
    append_crm_activity(record, "note", request.form.get("changeNote", "").strip() or "Registro CRM actualizado.")
    record_change_event(
        store,
        "update",
        "crm_record",
        record_id,
        f"CRM actualizado: {record.get('title', '')}.",
        before,
        record,
    )
    save_store(store)
    return redirect(url_for("crm"))


@app.post("/crm/<record_id>/activity")
@require_roles(*roles_for_action("crm", "edit"))
def crm_activity_create(record_id: str):
    store = load_store()
    record = find_by_id(store.get("crm_records", []), record_id)
    if not record or not can_access_crm_record(record, store):
        return redirect(url_for("crm"))
    before = copy.deepcopy(record)
    activity_type = request.form.get("activityType", "note")
    note = request.form.get("activityNote", "").strip()
    if not note:
        return render_template("crm.html", **crm_page_context(store, "La actividad requiere comentario.")), 400
    stage = request.form.get("pipelineStage", record.get("pipelineStage", "new_lead"))
    status = request.form.get("status", record.get("status", "active"))
    if stage in dict(CRM_PIPELINE_STAGE_OPTIONS):
        record["pipelineStage"] = stage
    if status in dict(CRM_STATUS_OPTIONS):
        record["status"] = status
    if record.get("pipelineStage") == "won":
        record["status"] = "won"
    elif record.get("pipelineStage") == "lost":
        record["status"] = "lost"
    elif record.get("pipelineStage") == "inactive":
        record["status"] = "inactive"
    append_crm_activity(record, activity_type, note, request.form.get("nextActionAt", "").strip())
    record_change_event(
        store,
        "crm_activity",
        "crm_record",
        record_id,
        f"Actividad CRM registrada: {crm_activity_type_label(activity_type)}.",
        before,
        record,
    )
    save_store(store)
    return redirect(url_for("crm"))


@app.post("/crm/<record_id>/delete")
@require_roles(*DELETE_ROLES)
def crm_delete(record_id: str):
    store = load_store()
    record = find_by_id(store.get("crm_records", []), record_id)
    if not record or not can_module_action("crm", "delete"):
        return redirect(url_for("crm"))
    before = copy.deepcopy(record)
    record["status"] = "deleted"
    record["updatedAt"] = utc_now()
    record_change_event(
        store,
        "delete",
        "crm_record",
        record_id,
        f"CRM eliminado logicamente: {record.get('title', '')}.",
        before,
        record,
    )
    push_admin_toast("Registro CRM eliminado logicamente.", "warning", "CRM actualizado")
    save_store(store)
    return redirect(url_for("crm"))


@app.get("/quotes")
@require_roles(*roles_for_action("quotes", "view"))
def quotes():
    store = load_store()
    return render_template("quotes.html", **quotes_page_context(store))


@app.get("/quotes/export")
@require_roles(*roles_for_action("quotes", "export"))
def quotes_export():
    store = load_store()
    context = quotes_page_context(store)
    output = io.StringIO()
    fieldnames = [
        "cotizacion",
        "fecha",
        "cliente",
        "vendedor",
        "estado",
        "vigencia",
        "tipo_venta",
        "plazo_dias",
        "version",
        "total_usd",
        "total_ves",
        "items",
        "orden_convertida",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for quote in context["quotes"]:
        writer.writerow(
            {
                "cotizacion": quote.get("quoteNumber", ""),
                "fecha": quote.get("createdAt", ""),
                "cliente": quote.get("clientName", ""),
                "vendedor": quote.get("sellerName", ""),
                "estado": quote.get("statusLabel", ""),
                "vigencia": quote.get("validUntil", ""),
                "tipo_venta": quote.get("saleTypeLabel", ""),
                "plazo_dias": quote.get("paymentTermDays", 0),
                "version": quote.get("version", 1),
                "total_usd": quote.get("totalUsd", 0),
                "total_ves": quote.get("totalVes", 0),
                "items": "|".join(
                    f"{item.get('sku', '')}:{item.get('quantity', 0)}"
                    for item in quote.get("items") or []
                ),
                "orden_convertida": quote.get("convertedOrderId", ""),
            }
        )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=cotizaciones_wulkan.csv"},
    )


@app.route("/quotes/new", methods=["GET", "POST"])
@require_roles(*roles_for_action("quotes", "create"))
def quote_new():
    store = load_store()
    if request.method == "POST":
        quote, error = quote_payload_from_form(store)
        if error:
            return render_template("quote_form.html", **quote_form_context(store, None, error)), 400
        append_quote_history(quote, quote.get("status", "draft"), "Cotizacion creada.")
        store.setdefault("quotes", []).append(quote)
        record_audit_event(
            store,
            "create",
            "quote",
            quote["id"],
            f"Cotizacion {quote['quoteNumber']} creada para {quote['client'].get('name', 'cliente')}.",
        )
        save_store(store)
        return redirect(url_for("quotes"))
    return render_template("quote_form.html", **quote_form_context(store))


@app.route("/quotes/<quote_id>/edit", methods=["GET", "POST"])
@require_roles(*roles_for_action("quotes", "edit"))
def quote_edit(quote_id: str):
    store = load_store()
    quote = find_by_id(store.get("quotes", []), quote_id)
    if not quote or not can_access_quote_record(quote, store):
        return redirect(url_for("quotes"))
    if request.method == "POST":
        before = copy.deepcopy(quote)
        updated, error = quote_payload_from_form(store, quote)
        if error:
            return render_template("quote_form.html", **quote_form_context(store, quote, error)), 400
        updated.setdefault("versions", []).append(quote_version_snapshot(before, "Version anterior antes de editar."))
        quote.clear()
        quote.update(updated)
        quote["version"] = safe_int(before.get("version"), 1) + 1
        append_quote_history(quote, quote.get("status", "draft"), f"Cotizacion editada a version {quote['version']}.")
        record_change_event(
            store,
            "update",
            "quote",
            quote_id,
            f"Cotizacion {quote.get('quoteNumber', quote_id)} editada.",
            before,
            quote,
        )
        save_store(store)
        return redirect(url_for("quotes"))
    return render_template("quote_form.html", **quote_form_context(store, quote))


@app.post("/quotes/<quote_id>/status")
@require_roles(*roles_for_action("quotes", "edit"))
def quote_status_update(quote_id: str):
    store = load_store()
    quote = find_by_id(store.get("quotes", []), quote_id)
    if not quote or not can_access_quote_record(quote, store):
        return redirect(url_for("quotes"))
    before = copy.deepcopy(quote)
    status = request.form.get("status", quote.get("status", "draft"))
    if status not in dict(QUOTE_STATUS_OPTIONS):
        return redirect(url_for("quotes"))
    note = request.form.get("note", "").strip()
    now = utc_now()
    quote["status"] = status
    quote["updatedAt"] = now
    if status == "sent":
        quote["sentAt"] = quote.get("sentAt") or now
    elif status == "viewed":
        quote["viewedAt"] = quote.get("viewedAt") or now
    elif status == "accepted":
        quote["acceptedAt"] = quote.get("acceptedAt") or now
    elif status == "rejected":
        quote["rejectedAt"] = quote.get("rejectedAt") or now
    append_quote_history(quote, status, note or f"Estado cambiado a {quote_status_label(status)}.")
    record_change_event(
        store,
        "update_status",
        "quote",
        quote_id,
        f"Cotizacion movida a {quote_status_label(status)}.",
        before,
        quote,
    )
    if status == "accepted":
        notify_quote_accepted(store, quote)
    save_store(store)
    return redirect(url_for("quotes"))


@app.post("/quotes/<quote_id>/duplicate")
@require_roles(*roles_for_action("quotes", "create"))
def quote_duplicate(quote_id: str):
    store = load_store()
    source = find_by_id(store.get("quotes", []), quote_id)
    if not source or not can_access_quote_record(source, store):
        return redirect(url_for("quotes"))
    quote = copy.deepcopy(source)
    quote["id"] = next_id("quote", quote.get("clientName") or quote.get("quoteNumber", "wulkan"))
    quote["quoteNumber"] = next_quote_number((quote.get("client") or {}).get("name", "Wulkan"))
    quote["status"] = "draft"
    quote["version"] = 1
    quote["versions"] = []
    quote["convertedOrderId"] = ""
    quote["createdAt"] = utc_now()
    quote["updatedAt"] = quote["createdAt"]
    quote["createdById"] = session.get("admin_user_id", "")
    quote["createdByName"] = session.get("admin_name", "Sistema")
    quote["history"] = []
    append_quote_history(quote, "draft", f"Duplicada desde {source.get('quoteNumber', source.get('id', ''))}.")
    store.setdefault("quotes", []).append(quote)
    record_audit_event(
        store,
        "create",
        "quote",
        quote["id"],
        f"Cotizacion {quote['quoteNumber']} duplicada desde {source.get('quoteNumber', '')}.",
    )
    save_store(store)
    return redirect(url_for("quotes"))


@app.post("/quotes/<quote_id>/convert")
@require_roles(*roles_for_action("orders", "create"))
def quote_convert(quote_id: str):
    store = load_store()
    quote = find_by_id(store.get("quotes", []), quote_id)
    if not quote or not can_access_quote_record(quote, store):
        return redirect(url_for("quotes"))
    if quote.get("convertedOrderId"):
        return redirect(url_for("orders"))
    before = copy.deepcopy(quote)
    if quote.get("status") not in {"accepted", "sent", "viewed", "negotiation"}:
        quote["status"] = "accepted"
        quote["acceptedAt"] = utc_now()
        append_quote_history(quote, "accepted", "Aceptada al convertir en orden.")
    order, error = build_commercial_order(
        store,
        quote_to_order_payload(quote),
        actor=order_actor(),
        default_channel="seller_assisted",
    )
    if error:
        return render_template("quotes.html", **quotes_page_context(store, error)), 400
    order["quoteId"] = quote["id"]
    order["quoteNumber"] = quote.get("quoteNumber", "")
    append_order_history(order, order.get("status", ""), f"Orden creada desde cotizacion {quote.get('quoteNumber', '')}.")
    store.setdefault("orders", []).append(order)
    quote["status"] = "converted"
    quote["convertedOrderId"] = order["orderId"]
    quote["updatedAt"] = utc_now()
    append_quote_history(quote, "converted", f"Convertida en orden {order['orderId']}.")
    record_change_event(
        store,
        "quote_convert",
        "quote",
        quote_id,
        f"Cotizacion {quote.get('quoteNumber', quote_id)} convertida en orden {order['orderId']}.",
        before,
        quote,
    )
    record_audit_event(
        store,
        "create",
        "order",
        order["orderId"],
        f"Orden creada desde cotizacion {quote.get('quoteNumber', '')}.",
    )
    notify_quote_accepted(store, quote, order)
    notify_order_created(store, order)
    save_store(store)
    return redirect(url_for("orders"))


@app.get("/quotes/<quote_id>/download")
@require_roles(*roles_for_action("quotes", "export"))
def quote_download(quote_id: str):
    store = load_store()
    quote = find_by_id(store.get("quotes", []), quote_id)
    if not quote or not can_access_quote_record(quote, store):
        return redirect(url_for("quotes"))
    enriched = enrich_quote(quote)
    html = render_template("quote_print.html", quote=enriched)
    filename = f"{enriched.get('quoteNumber', 'cotizacion')}.html".replace("/", "-")
    return Response(
        html,
        mimetype="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
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
        notify_order_created(store, order)
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
    notify_order_status_change(store, order, before.get("status", ""))
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
    notify_payment_registered(store, order, movement)
    notify_order_status_change(store, order, before.get("status", ""))
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


def dispatch_page_context(store: dict) -> dict:
    movements = store.get("credit_movements", [])
    filters = {
        "q": request.args.get("q", "").strip(),
        "status": request.args.get("status", "").strip(),
        "seller": request.args.get("seller", "").strip(),
        "view": request.args.get("view", "active").strip() or "active",
    }
    orders = [
        enrich_order(order, movements)
        for order in visible_orders_for_current_user(store)
        if order.get("status") not in {"credit_review", "payment_under_review", "cancelled", "rejected"}
    ]
    if filters["view"] == "active":
        orders = [order for order in orders if order.get("dispatchStatus") not in {"delivered", "closed", "cancelled"}]
    elif filters["view"] == "delivered":
        orders = [order for order in orders if order.get("dispatchStatus") in {"delivered", "closed"}]
    elif filters["view"] == "issues":
        orders = [order for order in orders if order.get("dispatchStatus") in {"failed", "rescheduled", "returned"}]
    if filters["q"]:
        query = filters["q"].lower()
        orders = [
            order for order in orders
            if query in " ".join(
                [
                    order.get("orderId", ""),
                    order.get("customerName", ""),
                    order.get("sellerName", ""),
                    order.get("shippingAddress", ""),
                    order.get("carrierName", ""),
                    order.get("trackingNumber", ""),
                ]
            ).lower()
        ]
    if filters["status"]:
        orders = [order for order in orders if order.get("dispatchStatus") == filters["status"]]
    if filters["seller"]:
        orders = [order for order in orders if order.get("sellerId") == filters["seller"]]
    metrics = {
        "pending": sum(1 for order in orders if order.get("dispatchStatus") == "pending"),
        "preparing": sum(1 for order in orders if order.get("dispatchStatus") in {"preparing", "prepared", "ready"}),
        "in_route": sum(1 for order in orders if order.get("dispatchStatus") in {"in_route", "dispatched"}),
        "delivered": sum(1 for order in orders if order.get("dispatchStatus") in {"delivered", "closed"}),
        "issues": sum(1 for order in orders if order.get("dispatchStatus") in {"failed", "rescheduled", "returned"}),
    }
    status_graph = {
        "title": "Despacho por estado",
        "items": [
            {"label": label, "value": sum(1 for order in orders if order.get("dispatchStatus") == status)}
            for status, label in DISPATCH_STATUS_LABELS.items()
            if sum(1 for order in orders if order.get("dispatchStatus") == status)
        ],
    }
    status_graph["max"] = max([item["value"] for item in status_graph["items"]] or [1])
    return {
        "orders": sorted(orders, key=lambda item: (item.get("estimatedDispatchAt", ""), item.get("createdAt", ""))),
        "metrics": metrics,
        "filters": filters,
        "status_graph": status_graph,
        "dispatch_status_options": list(DISPATCH_STATUS_LABELS.items()),
        "sellers": sales_users(store),
        "can_edit_dispatch": can_module_action("dispatch", "edit"),
        "can_export_dispatch": can_module_action("dispatch", "export"),
    }


@app.get("/dispatch")
@require_roles(*roles_for_action("dispatch", "view"))
def dispatch():
    store = load_store()
    return render_template("dispatch.html", **dispatch_page_context(store))


@app.get("/dispatch/export")
@require_roles(*roles_for_action("dispatch", "export"))
def dispatch_export():
    store = load_store()
    context = dispatch_page_context(store)
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "orden",
            "cliente",
            "direccion_despacho",
            "receptor",
            "telefono_receptor",
            "transportista",
            "guia",
            "estimado_despacho",
            "despachado",
            "estimado_entrega",
            "entregado",
            "estado",
            "responsable",
            "evidencia",
            "observacion",
        ],
        lineterminator="\n",
    )
    writer.writeheader()
    for order in context["orders"]:
        writer.writerow(
            {
                "orden": order.get("orderId", ""),
                "cliente": order.get("customerName", ""),
                "direccion_despacho": order.get("shippingAddress", ""),
                "receptor": order.get("receiverName", ""),
                "telefono_receptor": order.get("receiverPhone", ""),
                "transportista": order.get("carrierName", ""),
                "guia": order.get("trackingNumber", ""),
                "estimado_despacho": order.get("estimatedDispatchAt", ""),
                "despachado": order.get("dispatchedAt", ""),
                "estimado_entrega": order.get("estimatedDeliveryAt", ""),
                "entregado": order.get("deliveredAt", ""),
                "estado": order.get("dispatchStatusLabel", ""),
                "responsable": order.get("logisticsOwner", ""),
                "evidencia": order.get("deliveryEvidenceUrl", ""),
                "observacion": order.get("logisticsNote", ""),
            }
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=despacho_wulkan.csv"},
    )


@app.post("/dispatch/<order_id>/update")
@require_roles(*roles_for_action("dispatch", "edit"))
def dispatch_update(order_id: str):
    store = load_store()
    order = find_order(store.get("orders", []), order_id)
    if not order or not can_access_order_record(order, store):
        return redirect(url_for("dispatch"))
    before = copy.deepcopy(order)
    target_status = request.form.get("dispatchStatus", order.get("dispatchStatus", "pending"))
    if target_status not in DISPATCH_STATUS_LABELS:
        target_status = order.get("dispatchStatus", "pending")
    uploaded_evidence = save_upload(request.files.get("deliveryEvidenceFile"), "library")
    evidence_url = uploaded_evidence or sanitize_url(request.form.get("deliveryEvidenceUrl", ""))
    now = utc_now()
    for field in (
        "receiverName",
        "receiverPhone",
        "carrierName",
        "trackingNumber",
        "estimatedDispatchAt",
        "dispatchedAt",
        "estimatedDeliveryAt",
        "deliveredAt",
        "logisticsNote",
        "logisticsOwner",
    ):
        incoming = sanitize_text(request.form.get(field, ""), max_length=500, allow_newlines=field == "logisticsNote")
        if incoming:
            order[field] = incoming
    if evidence_url:
        order["deliveryEvidenceUrl"] = evidence_url
    order["dispatchStatus"] = target_status
    if target_status == "preparing":
        order["status"] = "preparing"
        order["currentOwner"] = "Despacho"
    elif target_status in {"ready", "prepared"}:
        order["currentOwner"] = "Despacho"
    elif target_status in {"in_route", "dispatched"}:
        order["dispatchedAt"] = order.get("dispatchedAt") or now
        order["currentOwner"] = "Despacho"
    elif target_status == "delivered":
        order["deliveredAt"] = order.get("deliveredAt") or now
        apply_inventory_transition(store, order, "delivered")
        order["status"] = "delivered" if order_balance_usd(order, store.get("credit_movements", [])) > 0 else "paid"
        order["currentOwner"] = "Cobranza" if order_balance_usd(order, store.get("credit_movements", [])) > 0 else "Cierre"
    elif target_status == "closed":
        order["currentOwner"] = "Cierre"
    elif target_status in {"failed", "rescheduled", "returned"}:
        order["currentOwner"] = "Despacho"
    order["updatedAt"] = now
    order.setdefault("dispatchHistory", []).append(
        {
            "status": target_status,
            "label": dispatch_status_label(target_status),
            "note": order.get("logisticsNote", ""),
            "adminName": session.get("admin_name", "Admin"),
            "createdAt": now,
        }
    )
    append_order_history(order, order.get("status", ""), f"Despacho: {dispatch_status_label(target_status)}.")
    record_change_event(
        store,
        "dispatch_update",
        "order",
        order_id,
        f"Despacho actualizado a {dispatch_status_label(target_status)}.",
        before,
        order,
    )
    save_store(store)
    return redirect(url_for("dispatch"))


@app.get("/commissions")
@require_roles(*roles_for_action("commissions", "view"))
def commissions():
    store = load_store()
    return render_template("commissions.html", **commissions_page_context(store))


@app.get("/commissions/export")
@require_roles(*roles_for_action("commissions", "export"))
def commissions_export():
    store = load_store()
    context = commissions_page_context(store)
    output = io.StringIO()
    fieldnames = [
        "orden",
        "fecha_generacion",
        "vendedor",
        "cliente",
        "total_venta_usd",
        "base_comisionable_usd",
        "porcentaje",
        "comision_usd",
        "regla",
        "estado_comision",
        "fecha_aprobacion",
        "aprobado_por",
        "fecha_pago",
        "pagado_por",
        "saldo_orden_usd",
        "bloqueos",
        "observacion",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for order in context["orders"]:
        writer.writerow(
            {
                "orden": order.get("orderId", ""),
                "fecha_generacion": order.get("commissionGeneratedAt", ""),
                "vendedor": order.get("sellerName", ""),
                "cliente": order.get("customerName", ""),
                "total_venta_usd": order.get("totalUsd", 0),
                "base_comisionable_usd": order.get("commissionBaseUsd", 0),
                "porcentaje": order.get("commissionRatePercent", 0),
                "comision_usd": order.get("commissionUsd", 0),
                "regla": order.get("commissionRuleLabel", ""),
                "estado_comision": order.get("commissionStatusLabel", ""),
                "fecha_aprobacion": order.get("commissionApprovedAt", ""),
                "aprobado_por": order.get("commissionApprovedBy", ""),
                "fecha_pago": order.get("commissionPaidAt", ""),
                "pagado_por": order.get("commissionPaidBy", ""),
                "saldo_orden_usd": order.get("balanceUsd", 0),
                "bloqueos": " | ".join(order.get("commissionReleaseBlockers") or []),
                "observacion": order.get("commissionObservation", ""),
            }
        )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=comisiones_wulkan.csv"},
    )


@app.post("/commissions/<order_id>/status")
@require_roles(*roles_for_action("commissions", "approve"))
def commission_status_update(order_id: str):
    store = load_store()
    order = find_order(store.get("orders", []), order_id)
    if not order:
        return redirect(url_for("commissions"))
    before = copy.deepcopy(order)
    status = request.form.get("commissionStatus", order.get("commissionStatus", "commission_pending"))
    if status not in {key for key, _label in COMMISSION_STATUS_OPTIONS}:
        return redirect(url_for("commissions"))
    note = request.form.get("commissionObservation", "").strip()
    hold_reason = request.form.get("commissionHoldReason", "").strip()
    movements = store.get("credit_movements", [])
    client_lookup = {
        client.get("id", ""): enrich_client(client, store.get("orders", []), movements)
        for client in store.get("clients", [])
    }
    enriched = enrich_commission_order(enrich_order(order, movements), client_lookup)
    if status in {"commission_approved", "commission_paid"} and order.get("status") in {"cancelled", "rejected"}:
        return render_template(
            "commissions.html",
            **commissions_page_context(store, "No se puede aprobar ni pagar comision de una orden anulada o rechazada."),
        ), 400
    if status == "commission_paid" and enriched.get("commissionReleaseBlockers"):
        return render_template(
            "commissions.html",
            **commissions_page_context(store, "No se puede pagar la comision: " + ", ".join(enriched["commissionReleaseBlockers"])),
        ), 400
    if status in {"commission_withheld", "commission_cancelled"} and not note and not hold_reason:
        return render_template(
            "commissions.html",
            **commissions_page_context(store, "Indica una observacion para retener o anular una comision."),
        ), 400
    order["commissionStatus"] = status
    order["updatedAt"] = utc_now()
    order["commissionObservation"] = note
    order["commissionHoldReason"] = hold_reason
    if status in {"commission_approved", "commission_paid"}:
        order["commissionApprovedAt"] = order.get("commissionApprovedAt") or utc_now()
        order["commissionApprovedBy"] = order.get("commissionApprovedBy") or session.get("admin_name", "Admin")
    elif status not in {"commission_approved", "commission_paid"}:
        order["commissionApprovedAt"] = ""
        order["commissionApprovedBy"] = ""
    if status == "commission_paid":
        order["commissionPaidAt"] = order.get("commissionPaidAt") or utc_now()
        order["commissionPaidBy"] = session.get("admin_name", "Admin")
    else:
        order["commissionPaidAt"] = ""
        order["commissionPaidBy"] = ""
    append_order_history(
        order,
        order.get("status", "credit_review"),
        f"Comision marcada como {commission_status_label(status)}. {note or hold_reason}".strip(),
    )
    record_change_event(
        store,
        "commission_update",
        "order",
        order_id,
        f"Comision actualizada a {commission_status_label(status)} por {session.get('admin_name', 'Admin')}.",
        before,
        order,
    )
    notify_commission_status(store, order, status)
    save_store(store)
    return redirect(url_for("commissions"))


@app.get("/reports")
@require_roles(*roles_for_action("reports", "view"))
def reports():
    store = load_store()
    return render_template("reports.html", **reports_page_context(store))


@app.get("/reports/export")
@require_roles(*roles_for_action("reports", "export"))
def reports_export():
    export_format = request.args.get("format", "csv").strip().lower()
    store = load_store()
    context = reports_page_context(store)
    record_audit_event(
        store,
        "export",
        "report",
        context["filters"]["type"],
        f"Reporte {context['report_title']} exportado en {export_format}.",
        metadata={"filters": context["filters"]},
    )
    save_store(store)
    if export_format == "xlsx":
        return report_response_xlsx(context)
    return report_response_csv(context)


@app.get("/reports/print")
@require_roles(*roles_for_action("reports", "export"))
def reports_print():
    store = load_store()
    context = reports_page_context(store)
    record_audit_event(
        store,
        "export",
        "report",
        context["filters"]["type"],
        f"Reporte {context['report_title']} abierto para PDF.",
        metadata={"filters": context["filters"], "format": "print"},
    )
    save_store(store)
    return render_template("reports_print.html", **context)


@app.route("/announcements", methods=["GET", "POST"])
@require_roles(*roles_for_action("announcements", "view"))
def announcements():
    store = load_store()
    if request.method == "POST":
        if not can_module_action("announcements", "create"):
            return forbidden_response()
        title = sanitize_text(request.form.get("title", ""), max_length=160, allow_newlines=False)
        uploaded_image = save_upload(request.files.get("imageFile"), "announcements")
        image_url = uploaded_image or sanitize_url(request.form.get("imageUrl", ""))
        announcement = {
            "id": next_id("ann", title),
            "title": title,
            "body": sanitize_text(request.form.get("body", ""), max_length=700),
            "placement": sanitize_text(request.form.get("placement", "home"), max_length=50, allow_newlines=False),
            "priority": int(request.form.get("priority") or 50),
            "ctaLabel": sanitize_text(request.form.get("ctaLabel", ""), max_length=80, allow_newlines=False),
            "ctaUrl": sanitize_url(request.form.get("ctaUrl", ""), allow_deeplink=True),
            "imageUrl": image_url,
            "startsAt": sanitize_text(request.form.get("startsAt") or utc_now(), max_length=32, allow_newlines=False),
            "endsAt": sanitize_text(request.form.get("endsAt", ""), max_length=32, allow_newlines=False),
            "status": sanitize_text(request.form.get("status", "active"), max_length=50, allow_newlines=False),
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
        image_url = sanitize_url(request.form.get("imageUrl", "")) or announcement.get("imageUrl", "")
        uploaded = save_upload(request.files.get("imageFile"), "announcements")
        if uploaded:
            image_url = uploaded
        announcement.update(
            {
                "title": sanitize_text(request.form.get("title", ""), max_length=160, allow_newlines=False),
                "body": sanitize_text(request.form.get("body", ""), max_length=700),
                "placement": sanitize_text(request.form.get("placement", "home"), max_length=50, allow_newlines=False),
                "priority": int(request.form.get("priority") or 50),
                "ctaLabel": sanitize_text(request.form.get("ctaLabel", ""), max_length=80, allow_newlines=False),
                "ctaUrl": sanitize_url(request.form.get("ctaUrl", ""), allow_deeplink=True),
                "imageUrl": image_url,
                "startsAt": sanitize_text(request.form.get("startsAt", ""), max_length=32, allow_newlines=False) or announcement.get("startsAt", ""),
                "endsAt": sanitize_text(request.form.get("endsAt", ""), max_length=32, allow_newlines=False),
                "status": sanitize_text(request.form.get("status", "active"), max_length=50, allow_newlines=False),
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
    push_admin_toast("Banner eliminado del carrusel movil.", "warning", "Anuncio actualizado")
    save_store(store)
    return redirect(url_for("announcements"))


@app.post("/api/v1/mobile/orders")
@app.post("/api/mobile/orders")
def api_create_order():
    store = load_store()
    payload = request.get_json(silent=True) or {}
    customer_payload = payload.get("customer") or {}
    client, auth_error = require_mobile_client(store)
    if auth_error:
        return auth_error, 401
    customer_id = (client or {}).get("id") or customer_payload.get("id", "")
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
    notify_order_created(store, order)
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


@app.get("/api/v1/mobile/orders")
@app.get("/api/mobile/orders")
def api_orders():
    store = load_store()
    client, auth_error = require_mobile_client(store)
    if auth_error:
        return auth_error, 401
    customer_id = (client or {}).get("id") or request.args.get("customerId", "").strip()
    orders = store.get("orders", [])
    if customer_id:
        orders = [order for order in orders if order.get("customerId") == customer_id]
    movements = store.get("credit_movements", [])

    items = [enrich_order(order, movements) for order in orders]
    items, filters = filter_mobile_orders(items)
    items, sort = sort_mobile_orders(items)
    return mobile_paginated_response(items, filters, sort)


@app.get("/api/v1/mobile/notifications")
@app.get("/api/mobile/notifications")
def api_mobile_notifications():
    store = load_store()
    subject_type, subject_id, role, auth_error = mobile_notification_subject(store)
    if auth_error:
        return auth_error, 401
    if generate_mobile_subject_notifications(store, subject_type, subject_id, role):
        save_store(store)
    status = request.args.get("status", "").strip()
    notifications = mobile_notifications_for_subject(store, subject_type, subject_id, role)
    if status:
        notifications = [item for item in notifications if item.get("status", "unread") == status]
    items = [mobile_notification_payload(item) for item in notifications]
    return mobile_paginated_response(items, {"status": status, "subject": subject_type}, "created_desc")


@app.post("/api/v1/mobile/notifications/<notification_id>/read")
@app.post("/api/mobile/notifications/<notification_id>/read")
def api_mobile_notification_read(notification_id: str):
    store = load_store()
    subject_type, subject_id, role, auth_error = mobile_notification_subject(store)
    if auth_error:
        return auth_error, 401
    visible_ids = {
        notification.get("id")
        for notification in mobile_notifications_for_subject(store, subject_type, subject_id, role)
    }
    notification = find_by_id(store.get("notifications", []), notification_id)
    if not notification or notification_id not in visible_ids:
        return jsonify({"error": "Notificacion no encontrada."}), 404
    notification["status"] = "read"
    notification["readAt"] = utc_now()
    notification["updatedAt"] = notification["readAt"]
    save_store(store)
    return jsonify({"notification": mobile_notification_payload(notification)})


@app.get("/api/v1/mobile/seller/summary")
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


@app.route("/api/v1/mobile/seller/clients", methods=["GET", "POST"])
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
            if str(term).strip().isdigit() and int(term) in payment_term_options(store)
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
        create_notification(
            store,
            title="Cliente nuevo por vendedor",
            body=f"{user.get('name', 'Vendedor Wulkan')} creo {client['businessName']}.",
            notification_type="client_created_by_seller",
            priority="normal",
            recipient_type="admin",
            channel="web",
            module="clients",
            entity_type="client",
            entity_id=client["id"],
            href=notification_url("clients", q=client["businessName"]),
            metadata={"clientId": client["id"], "sellerId": user["id"]},
            dedupe_key=f"admin-client-created-{client['id']}",
        )
        notify_seller(
            store,
            user["id"],
            "Cliente asignado",
            f"{client['businessName']} quedo asignado a tu cartera.",
            notification_type="client_assigned",
            priority="normal",
            module="clients",
            entity_type="client",
            entity_id=client["id"],
            deep_link=f"wulkan://seller/clients/{client['id']}",
            metadata={"clientId": client["id"]},
            dedupe_key=f"seller-client-assigned-{client['id']}",
        )
        notify_credit_requested(store, client)
        save_store(store)
        response = mobile_seller_client_payload(client, store)
        response["temporaryPassword"] = temporary_password
        return jsonify({"client": response}), 201

    clients = [mobile_seller_client_payload(client, store) for client in seller_scope_clients(store, user)]
    clients, filters = filter_mobile_clients(clients)
    clients, sort = sort_mobile_clients(clients)
    return mobile_paginated_response(clients, filters, sort)


@app.route("/api/v1/mobile/seller/orders", methods=["GET", "POST"])
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
        notify_order_created(store, order)
        save_store(store)
        return jsonify({"order": mobile_seller_order_payload(order, store), "orderId": order["orderId"]}), 201

    orders = [mobile_seller_order_payload(order, store) for order in seller_scope_orders(store, user)]
    orders, filters = filter_mobile_orders(orders)
    orders, sort = sort_mobile_orders(orders)
    return mobile_paginated_response(orders, filters, sort)


@app.get("/api/v1/mobile/seller/commissions")
@app.get("/api/mobile/seller/commissions")
def api_mobile_seller_commissions():
    store = load_store()
    user, auth_error = require_mobile_sales_user(store)
    if auth_error:
        return auth_error, 401
    orders = [
        mobile_seller_order_payload(order, store)
        for order in seller_scope_orders(store, user)
        if float(order.get("commissionUsd") or 0) > 0
    ]
    commission_status = request.args.get("commissionStatus", "").strip()
    if commission_status:
        orders = [order for order in orders if order.get("commissionStatus") == commission_status]
    orders, filters = filter_mobile_orders(orders)
    filters["commissionStatus"] = commission_status
    orders, sort = sort_mobile_orders(orders)
    return mobile_paginated_response(orders, filters, sort)


@app.route("/api/v1/mobile/seller/quotes", methods=["GET", "POST"])
@app.route("/api/mobile/seller/quotes", methods=["GET", "POST"])
def api_mobile_seller_quotes():
    store = load_store()
    user, auth_error = require_mobile_sales_user(store)
    if auth_error:
        return auth_error, 401

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        customer_id = str(payload.get("customerId") or (payload.get("customer") or {}).get("id") or "").strip()
        if not can_mobile_seller_access_client(store, user, customer_id):
            return jsonify({"error": "Cliente fuera de tu cartera."}), 403
        client = find_by_id(store.get("clients", []), customer_id)
        raw_items = payload.get("items") or []
        if not isinstance(raw_items, list) or not raw_items:
            return jsonify({"error": "Agrega al menos un producto a la cotizacion."}), 400

        items: list[dict] = []
        gross_usd = 0.0
        total_usd = 0.0
        products = store.get("products", [])
        for index, raw_item in enumerate(raw_items, start=1):
            if not isinstance(raw_item, dict):
                return jsonify({"error": f"Producto {index} invalido."}), 400
            product_ref = str(raw_item.get("productId") or raw_item.get("sku") or "").strip()
            quantity = safe_int(raw_item.get("quantity"), 0)
            if not product_ref or quantity <= 0:
                return jsonify({"error": f"Producto {index} requiere SKU/id y cantidad."}), 400
            product = next(
                (
                    item
                    for item in products
                    if item.get("id") == product_ref or item.get("sku") == product_ref
                ),
                None,
            )
            if not product or product.get("status") != "active":
                return jsonify({"error": f"Producto {product_ref} no disponible."}), 400
            unit_price = safe_float(
                raw_item.get("unitPriceUsd"),
                safe_float(product.get("b2bPriceUsd"), safe_float(product.get("publicPriceUsd"), 0)),
            )
            discount_percent = max(0.0, min(100.0, safe_float(raw_item.get("discountPercent"), 0)))
            line_gross = round(unit_price * quantity, 2)
            line_discount = round(line_gross * discount_percent / 100, 2)
            line_total = round(max(0.0, line_gross - line_discount), 2)
            gross_usd += line_gross
            total_usd += line_total
            items.append(
                {
                    "productId": product.get("id", ""),
                    "sku": product.get("sku", ""),
                    "title": product.get("title", "Producto Wulkan"),
                    "quantity": quantity,
                    "unitPriceUsd": unit_price,
                    "discountPercent": discount_percent,
                    "lineGrossUsd": line_gross,
                    "lineDiscountUsd": line_discount,
                    "lineTotalUsd": line_total,
                    "imageUrl": product.get("imageUrl", ""),
                    "requiresQuote": bool(product.get("requiresQuote")),
                    "requiresTechnicalValidation": bool(product.get("requiresTechnicalValidation")),
                }
            )

        exchange_rate = safe_float((payload.get("preview") or {}).get("exchangeRateUsdVes"), current_rate())
        sale_type = str(payload.get("saleType") or "cash")
        if sale_type not in dict(SALE_TYPE_OPTIONS):
            sale_type = "cash"
        payment_term_days = safe_int(payload.get("paymentTermDays"), 0)
        if sale_type == "cash":
            payment_term_days = 0
        now = utc_now()
        quote = {
            "id": next_id("quote", client.get("businessName", "wulkan")),
            "quoteNumber": next_quote_number(client.get("businessName", "Wulkan")),
            "version": 1,
            "versions": [],
            "history": [],
            "clientId": client["id"],
            "client": {
                "id": client["id"],
                "name": client.get("businessName", ""),
                "taxId": client.get("taxId", ""),
                "email": client.get("email", ""),
                "phone": client.get("phone", ""),
                "address": client.get("address", ""),
                "city": client.get("city", ""),
                "state": client.get("state", ""),
            },
            "sellerId": user["id"],
            "sellerName": user.get("name", "Vendedor Wulkan"),
            "items": items,
            "grossUsd": round(gross_usd, 2),
            "discountUsd": round(max(0.0, gross_usd - total_usd), 2),
            "totalUsd": round(total_usd, 2),
            "totalVes": round(total_usd * exchange_rate, 2),
            "exchangeRateUsdVes": exchange_rate,
            "saleType": sale_type,
            "paymentTermDays": payment_term_days,
            "validUntil": str(payload.get("validUntil") or "").strip(),
            "status": "sent" if payload.get("sendToClient") else str(payload.get("status") or "draft"),
            "comment": str(payload.get("comment") or "").strip(),
            "internalComment": str(payload.get("internalComment") or "").strip(),
            "source": "seller_mobile",
            "createdAt": now,
            "createdById": user["id"],
            "createdByName": user.get("name", "Vendedor Wulkan"),
            "updatedAt": now,
        }
        if quote["status"] not in dict(QUOTE_STATUS_OPTIONS):
            quote["status"] = "draft"
        append_quote_history(quote, quote["status"], "Cotizacion creada desde app movil vendedor.")
        store.setdefault("quotes", []).append(quote)
        record_audit_event(
            store,
            "create",
            "quote",
            quote["id"],
            f"Cotizacion movil creada por {user.get('name', 'Vendedor Wulkan')}.",
            actor={"id": user["id"], "name": user.get("name", ""), "role": user.get("role", "")},
        )
        save_store(store)
        return jsonify({"quote": mobile_quote_payload(quote)}), 201

    quotes = [mobile_quote_payload(quote) for quote in seller_scope_quotes(store, user)]
    quotes, filters = filter_mobile_quotes(quotes)
    quotes, sort = sort_mobile_quotes(quotes)
    return mobile_paginated_response(quotes, filters, sort)


@app.route("/api/v1/mobile/seller/activities", methods=["GET", "POST"])
@app.route("/api/mobile/seller/activities", methods=["GET", "POST"])
def api_mobile_seller_activities():
    store = load_store()
    user, auth_error = require_mobile_sales_user(store)
    if auth_error:
        return auth_error, 401

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        customer_id = str(payload.get("customerId") or payload.get("clientId") or "").strip()
        if not can_mobile_seller_access_client(store, user, customer_id):
            return jsonify({"error": "Cliente fuera de tu cartera."}), 403
        client = find_by_id(store.get("clients", []), customer_id)
        note = str(payload.get("note") or payload.get("activityNote") or "").strip()
        if not note:
            return jsonify({"error": "La actividad requiere una nota."}), 400
        activity_type = str(payload.get("activityType") or "note")
        if activity_type not in dict(CRM_ACTIVITY_TYPE_OPTIONS):
            activity_type = "note"
        record_id = str(payload.get("recordId") or "").strip()
        record = find_by_id(store.get("crm_records", []), record_id) if record_id else None
        if record and record not in seller_scope_crm_records(store, user):
            return jsonify({"error": "Registro CRM fuera de tu cartera."}), 403
        if not record:
            now = utc_now()
            record = {
                "id": next_id("crm", client.get("businessName", "seguimiento")),
                "title": str(payload.get("title") or f"Seguimiento {client.get('businessName', 'cliente')}").strip(),
                "recordType": str(payload.get("recordType") or "opportunity"),
                "pipelineStage": str(payload.get("pipelineStage") or "contacted"),
                "status": "active",
                "clientId": client["id"],
                "clientName": client.get("businessName", ""),
                "sellerId": user["id"],
                "sellerName": user.get("name", "Vendedor Wulkan"),
                "contactName": client.get("contactName", ""),
                "phone": client.get("phone", ""),
                "email": client.get("email", ""),
                "state": client.get("state", ""),
                "city": client.get("city", ""),
                "source": "seller_mobile",
                "estimatedValueUsd": safe_float(payload.get("estimatedValueUsd"), 0),
                "probabilityPercent": max(0, min(100, safe_int(payload.get("probabilityPercent"), 0))),
                "expectedCloseAt": str(payload.get("expectedCloseAt") or "").strip(),
                "nextActionAt": str(payload.get("nextActionAt") or "").strip(),
                "description": str(payload.get("description") or "").strip(),
                "lossReason": "",
                "activities": [],
                "createdAt": now,
                "createdById": user["id"],
                "createdByName": user.get("name", "Vendedor Wulkan"),
                "updatedAt": now,
            }
            if record["recordType"] not in dict(CRM_RECORD_TYPE_OPTIONS):
                record["recordType"] = "opportunity"
            if record["pipelineStage"] not in dict(CRM_PIPELINE_STAGE_OPTIONS):
                record["pipelineStage"] = "contacted"
            store.setdefault("crm_records", []).append(record)

        now = utc_now()
        activity = {
            "id": next_id("crm-act", record.get("title", "actividad")),
            "type": activity_type,
            "typeLabel": crm_activity_type_label(activity_type),
            "note": note,
            "nextActionAt": str(payload.get("nextActionAt") or "").strip(),
            "createdById": user["id"],
            "createdByName": user.get("name", "Vendedor Wulkan"),
            "createdAt": now,
        }
        record.setdefault("activities", []).append(activity)
        record["lastActivityAt"] = now
        if activity["nextActionAt"]:
            record["nextActionAt"] = activity["nextActionAt"]
        record["updatedAt"] = now
        record_audit_event(
            store,
            "crm_activity",
            "crm",
            record["id"],
            f"Actividad CRM movil registrada: {crm_activity_type_label(activity_type)}.",
            actor={"id": user["id"], "name": user.get("name", ""), "role": user.get("role", "")},
        )
        save_store(store)
        return jsonify({"record": mobile_crm_record_payload(record), "activity": activity}), 201

    records = [mobile_crm_record_payload(record) for record in seller_scope_crm_records(store, user)]
    records, filters = filter_mobile_crm_records(records)
    records, sort = sort_mobile_crm_records(records)
    return mobile_paginated_response(records, filters, sort)


@app.get("/api/v1/mobile/credit")
@app.get("/api/mobile/credit")
def api_client_credit():
    store = load_store()
    client, auth_error = require_mobile_client(store)
    if auth_error:
        return auth_error, 401
    if not client:
        client = find_by_id(store.get("clients", []), request.args.get("customerId", "").strip())
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


@app.get("/api/v1/mobile/meta")
def api_mobile_meta():
    store = load_store()
    return jsonify(
        {
            "meta": mobile_api_meta(),
            "capabilities": {
                "auth": ["login", "logout", "refresh", "change_password", "recover_password"],
                "mobile": ["home", "products", "product_detail", "categories", "banners", "cart", "orders", "credit", "profile"],
                "seller": ["summary", "clients", "orders", "quotes", "activities", "commissions"],
                "storage": app.config.get("STORAGE_BACKEND"),
                "data": app.config.get("DATA_BACKEND"),
                "tokenRequired": bool(app.config.get("REQUIRE_MOBILE_TOKEN")),
            },
            "counts": {
                "products": len(store.get("products", [])),
                "categories": len(store.get("categories", [])),
                "announcements": len(store.get("announcements", [])),
                "serviceTechnicians": len(store.get("service_technicians", [])),
            },
        }
    )


@app.get("/api/v1/mobile/home")
def api_mobile_home():
    store = load_store()
    profile, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401

    products = sorted(
        mobile_visible_products(store),
        key=lambda product: product.get("createdAt", ""),
        reverse=True,
    )
    featured_products = [product for product in products if product.get("featured")][:8] or products[:8]
    sale_products = [product for product in products if product.get("onSale") or product.get("hasDiscount")][:8]
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
            [enrich_category(item, store) for item in store.get("categories", []) if item.get("status", "active") == "active"],
            key=lambda item: (safe_int(item.get("sortOrder"), 0), item.get("name", "")),
        )
        if category.get("visibleInApp")
    ]
    payload = {
        "meta": mobile_api_meta(),
        "home": {
            "banners": active_announcements("home", store),
            "categories": categories[:10],
            "featuredProducts": [mobile_product_payload(product) for product in featured_products],
            "saleProducts": [mobile_product_payload(product) for product in sale_products],
            "recentProducts": [mobile_product_payload(product) for product in products[:8]],
        },
    }
    if isinstance(profile, dict):
        payload["home"]["role"] = profile.get("role", profile.get("accountRole", "client"))
    return jsonify(payload)


@app.get("/api/v1/mobile/profile")
def api_mobile_profile():
    store = load_store()
    profile, auth_error = mobile_profile_from_token(store)
    if auth_error:
        return auth_error, 401
    return jsonify({"meta": mobile_api_meta(), "profile": profile})


@app.get("/api/v1/mobile/cart")
def api_mobile_cart():
    store = load_store()
    _, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    return jsonify(
        {
            "meta": mobile_api_meta(),
            "items": [],
            "mode": "local_persistent",
            "message": "El carrito se mantiene en almacenamiento seguro del dispositivo y las ordenes se sincronizan al confirmar.",
        }
    )


@app.get("/api/v1/mobile/categories")
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
    categories, filters = filter_mobile_categories(categories)
    categories, sort = sort_mobile_categories(categories)
    return mobile_paginated_response(categories, filters, sort)


@app.post("/api/v1/mobile/auth/login")
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
        client["lastMobileLoginIp"] = request_ip_address()
        client["lastMobileDeviceId"] = mobile_device_id()
        client["mobileSessionVersion"] = safe_int(client.get("mobileSessionVersion"), 0)
        access_token = issue_mobile_token(client)
        record_audit_event(
            store,
            "login",
            "client",
            client["id"],
            "Inicio de sesion movil.",
            actor={"id": client["id"], "name": client.get("businessName", email), "role": "client"},
            metadata={"ipAddress": client["lastMobileLoginIp"], "deviceId": client["lastMobileDeviceId"]},
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
        admin_user["lastMobileLoginIp"] = request_ip_address()
        admin_user["lastMobileDeviceId"] = mobile_device_id()
        access_token = issue_mobile_admin_token(admin_user)
        record_audit_event(
            store,
            "login",
            "admin_user",
            admin_user["id"],
            "Inicio de sesion movil operativo.",
            actor={"id": admin_user["id"], "name": admin_user.get("name", email), "role": admin_user.get("role", "")},
            metadata={"ipAddress": admin_user["lastMobileLoginIp"], "deviceId": admin_user["lastMobileDeviceId"]},
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


@app.post("/api/v1/mobile/auth/refresh")
def api_mobile_refresh_token():
    store = load_store()
    token_payload = mobile_token_payload()
    if not token_payload:
        return jsonify({"error": "Token movil requerido."}), 401

    if token_payload and token_payload.get("type") == "admin":
        user = find_by_id(store.get("admin_users", []), token_payload.get("adminUserId") or token_payload.get("id", ""))
        if (
            not user
            or user.get("status") != "active"
            or user.get("role") not in MOBILE_SALES_ROLES
            or user.get("mobileAccessEnabled", True) is False
            or not mobile_token_version_valid(user, token_payload, "sessionVersion")
        ):
            return jsonify({"error": "Token movil invalido."}), 401
        return jsonify(mobile_admin_payload(user, issue_mobile_admin_token(user)))

    client = find_by_id(store.get("clients", []), token_payload.get("clientId") or token_payload.get("id", ""))
    if not client or client.get("status") != "active" or not mobile_token_version_valid(client, token_payload, "mobileSessionVersion"):
        return jsonify({"error": "Cliente no encontrado."}), 401
    return jsonify(mobile_customer_payload(client, store, issue_mobile_token(client)))


@app.post("/api/v1/mobile/auth/logout")
def api_mobile_logout():
    store = load_store()
    token_payload = mobile_token_payload()
    subject_id = token_payload.get("id", "") if token_payload else ""
    subject_type = "mobile_user"
    subject_name = "App movil"
    subject_role = token_payload.get("role", "mobile") if token_payload else "mobile"
    if token_payload and token_payload.get("type") == "admin":
        subject_type = "admin_user"
        user = find_by_id(store.get("admin_users", []), token_payload.get("adminUserId") or token_payload.get("id", ""))
        subject_name = (user or {}).get("name", subject_id)
    elif token_payload:
        subject_type = "client"
        client = find_by_id(store.get("clients", []), token_payload.get("clientId") or token_payload.get("id", ""))
        subject_name = (client or {}).get("businessName", subject_id)

    record_audit_event(
        store,
        "logout",
        subject_type,
        subject_id,
        "Cierre de sesion desde app movil.",
        actor={"id": subject_id, "name": subject_name, "role": subject_role},
    )
    save_store(store)
    return jsonify({"status": "logged_out"})


@app.post("/api/v1/mobile/auth/change-password")
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
            or not mobile_token_version_valid(subject, token_payload, "sessionVersion")
        ):
            return jsonify({"error": "Token movil invalido."}), 401
    elif not subject or subject.get("status") != "active" or not mobile_token_version_valid(subject, token_payload, "mobileSessionVersion"):
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
    if subject_type == "client":
        subject["mobileSessionVersion"] = safe_int(subject.get("mobileSessionVersion"), 0) + 1
    else:
        bump_user_session_version(subject)
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
    if subject_type == "client":
        access_token = issue_mobile_token(subject)
    else:
        access_token = issue_mobile_admin_token(subject)
    return jsonify({"status": "updated", "mustChangePassword": False, "accessToken": access_token, "tokenType": "Bearer"})


@app.post("/api/v1/mobile/auth/recover-password")
@app.post("/api/mobile/auth/recover-password")
def api_mobile_recover_password():
    store = load_store()
    payload = request.get_json(silent=True) or {}
    email = payload.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "Correo requerido."}), 400

    subject_type = "mobile_user"
    subject_id = email
    subject_name = email
    subject_role = "mobile"
    subject = next(
        (
            item
            for item in store.get("clients", [])
            if item.get("email", "").lower() == email and item.get("status") == "active"
        ),
        None,
    )
    if subject:
        subject_type = "client"
        subject_id = subject.get("id", email)
        subject_name = subject.get("businessName", email)
        subject_role = "client"
    else:
        subject = next(
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
        if subject:
            subject_type = "admin_user"
            subject_id = subject.get("id", email)
            subject_name = subject.get("name", email)
            subject_role = subject.get("role", "mobile")

    if subject:
        subject["passwordRecoveryRequestedAt"] = utc_now()
        subject["passwordRecoveryStatus"] = "pending"
        subject["updatedAt"] = utc_now()

    record_audit_event(
        store,
        "password_reset_request",
        subject_type,
        subject_id,
        "Solicitud de recuperacion de contrasena desde app movil.",
        metadata={"email": email, "status": "received"},
        actor={"id": subject_id, "name": subject_name, "role": subject_role},
    )
    save_store(store)
    return jsonify(
        {
            "status": "received",
            "message": "Si el correo existe, Wulkan gestionara la recuperacion de acceso.",
        }
    )


@app.get("/api/v1/mobile/products")
@app.get("/api/mobile/products")
def api_products():
    store = load_store()
    _, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    products = [mobile_product_payload(product) for product in mobile_visible_products(store)]
    products, filters = filter_mobile_products(products)
    products, sort = sort_mobile_products(products)
    return mobile_paginated_response(products, filters, sort)


@app.get("/api/v1/mobile/products/<product_id>")
@app.get("/api/mobile/products/<product_id>")
def api_mobile_product_detail(product_id: str):
    store = load_store()
    _, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    product = next(
        (
            item
            for item in mobile_visible_products(store)
            if item.get("id") == product_id or item.get("sku") == product_id
        ),
        None,
    )
    if not product:
        return jsonify({"error": "Producto no encontrado."}), 404
    related_skus = {str(sku) for sku in product.get("relatedSkus", [])}
    related_products = [
        mobile_product_payload(item)
        for item in mobile_visible_products(store)
        if item.get("sku") in related_skus and item.get("id") != product.get("id")
    ][:8]
    return jsonify(
        {
            "meta": mobile_api_meta(),
            "product": mobile_product_payload(product),
            "relatedProducts": related_products,
        }
    )


@app.get("/api/v1/mobile/announcements")
@app.get("/api/mobile/announcements")
def api_announcements():
    store = load_store()
    _, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    placement = request.args.get("placement")
    announcements = active_announcements(placement, store)
    announcements, filters = filter_mobile_announcements(announcements)
    announcements, sort = sort_mobile_announcements(announcements)
    return mobile_paginated_response(announcements, filters, sort)


@app.get("/api/v1/mobile/service-technicians")
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
    technicians, filters = filter_mobile_directory_items(technicians)
    technicians, sort = sort_mobile_directory_items(technicians)
    return mobile_paginated_response(technicians, filters, sort)


@app.get("/api/v1/mobile/locations")
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
    locations = [
        {
            "id": technician.get("id", ""),
            "name": technician.get("name", ""),
            "state": technician.get("state", ""),
            "city": technician.get("city", ""),
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
    locations, filters = filter_mobile_directory_items(locations)
    locations, sort = sort_mobile_directory_items(locations)
    return mobile_paginated_response(locations, filters, sort)


@app.context_processor
def inject_helpers():
    return {
        "money_usd": money_usd,
        "usd_to_ves": usd_to_ves,
        "brand_name": "Wulkan",
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=app.config.get("ENV") != "production")
