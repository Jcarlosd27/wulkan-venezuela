from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import sys
import threading
from pathlib import Path

from werkzeug.serving import make_server


APP_NAME = "FVENTAS Desktop"
DEFAULT_ADMIN_EMAIL = "admin@fventas.local"


def desktop_root() -> Path:
    configured_root = os.environ.get("FVENTAS_DESKTOP_HOME", "").strip()
    if configured_root:
        return Path(configured_root).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        return Path(local_app_data) / APP_NAME
    return Path.home() / f".{APP_NAME.lower().replace(' ', '-')}"


def sqlite_url(database_path: Path) -> str:
    return f"sqlite:///{database_path.as_posix()}"


def ensure_secret_key(root: Path) -> str:
    secret_path = root / "secret.key"
    if secret_path.exists():
        secret = secret_path.read_text(encoding="utf-8").strip()
        if secret:
            return secret
    secret = secrets.token_urlsafe(48)
    secret_path.write_text(secret, encoding="utf-8")
    return secret


def prepare_environment() -> Path:
    root = desktop_root()
    data_dir = root / "data"
    uploads_dir = root / "uploads"
    backups_dir = root / "backups"
    for folder in (root, data_dir, uploads_dir, backups_dir):
        folder.mkdir(parents=True, exist_ok=True)

    os.environ["FVENTAS_ENV"] = "desktop"
    os.environ.setdefault("FVENTAS_DATA_BACKEND", "sql")
    os.environ.setdefault("FVENTAS_DATABASE_URL", sqlite_url(data_dir / "fventas.db"))
    os.environ.setdefault("FVENTAS_STORAGE_BACKEND", "local")
    os.environ.setdefault("FVENTAS_UPLOAD_FOLDER", str(uploads_dir))
    os.environ.setdefault("FVENTAS_BACKUP_DIR", str(backups_dir))
    os.environ.setdefault("FVENTAS_SQL_FALLBACK_TO_JSON", "0")
    os.environ.setdefault("FVENTAS_REQUIRE_MOBILE_TOKEN", "0")
    os.environ.setdefault("FVENTAS_SECRET_KEY", ensure_secret_key(root))
    return root


def generate_desktop_password() -> str:
    return f"Fventas-{secrets.randbelow(900000) + 100000}"


def generate_password_hash(password: str) -> str:
    from werkzeug.security import generate_password_hash as werkzeug_generate_password_hash

    method = "scrypt" if hasattr(hashlib, "scrypt") else "pbkdf2:sha256:1000000"
    return werkzeug_generate_password_hash(password, method=method)


def write_first_access_file(root: Path, password: str) -> None:
    content = (
        "Credenciales iniciales FVENTAS Desktop\n"
        "======================================\n\n"
        f"Usuario: {DEFAULT_ADMIN_EMAIL}\n"
        f"Contrasena temporal: {password}\n\n"
        "El sistema solicitara cambiar esta contrasena al primer ingreso.\n"
    )
    (root / "primer-acceso.txt").write_text(content, encoding="utf-8")


def ensure_desktop_admin(root: Path) -> None:
    from core.db import init_database
    from store import DEFAULT_COMPANY_ID, load_store, save_store, utc_now

    init_database()
    store = load_store()
    now = utc_now()
    active_admin_exists = any(
        user.get("status") == "active"
        and user.get("role") in {"super_admin", "platform_admin"}
        for user in store.get("admin_users", [])
    )
    if not active_admin_exists:
        password = os.environ.get("FVENTAS_DESKTOP_ADMIN_PASSWORD", "").strip() or generate_desktop_password()
        store.setdefault("admin_users", []).append(
            {
                "id": "admin-desktop-fventas",
                "companyId": DEFAULT_COMPANY_ID,
                "name": "Admin FVENTAS",
                "email": DEFAULT_ADMIN_EMAIL,
                "role": "super_admin",
                "status": "active",
                "passwordHash": generate_password_hash(password),
                "mustChangePassword": True,
                "sellerCode": "",
                "sellerZone": "",
                "sellerTerritory": "",
                "sellerSupervisor": "",
                "phone": "",
                "commissionRatePercent": 0.0,
                "salesGoalUsd": 0.0,
                "mobileAccessEnabled": True,
                "lastLoginAt": "",
                "lastMobileLoginAt": "",
                "createdAt": now,
                "updatedAt": now,
            }
        )
        write_first_access_file(root, password)
    save_store(store)


class EmbeddedServer(threading.Thread):
    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        super().__init__(daemon=True)
        from app import app

        self.server = make_server(host, port, app, threaded=True)
        self.host = host
        self.port = self.server.server_port

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def run(self) -> None:
        self.server.serve_forever()

    def stop(self) -> None:
        self.server.shutdown()


def run_window(server: EmbeddedServer) -> None:
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError(
            "pywebview no esta instalado. Ejecuta: python -m pip install -r requirements-desktop.txt"
        ) from exc

    webview.create_window(
        APP_NAME,
        f"{server.url}/login",
        width=1366,
        height=820,
        min_size=(1100, 720),
        text_select=True,
    )
    webview.start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ejecuta FVENTAS como aplicacion de escritorio Windows.")
    parser.add_argument("--check", action="store_true", help="Inicializa y valida el entorno sin abrir ventana.")
    args = parser.parse_args(argv)

    root = prepare_environment()
    ensure_desktop_admin(root)
    if args.check:
        print(f"{APP_NAME} listo.")
        print(f"Datos locales: {root}")
        print(f"Credenciales iniciales: {root / 'primer-acceso.txt'}")
        return 0

    server = EmbeddedServer()
    server.start()
    try:
        run_window(server)
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
