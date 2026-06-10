from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"


def env_bool(name: str, default: bool = False) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


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
        os.environ.get("WULKAN_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or f"sqlite:///{DATA_DIR / 'wulkan.db'}"
    )
    return normalize_database_url(raw_url)


class Config:
    ENV = os.environ.get("WULKAN_ENV", "development")
    SECRET_KEY = os.environ.get("WULKAN_SECRET_KEY", "wulkan-dev")
    DATA_BACKEND = os.environ.get("WULKAN_DATA_BACKEND", "json")
    DATABASE_URL = database_url()
    REQUIRE_MOBILE_TOKEN = env_bool("WULKAN_REQUIRE_MOBILE_TOKEN", False)
    SQL_FALLBACK_TO_JSON = env_bool("WULKAN_SQL_FALLBACK_TO_JSON", True)
    LOGIN_MAX_ATTEMPTS = int(os.environ.get("WULKAN_LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_WINDOW_SECONDS = int(os.environ.get("WULKAN_LOGIN_WINDOW_SECONDS", "300"))
    UPLOAD_FOLDER = str(UPLOAD_DIR)
    STORAGE_BACKEND = os.environ.get("WULKAN_STORAGE_BACKEND", "local")
    STORAGE_PUBLIC_BASE_URL = os.environ.get("WULKAN_STORAGE_PUBLIC_BASE_URL", "")
    S3_BUCKET = os.environ.get("WULKAN_S3_BUCKET", "")
    S3_REGION = os.environ.get("WULKAN_S3_REGION", "us-east-1")
    S3_ENDPOINT_URL = os.environ.get("WULKAN_S3_ENDPOINT_URL", "")
    S3_PREFIX = os.environ.get("WULKAN_S3_PREFIX", "wulkan")
    S3_ACL = os.environ.get("WULKAN_S3_ACL", "")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DB_POOL_SIZE = int(os.environ.get("WULKAN_DB_POOL_SIZE", "2"))
    DB_MAX_OVERFLOW = int(os.environ.get("WULKAN_DB_MAX_OVERFLOW", "2"))
    DB_POOL_RECYCLE_SECONDS = int(os.environ.get("WULKAN_DB_POOL_RECYCLE_SECONDS", "1800"))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    MAX_CONTENT_LENGTH = int(os.environ.get("WULKAN_MAX_UPLOAD_MB", "16")) * 1024 * 1024


class DevelopmentConfig(Config):
    ENV = "development"


class StagingConfig(Config):
    ENV = "staging"
    REQUIRE_MOBILE_TOKEN = True


class ProductionConfig(Config):
    ENV = "production"
    DATA_BACKEND = os.environ.get("WULKAN_DATA_BACKEND", "sql")
    STORAGE_BACKEND = os.environ.get("WULKAN_STORAGE_BACKEND", "s3")
    REQUIRE_MOBILE_TOKEN = True
    SQL_FALLBACK_TO_JSON = env_bool("WULKAN_SQL_FALLBACK_TO_JSON", False)
    SESSION_COOKIE_SECURE = True


CONFIG_BY_ENV = {
    "development": DevelopmentConfig,
    "staging": StagingConfig,
    "production": ProductionConfig,
}


def get_config() -> type[Config]:
    return CONFIG_BY_ENV.get(os.environ.get("WULKAN_ENV", "development"), DevelopmentConfig)
