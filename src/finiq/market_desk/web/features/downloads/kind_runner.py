"""KIND disclosure download execution helpers."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from finiq.concurrency import available_cpu_count, bounded_as_completed
from finiq.data_scraper.core.client import (
    SEARCH_RESULTS_FILENAME_TEMPLATE,
    download_pages,
)
from finiq.data_scraper.core.constants import DEFAULT_REQUEST_HEADERS
from finiq.data_scraper.parse import disclosure_rows, pagination_info
from finiq.data_scraper.workflow import (
    KindWorkflow,
    KindWorkflowCheckpoint,
    inspect_download_directory_pages,
    make_page_size_integrity_validator,
    validate_kind_workflow_input_snapshot,
)

from finiq.market_desk.web.features.downloads.kind_common import *


_DOWNLOAD_STAGING_SUFFIX = ".kind-download-staging"


def _download_staging_directory(output_directory: Path) -> Path:
    return output_directory.with_name(
        f".{output_directory.name}{_DOWNLOAD_STAGING_SUFFIX}"
    )


def _read_download_checkpoint(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"KIND download checkpoint is unreadable: {path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("input"), dict):
        raise ValueError(f"KIND download checkpoint is invalid: {path}")
    validate_kind_workflow_input_snapshot(payload["input"])
    return payload


def _validate_staged_download_input(
    checkpoint: dict[str, Any],
    *,
    payload: dict[str, Any],
    start_date: str,
    end_date: str,
    page_size: int,
    wait_seconds: float,
    timeout: float,
) -> None:
    saved_input = checkpoint["input"]
    saved_filters = _snapshot_filters_payload(saved_input)
    requested_filters = _current_filters_payload(payload)
    requested_filters["last_report_only"] = bool(
        requested_filters.get("last_report_only")
    )
    matches = (
        saved_input.get("request_headers") == DEFAULT_REQUEST_HEADERS
        and saved_input.get("start_date") == start_date
        and saved_input.get("end_date") == end_date
        and saved_input.get("page_size") == page_size
        and saved_input.get("include_previous_disclosures") is None
        and saved_input.get("wait_seconds_between_requests") == wait_seconds
        and saved_input.get("timeout") == timeout
        and saved_filters == requested_filters
    )
    if not matches:
        raise ValueError(
            "중단된 KIND 임시 다운로드의 입력이 현재 요청과 다릅니다. "
            "기존 임시 다운로드를 정리한 뒤 다시 실행하세요."
        )


def _configure_full_download_workflow(
    *,
    output_directory: Path,
    start_date: str,
    end_date: str,
    end_page: int,
    page_size: int,
    search_filters: dict[str, str] | None,
    disclosure_type_groups: dict[str, list[str]] | None,
    last_report_only: bool | None,
    wait_seconds: float,
    timeout: float,
) -> KindWorkflow:
    workflow = KindWorkflow()
    workflow.configure(
        output_directory=output_directory,
        request_headers=DEFAULT_REQUEST_HEADERS,
        start_date=start_date,
        end_date=end_date,
        start_page=1,
        end_page=end_page,
        page_size=page_size,
        search_filters=search_filters,
        disclosure_type_groups=disclosure_type_groups,
        last_report_only=last_report_only,
        include_previous_disclosures=None,
        wait_seconds_between_requests=wait_seconds,
        timeout=timeout,
        parse_mode="simpletable",
    )
    return workflow


def _verify_first_page_consistency(
    first_page: Path,
    verification_page: Path,
) -> None:
    first_bytes = first_page.read_bytes()
    verification_bytes = verification_page.read_bytes()
    first_pagination = pagination_info(first_bytes)
    verification_pagination = pagination_info(verification_bytes)
    first_rows = disclosure_rows(first_bytes)
    verification_rows = disclosure_rows(verification_bytes)
    if (
        first_pagination != verification_pagination
        or first_rows != verification_rows
    ):
        raise ValueError(
            "KIND 목록이 다운로드 중 변경되었습니다. 처음과 마지막 1페이지의 "
            "페이지네이션 또는 공시 행이 다르므로 새 결과를 게시하지 않습니다."
        )


def _publish_staged_download(
    staging_directory: Path,
    output_directory: Path,
) -> None:
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    if staging_directory.is_symlink():
        raise ValueError(
            "KIND download staging directory must not be a symlink: "
            f"{staging_directory}"
        )
    if output_directory.exists() and (
        output_directory.is_symlink() or not output_directory.is_dir()
    ):
        raise ValueError(
            f"KIND output directory must be a regular directory: {output_directory}"
        )

    backup_directory = output_directory.with_name(
        f".{output_directory.name}.kind-download-backup-{uuid.uuid4().hex}"
    )
    previous_moved = False
    try:
        if output_directory.exists():
            os.replace(output_directory, backup_directory)
            previous_moved = True
        os.replace(staging_directory, output_directory)
    except Exception:
        if previous_moved and not output_directory.exists():
            os.replace(backup_directory, output_directory)
        raise
    if previous_moved:
        shutil.rmtree(backup_directory)


def _run_auto_download_staged(
    *,
    output_directory: Path,
    payload: dict[str, Any],
    start_date: str,
    end_date: str,
    page_size: int,
    wait_seconds: float,
    timeout: float,
    search_filters: dict[str, str] | None,
    disclosure_type_groups: dict[str, list[str]] | None,
    last_report_only: bool | None,
    page_worker_count: int,
    progress_callback: Any | None,
    cancel_check: Any | None,
) -> None:
    staging_directory = _download_staging_directory(output_directory)
    checkpoint_path = staging_directory / "kind_workflow.checkpoint.json"
    staging_directory.parent.mkdir(parents=True, exist_ok=True)
    if staging_directory.exists() and (
        staging_directory.is_symlink() or not staging_directory.is_dir()
    ):
        raise ValueError(
            f"KIND download staging path must be a regular directory: {staging_directory}"
        )
    staging_directory.mkdir(exist_ok=True)

    page_paths = sorted_result_page_paths(staging_directory)
    if page_paths:
        if not checkpoint_path.is_file():
            raise ValueError(
                f"KIND download checkpoint is missing for staged pages: {staging_directory}"
            )
        checkpoint_payload = _read_download_checkpoint(checkpoint_path)
        _validate_staged_download_input(
            checkpoint_payload,
            payload=payload,
            start_date=start_date,
            end_date=end_date,
            page_size=page_size,
            wait_seconds=wait_seconds,
            timeout=timeout,
        )
        inspected = inspect_download_directory_pages(
            staging_directory,
            expected_page_size=page_size,
            require_complete=False,
        )
        downloaded_pages = int(inspected["downloaded_pages"])
        checkpoint_pages = sorted(
            Path(name).name
            for name in checkpoint_payload.get("saved_files") or []
            if "_post_page_" in Path(name).name
        )
        actual_pages = [path.name for path in page_paths]
        if (
            checkpoint_payload.get("last_saved_page") != downloaded_pages
            or checkpoint_pages != actual_pages
        ):
            raise ValueError(
                "중단된 KIND 임시 다운로드의 checkpoint와 저장 페이지가 다릅니다."
            )
        total_pages = int(inspected["total_pages"])
    else:
        probe = _configure_full_download_workflow(
            output_directory=staging_directory,
            start_date=start_date,
            end_date=end_date,
            end_page=1,
            page_size=page_size,
            search_filters=search_filters,
            disclosure_type_groups=disclosure_type_groups,
            last_report_only=last_report_only,
            wait_seconds=wait_seconds,
            timeout=timeout,
        )
        probe.save_search_results(
            progress_callback=progress_callback,
            cancel_check=cancel_check,
            max_workers=1,
        )
        if cancel_check is not None and cancel_check():
            raise DownloadCancelled("download job cancelled")
        pagination = _detect_pagination(staging_directory)
        if pagination is None:
            raise ValueError("KIND pagination not found after first page download")
        page_paths = sorted_result_page_paths(staging_directory)
        downloaded_pages = 1
        total_pages = int(pagination["total_pages"])

    full_workflow = _configure_full_download_workflow(
        output_directory=staging_directory,
        start_date=start_date,
        end_date=end_date,
        end_page=total_pages,
        page_size=page_size,
        search_filters=search_filters,
        disclosure_type_groups=disclosure_type_groups,
        last_report_only=last_report_only,
        wait_seconds=wait_seconds,
        timeout=timeout,
    )
    full_input = full_workflow.get_input()
    full_workflow.checkpoint = KindWorkflowCheckpoint(
        input=full_input.to_dict(),
        saved_files=[
            path.relative_to(staging_directory).as_posix()
            for path in sorted(staging_directory.glob("*.body"))
        ],
        last_saved_file=page_paths[-1].name if page_paths else None,
        last_saved_page=downloaded_pages,
        last_request_data=list(
            full_workflow.build_request_data(page_number=downloaded_pages)
        ),
        completed=False,
    )
    full_workflow.save_checkpoint(checkpoint_path)

    if downloaded_pages < total_pages:
        update_checkpoint = full_workflow._make_saved_file_callback(
            checkpoint_path,
            None,
        )

        def update_result_page_checkpoint(
            path: Path,
            page_number: int | None,
            request_data: Any,
        ) -> None:
            if page_number is not None:
                update_checkpoint(path, page_number, request_data)

        download_pages(
            output_directory=staging_directory,
            request_headers=full_input.request_headers,
            start_date=full_input.start_date,
            end_date=full_input.end_date,
            start_page=downloaded_pages + 1,
            end_page=total_pages,
            page_size=full_input.page_size,
            search_filters=full_input.search_filters,
            disclosure_type_groups=full_input.disclosure_type_groups,
            last_report_only=full_input.last_report_only,
            include_previous_disclosures=full_input.include_previous_disclosures,
            wait_seconds_between_requests=wait_seconds,
            timeout=timeout,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
            saved_file_validator=make_page_size_integrity_validator(
                expected_page_size=page_size,
            ),
            saved_file_callback=update_result_page_checkpoint,
            max_workers=page_worker_count,
        )
        if cancel_check is not None and cancel_check():
            raise DownloadCancelled("download job cancelled")

    inspect_download_directory_pages(
        staging_directory,
        expected_page_size=page_size,
        require_complete=True,
    )
    with tempfile.TemporaryDirectory(
        dir=staging_directory.parent,
        prefix=f".{output_directory.name}.kind-first-page-check-",
    ) as verification_raw:
        verification_directory = Path(verification_raw)
        download_pages(
            output_directory=verification_directory,
            request_headers=full_input.request_headers,
            start_date=full_input.start_date,
            end_date=full_input.end_date,
            start_page=1,
            end_page=1,
            page_size=full_input.page_size,
            search_filters=full_input.search_filters,
            disclosure_type_groups=full_input.disclosure_type_groups,
            last_report_only=full_input.last_report_only,
            include_previous_disclosures=full_input.include_previous_disclosures,
            wait_seconds_between_requests=wait_seconds,
            timeout=timeout,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
            saved_file_validator=make_page_size_integrity_validator(
                expected_page_size=page_size,
            ),
            max_workers=1,
        )
        if cancel_check is not None and cancel_check():
            raise DownloadCancelled("download job cancelled")
        _verify_first_page_consistency(
            staging_directory / SEARCH_RESULTS_FILENAME_TEMPLATE.format(page_number=1),
            verification_directory
            / SEARCH_RESULTS_FILENAME_TEMPLATE.format(page_number=1),
        )

    full_workflow.save_input_snapshot(
        staging_directory / "kind_workflow.input.json"
    )
    checkpoint = full_workflow.get_checkpoint()
    checkpoint.completed = True
    checkpoint.last_saved_page = total_pages
    checkpoint.last_saved_file = SEARCH_RESULTS_FILENAME_TEMPLATE.format(
        page_number=total_pages
    )
    checkpoint.last_request_data = list(
        full_workflow.build_request_data(page_number=total_pages)
    )
    full_workflow.save_checkpoint(checkpoint_path)
    _publish_staged_download(staging_directory, output_directory)


def _append_progress(
    progress_log: MutableSequence[str] | deque[str],
    message: str,
    progress_callback: Any | None = None,
) -> None:
    if getattr(progress_log, "maxlen", None) != 0:
        progress_log.append(message)
    if progress_callback is not None:
        progress_callback(message)


def _download_payload_summary(payload: dict[str, Any]) -> list[str]:
    mode = str(payload.get("mode") or "single").strip().lower()
    return [
        f"mode={mode}",
        f"output={str(payload.get('output_directory') or '').strip()}",
        f"range={str(payload.get('start_date') or '').strip()}~{str(payload.get('end_date') or '').strip()}",
        f"pages={payload.get('start_page') or 1}~{payload.get('end_page') or 'auto'}",
        f"page_size={payload.get('page_size') or 100}",
        f"wait={payload.get('wait_seconds') or 1}s",
        f"timeout={payload.get('timeout') or 20}s",
        f"workers={payload.get('worker_count') or available_cpu_count()}",
        f"parallel_strategy={payload.get('parallel_strategy') or 'years'}",
        f"log_limit={payload.get('log_limit') or 20}",
    ]


def _append_status_progress(
    progress_log: MutableSequence[str] | deque[str],
    status: dict[str, Any],
    progress_callback: Any | None = None,
) -> None:
    pagination = status.get("pagination") or {}
    downloaded = (
        status.get("downloaded_pages") or pagination.get("downloaded_pages") or 0
    )
    total = status.get("total_pages") or pagination.get("total_pages") or 0
    total_items = status.get("total_items") or pagination.get("total_items") or 0
    _append_progress(
        progress_log,
        f"STATUS output={status.get('output_directory')} downloaded={downloaded}/{total} total_items={total_items}",
        progress_callback,
    )
    latest_file = pagination.get("latest_file")
    if latest_file:
        _append_progress(
            progress_log, f"STATUS latest_file={latest_file}", progress_callback
        )
    missing_pages = status.get("missing_pages") or []
    if missing_pages:
        preview = ",".join(str(page) for page in missing_pages[:20])
        suffix = f"...(+{len(missing_pages) - 20})" if len(missing_pages) > 20 else ""
        _append_progress(
            progress_log, f"STATUS missing_pages={preview}{suffix}", progress_callback
        )
    if int(downloaded or 0) == 0:
        _append_progress(
            progress_log, "STATUS no_saved_result_pages=true", progress_callback
        )
        return
    if status.get("integrity_valid"):
        _append_progress(
            progress_log,
            "INTEGRITY ok page_numbers=true row_counts=true",
            progress_callback,
        )
    else:
        _append_progress(
            progress_log,
            "INTEGRITY failed " + " / ".join(status.get("errors") or ["unknown"]),
            progress_callback,
        )


def _download_status_summary(status: dict[str, Any]) -> dict[str, int]:
    pagination = status.get("pagination") or {}
    downloaded = int(
        status.get("downloaded_pages") or pagination.get("downloaded_pages") or 0
    )
    total = int(
        status.get("total_pages") or pagination.get("total_pages") or downloaded
    )
    return {
        "success": downloaded,
        "failed": max(total - downloaded, 0),
        "total": total,
    }


def _aggregate_download_summary(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"success": 0, "failed": 0, "total": 0}
    for result in results:
        item = _download_status_summary(dict(result.get("download_status") or {}))
        summary["success"] += item["success"]
        summary["failed"] += item["failed"]
        summary["total"] += item["total"]
    return summary


def _run_single(
    payload: dict[str, Any],
    progress_callback: Any | None = None,
    cancel_check: Any | None = None,
) -> dict[str, Any]:
    output_directory_raw = str(payload.get("output_directory") or "").strip()
    if not output_directory_raw:
        raise ValueError("output_directory is required")
    output_directory = Path(output_directory_raw).expanduser().resolve()

    start_date_raw = str(payload.get("start_date") or "").strip()
    end_date_raw = str(payload.get("end_date") or "").strip()
    if not start_date_raw or not end_date_raw:
        raise ValueError("start_date and end_date are required")
    _parse_iso_date(start_date_raw, "start_date")
    _parse_iso_date(end_date_raw, "end_date")

    start_page = _as_int(payload, "start_page", 1)
    end_page = payload.get("end_page")
    end_page_value = (
        _as_int(payload, "end_page", start_page) if end_page not in ("", None) else None
    )
    page_size = _as_int(payload, "page_size", 100)
    wait_seconds = _as_float(payload, "wait_seconds", 1.0)
    timeout = _as_float(payload, "timeout", 20.0)
    _as_parallel_strategy(payload)
    page_worker_count = _as_worker_count(payload)
    if wait_seconds < 0:
        raise ValueError("wait_seconds must be >= 0")
    if timeout <= 0:
        raise ValueError("timeout must be > 0")

    workflow = KindWorkflow()
    progress_log, local_progress_callback = _build_progress_collector(
        external_callback=progress_callback
    )
    for line in _download_payload_summary(payload):
        _append_progress(progress_log, f"SINGLE {line}", progress_callback)
    search_filters = _build_search_filters(payload)
    disclosure_type_groups = _normalize_disclosure_type_groups(payload)
    last_report_only = _as_bool(payload, "last_report_only")
    _append_progress(
        progress_log, f"SINGLE search_filters={search_filters or {}}", progress_callback
    )
    _append_progress(
        progress_log,
        f"SINGLE disclosure_group_count={len(disclosure_type_groups or {})}",
        progress_callback,
    )

    if end_page_value is not None:
        _append_progress(
            progress_log,
            f"SINGLE fixed_page_download start_page={start_page} end_page={end_page_value}",
            progress_callback,
        )
        workflow.run(
            output_directory=output_directory,
            request_headers=DEFAULT_REQUEST_HEADERS,
            start_date=start_date_raw,
            end_date=end_date_raw,
            start_page=start_page,
            end_page=end_page_value,
            page_size=page_size,
            search_filters=search_filters,
            disclosure_type_groups=disclosure_type_groups,
            last_report_only=last_report_only,
            include_previous_disclosures=None,
            wait_seconds_between_requests=wait_seconds,
            timeout=timeout,
            parse_mode="simpletable",
            save=True,
            progress_callback=local_progress_callback,
            cancel_check=cancel_check,
            max_workers=page_worker_count,
        )
        if cancel_check is not None and cancel_check():
            raise DownloadCancelled("download job cancelled")
    else:
        _append_progress(
            progress_log,
            "SINGLE auto_page_download first_page_probe=1",
            progress_callback,
        )
        _run_auto_download_staged(
            output_directory=output_directory,
            payload=payload,
            start_date=start_date_raw,
            end_date=end_date_raw,
            page_size=page_size,
            search_filters=search_filters,
            disclosure_type_groups=disclosure_type_groups,
            last_report_only=last_report_only,
            wait_seconds=wait_seconds,
            timeout=timeout,
            progress_callback=local_progress_callback,
            cancel_check=cancel_check,
            page_worker_count=page_worker_count,
        )

    status = _download_integrity_status(output_directory, page_size)
    _append_status_progress(progress_log, status, progress_callback)
    return {
        "mode": "single",
        "output_directory": str(output_directory),
        "pagination": status.get("pagination"),
        "download_status": status,
        "summary": _download_status_summary(status),
        "progress_log": list(progress_log),
    }


def _run_yearly_task(
    task: dict[str, Any],
    *,
    progress_callback: Any | None = None,
    cancel_check: Any | None = None,
) -> dict[str, Any]:
    if cancel_check is not None and cancel_check():
        raise DownloadCancelled("download job cancelled")
    return _run_single(
        task, progress_callback=progress_callback, cancel_check=cancel_check
    )


def _run_yearly(
    payload: dict[str, Any],
    progress_callback: Any | None = None,
    cancel_check: Any | None = None,
) -> dict[str, Any]:
    output_directory_raw = str(payload.get("output_directory") or "").strip()
    if not output_directory_raw:
        raise ValueError("output_directory is required")

    start_date_raw = str(payload.get("start_date") or "").strip()
    end_date_raw = str(payload.get("end_date") or "").strip()
    if not start_date_raw or not end_date_raw:
        raise ValueError("start_date and end_date are required")

    start_date = _parse_iso_date(start_date_raw, "start_date")
    end_date = _parse_iso_date(end_date_raw, "end_date")
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")

    base_output = Path(output_directory_raw).expanduser().resolve()
    page_size = _as_int(payload, "page_size", 100)
    wait_seconds = _as_float(payload, "wait_seconds", 1.0)
    timeout = _as_float(payload, "timeout", 20.0)
    if wait_seconds < 0:
        raise ValueError("wait_seconds must be >= 0")
    if timeout <= 0:
        raise ValueError("timeout must be > 0")

    search_filters = _build_search_filters(payload)
    disclosure_type_groups = _normalize_disclosure_type_groups(payload)
    last_report_only = _as_bool(payload, "last_report_only")
    parallel_strategy = _as_parallel_strategy(payload)
    yearly_ranges = _split_yearly_ranges(start_date, end_date)
    requested_worker_count = _as_worker_count(payload)
    worker_count = (
        min(requested_worker_count, max(1, len(yearly_ranges)))
        if parallel_strategy == "years"
        else 1
    )
    progress_log: deque[str] = deque(maxlen=0)
    for line in _download_payload_summary(payload):
        _append_progress(progress_log, f"YEARLY {line}", progress_callback)
    _append_progress(
        progress_log,
        f"YEARLY chunks={len(yearly_ranges)} workers={worker_count}",
        progress_callback,
    )
    tasks: list[dict[str, Any]] = []

    for chunk_start, chunk_end in yearly_ranges:
        folder_name = f"{chunk_start.strftime('%Y%m%d')}_{chunk_end.strftime('%Y%m%d')}"
        chunk_output = base_output / folder_name
        tasks.append(
            {
                "output_directory": str(chunk_output),
                "start_date": chunk_start.isoformat(),
                "end_date": chunk_end.isoformat(),
                "start_page": 1,
                "end_page": None,
                "page_size": page_size,
                "wait_seconds": wait_seconds,
                "timeout": timeout,
                "company_name": (search_filters or {}).get("searchCorpName", ""),
                "submitter_name": (search_filters or {}).get("submitOblgNm", ""),
                "market_label": str(payload.get("market_label") or ""),
                "securities_label": str(payload.get("securities_label") or ""),
                "disclosure_type_groups": disclosure_type_groups or {},
                "last_report_only": last_report_only,
                "worker_count": (
                    requested_worker_count
                    if parallel_strategy == "pages" or len(yearly_ranges) == 1
                    else 1
                ),
                "parallel_strategy": parallel_strategy,
                "log_limit": payload.get("log_limit") or 20,
                "_folder_name": folder_name,
            }
        )

    chunk_results_by_folder: dict[str, dict[str, Any]] = {}
    if worker_count == 1:
        for task in tasks:
            if cancel_check is not None and cancel_check():
                raise DownloadCancelled("download job cancelled")
            folder_name = str(task["_folder_name"])
            _append_progress(
                progress_log,
                f"[{folder_name}] worker_start thread=main",
                progress_callback,
            )
            chunk_results_by_folder[folder_name] = _run_yearly_task(
                task,
                progress_callback=lambda line, folder=folder_name: _append_progress(
                    progress_log,
                    f"[{folder}] {line}",
                    progress_callback,
                ),
                cancel_check=cancel_check,
            )
            _append_progress(
                progress_log, f"[{folder_name}] worker_done", progress_callback
            )
    else:
        executor = ThreadPoolExecutor(
            max_workers=worker_count, thread_name_prefix="kind-download"
        )
        try:
            def submit_task(indexed_task: tuple[int, dict[str, Any]]):
                worker_index, task = indexed_task
                folder_name = str(task["_folder_name"])
                _append_progress(
                    progress_log,
                    f"[{folder_name}] worker_submit index={worker_index}/{len(tasks)}",
                    progress_callback,
                )
                return executor.submit(
                    _run_yearly_task,
                    task,
                    progress_callback=lambda line, folder=folder_name: _append_progress(
                        progress_log,
                        f"[{folder}] {line}",
                        progress_callback,
                    ),
                    cancel_check=cancel_check,
                )

            indexed_tasks = (
                (worker_index, task)
                for worker_index, task in enumerate(tasks, start=1)
                if cancel_check is None or not cancel_check()
            )
            for future, (_worker_index, task) in bounded_as_completed(
                executor,
                indexed_tasks,
                submit_task,
                max_pending=worker_count * 2,
            ):
                folder_name = str(task["_folder_name"])
                try:
                    chunk_results_by_folder[folder_name] = future.result()
                    _append_progress(
                        progress_log, f"[{folder_name}] worker_done", progress_callback
                    )
                except DownloadCancelled:
                    raise
                except Exception as exc:
                    _append_progress(
                        progress_log,
                        f"[{folder_name}] worker_failed error={exc}",
                        progress_callback,
                    )
                    raise ValueError(f"{folder_name} download failed: {exc}") from exc
        except BaseException:
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True)

    if cancel_check is not None and cancel_check():
        raise DownloadCancelled("download job cancelled")

    results: list[dict[str, Any]] = []
    for task in tasks:
        folder_name = str(task["_folder_name"])
        result = chunk_results_by_folder[folder_name]
        results.append(
            {
                "folder": folder_name,
                "output_directory": result.get("output_directory"),
                "pagination": result.get("pagination"),
                "download_status": result.get("download_status"),
            }
        )

    return {
        "mode": "yearly",
        "base_output_directory": str(base_output),
        "ranges": len(yearly_ranges),
        "worker_count": worker_count,
        "parallel_strategy": parallel_strategy,
        "results": results,
        "summary": _aggregate_download_summary(results),
        "progress_log": list(progress_log),
    }
