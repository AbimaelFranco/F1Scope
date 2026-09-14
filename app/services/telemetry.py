"""Derive one driver's telemetry (speed, throttle, brake, RPM, gear) from
OpenF1's ``car_data``.

Revised for issue #47 (live-validation feedback): v1 originally windowed
this to a single lap (see git history). The default is now the **whole
session**, downsampled like ``track.build_car_positions`` — a full race
per driver is tens of thousands of raw samples, more than a line chart
needs. ``lap_number`` still works as an optional filter to zoom into one
lap at full resolution (no downsampling — a single lap is already small).

Either way, ``t`` is relative to ``session_origin`` — the same reference
``track.session_time_origin`` gives ``build_car_positions`` — so chart
points land in the same time domain as the 3D replay's
``playback.simTime``. This is what let issue #16's synced cursor drop
its per-driver ``lap_start_offset`` conversion: one shared vertical line
at ``simTime`` now works for every chart, full-race or single-lap alike.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

DEFAULT_SAMPLE_INTERVAL = 0.5  # seconds; car_data samples at ~3.7 Hz


class TelemetryError(Exception):
    """Raised when the requested driver/lap has no usable telemetry."""


def build_telemetry(
    car_data: list[dict[str, Any]],
    laps: list[dict[str, Any]],
    driver_number: int,
    lap_number: int | None = None,
    session_origin: datetime | None = None,
    sample_interval: float = DEFAULT_SAMPLE_INTERVAL,
) -> dict[str, Any]:
    """Build one driver's telemetry series.

    With no ``lap_number``, covers the whole session downsampled to
    roughly one point per ``sample_interval`` seconds. With ``lap_number``,
    windows to exactly that lap at full resolution (raises
    ``TelemetryError`` if that lap isn't on record with usable timing).

    Returns ``{"driver_number", "lap_number", "points": [{"t", "speed",
    "throttle", "brake", "rpm", "n_gear"}, ...]}``. ``lap_number`` in the
    response is ``None`` unless a specific lap was requested.
    """
    samples = [s for s in car_data if s.get("driver_number") == driver_number]
    if not samples:
        raise TelemetryError(f"No car_data for driver_number={driver_number!r}")
    samples.sort(key=lambda s: s["date"])

    resolved_lap_number = None
    if lap_number is not None:
        lap = _find_lap(laps, driver_number, lap_number)
        if lap is None:
            raise TelemetryError(
                f"No lap {lap_number!r} on record for driver_number={driver_number!r}"
            )
        start = datetime.fromisoformat(lap["date_start"])
        end = start + timedelta(seconds=lap["lap_duration"])
        windowed = [s for s in samples if start <= datetime.fromisoformat(s["date"]) <= end]
        if windowed:
            samples = windowed
        resolved_lap_number = lap["lap_number"]

    origin = (
        session_origin if session_origin is not None else datetime.fromisoformat(samples[0]["date"])
    )

    if lap_number is not None:
        points = [_telemetry_point(s, origin) for s in samples]
    else:
        points = _downsample_telemetry(samples, origin, sample_interval)

    return {
        "driver_number": driver_number,
        "lap_number": resolved_lap_number,
        "points": points,
    }


def _telemetry_point(sample: dict[str, Any], origin: datetime) -> dict[str, Any]:
    return {
        "t": round((datetime.fromisoformat(sample["date"]) - origin).total_seconds(), 3),
        "speed": sample.get("speed"),
        "throttle": sample.get("throttle"),
        "brake": sample.get("brake"),
        "rpm": sample.get("rpm"),
        "n_gear": sample.get("n_gear"),
    }


def _downsample_telemetry(
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
        points.append(_telemetry_point(sample, origin))
    return points


def _find_lap(
    laps: list[dict[str, Any]], driver_number: int, lap_number: int
) -> dict[str, Any] | None:
    return next(
        (
            lap
            for lap in laps
            if lap.get("driver_number") == driver_number
            and lap.get("lap_number") == lap_number
            and lap.get("date_start")
            and lap.get("lap_duration")
        ),
        None,
    )
