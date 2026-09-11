"""Web view routes (HTML pages) for F1Scope.

Serves the Jinja2 templates and static assets (Three.js scene, telemetry
charts, cyberpunk theme). Kept separate from the internal JSON API in
app/routes/api.py — see docs/architecture/ for the full request flow.
"""

from flask import Blueprint, render_template

views_bp = Blueprint("views", __name__)


@views_bp.get("/")
def index():
    """Landing page: entry point for session/driver selection."""
    return render_template("index.html")
