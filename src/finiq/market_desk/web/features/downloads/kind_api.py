"""KIND download request payload APIs."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from finiq.data_scraper.core.constants import DEFAULT_REQUEST_HEADERS, DISCLOSURE_GROUPS, MARKET_TYPES, SECURITIES_TYPES
from finiq.data_scraper.workflow import KindWorkflow

from finiq.market_desk.web.features.downloads.kind_common import *
from finiq.market_desk.web.features.downloads.kind_runner import _run_resume, _run_single, _run_yearly
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
)


def build_download_options_payload(
    *, default_output_directory: str | Path
) -> dict[str, Any]:
    return {
        "default_output_directory": str(Path(default_output_directory).resolve()),
        "market_types": [
            {"label": label, "value": value} for label, value in MARKET_TYPES.items()
        ],
        "securities_types": [
            {"label": label, "value": value}
            for label, value in SECURITIES_TYPES.items()
        ],
        "disclosure_groups": [
            {
                "suffix": suffix,
                "label": label,
                "items": [{"code": code, "name": name} for code, name in items],
            }
            for suffix, label, items in DISCLOSURE_GROUPS
        ],
    }


def build_download_preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = apply_workspace_defaults("kind_download", payload)
    output_directory_raw = str(payload.get("output_directory") or "").strip()
    if not output_directory_raw:
        raise ValueError("output_directory is required")
    start_date_raw = str(payload.get("start_date") or "").strip()
    end_date_raw = str(payload.get("end_date") or "").strip()
    if not start_date_raw or not end_date_raw:
        raise ValueError("start_date and end_date are required")
    _parse_iso_date(start_date_raw, "start_date")
    _parse_iso_date(end_date_raw, "end_date")

    start_page = _as_int(payload, "start_page", 1)
    end_page = payload.get("end_page")
    end_page_value = (
        _as_int(payload, "end_page", start_page)
        if end_page not in ("", None)
        else start_page
    )
    page_size = _as_int(payload, "page_size", 100)
    wait_seconds = _as_float(payload, "wait_seconds", 1.0)
    timeout = _as_float(payload, "timeout", 20.0)
    if wait_seconds < 0:
        raise ValueError("wait_seconds must be >= 0")
    if timeout <= 0:
        raise ValueError("timeout must be > 0")

    workflow = KindWorkflow()
    workflow.configure(
        output_directory=output_directory_raw,
        request_headers=DEFAULT_REQUEST_HEADERS,
        start_date=start_date_raw,
        end_date=end_date_raw,
        start_page=start_page,
        end_page=end_page_value,
        page_size=page_size,
        search_filters=_build_search_filters(payload),
        disclosure_type_groups=_normalize_disclosure_type_groups(payload),
        last_report_only=_as_bool(payload, "last_report_only"),
        include_previous_disclosures=None,
        wait_seconds_between_requests=wait_seconds,
        timeout=timeout,
    )
    request_data = workflow.build_request_data(page_number=start_page)
    return {
        "mode": str(payload.get("mode") or "single"),
        "request_data": [
            {"name": name, "value": value} for name, value in request_data
        ],
    }


def build_download_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = apply_workspace_defaults("kind_download", payload)
    output_directory_raw = str(payload.get("output_directory") or "").strip()
    if not output_directory_raw:
        raise ValueError("output_directory is required")
    output_directory = Path(output_directory_raw).expanduser().resolve()
    if not output_directory.is_dir():
        raise ValueError(f"directory not found: {output_directory}")

    saved_input = _load_workflow_input(output_directory) or {}
    page_size = _as_int(payload, "page_size", int(saved_input.get("page_size") or 100))
    status = _download_integrity_status(output_directory, page_size)
    progress_log: deque[str] = deque(maxlen=_as_log_limit(payload))
    _append_status_progress(progress_log, status)
    return {
        "mode": "status",
        "output_directory": str(output_directory),
        "pagination": status.get("pagination"),
        "download_status": status,
        "summary": _download_status_summary(status),
        "progress_log": list(progress_log),
    }


def run_download_action(
    payload: dict[str, Any],
    progress_callback: Any | None = None,
    cancel_check: Any | None = None,
) -> dict[str, Any]:
    payload = apply_workspace_defaults("kind_download", payload)
    mode = str(payload.get("mode") or "single").strip().lower()
    if mode == "single":
        return _run_single(
            payload, progress_callback=progress_callback, cancel_check=cancel_check
        )
    if mode == "yearly":
        return _run_yearly(
            payload, progress_callback=progress_callback, cancel_check=cancel_check
        )
    if mode == "resume":
        return _run_resume(
            payload, progress_callback=progress_callback, cancel_check=cancel_check
        )
    raise ValueError("mode must be one of: single, yearly, resume")
