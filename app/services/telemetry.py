"""Derive one driver's telemetry (speed, throttle, brake, RPM, gear) for
one lap from OpenF1's ``car_data``.

v1 scope (docs/PLANNING.md): compare two drivers over a single lap — this
module produces one driver's series at a time; the caller (route) is
called once per driver being compared.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class TelemetryError(Exception):
    """Raised when the requested driver has no usable telemetry at all."""


def build_telemetry(
    car_data: list[dict[str, Any]],
    laps: list[dict[str, Any]],
    driver_number: int,
    lap_number: int | None = None,
) -> dict[str, Any]:
    """Build one driver's telemetry series, windowed to a single lap.

    If ``lap_number`` is given, windows to exactly that lap (raises
    ``TelemetryError`` if that lap isn't on record with usable timing).
    Otherwise picks the driver's first non-out-lap, same heuristic as
    ``app.services.track.build_track``. Falls back to the driver's full
    trace if no lap window can be resolved.

    Returns ``{"driver_number", "lap_number", "points": [{"t", "speed",
    "throttle", "brake", "rpm", "n_gear"}, ...]}``, with ``t`` seconds
    elapsed since the window (or trace) start.
    """
    samples = [s for s in car_data if s.get("driver_number") == driver_number]
    if not samples:
        raise TelemetryError(f"No car_data for driver_number={driver_number!r}")
    samples.sort(key=lambda s: s["date"])

    lap = _pick_lap(laps, driver_number, lap_number)
    if lap_number is not None and lap is None:
        raise TelemetryError(f"No lap {lap_number!r} on record for driver_number={driver_number!r}")

    origin = datetime.fromisoformat(samples[0]["date"])
    if lap is not None:
        start = datetime.fromisoformat(lap["date_start"])
        end = start + timedelta(seconds=lap["lap_duration"])
        windowed = [s for s in samples if start <= datetime.fromisoformat(s["date"]) <= end]
        if windowed:
            samples = windowed
            origin = start

    points = [
        {
            "t": round((datetime.fromisoformat(s["date"]) - origin).total_seconds(), 3),
            "speed": s.get("speed"),
            "throttle": s.get("throttle"),
            "brake": s.get("brake"),
            "rpm": s.get("rpm"),
            "n_gear": s.get("n_gear"),
        }
        for s in samples
    ]

    return {
        "driver_number": driver_number,
        "lap_number": lap["lap_number"] if lap else None,
        "points": points,
    }


def _pick_lap(
    laps: list[dict[str, Any]], driver_number: int, lap_number: int | None
) -> dict[str, Any] | None:
    driver_laps = [
        lap
        for lap in laps
        if lap.get("driver_number") == driver_number
        and lap.get("date_start")
        and lap.get("lap_duration")
    ]

    if lap_number is not None:
        return next((lap for lap in driver_laps if lap.get("lap_number") == lap_number), None)

    candidates = sorted(
        (lap for lap in driver_laps if not lap.get("is_pit_out_lap")),
        key=lambda lap: lap["lap_number"],
    )
    return candidates[0] if candidates else None
