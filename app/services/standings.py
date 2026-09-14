"""Derive per-driver position/gap/interval timeseries for the live
standings HUD (issue #17), synced to the same session-wide time origin
used by the 3D replay (``track.session_time_origin`` / ``build_car_positions``).

Position and intervals update at different, sparse, unaligned moments (a
driver's position only gets a new record when it actually changes; gaps
update roughly every few seconds) — rather than trying to merge them into
one aligned series, each field stays its own per-driver timeseries and
the frontend looks up "the latest known value at or before the current
replay time" for each independently, same as a real timing screen holds
the last known value between updates.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def build_standings(
    position: list[dict[str, Any]],
    intervals: list[dict[str, Any]],
    drivers: list[dict[str, Any]],
    session_origin: datetime,
) -> dict[str, Any]:
    """Build one {position, gap_to_leader, interval} timeseries per driver.

    Returns ``{"drivers": [{"driver_number", "name_acronym", "team_colour",
    "position": [{"t", "value"}, ...], "gap_to_leader": [...],
    "interval": [...]}, ...]}``.
    """
    driver_info = {d["driver_number"]: d for d in drivers if d.get("driver_number") is not None}

    position_by_driver = _series_by_driver(position, "position", session_origin)
    gap_by_driver = _series_by_driver(intervals, "gap_to_leader", session_origin)
    interval_by_driver = _series_by_driver(intervals, "interval", session_origin)

    driver_numbers = set(position_by_driver) | set(gap_by_driver) | set(interval_by_driver)

    result = []
    for driver_number in sorted(driver_numbers):
        info = driver_info.get(driver_number, {})
        result.append(
            {
                "driver_number": driver_number,
                "name_acronym": info.get("name_acronym") or str(driver_number),
                "team_colour": info.get("team_colour") or "888888",
                "position": position_by_driver.get(driver_number, []),
                "gap_to_leader": gap_by_driver.get(driver_number, []),
                "interval": interval_by_driver.get(driver_number, []),
            }
        )
    return {"drivers": result}


def _series_by_driver(
    records: list[dict[str, Any]], field: str, origin: datetime
) -> dict[int, list[dict[str, Any]]]:
    """One sorted [{"t", "value"}, ...] series per driver for ``field``."""
    by_driver: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        driver_number = record.get("driver_number")
        value = record.get(field)
        date = record.get("date")
        if driver_number is None or value is None or not date:
            continue
        t = round((datetime.fromisoformat(date) - origin).total_seconds(), 2)
        by_driver.setdefault(driver_number, []).append({"t": t, "value": value})

    for series in by_driver.values():
        series.sort(key=lambda point: point["t"])

    return by_driver
