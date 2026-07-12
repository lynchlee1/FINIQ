"""KIND disclosure download execution helpers."""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from finiq.concurrency import bounded_as_completed
from finiq.data_scraper.core.client import download_pages
from finiq.data_scraper.core.constants import DEFAULT_REQUEST_HEADERS
from finiq.data_scraper.workflow import KindWorkflow, make_page_size_integrity_validator

from finiq.market_desk.web.features.downloads.kind_common import *

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
        f"workers={payload.get('worker_count') or 1}",
        f"parallel_strategy={payload.get('parallel_strategy') or 'years'}",
        f"log_limit={payload.get('log_limit') or 20}",
        f"resume_yearly={payload.get('resume_yearly', True)}",
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
    parallel_strategy = _as_parallel_strategy(payload)
    page_worker_count = (
        _as_worker_count(payload) if parallel_strategy == "pages" else 1
    )
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
        workflow.run(
            output_directory=output_directory,
            request_headers=DEFAULT_REQUEST_HEADERS,
            start_date=start_date_raw,
            end_date=end_date_raw,
            start_page=1,
            end_page=1,
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
            max_workers=1,
        )
        if cancel_check is not None and cancel_check():
            raise DownloadCancelled("download job cancelled")
        paging = _detect_pagination(output_directory)
        if paging and int(paging.get("total_pages") or 0) > 1:
            saved_input = _load_workflow_input(output_directory)
            if saved_input is None:
                raise ValueError("kind_workflow.input.json is missing")
            _append_progress(
                progress_log,
                f"SINGLE pagination_detected total_pages={int(paging['total_pages'])} total_items={int(paging.get('total_items') or 0)}",
                progress_callback,
            )
            download_pages(
                output_directory=output_directory,
                request_headers=saved_input["request_headers"],
                start_date=saved_input["start_date"],
                end_date=saved_input["end_date"],
                start_page=2,
                end_page=int(paging["total_pages"]),
                page_size=int(saved_input.get("page_size", page_size)),
                search_filters=saved_input.get("search_filters") or None,
                disclosure_type_groups=saved_input.get("disclosure_type_groups")
                or None,
                last_report_only=saved_input.get("last_report_only"),
                include_previous_disclosures=saved_input.get(
                    "include_previous_disclosures"
                ),
                wait_seconds_between_requests=wait_seconds,
                timeout=float(saved_input.get("timeout", timeout)),
                progress_callback=local_progress_callback,
                cancel_check=cancel_check,
                saved_file_validator=make_page_size_integrity_validator(
                    expected_page_size=int(saved_input.get("page_size", page_size)),
                ),
                max_workers=page_worker_count,
            )
            if cancel_check is not None and cancel_check():
                raise DownloadCancelled("download job cancelled")

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


def _run_yearly_chunk(payload: dict[str, Any]) -> dict[str, Any]:
    return _run_single(payload)


def _yearly_task_resume_payload(task: dict[str, Any]) -> dict[str, Any] | None:
    output_directory = (
        Path(str(task.get("output_directory") or "")).expanduser().resolve()
    )
    if not output_directory.is_dir():
        return None
    if _detect_pagination(output_directory) is None:
        return None
    if _load_workflow_input(output_directory) is None:
        return None
    return {
        **task,
        "mode": "resume",
        "start_date": "",
        "end_date": "",
    }


def _run_yearly_task(
    task: dict[str, Any],
    *,
    resume_yearly: bool,
    progress_callback: Any | None = None,
    cancel_check: Any | None = None,
) -> dict[str, Any]:
    if cancel_check is not None and cancel_check():
        raise DownloadCancelled("download job cancelled")
    resume_payload = _yearly_task_resume_payload(task) if resume_yearly else None
    if resume_payload is None:
        if resume_yearly:
            _append_progress(
                deque(maxlen=0),
                "resume_unavailable -> full_download",
                progress_callback,
            )
        return _run_single(
            task, progress_callback=progress_callback, cancel_check=cancel_check
        )
    _append_progress(
        deque(maxlen=0), "resume_available -> resume_download", progress_callback
    )
    return _run_resume(
        resume_payload, progress_callback=progress_callback, cancel_check=cancel_check
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
    resume_yearly = _as_resume_yearly(payload)
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
                    requested_worker_count if parallel_strategy == "pages" else 1
                ),
                "parallel_strategy": parallel_strategy,
                "resume_yearly": resume_yearly,
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
                resume_yearly=resume_yearly,
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
                    resume_yearly=resume_yearly,
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


def _run_resume(
    payload: dict[str, Any],
    progress_callback: Any | None = None,
    cancel_check: Any | None = None,
) -> dict[str, Any]:
    output_directory_raw = str(payload.get("output_directory") or "").strip()
    if not output_directory_raw:
        raise ValueError("output_directory is required")
    output_directory = Path(output_directory_raw).expanduser().resolve()
    if not output_directory.is_dir():
        raise ValueError(f"directory not found: {output_directory}")

    paging = _detect_pagination(output_directory)
    if paging is None:
        raise ValueError("pagination info not found in output directory")

    saved_input = _load_workflow_input(output_directory)
    if saved_input is None:
        raise ValueError("kind_workflow.input.json is missing")

    total_pages = int(paging["total_pages"])
    downloaded_pages = int(paging["downloaded_pages"])
    page_size = int(saved_input.get("page_size", 100))
    status_before = _download_integrity_status(output_directory, page_size)
    progress_log, local_progress_callback = _build_progress_collector(
        external_callback=progress_callback
    )
    _append_status_progress(progress_log, status_before, progress_callback)
    start_page = downloaded_pages + 1
    if start_page > total_pages:
        return {
            "mode": "resume",
            "output_directory": str(output_directory),
            "message": "all pages already downloaded",
            "pagination": paging,
            "download_status": status_before,
            "summary": _download_status_summary(status_before),
            "progress_log": list(progress_log),
        }

    wait_seconds = _as_float(
        payload,
        "wait_seconds",
        float(saved_input.get("wait_seconds_between_requests", 1.0)),
    )
    timeout = _as_float(payload, "timeout", float(saved_input.get("timeout", 20.0)))
    parallel_strategy = _as_parallel_strategy(payload)
    page_worker_count = (
        _as_worker_count(payload) if parallel_strategy == "pages" else 1
    )
    if wait_seconds < 0:
        raise ValueError("wait_seconds must be >= 0")
    if timeout <= 0:
        raise ValueError("timeout must be > 0")

    download_pages(
        output_directory=output_directory,
        request_headers=saved_input["request_headers"],
        start_date=saved_input["start_date"],
        end_date=saved_input["end_date"],
        start_page=start_page,
        end_page=total_pages,
        page_size=int(saved_input.get("page_size", 100)),
        search_filters=saved_input.get("search_filters") or None,
        disclosure_type_groups=saved_input.get("disclosure_type_groups") or None,
        last_report_only=saved_input.get("last_report_only"),
        include_previous_disclosures=saved_input.get("include_previous_disclosures"),
        wait_seconds_between_requests=wait_seconds,
        timeout=timeout,
        progress_callback=local_progress_callback,
        cancel_check=cancel_check,
        saved_file_validator=make_page_size_integrity_validator(
            expected_page_size=page_size,
        ),
        max_workers=page_worker_count,
    )
    if cancel_check is not None and cancel_check():
        raise DownloadCancelled("download job cancelled")
    status_after = _download_integrity_status(output_directory, page_size)
    _append_status_progress(progress_log, status_after, progress_callback)
    return {
        "mode": "resume",
        "output_directory": str(output_directory),
        "pagination": status_after.get("pagination"),
        "download_status": status_after,
        "summary": _download_status_summary(status_after),
        "progress_log": list(progress_log),
    }
