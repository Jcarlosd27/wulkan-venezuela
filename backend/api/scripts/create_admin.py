from __future__ import annotations

import argparse
import getpass
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.security import generate_password_hash as werkzeug_generate_password_hash


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.db import SessionLocal, init_database
from models import AdminUser
from store import DEFAULT_COMPANY_ID


ROLES = {
    "platform_admin",
    "super_admin",
    "general_manager",
    "commercial_manager",
    "operator",
    "sales",
    "inventory",
    "collections",
    "dispatch",
    "auditor",
    "readonly",
}
PASSWORD_MIN_LENGTH = 10


def generate_password_hash(password: str) -> str:
    method = "scrypt" if hasattr(hashlib, "scrypt") else "pbkdf2:sha256:1000000"
    return werkzeug_generate_password_hash(password, method=method)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "admin"


def row_company_id(user: AdminUser) -> str:
    payload = user.payload or {}
    return str(payload.get("companyId") or DEFAULT_COMPANY_ID)


def password_errors(password: str) -> list[str]:
    errors: list[str] = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"Debe tener al menos {PASSWORD_MIN_LENGTH} caracteres.")
    if not any(char.isalpha() for char in password):
        errors.append("Debe incluir letras.")
    if not any(char.isdigit() for char in password):
        errors.append("Debe incluir numeros.")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or reset a FVENTAS admin user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", default="super_admin", choices=sorted(ROLES))
    parser.add_argument("--company-id", default=DEFAULT_COMPANY_ID)
    parser.add_argument("--password", default="")
    parser.add_argument("--inactive", action="store_true", help="Create the user as inactive.")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Nueva contrasena temporal: ")
    errors = password_errors(password)
    if errors:
        raise SystemExit(" ".join(errors))

    init_database()
    now = utc_now()
    email = args.email.strip().lower()
    company_id = args.company_id.strip() or DEFAULT_COMPANY_ID
    with SessionLocal() as session:
        email_matches = session.query(AdminUser).filter(AdminUser.email == email).all()
        company_matches = [user for user in email_matches if row_company_id(user) == company_id]
        if len(company_matches) > 1:
            raise SystemExit(f"Existen multiples admins con {email} en {company_id}. Corrige duplicados antes de resetear.")
        user = company_matches[0] if company_matches else None
        if user is None:
            user = AdminUser(
                id=f"admin-{slugify(company_id)}-{slugify(email)}",
                email=email,
                created_at=now,
                payload={},
            )
            session.add(user)

        user.name = args.name.strip()
        user.email = email
        user.role = args.role
        user.status = "inactive" if args.inactive else "active"
        user.password_hash = generate_password_hash(password)
        user.must_change_password = True
        user.updated_at = now
        user.payload = {
            "id": user.id,
            "companyId": company_id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "status": user.status,
            "mustChangePassword": True,
            "createdAt": user.created_at.isoformat(),
            "updatedAt": user.updated_at.isoformat(),
        }
        session.commit()

    print(f"Admin listo: {email} ({args.role}). Debe cambiar contrasena al ingresar.")


if __name__ == "__main__":
    main()
