"""Existing KIND download discovery and metadata helpers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from finiq.concurrency import bounded_as_completed, resolve_worker_count
from finiq.data_scraper.core.constants import DEFAULT_REQUEST_HEADERS, DISCLOSURE_GROUPS, MARKET_TYPES, SECURITIES_TYPES
from finiq.data_scraper.workflow import inspect_download_directory_pages

from finiq.market_desk.web.features.downloads.kind_common import *

def get_current_kind_total_count(input_snapshot: dict[str, Any]) -> int | None:
    """Make a live query to KIND to fetch the current total count for the given filters."""
    try:
        import requests

        from finiq.data_scraper.core.client import KIND_SEARCH_RESULTS_URL
        from finiq.data_scraper.core.payload import build_search_form
        from finiq.data_scraper.parse import pagination_info

        request_headers = (
            input_snapshot.get("request_headers") or DEFAULT_REQUEST_HEADERS
        )

        request_data = build_search_form(
            page_number=1,
            start_date=input_snapshot.get("start_date") or "",
            end_date=input_snapshot.get("end_date") or "",
            page_size=input_snapshot.get("page_size") or 100,
            search_filters=input_snapshot.get("search_filters"),
            disclosure_type_groups=input_snapshot.get("disclosure_type_groups"),
            last_report_only=input_snapshot.get("last_report_only"),
            include_previous_disclosures=input_snapshot.get(
                "include_previous_disclosures"
            ),
        )

        response = requests.post(
            KIND_SEARCH_RESULTS_URL,
            headers=request_headers,
            data=request_data,
            timeout=5.0,
        )
        response.raise_for_status()

        info = pagination_info(response.content)
        if info and "total_items" in info:
            return int(info["total_items"])
    except Exception:
        pass
    return None


def _expected_rows_for_page(
    *,
    total_items: int,
    current_page: int,
    total_pages: int,
    page_size: int,
) -> int:
    if current_page < 1 or total_pages < 1 or current_page > total_pages:
        raise ValueError(
            f"Invalid pagination: current_page={current_page}, total_pages={total_pages}"
        )
    if current_page < total_pages:
        return page_size
    expected_rows = total_items - (page_size * (total_pages - 1))
    if expected_rows < 0 or expected_rows > page_size:
        raise ValueError(
            f"Inconsistent total items {total_items} for total pages {total_pages} and page size {page_size}"
        )
    return expected_rows


def _validate_single_folder(
    folder: Path,
    folder_name: str,
    _date_range: tuple[date, date],
    *,
    verify_with_kind: bool = True,
) -> dict[str, Any] | None:
    body_files = list(folder.glob("*_post_page_*.body"))
    if not body_files:
        return None

    input_snapshot = _require_current_download_input_snapshot(folder)
    start_date = date.fromisoformat(str(input_snapshot["start_date"]))
    end_date = date.fromisoformat(str(input_snapshot["end_date"]))

    status = "validated"
    error_detail = None
    kind_count = None
    local_count = None

    expected_page_size = int(input_snapshot["page_size"])

    if verify_with_kind:
        kind_count = get_current_kind_total_count(input_snapshot)
        if kind_count is None:
            return {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "folder_name": folder_name,
                "local_count": None,
                "kind_count": None,
                "status": "stale",
                "error_detail": "Failed to fetch current count from KIND (network error or timeout).",
                "metadata_missing": False,
                "metadata_obsolete": False,
                "folder_path": str(folder),
            }

    try:
        if not verify_with_kind:
            # 1. Check page number continuity using filenames.
            page_nums = []
            import re

            page_num_re = re.compile(r"_post_page_(\d+)\.body$")
            for f in body_files:
                m = page_num_re.search(f.name)
                if not m:
                    raise ValueError(f"Invalid filename format: {f.name}")
                page_nums.append(int(m.group(1)))

            sorted_page_nums = sorted(page_nums)
            expected_page_nums = list(range(1, len(body_files) + 1))
            if sorted_page_nums != expected_page_nums:
                raise ValueError(
                    f"Page numbers are not contiguous: {sorted_page_nums}"
                )

            # 2. Extract total items and total pages by parsing the last page.
            paging = _detect_pagination(folder)
            if paging is None:
                raise ValueError(
                    "Failed to parse pagination metadata from the last page"
                )

            local_count = paging.get("total_items")
            total_pages = paging.get("total_pages")
            downloaded_pages = len(body_files)

            if downloaded_pages != total_pages:
                raise ValueError(
                    f"Page completeness check failed: downloaded pages ({downloaded_pages}) "
                    f"does not match total pages ({total_pages})"
                )
        else:
            inspected = inspect_download_directory_pages(
                folder,
                expected_page_size=expected_page_size,
                require_complete=True,
            )
            local_count = inspected.get("total_items")
    except Exception as exc:
        status = "stale"
        if verify_with_kind:
            error_detail = f"Failed to parse local download files (local count is null), while KIND current count is {kind_count}. Page completeness check failed: {exc}"
        else:
            error_detail = f"Page completeness check failed: {exc}"

    if status != "stale":
        if verify_with_kind:
            if local_count is None:
                status = "stale"
                error_detail = f"Failed to parse local download files (local count is null), while KIND current count is {kind_count}."
            elif local_count != kind_count:
                status = "stale"
                error_detail = f"KIND current count ({kind_count}) differs from local count ({local_count})."
        else:
            status = "unverified"
            error_detail = "KIND verification skipped (fast check mode)."

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "folder_name": folder_name,
        "local_count": local_count,
        "kind_count": kind_count,
        "status": status,
        "error_detail": error_detail,
        "metadata_missing": False,
        "metadata_obsolete": False,
        "folder_path": str(folder),
    }


def check_existing_downloads(
    output_directory_raw: str,
    *,
    verify_with_kind: bool = True,
    current_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inspect output directory to detect and validate existing downloaded date ranges."""
    if not output_directory_raw:
        return {"has_existing": False}
    try:
        output_directory = Path(output_directory_raw).expanduser().resolve()
    except Exception as exc:
        raise ValueError(f"Invalid output directory: {exc}") from exc

    if not output_directory.is_dir():
        return {"has_existing": False}

    def stale_range(
        folder: Path,
        folder_name: str,
        error_detail: str,
        date_range: tuple[date, date] | None = None,
        *,
        metadata_missing: bool = False,
        metadata_obsolete: bool = False,
    ) -> dict[str, Any]:
        return {
            "start_date": date_range[0].isoformat() if date_range else None,
            "end_date": date_range[1].isoformat() if date_range else None,
            "folder_name": folder_name,
            "local_count": None,
            "kind_count": None,
            "status": "stale",
            "error_detail": error_detail,
            "metadata_missing": metadata_missing,
            "metadata_obsolete": metadata_obsolete,
            "folder_path": str(folder),
        }

    candidates = []
    discovery_errors: list[dict[str, Any]] = []

    # Check for yearly subfolders (YYYYMMDD_YYYYMMDD)
    try:
        for child in output_directory.iterdir():
            if child.is_dir():
                parts = child.name.split("_")
                if (
                    len(parts) == 2
                    and len(parts[0]) == 8
                    and len(parts[1]) == 8
                    and parts[0].isdigit()
                    and parts[1].isdigit()
                ):
                    try:
                        folder_start = date(
                            int(child.name[0:4]),
                            int(child.name[4:6]),
                            int(child.name[6:8]),
                        )
                        folder_end = date(
                            int(child.name[9:13]),
                            int(child.name[13:15]),
                            int(child.name[15:17]),
                        )
                        candidates.append(
                            (child, child.name, (folder_start, folder_end))
                        )
                    except Exception as exc:
                        discovery_errors.append(
                            stale_range(
                                child,
                                child.name,
                                f"Invalid download folder date range: {exc}",
                            )
                        )
    except Exception as exc:
        raise RuntimeError(f"Failed to inspect output directory: {exc}") from exc

    if candidates:
        candidates = [
            candidate
            for candidate in candidates
            if list(candidate[0].glob("*_post_page_*.body"))
        ]
        for folder, _folder_name, _folder_range in candidates:
            _require_current_download_input_snapshot(folder)

    # If no yearly subfolders, check the directory itself (Single mode)
    if not candidates:
        try:
            if list(output_directory.glob("*_post_page_*.body")):
                input_snapshot = _require_current_download_input_snapshot(
                    output_directory
                )
                start_date = date.fromisoformat(str(input_snapshot["start_date"]))
                end_date = date.fromisoformat(str(input_snapshot["end_date"]))
                candidates.append(
                    (
                        output_directory,
                        output_directory.name,
                        (start_date, end_date),
                    )
                )
        except DownloadInputMetadataError:
            raise
        except Exception as exc:
            discovery_errors.append(
                stale_range(
                    output_directory,
                    output_directory.name,
                    f"Failed to inspect existing download files: {exc}",
                )
            )

    if not candidates and not discovery_errors:
        return {"has_existing": False}

    ranges_data = list(discovery_errors)
    # Run validation checks concurrently in a ThreadPool
    worker_count = resolve_worker_count(item_count=len(candidates))
    if candidates:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            completed = bounded_as_completed(
                executor,
                candidates,
                lambda item: executor.submit(
                    _validate_single_folder,
                    item[0],
                    item[1],
                    item[2],
                    verify_with_kind=verify_with_kind,
                ),
                max_pending=worker_count * 2,
            )
            for future, _candidate in completed:
                try:
                    res = future.result()
                    if res is not None:
                        ranges_data.append(res)
                except DownloadInputMetadataError:
                    raise
                except Exception as exc:
                    folder, folder_name, (folder_start, folder_end) = _candidate
                    ranges_data.append(
                        stale_range(
                            folder,
                            folder_name,
                            f"Download validation failed: {exc}",
                            (folder_start, folder_end),
                        )
                    )

    if not ranges_data:
        return {"has_existing": False}

    sorted_ranges = sorted(ranges_data, key=lambda x: str(x.get("start_date") or ""))
    starts = [r["start_date"] for r in ranges_data if r.get("start_date")]
    ends = [r["end_date"] for r in ranges_data if r.get("end_date")]
    earliest_date = min(starts) if starts else None
    latest_date = max(ends) if ends else None

    saved_filters = None
    for folder, _, _ in candidates:
        input_snapshot = _require_current_download_input_snapshot(folder)
        try:
            search_filters_dict = dict(input_snapshot.get("search_filters") or [])

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

            saved_filters = {
                "company_name": search_filters_dict.get("searchCorpName", ""),
                "submitter_name": search_filters_dict.get("submitOblgNm", ""),
                "market_label": market_label,
                "securities_label": securities_label,
                "disclosure_type_groups": input_snapshot.get(
                    "disclosure_type_groups"
                )
                or {},
                "last_report_only": bool(input_snapshot.get("last_report_only")),
            }
            break
        except Exception:
            pass

    return {
        "has_existing": True,
        "earliest_date": earliest_date,
        "latest_date": latest_date,
        "ranges": sorted_ranges,
        "saved_filters": saved_filters,
    }


def detect_existing_downloads(
    output_directory_raw: str,
    *,
    current_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Detect existing download folders and metadata state without parsing downloaded pages."""
    if not output_directory_raw:
        return {"has_existing": False}
    try:
        output_directory = Path(output_directory_raw).expanduser().resolve()
    except Exception:
        return {"has_existing": False}

    if not output_directory.is_dir():
        return {"has_existing": False}

    candidates: list[tuple[Path, str, tuple[date, date] | None]] = []
    try:
        for child in output_directory.iterdir():
            if not child.is_dir():
                continue
            folder_range = _folder_date_range_from_name(child)
            if folder_range is not None and list(
                child.glob("*_post_page_*.body")
            ):
                candidates.append((child, child.name, folder_range))
    except Exception:
        pass

    if not candidates:
        try:
            if list(output_directory.glob("*_post_page_*.body")):
                input_snapshot = _require_current_download_input_snapshot(
                    output_directory
                )
                folder_range = (
                    date.fromisoformat(str(input_snapshot["start_date"])),
                    date.fromisoformat(str(input_snapshot["end_date"])),
                )
                candidates.append(
                    (output_directory, output_directory.name, folder_range)
                )
        except DownloadInputMetadataError:
            raise
        except Exception:
            pass

    if not candidates:
        return {"has_existing": False}

    current_filters = (
        _current_filters_payload(current_payload or {}) if current_payload else None
    )
    ranges_data: list[dict[str, Any]] = []
    saved_filters = None
    for folder, folder_name, folder_range in candidates:
        snapshot = _require_current_download_input_snapshot(folder)
        folder_start = None
        folder_end = None
        try:
            folder_start = date.fromisoformat(str(snapshot["start_date"]))
            folder_end = date.fromisoformat(str(snapshot["end_date"]))
        except Exception:
            pass

        range_saved_filters = _snapshot_filters_payload(snapshot)
        filters_match = (
            _filters_payloads_match(current_filters, range_saved_filters)
            if current_filters
            else True
        )
        if saved_filters is None and range_saved_filters is not None:
            saved_filters = range_saved_filters

        metadata_status = "ok" if filters_match else "mismatch"

        ranges_data.append(
            {
                "start_date": folder_start.isoformat() if folder_start else None,
                "end_date": folder_end.isoformat() if folder_end else None,
                "folder_name": folder_name,
                "local_count": None,
                "kind_count": None,
                "status": "unverified",
                "error_detail": None,
                "metadata_missing": False,
                "metadata_obsolete": False,
                "metadata_status": metadata_status,
                "filters_match": filters_match,
                "folder_path": str(folder),
            }
        )

    dated_ranges = [r for r in ranges_data if r.get("start_date") and r.get("end_date")]
    return {
        "has_existing": True,
        "earliest_date": min((r["start_date"] for r in dated_ranges), default=None),
        "latest_date": max((r["end_date"] for r in dated_ranges), default=None),
        "ranges": sorted(ranges_data, key=lambda x: x.get("start_date") or ""),
        "saved_filters": saved_filters,
    }
