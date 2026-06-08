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


class Config:
    ENV = os.environ.get("WULKAN_ENV", "development")
    SECRET_KEY = os.environ.get("WULKAN_SECRET_KEY", "wulkan-dev")
    DATA_BACKEND = os.environ.get("WULKAN_DATA_BACKEND", "json")
    DATABASE_URL = os.environ.get("WULKAN_DATABASE_URL", f"sqlite:///{DATA_DIR / 'wulkan.db'}")
    REQUIRE_MOBILE_TOKEN = env_bool("WULKAN_REQUIRE_MOBILE_TOKEN", False)
    SQL_FALLBACK_TO_JSON = env_bool("WULKAN_SQL_FALLBACK_TO_JSON", True)
    UPLOAD_FOLDER = str(UPLOAD_DIR)
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    ENV = "development"


class StagingConfig(Config):
    ENV = "staging"
    REQUIRE_MOBILE_TOKEN = True


class ProductionConfig(Config):
    ENV = "production"
    REQUIRE_MOBILE_TOKEN = True


CONFIG_BY_ENV = {
    "development": DevelopmentConfig,
    "staging": StagingConfig,
    "production": ProductionConfig,
}


def get_config() -> type[Config]:
    return CONFIG_BY_ENV.get(os.environ.get("WULKAN_ENV", "development"), DevelopmentConfig)
