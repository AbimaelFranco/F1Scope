"""Unit tests for ingest_session() (#25) — request orchestration, not HTTP
mechanics (that's test_openf1_client.py/test_rate_limit.py). Uses
FakeIngestClient (conftest.py) so these assert *what got called and how
often*, without any real network access.
"""

from __future__ import annotations

import pytest

from app.services.ingestion import SessionIngestionError, ingest_session
from tests.conftest import FakeIngestClient


def test_raises_when_session_not_found():
    client = FakeIngestClient(sessions=[])

    with pytest.raises(SessionIngestionError):
        ingest_session(client, session_key=999999)


def test_fails_fast_without_fetching_the_other_endpoints():
    """An unknown session_key shouldn't fire nine more requests for data
    that can't exist — see ingest_session's docstring."""
    client = FakeIngestClient(sessions=[])

    with pytest.raises(SessionIngestionError):
        ingest_session(client, session_key=999999)

    called_endpoints = {name for name, _ in client.calls}
    assert called_endpoints == {"get_sessions"}


def test_looks_up_the_meeting_for_the_session():
    client = FakeIngestClient(
        sessions=[{"session_key": 7953, "meeting_key": 1140, "session_name": "Race"}],
        meetings=[{"meeting_key": 1140, "meeting_name": "Bahrain Grand Prix"}],
    )

    data = ingest_session(client, session_key=7953)

    assert data.meeting == {"meeting_key": 1140, "meeting_name": "Bahrain Grand Prix"}
    meeting_calls = [kwargs for name, kwargs in client.calls if name == "get_meetings"]
    assert meeting_calls == [{"meeting_key": 1140}]


def test_meeting_is_none_when_the_lookup_finds_nothing():
    client = FakeIngestClient(
        sessions=[{"session_key": 7953, "meeting_key": 1140, "session_name": "Race"}],
        meetings=[],
    )

    data = ingest_session(client, session_key=7953)

    assert data.meeting is None


def test_location_and_car_data_are_fetched_once_per_driver():
    """OpenF1 rejects location/car_data scoped to just session_key with a
    422 ("too much data at once") — they need a driver_number filter, so
    ingest_session must call them once per driver rather than once per
    session. See _fetch_per_driver's docstring."""
    client = FakeIngestClient(
        sessions=[{"session_key": 7953, "meeting_key": 1140, "session_name": "Race"}],
        drivers=[
            {"driver_number": 1, "name_acronym": "VER"},
            {"driver_number": 16, "name_acronym": "LEC"},
            {"driver_number": 55, "name_acronym": "SAI"},
        ],
    )

    ingest_session(client, session_key=7953)

    location_calls = [kwargs for name, kwargs in client.calls if name == "get_location"]
    car_data_calls = [kwargs for name, kwargs in client.calls if name == "get_car_data"]
    assert location_calls == [
        {"session_key": 7953, "driver_number": 1},
        {"session_key": 7953, "driver_number": 16},
        {"session_key": 7953, "driver_number": 55},
    ]
    assert car_data_calls == [
        {"session_key": 7953, "driver_number": 1},
        {"session_key": 7953, "driver_number": 16},
        {"session_key": 7953, "driver_number": 55},
    ]


def test_drivers_without_a_driver_number_are_skipped_for_per_driver_fetches():
    client = FakeIngestClient(
        sessions=[{"session_key": 7953, "meeting_key": 1140, "session_name": "Race"}],
        drivers=[
            {"driver_number": 1, "name_acronym": "VER"},
            {"name_acronym": "MISSING_NUMBER"},  # malformed/incomplete record
        ],
    )

    ingest_session(client, session_key=7953)

    location_calls = [kwargs for name, kwargs in client.calls if name == "get_location"]
    assert location_calls == [{"session_key": 7953, "driver_number": 1}]


def test_session_scoped_endpoints_are_fetched_once_for_the_whole_session():
    """Unlike location/car_data, laps/position/intervals/pit/stints/
    race_control/weather all accept a plain session_key filter."""
    client = FakeIngestClient(
        sessions=[{"session_key": 7953, "meeting_key": 1140, "session_name": "Race"}],
        drivers=[{"driver_number": 1}, {"driver_number": 16}],
        laps=[{"driver_number": 1, "lap_number": 1}],
    )

    data = ingest_session(client, session_key=7953)

    for endpoint in (
        "get_laps",
        "get_position",
        "get_intervals",
        "get_pit",
        "get_stints",
        "get_race_control",
        "get_weather",
    ):
        calls = [kwargs for name, kwargs in client.calls if name == endpoint]
        assert calls == [{"session_key": 7953}], f"{endpoint} should be called once per session"
    assert data.laps == [{"driver_number": 1, "lap_number": 1}]


def test_returns_a_fully_populated_session_data():
    client = FakeIngestClient(
        sessions=[{"session_key": 7953, "meeting_key": 1140, "session_name": "Race"}],
        meetings=[{"meeting_key": 1140, "meeting_name": "Bahrain Grand Prix"}],
        drivers=[{"driver_number": 1, "name_acronym": "VER"}],
        location=[
            {"driver_number": 1, "x": 100, "y": 200, "z": -50, "date": "2023-01-01T00:00:00"}
        ],
        weather=[{"air_temperature": 28.5}],
    )

    data = ingest_session(client, session_key=7953)

    assert data.session_key == 7953
    assert data.session == {"session_key": 7953, "meeting_key": 1140, "session_name": "Race"}
    assert data.drivers == [{"driver_number": 1, "name_acronym": "VER"}]
    assert data.location == [
        {"driver_number": 1, "x": 100, "y": 200, "z": -50, "date": "2023-01-01T00:00:00"}
    ]
    assert data.weather == [{"air_temperature": 28.5}]
