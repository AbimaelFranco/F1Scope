"""Integration tests for the internal JSON API (#26): the Flask routes in
app/routes/api.py (live OpenF1 pass-through for session/meeting/driver
browsing) and app/routes/replay.py (cache-backed replay/telemetry/
standings data).

Uses Flask's real test client and real route/service code end-to-end —
only the two things that would otherwise touch the outside world are
swapped for test doubles: app.extensions["openf1_client"] (no real HTTP)
and app.extensions["session_cache"] (a SessionCache pointed at tmp_path
instead of the real instance/cache).
"""

from __future__ import annotations

import pytest

from app import create_app
from app.services.cache import SessionCache
from app.services.ingestion import SessionData
from tests.conftest import FakeIngestClient


def make_full_session_data(session_key: int = 7953) -> SessionData:
    """A small but realistically-shaped two-driver session: enough real
    structure (ISO dates, x/y/z, driver_number-keyed records) for
    build_track/build_car_positions/build_telemetry/build_standings to
    all produce real, non-empty output — not just empty-list happy paths.
    """
    return SessionData(
        session_key=session_key,
        session={"session_key": session_key, "session_name": "Race", "meeting_key": 1140},
        meeting={"meeting_key": 1140, "meeting_name": "Bahrain Grand Prix"},
        drivers=[
            {"driver_number": 1, "name_acronym": "VER", "team_colour": "3671C6"},
            {"driver_number": 16, "name_acronym": "LEC", "team_colour": "E8002D"},
        ],
        location=[
            {"driver_number": 1, "x": 100, "y": 200, "z": -50, "date": "2023-03-05T15:00:00"},
            {"driver_number": 1, "x": 110, "y": 210, "z": -50, "date": "2023-03-05T15:00:01"},
            {"driver_number": 1, "x": 120, "y": 220, "z": -49, "date": "2023-03-05T15:00:02"},
            {"driver_number": 16, "x": 90, "y": 190, "z": -50, "date": "2023-03-05T15:00:00"},
            {"driver_number": 16, "x": 95, "y": 195, "z": -50, "date": "2023-03-05T15:00:01"},
        ],
        car_data=[
            {
                "driver_number": 1,
                "date": "2023-03-05T15:00:00",
                "speed": 250,
                "throttle": 80,
                "brake": 0,
                "rpm": 10500,
                "n_gear": 6,
            },
            {
                "driver_number": 1,
                "date": "2023-03-05T15:00:01",
                "speed": 260,
                "throttle": 100,
                "brake": 0,
                "rpm": 11000,
                "n_gear": 7,
            },
        ],
        laps=[
            {
                "driver_number": 1,
                "lap_number": 1,
                "date_start": "2023-03-05T15:00:00",
                "lap_duration": 91.234,
                "is_pit_out_lap": False,
            }
        ],
        position=[
            {"driver_number": 1, "position": 1, "date": "2023-03-05T15:00:00"},
            {"driver_number": 16, "position": 2, "date": "2023-03-05T15:00:00"},
        ],
        intervals=[
            {
                "driver_number": 16,
                "gap_to_leader": 1.234,
                "interval": 1.234,
                "date": "2023-03-05T15:00:00",
            },
        ],
        pit=[],
        stints=[{"driver_number": 1, "compound": "SOFT", "lap_start": 1}],
        race_control=[],
        weather=[{"air_temperature": 28.5, "date": "2023-03-05T15:00:00"}],
    )


@pytest.fixture
def app(tmp_path):
    application = create_app("testing")
    application.extensions["session_cache"] = SessionCache(tmp_path)
    application.extensions["openf1_client"] = FakeIngestClient()  # empty by default
    return application


@pytest.fixture
def client(app):
    return app.test_client()


# -- /api/health ------------------------------------------------------------


def test_health(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


# -- /api/sessions, /api/meetings, /api/drivers (live pass-through) --------


def test_list_sessions_proxies_to_the_client_with_query_params(app, client):
    fake_client = FakeIngestClient(sessions=[{"session_key": 7953, "session_name": "Race"}])
    app.extensions["openf1_client"] = fake_client

    response = client.get("/api/sessions?year=2023&country_name=Bahrain")

    assert response.status_code == 200
    assert response.get_json() == [{"session_key": 7953, "session_name": "Race"}]
    calls = [kwargs for name, kwargs in fake_client.calls if name == "get_sessions"]
    assert calls == [{"year": "2023", "country_name": "Bahrain"}]


def test_list_meetings(app, client):
    app.extensions["openf1_client"] = FakeIngestClient(
        meetings=[{"meeting_key": 1140, "meeting_name": "Bahrain Grand Prix"}]
    )

    response = client.get("/api/meetings?year=2023")

    assert response.status_code == 200
    assert response.get_json() == [{"meeting_key": 1140, "meeting_name": "Bahrain Grand Prix"}]


def test_list_drivers(app, client):
    app.extensions["openf1_client"] = FakeIngestClient(
        drivers=[{"driver_number": 1, "name_acronym": "VER"}]
    )

    response = client.get("/api/drivers?session_key=7953")

    assert response.status_code == 200
    assert response.get_json() == [{"driver_number": 1, "name_acronym": "VER"}]


def test_upstream_openf1_error_becomes_a_502(app, client):
    class FailingClient:
        def get_sessions(self, **kwargs):
            from app.services.openf1_client import OpenF1ClientError

            raise OpenF1ClientError("boom", status_code=500)

    app.extensions["openf1_client"] = FailingClient()

    response = client.get("/api/sessions?year=2023")

    assert response.status_code == 502
    body = response.get_json()
    assert body["error"] == "upstream_error"


# -- /api/session/<key>/track, /cars, /telemetry, /standings ---------------
# (cache-backed — these must never touch openf1_client for an already
# -cached session; see the ExplodingClient tests below.)


class ExplodingClient:
    """Fails loudly if the route layer ever falls through to a live OpenF1
    call for a session that's already cached — that would defeat the
    entire point of the cache."""

    def __getattr__(self, name):
        raise AssertionError(f"openf1_client.{name} should not be called for a cached session")


def test_track_serves_cached_data_without_touching_the_client(app, client):
    app.extensions["session_cache"].save(make_full_session_data())
    app.extensions["openf1_client"] = ExplodingClient()

    response = client.get("/api/session/7953/track")

    assert response.status_code == 200
    body = response.get_json()
    # Driver 1 has 3 location samples vs. driver 16's 2 — build_track
    # picks whichever driver has the most usable samples.
    assert body["driver_number"] == 1
    assert body["points"] == [
        {"x": 100, "y": 200, "z": -50},
        {"x": 110, "y": 210, "z": -50},
        {"x": 120, "y": 220, "z": -49},
    ]


def test_track_404s_for_an_unknown_session(app, client):
    app.extensions["openf1_client"] = FakeIngestClient(sessions=[])  # nothing found upstream either

    response = client.get("/api/session/999999/track")

    assert response.status_code == 404
    assert response.get_json()["error"] == "not_found"


def test_cars_serves_cached_positions_for_every_driver(app, client):
    app.extensions["session_cache"].save(make_full_session_data())
    app.extensions["openf1_client"] = ExplodingClient()

    response = client.get("/api/session/7953/cars")

    assert response.status_code == 200
    body = response.get_json()
    driver_numbers = {d["driver_number"] for d in body["drivers"]}
    assert driver_numbers == {1, 16}
    assert body["drivers"][0]["points"][0].keys() >= {"t", "x", "y", "z"}


def test_telemetry_requires_driver_number(app, client):
    app.extensions["session_cache"].save(make_full_session_data())
    app.extensions["openf1_client"] = ExplodingClient()

    response = client.get("/api/session/7953/telemetry")

    assert response.status_code == 400
    assert response.get_json()["error"] == "bad_request"


def test_telemetry_returns_points_for_a_known_driver(app, client):
    app.extensions["session_cache"].save(make_full_session_data())
    app.extensions["openf1_client"] = ExplodingClient()

    response = client.get("/api/session/7953/telemetry?driver_number=1")

    assert response.status_code == 200
    body = response.get_json()
    assert body["driver_number"] == 1
    assert len(body["points"]) > 0
    assert body["points"][0]["speed"] == 250


def test_telemetry_404s_for_a_driver_with_no_car_data(app, client):
    app.extensions["session_cache"].save(make_full_session_data())
    app.extensions["openf1_client"] = ExplodingClient()

    response = client.get("/api/session/7953/telemetry?driver_number=999")

    assert response.status_code == 404
    assert response.get_json()["error"] == "no_telemetry_data"


def test_standings_serves_position_gap_and_lap_data(app, client):
    app.extensions["session_cache"].save(make_full_session_data())
    app.extensions["openf1_client"] = ExplodingClient()

    response = client.get("/api/session/7953/standings")

    assert response.status_code == 200
    body = response.get_json()
    by_number = {d["driver_number"]: d for d in body["drivers"]}
    assert by_number[1]["position"] == [{"t": 0.0, "value": 1}]
    assert by_number[16]["gap_to_leader"] == [{"t": 0.0, "value": 1.234}]
    assert by_number[1]["laps"][0]["lap_number"] == 1


def test_a_second_request_for_the_same_session_is_still_served_from_cache(app, client):
    """The whole point of the cache: once ingested, a session is never
    re-ingested — verified here across two separate HTTP requests through
    the real Flask routing, not just at the service-layer call site."""
    fake_client = FakeIngestClient(
        sessions=[{"session_key": 7953, "meeting_key": 1140, "session_name": "Race"}],
        drivers=[{"driver_number": 1}],
        location=[{"driver_number": 1, "x": 1, "y": 1, "z": 1, "date": "2023-03-05T15:00:00"}],
    )
    app.extensions["openf1_client"] = fake_client

    first = client.get("/api/session/7953/track")
    calls_after_first = len(fake_client.calls)
    second = client.get("/api/session/7953/track")

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(fake_client.calls) == calls_after_first  # no new upstream calls
