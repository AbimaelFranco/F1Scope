"""F1Scope Flask application factory."""
from __future__ import annotations

from flask import Flask

from app.config import get_config
from app.errors import register_error_handlers
from app.logging_config import configure_logging


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the F1Scope Flask application.

    Args:
        config_name: Explicit config name ("development", "testing",
            "production"). Falls back to the FLASK_ENV environment
            variable, defaulting to "development".
    """
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    configure_logging(app)
    _register_blueprints(app)
    register_error_handlers(app)

    app.logger.info("F1Scope starting (debug=%s)", app.debug)

    return app


def _register_blueprints(app: Flask) -> None:
    from app.routes.api import api_bp
    from app.routes.views import views_bp

    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
