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
    by_driver = _group_by_driver(location)
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


def _group_by_driver(location: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """Group location samples by driver, dropping (0, 0, 0) no-fix noise."""
    by_driver: dict[int, list[dict[str, Any]]] = {}
    for sample in location:
        if sample.get("x") == 0 and sample.get("y") == 0 and sample.get("z") == 0:
            continue
        by_driver.setdefault(sample["driver_number"], []).append(sample)
    return by_driver


def build_car_positions(
    location: list[dict[str, Any]],
    drivers: list[dict[str, Any]],
    sample_interval: float = 1.0,
) -> dict[str, Any]:
    """Downsample every driver's location trace for animating cars over time.

    Unlike :func:`build_track` (one driver, one lap, for the static circuit
    outline), this covers the whole session for every driver — needed to
    animate the full grid moving, not just trace the track shape once.
    Downsampled to roughly one point per ``sample_interval`` seconds
    (OpenF1 samples at ~3.7 Hz) since smooth-enough animation doesn't need
    every raw sample, and a full session's worth for ~20 drivers otherwise
    means hundreds of thousands of points shipped to the browser.

    Returns ``{"drivers": [{"driver_number", "name_acronym", "team_colour",
    "points": [{"t", "x", "y", "z"}, ...]}, ...]}``, where ``t`` is seconds
    elapsed since the earliest sample across the whole session — the same
    time origin for every driver, so they animate in sync.
    """
    by_driver = _group_by_driver(location)
    if not by_driver:
        return {"drivers": []}

    session_start = min(
        datetime.fromisoformat(sample["date"])
        for samples in by_driver.values()
        for sample in samples
    )
    driver_info = {d["driver_number"]: d for d in drivers if d.get("driver_number") is not None}

    result: list[dict[str, Any]] = []
    for driver_number, samples in sorted(by_driver.items()):
        samples.sort(key=lambda s: s["date"])
        points = _downsample(samples, session_start, sample_interval)
        if not points:
            continue

        info = driver_info.get(driver_number, {})
        result.append(
            {
                "driver_number": driver_number,
                "name_acronym": info.get("name_acronym") or str(driver_number),
                "team_colour": info.get("team_colour") or "888888",
                "points": points,
            }
        )

    return {"drivers": result}


def _downsample(
    samples: list[dict[str, Any]], origin: datetime, interval: float
) -> list[dict[str, Any]]:
    """Keep at most one sample per ``interval``-second bucket, in order."""
    points: list[dict[str, Any]] = []
    last_bucket: int | None = None
    for sample in samples:
        elapsed = (datetime.fromisoformat(sample["date"]) - origin).total_seconds()
        bucket = int(elapsed // interval)
        if bucket == last_bucket:
            continue
        last_bucket = bucket
        points.append(
            {"t": round(elapsed, 2), "x": sample["x"], "y": sample["y"], "z": sample.get("z", 0)}
        )
    return points
