from __future__ import annotations

import os
import secrets
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_
from werkzeug.security import generate_password_hash as werkzeug_generate_password_hash


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.config import Config
from core.db import SessionLocal, init_database
from models import (
    AdminUser,
    Announcement,
    AuditEvent,
    Category,
    Client,
    CreditMovement,
    Order,
    Product,
    ServiceTechnician,
    StockMovement,
)
from store import (
    INSECURE_PRODUCTION_ADMIN_EMAILS,
    INSECURE_PRODUCTION_ANNOUNCEMENT_IDS,
    INSECURE_PRODUCTION_CATEGORY_IDS,
    INSECURE_PRODUCTION_CLIENT_IDS,
    INSECURE_PRODUCTION_CLIENT_EMAILS,
    INSECURE_PRODUCTION_ORDER_PREFIXES,
    INSECURE_PRODUCTION_PRODUCT_IDS,
    INSECURE_PRODUCTION_SERVICE_TECHNICIAN_IDS,
    INSECURE_PRODUCTION_STOCK_MOVEMENT_IDS,
)


DEFAULT_ADMIN_EMAILS = INSECURE_PRODUCTION_ADMIN_EMAILS
DEFAULT_CLIENT_EMAILS = INSECURE_PRODUCTION_CLIENT_EMAILS
DEFAULT_ORDER_MARKERS = ("%demo%", "%@fventas.local%")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def disabled_payload(payload: dict, status: str) -> dict:
    updated = dict(payload or {})
    updated["status"] = status
    updated["mustChangePassword"] = True
    updated["disabledReason"] = "disabled_default_production_account"
    updated["updatedAt"] = utc_now().isoformat()
    return updated


def disabled_catalog_payload(payload: dict, status: str) -> dict:
    updated = dict(payload or {})
    updated["status"] = status
    updated["disabledReason"] = "disabled_default_production_seed"
    updated["updatedAt"] = utc_now().isoformat()
    return updated


def random_password_hash() -> str:
    method = "scrypt" if hasattr(hashlib, "scrypt") else "pbkdf2:sha256:1000000"
    return werkzeug_generate_password_hash(secrets.token_urlsafe(48), method=method)


def disable_status_rows(session, model, ids: set[str], status: str, label: str) -> list[str]:
    rows = session.query(model).filter(model.id.in_(ids)).all()
    disabled: list[str] = []
    now = utc_now()
    for row in rows:
        row.status = status
        row.updated_at = now
        row.payload = disabled_catalog_payload(row.payload, status)
        disabled.append(f"{label}:{row.id}")
    return disabled


def delete_matching(session, model, filters: list, label: str) -> list[str]:
    if not filters:
        return []

    deleted = session.query(model).filter(or_(*filters)).delete(synchronize_session=False)
    return [f"{label}:{deleted}"] if deleted else []


def main() -> None:
    if str(Config.ENV).strip().lower() != "production":
        print("Skipping production hardening outside production.")
        return
    if os.environ.get("FVENTAS_HARDEN_DEFAULT_ACCOUNTS", "1").strip().lower() in {"0", "false", "no", "off"}:
        print("Skipping production hardening by configuration.")
        return

    init_database()
    disabled: list[str] = []
    now = utc_now()

    with SessionLocal() as session:
        admin_users = (
            session.query(AdminUser)
            .filter(AdminUser.email.in_(DEFAULT_ADMIN_EMAILS))
            .all()
        )
        for user in admin_users:
            user.status = "inactive"
            user.must_change_password = True
            user.password_hash = random_password_hash()
            user.updated_at = now
            user.payload = disabled_payload(user.payload, "inactive")
            disabled.append(f"admin:{user.email}")

        demo_clients = (
            session.query(Client)
            .filter(
                or_(
                    Client.id.in_(INSECURE_PRODUCTION_CLIENT_IDS),
                    Client.email.in_(DEFAULT_CLIENT_EMAILS),
                    Client.email.ilike("%@fventas.local"),
                    Client.business_name.ilike("%demo%"),
                )
            )
            .all()
        )
        demo_client_ids = {client.id for client in demo_clients}

        demo_order_filters = [
            Order.id.startswith(prefix) for prefix in INSECURE_PRODUCTION_ORDER_PREFIXES
        ] + [
            Order.order_number.startswith(prefix) for prefix in INSECURE_PRODUCTION_ORDER_PREFIXES
        ]
        if demo_client_ids:
            demo_order_filters.append(Order.customer_id.in_(demo_client_ids))
        for marker in DEFAULT_ORDER_MARKERS:
            demo_order_filters.extend(
                [
                    Order.id.ilike(marker),
                    Order.order_number.ilike(marker),
                ]
            )

        demo_orders = (
            session.query(Order)
            .filter(or_(*demo_order_filters))
            .all()
            if demo_order_filters
            else []
        )
        demo_order_ids = {order.id for order in demo_orders} | {order.order_number for order in demo_orders}

        if demo_client_ids or demo_order_ids:
            credit_filters = []
            if demo_client_ids:
                credit_filters.append(CreditMovement.client_id.in_(demo_client_ids))
            if demo_order_ids:
                credit_filters.append(CreditMovement.order_id.in_(demo_order_ids))
            credit_filters.extend(
                CreditMovement.order_id.startswith(prefix)
                for prefix in INSECURE_PRODUCTION_ORDER_PREFIXES
            )
            disabled.extend(delete_matching(session, CreditMovement, credit_filters, "credit-movement-demo"))

            audit_filters = []
            entity_ids = demo_client_ids | demo_order_ids
            if entity_ids:
                audit_filters.append(AuditEvent.entity_id.in_(entity_ids))
            audit_filters.extend(
                [
                    AuditEvent.detail.ilike("%Cliente Demo Santiago%"),
                    AuditEvent.detail.ilike("%demo%"),
                    AuditEvent.detail.ilike("%@fventas.local%"),
                ]
            )
            disabled.extend(delete_matching(session, AuditEvent, audit_filters, "audit-demo"))

            stock_filters = [
                StockMovement.id.in_(INSECURE_PRODUCTION_STOCK_MOVEMENT_IDS),
                StockMovement.product_id.in_(INSECURE_PRODUCTION_PRODUCT_IDS),
            ]
            stock_filters.extend(
                StockMovement.note.ilike(f"%{prefix}%")
                for prefix in INSECURE_PRODUCTION_ORDER_PREFIXES
            )
            disabled.extend(delete_matching(session, StockMovement, stock_filters, "stock-movement-demo"))

            order_filters = []
            if demo_order_ids:
                order_filters.extend([Order.id.in_(demo_order_ids), Order.order_number.in_(demo_order_ids)])
            if demo_client_ids:
                order_filters.append(Order.customer_id.in_(demo_client_ids))
            order_filters.extend(
                Order.id.startswith(prefix) for prefix in INSECURE_PRODUCTION_ORDER_PREFIXES
            )
            order_filters.extend(
                Order.order_number.startswith(prefix) for prefix in INSECURE_PRODUCTION_ORDER_PREFIXES
            )
            disabled.extend(delete_matching(session, Order, order_filters, "order-demo"))
            session.flush()

            if demo_client_ids:
                disabled.extend(
                    delete_matching(session, Client, [Client.id.in_(demo_client_ids)], "client-demo")
                )
                session.flush()

        disabled.extend(disable_status_rows(session, Product, INSECURE_PRODUCTION_PRODUCT_IDS, "deleted", "product"))
        disabled.extend(disable_status_rows(session, Category, INSECURE_PRODUCTION_CATEGORY_IDS, "deleted", "category"))
        disabled.extend(
            disable_status_rows(session, Announcement, INSECURE_PRODUCTION_ANNOUNCEMENT_IDS, "deleted", "announcement")
        )

        technicians = (
            session.query(ServiceTechnician)
            .filter(ServiceTechnician.id.in_(INSECURE_PRODUCTION_SERVICE_TECHNICIAN_IDS))
            .all()
        )
        for technician in technicians:
            technician.status = "inactive"
            technician.visible_in_app = False
            technician.updated_at = now
            technician.payload = disabled_catalog_payload(technician.payload, "inactive")
            technician.payload["visibleInApp"] = False
            disabled.append(f"service-technician:{technician.id}")

        disabled.extend(
            delete_matching(
                session,
                StockMovement,
                [
                    StockMovement.id.in_(INSECURE_PRODUCTION_STOCK_MOVEMENT_IDS),
                    StockMovement.product_id.in_(INSECURE_PRODUCTION_PRODUCT_IDS),
                ],
                "stock-movement",
            )
        )

        session.commit()

    if disabled:
        print("Disabled default production accounts: " + ", ".join(disabled))
    else:
        print("No default production accounts found.")


if __name__ == "__main__":
    main()
