"""Process-wide serialization for jobs that issue KIND HTTP requests."""

from __future__ import annotations

import threading


KIND_NETWORK_JOB_LOCK = threading.Lock()


__all__ = ["KIND_NETWORK_JOB_LOCK"]
