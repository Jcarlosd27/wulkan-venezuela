from __future__ import annotations

import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.security import generate_password_hash


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import Config
from db import SessionLocal, init_database
from models import AdminUser, Client


DEFAULT_ADMIN_EMAILS = {"admin@wulkan.local"}
DEFAULT_CLIENT_EMAILS = {"ferreteria@wulkan.local"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def disabled_payload(payload: dict, status: str) -> dict:
    updated = dict(payload or {})
    updated["status"] = status
    updated["mustChangePassword"] = True
    updated["disabledReason"] = "disabled_default_production_account"
    updated["updatedAt"] = utc_now().isoformat()
    return updated


def random_password_hash() -> str:
    return generate_password_hash(secrets.token_urlsafe(48))


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

        clients = (
            session.query(Client)
            .filter(Client.email.in_(DEFAULT_CLIENT_EMAILS))
            .all()
        )
        for client in clients:
            client.status = "blocked"
            client.must_change_password = True
            client.password_hash = random_password_hash()
            client.updated_at = now
            client.payload = disabled_payload(client.payload, "blocked")
            disabled.append(f"client:{client.email}")

        session.commit()

    if disabled:
        print("Disabled default production accounts: " + ", ".join(disabled))
    else:
        print("No default production accounts found.")


if __name__ == "__main__":
    main()
