"""Thin HTTP client for the OpenF1 API (https://api.openf1.org).

Only responsible for building requests, calling the API, and turning
transport/HTTP failures into a single ``OpenF1ClientError``. Rate limiting
and retry/backoff are layered on top separately (milestone E2, issue #5)
rather than baked in here, so this stays a small, easily testable building
block that the ingestion layer (issue #6) composes with.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openf1.org/v1"
DEFAULT_TIMEOUT = 10  # seconds


class OpenF1ClientError(Exception):
    """Raised when a request to the OpenF1 API fails or returns unusable data."""


class OpenF1Client:
    """Minimal client for OpenF1's read-only, free-tier REST API.

    Every method returns the endpoint's raw list of JSON records — no
    caching, retries, or rate limiting happen here (see the ingestion
    layer for that).
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        session: requests.Session | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout

    # -- Generic request ---------------------------------------------------

    def _get(self, endpoint: str, **params: Any) -> list[dict[str, Any]]:
        """GET ``{base_url}/{endpoint}`` with the given filters as query params."""
        url = f"{self.base_url}/{endpoint}"
        query = {key: value for key, value in params.items() if value is not None}

        logger.debug("OpenF1 request: GET %s params=%s", url, query)

        try:
            response = self.session.get(url, params=query, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OpenF1ClientError(f"OpenF1 request to {endpoint!r} failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise OpenF1ClientError(f"OpenF1 response for {endpoint!r} was not valid JSON") from exc

        if not isinstance(data, list):
            raise OpenF1ClientError(
                f"OpenF1 response for {endpoint!r} was not a list: {type(data)!r}"
            )

        return data

    # -- Typed endpoint wrappers --------------------------------------------
    # One thin wrapper per OpenF1 endpoint used by F1Scope (docs/PLANNING.md).

    def get_sessions(self, **filters: Any) -> list[dict[str, Any]]:
        """List sessions (filter by e.g. year, country_name, session_type)."""
        return self._get("sessions", **filters)

    def get_meetings(self, **filters: Any) -> list[dict[str, Any]]:
        """List meetings (Grand Prix weekends)."""
        return self._get("meetings", **filters)

    def get_drivers(self, **filters: Any) -> list[dict[str, Any]]:
        """List drivers taking part in a session."""
        return self._get("drivers", **filters)

    def get_location(self, **filters: Any) -> list[dict[str, Any]]:
        """Car x/y/z positions — used to reconstruct the 3D replay track."""
        return self._get("location", **filters)

    def get_car_data(self, **filters: Any) -> list[dict[str, Any]]:
        """Telemetry samples: speed, throttle, brake, RPM, gear (~3.7 Hz)."""
        return self._get("car_data", **filters)

    def get_laps(self, **filters: Any) -> list[dict[str, Any]]:
        """Lap and sector times."""
        return self._get("laps", **filters)

    def get_position(self, **filters: Any) -> list[dict[str, Any]]:
        """Race position over time."""
        return self._get("position", **filters)

    def get_intervals(self, **filters: Any) -> list[dict[str, Any]]:
        """Gaps/intervals between drivers."""
        return self._get("intervals", **filters)

    def get_pit(self, **filters: Any) -> list[dict[str, Any]]:
        """Pit stop timing."""
        return self._get("pit", **filters)

    def get_stints(self, **filters: Any) -> list[dict[str, Any]]:
        """Tyre stints (compound, lap range)."""
        return self._get("stints", **filters)

    def get_race_control(self, **filters: Any) -> list[dict[str, Any]]:
        """Race control messages: flags, safety car, incidents."""
        return self._get("race_control", **filters)

    def get_weather(self, **filters: Any) -> list[dict[str, Any]]:
        """Weather samples for a session."""
        return self._get("weather", **filters)
