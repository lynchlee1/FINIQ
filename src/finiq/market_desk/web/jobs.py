"""Background job management for the MarketDesk API."""

from __future__ import annotations

import time
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Callable

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
    def __init__(self):
        self._jobs: Dict[str, HtmlJob] = {}
        self._lock = threading.RLock()

    def create_job(self, job_id: str, kind: str) -> HtmlJob:
        job = HtmlJob(id=job_id, kind=kind)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[HtmlJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def start_job(self, job_id: str):
        with self._lock:
            if job := self._jobs.get(job_id):
                job.status = "running"
                job.updated_at = time.time()
                self.add_log(job_id, f"JOB start kind={job.kind} id={job_id}")

    def complete_job(self, job_id: str, result: Any):
        with self._lock:
            if job := self._jobs.get(job_id):
                job.status = "completed"
                job.result = result
                job.updated_at = time.time()
                self.add_log(job_id, f"JOB completed kind={job.kind} id={job_id}")

    def fail_job(self, job_id: str, error: str):
        with self._lock:
            if job := self._jobs.get(job_id):
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

# Global job manager instance
job_manager = JobManager()
