"""Structured logging setup for F1Scope.

Attaches a single console handler with a consistent format to the Flask
app logger. Verbosity follows the app's DEBUG flag, so local development
stays noisy while production/testing stay at INFO.
"""

from __future__ import annotations

import logging

from flask import Flask

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(app: Flask) -> None:
    """Attach and configure the console handler for ``app.logger``."""
    level = logging.DEBUG if app.debug else logging.INFO

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(level)
    app.logger.propagate = False
