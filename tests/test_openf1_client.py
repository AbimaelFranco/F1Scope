"""Unit tests for OpenF1Client (#25) — request building and error handling.

No real HTTP: FakeSession/FakeResponse (see conftest.py) stand in for
``requests``, so these run instantly and don't touch OpenF1 or burn its
rate-limit budget.
"""

from __future__ import annotations

import requests

from app.services.openf1_client import OpenF1Client, OpenF1ClientError
from tests.conftest import FakeResponse, FakeSession


def make_client(session: FakeSession) -> OpenF1Client:
    return OpenF1Client(base_url="https://api.openf1.org/v1", session=session)


def test_get_returns_the_json_list():
    session = FakeSession()
    session.queue_response(FakeResponse(200, [{"session_key": 7953}]))
    client = make_client(session)

    result = client.get_sessions(session_key=7953)

    assert result == [{"session_key": 7953}]


def test_get_builds_the_correct_url_and_params():
    session = FakeSession()
    session.queue_response(FakeResponse(200, []))
    client = make_client(session)

    client.get_location(session_key=7953, driver_number=1)

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == "https://api.openf1.org/v1/location"
    assert call["params"] == {"session_key": 7953, "driver_number": 1}


def test_get_drops_none_valued_filters():
    """A caller passing lap_number=None (e.g. build_telemetry's "no lap
    filter" case) shouldn't send `lap_number=None` as a literal query
    param — OpenF1 would treat that as the string "None", not "omitted"."""
    session = FakeSession()
    session.queue_response(FakeResponse(200, []))
    client = make_client(session)

    client.get_laps(session_key=7953, lap_number=None)

    assert session.calls[0]["params"] == {"session_key": 7953}


def test_404_returns_empty_list_not_an_error():
    """OpenF1's own documented behavior: 404 means "no results", not a
    real error — e.g. a session with zero pit stops. See the docstring on
    OpenF1Client._get for the full rationale."""
    session = FakeSession()
    session.queue_response(FakeResponse(404, {"detail": "No results found."}))
    client = make_client(session)

    result = client.get_pit(session_key=7953)

    assert result == []


def test_http_error_raises_with_status_code():
    session = FakeSession()
    session.queue_response(FakeResponse(422, {"detail": "Too much data"}))
    client = make_client(session)

    try:
        client.get_location(session_key=7953)
        raise AssertionError("expected OpenF1ClientError")
    except OpenF1ClientError as exc:
        assert exc.status_code == 422


def test_transport_error_raises_without_status_code():
    """A connection/timeout failure (no HTTP response at all) should still
    surface as OpenF1ClientError, but with status_code=None — the
    rate-limited client (#5) uses that None to know it's worth retrying
    regardless of any status code."""
    session = FakeSession()
    session.queue_error(requests.ConnectionError("connection refused"))
    client = make_client(session)

    try:
        client.get_weather(session_key=7953)
        raise AssertionError("expected OpenF1ClientError")
    except OpenF1ClientError as exc:
        assert exc.status_code is None


def test_non_json_response_raises():
    session = FakeSession()
    session.queue_response(FakeResponse(200, None, json_error=True))
    client = make_client(session)

    try:
        client.get_stints(session_key=7953)
        raise AssertionError("expected OpenF1ClientError")
    except OpenF1ClientError:
        pass


def test_non_list_json_raises():
    """OpenF1 endpoints always return a JSON array — a dict body (e.g. an
    unexpected error shape) should be treated as a broken response, not
    silently accepted."""
    session = FakeSession()
    session.queue_response(FakeResponse(200, {"unexpected": "shape"}))
    client = make_client(session)

    try:
        client.get_race_control(session_key=7953)
        raise AssertionError("expected OpenF1ClientError")
    except OpenF1ClientError:
        pass


def test_base_url_trailing_slash_is_stripped():
    session = FakeSession()
    session.queue_response(FakeResponse(200, []))
    client = OpenF1Client(base_url="https://api.openf1.org/v1/", session=session)

    client.get_meetings(meeting_key=1140)

    assert session.calls[0]["url"] == "https://api.openf1.org/v1/meetings"
