"""Centralized error handling for F1Scope.

Errors are logged consistently and rendered differently depending on who
asked: the internal API (blueprint "api") gets a JSON error body, the web
views get a rendered HTML error page.

Note: with DEBUG=True (development), Flask propagates unhandled exceptions
to Werkzeug's interactive debugger instead of calling these handlers — that
is the desired local-dev experience. These handlers take over in
production/testing, where DEBUG is False.
"""
from __future__ import annotations

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

_ERROR_NAMES = {404: "not_found", 500: "internal_server_error"}


def register_error_handlers(app: Flask) -> None:
    """Register the app-wide 404/500/unexpected-exception handlers."""

    @app.errorhandler(404)
    def handle_not_found(error: HTTPException):
        return _error_response(error, status=404)

    @app.errorhandler(500)
    def handle_internal_error(error: HTTPException):
        app.logger.exception("Unhandled 500 error on %s", request.path)
        return _error_response(error, status=500)

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):
        app.logger.exception("Unhandled exception on %s", request.path)
        return _error_response(error, status=500)


def _wants_json() -> bool:
    """Serve JSON errors for the internal API, HTML pages everywhere else.

    Uses the path prefix rather than ``request.blueprint``: for a 404 on a
    URL that matches no rule at all (e.g. a typo'd /api/... path), Flask
    never resolves a blueprint, so that check would silently fall through
    to the HTML error page instead of JSON.
    """
    return request.path.startswith("/api/")


def _error_response(error: Exception, *, status: int):
    if _wants_json():
        message = error.description if isinstance(error, HTTPException) else "Internal server error"
        return jsonify(error=_ERROR_NAMES.get(status, "error"), message=message), status

    template = "errors/404.html" if status == 404 else "errors/500.html"
    return render_template(template), status
