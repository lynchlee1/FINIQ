"""Background job management for KIND downloads."""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Any

from finiq.market_desk.web.features.downloads.kind_api import run_download_action
from finiq.market_desk.web.features.downloads.kind_common import *
from finiq.market_desk.web.features.downloads.kind_inspect import inspect_download_output_directory_payload

def _job_snapshot(job: DownloadJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "progress_log": list(job.progress_log),
        "result": job.result,
        "error": job.error,
    }


def _update_job(job_id: str, **updates: Any) -> None:
    with _DOWNLOAD_JOBS_LOCK:
        job = _DOWNLOAD_JOBS[job_id]
        for key, value in updates.items():
            setattr(job, key, value)
        job.updated_at = time.time()


def _append_job_progress(job_id: str, message: str) -> None:
    with _DOWNLOAD_JOBS_LOCK:
        job = _DOWNLOAD_JOBS[job_id]
        timestamp = time.strftime("%H:%M:%S")
        job.progress_log.append(f"[{timestamp}] {message}")
        job.updated_at = time.time()


def start_download_job(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    job = DownloadJob(id=job_id, progress_log=deque(maxlen=_as_log_limit(payload)))
    with _DOWNLOAD_JOBS_LOCK:
        _DOWNLOAD_JOBS[job_id] = job
        _CANCELLED_DOWNLOAD_JOBS.discard(job_id)

    def _worker() -> None:
        acquired = False
        try:
            _append_job_progress(job_id, f"JOB queued id={job_id}")
            _DOWNLOAD_JOB_SEMAPHORE.acquire()
            acquired = True
            if _is_download_cancelled(job_id):
                raise DownloadCancelled()
            _update_job(job_id, status="running")
            _append_job_progress(job_id, f"JOB start id={job_id}")
            for line in _download_payload_summary(payload):
                _append_job_progress(job_id, f"JOB {line}")
            result = run_download_action(
                payload,
                progress_callback=lambda message: _append_job_progress(job_id, message),
                cancel_check=lambda: _is_download_cancelled(job_id),
            )
            _update_job(job_id, status="completed", result=result)
            _append_job_progress(job_id, f"JOB completed id={job_id}")
        except DownloadCancelled:
            try:
                current = inspect_download_output_directory_payload(
                    {**payload, "dry_run": True}
                )
                _update_job(job_id, result=current)
            except Exception:
                pass
            _update_job(job_id, status="cancelled")
            _append_job_progress(job_id, f"JOB cancelled id={job_id}")
        except Exception as exc:  # pragma: no cover - runtime path
            try:
                current = inspect_download_output_directory_payload(
                    {**payload, "dry_run": True}
                )
                summary = current.get("summary") or {}
                _append_job_progress(
                    job_id,
                    f"CURRENT success={summary.get('success', 0)}/{summary.get('total', 0)} failed={summary.get('failed', 0)}",
                )
                _update_job(job_id, result=current)
            except Exception:
                pass
            _update_job(job_id, status="failed", error=str(exc))
            _append_job_progress(job_id, f"JOB failed error={exc}")
        finally:
            if acquired:
                _DOWNLOAD_JOB_SEMAPHORE.release()
            with _DOWNLOAD_JOBS_LOCK:
                _CANCELLED_DOWNLOAD_JOBS.discard(job_id)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return get_download_job(job_id)


def cancel_download_job(job_id: str) -> dict[str, Any]:
    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        raise ValueError("job_id is required")
    with _DOWNLOAD_JOBS_LOCK:
        job = _DOWNLOAD_JOBS.get(normalized_job_id)
        if job is None:
            raise ValueError(f"download job not found: {normalized_job_id}")
        if job.status in {"completed", "failed", "cancelled"}:
            return _job_snapshot(job)
        _CANCELLED_DOWNLOAD_JOBS.add(normalized_job_id)
        job.updated_at = time.time()
    _append_job_progress(normalized_job_id, "JOB cancel_requested")
    return get_download_job(normalized_job_id)


def get_download_job(job_id: str) -> dict[str, Any]:
    with _DOWNLOAD_JOBS_LOCK:
        job = _DOWNLOAD_JOBS.get(job_id)
        if job is None:
            raise ValueError(f"download job not found: {job_id}")
        return _job_snapshot(job)


def start_inspect_folder_job(payload: dict[str, Any]) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    job = DownloadJob(id=job_id, progress_log=deque(maxlen=_as_log_limit(payload)))
    with _DOWNLOAD_JOBS_LOCK:
        _DOWNLOAD_JOBS[job_id] = job
        _CANCELLED_DOWNLOAD_JOBS.discard(job_id)

    def _worker() -> None:
        try:
            _update_job(job_id, status="running")
            _append_job_progress(job_id, f"JOB inspect start id={job_id}")
            result = inspect_download_output_directory_payload(
                payload,
                progress_callback=lambda message: _append_job_progress(job_id, message),
                cancel_check=lambda: _is_download_cancelled(job_id),
            )
            _update_job(job_id, status="completed", result=result)
            _append_job_progress(job_id, f"JOB inspect completed id={job_id}")
        except DownloadCancelled:
            _update_job(job_id, status="cancelled")
            _append_job_progress(job_id, f"JOB inspect cancelled id={job_id}")
        except Exception as exc:
            _update_job(job_id, status="failed", error=str(exc))
            _append_job_progress(job_id, f"JOB inspect failed error={exc}")
        finally:
            with _DOWNLOAD_JOBS_LOCK:
                _CANCELLED_DOWNLOAD_JOBS.discard(job_id)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return get_download_job(job_id)


