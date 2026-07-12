"""Background job management for the MarketDesk API."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


DEFAULT_JOB_RETENTION_MINUTES = 60
TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}


def normalize_job_retention_minutes(value: Any) -> int:
    try:
        minutes = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("job_retention_minutes must be an integer") from exc
    if minutes < 1:
        raise ValueError("job_retention_minutes must be >= 1")
    return minutes


@dataclass(slots=True)
class HtmlJob:
    """Represents a background job."""

    id: str
    kind: str
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    progress_log: deque[str] = field(default_factory=lambda: deque(maxlen=100))
    result: dict[str, Any] | None = None
    error: str | None = None


class JobManager:
    """Manages background jobs in memory."""

    def __init__(self, *, retention_minutes: int = DEFAULT_JOB_RETENTION_MINUTES):
        self._jobs: Dict[str, HtmlJob] = {}
        self._lock = threading.RLock()
        self._retention_minutes = normalize_job_retention_minutes(retention_minutes)

    def set_retention_minutes(self, minutes: int) -> None:
        normalized = normalize_job_retention_minutes(minutes)
        with self._lock:
            self._retention_minutes = normalized
            self._purge_expired_locked()

    def _purge_expired_locked(self, *, now: float | None = None) -> int:
        current_time = time.time() if now is None else now
        cutoff = current_time - (self._retention_minutes * 60)
        expired_ids = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in TERMINAL_JOB_STATUSES and job.updated_at < cutoff
        ]
        for job_id in expired_ids:
            del self._jobs[job_id]
        return len(expired_ids)

    def purge_expired(self, *, now: float | None = None) -> int:
        with self._lock:
            return self._purge_expired_locked(now=now)

    def create_job(self, job_id: str, kind: str) -> HtmlJob:
        job = HtmlJob(id=job_id, kind=kind)
        with self._lock:
            self._purge_expired_locked()
            self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[HtmlJob]:
        with self._lock:
            self._purge_expired_locked()
            return self._jobs.get(job_id)

    def start_job(self, job_id: str) -> bool:
        with self._lock:
            if job := self._jobs.get(job_id):
                if job.status == "cancelled":
                    return False
                job.status = "running"
                job.updated_at = time.time()
                self.add_log(job_id, f"JOB start kind={job.kind} id={job_id}")
                return True
            return False

    def complete_job(self, job_id: str, result: Any):
        with self._lock:
            if job := self._jobs.get(job_id):
                if job.status == "cancelled":
                    return
                job.status = "completed"
                job.result = result
                job.updated_at = time.time()
                self.add_log(job_id, f"JOB completed kind={job.kind} id={job_id}")

    def fail_job(self, job_id: str, error: str):
        with self._lock:
            if job := self._jobs.get(job_id):
                if job.status == "cancelled":
                    return
                job.status = "failed"
                job.error = error
                job.updated_at = time.time()
                self.add_log(job_id, f"JOB failed error={error}")

    def add_log(self, job_id: str, message: str):
        timestamp = time.strftime("%H:%M:%S")
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].progress_log.append(f"[{timestamp}] {message}")
                self._jobs[job_id].updated_at = time.time()

    def get_snapshot(self, job_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            self._purge_expired_locked()
            job = self._jobs.get(job_id)
            if not job:
                return None
            return {
                "job_id": job.id,
                "kind": job.kind,
                "status": job.status,
                "created_at": job.created_at,
                "updated_at": job.updated_at,
                "progress_log": list(job.progress_log),
                "result": job.result,
                "error": job.error,
            }

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            self._purge_expired_locked()
            if job := self._jobs.get(job_id):
                if job.status not in {"completed", "failed", "cancelled"}:
                    job.status = "cancelled"
                    job.updated_at = time.time()
                    self.add_log(job_id, "작업 중단이 요청되었습니다.")
                return True
            return False

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            if job := self._jobs.get(job_id):
                return job.status == "cancelled"
            return False


# Global job manager instance
job_manager = JobManager()
