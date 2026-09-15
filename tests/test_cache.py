"""Unit tests for SessionCache and get_or_ingest_session (#25).

Uses pytest's tmp_path fixture for a real, isolated filesystem — never
touches the project's own instance/cache directory.
"""

from __future__ import annotations

import pytest

from app.services.cache import SessionCache, get_or_ingest_session
from app.services.ingestion import SessionData
from tests.conftest import FakeIngestClient


def make_session_data(session_key: int = 7953) -> SessionData:
    return SessionData(
        session_key=session_key,
        session={"session_key": session_key, "session_name": "Race"},
        meeting={"meeting_key": 1140, "meeting_name": "Bahrain Grand Prix"},
        drivers=[{"driver_number": 1, "name_acronym": "VER"}],
        location=[{"driver_number": 1, "x": 100, "y": 200, "z": -50}],
        car_data=[{"driver_number": 1, "speed": 300}],
        laps=[{"driver_number": 1, "lap_number": 1, "lap_duration": 91.234}],
        position=[{"driver_number": 1, "position": 1}],
        intervals=[{"driver_number": 1, "gap_to_leader": 0.0}],
        pit=[],
        stints=[{"driver_number": 1, "compound": "SOFT"}],
        race_control=[],
        weather=[{"air_temperature": 28.5}],
    )


# -- SessionCache -----------------------------------------------------------


def test_has_is_false_before_anything_is_cached(tmp_path):
    cache = SessionCache(tmp_path)

    assert cache.has(7953) is False


def test_has_is_true_after_save(tmp_path):
    cache = SessionCache(tmp_path)
    cache.save(make_session_data())

    assert cache.has(7953) is True


def test_load_raises_when_nothing_cached(tmp_path):
    cache = SessionCache(tmp_path)

    with pytest.raises(FileNotFoundError):
        cache.load(7953)


def test_save_then_load_round_trips_every_field(tmp_path):
    cache = SessionCache(tmp_path)
    original = make_session_data()

    cache.save(original)
    loaded = cache.load(7953)

    assert loaded == original


def test_save_creates_one_json_file_per_field_plus_a_manifest(tmp_path):
    cache = SessionCache(tmp_path)
    cache.save(make_session_data())

    session_dir = tmp_path / "7953"
    filenames = {p.name for p in session_dir.iterdir()}
    assert "_manifest.json" in filenames
    assert "location.json" in filenames
    assert "car_data.json" in filenames
    assert "weather.json" in filenames
    # session_key itself isn't a separate file — it's the directory name
    # and gets threaded back in on load() instead.
    assert "session_key.json" not in filenames


def test_different_sessions_are_cached_independently(tmp_path):
    cache = SessionCache(tmp_path)
    cache.save(make_session_data(session_key=7953))
    cache.save(make_session_data(session_key=9222))

    assert cache.has(7953) is True
    assert cache.has(9222) is True
    assert cache.load(7953).session_key == 7953
    assert cache.load(9222).session_key == 9222


def test_non_ascii_data_round_trips(tmp_path):
    """Driver/meeting names routinely contain accented characters (e.g.
    "Pérez", "São Paulo") — a naive ensure_ascii write would still work,
    but let's actually confirm the round trip preserves them exactly."""
    cache = SessionCache(tmp_path)
    data = make_session_data()
    data.drivers = [{"full_name": "Sérgio Pérez", "team_name": "São Paulo Racing"}]

    cache.save(data)
    loaded = cache.load(7953)

    assert loaded.drivers[0]["full_name"] == "Sérgio Pérez"
    assert loaded.drivers[0]["team_name"] == "São Paulo Racing"


# -- get_or_ingest_session ----------------------------------------------


def test_cache_hit_never_touches_the_client(tmp_path):
    cache = SessionCache(tmp_path)
    cache.save(make_session_data())

    class ExplodingClient:
        def __getattr__(self, name):
            raise AssertionError(f"client.{name} should not be called on a cache hit")

    result = get_or_ingest_session(ExplodingClient(), cache, session_key=7953)

    assert result.session_key == 7953


def test_cache_miss_ingests_and_saves(tmp_path):
    cache = SessionCache(tmp_path)
    client = FakeIngestClient(
        sessions=[{"session_key": 7953, "meeting_key": 1140, "session_name": "Race"}],
        drivers=[{"driver_number": 1}],
    )
    assert cache.has(7953) is False

    result = get_or_ingest_session(client, cache, session_key=7953)

    assert result.session_key == 7953
    assert cache.has(7953) is True  # persisted for next time
    assert any(name == "get_sessions" for name, _ in client.calls)


def test_second_call_after_a_miss_is_a_hit(tmp_path):
    """The whole point of the cache: ingest_session should run at most
    once per session_key, ever."""
    cache = SessionCache(tmp_path)
    client = FakeIngestClient(
        sessions=[{"session_key": 7953, "meeting_key": 1140, "session_name": "Race"}],
        drivers=[{"driver_number": 1}],
    )

    get_or_ingest_session(client, cache, session_key=7953)
    calls_after_first = len(client.calls)
    get_or_ingest_session(client, cache, session_key=7953)

    assert len(client.calls) == calls_after_first  # no new client calls on the second call
