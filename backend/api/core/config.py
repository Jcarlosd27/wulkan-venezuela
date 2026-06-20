from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"


def env_value(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value != "":
            return value
    return default


def env_bool_any(*names: str, default: bool = False) -> bool:
    raw_value = env_value(*names, default="")
    if raw_value is None:
        return default
    if raw_value == "":
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def env_bool(name: str, default: bool = False) -> bool:
    return env_bool_any(name, default=default)


def normalize_database_url(database_url: str) -> str:
    """Return a SQLAlchemy URL compatible with the psycopg v3 driver."""
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    return database_url


def database_url() -> str:
    raw_url = (
        env_value("FVENTAS_DATABASE_URL", "DATABASE_URL")
        or f"sqlite:///{DATA_DIR / 'fventas.db'}"
    )
    return normalize_database_url(raw_url)


class Config:
    ENV = env_value("FVENTAS_ENV", default="development")
    APP_VERSION = env_value("FVENTAS_APP_VERSION", default="0.9.0")
    BUILD_SHA = env_value("FVENTAS_BUILD_SHA", default="")
    SECRET_KEY = env_value("FVENTAS_SECRET_KEY", default="fventas-dev")
    DATA_BACKEND = env_value("FVENTAS_DATA_BACKEND", default="json")
    DATABASE_URL = database_url()
    REQUIRE_MOBILE_TOKEN = env_bool_any("FVENTAS_REQUIRE_MOBILE_TOKEN", default=False)
    SQL_FALLBACK_TO_JSON = env_bool_any("FVENTAS_SQL_FALLBACK_TO_JSON", default=True)
    LOGIN_MAX_ATTEMPTS = int(env_value("FVENTAS_LOGIN_MAX_ATTEMPTS", default="5"))
    LOGIN_WINDOW_SECONDS = int(env_value("FVENTAS_LOGIN_WINDOW_SECONDS", default="300"))
    ADMIN_SESSION_IDLE_SECONDS = int(env_value("FVENTAS_ADMIN_SESSION_IDLE_SECONDS", default="3600"))
    ADMIN_SESSION_ABSOLUTE_SECONDS = int(env_value("FVENTAS_ADMIN_SESSION_ABSOLUTE_SECONDS", default="28800"))
    MOBILE_TOKEN_MAX_AGE_SECONDS = int(env_value("FVENTAS_MOBILE_TOKEN_MAX_AGE_SECONDS", default=str(60 * 60 * 24 * 7)))
    REJECT_LEGACY_MOBILE_TOKENS = env_bool_any("FVENTAS_REJECT_LEGACY_MOBILE_TOKENS", default=False)
    REQUIRE_MOBILE_DEVICE_HEADER = env_bool_any("FVENTAS_REQUIRE_MOBILE_DEVICE_HEADER", default=False)
    ALLOW_LEGACY_MOBILE_API = env_bool_any("FVENTAS_ALLOW_LEGACY_MOBILE_API", default=True)
    READYZ_PUBLIC_DETAILS = env_bool_any("FVENTAS_READYZ_PUBLIC_DETAILS", default=False)
    TRUST_PROXY_HEADERS = env_bool_any("FVENTAS_TRUST_PROXY_HEADERS", default=False)
    LANDING_ACCESS_PREFERENCE_WINDOW_SECONDS = int(env_value("FVENTAS_LANDING_ACCESS_PREFERENCE_WINDOW_SECONDS", default="60"))
    LANDING_ACCESS_PREFERENCE_MAX_EVENTS = int(env_value("FVENTAS_LANDING_ACCESS_PREFERENCE_MAX_EVENTS", default="12"))
    SIGNUP_WINDOW_SECONDS = int(env_value("FVENTAS_SIGNUP_WINDOW_SECONDS", default="300"))
    SIGNUP_MAX_EVENTS = int(env_value("FVENTAS_SIGNUP_MAX_EVENTS", default="5"))
    ACCOUNT_DELETION_WINDOW_SECONDS = int(env_value("FVENTAS_ACCOUNT_DELETION_WINDOW_SECONDS", default="300"))
    ACCOUNT_DELETION_MAX_EVENTS = int(env_value("FVENTAS_ACCOUNT_DELETION_MAX_EVENTS", default="5"))
    MOBILE_PASSWORD_RECOVERY_WINDOW_SECONDS = int(env_value("FVENTAS_MOBILE_PASSWORD_RECOVERY_WINDOW_SECONDS", default="300"))
    MOBILE_PASSWORD_RECOVERY_MAX_EVENTS = int(env_value("FVENTAS_MOBILE_PASSWORD_RECOVERY_MAX_EVENTS", default="5"))
    MOBILE_WRITE_WINDOW_SECONDS = int(env_value("FVENTAS_MOBILE_WRITE_WINDOW_SECONDS", default="60"))
    MOBILE_WRITE_MAX_EVENTS = int(env_value("FVENTAS_MOBILE_WRITE_MAX_EVENTS", default="30"))
    UPLOAD_FOLDER = env_value("FVENTAS_UPLOAD_FOLDER", default=str(UPLOAD_DIR))
    STORAGE_BACKEND = env_value("FVENTAS_STORAGE_BACKEND", default="local")
    STORAGE_PUBLIC_BASE_URL = env_value("FVENTAS_STORAGE_PUBLIC_BASE_URL", default="")
    S3_BUCKET = env_value("FVENTAS_S3_BUCKET", default="")
    S3_REGION = env_value("FVENTAS_S3_REGION", default="us-east-1")
    S3_ENDPOINT_URL = env_value("FVENTAS_S3_ENDPOINT_URL", default="")
    S3_PREFIX = env_value("FVENTAS_S3_PREFIX", default="fventas")
    S3_ACL = env_value("FVENTAS_S3_ACL", default="")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DB_POOL_SIZE = int(env_value("FVENTAS_DB_POOL_SIZE", default="2"))
    DB_MAX_OVERFLOW = int(env_value("FVENTAS_DB_MAX_OVERFLOW", default="2"))
    DB_POOL_RECYCLE_SECONDS = int(env_value("FVENTAS_DB_POOL_RECYCLE_SECONDS", default="1800"))
    BACKUP_DIR = env_value("FVENTAS_BACKUP_DIR", default="backups")
    LOG_LEVEL = env_value("FVENTAS_LOG_LEVEL", default="INFO")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    MAX_CONTENT_LENGTH = int(env_value("FVENTAS_MAX_UPLOAD_MB", default="16")) * 1024 * 1024
    MAX_IMPORT_ROWS = int(env_value("FVENTAS_MAX_IMPORT_ROWS", default="5000"))
    DOCUMENT_SIGNED_URL_MAX_AGE_SECONDS = int(env_value("FVENTAS_DOCUMENT_SIGNED_URL_MAX_AGE_SECONDS", default="300"))
    CONTENT_SECURITY_POLICY_REPORT_ONLY = env_bool_any("FVENTAS_CSP_REPORT_ONLY", default=True)


class DevelopmentConfig(Config):
    ENV = "development"


class StagingConfig(Config):
    ENV = "staging"
    REQUIRE_MOBILE_TOKEN = True
    CONTENT_SECURITY_POLICY_REPORT_ONLY = env_bool_any("FVENTAS_CSP_REPORT_ONLY", default=False)


class ProductionConfig(Config):
    ENV = "production"
    DATA_BACKEND = env_value("FVENTAS_DATA_BACKEND", default="sql")
    STORAGE_BACKEND = env_value("FVENTAS_STORAGE_BACKEND", default="s3")
    REQUIRE_MOBILE_TOKEN = True
    SQL_FALLBACK_TO_JSON = env_bool_any("FVENTAS_SQL_FALLBACK_TO_JSON", default=False)
    SESSION_COOKIE_SECURE = True
    REJECT_LEGACY_MOBILE_TOKENS = env_bool_any("FVENTAS_REJECT_LEGACY_MOBILE_TOKENS", default=True)
    REQUIRE_MOBILE_DEVICE_HEADER = env_bool_any("FVENTAS_REQUIRE_MOBILE_DEVICE_HEADER", default=True)
    ALLOW_LEGACY_MOBILE_API = env_bool_any("FVENTAS_ALLOW_LEGACY_MOBILE_API", default=False)
    CONTENT_SECURITY_POLICY_REPORT_ONLY = env_bool_any("FVENTAS_CSP_REPORT_ONLY", default=False)


class DesktopConfig(Config):
    ENV = "desktop"
    DATA_BACKEND = env_value("FVENTAS_DATA_BACKEND", default="sql")
    STORAGE_BACKEND = env_value("FVENTAS_STORAGE_BACKEND", default="local")
    REQUIRE_MOBILE_TOKEN = env_bool_any("FVENTAS_REQUIRE_MOBILE_TOKEN", default=False)
    SQL_FALLBACK_TO_JSON = env_bool_any("FVENTAS_SQL_FALLBACK_TO_JSON", default=False)
    SESSION_COOKIE_SECURE = False
    REJECT_LEGACY_MOBILE_TOKENS = env_bool_any("FVENTAS_REJECT_LEGACY_MOBILE_TOKENS", default=False)


CONFIG_BY_ENV = {
    "development": DevelopmentConfig,
    "staging": StagingConfig,
    "production": ProductionConfig,
    "desktop": DesktopConfig,
}


def get_config() -> type[Config]:
    return CONFIG_BY_ENV.get(env_value("FVENTAS_ENV", default="development"), DevelopmentConfig)
