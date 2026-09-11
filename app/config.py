"""Environment-based configuration for the F1Scope Flask app.

Values are read from environment variables (see .env.example) so the same
codebase runs the same way locally and inside the Docker container. Nothing
here requires a real secret for v1 — OpenF1's free tier needs no API key.
"""
from __future__ import annotations

import os


class Config:
    """Base configuration shared by every environment."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    # OpenF1 integration (see docs/PLANNING.md section 2).
    OPENF1_BASE_URL = os.environ.get("OPENF1_BASE_URL", "https://api.openf1.org/v1")

    # Local session cache — persisted on a Docker volume in production so
    # ingested sessions survive container restarts.
    CACHE_DIR = os.environ.get("CACHE_DIR", "instance/cache")


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    DEBUG = True
    TESTING = True


class ProductionConfig(Config):
    DEBUG = False


_CONFIGS: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    """Resolve a config class by explicit name, FLASK_ENV, or a dev default."""
    resolved = name or os.environ.get("FLASK_ENV", "development")
    return _CONFIGS.get(resolved, DevelopmentConfig)
