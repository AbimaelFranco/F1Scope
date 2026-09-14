"""Internal API for session replay data (mounted under /api/session).

Unlike app/routes/api.py's live catalog-browsing endpoints, everything
here is served from the local session cache (milestone E2): a session is
ingested from OpenF1 at most once, the first time it's requested here —
see app.services.cache.get_or_ingest_session.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.services.cache import get_or_ingest_session
from app.services.ingestion import SessionData, SessionIngestionError
from app.services.standings import build_standings
from app.services.telemetry import TelemetryError, build_telemetry
from app.services.track import build_car_positions, build_track, session_time_origin

replay_bp = Blueprint("replay", __name__)


@replay_bp.get("/<int:session_key>/track")
def get_track(session_key: int):
    """Return a simplified 3D track shape for ``session_key``."""
    data = _get_session_or_404(session_key)
    if not isinstance(data, SessionData):
        return data  # error response, see _get_session_or_404

    track = build_track(data.location, data.laps)
    if track is None:
        return jsonify(error="no_track_data", message="No location data for this session"), 404

    return jsonify(track)


@replay_bp.get("/<int:session_key>/cars")
def get_cars(session_key: int):
    """Return downsampled per-driver position timeseries, for animating cars."""
    data = _get_session_or_404(session_key)
    if not isinstance(data, SessionData):
        return data  # error response, see _get_session_or_404

    return jsonify(build_car_positions(data.location, data.drivers))


@replay_bp.get("/<int:session_key>/telemetry")
def get_telemetry(session_key: int):
    """Return one driver's speed/throttle/brake/RPM/gear for a single lap.

    Query params: ``driver_number`` (required), ``lap_number`` (optional
    — defaults to that driver's first non-out-lap).
    """
    data = _get_session_or_404(session_key)
    if not isinstance(data, SessionData):
        return data  # error response, see _get_session_or_404

    driver_number = request.args.get("driver_number", type=int)
    if driver_number is None:
        return jsonify(error="bad_request", message="driver_number is required"), 400

    lap_number = request.args.get("lap_number", type=int)
    session_origin = session_time_origin(data.location)

    try:
        telemetry = build_telemetry(
            data.car_data, data.laps, driver_number, lap_number, session_origin=session_origin
        )
    except TelemetryError as exc:
        return jsonify(error="no_telemetry_data", message=str(exc)), 404

    return jsonify(telemetry)


@replay_bp.get("/<int:session_key>/standings")
def get_standings(session_key: int):
    """Return per-driver position/gap/interval timeseries for the HUD table."""
    data = _get_session_or_404(session_key)
    if not isinstance(data, SessionData):
        return data  # error response, see _get_session_or_404

    session_origin = session_time_origin(data.location)
    if session_origin is None:
        return jsonify(error="no_standings_data", message="No location data for this session"), 404

    return jsonify(
        build_standings(data.position, data.intervals, data.laps, data.drivers, session_origin)
    )


def _get_session_or_404(session_key: int):
    """Shared cache-backed lookup for this blueprint's routes.

    Triggers a full session ingest (once, ever, per session — cached
    afterwards) if this session hasn't been requested before. Returns the
    ``SessionData`` on success, or a ready-to-return 404 response on
    failure.
    """
    client = current_app.extensions["openf1_client"]
    cache = current_app.extensions["session_cache"]

    try:
        return get_or_ingest_session(client, cache, session_key)
    except SessionIngestionError as exc:
        return jsonify(error="not_found", message=str(exc)), 404
