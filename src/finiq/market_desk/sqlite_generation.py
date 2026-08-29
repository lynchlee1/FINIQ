"""Coordinate SQLite manifest readers with generation publication."""

from __future__ import annotations

from functools import wraps
import threading
from typing import Any, Callable


SQLITE_GENERATION_LOCK = threading.RLock()


def sqlite_generation_locked(callback: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(callback)
    def locked(*args: Any, **kwargs: Any) -> Any:
        with SQLITE_GENERATION_LOCK:
            return callback(*args, **kwargs)

    return locked
