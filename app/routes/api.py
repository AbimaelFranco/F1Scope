"""Internal JSON API consumed by the frontend (mounted under /api).

Two kinds of data flow through here, deliberately handled differently:

- Session/meeting/driver *browsing* (this module's /sessions, /meetings,
  /drivers) is a live, rate-limited pass-through to OpenF1. It's what lets
  the user pick what to watch: it happens once per browse action (not once
  per replay frame) and the payloads are small, so there's nothing to gain
  from caching it.
- Everything needed to actually *replay* a session (location, car_data,
  laps, ...) is heavy and read repeatedly — that's served exclusively from
  the local session cache (milestone E2), never proxied live. Those
  endpoints land once the session-selection flow is wired to the
  ingestion/cache layer, later in this milestone (E3).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from app.services.openf1_client import OpenF1Client, OpenF1ClientError

api_bp = Blueprint("api", __name__)


@api_bp.get("/health")
def health():
    """Basic liveness check for the internal API."""
    return jsonify(status="ok")


@api_bp.get("/sessions")
def list_sessions():
    """List sessions, filtered by whatever query params the caller sends
    (e.g. ``?year=2024&meeting_key=1219``)."""
    return _proxy(lambda client: client.get_sessions(**request.args.to_dict()))


@api_bp.get("/meetings")
def list_meetings():
    """List meetings (Grand Prix weekends), filtered by e.g. ``?year=2024``."""
    return _proxy(lambda client: client.get_meetings(**request.args.to_dict()))


@api_bp.get("/drivers")
def list_drivers():
    """List drivers for a session, e.g. ``?session_key=9159``."""
    return _proxy(lambda client: client.get_drivers(**request.args.to_dict()))


def _proxy(call: Callable[[OpenF1Client], list[dict[str, Any]]]):
    """Run an OpenF1 client call, turning ``OpenF1ClientError`` into a 502."""
    client = current_app.extensions["openf1_client"]
    try:
        data = call(client)
    except OpenF1ClientError as exc:
        current_app.logger.warning("OpenF1 upstream request failed: %s", exc)
        return jsonify(error="upstream_error", message=str(exc)), 502
    return jsonify(data)
