"""Unit tests for RateLimiter, backoff_delay, and RateLimitedOpenF1Client
(#25) — all deterministic: fake clock/sleep instead of real wall-clock
time, so these run instantly.
"""

from __future__ import annotations

import pytest
import requests

from app.services.openf1_client import OpenF1ClientError
from app.services.rate_limit import RateLimitedOpenF1Client, RateLimiter, backoff_delay
from tests.conftest import FakeResponse, FakeSession


class FakeClock:
    """A controllable clock: sleep() advances time instead of blocking, so
    RateLimiter's wait-then-retry loop runs instantly and deterministically."""

    def __init__(self, start: float = 0.0):
        self.now = start
        self.sleep_calls: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self.now += seconds


# -- RateLimiter --------------------------------------------------------


def test_acquire_does_not_sleep_under_both_limits():
    clock = FakeClock()
    limiter = RateLimiter(per_second=3, per_minute=100, clock=clock.time, sleep=clock.sleep)

    for _ in range(3):
        limiter.acquire()

    assert clock.sleep_calls == []


def test_acquire_sleeps_when_the_per_second_limit_is_exceeded():
    clock = FakeClock()
    limiter = RateLimiter(per_second=3, per_minute=100, clock=clock.time, sleep=clock.sleep)
    for _ in range(3):
        limiter.acquire()

    limiter.acquire()  # 4th call within the same second

    assert len(clock.sleep_calls) == 1
    assert clock.sleep_calls[0] == pytest.approx(1.0)


def test_acquire_sleeps_when_the_per_minute_limit_is_exceeded():
    clock = FakeClock()
    limiter = RateLimiter(per_second=100, per_minute=2, clock=clock.time, sleep=clock.sleep)
    limiter.acquire()
    limiter.acquire()

    limiter.acquire()  # 3rd call, per_minute=2 already used up

    assert len(clock.sleep_calls) == 1
    assert clock.sleep_calls[0] == pytest.approx(60.0)


def test_acquire_does_not_sleep_once_the_window_has_naturally_elapsed():
    clock = FakeClock()
    limiter = RateLimiter(per_second=2, per_minute=100, clock=clock.time, sleep=clock.sleep)
    limiter.acquire()
    limiter.acquire()

    clock.now += 1.5  # advance time directly, without going through sleep()
    limiter.acquire()

    assert clock.sleep_calls == []


# -- backoff_delay --------------------------------------------------------


def test_backoff_delay_doubles_per_attempt_up_to_the_cap():
    # rand=0.0 -> the low end of the jitter range (delay * 0.5)
    assert backoff_delay(1, base=0.5, cap=8.0, rand=lambda: 0.0) == pytest.approx(0.25)
    assert backoff_delay(2, base=0.5, cap=8.0, rand=lambda: 0.0) == pytest.approx(0.5)
    assert backoff_delay(5, base=0.5, cap=8.0, rand=lambda: 0.0) == pytest.approx(4.0)


def test_backoff_delay_is_capped_regardless_of_attempt():
    assert backoff_delay(10, base=0.5, cap=8.0, rand=lambda: 1.0) == pytest.approx(8.0)
    assert backoff_delay(20, base=0.5, cap=8.0, rand=lambda: 1.0) == pytest.approx(8.0)


def test_backoff_delay_jitter_range_is_half_to_full():
    low = backoff_delay(3, base=1.0, cap=100.0, rand=lambda: 0.0)
    high = backoff_delay(3, base=1.0, cap=100.0, rand=lambda: 1.0)
    assert low == pytest.approx(2.0)  # min(100, 1*4) * 0.5
    assert high == pytest.approx(4.0)  # min(100, 1*4) * 1.0


# -- RateLimitedOpenF1Client -----------------------------------------------


class RecordingRateLimiter:
    """A stub rate limiter that just counts acquire() calls — the actual
    throttling math is RateLimiter's own responsibility, tested above."""

    def __init__(self):
        self.acquire_calls = 0

    def acquire(self) -> None:
        self.acquire_calls += 1


def make_rate_limited_client(session, *, rate_limiter=None, max_retries=3):
    sleeps: list[float] = []
    client = RateLimitedOpenF1Client(
        base_url="https://api.openf1.org/v1",
        session=session,
        rate_limiter=rate_limiter or RecordingRateLimiter(),
        max_retries=max_retries,
        sleep=sleeps.append,
    )
    return client, sleeps


def test_retries_a_retryable_error_and_then_succeeds():
    session = FakeSession()
    session.queue_response(FakeResponse(503, {"detail": "busy"}))
    session.queue_response(FakeResponse(200, [{"ok": True}]))
    limiter = RecordingRateLimiter()
    client, sleeps = make_rate_limited_client(session, rate_limiter=limiter)

    result = client.get_sessions(session_key=7953)

    assert result == [{"ok": True}]
    assert limiter.acquire_calls == 2  # one per real HTTP attempt
    assert len(sleeps) == 1  # one backoff sleep between the two attempts


def test_gives_up_after_max_retries():
    session = FakeSession()
    for _ in range(4):  # max_retries=3 -> 1 initial attempt + 3 retries
        session.queue_response(FakeResponse(500, {}))
    client, sleeps = make_rate_limited_client(session, max_retries=3)

    with pytest.raises(OpenF1ClientError):
        client.get_sessions(session_key=7953)

    assert len(session.calls) == 4
    assert len(sleeps) == 3


def test_non_retryable_error_is_not_retried():
    session = FakeSession()
    session.queue_response(FakeResponse(422, {"detail": "too much data"}))
    client, sleeps = make_rate_limited_client(session, max_retries=3)

    with pytest.raises(OpenF1ClientError) as exc_info:
        client.get_location(session_key=7953)

    assert exc_info.value.status_code == 422
    assert len(session.calls) == 1
    assert sleeps == []


def test_transport_error_is_retried():
    session = FakeSession()
    session.queue_error(requests.ConnectionError("boom"))
    session.queue_response(FakeResponse(200, []))
    client, sleeps = make_rate_limited_client(session, max_retries=3)

    result = client.get_weather(session_key=7953)

    assert result == []
    assert len(sleeps) == 1


def test_404_never_reaches_the_retry_logic():
    """404 is handled inside OpenF1Client._get itself (empty list, no
    exception raised) — the retry wrapper never even sees it as a failure."""
    session = FakeSession()
    session.queue_response(FakeResponse(404, {}))
    client, sleeps = make_rate_limited_client(session, max_retries=3)

    result = client.get_pit(session_key=7953)

    assert result == []
    assert sleeps == []


def test_rate_limiter_acquired_before_every_attempt_including_retries():
    session = FakeSession()
    session.queue_response(FakeResponse(500, {}))
    session.queue_response(FakeResponse(500, {}))
    session.queue_response(FakeResponse(200, []))
    limiter = RecordingRateLimiter()
    client, _sleeps = make_rate_limited_client(session, rate_limiter=limiter, max_retries=3)

    client.get_laps(session_key=7953)

    assert limiter.acquire_calls == 3
