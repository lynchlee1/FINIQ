"""KIND download orchestration, checkpoints, and merging ``*.body`` files to JSON."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any

import requests

from finiq_dataScraper.core.client import (
    KIND_SEARCH_PAGE_URL,
    KIND_SEARCH_RESULTS_URL,
    SEARCH_RESULTS_FILENAME_TEMPLATE,
    KindProgressCallback,
    KindSavedFileCallback,
    KindSavedFileValidator,
    KindViewerSavedFileCallback,
    _normalize_request_headers,
    _validate_save_request,
    download_disclosure_viewer_htmls,
    download_pages,
)
from finiq_dataScraper.storage.classification_store import (
    load_folder_partial_cache,
    write_company_classification_artifact,
    write_folder_partial_cache,
)
from finiq_dataScraper.parse import ParseMode, disclosure_file_rows, disclosure_rows, file_to_json, pagination_info
from finiq_dataScraper.core.payload import (
    DisclosureTypeGroupKey,
    DisclosureTypeGroupValue,
    KindDisclosureGroup,
    KindSearchFormData,
    _iter_search_filter_items,
    build_search_form,
)
from finiq_dataScraper.storage.result_files import KIND_REPAIR_OVERLAY_DIRNAME, result_page_number, sorted_result_page_paths

KindSearchFilters = Mapping[str, object] | Sequence[tuple[str, object]] | None


@dataclass(slots=True)
class KindModeBatchResult:
    """Batch export result per source folder."""

    folder: str
    body_files: int
    records: int
    output_path: str


@dataclass(slots=True)
class KindCompanyClassificationResult:
    """Company classification export summary."""

    source_folders: int
    body_files: int
    companies: int
    disclosures: int
    output_path: str
    integrity_errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class KindCompanyClassificationIntegrityReport:
    """Structured integrity diagnostics for company classification."""

    source_folders: int
    body_files: int
    parsed_disclosures: int
    classified_disclosures: int
    duplicates_removed: int
    integrity_errors: list[str] = field(default_factory=list)
    repair_targets: dict[str, list[int]] = field(default_factory=dict)
    repair_attempt_counts: dict[str, dict[int, int]] = field(default_factory=dict)
    repaired_folders: list[str] = field(default_factory=list)
    repair_attempted: bool = False


class KindCompanyClassificationIntegrityError(ValueError):
    """Raised when company classification fails integrity checks."""

    def __init__(self, report: KindCompanyClassificationIntegrityReport) -> None:
        self.report = report
        details = "\n".join(f"- {err}" for err in report.integrity_errors[:10])
        if len(report.integrity_errors) > 10:
            details += f"\n- ... 외 {len(report.integrity_errors) - 10}건"
        repair_summary = ""
        if report.repair_targets:
            repair_summary = (
                "\n자동 보완 대상: "
                + ", ".join(
                    f"{Path(folder).name}({','.join(str(page) for page in pages)})"
                    for folder, pages in sorted(report.repair_targets.items())
                )
            )
        if report.repair_attempted and report.repaired_folders:
            repair_summary += (
                "\n자동 보완 시도 폴더: "
                + ", ".join(Path(folder).name for folder in sorted(report.repaired_folders))
            )
        super().__init__(
            "회사별 분류 저장을 중단했습니다. 페이지 무결성 검사를 통과하지 못했습니다.\n"
            f"{details}{repair_summary}"
        )


def _collect_unique_acpt_numbers_from_result_pages(folder: Path) -> list[str]:
    acpt_numbers: list[str] = []
    seen_acpt_numbers: set[str] = set()
    for body_path in sorted_result_page_paths(folder):
        for row in disclosure_file_rows(body_path):
            acpt_no = str(row.get("acpt_no") or "").strip()
            if not acpt_no or acpt_no in seen_acpt_numbers:
                continue
            seen_acpt_numbers.add(acpt_no)
            acpt_numbers.append(acpt_no)
    return acpt_numbers


def _iter_target_kind_dirs(
    root_directory: Path,
    *,
    folder_prefix: str,
) -> list[Path]:
    candidates: list[Path] = []
    for child in sorted(root_directory.iterdir()):
        if child.is_dir() and child.name.startswith(folder_prefix):
            candidates.append(child)
    return candidates


def _iter_kind_result_dirs(root_directory: Path) -> list[Path]:
    result_dirs = {body_path.parent.resolve() for body_path in root_directory.rglob("*_post_page_*.body")}
    return sorted(result_dirs)


def _resolve_folder_parallelism(parallelism: int | None, item_count: int) -> int:
    if item_count <= 1:
        return max(1, item_count)
    requested = parallelism if parallelism is not None else (os.cpu_count() or 1)
    return max(1, min(int(requested), item_count))


def _merge_kind_body_records_by_mode(
    folder: Path,
    *,
    parse_mode: ParseMode,
) -> tuple[list[Any], int]:
    body_paths = sorted_result_page_paths(folder)
    merged_records: list[Any] = []
    for body_path in body_paths:
        parsed = file_to_json(body_path, mode=parse_mode)
        records = parsed.get(parse_mode, [])
        if isinstance(records, list):
            merged_records.extend(records)
    return merged_records, len(body_paths)


def _merge_company_badges(existing_badges: list[str], incoming_badges: Sequence[str]) -> list[str]:
    merged = list(existing_badges)
    for badge in incoming_badges:
        if badge and badge not in merged:
            merged.append(str(badge))
    return merged


def _merge_company_record(
    companies_by_key: dict[str, dict[str, Any]],
    company_key: str,
    incoming: dict[str, Any],
) -> int:
    seen_disclosure_keys: set[tuple[str, ...]] | None = incoming.get("_seen_disclosure_keys")
    disclosure_rows = list(incoming.get("disclosures") or [])
    filtered_disclosures: list[dict[str, Any]] = []
    duplicates_removed = 0
    if seen_disclosure_keys is None:
        filtered_disclosures = disclosure_rows
    else:
        for disclosure_item in disclosure_rows:
            acpt_no = str(disclosure_item.get("acpt_no") or "").strip()
            dedup_key = (
                ("acpt_no", acpt_no)
                if acpt_no
                else (
                    "fallback",
                    company_key,
                    str(disclosure_item.get("disclosed_at") or "").strip(),
                    str(disclosure_item.get("title") or "").strip(),
                    str(disclosure_item.get("submitter") or "").strip(),
                )
            )
            if dedup_key in seen_disclosure_keys:
                duplicates_removed += 1
                continue
            seen_disclosure_keys.add(dedup_key)
            filtered_disclosures.append(disclosure_item)

    existing = companies_by_key.get(company_key)
    if existing is None:
        if not filtered_disclosures and seen_disclosure_keys is not None:
            return duplicates_removed
        companies_by_key[company_key] = {
            "company_name": incoming.get("company_name"),
            "company_id": incoming.get("company_id"),
            "market": incoming.get("market"),
            "badges": list(incoming.get("badges") or []),
            "disclosures": filtered_disclosures,
        }
        return duplicates_removed

    company_name = str(incoming.get("company_name") or "").strip()
    company_id = incoming.get("company_id")
    market = incoming.get("market")
    if not existing.get("company_name") and company_name:
        existing["company_name"] = company_name
    if not existing.get("company_id") and company_id:
        existing["company_id"] = company_id
    if not existing.get("market") and market:
        existing["market"] = market
    existing["badges"] = _merge_company_badges(
        existing.get("badges") or [],
        incoming.get("badges") or [],
    )
    existing["disclosures"].extend(filtered_disclosures)
    return duplicates_removed


def _infer_page_size_from_inspected_pages(inspected_pages: list[dict[str, int]]) -> int:
    non_last_sizes = [
        int(page_info["actual_rows"])
        for page_info in inspected_pages
        if int(page_info["current_page"]) < int(page_info["total_pages"])
    ]
    if non_last_sizes:
        return max(non_last_sizes)
    if inspected_pages:
        return max(int(page_info["actual_rows"]) for page_info in inspected_pages)
    return 0


def _collect_company_records_from_folder(
    folder: str | Path,
    validate_integrity: bool = True,
) -> dict[str, Any]:
    target_folder = Path(folder).resolve()
    input_snapshot = _load_folder_input_snapshot(target_folder) if validate_integrity else None
    expected_page_size = int(input_snapshot.get("page_size") or 100) if input_snapshot else 100
    cached_payload = load_folder_partial_cache(
        target_folder,
        require_validated=validate_integrity,
    )
    if cached_payload is not None:
        companies_by_key = {
            str(company.get("company_id") or company.get("company_name") or "").strip(): company
            for company in list(cached_payload.get("companies") or [])
            if str(company.get("company_id") or company.get("company_name") or "").strip()
        }
        return {
            "companies_by_key": companies_by_key,
            "body_files": int(cached_payload.get("body_files") or 0),
            "parsed_disclosures": int(cached_payload.get("parsed_disclosures") or 0),
            "classified_disclosures": int(cached_payload.get("classified_disclosures") or 0),
            "intra_folder_duplicates": 0,
            "integrity_errors": [],
            "repair_pages": [],
            "folder_path": str(target_folder),
        }

    companies_by_key: dict[str, dict[str, Any]] = {}
    seen_disclosure_keys: set[tuple[str, ...]] = set()
    inspected_pages: list[dict[str, int]] = []
    page_numbers: set[int] = set()
    total_pages_values: set[int] = set()
    total_items_values: set[int] = set()
    integrity_errors: list[str] = []
    pages_to_redownload: list[int] = []
    body_files = 0
    parsed_disclosures = 0
    classified_disclosures = 0
    intra_folder_duplicates = 0

    for body_path in _effective_company_result_page_paths(target_folder):
        body_files += 1
        body_bytes = body_path.read_bytes()
        rows = disclosure_rows(body_bytes)
        actual_rows = len(rows)
        parsed_disclosures += actual_rows

        for row in rows:
            company_key = str(row.get("company_id") or row.get("company_name") or "").strip()
            if not company_key:
                continue

            classified_disclosures += 1
            company_name = str(row.get("company_name") or "").strip()
            disclosure_item = {
                "row_no": row.get("row_no"),
                "disclosed_at": row.get("disclosed_at"),
                "title": row.get("title"),
                "title_attr": row.get("title_attr"),
                "title_base": row.get("title_base"),
                "title_display": row.get("title_display"),
                "title_flags": list(row.get("title_flags") or []),
                "is_correction_report": row.get("is_correction_report"),
                "has_later_correction": row.get("has_later_correction"),
                "acpt_no": row.get("acpt_no"),
                "doc_no": row.get("doc_no"),
                "submitter": row.get("submitter"),
                "source_file": str(body_path),
                "source_page": result_page_number(body_path),
            }
            intra_folder_duplicates += _merge_company_record(
                companies_by_key,
                company_key,
                {
                    "company_name": company_name,
                    "company_id": row.get("company_id"),
                    "market": row.get("market"),
                    "badges": list(row.get("badges") or []),
                    "disclosures": [disclosure_item],
                    "_seen_disclosure_keys": seen_disclosure_keys,
                },
            )

        if validate_integrity:
            file_page_num = result_page_number(body_path)
            paging = pagination_info(body_bytes)
            if paging is None:
                integrity_errors.append(
                    f"{target_folder.name}/{body_path.name}에서 페이지네이션 정보를 찾지 못했습니다."
                )
                if file_page_num >= 1:
                    pages_to_redownload.append(file_page_num)
                continue
            current_page = int(paging["current_page"])
            total_pages = int(paging["total_pages"])
            total_items = int(paging["total_items"])
            if current_page in page_numbers:
                integrity_errors.append(
                    f"{target_folder.name}/{body_path.name}와 중복되는 페이지 번호 {current_page}가 있습니다."
                )
            page_numbers.add(current_page)
            total_pages_values.add(total_pages)
            total_items_values.add(total_items)
            inspected_pages.append(
                {
                    "current_page": current_page,
                    "total_pages": total_pages,
                    "total_items": total_items,
                    "actual_rows": actual_rows,
                }
            )

    pages_missing: list[int] = []
    expected_pages: set[int] = set()

    if validate_integrity and inspected_pages and not integrity_errors:
        pages_by_total_items: dict[int, list[int]] = {}
        for pi in inspected_pages:
            pages_by_total_items.setdefault(int(pi["total_items"]), []).append(int(pi["current_page"]))

        if len(total_items_values) != 1:
            majority_total_items = max(
                pages_by_total_items,
                key=lambda ti: len(pages_by_total_items[ti]),
            )
            minority_pages_ti = [
                page for ti, pgs in pages_by_total_items.items()
                if ti != majority_total_items
                for page in pgs
            ]
            breakdown = ", ".join(
                f"{ti}건({len(pgs)}개 페이지)"
                for ti, pgs in sorted(pages_by_total_items.items())
            )
            integrity_errors.append(
                f"{target_folder.name} 전체 건수 불일치: {breakdown}. "
                f"기준값 {majority_total_items}건과 다른 {len(minority_pages_ti)}개 페이지를 보완 대상으로 지정합니다."
            )
            pages_to_redownload.extend(minority_pages_ti)
            resolved_total_items = majority_total_items
        else:
            resolved_total_items = next(iter(total_items_values))

        if len(total_pages_values) != 1:
            pages_by_total_pages: dict[int, list[int]] = {}
            for pi in inspected_pages:
                pages_by_total_pages.setdefault(int(pi["total_pages"]), []).append(int(pi["current_page"]))
            majority_total_pages = max(
                pages_by_total_pages,
                key=lambda tp: len(pages_by_total_pages[tp]),
            )
            minority_pages_tp = [
                page for tp, pgs in pages_by_total_pages.items()
                if tp != majority_total_pages
                for page in pgs
            ]
            breakdown = ", ".join(
                f"{tp}페이지({len(pgs)}개 페이지)"
                for tp, pgs in sorted(pages_by_total_pages.items())
            )
            integrity_errors.append(
                f"{target_folder.name} 전체 페이지 수 불일치: {breakdown}"
            )
            for p in minority_pages_tp:
                if p not in pages_to_redownload:
                    pages_to_redownload.append(p)
            resolved_total_pages = majority_total_pages
        else:
            resolved_total_pages = next(iter(total_pages_values))

        expected_pages = set(range(1, resolved_total_pages + 1))
        gap_pages = sorted(expected_pages - page_numbers)
        extra_pages = sorted(page_numbers - expected_pages)
        if gap_pages:
            pages_missing = gap_pages
        if gap_pages or extra_pages:
            detail = f"누락: {gap_pages!r}" if gap_pages else ""
            if extra_pages:
                detail += (", " if detail else "") + f"초과: {extra_pages!r}"
            integrity_errors.append(
                f"{target_folder.name} 저장된 페이지 번호가 1~{resolved_total_pages} 범위와 맞지 않습니다. "
                f"{detail}"
            )

        if len(total_pages_values) == 1:
            for page_info in inspected_pages:
                expected_rows = _expected_rows_for_page(
                    total_items=resolved_total_items,
                    current_page=int(page_info["current_page"]),
                    total_pages=resolved_total_pages,
                    page_size=expected_page_size,
                )
                if int(page_info["actual_rows"]) != expected_rows:
                    integrity_errors.append(
                        f"{target_folder.name} {int(page_info['current_page'])}페이지의 행 수가 "
                        f"{int(page_info['actual_rows'])}건으로 기대값 {expected_rows}건과 다릅니다. "
                        f"(페이지 크기 {expected_page_size}, 전체 {resolved_total_items}건 중 "
                        f"{int(page_info['current_page'])}/{resolved_total_pages}페이지)"
                    )
                    pages_to_redownload.append(int(page_info["current_page"]))

        if len(total_items_values) == 1 and parsed_disclosures != resolved_total_items:
            integrity_errors.append(
                f"{target_folder.name}에서 파싱한 공시 {parsed_disclosures}건과 "
                f"페이지네이션 전체 건수 {resolved_total_items}건이 다릅니다. "
                f"(차이: {abs(parsed_disclosures - resolved_total_items)}건)"
            )

    all_repair_pages = sorted(set(pages_to_redownload + pages_missing))
    companies = sorted(
        companies_by_key.values(),
        key=lambda item: (
            str(item.get("company_name") or ""),
            str(item.get("company_id") or ""),
        ),
    )
    if not integrity_errors:
        write_folder_partial_cache(
            target_folder,
            validated=validate_integrity,
            body_files=body_files,
            parsed_disclosures=parsed_disclosures,
            classified_disclosures=classified_disclosures,
            companies=companies,
        )

    return {
        "companies_by_key": companies_by_key,
        "body_files": body_files,
        "parsed_disclosures": parsed_disclosures,
        "classified_disclosures": classified_disclosures,
        "intra_folder_duplicates": intra_folder_duplicates,
        "integrity_errors": integrity_errors,
        "repair_pages": all_repair_pages,
        "folder_path": str(target_folder),
    }


def _load_folder_input_snapshot(folder: Path) -> dict[str, Any] | None:
    """폴더의 kind_workflow.input.json을 읽어 다운로드 파라미터를 복원한다."""
    snapshot_path = folder / "kind_workflow.input.json"
    if not snapshot_path.exists():
        return None
    try:
        return _load_json_file(snapshot_path)
    except Exception:
        return None


def _group_contiguous_pages(pages: list[int]) -> list[tuple[int, int]]:
    """페이지 번호 리스트를 연속 구간 (start, end) 튜플로 묶는다."""
    if not pages:
        return []
    groups: list[tuple[int, int]] = []
    sorted_pages = sorted(set(pages))
    start = sorted_pages[0]
    end = start
    for page in sorted_pages[1:]:
        if page == end + 1:
            end = page
        else:
            groups.append((start, end))
            start = page
            end = page
    groups.append((start, end))
    return groups


_MAX_PAGE_REPAIR_ATTEMPTS = 100


def _repair_overlay_root(folder: Path) -> Path:
    return folder / KIND_REPAIR_OVERLAY_DIRNAME


def _repair_manifest_path(folder: Path) -> Path:
    return _repair_overlay_root(folder) / "manifest.json"


def _load_repair_manifest(folder: Path) -> dict[str, Any]:
    manifest_path = _repair_manifest_path(folder)
    if not manifest_path.exists():
        return {"pages": {}}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {"pages": {}}
    pages = payload.get("pages")
    if not isinstance(pages, dict):
        return {"pages": {}}
    return {"pages": dict(pages)}


def _write_repair_manifest(folder: Path, payload: dict[str, Any]) -> None:
    manifest_path = _repair_manifest_path(folder)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _repair_attempt_directory(folder: Path, page_number: int, attempt: int) -> Path:
    return _repair_overlay_root(folder) / f"page_{page_number:05d}" / f"attempt_{attempt:03d}"


def _effective_company_result_page_paths(folder: Path) -> list[Path]:
    page_paths: dict[int, Path] = {}
    for body_path in sorted_result_page_paths(folder):
        page_number = result_page_number(body_path)
        if page_number >= 1:
            page_paths[page_number] = body_path

    manifest = _load_repair_manifest(folder)
    for page_key, entry in dict(manifest.get("pages") or {}).items():
        try:
            page_number = int(page_key)
        except (TypeError, ValueError):
            continue
        relative_page_path = str(dict(entry).get("page_path") or "").strip()
        if not relative_page_path:
            continue
        overlay_path = (folder / relative_page_path).resolve()
        if overlay_path.exists():
            page_paths[page_number] = overlay_path

    return [page_paths[page_number] for page_number in sorted(page_paths)]


def _repair_folder_pages(
    folder: Path,
    page_numbers: list[int],
    *,
    progress_callback: KindProgressCallback | None = None,
) -> tuple[list[str], dict[int, int]]:
    """입력 스냅샷을 참조해 손상되거나 누락된 페이지를 재다운로드한다.

    Returns a list of remaining error messages (empty on full success).
    """
    if not page_numbers:
        return ([], {})

    snapshot = _load_folder_input_snapshot(folder)
    if snapshot is None:
        return (
            [
                f"{folder.name}: kind_workflow.input.json이 없어 "
                f"{len(page_numbers)}개 페이지를 보완할 수 없습니다."
            ],
            {},
        )

    request_headers = dict(snapshot.get("request_headers") or {})
    start_date = str(snapshot.get("start_date") or "")
    end_date = str(snapshot.get("end_date") or "")
    page_size = int(snapshot.get("page_size") or 100)
    search_filters = snapshot.get("search_filters")
    disclosure_type_groups = snapshot.get("disclosure_type_groups")
    last_report_only = snapshot.get("last_report_only")
    include_previous_disclosures = snapshot.get("include_previous_disclosures")
    wait_seconds = float(snapshot.get("wait_seconds_between_requests", 1.0))
    timeout = float(snapshot.get("timeout", 20.0))

    if not request_headers:
        return (
            [
                f"{folder.name}: request_headers가 없어 "
                f"{len(page_numbers)}개 페이지를 자동 보완할 수 없습니다."
            ],
            {},
        )

    remaining_errors: list[str] = []
    attempt_counts: dict[int, int] = {}
    manifest_payload = _load_repair_manifest(folder)
    manifest_pages = dict(manifest_payload.get("pages") or {})
    manifest_changed = False

    for page_number in sorted(set(page_numbers)):
        last_error: Exception | None = None
        success = False
        for attempt in range(1, _MAX_PAGE_REPAIR_ATTEMPTS + 1):
            attempt_counts[page_number] = attempt
            if progress_callback is not None:
                progress_callback(
                    f"{folder.name} {page_number}페이지 보완 시도 {attempt}/{_MAX_PAGE_REPAIR_ATTEMPTS}"
                )
            attempt_directory = _repair_attempt_directory(folder, page_number, attempt)
            try:
                download_pages(
                    output_directory=attempt_directory,
                    request_headers=request_headers,
                    start_date=start_date,
                    end_date=end_date,
                    start_page=page_number,
                    end_page=page_number,
                    page_size=page_size,
                    search_filters=search_filters,
                    disclosure_type_groups=disclosure_type_groups,
                    last_report_only=last_report_only,
                    include_previous_disclosures=include_previous_disclosures,
                    wait_seconds_between_requests=wait_seconds,
                    timeout=timeout,
                    progress_callback=progress_callback,
                    saved_file_validator=make_page_size_integrity_validator(
                        expected_page_size=page_size,
                    ),
                )
            except Exception as exc:
                last_error = exc
                continue
            candidate_path = attempt_directory / SEARCH_RESULTS_FILENAME_TEMPLATE.format(page_number=page_number)
            manifest_pages[str(page_number)] = {
                "attempt": attempt,
                "page_path": str(candidate_path.relative_to(folder)),
            }
            manifest_changed = True
            success = True
            break

        if success:
            continue

        remaining_errors.append(
            f"{folder.name} {page_number}페이지 재다운로드 실패: "
            f"{_MAX_PAGE_REPAIR_ATTEMPTS}회 시도 후에도 복구되지 않았습니다. "
            f"마지막 오류: {last_error}"
        )

    if manifest_changed:
        _write_repair_manifest(folder, {"pages": manifest_pages})

    return (remaining_errors, attempt_counts)


def _collect_all_folder_summaries(
    target_folders: list[Path],
    *,
    parallelism: int | None = None,
    validate_integrity: bool = True,
) -> list[dict[str, Any]]:
    """모든 대상 폴더에서 회사별 레코드 요약을 수집한다."""
    worker_count = _resolve_folder_parallelism(parallelism, len(target_folders))
    folder_targets = [str(folder) for folder in target_folders]
    if worker_count == 1:
        return [
            _collect_company_records_from_folder(folder, validate_integrity=validate_integrity)
            for folder in folder_targets
        ]
    try:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            return list(
                executor.map(
                    _collect_company_records_from_folder,
                    folder_targets,
                    [validate_integrity] * len(folder_targets),
                )
            )
    except (BrokenProcessPool, OSError, PermissionError):
        return [
            _collect_company_records_from_folder(folder, validate_integrity=validate_integrity)
            for folder in folder_targets
        ]


def _merge_folder_summaries(
    folder_summaries: list[dict[str, Any]],
    source_folder_count: int,
) -> tuple[dict[str, Any], int, int, int, int, int, list[str], dict[str, list[int]]]:
    """폴더 요약들을 병합해 전체 payload와 무결성 정보를 반환한다."""
    companies_by_key: dict[str, dict[str, Any]] = {}
    body_files = 0
    parsed_disclosures = 0
    raw_classified_disclosures = 0
    seen_disclosure_keys: set[tuple[str, ...]] = set()
    duplicates_removed = 0
    all_integrity_errors: list[str] = []
    repair_targets: dict[str, list[int]] = {}

    for folder_summary in folder_summaries:
        body_files += int(folder_summary["body_files"])
        parsed_disclosures += int(folder_summary["parsed_disclosures"])
        raw_classified_disclosures += int(folder_summary["classified_disclosures"])
        duplicates_removed += int(folder_summary.get("intra_folder_duplicates") or 0)
        all_integrity_errors.extend(list(folder_summary.get("integrity_errors") or []))
        repair_pages = list(folder_summary.get("repair_pages") or [])
        if repair_pages:
            folder_path = str(folder_summary.get("folder_path") or "")
            if folder_path:
                repair_targets[folder_path] = repair_pages
        for company_key, incoming in dict(folder_summary["companies_by_key"]).items():
            duplicates_removed += _merge_company_record(
                companies_by_key,
                company_key,
                {
                    **incoming,
                    "_seen_disclosure_keys": seen_disclosure_keys,
                },
            )

    companies = sorted(
        companies_by_key.values(),
        key=lambda item: (
            str(item.get("company_name") or ""),
            str(item.get("company_id") or ""),
        ),
    )
    deduplicated_disclosures = sum(len(company["disclosures"]) for company in companies)
    payload = {
        "summary": {
            "source_folders": source_folder_count,
            "body_files": body_files,
            "companies": len(companies),
            "disclosures": deduplicated_disclosures,
        },
        "companies": companies,
    }
    return (
        payload,
        parsed_disclosures,
        raw_classified_disclosures,
        duplicates_removed,
        source_folder_count,
        body_files,
        all_integrity_errors,
        repair_targets,
    )


def _build_company_classification_payload(
    root_directory: Path,
    *,
    parallelism: int | None = None,
    validate_integrity: bool = True,
    progress_callback: KindProgressCallback | None = None,
) -> tuple[dict[str, Any], KindCompanyClassificationIntegrityReport]:
    target_folders = _iter_kind_result_dirs(root_directory)
    folder_summaries = _collect_all_folder_summaries(
        target_folders,
        parallelism=parallelism,
        validate_integrity=validate_integrity,
    )

    (
        payload,
        parsed_disclosures,
        raw_classified_disclosures,
        duplicates_removed,
        source_folders,
        body_files,
        integrity_errors,
        repair_targets,
    ) = _merge_folder_summaries(folder_summaries, len(target_folders))

    report = KindCompanyClassificationIntegrityReport(
        source_folders=source_folders,
        body_files=body_files,
        parsed_disclosures=parsed_disclosures,
        classified_disclosures=raw_classified_disclosures,
        duplicates_removed=duplicates_removed,
        integrity_errors=list(integrity_errors),
        repair_targets=dict(repair_targets),
        repair_attempt_counts={},
        repaired_folders=[],
        repair_attempted=False,
    )

    if not repair_targets or not validate_integrity:
        return (payload, report)

    total_repair_pages = sum(len(pages) for pages in repair_targets.values())
    if progress_callback is not None:
        progress_callback(
            f"무결성 보완 시작: {len(repair_targets)}개 폴더, {total_repair_pages}개 페이지 재다운로드"
        )

    repair_remaining_errors: list[str] = []
    repaired_folders: list[Path] = []
    repair_attempt_counts: dict[str, dict[int, int]] = {}
    for folder_path_str, pages in repair_targets.items():
        folder_path = Path(folder_path_str)
        errors, attempt_counts = _repair_folder_pages(
            folder_path,
            pages,
            progress_callback=progress_callback,
        )
        if errors:
            repair_remaining_errors.extend(errors)
        if attempt_counts:
            repair_attempt_counts[str(folder_path)] = dict(attempt_counts)
        repaired_folders.append(folder_path)

    report.repair_attempted = True
    report.repaired_folders = [str(folder) for folder in repaired_folders]
    report.repair_attempt_counts = repair_attempt_counts

    if not repaired_folders:
        report.integrity_errors = repair_remaining_errors + integrity_errors
        return (payload, report)

    if progress_callback is not None:
        progress_callback(
            f"보완 완료된 {len(repaired_folders)}개 폴더 재수집 중..."
        )

    repaired_summaries = _collect_all_folder_summaries(
        repaired_folders,
        parallelism=parallelism,
        validate_integrity=validate_integrity,
    )
    all_summaries = [
        summary for summary in folder_summaries
        if summary.get("folder_path") not in {str(f) for f in repaired_folders}
    ] + repaired_summaries

    (
        payload,
        parsed_disclosures,
        raw_classified_disclosures,
        duplicates_removed,
        _,
        body_files,
        remaining_integrity_errors,
        _still_broken,
    ) = _merge_folder_summaries(all_summaries, len(target_folders))

    final_errors = repair_remaining_errors + remaining_integrity_errors
    report.body_files = body_files
    report.parsed_disclosures = parsed_disclosures
    report.classified_disclosures = raw_classified_disclosures
    report.duplicates_removed = duplicates_removed
    report.integrity_errors = final_errors
    return (payload, report)


def export_kind_mode_folder(
    folder: str | Path,
    *,
    parse_mode: ParseMode = "simpletable",
    output_path: str | Path | None = None,
    compact: bool = True,
) -> KindModeBatchResult:
    """Merge one folder's KIND `*.body` files into a single mode JSON."""
    target_folder = Path(folder).resolve()
    if not target_folder.is_dir():
        msg = f"Not a directory: {target_folder}"
        raise NotADirectoryError(msg)

    merged_records, body_count = _merge_kind_body_records_by_mode(
        target_folder,
        parse_mode=parse_mode,
    )
    destination = (
        Path(output_path).resolve()
        if output_path is not None
        else target_folder / f"{target_folder.name}.{parse_mode}.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {parse_mode: merged_records}
    if compact:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    destination.write_text(text, encoding="utf-8")

    return KindModeBatchResult(
        folder=target_folder.name,
        body_files=body_count,
        records=len(merged_records),
        output_path=str(destination),
    )


def _export_kind_mode_folder_task(
    task: tuple[str, ParseMode, str | None, bool],
) -> KindModeBatchResult:
    folder, parse_mode, output_path, compact = task
    return export_kind_mode_folder(
        folder,
        parse_mode=parse_mode,
        output_path=output_path,
        compact=compact,
    )


def export_kind_mode_folders(
    folders: Sequence[str | Path],
    *,
    parse_mode: ParseMode = "simpletable",
    output_paths: Sequence[str | Path | None] | None = None,
    compact: bool = True,
    parallelism: int | None = None,
) -> list[KindModeBatchResult]:
    """Export multiple downloaded result folders, optionally in parallel."""
    resolved_folders = [Path(folder).resolve() for folder in folders]
    if not resolved_folders:
        return []

    if output_paths is None:
        resolved_output_paths: list[str | None] = [None] * len(resolved_folders)
    else:
        if len(output_paths) != len(resolved_folders):
            msg = "output_paths length must match folders length"
            raise ValueError(msg)
        resolved_output_paths = [
            str(Path(path).resolve()) if path is not None else None
            for path in output_paths
        ]

    tasks = [
        (str(folder), parse_mode, output_path, compact)
        for folder, output_path in zip(resolved_folders, resolved_output_paths)
    ]
    worker_count = _resolve_folder_parallelism(parallelism, len(tasks))
    if worker_count == 1:
        return [_export_kind_mode_folder_task(task) for task in tasks]
    try:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            return list(executor.map(_export_kind_mode_folder_task, tasks))
    except (BrokenProcessPool, OSError, PermissionError):
        return [_export_kind_mode_folder_task(task) for task in tasks]


def export_kind_mode_batch(
    root_directory: str | Path,
    *,
    parse_mode: ParseMode = "simpletable",
    folder_prefix: str = "seibro_",
    output_root_directory: str | Path | None = None,
    compact: bool = True,
    parallelism: int | None = None,
) -> list[KindModeBatchResult]:
    """Batch-export all matching folders under root into mode JSON files."""
    root = Path(root_directory).resolve()
    if not root.is_dir():
        msg = f"Not a directory: {root}"
        raise NotADirectoryError(msg)

    output_root = Path(output_root_directory).resolve() if output_root_directory else None
    targets = _iter_target_kind_dirs(root, folder_prefix=folder_prefix)
    output_paths = [
        output_root / f"{folder.name}.{parse_mode}.json" if output_root is not None else None
        for folder in targets
    ]
    return export_kind_mode_folders(
        targets,
        parse_mode=parse_mode,
        output_paths=output_paths,
        compact=compact,
        parallelism=parallelism,
    )


def export_kind_company_classification(
    root_directory: str | Path,
    *,
    output_path: str | Path | None = None,
    compact: bool = True,
    parallelism: int | None = None,
    validate_integrity: bool = True,
    progress_callback: KindProgressCallback | None = None,
) -> KindCompanyClassificationResult:
    """Recursively classify KIND disclosures by company under one root directory."""
    root = Path(root_directory).resolve()
    if not root.is_dir():
        msg = f"Not a directory: {root}"
        raise NotADirectoryError(msg)

    payload, integrity_report = _build_company_classification_payload(
        root,
        parallelism=parallelism,
        validate_integrity=validate_integrity,
        progress_callback=progress_callback,
    )
    deduplicated_disclosures = int(payload["summary"]["disclosures"])
    if validate_integrity and integrity_report.integrity_errors:
        raise KindCompanyClassificationIntegrityError(integrity_report)

    if not integrity_report.integrity_errors:
        if integrity_report.classified_disclosures != integrity_report.parsed_disclosures:
            msg = (
                "Disclosure classification count mismatch: "
                f"parsed {integrity_report.parsed_disclosures} disclosures but "
                f"classified {integrity_report.classified_disclosures}."
            )
            raise ValueError(msg)
        if deduplicated_disclosures + integrity_report.duplicates_removed != integrity_report.classified_disclosures:
            msg = (
                "Disclosure deduplication count mismatch: "
                f"classified {integrity_report.classified_disclosures} disclosures but "
                f"deduplicated result kept {deduplicated_disclosures} and removed "
                f"{integrity_report.duplicates_removed}."
            )
            raise ValueError(msg)

    destination = (
        Path(output_path).resolve()
        if output_path is not None
        else root / "kind.company_classification.json"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_company_classification_artifact(
        destination,
        payload,
        compact=compact,
    )

    return KindCompanyClassificationResult(
        source_folders=integrity_report.source_folders,
        body_files=integrity_report.body_files,
        companies=int(payload["summary"]["companies"]),
        disclosures=deduplicated_disclosures,
        output_path=str(destination),
        integrity_errors=list(integrity_report.integrity_errors),
    )


def diagnose_kind_company_classification_integrity(
    root_directory: str | Path,
    *,
    parallelism: int | None = None,
    validate_integrity: bool = True,
    progress_callback: KindProgressCallback | None = None,
) -> KindCompanyClassificationIntegrityReport:
    """Diagnose integrity issues and attempt auto-repair without writing output JSON."""
    root = Path(root_directory).resolve()
    if not root.is_dir():
        msg = f"Not a directory: {root}"
        raise NotADirectoryError(msg)

    _, integrity_report = _build_company_classification_payload(
        root,
        parallelism=parallelism,
        validate_integrity=validate_integrity,
        progress_callback=progress_callback,
    )
    return integrity_report


def download_kind_viewer_htmls_from_result_folder(
    result_folder: str | Path,
    *,
    output_directory: str | Path | None = None,
    request_headers: Mapping[str, object],
    timeout: float = 20.0,
    wait_seconds_between_requests: float = 0.0,
    max_requests_per_minute: int = 90,
    limit: int | None = None,
    session: requests.Session | None = None,
    skip_existing: bool = True,
    progress_callback: KindProgressCallback | None = None,
    saved_file_callback: KindViewerSavedFileCallback | None = None,
) -> dict[str, Any]:
    """저장된 KIND 검색 결과 폴더의 접수번호별 뷰어 HTML 전체를 저장한다."""
    source_folder = Path(result_folder).resolve()
    if not source_folder.is_dir():
        msg = f"Not a directory: {source_folder}"
        raise NotADirectoryError(msg)
    if limit is not None and limit < 1:
        raise ValueError("limit must be >= 1")

    viewer_output_directory = (
        source_folder / "viewer_html"
        if output_directory is None
        else Path(output_directory).resolve()
    )
    acpt_numbers = _collect_unique_acpt_numbers_from_result_pages(source_folder)
    if limit is not None:
        acpt_numbers = acpt_numbers[:limit]

    saved_paths = download_disclosure_viewer_htmls(
        output_directory=viewer_output_directory,
        request_headers=request_headers,
        acpt_numbers=acpt_numbers,
        timeout=timeout,
        wait_seconds_between_requests=wait_seconds_between_requests,
        max_requests_per_minute=max_requests_per_minute,
        session=session,
        skip_existing=skip_existing,
        progress_callback=progress_callback,
        saved_file_callback=saved_file_callback,
    )
    return {
        "source_folder": str(source_folder),
        "output_directory": str(viewer_output_directory),
        "acpt_numbers": acpt_numbers,
        "saved_files": [str(path) for path in saved_paths],
    }


def _normalize_disclosure_type_groups(
    disclosure_type_groups: Mapping[DisclosureTypeGroupKey, DisclosureTypeGroupValue] | None,
) -> dict[str, list[str]]:
    """공시유형 그룹 입력을 workflow state에 저장하기 쉬운 형태로 맞춘다."""
    normalized_groups: dict[str, list[str]] = {}
    for group_key, group_value in (disclosure_type_groups or {}).items():
        disclosure_group = KindDisclosureGroup.from_raw(group_key, group_value)
        normalized_groups[disclosure_group.suffix] = disclosure_group.codes
    return normalized_groups


@dataclass(slots=True)
class KindWorkflowInput:
    """KIND workflow 실행에 필요한 사용자 입력을 보관한다."""

    output_directory: Path
    request_headers: dict[str, str]
    start_date: str
    end_date: str
    start_page: int
    end_page: int
    search_filters: KindSearchFormData
    disclosure_type_groups: dict[str, list[str]]
    last_report_only: bool | None
    include_previous_disclosures: bool | None
    page_size: int
    wait_seconds_between_requests: float
    timeout: float
    parse_mode: ParseMode

    def to_dict(self) -> dict[str, Any]:
        """현재 workflow 입력 상태를 JSON 친화적인 dict로 내보낸다."""
        return {
            "output_directory": str(self.output_directory),
            "request_headers": dict(self.request_headers),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "search_filters": list(self.search_filters),
            "disclosure_type_groups": {
                suffix: list(codes) for suffix, codes in self.disclosure_type_groups.items()
            },
            "last_report_only": self.last_report_only,
            "include_previous_disclosures": self.include_previous_disclosures,
            "page_size": self.page_size,
            "wait_seconds_between_requests": self.wait_seconds_between_requests,
            "timeout": self.timeout,
            "parse_mode": self.parse_mode,
        }


@dataclass(slots=True)
class KindWorkflowCheckpoint:
    """중간 저장 상태를 표현하는 checkpoint object다."""

    input: dict[str, Any]
    saved_files: list[str]
    last_saved_file: str | None
    last_saved_page: int | None
    last_request_data: KindSearchFormData
    completed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "input": self.input,
            "saved_files": list(self.saved_files),
            "last_saved_file": self.last_saved_file,
            "last_saved_page": self.last_saved_page,
            "last_request_data": list(self.last_request_data),
            "completed": self.completed,
        }


def _write_json_file(file_path: Path, payload: dict[str, Any]) -> None:
    """JSON 파일을 원자적으로 교체해 깨진 저장을 줄인다."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = file_path.with_suffix(f"{file_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(file_path)


def _load_json_file(file_path: Path) -> dict[str, Any]:
    return json.loads(file_path.read_text(encoding="utf-8"))


def _iter_saved_result_pages(output_directory: Path) -> list[Path]:
    return sorted_result_page_paths(output_directory)


def _resolve_validation_parallelism(worker_count: int | None) -> int:
    if worker_count is None:
        return max(1, os.cpu_count() or 1)
    if worker_count < 1:
        raise ValueError("validation_parallelism must be >= 1")
    return worker_count


def _expected_rows_for_page(
    *,
    total_items: int,
    current_page: int,
    total_pages: int,
    page_size: int,
) -> int:
    if current_page < 1 or total_pages < 1 or current_page > total_pages:
        msg = (
            "페이지 무결성 검사 실패: "
            f"잘못된 페이지네이션(current_page={current_page}, total_pages={total_pages})"
        )
        raise ValueError(msg)
    if current_page < total_pages:
        return page_size
    expected_rows = total_items - (page_size * (total_pages - 1))
    if expected_rows < 0 or expected_rows > page_size:
        msg = (
            "페이지 무결성 검사 실패: "
            f"전체 건수 {total_items}와 페이지 수 {total_pages}가 고정 페이지 크기 {page_size}와 맞지 않습니다."
        )
        raise ValueError(msg)
    return expected_rows


def validate_downloaded_result_page(
    page_path: str | Path,
    *,
    expected_page_size: int,
) -> dict[str, int]:
    """저장된 KIND 결과 페이지가 고정 페이지 크기와 맞는지 검사한다."""
    resolved_path = Path(page_path).resolve()
    paging = pagination_info(resolved_path.read_bytes())
    if paging is None:
        msg = f"페이지 무결성 검사 실패: {resolved_path.name}에서 페이지네이션 정보를 찾지 못했습니다."
        raise ValueError(msg)

    actual_rows = len(disclosure_file_rows(resolved_path))
    expected_rows = _expected_rows_for_page(
        total_items=int(paging["total_items"]),
        current_page=int(paging["current_page"]),
        total_pages=int(paging["total_pages"]),
        page_size=expected_page_size,
    )
    if actual_rows != expected_rows:
        msg = (
            "페이지 무결성 검사 실패: "
            f"{resolved_path.name}의 행 수가 {actual_rows}건으로, "
            f"고정 페이지 크기 {expected_page_size} 기준 기대값 {expected_rows}건과 다릅니다."
        )
        raise ValueError(msg)
    return {
        "current_page": int(paging["current_page"]),
        "total_pages": int(paging["total_pages"]),
        "total_items": int(paging["total_items"]),
    }


def _validate_downloaded_result_page_task(task: tuple[str, int]) -> dict[str, int]:
    page_path, expected_page_size = task
    return validate_downloaded_result_page(page_path, expected_page_size=expected_page_size)


def validate_download_directory_page_size(
    output_directory: str | Path,
    *,
    expected_page_size: int,
    validation_parallelism: int | None = None,
) -> None:
    """폴더 안의 기존 결과 페이지들이 고정 페이지 크기와 일치하는지 검사한다."""
    resolved_output_directory = Path(output_directory).resolve()
    page_paths = _iter_saved_result_pages(resolved_output_directory)
    worker_count = min(_resolve_validation_parallelism(validation_parallelism), max(1, len(page_paths)))
    if worker_count == 1:
        for page_path in page_paths:
            validate_downloaded_result_page(page_path, expected_page_size=expected_page_size)
        return
    try:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            list(
                executor.map(
                    _validate_downloaded_result_page_task,
                    [(str(page_path), expected_page_size) for page_path in page_paths],
                )
            )
    except (BrokenProcessPool, OSError, PermissionError):
        for page_path in page_paths:
            validate_downloaded_result_page(page_path, expected_page_size=expected_page_size)


def inspect_download_directory_pages(
    output_directory: str | Path,
    *,
    expected_page_size: int,
    require_complete: bool = False,
    validation_parallelism: int | None = None,
) -> dict[str, int]:
    """폴더 안의 페이지네이션 정보와 페이지 개수 일관성을 검사한다."""
    resolved_output_directory = Path(output_directory).resolve()
    page_paths = _iter_saved_result_pages(resolved_output_directory)
    if not page_paths:
        return {
            "downloaded_pages": 0,
            "total_pages": 0,
            "total_items": 0,
        }

    page_numbers: set[int] = set()
    total_pages_values: set[int] = set()
    total_items_values: set[int] = set()

    worker_count = min(_resolve_validation_parallelism(validation_parallelism), max(1, len(page_paths)))
    if worker_count == 1:
        inspected_pages = [
            validate_downloaded_result_page(page_path, expected_page_size=expected_page_size)
            for page_path in page_paths
        ]
    else:
        try:
            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                inspected_pages = list(
                    executor.map(
                        _validate_downloaded_result_page_task,
                        [(str(page_path), expected_page_size) for page_path in page_paths],
                    )
                )
        except (BrokenProcessPool, OSError, PermissionError):
            inspected_pages = [
                validate_downloaded_result_page(page_path, expected_page_size=expected_page_size)
                for page_path in page_paths
            ]

    for page_path, page_info in zip(page_paths, inspected_pages):
        current_page = int(page_info["current_page"])
        if current_page in page_numbers:
            msg = f"페이지 무결성 검사 실패: {page_path.name}와 중복되는 페이지 번호 {current_page}가 있습니다."
            raise ValueError(msg)
        page_numbers.add(current_page)
        total_pages_values.add(int(page_info["total_pages"]))
        total_items_values.add(int(page_info["total_items"]))

    if len(total_pages_values) != 1 or len(total_items_values) != 1:
        msg = "페이지 무결성 검사 실패: 저장된 페이지들 사이의 전체 페이지 수 또는 전체 건수가 서로 다릅니다."
        raise ValueError(msg)

    downloaded_pages = len(page_paths)
    total_pages = next(iter(total_pages_values))
    total_items = next(iter(total_items_values))
    expected_prefix = set(range(1, downloaded_pages + 1))
    if page_numbers != expected_prefix:
        msg = (
            "페이지 무결성 검사 실패: 저장된 페이지 번호가 1페이지부터 연속적이지 않습니다. "
            f"현재 페이지 번호는 {sorted(page_numbers)!r}입니다."
        )
        raise ValueError(msg)
    if require_complete and downloaded_pages != total_pages:
        msg = (
            "페이지 무결성 검사 실패: 저장된 페이지 수와 페이지네이션의 전체 페이지 수가 다릅니다. "
            f"저장된 페이지는 {downloaded_pages}개, 페이지네이션은 {total_pages}페이지입니다."
        )
        raise ValueError(msg)

    return {
        "downloaded_pages": downloaded_pages,
        "total_pages": total_pages,
        "total_items": total_items,
    }


def ensure_download_directory_integrity(
    output_directory: str | Path,
    *,
    requested_page_size: int,
    input_snapshot_path: str | Path | None = None,
    validation_parallelism: int | None = None,
) -> int:
    """기존 폴더의 고정 페이지 크기와 저장된 페이지 무결성을 확인한다."""
    resolved_output_directory = Path(output_directory).resolve()
    resolved_input_snapshot_path = (
        resolved_output_directory / "kind_workflow.input.json"
        if input_snapshot_path is None
        else Path(input_snapshot_path).resolve()
    )
    saved_result_pages = _iter_saved_result_pages(resolved_output_directory)

    if not resolved_input_snapshot_path.exists():
        if saved_result_pages:
            msg = (
                "기존 다운로드 페이지가 있지만 고정 페이지 크기를 담은 "
                f"{resolved_input_snapshot_path.name}이 없어 무결성 검사를 할 수 없습니다."
            )
            raise ValueError(msg)
        return requested_page_size

    saved_input = _load_json_file(resolved_input_snapshot_path)
    locked_page_size = saved_input.get("page_size")
    if locked_page_size is None:
        msg = f"{resolved_input_snapshot_path.name}에 고정된 page_size가 없습니다."
        raise ValueError(msg)
    locked_page_size = int(locked_page_size)
    if locked_page_size != requested_page_size:
        msg = (
            "기존 다운로드 폴더의 고정 페이지 크기와 현재 요청이 다릅니다. "
            f"저장값은 {locked_page_size}, 현재 요청은 {requested_page_size}입니다."
        )
        raise ValueError(msg)
    inspect_download_directory_pages(
        resolved_output_directory,
        expected_page_size=locked_page_size,
        require_complete=False,
        validation_parallelism=validation_parallelism,
    )
    return locked_page_size


def make_page_size_integrity_validator(
    *,
    expected_page_size: int,
) -> KindSavedFileValidator:
    """새로 저장한 KIND 결과 페이지를 즉시 검증하는 validator를 만든다."""

    def _validator(
        output_path: Path,
        page_number: int | None,
        request_data: KindSearchFormData | None,
    ) -> None:
        del request_data
        if page_number is None:
            return
        try:
            validate_downloaded_result_page(output_path, expected_page_size=expected_page_size)
        except Exception:
            output_path.unlink(missing_ok=True)
            raise

    return _validator


class KindWorkflow:
    """Store KIND search inputs and optionally save raw responses."""

    def __init__(self) -> None:
        self.input: KindWorkflowInput | None = None
        self.checkpoint: KindWorkflowCheckpoint | None = None

    def _require_input(self) -> KindWorkflowInput:
        if self.input is None:
            raise ValueError("KindWorkflow is not configured. Call configure() or run() first.")
        return self.input

    def configure(
        self,
        *,
        output_directory: str | Path,
        request_headers: Mapping[str, object],
        start_date: str = "",
        end_date: str = "",
        start_page: int = 1,
        end_page: int = 1,
        search_filters: KindSearchFilters = None,
        disclosure_type_groups: Mapping[DisclosureTypeGroupKey, DisclosureTypeGroupValue] | None = None,
        last_report_only: bool | None = None,
        include_previous_disclosures: bool | None = None,
        page_size: int = 100,
        wait_seconds_between_requests: float = 1.0,
        timeout: float = 20.0,
        parse_mode: ParseMode = "tables",
    ) -> KindWorkflowInput:
        """사용자 입력을 normalize해서 instance state에 저장한다."""
        _validate_save_request(
            page_size=page_size,
            start_page=start_page,
            end_page=end_page,
            timeout=timeout,
        )
        if wait_seconds_between_requests < 0:
            raise ValueError("wait_seconds_between_requests must be >= 0")

        configured_input = KindWorkflowInput(
            output_directory=Path(output_directory).resolve(),
            request_headers=_normalize_request_headers(request_headers),
            start_date=str(start_date),
            end_date=str(end_date),
            start_page=start_page,
            end_page=end_page,
            search_filters=_iter_search_filter_items(search_filters),
            disclosure_type_groups=_normalize_disclosure_type_groups(disclosure_type_groups),
            last_report_only=last_report_only,
            include_previous_disclosures=include_previous_disclosures,
            page_size=page_size,
            wait_seconds_between_requests=wait_seconds_between_requests,
            timeout=timeout,
            parse_mode=parse_mode,
        )
        self.input = configured_input
        return configured_input

    def build_request_data(self, *, page_number: int | None = None) -> KindSearchFormData:
        """저장된 입력값으로 KIND 검색 POST payload를 만든다."""
        configured_input = self._require_input()
        target_page = configured_input.start_page if page_number is None else page_number
        if target_page < 1:
            raise ValueError("page_number must be >= 1")
        return build_search_form(
            page_number=target_page,
            start_date=configured_input.start_date,
            end_date=configured_input.end_date,
            page_size=configured_input.page_size,
            search_filters=configured_input.search_filters,
            disclosure_type_groups=configured_input.disclosure_type_groups,
            last_report_only=configured_input.last_report_only,
            include_previous_disclosures=configured_input.include_previous_disclosures,
        )

    def get_input(self) -> KindWorkflowInput:
        """현재 저장된 입력값을 반환한다."""
        return self._require_input()

    def _build_checkpoint(self) -> KindWorkflowCheckpoint:
        configured_input = self._require_input()
        if self.checkpoint is None:
            self.checkpoint = KindWorkflowCheckpoint(
                input=configured_input.to_dict(),
                saved_files=[],
                last_saved_file=None,
                last_saved_page=None,
                last_request_data=[],
                completed=False,
            )
        return self.checkpoint

    def get_checkpoint(self) -> KindWorkflowCheckpoint:
        """현재 checkpoint 상태를 반환한다."""
        return self._build_checkpoint()

    def save_input_snapshot(self, path: str | Path | None = None) -> Path:
        """현재 입력 상태를 JSON 파일로 저장한다."""
        configured_input = self._require_input()
        snapshot_path = (
            configured_input.output_directory / "kind_workflow.input.json"
            if path is None
            else Path(path).resolve()
        )
        _write_json_file(snapshot_path, configured_input.to_dict())
        return snapshot_path

    def save_checkpoint(self, path: str | Path | None = None) -> Path:
        """현재 checkpoint 상태를 JSON 파일로 저장한다."""
        configured_input = self._require_input()
        checkpoint_path = (
            configured_input.output_directory / "kind_workflow.checkpoint.json"
            if path is None
            else Path(path).resolve()
        )
        _write_json_file(checkpoint_path, self._build_checkpoint().to_dict())
        return checkpoint_path

    def _make_saved_file_callback(
        self,
        checkpoint_path: Path | None,
        user_callback: KindSavedFileCallback | None,
    ) -> KindSavedFileCallback:
        checkpoint = self._build_checkpoint()

        def _callback(
            output_path: Path,
            page_number: int | None,
            request_data: KindSearchFormData | None,
        ) -> None:
            resolved_output_path = str(output_path.resolve())
            checkpoint.saved_files.append(resolved_output_path)
            checkpoint.last_saved_file = resolved_output_path
            checkpoint.last_saved_page = page_number
            checkpoint.last_request_data = [] if request_data is None else list(request_data)
            checkpoint.completed = False
            if checkpoint_path is not None:
                _write_json_file(checkpoint_path, checkpoint.to_dict())
            if user_callback is not None:
                user_callback(output_path, page_number, request_data)

        return _callback

    def save_search_results(
        self,
        *,
        session: requests.Session | None = None,
        progress_callback: KindProgressCallback | None = None,
        saved_file_callback: KindSavedFileCallback | None = None,
        input_snapshot_path: str | Path | None = None,
        checkpoint_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """저장된 입력값으로 KIND raw response를 폴더에 저장한다."""
        configured_input = self._require_input()
        resolved_input_snapshot_path = (
            configured_input.output_directory / "kind_workflow.input.json"
            if input_snapshot_path is None
            else Path(input_snapshot_path).resolve()
        )
        ensure_download_directory_integrity(
            configured_input.output_directory,
            requested_page_size=configured_input.page_size,
            input_snapshot_path=resolved_input_snapshot_path,
        )
        resolved_input_snapshot_path = self.save_input_snapshot(resolved_input_snapshot_path)
        resolved_checkpoint_path = (
            configured_input.output_directory / "kind_workflow.checkpoint.json"
            if checkpoint_path is None
            else Path(checkpoint_path).resolve()
        )
        checkpoint = self._build_checkpoint()
        checkpoint.input = configured_input.to_dict()
        checkpoint.saved_files = []
        checkpoint.last_saved_file = None
        checkpoint.last_saved_page = None
        checkpoint.last_request_data = []
        checkpoint.completed = False
        _write_json_file(resolved_checkpoint_path, checkpoint.to_dict())
        download_pages(
            output_directory=configured_input.output_directory,
            request_headers=configured_input.request_headers,
            start_date=configured_input.start_date,
            end_date=configured_input.end_date,
            start_page=configured_input.start_page,
            end_page=configured_input.end_page,
            search_filters=configured_input.search_filters,
            disclosure_type_groups=configured_input.disclosure_type_groups,
            last_report_only=configured_input.last_report_only,
            include_previous_disclosures=configured_input.include_previous_disclosures,
            page_size=configured_input.page_size,
            wait_seconds_between_requests=configured_input.wait_seconds_between_requests,
            timeout=configured_input.timeout,
            session=session,
            progress_callback=progress_callback,
            saved_file_validator=make_page_size_integrity_validator(
                expected_page_size=configured_input.page_size
            ),
            saved_file_callback=self._make_saved_file_callback(
                resolved_checkpoint_path,
                saved_file_callback,
            ),
        )
        checkpoint.completed = True
        _write_json_file(resolved_checkpoint_path, checkpoint.to_dict())
        return {
            "input": configured_input.to_dict(),
            "request_data": self.build_request_data(page_number=configured_input.start_page),
            "saved_files": [
                str(path)
                for path in sorted(configured_input.output_directory.glob("*.body"))
            ],
            "input_snapshot_path": str(resolved_input_snapshot_path),
            "checkpoint_path": str(resolved_checkpoint_path),
        }

    def run(
        self,
        *,
        output_directory: str | Path,
        request_headers: Mapping[str, object],
        start_date: str = "",
        end_date: str = "",
        start_page: int = 1,
        end_page: int = 1,
        search_filters: KindSearchFilters = None,
        disclosure_type_groups: Mapping[DisclosureTypeGroupKey, DisclosureTypeGroupValue] | None = None,
        last_report_only: bool | None = None,
        include_previous_disclosures: bool | None = None,
        page_size: int = 100,
        wait_seconds_between_requests: float = 1.0,
        timeout: float = 20.0,
        parse_mode: ParseMode = "tables",
        save: bool = True,
        session: requests.Session | None = None,
        progress_callback: KindProgressCallback | None = None,
        saved_file_callback: KindSavedFileCallback | None = None,
        input_snapshot_path: str | Path | None = None,
        checkpoint_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """입력을 저장하고, 필요하면 바로 KIND raw response를 내려받는다."""
        configured_input = self.configure(
            output_directory=output_directory,
            request_headers=request_headers,
            start_date=start_date,
            end_date=end_date,
            start_page=start_page,
            end_page=end_page,
            search_filters=search_filters,
            disclosure_type_groups=disclosure_type_groups,
            last_report_only=last_report_only,
            include_previous_disclosures=include_previous_disclosures,
            page_size=page_size,
            wait_seconds_between_requests=wait_seconds_between_requests,
            timeout=timeout,
            parse_mode=parse_mode,
        )
        result = {
            "input": configured_input.to_dict(),
            "request_data": self.build_request_data(page_number=configured_input.start_page),
            "saved_files": [],
            "input_snapshot_path": None,
            "checkpoint_path": None,
        }
        if not save:
            return result
        return self.save_search_results(
            session=session,
            progress_callback=progress_callback,
            saved_file_callback=saved_file_callback,
            input_snapshot_path=input_snapshot_path,
            checkpoint_path=checkpoint_path,
        )


_DEFAULT_WORKFLOW = KindWorkflow()


def run_download(
    *,
    output_directory: str | Path,
    request_headers: Mapping[str, object],
    start_date: str = "",
    end_date: str = "",
    start_page: int = 1,
    end_page: int = 1,
    search_filters: KindSearchFilters = None,
    disclosure_type_groups: Mapping[DisclosureTypeGroupKey, DisclosureTypeGroupValue] | None = None,
    last_report_only: bool | None = None,
    include_previous_disclosures: bool | None = None,
    page_size: int = 100,
    wait_seconds_between_requests: float = 1.0,
    timeout: float = 20.0,
    parse_mode: ParseMode = "tables",
    save: bool = True,
    session: requests.Session | None = None,
    progress_callback: KindProgressCallback | None = None,
    saved_file_callback: KindSavedFileCallback | None = None,
    input_snapshot_path: str | Path | None = None,
    checkpoint_path: str | Path | None = None,
) -> dict[str, Any]:
    """기본 KIND workflow instance로 입력을 저장하고 필요하면 다운로드한다."""
    return _DEFAULT_WORKFLOW.run(
        output_directory=output_directory,
        request_headers=request_headers,
        start_date=start_date,
        end_date=end_date,
        start_page=start_page,
        end_page=end_page,
        search_filters=search_filters,
        disclosure_type_groups=disclosure_type_groups,
        last_report_only=last_report_only,
        include_previous_disclosures=include_previous_disclosures,
        page_size=page_size,
        wait_seconds_between_requests=wait_seconds_between_requests,
        timeout=timeout,
        parse_mode=parse_mode,
        save=save,
        session=session,
        progress_callback=progress_callback,
        saved_file_callback=saved_file_callback,
        input_snapshot_path=input_snapshot_path,
        checkpoint_path=checkpoint_path,
    )


__all__ = [
    "KindCompanyClassificationIntegrityError",
    "KindCompanyClassificationIntegrityReport",
    "KindCompanyClassificationResult",
    "KindModeBatchResult",
    "KindSearchFilters",
    "KindWorkflow",
    "KindWorkflowCheckpoint",
    "KindWorkflowInput",
    "diagnose_kind_company_classification_integrity",
    "download_kind_viewer_htmls_from_result_folder",
    "ensure_download_directory_integrity",
    "export_kind_company_classification",
    "export_kind_mode_batch",
    "export_kind_mode_folder",
    "export_kind_mode_folders",
    "inspect_download_directory_pages",
    "make_page_size_integrity_validator",
    "run_download",
    "validate_download_directory_page_size",
    "validate_downloaded_result_page",
]
