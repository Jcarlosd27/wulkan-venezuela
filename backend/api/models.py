from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
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
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Client(TimestampMixin, Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    business_name: Mapped[str] = mapped_column(String(180), nullable=False)
    tax_id: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    contact_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), default="", nullable=False)
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

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    image_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Product(TimestampMixin, Base):
    __tablename__ = "products"

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

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(80), ForeignKey("products.id"), nullable=False)
    sku: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    movement_type: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

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


class CreditMovement(Base):
    __tablename__ = "credit_movements"

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
