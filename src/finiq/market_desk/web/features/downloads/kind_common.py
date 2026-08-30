"""KIND download page and API helpers for kind-web."""

from __future__ import annotations

import hashlib
import json
import re
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

from finiq.concurrency import resolve_worker_count
from finiq.data_scraper.core.client import download_pages
from finiq.data_scraper.core.constants import (
    DEFAULT_REQUEST_HEADERS,
    DISCLOSURE_GROUPS,
    MARKET_TYPES,
    SECURITIES_TYPES,
)
from finiq.data_scraper.parse import pagination_info
from finiq.data_scraper.storage.result_files import sorted_result_page_paths
from finiq.data_scraper.workflow import (
    KIND_WORKFLOW_INPUT_FORMAT,
    KindWorkflow,
    inspect_download_directory_pages,
    make_page_size_integrity_validator,
    validate_kind_workflow_input_snapshot,
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
    input_fingerprint: str = ""
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


class DownloadInputMetadataError(ValueError):
    """Raised before reusing a download folder with unusable input metadata."""


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

    known_suffixes = {suffix for suffix, _name, _items in DISCLOSURE_GROUPS}
    unknown_suffixes = sorted(str(suffix) for suffix in raw_groups if suffix not in known_suffixes)
    if unknown_suffixes:
        raise ValueError(
            "unsupported disclosure_type_groups suffixes: "
            + ", ".join(unknown_suffixes)
        )

    normalized: dict[str, list[str]] = {}
    for suffix, _, items in DISCLOSURE_GROUPS:
        selected = raw_groups.get(suffix)
        if selected is None or selected == []:
            continue
        if not isinstance(selected, list):
            raise ValueError(f"disclosure_type_groups.{suffix} must be an array")
        allowed = {code for code, _name in items}
        selected_codes = {str(code) for code in selected}
        codes = [code for code, _name in items if code in selected_codes]
        unsupported_codes = sorted(selected_codes.difference(allowed))
        if unsupported_codes:
            raise ValueError(
                f"unsupported disclosure_type_groups.{suffix} codes: "
                + ", ".join(unsupported_codes)
            )
        if codes:
            normalized[suffix] = codes
    return normalized or None


def _build_search_filters(payload: dict[str, Any]) -> dict[str, str] | None:
    search_filters: dict[str, str] = {}

    company_name = str(payload.get("company_name") or "").strip()
    if company_name:
        search_filters["searchCorpName"] = company_name

    submitter_name = str(payload.get("submitter_name") or "").strip()
    if submitter_name:
        search_filters["submitOblgNm"] = submitter_name

    market_label = str(payload.get("market_label") or "").strip()
    if market_label and market_label not in MARKET_TYPES:
        raise ValueError(f"unsupported market_label: {market_label}")
    market_value = MARKET_TYPES.get(market_label, "")
    if market_value:
        search_filters["marketType"] = market_value

    securities_label = str(payload.get("securities_label") or "").strip()
    if securities_label and securities_label not in SECURITIES_TYPES:
        raise ValueError(f"unsupported securities_label: {securities_label}")
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
    body_files = sorted_result_page_paths(folder)
    if not body_files:
        return None
    latest_file = body_files[-1]
    info = pagination_info(latest_file.read_bytes())
    if info is None:
        raise ValueError(
            f"KIND pagination not found in result page: {latest_file.name}"
        )
    info["downloaded_pages"] = len(body_files)
    info["latest_file"] = latest_file.name
    return info


def _load_workflow_input(folder: Path) -> dict[str, Any] | None:
    input_path = folder / "kind_workflow.input.json"
    if not input_path.exists():
        return None
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return None


def _require_current_download_input_snapshot(folder: Path) -> dict[str, Any]:
    input_path = folder / "kind_workflow.input.json"
    if not input_path.is_file():
        raise DownloadInputMetadataError(
            f"{folder.name}: kind_workflow.input.json metadata is missing"
        )
    try:
        snapshot = _load_workflow_input(folder)
    except Exception as exc:
        raise DownloadInputMetadataError(
            f"{folder.name}: kind_workflow.input.json metadata is corrupted: {exc}"
        ) from exc
    try:
        return validate_kind_workflow_input_snapshot(snapshot)
    except ValueError as exc:
        raise DownloadInputMetadataError(f"{folder.name}: {exc}") from exc


def _as_worker_count(payload: dict[str, Any]) -> int:
    return resolve_worker_count(
        payload.get("worker_count"),
        field_name="worker_count",
    )


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
    precomputed_file_state: str | None = None,
) -> dict[str, Any]:
    status: dict[str, Any] = {
        "output_directory": str(output_directory),
        "page_size": page_size,
        "pagination": None,
        "integrity_valid": False,
        "complete": False,
        "missing_pages": [],
        "errors": [],
    }
    try:
        file_state_before = (
            precomputed_file_state
            if precomputed_status is not None and precomputed_file_state is not None
            else _result_body_file_state(output_directory)
        )
        status["pagination"] = _detect_pagination(output_directory)
        if precomputed_status is not None and precomputed_file_state is not None:
            status.update(precomputed_status)
            status["integrity_valid"] = True
            total_pages = int(precomputed_status.get("total_pages") or 0)
            downloaded_pages = int(precomputed_status.get("downloaded_pages") or 0)
            status["complete"] = total_pages > 0 and downloaded_pages == total_pages
            if total_pages > downloaded_pages:
                status["missing_pages"] = list(range(downloaded_pages + 1, total_pages + 1))
            if file_state_before == _result_body_file_state(output_directory):
                status["file_state"] = file_state_before
            return status

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
        if file_state_before == _result_body_file_state(output_directory):
            status["file_state"] = file_state_before
    except Exception as exc:
        status["errors"].append(str(exc))
    return status


def _result_body_files(output_directory: Path) -> list[Path]:
    return sorted(output_directory.glob("*_post_page_*.body"))


def _result_body_file_state(
    output_directory: Path,
) -> str:
    digest = hashlib.sha256()
    for path in _result_body_files(output_directory):
        stat = path.stat()
        digest.update(
            f"{len(path.name)}:{path.name}:{stat.st_size}:{stat.st_mtime_ns}\n".encode(
                "utf-8"
            )
        )
    return digest.hexdigest()


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
    snapshot = {
        "format": KIND_WORKFLOW_INPUT_FORMAT,
        "request_headers": DEFAULT_REQUEST_HEADERS,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "page_size": page_size,
        "search_filters": _build_search_filters(payload),
        "disclosure_type_groups": _normalize_disclosure_type_groups(payload),
        "last_report_only": _as_bool(payload, "last_report_only"),
        "include_previous_disclosures": None,
    }
    return validate_kind_workflow_input_snapshot(snapshot)


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


def _snapshot_filters_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    try:
        validate_kind_workflow_input_snapshot(snapshot)
        search_filters_dict = dict(snapshot.get("search_filters") or [])

        market_val = search_filters_dict.get("marketType", "")
        market_labels = [label for label, value in MARKET_TYPES.items() if value == market_val]
        if len(market_labels) != 1:
            raise ValueError(f"unsupported saved marketType: {market_val!r}")

        securities_val = search_filters_dict.get("securities", "")
        securities_labels = [
            label for label, value in SECURITIES_TYPES.items() if value == securities_val
        ]
        if len(securities_labels) != 1:
            raise ValueError(f"unsupported saved securities: {securities_val!r}")

        return {
            "company_name": search_filters_dict.get("searchCorpName", ""),
            "submitter_name": search_filters_dict.get("submitOblgNm", ""),
            "market_label": market_labels[0],
            "securities_label": securities_labels[0],
            "disclosure_type_groups": snapshot.get("disclosure_type_groups") or {},
            "last_report_only": bool(snapshot.get("last_report_only")),
        }
    except (TypeError, ValueError) as exc:
        raise DownloadInputMetadataError(
            f"saved search filters cannot be normalized: {exc}"
        ) from exc


def _current_filters_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_name": str(payload.get("company_name") or "").strip(),
        "submitter_name": str(payload.get("submitter_name") or "").strip(),
        "market_label": str(payload.get("market_label") or "전체").strip()
        or "전체",
        "securities_label": str(payload.get("securities_label") or "전체").strip()
        or "전체",
        "disclosure_type_groups": _normalize_disclosure_type_groups(payload) or {},
        "last_report_only": bool(_as_bool(payload, "last_report_only")),
    }


def _download_inspection_input_fingerprint(payload: dict[str, Any]) -> str:
    """Bind an inspection receipt to inputs that affect files or their validity."""
    if _as_int(payload, "start_page", 1) != 1 or payload.get("end_page") not in (
        "",
        None,
    ):
        raise ValueError(
            "페이지 범위 제한은 더 이상 지원하지 않습니다. 전체 결과를 받으세요."
        )
    output_directory_raw = str(payload.get("output_directory") or "").strip()
    if not output_directory_raw:
        raise ValueError("output_directory is required")
    start_date_raw = str(payload.get("start_date") or "").strip()
    end_date_raw = str(payload.get("end_date") or "").strip()
    if bool(start_date_raw) != bool(end_date_raw):
        raise ValueError("start_date and end_date must be provided together")
    if start_date_raw:
        start_date = _parse_iso_date(start_date_raw, "start_date")
        end_date = _parse_iso_date(end_date_raw, "end_date")
        if end_date < start_date:
            raise ValueError("end_date must be >= start_date")
        normalized_start_date = start_date.isoformat()
        normalized_end_date = end_date.isoformat()
    else:
        normalized_start_date = ""
        normalized_end_date = ""
    mode = str(payload.get("mode") or "single").strip().lower()
    if mode not in {"single", "yearly"}:
        raise ValueError("mode must be single or yearly")
    page_size = _as_int(payload, "page_size", 100)
    if page_size < 1:
        raise ValueError("page_size must be >= 1")
    normalized = {
        "mode": mode,
        "output_directory": str(Path(output_directory_raw).expanduser().resolve()),
        "start_date": normalized_start_date,
        "end_date": normalized_end_date,
        "page_size": page_size,
        "filters": _current_filters_payload(payload),
    }
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _filters_payloads_match(
    current: dict[str, Any], saved: dict[str, Any]
) -> bool:
    def normalized_groups(payload: dict[str, Any]) -> dict[str, list[str]]:
        normalized: dict[str, list[str]] = {}
        for suffix, codes in dict(
            payload.get("disclosure_type_groups") or {}
        ).items():
            normalized_codes = sorted({str(code) for code in codes})
            if normalized_codes:
                normalized[str(suffix)] = normalized_codes
        return normalized

    return (
        str(current.get("company_name") or "").strip()
        == str(saved.get("company_name") or "").strip()
        and str(current.get("submitter_name") or "").strip()
        == str(saved.get("submitter_name") or "").strip()
        and str(current.get("market_label") or "전체")
        == str(saved.get("market_label") or "전체")
        and str(current.get("securities_label") or "전체")
        == str(saved.get("securities_label") or "전체")
        and bool(current.get("last_report_only")) == bool(saved.get("last_report_only"))
        and normalized_groups(current) == normalized_groups(saved)
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
    expected_targets = [
        (
            output_directory
            / f"{chunk_start.strftime('%Y%m%d')}_{chunk_end.strftime('%Y%m%d')}",
            page_size,
        )
        for chunk_start, chunk_end in _split_yearly_ranges(start_date, end_date)
    ]
    targets_by_path = {str(folder): (folder, size) for folder, size in expected_targets}
    if output_directory.is_dir():
        for child in output_directory.iterdir():
            if child.is_symlink():
                if child.is_dir() and _result_body_files(child):
                    raise ValueError(
                        "KIND download output directory must not contain "
                        f"symbolic-link result folders: {child}"
                    )
                continue
            if child.is_dir() and _result_body_files(child):
                targets_by_path[str(child.resolve())] = (child.resolve(), page_size)
        if _result_body_files(output_directory):
            targets_by_path[str(output_directory)] = (output_directory, page_size)
    return output_directory, [targets_by_path[key] for key in sorted(targets_by_path)]


__all__ = [name for name in globals() if not name.startswith("__")]
