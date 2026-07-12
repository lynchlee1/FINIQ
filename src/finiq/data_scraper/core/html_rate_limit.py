"""Process-wide request limit shared by KIND HTML download workflows."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


HTML_DOWNLOAD_MAX_REQUESTS_PER_MINUTE = 100
CancelCheck = Callable[[], bool]


class SlidingWindowRateLimiter:
    def __init__(self, max_requests_per_minute: int):
        self._lock = threading.Lock()
        self._max_requests_per_minute = max_requests_per_minute
        self._request_timestamps: list[float] = []

    def wait(self, cancel_check: CancelCheck | None = None) -> bool:
        while True:
            if cancel_check is not None and cancel_check():
                return True

            now = time.monotonic()
            with self._lock:
                self._request_timestamps = [
                    timestamp
                    for timestamp in self._request_timestamps
                    if now - timestamp < 60
                ]
                if len(self._request_timestamps) < self._max_requests_per_minute:
                    self._request_timestamps.append(now)
                    return False

            time.sleep(0.1)


_HTML_DOWNLOAD_RATE_LIMITER = SlidingWindowRateLimiter(
    HTML_DOWNLOAD_MAX_REQUESTS_PER_MINUTE
)


def wait_for_html_download_request_slot(
    cancel_check: CancelCheck | None = None,
) -> bool:
    """Reserve one request shared by external and content HTML downloads."""
    return _HTML_DOWNLOAD_RATE_LIMITER.wait(cancel_check)
