from __future__ import annotations

import argparse
import getpass
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.security import generate_password_hash


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from db import SessionLocal, init_database
from models import AdminUser


ROLES = {"super_admin", "commercial_manager", "operator", "sales", "inventory", "readonly"}
PASSWORD_MIN_LENGTH = 10


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "admin"


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
    parser = argparse.ArgumentParser(description="Create or reset a Wulkan admin user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", default="super_admin", choices=sorted(ROLES))
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
    with SessionLocal() as session:
        user = session.query(AdminUser).filter(AdminUser.email == email).one_or_none()
        if user is None:
            user = AdminUser(
                id=f"admin-{slugify(email)}",
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
