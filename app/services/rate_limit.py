"""Rate limiting and retry/backoff for the OpenF1 API.

OpenF1's free tier allows 3 requests/second and 30 requests/minute. This
module provides:

- ``RateLimiter``: a dual sliding-window limiter that blocks until a
  request is allowed under both windows.
- ``RateLimitedOpenF1Client``: wraps ``OpenF1Client`` so every typed
  endpoint method throttles through the limiter and retries transient
  failures (timeouts, 429, 5xx) with exponential backoff + jitter. Client
  errors that a retry can't fix (e.g. 404) are raised immediately.

Kept separate from ``openf1_client.py`` (issue #4) so the plain client
stays a small, dependency-free building block.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from app.services.openf1_client import OpenF1Client, OpenF1ClientError

logger = logging.getLogger(__name__)

OPENF1_REQUESTS_PER_SECOND = 3
OPENF1_REQUESTS_PER_MINUTE = 30

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class RateLimiter:
    """Dual sliding-window rate limiter (requests per second AND per minute).

    ``acquire()`` blocks (sleeping) until a request is allowed under both
    windows, then records it. ``clock``/``sleep`` are injectable so this is
    testable without waiting on real wall-clock time.
    """

    def __init__(
        self,
        per_second: int = OPENF1_REQUESTS_PER_SECOND,
        per_minute: int = OPENF1_REQUESTS_PER_MINUTE,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.per_second = per_second
        self.per_minute = per_minute
        self._clock = clock
        self._sleep = sleep
        self._second_window: deque[float] = deque()
        self._minute_window: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until both windows have room, then record this request."""
        with self._lock:
            while True:
                now = self._clock()
                self._prune(self._second_window, now, span=1.0)
                self._prune(self._minute_window, now, span=60.0)

                wait_for = max(
                    self._wait_time(self._second_window, self.per_second, now, span=1.0),
                    self._wait_time(self._minute_window, self.per_minute, now, span=60.0),
                )
                if wait_for <= 0:
                    self._second_window.append(now)
                    self._minute_window.append(now)
                    return

                self._sleep(wait_for)

    @staticmethod
    def _prune(window: deque[float], now: float, *, span: float) -> None:
        while window and now - window[0] >= span:
            window.popleft()

    @staticmethod
    def _wait_time(window: deque[float], limit: int, now: float, *, span: float) -> float:
        if len(window) < limit:
            return 0.0
        return span - (now - window[0])


def backoff_delay(
    attempt: int, *, base: float = 0.5, cap: float = 8.0, rand: Callable[[], float] = random.random
) -> float:
    """Exponential backoff with jitter for a given retry ``attempt`` (1-based).

    Returns a delay in [50%, 100%] of ``min(cap, base * 2**(attempt-1))`` so
    concurrent retries don't all wake up at the exact same instant.
    """
    delay = min(cap, base * (2 ** (attempt - 1)))
    return delay * (0.5 + rand() / 2)


def _is_retryable(error: OpenF1ClientError) -> bool:
    """Network/timeout errors (no status code) and 429/5xx are worth retrying."""
    return error.status_code is None or error.status_code in _RETRYABLE_STATUS_CODES


class RateLimitedOpenF1Client(OpenF1Client):
    """``OpenF1Client`` with rate limiting and retry/backoff applied.

    Only ``_get`` is overridden, so every typed endpoint method inherited
    from ``OpenF1Client`` (get_sessions, get_location, ...) automatically
    gets both behaviors without duplicating the wrapper methods.
    """

    def __init__(
        self,
        *args: Any,
        rate_limiter: RateLimiter | None = None,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.rate_limiter = rate_limiter or RateLimiter()
        self.max_retries = max_retries
        self._sleep = sleep

    def _get(self, endpoint: str, **params: Any) -> list[dict[str, Any]]:
        attempt = 0
        while True:
            self.rate_limiter.acquire()
            try:
                return super()._get(endpoint, **params)
            except OpenF1ClientError as exc:
                attempt += 1
                if attempt > self.max_retries or not _is_retryable(exc):
                    raise

                delay = backoff_delay(attempt)
                logger.warning(
                    "OpenF1 request to %r failed (attempt %d/%d), retrying in %.2fs: %s",
                    endpoint,
                    attempt,
                    self.max_retries,
                    delay,
                    exc,
                )
                self._sleep(delay)
