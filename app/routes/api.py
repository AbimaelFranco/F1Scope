"""Internal JSON API consumed by the frontend (mounted under /api).

This API only ever serves data already ingested into the local session
cache (see docs/PLANNING.md section 2) — it never proxies live requests to
OpenF1 on the frontend's behalf. The ingestion/cache endpoints land in a
later issue (milestone E2).
"""

from flask import Blueprint, jsonify

api_bp = Blueprint("api", __name__)


@api_bp.get("/health")
def health():
    """Basic liveness check for the internal API."""
    return jsonify(status="ok")
