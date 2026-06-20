from __future__ import annotations

import argparse
import getpass
import hashlib
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from werkzeug.security import generate_password_hash as werkzeug_generate_password_hash


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.db import SessionLocal, init_database
from models import AuditEvent, Client
from store import DEFAULT_COMPANY_ID


PASSWORD_MIN_LENGTH = 10


def generate_password_hash(password: str) -> str:
    method = "scrypt" if hasattr(hashlib, "scrypt") else "pbkdf2:sha256:1000000"
    return werkzeug_generate_password_hash(password, method=method)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "client"


def row_company_id(client: Client) -> str:
    payload = client.payload or {}
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


def build_payload(args: argparse.Namespace, client_id: str, password_hash: str, now: datetime) -> dict:
    business_name = args.business_name.strip()
    company_id = args.company_id.strip() or DEFAULT_COMPANY_ID
    return {
        "id": client_id,
        "companyId": company_id,
        "legalName": args.legal_name.strip() or business_name,
        "commercialName": args.commercial_name.strip() or business_name,
        "businessName": business_name,
        "taxId": args.tax_id.strip(),
        "contactName": args.contact_name.strip(),
        "administrativeContact": args.contact_name.strip(),
        "receivingContact": args.contact_name.strip(),
        "phone": args.phone.strip(),
        "whatsapp": args.whatsapp.strip() or args.phone.strip(),
        "email": args.email.strip().lower(),
        "clientType": "b2b",
        "clientCategory": "review",
        "priceList": "b2b",
        "authorizedDiscountPercent": 0.0,
        "status": "active",
        "onboardingStatus": "review_account",
        "address": args.address.strip(),
        "fiscalAddress": args.address.strip(),
        "shippingAddress": args.address.strip(),
        "country": args.country.strip() or "CL",
        "state": args.state.strip(),
        "city": args.city.strip(),
        "deliveryZone": "Google Play Review",
        "assignedSellerId": "",
        "assignedSellerName": "",
        "defaultSaleType": "cash",
        "allowedPaymentTermsDays": [0],
        "collectionStatus": "without_debt",
        "creditRiskLevel": "low",
        "creditScore": 0,
        "creditManagerNote": "Cuenta tecnica para revision de Google Play. No usar para operaciones comerciales reales.",
        "creditReviewedBy": "",
        "creditReviewedAt": "",
        "creditRequestStatus": "none",
        "creditRequestedUsd": 0.0,
        "creditEnabled": False,
        "creditLimitUsd": 0.0,
        "creditUsedUsd": 0.0,
        "paymentTermsDays": 0,
        "notes": "Cuenta de acceso para revision de Google Play. Sin credito, sin pagos online y sin cartera comercial.",
        "passwordHash": password_hash,
        "mustChangePassword": False,
        "mobileSessionVersion": 0,
        "createdAt": now.isoformat(),
        "updatedAt": now.isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or reset a mobile B2B client account.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--business-name", default="Google Play Reviewer FVENTAS")
    parser.add_argument("--legal-name", default="")
    parser.add_argument("--commercial-name", default="")
    parser.add_argument("--tax-id", default="11.111.111-1")
    parser.add_argument("--contact-name", default="Google Play Reviewer")
    parser.add_argument("--phone", default="")
    parser.add_argument("--whatsapp", default="")
    parser.add_argument("--address", default="Cuenta tecnica de revision")
    parser.add_argument("--country", default="CL")
    parser.add_argument("--state", default="")
    parser.add_argument("--city", default="")
    parser.add_argument("--company-id", default=DEFAULT_COMPANY_ID)
    parser.add_argument("--password", default="")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Nueva contrasena para app movil: ")
    errors = password_errors(password)
    if errors:
        raise SystemExit(" ".join(errors))

    init_database()
    now = utc_now()
    email = args.email.strip().lower()
    company_id = args.company_id.strip() or DEFAULT_COMPANY_ID
    password_hash = generate_password_hash(password)

    with SessionLocal() as session:
        email_matches = session.query(Client).filter(Client.email == email).all()
        company_matches = [client for client in email_matches if row_company_id(client) == company_id]
        if len(company_matches) > 1:
            raise SystemExit(f"Existen multiples clientes con {email} en {company_id}. Corrige duplicados antes de resetear.")
        client = company_matches[0] if company_matches else None
        created = client is None
        if client is None:
            client = Client(
                id=f"client-{slugify(company_id)}-{slugify(email)}",
                email=email,
                created_at=now,
                payload={},
            )
            session.add(client)

        payload = build_payload(args, client.id, password_hash, now)
        if not created:
            created_at = client.created_at or now
            payload["createdAt"] = created_at.isoformat()
            client.created_at = created_at

        client.business_name = payload["businessName"]
        client.tax_id = payload["taxId"]
        client.contact_name = payload["contactName"]
        client.phone = payload["phone"]
        client.email = email
        client.password_hash = password_hash
        client.must_change_password = False
        client.client_type = "b2b"
        client.status = "active"
        client.credit_enabled = False
        client.credit_limit_usd = 0.0
        client.credit_used_usd = 0.0
        client.payment_terms_days = 0
        client.notes = payload["notes"]
        client.updated_at = now
        client.payload = payload

        audit_id = f"audit-google-play-review-{slugify(email)}-{int(now.timestamp())}"
        session.add(
            AuditEvent(
                id=audit_id,
                actor_id="system",
                actor_name="Create mobile client script",
                actor_role="system",
                action="create" if created else "password_reset",
                entity_type="client",
                entity_id=client.id,
                detail=f"Cuenta movil de revision Google Play {'creada' if created else 'actualizada'}: {payload['businessName']}.",
                ip_address="",
                path="scripts/create_mobile_client.py",
                method="CLI",
                created_at=now,
                payload={
                    "email": email,
                    "purpose": "google_play_review_user",
                    "created": created,
                    "creditEnabled": False,
                    "creditLimitUsd": 0.0,
                },
            )
        )
        session.commit()

    verb = "creado" if created else "actualizado"
    print(f"Cliente movil {verb}: {email} ({payload['businessName']}).")


if __name__ == "__main__":
    main()
