from __future__ import annotations

import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_
from werkzeug.security import generate_password_hash


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import Config
from db import SessionLocal, init_database
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
    return generate_password_hash(secrets.token_urlsafe(48))


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


def main() -> None:
    if str(Config.ENV).strip().lower() != "production":
        print("Skipping production hardening outside production.")
        return
    if os.environ.get("WULKAN_HARDEN_DEFAULT_ACCOUNTS", "1").strip().lower() in {"0", "false", "no", "off"}:
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
                    Client.business_name.ilike("Ferreteria Demo Valencia"),
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

        demo_orders = (
            session.query(Order)
            .filter(or_(*demo_order_filters))
            .all()
            if demo_order_filters
            else []
        )
        demo_order_ids = {order.id for order in demo_orders} | {order.order_number for order in demo_orders}

        if demo_client_ids or demo_order_ids:
            credit_deleted = (
                session.query(CreditMovement)
                .filter(
                    or_(
                        CreditMovement.client_id.in_(demo_client_ids or {""}),
                        CreditMovement.order_id.in_(demo_order_ids or {""}),
                    )
                )
                .delete(synchronize_session=False)
            )
            if credit_deleted:
                disabled.append(f"credit-movement-demo:{credit_deleted}")

            audit_deleted = (
                session.query(AuditEvent)
                .filter(
                    or_(
                        AuditEvent.entity_id.in_((demo_client_ids | demo_order_ids) or {""}),
                        AuditEvent.detail.ilike("%Ferreteria Demo Valencia%"),
                        AuditEvent.detail.ilike("%demo%"),
                    )
                )
                .delete(synchronize_session=False)
            )
            if audit_deleted:
                disabled.append(f"audit-demo:{audit_deleted}")

            for order in demo_orders:
                session.delete(order)
                disabled.append(f"order-demo:{order.order_number}")

            for client in demo_clients:
                session.delete(client)
                disabled.append(f"client-demo:{client.email}")

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

        stock_deleted = (
            session.query(StockMovement)
            .filter(StockMovement.id.in_(INSECURE_PRODUCTION_STOCK_MOVEMENT_IDS))
            .delete(synchronize_session=False)
        )
        if stock_deleted:
            disabled.append(f"stock-movement:{stock_deleted}")

        session.commit()

    if disabled:
        print("Disabled default production accounts: " + ", ".join(disabled))
    else:
        print("No default production accounts found.")


if __name__ == "__main__":
    main()
