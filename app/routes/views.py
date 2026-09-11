"""Web view routes (HTML pages) for F1Scope.

Serves the Jinja2 templates and static assets (Three.js scene, telemetry
charts, cyberpunk theme). Kept separate from the internal JSON API in
app/routes/api.py — see docs/architecture/ for the full request flow.
"""

from flask import Blueprint, abort, render_template, request

views_bp = Blueprint("views", __name__)


@views_bp.get("/")
def index():
    """Landing page: entry point for session/driver selection."""
    return render_template("index.html")


@views_bp.get("/replay")
def replay():
    """3D replay view for ?session_key=... (and optionally &drivers=...)."""
    session_key = request.args.get("session_key")
    if not session_key or not session_key.isdigit():
        abort(404, description="Missing or invalid session_key")
    return render_template("replay.html", session_key=session_key)
