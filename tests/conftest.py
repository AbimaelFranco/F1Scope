"""Shared test doubles for the data/cache layer (#25).

Nothing here talks to the real OpenF1 API or the real ``instance/cache``
directory — ``FakeSession``/``FakeResponse`` stand in for ``requests``,
and any test needing a filesystem uses pytest's ``tmp_path`` fixture.
"""

from __future__ import annotations

import requests


class FakeResponse:
    """Stands in for ``requests.Response`` — only what ``OpenF1Client._get``
    actually touches: ``status_code``, ``raise_for_status()``, ``json()``.
    """

    def __init__(self, status_code: int = 200, json_data=None, *, json_error: bool = False):
        self.status_code = status_code
        self._json_data = json_data
        self._json_error = json_error

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"{self.status_code} error for url")
            error.response = self  # type: ignore[assignment]
            raise error

    def json(self):
        if self._json_error:
            raise ValueError("invalid JSON")
        return self._json_data


class FakeSession:
    """Stands in for ``requests.Session``.

    Responses are queued in call order via ``queue_response``/``queue_error``;
    each ``.get()`` call pops the next one and records the call for
    assertions. A test that only cares about the *last* response can just
    queue one.
    """

    def __init__(self):
        self.calls: list[dict] = []
        self._queue: list = []

    def queue_response(self, response: FakeResponse) -> None:
        self._queue.append(response)

    def queue_error(self, exc: Exception) -> None:
        self._queue.append(exc)

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if not self._queue:
            raise AssertionError("FakeSession.get() called with no response queued")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeIngestClient:
    """A minimal stand-in for OpenF1Client, used by ingestion/cache tests
    that need a whole session's worth of data rather than one endpoint at
    a time. Records every call (endpoint name + kwargs) so tests can
    assert *how* ingest_session() drove it — e.g. that location/car_data
    are fetched once per driver, not once for the whole session.
    """

    def __init__(self, *, sessions=None, meetings=None, drivers=None, **endpoint_data):
        self.calls: list[tuple[str, dict]] = []
        self._sessions = sessions if sessions is not None else []
        self._meetings = meetings if meetings is not None else []
        self._drivers = drivers if drivers is not None else []
        # Any other endpoint (laps, position, ...) -> a fixed list to
        # return for every call, defaulting to empty.
        self._endpoint_data = endpoint_data

    def _record(self, name, **kwargs):
        self.calls.append((name, kwargs))

    def get_sessions(self, **kwargs):
        self._record("get_sessions", **kwargs)
        return self._sessions

    def get_meetings(self, **kwargs):
        self._record("get_meetings", **kwargs)
        return self._meetings

    def get_drivers(self, **kwargs):
        self._record("get_drivers", **kwargs)
        return self._drivers

    def get_location(self, **kwargs):
        self._record("get_location", **kwargs)
        return self._endpoint_data.get("location", [])

    def get_car_data(self, **kwargs):
        self._record("get_car_data", **kwargs)
        return self._endpoint_data.get("car_data", [])

    def get_laps(self, **kwargs):
        self._record("get_laps", **kwargs)
        return self._endpoint_data.get("laps", [])

    def get_position(self, **kwargs):
        self._record("get_position", **kwargs)
        return self._endpoint_data.get("position", [])

    def get_intervals(self, **kwargs):
        self._record("get_intervals", **kwargs)
        return self._endpoint_data.get("intervals", [])

    def get_pit(self, **kwargs):
        self._record("get_pit", **kwargs)
        return self._endpoint_data.get("pit", [])

    def get_stints(self, **kwargs):
        self._record("get_stints", **kwargs)
        return self._endpoint_data.get("stints", [])

    def get_race_control(self, **kwargs):
        self._record("get_race_control", **kwargs)
        return self._endpoint_data.get("race_control", [])

    def get_weather(self, **kwargs):
        self._record("get_weather", **kwargs)
        return self._endpoint_data.get("weather", [])
