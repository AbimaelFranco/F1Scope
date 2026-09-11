"""Session ingestion: pull everything F1Scope needs for one session from
OpenF1 in a single pass.

Persisting the result to a local cache (SQLite/files) is a separate
concern — see the caching layer landing in issue #7. This module only
orchestrates the OpenF1 calls (through the rate-limited client from issue
#5) and normalizes the result into one in-memory bundle.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.services.openf1_client import OpenF1Client

logger = logging.getLogger(__name__)


class SessionIngestionError(Exception):
    """Raised when a session can't be ingested (e.g. unknown session_key)."""


@dataclass
class SessionData:
    """Everything ingested for a single OpenF1 session.

    ``session``/``meeting`` are single records; everything else is the raw
    list of records OpenF1 returned for that endpoint, filtered to this
    session_key.
    """

    session_key: int
    session: dict[str, Any]
    meeting: dict[str, Any] | None = None
    drivers: list[dict[str, Any]] = field(default_factory=list)
    location: list[dict[str, Any]] = field(default_factory=list)
    car_data: list[dict[str, Any]] = field(default_factory=list)
    laps: list[dict[str, Any]] = field(default_factory=list)
    position: list[dict[str, Any]] = field(default_factory=list)
    intervals: list[dict[str, Any]] = field(default_factory=list)
    pit: list[dict[str, Any]] = field(default_factory=list)
    stints: list[dict[str, Any]] = field(default_factory=list)
    race_control: list[dict[str, Any]] = field(default_factory=list)
    weather: list[dict[str, Any]] = field(default_factory=list)


def ingest_session(client: OpenF1Client, session_key: int) -> SessionData:
    """Fetch every endpoint F1Scope needs for ``session_key`` in one pass.

    Looks up the session first and fails fast with ``SessionIngestionError``
    if it doesn't exist, instead of firing nine more requests for nothing.
    """
    sessions = client.get_sessions(session_key=session_key)
    if not sessions:
        raise SessionIngestionError(f"No session found for session_key={session_key!r}")
    session = sessions[0]

    meetings = client.get_meetings(meeting_key=session.get("meeting_key"))
    meeting = meetings[0] if meetings else None

    logger.info(
        "Ingesting session_key=%s (%s, %s)",
        session_key,
        session.get("session_name"),
        session.get("session_type"),
    )

    drivers = client.get_drivers(session_key=session_key)
    driver_numbers = [d["driver_number"] for d in drivers if d.get("driver_number") is not None]

    data = SessionData(
        session_key=session_key,
        session=session,
        meeting=meeting,
        drivers=drivers,
        location=_fetch_per_driver(client.get_location, session_key, driver_numbers),
        car_data=_fetch_per_driver(client.get_car_data, session_key, driver_numbers),
        laps=client.get_laps(session_key=session_key),
        position=client.get_position(session_key=session_key),
        intervals=client.get_intervals(session_key=session_key),
        pit=client.get_pit(session_key=session_key),
        stints=client.get_stints(session_key=session_key),
        race_control=client.get_race_control(session_key=session_key),
        weather=client.get_weather(session_key=session_key),
    )

    logger.info(
        "Ingested session_key=%s: drivers=%d location=%d car_data=%d laps=%d "
        "position=%d intervals=%d pit=%d stints=%d race_control=%d weather=%d",
        session_key,
        len(data.drivers),
        len(data.location),
        len(data.car_data),
        len(data.laps),
        len(data.position),
        len(data.intervals),
        len(data.pit),
        len(data.stints),
        len(data.race_control),
        len(data.weather),
    )

    return data


def _fetch_per_driver(
    method: Callable[..., list[dict[str, Any]]],
    session_key: int,
    driver_numbers: list[int],
) -> list[dict[str, Any]]:
    """Call an OpenF1 endpoint once per driver and concatenate the results.

    OpenF1 rejects ``location``/``car_data`` queries scoped to just
    ``session_key`` with a 422 ("You're likely asking for too much data at
    once") — those two endpoints require a ``driver_number`` filter.
    """
    records: list[dict[str, Any]] = []
    for driver_number in driver_numbers:
        records.extend(method(session_key=session_key, driver_number=driver_number))
    return records
