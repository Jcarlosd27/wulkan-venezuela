from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class AdminUser(TimestampMixin, Base):
    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="operator", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Client(TimestampMixin, Base):
    __tablename__ = "clients"
    __table_args__ = (
        Index("ix_clients_tax_id", "tax_id"),
        Index("ix_clients_status", "status"),
        Index("ix_clients_client_type", "client_type"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    business_name: Mapped[str] = mapped_column(String(180), nullable=False)
    tax_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    contact_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    client_type: Mapped[str] = mapped_column(String(50), default="ferretero", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    credit_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    credit_limit_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    credit_used_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Category(TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (Index("ix_categories_status", "status"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_status", "status"),
        Index("ix_products_product_type", "product_type"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    sku: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    product_type: Mapped[str] = mapped_column(String(60), default="machine", nullable=False)
    category_id: Mapped[str] = mapped_column(String(80), ForeignKey("categories.id"), nullable=False)
    category_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    public_price_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    original_price_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    discount_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    b2b_price_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    exchange_rate_usd_ves: Mapped[float] = mapped_column(Float, default=38.5, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    image_urls: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    pdf_urls: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    variants: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    specifications: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    requires_quote: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_technical_validation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rotation_last_30_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class MediaAsset(TimestampMixin, Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        Index("ix_media_assets_product_id", "product_id"),
        Index("ix_media_assets_asset_type", "asset_type"),
        Index("ix_media_assets_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(80), ForeignKey("products.id"))
    asset_type: Mapped[str] = mapped_column(String(50), default="image", nullable=False)
    url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Announcement(TimestampMixin, Base):
    __tablename__ = "announcements"
    __table_args__ = (
        Index("ix_announcements_placement", "placement"),
        Index("ix_announcements_status", "status"),
        Index("ix_announcements_priority", "priority"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    placement: Mapped[str] = mapped_column(String(50), default="home", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    cta_label: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    cta_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    starts_at: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    ends_at: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        Index("ix_stock_movements_product_id", "product_id"),
        Index("ix_stock_movements_movement_type", "movement_type"),
        Index("ix_stock_movements_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(80), ForeignKey("products.id"), nullable=False)
    sku: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    movement_type: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class BusinessSetting(TimestampMixin, Base):
    __tablename__ = "business_settings"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_customer_id", "customer_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_credit_status", "credit_status"),
        Index("ix_orders_payment_status", "payment_status"),
        Index("ix_orders_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    order_number: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    customer_id: Mapped[str] = mapped_column(String(80), ForeignKey("clients.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="credit_review", nullable=False)
    credit_status: Mapped[str] = mapped_column(String(50), default="manual_review", nullable=False)
    payment_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    total_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_ves: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    exchange_rate_usd_ves: Mapped[float] = mapped_column(Float, default=38.5, nullable=False)
    paid_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    balance_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    credit_before_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    credit_after_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    inventory_status: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    stock_status: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    managed_by: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    managed_at: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    customer_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Quote(TimestampMixin, Base):
    __tablename__ = "quotes"
    __table_args__ = (
        Index("ix_quotes_client_id", "client_id"),
        Index("ix_quotes_seller_id", "seller_id"),
        Index("ix_quotes_status", "status"),
        Index("ix_quotes_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    quote_number: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    client_id: Mapped[str] = mapped_column(String(80), ForeignKey("clients.id"), nullable=False)
    seller_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    valid_until: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    sale_type: Mapped[str] = mapped_column(String(50), default="cash", nullable=False)
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_ves: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    exchange_rate_usd_ves: Mapped[float] = mapped_column(Float, default=38.5, nullable=False)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    client_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    versions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    internal_comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    converted_order_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class CrmRecord(TimestampMixin, Base):
    __tablename__ = "crm_records"
    __table_args__ = (
        Index("ix_crm_records_record_type", "record_type"),
        Index("ix_crm_records_status", "status"),
        Index("ix_crm_records_client_id", "client_id"),
        Index("ix_crm_records_next_action_at", "next_action_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    record_type: Mapped[str] = mapped_column(String(50), default="lead", nullable=False)
    pipeline_stage: Mapped[str] = mapped_column(String(50), default="new_lead", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    client_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    seller_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    contact_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    estimated_value_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    probability_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expected_close_at: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    next_action_at: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    last_activity_at: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    activities: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class CreditMovement(Base):
    __tablename__ = "credit_movements"
    __table_args__ = (
        Index("ix_credit_movements_client_id", "client_id"),
        Index("ix_credit_movements_order_id", "order_id"),
        Index("ix_credit_movements_movement_type", "movement_type"),
        Index("ix_credit_movements_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    movement_type: Mapped[str] = mapped_column(String(50), nullable=False)
    client_id: Mapped[str] = mapped_column(String(80), ForeignKey("clients.id"), nullable=False)
    order_id: Mapped[str] = mapped_column(String(80), ForeignKey("orders.id"), nullable=False)
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    amount_ves: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    exchange_rate_usd_ves: Mapped[float] = mapped_column(Float, default=38.5, nullable=False)
    method: Mapped[str] = mapped_column(String(50), default="other", nullable=False)
    reference: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_priority", "priority"),
        Index("ix_notifications_created_at", "created_at"),
        Index("ix_notifications_module_created_at", "module", "created_at"),
        Index("ix_notifications_recipient_status", "recipient_type", "recipient_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notification_type: Mapped[str] = mapped_column(String(60), default="info", nullable=False)
    channel: Mapped[str] = mapped_column(String(40), default="web", nullable=False)
    priority: Mapped[str] = mapped_column(String(30), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="unread", nullable=False)
    recipient_type: Mapped[str] = mapped_column(String(40), default="admin", nullable=False)
    recipient_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    recipient_role: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    module: Mapped[str] = mapped_column(String(80), default="dashboard", nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    href: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    deep_link: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    read_at: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    expires_at: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ServiceTechnician(TimestampMixin, Base):
    __tablename__ = "service_technicians"
    __table_args__ = (
        Index("ix_service_technicians_state_city", "state", "city"),
        Index("ix_service_technicians_status", "status"),
        Index("ix_service_technicians_visible_in_app", "visible_in_app"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    company_name: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    contact_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    whatsapp: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    state: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    city: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    address: Mapped[str] = mapped_column(Text, default="", nullable=False)
    specialties: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    coverage: Mapped[str] = mapped_column(String(220), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    visible_in_app: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_created_at", "created_at"),
        Index("ix_audit_events_actor_created_at", "actor_id", "created_at"),
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
        Index("ix_audit_events_action", "action"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    actor_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    actor_role: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ip_address: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    path: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    method: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ImportDraft(Base):
    __tablename__ = "import_drafts"
    __table_args__ = (
        Index("ix_import_drafts_status", "status"),
        Index("ix_import_drafts_expires_at", "expires_at"),
        Index("ix_import_drafts_created_by_id", "created_by_id"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    module: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="preview", nullable=False)
    created_by_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    created_by_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
