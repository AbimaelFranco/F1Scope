"""F1Scope Flask application factory."""
from __future__ import annotations

from flask import Flask

from app.config import get_config


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the F1Scope Flask application.

    Args:
        config_name: Explicit config name ("development", "testing",
            "production"). Falls back to the FLASK_ENV environment
            variable, defaulting to "development".
    """
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    _register_blueprints(app)

    return app


def _register_blueprints(app: Flask) -> None:
    from app.routes.api import api_bp
    from app.routes.views import views_bp

    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
