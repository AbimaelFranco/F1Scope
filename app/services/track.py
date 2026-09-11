"""Derive a simplified 3D track shape from OpenF1 location samples.

The circuit itself doesn't move during a session, so one driver's path is
enough to trace its outline — there's no need to look at all ~20 cars'
worth of location data just to draw the track. See
docs/architecture/f1scope-architecture.html for where this fits: it reads
from the already-ingested/cached SessionData (milestone E2), never OpenF1
directly.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def build_track(
    location: list[dict[str, Any]], laps: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Build a track shape from one clean lap of one driver's location trace.

    - Picks the driver with the most usable (non-zero) location samples —
      OpenF1 reports (0, 0, 0) while a car sits in the garage with no
      position fix yet, which isn't real track geometry.
    - Slices to that driver's first non-out-lap (via ``laps``), so the
      track is traced once instead of every lap of the session stacked on
      top of each other. Falls back to the driver's full trace if lap
      data isn't usable for windowing.

    Returns ``{"driver_number": int, "points": [{"x", "y", "z"}, ...]}``,
    or ``None`` if there's no usable location data at all.
    """
    by_driver: dict[int, list[dict[str, Any]]] = {}
    for sample in location:
        if sample.get("x") == 0 and sample.get("y") == 0 and sample.get("z") == 0:
            continue
        by_driver.setdefault(sample["driver_number"], []).append(sample)

    if not by_driver:
        return None

    driver_number, samples = max(by_driver.items(), key=lambda item: len(item[1]))
    samples.sort(key=lambda s: s["date"])

    window = _pick_clean_lap_window(laps, driver_number)
    if window is not None:
        start, end = window
        windowed = [s for s in samples if start <= datetime.fromisoformat(s["date"]) <= end]
        if windowed:
            samples = windowed

    points = [{"x": s["x"], "y": s["y"], "z": s.get("z", 0)} for s in samples]
    return {"driver_number": driver_number, "points": points}


def _pick_clean_lap_window(
    laps: list[dict[str, Any]], driver_number: int
) -> tuple[datetime, datetime] | None:
    """First lap for ``driver_number`` that isn't a pit-out lap, as a (start, end) window."""
    candidates = sorted(
        (
            lap
            for lap in laps
            if lap.get("driver_number") == driver_number
            and lap.get("date_start")
            and lap.get("lap_duration")
            and not lap.get("is_pit_out_lap")
        ),
        key=lambda lap: lap["lap_number"],
    )
    if not candidates:
        return None

    lap = candidates[0]
    start = datetime.fromisoformat(lap["date_start"])
    end = start + timedelta(seconds=lap["lap_duration"])
    return start, end
