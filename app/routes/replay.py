"""Internal API for session replay data (mounted under /api/session).

Unlike app/routes/api.py's live catalog-browsing endpoints, everything
here is served from the local session cache (milestone E2): a session is
ingested from OpenF1 at most once, the first time it's requested here —
see app.services.cache.get_or_ingest_session.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from app.services.cache import get_or_ingest_session
from app.services.ingestion import SessionIngestionError
from app.services.track import build_track

replay_bp = Blueprint("replay", __name__)


@replay_bp.get("/<int:session_key>/track")
def get_track(session_key: int):
    """Return a simplified 3D track shape for ``session_key``.

    Triggers a full session ingest (once, ever, per session — cached
    afterwards) if this session hasn't been requested before.
    """
    client = current_app.extensions["openf1_client"]
    cache = current_app.extensions["session_cache"]

    try:
        data = get_or_ingest_session(client, cache, session_key)
    except SessionIngestionError as exc:
        return jsonify(error="not_found", message=str(exc)), 404

    track = build_track(data.location, data.laps)
    if track is None:
        return jsonify(error="no_track_data", message="No location data for this session"), 404

    return jsonify(track)
