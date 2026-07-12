"""Process-wide request limit shared by KIND HTML download workflows."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from contextlib import ExitStack


HTML_DOWNLOAD_MAX_REQUESTS_PER_MINUTE = 100
CancelCheck = Callable[[], bool]


class SlidingWindowRateLimiter:
    def __init__(self, max_requests_per_minute: int):
        if max_requests_per_minute < 1:
            raise ValueError("max_requests_per_minute must be at least 1")
        self._lock = threading.Lock()
        self._max_requests_per_minute = max_requests_per_minute
        self._request_timestamps: list[float] = []

    def wait(self, cancel_check: CancelCheck | None = None) -> bool:
        return wait_for_rate_limiters((self,), cancel_check)

    def _prune_locked(self, now: float) -> None:
        self._request_timestamps = [
            timestamp
            for timestamp in self._request_timestamps
            if now - timestamp < 60
        ]


class RequestSpacingLimiter:
    def __init__(self, minimum_interval_seconds: float):
        if minimum_interval_seconds < 0:
            raise ValueError("minimum_interval_seconds must be non-negative")
        self._lock = threading.Lock()
        self._minimum_interval_seconds = minimum_interval_seconds
        self._next_request_time = 0.0


def wait_for_rate_limiters(
    limiters: tuple[SlidingWindowRateLimiter, ...],
    cancel_check: CancelCheck | None = None,
    *,
    spacing_limiter: RequestSpacingLimiter | None = None,
) -> bool:
    ordered_limiters = tuple(sorted(dict.fromkeys(limiters), key=id))
    if not ordered_limiters and spacing_limiter is None:
        return bool(cancel_check is not None and cancel_check())

    while True:
        if cancel_check is not None and cancel_check():
            return True

        now = time.monotonic()
        locks = [limiter._lock for limiter in ordered_limiters]
        if spacing_limiter is not None:
            locks.append(spacing_limiter._lock)
        with ExitStack() as stack:
            for lock in sorted(locks, key=id):
                stack.enter_context(lock)
            for limiter in ordered_limiters:
                limiter._prune_locked(now)
            windows_available = all(
                len(limiter._request_timestamps)
                < limiter._max_requests_per_minute
                for limiter in ordered_limiters
            )
            spacing_available = (
                spacing_limiter is None
                or now >= spacing_limiter._next_request_time
            )
            if windows_available and spacing_available:
                for limiter in ordered_limiters:
                    limiter._request_timestamps.append(now)
                if spacing_limiter is not None:
                    spacing_limiter._next_request_time = (
                        now + spacing_limiter._minimum_interval_seconds
                    )
                return False

        time.sleep(0.1)


_HTML_DOWNLOAD_RATE_LIMITER = SlidingWindowRateLimiter(
    HTML_DOWNLOAD_MAX_REQUESTS_PER_MINUTE
)


def wait_for_html_download_request_slot(
    cancel_check: CancelCheck | None = None,
    *,
    local_limiter: SlidingWindowRateLimiter | None = None,
    spacing_limiter: RequestSpacingLimiter | None = None,
) -> bool:
    """Reserve one request atomically across windows and minimum spacing."""
    limiters = (
        (_HTML_DOWNLOAD_RATE_LIMITER, local_limiter)
        if local_limiter is not None
        else (_HTML_DOWNLOAD_RATE_LIMITER,)
    )
    return wait_for_rate_limiters(
        limiters,
        cancel_check,
        spacing_limiter=spacing_limiter,
    )
