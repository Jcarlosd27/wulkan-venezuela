from __future__ import annotations

import hashlib
import hmac
import csv
import copy
import io
import math
import os
import re
import secrets
import sys
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, abort, g, has_request_context, jsonify, redirect, render_template, request, send_file, send_from_directory, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from markupsafe import Markup, escape
from sqlalchemy.exc import DataError, IntegrityError, OperationalError, ProgrammingError, SQLAlchemyError
from werkzeug.exceptions import BadRequest, HTTPException
from werkzeug.security import (
    check_password_hash,
    generate_password_hash as werkzeug_generate_password_hash,
)
from werkzeug.utils import secure_filename

from core.config import get_config
from core.insights import rotation_chart, stock_health
from core.storage import generate_s3_signed_url, key_from_public_url, save_uploaded_file, stream_size
from store import (
    DEFAULT_COMPANY_ID,
    INSECURE_PRODUCTION_ADMIN_EMAILS,
    INSECURE_PRODUCTION_CLIENT_EMAILS,
    SAAS_PLAN_ID,
    SAAS_PLAN_NAME,
    SAAS_PLAN_PRICE_CLP,
    load_store,
    next_id,
    save_store,
    utc_now,
    use_sql_backend,
)
from core.uix import badge_class, convert_currency, money_currency, money_usd, usd_to_clp
from core.chile_locations import normalize_chilean_phone, normalize_chilean_rut
from core.country_locations import (
    country_location_labels,
    country_location_options,
    country_location_payload,
    normalize_country_location,
)


def generate_password_hash(password: str, *args, **kwargs) -> str:
    if "method" not in kwargs and not args:
        kwargs["method"] = "scrypt" if hasattr(hashlib, "scrypt") else "pbkdf2:sha256:1000000"
    return werkzeug_generate_password_hash(password, *args, **kwargs)


APP_RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

app = Flask(
    __name__,
    template_folder=str(APP_RESOURCE_ROOT / "templates"),
    static_folder=str(APP_RESOURCE_ROOT / "static"),
)
app.config.from_object(get_config())
app.jinja_env.filters["badge_class"] = badge_class
app.jinja_env.filters["money_usd"] = money_usd


RUNTIME_REQUEST_LOCK = threading.Lock()
RUNTIME_IDENTITY_LOCK = threading.Lock()
RUNTIME_STARTED_AT_EPOCH = int(time.time())
RUNTIME_REQUEST_METRICS = {
    "activeRequests": 0,
    "peakActiveRequests": 0,
    "totalRequests": 0,
    "lastRequestAtEpoch": 0,
}
RUNTIME_SEEN_IDENTITIES: dict[str, dict] = {}
RUNTIME_SEEN_RETENTION_SECONDS = 60 * 60 * 24


CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")
LOCAL_UPLOAD_PREFIX = "/static/uploads/"
IMAGE_UPLOAD_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "webp", "gif"})
PDF_UPLOAD_EXTENSIONS = frozenset({"pdf"})
DOCUMENT_UPLOAD_EXTENSIONS = IMAGE_UPLOAD_EXTENSIONS | PDF_UPLOAD_EXTENSIONS


def safe_export_cell(value):
    if not isinstance(value, str) or not value:
        return value
    if value.lstrip().startswith(CSV_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def safe_export_row(row: dict) -> dict:
    return {key: safe_export_cell(value) for key, value in row.items()}


def safe_export_values(values) -> list:
    return [safe_export_cell(value) for value in values]


class SafeCsvDictWriter(csv.DictWriter):
    def writerow(self, rowdict):
        return super().writerow(safe_export_row(rowdict))

    def writerows(self, rowdicts):
        return super().writerows(safe_export_row(rowdict) for rowdict in rowdicts)


def safe_csv_dict_writer(*args, **kwargs) -> SafeCsvDictWriter:
    return SafeCsvDictWriter(*args, **kwargs)


def safe_internal_url(raw_url: str | None, fallback_endpoint: str = "dashboard") -> str:
    fallback = url_for(fallback_endpoint)
    value = str(raw_url or "").strip()
    if not value:
        return fallback
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return fallback
    return value


def safe_download_filename(raw_filename: str, fallback: str = "fventas.csv") -> str:
    fallback_name = secure_filename(str(fallback or "fventas.csv")) or "fventas.csv"
    cleaned = str(raw_filename or "").replace("\r", "").replace("\n", "").strip()
    filename = secure_filename(cleaned) or fallback_name
    return filename[:180] or fallback_name


def uploaded_document_is_public(filename: str) -> bool:
    normalized = str(filename or "").lstrip("/\\")
    if not normalized.startswith("documents/"):
        return True
    raw_url = f"{LOCAL_UPLOAD_PREFIX}{normalized}"
    try:
        store = load_store()
    except Exception:
        return False
    for asset in store.get("media_assets", []):
        if not document_is_asset(asset) or asset.get("status") == "deleted":
            continue
        asset_url = str(asset.get("url") or "").strip()
        if asset_url == raw_url or document_storage_key(asset_url) == normalized:
            return not document_is_private(asset)
    return False


def runtime_request_begin() -> None:
    now = int(time.time())
    with RUNTIME_REQUEST_LOCK:
        RUNTIME_REQUEST_METRICS["activeRequests"] += 1
        RUNTIME_REQUEST_METRICS["totalRequests"] += 1
        RUNTIME_REQUEST_METRICS["lastRequestAtEpoch"] = now
        RUNTIME_REQUEST_METRICS["peakActiveRequests"] = max(
            RUNTIME_REQUEST_METRICS["peakActiveRequests"],
            RUNTIME_REQUEST_METRICS["activeRequests"],
        )


def runtime_request_end() -> None:
    with RUNTIME_REQUEST_LOCK:
        RUNTIME_REQUEST_METRICS["activeRequests"] = max(
            0,
            RUNTIME_REQUEST_METRICS["activeRequests"] - 1,
        )


def runtime_identity_seen(identity_type: str, company_id: str, subject_id: str, role: str = "") -> None:
    if not identity_type or not subject_id:
        return
    now = int(time.time())
    key = f"{identity_type}:{company_id}:{subject_id}"
    cutoff = now - RUNTIME_SEEN_RETENTION_SECONDS
    if not RUNTIME_IDENTITY_LOCK.acquire(blocking=False):
        return
    try:
        if len(RUNTIME_SEEN_IDENTITIES) > 10000:
            stale_keys = [
                item_key
                for item_key, item in RUNTIME_SEEN_IDENTITIES.items()
                if int(item.get("lastSeenEpoch") or 0) < cutoff
            ]
            for item_key in stale_keys[:2000]:
                RUNTIME_SEEN_IDENTITIES.pop(item_key, None)
        RUNTIME_SEEN_IDENTITIES[key] = {
            "type": identity_type,
            "companyId": company_id,
            "subjectId": subject_id,
            "role": role,
            "lastSeenEpoch": now,
        }
    finally:
        RUNTIME_IDENTITY_LOCK.release()


@app.before_request
def track_runtime_request_start():
    g.runtime_request_counted = True
    runtime_request_begin()
    return None


@app.teardown_request
def track_runtime_request_end(_exc=None):
    if getattr(g, "runtime_request_counted", False):
        runtime_request_end()


def validate_runtime_config() -> None:
    if app.config.get("ENV") != "production":
        return
    database_url = str(app.config.get("DATABASE_URL", ""))
    if app.config.get("SECRET_KEY") in {"fventas-dev"}:
        raise RuntimeError("FVENTAS_SECRET_KEY real es obligatorio en produccion.")
    if app.config.get("DATA_BACKEND") != "sql":
        raise RuntimeError("FVENTAS_DATA_BACKEND=sql es obligatorio en produccion.")
    if database_url.startswith("sqlite"):
        raise RuntimeError("FVENTAS_DATABASE_URL debe apuntar a PostgreSQL en produccion.")
    if app.config.get("SQL_FALLBACK_TO_JSON"):
        raise RuntimeError("FVENTAS_SQL_FALLBACK_TO_JSON debe estar desactivado en produccion.")
    if not app.config.get("REQUIRE_MOBILE_DEVICE_HEADER"):
        raise RuntimeError("FVENTAS_REQUIRE_MOBILE_DEVICE_HEADER debe estar activo en produccion.")
    if app.config.get("ALLOW_LEGACY_MOBILE_API"):
        raise RuntimeError("FVENTAS_ALLOW_LEGACY_MOBILE_API debe estar desactivado en produccion.")
    storage_backend = str(app.config.get("STORAGE_BACKEND", "")).strip().lower()
    if storage_backend != "s3":
        raise RuntimeError("FVENTAS_STORAGE_BACKEND=s3 es obligatorio en produccion.")
    if not app.config.get("S3_BUCKET"):
        raise RuntimeError("FVENTAS_S3_BUCKET es obligatorio en produccion.")


validate_runtime_config()


@app.get("/static/uploads/<path:filename>")
def serve_uploaded_asset(filename: str):
    if not uploaded_document_is_public(filename):
        abort(404)
    configured_upload_root = Path(app.config["UPLOAD_FOLDER"]).resolve()
    requested_file = (configured_upload_root / filename).resolve()
    try:
        requested_file.relative_to(configured_upload_root)
    except ValueError:
        abort(404)
    if requested_file.is_file():
        return send_from_directory(configured_upload_root, filename)

    packaged_static_root = Path(app.static_folder or "").resolve()
    packaged_upload_root = packaged_static_root / "uploads"
    packaged_file = (packaged_upload_root / filename).resolve()
    try:
        packaged_file.relative_to(packaged_upload_root.resolve())
    except ValueError:
        abort(404)
    if packaged_file.is_file():
        return send_from_directory(packaged_upload_root, filename)
    abort(404)


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    csp_value = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
        "font-src 'self' https://cdn.jsdelivr.net data:; "
        "img-src 'self' data: https: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    csp_header = (
        "Content-Security-Policy-Report-Only"
        if app.config.get("CONTENT_SECURITY_POLICY_REPORT_ONLY", True)
        else "Content-Security-Policy"
    )
    response.headers.setdefault(csp_header, csp_value)
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


def database_error_message(exc: SQLAlchemyError) -> tuple[str, str, int]:
    if isinstance(exc, IntegrityError):
        return (
            "integrity_error",
            "El registro ya existe o esta relacionado con otra operacion activa.",
            409,
        )
    if isinstance(exc, DataError):
        return (
            "invalid_database_value",
            "Hay un dato con formato invalido para guardar la operacion.",
            400,
        )
    if isinstance(exc, OperationalError):
        return (
            "database_unavailable",
            "La base de datos no esta disponible temporalmente.",
            503,
        )
    if isinstance(exc, ProgrammingError):
        return (
            "database_schema_error",
            "La operacion requiere revisar la estructura de datos antes de continuar.",
            500,
        )
    return (
        "database_error",
        "No se pudo completar la operacion en la base de datos.",
        500,
    )


@app.errorhandler(SQLAlchemyError)
def handle_database_exception(exc: SQLAlchemyError):
    code, message, status = database_error_message(exc)
    app.logger.exception("Database error %s on %s", code, request.path)
    if request.path.startswith("/api/"):
        return jsonify({"meta": mobile_api_meta(), "error": message, "code": code}), status

    if request.method == "POST":
        push_admin_toast(message, "danger", "Accion no aplicada")
        return redirect(safe_internal_url(request.referrer))

    return render_template("forbidden.html", heading="Accion no aplicada", description=message), status


@app.errorhandler(Exception)
def handle_api_unexpected_exception(exc: Exception):
    if not request.path.startswith("/api/"):
        app.logger.exception("Unexpected web error on %s", request.path)
        if request.method == "POST":
            push_admin_toast(
                "No se pudo completar la operacion. Revisa los datos o intenta nuevamente.",
                "danger",
                "Accion no aplicada",
            )
            return redirect(safe_internal_url(request.referrer))
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
ORDER_PAYMENT_TOLERANCE_USD = 0.01
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
    "mobile": "App Cliente B2B",
    "seller_mobile": "App vendedor",
    "seller_assisted": "Pedido asistido",
    "admin": "Admin",
    "phone": "Telefono",
}
CLIENT_ORIGIN_LABELS = {
    "admin": "Panel admin",
    "import": "Carga masiva",
    "mobile": "App Cliente B2B",
    "client_mobile": "App Cliente B2B",
    "seller_mobile": "App vendedor",
    "seller_assisted": "Pedido asistido",
    "api": "API externa",
}
DISPATCH_STATUS_LABELS = {
    "pending": "Pendiente",
    "preparing": "Preparando",
    "prepared": "Preparado",
    "ready": "Listo para despacho",
    "in_route": "En ruta",
    "dispatched": "Despachado",
    "payment_hold": "Retenido por pago",
    "delivered": "Entregado",
    "failed": "Entrega fallida",
    "rescheduled": "Reprogramado",
    "returned": "Devuelto",
    "closed": "Cerrado",
    "cancelled": "Cancelado",
}
PAYMENT_TERM_OPTIONS = [0, 10, 15, 20, 30, 40]
MARKET_PROFILES = {
    "CL": {
        "code": "CL",
        "label": "Chile",
        "companyNoun": "empresa",
        "taxLabel": "RUT",
        "taxPlaceholder": "76.123.456-7",
        "phonePrefix": "+56",
        "phonePlaceholder": "+56 9 1234 5678",
        "salesCurrency": "CLP",
        "localCurrency": "CLP",
        "exchangeRateBaseToLocal": 1,
        "planCurrency": "CLP",
        "planPrice": 69990,
        "locale": "es-CL",
        "timezone": "America/Santiago",
    },
    "VE": {
        "code": "VE",
        "label": "Venezuela",
        "companyNoun": "empresa",
        "taxLabel": "RIF",
        "taxPlaceholder": "J-12345678-9",
        "phonePrefix": "+58",
        "phonePlaceholder": "+58 412 123 4567",
        "salesCurrency": "USD",
        "localCurrency": "USD",
        "exchangeRateBaseToLocal": 1,
        "planCurrency": "USD",
        "planPrice": 79,
        "locale": "es-VE",
        "timezone": "America/Caracas",
    },
}
ACTIVE_MARKET_COUNTRIES = ("CL", "VE")
ACTIVE_MARKET_PROFILES = {code: MARKET_PROFILES[code] for code in ACTIVE_MARKET_COUNTRIES}
MARKET_COUNTRY_OPTIONS = [(code, MARKET_PROFILES[code]["label"]) for code in ACTIVE_MARKET_COUNTRIES]
LEGAL_TERMS_VERSION = "2026-06-17"
LEGAL_PRIVACY_VERSION = "2026-06-17"
CURRENCY_OPTIONS = [
    ("USD", "USD - Dolar estadounidense"),
    ("CLP", "CLP - Peso chileno"),
]
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
FVENTAS_STARTER_CATEGORY_TREE = [
    {
        "name": "Jardin y Bosque",
        "slug": "jardin-bosque",
        "description": "Equipos para jardin, bosque y mantenimiento de espacios verdes.",
        "icon": "bi-tree",
        "children": [
            ("Ahoyadores", "Perforacion de suelo y trabajo agricola.", "bi-bullseye"),
            ("Chipeadoras", "Reduccion de ramas, poda y material vegetal.", "bi-recycle"),
            ("Cortacesped", "Corte y mantenimiento de cesped.", "bi-scissors"),
            ("Cortasetos", "Corte fino para setos y cercos vivos.", "bi-flower1"),
            ("Motocultivadores", "Preparacion de suelo y labores de cultivo.", "bi-gear-wide-connected"),
            ("Desmalezadoras", "Control de maleza y limpieza de terreno.", "bi-tree"),
            ("Fumigacion", "Equipos para aplicacion agricola y control sanitario.", "bi-droplet"),
            ("Motosierras", "Corte forestal, poda y faena de madera.", "bi-tools"),
            ("Partelenas", "Equipos para partir lena y trabajo forestal.", "bi-diagram-3"),
            ("Sopladores", "Limpieza de hojas, polvo y residuos livianos.", "bi-wind"),
            ("Trituradores", "Trituracion de restos vegetales y material organico.", "bi-boxes"),
        ],
    },
    {
        "name": "Industrial",
        "slug": "industrial",
        "description": "Equipos FVENTAS para faena, industria, obra y trabajo pesado.",
        "icon": "bi-building-gear",
        "children": [],
    },
    {
        "name": "Repuestos",
        "slug": "repuestos",
        "description": "Piezas, consumibles y repuestos compatibles por SKU.",
        "icon": "bi-tools",
        "children": [],
    },
]
FVENTAS_STARTER_PRODUCTS = [
    {
        "sku": "FV-EA-60-3B",
        "title": "Ahoyador 60cc FVENTAS + 3 brocas",
        "categorySlug": "ahoyadores",
        "productType": "machine",
        "model": "FV-EA-60-3B",
        "price": 310,
        "b2bPrice": 285,
        "discount": 7,
        "stock": 4,
        "rotation": 6,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Equipo para perforacion de suelo en jardin, bosque y faena agricola.",
        "variants": ["Incluye 3 brocas", "Uso agricola", "Motor 60cc"],
        "specifications": {"Motor": "60cc", "Categoria": "Ahoyadores", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-EA-750",
        "title": "Ahoyador FVENTAS quick stop 71cc",
        "categorySlug": "ahoyadores",
        "productType": "machine",
        "model": "FV-EA-750",
        "price": 465,
        "b2bPrice": 430,
        "discount": 0,
        "stock": 3,
        "rotation": 4,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Ahoyador de mayor potencia para perforaciones exigentes y trabajo continuo.",
        "variants": ["Quick stop", "Motor 71cc", "Trabajo agricola"],
        "specifications": {"Motor": "71cc", "Categoria": "Ahoyadores", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-WCH-950",
        "title": "Chipeadora 7 HP FVENTAS",
        "categorySlug": "chipeadoras",
        "productType": "machine",
        "model": "FV-WCH-950",
        "price": 890,
        "b2bPrice": 830,
        "discount": 5,
        "stock": 2,
        "rotation": 3,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Chipeadora compacta para ramas, poda y material vegetal.",
        "variants": ["7 HP", "Motor bencinero", "Uso jardin y bosque"],
        "specifications": {"Potencia": "7 HP", "Categoria": "Chipeadoras", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-WCH-2100",
        "title": "Chipeadora 15 HP FVENTAS",
        "categorySlug": "chipeadoras",
        "productType": "machine",
        "model": "FV-WCH-2100",
        "price": 1750,
        "b2bPrice": 1650,
        "discount": 0,
        "stock": 1,
        "rotation": 2,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Chipeadora de alta potencia para reduccion de ramas y trabajo intensivo.",
        "variants": ["15 HP", "Trabajo pesado", "Uso agricola"],
        "specifications": {"Potencia": "15 HP", "Categoria": "Chipeadoras", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-PM-166",
        "title": "Cortacesped de empuje 3 en 1 FVENTAS",
        "categorySlug": "cortacesped",
        "productType": "machine",
        "model": "FV-PM-166",
        "price": 280,
        "b2bPrice": 255,
        "discount": 8,
        "stock": 6,
        "rotation": 8,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Cortacesped de empuje para mantenimiento residencial y comercial.",
        "variants": ["3 en 1", "Empuje", "Uso jardin"],
        "specifications": {"Formato": "Empuje", "Categoria": "Cortacesped", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-PM-170",
        "title": "Cortacesped FVENTAS 170cc de empuje 3 en 1",
        "categorySlug": "cortacesped",
        "productType": "machine",
        "model": "FV-PM-170",
        "price": 335,
        "b2bPrice": 310,
        "discount": 0,
        "stock": 5,
        "rotation": 7,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Cortacesped 170cc para superficies verdes y faenas de mantenimiento.",
        "variants": ["170cc", "3 en 1", "Empuje"],
        "specifications": {"Motor": "170cc", "Categoria": "Cortacesped", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-HT-26",
        "title": "Cortaseto FVENTAS 26cc",
        "categorySlug": "cortasetos",
        "productType": "machine",
        "model": "FV-HT-26",
        "price": 185,
        "b2bPrice": 165,
        "discount": 6,
        "stock": 4,
        "rotation": 4,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Equipo para corte fino de setos, cercos vivos y terminaciones de jardin.",
        "variants": ["26cc", "Corte fino", "Uso jardin"],
        "specifications": {"Motor": "26cc", "Categoria": "Cortasetos", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-MF-51",
        "title": "Multifuncion FVENTAS 52cc 5 en 1",
        "categorySlug": "cortasetos",
        "productType": "machine",
        "model": "FV-MF-51",
        "price": 245,
        "b2bPrice": 220,
        "discount": 0,
        "stock": 3,
        "rotation": 5,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Equipo multifuncional para poda, corte y mantenimiento de areas verdes.",
        "variants": ["5 en 1", "52cc", "Incluye accesorio cortaseto"],
        "specifications": {"Motor": "52cc", "Categoria": "Cortasetos", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-DRT-950",
        "title": "Motocultivador 7 HP motor Loncin",
        "categorySlug": "motocultivadores",
        "productType": "machine",
        "model": "FV-DRT-950",
        "price": 720,
        "b2bPrice": 670,
        "discount": 0,
        "stock": 3,
        "rotation": 4,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Motocultivador bencinero para preparacion de suelo y labores de cultivo.",
        "variants": ["7 HP", "Motor Loncin", "Uso agricola"],
        "specifications": {"Potencia": "7 HP", "Categoria": "Motocultivadores", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-TD-10",
        "title": "Motocultivador diesel 10 HP FVENTAS",
        "categorySlug": "motocultivadores",
        "productType": "machine",
        "model": "FV-TD-10",
        "price": 1420,
        "b2bPrice": 1320,
        "discount": 0,
        "stock": 2,
        "rotation": 2,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Motocultivador diesel para trabajo agricola de mayor exigencia.",
        "variants": ["Diesel", "10 HP", "Trabajo agricola"],
        "specifications": {"Potencia": "10 HP", "Categoria": "Motocultivadores", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-BC-33",
        "title": "Desmalezadora FVENTAS Slim 33cc",
        "categorySlug": "desmalezadoras",
        "productType": "machine",
        "model": "FV-BC-33",
        "price": 155,
        "b2bPrice": 138,
        "discount": 9,
        "stock": 8,
        "rotation": 10,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Desmalezadora liviana para limpieza y mantenimiento de terreno.",
        "variants": ["33cc", "2 tiempos", "Uso jardin"],
        "specifications": {"Motor": "33cc", "Categoria": "Desmalezadoras", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-BC-43L",
        "title": "Desmalezadora FVENTAS Slim 43cc",
        "categorySlug": "desmalezadoras",
        "productType": "machine",
        "model": "FV-BC-43L",
        "price": 185,
        "b2bPrice": 165,
        "discount": 0,
        "stock": 6,
        "rotation": 8,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Desmalezadora 43cc para control de maleza y faena de limpieza.",
        "variants": ["43cc", "2 tiempos", "Trabajo agricola"],
        "specifications": {"Motor": "43cc", "Categoria": "Desmalezadoras", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-MD-43",
        "title": "Fumigador de mochila FVENTAS 41.5cc",
        "categorySlug": "fumigacion",
        "productType": "machine",
        "model": "FV-MD-43",
        "price": 265,
        "b2bPrice": 245,
        "discount": 0,
        "stock": 5,
        "rotation": 6,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Fumigador de mochila para aplicacion agricola y control sanitario.",
        "variants": ["41.5cc", "Mochila", "Aplicacion agricola"],
        "specifications": {"Motor": "41.5cc", "Categoria": "Fumigacion", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-BPS-4T",
        "title": "Pulverizador agricola 4 tiempos 37.7cc",
        "categorySlug": "fumigacion",
        "productType": "machine",
        "model": "FV-BPS-4T",
        "price": 310,
        "b2bPrice": 285,
        "discount": 5,
        "stock": 4,
        "rotation": 5,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Pulverizador de mochila 4 tiempos para trabajo agricola.",
        "variants": ["37.7cc", "4 tiempos", "Mochila"],
        "specifications": {"Motor": "37.7cc", "Categoria": "Fumigacion", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-CS-25",
        "title": "Motosierra de poda FVENTAS 25.4cc",
        "categorySlug": "motosierras",
        "productType": "machine",
        "model": "FV-CS-25",
        "price": 145,
        "b2bPrice": 128,
        "discount": 10,
        "stock": 9,
        "rotation": 13,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Motosierra de poda para cortes livianos y mantencion forestal.",
        "variants": ["25.4cc", "Poda", "Uso forestal"],
        "specifications": {"Motor": "25.4cc", "Categoria": "Motosierras", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-CS-58",
        "title": "Motosierra FVENTAS 54cc agricola",
        "categorySlug": "motosierras",
        "productType": "machine",
        "model": "FV-CS-58",
        "price": 245,
        "b2bPrice": 220,
        "discount": 0,
        "stock": 7,
        "rotation": 11,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Motosierra agricola para corte forestal, poda y faena de madera.",
        "variants": ["54cc", "Agricola", "Uso forestal"],
        "specifications": {"Motor": "54cc", "Categoria": "Motosierras", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-PL-8T",
        "title": "Partidor de lena rapido 8 toneladas",
        "categorySlug": "partelenas",
        "productType": "machine",
        "model": "FV-PL-8T",
        "price": 590,
        "b2bPrice": 550,
        "discount": 0,
        "stock": 2,
        "rotation": 3,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Partidor electrico para lena y faena forestal liviana.",
        "variants": ["8 toneladas", "Electrico", "2 HP"],
        "specifications": {"Fuerza": "8 TON", "Categoria": "Partelenas", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-PL-22",
        "title": "Partidor de lena dual FVENTAS 22 toneladas",
        "categorySlug": "partelenas",
        "productType": "machine",
        "model": "FV-PL-22",
        "price": 1450,
        "b2bPrice": 1350,
        "discount": 4,
        "stock": 1,
        "rotation": 2,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Partidor de lena dual para trabajo forestal de alta exigencia.",
        "variants": ["22 toneladas", "Dual", "Trabajo pesado"],
        "specifications": {"Fuerza": "22 TON", "Categoria": "Partelenas", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-BL-43",
        "title": "Soplador de hojas FVENTAS 43cc",
        "categorySlug": "sopladores",
        "productType": "machine",
        "model": "FV-BL-43",
        "price": 165,
        "b2bPrice": 148,
        "discount": 0,
        "stock": 6,
        "rotation": 8,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Soplador para limpieza de hojas, polvo y residuos livianos.",
        "variants": ["43cc", "Hojas", "Limpieza"],
        "specifications": {"Motor": "43cc", "Categoria": "Sopladores", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-BL-26V",
        "title": "Soplador aspirador FVENTAS 26cc",
        "categorySlug": "sopladores",
        "productType": "machine",
        "model": "FV-BL-26V",
        "price": 155,
        "b2bPrice": 138,
        "discount": 6,
        "stock": 5,
        "rotation": 6,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Soplador aspirador para mantenimiento de areas verdes.",
        "variants": ["26cc", "Soplador aspirador", "Uso jardin"],
        "specifications": {"Motor": "26cc", "Categoria": "Sopladores", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-TG-30",
        "title": "Triturador de granos FVENTAS",
        "categorySlug": "trituradores",
        "productType": "machine",
        "model": "FV-TG-30",
        "price": 280,
        "b2bPrice": 255,
        "discount": 0,
        "stock": 4,
        "rotation": 5,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Triturador de granos para uso agricola y procesamiento liviano.",
        "variants": ["Granos", "Uso agricola", "Electrico"],
        "specifications": {"Aplicacion": "Granos", "Categoria": "Trituradores", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-TG-65",
        "title": "Triturador de granos FVENTAS bencinero",
        "categorySlug": "trituradores",
        "productType": "machine",
        "model": "FV-TG-65",
        "price": 620,
        "b2bPrice": 580,
        "discount": 0,
        "stock": 2,
        "rotation": 3,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Triturador bencinero para faenas agricolas con autonomia de trabajo.",
        "variants": ["Bencinero", "Granos", "Trabajo agricola"],
        "specifications": {"Aplicacion": "Granos", "Categoria": "Trituradores", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-WP-2X2",
        "title": "Motobomba 2x2 FVENTAS Strong",
        "categorySlug": "industrial",
        "productType": "machine",
        "model": "FV-WP-2X2",
        "price": 255,
        "b2bPrice": 235,
        "discount": 0,
        "stock": 6,
        "rotation": 7,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Motobomba para traslado de agua en faena, riego y trabajo industrial.",
        "variants": ["2x2", "Bencinera", "Uso industrial"],
        "specifications": {"Formato": "2x2", "Categoria": "Industrial", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-GEN-6000",
        "title": "Generador bencinero FVENTAS 5.0/5.5 KW",
        "categorySlug": "industrial",
        "productType": "machine",
        "model": "FV-GEN-6000",
        "price": 760,
        "b2bPrice": 710,
        "discount": 5,
        "stock": 2,
        "rotation": 4,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Generador bencinero para respaldo electrico y faenas operativas.",
        "variants": ["5.0/5.5 KW", "Bencinero", "Uso industrial"],
        "specifications": {"Potencia": "5.0/5.5 KW", "Categoria": "Industrial", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-EA-111",
        "title": "Broca ahoyador FVENTAS 100mm punta diamante",
        "categorySlug": "repuestos",
        "productType": "spare_part",
        "model": "FV-EA-111",
        "price": 28,
        "b2bPrice": 24,
        "discount": 0,
        "stock": 12,
        "rotation": 14,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Broca compatible para ahoyadores FVENTAS.",
        "variants": ["100mm", "Punta diamante", "Compatible ahoyador"],
        "specifications": {"Medida": "100mm", "Categoria": "Repuestos", "Origen": "Catalogo inicial FVENTAS"},
    },
    {
        "sku": "FV-EA-107",
        "title": "Broca ahoyador FVENTAS 150mm punta diamante",
        "categorySlug": "repuestos",
        "productType": "spare_part",
        "model": "FV-EA-107",
        "price": 35,
        "b2bPrice": 30,
        "discount": 0,
        "stock": 10,
        "rotation": 11,
        "imageUrl": "/static/uploads/catalog/fventas-product.svg",
        "sourceUrl": "",
        "description": "Broca compatible para ahoyadores FVENTAS en medida 150mm.",
        "variants": ["150mm", "Punta diamante", "Compatible ahoyador"],
        "specifications": {"Medida": "150mm", "Categoria": "Repuestos", "Origen": "Catalogo inicial FVENTAS"},
    },
]
CLIENT_TYPE_OPTIONS = [
    ("b2b", "Cliente B2B"),
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
    ("rif", "Documento fiscal"),
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
    "platform_admin": "Administrador plataforma",
    "super_admin": "Super admin",
    "general_manager": "Gerente general",
    "commercial_manager": "Gerente comercial",
    "operator": "Operador",
    "auditor": "Auditor",
    "sales": "Vendedor app movil",
    "inventory": "Inventario",
    "readonly": "Solo lectura",
}
LOGIN_ATTEMPTS: dict[str, list[float]] = {}
PASSWORD_MIN_LENGTH = 10
IMPORT_DRAFT_TTL_SECONDS = 60 * 60
WEB_ADMIN_ROLES = {"platform_admin", "super_admin", "general_manager", "commercial_manager", "operator", "inventory", "auditor", "readonly"}
WEB_ADMIN_ROLE_ORDER = ["platform_admin", "super_admin", "general_manager", "commercial_manager", "operator", "inventory", "auditor", "readonly"]
WRITE_ROLES = {"platform_admin", "super_admin", "general_manager", "commercial_manager", "operator"}
SALES_ROLES = {"platform_admin", "super_admin", "commercial_manager", "operator"}
INVENTORY_ROLES = {"platform_admin", "super_admin", "commercial_manager", "operator", "inventory"}
CREDIT_APPROVAL_ROLES = {"platform_admin", "super_admin", "general_manager", "commercial_manager"}
ORDER_MANAGEMENT_ROLES = {"platform_admin", "super_admin", "general_manager", "commercial_manager", "operator"}
COMMISSION_MANAGEMENT_ROLES = {"platform_admin", "super_admin", "general_manager", "commercial_manager"}
MOBILE_SALES_ROLES = {"super_admin", "commercial_manager", "sales"}
ADMIN_ONLY_ROLES = {"platform_admin", "super_admin"}
DELETE_ROLES = {"platform_admin", "super_admin"}
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
    ("dashboard", "Dashboard", "bi-grid-1x2", "KPIs ejecutivos e insights comerciales."),
    ("platform_companies", "Empresas SaaS", "bi-buildings", "Empresas suscritas, planes y activacion comercial."),
    ("platform_privacy", "Privacidad plataforma", "bi-person-x", "Solicitudes de eliminacion, bloqueo movil y trazabilidad normativa."),
    ("sellers", "Vendedores", "bi-person-badge", "Fuerza comercial, cartera y metas."),
    ("clients", "Clientes", "bi-shop", "Clientes B2B, datos comerciales y credito."),
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
PLATFORM_MODULES = {"platform_companies", "platform_privacy"}
TENANT_MODULE_KEYS = [module for module in ALL_MODULE_KEYS if module not in PLATFORM_MODULES]
MOBILE_LAUNCH_TENANT_MODULES = {
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
    "notifications",
    "business_rules",
    "admin_users",
    "settings",
    "audit",
    "import_templates",
    "documents",
}
ARCHIVED_TENANT_MODULES = set(TENANT_MODULE_KEYS) - MOBILE_LAUNCH_TENANT_MODULES
ROLE_MODULE_PERMISSIONS = {
    "platform_admin": {module: set(ALL_ACTION_KEYS) for module in ALL_MODULE_KEYS},
    "super_admin": {module: set(ALL_ACTION_KEYS) for module in MOBILE_LAUNCH_TENANT_MODULES},
    "general_manager": {
        module: set(ACTION_AUDIT)
        for module in MOBILE_LAUNCH_TENANT_MODULES
        if module not in {"admin_users", "settings"}
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
        "notifications": set(ACTION_READ | {"edit"}),
        "business_rules": set(ACTION_AUDIT),
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
        "notifications": set(ACTION_READ | {"edit"}),
        "business_rules": set(ACTION_READ),
        "import_templates": set(ACTION_READ),
        "documents": set(ACTION_WORK),
    },
    "auditor": {
        module: set(ACTION_AUDIT)
        for module in MOBILE_LAUNCH_TENANT_MODULES
        if module not in {"admin_users", "settings"}
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
            "notifications",
            "business_rules",
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
for role, permissions in ROLE_MODULE_PERMISSIONS.items():
    if role == "platform_admin":
        continue
    for module in PLATFORM_MODULES | ARCHIVED_TENANT_MODULES:
        permissions[module] = set()
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
        "label": "Plataforma",
        "icon": "bi-buildings",
        "items": [
            {
                "module": "platform_companies",
                "endpoint": "platform_companies",
                "label": "Empresas SaaS",
                "icon": "bi-buildings",
                "active": ["platform_companies", "company_subscription_update"],
            },
            {
                "module": "platform_privacy",
                "endpoint": "platform_privacy",
                "label": "Privacidad",
                "icon": "bi-person-x",
                "active": [
                    "platform_privacy",
                    "platform_privacy_export",
                    "platform_privacy_deletion_action",
                ],
            },
        ],
    },
    {
        "label": "Comercial",
        "icon": "bi-briefcase",
        "items": [
            {"module": "sellers", "endpoint": "sellers", "label": "Vendedores", "icon": "bi-person-badge", "active": ["sellers", "seller_edit", "sellers_import", "seller_delete"]},
            {"module": "clients", "endpoint": "clients", "label": "Clientes", "icon": "bi-shop", "active": ["clients", "client_edit", "client_status_update", "clients_import", "client_account_deletion_complete", "client_delete"]},
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
            {"module": "products", "endpoint": "products", "label": "Productos", "icon": "bi-box-seam", "active": ["products", "product_new", "product_edit", "products_import", "products_export", "products_starter_fventas", "product_duplicate", "product_delete"]},
            {"module": "categories", "endpoint": "categories", "label": "Categorias", "icon": "bi-tags", "active": ["categories", "category_edit", "categories_import", "categories_export", "categories_starter_fventas", "category_status", "category_delete"]},
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
    "company_subscription_update": "platform_companies",
    "platform_privacy_export": "platform_privacy",
    "platform_privacy_deletion_action": "platform_privacy",
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
    "platform_companies": "Empresas SaaS",
    "company_subscription_update": "Actualizar suscripcion",
    "platform_privacy": "Privacidad plataforma",
    "platform_privacy_export": "Exportar privacidad",
    "platform_privacy_deletion_action": "Resolver eliminacion",
    "admin_search": "Busqueda",
    "product_new": "Crear producto",
    "product_edit": "Editar producto",
    "products_import": "Importar productos",
    "products_export": "Exportar productos",
    "products_starter_fventas": "Productos base FVENTAS",
    "category_edit": "Editar categoria",
    "categories_import": "Importar categorias",
    "categories_export": "Exportar categorias",
    "categories_starter_fventas": "Categorias base FVENTAS",
    "seller_edit": "Editar vendedor",
    "sellers_import": "Importar vendedores",
    "client_edit": "Editar cliente",
    "clients_import": "Importar clientes",
    "credit_due": "Vencimientos",
    "credit_history": "Historial credito",
    "client_account_deletion_complete": "Completar eliminacion cliente",
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
    "platform_companies": {"GET": "view", "POST": "create"},
    "company_subscription_update": "edit",
    "platform_privacy": "view",
    "platform_privacy_export": "export",
    "platform_privacy_deletion_action": "approve",
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
    "client_account_deletion_complete": "delete",
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
    "products_starter_fventas": "create",
    "product_new": "create",
    "product_edit": "edit",
    "product_duplicate": "create",
    "product_delete": "delete",
    "categories": {"GET": "view", "POST": "create"},
    "categories_export": "export",
    "categories_import": "import",
    "categories_starter_fventas": "create",
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
                    {"name": "email", "required": True, "example": "carlos@fventas.cl", "help": "Correo unico para login movil."},
                    {"name": "telefono", "required": False, "example": "+56912345678", "help": "Telefono o WhatsApp."},
                    {"name": "codigo_vendedor", "required": False, "example": "CL-CAR-01", "help": "Codigo interno comercial."},
                    {"name": "zona", "required": False, "example": "Zona Norte", "help": "Zona o cartera principal."},
                    {"name": "territorio", "required": False, "example": "Centro - Ruta A", "help": "Ruta, territorio o cobertura."},
                    {"name": "supervisor", "required": False, "example": "Gerente Comercial", "help": "Responsable interno del vendedor."},
                    {"name": "comision", "required": False, "example": "5", "help": "Porcentaje de comision."},
                    {"name": "meta_mensual", "required": False, "example": "2500000", "help": "Meta comercial mensual en moneda de venta."},
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
                "title": "Clientes B2B",
                "description": "Cartera B2B con datos fiscales, direccion, vendedor y credito.",
                "columns": [
                    {"name": "cliente", "required": True, "example": "Cliente Principal SpA", "help": "Razon social o nombre comercial."},
                    {"name": "razon_social", "required": False, "example": "Cliente Principal SpA", "help": "Nombre legal para documentos fiscales."},
                    {"name": "nombre_comercial", "required": False, "example": "Cliente Principal", "help": "Nombre visible en app y cartera."},
                    {"name": "email", "required": True, "example": "compras@clienteprincipal.com", "help": "Correo unico para acceso movil."},
                    {"name": "documento_fiscal", "required": True, "example": "76.123.456-7", "help": "Documento fiscal del pais configurado. En Chile se valida como RUT."},
                    {"name": "contacto", "required": False, "example": "Maria Gonzalez", "help": "Responsable de compras."},
                    {"name": "contacto_administrativo", "required": False, "example": "Luis Perez", "help": "Responsable de pagos o administracion."},
                    {"name": "contacto_recepcion", "required": False, "example": "Ana Torres", "help": "Responsable de recibir mercancia."},
                    {"name": "telefono", "required": True, "example": "+56 9 1234 5678", "help": "Telefono comercial. Se normaliza segun el pais configurado."},
                    {"name": "whatsapp", "required": False, "example": "+56912345678", "help": "WhatsApp principal si es distinto al telefono."},
                    {"name": "direccion", "required": False, "example": "Av. Principal 123, local 12", "help": "Direccion fiscal o despacho."},
                    {"name": "direccion_fiscal", "required": False, "example": "Av. Principal 123, local 12", "help": "Direccion fiscal."},
                    {"name": "direccion_despacho", "required": False, "example": "Galpon 4, Zona Industrial", "help": "Direccion de entrega."},
                    {"name": "estado_ubicacion", "required": True, "example": "Metropolitana", "help": "Region, estado o provincia del cliente."},
                    {"name": "ciudad", "required": True, "example": "Ciudad principal", "help": "Ciudad del cliente. En Chile se valida contra la region."},
                    {"name": "pais", "required": False, "example": "CL", "help": "Pais del cliente."},
                    {"name": "zona", "required": False, "example": "Centro", "help": "Zona de despacho o cartera."},
                    {"name": "vendedor_email", "required": False, "example": "carlos@fventas.cl", "help": "Asigna cartera por email del vendedor."},
                    {"name": "tipo_cliente", "required": False, "example": "b2b", "help": "b2b, distribuidor o cliente_especial."},
                    {"name": "categoria_comercial", "required": False, "example": "preferential", "help": "standard, preferential, strategic o wholesale."},
                    {"name": "lista_precios", "required": False, "example": "b2b", "help": "b2b, retail, wholesale o special."},
                    {"name": "descuento_autorizado", "required": False, "example": "5", "help": "Descuento comercial maximo autorizado."},
                    {"name": "estado", "required": False, "example": "active", "help": "active, prospect, review, inactive, suspended o bloqueos."},
                    {"name": "estado_cobranza", "required": False, "example": "without_debt", "help": "without_debt, current, due_soon, overdue, promise o blocked."},
                    {"name": "riesgo_credito", "required": False, "example": "low", "help": "low, medium, high o critical."},
                    {"name": "score_credito", "required": False, "example": "82", "help": "Score interno de 0 a 100. Si viene vacio se calcula."},
                    {"name": "observacion_gerencia", "required": False, "example": "Cupo inicial sujeto a revision mensual.", "help": "Nota privada para decisiones de credito."},
                    {"name": "estado_credito", "required": False, "example": "pending", "help": "none, pending, review, approved, rejected, suspended, blocked_debt o blocked_limit."},
                    {"name": "credito_solicitado", "required": False, "example": "1500000", "help": "Monto solicitado por el cliente o vendedor en moneda de venta."},
                    {"name": "deuda_manual", "required": False, "example": "0", "help": "Deuda externa anterior a la plataforma en moneda de venta."},
                    {"name": "tipo_venta_default", "required": False, "example": "credit_line", "help": "cash, term_credit o credit_line."},
                    {"name": "cupo", "required": False, "example": "1000000", "help": "Linea aprobada en moneda de venta si el rol puede aprobar."},
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
                    {"name": "sku", "required": True, "example": "FVT-MOT-45CC", "help": "Codigo unico del producto."},
                    {"name": "codigo_interno", "required": False, "example": "MOT-45-2026", "help": "Codigo interno administrativo o ERP."},
                    {"name": "nombre", "required": True, "example": "Motosierra FVENTAS 45cc", "help": "Nombre visible comercial."},
                    {"name": "categoria", "required": True, "example": "Maquinaria y jardin", "help": "Familia del catalogo."},
                    {"name": "subcategoria", "required": False, "example": "Motosierras", "help": "Linea interna dentro de la categoria."},
                    {"name": "marca", "required": False, "example": "FVENTAS", "help": "Marca comercial."},
                    {"name": "modelo", "required": False, "example": "45CC", "help": "Modelo o referencia visible."},
                    {"name": "unidad_venta", "required": False, "example": "unidad", "help": "Unidad, kit, caja, metro, litro, etc."},
                    {"name": "descripcion_corta", "required": False, "example": "Equipo de corte para jardin y finca.", "help": "Resumen corto para listados."},
                    {"name": "descripcion_larga", "required": False, "example": "Incluye espada, cadena y garantia FVENTAS.", "help": "Detalle ampliado para ficha de producto."},
                    {"name": "precio_publico", "required": True, "example": "153900", "help": "Precio PVP en moneda de venta configurada."},
                    {"name": "precio_b2b", "required": False, "example": "14250", "help": "Precio B2B en moneda de venta configurada."},
                    {"name": "costo_referencial", "required": False, "example": "120000", "help": "Costo interno referencial. No se publica en app."},
                    {"name": "margen_porcentaje", "required": False, "example": "25", "help": "Margen estimado administrativo."},
                    {"name": "stock", "required": False, "example": "12", "help": "Stock fisico inicial."},
                    {"name": "stock_minimo", "required": False, "example": "3", "help": "Punto de alerta de reposicion."},
                    {"name": "stock_maximo", "required": False, "example": "30", "help": "Stock objetivo o maximo."},
                    {"name": "descripcion", "required": False, "example": "Equipo para uso tecnico y jardin.", "help": "Descripcion app movil."},
                    {"name": "tipo_producto", "required": False, "example": "machine", "help": "machine, spare_part, accessory, service o consumable."},
                    {"name": "precio_anterior", "required": False, "example": "175750", "help": "Precio antes del descuento en moneda de venta."},
                    {"name": "descuento_porcentaje", "required": False, "example": "12", "help": "Descuento visible."},
                    {"name": "tasa_moneda_local", "required": False, "example": "1", "help": "Tasa referencial entre moneda de venta y moneda local cuando aplique."},
                    {"name": "imagen_principal", "required": False, "example": "https://cdn.fventas.cl/producto.jpg", "help": "Imagen principal."},
                    {"name": "imagenes", "required": False, "example": "https://cdn.fventas.cl/1.jpg|https://cdn.fventas.cl/2.jpg", "help": "Galeria separada por |, coma o salto de linea."},
                    {"name": "pdf_tecnicos", "required": False, "example": "https://cdn.fventas.cl/ficha.pdf", "help": "Fichas tecnicas."},
                    {"name": "variantes", "required": False, "example": "18 pulgadas|20 pulgadas", "help": "Opciones visibles."},
                    {"name": "especificaciones", "required": False, "example": "Motor:45cc|Garantia:6 meses", "help": "Formato clave:valor."},
                    {"name": "skus_relacionados", "required": False, "example": "FVT-REP-CAD18|FVT-ACE-2T", "help": "Productos relacionados por SKU."},
                    {"name": "notas_compatibilidad", "required": False, "example": "Compatible con FVT-REP-CAD18|Validar serie antes de despacho", "help": "Notas visibles en app movil para compatibilidad o validacion."},
                    {"name": "requiere_revision", "required": False, "example": "no", "help": "si/no para pedido sujeto a revision comercial."},
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
                    {"name": "imagen_url", "required": False, "example": "https://cdn.fventas.cl/categorias/repuestos.jpg", "help": "Imagen de categoria."},
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
                    {"name": "sku", "required": True, "example": "FVT-MOT-45CC", "help": "Debe existir en productos."},
                    {"name": "cantidad", "required": True, "example": "25", "help": "Stock fisico final."},
                    {"name": "stock_minimo", "required": False, "example": "3", "help": "Punto de alerta operativa."},
                    {"name": "stock_maximo", "required": False, "example": "40", "help": "Stock objetivo o maximo sugerido."},
                    {"name": "stock_reposicion", "required": False, "example": "15", "help": "Cantidad sugerida para reposicion."},
                    {"name": "ubicacion", "required": False, "example": "Bodega principal A-02", "help": "Ubicacion fisica o bodega."},
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
                    {"name": "sku", "required": True, "example": "FVT-MOT-45CC", "help": "Producto asociado."},
                    {"name": "titulo", "required": False, "example": "Ficha tecnica motosierra", "help": "Nombre interno."},
                    {"name": "tipo", "required": True, "example": "pdf", "help": "image o pdf."},
                    {"name": "url", "required": True, "example": "https://cdn.fventas.cl/ficha.pdf", "help": "URL publica del recurso."},
                ],
            },
            {
                "key": "documentos",
                "module": "documents",
                "endpoint": "documents",
                "title": "Documentos",
                "description": "Contratos, documentos fiscales, garantias, evidencias y documentos por cliente, producto u orden.",
                "columns": [
                    {"name": "titulo", "required": True, "example": "Documento fiscal Cliente Principal", "help": "Nombre interno del documento."},
                    {"name": "tipo_documento", "required": True, "example": "rut", "help": "rut, contract, credit, account_statement, technical_sheet, manual, warranty, certificate, quote, payment_proof, dispatch_guide, delivery_evidence, invoice o administrative."},
                    {"name": "ambito", "required": True, "example": "cliente", "help": "cliente, producto, orden o administrativo."},
                    {"name": "referencia", "required": False, "example": "compras@clienteprincipal.com", "help": "Email/documento fiscal/nombre cliente, SKU producto u orden segun ambito."},
                    {"name": "url", "required": True, "example": "https://cdn.fventas.cl/documentos/rut.pdf", "help": "URL publica o privada del archivo."},
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
                    {"name": "imagen_url", "required": False, "example": "https://cdn.fventas.cl/banners/oferta.jpg", "help": "Imagen del carrusel."},
                    {"name": "boton", "required": False, "example": "Ver catalogo", "help": "Texto del CTA."},
                    {"name": "url_accion", "required": False, "example": "fventas://catalogo", "help": "Accion o enlace."},
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
                    {"name": "nombre", "required": True, "example": "Servicio tecnico autorizado", "help": "Nombre comercial."},
                    {"name": "empresa", "required": False, "example": "Taller Central SpA", "help": "Empresa asociada."},
                    {"name": "contacto", "required": False, "example": "Luis Martinez", "help": "Persona responsable."},
                    {"name": "telefono", "required": False, "example": "+56912345678", "help": "Telefono principal."},
                    {"name": "whatsapp", "required": False, "example": "+56912345678", "help": "WhatsApp."},
                    {"name": "email", "required": False, "example": "servicio@fventas.cl", "help": "Correo de contacto."},
                    {"name": "estado_ubicacion", "required": False, "example": "Metropolitana", "help": "Estado o region."},
                    {"name": "ciudad", "required": False, "example": "Ciudad principal", "help": "Ciudad."},
                    {"name": "direccion", "required": False, "example": "Zona industrial, local 8", "help": "Direccion visible."},
                    {"name": "especialidades", "required": False, "example": "Motosierras|Motobombas", "help": "Separadas por |, coma o salto."},
                    {"name": "cobertura", "required": False, "example": "Zona centro y comunas cercanas", "help": "Zona cubierta."},
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
    token = escape(csrf_token())
    return Markup(f'<input type="hidden" name="_csrf_token" value="{token}">')  # nosec B704


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
    is_platform = current_admin_role() == "platform_admin"
    company_id = current_company_id(store)
    return sorted(
        [
            user
            for user in store.get("admin_users", [])
            if user.get("role") == "sales" and user.get("status") == "active"
            and (is_platform or record_company_id(user, store) == company_id)
        ],
        key=lambda user: user.get("name", ""),
    )


def web_admin_users(store: dict) -> list[dict]:
    is_platform = current_admin_role() == "platform_admin"
    company_id = current_company_id(store)
    return sorted(
        [
            user
            for user in store.get("admin_users", [])
            if user.get("role") != "sales" and user.get("status") != "deleted"
            and (is_platform or user.get("companyId", default_company_id(store)) == company_id)
        ],
        key=lambda user: user.get("name", ""),
    )


def current_admin_user(store: dict) -> dict | None:
    admin_user_id = session.get("admin_user_id", "")
    if not admin_user_id:
        return None
    matches = [
        user
        for user in store.get("admin_users", [])
        if user.get("id") == admin_user_id
    ]
    if not matches:
        return None
    session_company_id = str(session.get("company_id") or "").strip()
    if session_company_id:
        scoped = next(
            (user for user in matches if record_company_id(user, store) == session_company_id),
            None,
        )
        if scoped:
            return scoped
        return None
    if len(matches) == 1:
        return matches[0]
    return None


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
    return f"FVENTAS{secrets.randbelow(900000) + 100000}"


def temporary_mobile_client_password() -> str:
    return f"Fventas-{secrets.token_urlsafe(12)}-1"


def request_ip_address() -> str:
    remote_addr = (request.remote_addr or "").strip()
    if app.config.get("TRUST_PROXY_HEADERS"):
        forwarded_for = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP", "").strip()
        return forwarded_for or real_ip or remote_addr
    return remote_addr


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
    session["company_id"] = admin_user.get("companyId", DEFAULT_COMPANY_ID)
    session["admin_name"] = admin_user.get("name", "FVENTAS Admin")
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


def client_origin_label(value: str) -> str:
    return CLIENT_ORIGIN_LABELS.get(value, value or "Sin origen")


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


def runtime_capacity_snapshot(company_id: str = "") -> dict:
    now = int(time.time())
    workers = max(1, safe_int(os.environ.get("FVENTAS_WEB_WORKERS"), 1))
    threads = max(1, safe_int(os.environ.get("FVENTAS_WEB_THREADS"), 4))
    company_id = str(company_id or "").strip()
    with RUNTIME_REQUEST_LOCK:
        request_metrics = dict(RUNTIME_REQUEST_METRICS)
    with RUNTIME_IDENTITY_LOCK:
        seen_items = list(RUNTIME_SEEN_IDENTITIES.values())

    if company_id:
        seen_items = [
            item for item in seen_items
            if str(item.get("companyId") or "") == company_id
        ]

    def count_seen(seconds: int, *types: str) -> int:
        allowed_types = set(types)
        return sum(
            1
            for item in seen_items
            if now - safe_int(item.get("lastSeenEpoch"), 0) <= seconds
            and (not allowed_types or item.get("type") in allowed_types)
        )

    uptime = max(0, now - RUNTIME_STARTED_AT_EPOCH)
    return {
        "pid": os.getpid(),
        "workers": workers,
        "threads": threads,
        "configuredRequestSlots": workers * threads,
        "activeRequests": request_metrics.get("activeRequests", 0),
        "peakActiveRequests": request_metrics.get("peakActiveRequests", 0),
        "totalRequests": request_metrics.get("totalRequests", 0),
        "uptimeSeconds": uptime,
        "requestsPerMinute": round((request_metrics.get("totalRequests", 0) / max(uptime, 1)) * 60, 2),
        "mobileUsers5m": count_seen(300, "client_app", "seller_app"),
        "mobileUsers15m": count_seen(900, "client_app", "seller_app"),
        "clientUsers15m": count_seen(900, "client_app"),
        "sellerUsers15m": count_seen(900, "seller_app"),
        "adminUsers15m": count_seen(900, "admin_panel"),
    }


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


def insights_from_pairs(pairs: list[tuple[str, float]], limit: int = 6) -> dict:
    sorted_pairs = sorted(pairs, key=lambda item: item[1], reverse=True)[:limit]
    return {
        "labels": [label for label, _value in sorted_pairs],
        "values": [round(float(value), 2) for _label, value in sorted_pairs],
    }


def dashboard_date_keys(value: str | None) -> tuple[str, str]:
    text = str(value or "")
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return f"{text[8:10]}/{text[5:7]}", text[:7]
    created_at = parse_utc_datetime(text)
    return f"{created_at.day:02d}/{created_at.month:02d}", f"{created_at.year:04d}-{created_at.month:02d}"


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
    client_names = {client.get("id", ""): client.get("businessName", "Cliente FVENTAS") for client in clients}

    for order in orders:
        day_key, month_key = dashboard_date_keys(order.get("createdAt", ""))
        total = float(order.get("totalUsd") or 0)
        sales_by_day[day_key] = sales_by_day.get(day_key, 0) + total
        sales_by_month[month_key] = sales_by_month.get(month_key, 0) + total
        seller_name = order.get("sellerName") or "Sin vendedor"
        sales_by_seller[seller_name] = sales_by_seller.get(seller_name, 0) + total
        commissions_by_seller[seller_name] = commissions_by_seller.get(seller_name, 0) + float(order.get("commissionUsd") or 0)
        client_name = client_names.get(order.get("customerId", ""), order.get("customer", {}).get("name", "Cliente FVENTAS"))
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
        "sales_by_day": insights_from_pairs(list(sales_by_day.items()), 8),
        "sales_by_month": insights_from_pairs(list(sales_by_month.items()), 6),
        "sales_by_seller": insights_from_pairs(list(sales_by_seller.items()), 6),
        "sales_by_category": insights_from_pairs(list(sales_by_category.items()), 6),
        "products_sold": insights_from_pairs(list(products_sold.items()), 6),
        "clients_purchase": insights_from_pairs(list(clients_purchase.items()), 6),
        "overdue_by_client": insights_from_pairs(list(overdue_by_client.items()), 6),
        "commissions_by_seller": insights_from_pairs(list(commissions_by_seller.items()), 6),
    }


def seller_record_for(store: dict, seller_id: str, company_id: str = "") -> dict | None:
    if not seller_id:
        return None
    matches = [
        user
        for user in store.get("admin_users", [])
        if user.get("id") == seller_id and user.get("role") == "sales"
    ]
    if not matches:
        return None
    target_company_id = company_id or current_company_id(store)
    scoped = next(
        (user for user in matches if record_company_id(user, store) == target_company_id),
        None,
    )
    if scoped:
        return scoped
    if is_platform_scope():
        return matches[0]
    return None


def seller_commission_rate(store: dict, seller_id: str, company_id: str = "") -> float:
    seller = seller_record_for(store, seller_id, company_id)
    seller_rate = safe_float((seller or {}).get("commissionRatePercent"), 0)
    return seller_rate if seller_rate > 0 else safe_float(business_settings(store).get("defaultCommissionPercent"), 0)


def seller_name_for(store: dict, seller_id: str, company_id: str = "") -> str:
    seller = seller_record_for(store, seller_id, company_id)
    return (seller or {}).get("name", "")


def is_platform_scope() -> bool:
    return current_admin_role() == "platform_admin"


def record_company_id(record: dict | None, store: dict) -> str:
    if not record:
        return current_company_id(store)
    return str(record.get("companyId") or default_company_id(store))


def can_access_company_record(record: dict | None, store: dict) -> bool:
    if not record:
        return False
    if is_platform_scope():
        return True
    return record_company_id(record, store) == current_company_id(store)


def visible_records_for_current_company(store: dict, collection: str) -> list[dict]:
    records = store.get(collection, [])
    if is_platform_scope():
        return records
    company_id = current_company_id(store)
    return [
        record
        for record in records
        if record_company_id(record, store) == company_id
    ]


def find_company_record(store: dict, collection: str, record_id: str) -> dict | None:
    if not record_id:
        return None
    matches = [
        record
        for record in store.get(collection, [])
        if record.get("id") == record_id
    ]
    if not matches:
        return None
    company_id = current_company_id(store)
    scoped_record = next(
        (record for record in matches if record_company_id(record, store) == company_id),
        None,
    )
    if scoped_record:
        return scoped_record
    if is_platform_scope():
        return matches[0]
    return None


def same_company_record(store: dict, item: dict | None, target: dict | None) -> bool:
    if not item or not target:
        return False
    return (
        item.get("id") == target.get("id")
        and record_company_id(item, store) == record_company_id(target, store)
    )


def replace_company_record(store: dict, collection: str, target: dict, replacement: dict) -> None:
    store[collection] = [
        replacement if same_company_record(store, item, target) else item
        for item in store.get(collection, [])
    ]


def remove_company_record(store: dict, collection: str, target: dict) -> None:
    store[collection] = [
        item
        for item in store.get(collection, [])
        if not same_company_record(store, item, target)
    ]


def visible_clients_for_current_user(store: dict) -> list[dict]:
    clients = visible_records_for_current_company(store, "clients")
    if current_admin_role() != "sales":
        return clients
    seller_id = session.get("admin_user_id", "")
    return [client for client in clients if client.get("assignedSellerId") == seller_id]


def can_access_client_record(client: dict | None, store: dict) -> bool:
    if not can_access_company_record(client, store):
        return False
    if current_admin_role() != "sales":
        return True
    return client.get("assignedSellerId") == session.get("admin_user_id", "")


def visible_orders_for_current_user(store: dict) -> list[dict]:
    orders = visible_records_for_current_company(store, "orders")
    if current_admin_role() != "sales":
        return orders
    seller_id = session.get("admin_user_id", "")
    assigned_client_ids = {
        client.get("id", "")
        for client in visible_clients_for_current_user(store)
        if client.get("assignedSellerId") == seller_id
    }
    return [
        order
        for order in orders
        if order.get("sellerId") == seller_id or order.get("customerId") in assigned_client_ids
    ]


def can_access_order_record(order: dict | None, store: dict) -> bool:
    if not can_access_company_record(order, store):
        return False
    if current_admin_role() != "sales":
        return True
    seller_id = session.get("admin_user_id", "")
    if order.get("sellerId") == seller_id:
        return True
    client = find_company_record(store, "clients", order.get("customerId", ""))
    return bool(client and client.get("assignedSellerId") == seller_id)


def visible_quotes_for_current_user(store: dict) -> list[dict]:
    quotes = visible_records_for_current_company(store, "quotes")
    if current_admin_role() != "sales":
        return quotes
    seller_id = session.get("admin_user_id", "")
    assigned_client_ids = {
        client.get("id", "")
        for client in visible_clients_for_current_user(store)
        if client.get("assignedSellerId") == seller_id
    }
    return [
        quote
        for quote in quotes
        if quote.get("sellerId") == seller_id or quote.get("clientId") in assigned_client_ids
    ]


def can_access_quote_record(quote: dict | None, store: dict) -> bool:
    if not can_access_company_record(quote, store):
        return False
    if current_admin_role() != "sales":
        return True
    seller_id = session.get("admin_user_id", "")
    if quote.get("sellerId") == seller_id:
        return True
    client = find_company_record(store, "clients", quote.get("clientId", ""))
    return bool(client and client.get("assignedSellerId") == seller_id)


def visible_crm_records_for_current_user(store: dict) -> list[dict]:
    records = visible_records_for_current_company(store, "crm_records")
    if current_admin_role() != "sales":
        return records
    seller_id = session.get("admin_user_id", "")
    assigned_client_ids = {
        client.get("id", "")
        for client in visible_clients_for_current_user(store)
        if client.get("assignedSellerId") == seller_id
    }
    return [
        record
        for record in records
        if record.get("sellerId") == seller_id or record.get("clientId") in assigned_client_ids
    ]


def can_access_crm_record(record: dict | None, store: dict) -> bool:
    if not can_access_company_record(record, store):
        return False
    if current_admin_role() != "sales":
        return True
    seller_id = session.get("admin_user_id", "")
    if record.get("sellerId") == seller_id:
        return True
    client = find_company_record(store, "clients", record.get("clientId", ""))
    return bool(client and client.get("assignedSellerId") == seller_id)


def product_has_commercial_history(store: dict, product: dict | None) -> bool:
    if not product:
        return False
    company_id = record_company_id(product, store)
    product_id = product.get("id", "")
    sku = product.get("sku", "")
    for order in store.get("orders", []):
        if record_company_id(order, store) != company_id:
            continue
        for item in order.get("items", []):
            if item.get("productId") == product_id or item.get("sku") == sku:
                return True
    return any(
        movement.get("productId") == product_id or movement.get("sku") == sku
        for movement in store.get("stock_movements", [])
        if record_company_id(movement, store) == company_id
    )


def login_attempt_key(scope: str, email: str) -> str:
    ip_address = request_ip_address() or "local"
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


def mobile_password_recovery_response():
    return jsonify(
        {
            "status": "received",
            "message": "Si el correo existe, FVENTAS gestionara la recuperacion de acceso.",
        }
    )


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
    return safe_download_filename(
        f"plantilla_fventas_{spec.get('key', 'importacion')}.{file_format}",
        f"plantilla_fventas.{file_format}",
    )


def build_csv_template(spec: dict) -> Response:
    headers = [column["name"] for column in spec["columns"]]
    output = io.StringIO()
    writer = safe_csv_dict_writer(output, fieldnames=headers, lineterminator="\n")
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
            "FVENTAS",
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
    orders = visible_orders_for_current_user(store)
    products = visible_records_for_current_company(store, "products")
    stock_movements = visible_records_for_current_company(store, "stock_movements")
    movements = visible_records_for_current_company(store, "credit_movements")
    search_currency = sales_currency_for_company(store, current_company_id(store))
    sellers = [
        user
        for user in visible_records_for_current_company(store, "admin_users")
        if user.get("role") == "sales" and user.get("status") != "deleted"
    ]
    categories = visible_records_for_current_company(store, "categories")
    tokens = normalized_query.split()

    def matches(*values) -> bool:
        blob = searchable_text(*values)
        return all(token in blob for token in tokens)

    if can_access_module("products"):
        for product in enrich_inventory_products(products, orders, stock_movements):
            if matches(product.get("sku"), product.get("title"), product.get("categoryName"), product.get("brand"), product.get("model"), product.get("description")):
                href = url_for("product_edit", product_id=product["id"]) if can_module_action("products", "edit") else url_for("products", q=product.get("sku", ""))
                append_search_result(groups, "products", {
                    "group_label": "Productos",
                    "group_icon": "bi-box-seam",
                    "title": product.get("title") or product.get("sku"),
                    "subtitle": f"{product.get('sku', '')} - {product.get('categoryName') or 'Sin categoria'}",
                    "meta": f"{product.get('availableStock', 0)} disp. / {money_currency(product.get('publicPriceUsd', 0), search_currency)}",
                    "badge": product.get("statusLabel", product.get("status", "")),
                    "href": href,
                    "icon": "bi-box-seam",
                })

    if can_access_module("clients"):
        client_profile = active_market_profile_for_store(store)
        for client in [enrich_client(item, orders, movements) for item in visible_clients_for_current_user(store) if item.get("status") != "deleted"]:
            if matches(client.get("businessName"), client.get("legalName"), client.get("taxId"), client.get("email"), client.get("phone"), client.get("assignedSellerName")):
                append_search_result(groups, "clients", {
                    "group_label": "Clientes",
                    "group_icon": "bi-shop",
                    "title": client.get("businessName") or client.get("email"),
                    "subtitle": f"{client.get('taxId') or 'Sin ' + client_profile.get('taxLabel', 'documento fiscal')} - {client.get('assignedSellerName') or 'Sin vendedor'}",
                    "meta": f"Credito {money_currency(client.get('creditAvailableUsd', 0), search_currency)}",
                    "badge": client.get("statusLabel", client.get("status", "")),
                    "href": url_for("clients", q=client.get("businessName", "")),
                    "icon": "bi-shop",
                })

    if can_access_module("sellers"):
        for seller in [enrich_seller(store, item) for item in sellers]:
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
        for order in [enrich_order(item, movements) for item in orders]:
            if matches(order.get("orderId"), order.get("customerName"), order.get("sellerName"), order.get("saleTypeLabel"), order.get("statusLabel")):
                append_search_result(groups, "orders", {
                    "group_label": "Ordenes",
                    "group_icon": "bi-receipt",
                    "title": order.get("orderId") or order.get("id"),
                    "subtitle": f"{order.get('customerName')} - {order.get('sellerName')}",
                    "meta": f"{money_currency(order.get('totalUsd', 0), search_currency)} / saldo {money_currency(order.get('balanceUsd', 0), search_currency)}",
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
                    "meta": money_currency(quote.get("totalUsd", 0), search_currency),
                    "badge": quote_status_label(quote.get("status", "")),
                    "href": href,
                    "icon": "bi-file-earmark-text",
                })

    if can_access_module("categories"):
        for category in categories:
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

        wrapped._required_roles = tuple(sorted(allowed_roles))
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
        "client_origin_label": client_origin_label,
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
def block_legacy_mobile_api_in_production():
    if not request.path.startswith("/api/mobile/"):
        return None
    if app.config.get("ALLOW_LEGACY_MOBILE_API"):
        return None
    return jsonify(
        {
            "error": "Version de API movil obsoleta. Actualiza la app para usar /api/v1/mobile.",
            "code": "legacy_mobile_api_disabled",
        }
    ), 410


@app.before_request
def require_admin_session():
    public_prefixes = ("/api/mobile/", "/api/v1/mobile/", "/static/")
    public_endpoints = {
        "landing",
        "landing_access_preference",
        "desktop_download",
        "login",
        "signup",
        "signup_success",
        "terms_of_service",
        "privacy_policy",
        "account_deletion_page",
        "healthz",
        "readyz",
    }

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

    session["admin_name"] = admin_user.get("name", "FVENTAS Admin")
    session["admin_role"] = admin_user.get("role", "operator")
    session["company_id"] = admin_user.get("companyId", default_company_id(store))
    session["must_change_password"] = bool(admin_user.get("mustChangePassword"))

    if admin_user.get("role") == "sales":
        session.clear()
        return redirect(url_for("login", mobile_only="1"))

    if not subscription_allows_access(store, admin_user):
        record_audit_event(
            store,
            "login_blocked",
            "subscription",
            admin_user.get("companyId", default_company_id(store)),
            "Acceso bloqueado por suscripcion pendiente o suspendida.",
            actor={"id": admin_user["id"], "name": admin_user.get("name", ""), "role": admin_user.get("role", "")},
            metadata={"path": request.path, "method": request.method},
        )
        save_store(store)
        session.clear()
        return redirect(url_for("login", next=request.path, subscription="inactive"))

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


LEGACY_ADMIN_ROUTE_ALIASES = {
    "/dashboard": "dashboard",
    "/dashboard/perfil": "account_password",
    "/dashboard/profile": "account_password",
    "/perfil": "account_password",
    "/profile": "account_password",
}


def normalize_admin_next_url(raw_next: str | None) -> str:
    value = str(raw_next or "").strip()
    if not value:
        return url_for("dashboard")

    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return url_for("dashboard")

    normalized_path = parsed.path.rstrip("/") or "/"
    if normalized_path == "/":
        return url_for("dashboard")
    alias_endpoint = LEGACY_ADMIN_ROUTE_ALIASES.get(normalized_path)
    if alias_endpoint:
        return url_for(alias_endpoint)
    return value


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.args.get("mobile_only") == "1":
        error = "Los vendedores ingresan desde la app movil. El panel web es solo administrativo."
    elif request.args.get("subscription") == "inactive":
        error = "La suscripcion de la empresa esta pendiente o suspendida. Contacta a FVENTAS para reactivar el plan."

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

        admin_candidates = [
            user
            for user in store.get("admin_users", [])
            if user.get("email", "").lower() == email and user.get("status") == "active"
        ]
        if len(admin_candidates) > 1:
            register_login_failure("admin", email)
            now = utc_now()
            for candidate in admin_candidates:
                candidate["failedLoginAttempts"] = safe_int(candidate.get("failedLoginAttempts")) + 1
                candidate["lastFailedLoginAt"] = now
                candidate["lastLoginIp"] = request_ip_address()
            record_audit_event(
                store,
                "login_blocked",
                "admin_user",
                email,
                "Login admin bloqueado por identidad duplicada entre empresas o roles.",
                actor={"id": email, "name": email or "desconocido", "role": "anonymous"},
                metadata={
                    "matches": [
                        {
                            "id": user.get("id", ""),
                            "companyId": record_company_id(user, store),
                            "role": user.get("role", ""),
                        }
                        for user in admin_candidates
                    ]
                },
                criticality="high",
            )
            save_store(store)
            error = "Credenciales invalidas."
            return render_template("login.html", error=error)

        admin_user = admin_candidates[0] if admin_candidates else None

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
            if not subscription_allows_access(store, admin_user):
                register_login_failure("admin", email)
                register_admin_user_failed_attempt(store, email)
                record_audit_event(
                    store,
                    "login_blocked",
                    "subscription",
                    admin_user.get("companyId", default_company_id(store)),
                    "Intento de acceso con suscripcion pendiente o suspendida.",
                    actor={"id": admin_user["id"], "name": admin_user.get("name", email), "role": admin_user.get("role", "")},
                    metadata={"email": email},
                )
                save_store(store)
                error = "La suscripcion de la empresa esta pendiente o suspendida. Activa el plan mensual para ingresar."
                return render_template("login.html", error=error), 403
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
            return redirect(normalize_admin_next_url(request.args.get("next")))

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


@app.route("/signup", methods=["GET", "POST"])
def signup():
    store = load_store()
    error = ""
    response_status = 200
    mobile_first_choices = {"mobile_first", "mobile_only", "desktop_download_cancelled"}

    if request.method == "POST":
        market_country = normalize_market_country(request.form.get("marketCountry", "CL"))
        profile = market_profile(market_country)
        pricing = plan_pricing_for_country(market_country)
        company_name = sanitize_text(request.form.get("companyName", ""), max_length=180, allow_newlines=False)
        legal_name = sanitize_text(request.form.get("legalName", ""), max_length=180, allow_newlines=False)
        tax_id = normalize_tax_id_for_market(request.form.get("taxId", ""), profile)
        owner_name = sanitize_text(request.form.get("ownerName", ""), max_length=160, allow_newlines=False)
        owner_email = request.form.get("ownerEmail", "").strip().lower()
        support_phone = normalize_phone_for_market(request.form.get("supportPhone", ""), profile)
        desktop_access_preference = sanitize_text(
            request.form.get("desktopAccessPreference", ""),
            max_length=80,
            allow_newlines=False,
        )
        if desktop_access_preference not in {
            "desktop_download_started",
            "desktop_download_cancelled",
            "mobile_first",
            "mobile_only",
        }:
            desktop_access_preference = ""
        mobile_app_access_requested = desktop_access_preference in mobile_first_choices
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirmPassword", "")
        legal_accepted = request.form.get("legalAccepted") == "on"
        ip_address = request_ip_address()
        signup_window_seconds = max(1, int(app.config.get("SIGNUP_WINDOW_SECONDS", 300)))
        signup_max_events = max(1, int(app.config.get("SIGNUP_MAX_EVENTS", 5)))
        signup_rate_limited = public_submission_rate_limited(
            store,
            "signup_rate_events",
            ip_address=ip_address,
            email=owner_email,
            window_seconds=signup_window_seconds,
            max_events=signup_max_events,
        )
        owner_admin_conflict = admin_user_by_email(store, owner_email) if owner_email else None
        owner_client_conflict = next(
            (
                client
                for client in store.get("clients", [])
                if client.get("email", "").strip().lower() == owner_email
                and client.get("status") == "active"
            ),
            None,
        )
        company_tax_conflict = next(
            (
                company
                for company in store.get("companies", [])
                if company.get("status") not in {"deleted", "cancelled"}
                and normalize_market_country(
                    company.get("country")
                    or company.get("marketCountry")
                    or (company.get("marketProfile") or {}).get("code")
                )
                == profile["code"]
                and normalize_tax_id_for_market(company.get("taxId", ""), profile).lower() == tax_id.lower()
            ),
            None,
        ) if tax_id else None

        if signup_rate_limited:
            error = "Hemos recibido varios registros recientes. Espera unos minutos antes de intentarlo nuevamente."
            response_status = 429
        elif not company_name:
            error = "El nombre de la empresa es obligatorio."
        elif not tax_id:
            error = f"Ingresa un {profile.get('taxLabel', 'documento fiscal')} valido para {profile.get('label', 'el pais seleccionado')}."
        elif company_tax_conflict:
            error = "Ya existe una empresa registrada con ese documento fiscal."
        elif not owner_name:
            error = "El nombre del administrador es obligatorio."
        elif not owner_email:
            error = "El correo del administrador es obligatorio."
        elif owner_admin_conflict or owner_client_conflict:
            error = "Ese correo ya pertenece a una cuenta FVENTAS y no puede registrar otra empresa."
        elif not support_phone:
            error = f"Ingresa un telefono valido para {profile.get('label', 'el pais seleccionado')}."
        elif password != confirm_password:
            error = "Las contrasenas no coinciden."
        elif not legal_accepted:
            error = "Debes aceptar los terminos del servicio y la politica de privacidad para continuar."
        else:
            password_issues = password_errors(password)
            if password_issues:
                error = " ".join(password_issues)

        if not signup_rate_limited:
            record_public_submission_rate_event(
                store,
                "signup_rate_events",
                ip_address=ip_address,
                email=owner_email,
                action="signup",
                window_seconds=signup_window_seconds,
            )
            if error:
                save_store(store)

        if not error:
            now = utc_now()
            company_id = next_id("company", company_name)
            company = {
                "id": company_id,
                "name": company_name,
                "slug": category_slug(company_name),
                "legalName": legal_name or company_name,
                "taxId": tax_id,
                "country": profile["code"],
                "currency": profile["localCurrency"],
                "baseCurrency": profile["salesCurrency"],
                "marketProfile": profile,
                "taxLabel": profile["taxLabel"],
                "planCurrency": pricing["currency"],
                "planPrice": pricing["price"],
                "status": "pending_payment",
                "planId": SAAS_PLAN_ID,
                "planName": SAAS_PLAN_NAME,
                "planPriceClp": pricing["priceClp"],
                "ownerName": owner_name,
                "ownerEmail": owner_email,
                "supportPhone": support_phone,
                "desktopAccessPreference": desktop_access_preference,
                "mobileAppAccessRequested": mobile_app_access_requested,
                "legalAcceptance": {
                    "accepted": True,
                    "termsVersion": LEGAL_TERMS_VERSION,
                    "privacyVersion": LEGAL_PRIVACY_VERSION,
                    "acceptedAt": now,
                    "acceptedByEmail": owner_email,
                    "ipAddress": ip_address,
                    "userAgent": sanitize_text(request.headers.get("User-Agent", ""), max_length=240, allow_newlines=False),
                },
                "createdAt": now,
                "updatedAt": now,
            }
            subscription = {
                "id": next_id("sub", company_id),
                "companyId": company_id,
                "planId": SAAS_PLAN_ID,
                "planName": SAAS_PLAN_NAME,
                "status": "pending_payment",
                "billingPeriod": "monthly",
                "country": profile["code"],
                "currency": pricing["currency"],
                "price": pricing["price"],
                "priceClp": pricing["priceClp"],
                "currentPeriodStart": "",
                "currentPeriodEnd": "",
                "trialEndsAt": "",
                "lastPaymentAt": "",
                "nextPaymentAt": "",
                "createdAt": now,
                "updatedAt": now,
            }
            admin_user = {
                "id": next_id("admin", owner_email),
                "companyId": company_id,
                "firstName": owner_name,
                "lastName": "",
                "name": owner_name,
                "email": owner_email,
                "role": "super_admin",
                "status": "active",
                "passwordHash": generate_password_hash(password),
                "mustChangePassword": False,
                "sellerCode": "",
                "sellerZone": "",
                "sellerTerritory": "",
                "sellerSupervisor": "",
                "phone": support_phone,
                "mobileAccessEnabled": mobile_app_access_requested,
                "internalNotes": (
                    "Administrador creado desde registro SaaS. "
                    + (
                        "Cliente prefirio acceso por app movil sin descargar panel desktop."
                        if mobile_app_access_requested
                        else ""
                    )
                ).strip(),
                "commissionRatePercent": 0,
                "salesGoalUsd": 0,
                "createdAt": now,
                "updatedAt": now,
            }
            store.setdefault("companies", []).append(company)
            store.setdefault("subscriptions", []).append(subscription)
            store.setdefault("admin_users", []).append(admin_user)
            record_create_event(
                store,
                "company",
                company_id,
                f"Empresa SaaS registrada: {company_name}.",
                company,
                actor={"id": owner_email, "name": owner_name, "role": "signup"},
            )
            record_create_event(
                store,
                "admin_user",
                admin_user["id"],
                f"Administrador de empresa registrado: {owner_email}.",
                admin_user,
                actor={"id": owner_email, "name": owner_name, "role": "signup"},
            )
            save_store(store)
            session["signup_success_company_id"] = company_id
            return redirect(url_for("signup_success", company_id=company_id, token=issue_signup_success_token(company_id)))

    selected_market_country = normalize_market_country(
        request.form.get("marketCountry")
        or request.args.get("marketCountry")
        or "CL"
    )
    selected_market_profile = market_profile(selected_market_country)
    selected_plan = plan_pricing_for_country(selected_market_country)
    desktop_access_preference = sanitize_text(
        request.form.get("desktopAccessPreference")
        or request.args.get("desktopAccessPreference")
        or "",
        max_length=80,
        allow_newlines=False,
    )
    if desktop_access_preference not in {
        "desktop_download_started",
        "desktop_download_cancelled",
        "mobile_first",
        "mobile_only",
    }:
        desktop_access_preference = ""
    rendered_signup = render_template(
        "signup.html",
        error=error,
        plan_name=SAAS_PLAN_NAME,
        plan_price_display=selected_plan["display"],
        selected_market_country=selected_market_country,
        selected_market_profile=selected_market_profile,
        market_country_options=MARKET_COUNTRY_OPTIONS,
        market_profiles=ACTIVE_MARKET_PROFILES,
        desktop_access_preference=desktop_access_preference,
        legal_terms_version=LEGAL_TERMS_VERSION,
        legal_privacy_version=LEGAL_PRIVACY_VERSION,
    )
    if response_status != 200:
        return rendered_signup, response_status
    return rendered_signup


@app.get("/signup/success/<company_id>")
def signup_success(company_id: str):
    store = load_store()
    company = get_company(store, company_id)
    if not company:
        return redirect(url_for("signup"))
    token_company_id = signup_success_token_company_id(request.args.get("token", ""))
    session_company_id = str(session.get("signup_success_company_id") or "")
    if company_id not in {token_company_id, session_company_id}:
        return redirect(url_for("signup"))
    subscription = current_subscription(store, company_id) or {}
    profile = market_profile(company.get("country") or subscription.get("country") or "CL")
    installer_info = desktop_installer_info()
    display_company = copy.deepcopy(company)
    display_company["ownerEmail"] = masked_email(display_company.get("ownerEmail", ""))
    return render_template(
        "signup_success.html",
        company=display_company,
        subscription=subscription,
        market_profile=profile,
        plan_name=SAAS_PLAN_NAME,
        plan_display=money_currency(
            safe_float(subscription.get("price") or company.get("planPrice"), 0),
            normalize_currency_code(subscription.get("currency") or company.get("planCurrency"), profile["planCurrency"]),
        ),
        desktop_installer=installer_info,
        desktop_download_available=installer_info["available"],
    )


@app.post("/logout")
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
    admin_user = current_admin_user(store)
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
            before = copy.deepcopy(admin_user)
            admin_user["passwordHash"] = generate_password_hash(new_password)
            admin_user["mustChangePassword"] = False
            bump_user_session_version(admin_user)
            session["must_change_password"] = False
            session["admin_session_version"] = user_session_version(admin_user)
            record_change_event(
                store,
                "password_change",
                "admin_user",
                admin_user["id"],
                "Contrasena admin actualizada por el usuario.",
                before,
                admin_user,
            )
            save_store(store)
            success = "Contrasena actualizada correctamente."

    return render_template(
        "account_password.html",
        error=error,
        success=success,
        must_change=bool(session.get("must_change_password")),
    )


def desktop_installer_candidates() -> list[Path]:
    return [
        APP_RESOURCE_ROOT / "dist" / "FVENTAS Desktop.exe",
        Path(__file__).resolve().parent / "dist" / "FVENTAS Desktop.exe",
    ]


def desktop_installer_info() -> dict:
    for candidate in desktop_installer_candidates():
        if not candidate.exists() or not candidate.is_file():
            continue
        digest = hashlib.sha256()
        with candidate.open("rb") as installer_file:
            for chunk in iter(lambda: installer_file.read(1024 * 1024), b""):
                digest.update(chunk)
        size_bytes = candidate.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        return {
            "available": True,
            "path": candidate,
            "filename": "FVENTAS Desktop.exe",
            "sizeBytes": size_bytes,
            "sizeDisplay": f"{size_mb:.1f} MB",
            "sha256": digest.hexdigest(),
            "updatedAt": datetime.fromtimestamp(candidate.stat().st_mtime, timezone.utc).isoformat(),
        }
    return {
        "available": False,
        "path": None,
        "filename": "FVENTAS Desktop.exe",
        "sizeBytes": 0,
        "sizeDisplay": "",
        "sha256": "",
        "updatedAt": "",
    }


@app.get("/")
@app.get("/landing")
@app.get("/inicio")
def landing():
    selected_market_country = normalize_market_country(request.args.get("marketCountry") or "CL")
    selected_plan = plan_pricing_for_country(selected_market_country)
    installer_info = desktop_installer_info()
    return render_template(
        "landing.html",
        plan_name=SAAS_PLAN_NAME,
        plan_price_display=selected_plan["display"],
        selected_market_country=selected_market_country,
        selected_market_profile=market_profile(selected_market_country),
        market_country_options=MARKET_COUNTRY_OPTIONS,
        market_profiles=ACTIVE_MARKET_PROFILES,
        desktop_download_available=installer_info["available"],
        desktop_installer=installer_info,
        desktop_download_unavailable=request.args.get("desktop") == "unavailable",
    )


@app.get("/desktop/download")
def desktop_download():
    installer_info = desktop_installer_info()
    candidate = installer_info.get("path")
    if candidate:
        return send_file(
            candidate,
            as_attachment=True,
            download_name=safe_download_filename(
                installer_info.get("filename") or "FVENTAS Desktop.exe",
                "FVENTAS_Desktop.exe",
            ),
        )
    return redirect(url_for("landing", desktop="unavailable"))


def public_submission_rate_limited(
    store: dict,
    collection: str,
    *,
    ip_address: str,
    email: str = "",
    window_seconds: int = 300,
    max_events: int = 5,
) -> bool:
    now_dt = datetime.now(timezone.utc)
    normalized_email = str(email or "").strip().lower()
    window_seconds = max(1, int(window_seconds or 300))
    max_events = max(1, int(max_events or 5))
    recent_events = []
    for event in store.setdefault(collection, []):
        created_at = parse_utc_datetime(event.get("createdAt"))
        if (now_dt - created_at).total_seconds() > window_seconds:
            continue
        if event.get("ipAddress") == ip_address or (normalized_email and event.get("email", "").lower() == normalized_email):
            recent_events.append(event)
    return len(recent_events) >= max_events


def record_public_submission_rate_event(
    store: dict,
    collection: str,
    *,
    ip_address: str,
    email: str = "",
    action: str = "submit",
    window_seconds: int = 300,
) -> None:
    now = utc_now()
    now_dt = datetime.now(timezone.utc)
    normalized_email = str(email or "").strip().lower()
    events = store.setdefault(collection, [])
    events.append(
        {
            "id": next_id("public-rate", f"{collection}-{ip_address}-{normalized_email}-{action}-{now}"),
            "action": sanitize_text(action, max_length=80, allow_newlines=False),
            "ipAddress": ip_address,
            "email": normalized_email,
            "createdAt": now,
        }
    )
    retention_seconds = max(1, int(window_seconds or 300)) * 4
    store[collection] = [
        event
        for event in events[-1000:]
        if (now_dt - parse_utc_datetime(event.get("createdAt"))).total_seconds() <= retention_seconds
    ]


def mobile_write_subject_key(*, action: str, actor_id: str, company_id: str, device_id: str) -> str:
    raw_value = f"{company_id}:{actor_id}:{device_id}:{action}"
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()[:48]


def guard_mobile_write_rate_limit(
    store: dict,
    *,
    action: str,
    actor: dict,
    actor_type: str,
    company_id: str,
) -> object | None:
    actor_id = str(actor.get("id") or "").strip()
    device_id = mobile_device_id()
    ip_address = request_ip_address()
    window_seconds = max(1, int(app.config.get("MOBILE_WRITE_WINDOW_SECONDS", 60)))
    max_events = max(1, int(app.config.get("MOBILE_WRITE_MAX_EVENTS", 30)))
    subject_key = mobile_write_subject_key(
        action=action,
        actor_id=actor_id,
        company_id=company_id,
        device_id=device_id,
    )
    now_dt = datetime.now(timezone.utc)
    events = store.setdefault("mobile_write_rate_events", [])
    recent_events = [
        event
        for event in events
        if event.get("subjectKey") == subject_key
        and (now_dt - parse_utc_datetime(event.get("createdAt"))).total_seconds() <= window_seconds
    ]
    metadata = {
        "companyId": company_id,
        "actorType": actor_type,
        "action": action,
        "deviceId": device_id,
        "subjectKey": subject_key,
        "windowSeconds": window_seconds,
        "maxEvents": max_events,
    }
    if len(recent_events) >= max_events:
        record_audit_event(
            store,
            "mobile_write_limited",
            actor_type,
            actor_id,
            "Escritura movil bloqueada temporalmente por solicitudes repetidas.",
            metadata=metadata,
            actor={
                "id": actor_id,
                "name": actor.get("businessName") or actor.get("name") or actor_id,
                "role": actor.get("role") or actor_type,
                "companyId": company_id,
            },
            criticality="medium",
        )
        save_store(store)
        return jsonify({"error": "Demasiadas solicitudes recientes. Espera unos minutos antes de reintentar."}), 429

    now = utc_now()
    events.append(
        {
            "id": next_id("mobile-rate", f"{subject_key}-{now}"),
            "companyId": company_id,
            "actorType": actor_type,
            "actorId": actor_id,
            "action": sanitize_text(action, max_length=80, allow_newlines=False),
            "subjectKey": subject_key,
            "ipAddress": ip_address,
            "deviceId": sanitize_text(device_id, max_length=120, allow_newlines=False),
            "createdAt": now,
        }
    )
    retention_seconds = window_seconds * 4
    store["mobile_write_rate_events"] = [
        event
        for event in events[-1000:]
        if (now_dt - parse_utc_datetime(event.get("createdAt"))).total_seconds() <= retention_seconds
    ]
    save_store(store)
    return None


@app.post("/api/landing/access-preference")
def landing_access_preference():
    payload = request.get_json(silent=True) or request.form
    preference = sanitize_text(
        payload.get("preference") or payload.get("choice") or "",
        max_length=80,
        allow_newlines=False,
    )
    allowed = {
        "desktop_download_started",
        "desktop_download_cancelled",
        "mobile_first",
        "mobile_only",
    }
    if preference not in allowed:
        return jsonify({"error": "Preferencia no valida."}), 400

    store = load_store()
    ip_address = request_ip_address()
    now_dt = datetime.now(timezone.utc)
    window_seconds = max(1, int(app.config.get("LANDING_ACCESS_PREFERENCE_WINDOW_SECONDS", 60)))
    max_events = max(1, int(app.config.get("LANDING_ACCESS_PREFERENCE_MAX_EVENTS", 12)))
    recent_events = [
        event
        for event in store.get("landing_access_preferences", [])
        if event.get("ipAddress") == ip_address
        and (now_dt - parse_utc_datetime(event.get("createdAt"))).total_seconds() <= window_seconds
    ]
    if len(recent_events) >= max_events:
        return jsonify({"error": "Demasiadas solicitudes. Intentalo nuevamente en unos minutos."}), 429
    market_country = normalize_market_country(payload.get("marketCountry") or "CL")
    event = {
        "id": next_id("landing-pref", preference),
        "preference": preference,
        "source": sanitize_text(payload.get("source") or "landing", max_length=80, allow_newlines=False),
        "marketCountry": market_country,
        "mobileAppAccessRequested": preference in {"desktop_download_cancelled", "mobile_first", "mobile_only"},
        "userAgent": sanitize_text(request.headers.get("User-Agent", ""), max_length=240, allow_newlines=False),
        "ipAddress": ip_address,
        "createdAt": utc_now(),
    }
    events = store.setdefault("landing_access_preferences", [])
    events.append(event)
    if len(events) > 500:
        del events[:-500]
    save_store(store)
    return jsonify(
        {
            "ok": True,
            "preference": preference,
            "mobileAppAccessRequested": event["mobileAppAccessRequested"],
            "signupUrl": url_for("signup", marketCountry=market_country, desktopAccessPreference=preference),
            "mobileApiUrl": url_for("api_mobile_meta"),
        }
    )


@app.get("/dashboard/perfil")
@app.get("/dashboard/profile")
@app.get("/perfil")
@app.get("/profile")
def account_profile_alias():
    return redirect(url_for("account_password"))


def business_settings(store: dict | None = None) -> dict:
    try:
        active_store = store if store is not None else load_store()
        return dict(active_store.get("business_settings") or {})
    except Exception:
        return {}


def normalize_currency_code(value: str | None, default: str = "USD") -> str:
    code = sanitize_text(value or "", max_length=8, allow_newlines=False).upper()
    code = re.sub(r"[^A-Z]", "", code)
    return code[:3] or default


def normalize_market_country(value: str | None, default: str = "CL") -> str:
    code = sanitize_text(value or default, max_length=10, allow_newlines=False).upper()
    if code in ACTIVE_MARKET_COUNTRIES:
        return code
    fallback = sanitize_text(default or "CL", max_length=10, allow_newlines=False).upper()
    return fallback if fallback in ACTIVE_MARKET_COUNTRIES else "CL"


def market_profile(country_code: str | None = None) -> dict:
    return copy.deepcopy(MARKET_PROFILES[normalize_market_country(country_code)])


def market_profile_from_settings(settings: dict | None = None) -> dict:
    data = settings or {}
    return market_profile(data.get("marketCountry") or data.get("country") or "CL")


def plan_pricing_for_country(country_code: str | None = None) -> dict:
    profile = market_profile(country_code)
    currency = normalize_currency_code(profile.get("planCurrency"), "CLP")
    price = safe_float(profile.get("planPrice"), SAAS_PLAN_PRICE_CLP)
    return {
        "currency": currency,
        "price": price,
        "priceClp": price if currency == "CLP" else 0,
        "display": money_currency(price, currency),
        "profile": profile,
    }


def currency_context(store: dict | None = None) -> dict:
    settings = business_settings(store)
    profile = market_profile_from_settings(settings)
    sales_currency = normalize_currency_code(profile.get("salesCurrency"), "USD")
    local_currency = normalize_currency_code(profile.get("localCurrency"), sales_currency)
    rate = safe_float(profile.get("exchangeRateBaseToLocal"), 1)
    return {
        "market_country": profile["code"],
        "market_profile": profile,
        "sales_currency": sales_currency,
        "local_currency": local_currency,
        "exchange_rate": rate,
    }


def sales_currency_for_company(store: dict | None = None, company_id: str | None = None) -> str:
    source_store = store or load_store()
    profile = active_market_profile_for_store(source_store, company_id)
    return normalize_currency_code(profile.get("salesCurrency"), "USD")


def money_sales(value: float | int | str | None, store: dict | None = None, company_id: str | None = None) -> str:
    return money_currency(value, sales_currency_for_company(store, company_id))


def active_market_profile_for_store(store: dict | None = None, company_id: str | None = None) -> dict:
    source_store = store or load_store()
    settings = business_settings(source_store)
    company = get_company(source_store, company_id) if company_id else None
    if company:
        company_country = (
            company.get("marketCountry")
            or company.get("country")
            or (company.get("marketProfile") or {}).get("code")
        )
        if company_country:
            return market_profile(company_country)
    return market_profile_from_settings(settings)


def normalize_tax_id_for_market(value: str | None, profile: dict | None = None) -> str:
    active_profile = profile or market_profile("CL")
    if active_profile.get("code") == "CL":
        return normalize_chilean_rut(value)
    text = sanitize_text(value or "", max_length=40, allow_newlines=False).upper()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^A-Z0-9.\-]", "", text)
    core = re.sub(r"[^A-Z0-9]", "", text)
    return text if len(core) >= 4 else ""


def normalize_phone_for_market(value: str | None, profile: dict | None = None) -> str:
    active_profile = profile or market_profile("CL")
    if active_profile.get("code") == "CL":
        return normalize_chilean_phone(value)
    raw = str(value or "").strip()
    digits = re.sub(r"\D+", "", raw)
    prefix_digits = re.sub(r"\D+", "", str(active_profile.get("phonePrefix") or ""))
    if not digits:
        return ""
    if not raw.startswith("+") and prefix_digits and not digits.startswith(prefix_digits):
        digits = prefix_digits + digits
    if len(digits) < 7 or len(digits) > 15:
        return ""
    return f"+{digits}"


def normalize_location_for_market(
    state: str | None,
    city: str | None,
    profile: dict | None = None,
) -> tuple[str, str, str]:
    active_profile = profile or market_profile("CL")
    location_options = country_location_options(active_profile.get("code"))
    if location_options:
        return normalize_country_location(active_profile.get("code"), state, city)
    normalized_state = sanitize_text(state or "", max_length=120, allow_newlines=False)
    normalized_city = sanitize_text(city or "", max_length=120, allow_newlines=False)
    if not normalized_state:
        return "", "", "Ingresa region, estado o provincia."
    if not normalized_city:
        return normalized_state, "", "Ingresa ciudad."
    return normalized_state, normalized_city, ""


def current_rate() -> float:
    return currency_context().get("exchange_rate", 950)


SUBSCRIPTION_ACTIVE_STATUSES = {"active", "trial"}
SUBSCRIPTION_STATUS_OPTIONS = [
    ("pending_payment", "Pendiente de pago"),
    ("active", "Activa"),
    ("trial", "Prueba"),
    ("past_due", "Pago vencido"),
    ("suspended", "Suspendida"),
    ("cancelled", "Cancelada"),
]


def subscription_status_label(status: str) -> str:
    return dict(SUBSCRIPTION_STATUS_OPTIONS).get(status, status or "Sin estado")


ACCESS_PREFERENCE_LABELS = {
    "desktop_download_started": "Panel Windows",
    "desktop_download_cancelled": "App movil prioritaria",
    "mobile_first": "App movil prioritaria",
    "mobile_only": "Solo app movil",
}


def access_preference_label(value: str | None) -> str:
    return ACCESS_PREFERENCE_LABELS.get(str(value or "").strip(), "Alta completa")


def company_setup_checklist(company: dict, subscription: dict, store: dict) -> dict:
    company_id = company.get("id", "")

    def in_company(record: dict) -> bool:
        return record_company_id(record, store) == company_id

    active_admins = [
        user
        for user in store.get("admin_users", [])
        if in_company(user)
        and user.get("role") in WEB_ADMIN_ROLES
        and user.get("status") == "active"
    ]
    active_sellers = [
        user
        for user in store.get("admin_users", [])
        if in_company(user)
        and user.get("role") == "sales"
        and user.get("status") == "active"
    ]
    active_clients = [
        client
        for client in store.get("clients", [])
        if in_company(client) and client.get("status") == "active"
    ]
    active_products = [
        product
        for product in store.get("products", [])
        if in_company(product) and product.get("status") == "active"
    ]
    active_categories = [
        category
        for category in store.get("categories", [])
        if in_company(category) and category.get("status") == "active"
    ]
    purchase_conditions = company.get("purchaseConditions") if isinstance(company.get("purchaseConditions"), dict) else {}
    subscription_active = (
        subscription.get("status") in SUBSCRIPTION_ACTIVE_STATUSES
        or company.get("status") in SUBSCRIPTION_ACTIVE_STATUSES
    )
    items = [
        {
            "label": "Suscripcion activa",
            "done": subscription_active,
            "detail": subscription_status_label(subscription.get("status") or company.get("status")),
        },
        {
            "label": "Aceptacion legal",
            "done": bool((company.get("legalAcceptance") or {}).get("accepted")),
            "detail": (company.get("legalAcceptance") or {}).get("termsVersion") or "Pendiente",
        },
        {
            "label": "Administrador",
            "done": bool(active_admins),
            "detail": f"{len(active_admins)} activo(s)",
        },
        {
            "label": "Condiciones de compra",
            "done": bool(purchase_conditions.get("title") and purchase_conditions.get("scopeLabel")),
            "detail": purchase_conditions.get("title") or "Sin configurar",
        },
        {
            "label": "Categorias",
            "done": bool(active_categories),
            "detail": f"{len(active_categories)} activa(s)",
        },
        {
            "label": "Catalogo",
            "done": bool(active_products),
            "detail": f"{len(active_products)} producto(s)",
        },
        {
            "label": "Usuarios moviles",
            "done": bool(active_sellers or active_clients),
            "detail": f"{len(active_sellers)} vendedor(es), {len(active_clients)} cliente(s)",
        },
    ]
    done_count = sum(1 for item in items if item["done"])
    total_count = len(items)
    return {
        "items": items,
        "done": done_count,
        "total": total_count,
        "percent": round((done_count / total_count) * 100) if total_count else 0,
        "missing": [item["label"] for item in items if not item["done"]],
        "ready": done_count == total_count,
    }


def default_company_id(store: dict | None = None) -> str:
    if store and store.get("companies"):
        return store["companies"][0].get("id") or DEFAULT_COMPANY_ID
    return DEFAULT_COMPANY_ID


def get_company(store: dict, company_id: str) -> dict | None:
    return next((company for company in store.get("companies", []) if company.get("id") == company_id), None)


def current_company_id(store: dict | None = None) -> str:
    if session.get("company_id"):
        return session["company_id"]
    if store is None:
        store = load_store()
    admin_user = current_admin_user(store)
    return (admin_user or {}).get("companyId") or default_company_id(store)


def current_company(store: dict | None = None) -> dict:
    if store is None:
        store = load_store()
    company = get_company(store, current_company_id(store))
    if company:
        return company
    if store.get("companies"):
        return store["companies"][0]
    return {"id": DEFAULT_COMPANY_ID, "name": "FVENTAS", "status": "active"}


def current_subscription(store: dict | None = None, company_id: str | None = None) -> dict | None:
    if store is None:
        store = load_store()
    company_id = company_id or current_company_id(store)
    return next(
        (subscription for subscription in store.get("subscriptions", []) if subscription.get("companyId") == company_id),
        None,
    )


def subscription_allows_access(store: dict, admin_user: dict) -> bool:
    if admin_user.get("role") == "platform_admin":
        return True
    company_id = admin_user.get("companyId") or default_company_id(store)
    return company_subscription_allows_access(store, company_id)


def company_subscription_allows_access(store: dict, company_id: str | None) -> bool:
    company_id = company_id or default_company_id(store)
    company = get_company(store, company_id)
    if company and company.get("status") not in SUBSCRIPTION_ACTIVE_STATUSES:
        return False
    subscription = current_subscription(store, company_id)
    return bool(subscription and subscription.get("status") in SUBSCRIPTION_ACTIVE_STATUSES)


def normalized_payment_terms(value, fallback: list[int] | None = None) -> list[int]:
    if isinstance(value, str):
        raw_terms = re.split(r"[\s,;|/]+", value)
    elif isinstance(value, list):
        raw_terms = value
    elif value in (None, ""):
        raw_terms = []
    else:
        raw_terms = [value]

    terms = []
    for term in raw_terms:
        value = safe_int(term, -1)
        if value >= 0 and value not in terms:
            terms.append(value)
    if terms:
        return sorted(terms)
    return sorted(set(fallback or [0]))


def payment_term_options(store: dict | None = None) -> list[int]:
    raw_terms = business_settings(store).get("defaultPaymentTermsDays") or PAYMENT_TERM_OPTIONS
    return normalized_payment_terms(raw_terms, PAYMENT_TERM_OPTIONS)


@app.get("/healthz")
def healthz():
    return jsonify(
        {
            "status": "ok",
            "service": "fventas-admin",
            "appVersion": app.config.get("APP_VERSION", "0.9.0"),
            "buildSha": app.config.get("BUILD_SHA", ""),
        }
    )


@app.get("/privacy")
@app.get("/privacidad")
def privacy_policy():
    return render_template(
        "privacy_policy.html",
        legal_privacy_version=LEGAL_PRIVACY_VERSION,
        legal_terms_version=LEGAL_TERMS_VERSION,
    )


@app.get("/terms")
@app.get("/terminos")
@app.get("/terms-of-service")
def terms_of_service():
    return render_template(
        "terms_of_service.html",
        legal_terms_version=LEGAL_TERMS_VERSION,
        legal_privacy_version=LEGAL_PRIVACY_VERSION,
    )


@app.route("/account-deletion", methods=["GET", "POST"])
@app.route("/delete-account", methods=["GET", "POST"])
def account_deletion_page():
    submitted = False
    request_id = ""
    message = ""
    error = ""
    email = ""

    if request.method == "POST":
        store = load_store()
        email = str(request.form.get("email") or "").strip().lower()
        reason = str(request.form.get("reason") or "").strip()
        ip_address = request_ip_address()
        window_seconds = max(1, int(app.config.get("ACCOUNT_DELETION_WINDOW_SECONDS", 300)))
        max_events = max(1, int(app.config.get("ACCOUNT_DELETION_MAX_EVENTS", 5)))
        if public_submission_rate_limited(
            store,
            "account_deletion_rate_events",
            ip_address=ip_address,
            email=email,
            window_seconds=window_seconds,
            max_events=max_events,
        ):
            error = "Hemos recibido varias solicitudes recientes. Espera unos minutos antes de intentarlo nuevamente."
        else:
            subject_type, subject = find_mobile_account_for_deletion(store, email)
            if subject:
                request_id = register_public_account_deletion_request(
                    store,
                    subject_type=subject_type,
                    subject=subject,
                    email=email,
                    channel="web",
                    reason=reason,
                    actor={"id": email, "name": email, "role": "public"},
                )
            else:
                request_id = register_unknown_account_deletion_request(
                    store,
                    email=email,
                    channel="web",
                    reason=reason,
                    actor={
                        "id": email or "account-deletion-public",
                        "name": email or "solicitud publica",
                        "role": "public",
                    },
                )
                if subject_type == "ambiguous":
                    record_audit_event(
                        store,
                        "account_deletion_ambiguous_public",
                        "account_deletion_request",
                        request_id,
                        "Solicitud publica de eliminacion requiere revision manual por correo asociado a multiples cuentas.",
                        actor={
                            "id": email or "account-deletion-public",
                            "name": email or "solicitud publica",
                            "role": "public",
                        },
                        metadata={"email": email, "requestId": request_id},
                        criticality="high",
                    )
                notify_admin(
                    store,
                    "Solicitud de eliminacion de cuenta",
                    (
                        f"Solicitud recibida para {email}. El correo coincide con multiples cuentas; revisar manualmente."
                        if subject_type == "ambiguous"
                        else f"Solicitud recibida para {email or 'correo no informado'}. Revisar manualmente."
                    ),
                    notification_type="warning",
                    priority="high",
                    module="admin_users",
                    entity_type="account_deletion_request",
                    entity_id=request_id,
                    dedupe_key=f"account-deletion-web-{email}",
                )
            record_public_submission_rate_event(
                store,
                "account_deletion_rate_events",
                ip_address=ip_address,
                email=email,
                action="account_deletion",
                window_seconds=window_seconds,
            )
            save_store(store)
            submitted = True
            message = "Solicitud recibida. FVENTAS revisara la cuenta y te contactara si necesita validar informacion comercial."

    return render_template(
        "account_deletion.html",
        submitted=submitted,
        request_id=request_id,
        message=message,
        error=error,
        email=email,
    ), (429 if error else 200)


@app.get("/readyz")
def readyz():
    try:
        store = load_store()
        response = {
            "status": "ready",
            "appVersion": app.config.get("APP_VERSION", "0.9.0"),
            "buildSha": app.config.get("BUILD_SHA", ""),
        }
        if app.config.get("READYZ_PUBLIC_DETAILS"):
            response.update(
                {
                    "dataBackend": app.config.get("DATA_BACKEND"),
                    "storageBackend": app.config.get("STORAGE_BACKEND"),
                    "mobileTokenRequired": bool(app.config.get("REQUIRE_MOBILE_TOKEN")),
                    "products": len(store.get("products", [])),
                    "clients": len(store.get("clients", [])),
                    "orders": len(store.get("orders", [])),
                    "quotes": len(store.get("quotes", [])),
                    "crm": len(store.get("crm_records", [])),
                    "runtime": runtime_capacity_snapshot(),
                }
            )
        return jsonify(response)
    except Exception as exc:
        response = {"status": "not_ready"}
        if app.config.get("READYZ_PUBLIC_DETAILS"):
            response["error"] = str(exc)
        return jsonify(response), 503


def mobile_token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="fventas-mobile-client")


def document_token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="fventas-document-download")


def signup_success_token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="fventas-signup-success")


def issue_signup_success_token(company_id: str) -> str:
    return signup_success_token_serializer().dumps({"companyId": company_id})


def signup_success_token_company_id(token: str) -> str:
    if not token:
        return ""
    try:
        payload = signup_success_token_serializer().loads(token, max_age=60 * 30)
    except (BadSignature, SignatureExpired):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("companyId") or "")


def mobile_request_device_id(payload: dict | None = None) -> str:
    payload = payload or {}
    return (
        request.headers.get("X-FVENTAS-Device-Id")
        or request.headers.get("X-Device-Id")
        or str(payload.get("deviceId") or "")
    )[:120]


def mobile_device_id(payload: dict | None = None) -> str:
    return (
        mobile_request_device_id(payload)
        or request_device_hash()
    )[:120]


def issue_mobile_token(client: dict, device_id: str = "") -> str:
    company_id = mobile_required_company_id(client)
    return mobile_token_serializer().dumps(
        {
            "type": "client",
            "clientId": client["id"],
            "id": client["id"],
            "companyId": company_id,
            "role": "client",
            "sessionVersion": safe_int(client.get("mobileSessionVersion"), 0),
            "deviceId": device_id or mobile_device_id(),
        }
    )


def issue_mobile_admin_token(user: dict, device_id: str = "") -> str:
    company_id = mobile_required_company_id(user)
    return mobile_token_serializer().dumps(
        {
            "type": "admin",
            "adminUserId": user["id"],
            "id": user["id"],
            "companyId": company_id,
            "role": user.get("role", ""),
            "sessionVersion": user_session_version(user),
            "deviceId": device_id or mobile_device_id(),
        }
    )


def mobile_token_payload() -> dict:
    if has_request_context() and hasattr(g, "mobile_token_payload"):
        return g.mobile_token_payload

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        if has_request_context():
            g.mobile_token_payload = {}
        return {}

    token = header.removeprefix("Bearer ").strip()
    if not token:
        if has_request_context():
            g.mobile_token_payload = {}
        return {}

    try:
        payload = mobile_token_serializer().loads(
            token,
            max_age=int(app.config.get("MOBILE_TOKEN_MAX_AGE_SECONDS", 60 * 60 * 24 * 7)),
        )
    except (BadSignature, SignatureExpired):
        if has_request_context():
            g.mobile_token_payload = {}
        return {}

    normalized_payload = payload if isinstance(payload, dict) else {}
    if has_request_context():
        g.mobile_token_payload = normalized_payload
    return normalized_payload


def mobile_token_company_id(payload: dict) -> str:
    return str(payload.get("companyId") or "").strip()


def mobile_required_company_id(record: dict | None) -> str:
    return str((record or {}).get("companyId") or "").strip()


def mobile_subject_matches_token_company(subject: dict | None, store: dict, payload: dict) -> bool:
    if not subject:
        return False
    subject_company_id = mobile_required_company_id(subject)
    if not subject_company_id:
        return False
    token_company_id = mobile_token_company_id(payload)
    if not token_company_id:
        return not bool(app.config.get("REJECT_LEGACY_MOBILE_TOKENS"))
    return hmac.compare_digest(subject_company_id, token_company_id)


def mobile_find_admin_for_token(store: dict, payload: dict) -> dict | None:
    admin_id = payload.get("adminUserId") or payload.get("id", "")
    token_company_id = mobile_token_company_id(payload)
    candidates = [
        user for user in store.get("admin_users", [])
        if user.get("id") == admin_id
    ]
    if token_company_id:
        candidates = [
            user for user in candidates
            if record_company_id(user, store) == token_company_id
        ]
    return candidates[0] if candidates else None


def mobile_find_client_for_token(store: dict, payload: dict) -> dict | None:
    client_id = payload.get("clientId") or payload.get("id", "")
    token_company_id = mobile_token_company_id(payload)
    candidates = [
        client for client in store.get("clients", [])
        if client.get("id") == client_id
    ]
    if token_company_id:
        candidates = [
            client for client in candidates
            if record_company_id(client, store) == token_company_id
        ]
    return candidates[0] if candidates else None


def mobile_subscription_response(company_id: str | None):
    return jsonify(
        {
            "meta": mobile_api_meta(),
            "error": "La suscripcion de la empresa no esta activa.",
            "code": "subscription_inactive",
            "companyId": company_id or "",
        }
    ), 402


def mobile_token_subject_company_id(store: dict, payload: dict) -> str:
    if payload.get("type") == "admin":
        user = mobile_find_admin_for_token(store, payload)
        return mobile_required_company_id(user) if user else ""
    client = mobile_find_client_for_token(store, payload)
    return mobile_required_company_id(client) if client else ""


@app.before_request
def track_runtime_identity_seen():
    if session.get("admin_authenticated"):
        runtime_identity_seen(
            "admin_panel",
            str(session.get("company_id") or ""),
            str(session.get("admin_user_id") or session.get("admin_session_id") or ""),
            str(session.get("admin_role") or "admin"),
        )

    if not request.path.startswith(("/api/mobile/", "/api/v1/mobile/")):
        return None

    payload = mobile_token_payload()
    if not payload:
        return None

    identity_type = "seller_app" if payload.get("type") == "admin" else "client_app"
    subject_id = str(payload.get("adminUserId") or payload.get("clientId") or payload.get("id") or "")
    runtime_identity_seen(
        identity_type,
        mobile_token_company_id(payload),
        subject_id,
        str(payload.get("role") or identity_type),
    )
    return None


@app.before_request
def protect_mobile_company_subscription():
    if not request.path.startswith(("/api/mobile/", "/api/v1/mobile/")):
        return None
    exempt_paths = {
        "/api/mobile/auth/login",
        "/api/v1/mobile/auth/login",
        "/api/mobile/auth/recover-password",
        "/api/v1/mobile/auth/recover-password",
        "/api/v1/mobile/meta",
        "/api/mobile/meta",
        "/api/v1/mobile/locations/chile",
    }
    if request.path in exempt_paths:
        return None

    payload = mobile_token_payload()
    if not payload:
        return None

    store = load_store()
    company_id = mobile_token_subject_company_id(store, payload)
    if company_id and not company_subscription_allows_access(store, company_id):
        record_audit_event(
            store,
            "mobile_subscription_blocked",
            "subscription",
            company_id,
            "Acceso movil bloqueado por suscripcion pendiente o suspendida.",
            actor={
                "id": payload.get("id", ""),
                "name": payload.get("id", "app movil"),
                "role": payload.get("role", "mobile"),
            },
            metadata={"path": request.path, "method": request.method},
        )
        save_store(store)
        return mobile_subscription_response(company_id)

    return None


def mobile_token_matches_device(payload: dict) -> bool:
    header_device = request.headers.get("X-FVENTAS-Device-Id") or request.headers.get("X-Device-Id")
    token_device = str(payload.get("deviceId") or "")[:120]
    if not token_device:
        return not bool(app.config.get("REJECT_LEGACY_MOBILE_TOKENS"))
    if not header_device:
        return not bool(app.config.get("REQUIRE_MOBILE_DEVICE_HEADER"))
    return hmac.compare_digest(token_device, header_device[:120])


def mobile_token_version_valid(subject: dict, payload: dict, version_key: str) -> bool:
    if not mobile_token_matches_device(payload):
        return False
    if "sessionVersion" not in payload:
        return not bool(app.config.get("REJECT_LEGACY_MOBILE_TOKENS"))
    return safe_int(payload.get("sessionVersion"), -1) == safe_int(subject.get(version_key), 0)


ACCOUNT_DELETION_BLOCKING_STATUSES = {"requested", "processing", "approved", "deleted"}


def mobile_account_deletion_status(subject: dict | None) -> str:
    return str((subject or {}).get("deletionStatus") or "").strip().lower()


def mobile_account_access_blocked(subject: dict | None) -> bool:
    if not subject:
        return True
    mobile_access = str(subject.get("mobileAccess") or "").strip().lower()
    return (
        mobile_account_deletion_status(subject) in ACCOUNT_DELETION_BLOCKING_STATUSES
        or mobile_access in {"deletion_requested", "blocked", "disabled"}
        or subject.get("mobileAccessBlocked") is True
    )


def mobile_account_deletion_response():
    return jsonify(
        {
            "meta": mobile_api_meta(),
            "error": "La cuenta tiene una solicitud de eliminacion en proceso.",
            "code": "account_deletion_requested",
        }
    )


def account_deletion_public_label(subject_id: str) -> str:
    suffix = str(subject_id or secrets.token_hex(4))[-8:].upper()
    return f"Cuenta eliminada {suffix}"


def complete_client_account_deletion(store: dict, client: dict) -> tuple[dict, list[dict]]:
    """Anonymize mobile B2B access while preserving commercial traceability."""
    before = copy.deepcopy(client)
    now = utc_now()
    actor_id = session.get("admin_user_id", "")
    actor_name = session.get("admin_name", "FVENTAS Admin")
    actor_role = current_admin_role()
    public_label = account_deletion_public_label(client.get("id", ""))
    deleted_email = f"deleted+{client.get('id', secrets.token_hex(4))}@deleted.fventas.local"

    client.update(
        {
            "businessName": public_label,
            "legalName": public_label,
            "commercialName": public_label,
            "contactName": "",
            "administrativeContact": "",
            "receivingContact": "",
            "email": deleted_email,
            "phone": "",
            "whatsapp": "",
            "taxId": "",
            "address": "",
            "fiscalAddress": "",
            "shippingAddress": "",
            "status": "inactive",
            "collectionStatus": "without_debt",
            "mobileAccess": "deleted",
            "mobileAccessEnabled": False,
            "mobileAccessBlocked": True,
            "mustChangePassword": True,
            "passwordHash": generate_password_hash(secrets.token_urlsafe(32)),
            "creditEnabled": False,
            "creditRequestStatus": "none",
            "creditLimitUsd": 0,
            "creditRequestedUsd": 0,
            "deletionStatus": "deleted",
            "deletionCompletedAt": now,
            "deletionCompletedById": actor_id,
            "deletionCompletedByName": actor_name,
            "updatedAt": now,
            "updatedVia": "admin",
            "updatedById": actor_id,
            "updatedByName": actor_name,
            "updatedByRole": actor_role,
            "mobileSessionVersion": safe_int(client.get("mobileSessionVersion"), 0) + 1,
        }
    )

    changed_orders: list[dict] = []
    for order in visible_records_for_current_company(store, "orders"):
        if order.get("customerId") != client.get("id"):
            continue
        order["customerName"] = public_label
        order["customerEmail"] = ""
        order["customerPhone"] = ""
        order["updatedAt"] = now
        order["updatedByName"] = actor_name
        customer = order.get("customer")
        if isinstance(customer, dict):
            customer["name"] = public_label
            for key in ("email", "phone", "taxId", "rif", "address", "contactName"):
                customer[key] = ""
        changed_orders.append(order)

    return before, changed_orders


ACCOUNT_DELETION_STATUS_LABELS = {
    "requested": "Solicitada",
    "processing": "En revision",
    "approved": "Aprobada para cierre",
    "rejected": "Rechazada",
    "deleted": "Eliminada/anonimizada",
    "closed_no_account": "Cerrada sin cuenta",
}


def account_deletion_status_label(status: str) -> str:
    return ACCOUNT_DELETION_STATUS_LABELS.get(str(status or "").strip().lower(), status or "Sin estado")


def account_deletion_status_badge(status: str) -> str:
    return {
        "requested": "text-bg-warning",
        "processing": "text-bg-info",
        "approved": "text-bg-primary",
        "rejected": "text-bg-secondary",
        "deleted": "text-bg-dark",
        "closed_no_account": "text-bg-light",
    }.get(str(status or "").strip().lower(), "text-bg-light")


def complete_admin_user_account_deletion(store: dict, user: dict) -> tuple[dict, list[dict], list[dict]]:
    """Anonymize a mobile/admin user while retaining commercial history by id."""
    before = copy.deepcopy(user)
    now = utc_now()
    actor_id = session.get("admin_user_id", "")
    actor_name = session.get("admin_name", "FVENTAS Admin")
    actor_role = current_admin_role()
    public_label = account_deletion_public_label(user.get("id", ""))
    deleted_email = f"deleted+{user.get('id', secrets.token_hex(4))}@deleted.fventas.local"

    user.update(
        {
            "firstName": "",
            "lastName": "",
            "name": public_label,
            "email": deleted_email,
            "phone": "",
            "status": "inactive",
            "mobileAccess": "deleted",
            "mobileAccessEnabled": False,
            "mobileAccessBlocked": True,
            "mustChangePassword": True,
            "passwordHash": generate_password_hash(secrets.token_urlsafe(32)),
            "deletionStatus": "deleted",
            "deletionCompletedAt": now,
            "deletionCompletedById": actor_id,
            "deletionCompletedByName": actor_name,
            "updatedAt": now,
            "updatedVia": "admin",
            "updatedById": actor_id,
            "updatedByName": actor_name,
            "updatedByRole": actor_role,
        }
    )
    bump_user_session_version(user)

    changed_clients: list[dict] = []
    changed_orders: list[dict] = []
    subject_company_id = record_company_id(user, store)
    for client in store.get("clients", []):
        if record_company_id(client, store) != subject_company_id or client.get("assignedSellerId") != user.get("id"):
            continue
        client["assignedSellerName"] = public_label
        client["updatedAt"] = now
        client["updatedByName"] = actor_name
        changed_clients.append(client)

    for order in store.get("orders", []):
        if record_company_id(order, store) != subject_company_id:
            continue
        touched = False
        if order.get("sellerId") == user.get("id"):
            order["sellerName"] = public_label
            touched = True
        if order.get("createdById") == user.get("id"):
            order["createdByName"] = public_label
            touched = True
        if touched:
            order["updatedAt"] = now
            order["updatedByName"] = actor_name
            changed_orders.append(order)

    return before, changed_clients, changed_orders


def register_unknown_account_deletion_request(
    store: dict,
    *,
    email: str,
    channel: str,
    reason: str,
    actor: dict | None = None,
) -> str:
    now = utc_now()
    normalized_email = str(email or "").strip().lower()
    existing = next(
        (
            item
            for item in store.setdefault("account_deletion_requests", [])
            if item.get("email", "").lower() == normalized_email
            and item.get("subjectType") == "unknown"
            and item.get("status") in {"requested", "processing", "approved"}
        ),
        None,
    )
    if existing:
        existing["updatedAt"] = now
        existing["lastRepeatedAt"] = now
        existing["repeatCount"] = safe_int(existing.get("repeatCount"), 0) + 1
        return existing["id"]

    request_id = next_id("acctdel", normalized_email or now)
    store.setdefault("account_deletion_requests", []).append(
        {
            "id": request_id,
            "email": normalized_email,
            "subjectType": "unknown",
            "subjectId": "",
            "companyId": "",
            "channel": channel,
            "reason": str(reason or "").strip()[:500],
            "status": "requested",
            "resolutionNote": "",
            "createdAt": now,
            "updatedAt": now,
        }
    )
    record_audit_event(
        store,
        "account_deletion_requested_unknown",
        "account_deletion_request",
        request_id,
        "Solicitud publica de eliminacion para un correo no encontrado.",
        actor=actor or {"id": normalized_email or request_id, "name": normalized_email or "solicitud publica", "role": "public"},
        metadata={"email": normalized_email, "channel": channel, "reason": str(reason or "").strip()[:500]},
        criticality="medium",
    )
    return request_id


def find_mobile_account_for_deletion(store: dict, email: str) -> tuple[str, dict | None]:
    normalized = email.strip().lower()
    if not normalized:
        return "", None
    matches: list[tuple[str, dict]] = [
        ("client", item)
        for item in store.get("clients", [])
        if item.get("email", "").lower() == normalized
    ]
    matches.extend(
        ("admin_user", item)
        for item in store.get("admin_users", [])
        if item.get("email", "").lower() == normalized
    )
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return "ambiguous", None
    return "", None


def register_public_account_deletion_request(
    store: dict,
    *,
    subject_type: str,
    subject: dict,
    email: str,
    channel: str,
    reason: str,
    actor: dict | None = None,
) -> str:
    """Register a public erasure request without mutating the matched account yet."""
    now = utc_now()
    normalized_email = str(email or "").strip().lower()
    subject_id = subject.get("id", "")
    company_id = record_company_id(subject, store)
    subject_label = subject.get("businessName") or subject.get("name") or subject.get("email", "")
    role_label = "Cliente B2B" if subject_type == "client" else ROLE_LABELS.get(subject.get("role", ""), subject.get("role", ""))
    existing = next(
        (
            item
            for item in store.setdefault("account_deletion_requests", [])
            if item.get("subjectType") == subject_type
            and item.get("subjectId") == subject_id
            and item.get("status") in {"requested", "processing", "approved"}
        ),
        None,
    )
    if existing:
        before = copy.deepcopy(existing)
        existing["updatedAt"] = now
        existing["lastRepeatedAt"] = now
        existing["repeatCount"] = safe_int(existing.get("repeatCount"), 0) + 1
        if reason:
            existing["reason"] = str(reason or "").strip()[:500]
        record_change_event(
            store,
            "account_deletion_public_repeat",
            "account_deletion_request",
            existing["id"],
            "Solicitud publica de eliminacion repetida; acceso movil sigue pendiente de verificacion.",
            before,
            existing,
            actor=actor or {"id": normalized_email or subject_id, "name": normalized_email or "solicitud publica", "role": "public"},
            criticality="medium",
        )
        return existing["id"]

    request_id = next_id("acctdel", f"public-{subject_type}-{subject_id}-{now}")
    request_record = {
        "id": request_id,
        "email": normalized_email,
        "subjectType": subject_type,
        "subjectId": subject_id,
        "subjectLabel": subject_label,
        "companyId": company_id,
        "companyName": (find_by_id(store.get("companies", []), company_id) or {}).get("name", ""),
        "role": role_label,
        "channel": channel,
        "reason": str(reason or "").strip()[:500],
        "status": "requested",
        "resolutionNote": "",
        "requiresVerification": True,
        "accessBlocked": False,
        "createdAt": now,
        "updatedAt": now,
    }
    store.setdefault("account_deletion_requests", []).append(request_record)
    record_audit_event(
        store,
        "account_deletion_public_requested",
        "account_deletion_request",
        request_id,
        "Solicitud publica de eliminacion registrada para verificacion antes de bloquear acceso movil.",
        metadata={"after": request_record, "companyId": company_id},
        actor=actor or {"id": normalized_email or subject_id, "name": normalized_email or "solicitud publica", "role": "public"},
        criticality="medium",
    )
    notify_admin(
        store,
        "Solicitud publica de eliminacion",
        f"{subject_label or normalized_email} solicito eliminar su cuenta desde web. Validar identidad antes de bloquear acceso movil.",
        notification_type="warning",
        priority="high",
        module="platform_privacy",
        entity_type="account_deletion_request",
        entity_id=request_id,
        dedupe_key=f"account-deletion-public-{subject_type}-{subject_id}",
        metadata={"subjectType": subject_type, "subjectId": subject_id, "companyId": company_id, "channel": channel},
    )
    return request_id


def request_mobile_account_deletion(
    store: dict,
    subject_type: str,
    subject: dict,
    *,
    channel: str = "mobile",
    reason: str = "",
    actor: dict | None = None,
) -> tuple[str, bool]:
    now = utc_now()
    company_id = record_company_id(subject, store)
    request_id = subject.get("deletionRequestId") or next_id("acctdel", f"{subject_type}-{subject.get('id', '')}-{now}")
    reason = str(reason or "").strip()[:500]
    actor = actor or {
        "id": subject.get("id", ""),
        "name": subject.get("businessName") or subject.get("name") or subject.get("email", ""),
        "role": subject.get("role", "client"),
    }

    if mobile_account_deletion_status(subject) in ACCOUNT_DELETION_BLOCKING_STATUSES:
        record_audit_event(
            store,
            "account_deletion_requested_repeat",
            subject_type,
            subject.get("id", ""),
            "Solicitud de eliminacion repetida sobre una cuenta ya bloqueada para revision.",
            actor=actor,
            metadata={"companyId": company_id, "requestId": request_id, "channel": channel, "reason": reason},
            criticality="medium",
        )
        return request_id, False

    before = copy.deepcopy(subject)
    subject["deletionStatus"] = "requested"
    subject["deletionRequestId"] = request_id
    subject["deletionRequestedAt"] = now
    subject["deletionRequestChannel"] = channel
    subject["deletionRequestReason"] = reason
    subject["mobileAccess"] = "deletion_requested"
    subject["mobileAccessEnabled"] = False
    subject["updatedAt"] = now
    if subject_type == "client":
        subject["mobileSessionVersion"] = safe_int(subject.get("mobileSessionVersion"), 0) + 1
    else:
        bump_user_session_version(subject)

    record_change_event(
        store,
        "account_deletion_requested",
        subject_type,
        subject.get("id", ""),
        f"Solicitud de eliminacion de cuenta recibida via {channel}. Acceso movil bloqueado hasta revision operativa.",
        before,
        subject,
        actor=actor,
        criticality="high",
    )
    notify_admin(
        store,
        "Solicitud de eliminacion de cuenta",
        f"{actor.get('name') or subject.get('email', '')} solicito eliminar o desactivar su cuenta.",
        notification_type="warning",
        priority="high",
        module="admin_users" if subject_type == "admin_user" else "clients",
        entity_type=subject_type,
        entity_id=subject.get("id", ""),
        dedupe_key=f"account-deletion-{subject_type}-{subject.get('id', '')}",
        metadata={"companyId": company_id, "requestId": request_id, "channel": channel},
    )
    return request_id, True


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
    user = mobile_find_admin_for_token(store, payload) if payload.get("type") == "admin" else None
    if (
        not user
        or user.get("status") != "active"
        or user.get("role") not in MOBILE_SALES_ROLES
        or not mobile_required_company_id(user)
        or user.get("mobileAccessEnabled", True) is False
        or mobile_account_access_blocked(user)
        or not mobile_subject_matches_token_company(user, store, payload)
        or not mobile_token_version_valid(user, payload, "sessionVersion")
    ):
        return None, jsonify({"error": "Token de vendedor requerido."})
    return user, None


def require_mobile_client_id() -> tuple[str, object | None]:
    customer_id = mobile_token_client_id()
    if not customer_id:
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
    client = mobile_find_client_for_token(store, payload)
    if (
        not client
        or client.get("status") != "active"
        or client.get("mobileAccessEnabled", True) is False
        or mobile_account_access_blocked(client)
        or not mobile_subject_matches_token_company(client, store, payload)
        or not mobile_token_version_valid(client, payload, "mobileSessionVersion")
    ):
        return None, jsonify({"error": "Token movil invalido."})
    return client, None


def require_mobile_catalog_access(store: dict) -> tuple[dict | None, object | None]:
    if not app.config.get("REQUIRE_MOBILE_TOKEN"):
        return None, None

    payload = mobile_token_payload()
    if not payload:
        return None, jsonify({"error": "Token movil requerido."})

    if payload.get("type") == "admin":
        user = mobile_find_admin_for_token(store, payload)
        if (
            user
            and user.get("status") == "active"
            and user.get("role") in MOBILE_SALES_ROLES
            and mobile_required_company_id(user)
            and user.get("mobileAccessEnabled", True) is not False
            and not mobile_account_access_blocked(user)
            and mobile_subject_matches_token_company(user, store, payload)
            and mobile_token_version_valid(user, payload, "sessionVersion")
        ):
            return user, None
        return None, jsonify({"error": "Token movil invalido."})

    client = mobile_find_client_for_token(store, payload)
    if (
        client
        and client.get("status") == "active"
        and mobile_required_company_id(client)
        and client.get("mobileAccessEnabled", True) is not False
        and not mobile_account_access_blocked(client)
        and mobile_subject_matches_token_company(client, store, payload)
        and mobile_token_version_valid(client, payload, "mobileSessionVersion")
    ):
        return client, None
    return None, jsonify({"error": "Token movil invalido."})


def mobile_market_payload(store: dict, company_id: str | None = None) -> dict:
    profile = active_market_profile_for_store(store, company_id)
    sales_currency = normalize_currency_code(profile.get("salesCurrency"), "USD")
    local_currency = normalize_currency_code(profile.get("localCurrency"), sales_currency)
    exchange_rate = safe_float(profile.get("exchangeRateBaseToLocal"), 1)

    return {
        "companyId": company_id or "",
        "country": profile.get("code", "CL"),
        "countryName": profile.get("label", "Mercado configurado"),
        "salesCurrency": sales_currency,
        "localCurrency": local_currency,
        "exchangeRateBaseToLocal": exchange_rate,
        "locale": profile.get("locale", "es"),
        "timezone": profile.get("timezone", "UTC"),
    }


def purchase_terms_label(terms: list[int]) -> str:
    normalized = normalized_payment_terms(terms, [0])
    cash_enabled = 0 in normalized
    credit_terms = [term for term in normalized if term > 0]
    parts = []
    if cash_enabled:
        parts.append("Contado")
    if credit_terms:
        suffix = "dia" if len(credit_terms) == 1 and credit_terms[0] == 1 else "dias"
        parts.append(f"{', '.join(str(term) for term in credit_terms)} {suffix}")
    return " / ".join(parts) or "Contado"


def purchase_conditions_payload(
    store: dict,
    company_id: str | None = None,
    *,
    allowed_terms=None,
    default_sale_type: str = "",
) -> dict:
    settings = business_settings(store)
    company = get_company(store, company_id) if company_id else None
    settings_conditions = settings.get("purchaseConditions") if isinstance(settings.get("purchaseConditions"), dict) else {}
    company_conditions = (company or {}).get("purchaseConditions") if isinstance((company or {}).get("purchaseConditions"), dict) else {}
    condition_data = {**settings_conditions, **company_conditions}
    market = mobile_market_payload(store, company_id)
    terms = normalized_payment_terms(
        allowed_terms
        or condition_data.get("allowedPaymentTermsDays")
        or settings.get("defaultPaymentTermsDays"),
        PAYMENT_TERM_OPTIONS,
    )
    sale_type = str(
        default_sale_type
        or condition_data.get("defaultSaleType")
        or settings.get("purchaseDefaultSaleType")
        or "cash"
    )
    if sale_type not in dict(SALE_TYPE_OPTIONS):
        sale_type = "cash"

    rate = safe_float(market.get("exchangeRateBaseToLocal"), 1)
    rate_label = ""
    if market.get("salesCurrency") != market.get("localCurrency"):
        rate_label = f"{rate:g} {market.get('localCurrency')}/{market.get('salesCurrency')}"

    return {
        "title": sanitize_text(
            condition_data.get("title") or settings.get("purchaseConditionsTitle") or "Condiciones de compra",
            max_length=80,
            allow_newlines=False,
        ),
        "currency": market.get("localCurrency", "USD"),
        "salesCurrency": market.get("salesCurrency", "USD"),
        "localCurrency": market.get("localCurrency", "USD"),
        "currencyLabel": f"$ {market.get('localCurrency', 'USD')}",
        "exchangeRate": rate,
        "exchangeRateLabel": rate_label,
        "allowedPaymentTermsDays": terms,
        "paymentTermsLabel": purchase_terms_label(terms),
        "defaultSaleType": sale_type,
        "defaultSaleTypeLabel": sale_type_label(sale_type),
        "scopeLabel": sanitize_text(
            condition_data.get("scopeLabel") or settings.get("purchaseConditionsScope") or "Solo datos de tu empresa",
            max_length=120,
            allow_newlines=False,
        ),
        "note": sanitize_text(
            condition_data.get("note") or settings.get("purchaseConditionsNote") or settings.get("orderTermsText", ""),
            max_length=500,
        ),
    }


def mobile_customer_payload(client: dict, store: dict, access_token: str) -> dict:
    company_id = mobile_required_company_id(client)
    orders = [
        order
        for order in store.get("orders", [])
        if mobile_record_matches_company(order, company_id)
    ]
    movements = [
        movement
        for movement in store.get("credit_movements", [])
        if mobile_record_matches_company(movement, company_id)
    ]
    enriched = enrich_client(client, orders, movements)
    market = mobile_market_payload(store, company_id)
    purchase_conditions = purchase_conditions_payload(
        store,
        company_id,
        allowed_terms=enriched.get("allowedPaymentTermsDays", [0]),
        default_sale_type=enriched.get("defaultSaleType", "cash"),
    )
    return {
        "accessToken": access_token,
        "tokenType": "Bearer",
        "customer": {
            "id": enriched["id"],
            "companyId": company_id,
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
            "country": market["country"],
            "billingCountry": enriched.get("country", ""),
            "marketCountry": market["country"],
            "salesCurrency": market["salesCurrency"],
            "localCurrency": market["localCurrency"],
            "exchangeRateBaseToLocal": market["exchangeRateBaseToLocal"],
            "market": market,
            "purchaseConditions": purchase_conditions,
            "deliveryZone": enriched.get("deliveryZone", ""),
            "contactName": enriched.get("contactName", ""),
            "administrativeContact": enriched.get("administrativeContact", ""),
            "receivingContact": enriched.get("receivingContact", ""),
            "accountRole": "client",
            "roleLabel": "Cliente B2B",
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
            "deletionStatus": enriched.get("deletionStatus", ""),
            "deletionRequestedAt": enriched.get("deletionRequestedAt", ""),
        },
    }


def mobile_admin_payload(user: dict, store: dict, access_token: str) -> dict:
    role = user.get("role", "sales")
    assigned_seller_id = user.get("id", "") if role in MOBILE_SALES_ROLES else ""
    assigned_seller_name = user.get("name", "") if role in MOBILE_SALES_ROLES else ""
    company_id = mobile_required_company_id(user)
    market = mobile_market_payload(store, company_id)
    purchase_conditions = purchase_conditions_payload(store, company_id)
    return {
        "accessToken": access_token,
        "tokenType": "Bearer",
        "customer": {
            "id": user["id"],
            "companyId": company_id,
            "businessName": user.get("name", "Vendedor FVENTAS"),
            "email": user.get("email", ""),
            "clientType": role,
            "accountRole": role,
            "roleLabel": ROLE_LABELS.get(role, "Vendedor"),
            "country": market["country"],
            "marketCountry": market["country"],
            "salesCurrency": market["salesCurrency"],
            "localCurrency": market["localCurrency"],
            "exchangeRateBaseToLocal": market["exchangeRateBaseToLocal"],
            "market": market,
            "purchaseConditions": purchase_conditions,
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
                "id": assigned_seller_id,
                "name": assigned_seller_name,
            },
            "mustChangePassword": bool(user.get("mustChangePassword")),
            "deletionStatus": user.get("deletionStatus", ""),
            "deletionRequestedAt": user.get("deletionRequestedAt", ""),
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
        "service": "fventas-mobile-api",
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
    raw_notes = product.get("compatibilityNotes") or []
    if isinstance(raw_notes, str):
        compatibility_notes = split_lines(raw_notes)
    elif isinstance(raw_notes, list):
        compatibility_notes = [
            sanitize_text(str(note), max_length=500)
            for note in raw_notes
            if sanitize_text(str(note), max_length=500)
        ]
    else:
        compatibility_notes = []
    if not compatibility_notes and product.get("requiresTechnicalValidation"):
        compatibility_notes = ["Validar compatibilidad con soporte FVENTAS"]

    return {
        "id": product["id"],
        "sku": product["sku"],
        "internalCode": product.get("internalCode", ""),
        "name": product["title"],
        "title": product["title"],
        "description": product.get("description", ""),
        "shortDescription": product.get("shortDescription", ""),
        "longDescription": product.get("longDescription", ""),
        "brand": product.get("brand", "FVENTAS"),
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
        "badge": "Revision" if product.get("requiresQuote") else "Comprar",
        "requiresQuote": bool(product.get("requiresQuote")),
        "requiresTechnicalValidation": bool(product.get("requiresTechnicalValidation")),
        "compatibilityNotes": compatibility_notes,
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


def mobile_catalog_company_id(store: dict, profile: dict | None = None) -> str:
    if profile:
        return mobile_required_company_id(profile)
    return current_company_id(store)


def mobile_visible_products(store: dict, company_id: str | None = None) -> list[dict]:
    company_id = company_id or current_company_id(store)
    orders = [
        order
        for order in store.get("orders", [])
        if mobile_record_matches_company(order, company_id)
    ]
    products = [
        item
        for item in store.get("products", [])
        if item.get("status") == "active" and item.get("visibleInApp")
        and mobile_record_matches_company(item, company_id)
    ]
    return enrich_inventory_products(products, orders)


def mobile_product_catalog_price(product: dict | None) -> float:
    product = product or {}
    return safe_float(product.get("b2bPriceUsd"), safe_float(product.get("publicPriceUsd"), 0))


def mobile_product_commercial_blocker(product: dict | None) -> str:
    if not product:
        return "Producto no disponible."
    if product.get("status") != "active":
        return "Producto no disponible."
    if not product.get("visibleInApp"):
        return "Producto no publicado para venta movil."
    if mobile_product_catalog_price(product) <= 0:
        return "Producto sin precio comercial vigente."
    return ""


def mobile_visible_categories(store: dict, company_id: str | None = None) -> list[dict]:
    company_id = company_id or current_company_id(store)
    return [
        enrich_category(item, store)
        for item in store.get("categories", [])
        if item.get("status", "active") == "active"
        and mobile_record_matches_company(item, company_id)
    ]


def mobile_visible_service_technicians(
    store: dict,
    company_id: str | None = None,
) -> list[dict]:
    company_id = company_id or current_company_id(store)
    return [
        technician
        for technician in store.get("service_technicians", [])
        if technician.get("status") == "active"
        and technician.get("visibleInApp")
        and mobile_record_matches_company(technician, company_id)
    ]


def mobile_profile_from_token(store: dict) -> tuple[dict | None, object | None]:
    token_payload = mobile_token_payload()
    if not token_payload:
        return None, jsonify({"error": "Token movil requerido."})

    if token_payload and token_payload.get("type") == "admin":
        user = mobile_find_admin_for_token(store, token_payload)
        if (
            not user
            or user.get("status") != "active"
            or user.get("role") not in MOBILE_SALES_ROLES
            or not mobile_required_company_id(user)
            or user.get("mobileAccessEnabled", True) is False
            or mobile_account_access_blocked(user)
            or not mobile_subject_matches_token_company(user, store, token_payload)
            or not mobile_token_version_valid(user, token_payload, "sessionVersion")
        ):
            return None, jsonify({"error": "Token movil invalido."})
        return mobile_admin_payload(user, store, "")["customer"], None

    client = mobile_find_client_for_token(store, token_payload)
    if (
        not client
        or client.get("status") != "active"
        or not mobile_required_company_id(client)
        or client.get("mobileAccessEnabled", True) is False
        or mobile_account_access_blocked(client)
        or not mobile_subject_matches_token_company(client, store, token_payload)
        or not mobile_token_version_valid(client, token_payload, "mobileSessionVersion")
    ):
        return None, jsonify({"error": "Cliente no encontrado."})
    return mobile_customer_payload(client, store, "")["customer"], None


def mobile_user_company_id(store: dict, user: dict) -> str:
    return mobile_required_company_id(user)


def mobile_record_company_id(record: dict | None) -> str:
    return str((record or {}).get("companyId") or "").strip()


def mobile_record_matches_company(record: dict | None, company_id: str | None) -> bool:
    record_company_id_value = mobile_record_company_id(record)
    expected_company_id = str(company_id or "").strip()
    return bool(record_company_id_value and expected_company_id and hmac.compare_digest(record_company_id_value, expected_company_id))


def mobile_company_records(store: dict, collection: str, user: dict) -> list[dict]:
    company_id = mobile_user_company_id(store, user)
    if not company_id:
        return []
    return [
        record
        for record in store.get(collection, [])
        if mobile_record_matches_company(record, company_id)
    ]


def seller_scope_clients(store: dict, user: dict) -> list[dict]:
    clients = mobile_company_records(store, "clients", user)
    if user.get("role") != "sales":
        return clients
    return [client for client in clients if client.get("assignedSellerId") == user.get("id")]


def seller_scope_orders(store: dict, user: dict) -> list[dict]:
    orders = mobile_company_records(store, "orders", user)
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
    quotes = mobile_company_records(store, "quotes", user)
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
    records = mobile_company_records(store, "crm_records", user)
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
    client = find_by_id(mobile_company_records(store, "clients", user), client_id)
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
        "totalClp": safe_float(enriched.get("totalClp") or enriched.get("totalVes"), 0),
        "totalVes": safe_float(enriched.get("totalVes") or enriched.get("totalClp"), 0),
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
    company_id = mobile_record_company_id(client)
    orders = [
        order
        for order in store.get("orders", [])
        if mobile_record_matches_company(order, company_id)
    ]
    movements = [
        movement
        for movement in store.get("credit_movements", [])
        if mobile_record_matches_company(movement, company_id)
    ]
    enriched = enrich_client(client, orders, movements)
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
        "country": enriched.get("country", "CL"),
        "deliveryZone": enriched.get("deliveryZone", ""),
        "clientType": enriched.get("clientType", "b2b"),
        "clientCategory": enriched.get("clientCategory", "standard"),
        "priceList": enriched.get("priceList", "b2b"),
        "authorizedDiscountPercent": enriched.get("authorizedDiscountPercent", 0),
        "discountRequestedPercent": enriched.get("discountRequestedPercent", 0),
        "discountRequestStatus": enriched.get("discountRequestStatus", "none"),
        "status": enriched.get("status", ""),
        "statusLabel": enriched.get("statusLabel", ""),
        "creditEnabled": bool(enriched.get("creditEnabled")),
        "creditStatus": enriched.get("creditStatus", "without_credit"),
        "creditStatusLabel": enriched.get("creditStatusLabel", ""),
        "creditLimitUsd": enriched.get("creditLimitUsd", 0.0),
        "creditAvailableUsd": enriched.get("creditAvailableUsd", 0.0),
        "creditExposureUsd": enriched.get("creditExposureUsd", 0.0),
        "creditRequestedUsd": enriched.get("creditRequestedUsd", 0.0),
        "creditRequestStatus": enriched.get("creditRequestStatus", "none"),
        "creditRequestStatusLabel": enriched.get("creditRequestStatusLabel", ""),
        "defaultSaleType": enriched.get("defaultSaleType", "cash"),
        "allowedPaymentTermsDays": enriched.get("allowedPaymentTermsDays", [0]),
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
        "createdVia": enriched.get("createdVia", ""),
        "createdViaLabel": enriched.get("createdViaLabel", ""),
        "createdByName": enriched.get("createdByName", ""),
        "updatedVia": enriched.get("updatedVia", ""),
        "updatedViaLabel": enriched.get("updatedViaLabel", ""),
        "updatedByName": enriched.get("updatedByName", ""),
    }


def mobile_seller_order_payload(order: dict, store: dict) -> dict:
    company_id = mobile_record_company_id(order)
    movements = [
        movement
        for movement in store.get("credit_movements", [])
        if mobile_record_matches_company(movement, company_id)
    ]
    enriched = enrich_order(order, movements)
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
    rate = safe_float(product.get("exchangeRateUsdClp"), current_rate())
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
    enriched["publicPriceClp"] = round(price * rate, 2)
    enriched["publicPriceVes"] = enriched["publicPriceClp"]
    enriched["originalPriceUsd"] = original_price
    enriched["discountPercent"] = max(0.0, min(discount, 100.0))
    enriched["hasDiscount"] = enriched["discountPercent"] > 0 or original_price > price
    enriched["exchangeRateUsdClp"] = rate
    enriched["description"] = description
    enriched["shortDescription"] = enriched.get("shortDescription") or description[:140]
    enriched["longDescription"] = enriched.get("longDescription") or description
    enriched["brand"] = enriched.get("brand") or "FVENTAS"
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
    raw_notes = enriched.get("compatibilityNotes") or []
    if isinstance(raw_notes, str):
        enriched["compatibilityNotes"] = split_lines(raw_notes)
    elif isinstance(raw_notes, list):
        enriched["compatibilityNotes"] = [
            sanitize_text(str(note), max_length=500)
            for note in raw_notes
            if sanitize_text(str(note), max_length=500)
        ]
    else:
        enriched["compatibilityNotes"] = []
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


def masked_email(value: str) -> str:
    email = sanitize_text(value, max_length=180, allow_newlines=False)
    if "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    if not local or not domain:
        return ""
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'*' * max(3, len(local) - len(visible))}@{domain}"


def sanitize_url(value: str, *, allow_deeplink: bool = False, allow_local: bool = True) -> str:
    url = sanitize_text(value, max_length=1200, allow_newlines=False)
    if not url:
        return ""
    if allow_local and url.startswith("/static/uploads/"):
        return url
    if allow_deeplink and re.match(r"^fventas://[a-zA-Z0-9/_?=&.%#:-]+$", url):
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
    from core.db import SessionLocal, init_database
    from models import ImportDraft

    init_database()
    with SessionLocal() as db_session:
        db_session.query(ImportDraft).filter(ImportDraft.expires_at < datetime.now(timezone.utc)).delete()
        db_session.commit()


def create_import_draft(module: str, entity_type: str, rows: list[dict], result: dict) -> str:
    from core.db import SessionLocal, init_database
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


def import_draft_is_accessible(draft) -> bool:
    if not draft:
        return False
    if is_platform_scope():
        return True
    result = dict(draft.result or {})
    draft_company_id = str(result.get("companyId") or "").strip()
    if draft_company_id:
        return hmac.compare_digest(draft_company_id, current_company_id())
    return str(draft.created_by_id or "") == str(session.get("admin_user_id", ""))


def load_import_draft(module: str, draft_id: str):
    from core.db import SessionLocal, init_database
    from models import ImportDraft

    init_database()
    purge_expired_import_drafts()
    with SessionLocal() as db_session:
        draft = db_session.get(ImportDraft, draft_id)
        if not draft or draft.module != module or draft.status != "preview" or not import_draft_is_accessible(draft):
            return None
        return {
            "id": draft.id,
            "module": draft.module,
            "entityType": draft.entity_type,
            "rows": list(draft.rows or []),
            "result": dict(draft.result or {}),
        }


def finish_import_draft(module: str, draft_id: str, status: str, result: dict | None = None) -> bool:
    from core.db import SessionLocal, init_database
    from models import ImportDraft

    init_database()
    with SessionLocal() as db_session:
        draft = db_session.get(ImportDraft, draft_id)
        if not draft or draft.module != module or not import_draft_is_accessible(draft):
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
    from core.db import SessionLocal, init_database
    from models import ImportDraft

    init_database()
    with SessionLocal() as db_session:
        draft = db_session.get(ImportDraft, draft_id)
        if not draft or draft.module != module or not import_draft_is_accessible(draft):
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
    from core.db import SessionLocal, init_database
    from models import ImportDraft

    init_database()
    purge_expired_import_drafts()
    with SessionLocal() as db_session:
        drafts = (
            db_session.query(ImportDraft)
            .order_by(ImportDraft.created_at.desc())
            .limit(max(limit * 4, limit))
            .all()
        )
        history = []
        for draft in drafts:
            if not import_draft_is_accessible(draft):
                continue
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
            if len(history) >= limit:
                break
        return history


def find_product_by_sku(store: dict, sku: str, *, company_id: str | None = None) -> dict | None:
    normalized = sku.strip().upper()
    products = store.get("products", [])
    if company_id:
        products = [product for product in products if record_company_id(product, store) == company_id]
    elif not is_platform_scope():
        products = visible_records_for_current_company(store, "products")
    return next((product for product in products if product.get("sku", "").upper() == normalized), None)


def find_category_by_name(store: dict, name: str, *, company_id: str | None = None) -> dict | None:
    normalized = normalize_import_key(name)
    categories = store.get("categories", [])
    if company_id:
        categories = [category for category in categories if record_company_id(category, store) == company_id]
    elif not is_platform_scope():
        categories = visible_records_for_current_company(store, "categories")
    return next(
        (
            category
            for category in categories
            if normalize_import_key(category.get("name", "")) == normalized
            or normalize_import_key(category.get("id", "")) == normalized
        ),
        None,
    )


def category_slug(value: str) -> str:
    return normalize_import_key(value).replace("_", "-")


def find_category_by_slug(store: dict, slug: str, *, company_id: str | None = None) -> dict | None:
    normalized = category_slug(slug)
    if not normalized:
        return None
    categories = store.get("categories", [])
    if company_id:
        categories = [category for category in categories if record_company_id(category, store) == company_id]
    elif not is_platform_scope():
        categories = visible_records_for_current_company(store, "categories")
    return next(
        (
            category
            for category in categories
            if category_slug(category.get("slug", "") or category.get("id", "")) == normalized
            or category_slug(category.get("name", "")) == normalized
        ),
        None,
    )


def find_category_reference(store: dict, value: str) -> dict | None:
    if not value:
        return None
    return find_company_record(store, "categories", value) or find_category_by_slug(store, value) or find_category_by_name(store, value)


def ensure_import_category(store: dict, category_id: str = "", category_name: str = "") -> dict:
    company_id = current_company_id(store)
    category = find_company_record(store, "categories", category_id) if category_id else None
    if category:
        return category
    category = find_category_by_name(store, category_name, company_id=company_id) if category_name else None
    if category:
        return category
    if category_name:
        category = {
            "id": next_id("cat", category_name),
            "companyId": company_id,
            "name": category_name,
            "slug": category_slug(category_name),
            "description": "Categoria creada automaticamente por carga masiva.",
            "imageUrl": "",
            "icon": "bi-tags",
            "sortOrder": len(visible_records_for_current_company(store, "categories")) + 1,
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
        seller = find_company_record(store, "admin_users", seller_id)
        if seller:
            return seller
    seller_email = row_value(row, "sellerEmail", "vendedor_email", "email_vendedor")
    if seller_email:
        return next(
            (
                user
                for user in visible_records_for_current_company(store, "admin_users")
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
                for user in visible_records_for_current_company(store, "admin_users")
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
    company_id = current_company_id(store)
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
            find_company_record(store, "categories", category_id)
            if category_id
            else find_category_by_slug(store, slug, company_id=company_id) or find_category_by_name(store, name, company_id=company_id)
        )
        if any(
            item.get("id") != (category or {}).get("id") and category_slug(item.get("slug", "")) == slug
            for item in visible_records_for_current_company(store, "categories")
        ):
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
            "companyId": record_company_id(category, store) if category else company_id,
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
            for product in visible_records_for_current_company(store, "products"):
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
    company_id = current_company_id(store)
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
            row_value(row, "publicPriceUsd", "precio_publico", "precio_publico_usd", "precio_usd", "precio"),
            float(current.get("publicPriceUsd") or 0),
        )
        original_price = parse_import_float(
            row_value(row, "originalPriceUsd", "precio_anterior", "precio_anterior_usd", "precio_lista_usd"),
            float(current.get("originalPriceUsd") or public_price),
        )
        b2b_price = parse_import_float(
            row_value(row, "b2bPriceUsd", "precio_b2b", "precio_b2b_usd"),
            float(current.get("b2bPriceUsd") or public_price),
        )
        discount = parse_import_float(
            row_value(row, "discountPercent", "descuento", "descuento_porcentaje"),
            float(current.get("discountPercent") or 0),
        )
        if public_price <= 0:
            bulk_error(result, row_number, f"SKU {sku} requiere precio_publico mayor a 0.")
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
            row_value(row, "costReferenceUsd", "costo_referencial", "costo_referencial_usd", "costo_usd"),
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
            "companyId": record_company_id(existing, store) if existing else company_id,
            "sku": sku,
            "internalCode": row_value(row, "internalCode", "codigo_interno", default=current.get("internalCode", "")),
            "title": title,
            "brand": row_value(row, "brand", "marca", default=current.get("brand", "FVENTAS")) or "FVENTAS",
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
            "exchangeRateUsdClp": parse_import_float(
                row_value(row, "exchangeRateUsdClp", "tasa_moneda_local", "tasa_usd_local", "tasa_usd_clp", "tasa"),
                float(current.get("exchangeRateUsdClp") or current_rate()),
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
            "compatibilityNotes": parse_import_list(row_value(row, "compatibilityNotes", "notas_compatibilidad", "compatibilidad")) or list(current.get("compatibilityNotes") or []),
            "requiresQuote": parse_import_bool(row_value(row, "requiresQuote", "requiere_revision", "requiere_cotizacion"), bool(current.get("requiresQuote", False))),
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
            replace_company_record(store, "products", existing, payload)
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
    target_company_id = current_company_id(store)
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
        user_matches = [
            item
            for item in store.get("admin_users", [])
            if item.get("email", "").lower() == email
        ]
        user = next((item for item in user_matches if record_company_id(item, store) == target_company_id), None)
        foreign_user = next((item for item in user_matches if record_company_id(item, store) != target_company_id), None)
        if foreign_user:
            bulk_error(result, row_number, f"{email} ya existe como vendedor de otra empresa.")
            continue
        if user and user.get("role") != "sales":
            bulk_error(result, row_number, f"{email} ya existe con rol administrativo.")
            continue
        client_conflict = next(
            (
                client
                for client in store.get("clients", [])
                if client.get("email", "").lower() == email
                and client.get("status") == "active"
            ),
            None,
        )
        if client_conflict:
            bulk_error(result, row_number, f"{email} ya existe como cliente movil.")
            continue
        password = row_value(row, "password", "contrasena", "clave")
        if password and password_errors(password):
            bulk_error(result, row_number, "la clave no cumple la politica de seguridad.")
            continue
        if not password and not user:
            password = temporary_admin_password()
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
            "companyId": target_company_id,
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
                row_value(row, "salesGoalUsd", "meta_mensual", "meta", "meta_usd", "meta_mensual_usd", "meta_ventas_usd"),
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
            replace_company_record(store, "admin_users", user, payload)
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
    target_company_id = current_company_id(store)
    default_profile = active_market_profile_for_store(store)
    seen_emails: dict[str, int] = {}
    seen_tax_ids: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=2):
        email = row_value(row, "email", "correo").lower()
        business_name = row_value(row, "businessName", "razon_social", "nombre_comercial", "cliente")
        row_country = normalize_market_country(default_profile.get("code", "CL"))
        row_profile = market_profile(row_country)
        raw_tax_id = row_value(row, "taxId", "documento_fiscal", "rif", "rut")
        tax_id = normalize_tax_id_for_market(raw_tax_id, row_profile)
        raw_phone = row_value(row, "phone", "telefono", "whatsapp")
        raw_whatsapp = row_value(row, "whatsapp", "telefono_whatsapp")
        phone = normalize_phone_for_market(raw_phone, row_profile)
        whatsapp = normalize_phone_for_market(raw_whatsapp, row_profile) if raw_whatsapp else phone
        raw_state = row_value(row, "state", "estado_ubicacion", "provincia")
        raw_city = row_value(row, "city", "ciudad")
        normalized_state, normalized_city, location_error = normalize_location_for_market(raw_state, raw_city, row_profile)
        if not email or not business_name:
            bulk_error(result, row_number, "cliente requiere nombre comercial y email.")
            continue
        if not tax_id:
            bulk_error(result, row_number, f"{business_name}: {row_profile.get('taxLabel', 'documento fiscal')} obligatorio. Ejemplo {row_profile.get('taxPlaceholder', 'Documento fiscal')}.")
            continue
        if not phone:
            bulk_error(result, row_number, f"{business_name}: telefono obligatorio. Ejemplo {row_profile.get('phonePlaceholder', '+56 9 1234 5678')}.")
            continue
        if raw_whatsapp and not whatsapp:
            bulk_error(result, row_number, f"{business_name}: WhatsApp no tiene un formato valido para {row_profile.get('label', 'el pais configurado')}.")
            continue
        if location_error:
            bulk_error(result, row_number, f"{business_name}: {location_error}")
            continue
        duplicate_message = duplicate_in_upload(seen_emails, email, row_number)
        if duplicate_message:
            bulk_error(result, row_number, f"{email}: {duplicate_message}")
            continue
        duplicate_tax = duplicate_in_upload(seen_tax_ids, tax_id.lower(), row_number)
        if duplicate_tax:
            bulk_error(result, row_number, f"{tax_id}: {duplicate_tax}")
            continue
        mobile_user_conflict = next(
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
        if mobile_user_conflict:
            bulk_error(result, row_number, f"{email}: ya existe como usuario operativo movil.")
            continue
        client_matches = [
            item
            for item in store.get("clients", [])
            if item.get("email", "").lower() == email
        ]
        client_by_email = next((item for item in client_matches if record_company_id(item, store) == target_company_id), None)
        foreign_client_by_email = next((item for item in client_matches if record_company_id(item, store) != target_company_id), None)
        if foreign_client_by_email:
            bulk_error(result, row_number, f"{email}: ya existe como cliente movil de otra empresa.")
            continue
        client_by_tax = next(
            (
                item
                for item in store.get("clients", [])
                if record_company_id(item, store) == target_company_id
                and normalize_market_country(item.get("country") or row_profile.get("code", "CL")) == row_profile.get("code", "CL")
                and normalize_tax_id_for_market(item.get("taxId", ""), row_profile).lower() == tax_id.lower()
            ),
            None,
        )
        if client_by_email and client_by_tax and client_by_email.get("id") != client_by_tax.get("id"):
            bulk_error(result, row_number, f"{business_name}: email y {row_profile.get('taxLabel', 'documento fiscal')} pertenecen a clientes distintos.")
            continue
        client = client_by_email or client_by_tax
        password = row_value(row, "password", "contrasena", "clave")
        if password and password_errors(password):
            bulk_error(result, row_number, "la clave no cumple la politica de seguridad.")
            continue
        if not password and not client:
            password = temporary_mobile_client_password()
        seller = find_seller_for_import(store, row)
        credit_requested = parse_import_float(row_value(row, "creditRequestedUsd", "credito_solicitado", "credito_solicitado_usd", "solicitud_credito_usd"), float((client or {}).get("creditRequestedUsd") or 0))
        credit_limit = parse_import_float(row_value(row, "creditLimitUsd", "credito_limite", "cupo", "credito_limite_usd", "cupo_usd", "linea_credito_usd"), float((client or {}).get("creditLimitUsd") or 0))
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
        client_type = row_value(
            row,
            "clientType",
            "tipo_cliente",
            default=normalize_option_value((client or {}).get("clientType"), CLIENT_TYPE_OPTIONS, "b2b"),
        ) or "b2b"
        client_category = row_value(
            row,
            "clientCategory",
            "categoria_comercial",
            default=normalize_option_value((client or {}).get("clientCategory"), CLIENT_CATEGORY_OPTIONS, "standard"),
        ) or "standard"
        price_list = row_value(
            row,
            "priceList",
            "lista_precios",
            default=normalize_option_value((client or {}).get("priceList"), PRICE_LIST_OPTIONS, "b2b"),
        ) or "b2b"
        status = row_value(row, "status", "estado", default=(client or {}).get("status", "active")) or "active"
        default_sale_type = row_value(
            row,
            "defaultSaleType",
            "tipo_venta_default",
            default=normalize_option_value((client or {}).get("defaultSaleType"), SALE_TYPE_OPTIONS, "cash"),
        ) or "cash"
        collection_status = row_value(
            row,
            "collectionStatus",
            "estado_cobranza",
            default=normalize_option_value((client or {}).get("collectionStatus"), COLLECTION_STATUS_OPTIONS, "without_debt"),
        ) or "without_debt"
        credit_risk = row_value(
            row,
            "creditRiskLevel",
            "riesgo_credito",
            default=normalize_option_value((client or {}).get("creditRiskLevel"), CREDIT_RISK_OPTIONS, "low"),
        ) or "low"
        authorized_discount = parse_import_float(
            row_value(row, "authorizedDiscountPercent", "descuento_autorizado"),
            float((client or {}).get("authorizedDiscountPercent") or 0),
        )
        credit_score = parse_import_int(row_value(row, "creditScore", "score_credito"), int((client or {}).get("creditScore") or 0))
        if client_type not in dict(CLIENT_TYPE_OPTIONS):
            bulk_error(result, row_number, f"{business_name}: tipo_cliente no valido.")
            continue
        if client_category not in dict(CLIENT_CATEGORY_OPTIONS):
            bulk_error(result, row_number, f"{business_name}: categoria_comercial no valida.")
            continue
        if price_list not in dict(PRICE_LIST_OPTIONS):
            bulk_error(result, row_number, f"{business_name}: lista_precios no valida.")
            continue
        if status not in dict(CLIENT_STATUS_OPTIONS):
            bulk_error(result, row_number, f"{business_name}: estado no valido.")
            continue
        if default_sale_type not in dict(SALE_TYPE_OPTIONS):
            bulk_error(result, row_number, f"{business_name}: tipo_venta_default no valido.")
            continue
        if collection_status not in dict(COLLECTION_STATUS_OPTIONS):
            bulk_error(result, row_number, f"{business_name}: estado_cobranza no valido.")
            continue
        if credit_risk not in dict(CREDIT_RISK_OPTIONS):
            bulk_error(result, row_number, f"{business_name}: riesgo_credito no valido.")
            continue
        if authorized_discount < 0 or authorized_discount > 100:
            bulk_error(result, row_number, f"{business_name}: descuento_autorizado debe estar entre 0 y 100%.")
            continue
        if credit_score < 0 or credit_score > 100:
            bulk_error(result, row_number, f"{business_name}: score_credito debe estar entre 0 y 100.")
            continue
        payload = {
            "companyId": target_company_id,
            "legalName": row_value(row, "legalName", "razon_social", default=(client or {}).get("legalName", business_name)) or business_name,
            "commercialName": row_value(row, "commercialName", "nombre_comercial", default=(client or {}).get("commercialName", business_name)) or business_name,
            "businessName": business_name,
            "taxId": tax_id or (client or {}).get("taxId", ""),
            "contactName": row_value(row, "contactName", "contacto", "responsable", default=(client or {}).get("contactName", "")),
            "administrativeContact": row_value(row, "administrativeContact", "contacto_administrativo", "admin_contacto", default=(client or {}).get("administrativeContact", "")),
            "receivingContact": row_value(row, "receivingContact", "contacto_recepcion", "recepcion_contacto", default=(client or {}).get("receivingContact", "")),
            "phone": phone,
            "whatsapp": whatsapp,
            "email": email,
            "clientType": client_type,
            "clientCategory": client_category,
            "priceList": price_list,
            "authorizedDiscountPercent": authorized_discount,
            "status": status,
            "address": row_value(row, "address", "direccion", default=(client or {}).get("address", "")),
            "fiscalAddress": row_value(row, "fiscalAddress", "direccion_fiscal", default=(client or {}).get("fiscalAddress", "")),
            "shippingAddress": row_value(row, "shippingAddress", "direccion_despacho", "direccion_entrega", default=(client or {}).get("shippingAddress", "")),
            "country": row_profile.get("code", "CL"),
            "state": normalized_state,
            "city": normalized_city,
            "deliveryZone": row_value(row, "deliveryZone", "zona", default=(client or {}).get("deliveryZone", "")),
            "assignedSellerId": (seller or {}).get("id", (client or {}).get("assignedSellerId", "")),
            "assignedSellerName": (seller or {}).get("name", (client or {}).get("assignedSellerName", "")),
            "defaultSaleType": default_sale_type,
            "allowedPaymentTermsDays": sorted(set(terms)),
            "collectionStatus": collection_status,
            "creditRiskLevel": credit_risk,
            "creditScore": credit_score,
            "creditManagerNote": row_value(row, "creditManagerNote", "observacion_gerencia", "nota_credito", default=(client or {}).get("creditManagerNote", "")),
            "creditReviewedBy": (client or {}).get("creditReviewedBy", ""),
            "creditReviewedAt": (client or {}).get("creditReviewedAt", ""),
            "creditRequestStatus": credit_status,
            "creditRequestedUsd": credit_requested,
            "creditEnabled": credit_enabled and credit_status == "approved",
            "creditLimitUsd": credit_limit if credit_enabled and credit_status == "approved" else float((client or {}).get("creditLimitUsd") or 0),
            "creditUsedUsd": parse_import_float(row_value(row, "creditUsedUsd", "deuda_manual", "credito_usado", "credito_usado_usd", "deuda_manual_usd"), float((client or {}).get("creditUsedUsd") or 0)),
            "paymentTermsDays": payment_term if credit_status == "approved" else int((client or {}).get("paymentTermsDays") or 0),
            "notes": row_value(row, "notes", "notas", default=(client or {}).get("notes", "")),
            "updatedVia": "import",
            "updatedById": session.get("admin_user_id", ""),
            "updatedByName": session.get("admin_name", "FVENTAS Admin"),
            "updatedByRole": current_admin_role(),
            "updatedAt": utc_now(),
        }
        payload["whatsapp"] = payload["whatsapp"] or payload["phone"]
        payload["fiscalAddress"] = payload["fiscalAddress"] or payload["address"]
        payload["shippingAddress"] = payload["shippingAddress"] or payload["address"]
        payload["address"] = payload["address"] or payload["shippingAddress"] or payload["fiscalAddress"]
        if not payload.get("contactName"):
            bulk_warning(result, row_number, f"{business_name} no tiene contacto principal.")
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
            payload["createdVia"] = client.get("createdVia", "import")
            payload["createdById"] = client.get("createdById", "")
            payload["createdByName"] = client.get("createdByName") or client.get("assignedSellerName") or "Carga masiva"
            payload["createdByRole"] = client.get("createdByRole") or ("sales" if payload["createdVia"] == "seller_mobile" else "admin")
            payload["createdAt"] = client.get("createdAt", utc_now())
            payload["passwordHash"] = generate_password_hash(password) if password else client.get("passwordHash", "")
            payload["mustChangePassword"] = True if password else bool(client.get("mustChangePassword"))
            replace_company_record(store, "clients", client, payload)
            result["updated"] += 1
            bulk_row(result, "updated", row_number, f"{business_name} - {email}")
        else:
            payload["id"] = next_id("client", email)
            payload["createdVia"] = "import"
            payload["createdById"] = session.get("admin_user_id", "")
            payload["createdByName"] = session.get("admin_name", "Carga masiva")
            payload["createdByRole"] = current_admin_role()
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
    company_id = current_company_id(store)
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
        announcement = find_company_record(store, "announcements", announcement_id) if announcement_id else next(
            (
                item
                for item in visible_records_for_current_company(store, "announcements")
                if normalize_import_key(item.get("title", "")) == normalize_import_key(title)
            ),
            None,
        )
        raw_cta_url = row_value(row, "ctaUrl", "accion", "url_accion", default=(announcement or {}).get("ctaUrl", ""))
        raw_image_url = row_value(row, "imageUrl", "imagen", "imagen_url", default=(announcement or {}).get("imageUrl", ""))
        payload = {
            "companyId": record_company_id(announcement, store) if announcement else company_id,
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
            replace_company_record(store, "announcements", announcement, payload)
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
    company_id = current_company_id(store)
    for row_number, row in enumerate(rows, start=2):
        title = row_value(row, "title", "titulo", "recurso", default="Activo FVENTAS")
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
        product = find_company_record(store, "products", product_id) if product_id else find_product_by_sku(
            store,
            row_value(row, "sku", "producto_sku", "sku_producto"),
            company_id=company_id,
        )
        asset_type = normalize_import_key(row_value(row, "assetType", "tipo", default="image"))
        asset_type = "pdf" if asset_type in {"pdf", "ficha", "ficha_pdf"} else "image"
        duplicate = next(
            (
                item
                for item in visible_records_for_current_company(store, "media_assets")
                if item.get("url") == asset_url and item.get("productId", "") == (product or {}).get("id", product_id)
            ),
            None,
        )
        if duplicate:
            duplicate.update({
                "title": title,
                "assetType": asset_type,
                "companyId": record_company_id(duplicate, store) or company_id,
                "createdAt": duplicate.get("createdAt", utc_now()),
            })
            result["updated"] += 1
            bulk_row(result, "updated", row_number, f"{title} - {asset_type}")
        else:
            asset = {
                "id": next_id("asset", title),
                "companyId": company_id,
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
        return can_access_client_record(find_company_record(store, "clients", subject_id), store)
    if scope == "order":
        return can_access_order_record(find_company_record(store, "orders", subject_id), store)
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
                for item in visible_records_for_current_company(store, "clients")
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
        product = find_company_record(store, "products", reference)
        if not product and reference:
            normalized_reference = normalize_import_key(reference)
            product = next(
                (
                    item
                    for item in visible_records_for_current_company(store, "products")
                    if normalize_import_key(item.get("sku", "")) == normalized_reference
                ),
                None,
            )
        if not product and reference:
            normalized = normalize_import_key(reference)
            product = next((item for item in visible_records_for_current_company(store, "products") if normalize_import_key(item.get("title", "")) == normalized), None)
        if product:
            return product.get("id", ""), f"{product.get('sku', '')} - {product.get('title', 'Producto')}".strip(" -")

    if scope == "order":
        normalized = normalize_import_key(reference)
        order = next(
            (
                item
                for item in visible_records_for_current_company(store, "orders")
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
                for client in visible_records_for_current_company(store, "clients")
            ],
        },
        {
            "label": "Productos",
            "items": [
                {"value": f"product:{product.get('id', '')}", "label": f"{product.get('sku', '')} - {product.get('title', 'Producto')}"}
                for product in visible_records_for_current_company(store, "products")
            ],
        },
        {
            "label": "Ordenes",
            "items": [
                {"value": f"order:{order.get('id', '')}", "label": f"{order.get('orderId') or order.get('id', 'Orden')} - {order.get('customer', {}).get('name', '')}"}
                for order in visible_records_for_current_company(store, "orders")
            ],
        },
    ]


def parse_document_subject_ref(value: str) -> tuple[str, str]:
    if ":" not in (value or ""):
        return "admin", ""
    scope, subject_id = value.split(":", 1)
    return normalize_document_scope(scope), subject_id


def document_assets(store: dict) -> list[dict]:
    products = {product.get("id"): product for product in visible_records_for_current_company(store, "products")}
    clients = {client.get("id"): client for client in visible_records_for_current_company(store, "clients")}
    orders = {order.get("id"): order for order in visible_records_for_current_company(store, "orders")}
    now = datetime.now(timezone.utc)
    assets = []
    for asset in reversed(store.get("media_assets", [])):
        if not document_is_asset(asset) or asset.get("status") == "deleted":
            continue
        if not can_access_company_record(asset, store):
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
    company_id = current_company_id(store)
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
                for item in visible_records_for_current_company(store, "media_assets")
                if document_is_asset(item)
                and item.get("subjectType") == scope
                and item.get("subjectId", "") == subject_id
                and item.get("documentType") == document_type
                and item.get("url") == document_url
            ),
            None,
        )
        payload = {
            "companyId": record_company_id(existing, store) if existing else company_id,
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
    company_id = current_company_id(store)
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
        technician = find_company_record(store, "service_technicians", technician_id) if technician_id else next(
            (
                item
                for item in visible_records_for_current_company(store, "service_technicians")
                if normalize_import_key(item.get("name", "")) == normalize_import_key(name)
            ),
            None,
        )
        payload = {
            "companyId": record_company_id(technician, store) if technician else company_id,
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
            replace_company_record(store, "service_technicians", technician, payload)
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
    import_company_id = current_company_id(store)

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
        result["companyId"] = import_company_id
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
            result["companyId"] = import_company_id
            result["preview"] = True
            result["draftId"] = create_import_draft(module, entity_type, rows, result)
            result["confirmEndpoint"] = request.endpoint
            result["discardEndpoint"] = request.endpoint
            result["expiresInMinutes"] = max(1, IMPORT_DRAFT_TTL_SECONDS // 60)
            remember_bulk_result(module, result)
            return redirect(url_for(redirect_endpoint))

        result = importer(store, rows)
        result["module"] = module
        result["companyId"] = import_company_id
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
        "companyId": session.get("company_id", ""),
    }


def normalize_order_items(
    store: dict,
    raw_items: list[dict],
    *,
    company_id: str = "",
    strict_catalog: bool = False,
    trusted_prices: bool = False,
) -> tuple[list[dict], float, bool, str]:
    items: list[dict] = []
    total_usd = 0.0
    requires_operator_review = False
    invalid_refs: list[str] = []
    if company_id:
        product_pool = [
            product
            for product in store.get("products", [])
            if record_company_id(product, store) == company_id
        ]
    else:
        product_pool = visible_records_for_current_company(store, "products")
    for raw_item in raw_items:
        product_id = str(raw_item.get("productId") or "").strip()
        sku = str(raw_item.get("sku") or "").strip()
        product = find_by_id(product_pool, product_id) if product_id else None
        if not product and sku:
            product = next((item for item in product_pool if item.get("sku") == sku), None)
        quantity = int(raw_item.get("quantity") or 0)
        if quantity <= 0:
            continue
        if strict_catalog and not product:
            invalid_refs.append(sku or product_id or str(raw_item.get("title") or "linea sin SKU"))
            continue
        if strict_catalog and product:
            blocker = mobile_product_commercial_blocker(product)
            if blocker:
                invalid_refs.append(sku or product_id or product.get("sku") or product.get("title") or "linea sin SKU")
                continue
        if product:
            product_id = product.get("id", product_id)
            sku = product.get("sku", sku)
            title = product.get("title") or product.get("name") or raw_item.get("title") or sku
            catalog_price = mobile_product_catalog_price(product)
            if strict_catalog and trusted_prices and "unitPriceUsd" in raw_item:
                unit_price = max(0.0, safe_float(raw_item.get("unitPriceUsd"), catalog_price))
            elif strict_catalog:
                unit_price = catalog_price
            else:
                unit_price = safe_float(raw_item.get("unitPriceUsd"), catalog_price)
            image_url = raw_item.get("imageUrl") or product.get("imageUrl", "")
            requires_quote = bool(product.get("requiresQuote"))
            requires_validation = bool(product.get("requiresTechnicalValidation"))
        else:
            title = str(raw_item.get("title") or sku or product_id or "Producto FVENTAS")
            unit_price = safe_float(raw_item.get("unitPriceUsd"), 0)
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
    error = ""
    if invalid_refs:
        refs = ", ".join(invalid_refs[:3])
        error = f"Producto no disponible para esta empresa: {refs}."
    return items, round(total_usd, 2), requires_operator_review, error


def build_commercial_order(
    store: dict,
    payload: dict,
    *,
    actor: dict | None = None,
    default_channel: str = "mobile",
    trusted_pricing: bool = False,
) -> tuple[dict | None, str]:
    actor = actor or {"id": "", "name": "Sistema", "role": "system"}
    preview = payload.get("preview") or {}
    customer_payload = payload.get("customer") or {}
    customer_id = str(payload.get("customerId") or customer_payload.get("id") or "").strip()
    actor_company_id = actor.get("companyId") or ""
    if actor.get("role") in MOBILE_SALES_ROLES:
        seller_user = seller_record_for(store, actor.get("id", ""), actor_company_id)
        actor_company_id = actor_company_id or record_company_id(seller_user, store) or current_company_id(store)
    elif actor.get("role") != "client":
        actor_company_id = actor_company_id or current_company_id(store)
    client_candidates = [
        item
        for item in store.get("clients", [])
        if item.get("id") == customer_id
    ]
    if actor_company_id:
        client_candidates = [
            item
            for item in client_candidates
            if record_company_id(item, store) == actor_company_id
        ]
    client = client_candidates[0] if client_candidates else None
    if not client:
        return None, "Cliente no encontrado."
    client_company_id = record_company_id(client, store)
    if not client_company_id:
        return None, "Cliente sin empresa asignada."
    if actor_company_id and actor_company_id != client_company_id:
        return None, "El cliente no pertenece a tu empresa."
    if actor.get("role") == "client" and actor.get("id") != client.get("id"):
        return None, "No puedes crear ordenes para otro cliente."
    if client.get("mustChangePassword") and actor.get("role") == "client":
        return None, "Debes cambiar la contrasena temporal antes de crear ordenes."

    items, calculated_total_usd, requires_operator_review, items_error = normalize_order_items(
        store,
        payload.get("items") or [],
        company_id=client_company_id,
        strict_catalog=True,
        trusted_prices=trusted_pricing,
    )
    if items_error:
        return None, items_error
    if not items:
        return None, "La orden no tiene productos validos."

    total_usd = calculated_total_usd
    gross_usd = calculated_total_usd
    discount_usd = 0.0
    if trusted_pricing:
        preview_total = safe_float(preview.get("totalUsd"), calculated_total_usd)
        if abs(preview_total - calculated_total_usd) > 0.01:
            return None, "El total de la cotizacion no coincide con sus lineas."
        preview_gross = safe_float(preview.get("grossUsd") or preview.get("subtotalUsd"), calculated_total_usd)
        gross_usd = max(calculated_total_usd, round(preview_gross, 2))
        discount_usd = round(max(0.0, gross_usd - calculated_total_usd), 2)
    market = mobile_market_payload(store, client_company_id)
    exchange_rate = safe_float(market.get("exchangeRateBaseToLocal"), current_rate())
    total_clp = round(total_usd * exchange_rate, 2)
    company_orders = [
        order_item
        for order_item in store.get("orders", [])
        if record_company_id(order_item, store) == client_company_id
    ]
    movements = [
        movement
        for movement in store.get("credit_movements", [])
        if record_company_id(movement, store) == client_company_id
    ]
    credit_before = credit_available(client, company_orders, movements)

    requested_sale_type = (
        payload.get("saleType")
        or payload.get("paymentMethod")
        or client.get("defaultSaleType")
        or "cash"
    )
    sale_type = requested_sale_type if requested_sale_type in dict(SALE_TYPE_OPTIONS) else "cash"
    raw_payment_term_days = payload.get("paymentTermDays")
    if raw_payment_term_days in (None, ""):
        payment_term_days = int(client.get("paymentTermsDays") or 0)
    else:
        payment_term_days = int(raw_payment_term_days or 0)
    condition_error, sale_type, payment_term_days = validate_client_purchase_conditions(client, sale_type, payment_term_days)
    if condition_error:
        return None, condition_error
    due_date = add_days_iso(utc_now(), payment_term_days) if payment_term_days > 0 else ""

    seller_id = client.get("assignedSellerId", "")
    seller_name = client.get("assignedSellerName", "") or seller_name_for(store, seller_id, client_company_id)
    if (
        default_channel == "seller_mobile"
        and not seller_id
        and actor.get("role") in MOBILE_SALES_ROLES
    ):
        seller_id = actor.get("id", "")
        seller_name = actor.get("name", "Vendedor FVENTAS")
    commission_rate = seller_commission_rate(store, seller_id, client_company_id) if seller_id else 0.0
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
        "companyId": client_company_id,
        "orderId": order_id,
        "customerId": client["id"],
        "customer": {
            "id": client["id"],
            "name": client.get("businessName", "Cliente FVENTAS"),
            "businessName": client.get("businessName", "Cliente FVENTAS"),
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
        "totalClp": total_clp,
        "totalVes": total_clp,
        "exchangeRateUsdClp": exchange_rate,
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


AUDIT_ENTITY_COLLECTIONS = {
    "admin_user": "admin_users",
    "seller": "admin_users",
    "client": "clients",
    "order": "orders",
    "quote": "quotes",
    "crm_record": "crm_records",
    "product": "products",
    "category": "categories",
    "document": "media_assets",
    "media_asset": "media_assets",
    "announcement": "announcements",
    "service_technician": "service_technicians",
    "notification": "notifications",
    "account_deletion_request": "account_deletion_requests",
}


def audit_company_id_for_entity(store: dict, entity_type: str, entity_id: str) -> str:
    if not entity_id:
        return ""
    if entity_type == "company" and get_company(store, entity_id):
        return entity_id
    if entity_type == "subscription":
        subscriptions = [
            subscription
            for subscription in store.get("subscriptions", [])
            if subscription.get("id") == entity_id
        ]
        session_company_id = current_company_id(store)
        session_subscription = next(
            (
                subscription
                for subscription in subscriptions
                if record_company_id(subscription, store) == session_company_id
            ),
            None,
        )
        if session_subscription:
            return session_company_id
        subscription_company_ids = [
            record_company_id(subscription, store)
            for subscription in subscriptions
            if record_company_id(subscription, store)
        ]
        if len(set(subscription_company_ids)) == 1:
            return subscription_company_ids[0]
        if get_company(store, entity_id):
            return entity_id
    collection = AUDIT_ENTITY_COLLECTIONS.get(entity_type)
    if not collection:
        return ""
    company_ids: list[str] = []
    for record in store.get(collection, []):
        if record.get("id") != entity_id:
            continue
        raw_company_id = str(record.get("companyId") or "").strip()
        if raw_company_id:
            company_id = raw_company_id
        elif collection == "account_deletion_requests":
            continue
        else:
            company_id = record_company_id(record, store)
        if company_id and company_id not in company_ids:
            company_ids.append(company_id)
    if len(company_ids) == 1:
        return company_ids[0]
    session_company_id = session.get("company_id", "")
    if session_company_id and session_company_id in company_ids:
        return session_company_id
    return ""


def record_audit_event(
    store: dict,
    action: str,
    entity_type: str,
    entity_id: str = "",
    detail: str = "",
    metadata: dict | None = None,
    actor: dict | None = None,
    criticality: str | None = None,
) -> None:
    actor_payload = actor or {}
    actor_name = actor_payload.get("name") or session.get("admin_name", "Sistema")
    metadata_payload = metadata or {}
    metadata_after = metadata_payload.get("after") if isinstance(metadata_payload.get("after"), dict) else {}
    metadata_before = metadata_payload.get("before") if isinstance(metadata_payload.get("before"), dict) else {}
    entity_company_id = audit_company_id_for_entity(store, entity_type, entity_id)
    company_id = (
        actor_payload.get("companyId")
        or metadata_payload.get("companyId")
        or metadata_after.get("companyId")
        or metadata_before.get("companyId")
        or entity_company_id
        or session.get("company_id", "")
        or current_company_id(store)
    )
    audit_criticality = (criticality or str(metadata_payload.get("criticality") or "medium")).strip().lower()
    if audit_criticality not in {"low", "medium", "high", "critical"}:
        audit_criticality = "medium"
    metadata_payload = {**metadata_payload, "criticality": audit_criticality}
    event = {
        "id": next_id("audit", f"{action}-{entity_type}-{entity_id or actor_name}"),
        "companyId": company_id,
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
        "criticality": audit_criticality,
        "metadata": audit_snapshot(metadata_payload),
    }
    store.setdefault("audit_events", []).append(event)
    store["audit_events"] = store["audit_events"][-1000:]


AUDIT_REDACTED_KEYS = {
    "password",
    "passwordhash",
    "currentpassword",
    "newpassword",
    "accesstoken",
    "secret",
    "token",
    "apikey",
    "api_key",
    "authorization",
}


def audit_key_is_sensitive(key: str) -> bool:
    normalized = str(key or "").lower()
    return (
        normalized in AUDIT_REDACTED_KEYS
        or "password" in normalized
        or normalized.endswith("secret")
        or normalized.endswith("token")
    )


def audit_snapshot(value):
    if isinstance(value, dict):
        snapshot = {}
        for key, item in value.items():
            if audit_key_is_sensitive(key):
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
    criticality: str | None = None,
    metadata: dict | None = None,
) -> None:
    metadata_payload = {
        "changedFields": changed_fields(before, after),
        "before": audit_snapshot(before or {}),
        "after": audit_snapshot(after or {}),
    }
    if metadata:
        metadata_payload.update(audit_snapshot(metadata))
    record_audit_event(
        store,
        action,
        entity_type,
        entity_id,
        detail,
        metadata=metadata_payload,
        actor=actor,
        criticality=criticality,
    )


def record_create_event(
    store: dict,
    entity_type: str,
    entity_id: str,
    detail: str,
    after: dict | None,
    actor: dict | None = None,
    criticality: str | None = None,
) -> None:
    record_change_event(store, "create", entity_type, entity_id, detail, None, after, actor=actor, criticality=criticality)


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
UNRESOLVED_NOTIFICATION_COMPANY_ID = "__unresolved_notification_company__"
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
    company_id = infer_notification_company_id(
        store,
        recipient_type=recipient_type,
        recipient_id=recipient_id,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=metadata,
    )
    if company_id:
        metadata.setdefault("companyId", company_id)
    if dedupe_key:
        metadata["dedupeKey"] = dedupe_key
        for existing in store.setdefault("notifications", []):
            existing_payload = existing.get("payload") or existing.get("metadata") or {}
            if (
                existing.get("status", "unread") == "unread"
                and existing_payload.get("dedupeKey") == dedupe_key
                and record_company_id(existing, store) == company_id
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
        "title": title.strip() or "Notificacion FVENTAS",
        "body": body.strip(),
        "notificationType": notification_type,
        "type": notification_type,
        "channel": channel,
        "priority": priority if priority in NOTIFICATION_PRIORITY_LABELS else "normal",
        "status": "unread",
        "recipientType": recipient_type,
        "recipientId": recipient_id,
        "recipientRole": recipient_role,
        "companyId": company_id,
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


def infer_notification_company_id(
    store: dict,
    *,
    recipient_type: str = "",
    recipient_id: str = "",
    entity_type: str = "",
    entity_id: str = "",
    metadata: dict | None = None,
) -> str:
    metadata = metadata or {}
    for key in ("companyId", "company_id"):
        if metadata.get(key):
            return str(metadata[key])
    for nested_key in ("after", "before", "record", "entity"):
        nested = metadata.get(nested_key)
        if isinstance(nested, dict):
            nested_company = nested.get("companyId") or nested.get("company_id")
            if nested_company:
                return str(nested_company)
    entity_collection_by_type = {
        "order": "orders",
        "client": "clients",
        "seller": "admin_users",
        "admin_user": "admin_users",
        "product": "products",
        "category": "categories",
        "quote": "quotes",
        "crm_record": "crm_records",
        "document": "media_assets",
        "media_asset": "media_assets",
        "service_technician": "service_technicians",
        "notification": "notifications",
        "account_deletion_request": "account_deletion_requests",
    }
    collection = entity_collection_by_type.get(entity_type)
    if collection and entity_id:
        entity_company_ids = notification_company_ids_for_record(store, collection, entity_id)
    else:
        entity_company_ids = []
    if recipient_type in {"seller", "admin_user", "user"} and recipient_id:
        recipient_company_ids = notification_company_ids_for_record(store, "admin_users", recipient_id)
    elif recipient_type == "client" and recipient_id:
        recipient_company_ids = notification_company_ids_for_record(store, "clients", recipient_id)
    else:
        recipient_company_ids = []

    session_company_id = ""
    if session.get("admin_authenticated"):
        session_company_id = current_company_id(store)
        if session_company_id:
            scoped_candidates = set(entity_company_ids or recipient_company_ids)
            if not scoped_candidates or session_company_id in scoped_candidates:
                return session_company_id

    if entity_company_ids and recipient_company_ids:
        intersection = [company_id for company_id in entity_company_ids if company_id in recipient_company_ids]
        if len(intersection) == 1:
            return intersection[0]
    if len(entity_company_ids) == 1:
        return entity_company_ids[0]
    if len(recipient_company_ids) == 1:
        return recipient_company_ids[0]
    if entity_company_ids or recipient_company_ids:
        return UNRESOLVED_NOTIFICATION_COMPANY_ID
    if session.get("admin_authenticated"):
        return current_company_id(store)
    return default_company_id(store)


def notification_company_ids_for_record(store: dict, collection: str, record_id: str) -> list[str]:
    company_ids: list[str] = []
    for record in store.get(collection, []):
        if record.get("id") != record_id:
            continue
        raw_company_id = str(record.get("companyId") or "").strip()
        if raw_company_id:
            company_id = raw_company_id
        elif collection == "account_deletion_requests":
            continue
        else:
            company_id = record_company_id(record, store)
        if company_id and company_id not in company_ids:
            company_ids.append(company_id)
    return company_ids


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


def notification_visible_to_current_admin(store: dict, notification: dict) -> bool:
    if notification.get("status") == "archived" or notification_is_expired(notification):
        return False
    if not can_access_company_record(notification, store):
        return False
    role = current_admin_role()
    if role in {"platform_admin", "super_admin"}:
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
        if notification_visible_to_current_admin(store, notification)
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


def mobile_subject_record_for_company(
    store: dict,
    subject_type: str,
    subject_id: str,
    company_id: str = "",
) -> dict | None:
    collection = "admin_users" if subject_type == "seller" else "clients" if subject_type == "client" else ""
    if not collection:
        return None
    candidates = [
        item
        for item in store.get(collection, [])
        if item.get("id") == subject_id
    ]
    if company_id:
        candidates = [
            item
            for item in candidates
            if record_company_id(item, store) == company_id
        ]
    return candidates[0] if candidates else None


def mobile_notifications_for_subject(
    store: dict,
    subject_type: str,
    subject_id: str,
    role: str = "",
    company_id: str = "",
) -> list[dict]:
    visible = []
    subject_company_id = company_id
    if subject_type == "seller":
        subject_company_id = subject_company_id or record_company_id(
            mobile_subject_record_for_company(store, subject_type, subject_id, company_id),
            store,
        )
    elif subject_type == "client":
        subject_company_id = subject_company_id or record_company_id(
            mobile_subject_record_for_company(store, subject_type, subject_id, company_id),
            store,
        )
    for notification in store.get("notifications", []):
        if notification.get("status") == "archived" or notification_is_expired(notification):
            continue
        if subject_company_id and record_company_id(notification, store) != subject_company_id:
            continue
        recipient_type = notification.get("recipientType", "")
        recipient_id = notification.get("recipientId", "")
        recipient_role = notification.get("recipientRole", "")
        if recipient_type == subject_type and recipient_id == subject_id:
            visible.append(notification)
        elif recipient_type == "role" and role and recipient_role == role:
            visible.append(notification)
    return sorted(visible, key=lambda item: item.get("createdAt", ""), reverse=True)


def mobile_notification_subject(store: dict) -> tuple[str, str, str, str, object | None]:
    payload = mobile_token_payload()
    if payload.get("type") == "admin":
        user, auth_error = require_mobile_sales_user(store)
        if auth_error:
            return "", "", "", "", auth_error
        return "seller", user["id"], user.get("role", ""), mobile_required_company_id(user), None
    client, auth_error = require_mobile_client(store)
    if auth_error or not client:
        return "", "", "", "", auth_error or jsonify({"error": "Token movil requerido."})
    return "client", client["id"], "client", mobile_required_company_id(client), None


def generate_mobile_subject_notifications(
    store: dict,
    subject_type: str,
    subject_id: str,
    role: str = "",
    company_id: str = "",
) -> bool:
    before_count = len(store.setdefault("notifications", []))
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    subject_user = mobile_subject_record_for_company(store, subject_type, subject_id, company_id) if subject_type == "seller" else None
    subject_client = mobile_subject_record_for_company(store, subject_type, subject_id, company_id) if subject_type == "client" else None
    subject_company_id = record_company_id(subject_user or subject_client, store)
    orders = [
        order for order in store.get("orders", [])
        if record_company_id(order, store) == subject_company_id
    ]
    movements = [
        movement for movement in store.get("credit_movements", [])
        if record_company_id(movement, store) == subject_company_id
    ]

    if subject_type == "seller":
        user = subject_user
        if not user:
            return False
        seller_snapshot = enrich_seller(store, user)
        if safe_float(seller_snapshot.get("salesGoalUsd"), 0) > 0 and safe_float(seller_snapshot.get("goalProgressPercent"), 0) < 100:
            notify_seller(
                store,
                subject_id,
                "Meta pendiente",
                f"Avance {seller_snapshot.get('goalProgressPercent', 0)}% de meta mensual {money_sales(seller_snapshot.get('salesGoalUsd', 0), store, subject_company_id)}.",
                notification_type="goal_pending",
                priority="low",
                module="sellers",
                entity_type="seller",
                entity_id=subject_id,
                deep_link="fventas://seller/home",
                metadata={
                    "companyId": subject_company_id,
                    "month": current_month,
                    "goalProgressPercent": seller_snapshot.get("goalProgressPercent", 0),
                },
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
                    f"{client_name} mantiene {money_sales(overdue, store, subject_company_id)} vencidos.",
                    notification_type="client_debt",
                    priority="high",
                    module="clients",
                    entity_type="client",
                    entity_id=client_id,
                    deep_link=f"fventas://seller/clients/{client_id}",
                    metadata={"companyId": subject_company_id, "clientId": client_id, "overdueBalanceUsd": overdue},
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
                        deep_link=f"fventas://seller/clients/{client_id}",
                        metadata={"companyId": subject_company_id, "clientId": client_id, "inactiveDays": inactive_days},
                        dedupe_key=f"seller-client-inactive-{subject_id}-{client_id}-{current_month}",
                    )

    if subject_type == "client":
        client = subject_client
        if client:
            enriched = enrich_client(client, orders, movements)
            overdue = safe_float(enriched.get("overdueBalanceUsd"), 0)
            if overdue > 0:
                notify_client(
                    store,
                    subject_id,
                    "Saldo vencido",
                    f"Tienes {money_sales(overdue, store, subject_company_id)} vencidos. Contacta a tu vendedor FVENTAS.",
                    notification_type="overdue_balance",
                    priority="high",
                    module="credit",
                    entity_type="client",
                    entity_id=subject_id,
                    deep_link="fventas://credit",
                    metadata={"companyId": subject_company_id, "clientId": subject_id, "overdueBalanceUsd": overdue},
                    dedupe_key=f"client-overdue-{subject_id}-{current_month}",
                )

    return len(store.get("notifications", [])) != before_count


def notify_order_created(store: dict, order: dict) -> None:
    order_id = order.get("orderId") or order.get("id", "")
    company_id = record_company_id(order, store)
    customer = order.get("customer") or {}
    customer_name = customer.get("name") or customer.get("businessName") or "Cliente FVENTAS"
    total = money_sales(order.get("totalUsd") or order.get("netUsd") or 0, store, company_id)
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
        deep_link=f"fventas://orders/{order_id}",
        metadata={"companyId": company_id, "orderId": order_id, "saleType": order.get("saleType", ""), "status": status},
        dedupe_key=f"admin-order-created-{order_id}",
    )
    notify_client(
        store,
        order.get("customerId", ""),
        "Orden recibida",
        f"FVENTAS recibio tu orden {order_id} por {total}.",
        notification_type="order_received",
        priority="normal",
        module="orders",
        entity_type="order",
        entity_id=order_id,
        deep_link=f"fventas://orders/{order_id}",
        metadata={"companyId": company_id, "orderId": order_id, "status": status},
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
        deep_link=f"fventas://seller/orders/{order_id}",
        metadata={"companyId": company_id, "orderId": order_id, "customerId": order.get("customerId", "")},
        dedupe_key=f"seller-order-created-{order_id}",
    )


def notify_order_status_change(store: dict, order: dict, before_status: str) -> None:
    after_status = order.get("status", "")
    if not after_status or before_status == after_status:
        return
    order_id = order.get("orderId") or order.get("id", "")
    company_id = record_company_id(order, store)
    total = money_sales(order.get("totalUsd") or 0, store, company_id)
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
        deep_link=f"fventas://orders/{order_id}",
        metadata={"companyId": company_id, "orderId": order_id, "beforeStatus": before_status, "status": after_status},
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
        deep_link=f"fventas://seller/orders/{order_id}",
        metadata={"companyId": company_id, "orderId": order_id, "beforeStatus": before_status, "status": after_status},
        dedupe_key=f"seller-order-status-{order_id}-{after_status}",
    )


def notify_credit_decision(store: dict, client: dict, decision: str) -> None:
    client_id = client.get("id", "")
    company_id = record_company_id(client, store)
    approved = decision in {"approved", "reactivate", "adjust"} and safe_float(client.get("creditLimitUsd"), 0) > 0
    rejected = decision in {"rejected", "suspended", "blocked_debt", "blocked_limit"}
    if not approved and not rejected:
        return
    notification_type = "credit_approved" if approved else "credit_rejected"
    title = "Credito aprobado" if approved else "Credito no aprobado"
    body = (
        f"Linea disponible por {money_sales(client.get('creditLimitUsd', 0), store, company_id)} a {client.get('paymentTermsDays', 0)} dias."
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
        deep_link="fventas://credit",
        metadata={"companyId": company_id, "clientId": client_id, "decision": decision},
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
        deep_link=f"fventas://seller/clients/{client_id}",
        metadata={"companyId": company_id, "clientId": client_id, "decision": decision},
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
            metadata={"companyId": company_id, "clientId": client_id, "decision": decision},
            dedupe_key=f"admin-client-blocked-{client_id}-{client.get('creditReviewedAt', '')}",
        )


def notify_credit_requested(store: dict, client: dict) -> None:
    client_id = client.get("id", "")
    company_id = record_company_id(client, store)
    amount = safe_float(client.get("creditRequestedUsd"), 0)
    if amount <= 0:
        return
    title = "Credito solicitado"
    body = f"{client.get('businessName') or client.get('commercialName') or 'Cliente'} solicito {money_sales(amount, store, company_id)}."
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
        metadata={"companyId": company_id, "clientId": client_id, "requestedUsd": amount},
        dedupe_key=f"admin-credit-requested-{client_id}-{client.get('updatedAt', client.get('createdAt', ''))}",
    )


def notify_payment_registered(store: dict, order: dict, movement: dict) -> None:
    order_id = order.get("orderId") or order.get("id", "")
    company_id = record_company_id(order, store)
    amount = money_sales(movement.get("amountUsd") or 0, store, company_id)
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
        metadata={"companyId": company_id, "orderId": order_id, "movementId": movement.get("id", "")},
        dedupe_key=f"admin-payment-{movement.get('id', '')}",
    )
    notify_client(
        store,
        order.get("customerId", ""),
        "Abono recibido",
        f"FVENTAS registro {amount} en tu orden {order_id}.",
        notification_type="payment_registered",
        priority="normal",
        module="orders",
        entity_type="order",
        entity_id=order_id,
        deep_link=f"fventas://orders/{order_id}",
        metadata={"companyId": company_id, "orderId": order_id, "movementId": movement.get("id", "")},
        dedupe_key=f"client-payment-{movement.get('id', '')}",
    )


def notify_commission_status(store: dict, order: dict, status: str) -> None:
    if status not in {"commission_approved", "commission_paid"}:
        return
    order_id = order.get("orderId") or order.get("id", "")
    company_id = record_company_id(order, store)
    notification_type = "commission_paid" if status == "commission_paid" else "commission_approved"
    title = "Comision pagada" if status == "commission_paid" else "Comision aprobada"
    notify_seller(
        store,
        order.get("sellerId", ""),
        title,
        f"{commission_status_label(status)} por {money_sales(order.get('commissionUsd', 0), store, company_id)} en orden {order_id}.",
        notification_type=notification_type,
        priority="normal",
        module="commissions",
        entity_type="order",
        entity_id=order_id,
        deep_link=f"fventas://seller/commissions/{order_id}",
        metadata={"companyId": company_id, "orderId": order_id, "commissionStatus": status},
        dedupe_key=f"seller-commission-{order_id}-{status}",
    )


def notify_stock_state(store: dict, product: dict) -> None:
    company_id = record_company_id(product, store)
    enriched = enrich_inventory_product(
        product,
        records_for_company_id(store, "orders", company_id),
        records_for_company_id(store, "stock_movements", company_id),
    )
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
        metadata={
            "companyId": company_id,
            "productId": enriched.get("id", ""),
            "sku": enriched.get("sku", ""),
            "stockStatus": status,
        },
        dedupe_key=f"stock-{enriched.get('id', '')}-{status}",
    )


def notify_quote_accepted(store: dict, quote: dict, order: dict | None = None) -> None:
    quote_id = quote.get("id", "")
    order_id = (order or {}).get("orderId", "")
    company_id = record_company_id(order or quote, store)
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
        metadata={"companyId": company_id, "quoteId": quote_id, "orderId": order_id},
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


def order_release_block_reason(
    order: dict,
    movements: list[dict] | None = None,
    store: dict | None = None,
) -> str:
    balance = order_balance_usd(order, movements)
    if balance > ORDER_PAYMENT_TOLERANCE_USD:
        company_id = record_company_id(order, store) if store else str(order.get("companyId") or "")
        return f"Entrega bloqueada: saldo pendiente {money_sales(balance, store, company_id)}. El cliente debe cancelar antes de recibir producto."
    return ""


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


def validate_client_purchase_conditions(client: dict | None, sale_type: str, payment_term_days: int) -> tuple[str, str, int]:
    normalized_sale_type = sale_type if sale_type in dict(SALE_TYPE_OPTIONS) else "cash"
    normalized_term_days = safe_int(payment_term_days, 0)
    blocker = client_sales_blocker(client, normalized_sale_type)
    if blocker:
        return blocker, normalized_sale_type, normalized_term_days
    if not client:
        return "Cliente no encontrado.", normalized_sale_type, normalized_term_days
    if normalized_sale_type == "cash":
        return "", normalized_sale_type, 0
    if normalized_sale_type == "credit_line" and not client.get("creditEnabled"):
        return "El cliente no tiene linea de credito aprobada."
    if normalized_sale_type == "credit_line" and normalized_term_days == 0:
        normalized_term_days = safe_int(client.get("paymentTermsDays"), 0)
    allowed_terms = [
        safe_int(term, -1)
        for term in client.get("allowedPaymentTermsDays", [0])
        if str(term).isdigit()
    ] or [0]
    if normalized_sale_type in {"term_credit", "credit_line"} and normalized_term_days not in allowed_terms:
        return "El plazo solicitado no esta autorizado para este cliente.", normalized_sale_type, normalized_term_days
    return "", normalized_sale_type, normalized_term_days


def enrich_client(
    client: dict,
    orders: list[dict] | None = None,
    movements: list[dict] | None = None,
) -> dict:
    enriched = dict(client)
    origin = (
        enriched.get("createdVia")
        or enriched.get("source")
        or ("seller_mobile" if enriched.get("onboardingStatus") == "pending_review" and enriched.get("assignedSellerId") else "")
        or "admin"
    )
    updated_origin = enriched.get("updatedVia") or origin
    enriched["createdVia"] = origin
    enriched["createdViaLabel"] = client_origin_label(origin)
    enriched["updatedVia"] = updated_origin
    enriched["updatedViaLabel"] = client_origin_label(updated_origin)
    enriched["createdById"] = enriched.get("createdById", "")
    enriched["createdByName"] = enriched.get("createdByName") or (
        enriched.get("assignedSellerName") if origin == "seller_mobile" else "FVENTAS Admin"
    )
    enriched["createdByRole"] = enriched.get("createdByRole") or ("sales" if origin == "seller_mobile" else "admin")
    enriched["updatedById"] = enriched.get("updatedById") or enriched["createdById"]
    enriched["updatedByName"] = enriched.get("updatedByName") or enriched["createdByName"]
    enriched["updatedByRole"] = enriched.get("updatedByRole") or enriched["createdByRole"]
    enriched["legalName"] = enriched.get("legalName") or enriched.get("businessName", "")
    enriched["commercialName"] = enriched.get("commercialName") or enriched.get("businessName", "")
    enriched["whatsapp"] = enriched.get("whatsapp") or enriched.get("phone", "")
    enriched["fiscalAddress"] = enriched.get("fiscalAddress") or enriched.get("address", "")
    enriched["shippingAddress"] = enriched.get("shippingAddress") or enriched.get("address", "")
    enriched["address"] = enriched.get("address") or enriched["shippingAddress"] or enriched["fiscalAddress"]
    enriched["country"] = enriched.get("country") or "CL"
    enriched["administrativeContact"] = enriched.get("administrativeContact", "")
    enriched["receivingContact"] = enriched.get("receivingContact", "")
    enriched["clientType"] = enriched.get("clientType") or "b2b"
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
    enriched["creditEnabled"] = bool(enriched.get("creditEnabled"))
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


def enrich_clients(
    clients: list[dict],
    orders: list[dict] | None = None,
    movements: list[dict] | None = None,
) -> list[dict]:
    orders_by_client: dict[str, list[dict]] = {}
    for order in orders or []:
        orders_by_client.setdefault(order.get("customerId", ""), []).append(order)

    movements_by_client: dict[str, list[dict]] = {}
    unassigned_movements: list[dict] = []
    for movement in movements or []:
        client_id = movement.get("clientId", "")
        if client_id:
            movements_by_client.setdefault(client_id, []).append(movement)
        else:
            unassigned_movements.append(movement)

    enriched_clients = []
    for client in clients:
        client_id = client.get("id", "")
        client_movements = movements_by_client.get(client_id, [])
        if unassigned_movements:
            client_movements = [*client_movements, *unassigned_movements]
        enriched_clients.append(enrich_client(client, orders_by_client.get(client_id, []), client_movements))
    return enriched_clients


def dashboard_client_summaries(clients: list[dict], orders: list[dict]) -> list[dict]:
    credit_orders_by_client: dict[str, float] = {}
    for order in orders:
        client_id = order.get("customerId", "")
        if (
            client_id
            and order.get("saleType") == "credit_line"
            and order.get("status") in ORDER_CREDIT_RESERVING_STATUSES
        ):
            credit_orders_by_client[client_id] = credit_orders_by_client.get(client_id, 0.0) + float(order.get("balanceUsd") or 0)

    summaries: list[dict] = []
    for client in clients:
        summary = dict(client)
        summary["businessName"] = summary.get("businessName") or summary.get("commercialName") or summary.get("legalName") or "Cliente FVENTAS"
        summary["status"] = summary.get("status") or "inactive"
        summary["creditEnabled"] = bool(summary.get("creditEnabled"))
        summary["creditLimitUsd"] = float(summary.get("creditLimitUsd") or 0)
        summary["creditUsedUsd"] = float(summary.get("creditUsedUsd") or 0)
        summary["creditOrdersUsd"] = round(credit_orders_by_client.get(summary.get("id", ""), 0.0), 2)
        summary["creditExposureUsd"] = round(summary["creditUsedUsd"] + summary["creditOrdersUsd"], 2)
        summary["creditAvailableUsd"] = (
            max(0.0, round(summary["creditLimitUsd"] - summary["creditExposureUsd"], 2))
            if summary["creditEnabled"]
            else 0.0
        )
        if summary.get("creditRequestStatus") not in dict(CREDIT_REQUEST_STATUS_OPTIONS):
            summary["creditRequestStatus"] = "none"
        summaries.append(summary)
    return summaries


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
    enriched["customerName"] = customer.get("name") or customer.get("businessName") or "Cliente FVENTAS"
    enriched["itemsCount"] = len(enriched.get("items") or [])
    enriched["statusHistory"] = sorted(enriched.get("statusHistory") or [], key=lambda item: item.get("createdAt", ""), reverse=True)
    return enriched


def enrich_orders(orders: list[dict], movements: list[dict] | None = None) -> list[dict]:
    movements_by_order: dict[str, list[dict]] = {}
    for movement in movements or []:
        order_id = movement.get("orderId", "")
        if order_id:
            movements_by_order.setdefault(order_id, []).append(movement)

    enriched_orders = []
    for order in orders:
        order_movements: list[dict] = []
        seen_movements: set[str] = set()
        for key in (order.get("orderId", ""), order.get("id", "")):
            for movement in movements_by_order.get(key, []):
                movement_id = movement.get("id", "")
                if movement_id and movement_id in seen_movements:
                    continue
                if movement_id:
                    seen_movements.add(movement_id)
                order_movements.append(movement)
        enriched_orders.append(enrich_order(order, order_movements))
    return enriched_orders


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


def latest_stock_movements_by_product(movements: list[dict] | None) -> dict[str, dict]:
    latest_by_product: dict[str, dict] = {}
    for movement in movements or []:
        product_id = movement.get("productId", "")
        if not product_id:
            continue
        current = latest_by_product.get(product_id)
        if not current or movement.get("createdAt", "") > current.get("createdAt", ""):
            latest_by_product[product_id] = movement
    return latest_by_product


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
    company_id = record_company_id(order, store) if order else record_company_id(product, store)
    movement = {
        "id": next_id("mov", f"{product.get('sku', '')}-{normalized_type}"),
        "companyId": company_id,
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


def enrich_inventory_product(
    product: dict,
    orders: list[dict],
    movements: list[dict] | None = None,
    reserved_by_product: dict[str, int] | None = None,
    latest_movement_by_product: dict[str, dict] | None = None,
) -> dict:
    if reserved_by_product is None:
        reserved_by_product = stock_reserved_quantities(orders)
    enriched = enrich_product(product)
    physical_stock = int(enriched.get("stock") or 0)
    committed = int(reserved_by_product.get(enriched["id"], 0))
    available = max(0, physical_stock - committed)
    minimum_stock = max(0, safe_int(enriched.get("minimumStock"), 0))
    maximum_stock = max(0, safe_int(enriched.get("maximumStock"), 0))
    replenishment_qty = max(0, safe_int(enriched.get("replenishmentQty"), 0))
    if latest_movement_by_product is not None:
        last_movement = latest_movement_by_product.get(enriched["id"], {})
    else:
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


def enrich_inventory_products(
    products: list[dict],
    orders: list[dict],
    movements: list[dict] | None = None,
) -> list[dict]:
    reserved_by_product = stock_reserved_quantities(orders)
    latest_movement_by_product = latest_stock_movements_by_product(movements)
    return [
        enrich_inventory_product(
            product,
            orders,
            movements,
            reserved_by_product=reserved_by_product,
            latest_movement_by_product=latest_movement_by_product,
        )
        for product in products
    ]


def available_stock_for_product(product: dict, orders: list[dict]) -> int:
    enriched = enrich_inventory_product(product, orders)
    return int(enriched.get("availableStock") or 0)


def records_for_company_id(store: dict, collection: str, company_id: str) -> list[dict]:
    return [
        record
        for record in store.get(collection, [])
        if record_company_id(record, store) == company_id
    ]


def inventory_company_id_for_order(store: dict, order: dict) -> str:
    return record_company_id(order, store)


def inventory_products_for_order(store: dict, order: dict) -> dict[str, dict]:
    company_id = inventory_company_id_for_order(store, order)
    return {
        product["id"]: product
        for product in records_for_company_id(store, "products", company_id)
    }


def inventory_orders_for_order(store: dict, order: dict) -> list[dict]:
    return records_for_company_id(store, "orders", inventory_company_id_for_order(store, order))


def inventory_movements_for_order(store: dict, order: dict) -> list[dict]:
    return records_for_company_id(store, "credit_movements", inventory_company_id_for_order(store, order))


def order_has_sufficient_stock(store: dict, order: dict) -> bool:
    products = inventory_products_for_order(store, order)
    scoped_orders = inventory_orders_for_order(store, order)
    for product_id, quantity in order_item_quantities(order).items():
        product = products.get(product_id)
        if not product or available_stock_for_product(product, scoped_orders) < quantity:
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

    products = inventory_products_for_order(store, order)
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

    products = inventory_products_for_order(store, order)
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
    payment_block_reason = order_release_block_reason(order, inventory_movements_for_order(store, order), store)
    if payment_block_reason:
        order["dispatchStatus"] = "payment_hold"
        order["stockStatus"] = "payment_hold"
        order["paymentHoldReason"] = payment_block_reason
        order["currentOwner"] = "Cobranza"
        order["updatedAt"] = utc_now()
        return False
    if order.get("inventoryStatus") not in {"reserved", "review", "", None} and not order_has_sufficient_stock(store, order):
        order["inventoryStatus"] = "review"
        order["stockStatus"] = "insufficient_stock"
        return False
    if order.get("inventoryStatus") != "reserved" and not reserve_stock_for_order(store, order):
        return False

    products = inventory_products_for_order(store, order)
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


def save_upload(
    file_storage,
    folder: str = "library",
    *,
    public: bool = True,
    allowed_extensions: set[str] | frozenset[str] | None = None,
) -> str:
    if not file_storage or not file_storage.filename:
        return ""

    try:
        s3_acl = app.config.get("S3_ACL", "") if public else ""
        return save_uploaded_file(
            file_storage=file_storage,
            folder=folder,
            upload_folder=Path(app.config["UPLOAD_FOLDER"]),
            storage_backend=app.config.get("STORAGE_BACKEND", "local"),
            public_base_url=app.config.get("STORAGE_PUBLIC_BASE_URL", ""),
            s3_bucket=app.config.get("S3_BUCKET", ""),
            s3_region=app.config.get("S3_REGION", "us-east-1"),
            s3_endpoint_url=app.config.get("S3_ENDPOINT_URL", ""),
            s3_prefix=app.config.get("S3_PREFIX", "fventas"),
            s3_acl=s3_acl,
            max_bytes=int(app.config.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)),
            allowed_extensions=allowed_extensions,
        )
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def product_payload(store: dict, existing: dict | None = None) -> dict:
    target_company_id = record_company_id(existing, store) if existing else current_company_id(store)
    category_id = request.form.get("categoryId", "machinery-garden")
    categories = product_category_options(store) or [{"id": "uncategorized", "name": "Sin categoria"}]
    category = find_by_id(categories, category_id) or categories[0]
    sku = sanitize_text(request.form.get("sku", ""), max_length=80, allow_newlines=False).upper()
    title = sanitize_text(request.form.get("title", ""), max_length=180, allow_newlines=False)
    primary_image = sanitize_url(request.form.get("imageUrl", ""))
    image_urls = sanitize_url_list(split_lines(request.form.get("imageUrls", "")))
    pdf_urls = sanitize_url_list(split_lines(request.form.get("pdfUrls", "")))
    uploaded_image = save_upload(request.files.get("imageFile"), "products", allowed_extensions=IMAGE_UPLOAD_EXTENSIONS)
    uploaded_pdf = save_upload(request.files.get("pdfFile"), "products", allowed_extensions=PDF_UPLOAD_EXTENSIONS)
    uploaded_gallery = [
        save_upload(file_storage, "products", allowed_extensions=IMAGE_UPLOAD_EXTENSIONS)
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
    exchange_rate = safe_float(
        request.form.get("exchangeRateUsdClp") or request.form.get("exchangeRateUsdVes"),
        current_rate(),
    )
    payload = {
        "companyId": target_company_id,
        "sku": sku,
        "internalCode": sanitize_text(request.form.get("internalCode", ""), max_length=80, allow_newlines=False).upper(),
        "title": title,
        "brand": sanitize_text(request.form.get("brand", "FVENTAS"), max_length=120, allow_newlines=False) or "FVENTAS",
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
        "exchangeRateUsdClp": exchange_rate,
        "exchangeRateUsdVes": exchange_rate,
        "stock": safe_int(request.form.get("stock"), 0),
        "minimumStock": safe_int(request.form.get("minimumStock"), 0),
        "maximumStock": safe_int(request.form.get("maximumStock"), 0),
        "reserved": safe_int(request.form.get("reserved") or (existing or {}).get("reserved"), 0),
        "status": normalize_option_value(request.form.get("status"), CLIENT_STATUS_OPTIONS, "active"),
        "imageUrl": primary_image,
        "imageUrls": image_urls,
        "pdfUrls": pdf_urls,
        "variants": split_lines(request.form.get("variants", "")),
        "specifications": parse_specs(request.form.get("specifications", "")),
        "relatedSkus": split_lines(request.form.get("relatedSkus", "")),
        "compatibilityNotes": split_lines(request.form.get("compatibilityNotes", "")),
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
    exchange_rate = request.form.get("exchangeRateUsdClp") or request.form.get("exchangeRateUsdVes") or current_rate()
    return {
        "sku": sanitize_text(request.form.get("sku", ""), max_length=80, allow_newlines=False).upper(),
        "internalCode": sanitize_text(request.form.get("internalCode", ""), max_length=80, allow_newlines=False).upper(),
        "title": sanitize_text(request.form.get("title", ""), max_length=180, allow_newlines=False),
        "brand": sanitize_text(request.form.get("brand", "FVENTAS"), max_length=120, allow_newlines=False),
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
        "exchangeRateUsdClp": exchange_rate,
        "exchangeRateUsdVes": exchange_rate,
        "stock": request.form.get("stock", 0),
        "minimumStock": request.form.get("minimumStock", 0),
        "maximumStock": request.form.get("maximumStock", 0),
        "imageUrl": sanitize_url(request.form.get("imageUrl", "")),
        "imageUrls": sanitize_url_list(split_lines(request.form.get("imageUrls", ""))),
        "pdfUrls": sanitize_url_list(split_lines(request.form.get("pdfUrls", ""))),
        "variants": split_lines(request.form.get("variants", "")),
        "specifications": parse_specs(request.form.get("specifications", "")),
        "relatedSkus": split_lines(request.form.get("relatedSkus", "")),
        "compatibilityNotes": split_lines(request.form.get("compatibilityNotes", "")),
        "requiresQuote": request.form.get("requiresQuote") == "on",
        "requiresTechnicalValidation": request.form.get("requiresTechnicalValidation") == "on",
        "visibleInApp": "on" in request.form.getlist("visibleInApp"),
        "featured": request.form.get("featured") == "on",
        "onSale": request.form.get("onSale") == "on",
    }


def product_form_error(store: dict, existing: dict | None = None) -> str:
    target_company_id = record_company_id(existing, store) if existing else current_company_id(store)
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
        and record_company_id(product, store) == target_company_id
        for product in store["products"]
    )
    if duplicated:
        return f"El SKU {sku} ya existe en el catalogo."
    if status not in {key for key, _label in PRODUCT_STATUS_OPTIONS}:
        return "El estado del producto no es valido."
    if product_type not in {key for key, _label in PRODUCT_TYPE_OPTIONS}:
        return "El tipo de producto no es valido."
    if public_price <= 0:
        return "El precio publico debe ser mayor a 0."
    if original_price < 0:
        return "El precio anterior no puede ser negativo."
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
    category_company_id = record_company_id(category, store)
    products = [
        product
        for product in store.get("products", [])
        if product.get("categoryId") == category.get("id")
        and product.get("status") != "deleted"
        and record_company_id(product, store) == category_company_id
    ]
    children = [
        item
        for item in store.get("categories", [])
        if item.get("parentId") == category.get("id")
        and item.get("status") != "deleted"
        and record_company_id(item, store) == category_company_id
    ]
    parent = find_company_record(store, "categories", category.get("parentId", ""))
    if parent and record_company_id(parent, store) != category_company_id:
        parent = None
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
    target_company_id = record_company_id(existing, store) if existing else current_company_id(store)
    name = sanitize_text(request.form.get("name", ""), max_length=140, allow_newlines=False)
    uploaded_image = save_upload(request.files.get("imageFile"), "categories", allowed_extensions=IMAGE_UPLOAD_EXTENSIONS)
    image_url = uploaded_image or sanitize_url(request.form.get("imageUrl", "")) or (existing or {}).get("imageUrl", "")
    status = request.form.get("status", "active")
    visible_in_app = request.form.get("visibleInApp") == "on"
    if status != "active":
        visible_in_app = False
    parent_id = request.form.get("parentId", "").strip()
    if existing and parent_id == existing.get("id"):
        parent_id = ""
    parent = find_company_record(store, "categories", parent_id) if parent_id else None
    now = utc_now()
    payload = {
        "companyId": target_company_id,
        "name": name,
        "slug": category_slug(request.form.get("slug", "").strip() or name),
        "description": sanitize_text(request.form.get("description", ""), max_length=500),
        "imageUrl": image_url,
        "icon": sanitize_text(request.form.get("icon", "bi-tags"), max_length=80, allow_newlines=False) or "bi-tags",
        "sortOrder": max(0, safe_int(request.form.get("sortOrder"), 0)),
        "status": status,
        "visibleInApp": visible_in_app,
        "parentId": parent_id if parent else "",
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


def category_descendant_ids(store: dict, category_id: str, company_id: str | None = None) -> set[str]:
    if company_id is None:
        category = find_company_record(store, "categories", category_id)
        company_id = record_company_id(category, store) if category else current_company_id(store)
    descendants: set[str] = set()
    pending = [category_id]
    while pending:
        parent_id = pending.pop()
        for category in store.get("categories", []):
            if (
                category.get("parentId") == parent_id
                and category.get("id") not in descendants
                and record_company_id(category, store) == company_id
            ):
                descendants.add(category.get("id", ""))
                pending.append(category.get("id", ""))
    return descendants


def product_count_for_categories(store: dict, category_ids: set[str], company_id: str | None = None) -> int:
    if company_id is None:
        company_id = current_company_id(store)
    return sum(
        1
        for product in store.get("products", [])
        if product.get("categoryId") in category_ids
        and record_company_id(product, store) == company_id
    )


def persist_category_action(
    store: dict,
    changed_categories: list[dict],
    audit_events_start: int,
    fallback_detail: str,
) -> bool:
    try:
        save_store(store)
        return True
    except Exception:
        app.logger.exception("No se pudo sincronizar el store completo para categorias: %s", fallback_detail)
        if use_sql_backend() and changed_categories:
            try:
                from sql_store import sync_category_records

                sync_category_records(changed_categories, store.get("audit_events", [])[audit_events_start:])
                push_admin_toast(
                    "El cambio se aplico en categorias, pero se detecto una inconsistencia pendiente en otra tabla.",
                    "warning",
                    "Categoria actualizada",
                )
                return True
            except Exception:
                app.logger.exception("No se pudo aplicar fallback puntual de categorias: %s", fallback_detail)
        push_admin_toast(
            "No se pudo guardar la categoria. Revisa los registros relacionados o intenta nuevamente.",
            "danger",
            "Accion no aplicada",
        )
        return False


def persist_product_seed_action(
    store: dict,
    changed_categories: list[dict],
    changed_products: list[dict],
    audit_events_start: int,
    fallback_detail: str,
) -> bool:
    try:
        save_store(store)
        return True
    except Exception:
        app.logger.exception("No se pudo sincronizar el store completo para productos base: %s", fallback_detail)
        if use_sql_backend() and (changed_categories or changed_products):
            try:
                from sql_store import sync_product_seed_records

                sync_product_seed_records(
                    changed_categories,
                    changed_products,
                    store.get("audit_events", [])[audit_events_start:],
                )
                push_admin_toast(
                    "Los productos base se aplicaron, pero se detecto una inconsistencia pendiente en otra tabla.",
                    "warning",
                    "Seed aplicado parcialmente",
                )
                return True
            except Exception:
                app.logger.exception("No se pudo aplicar fallback puntual de productos base: %s", fallback_detail)
        push_admin_toast(
            "No se pudieron crear los productos base FVENTAS. Revisa los registros relacionados o intenta nuevamente.",
            "danger",
            "Productos no aplicados",
        )
        return False


def persist_seller_action(
    store: dict,
    changed_users: list[dict],
    audit_events_start: int,
    fallback_detail: str,
    deleted_user_ids: list[str] | None = None,
    changed_clients: list[dict] | None = None,
    changed_orders: list[dict] | None = None,
) -> bool:
    try:
        save_store(store)
        return True
    except Exception:
        app.logger.exception("No se pudo sincronizar el store completo para vendedores: %s", fallback_detail)
        if use_sql_backend() and (changed_users or deleted_user_ids):
            try:
                from sql_store import sync_admin_user_records

                sync_admin_user_records(
                    changed_users,
                    store.get("audit_events", [])[audit_events_start:],
                    deleted_user_ids or [],
                    changed_clients or [],
                    changed_orders or [],
                )
                push_admin_toast(
                    "El cambio se aplico en vendedores, pero se detecto una inconsistencia pendiente en otra tabla.",
                    "warning",
                    "Vendedor actualizado",
                )
                return True
            except Exception:
                app.logger.exception("No se pudo aplicar fallback puntual de vendedores: %s", fallback_detail)
        push_admin_toast(
            "No se pudo guardar el vendedor. Revisa los registros relacionados o intenta nuevamente.",
            "danger",
            "Accion no aplicada",
        )
        return False


def persist_client_action(
    store: dict,
    changed_clients: list[dict],
    audit_events_start: int,
    fallback_detail: str,
    notifications_start: int | None = None,
    deleted_client_ids: list[str] | None = None,
    changed_orders: list[dict] | None = None,
) -> bool:
    try:
        save_store(store)
        return True
    except Exception:
        app.logger.exception("No se pudo sincronizar el store completo para clientes: %s", fallback_detail)
        if use_sql_backend() and (changed_clients or deleted_client_ids or changed_orders):
            try:
                from sql_store import sync_admin_user_records, sync_client_records

                sync_client_records(
                    changed_clients,
                    store.get("audit_events", [])[audit_events_start:],
                    store.get("notifications", [])[notifications_start:] if notifications_start is not None else [],
                    deleted_client_ids or [],
                )
                if changed_orders:
                    sync_admin_user_records([], orders=changed_orders)
                push_admin_toast(
                    "El cambio se aplico en clientes, pero se detecto una inconsistencia pendiente en otra tabla.",
                    "warning",
                    "Cliente actualizado",
                )
                return True
            except Exception:
                app.logger.exception("No se pudo aplicar fallback puntual de clientes: %s", fallback_detail)
        push_admin_toast(
            "No se pudo guardar el cliente. Revisa los datos o intenta nuevamente.",
            "danger",
            "Accion no aplicada",
        )
        return False


def category_form_error(store: dict, existing: dict | None = None) -> str:
    target_company_id = record_company_id(existing, store) if existing else current_company_id(store)
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
        and record_company_id(category, store) == target_company_id
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
        if existing and parent_id in category_descendant_ids(store, existing.get("id", ""), target_company_id):
            return "La categoria padre seleccionada generaria una jerarquia circular."
        if not find_company_record(store, "categories", parent_id):
            return "Selecciona una categoria padre valida."
    return ""


def create_fventas_starter_categories(store: dict) -> dict:
    created: list[dict] = []
    existing: list[dict] = []
    root_ids: dict[str, str] = {}
    company_id = current_company_id(store)

    def create_or_get(entry: dict, parent_id: str = "", order: int = 0) -> dict:
        slug = category_slug(entry["slug"])
        category = next(
            (
                item
                for item in store.get("categories", [])
                if item.get("status") != "deleted"
                and record_company_id(item, store) == company_id
                and (
                    category_slug(item.get("slug", "") or item.get("name", "")) == slug
                    or item.get("name", "").strip().lower() == entry["name"].strip().lower()
                )
            ),
            None,
        )
        if category and category.get("status") != "deleted":
            existing.append({"id": category.get("id", ""), "name": category.get("name", ""), "slug": slug})
            return category

        now = utc_now()
        category = {
            "id": next_id("cat", slug),
            "companyId": company_id,
            "name": entry["name"],
            "slug": slug,
            "description": entry.get("description", ""),
            "imageUrl": "",
            "icon": entry.get("icon", "bi-tags") or "bi-tags",
            "sortOrder": order,
            "status": "active",
            "visibleInApp": True,
            "parentId": parent_id,
            "createdAt": now,
            "updatedAt": now,
        }
        store.setdefault("categories", []).append(category)
        created.append({"id": category["id"], "name": category["name"], "slug": slug, "parentId": parent_id})
        return category

    for index, root in enumerate(FVENTAS_STARTER_CATEGORY_TREE, start=1):
        root_category = create_or_get(root, "", index * 10)
        root_ids[root["slug"]] = root_category.get("id", "")
        child_parent_id = root_ids[root["slug"]]
        for child_index, (name, description, icon) in enumerate(root.get("children", []), start=1):
            create_or_get(
                {
                    "name": name,
                    "slug": name,
                    "description": description,
                    "icon": icon,
                },
                child_parent_id,
                (index * 10) + child_index,
            )

    return {"created": created, "existing": existing}


def create_fventas_starter_products(store: dict) -> dict:
    created: list[dict] = []
    existing: list[dict] = []
    missing_categories: list[dict] = []
    company_id = current_company_id(store)

    category_result = create_fventas_starter_categories(store)
    categories_by_slug: dict[str, dict] = {}
    for category in visible_records_for_current_company(store, "categories"):
        if category.get("status") == "deleted":
            continue
        categories_by_slug[category_slug(category.get("slug", "") or category.get("name", ""))] = category
        categories_by_slug[category_slug(category.get("name", ""))] = category

    for index, entry in enumerate(FVENTAS_STARTER_PRODUCTS, start=1):
        sku = entry["sku"].strip().upper()
        current = next(
            (
                product
                for product in visible_records_for_current_company(store, "products")
                if product.get("status") != "deleted"
                and normalize_import_key(product.get("sku", "")) == normalize_import_key(sku)
            ),
            None,
        )
        if current:
            existing.append({"id": current.get("id", ""), "sku": sku, "title": current.get("title", "")})
            continue

        category = categories_by_slug.get(category_slug(entry.get("categorySlug", "")))
        if not category:
            missing_categories.append({"sku": sku, "categorySlug": entry.get("categorySlug", "")})
            continue

        public_price = round(safe_float(entry.get("price"), 0), 2)
        discount = max(0.0, min(safe_float(entry.get("discount"), 0), 100.0))
        original_price = public_price
        if discount:
            original_price = round(public_price / max(0.01, 1 - (discount / 100)), 2)
        stock = max(0, safe_int(entry.get("stock"), 0))
        image_url = entry.get("imageUrl", "")
        now = utc_now()
        product = {
            "id": next_id("prod", sku),
            "companyId": company_id,
            "sku": sku,
            "internalCode": sku,
            "title": entry["title"],
            "brand": "FVENTAS",
            "model": entry.get("model", sku),
            "unitOfSale": "unidad",
            "shortDescription": entry.get("description", ""),
            "longDescription": entry.get("description", ""),
            "description": entry.get("description", ""),
            "productType": entry.get("productType", "machine"),
            "categoryId": category["id"],
            "categoryName": category.get("name", ""),
            "subCategory": category.get("name", ""),
            "publicPriceUsd": public_price,
            "originalPriceUsd": original_price,
            "discountPercent": discount,
            "b2bPriceUsd": round(safe_float(entry.get("b2bPrice"), public_price), 2),
            "costReferenceUsd": 0,
            "marginPercent": 0,
            "exchangeRateUsdClp": current_rate(),
            "stock": stock,
            "physicalStock": stock,
            "availableStock": stock,
            "reservedStock": 0,
            "committedStock": 0,
            "minimumStock": max(1, min(3, stock)),
            "maximumStock": max(10, stock * 3),
            "reserved": 0,
            "stockStatus": "available" if stock > 0 else "out",
            "stockStatusLabel": stock_status_label("available" if stock > 0 else "out"),
            "status": "active",
            "imageUrl": image_url,
            "imageUrls": [image_url] if image_url else [],
            "pdfUrls": [],
            "variants": entry.get("variants", []),
            "specifications": entry.get("specifications", {}),
            "relatedSkus": [],
            "requiresQuote": False,
            "requiresTechnicalValidation": entry.get("productType") == "machine" and public_price >= 1000,
            "visibleInApp": True,
            "publishedInApp": True,
            "featured": index <= 8,
            "onSale": discount > 0,
            "rotationLast30Days": max(0, safe_int(entry.get("rotation"), 0)),
            "sourceUrl": entry.get("sourceUrl", ""),
            "sourceName": "Catalogo inicial FVENTAS",
            "createdAt": now,
            "updatedAt": now,
        }
        store.setdefault("products", []).append(product)
        created.append({"id": product["id"], "sku": sku, "title": product["title"], "category": category.get("name", "")})

    return {
        "created": created,
        "existing": existing,
        "missingCategories": missing_categories,
        "categories": category_result,
    }


def category_page_context(store: dict, error: str = "") -> dict:
    filters = {
        "q": request.args.get("q", "").strip().lower(),
        "status": request.args.get("status", "").strip(),
        "visibility": request.args.get("visibility", "").strip(),
        "parent": request.args.get("parent", "").strip(),
    }
    categories = [
        enrich_category(category, store)
        for category in visible_records_for_current_company(store, "categories")
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
            "products": insights_from_pairs(
                [(category.get("name", ""), float(category.get("productsCount") or 0)) for category in categories],
                6,
            ),
            "visibility": insights_from_pairs(
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
            for category in visible_records_for_current_company(store, "categories")
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
    requested_role = request.form.get("role", "operator")
    if not email:
        return "El email del usuario admin es obligatorio."
    if requested_role not in WEB_ADMIN_ROLES or requested_role == "sales":
        return "El rol seleccionado no es valido para panel administrativo."
    if requested_role == "platform_admin" and current_admin_role() != "platform_admin":
        return "Solo FVENTAS puede crear administradores de plataforma."
    if existing and existing.get("role") == "platform_admin" and current_admin_role() != "platform_admin":
        return "No puedes modificar administradores de plataforma."
    duplicated = any(
        str(user.get("email") or "").lower() == email
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
        str(user.get("email") or "").lower() == email
        and (existing is None or user.get("id") != existing.get("id"))
        for user in store["admin_users"]
    )
    if duplicated:
        return f"Ya existe un usuario con el email {email}."
    client_conflict = any(
        str(client.get("email") or "").lower() == email and client.get("status") == "active"
        for client in store.get("clients", [])
    )
    if client_conflict:
        return f"Ya existe un cliente movil con el email {email}."
    seller_code = sanitize_text(request.form.get("sellerCode", ""), max_length=80, allow_newlines=False).upper()
    target_company_id = record_company_id(existing, store) if existing else current_company_id(store)
    duplicated_code = any(
        user.get("role") == "sales"
        and str(user.get("sellerCode") or "").upper() == seller_code
        and record_company_id(user, store) == target_company_id
        and (existing is None or user.get("id") != existing.get("id"))
        for user in store.get("admin_users", [])
    )
    if seller_code and duplicated_code:
        return "Ya existe un vendedor con ese codigo en esta empresa."
    return credential_form_error(password, existing)


def client_form_error(store: dict, existing: dict | None = None) -> str:
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    target_company_id = record_company_id(existing, store) if existing else current_company_id(store)
    profile = active_market_profile_for_store(store, target_company_id)
    business_name = (
        request.form.get("businessName", "").strip()
        or request.form.get("commercialName", "").strip()
        or request.form.get("legalName", "").strip()
    )
    raw_tax_id = request.form.get("taxId", "").strip()
    raw_phone = request.form.get("phone", "").strip()
    normalized_tax_id = normalize_tax_id_for_market(raw_tax_id, profile)
    normalized_phone = normalize_phone_for_market(raw_phone, profile)
    normalized_state, _normalized_city, location_error = normalize_location_for_market(
        request.form.get("state", ""),
        request.form.get("city", ""),
        profile,
    )
    if not business_name:
        return "La razon social o nombre comercial del cliente es obligatoria."
    if not email:
        return "El email del cliente B2B es obligatorio."
    if not normalized_tax_id:
        return f"El {profile.get('taxLabel', 'documento fiscal')} no es valido. Ejemplo: {profile.get('taxPlaceholder', 'ID fiscal')}."
    if not normalized_phone:
        return f"El telefono no es valido. Ejemplo: {profile.get('phonePlaceholder', '+ codigo pais telefono')}."
    if location_error:
        return location_error
    if request.form.get("clientType", "b2b") not in dict(CLIENT_TYPE_OPTIONS):
        return "El tipo de cliente no es valido."
    if request.form.get("clientCategory", "standard") not in dict(CLIENT_CATEGORY_OPTIONS):
        return "La categoria comercial no es valida."
    if request.form.get("priceList", "b2b") not in dict(PRICE_LIST_OPTIONS):
        return "La lista de precios no es valida."
    if request.form.get("status", "active") not in dict(CLIENT_STATUS_OPTIONS):
        return "El estado del cliente no es valido."
    if request.form.get("defaultSaleType", "cash") not in dict(SALE_TYPE_OPTIONS):
        return "El tipo de venta default no es valido."
    if request.form.get("collectionStatus", "without_debt") not in dict(COLLECTION_STATUS_OPTIONS):
        return "El estado de cobranza no es valido."
    if request.form.get("creditRiskLevel", "low") not in dict(CREDIT_RISK_OPTIONS):
        return "El riesgo comercial no es valido."
    discount = safe_float(request.form.get("authorizedDiscountPercent"), 0)
    if discount < 0 or discount > 100:
        return "El descuento autorizado debe estar entre 0 y 100%."
    credit_score = safe_int(request.form.get("creditScore"), safe_int((existing or {}).get("creditScore"), 0))
    if credit_score < 0 or credit_score > 100:
        return "El score comercial debe estar entre 0 y 100."
    scoped_clients = [
        client
        for client in store.get("clients", [])
        if record_company_id(client, store) == target_company_id
    ]
    global_email_owner = next(
        (
            client
            for client in store.get("clients", [])
            if str(client.get("email") or "").lower() == email
            and (existing is None or client.get("id") != existing.get("id"))
        ),
        None,
    )
    if global_email_owner and record_company_id(global_email_owner, store) != target_company_id:
        return "Ese email ya esta registrado como acceso movil de otra empresa."
    mobile_user_conflict = next(
        (
            user
            for user in store.get("admin_users", [])
            if str(user.get("email") or "").lower() == email
            and user.get("status") == "active"
            and user.get("mobileAccessEnabled", True) is not False
            and user.get("role") in MOBILE_SALES_ROLES
        ),
        None,
    )
    if mobile_user_conflict:
        return "Ese email ya esta registrado como usuario operativo movil."
    duplicated = any(
        str(client.get("email") or "").lower() == email
        and (existing is None or client.get("id") != existing.get("id"))
        for client in scoped_clients
    )
    if duplicated:
        return f"Ya existe un cliente con el email {email}."
    duplicated_tax_id = any(
        normalize_tax_id_for_market(client.get("taxId", ""), profile).lower() == normalized_tax_id.lower()
        and (existing is None or client.get("id") != existing.get("id"))
        for client in scoped_clients
    )
    if duplicated_tax_id:
        return f"Ya existe un cliente con el {profile.get('taxLabel', 'documento fiscal')} {normalized_tax_id}."
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


def normalize_option_value(value: str | None, options: list[tuple[str, str]], default: str) -> str:
    normalized = str(value or default).strip()
    return normalized if normalized in dict(options) else default


def client_status_blocks_mobile_access(status: str) -> bool:
    return str(status or "").strip() in CLIENT_SALE_BLOCKING_STATUSES


def sync_client_mobile_access_state(
    client: dict,
    existing: dict | None = None,
    *,
    force_revoke: bool = False,
    allow_reenable: bool = False,
) -> None:
    previous = existing or {}
    previous_enabled = bool(previous.get("mobileAccessEnabled", True))
    previous_version = safe_int(previous.get("mobileSessionVersion"), 0)
    desired_enabled = bool(client.get("mobileAccessEnabled", previous_enabled))
    if client_status_blocks_mobile_access(client.get("status", "")) or mobile_account_access_blocked(client):
        desired_enabled = False
    elif allow_reenable and client.get("status") == "active":
        desired_enabled = True
    client["mobileAccessEnabled"] = desired_enabled
    should_revoke = bool(existing) and (force_revoke or (previous_enabled and not desired_enabled))
    client["mobileSessionVersion"] = previous_version + (1 if should_revoke else 0)


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
    truthy_values = {"on", "1", "true", "yes", "si", "sÃƒÂ­"}
    requested_role = request.form.get("role", "operator")
    if requested_role == "platform_admin" and current_admin_role() != "platform_admin":
        requested_role = (existing or {}).get("role", "operator")
    company_id = (
        request.form.get("companyId")
        if current_admin_role() == "platform_admin" and request.form.get("companyId")
        else (existing or {}).get("companyId") or session.get("company_id") or DEFAULT_COMPANY_ID
    )
    payload = {
        "companyId": company_id,
        "firstName": first_name or (existing or {}).get("firstName", ""),
        "lastName": last_name or (existing or {}).get("lastName", ""),
        "name": display_name,
        "email": email,
        "role": requested_role,
        "status": request.form.get("status", "active"),
        "sellerCode": sanitize_text(request.form.get("sellerCode", ""), max_length=80, allow_newlines=False).upper(),
        "sellerZone": sanitize_text(request.form.get("sellerZone", ""), max_length=120, allow_newlines=False),
        "sellerTerritory": sanitize_text(request.form.get("sellerTerritory", ""), max_length=120, allow_newlines=False),
        "sellerSupervisor": sanitize_text(request.form.get("sellerSupervisor", ""), max_length=160, allow_newlines=False),
        "phone": sanitize_text(request.form.get("phone", ""), max_length=60, allow_newlines=False),
        "hiredAt": sanitize_text(request.form.get("hiredAt", ""), max_length=32, allow_newlines=False),
        "mobileAccessEnabled": (
            any(str(value).strip().lower() in truthy_values for value in mobile_access_values)
            if mobile_access_values
            else bool((existing or {}).get("mobileAccessEnabled", True))
        ),
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
    actor_id = session.get("admin_user_id", "")
    actor_name = session.get("admin_name", "FVENTAS Admin")
    actor_role = current_admin_role()
    active_store = load_store()
    company_id = record_company_id(existing, active_store) if existing else current_company_id(active_store)
    base_profile = active_market_profile_for_store(active_store, company_id=company_id)
    requested_country = normalize_market_country(base_profile.get("code", "CL"))
    client_profile = market_profile(requested_country)
    seller_id = request.form.get("assignedSellerId", "").strip()
    current_seller_id, current_seller_name = current_seller_assignment(active_store)
    if current_seller_id:
        seller_id = current_seller_id
    seller = find_company_record(active_store, "admin_users", seller_id) if seller_id else None
    if seller_id and (not seller or seller.get("role") != "sales"):
        seller_id = ""
        seller = None
    seller_name = (seller or {}).get("name", "") or current_seller_name
    normalized_tax_id = normalize_tax_id_for_market(request.form.get("taxId", ""), client_profile)
    normalized_phone = normalize_phone_for_market(request.form.get("phone", ""), client_profile)
    normalized_whatsapp = normalize_phone_for_market(request.form.get("whatsapp", ""), client_profile) or normalized_phone
    normalized_state, normalized_city, _location_error = normalize_location_for_market(
        request.form.get("state", ""),
        request.form.get("city", ""),
        client_profile,
    )

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
        "companyId": company_id,
        "legalName": sanitize_text(request.form.get("legalName", ""), max_length=180, allow_newlines=False),
        "commercialName": sanitize_text(request.form.get("commercialName", ""), max_length=180, allow_newlines=False),
        "businessName": sanitize_text(request.form.get("businessName", ""), max_length=180, allow_newlines=False),
        "taxId": normalized_tax_id,
        "contactName": sanitize_text(request.form.get("contactName", ""), max_length=160, allow_newlines=False),
        "administrativeContact": sanitize_text(request.form.get("administrativeContact", ""), max_length=160, allow_newlines=False),
        "receivingContact": sanitize_text(request.form.get("receivingContact", ""), max_length=160, allow_newlines=False),
        "phone": normalized_phone,
        "whatsapp": normalized_whatsapp,
        "email": email,
        "clientType": normalize_option_value(request.form.get("clientType"), CLIENT_TYPE_OPTIONS, "b2b"),
        "clientCategory": normalize_option_value(request.form.get("clientCategory"), CLIENT_CATEGORY_OPTIONS, "standard"),
        "priceList": normalize_option_value(request.form.get("priceList"), PRICE_LIST_OPTIONS, "b2b"),
        "authorizedDiscountPercent": max(0.0, min(100.0, safe_float(request.form.get("authorizedDiscountPercent"), 0))),
        "status": request.form.get("status", "active"),
        "address": sanitize_text(request.form.get("address", ""), max_length=400),
        "fiscalAddress": sanitize_text(request.form.get("fiscalAddress", ""), max_length=400),
        "shippingAddress": sanitize_text(request.form.get("shippingAddress", ""), max_length=400),
        "country": client_profile.get("code", "CL"),
        "state": normalized_state,
        "city": normalized_city,
        "deliveryZone": sanitize_text(request.form.get("deliveryZone", ""), max_length=120, allow_newlines=False),
        "assignedSellerId": seller_id,
        "assignedSellerName": seller_name,
        "defaultSaleType": normalize_option_value(request.form.get("defaultSaleType"), SALE_TYPE_OPTIONS, "cash"),
        "allowedPaymentTermsDays": selected_payment_terms(),
        "collectionStatus": normalize_option_value(request.form.get("collectionStatus"), COLLECTION_STATUS_OPTIONS, "without_debt"),
        "creditRiskLevel": normalize_option_value(request.form.get("creditRiskLevel"), CREDIT_RISK_OPTIONS, "low"),
        "creditScore": max(0, min(100, safe_int(request.form.get("creditScore"), safe_int((existing or {}).get("creditScore"), 0)))),
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
        "mobileAccessEnabled": bool((existing or {}).get("mobileAccessEnabled", True)),
        "updatedVia": "admin",
        "updatedById": actor_id,
        "updatedByName": actor_name,
        "updatedByRole": actor_role,
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
        payload["createdVia"] = "admin"
        payload["createdById"] = actor_id
        payload["createdByName"] = actor_name
        payload["createdByRole"] = actor_role
        payload["createdAt"] = now
        payload["passwordHash"] = generate_password_hash(password)
        payload["mustChangePassword"] = True
    else:
        payload["id"] = existing["id"]
        payload["createdVia"] = existing.get("createdVia", "admin")
        payload["createdById"] = existing.get("createdById", "")
        payload["createdByName"] = existing.get("createdByName") or existing.get("assignedSellerName") or "FVENTAS Admin"
        payload["createdByRole"] = existing.get("createdByRole") or ("sales" if payload["createdVia"] == "seller_mobile" else "admin")
        payload["createdAt"] = existing.get("createdAt", now)
        payload["passwordHash"] = (
            generate_password_hash(password) if password else existing.get("passwordHash", "")
        )
        payload["mustChangePassword"] = True if password else bool(existing.get("mustChangePassword"))
        for key in (
            "deletionStatus",
            "deletionRequestId",
            "deletionRequestedAt",
            "deletionRequestChannel",
            "deletionRequestReason",
            "deletionApprovedAt",
            "deletionCompletedAt",
            "mobileAccess",
            "passwordRecoveryRequestedAt",
            "passwordRecoveryStatus",
        ):
            if key in existing:
                payload[key] = existing.get(key)
    sync_client_mobile_access_state(payload, existing, force_revoke=bool(existing and password))
    return payload


def clients_page_context(store: dict, error: str = "") -> dict:
    scoped_orders = visible_records_for_current_company(store, "orders")
    scoped_credit_movements = visible_records_for_current_company(store, "credit_movements")
    clients_list = enrich_clients(visible_clients_for_current_user(store), scoped_orders, scoped_credit_movements)
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
    clients_list = sorted(clients_list, key=lambda item: item.get("businessName", ""))
    page_clients, pagination = api_list_pagination(clients_list, default_limit=24)
    total_pages = max(1, math.ceil((pagination.get("total") or 0) / max(1, pagination.get("limit") or 1)))
    pagination.update({
        "pages": total_pages,
        "start": (pagination.get("offset") or 0) + 1 if pagination.get("total") else 0,
        "end": (pagination.get("offset") or 0) + len(page_clients),
        "previousPage": (pagination.get("page") or 1) - 1 if (pagination.get("page") or 1) > 1 else None,
        "nextPage": (pagination.get("page") or 1) + 1 if pagination.get("hasMore") else None,
    })
    client_ids = {client.get("id", "") for client in page_clients}
    orders_by_client: dict[str, list[dict]] = {}
    for order in sorted(scoped_orders, key=lambda item: item.get("createdAt", ""), reverse=True):
        if order.get("customerId") not in client_ids:
            continue
        orders_by_client.setdefault(order.get("customerId", ""), []).append(enrich_order(order, scoped_credit_movements))
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
    active_profile = active_market_profile_for_store(store, current_company_id(store))
    return {
        "clients": page_clients,
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
        "country_locations": country_location_options(active_profile.get("code")),
        "country_location_labels": country_location_labels(active_profile.get("code")),
        "client_market_profile": active_profile,
        "chile_locations": country_location_options("CL"),
        "can_approve_credit": can_module_action("credit", "approve"),
        "can_edit_clients": can_module_action("clients", "edit"),
        "can_create_clients": can_module_action("clients", "create"),
        "metrics": metrics,
        "filters": filters,
        "pagination": pagination,
        "total_clients": len(clients_list),
        "orders_by_client": orders_by_client,
        "error": error,
        "bulk_result": consume_bulk_result("clients") if not error else None,
    }


def enrich_seller(store: dict, seller: dict) -> dict:
    enriched = dict(seller)
    seller_id = enriched.get("id", "")
    seller_company_id = record_company_id(seller, store)
    movements = records_for_company_id(store, "credit_movements", seller_company_id)
    scoped_orders = records_for_company_id(store, "orders", seller_company_id)
    scoped_clients = records_for_company_id(store, "clients", seller_company_id)
    seller_orders = [
        enrich_order(order, movements)
        for order in scoped_orders
        if order.get("sellerId") == seller_id
    ]
    seller_clients = [
        enrich_client(client, scoped_orders, movements)
        for client in scoped_clients
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
        for seller in visible_records_for_current_company(store, "admin_users")
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
            "sales_month": insights_from_pairs(
                [(seller.get("name", "Vendedor"), float(seller.get("salesMonthUsd") or 0)) for seller in sellers],
                6,
            ),
            "clients": insights_from_pairs(
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
    orders = visible_orders_for_current_user(store)
    movements = visible_records_for_current_company(store, "credit_movements")
    clients_list = [
        enrich_client(client, orders, movements)
        for client in visible_clients_for_current_user(store)
        if client.get("status") == "active"
    ]
    products = enrich_inventory_products(
        [
            product
            for product in visible_records_for_current_company(store, "products")
            if product.get("status") == "active"
        ],
        orders,
    )
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
    orders = visible_orders_for_current_user(store)
    movements = visible_records_for_current_company(store, "stock_movements")
    all_products = enrich_inventory_products(
        visible_records_for_current_company(store, "products"),
        orders,
        movements,
    )
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
            "stock": insights_from_pairs(
                [(product.get("sku", ""), float(product.get("availableStock") or 0)) for product in products],
                6,
            ),
            "media": insights_from_pairs(
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
    movements = [enrich_stock_movement(movement) for movement in visible_records_for_current_company(store, "stock_movements")]
    orders = visible_orders_for_current_user(store)
    all_products = enrich_inventory_products(
        visible_records_for_current_company(store, "products"),
        orders,
        movements,
    )
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
            "available": insights_from_pairs(
                [(product.get("sku", ""), float(product.get("availableStock") or 0)) for product in products],
                8,
            ),
            "movement_types": insights_from_pairs(list(movement_counts.items()), 6),
            "critical": insights_from_pairs(
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
        "preview": {"exchangeRateUsdClp": current_rate()},
    }


def next_quote_number(client_name: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    suffix = secrets.token_hex(2).upper()
    seed = re.sub(r"[^A-Za-z0-9]+", "", client_name or "FVENTAS")[:8].upper()
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
        product = find_company_record(store, "products", product_id)
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
                "title": product.get("title", "Producto FVENTAS"),
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
    client = find_company_record(store, "clients", client_id)
    if not can_access_client_record(client, store):
        return None, "Cliente no encontrado o fuera de tu alcance."
    items, gross_usd, total_usd, error = quote_items_from_form(store)
    if error:
        return None, error
    if not items:
        return None, "Agrega al menos un producto a la cotizacion."

    exchange_rate = safe_float(request.form.get("exchangeRateUsdClp"), current_rate())
    client_company_id = record_company_id(client, store)
    seller_id = client.get("assignedSellerId", "") if client else ""
    seller_name = client.get("assignedSellerName", "") or seller_name_for(store, seller_id, client_company_id)
    status = request.form.get("status", (existing or {}).get("status", "draft"))
    if status not in dict(QUOTE_STATUS_OPTIONS):
        status = "draft"
    sale_type = request.form.get("saleType", (existing or {}).get("saleType", "cash"))
    if sale_type not in dict(SALE_TYPE_OPTIONS):
        sale_type = "cash"
    payment_term_days = safe_int(request.form.get("paymentTermDays"), safe_int((existing or {}).get("paymentTermDays"), 0))
    condition_error, sale_type, payment_term_days = validate_client_purchase_conditions(client, sale_type, payment_term_days)
    if condition_error:
        return None, condition_error

    quote = copy.deepcopy(existing or {})
    now = utc_now()
    if not quote:
        quote["id"] = next_id("quote", client.get("businessName", "fventas"))
        quote["quoteNumber"] = next_quote_number(client.get("businessName", "FVENTAS"))
        quote["version"] = 1
        quote["versions"] = []
        quote["history"] = []
        quote["createdAt"] = now
        quote["createdById"] = session.get("admin_user_id", "")
        quote["createdByName"] = session.get("admin_name", "Sistema")
    quote.update(
        {
            "companyId": record_company_id(client, store),
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
            "totalClp": round(total_usd * exchange_rate, 2),
            "totalVes": round(total_usd * exchange_rate, 2),
            "exchangeRateUsdClp": exchange_rate,
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
    enriched["clientName"] = (enriched.get("client") or {}).get("name", "Cliente FVENTAS")
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
            "totalClp": quote.get("totalClp", quote.get("totalVes", 0)),
            "totalVes": quote.get("totalVes", quote.get("totalClp", 0)),
            "exchangeRateUsdClp": quote.get("exchangeRateUsdClp", quote.get("exchangeRateUsdVes", current_rate())),
            "exchangeRateUsdVes": quote.get("exchangeRateUsdVes", quote.get("exchangeRateUsdClp", current_rate())),
        },
    }


def quote_form_context(store: dict, quote: dict | None = None, error: str = "") -> dict:
    currency_data = currency_context(store)
    scoped_orders = visible_records_for_current_company(store, "orders")
    scoped_credit_movements = visible_records_for_current_company(store, "credit_movements")
    clients_list = [
        enrich_client(client, scoped_orders, scoped_credit_movements)
        for client in visible_clients_for_current_user(store)
        if client.get("status") in {"active", "prospect", "review"}
    ]
    products = enrich_inventory_products(
        [
            product
            for product in visible_records_for_current_company(store, "products")
            if product.get("status") == "active"
        ],
        scoped_orders,
    )
    default_valid_until = (datetime.now(timezone.utc) + timedelta(days=7)).date().isoformat()
    return {
        "quote": enrich_quote(quote) if quote else None,
        "clients": sorted(clients_list, key=lambda item: item.get("businessName", "")),
        "products": sorted(products, key=lambda item: item.get("title", "")),
        "status_options": QUOTE_STATUS_OPTIONS,
        "sale_type_options": SALE_TYPE_OPTIONS,
        "payment_terms": payment_term_options(store),
        "default_valid_until": default_valid_until,
        "sales_currency": currency_data["sales_currency"],
        "local_currency": currency_data["local_currency"],
        "exchange_rate": currency_data["exchange_rate"],
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
        for seller in visible_records_for_current_company(store, "admin_users")
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
            "status": insights_from_pairs(list(status_counts.items()), 8),
            "seller": insights_from_pairs(list(seller_totals.items()), 6),
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
    client = find_company_record(store, "clients", client_id) if client_id else None
    if client_id and not can_access_client_record(client, store):
        return None, "Cliente vinculado no encontrado o fuera de tu alcance."

    seller_id = request.form.get("sellerId", "").strip()
    if client and not seller_id:
        seller_id = client.get("assignedSellerId", "")
    seller = find_company_record(store, "admin_users", seller_id) if seller_id else None
    if seller and seller.get("role") != "sales":
        seller = None
        seller_id = ""
    seller_name = (seller or {}).get("name", "") or (client or {}).get("assignedSellerName", "")
    company_id = record_company_id(existing, store) if existing else (record_company_id(client, store) if client else current_company_id(store))

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
            "companyId": company_id,
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
        seller for seller in visible_records_for_current_company(store, "admin_users")
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
            "stage": insights_from_pairs(list(stage_counts.items()), 8),
            "value": insights_from_pairs(list(value_by_stage.items()), 8),
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
    movements = visible_records_for_current_company(store, "credit_movements")
    all_orders = enrich_orders(
        sorted(visible_orders_for_current_user(store), key=lambda item: item.get("createdAt", ""), reverse=True),
        movements,
    )
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
        for seller in visible_records_for_current_company(store, "admin_users")
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
    page_orders, pagination = api_list_pagination(orders_list, default_limit=24)
    total_pages = max(1, math.ceil((pagination.get("total") or 0) / max(1, pagination.get("limit") or 1)))
    pagination.update({
        "pages": total_pages,
        "start": (pagination.get("offset") or 0) + 1 if pagination.get("total") else 0,
        "end": (pagination.get("offset") or 0) + len(page_orders),
        "previousPage": (pagination.get("page") or 1) - 1 if (pagination.get("page") or 1) > 1 else None,
        "nextPage": (pagination.get("page") or 1) + 1 if pagination.get("hasMore") else None,
    })
    return {
        "orders": page_orders,
        "all_orders": all_orders,
        "metrics": metrics,
        "filters": filters,
        "pagination": pagination,
        "total_orders": len(orders_list),
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
            "status": insights_from_pairs([(label, float(value)) for label, value in status_counts.items()], 6),
            "sale_type": insights_from_pairs(list(sale_type_totals.items()), 6),
            "seller": insights_from_pairs(list(seller_totals.items()), 6),
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
    movements = visible_records_for_current_company(store, "credit_movements")
    filters = {
        "q": request.args.get("q", "").strip(),
        "status": request.args.get("status", "").strip(),
        "seller": request.args.get("seller", "").strip(),
        "rule": request.args.get("rule", "").strip(),
        "release": request.args.get("release", "").strip(),
    }
    client_lookup = {
        client.get("id", ""): enrich_client(client, visible_orders_for_current_user(store), movements)
        for client in visible_clients_for_current_user(store)
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
        "seller_options": sales_users(store),
        "commission_charts": {
            "status": insights_from_pairs([(commission_status_label(key), value) for key, value in status_totals.items()], 8),
            "seller": insights_from_pairs(list(seller_totals.items()), 8),
            "rule": insights_from_pairs(list(rule_totals.items()), 8),
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
    movements = visible_records_for_current_company(store, "credit_movements")
    products_by_id, products_by_sku = product_lookup_maps(visible_records_for_current_company(store, "products"))
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
            ("total", "Total moneda venta"),
            ("abonado", "Abonado moneda venta"),
            ("saldo", "Saldo moneda venta"),
        ],
        "finance": [
            ("vence", "Vence"),
            ("orden", "Orden"),
            ("cliente", "Cliente"),
            ("vendedor", "Vendedor"),
            ("condicion", "Condicion"),
            ("estado_cobranza", "Cobranza"),
            ("total", "Total moneda venta"),
            ("abonado", "Abonado moneda venta"),
            ("saldo", "Saldo moneda venta"),
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
            ("precio", "Precio moneda venta"),
            ("valor_stock", "Valor stock moneda venta"),
        ],
        "sellers": [
            ("vendedor", "Vendedor"),
            ("zona", "Zona"),
            ("clientes", "Clientes"),
            ("ordenes", "Ordenes"),
            ("ventas", "Ventas moneda venta"),
            ("ticket_promedio", "Ticket promedio moneda venta"),
            ("meta", "Meta moneda venta"),
            ("avance_meta", "Avance meta"),
            ("comision_pendiente", "Comision pendiente moneda venta"),
            ("comision_pagada", "Comision pagada moneda venta"),
        ],
    }
    return columns.get(report_type, columns["commercial"])


def build_report_rows(store: dict, filters: dict[str, str], orders: list[dict]) -> list[dict]:
    report_type = filters["type"]
    scoped_products = visible_records_for_current_company(store, "products")
    products_by_id, products_by_sku = product_lookup_maps(scoped_products)
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
                    "total": round(safe_float(order.get("totalUsd"), 0), 2),
                    "abonado": round(safe_float(order.get("paidUsd"), 0), 2),
                    "saldo": round(safe_float(order.get("balanceUsd"), 0), 2),
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
                "total": round(safe_float(order.get("totalUsd"), 0), 2),
                "abonado": round(safe_float(order.get("paidUsd"), 0), 2),
                "saldo": round(safe_float(order.get("balanceUsd"), 0), 2),
                "ultimo_abono": order.get("lastPaymentAt", ""),
            }
            for order in sorted(orders, key=lambda item: (item.get("dueDate", ""), item.get("createdAt", "")))
            if safe_float(order.get("balanceUsd"), 0) > 0
        ]
    if report_type == "inventory":
        products = [enrich_product(product) for product in scoped_products]
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
                "precio": round(safe_float(product.get("publicPriceUsd"), 0), 2),
                "valor_stock": round(max(0, safe_int(product.get("stock"), 0) - safe_int(product.get("reserved"), 0)) * safe_float(product.get("publicPriceUsd"), 0), 2),
            }
            for product in sorted(products, key=lambda item: (item.get("categoryName", ""), item.get("title", "")))
        ]
    sellers = [
        enrich_seller(store, seller)
        for seller in visible_records_for_current_company(store, "admin_users")
        if seller.get("role") == "sales" and seller.get("status") != "deleted"
    ]
    if filters.get("seller"):
        sellers = [seller for seller in sellers if seller.get("id") == filters["seller"]]
    return [
        {
            "vendedor": seller.get("name", ""),
            "zona": seller.get("zone", ""),
            "clientes": seller.get("clientsCount", 0),
            "ordenes": seller.get("ordersCount", 0),
            "ventas": round(safe_float(seller.get("salesUsd"), 0), 2),
            "ticket_promedio": round(safe_float(seller.get("ticketAverageUsd"), 0), 2),
            "meta": round(safe_float(seller.get("salesGoalUsd"), 0), 2),
            "avance_meta": f"{seller.get('goalProgressPercent', 0)}%",
            "comision_pendiente": round(safe_float(seller.get("commissionPendingUsd"), 0), 2),
            "comision_pagada": round(safe_float(seller.get("commissionPaidUsd"), 0), 2),
        }
        for seller in sorted(sellers, key=lambda item: safe_float(item.get("salesUsd"), 0), reverse=True)
    ]


def reports_page_context(store: dict) -> dict:
    filters = reports_filters_from_request()
    orders = report_orders(store, filters)
    scoped_products = visible_records_for_current_company(store, "products")
    scoped_clients = visible_clients_for_current_user(store)
    scoped_movements = visible_records_for_current_company(store, "credit_movements")
    scoped_sellers = [
        seller
        for seller in visible_records_for_current_company(store, "admin_users")
        if seller.get("role") == "sales" and seller.get("status") != "deleted"
    ]
    products_by_id, products_by_sku = product_lookup_maps(scoped_products)
    rows = build_report_rows(store, filters, orders)
    payments = [
        movement
        for movement in scoped_movements
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
            client_name = order.get("customerName") or "Cliente FVENTAS"
            receivables_by_client[client_name] = receivables_by_client.get(client_name, 0) + safe_float(order.get("balanceUsd"), 0)
        seller_commissions[seller] = seller_commissions.get(seller, 0) + safe_float(order.get("commissionUsd"), 0)
        for line in reports_product_lines(order, products_by_id, products_by_sku):
            category_totals[line["category"]] = category_totals.get(line["category"], 0) + safe_float(line.get("lineTotalUsd"), 0)
    for product in scoped_products:
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
        "stock_units": sum(max(0, safe_int(product.get("stock"), 0) - safe_int(product.get("reserved"), 0)) for product in scoped_products),
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
        "seller_options": sorted(scoped_sellers, key=lambda item: item.get("name", "")),
        "client_options": sorted(scoped_clients, key=lambda item: item.get("businessName", "")),
        "category_options": product_category_options(store),
        "product_options": sorted(scoped_products, key=lambda item: item.get("title", "")),
        "order_status_options": ORDER_STATUS_OPTIONS,
        "charts": {
            "sales_by_day": insights_from_pairs(list(sales_by_day.items()), 8),
            "seller_totals": insights_from_pairs(list(seller_totals.items()), 8),
            "category_totals": insights_from_pairs(list(category_totals.items()), 8),
            "receivables_by_client": insights_from_pairs(list(receivables_by_client.items()), 8),
            "stock_by_category": insights_from_pairs(list(stock_by_category.items()), 8),
            "seller_commissions": insights_from_pairs(list(seller_commissions.items()), 8),
        },
        "can_export_reports": can_module_action("reports", "export"),
    }


def report_response_csv(context: dict) -> Response:
    output = io.StringIO()
    columns = context["columns"]
    writer = safe_csv_dict_writer(output, fieldnames=[key for key, _label in columns], lineterminator="\n")
    writer.writeheader()
    for row in context["rows"]:
        writer.writerow({key: row.get(key, "") for key, _label in columns})
    filename = safe_download_filename(
        f"reporte_{context['filters']['type']}_fventas.csv",
        "reporte_fventas.csv",
    )
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
        sheet.append(safe_export_values([row.get(key, "") for key, _label in columns]))
    for index, (_key, label) in enumerate(columns, start=1):
        sheet.column_dimensions[sheet.cell(row=4, column=index).column_letter].width = min(max(len(label) + 8, 16), 34)
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=safe_download_filename(
            f"reporte_{context['filters']['type']}_fventas.xlsx",
            "reporte_fventas.xlsx",
        ),
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
        [item for item in visible_records_for_current_company(store, "service_technicians") if item.get("status") != "deleted"],
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


def active_announcements(
    placement: str | None = None,
    store: dict | None = None,
    company_id: str | None = None,
) -> list[dict]:
    store = store or load_store()
    announcements = [
        announcement
        for announcement in store.get("announcements", [])
        if announcement.get("status") == "active"
        and (placement is None or announcement.get("placement") == placement)
        and (company_id is None or mobile_record_matches_company(announcement, company_id))
    ]
    return sorted(announcements, key=lambda item: int(item.get("priority") or 0), reverse=True)


@app.get("/dashboard")
@require_roles(*roles_for_action("dashboard", "view"))
def dashboard():
    store = load_store()
    orders = visible_orders_for_current_user(store)
    products_source = visible_records_for_current_company(store, "products")
    stock_movements = visible_records_for_current_company(store, "stock_movements")
    products = enrich_inventory_products(products_source, orders, stock_movements)
    products_by_id, products_by_sku = product_lookup_maps(products_source)
    movements = visible_records_for_current_company(store, "credit_movements")
    enriched_orders = enrich_orders(orders, movements)
    clients_list = dashboard_client_summaries(visible_clients_for_current_user(store), enriched_orders)
    announcements = visible_records_for_current_company(store, "announcements")
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
            "announcements": len(announcements),
        }
    )
    filter_options = {
        "sellers": sellers,
        "clients": sorted(clients_list, key=lambda item: item.get("businessName", "")),
        "categories": sorted(visible_records_for_current_company(store, "categories"), key=lambda item: item.get("name", "")),
        "products": sorted(products_source, key=lambda item: item.get("title", "")),
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
    writer = safe_csv_dict_writer(output, fieldnames=fieldnames, lineterminator="\n")
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
        headers={
            "Content-Disposition": (
                "attachment; filename="
                f"{safe_download_filename(f'incidencias_{module}_{draft_id}.csv', 'incidencias_importacion.csv')}"
            )
        },
    )


def platform_companies_page_context(
    store: dict,
    error: str = "",
    temporary_password: str = "",
    created_email: str = "",
) -> dict:
    subscriptions_by_company = {
        subscription.get("companyId"): subscription
        for subscription in store.get("subscriptions", [])
    }
    rows = []
    for company in sorted(store.get("companies", []), key=lambda item: item.get("createdAt", ""), reverse=True):
        subscription = subscriptions_by_company.get(company.get("id"), {})
        profile = market_profile(company.get("country") or subscription.get("country") or "CL")
        default_pricing = plan_pricing_for_country(profile["code"])
        subscription_currency = normalize_currency_code(
            subscription.get("currency") or company.get("planCurrency"),
            default_pricing["currency"],
        )
        subscription_price = safe_float(
            subscription.get("price")
            or subscription.get("priceClp")
            or company.get("planPrice")
            or company.get("planPriceClp"),
            default_pricing["price"],
        )
        admins = [
            user
            for user in store.get("admin_users", [])
            if user.get("companyId") == company.get("id")
            and user.get("role") in WEB_ADMIN_ROLES
            and user.get("status") != "deleted"
        ]
        setup = company_setup_checklist(company, subscription, store)
        access_preference = company.get("desktopAccessPreference") or company.get("accessPreference")
        mobile_requested = bool(company.get("mobileAppAccessRequested"))
        rows.append(
            {
                "company": company,
                "subscription": subscription,
                "adminCount": len(admins),
                "activeAdmins": sum(1 for user in admins if user.get("status") == "active"),
                "marketProfile": profile,
                "subscriptionCurrency": subscription_currency,
                "subscriptionPrice": subscription_price,
                "subscriptionDisplay": money_currency(subscription_price, subscription_currency),
                "accessPreference": access_preference,
                "accessPreferenceLabel": access_preference_label(access_preference),
                "mobileRequested": mobile_requested,
                "setup": setup,
            }
        )

    active_rows = [
        row
        for row in rows
        if row["subscription"].get("status") in SUBSCRIPTION_ACTIVE_STATUSES
        or row["company"].get("status") in SUBSCRIPTION_ACTIVE_STATUSES
    ]
    pending_rows = [
        row
        for row in rows
        if row["subscription"].get("status") == "pending_payment"
        or row["company"].get("status") == "pending_payment"
    ]
    mrr_by_currency = {}
    for row in active_rows:
        currency = row["subscriptionCurrency"]
        mrr_by_currency[currency] = mrr_by_currency.get(currency, 0.0) + row["subscriptionPrice"]
    mrr_summary = [
        {"currency": currency, "amount": amount, "display": money_currency(amount, currency)}
        for currency, amount in sorted(mrr_by_currency.items())
    ]
    if not mrr_summary:
        mrr_summary = [{"currency": SAAS_PLAN_CURRENCY, "amount": 0, "display": money_currency(0, SAAS_PLAN_CURRENCY)}]
    metrics = {
        "companies": len(rows),
        "active": len(active_rows),
        "pending": len(pending_rows),
        "mrr_summary": mrr_summary,
    }
    return {
        "heading": "Empresas SaaS",
        "description": "Gestiona empresas suscritas, activacion del plan mensual y administradores iniciales.",
        "rows": rows,
        "metrics": metrics,
        "error": error,
        "temporary_password": temporary_password,
        "created_email": created_email,
        "subscription_status_options": SUBSCRIPTION_STATUS_OPTIONS,
        "plan_name": SAAS_PLAN_NAME,
        "default_plan": plan_pricing_for_country("CL"),
        "market_country_options": MARKET_COUNTRY_OPTIONS,
        "market_profiles": ACTIVE_MARKET_PROFILES,
    }


@app.route("/platform/companies", methods=["GET", "POST"])
@require_roles("platform_admin")
def platform_companies():
    store = load_store()
    if request.method == "POST":
        market_country = normalize_market_country(request.form.get("marketCountry", "CL"))
        profile = market_profile(market_country)
        pricing = plan_pricing_for_country(market_country)
        company_name = sanitize_text(request.form.get("companyName", ""), max_length=180, allow_newlines=False)
        legal_name = sanitize_text(request.form.get("legalName", ""), max_length=180, allow_newlines=False)
        tax_id = sanitize_text(request.form.get("taxId", ""), max_length=60, allow_newlines=False)
        owner_name = sanitize_text(request.form.get("ownerName", ""), max_length=160, allow_newlines=False)
        owner_email = request.form.get("ownerEmail", "").strip().lower()
        support_phone = sanitize_text(request.form.get("supportPhone", ""), max_length=80, allow_newlines=False)
        status = request.form.get("subscriptionStatus", "active")
        next_payment_at = sanitize_text(request.form.get("nextPaymentAt", ""), max_length=32, allow_newlines=False)
        access_preference = sanitize_text(
            request.form.get("desktopAccessPreference", ""),
            max_length=80,
            allow_newlines=False,
        )
        if access_preference not in {
            "desktop_download_started",
            "desktop_download_cancelled",
            "mobile_first",
            "mobile_only",
        }:
            access_preference = ""
        mobile_app_access_requested = request.form.get("mobileAppAccessRequested") == "on" or access_preference in {
            "desktop_download_cancelled",
            "mobile_first",
            "mobile_only",
        }
        password = request.form.get("password", "").strip() or temporary_admin_password()
        generated_password = not bool(request.form.get("password", "").strip())
        error = ""

        if not company_name:
            error = "El nombre de la empresa es obligatorio."
        elif not owner_name:
            error = "El nombre del administrador es obligatorio."
        elif not owner_email:
            error = "El correo del administrador es obligatorio."
        elif admin_user_by_email(store, owner_email):
            error = "Ya existe un usuario con ese correo."
        elif any(category_slug(company.get("name", "")) == category_slug(company_name) for company in store.get("companies", [])):
            error = "Ya existe una empresa con ese nombre."
        elif status not in dict(SUBSCRIPTION_STATUS_OPTIONS):
            error = "El estado de suscripcion no es valido."
        else:
            credential_error = credential_form_error(password)
            if credential_error:
                error = credential_error

        if error:
            return render_template("platform_companies.html", **platform_companies_page_context(store, error))

        now = utc_now()
        company_id = next_id("company", company_name)
        company_status = "active" if status in SUBSCRIPTION_ACTIVE_STATUSES else status
        company = {
            "id": company_id,
            "name": company_name,
            "slug": category_slug(company_name),
            "legalName": legal_name or company_name,
            "taxId": tax_id,
            "country": profile["code"],
            "currency": profile["localCurrency"],
            "baseCurrency": profile["salesCurrency"],
            "marketProfile": profile,
            "taxLabel": profile["taxLabel"],
            "planCurrency": pricing["currency"],
            "planPrice": pricing["price"],
            "purchaseConditions": {
                "title": "Condiciones de compra",
                "defaultSaleType": "cash",
                "allowedPaymentTermsDays": list(PAYMENT_TERM_OPTIONS),
                "scopeLabel": "Solo datos de tu empresa",
                "note": "Pedidos sujetos a validacion de stock, credito y despacho.",
            },
            "status": company_status,
            "planId": SAAS_PLAN_ID,
            "planName": SAAS_PLAN_NAME,
            "planPriceClp": pricing["priceClp"],
            "ownerName": owner_name,
            "ownerEmail": owner_email,
            "supportPhone": support_phone,
            "desktopAccessPreference": access_preference,
            "mobileAppAccessRequested": mobile_app_access_requested,
            "createdAt": now,
            "updatedAt": now,
        }
        subscription = {
            "id": next_id("sub", company_id),
            "companyId": company_id,
            "planId": SAAS_PLAN_ID,
            "planName": SAAS_PLAN_NAME,
            "status": status,
            "billingPeriod": "monthly",
            "country": profile["code"],
            "currency": pricing["currency"],
            "price": pricing["price"],
            "priceClp": pricing["priceClp"],
            "currentPeriodStart": now if status in SUBSCRIPTION_ACTIVE_STATUSES else "",
            "currentPeriodEnd": "",
            "trialEndsAt": "",
            "lastPaymentAt": now if status == "active" else "",
            "nextPaymentAt": next_payment_at,
            "createdAt": now,
            "updatedAt": now,
        }
        admin_user = {
            "id": next_id("admin", owner_email),
            "companyId": company_id,
            "firstName": owner_name,
            "lastName": "",
            "name": owner_name,
            "email": owner_email,
            "role": "super_admin",
            "status": "active",
            "passwordHash": generate_password_hash(password),
            "mustChangePassword": True,
            "sellerCode": "",
            "sellerZone": "",
            "sellerTerritory": "",
            "sellerSupervisor": "",
            "phone": support_phone,
            "mobileAccessEnabled": mobile_app_access_requested,
            "internalNotes": "Administrador inicial creado desde Empresas SaaS.",
            "commissionRatePercent": 0,
            "salesGoalUsd": 0,
            "failedLoginAttempts": 0,
            "lastFailedLoginAt": "",
            "lastLoginAt": "",
            "lastLoginIp": "",
            "sessionVersion": 0,
            "createdAt": now,
            "updatedAt": now,
        }
        store.setdefault("companies", []).append(company)
        store.setdefault("subscriptions", []).append(subscription)
        store.setdefault("admin_users", []).append(admin_user)
        record_create_event(store, "company", company_id, f"Empresa SaaS creada: {company_name}.", company)
        record_create_event(store, "subscription", subscription["id"], f"Suscripcion creada para {company_name}.", subscription)
        record_create_event(store, "admin_user", admin_user["id"], f"Administrador inicial creado: {owner_email}.", admin_user)
        save_store(store)
        push_admin_toast("Empresa SaaS creada correctamente.", "success", "Empresa activada")
        return render_template(
            "platform_companies.html",
            **platform_companies_page_context(
                load_store(),
                temporary_password=password if generated_password else "",
                created_email=owner_email,
            ),
        )

    return render_template("platform_companies.html", **platform_companies_page_context(store))


@app.post("/platform/companies/<company_id>/subscription")
@require_roles("platform_admin")
def company_subscription_update(company_id: str):
    store = load_store()
    company = get_company(store, company_id)
    if not company:
        return redirect(url_for("platform_companies"))

    status = request.form.get("subscriptionStatus", "active")
    if status not in dict(SUBSCRIPTION_STATUS_OPTIONS):
        push_admin_toast("Estado de suscripcion no valido.", "danger", "Accion no aplicada")
        return redirect(url_for("platform_companies"))

    next_payment_at = sanitize_text(request.form.get("nextPaymentAt", ""), max_length=32, allow_newlines=False)
    enable_mobile_access = request.form.get("enableMobileAccess") == "on"
    profile = market_profile(company.get("country") or "CL")
    pricing = plan_pricing_for_country(profile["code"])
    now = utc_now()
    before_company = copy.deepcopy(company)
    subscription = current_subscription(store, company_id)
    if subscription is None:
        subscription = {
            "id": next_id("sub", company_id),
            "companyId": company_id,
            "planId": SAAS_PLAN_ID,
            "planName": SAAS_PLAN_NAME,
            "billingPeriod": "monthly",
            "country": profile["code"],
            "currency": pricing["currency"],
            "price": pricing["price"],
            "priceClp": pricing["priceClp"],
            "createdAt": now,
        }
        store.setdefault("subscriptions", []).append(subscription)
    before_subscription = copy.deepcopy(subscription)

    company["status"] = "active" if status in SUBSCRIPTION_ACTIVE_STATUSES else status
    company["country"] = profile["code"]
    company["currency"] = profile["localCurrency"]
    company["baseCurrency"] = profile["salesCurrency"]
    company["marketProfile"] = profile
    company["planCurrency"] = pricing["currency"]
    company["planPrice"] = pricing["price"]
    company["planPriceClp"] = pricing["priceClp"]
    if enable_mobile_access:
        company["mobileAppAccessRequested"] = True
    company["updatedAt"] = now
    subscription["status"] = status
    subscription["country"] = profile["code"]
    subscription["price"] = pricing["price"]
    subscription["priceClp"] = pricing["priceClp"]
    subscription["currency"] = pricing["currency"]
    subscription["nextPaymentAt"] = next_payment_at
    subscription["updatedAt"] = now
    if status == "active" and not subscription.get("lastPaymentAt"):
        subscription["lastPaymentAt"] = now
    if enable_mobile_access:
        for user in store.get("admin_users", []):
            if user.get("companyId") == company_id and user.get("role") in WEB_ADMIN_ROLES and user.get("status") == "active":
                user["mobileAccessEnabled"] = True
                user["updatedAt"] = now

    record_change_event(
        store,
        "subscription_update",
        "company",
        company_id,
        f"Estado de suscripcion actualizado a {subscription_status_label(status)} para {company.get('name', company_id)}.",
        {"company": before_company, "subscription": before_subscription},
        {"company": company, "subscription": subscription},
    )
    save_store(store)
    push_admin_toast("Suscripcion actualizada.", "success", "Empresa SaaS")
    return redirect(url_for("platform_companies"))


def account_deletion_subject_for_company(
    store: dict,
    subject_type: str,
    subject_id: str,
    company_id: str = "",
) -> dict | None:
    collection = "clients" if subject_type == "client" else "admin_users" if subject_type == "admin_user" else ""
    if not collection:
        return None
    matches = [
        subject
        for subject in store.get(collection, [])
        if subject.get("id") == subject_id
    ]
    if company_id:
        matches = [
            subject
            for subject in matches
            if record_company_id(subject, store) == company_id
        ]
    return matches[0] if matches else None


def account_deletion_open_orders_for_client(store: dict, client_id: str, company_id: str = "") -> int:
    return sum(
        1
        for order in store.get("orders", [])
        if order.get("customerId") == client_id
        and (not company_id or record_company_id(order, store) == company_id)
        and order.get("status") not in {"cancelled", "rejected", "paid"}
    )


def account_deletion_subject_rows(store: dict) -> list[dict]:
    companies_by_id = {company.get("id"): company for company in store.get("companies", [])}
    rows: list[dict] = []
    for subject_type, collection in (("client", "clients"), ("admin_user", "admin_users")):
        for subject in store.get(collection, []):
            status = mobile_account_deletion_status(subject)
            if not status:
                continue
            company_id = record_company_id(subject, store)
            company = companies_by_id.get(company_id, {})
            rows.append(
                {
                    "id": subject.get("deletionRequestId") or subject.get("id", ""),
                    "subjectType": subject_type,
                    "subjectId": subject.get("id", ""),
                    "subjectLabel": subject.get("businessName") or subject.get("name") or subject.get("email", ""),
                    "email": subject.get("email", ""),
                    "companyId": company_id,
                    "companyName": company.get("name", "Empresa sin nombre"),
                    "role": "Cliente B2B" if subject_type == "client" else ROLE_LABELS.get(subject.get("role", ""), subject.get("role", "")),
                    "status": status,
                    "statusLabel": account_deletion_status_label(status),
                    "badgeClass": account_deletion_status_badge(status),
                    "channel": subject.get("deletionRequestChannel", ""),
                    "reason": subject.get("deletionRequestReason", ""),
                    "requestedAt": subject.get("deletionRequestedAt", ""),
                    "updatedAt": subject.get("updatedAt", ""),
                    "completedAt": subject.get("deletionCompletedAt", ""),
                    "resolutionNote": subject.get("deletionResolutionNote", ""),
                    "requiresVerification": False,
                    "accessBlocked": mobile_account_access_blocked(subject),
                    "openOrders": (
                        account_deletion_open_orders_for_client(store, subject.get("id", ""), company_id)
                        if subject_type == "client"
                        else 0
                    ),
                }
            )
    for request_record in store.get("account_deletion_requests", []):
        status = str(request_record.get("status") or "requested").strip().lower()
        subject_type = str(request_record.get("subjectType") or "unknown").strip().lower()
        if subject_type not in {"client", "admin_user", "unknown"}:
            subject_type = "unknown"
        subject_id = request_record.get("subjectId", "")
        request_company_id = request_record.get("companyId", "")
        subject = account_deletion_subject_for_company(store, subject_type, subject_id, request_company_id)
        if subject and mobile_account_deletion_status(subject):
            continue
        company_id = request_company_id
        if subject and not company_id:
            company_id = record_company_id(subject, store)
        company = companies_by_id.get(company_id, {})
        open_orders = (
            account_deletion_open_orders_for_client(store, subject_id, company_id)
            if subject_type == "client"
            else 0
        )
        rows.append(
            {
                "id": request_record.get("id", ""),
                "subjectType": subject_type,
                "subjectId": subject_id if subject_type != "unknown" else request_record.get("id", ""),
                "subjectLabel": request_record.get("subjectLabel") or "Correo no encontrado",
                "email": request_record.get("email", ""),
                "companyId": company_id,
                "companyName": request_record.get("companyName") or company.get("name", "") or "Sin empresa asociada",
                "role": request_record.get("role") or "Solicitud publica",
                "status": status,
                "statusLabel": account_deletion_status_label(status),
                "badgeClass": account_deletion_status_badge(status),
                "channel": request_record.get("channel", ""),
                "reason": request_record.get("reason", ""),
                "requestedAt": request_record.get("createdAt", ""),
                "updatedAt": request_record.get("updatedAt", ""),
                "completedAt": request_record.get("closedAt", ""),
                "resolutionNote": request_record.get("resolutionNote", ""),
                "requiresVerification": bool(request_record.get("requiresVerification", subject_type != "unknown")),
                "accessBlocked": bool(request_record.get("accessBlocked", False)),
                "openOrders": open_orders,
            }
        )
    return sorted(rows, key=lambda row: row.get("requestedAt") or row.get("updatedAt") or "", reverse=True)


def platform_privacy_context(store: dict) -> dict:
    rows = account_deletion_subject_rows(store)
    selected_status = request.args.get("status", "").strip().lower()
    selected_type = request.args.get("type", "").strip().lower()
    selected_company = request.args.get("company", "").strip()
    query = normalize_search_text(request.args.get("q", ""))
    filtered_rows = []
    for row in rows:
        if selected_status and row["status"] != selected_status:
            continue
        if selected_type and row["subjectType"] != selected_type:
            continue
        if selected_company and row["companyId"] != selected_company:
            continue
        searchable = normalize_search_text(" ".join([row["subjectLabel"], row["email"], row["companyName"], row["role"]]))
        if query and query not in searchable:
            continue
        filtered_rows.append(row)

    pending_statuses = {"requested", "processing", "approved"}
    metrics = {
        "total": len(rows),
        "pending": sum(1 for row in rows if row["status"] in pending_statuses),
        "completed": sum(1 for row in rows if row["status"] in {"deleted", "closed_no_account"}),
        "rejected": sum(1 for row in rows if row["status"] == "rejected"),
    }
    return {
        "heading": "Privacidad plataforma",
        "description": "Gestiona solicitudes de eliminacion de cuenta, bloqueo movil y trazabilidad normativa por empresa.",
        "rows": filtered_rows,
        "metrics": metrics,
        "filters": {
            "q": request.args.get("q", ""),
            "status": selected_status,
            "type": selected_type,
            "company": selected_company,
        },
        "status_options": [
            ("", "Todos"),
            ("requested", "Solicitadas"),
            ("processing", "En revision"),
            ("approved", "Aprobadas"),
            ("deleted", "Eliminadas"),
            ("rejected", "Rechazadas"),
            ("closed_no_account", "Sin cuenta"),
        ],
        "type_options": [
            ("", "Todos"),
            ("client", "Clientes"),
            ("admin_user", "Vendedores/admin"),
            ("unknown", "No encontradas"),
        ],
        "companies": sorted(store.get("companies", []), key=lambda company: company.get("name", "")),
    }


@app.get("/platform/privacy")
@require_roles("platform_admin")
def platform_privacy():
    store = load_store()
    return render_template("platform_privacy.html", **platform_privacy_context(store))


@app.get("/platform/privacy/export")
@require_roles("platform_admin")
def platform_privacy_export():
    store = load_store()
    output = io.StringIO()
    fieldnames = [
        "solicitud",
        "tipo",
        "cuenta",
        "email",
        "empresa",
        "estado",
        "canal",
        "solicitada",
        "actualizada",
        "cerrada",
        "ordenes_abiertas",
        "motivo",
        "resolucion",
    ]
    writer = safe_csv_dict_writer(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in platform_privacy_context(store)["rows"]:
        writer.writerow(
            {
                "solicitud": row["id"],
                "tipo": row["role"],
                "cuenta": row["subjectLabel"],
                "email": row["email"],
                "empresa": row["companyName"],
                "estado": row["statusLabel"],
                "canal": row["channel"],
                "solicitada": row["requestedAt"],
                "actualizada": row["updatedAt"],
                "cerrada": row["completedAt"],
                "ordenes_abiertas": row["openOrders"],
                "motivo": row["reason"],
                "resolucion": row["resolutionNote"],
            }
        )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=privacidad_solicitudes_eliminacion.csv"},
    )


def pending_account_deletion_request_for_subject(
    store: dict,
    subject_type: str,
    subject_id: str,
    company_id: str = "",
) -> dict | None:
    return next(
        (
            item
            for item in store.get("account_deletion_requests", [])
            if item.get("subjectType") == subject_type
            and item.get("subjectId") == subject_id
            and (not company_id or item.get("companyId") == company_id)
            and item.get("status") in {"requested", "processing", "approved"}
        ),
        None,
    )


@app.post("/platform/privacy/account-deletion/<subject_type>/<subject_id>/<action>")
@require_roles("platform_admin")
def platform_privacy_deletion_action(subject_type: str, subject_id: str, action: str):
    store = load_store()
    note = sanitize_text(request.form.get("resolutionNote", ""), max_length=500, allow_newlines=True)
    request_company_id = sanitize_text(request.form.get("companyId", ""), max_length=120, allow_newlines=False)
    now = utc_now()
    actor = {
        "id": session.get("admin_user_id", ""),
        "name": session.get("admin_name", "FVENTAS Admin"),
        "role": current_admin_role(),
    }

    if subject_type == "unknown":
        request_record = find_by_id(store.get("account_deletion_requests", []), subject_id)
        if not request_record:
            push_admin_toast("No se encontro la solicitud.", "warning", "Privacidad")
            return redirect(url_for("platform_privacy"))
        if request_company_id and request_record.get("companyId", "") != request_company_id:
            push_admin_toast("La solicitud no pertenece a la empresa indicada.", "danger", "Privacidad")
            return redirect(url_for("platform_privacy"))
        before = copy.deepcopy(request_record)
        if action == "processing":
            request_record["status"] = "processing"
        elif action == "approve":
            request_record["status"] = "approved"
        elif action == "reject":
            request_record["status"] = "rejected"
            request_record["rejectedAt"] = now
        elif action == "complete":
            request_record["status"] = "closed_no_account"
            request_record["closedAt"] = now
        else:
            push_admin_toast("Accion no valida.", "danger", "Privacidad")
            return redirect(url_for("platform_privacy"))
        request_record["resolutionNote"] = note
        request_record["updatedAt"] = now
        record_change_event(
            store,
            f"account_deletion_{action}",
            "account_deletion_request",
            subject_id,
            "Solicitud de eliminacion sin cuenta asociada actualizada por plataforma.",
            before,
            request_record,
            actor=actor,
            criticality="medium",
        )
        save_store(store)
        push_admin_toast("Solicitud actualizada.", "success", "Privacidad")
        return redirect(url_for("platform_privacy"))

    subject = account_deletion_subject_for_company(store, subject_type, subject_id, request_company_id)
    if not subject:
        push_admin_toast("No se encontro la cuenta solicitada.", "warning", "Privacidad")
        return redirect(url_for("platform_privacy"))

    subject_company_id = record_company_id(subject, store)
    linked_request = pending_account_deletion_request_for_subject(
        store,
        subject_type,
        subject_id,
        request_company_id or subject_company_id,
    )
    status = mobile_account_deletion_status(subject)
    if linked_request and not status:
        if action == "reject":
            before_request = copy.deepcopy(linked_request)
            linked_request["status"] = "rejected"
            linked_request["rejectedAt"] = now
            linked_request["rejectedById"] = actor["id"]
            linked_request["rejectedByName"] = actor["name"]
            linked_request["resolutionNote"] = note
            linked_request["updatedAt"] = now
            record_change_event(
                store,
                "account_deletion_reject",
                "account_deletion_request",
                linked_request["id"],
                "Solicitud publica de eliminacion rechazada sin bloquear la cuenta asociada.",
                before_request,
                linked_request,
                actor=actor,
                criticality="medium",
            )
            save_store(store)
            push_admin_toast("Solicitud rechazada sin cambios en la cuenta.", "success", "Privacidad")
            return redirect(url_for("platform_privacy"))
        if action == "complete":
            push_admin_toast("Primero valida la solicitud para bloquear acceso antes del cierre.", "warning", "Privacidad")
            return redirect(url_for("platform_privacy"))
        if action in {"processing", "approve"}:
            request_id, _ = request_mobile_account_deletion(
                store,
                subject_type,
                subject,
                channel=linked_request.get("channel") or "web",
                reason=linked_request.get("reason", ""),
                actor=actor,
            )
            linked_request["linkedRequestId"] = request_id
            linked_request["accessBlocked"] = True
            linked_request["requiresVerification"] = False
            linked_request["verifiedAt"] = now
            linked_request["verifiedById"] = actor["id"]
            linked_request["verifiedByName"] = actor["name"]
            linked_request["updatedAt"] = now
            status = mobile_account_deletion_status(subject)
    if status not in {"requested", "processing", "approved"} and action not in {"processing", "approve"}:
        push_admin_toast("La cuenta no tiene una solicitud pendiente.", "warning", "Privacidad")
        return redirect(url_for("platform_privacy"))

    before = copy.deepcopy(subject)
    if action == "processing":
        subject["deletionStatus"] = "processing"
        subject["deletionProcessingAt"] = now
        subject["mobileAccess"] = "deletion_requested"
        subject["mobileAccessEnabled"] = False
        subject["mobileAccessBlocked"] = True
        if subject_type == "client":
            sync_client_mobile_access_state(subject, before)
        elif before.get("mobileAccessEnabled", True) is not False:
            bump_user_session_version(subject)
        detail = "Solicitud de eliminacion marcada en revision por plataforma."
    elif action == "approve":
        subject["deletionStatus"] = "approved"
        subject["deletionApprovedAt"] = now
        subject["deletionApprovedById"] = actor["id"]
        subject["deletionApprovedByName"] = actor["name"]
        subject["mobileAccess"] = "deletion_requested"
        subject["mobileAccessEnabled"] = False
        subject["mobileAccessBlocked"] = True
        if subject_type == "client":
            sync_client_mobile_access_state(subject, before)
        elif before.get("mobileAccessEnabled", True) is not False:
            bump_user_session_version(subject)
        detail = "Solicitud de eliminacion aprobada para cierre por plataforma."
    elif action == "reject":
        subject["deletionStatus"] = "rejected"
        subject["deletionRejectedAt"] = now
        subject["deletionRejectedById"] = actor["id"]
        subject["deletionRejectedByName"] = actor["name"]
        subject["deletionResolutionNote"] = note
        subject["mobileAccess"] = ""
        subject["mobileAccessBlocked"] = False
        if subject_type == "admin_user":
            subject["mobileAccessEnabled"] = subject.get("status") == "active"
            bump_user_session_version(subject)
        else:
            subject["mobileAccessEnabled"] = subject.get("status") == "active"
            subject["mobileSessionVersion"] = safe_int(subject.get("mobileSessionVersion"), 0) + 1
        detail = "Solicitud de eliminacion rechazada y acceso movil restablecido si la cuenta sigue activa."
    elif action == "complete":
        if subject_type == "client":
            before, changed_orders = complete_client_account_deletion(store, subject)
            metadata = {
                "requestId": before.get("deletionRequestId", ""),
                "ordersAnonymized": len(changed_orders),
                "policy": "account-erasure-platform-review",
            }
        else:
            before, changed_clients, changed_orders = complete_admin_user_account_deletion(store, subject)
            metadata = {
                "requestId": before.get("deletionRequestId", ""),
                "clientsRelabeled": len(changed_clients),
                "ordersRelabeled": len(changed_orders),
                "policy": "account-erasure-platform-review",
            }
        subject["deletionResolutionNote"] = note
        if linked_request:
            linked_request["status"] = "deleted"
            linked_request["linkedRequestId"] = subject.get("deletionRequestId", linked_request.get("linkedRequestId", ""))
            linked_request["accessBlocked"] = True
            linked_request["requiresVerification"] = False
            linked_request["closedAt"] = subject.get("deletionCompletedAt", now)
            linked_request["resolutionNote"] = note
            linked_request["updatedAt"] = now
        record_change_event(
            store,
            "account_deletion_completed",
            subject_type,
            subject_id,
            "Solicitud de eliminacion cerrada por plataforma: cuenta anonima y acceso movil bloqueado.",
            before,
            subject,
            actor=actor,
            criticality="high",
            metadata=metadata,
        )
        save_store(store)
        push_admin_toast("Cuenta anonimizada y cerrada.", "success", "Privacidad")
        return redirect(url_for("platform_privacy"))
    else:
        push_admin_toast("Accion no valida.", "danger", "Privacidad")
        return redirect(url_for("platform_privacy"))

    subject["deletionResolutionNote"] = note
    subject["updatedAt"] = now
    if linked_request:
        linked_request["status"] = subject.get("deletionStatus", linked_request.get("status", ""))
        linked_request["linkedRequestId"] = subject.get("deletionRequestId", linked_request.get("linkedRequestId", ""))
        linked_request["accessBlocked"] = mobile_account_access_blocked(subject)
        linked_request["requiresVerification"] = False
        linked_request["resolutionNote"] = note
        linked_request["updatedAt"] = now
    record_change_event(
        store,
        f"account_deletion_{action}",
        subject_type,
        subject_id,
        detail,
        before,
        subject,
        actor=actor,
        criticality="high",
        metadata={"requestId": before.get("deletionRequestId", "")},
    )
    save_store(store)
    push_admin_toast("Solicitud actualizada.", "success", "Privacidad")
    return redirect(url_for("platform_privacy"))


@app.get("/permissions")
@require_roles(*ADMIN_ONLY_ROLES)
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
@require_roles(*ADMIN_ONLY_ROLES)
def admin_users():
    store = load_store()
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        error = admin_user_form_error(store)
        if error:
            return render_template("admin_users.html", **admin_users_page_context(store, error))
        user = admin_user_payload()
        store["admin_users"].append(user)
        record_create_event(store, "admin_user", user["id"], f"Usuario admin creado: {email}.", user)
        save_store(store)
        return redirect(url_for("admin_users"))

    return render_template("admin_users.html", **admin_users_page_context(store))


@app.post("/admin-users/<user_id>/edit")
@require_roles(*ADMIN_ONLY_ROLES)
def admin_user_edit(user_id: str):
    store = load_store()
    user = find_company_record(store, "admin_users", user_id)
    if user and user.get("role") == "sales":
        return forbidden_response()
    if user:
        error = admin_user_form_error(store, user)
        if error:
            return render_template("admin_users.html", **admin_users_page_context(store, error))
        before = copy.deepcopy(user)
        updated = admin_user_payload(user)
        replace_company_record(store, "admin_users", user, updated)
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
@require_roles(*ADMIN_ONLY_ROLES)
def admin_user_delete(user_id: str):
    store = load_store()
    user = find_company_record(store, "admin_users", user_id)
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
@require_roles(*ADMIN_ONLY_ROLES)
def admin_user_status(user_id: str):
    store = load_store()
    user = find_company_record(store, "admin_users", user_id)
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
@require_roles(*ADMIN_ONLY_ROLES)
def admin_user_reset_password(user_id: str):
    store = load_store()
    user = find_company_record(store, "admin_users", user_id)
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
@require_roles(*ADMIN_ONLY_ROLES)
def admin_user_revoke_sessions(user_id: str):
    store = load_store()
    user = find_company_record(store, "admin_users", user_id)
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
            seller["sellerCode"] = seller["id"].replace("admin-", "CL-").upper()[:24]
        audit_events_start = len(store.get("audit_events", []))
        store["admin_users"].append(seller)
        record_create_event(store, "seller", seller["id"], f"Vendedor creado: {seller['name']}.", seller)
        if not persist_seller_action(store, [seller], audit_events_start, "crear vendedor"):
            remove_company_record(store, "admin_users", seller)
            error = "No se pudo guardar el vendedor. Intenta nuevamente."
            return render_template("sellers.html", **sellers_page_context(store, error))
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
    seller = find_company_record(store, "admin_users", seller_id)
    if seller and seller.get("role") == "sales":
        error = seller_form_error(store, seller)
        if error:
            return render_template("sellers.html", **sellers_page_context(store, error))
        before = copy.deepcopy(seller)
        updated = admin_user_payload(seller)
        updated["role"] = "sales"
        replace_company_record(store, "admin_users", seller, updated)
        changed_clients: list[dict] = []
        for client in visible_records_for_current_company(store, "clients"):
            if client.get("assignedSellerId") == seller_id:
                client["assignedSellerName"] = updated.get("name", "")
                client["updatedAt"] = utc_now()
                changed_clients.append(client)
        changed_orders: list[dict] = []
        for order in visible_records_for_current_company(store, "orders"):
            if order.get("sellerId") == seller_id:
                order["sellerName"] = updated.get("name", "")
                order["updatedAt"] = utc_now()
                changed_orders.append(order)
        audit_events_start = len(store.get("audit_events", []))
        record_change_event(
            store,
            "update",
            "seller",
            seller_id,
            f"Vendedor actualizado: {updated['name']}.",
            before,
            updated,
        )
        if not persist_seller_action(
            store,
            [updated],
            audit_events_start,
            "editar vendedor",
            changed_clients=changed_clients,
            changed_orders=changed_orders,
        ):
            replace_company_record(store, "admin_users", updated, before)
            error = "No se pudo actualizar el vendedor. Intenta nuevamente."
            return render_template("sellers.html", **sellers_page_context(store, error))
    return redirect(url_for("sellers"))


@app.post("/sellers/<seller_id>/delete")
@require_roles(*roles_for_action("sellers", "delete"))
def seller_delete(seller_id: str):
    store = load_store()
    seller = find_company_record(store, "admin_users", seller_id)
    if not seller or seller.get("role") != "sales":
        return redirect(url_for("sellers"))
    before = copy.deepcopy(seller)
    has_clients = any(client.get("assignedSellerId") == seller_id for client in visible_records_for_current_company(store, "clients"))
    has_orders = any(order.get("sellerId") == seller_id for order in visible_records_for_current_company(store, "orders"))
    if has_clients or has_orders:
        seller["status"] = "inactive"
        seller["mobileAccessEnabled"] = False
        seller["updatedAt"] = utc_now()
        after = seller
    else:
        remove_company_record(store, "admin_users", seller)
        after = None
    audit_events_start = len(store.get("audit_events", []))
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
    if not persist_seller_action(
        store,
        [after] if after else [],
        audit_events_start,
        "eliminar vendedor",
        deleted_user_ids=[] if after else [seller_id],
    ):
        if after:
            seller.update(before)
        else:
            store["admin_users"].append(before)
        return redirect(url_for("sellers"))
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
        audit_events_start = len(store.get("audit_events", []))
        notifications_start = len(store.get("notifications", []))
        client = client_payload()
        store["clients"].append(client)
        record_create_event(store, "client", client["id"], f"Cliente creado: {client['businessName']}.", client)
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
            deep_link=f"fventas://seller/clients/{client['id']}",
            metadata={"clientId": client["id"]},
            dedupe_key=f"seller-client-assigned-{client['id']}",
        )
        if not persist_client_action(store, [client], audit_events_start, "crear cliente", notifications_start):
            remove_company_record(store, "clients", client)
            store["audit_events"] = store.get("audit_events", [])[:audit_events_start]
            store["notifications"] = store.get("notifications", [])[:notifications_start]
            error = "No se pudo guardar el cliente. Intenta nuevamente."
            return render_template("clients.html", **clients_page_context(store, error))
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
    client = find_company_record(store, "clients", client_id)
    if not can_access_client_record(client, store):
        return forbidden_response()
    if client:
        error = client_form_error(store, client)
        if error:
            return render_template("clients.html", **clients_page_context(store, error))
        before = copy.deepcopy(client)
        audit_events_start = len(store.get("audit_events", []))
        notifications_start = len(store.get("notifications", []))
        updated = client_payload(client)
        replace_company_record(store, "clients", client, updated)
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
                deep_link=f"fventas://seller/clients/{updated['id']}",
                metadata={"clientId": updated["id"]},
                dedupe_key=f"seller-client-assigned-{updated['id']}-{updated.get('updatedAt', '')}",
            )
        if not persist_client_action(store, [updated], audit_events_start, "editar cliente", notifications_start):
            replace_company_record(store, "clients", updated, before)
            store["audit_events"] = store.get("audit_events", [])[:audit_events_start]
            store["notifications"] = store.get("notifications", [])[:notifications_start]
            error = "No se pudo actualizar el cliente. Intenta nuevamente."
            return render_template("clients.html", **clients_page_context(store, error))
    return redirect(url_for("clients"))


@app.post("/clients/<client_id>/status")
@require_roles(*roles_for_action("clients", "edit"))
def client_status_update(client_id: str):
    store = load_store()
    client = find_company_record(store, "clients", client_id)
    if not can_access_client_record(client, store):
        return forbidden_response()
    target_status = request.form.get("status", "").strip()
    allowed_statuses = {status for status, _label in CLIENT_STATUS_OPTIONS}
    if not client or target_status not in allowed_statuses:
        return redirect(url_for("clients"))
    before = copy.deepcopy(client)
    audit_events_start = len(store.get("audit_events", []))
    notifications_start = len(store.get("notifications", []))
    client["status"] = target_status
    client["updatedAt"] = utc_now()
    client["updatedVia"] = "admin"
    client["updatedById"] = session.get("admin_user_id", "")
    client["updatedByName"] = session.get("admin_name", "FVENTAS Admin")
    client["updatedByRole"] = current_admin_role()
    sync_client_mobile_access_state(client, before, allow_reenable=True)
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
    if not persist_client_action(store, [client], audit_events_start, "cambiar estado cliente", notifications_start):
        client.update(before)
        store["audit_events"] = store.get("audit_events", [])[:audit_events_start]
        store["notifications"] = store.get("notifications", [])[:notifications_start]
    return redirect(url_for("clients"))


@app.post("/clients/<client_id>/account-deletion/complete")
@require_roles(*roles_for_action("clients", "delete"))
def client_account_deletion_complete(client_id: str):
    store = load_store()
    client = find_company_record(store, "clients", client_id)
    if not client:
        push_admin_toast("No se encontro el cliente solicitado.", "warning", "Cliente no encontrado")
        return redirect(url_for("clients"))

    deletion_status = mobile_account_deletion_status(client)
    if deletion_status not in {"requested", "processing", "approved"}:
        push_admin_toast(
            "Este cliente no tiene una solicitud de eliminacion pendiente.",
            "warning",
            "Sin solicitud pendiente",
        )
        return redirect(url_for("clients"))

    audit_events_start = len(store.get("audit_events", []))
    notifications_start = len(store.get("notifications", []))
    before, changed_orders = complete_client_account_deletion(store, client)

    record_change_event(
        store,
        "account_deletion_completed",
        "client",
        client_id,
        "Solicitud de eliminacion cerrada: acceso movil bloqueado y datos personales anonimizados.",
        before,
        client,
        actor={
            "id": session.get("admin_user_id", ""),
            "name": session.get("admin_name", "FVENTAS Admin"),
            "role": current_admin_role(),
        },
        criticality="high",
        metadata={
            "requestId": before.get("deletionRequestId", ""),
            "ordersAnonymized": len(changed_orders),
            "policy": "android-ios-account-deletion",
        },
    )
    notify_admin(
        store,
        "Cuenta B2B eliminada",
        f"La solicitud de eliminacion de {before.get('businessName', client_id)} fue procesada.",
        notification_type="success",
        priority="normal",
        module="clients",
        entity_type="client",
        entity_id=client_id,
        dedupe_key=f"account-deletion-completed-{client_id}-{client.get('deletionCompletedAt', '')}",
        metadata={"ordersAnonymized": len(changed_orders)},
    )
    push_admin_toast(
        "Cuenta anonimizada y acceso movil bloqueado correctamente.",
        "success",
        "Solicitud cerrada",
    )
    if not persist_client_action(
        store,
        [client],
        audit_events_start,
        "cerrar eliminacion de cuenta",
        notifications_start,
        changed_orders=changed_orders,
    ):
        client.clear()
        client.update(before)
        store["audit_events"] = store.get("audit_events", [])[:audit_events_start]
        store["notifications"] = store.get("notifications", [])[:notifications_start]
        push_admin_toast(
            "No se pudo procesar la eliminacion de cuenta. Intenta nuevamente.",
            "danger",
            "Accion no aplicada",
        )
    return redirect(url_for("clients"))


@app.post("/clients/<client_id>/delete")
@require_roles(*roles_for_action("clients", "delete"))
def client_delete(client_id: str):
    store = load_store()
    client = find_company_record(store, "clients", client_id)
    if not client:
        return redirect(url_for("clients"))
    before = copy.deepcopy(client)
    audit_events_start = len(store.get("audit_events", []))
    has_orders = any(order.get("customerId") == client_id for order in visible_records_for_current_company(store, "orders"))
    if has_orders:
        client["status"] = "inactive"
        client["updatedAt"] = utc_now()
        client["updatedVia"] = "admin"
        client["updatedById"] = session.get("admin_user_id", "")
        client["updatedByName"] = session.get("admin_name", "FVENTAS Admin")
        client["updatedByRole"] = current_admin_role()
        after = client
    else:
        remove_company_record(store, "clients", client)
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
    if not persist_client_action(
        store,
        [after] if after else [],
        audit_events_start,
        "eliminar cliente",
        deleted_client_ids=[] if after else [client_id],
    ):
        if after:
            client.update(before)
        else:
            store["clients"].append(before)
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
        "precio_publico",
        "precio_b2b",
        "precio_anterior",
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
        "notas_compatibilidad",
    ]
    writer = safe_csv_dict_writer(output, fieldnames=fieldnames, lineterminator="\n")
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
                "precio_publico": product.get("publicPriceUsd", 0),
                "precio_b2b": product.get("b2bPriceUsd", 0),
                "precio_anterior": product.get("originalPriceUsd", 0),
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
                "notas_compatibilidad": "|".join(product.get("compatibilityNotes") or []),
            }
        )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=productos_fventas.csv"},
    )


@app.post("/products/import")
@require_roles(*roles_for_action("products", "import"))
def products_import():
    return handle_bulk_import("products", "product", import_products_rows, "products")


@app.post("/products/starter-fventas")
@require_roles(*roles_for_action("products", "create"))
def products_starter_fventas():
    store = load_store()
    before = {
        "products": len(visible_records_for_current_company(store, "products")),
        "categories": len(
            [category for category in visible_records_for_current_company(store, "categories") if category.get("status") != "deleted"]
        ),
    }
    try:
        result = create_fventas_starter_products(store)
    except Exception:
        app.logger.exception("No se pudieron preparar productos base FVENTAS")
        push_admin_toast(
            "No se pudieron preparar los productos base FVENTAS. Revisa las categorias o intenta nuevamente.",
            "danger",
            "Seed no preparado",
        )
        return redirect(url_for("products"))

    created_count = len(result["created"])
    created_categories_count = len(result.get("categories", {}).get("created", []))
    if created_count or created_categories_count:
        audit_events_start = len(store.get("audit_events", []))
        created_skus = {item.get("sku", "").strip().upper() for item in result["created"]}
        created_category_ids = {
            item.get("id", "")
            for item in result.get("categories", {}).get("created", [])
            if item.get("id")
        }
        changed_products = [
            product
            for product in store.get("products", [])
            if product.get("sku", "").strip().upper() in created_skus
        ]
        changed_categories = [
            category for category in store.get("categories", []) if category.get("id") in created_category_ids
        ]
        after = {
            "products": len(visible_records_for_current_company(store, "products")),
            "categories": len(
                [category for category in visible_records_for_current_company(store, "categories") if category.get("status") != "deleted"]
            ),
            "created": result["created"],
            "existing": result["existing"],
            "missingCategories": result["missingCategories"],
            "createdCategories": result.get("categories", {}).get("created", []),
        }
        record_change_event(
            store,
            "create",
            "product_seed",
            "fventas-base",
            f"Productos base FVENTAS creados: {created_count}. Categorias creadas: {created_categories_count}.",
            before,
            after,
        )
        if persist_product_seed_action(
            store,
            changed_categories,
            changed_products,
            audit_events_start,
            "productos base FVENTAS",
        ):
            push_admin_toast(
                f"Se crearon {created_count} productos base FVENTAS con SKU, imagen, precio y stock inicial.",
                "success",
                "Productos listos",
            )
    else:
        push_admin_toast(
            "Los productos base FVENTAS ya existen o requieren revisar categorias faltantes.",
            "info" if not result["missingCategories"] else "warning",
            "Sin cambios",
        )
    return redirect(url_for("products"))


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
    product = find_company_record(store, "products", product_id)
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
        replace_company_record(store, "products", product, updated)
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
    product = find_company_record(store, "products", product_id)
    if not product:
        return redirect(url_for("products"))
    existing_skus = {item.get("sku", "").upper() for item in visible_records_for_current_company(store, "products")}
    base_sku = f"{product.get('sku', 'FVT-PROD').upper()}-COPY"
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
    product = find_company_record(store, "products", product_id)
    if not product:
        return redirect(url_for("products"))
    before = copy.deepcopy(product)
    has_history = product_has_commercial_history(store, product)
    if has_history:
        product["status"] = "inactive"
        product["updatedAt"] = utc_now()
        after = product
    else:
        remove_company_record(store, "products", product)
        store["media_assets"] = [
            item
            for item in store.get("media_assets", [])
            if item.get("productId") != product_id or not can_access_company_record(item, store)
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
        scoped_products = visible_records_for_current_company(store, "products")
        scoped_orders = visible_records_for_current_company(store, "orders")
        stock_before = {
            product["id"]: {
                "sku": product.get("sku", ""),
                "stock": int(product.get("stock") or 0),
                "minimumStock": int(product.get("minimumStock") or 0),
                "maximumStock": int(product.get("maximumStock") or 0),
                "stockLocation": product.get("stockLocation", ""),
                "stockNotes": product.get("stockNotes", ""),
            }
            for product in scoped_products
        }
        bulk_payload = request.form.get("bulkStock", "").strip()
        movement_type = normalize_stock_movement_type(request.form.get("type", "entry"))
        reserved_by_product = stock_reserved_quantities(scoped_orders)
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
            for product in scoped_products:
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
            product = find_company_record(store, "products", product_id)
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
            for product in scoped_products
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
        for product in scoped_products:
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
    writer = safe_csv_dict_writer(output, fieldnames=fieldnames, lineterminator="\n")
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
        headers={"Content-Disposition": "attachment; filename=stock_fventas.csv"},
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


@app.post("/categories/starter-fventas")
@require_roles(*roles_for_action("categories", "create"))
def categories_starter_fventas():
    store = load_store()
    before = {
        "total": len(
            [category for category in visible_records_for_current_company(store, "categories") if category.get("status") != "deleted"]
        )
    }
    audit_events_start = len(store.get("audit_events", []))
    result = create_fventas_starter_categories(store)
    created_count = len(result["created"])
    if created_count:
        created_ids = {category.get("id", "") for category in result["created"] if category.get("id")}
        changed_categories = [
            category for category in store.get("categories", []) if category.get("id") in created_ids
        ]
        after = {
            "total": len(
                [category for category in visible_records_for_current_company(store, "categories") if category.get("status") != "deleted"]
            ),
            "created": result["created"],
            "existing": result["existing"],
        }
        record_change_event(
            store,
            "create",
            "category_seed",
            "fventas-base",
            f"Categorias base FVENTAS creadas: {created_count}.",
            before,
            after,
        )
        if persist_category_action(store, changed_categories, audit_events_start, "categorias base FVENTAS"):
            push_admin_toast(f"Se crearon {created_count} categorias base FVENTAS.", "success", "Categorias listas")
        else:
            store["categories"] = [
                category for category in store.get("categories", []) if category.get("id") not in created_ids
            ]
            store["audit_events"] = store.get("audit_events", [])[:audit_events_start]
    else:
        push_admin_toast("Las categorias base FVENTAS ya existen. Puedes editarlas o agregar imagenes.", "info", "Sin cambios")
    return redirect(url_for("categories"))


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
        for category in visible_records_for_current_company(store, "categories")
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
    writer = safe_csv_dict_writer(output, fieldnames=fieldnames, lineterminator="\n")
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
        headers={"Content-Disposition": "attachment; filename=categorias_fventas.csv"},
    )


@app.post("/categories/import")
@require_roles(*roles_for_action("categories", "import"))
def categories_import():
    return handle_bulk_import("categories", "category", import_categories_rows, "categories")


@app.route("/categories/<category_id>/edit", methods=["POST"])
@require_roles(*roles_for_action("categories", "edit"))
def category_edit(category_id: str):
    store = load_store()
    category = find_company_record(store, "categories", category_id)
    if category:
        error = category_form_error(store, category)
        if error:
            return render_template("categories.html", **category_page_context(store, error))
        before = copy.deepcopy(category)
        category.update(category_payload(store, category))
        for product in visible_records_for_current_company(store, "products"):
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
    category = find_company_record(store, "categories", category_id)
    target_status = request.form.get("status", "").strip()
    if category and target_status in {key for key, _label in CATEGORY_STATUS_OPTIONS}:
        audit_events_start = len(store.get("audit_events", []))
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
        persist_category_action(
            store,
            [category],
            audit_events_start,
            f"status {category_id} -> {target_status}",
        )
    return redirect(url_for("categories"))


@app.post("/categories/<category_id>/delete")
@require_roles(*roles_for_action("categories", "delete"))
def category_delete(category_id: str):
    store = load_store()
    category = find_company_record(store, "categories", category_id)
    if not category:
        return redirect(url_for("categories"))
    audit_events_start = len(store.get("audit_events", []))
    before = copy.deepcopy(category)
    direct_children = [
        item
        for item in visible_records_for_current_company(store, "categories")
        if item.get("parentId") == category_id and item.get("status") != "deleted"
    ]
    product_references = product_count_for_categories(store, {category_id})
    if product_references:
        record_change_event(
            store,
            "delete_blocked",
            "category",
            category_id,
            f"Eliminacion bloqueada por productos asociados: {category.get('name', category_id)}.",
            before,
            category,
        )
        push_admin_toast(
            f"No se elimino: tiene {product_references} producto(s) asociado(s). Reasigna esos productos primero.",
            "warning",
            "Categoria protegida",
        )
        persist_category_action(
            store,
            [category],
            audit_events_start,
            f"blocked delete {category_id}",
        )
        return redirect(url_for("categories"))
    deleted_at = utc_now()
    changed_categories = []
    promoted_children = []
    for child in direct_children:
        child_before = copy.deepcopy(child)
        child["parentId"] = ""
        child["updatedAt"] = deleted_at
        changed_categories.append(child)
        promoted_children.append(child.get("id", ""))
        record_change_event(
            store,
            "parent_promoted",
            "category",
            child.get("id", ""),
            f"Subcategoria promovida a categoria raiz por eliminacion de {category.get('name', category_id)}.",
            child_before,
            child,
        )
    category["status"] = "deleted"
    category["visibleInApp"] = False
    category["deletedAt"] = deleted_at
    category["updatedAt"] = deleted_at
    changed_categories.append(category)
    remove_company_record(store, "categories", category)
    record_change_event(
        store,
        "delete",
        "category",
        category_id,
        f"Categoria eliminada: {category.get('name', category_id)}."
        + (f" Subcategorias promovidas: {len(promoted_children)}." if promoted_children else ""),
        before,
        None,
    )
    push_admin_toast("Categoria eliminada correctamente.", "warning", "Categoria eliminada")
    persist_category_action(
        store,
        changed_categories,
        audit_events_start,
        f"delete {category_id}",
    )
    return redirect(url_for("categories"))


@app.route("/media-library", methods=["GET", "POST"])
@require_roles(*roles_for_action("media_library", "view"))
def media_library():
    store = load_store()
    if request.method == "POST":
        if not can_module_action("media_library", "create"):
            return forbidden_response()
        product_id = request.form.get("productId", "")
        product = find_company_record(store, "products", product_id) if product_id else None
        if product_id and not product:
            return render_template(
                "media_library.html",
                products=visible_records_for_current_company(store, "products"),
                assets=[],
                bulk_result=consume_bulk_result("media_library"),
                error="Selecciona un producto valido para asociar el recurso.",
            ), 400
        asset_type = normalize_import_key(request.form.get("assetType", "image"))
        if asset_type not in {"image", "pdf"}:
            asset_type = "image"
        upload_extensions = PDF_UPLOAD_EXTENSIONS if asset_type == "pdf" else IMAGE_UPLOAD_EXTENSIONS
        uploaded_asset = save_upload(request.files.get("assetFile"), "library", allowed_extensions=upload_extensions)
        asset_url = uploaded_asset or sanitize_url(request.form.get("assetUrl", ""))
        title = sanitize_text(request.form.get("title", ""), max_length=180, allow_newlines=False) or "Activo FVENTAS"
        if asset_url:
            asset = {
                "companyId": current_company_id(store),
                "id": next_id("asset", title),
                "title": title,
                "assetType": asset_type,
                "productId": product_id,
                "url": asset_url,
                "createdAt": utc_now(),
            }
            store["media_assets"].append(asset)
            if product:
                if asset_type == "pdf":
                    product.setdefault("pdfUrls", []).append(asset_url)
                else:
                    product.setdefault("imageUrls", []).append(asset_url)
                    if not product.get("imageUrl"):
                        product["imageUrl"] = asset_url
            record_create_event(store, "media_asset", asset["id"], f"Recurso tecnico creado: {title}.", asset)
        save_store(store)
        return redirect(url_for("media_library"))

    products = visible_records_for_current_company(store, "products")
    product_lookup = {product["id"]: product for product in products}
    assets = []
    for asset in reversed(store.get("media_assets", [])):
        if document_is_asset(asset) or asset.get("status") == "deleted":
            continue
        if not can_access_company_record(asset, store):
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
    asset = find_company_record(store, "media_assets", asset_id)
    if asset:
        before = copy.deepcopy(asset)
        remove_company_record(store, "media_assets", asset)
        product = find_company_record(store, "products", asset.get("productId", ""))
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
        visibility = normalize_document_visibility(request.form.get("visibility", "internal"))
        uploaded_document = save_upload(
            request.files.get("documentFile"),
            "documents",
            public=visibility == "public",
            allowed_extensions=DOCUMENT_UPLOAD_EXTENSIONS,
        )
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
                "visibility": visibility,
                "expiresAt": sanitize_text(request.form.get("expiresAt", ""), max_length=32, allow_newlines=False),
                "status": request.form.get("status", "active") if request.form.get("status", "active") in dict(DOCUMENT_STATUS_OPTIONS) else "active",
                "notes": sanitize_text(request.form.get("notes", ""), max_length=1200),
                "createdById": session.get("admin_user_id", ""),
                "createdByName": session.get("admin_name", "FVENTAS Admin"),
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
    asset = find_company_record(store, "media_assets", asset_id)
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
    asset = find_company_record(store, "media_assets", payload.get("assetId", ""))
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
    writer = safe_csv_dict_writer(output, fieldnames=fieldnames, lineterminator="\n")
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
        headers={"Content-Disposition": "attachment; filename=documentos_fventas.csv"},
    )


@app.post("/documents/<asset_id>/delete")
@require_roles(*roles_for_action("documents", "delete"))
def document_delete(asset_id: str):
    store = load_store()
    asset = find_company_record(store, "media_assets", asset_id)
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
        record_create_event(
            store,
            "service_technician",
            technician["id"],
            f"Servicio tecnico creado: {technician['name']}.",
            technician,
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
    technician = find_company_record(store, "service_technicians", technician_id)
    if technician:
        before = copy.deepcopy(technician)
        updated = service_technician_payload(technician)
        replace_company_record(store, "service_technicians", technician, updated)
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
    technician = find_company_record(store, "service_technicians", technician_id)
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
    movements = visible_records_for_current_company(store, "credit_movements")
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
    clients_list = enrich_clients(visible_clients, visible_orders, movements)
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
        enriched_movement["clientName"] = client.get("businessName", "Cliente FVENTAS") if client else "Cliente FVENTAS"
        payments.append(enriched_movement)
    due_orders = [
        order
        for order in enrich_orders(visible_orders, movements)
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
    clients_list = sorted(clients_list, key=lambda item: item.get("businessName", ""))
    page_clients, pagination = api_list_pagination(clients_list, default_limit=24)
    total_pages = max(1, math.ceil((pagination.get("total") or 0) / max(1, pagination.get("limit") or 1)))
    pagination.update({
        "pages": total_pages,
        "start": (pagination.get("offset") or 0) + 1 if pagination.get("total") else 0,
        "end": (pagination.get("offset") or 0) + len(page_clients),
        "previousPage": (pagination.get("page") or 1) - 1 if (pagination.get("page") or 1) > 1 else None,
        "nextPage": (pagination.get("page") or 1) + 1 if pagination.get("hasMore") else None,
    })
    return {
        "clients": page_clients,
        "payments": sorted(payments, key=lambda item: item.get("createdAt", ""), reverse=True),
        "due_orders": sorted(due_orders, key=lambda item: item.get("dueDate", "")),
        "metrics": metrics,
        "filters": filters,
        "pagination": pagination,
        "total_clients": len(clients_list),
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
    writer = safe_csv_dict_writer(
        output,
        fieldnames=[
            "cliente",
            "documento_fiscal",
            "email",
            "vendedor",
            "estado_credito",
            "riesgo",
            "score",
            "solicitado",
            "limite",
            "deuda_vigente",
            "deuda_vencida",
            "ordenes_abiertas",
            "disponible",
            "dias_credito",
            "promedio_pago_dias",
            "ultimo_pago",
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
                "documento_fiscal": client.get("taxId", ""),
                "email": client.get("email", ""),
                "vendedor": client.get("assignedSellerName", ""),
                "estado_credito": client.get("creditStatusLabel", ""),
                "riesgo": client.get("creditRiskLabel", ""),
                "score": client.get("creditScore", 0),
                "solicitado": client.get("creditRequestedUsd", 0),
                "limite": client.get("creditLimitUsd", 0),
                "deuda_vigente": client.get("currentDebtUsd", 0),
                "deuda_vencida": client.get("overdueBalanceUsd", 0),
                "ordenes_abiertas": client.get("creditOrdersUsd", 0),
                "disponible": client.get("creditAvailableUsd", 0),
                "dias_credito": client.get("paymentTermsDays", 0),
                "promedio_pago_dias": client.get("averagePaymentDays", 0),
                "ultimo_pago": client.get("lastPaymentUsd", 0),
                "ultimo_pago_fecha": client.get("lastPaymentAt", ""),
                "observacion_gerencia": client.get("creditManagerNote", ""),
            }
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=credito_b2b_fventas.csv"},
    )


@app.get("/credit/vencimientos/export")
@require_roles(*roles_for_action("credit", "export"))
def credit_due_export():
    store = load_store()
    context = credit_dashboard_context(store)
    output = io.StringIO()
    writer = safe_csv_dict_writer(
        output,
        fieldnames=["vence", "orden", "cliente", "vendedor", "condicion", "saldo", "dias", "estado"],
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
                "saldo": order.get("balanceUsd", 0),
                "dias": order.get("dueDays", 0),
                "estado": order.get("dueStatus", ""),
            }
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=vencimientos_credito_fventas.csv"},
    )


@app.get("/credit/historial/export")
@require_roles(*roles_for_action("credit", "export"))
def credit_history_export():
    store = load_store()
    context = credit_dashboard_context(store)
    output = io.StringIO()
    writer = safe_csv_dict_writer(
        output,
        fieldnames=["fecha", "orden", "cliente", "metodo", "referencia", "monto", "monto_local", "usuario", "nota"],
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
                "monto": payment.get("amountUsd", 0),
                "monto_local": payment.get("amountClp", payment.get("amountVes", 0)),
                "usuario": payment.get("createdBy", ""),
                "nota": payment.get("note", ""),
            }
        )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=historial_credito_fventas.csv"},
    )


@app.post("/credit/<client_id>/decision")
@require_roles(*roles_for_action("credit", "approve"))
def credit_decision(client_id: str):
    store = load_store()
    client = find_company_record(store, "clients", client_id)
    if not client or not can_access_client_record(client, store):
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
        detail = f"Credito {credit_status_label(client['creditRequestStatus']).lower()} por {money_sales(client['creditLimitUsd'], store, record_company_id(client, store))} a {payment_terms} dias."
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
    notification = next(
        (
            item
            for item in store.get("notifications", [])
            if item.get("id") == notification_id and notification_visible_to_current_admin(store, item)
        ),
        None,
    )
    if not notification:
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
    return redirect(safe_internal_url(request.form.get("next"), "notifications"))


@app.post("/notifications/read-all")
@require_roles(*roles_for_action("notifications", "edit"))
def notifications_read_all():
    store = load_store()
    now = utc_now()
    updated = 0
    for notification in store.get("notifications", []):
        if notification.get("status") == "unread" and notification_visible_to_current_admin(store, notification):
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
    return redirect(safe_internal_url(request.form.get("next"), "notifications"))


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
    products = [product for product in visible_records_for_current_company(store, "products") if product.get("status") != "deleted"]
    clients = [client for client in visible_records_for_current_company(store, "clients") if client.get("status") != "deleted"]
    sellers = [
        user for user in visible_records_for_current_company(store, "admin_users")
        if user.get("role") == "sales" and user.get("status") != "deleted"
    ]
    orders = visible_orders_for_current_user(store)
    movements = visible_records_for_current_company(store, "credit_movements")
    audit_events = visible_records_for_current_company(store, "audit_events")
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
        description="No se permite crear ni mantener ordenes sin cliente B2B asociado.",
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
        description="Toda orden debe contener items validos del catalogo publicado por FVENTAS.",
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
            company_id = record_company_id(client, store)
            over_limit_clients.append(f"{client.get('businessName', client.get('id', 'Cliente'))}: {money_sales(exposure, store, company_id)} / {money_sales(limit, store, company_id)}")
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

    clients_mobile_access_inconsistent = [
        f"{client.get('businessName', client.get('id', 'Cliente'))}: {client_status_label(client.get('status', ''))}"
        for client in clients
        if client.get("mobileAccessEnabled", True) is not False
        and (client_status_blocks_mobile_access(client.get("status", "")) or mobile_account_access_blocked(client))
    ]
    sellers_mobile_access_inconsistent = [
        f"{seller.get('name', seller.get('id', 'Vendedor'))}: {ROLE_LABELS.get(seller.get('role', ''), seller.get('role', 'sales'))}"
        for seller in sellers
        if seller.get("mobileAccessEnabled", True) is not False
        and (seller.get("status") != "active" or mobile_account_access_blocked(seller))
    ]
    add_business_rule(
        rules,
        code="mobile.access.blocked_accounts",
        title="Acceso movil respeta bloqueos",
        module="Clientes",
        description="Clientes o vendedores bloqueados, suspendidos o con solicitud de eliminacion no deben conservar acceso movil activo.",
        count=len(clients_mobile_access_inconsistent) + len(sellers_mobile_access_inconsistent),
        examples=clients_mobile_access_inconsistent + sellers_mobile_access_inconsistent,
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

    client_rut_duplicates = duplicate_record_groups(clients, "taxId", "businessName")
    add_business_rule(
        rules,
        code="clients.tax_id.unique",
        title="Documento fiscal unico",
        module="Clientes",
        description="El documento fiscal no debe repetirse para evitar credito duplicado, cartera mezclada o facturacion incorrecta.",
        count=len(client_rut_duplicates),
        examples=[f"{rut.upper()}: {', '.join(names)}" for rut, names in client_rut_duplicates.items()],
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
        description="Los precios publico, B2B, anterior y costo referencial deben ser validos antes de publicar.",
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
        "status_graph": insights_from_pairs(
            [
                ("OK", metrics["ok"]),
                ("Atencion", metrics["warning"]),
                ("Critico", metrics["critical"]),
            ],
            3,
        ),
        "module_graph": insights_from_pairs(list(module_counts.items()), 8),
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
    runtime_snapshot = runtime_capacity_snapshot(current_company_id(store))

    areas: list[dict] = []
    production_ready = (
        data_backend == "sql"
        and database_engine == "PostgreSQL"
        and storage_backend == "s3"
        and bool(app.config.get("REQUIRE_MOBILE_TOKEN"))
        and not bool(app.config.get("SQL_FALLBACK_TO_JSON"))
        and app.config.get("SECRET_KEY") not in {"fventas-dev"}
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
        status="ok" if latest_migration.endswith("0011_tenant_scoped_client_product_indexes") else "warning",
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
        detail=f"Auditoria: {len(visible_records_for_current_company(store, 'audit_events'))} eventos. Notificaciones: {len(visible_admin_notifications(store))}.",
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
        action="Configurar FVENTAS_BUILD_SHA" if not app.config.get("BUILD_SHA") else "",
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
    configured_slots = safe_int(runtime_snapshot.get("configuredRequestSlots"), 0)
    active_requests = safe_int(runtime_snapshot.get("activeRequests"), 0)
    peak_requests = safe_int(runtime_snapshot.get("peakActiveRequests"), 0)
    capacity_status = "warning" if configured_slots and peak_requests >= configured_slots else "ok"
    add_maintenance_area(
        areas,
        key="runtime-capacity",
        title="Concurrencia por instancia",
        module="Operacion",
        status=capacity_status,
        detail=(
            f"{configured_slots} request(s) simultaneos configurados; "
            f"{active_requests} activos ahora, pico observado {peak_requests}. "
            f"App 15 min: {runtime_snapshot.get('mobileUsers15m', 0)} usuarios."
        ),
        action="Escalar workers/instancia" if capacity_status != "ok" else "",
    )

    counts = {
        "products": len([item for item in visible_records_for_current_company(store, "products") if item.get("status") != "deleted"]),
        "clients": len([item for item in visible_records_for_current_company(store, "clients") if item.get("status") != "deleted"]),
        "orders": len(visible_orders_for_current_user(store)),
        "sellers": len([item for item in visible_records_for_current_company(store, "admin_users") if item.get("role") == "sales" and item.get("status") != "deleted"]),
        "audit": len(visible_records_for_current_company(store, "audit_events")),
        "notifications": len(visible_admin_notifications(store)),
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
        ("Workers/threads", f"{runtime_snapshot['workers']} x {runtime_snapshot['threads']}"),
        ("Req simultaneos", runtime_snapshot["configuredRequestSlots"]),
        ("Req activos", f"{runtime_snapshot['activeRequests']} actual / {runtime_snapshot['peakActiveRequests']} pico"),
        ("Requests proceso", runtime_snapshot["totalRequests"]),
        ("RPM proceso", runtime_snapshot["requestsPerMinute"]),
        ("App activos 5m", runtime_snapshot["mobileUsers5m"]),
        ("App activos 15m", runtime_snapshot["mobileUsers15m"]),
        ("Clientes app 15m", runtime_snapshot["clientUsers15m"]),
        ("Vendedores app 15m", runtime_snapshot["sellerUsers15m"]),
        ("Admins panel 15m", runtime_snapshot["adminUsers15m"]),
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
        "status_graph": insights_from_pairs(
            [
                ("OK", metrics["ok"]),
                ("Atencion", metrics["warning"]),
                ("Critico", metrics["critical"]),
            ],
            3,
        ),
        "volume_graph": insights_from_pairs(
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
    writer = safe_csv_dict_writer(output, fieldnames=["area", "modulo", "estado", "detalle", "accion"])
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
        headers={"Content-Disposition": "attachment; filename=fventas_mantenimiento.csv"},
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
    all_events = sorted(
        visible_records_for_current_company(store, "audit_events"),
        key=lambda item: item.get("createdAt", ""),
        reverse=True,
    )
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
    write_events = [event for event in filtered_events if event.get("severity") == "write"]
    write_snapshots = sum(1 for event in write_events if event.get("hasSnapshot"))
    snapshot_gap = max(0, len(write_events) - write_snapshots)
    snapshot_rate = round((write_snapshots / len(write_events)) * 100) if write_events else 100
    metrics = {
        "total": len(all_events),
        "filtered": len(filtered_events),
        "actors": len({event.get("actorId") or event.get("actorName") for event in filtered_events}),
        "writes": len(write_events),
        "security": sum(1 for event in filtered_events if event.get("severity") in {"security", "critical"}),
        "exports": sum(1 for event in filtered_events if event.get("severity") == "export"),
        "snapshots": sum(1 for event in filtered_events if event.get("hasSnapshot")),
        "writeSnapshots": write_snapshots,
        "snapshotGap": snapshot_gap,
        "snapshotRate": snapshot_rate,
    }
    insights_summary = f"{metrics['writes']} cambios / {metrics['actors']} actores"
    return {
        "events": events,
        "metrics": metrics,
        "insights_summary": insights_summary,
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
            "actions": insights_from_pairs(list(action_counts.items()), 8),
            "entities": insights_from_pairs(list(entity_counts.items()), 8),
            "actors": insights_from_pairs(list(actor_counts.items()), 8),
            "severity": insights_from_pairs(list(severity_counts.items()), 8),
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
    market_country = normalize_market_country(request.form.get("marketCountry") or existing.get("marketCountry") or "CL")
    profile = market_profile(market_country)
    sales_currency = normalize_currency_code(profile.get("salesCurrency"), "USD")
    local_currency = normalize_currency_code(profile.get("localCurrency"), sales_currency)
    exchange_rate = safe_float(profile.get("exchangeRateBaseToLocal"), 1)
    pricing = plan_pricing_for_country(market_country)
    payload = dict(existing or {})
    payload.update(
        {
            "companyName": sanitize_text(request.form.get("companyName", ""), max_length=180, allow_newlines=False) or f"FVENTAS {profile['label']}",
            "companyLegalName": sanitize_text(request.form.get("companyLegalName", ""), max_length=180, allow_newlines=False),
            "taxId": sanitize_text(request.form.get("taxId", ""), max_length=60, allow_newlines=False),
            "supportEmail": request.form.get("supportEmail", "").strip().lower(),
            "supportPhone": sanitize_text(request.form.get("supportPhone", ""), max_length=60, allow_newlines=False),
            "logoUrl": sanitize_url(request.form.get("logoUrl", "")),
            "marketCountry": market_country,
            "marketCountryName": profile["label"],
            "country": profile["code"],
            "taxLabel": profile["taxLabel"],
            "taxPlaceholder": profile["taxPlaceholder"],
            "phonePrefix": profile["phonePrefix"],
            "phonePlaceholder": profile["phonePlaceholder"],
            "locale": profile["locale"],
            "timezone": profile["timezone"],
            "salesCurrency": sales_currency,
            "localCurrency": local_currency,
            "primaryCurrency": sales_currency,
            "referenceCurrency": local_currency,
            "exchangeRateBaseToLocal": exchange_rate,
            "exchangeRateUsdClp": exchange_rate,
            "exchangeRateUsdVes": exchange_rate,
            "planCurrency": pricing["currency"],
            "planPrice": pricing["price"],
            "planPriceClp": pricing["priceClp"],
            "defaultPaymentTermsDays": payment_terms_from_text(request.form.get("defaultPaymentTermsDays", "")),
            "purchaseConditionsTitle": sanitize_text(
                request.form.get("purchaseConditionsTitle", ""),
                max_length=80,
                allow_newlines=False,
            ) or "Condiciones de compra",
            "purchaseDefaultSaleType": request.form.get("purchaseDefaultSaleType", "cash"),
            "purchaseConditionsScope": sanitize_text(
                request.form.get("purchaseConditionsScope", ""),
                max_length=120,
                allow_newlines=False,
            ) or "Solo datos de tu empresa",
            "purchaseConditionsNote": sanitize_text(
                request.form.get("purchaseConditionsNote", ""),
                max_length=500,
            ),
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
    if payload["purchaseDefaultSaleType"] not in dict(SALE_TYPE_OPTIONS):
        payload["purchaseDefaultSaleType"] = "cash"
    payload["purchaseConditions"] = {
        "title": payload["purchaseConditionsTitle"],
        "defaultSaleType": payload["purchaseDefaultSaleType"],
        "allowedPaymentTermsDays": payload["defaultPaymentTermsDays"],
        "scopeLabel": payload["purchaseConditionsScope"],
        "note": payload["purchaseConditionsNote"] or payload["orderTermsText"],
    }
    return payload


def sync_company_from_settings(store: dict, settings_data: dict) -> None:
    company_id = current_company_id(store)
    company = get_company(store, company_id)
    if not company:
        return
    profile = market_profile(settings_data.get("marketCountry") or company.get("country") or "CL")
    pricing = plan_pricing_for_country(profile["code"])
    company.update(
        {
            "name": settings_data.get("companyName") or company.get("name", ""),
            "legalName": settings_data.get("companyLegalName") or company.get("legalName", ""),
            "taxId": settings_data.get("taxId", company.get("taxId", "")),
            "country": profile["code"],
            "marketCountry": profile["code"],
            "currency": settings_data.get("localCurrency") or profile["localCurrency"],
            "baseCurrency": settings_data.get("salesCurrency") or profile["salesCurrency"],
            "exchangeRateBaseToLocal": settings_data.get("exchangeRateBaseToLocal") or profile["exchangeRateBaseToLocal"],
            "marketProfile": profile,
            "taxLabel": profile["taxLabel"],
            "supportEmail": settings_data.get("supportEmail", company.get("supportEmail", "")),
            "supportPhone": settings_data.get("supportPhone", company.get("supportPhone", "")),
            "logoUrl": settings_data.get("logoUrl", company.get("logoUrl", "")),
            "planCurrency": settings_data.get("planCurrency") or pricing["currency"],
            "planPrice": settings_data.get("planPrice") or pricing["price"],
            "planPriceClp": settings_data.get("planPriceClp") or pricing["priceClp"],
            "purchaseConditions": dict(settings_data.get("purchaseConditions") or {}),
            "updatedAt": settings_data.get("updatedAt") or utc_now(),
        }
    )


def settings_page_context(store: dict, error: str = "", success: str = "") -> dict:
    settings_data = business_settings(store)
    currency_data = currency_context(store)
    profile = currency_data["market_profile"]
    pricing = plan_pricing_for_country(profile["code"])
    settings_data.update(
        {
            "marketCountry": currency_data["market_country"],
            "marketCountryName": profile["label"],
            "taxLabel": settings_data.get("taxLabel") or profile["taxLabel"],
            "taxPlaceholder": settings_data.get("taxPlaceholder") or profile["taxPlaceholder"],
            "phonePrefix": settings_data.get("phonePrefix") or profile["phonePrefix"],
            "phonePlaceholder": settings_data.get("phonePlaceholder") or profile["phonePlaceholder"],
            "locale": settings_data.get("locale") or profile["locale"],
            "timezone": settings_data.get("timezone") or profile["timezone"],
            "salesCurrency": currency_data["sales_currency"],
            "localCurrency": currency_data["local_currency"],
            "exchangeRateBaseToLocal": currency_data["exchange_rate"],
            "primaryCurrency": currency_data["sales_currency"],
            "referenceCurrency": currency_data["local_currency"],
            "planCurrency": settings_data.get("planCurrency") or pricing["currency"],
            "planPrice": settings_data.get("planPrice") or pricing["price"],
            "planPriceClp": settings_data.get("planPriceClp") or pricing["priceClp"],
            "purchaseConditionsTitle": settings_data.get("purchaseConditionsTitle") or (settings_data.get("purchaseConditions") or {}).get("title") or "Condiciones de compra",
            "purchaseDefaultSaleType": settings_data.get("purchaseDefaultSaleType") or (settings_data.get("purchaseConditions") or {}).get("defaultSaleType") or "cash",
            "purchaseConditionsScope": settings_data.get("purchaseConditionsScope") or (settings_data.get("purchaseConditions") or {}).get("scopeLabel") or "Solo datos de tu empresa",
            "purchaseConditionsNote": settings_data.get("purchaseConditionsNote") or (settings_data.get("purchaseConditions") or {}).get("note") or settings_data.get("orderTermsText", ""),
        }
    )
    return {
        "settings": settings_data,
        "payment_terms_text": ", ".join(str(term) for term in settings_data.get("defaultPaymentTermsDays", [0])),
        "notification_emails_text": "\n".join(settings_data.get("notificationEmails", [])),
        "commission_rule_options": COMMISSION_RULE_OPTIONS,
        "market_country_options": MARKET_COUNTRY_OPTIONS,
        "market_profiles": ACTIVE_MARKET_PROFILES,
        "market_profile": profile,
        "currency_options": CURRENCY_OPTIONS,
        "sale_type_options": SALE_TYPE_OPTIONS,
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
    writer = safe_csv_dict_writer(output, fieldnames=fieldnames, lineterminator="\n")
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
        headers={"Content-Disposition": "attachment; filename=auditoria_fventas.csv"},
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
        sync_company_from_settings(store, store["business_settings"])
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
        record_create_event(
            store,
            "crm_record",
            record["id"],
            f"CRM creado: {record.get('title', '')}.",
            record,
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
        "valor_estimado",
        "probabilidad",
        "valor_ponderado",
        "cierre_estimado",
        "proxima_accion",
        "ultima_actividad",
        "actividades",
    ]
    writer = safe_csv_dict_writer(output, fieldnames=fieldnames, lineterminator="\n")
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
                "valor_estimado": record.get("estimatedValueUsd", 0),
                "probabilidad": record.get("probabilityPercent", 0),
                "valor_ponderado": record.get("weightedValueUsd", 0),
                "cierre_estimado": record.get("expectedCloseAt", ""),
                "proxima_accion": record.get("nextActionAt", ""),
                "ultima_actividad": record.get("lastActivityAt", ""),
                "actividades": record.get("activitiesCount", 0),
            }
        )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=crm_comercial_fventas.csv"},
    )


@app.post("/crm/<record_id>/update")
@require_roles(*roles_for_action("crm", "edit"))
def crm_update(record_id: str):
    store = load_store()
    record = find_company_record(store, "crm_records", record_id)
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
    record = find_company_record(store, "crm_records", record_id)
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
    record = find_company_record(store, "crm_records", record_id)
    if not record or not can_access_crm_record(record, store) or not can_module_action("crm", "delete"):
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
        "total",
        "total_local",
        "items",
        "orden_convertida",
    ]
    writer = safe_csv_dict_writer(output, fieldnames=fieldnames, lineterminator="\n")
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
                "total": quote.get("totalUsd", 0),
                "total_local": quote.get("totalClp", quote.get("totalVes", quote.get("totalUsd", 0))),
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
        headers={"Content-Disposition": "attachment; filename=cotizaciones_fventas.csv"},
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
        record_create_event(
            store,
            "quote",
            quote["id"],
            f"Cotizacion {quote['quoteNumber']} creada para {quote['client'].get('name', 'cliente')}.",
            quote,
        )
        save_store(store)
        return redirect(url_for("quotes"))
    return render_template("quote_form.html", **quote_form_context(store))


@app.route("/quotes/<quote_id>/edit", methods=["GET", "POST"])
@require_roles(*roles_for_action("quotes", "edit"))
def quote_edit(quote_id: str):
    store = load_store()
    quote = find_company_record(store, "quotes", quote_id)
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
    quote = find_company_record(store, "quotes", quote_id)
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
    source = find_company_record(store, "quotes", quote_id)
    if not source or not can_access_quote_record(source, store):
        return redirect(url_for("quotes"))
    quote = copy.deepcopy(source)
    quote["id"] = next_id("quote", quote.get("clientName") or quote.get("quoteNumber", "fventas"))
    quote["quoteNumber"] = next_quote_number((quote.get("client") or {}).get("name", "FVENTAS"))
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
    record_create_event(
        store,
        "quote",
        quote["id"],
        f"Cotizacion {quote['quoteNumber']} duplicada desde {source.get('quoteNumber', '')}.",
        quote,
    )
    save_store(store)
    return redirect(url_for("quotes"))


@app.post("/quotes/<quote_id>/convert")
@require_roles(*roles_for_action("orders", "create"))
def quote_convert(quote_id: str):
    store = load_store()
    quote = find_company_record(store, "quotes", quote_id)
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
        trusted_pricing=True,
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
    record_create_event(
        store,
        "order",
        order["orderId"],
        f"Orden creada desde cotizacion {quote.get('quoteNumber', '')}.",
        order,
    )
    notify_quote_accepted(store, quote, order)
    notify_order_created(store, order)
    save_store(store)
    return redirect(url_for("orders"))


@app.get("/quotes/<quote_id>/download")
@require_roles(*roles_for_action("quotes", "export"))
def quote_download(quote_id: str):
    store = load_store()
    quote = find_company_record(store, "quotes", quote_id)
    if not quote or not can_access_quote_record(quote, store):
        return redirect(url_for("quotes"))
    enriched = enrich_quote(quote)
    html = render_template("quote_print.html", quote=enriched)
    filename = safe_download_filename(
        f"{enriched.get('quoteNumber', 'cotizacion')}.html",
        "cotizacion_fventas.html",
    )
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
        "total",
        "abonado",
        "saldo",
        "vence",
        "items",
        "direccion_despacho",
        "comision",
        "estado_comision",
    ]
    writer = safe_csv_dict_writer(output, fieldnames=fieldnames, lineterminator="\n")
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
                "total": order.get("totalUsd", 0),
                "abonado": order.get("paidUsd", 0),
                "saldo": order.get("balanceUsd", 0),
                "vence": order.get("dueDate", ""),
                "items": "|".join(
                    f"{item.get('sku', '')}:{item.get('quantity', 0)}"
                    for item in order.get("items") or []
                ),
                "direccion_despacho": order.get("shippingAddress", ""),
                "comision": order.get("commissionUsd", 0),
                "estado_comision": order.get("commissionStatusLabel", ""),
            }
        )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=ordenes_fventas.csv"},
    )


@app.route("/orders/new", methods=["GET", "POST"])
@require_roles(*roles_for_action("orders", "create"))
def order_new():
    store = load_store()
    if request.method == "POST":
        payload = assisted_order_payload_from_form()
        client = find_company_record(store, "clients", payload.get("customerId", ""))
        if not can_access_client_record(client, store):
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
        record_create_event(
            store,
            "order",
            order["orderId"],
            f"Pedido asistido creado para {order['customer'].get('name', 'Cliente FVENTAS')}.",
            order,
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

    client = find_company_record(store, "clients", order.get("customerId", ""))
    movements = visible_records_for_current_company(store, "credit_movements")
    scoped_orders = visible_records_for_current_company(store, "orders")
    balance = order_balance_usd(order, movements)
    note = request.form.get("note", "").strip()
    if target_status in {"cancelled", "rejected"} and not note:
        return render_template(
            "orders.html",
            **orders_page_context(store, "Motivo obligatorio para rechazar o anular una orden."),
        ), 400

    sale_type = order.get("saleType", "cash")
    if target_status == "delivered":
        delivery_block_reason = order_release_block_reason(order, movements, store)
        if delivery_block_reason:
            order["dispatchStatus"] = "payment_hold"
            order["stockStatus"] = "payment_hold"
            order["paymentHoldReason"] = delivery_block_reason
            order["currentOwner"] = "Cobranza"
            order["managedBy"] = session.get("admin_name", "Admin")
            order["managedAt"] = utc_now()
            order["updatedAt"] = utc_now()
            order["balanceUsd"] = balance
            order["paidUsd"] = order_paid_usd(order, movements)
            append_order_history(order, order.get("status", ""), delivery_block_reason)
            record_change_event(
                store,
                "delivery_blocked",
                "order",
                order_id,
                delivery_block_reason,
                before,
                order,
                criticality="high",
            )
            save_store(store)
            return render_template("orders.html", **orders_page_context(store, delivery_block_reason)), 400

    if target_status in ORDER_CREDIT_RESERVING_STATUSES and sale_type == "credit_line":
        available = credit_available(
            client,
            scoped_orders,
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
        note = note or order.get("paymentHoldReason") or "Stock insuficiente para reservar o entregar esta orden."

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
        order["currentOwner"] = "Cierre"
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
    next_url = safe_internal_url(request.form.get("next"), "orders")
    order = find_order(store["orders"], order_id)
    if not order or not can_access_order_record(order, store):
        return redirect(next_url)

    before = copy.deepcopy(order)
    company_id = record_company_id(order, store)
    movements = store.setdefault("credit_movements", [])
    scoped_movements = [
        movement
        for movement in movements
        if record_company_id(movement, store) == company_id
    ]
    balance_before = order_balance_usd(order, scoped_movements)
    amount_usd = min(float(request.form.get("amountUsd") or 0), balance_before)
    if amount_usd <= 0:
        return redirect(next_url)

    exchange_rate = float(request.form.get("exchangeRateUsdClp") or order.get("exchangeRateUsdClp") or current_rate())
    amount_clp = float(request.form.get("amountClp") or request.form.get("amountVes") or round(amount_usd * exchange_rate, 2))
    movement = {
        "id": next_id("credit-payment", order.get("orderId") or order.get("id", "")),
        "companyId": company_id,
        "movementType": "payment",
        "clientId": order.get("customerId", ""),
        "orderId": order.get("orderId") or order.get("id", ""),
        "amountUsd": amount_usd,
        "amountClp": amount_clp,
        "amountVes": amount_clp,
        "exchangeRateUsdClp": exchange_rate,
        "method": request.form.get("method", "cash"),
        "reference": request.form.get("reference", "").strip(),
        "note": request.form.get("note", "").strip(),
        "createdBy": session.get("admin_name", "Admin"),
        "createdAt": utc_now(),
    }
    movements.append(movement)
    scoped_movements.append(movement)

    balance_after = order_balance_usd(order, scoped_movements)
    paid_after = order_paid_usd(order, scoped_movements)
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
    amount_display = money_sales(amount_usd, store, record_company_id(order, store))
    append_order_history(order, order["status"], f"Abono externo registrado por {amount_display}.")
    record_change_event(
        store,
        "payment",
        "order",
        order_id,
        f"Abono registrado por {amount_display}.",
        before,
        order,
    )
    notify_payment_registered(store, order, movement)
    notify_order_status_change(store, order, before.get("status", ""))
    save_store(store)
    return redirect(next_url)


def collections_page_context(store: dict) -> dict:
    movements = visible_records_for_current_company(store, "credit_movements")
    visible_orders = visible_orders_for_current_user(store)
    filters = {
        "q": request.args.get("q", "").strip(),
        "status": request.args.get("status", "").strip(),
        "seller": request.args.get("seller", "").strip(),
        "view": request.args.get("view", "open").strip() or "open",
    }
    client_lookup = {
        client.get("id", ""): enrich_client(client, visible_orders, movements)
        for client in visible_clients_for_current_user(store)
    }
    orders = [
        enrich_order(order, movements)
        for order in visible_orders
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
    writer = safe_csv_dict_writer(
        output,
        fieldnames=[
            "orden",
            "cliente",
            "vendedor",
            "total",
            "abonado",
            "saldo",
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
                "total": order.get("totalUsd", 0),
                "abonado": order.get("paidUsd", 0),
                "saldo": order.get("balanceUsd", 0),
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
        headers={"Content-Disposition": "attachment; filename=cobranza_fventas.csv"},
    )


@app.get("/collections/client/<client_id>/statement.csv")
@require_roles(*roles_for_action("collections", "export"))
def collection_statement(client_id: str):
    store = load_store()
    client = find_company_record(store, "clients", client_id)
    if not client or not can_access_client_record(client, store):
        return redirect(url_for("collections"))
    movements = visible_records_for_current_company(store, "credit_movements")
    orders = [
        enrich_order(order, movements)
        for order in visible_orders_for_current_user(store)
        if order.get("customerId") == client_id and order.get("status") not in {"cancelled", "rejected"}
    ]
    output = io.StringIO()
    writer = safe_csv_dict_writer(
        output,
        fieldnames=["fecha", "tipo", "documento", "debe", "haber", "saldo", "detalle"],
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
                "debe": order.get("totalUsd", 0),
                "haber": 0,
                "saldo": round(running_balance, 2),
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
                    "debe": 0,
                    "haber": payment.get("amountUsd", 0),
                    "saldo": round(running_balance, 2),
                    "detalle": payment.get("reference") or payment.get("method", ""),
                }
            )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": (
                "attachment; filename="
                f"{safe_download_filename(f'estado_cuenta_{client_id}.csv', 'estado_cuenta_fventas.csv')}"
            )
        },
    )


@app.post("/collections/<order_id>/action")
@require_roles(*roles_for_action("collections", "edit"))
def collection_action(order_id: str):
    store = load_store()
    order = find_order(store.get("orders", []), order_id)
    if not order or not can_access_order_record(order, store):
        return redirect(url_for("collections"))
    client = find_company_record(store, "clients", order.get("customerId", ""))
    movements = visible_records_for_current_company(store, "credit_movements")
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
        client["collectionStatus"] = "current" if order_balance_usd(order, movements) > 0 else "without_debt"
        if client.get("creditLimitUsd", 0) > 0 and client.get("creditRequestStatus") == "blocked_debt":
            client["creditRequestStatus"] = "approved"
            client["creditEnabled"] = True
        client["updatedAt"] = now
    elif action == "close" and order_balance_usd(order, movements) <= 0:
        order["collectionStatus"] = "closed"
        order["currentOwner"] = "Cierre"
    order["currentOwner"] = "Cobranza" if order_balance_usd(order, movements) > 0 else order.get("currentOwner", "Cierre")
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
    movements = visible_records_for_current_company(store, "credit_movements")
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
    writer = safe_csv_dict_writer(
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
        headers={"Content-Disposition": "attachment; filename=despacho_fventas.csv"},
    )


@app.post("/dispatch/<order_id>/update")
@require_roles(*roles_for_action("dispatch", "edit"))
def dispatch_update(order_id: str):
    store = load_store()
    order = find_order(store.get("orders", []), order_id)
    if not order or not can_access_order_record(order, store):
        return redirect(url_for("dispatch"))
    movements = visible_records_for_current_company(store, "credit_movements")
    before = copy.deepcopy(order)
    target_status = request.form.get("dispatchStatus", order.get("dispatchStatus", "pending"))
    if target_status not in DISPATCH_STATUS_LABELS:
        target_status = order.get("dispatchStatus", "pending")
    uploaded_evidence = save_upload(
        request.files.get("deliveryEvidenceFile"),
        "library",
        allowed_extensions=DOCUMENT_UPLOAD_EXTENSIONS,
    )
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
    audit_action = "dispatch_update"
    audit_criticality = None
    if target_status != "delivered":
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
        delivery_block_reason = order_release_block_reason(order, movements, store)
        if delivery_block_reason:
            target_status = "payment_hold"
            order["dispatchStatus"] = target_status
            order["stockStatus"] = "payment_hold"
            order["paymentHoldReason"] = delivery_block_reason
            order["currentOwner"] = "Cobranza"
            order["logisticsNote"] = order.get("logisticsNote") or delivery_block_reason
            audit_action = "delivery_blocked"
            audit_criticality = "high"
        else:
            order["deliveredAt"] = order.get("deliveredAt") or now
            if apply_inventory_transition(store, order, "delivered"):
                order["dispatchStatus"] = "delivered"
                order["status"] = "paid"
                order["currentOwner"] = "Cierre"
                order["paymentHoldReason"] = ""
                if float(order.get("commissionUsd") or 0) > 0:
                    order["commissionStatus"] = "commission_approved"
            else:
                target_status = "failed"
                order["dispatchStatus"] = target_status
                order["currentOwner"] = "Despacho"
                order["logisticsNote"] = order.get("logisticsNote") or "Stock insuficiente para entregar esta orden."
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
        audit_action,
        "order",
        order_id,
        f"Despacho actualizado a {dispatch_status_label(target_status)}.",
        before,
        order,
        criticality=audit_criticality,
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
        "total_venta",
        "base_comisionable",
        "porcentaje",
        "comision",
        "regla",
        "estado_comision",
        "fecha_aprobacion",
        "aprobado_por",
        "fecha_pago",
        "pagado_por",
        "saldo_orden",
        "bloqueos",
        "observacion",
    ]
    writer = safe_csv_dict_writer(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for order in context["orders"]:
        writer.writerow(
            {
                "orden": order.get("orderId", ""),
                "fecha_generacion": order.get("commissionGeneratedAt", ""),
                "vendedor": order.get("sellerName", ""),
                "cliente": order.get("customerName", ""),
                "total_venta": order.get("totalUsd", 0),
                "base_comisionable": order.get("commissionBaseUsd", 0),
                "porcentaje": order.get("commissionRatePercent", 0),
                "comision": order.get("commissionUsd", 0),
                "regla": order.get("commissionRuleLabel", ""),
                "estado_comision": order.get("commissionStatusLabel", ""),
                "fecha_aprobacion": order.get("commissionApprovedAt", ""),
                "aprobado_por": order.get("commissionApprovedBy", ""),
                "fecha_pago": order.get("commissionPaidAt", ""),
                "pagado_por": order.get("commissionPaidBy", ""),
                "saldo_orden": order.get("balanceUsd", 0),
                "bloqueos": " | ".join(order.get("commissionReleaseBlockers") or []),
                "observacion": order.get("commissionObservation", ""),
            }
        )
    return Response(
        "\ufeff" + output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=comisiones_fventas.csv"},
    )


@app.post("/commissions/<order_id>/status")
@require_roles(*roles_for_action("commissions", "approve"))
def commission_status_update(order_id: str):
    store = load_store()
    order = find_order(store.get("orders", []), order_id)
    if not order or not can_access_order_record(order, store):
        return redirect(url_for("commissions"))
    before = copy.deepcopy(order)
    status = request.form.get("commissionStatus", order.get("commissionStatus", "commission_pending"))
    if status not in {key for key, _label in COMMISSION_STATUS_OPTIONS}:
        return redirect(url_for("commissions"))
    note = request.form.get("commissionObservation", "").strip()
    hold_reason = request.form.get("commissionHoldReason", "").strip()
    movements = visible_records_for_current_company(store, "credit_movements")
    client_lookup = {
        client.get("id", ""): enrich_client(client, visible_orders_for_current_user(store), movements)
        for client in visible_clients_for_current_user(store)
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
        uploaded_image = save_upload(request.files.get("imageFile"), "announcements", allowed_extensions=IMAGE_UPLOAD_EXTENSIONS)
        image_url = uploaded_image or sanitize_url(request.form.get("imageUrl", ""))
        announcement = {
            "id": next_id("ann", title),
            "companyId": current_company_id(store),
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
        store.setdefault("announcements", []).append(announcement)
        record_create_event(store, "announcement", announcement["id"], f"Anuncio creado: {title}.", announcement)
        save_store(store)
        return redirect(url_for("announcements"))

    return render_template(
        "announcements.html",
        announcements=sorted(
            visible_records_for_current_company(store, "announcements"),
            key=lambda item: int(item.get("priority") or 0),
            reverse=True,
        ),
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
    announcement = find_company_record(store, "announcements", announcement_id)
    if announcement:
        before = copy.deepcopy(announcement)
        image_url = sanitize_url(request.form.get("imageUrl", "")) or announcement.get("imageUrl", "")
        uploaded = save_upload(request.files.get("imageFile"), "announcements", allowed_extensions=IMAGE_UPLOAD_EXTENSIONS)
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
    announcement = find_company_record(store, "announcements", announcement_id)
    if not announcement:
        return redirect(url_for("announcements"))
    remove_company_record(store, "announcements", announcement)
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
    if not client:
        return jsonify({"error": "Token movil requerido."}), 401
    client_company_id = mobile_required_company_id(client)
    rate_limit_response = guard_mobile_write_rate_limit(
        store,
        action="client_order_create",
        actor=client,
        actor_type="client",
        company_id=client_company_id,
    )
    if rate_limit_response:
        return rate_limit_response
    customer_id = (client or {}).get("id") or customer_payload.get("id", "")
    payload["customerId"] = customer_id
    order, error = build_commercial_order(
        store,
        payload,
        actor={
            "id": customer_id,
            "name": customer_payload.get("name", "Cliente FVENTAS"),
            "role": "client",
            "companyId": client_company_id,
        },
        default_channel="mobile",
    )
    if error:
        return jsonify({"error": error}), 400
    store["orders"].append(order)
    record_create_event(
        store,
        "order",
        order["orderId"],
        f"Orden movil creada por {order['customer'].get('name', 'Cliente FVENTAS')}.",
        order,
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
    if not client:
        return jsonify({"error": "Token movil requerido."}), 401
    customer_id = client["id"]
    client_company_id = mobile_required_company_id(client)
    orders = [
        order
        for order in store.get("orders", [])
        if mobile_record_matches_company(order, client_company_id)
    ]
    if customer_id:
        orders = [order for order in orders if order.get("customerId") == customer_id]
    movements = [
        movement
        for movement in store.get("credit_movements", [])
        if mobile_record_matches_company(movement, client_company_id)
    ]

    items = [enrich_order(order, movements) for order in orders]
    items, filters = filter_mobile_orders(items)
    items, sort = sort_mobile_orders(items)
    return mobile_paginated_response(items, filters, sort)


@app.get("/api/v1/mobile/notifications")
@app.get("/api/mobile/notifications")
def api_mobile_notifications():
    store = load_store()
    subject_type, subject_id, role, company_id, auth_error = mobile_notification_subject(store)
    if auth_error:
        return auth_error, 401
    if generate_mobile_subject_notifications(store, subject_type, subject_id, role, company_id):
        save_store(store)
    status = request.args.get("status", "").strip()
    notifications = mobile_notifications_for_subject(store, subject_type, subject_id, role, company_id)
    if status:
        notifications = [item for item in notifications if item.get("status", "unread") == status]
    items = [mobile_notification_payload(item) for item in notifications]
    return mobile_paginated_response(items, {"status": status, "subject": subject_type}, "created_desc")


@app.post("/api/v1/mobile/notifications/<notification_id>/read")
@app.post("/api/mobile/notifications/<notification_id>/read")
def api_mobile_notification_read(notification_id: str):
    store = load_store()
    subject_type, subject_id, role, company_id, auth_error = mobile_notification_subject(store)
    if auth_error:
        return auth_error, 401
    notification = next(
        (
            item
            for item in mobile_notifications_for_subject(store, subject_type, subject_id, role, company_id)
            if item.get("id") == notification_id
        ),
        None,
    )
    if not notification:
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
    movements = mobile_company_records(store, "credit_movements", user)
    orders = [enrich_order(order, movements) for order in seller_scope_orders(store, user)]
    seller_snapshot = enrich_seller(store, user)
    pending_credit = [
        client for client in clients if client.get("creditRequestStatus") == "pending"
    ]
    return jsonify(
        {
            "summary": {
                "sellerId": user["id"],
                "sellerName": user.get("name", "Vendedor FVENTAS"),
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

@app.get("/api/v1/mobile/locations/chile")
@app.get("/api/mobile/locations/chile")
def api_mobile_locations_chile():
    return jsonify(country_location_payload("CL"))


@app.get("/api/v1/mobile/locations/countries/<country_code>")
@app.get("/api/mobile/locations/countries/<country_code>")
def api_mobile_locations_country(country_code):
    return jsonify(country_location_payload(country_code))


@app.route("/api/v1/mobile/seller/clients", methods=["GET", "POST"])
@app.route("/api/mobile/seller/clients", methods=["GET", "POST"])
def api_mobile_seller_clients():
    store = load_store()
    user, auth_error = require_mobile_sales_user(store)
    if auth_error:
        return auth_error, 401

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        user_company_id = mobile_user_company_id(store, user)
        rate_limit_response = guard_mobile_write_rate_limit(
            store,
            action="seller_client_create",
            actor=user,
            actor_type="admin_user",
            company_id=user_company_id,
        )
        if rate_limit_response:
            return rate_limit_response
        profile = active_market_profile_for_store(store, user_company_id)
        email = str(payload.get("email") or "").strip().lower()
        business_name = str(payload.get("businessName") or payload.get("name") or "").strip()
        raw_idempotency_key = request.headers.get("Idempotency-Key") or payload.get("idempotencyKey") or ""
        idempotency_key = re.sub(r"[^A-Za-z0-9._:-]", "-", str(raw_idempotency_key).strip())[:120]
        field_errors = {}
        if not business_name:
            field_errors["businessName"] = "Ingresa la razon social o nombre comercial del cliente."
        if not email:
            field_errors["email"] = "Ingresa el correo de acceso del cliente."
        elif not re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", email):
            field_errors["email"] = "Ingresa un correo valido, por ejemplo cliente@empresa.com."
        if app.config.get("ENV") == "production":
            unsafe_text = f"{business_name} {email}".lower()
            if email.endswith("@fventas.local"):
                field_errors["email"] = "Usa un correo real del cliente. @fventas.local solo sirve para desarrollo."
            elif "demo" in unsafe_text:
                field_errors["businessName"] = "No uses datos demo en produccion. Ingresa datos reales del cliente."
        normalized_tax_id = normalize_tax_id_for_market(payload.get("taxId"), profile)
        normalized_phone = normalize_phone_for_market(payload.get("phone"), profile)
        normalized_whatsapp = (
            normalize_phone_for_market(payload.get("whatsapp"), profile)
            if payload.get("whatsapp")
            else normalized_phone
        )
        normalized_state, normalized_city, location_error = normalize_location_for_market(
            payload.get("state"),
            payload.get("city"),
            profile,
        )
        if not normalized_tax_id:
            field_errors["taxId"] = (
                f"Ingresa un {profile.get('taxLabel', 'documento fiscal')} valido. "
                f"Ejemplo: {profile.get('taxPlaceholder', 'ID fiscal')}."
            )
        if not normalized_phone:
            field_errors["phone"] = f"Ingresa un telefono valido. Ejemplo: {profile.get('phonePlaceholder', '+ codigo pais telefono')}."
        if payload.get("whatsapp") and not normalized_whatsapp:
            field_errors["whatsapp"] = "Ingresa un WhatsApp valido."
        if location_error:
            field_errors["location"] = location_error
        if field_errors:
            return jsonify({"error": "Revisa los datos del cliente.", "errors": field_errors}), 400

        def find_existing_mobile_client(source_store: dict) -> dict | None:
            for candidate in mobile_company_records(source_store, "clients", user):
                candidate_email = str(candidate.get("email", "")).strip().lower()
                candidate_tax_id = normalize_tax_id_for_market(candidate.get("taxId", ""), profile).lower()
                candidate_key = str(candidate.get("idempotencyKey", "")).strip()
                if idempotency_key and candidate_key == idempotency_key:
                    return candidate
                if candidate_email and candidate_email == email:
                    return candidate
                if candidate_tax_id and candidate_tax_id == normalized_tax_id.lower():
                    return candidate
            return None

        def user_can_access_existing_client(candidate: dict) -> bool:
            if user.get("role") in {"super_admin", "commercial_manager"}:
                return True
            return candidate.get("assignedSellerId") == user["id"] or candidate.get("createdById") == user["id"]

        def existing_client_response(candidate: dict, source_store: dict | None = None):
            if not user_can_access_existing_client(candidate):
                return jsonify({"error": "Ese cliente ya existe y esta asignado a otra cartera comercial."}), 409
            response = mobile_seller_client_payload(candidate, source_store or store)
            return jsonify(
                {
                    "client": response,
                    "alreadyExists": True,
                    "message": "El cliente ya existia. Se sincronizo con tu cartera sin crear duplicados.",
                }
            ), 200

        existing_client = find_existing_mobile_client(store)
        if existing_client:
            return existing_client_response(existing_client, store)

        mobile_user_conflict = next(
            (
                candidate
                for candidate in store.get("admin_users", [])
                if candidate.get("email", "").lower() == email
                and candidate.get("status") == "active"
                and candidate.get("mobileAccessEnabled", True) is not False
                and candidate.get("role") in MOBILE_SALES_ROLES
            ),
            None,
        )
        if mobile_user_conflict:
            return jsonify({"error": "Ese correo ya esta registrado como usuario operativo movil."}), 409

        cross_company_email = next(
            (
                candidate
                for candidate in store.get("clients", [])
                if candidate.get("email", "").lower() == email
                and record_company_id(candidate, store) != user_company_id
            ),
            None,
        )
        if cross_company_email:
            return jsonify({"error": "Ese correo ya existe como cliente movil de otra empresa."}), 409

        if use_sql_backend():
            try:
                from sql_store import client_identity_exists

                duplicate_client = client_identity_exists(
                    email=email,
                    tax_id=normalized_tax_id,
                    company_id=user_company_id,
                )
                if duplicate_client:
                    duplicate_field = "correo" if duplicate_client.get("field") == "email" else profile.get("taxLabel", "documento fiscal")
                    return jsonify(
                        {
                            "error": (
                                f"Ya existe un cliente con ese {duplicate_field}. "
                                "Revisalo en Clientes o usa datos distintos antes de reintentar."
                            )
                        }
                    ), 409
            except Exception:
                app.logger.exception("No se pudo validar duplicidad SQL para cliente movil.")

        seller_id = user["id"]
        seller_name = user.get("name", "") or seller_name_for(store, seller_id, user_company_id)
        requested_credit = max(0.0, safe_float(payload.get("creditRequestedUsd"), 0))
        raw_terms = payload.get("allowedPaymentTermsDays") or [0]
        if isinstance(raw_terms, str):
            raw_terms = re.split(r"[\s,;|/]+", raw_terms)
        elif not isinstance(raw_terms, list):
            raw_terms = [raw_terms]
        available_terms = set(payment_term_options(store))
        requested_terms = []
        for term in raw_terms:
            value = safe_int(term, -1)
            if value in available_terms and value not in requested_terms:
                requested_terms.append(value)
        requested_terms = requested_terms or [0]
        requested_default_sale_type = str(payload.get("defaultSaleType") or "cash").strip()
        if requested_default_sale_type not in dict(SALE_TYPE_OPTIONS):
            requested_default_sale_type = "cash"
        can_authorize_conditions = user.get("role") in {"super_admin", "general_manager", "commercial_manager"}
        terms = requested_terms if can_authorize_conditions else [0]
        default_sale_type = requested_default_sale_type if can_authorize_conditions else "cash"
        provided_password = str(payload.get("password") or "").strip()
        if provided_password:
            provided_password_errors = password_errors(provided_password)
            if provided_password_errors:
                return jsonify(
                    {
                        "error": " ".join(provided_password_errors),
                        "errors": {"password": " ".join(provided_password_errors)},
                    }
                ), 400
            temporary_password = provided_password
        else:
            temporary_password = temporary_mobile_client_password()
        requested_authorized_discount = max(0.0, min(safe_float(payload.get("authorizedDiscountPercent"), 0), 100.0))
        can_authorize_discount = user.get("role") in {"super_admin", "general_manager", "commercial_manager"}
        authorized_discount = requested_authorized_discount if can_authorize_discount else 0.0
        discount_request_status = (
            "approved"
            if authorized_discount > 0
            else "pending"
            if requested_authorized_discount > 0
            else "none"
        )
        raw_notes = str(payload.get("notes") or "").strip()
        if requested_authorized_discount > 0 and not can_authorize_discount:
            discount_note = f"Solicitud vendedor: descuento comercial {requested_authorized_discount:g}% pendiente de aprobacion."
            raw_notes = f"{raw_notes}\n{discount_note}".strip()
        if not can_authorize_conditions and (
            requested_default_sale_type != "cash" or any(term > 0 for term in requested_terms)
        ):
            requested_terms_label = ", ".join(str(term) for term in requested_terms if term > 0) or "contado"
            condition_note = (
                "Solicitud vendedor: condiciones de compra "
                f"{sale_type_label(requested_default_sale_type).lower()} / plazos {requested_terms_label} "
                "pendientes de aprobacion comercial."
            )
            raw_notes = f"{raw_notes}\n{condition_note}".strip()
        client_category = str(payload.get("clientCategory") or "standard").strip()
        if client_category not in dict(CLIENT_CATEGORY_OPTIONS):
            client_category = "standard"
        price_list = str(payload.get("priceList") or "b2b").strip()
        if price_list not in dict(PRICE_LIST_OPTIONS):
            price_list = "b2b"
        now = utc_now()
        client = {
            "id": next_id("client", email or business_name),
            "companyId": user_company_id,
            "legalName": str(payload.get("legalName") or business_name).strip(),
            "commercialName": str(payload.get("commercialName") or business_name).strip(),
            "businessName": business_name,
            "taxId": normalized_tax_id,
            "contactName": str(payload.get("contactName") or "").strip(),
            "administrativeContact": str(payload.get("administrativeContact") or "").strip(),
            "receivingContact": str(payload.get("receivingContact") or "").strip(),
            "phone": normalized_phone,
            "whatsapp": normalized_whatsapp,
            "email": email,
            "clientType": "b2b",
            "clientCategory": client_category,
            "priceList": price_list,
            "authorizedDiscountPercent": authorized_discount,
            "discountRequestedPercent": requested_authorized_discount,
            "discountRequestStatus": discount_request_status,
            "discountRequestSource": "seller_mobile" if requested_authorized_discount > 0 else "",
            "status": "active",
            "onboardingStatus": "pending_review",
            "address": str(payload.get("address") or "").strip(),
            "fiscalAddress": str(payload.get("fiscalAddress") or payload.get("address") or "").strip(),
            "shippingAddress": str(payload.get("shippingAddress") or payload.get("address") or "").strip(),
            "country": profile.get("code") or "CL",
            "state": normalized_state,
            "city": normalized_city,
            "deliveryZone": str(payload.get("deliveryZone") or "").strip(),
            "assignedSellerId": seller_id,
            "assignedSellerName": seller_name,
            "defaultSaleType": default_sale_type,
            "allowedPaymentTermsDays": terms,
            "collectionStatus": "without_debt",
            "creditRiskLevel": "low",
            "creditRequestStatus": "pending" if requested_credit > 0 else "none",
            "creditRequestedUsd": requested_credit,
            "creditEnabled": False,
            "creditLimitUsd": 0.0,
            "creditUsedUsd": 0.0,
            "paymentTermsDays": 0,
            "notes": raw_notes,
            "passwordHash": generate_password_hash(temporary_password),
            "mustChangePassword": True,
            "idempotencyKey": idempotency_key,
            "source": "seller_mobile",
            "createdVia": "seller_mobile",
            "createdById": user["id"],
            "createdByName": user.get("name", "Vendedor FVENTAS"),
            "createdByRole": user.get("role", "sales"),
            "updatedVia": "seller_mobile",
            "updatedById": user["id"],
            "updatedByName": user.get("name", "Vendedor FVENTAS"),
            "updatedByRole": user.get("role", "sales"),
            "createdAt": now,
            "updatedAt": now,
        }
        base_audit_ids = {str(event.get("id")) for event in store.get("audit_events", [])}
        base_notification_ids = {str(item.get("id")) for item in store.get("notifications", [])}
        store["clients"].append(client)
        record_create_event(
            store,
            "client",
            client["id"],
            f"Cliente creado desde app movil vendedor: {client['businessName']}.",
            client,
            actor={"id": user["id"], "name": user.get("name", ""), "role": user.get("role", "")},
        )
        create_notification(
            store,
            title="Cliente nuevo por vendedor",
            body=f"{user.get('name', 'Vendedor FVENTAS')} creo {client['businessName']}.",
            notification_type="client_created_by_seller",
            priority="normal",
            recipient_type="admin",
            channel="web",
            module="clients",
            entity_type="client",
            entity_id=client["id"],
            href=notification_url("clients", q=client["businessName"]),
            metadata={"companyId": user_company_id, "clientId": client["id"], "sellerId": user["id"]},
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
            deep_link=f"fventas://seller/clients/{client['id']}",
            metadata={"companyId": user_company_id, "clientId": client["id"]},
            dedupe_key=f"seller-client-assigned-{client['id']}",
        )
        notify_credit_requested(store, client)
        new_audit_events = [
            event for event in store.get("audit_events", []) if str(event.get("id")) not in base_audit_ids
        ]
        new_notifications = [
            item for item in store.get("notifications", []) if str(item.get("id")) not in base_notification_ids
        ]
        try:
            save_store(store)
        except Exception as exc:
            app.logger.exception("No se pudo crear cliente desde app movil.")
            error_text = str(exc).lower()
            if any(token in error_text for token in ("unique", "duplicate", "integrity")):
                try:
                    fresh_store = load_store()
                    existing_client = find_existing_mobile_client(fresh_store)
                    if existing_client:
                        return existing_client_response(existing_client, fresh_store)
                except Exception:
                    app.logger.exception("No se pudo resolver duplicidad luego de fallo SQL.")
                return jsonify({"error": f"Ya existe un cliente con ese correo o {profile.get('taxLabel', 'documento fiscal')}. Revisa Clientes antes de reintentar."}), 409
            if use_sql_backend():
                try:
                    from sql_store import sync_client_records

                    sync_client_records(
                        [client],
                        audit_events=new_audit_events,
                        notifications=new_notifications,
                    )
                    fresh_store = load_store()
                    created_client = find_existing_mobile_client(fresh_store) or client
                    response = mobile_seller_client_payload(created_client, fresh_store)
                    response["temporaryPassword"] = temporary_password
                    return jsonify(
                        {
                            "client": response,
                            "alreadyExists": False,
                            "message": "Cliente creado correctamente.",
                        }
                    ), 201
                except Exception:
                    app.logger.exception("No se pudo guardar cliente movil con persistencia puntual SQL.")
            return jsonify({"error": "No se pudo guardar el cliente. Intenta nuevamente o revisa los datos ingresados."}), 500
        response = mobile_seller_client_payload(client, store)
        response["temporaryPassword"] = temporary_password
        return jsonify({"client": response, "alreadyExists": False, "message": "Cliente creado correctamente."}), 201

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
        user_company_id = mobile_user_company_id(store, user)
        rate_limit_response = guard_mobile_write_rate_limit(
            store,
            action="seller_order_create",
            actor=user,
            actor_type="admin_user",
            company_id=user_company_id,
        )
        if rate_limit_response:
            return rate_limit_response
        customer_id = str(payload.get("customerId") or (payload.get("customer") or {}).get("id") or "").strip()
        if not can_mobile_seller_access_client(store, user, customer_id):
            return jsonify({"error": "Cliente fuera de tu cartera."}), 403
        payload["customerId"] = customer_id
        order, error = build_commercial_order(
            store,
            payload,
            actor={
                "id": user["id"],
                "name": user.get("name", "Vendedor FVENTAS"),
                "role": user.get("role", "sales"),
                "companyId": user_company_id,
            },
            default_channel="seller_mobile",
        )
        if error:
            return jsonify({"error": error}), 400
        store["orders"].append(order)
        record_create_event(
            store,
            "order",
            order["orderId"],
            f"Pedido asistido movil creado por {user.get('name', 'Vendedor FVENTAS')}.",
            order,
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
    return jsonify(
        {
            "error": "Cotizaciones moviles archivadas para el lanzamiento. Usa pedidos asistidos.",
            "code": "mobile_feature_archived",
            "feature": "seller_quotes",
        }
    ), 410

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        user_company_id = mobile_user_company_id(store, user)
        rate_limit_response = guard_mobile_write_rate_limit(
            store,
            action="seller_quote_create",
            actor=user,
            actor_type="admin_user",
            company_id=user_company_id,
        )
        if rate_limit_response:
            return rate_limit_response
        customer_id = str(payload.get("customerId") or (payload.get("customer") or {}).get("id") or "").strip()
        if not can_mobile_seller_access_client(store, user, customer_id):
            return jsonify({"error": "Cliente fuera de tu cartera."}), 403
        client = find_by_id(mobile_company_records(store, "clients", user), customer_id)
        raw_items = payload.get("items") or []
        if not isinstance(raw_items, list) or not raw_items:
            return jsonify({"error": "Agrega al menos un producto a la cotizacion."}), 400

        items: list[dict] = []
        gross_usd = 0.0
        total_usd = 0.0
        products = mobile_company_records(store, "products", user)
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
            blocker = mobile_product_commercial_blocker(product)
            if blocker:
                return jsonify({"error": f"{blocker} ({product_ref})"}), 400
            unit_price = mobile_product_catalog_price(product)
            requested_discount = max(0.0, min(100.0, safe_float(raw_item.get("discountPercent"), 0)))
            max_discount = max(0.0, min(100.0, safe_float((client or {}).get("authorizedDiscountPercent"), 0)))
            if requested_discount > max_discount:
                sku_label = product.get("sku") or product_ref
                return jsonify({"error": f"Descuento no autorizado para {sku_label}. Maximo {max_discount:g}%."}), 400
            discount_percent = requested_discount
            line_gross = round(unit_price * quantity, 2)
            line_discount = round(line_gross * discount_percent / 100, 2)
            line_total = round(max(0.0, line_gross - line_discount), 2)
            gross_usd += line_gross
            total_usd += line_total
            items.append(
                {
                    "productId": product.get("id", ""),
                    "sku": product.get("sku", ""),
                    "title": product.get("title", "Producto FVENTAS"),
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

        market = mobile_market_payload(store, user_company_id)
        exchange_rate = safe_float(market.get("exchangeRateBaseToLocal"), current_rate())
        sale_type = str(payload.get("saleType") or "cash")
        if sale_type not in dict(SALE_TYPE_OPTIONS):
            sale_type = "cash"
        payment_term_days = safe_int(payload.get("paymentTermDays"), 0)
        condition_error, sale_type, payment_term_days = validate_client_purchase_conditions(client, sale_type, payment_term_days)
        if condition_error:
            return jsonify({"error": condition_error}), 400
        now = utc_now()
        quote = {
            "id": next_id("quote", client.get("businessName", "fventas")),
            "companyId": mobile_user_company_id(store, user),
            "quoteNumber": next_quote_number(client.get("businessName", "FVENTAS")),
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
            "sellerName": user.get("name", "Vendedor FVENTAS"),
            "items": items,
            "grossUsd": round(gross_usd, 2),
            "discountUsd": round(max(0.0, gross_usd - total_usd), 2),
            "totalUsd": round(total_usd, 2),
            "totalClp": round(total_usd * exchange_rate, 2),
            "totalVes": round(total_usd * exchange_rate, 2),
            "exchangeRateUsdClp": exchange_rate,
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
            "createdByName": user.get("name", "Vendedor FVENTAS"),
            "updatedAt": now,
        }
        if quote["status"] not in dict(QUOTE_STATUS_OPTIONS):
            quote["status"] = "draft"
        append_quote_history(quote, quote["status"], "Cotizacion creada desde app movil vendedor.")
        store.setdefault("quotes", []).append(quote)
        record_create_event(
            store,
            "quote",
            quote["id"],
            f"Cotizacion movil creada por {user.get('name', 'Vendedor FVENTAS')}.",
            quote,
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
    return jsonify(
        {
            "error": "Seguimiento CRM movil archivado para el lanzamiento. Usa clientes y pedidos asistidos.",
            "code": "mobile_feature_archived",
            "feature": "seller_activities",
        }
    ), 410

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        user_company_id = mobile_user_company_id(store, user)
        rate_limit_response = guard_mobile_write_rate_limit(
            store,
            action="seller_activity_create",
            actor=user,
            actor_type="admin_user",
            company_id=user_company_id,
        )
        if rate_limit_response:
            return rate_limit_response
        customer_id = str(payload.get("customerId") or payload.get("clientId") or "").strip()
        if not can_mobile_seller_access_client(store, user, customer_id):
            return jsonify({"error": "Cliente fuera de tu cartera."}), 403
        client = find_by_id(mobile_company_records(store, "clients", user), customer_id)
        note = str(payload.get("note") or payload.get("activityNote") or "").strip()
        if not note:
            return jsonify({"error": "La actividad requiere una nota."}), 400
        activity_type = str(payload.get("activityType") or "note")
        if activity_type not in dict(CRM_ACTIVITY_TYPE_OPTIONS):
            activity_type = "note"
        record_id = str(payload.get("recordId") or "").strip()
        record = find_by_id(mobile_company_records(store, "crm_records", user), record_id) if record_id else None
        if record and record not in seller_scope_crm_records(store, user):
            return jsonify({"error": "Registro CRM fuera de tu cartera."}), 403
        before_record = copy.deepcopy(record) if record else None
        if not record:
            now = utc_now()
            record = {
                "id": next_id("crm", client.get("businessName", "seguimiento")),
                "companyId": mobile_user_company_id(store, user),
                "title": str(payload.get("title") or f"Seguimiento {client.get('businessName', 'cliente')}").strip(),
                "recordType": str(payload.get("recordType") or "opportunity"),
                "pipelineStage": str(payload.get("pipelineStage") or "contacted"),
                "status": "active",
                "clientId": client["id"],
                "clientName": client.get("businessName", ""),
                "sellerId": user["id"],
                "sellerName": user.get("name", "Vendedor FVENTAS"),
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
                "createdByName": user.get("name", "Vendedor FVENTAS"),
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
            "createdByName": user.get("name", "Vendedor FVENTAS"),
            "createdAt": now,
        }
        record.setdefault("activities", []).append(activity)
        record["lastActivityAt"] = now
        if activity["nextActionAt"]:
            record["nextActionAt"] = activity["nextActionAt"]
        record["updatedAt"] = now
        record_change_event(
            store,
            "crm_activity",
            "crm_record",
            record["id"],
            f"Actividad CRM movil registrada: {crm_activity_type_label(activity_type)}.",
            before_record,
            record,
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
        return jsonify({"error": "Token movil requerido."}), 401

    client_company_id = mobile_required_company_id(client)
    scoped_orders = [
        order
        for order in store.get("orders", [])
        if mobile_record_matches_company(order, client_company_id)
    ]
    scoped_movements = [
        movement
        for movement in store.get("credit_movements", [])
        if mobile_record_matches_company(movement, client_company_id)
    ]
    enriched = enrich_client(client, scoped_orders, scoped_movements)
    purchase_conditions = purchase_conditions_payload(
        store,
        client_company_id,
        allowed_terms=enriched.get("allowedPaymentTermsDays", [0]),
        default_sale_type=enriched.get("defaultSaleType", "cash"),
    )
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
                "purchaseConditions": purchase_conditions,
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
    profile_payload = None
    if request.headers.get("Authorization", ""):
        profile_payload, auth_error = mobile_profile_from_token(store)
        if auth_error:
            return auth_error, 401

    company_id = str((profile_payload or {}).get("companyId") or "").strip()
    if company_id and not company_subscription_allows_access(store, company_id):
        return mobile_subscription_response(company_id)

    if company_id:
        company_market = mobile_market_payload(store, company_id)
        profile = active_market_profile_for_store(store, company_id)
        market = {
            "country": company_market.get("country", "CL"),
            "countryName": company_market.get("countryName", "Mercado configurado"),
            "taxLabel": profile.get("taxLabel", "Documento fiscal"),
            "taxPlaceholder": profile.get("taxPlaceholder", "Documento fiscal"),
            "phonePrefix": profile.get("phonePrefix", "+56"),
            "phonePlaceholder": profile.get("phonePlaceholder", "+56 9 1234 5678"),
            "salesCurrency": company_market.get("salesCurrency", "USD"),
            "localCurrency": company_market.get("localCurrency", "CLP"),
            "exchangeRate": company_market.get("exchangeRateBaseToLocal", 1),
            "exchangeRateBaseToLocal": company_market.get("exchangeRateBaseToLocal", 1),
            "locale": company_market.get("locale", profile.get("locale", "es-CL")),
            "timezone": company_market.get("timezone", profile.get("timezone", "America/Santiago")),
        }
        counts = {
            "products": len(mobile_visible_products(store, company_id)),
            "categories": len(mobile_visible_categories(store, company_id)),
            "announcements": len(
                [
                    item
                    for item in store.get("announcements", [])
                    if mobile_record_matches_company(item, company_id)
                ]
            ),
            "serviceTechnicians": len(mobile_visible_service_technicians(store, company_id)),
        }
    else:
        currency_data = currency_context(store)
        profile = currency_data["market_profile"]
        market = {
            "country": profile.get("code", "CL"),
            "countryName": profile.get("label", "Mercado configurado"),
            "taxLabel": profile.get("taxLabel", "Documento fiscal"),
            "taxPlaceholder": profile.get("taxPlaceholder", "Documento fiscal"),
            "phonePrefix": profile.get("phonePrefix", "+56"),
            "phonePlaceholder": profile.get("phonePlaceholder", "+56 9 1234 5678"),
            "salesCurrency": currency_data["sales_currency"],
            "localCurrency": currency_data["local_currency"],
            "exchangeRate": currency_data["exchange_rate"],
            "exchangeRateBaseToLocal": currency_data["exchange_rate"],
            "locale": profile.get("locale", "es-CL"),
            "timezone": profile.get("timezone", "America/Santiago"),
        }
        counts = {}

    payload = {
        "meta": mobile_api_meta(),
        "market": market,
        "capabilities": {
            "auth": ["login", "logout", "refresh", "change_password", "recover_password", "request_account_deletion"],
            "mobile": ["home", "products", "product_detail", "categories", "banners", "cart", "orders", "credit", "profile"],
            "seller": ["summary", "clients", "orders", "commissions"],
            "storage": app.config.get("STORAGE_BACKEND"),
            "data": app.config.get("DATA_BACKEND"),
            "tokenRequired": bool(app.config.get("REQUIRE_MOBILE_TOKEN")),
        },
    }
    if counts:
        payload["counts"] = counts
        payload["purchaseConditions"] = purchase_conditions_payload(store, company_id)
    return jsonify(payload)


@app.get("/api/v1/mobile/home")
def api_mobile_home():
    store = load_store()
    profile, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    company_id = mobile_catalog_company_id(store, profile)

    products = sorted(
        mobile_visible_products(store, company_id),
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
            "visibleInApp": bool(category.get("visibleInApp")),
        }
        for category in sorted(
            mobile_visible_categories(store, company_id),
            key=lambda item: (safe_int(item.get("sortOrder"), 0), item.get("name", "")),
        )
        if category.get("visibleInApp")
    ]
    payload = {
        "meta": mobile_api_meta(),
        "home": {
            "banners": active_announcements("home", store, company_id=company_id),
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
    profile, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    company_id = mobile_catalog_company_id(store, profile)
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
            "visibleInApp": bool(category.get("visibleInApp")),
        }
        for category in sorted(
            mobile_visible_categories(store, company_id),
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
    login_device_id = mobile_request_device_id(payload)
    if app.config.get("REQUIRE_MOBILE_DEVICE_HEADER") and not login_device_id:
        return jsonify({"error": "Identificador de dispositivo requerido."}), 400
    login_device_id = login_device_id or mobile_device_id(payload)
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

    client_candidates = [
        item
        for item in store.get("clients", [])
        if item.get("email", "").lower() == email and item.get("status") == "active"
        and item.get("mobileAccessEnabled", True) is not False
    ]
    admin_candidates = [
        user
        for user in store.get("admin_users", [])
        if user.get("email", "").lower() == email
        and user.get("status") == "active"
        and user.get("mobileAccessEnabled", True) is not False
        and user.get("role") in MOBILE_SALES_ROLES
    ]
    if len(client_candidates) + len(admin_candidates) > 1:
        register_login_failure("mobile", email)
        record_audit_event(
            store,
            "login_blocked",
            "mobile_user",
            email,
            "Login movil bloqueado por identidad duplicada entre empresas o roles.",
            actor={"id": email, "name": email or "desconocido", "role": "mobile"},
            metadata={
                "clientMatches": [client.get("id", "") for client in client_candidates],
                "adminMatches": [user.get("id", "") for user in admin_candidates],
            },
            criticality="high",
        )
        save_store(store)
        return jsonify({"error": "Credenciales invalidas."}), 401

    client = client_candidates[0] if client_candidates else None
    if client and check_password_hash(client.get("passwordHash", ""), password):
        company_id = mobile_required_company_id(client)
        if not company_id:
            record_audit_event(
                store,
                "mobile_login_blocked",
                "client",
                client["id"],
                "Login movil bloqueado porque la cuenta no tiene companyId explicito.",
                actor={"id": client["id"], "name": client.get("businessName", email), "role": "client"},
                metadata={"email": email},
                criticality="high",
            )
            save_store(store)
            return jsonify({"error": "Cuenta movil sin empresa asignada. Contacta al administrador."}), 403
        if mobile_account_access_blocked(client):
            record_audit_event(
                store,
                "mobile_login_blocked",
                "client",
                client["id"],
                "Login movil bloqueado por solicitud de eliminacion de cuenta.",
                actor={"id": client["id"], "name": client.get("businessName", email), "role": "client"},
                metadata={"email": email, "deletionStatus": client.get("deletionStatus", "")},
                criticality="high",
            )
            save_store(store)
            return mobile_account_deletion_response(), 403
        if not company_subscription_allows_access(store, company_id):
            record_audit_event(
                store,
                "mobile_login_blocked",
                "subscription",
                company_id,
                "Login movil de cliente bloqueado por suscripcion pendiente o suspendida.",
                actor={"id": client["id"], "name": client.get("businessName", email), "role": "client"},
                metadata={"email": email, "companyId": company_id},
            )
            save_store(store)
            return mobile_subscription_response(company_id)
        reset_login_attempts("mobile", email)
        client["lastLoginAt"] = utc_now()
        client["lastMobileLoginIp"] = request_ip_address()
        client["lastMobileDeviceId"] = login_device_id
        client["mobileSessionVersion"] = safe_int(client.get("mobileSessionVersion"), 0)
        access_token = issue_mobile_token(client, login_device_id)
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

    admin_user = admin_candidates[0] if admin_candidates else None
    if admin_user and check_password_hash(admin_user.get("passwordHash", ""), password):
        company_id = mobile_required_company_id(admin_user)
        if not company_id:
            record_audit_event(
                store,
                "mobile_login_blocked",
                "admin_user",
                admin_user["id"],
                "Login movil operativo bloqueado porque la cuenta no tiene companyId explicito.",
                actor={"id": admin_user["id"], "name": admin_user.get("name", email), "role": admin_user.get("role", "")},
                metadata={"email": email},
                criticality="high",
            )
            save_store(store)
            return jsonify({"error": "Cuenta movil sin empresa asignada. Contacta al administrador."}), 403
        if mobile_account_access_blocked(admin_user):
            record_audit_event(
                store,
                "mobile_login_blocked",
                "admin_user",
                admin_user["id"],
                "Login movil operativo bloqueado por solicitud de eliminacion de cuenta.",
                actor={"id": admin_user["id"], "name": admin_user.get("name", email), "role": admin_user.get("role", "")},
                metadata={"email": email, "deletionStatus": admin_user.get("deletionStatus", "")},
                criticality="high",
            )
            save_store(store)
            return mobile_account_deletion_response(), 403
        if not company_subscription_allows_access(store, company_id):
            record_audit_event(
                store,
                "mobile_login_blocked",
                "subscription",
                company_id,
                "Login movil operativo bloqueado por suscripcion pendiente o suspendida.",
                actor={"id": admin_user["id"], "name": admin_user.get("name", email), "role": admin_user.get("role", "")},
                metadata={"email": email, "companyId": company_id},
            )
            save_store(store)
            return mobile_subscription_response(company_id)
        reset_login_attempts("mobile", email)
        admin_user["lastMobileLoginAt"] = utc_now()
        admin_user["lastMobileLoginIp"] = request_ip_address()
        admin_user["lastMobileDeviceId"] = login_device_id
        access_token = issue_mobile_admin_token(admin_user, login_device_id)
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
        return jsonify(mobile_admin_payload(admin_user, store, access_token))

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
        user = mobile_find_admin_for_token(store, token_payload)
        if user and mobile_account_access_blocked(user):
            record_audit_event(
                store,
                "mobile_refresh_blocked",
                "admin_user",
                user.get("id", ""),
                "Refresh movil bloqueado por solicitud de eliminacion de cuenta.",
                actor={"id": user.get("id", ""), "name": user.get("name", ""), "role": user.get("role", "")},
                metadata={"deletionStatus": user.get("deletionStatus", "")},
                criticality="high",
            )
            save_store(store)
            return mobile_account_deletion_response(), 403
        if (
            not user
            or user.get("status") != "active"
            or user.get("role") not in MOBILE_SALES_ROLES
            or user.get("mobileAccessEnabled", True) is False
            or not mobile_subject_matches_token_company(user, store, token_payload)
            or not mobile_token_version_valid(user, token_payload, "sessionVersion")
        ):
            return jsonify({"error": "Token movil invalido."}), 401
        return jsonify(mobile_admin_payload(user, store, issue_mobile_admin_token(user)))

    client = mobile_find_client_for_token(store, token_payload)
    if client and mobile_account_access_blocked(client):
        record_audit_event(
            store,
            "mobile_refresh_blocked",
            "client",
            client.get("id", ""),
            "Refresh movil bloqueado por solicitud de eliminacion de cuenta.",
            actor={"id": client.get("id", ""), "name": client.get("businessName", ""), "role": "client"},
            metadata={"deletionStatus": client.get("deletionStatus", "")},
            criticality="high",
        )
        save_store(store)
        return mobile_account_deletion_response(), 403
    if (
        not client
        or client.get("status") != "active"
        or client.get("mobileAccessEnabled", True) is False
        or not mobile_subject_matches_token_company(client, store, token_payload)
        or not mobile_token_version_valid(client, token_payload, "mobileSessionVersion")
    ):
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
    subject = None
    session_revoked = False
    if token_payload and token_payload.get("type") == "admin":
        subject_type = "admin_user"
        user = mobile_find_admin_for_token(store, token_payload)
        if (
            user
            and user.get("status") == "active"
            and user.get("role") in MOBILE_SALES_ROLES
            and user.get("mobileAccessEnabled", True) is not False
            and mobile_subject_matches_token_company(user, store, token_payload)
            and mobile_token_version_valid(user, token_payload, "sessionVersion")
        ):
            subject = user
            before = copy.deepcopy(user)
            bump_user_session_version(user)
            user["updatedAt"] = utc_now()
            session_revoked = True
            record_change_event(
                store,
                "session_revoke",
                "admin_user",
                user["id"],
                "Token movil revocado por cierre de sesion.",
                before,
                user,
                actor={"id": user["id"], "name": user.get("name", subject_id), "role": user.get("role", "seller")},
            )
        subject_name = (user or {}).get("name", subject_id)
    elif token_payload:
        subject_type = "client"
        client = mobile_find_client_for_token(store, token_payload)
        if (
            client
            and client.get("status") == "active"
            and mobile_subject_matches_token_company(client, store, token_payload)
            and mobile_token_version_valid(client, token_payload, "mobileSessionVersion")
        ):
            subject = client
            before = copy.deepcopy(client)
            client["mobileSessionVersion"] = safe_int(client.get("mobileSessionVersion"), 0) + 1
            client["updatedAt"] = utc_now()
            session_revoked = True
            record_change_event(
                store,
                "session_revoke",
                "client",
                client["id"],
                "Token movil revocado por cierre de sesion.",
                before,
                client,
                actor={"id": client["id"], "name": client.get("businessName", subject_id), "role": "client"},
            )
        subject_name = (client or {}).get("businessName", subject_id)
    if subject:
        subject_id = subject.get("id", subject_id)
        subject_role = subject.get("role", subject_role)

    record_audit_event(
        store,
        "logout",
        subject_type,
        subject_id,
        "Cierre de sesion desde app movil.",
        actor={"id": subject_id, "name": subject_name, "role": subject_role},
        metadata={"sessionRevoked": session_revoked},
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
    subject = mobile_find_client_for_token(store, token_payload)
    subject_name_key = "businessName"
    if token_payload.get("type") == "admin":
        subject_type = "admin_user"
        subject = mobile_find_admin_for_token(store, token_payload)
        subject_name_key = "name"
        if subject and mobile_account_access_blocked(subject):
            return mobile_account_deletion_response(), 403
        if (
            not subject
            or subject.get("status") != "active"
            or subject.get("role") not in MOBILE_SALES_ROLES
            or subject.get("mobileAccessEnabled", True) is False
            or not mobile_subject_matches_token_company(subject, store, token_payload)
            or not mobile_token_version_valid(subject, token_payload, "sessionVersion")
        ):
            return jsonify({"error": "Token movil invalido."}), 401
    elif (
        not subject
        or subject.get("status") != "active"
        or subject.get("mobileAccessEnabled", True) is False
        or not mobile_subject_matches_token_company(subject, store, token_payload)
        or not mobile_token_version_valid(subject, token_payload, "mobileSessionVersion")
    ):
        return jsonify({"error": "Cliente no encontrado."}), 404
    elif mobile_account_access_blocked(subject):
        return mobile_account_deletion_response(), 403

    subject_company_id = mobile_required_company_id(subject)
    rate_limit_response = guard_mobile_write_rate_limit(
        store,
        action="mobile_password_change",
        actor=subject,
        actor_type=subject_type,
        company_id=subject_company_id,
    )
    if rate_limit_response:
        return rate_limit_response

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

    before = copy.deepcopy(subject)
    subject["passwordHash"] = generate_password_hash(new_password)
    subject["mustChangePassword"] = False
    if subject_type == "client":
        subject["mobileSessionVersion"] = safe_int(subject.get("mobileSessionVersion"), 0) + 1
    else:
        bump_user_session_version(subject)
    subject["updatedAt"] = utc_now()
    record_change_event(
        store,
        "password_change",
        subject_type,
        subject["id"],
        "Contrasena movil actualizada por el usuario.",
        before,
        subject,
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


@app.post("/api/v1/mobile/account/deletion-request")
@app.post("/api/mobile/account/deletion-request")
def api_mobile_account_deletion_request():
    store = load_store()
    token_payload = mobile_token_payload()
    if not token_payload:
        return jsonify({"meta": mobile_api_meta(), "error": "Token movil requerido.", "code": "mobile_token_required"}), 401

    subject_type = "client"
    subject = mobile_find_client_for_token(store, token_payload)
    version_key = "mobileSessionVersion"
    valid_subject = bool(subject and subject.get("status") == "active")

    if token_payload.get("type") == "admin":
        subject_type = "admin_user"
        subject = mobile_find_admin_for_token(store, token_payload)
        version_key = "sessionVersion"
        valid_subject = bool(
            subject
            and subject.get("status") == "active"
            and subject.get("role") in MOBILE_SALES_ROLES
            and subject.get("mobileAccessEnabled", True) is not False
            and mobile_subject_matches_token_company(subject, store, token_payload)
        )
    else:
        valid_subject = bool(
            subject
            and subject.get("status") == "active"
            and subject.get("mobileAccessEnabled", True) is not False
            and mobile_subject_matches_token_company(subject, store, token_payload)
        )

    if not subject or not valid_subject or not mobile_token_version_valid(subject, token_payload, version_key):
        return jsonify({"meta": mobile_api_meta(), "error": "Token movil invalido.", "code": "mobile_token_invalid"}), 401

    if mobile_account_deletion_status(subject) in ACCOUNT_DELETION_BLOCKING_STATUSES:
        return jsonify(
            {
                "meta": mobile_api_meta(),
                "status": "requested",
                "requestId": subject.get("deletionRequestId", ""),
                "message": "Solicitud ya registrada.",
            }
        )

    payload = request.get_json(silent=True) or {}
    actor = {
        "id": subject.get("id", ""),
        "name": subject.get("businessName") or subject.get("name") or subject.get("email", ""),
        "role": subject.get("role", "client") if subject_type == "admin_user" else "client",
    }
    request_id, created = request_mobile_account_deletion(
        store,
        subject_type,
        subject,
        channel="mobile",
        reason=payload.get("reason", ""),
        actor=actor,
    )
    save_store(store)
    return jsonify(
        {
            "meta": mobile_api_meta(),
            "status": "requested",
            "requestId": request_id,
            "created": created,
            "message": "Solicitud recibida. FVENTAS revisara la cuenta y bloqueara el acceso movil mientras se procesa.",
        }
    )


@app.post("/api/v1/mobile/auth/recover-password")
@app.post("/api/mobile/auth/recover-password")
def api_mobile_recover_password():
    store = load_store()
    payload = request.get_json(silent=True) or {}
    email = payload.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "Correo requerido."}), 400

    ip_address = request_ip_address()
    window_seconds = max(1, int(app.config.get("MOBILE_PASSWORD_RECOVERY_WINDOW_SECONDS", 300)))
    max_events = max(1, int(app.config.get("MOBILE_PASSWORD_RECOVERY_MAX_EVENTS", 5)))
    if public_submission_rate_limited(
        store,
        "mobile_password_recovery_rate_events",
        ip_address=ip_address,
        email=email,
        window_seconds=window_seconds,
        max_events=max_events,
    ):
        record_audit_event(
            store,
            "password_recovery_limited",
            "mobile_user",
            email,
            "Recuperacion movil bloqueada temporalmente por solicitudes repetidas.",
            actor={"id": email, "name": email, "role": "mobile"},
            metadata={"ipAddress": ip_address},
            criticality="medium",
        )
        save_store(store)
        return jsonify({"error": "Demasiadas solicitudes. Espera unos minutos."}), 429

    subject_type = "mobile_user"
    subject_id = email
    subject_name = email
    subject_role = "mobile"
    client_candidates = [
        item
        for item in store.get("clients", [])
        if item.get("email", "").lower() == email and item.get("status") == "active"
        and item.get("mobileAccessEnabled", True) is not False
        and not mobile_account_access_blocked(item)
    ]
    admin_candidates = [
        user
        for user in store.get("admin_users", [])
        if user.get("email", "").lower() == email
        and user.get("status") == "active"
        and user.get("mobileAccessEnabled", True) is not False
        and not mobile_account_access_blocked(user)
        and user.get("role") in MOBILE_SALES_ROLES
    ]
    if len(client_candidates) + len(admin_candidates) > 1:
        record_audit_event(
            store,
            "password_recovery_blocked",
            "mobile_user",
            email,
            "Recuperacion movil bloqueada por identidad duplicada.",
            actor={"id": email, "name": email, "role": "mobile"},
            metadata={
                "clientMatches": [client.get("id", "") for client in client_candidates],
                "adminMatches": [user.get("id", "") for user in admin_candidates],
            },
            criticality="high",
        )
        record_public_submission_rate_event(
            store,
            "mobile_password_recovery_rate_events",
            ip_address=ip_address,
            email=email,
            action="password_recovery",
            window_seconds=window_seconds,
        )
        save_store(store)
        return mobile_password_recovery_response()
    subject = client_candidates[0] if client_candidates else None
    if subject:
        subject_type = "client"
        subject_id = subject.get("id", email)
        subject_name = subject.get("businessName", email)
        subject_role = "client"
    else:
        subject = admin_candidates[0] if admin_candidates else None
        if subject:
            subject_type = "admin_user"
            subject_id = subject.get("id", email)
            subject_name = subject.get("name", email)
            subject_role = subject.get("role", "mobile")

    if subject:
        before = copy.deepcopy(subject)
        subject["passwordRecoveryRequestedAt"] = utc_now()
        subject["passwordRecoveryStatus"] = "pending"
        subject["updatedAt"] = utc_now()
        record_change_event(
            store,
            "password_reset_request",
            subject_type,
            subject_id,
            "Solicitud de recuperacion de contrasena desde app movil.",
            before,
            subject,
            actor={"id": subject_id, "name": subject_name, "role": subject_role},
        )
    else:
        record_audit_event(
            store,
            "password_reset_request",
            subject_type,
            subject_id,
            "Solicitud de recuperacion de contrasena desde app movil.",
            metadata={"email": email, "status": "received"},
            actor={"id": subject_id, "name": subject_name, "role": subject_role},
        )
    record_public_submission_rate_event(
        store,
        "mobile_password_recovery_rate_events",
        ip_address=ip_address,
        email=email,
        action="password_recovery",
        window_seconds=window_seconds,
    )
    save_store(store)
    return mobile_password_recovery_response()


@app.get("/api/v1/mobile/products")
@app.get("/api/mobile/products")
def api_products():
    store = load_store()
    profile, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    company_id = mobile_catalog_company_id(store, profile)
    products = [
        mobile_product_payload(product)
        for product in mobile_visible_products(store, company_id)
    ]
    products, filters = filter_mobile_products(products)
    products, sort = sort_mobile_products(products)
    return mobile_paginated_response(products, filters, sort)


@app.get("/api/v1/mobile/products/<product_id>")
@app.get("/api/mobile/products/<product_id>")
def api_mobile_product_detail(product_id: str):
    store = load_store()
    profile, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    company_id = mobile_catalog_company_id(store, profile)
    product = next(
        (
            item
            for item in mobile_visible_products(store, company_id)
            if item.get("id") == product_id or item.get("sku") == product_id
        ),
        None,
    )
    if not product:
        return jsonify({"error": "Producto no encontrado."}), 404
    related_skus = {str(sku) for sku in product.get("relatedSkus", [])}
    related_products = [
        mobile_product_payload(item)
        for item in mobile_visible_products(store, company_id)
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
    profile, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    company_id = mobile_catalog_company_id(store, profile)
    placement = request.args.get("placement")
    announcements = active_announcements(placement, store, company_id=company_id)
    announcements, filters = filter_mobile_announcements(announcements)
    announcements, sort = sort_mobile_announcements(announcements)
    return mobile_paginated_response(announcements, filters, sort)


@app.get("/api/v1/mobile/service-technicians")
@app.get("/api/mobile/service-technicians")
def api_service_technicians():
    store = load_store()
    profile, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    company_id = mobile_catalog_company_id(store, profile)
    technicians = mobile_visible_service_technicians(store, company_id)
    technicians, filters = filter_mobile_directory_items(technicians)
    technicians, sort = sort_mobile_directory_items(technicians)
    return mobile_paginated_response(technicians, filters, sort)


@app.get("/api/v1/mobile/locations")
@app.get("/api/mobile/locations")
def api_locations():
    store = load_store()
    profile, auth_error = require_mobile_catalog_access(store)
    if auth_error:
        return auth_error, 401
    company_id = mobile_catalog_company_id(store, profile)
    technicians = mobile_visible_service_technicians(store, company_id)
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
    currency_data = currency_context()
    active_company = {"id": DEFAULT_COMPANY_ID, "name": "FVENTAS", "status": "active"}
    active_subscription = {}
    try:
        if session.get("admin_authenticated"):
            store = load_store()
            active_company = current_company(store)
            active_subscription = current_subscription(store, active_company.get("id")) or {}
    except Exception:
        active_company = {"id": DEFAULT_COMPANY_ID, "name": "FVENTAS", "status": "active"}
        active_subscription = {}
    return {
        "money_usd": money_usd,
        "money_currency": money_currency,
        "convert_currency": convert_currency,
        "usd_to_clp": usd_to_clp,
        "currency_context": currency_context,
        "market_country": currency_data["market_country"],
        "market_profile": currency_data["market_profile"],
        "market_country_label": currency_data["market_profile"].get("label", ""),
        "sales_currency": currency_data["sales_currency"],
        "local_currency": currency_data["local_currency"],
        "exchange_rate": currency_data["exchange_rate"],
        "brand_name": "FVENTAS",
        "active_company": active_company,
        "active_company_name": active_company.get("name", "FVENTAS"),
        "active_subscription": active_subscription,
        "subscription_status_label": subscription_status_label,
    }


if __name__ == "__main__":
    app.run(
        host=os.environ.get("FVENTAS_DEV_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=app.config.get("ENV") != "production",
    )
