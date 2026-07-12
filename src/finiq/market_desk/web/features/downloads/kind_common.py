"""KIND download page and API helpers for kind-web."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import deque
from collections.abc import MutableSequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from finiq.data_scraper.core.client import download_pages
from finiq.data_scraper.core.constants import (
    DEFAULT_REQUEST_HEADERS,
    DISCLOSURE_GROUPS,
    MARKET_TYPES,
    SECURITIES_TYPES,
)
from finiq.data_scraper.parse import pagination_info
from finiq.data_scraper.workflow import (
    KindWorkflow,
    inspect_download_directory_pages,
    make_page_size_integrity_validator,
    validate_downloaded_result_page,
)
from finiq.data_scraper.workflow.workflow import _validate_downloaded_result_page_task
from finiq.market_desk.web.features.downloads.page import render_download_page
from finiq.market_desk.web.jobs import (
    DEFAULT_JOB_RETENTION_MINUTES,
    TERMINAL_JOB_STATUSES,
    normalize_job_retention_minutes,
)


@dataclass(slots=True)
class DownloadJob:
    id: str
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    progress_log: deque[str] = field(default_factory=lambda: deque(maxlen=20))
    result: dict[str, Any] | None = None
    error: str | None = None


_DOWNLOAD_JOBS: dict[str, DownloadJob] = {}
_DOWNLOAD_JOBS_LOCK = threading.Lock()
_DOWNLOAD_JOB_SEMAPHORE = threading.Semaphore(1)
_CANCELLED_DOWNLOAD_JOBS: set[str] = set()
_DOWNLOAD_JOB_RETENTION_MINUTES = DEFAULT_JOB_RETENTION_MINUTES
DOWNLOAD_DELETE_CONFIRMATION_TEXT = "확인했습니다."
DOWNLOAD_PARALLEL_STRATEGIES = {"years", "pages"}


class DownloadCancelled(Exception):
    """Raised when a running download job is cancelled by the user."""


def _purge_expired_download_jobs_locked(*, now: float | None = None) -> int:
    current_time = time.time() if now is None else now
    cutoff = current_time - (_DOWNLOAD_JOB_RETENTION_MINUTES * 60)
    expired_ids = [
        job_id
        for job_id, job in _DOWNLOAD_JOBS.items()
        if job.status in TERMINAL_JOB_STATUSES and job.updated_at < cutoff
    ]
    for job_id in expired_ids:
        del _DOWNLOAD_JOBS[job_id]
        _CANCELLED_DOWNLOAD_JOBS.discard(job_id)
    return len(expired_ids)


def configure_download_job_retention(minutes: int) -> None:
    global _DOWNLOAD_JOB_RETENTION_MINUTES
    normalized = normalize_job_retention_minutes(minutes)
    with _DOWNLOAD_JOBS_LOCK:
        _DOWNLOAD_JOB_RETENTION_MINUTES = normalized
        _purge_expired_download_jobs_locked()


def _is_download_cancelled(job_id: str | None) -> bool:
    return bool(job_id and job_id in _CANCELLED_DOWNLOAD_JOBS)


def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc


def _split_yearly_ranges(start: date, end: date) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        year_end = date(cursor.year, 12, 31)
        ranges.append((cursor, min(year_end, end)))
        cursor = date(cursor.year + 1, 1, 1)
    return ranges


def _normalize_disclosure_type_groups(
    payload: dict[str, Any],
) -> dict[str, list[str]] | None:
    raw_groups = payload.get("disclosure_type_groups")
    if not raw_groups:
        return None
    if not isinstance(raw_groups, dict):
        raise ValueError("disclosure_type_groups must be an object")

    normalized: dict[str, list[str]] = {}
    for suffix, _, items in DISCLOSURE_GROUPS:
        selected = raw_groups.get(suffix)
        if not selected:
            continue
        if not isinstance(selected, list):
            raise ValueError(f"disclosure_type_groups.{suffix} must be an array")
        allowed = {code for code, _name in items}
        codes = [str(code) for code in selected if str(code) in allowed]
        if codes:
            normalized[suffix] = codes
    return normalized or None


def _has_complete_current_download_payload(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    required_keys = {
        "start_date",
        "end_date",
        "company_name",
        "submitter_name",
        "market_label",
        "securities_label",
        "page_size",
        "last_report_only",
        "disclosure_type_groups",
    }
    return required_keys.issubset(payload.keys())


def _is_trusted_download_input_snapshot(snapshot: dict[str, Any] | None) -> bool:
    if not isinstance(snapshot, dict):
        return False
    required_keys = {
        "request_headers",
        "start_date",
        "end_date",
        "page_size",
        "search_filters",
        "disclosure_type_groups",
        "last_report_only",
        "include_previous_disclosures",
    }
    if not required_keys.issubset(snapshot.keys()):
        return False
    try:
        date.fromisoformat(str(snapshot["start_date"]))
        date.fromisoformat(str(snapshot["end_date"]))
        int(snapshot["page_size"])
    except Exception:
        return False
    return True


def _build_search_filters(payload: dict[str, Any]) -> dict[str, str] | None:
    search_filters: dict[str, str] = {}

    company_name = str(payload.get("company_name") or "").strip()
    if company_name:
        search_filters["searchCorpName"] = company_name

    submitter_name = str(payload.get("submitter_name") or "").strip()
    if submitter_name:
        search_filters["submitOblgNm"] = submitter_name

    market_label = str(payload.get("market_label") or "").strip()
    market_value = MARKET_TYPES.get(market_label, "")
    if market_value:
        search_filters["marketType"] = market_value

    securities_label = str(payload.get("securities_label") or "").strip()
    securities_value = SECURITIES_TYPES.get(securities_label, "")
    if securities_value:
        search_filters["securities"] = securities_value

    return search_filters or None


def _as_int(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key)
    if value in ("", None):
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _as_float(payload: dict[str, Any], key: str, default: float) -> float:
    value = payload.get(key)
    if value in ("", None):
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a number") from exc


def _as_bool(payload: dict[str, Any], key: str) -> bool | None:
    value = payload.get(key)
    if value in ("", None):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    raise ValueError(f"{key} must be a boolean")


def _detect_pagination(folder: Path) -> dict[str, Any] | None:
    body_files = sorted(folder.glob("*_post_page_*.body"))
    if not body_files:
        return None
    latest = body_files[-1]
    info = pagination_info(latest.read_bytes())
    if info is None:
        return None
    info["downloaded_pages"] = len(body_files)
    info["latest_file"] = latest.name
    return info


def _load_workflow_input(folder: Path) -> dict[str, Any] | None:
    input_path = folder / "kind_workflow.input.json"
    if not input_path.exists():
        return None
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return None


def _as_worker_count(payload: dict[str, Any], *, default: int | None = None) -> int:
    cpu_count = os.cpu_count() or 1
    fallback = default if default is not None else min(4, cpu_count)
    worker_count = _as_int(payload, "worker_count", fallback)
    if worker_count < 1:
        raise ValueError("worker_count must be >= 1")
    return min(worker_count, cpu_count)


def _as_parallel_strategy(payload: dict[str, Any]) -> str:
    strategy = str(payload.get("parallel_strategy") or "years").strip().lower()
    if strategy not in DOWNLOAD_PARALLEL_STRATEGIES:
        raise ValueError("parallel_strategy must be one of: years, pages")
    return strategy


def _as_log_limit(payload: dict[str, Any], *, default: int = 20) -> int:
    log_limit = _as_int(payload, "log_limit", default)
    if log_limit < 1:
        raise ValueError("log_limit must be >= 1")
    return min(log_limit, 500)


def _as_resume_yearly(payload: dict[str, Any]) -> bool:
    value = payload.get("resume_yearly")
    if value in ("", None):
        return True
    return bool(_as_bool(payload, "resume_yearly"))


def _build_progress_collector(
    prefix: str = "", external_callback: Any | None = None
) -> tuple[deque[str], Any]:
    progress_log: deque[str] = deque(maxlen=0)

    def _callback(message: str) -> None:
        normalized = str(message).strip()
        if normalized:
            line = f"{prefix}{normalized}"
            if progress_log.maxlen != 0:
                progress_log.append(line)
            if external_callback is not None:
                external_callback(line)

    return progress_log, _callback


def _download_integrity_status(
    output_directory: Path,
    page_size: int,
    precomputed_status: dict[str, int] | None = None,
) -> dict[str, Any]:
    pagination = _detect_pagination(output_directory)
    status: dict[str, Any] = {
        "output_directory": str(output_directory),
        "pagination": pagination,
        "integrity_valid": False,
        "complete": False,
        "missing_pages": [],
        "errors": [],
    }
    if precomputed_status is not None:
        status.update(precomputed_status)
        status["integrity_valid"] = True
        total_pages = int(precomputed_status.get("total_pages") or 0)
        downloaded_pages = int(precomputed_status.get("downloaded_pages") or 0)
        status["complete"] = total_pages > 0 and downloaded_pages == total_pages
        if total_pages > downloaded_pages:
            status["missing_pages"] = list(range(downloaded_pages + 1, total_pages + 1))
        return status

    try:
        inspected = inspect_download_directory_pages(
            output_directory,
            expected_page_size=page_size,
            require_complete=False,
        )
        total_pages = int(inspected.get("total_pages") or 0)
        downloaded_pages = int(inspected.get("downloaded_pages") or 0)
        status.update(inspected)
        status["integrity_valid"] = True
        status["complete"] = total_pages > 0 and downloaded_pages == total_pages
        if total_pages > downloaded_pages:
            status["missing_pages"] = list(range(downloaded_pages + 1, total_pages + 1))
    except Exception as exc:
        status["errors"].append(str(exc))
    return status


def _result_body_files(output_directory: Path) -> list[Path]:
    return sorted(output_directory.glob("*_post_page_*.body"))


def _workflow_auxiliary_files(output_directory: Path) -> list[Path]:
    return [
        path
        for path in (
            output_directory / "kind_workflow.input.json",
            output_directory / "kind_workflow.checkpoint.json",
        )
        if path.exists()
    ]


def _download_input_snapshot_from_payload(
    payload: dict[str, Any], *, start: date, end: date, page_size: int
) -> dict[str, Any]:
    return {
        "request_headers": DEFAULT_REQUEST_HEADERS,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "page_size": page_size,
        "search_filters": _build_search_filters(payload),
        "disclosure_type_groups": _normalize_disclosure_type_groups(payload),
        "last_report_only": _as_bool(payload, "last_report_only"),
        "include_previous_disclosures": None,
    }


def _write_download_input_snapshot(folder: Path, snapshot: dict[str, Any]) -> None:
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _folder_date_range_from_name(folder: Path) -> tuple[date, date] | None:
    parts = folder.name.split("_")
    if len(parts) != 2 or len(parts[0]) != 8 or len(parts[1]) != 8:
        return None
    if not parts[0].isdigit() or not parts[1].isdigit():
        return None
    try:
        return (
            date(int(parts[0][0:4]), int(parts[0][4:6]), int(parts[0][6:8])),
            date(int(parts[1][0:4]), int(parts[1][4:6]), int(parts[1][6:8])),
        )
    except Exception:
        return None


def _expected_date_range_for_folder(
    payload: dict[str, Any], folder: Path
) -> tuple[date, date]:
    mode = str(payload.get("mode") or "single").strip().lower()
    if mode == "yearly":
        folder_range = _folder_date_range_from_name(folder)
        if folder_range is not None:
            return folder_range
    start_date_raw = str(payload.get("start_date") or "").strip()
    end_date_raw = str(payload.get("end_date") or "").strip()
    return _parse_iso_date(start_date_raw, "start_date"), _parse_iso_date(
        end_date_raw, "end_date"
    )


def _snapshot_filters_payload(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    if not _is_trusted_download_input_snapshot(snapshot):
        return None
    try:
        search_filters_dict = dict(snapshot.get("search_filters") or [])

        market_val = search_filters_dict.get("marketType", "")
        market_label = "검색대상"
        for label, val in MARKET_TYPES.items():
            if val == market_val:
                market_label = label
                break

        securities_val = search_filters_dict.get("securities", "")
        securities_label = "전체"
        for label, val in SECURITIES_TYPES.items():
            if val == securities_val:
                securities_label = label
                break

        return {
            "company_name": search_filters_dict.get("searchCorpName", ""),
            "submitter_name": search_filters_dict.get("submitOblgNm", ""),
            "market_label": market_label,
            "securities_label": securities_label,
            "disclosure_type_groups": snapshot.get("disclosure_type_groups") or {},
            "last_report_only": bool(snapshot.get("last_report_only")),
        }
    except Exception:
        return None


def _current_filters_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_name": str(payload.get("company_name") or ""),
        "submitter_name": str(payload.get("submitter_name") or ""),
        "market_label": str(payload.get("market_label") or "검색대상"),
        "securities_label": str(payload.get("securities_label") or "전체"),
        "disclosure_type_groups": _normalize_disclosure_type_groups(payload) or {},
        "last_report_only": _as_bool(payload, "last_report_only"),
    }


def _filters_payloads_match(
    current: dict[str, Any], saved: dict[str, Any] | None
) -> bool:
    if saved is None:
        return True
    return (
        str(current.get("company_name") or "").strip()
        == str(saved.get("company_name") or "").strip()
        and str(current.get("submitter_name") or "").strip()
        == str(saved.get("submitter_name") or "").strip()
        and str(current.get("market_label") or "검색대상")
        == str(saved.get("market_label") or "검색대상")
        and str(current.get("securities_label") or "전체")
        == str(saved.get("securities_label") or "전체")
        and bool(current.get("last_report_only")) == bool(saved.get("last_report_only"))
        and json.dumps(current.get("disclosure_type_groups") or {}, sort_keys=True)
        == json.dumps(saved.get("disclosure_type_groups") or {}, sort_keys=True)
    )


def _relative_candidate(path: Path, base: Path, reason: str) -> dict[str, str]:
    return {
        "path": str(path),
        "name": str(path.relative_to(base)),
        "reason": reason,
    }


def _download_cleanup_targets(
    payload: dict[str, Any],
) -> tuple[Path, list[tuple[Path, int]]]:
    mode = str(payload.get("mode") or "single").strip().lower()
    output_directory_raw = str(payload.get("output_directory") or "").strip()
    if not output_directory_raw:
        raise ValueError("output_directory is required")
    output_directory = Path(output_directory_raw).expanduser().resolve()

    from finiq.config import PROJECT_ROOT

    risky_directories = {
        Path(output_directory.anchor).resolve(),
        Path.home().resolve(),
        PROJECT_ROOT.resolve(),
    }
    risky_directories.update(PROJECT_ROOT.resolve().parents)
    if output_directory in risky_directories:
        msg = f"Refusing to inspect or clean high-risk output_directory: {output_directory}"
        raise ValueError(msg)

    page_size = _as_int(payload, "page_size", 100)
    if mode != "yearly":
        return output_directory, [(output_directory, page_size)]

    start_date_raw = str(payload.get("start_date") or "").strip()
    end_date_raw = str(payload.get("end_date") or "").strip()
    if not start_date_raw or not end_date_raw:
        raise ValueError("start_date and end_date are required")
    start_date = _parse_iso_date(start_date_raw, "start_date")
    end_date = _parse_iso_date(end_date_raw, "end_date")
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")
    targets = [
        (
            output_directory
            / f"{chunk_start.strftime('%Y%m%d')}_{chunk_end.strftime('%Y%m%d')}",
            page_size,
        )
        for chunk_start, chunk_end in _split_yearly_ranges(start_date, end_date)
    ]
    return output_directory, targets


def _folder_download_deletion_candidates(
    folder: Path, page_size: int, base: Path
) -> list[dict[str, str]]:
    if not folder.exists():
        return []
    body_files = _result_body_files(folder)
    if not body_files:
        return []

    candidates: list[dict[str, str]] = []
    input_snapshot = _load_workflow_input(folder)
    if input_snapshot is None:
        return [
            _relative_candidate(path, base, "입력 스냅샷 없이 남아 있는 다운로드 결과")
            for path in body_files
        ]

    locked_page_size = input_snapshot.get("page_size")
    if locked_page_size is None or int(locked_page_size) != page_size:
        reason = "현재 요청의 페이지 크기와 맞지 않는 기존 다운로드 상태"
        return [
            _relative_candidate(path, base, reason)
            for path in body_files + _workflow_auxiliary_files(folder)
        ]

    for path in body_files:
        try:
            validate_downloaded_result_page(path, expected_page_size=page_size)
        except Exception as exc:
            candidates.append(_relative_candidate(path, base, str(exc)))

    if candidates:
        return candidates

    try:
        inspect_download_directory_pages(
            folder, expected_page_size=page_size, require_complete=False
        )
    except Exception as exc:
        reason = str(exc)
        return [_relative_candidate(path, base, reason) for path in body_files]
    return []


__all__ = [name for name in globals() if not name.startswith("__")]
