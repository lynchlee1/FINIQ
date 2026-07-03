"""Existing KIND download discovery and metadata helpers."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

from finiq.data_scraper.core.constants import DEFAULT_REQUEST_HEADERS, DISCLOSURE_GROUPS, MARKET_TYPES, SECURITIES_TYPES
from finiq.data_scraper.parse import pagination_info
from finiq.data_scraper.workflow import KindWorkflow, inspect_download_directory_pages

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


def _count_rows_fast_lxml(decoded: str) -> int:
    import re

    table_pattern = re.compile(r"<table[^>]*>", re.IGNORECASE)

    start_pos = -1
    for match in table_pattern.finditer(decoded):
        tag = match.group(0)
        if "summary" in tag and "회사명" in tag and "공시제목" in tag:
            start_pos = match.start()
            break
        if "class=" in tag and "list" in tag:
            start_pos = match.start()
            break

    if start_pos == -1:
        return 0

    end_match = decoded.find("</table>", start_pos)
    if end_match == -1:
        return 0

    table_content = decoded[start_pos : end_match + 8]

    import lxml.html

    parser = lxml.html.HTMLParser(recover=True, huge_tree=True)
    try:
        root = lxml.html.fragment_fromstring(table_content, parser=parser)
    except Exception:
        return 0

    tbodies = root.xpath("./tbody")
    parents = tbodies if tbodies else [root]

    rows_count = 0
    for p in parents:
        for tr in p.xpath("./tr"):
            if len(tr.xpath("./td")) >= 5:
                rows_count += 1
    return rows_count


def _validate_single_folder(
    folder: Path,
    folder_name: str,
    date_range: tuple[date, date],
    *,
    verify_with_kind: bool = True,
    current_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    body_files = list(folder.glob("*_post_page_*.body"))
    if not body_files:
        return None

    def get_dates_from_input_json(f: Path) -> dict[str, Any] | None:
        input_path = f / "kind_workflow.input.json"
        if input_path.is_file():
            try:
                data = json.loads(input_path.read_text(encoding="utf-8"))
                return data
            except Exception:
                pass
        return None

    saved_input_snapshot = get_dates_from_input_json(folder)
    metadata_path_exists = (folder / "kind_workflow.input.json").is_file()
    metadata_obsolete = (
        metadata_path_exists
        and not _is_trusted_download_input_snapshot(saved_input_snapshot)
    )
    input_snapshot = saved_input_snapshot if not metadata_obsolete else None
    start_date = date_range[0]
    end_date = date_range[1]

    if saved_input_snapshot:
        try:
            start_date = date.fromisoformat(saved_input_snapshot["start_date"])
            end_date = date.fromisoformat(saved_input_snapshot["end_date"])
        except Exception:
            pass
    if input_snapshot is None and _has_complete_current_download_payload(
        current_payload
    ):
        search_filters = _build_search_filters(current_payload)
        disclosure_type_groups = _normalize_disclosure_type_groups(current_payload)
        last_report_only = _as_bool(current_payload, "last_report_only")

        inferred_page_size = _infer_page_size_from_files(folder)
        if inferred_page_size <= 0:
            inferred_page_size = _as_int(current_payload, "page_size", 100)
            if inferred_page_size <= 0:
                inferred_page_size = 100

        input_snapshot = {
            "request_headers": DEFAULT_REQUEST_HEADERS,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "page_size": inferred_page_size,
            "search_filters": search_filters,
            "disclosure_type_groups": disclosure_type_groups,
            "last_report_only": last_report_only,
            "include_previous_disclosures": None,
        }

    status = "validated"
    error_detail = None
    kind_count = None
    local_count = None

    if input_snapshot:
        expected_page_size = 100
        try:
            expected_page_size = int(input_snapshot.get("page_size") or 100)
        except Exception:
            pass

        if verify_with_kind:
            kind_count = get_current_kind_total_count(input_snapshot)
        else:
            kind_count = None

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
                if kind_count is not None:
                    if local_count is None:
                        status = "stale"
                        error_detail = f"Failed to parse local download files (local count is null), while KIND current count is {kind_count}."
                    elif local_count != kind_count:
                        status = "stale"
                        error_detail = f"KIND current count ({kind_count}) differs from local count ({local_count})."
                else:
                    status = "unverified"
                    error_detail = "Failed to fetch current count from KIND (network error or timeout)."
            else:
                kind_count = None
                status = "unverified"
                error_detail = "KIND verification skipped (fast check mode)."
    else:
        paging = _detect_pagination(folder)
        local_count = paging.get("total_items") if paging else None
        status = "unverified"
        error_detail = "Missing or obsolete kind_workflow.input.json metadata to verify range against KIND."

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "folder_name": folder_name,
        "local_count": local_count,
        "kind_count": kind_count,
        "status": status,
        "error_detail": error_detail,
        "metadata_missing": not metadata_path_exists or metadata_obsolete,
        "metadata_obsolete": metadata_obsolete,
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
    except Exception:
        return {"has_existing": False}

    if not output_directory.is_dir():
        return {"has_existing": False}

    def get_dates_from_input_json(folder: Path) -> dict[str, Any] | None:
        input_path = folder / "kind_workflow.input.json"
        if input_path.is_file():
            try:
                data = json.loads(input_path.read_text(encoding="utf-8"))
                return data
            except Exception:
                pass
        return None

    candidates = []

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
                    except Exception:
                        pass
    except Exception:
        pass

    # If no yearly subfolders, check the directory itself (Single mode)
    if not candidates:
        try:
            if list(output_directory.glob("*_post_page_*.body")):
                input_snapshot = get_dates_from_input_json(output_directory)
                if input_snapshot:
                    try:
                        start_date = date.fromisoformat(input_snapshot["start_date"])
                        end_date = date.fromisoformat(input_snapshot["end_date"])
                        candidates.append(
                            (
                                output_directory,
                                output_directory.name,
                                (start_date, end_date),
                            )
                        )
                    except Exception:
                        pass
                else:
                    date_range = _infer_date_range_from_disclosures(output_directory)
                    if date_range:
                        candidates.append(
                            (output_directory, output_directory.name, date_range)
                        )
        except Exception:
            pass

    if not candidates:
        return {"has_existing": False}

    ranges_data = []
    # Run validation checks concurrently in a ThreadPool
    with ThreadPoolExecutor(max_workers=min(10, len(candidates))) as executor:
        futures = {
            executor.submit(
                _validate_single_folder,
                folder,
                folder_name,
                date_range,
                verify_with_kind=verify_with_kind,
                current_payload=current_payload,
            ): folder_name
            for folder, folder_name, date_range in candidates
        }
        for future in futures:
            try:
                res = future.result()
                if res is not None:
                    ranges_data.append(res)
            except Exception:
                pass

    if not ranges_data:
        return {"has_existing": False}

    sorted_ranges = sorted(ranges_data, key=lambda x: x["start_date"])
    earliest_date = min(r["start_date"] for r in ranges_data)
    latest_date = max(r["end_date"] for r in ranges_data)

    saved_filters = None
    for folder, _, _ in candidates:
        input_snapshot = get_dates_from_input_json(folder)
        if _is_trusted_download_input_snapshot(input_snapshot):
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
            if folder_range is not None:
                candidates.append((child, child.name, folder_range))
    except Exception:
        pass

    if not candidates:
        try:
            if list(output_directory.glob("*_post_page_*.body")):
                input_snapshot = _load_workflow_input(output_directory)
                folder_range = None
                if _is_trusted_download_input_snapshot(input_snapshot):
                    folder_range = (
                        date.fromisoformat(str(input_snapshot["start_date"])),
                        date.fromisoformat(str(input_snapshot["end_date"])),
                    )
                elif (
                    current_payload
                    and str(current_payload.get("start_date") or "")
                    and str(current_payload.get("end_date") or "")
                ):
                    folder_range = (
                        _parse_iso_date(
                            str(current_payload["start_date"]), "start_date"
                        ),
                        _parse_iso_date(str(current_payload["end_date"]), "end_date"),
                    )
                candidates.append(
                    (output_directory, output_directory.name, folder_range)
                )
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
        metadata_exists = (folder / "kind_workflow.input.json").is_file()
        try:
            snapshot = _load_workflow_input(folder)
        except Exception:
            snapshot = None
        metadata_trusted = _is_trusted_download_input_snapshot(snapshot)
        metadata_obsolete = metadata_exists and not metadata_trusted
        folder_start = folder_range[0] if folder_range else None
        folder_end = folder_range[1] if folder_range else None
        if metadata_trusted:
            try:
                folder_start = date.fromisoformat(str(snapshot["start_date"]))
                folder_end = date.fromisoformat(str(snapshot["end_date"]))
            except Exception:
                pass

        range_saved_filters = (
            _snapshot_filters_payload(snapshot or {}) if metadata_trusted else None
        )
        filters_match = (
            _filters_payloads_match(current_filters, range_saved_filters)
            if current_filters
            else True
        )
        if saved_filters is None and range_saved_filters is not None:
            saved_filters = range_saved_filters

        if metadata_trusted:
            metadata_status = "ok" if filters_match else "mismatch"
        elif metadata_obsolete:
            metadata_status = "obsolete"
        else:
            metadata_status = "missing"

        ranges_data.append(
            {
                "start_date": folder_start.isoformat() if folder_start else None,
                "end_date": folder_end.isoformat() if folder_end else None,
                "folder_name": folder_name,
                "local_count": None,
                "kind_count": None,
                "status": "unverified",
                "error_detail": None,
                "metadata_missing": not metadata_exists or metadata_obsolete,
                "metadata_obsolete": metadata_obsolete,
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


def _infer_page_size_from_files(folder: Path) -> int:
    body_files = list(folder.glob("*_post_page_*.body"))
    if not body_files:
        return 100

    import re

    page_num_re = re.compile(r"_post_page_(\d+)\.body$")
    inspected_pages = []
    for file_path in body_files:
        try:
            m = page_num_re.search(file_path.name)
            if not m:
                continue
            current_page = int(m.group(1))

            content = file_path.read_text(encoding="utf-8", errors="ignore")
            actual_rows = _count_rows_fast_lxml(content)

            paging = pagination_info(content.encode("utf-8"))
            if paging:
                total_pages = int(paging["total_pages"])
            else:
                total_pages = 1

            inspected_pages.append(
                {
                    "current_page": current_page,
                    "total_pages": total_pages,
                    "actual_rows": actual_rows,
                }
            )
        except Exception:
            pass

    non_last_sizes = [
        int(page_info["actual_rows"])
        for page_info in inspected_pages
        if int(page_info["current_page"]) < int(page_info["total_pages"])
    ]
    if non_last_sizes:
        return max(non_last_sizes)
    if inspected_pages:
        return max(int(page_info["actual_rows"]) for page_info in inspected_pages)
    return 100


def _infer_date_range_from_disclosures(folder: Path) -> tuple[date, date] | None:
    from finiq.data_scraper.parse import disclosure_rows

    body_files = list(folder.glob("*_post_page_*.body"))
    if not body_files:
        return None

    dates = []
    for file_path in body_files:
        try:
            content = file_path.read_bytes()
            rows = disclosure_rows(content)
            for row in rows:
                disclosed_at_str = row.get("disclosed_at")
                if disclosed_at_str:
                    date_part = str(disclosed_at_str).split()[0].replace(".", "-")
                    if (
                        len(date_part) == 10
                        and date_part[4] == "-"
                        and date_part[7] == "-"
                    ):
                        dates.append(date.fromisoformat(date_part))
        except Exception:
            pass

    if not dates:
        return None

    return min(dates), max(dates)


def create_folder_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    output_directory_raw = str(payload.get("output_directory") or "").strip()
    if not output_directory_raw:
        raise ValueError("output_directory is required")
    output_directory = Path(output_directory_raw).expanduser().resolve()
    if not output_directory.is_dir():
        raise ValueError(f"directory not found: {output_directory}")

    start_date_raw = str(payload.get("start_date") or "").strip()
    end_date_raw = str(payload.get("end_date") or "").strip()
    if not start_date_raw or not end_date_raw:
        raise ValueError("start_date and end_date are required")

    # Detect local pagination count
    paging = _detect_pagination(output_directory)
    if paging is None:
        raise ValueError(
            "no downloaded files found in the folder to detect local count"
        )
    local_count = paging.get("total_items")
    total_pages = paging.get("total_pages")
    if local_count is None or total_pages is None:
        raise ValueError(
            "failed to detect local count or page info from downloaded files"
        )

    # Infer page size from local files and validate
    inferred_page_size = _infer_page_size_from_files(output_directory)
    if inferred_page_size <= 0:
        inferred_page_size = _as_int(payload, "page_size", 100)
        if inferred_page_size <= 0:
            inferred_page_size = 100

    # Validate integrity using the inferred page size
    try:
        inspect_download_directory_pages(
            output_directory,
            expected_page_size=inferred_page_size,
            require_complete=True,
        )
    except Exception as exc:
        raise ValueError(
            f"Local files are not consistent with inferred page size ({inferred_page_size}): {exc}"
        )

    # Build input snapshot/workflow parameters using the inferred page size
    search_filters = _build_search_filters(payload)
    disclosure_type_groups = _normalize_disclosure_type_groups(payload)
    last_report_only = _as_bool(payload, "last_report_only")
    wait_seconds = _as_float(payload, "wait_seconds", 1.0)
    timeout = _as_float(payload, "timeout", 20.0)
    force = bool(_as_bool(payload, "force"))

    input_snapshot = {
        "request_headers": DEFAULT_REQUEST_HEADERS,
        "start_date": start_date_raw,
        "end_date": end_date_raw,
        "page_size": inferred_page_size,
        "search_filters": search_filters,
        "disclosure_type_groups": disclosure_type_groups,
        "last_report_only": last_report_only,
        "include_previous_disclosures": None,
    }

    # Fetch KIND live total count
    kind_count = get_current_kind_total_count(input_snapshot)

    # Compare
    is_matching = kind_count is not None and local_count == kind_count

    if is_matching or force:
        # Write metadata file using KindWorkflow
        workflow = KindWorkflow()
        workflow.configure(
            output_directory=output_directory,
            request_headers=DEFAULT_REQUEST_HEADERS,
            start_date=start_date_raw,
            end_date=end_date_raw,
            start_page=1,
            end_page=total_pages,
            page_size=inferred_page_size,
            search_filters=search_filters,
            disclosure_type_groups=disclosure_type_groups,
            last_report_only=last_report_only,
            include_previous_disclosures=None,
            wait_seconds_between_requests=wait_seconds,
            timeout=timeout,
        )
        workflow.save_input_snapshot()
        return {
            "success": True,
            "local_count": local_count,
            "kind_count": kind_count,
            "message": "Metadata created successfully.",
        }
    else:
        # Construct error message for mismatch
        if kind_count is None:
            message = (
                f"Failed to fetch live count from KIND. Local count is {local_count}."
            )
        else:
            message = f"KIND current count ({kind_count}) differs from local count ({local_count})."

        return {
            "success": False,
            "local_count": local_count,
            "kind_count": kind_count,
            "message": message,
        }
