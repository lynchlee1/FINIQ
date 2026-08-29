"""Safe compatibility orchestrator for the seven disclosure stages.

The existing stage implementations remain the source of truth.  This module adds a
small, fixed seven-stage coordinator, yearly KIND discovery, and durable
stage checkpoints for the new Web UI.  It intentionally is not a generic DAG.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from finiq.concurrency import resolve_worker_count
from finiq.data_scraper.core.client import _is_valid_html
from finiq.data_scraper.core.kind_computers import normalize_kind_proxy_urls
from finiq.data_scraper.parse import disclosure_file_rows, pagination_info
from finiq.data_scraper.workflow import inspect_download_directory_pages
from finiq.market_desk.sqlite_generation import sqlite_generation_locked

from finiq.market_desk.web.features.disclosures.internal_html_download import (
    _collect_internal_targets_from_compressed_payload,
    download_disclosure_internal_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_cleanup import (
    check_disclosure_html_output_directory_payload,
)
from finiq.market_desk.web.features.disclosures.html_common import (
    _hash_html_files,
    _load_html_manifest_integrity,
    _year_from_disclosure,
)
from finiq.market_desk.web.features.disclosures.external_compact import (
    _verify_compressed_external_html_files,
)
from finiq.market_desk.web.features.disclosures.external_html_download import (
    download_disclosure_external_html_payload,
)
from finiq.market_desk.web.features.disclosures.external_html_compress import (
    compress_disclosure_external_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_common import (
    PARSER_REGISTRY,
    _collect_html_files as _collect_parse_html_files,
    parse_disclosure_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_sections import (
    inspect_disclosure_html_section_output_payload,
    save_disclosure_html_sections_payload,
)
from finiq.market_desk.web.features.disclosures.table_export import (
    build_disclosure_table_payload,
)
from finiq.market_desk.web.features.disclosures.filter_presets import (
    begin_filter_workflow_payload,
    complete_filter_workflow_payload,
    fail_filter_workflow_payload,
    filter_workflow_path,
    interrupt_filter_workflow_payload,
    load_filter_workflow_result_payload,
    mark_filter_workflow_query_completed,
)
from finiq.market_desk.web.features.downloads.kind_runner import _run_single
from finiq.market_desk.web.features.downloads.kind_common import (
    _download_input_snapshot_from_payload,
    _require_current_download_input_snapshot,
    _split_yearly_ranges,
)
from finiq.market_desk.web.features.downloads.kind_coordination import (
    KIND_NETWORK_JOB_LOCK,
)
from finiq.market_desk.web.features.downloads.kind_existing import (
    check_existing_downloads,
)
from finiq.market_desk.web.features.market_data.service_payloads import (
    filter_disclosures_payload,
)
from finiq.market_desk.web.features.market_data.service_records import FilterCancelled
from finiq.market_desk.web.features.market_data.service_sources import (
    _load_sqlite_manifest,
    _validate_sqlite_manifest_counts,
)

from .layout import (
    DisclosureWorkspace,
    atomic_write_json,
    resolve_disclosure_workspace,
    validate_workspace_mode,
)


AUTOMATION_PROFILE_FORMAT = "finiq_disclosure_automation_profile_v1"
AUTOMATION_CHECKPOINT_FORMAT = "finiq_disclosure_automation_checkpoint_v1"
AUTOMATION_WINDOW_FORMAT = "finiq_disclosure_automation_window_v1"
AUTOMATION_SECTIONS_FORMAT = "finiq_disclosure_automation_sections_v1"
AUTOMATION_EXTERNAL_FORMAT = "finiq_disclosure_automation_external_html_download_v1"
AUTOMATION_INTERNAL_FORMAT = "finiq_disclosure_automation_internal_html_download_v1"
STAGE_NUMBERS = tuple(range(1, 8))
STAGE_KEYS = {
    1: "s1_download",
    2: "s2_table",
    3: "s3_filter",
    4: "s4_external_html_download",
    5: "s5_internal_html_download",
    6: "s6_sections",
    7: "s7_parse",
}
STAGE_LABELS = {
    1: "공시내역 다운로드",
    2: "공시내역 변환",
    3: "공시내역 필터링",
    4: "공시원문 외부 저장",
    5: "공시원문 내부 저장",
    6: "공시원문 목차 분리",
    7: "공시원문 변환",
}
KIND_AUTOMATION_MAX_REQUESTS_PER_MINUTE = 45
KIND_AUTOMATION_CONTENT_REQUESTS_PER_MINUTE = 30
KIND_AUTOMATION_WAIT_SECONDS = 60.0 / KIND_AUTOMATION_MAX_REQUESTS_PER_MINUTE
ProgressCallback = Callable[[str], None]
CancelCheck = Callable[[], bool]


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _iso_date(value: Any, key: str) -> date:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{key} must be YYYY-MM-DD") from exc


def _positive_int(value: Any, key: str, default: int, maximum: int) -> int:
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc
    if parsed < 1 or parsed > maximum:
        raise ValueError(f"{key} must be between 1 and {maximum}")
    return parsed


def normalize_automation_profile(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("profile must be an object")
    data_root_text = str(payload.get("data_root") or "").strip()
    if not data_root_text:
        raise ValueError("data_root is required")
    data_root = resolve_disclosure_workspace(data_root_text).root

    raw_steps = payload.get("steps")
    if raw_steps is None:
        raw_steps = {}
    if not isinstance(raw_steps, dict):
        raise ValueError("steps must be an object")
    steps = {
        STAGE_KEYS[number]: bool(raw_steps.get(STAGE_KEYS[number], True))
        for number in STAGE_NUMBERS
    }
    if not any(steps.values()):
        raise ValueError("at least one stage must be enabled")

    raw_mask = payload.get("execution_mask")
    if raw_mask is None:
        execution_mask = [
            number for number in STAGE_NUMBERS if steps[STAGE_KEYS[number]]
        ]
    elif not isinstance(raw_mask, list):
        raise ValueError("execution_mask must be a list")
    else:
        try:
            execution_mask = sorted({int(item) for item in raw_mask})
        except (TypeError, ValueError) as exc:
            raise ValueError("execution_mask must contain stage numbers") from exc
        if any(number not in STAGE_NUMBERS for number in execution_mask):
            raise ValueError("execution_mask must contain stage numbers 1 through 7")

    decisions = payload.get("decisions") or {}
    if not isinstance(decisions, dict):
        raise ValueError("decisions must be an object")
    raw_search = decisions.get("s1_search") or {}
    raw_selection = decisions.get("s3_selection") or {}
    raw_sections = decisions.get("s6_sections") or {}
    if not all(
        isinstance(item, dict)
        for item in (raw_search, raw_selection, raw_sections)
    ):
        raise ValueError("stage decisions must be objects")

    start_date = _iso_date(raw_search.get("start_date"), "start_date")
    end_date_value = str(raw_search.get("end_date") or "").strip()
    end_date = date.today() if not end_date_value else _iso_date(end_date_value, "end_date")
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    if bool(raw_search.get("last_report_only")):
        raise ValueError("공시 자동화에서는 최종보고서만 옵션을 사용할 수 없습니다.")

    disclosure_groups = raw_search.get("disclosure_type_groups") or {}
    if not isinstance(disclosure_groups, dict):
        raise ValueError("disclosure_type_groups must be an object")
    normalized_groups = {
        str(key): sorted(
            {
                str(code).strip()
                for code in value
                if str(code).strip()
            }
        )
        for key, value in disclosure_groups.items()
        if isinstance(value, list)
    }

    filter_blocks = raw_selection.get("filter_blocks") or []
    if not isinstance(filter_blocks, list):
        raise ValueError("filter_blocks must be a list")
    execution = payload.get("execution") or {}
    if not isinstance(execution, dict):
        raise ValueError("execution must be an object")
    mode = validate_workspace_mode(execution.get("mode"))
    parser_method = str(execution.get("parser_method") or "").strip()
    if parser_method not in PARSER_REGISTRY:
        raise ValueError("unsupported parser_method")
    return {
        "format": AUTOMATION_PROFILE_FORMAT,
        "name": str(payload.get("name") or "공시 자동화").strip() or "공시 자동화",
        "data_root": str(data_root),
        "steps": steps,
        "execution_mask": execution_mask,
        "decisions": {
            "s1_search": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "company_name": str(raw_search.get("company_name") or "").strip(),
                "submitter_name": str(raw_search.get("submitter_name") or "").strip(),
                "market_label": str(raw_search.get("market_label") or "전체").strip()
                or "전체",
                "securities_label": str(
                    raw_search.get("securities_label") or "전체"
                ).strip()
                or "전체",
                "disclosure_type_groups": normalized_groups,
                "last_report_only": False,
            },
            "s3_selection": {
                "filter_blocks": filter_blocks,
            },
            "s6_sections": {
                "unmatched_policy": "automatic",
                "section_save_rules": {},
            },
        },
        "execution": {
            "mode": mode,
            "parser_method": parser_method,
            "page_size": _positive_int(
                execution.get("page_size"), "page_size", 100, 100
            ),
            "timeout": _positive_int(execution.get("timeout"), "timeout", 20, 120),
            "local_workers": resolve_worker_count(
                execution.get("local_workers"),
                field_name="local_workers",
            ),
            "progress_interval": _positive_int(
                execution.get("progress_interval"),
                "progress_interval",
                25,
                10_000,
            ),
            "max_requests_per_minute": KIND_AUTOMATION_MAX_REQUESTS_PER_MINUTE,
            "kind_proxy_urls": normalize_kind_proxy_urls(
                execution.get("kind_proxy_urls")
            ),
        },
        "download_confirmation": str(
            payload.get("download_confirmation") or ""
        ).strip(),
    }


def _automation_root(profile: dict[str, Any]) -> Path:
    return Path(profile["data_root"]) / ".finiq" / "disclosure-automation"


def _profile_workspace(profile: dict[str, Any]) -> DisclosureWorkspace:
    return resolve_disclosure_workspace(profile["data_root"])


def _external_mode_directory(profile: dict[str, Any]) -> Path:
    return _profile_workspace(profile).external_mode(
        validate_workspace_mode(profile["execution"]["mode"])
    )


def _external_compress_mode_directory(profile: dict[str, Any]) -> Path:
    return _profile_workspace(profile).external_compress_mode(
        validate_workspace_mode(profile["execution"]["mode"])
    )


def _internal_mode_directory(profile: dict[str, Any]) -> Path:
    return _profile_workspace(profile).internal_mode(
        validate_workspace_mode(profile["execution"]["mode"])
    )


def _sections_mode_directory(profile: dict[str, Any]) -> Path:
    return _profile_workspace(profile).sections_mode(
        validate_workspace_mode(profile["execution"]["mode"])
    )


def _prepare_automation_output_directories(
    profile: dict[str, Any],
    stages: list[dict[str, Any]],
) -> None:
    workspace = _profile_workspace(profile)
    mode = validate_workspace_mode(profile["execution"]["mode"])
    for stage_plan in stages:
        if stage_plan["plan_action"] != "process":
            continue
        stage = int(stage_plan["stage"])
        if stage == 1:
            directory = workspace.list
        elif stage == 2:
            directory = workspace.table
        elif stage == 3:
            directory = workspace.filtered / mode
        elif stage == 4:
            workspace.external_mode(mode).mkdir(parents=True, exist_ok=True)
            directory = workspace.external_compress_mode(mode)
        elif stage == 5:
            directory = workspace.internal_mode(mode)
        elif stage == 6:
            directory = workspace.sections_mode(mode)
        elif stage == 7:
            directory = workspace.converted_mode(mode)
        else:
            raise ValueError(f"unsupported stage: {stage}")
        directory.mkdir(parents=True, exist_ok=True)


def _checkpoint_path(profile: dict[str, Any], stage: int) -> Path:
    return _automation_root(profile) / "checkpoints" / f"stage-{stage}.json"


def _stage_config_hash(profile: dict[str, Any], stage: int) -> str:
    decisions = profile["decisions"]
    semantic: dict[str, Any] = {
        "stage": stage,
    }
    if stage >= 1:
        semantic["s1_search"] = decisions["s1_search"]
    if stage >= 3:
        semantic["s3_selection"] = decisions["s3_selection"]
    if stage >= 6:
        semantic["s6_sections"] = {"unmatched_policy": "automatic"}
        semantic["mode"] = profile["execution"]["mode"]
    if stage >= 7:
        semantic["parser_method"] = profile["execution"]["parser_method"]
    return _canonical_hash(semantic)


def _stage_output_paths(profile: dict[str, Any], stage: int) -> list[Path]:
    workspace = _profile_workspace(profile)
    mode = profile["execution"]["mode"]
    if stage == 1:
        return [workspace.list / ".automation-windows"]
    if stage == 2:
        return [workspace.table]
    if stage == 3:
        return [
            filter_workflow_path(workspace.root, mode),
            workspace.filtered / mode / "filtered.json",
        ]
    if stage == 4:
        return [
            _external_compress_mode_directory(profile)
            / "compressed-external-html.json",
            _external_mode_directory(profile) / ".automation-current",
        ]
    if stage == 5:
        return [_internal_mode_directory(profile) / ".automation-current"]
    if stage == 6:
        return [_sections_mode_directory(profile) / ".automation-current"]
    if stage == 7:
        return [workspace.converted / mode / f"parsed-{mode}.json"]
    raise ValueError(f"unsupported stage: {stage}")


def _stage_output_fingerprint(profile: dict[str, Any], stage: int) -> str:
    snapshots: list[dict[str, Any]] = []
    for output_index, output_path in enumerate(_stage_output_paths(profile, stage)):
        if output_path.is_file():
            stat = output_path.stat()
            snapshots.append(
                {
                    "output": output_index,
                    "path": ".",
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
            continue
        if not output_path.is_dir():
            snapshots.append({"output": output_index, "missing": True})
            continue
        for child in sorted(output_path.rglob("*")):
            relative_path = child.relative_to(output_path).as_posix()
            if child.is_symlink():
                snapshots.append(
                    {
                        "output": output_index,
                        "path": relative_path,
                        "symlink": str(child.readlink()),
                    }
                )
            elif child.is_file():
                stat = child.stat()
                snapshots.append(
                    {
                        "output": output_index,
                        "path": relative_path,
                        "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                    }
                )
    return _canonical_hash(snapshots)


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _inspection_success(
    stage: int, *, reason: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "stage": stage,
        "label": STAGE_LABELS[stage],
        "confirmed": True,
        "reason": reason,
        "details": details or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _inspection_failure(
    stage: int, *, reason: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "stage": stage,
        "label": STAGE_LABELS[stage],
        "confirmed": False,
        "reason": reason,
        "details": details or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _detail_download_payload(profile: dict[str, Any]) -> dict[str, Any]:
    search = profile["decisions"]["s1_search"]
    return {
        "output_directory": str(_profile_workspace(profile).list),
        "mode": "yearly",
        "start_date": search["start_date"],
        "end_date": search["end_date"],
        "company_name": search["company_name"],
        "submitter_name": search["submitter_name"],
        "market_label": search["market_label"],
        "securities_label": search["securities_label"],
        "disclosure_type_groups": search["disclosure_type_groups"],
        "last_report_only": False,
        "page_size": profile["execution"]["page_size"],
        "worker_count": profile["execution"]["local_workers"],
        "wait_seconds": KIND_AUTOMATION_WAIT_SECONDS,
        "timeout": profile["execution"]["timeout"],
    }


def _snapshot_semantics(snapshot: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "start_date",
        "end_date",
        "page_size",
        "search_filters",
        "disclosure_type_groups",
        "last_report_only",
        "include_previous_disclosures",
        "wait_seconds_between_requests",
        "timeout",
    )
    return {key: snapshot.get(key) for key in keys}


def _inspect_detail_download(profile: dict[str, Any]) -> dict[str, Any]:
    payload = _detail_download_payload(profile)
    root = Path(payload["output_directory"])
    start = date.fromisoformat(payload["start_date"])
    end = date.fromisoformat(payload["end_date"])
    ranges = _split_yearly_ranges(start, end)
    expected_folders = {
        root / f"{range_start:%Y%m%d}_{range_end:%Y%m%d}"
        for range_start, range_end in ranges
    }
    actual_folders = {
        child
        for child in root.iterdir()
        if child.is_dir()
        and len(child.name) == 17
        and child.name[8] == "_"
        and child.name.replace("_", "").isdigit()
    } if root.is_dir() else set()
    if actual_folders != expected_folders:
        return _inspection_failure(
            1,
            reason="현재 날짜 범위와 다운로드 폴더 범위가 일치하지 않습니다.",
            details={
                "expected_folders": sorted(path.name for path in expected_folders),
                "actual_folders": sorted(path.name for path in actual_folders),
            },
        )

    for range_start, range_end in ranges:
        folder = root / f"{range_start:%Y%m%d}_{range_end:%Y%m%d}"
        snapshot = _require_current_download_input_snapshot(folder)
        expected_snapshot = _download_input_snapshot_from_payload(
            payload,
            start=range_start,
            end=range_end,
            page_size=int(payload["page_size"]),
        )
        if _snapshot_semantics(snapshot or {}) != _snapshot_semantics(
            expected_snapshot
        ):
            return _inspection_failure(
                1,
                reason=f"{folder.name}의 다운로드 설정이 현재 실행 설정과 다릅니다.",
                details={
                    "expected": _snapshot_semantics(expected_snapshot),
                    "actual": _snapshot_semantics(snapshot or {}),
                },
            )

    with KIND_NETWORK_JOB_LOCK:
        existing = check_existing_downloads(
            str(root),
            verify_with_kind=True,
            current_payload=payload,
            parallel_workers=profile["execution"]["local_workers"],
        )
    statuses = list(existing.get("ranges") or [])
    if len(statuses) != len(expected_folders):
        return _inspection_failure(
            1,
            reason="다운로드 완료 범위를 모두 확인할 수 없습니다.",
            details={"expected_ranges": len(expected_folders), "actual_ranges": len(statuses)},
        )
    failed = [item for item in statuses if item.get("status") != "validated"]
    if failed:
        first = failed[0]
        return _inspection_failure(
            1,
            reason=str(first.get("error_detail") or "다운로드 무결성 검사에 실패했습니다."),
            details={"failed_ranges": failed},
        )
    return _inspection_success(
        1,
        reason="현재 검색 설정과 일치하며 모든 페이지와 KIND 현재 건수를 확인했습니다.",
        details={
            "ranges": len(statuses),
            "local_count": sum(int(item.get("local_count") or 0) for item in statuses),
            "kind_count": sum(int(item.get("kind_count") or 0) for item in statuses),
        },
    )


def _automation_window_snapshot(
    profile: dict[str, Any], window_start: date, window_end: date
) -> dict[str, Any]:
    search = profile["decisions"]["s1_search"]
    return _download_input_snapshot_from_payload(
        {
            "company_name": search["company_name"],
            "submitter_name": search["submitter_name"],
            "market_label": search["market_label"],
            "securities_label": search["securities_label"],
            "disclosure_type_groups": search["disclosure_type_groups"],
            "last_report_only": False,
            "wait_seconds": KIND_AUTOMATION_WAIT_SECONDS,
            "timeout": profile["execution"]["timeout"],
        },
        start=window_start,
        end=window_end,
        page_size=profile["execution"]["page_size"],
    )


def _inspect_automation_download(profile: dict[str, Any]) -> dict[str, Any]:
    with KIND_NETWORK_JOB_LOCK:
        inspected = _inspect_stage_one_downloads(
            profile,
            progress_callback=None,
            cancel_check=lambda: False,
        )
    conflicts = inspected["conflicts"]
    if conflicts:
        return _inspection_failure(
            1,
            reason=str(conflicts[0]["reason"]),
            details={"conflicts": conflicts},
        )
    return _inspection_success(
        1,
        reason="기존 연도별 다운로드와 KIND 1페이지의 전체 페이지 수가 같습니다.",
        details={
            "checked_ranges": inspected["checked_ranges"],
            "ranges": len(inspected["ranges"]),
        },
    )


def _table_manifest(profile: dict[str, Any]) -> Path:
    path = _profile_workspace(profile).table / "sqlite_manifest.json"
    try:
        manifest = _load_sqlite_manifest(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("공시내역 변환 기록을 찾을 수 없습니다.") from error
    if manifest.get("source_type") != "source_folder":
        raise ValueError("공시내역 변환 기록을 찾을 수 없습니다.")
    return path


def _filter_result_path(profile: dict[str, Any]) -> Path:
    return (
        _profile_workspace(profile).filtered
        / profile["execution"]["mode"]
        / "filtered.json"
    )


def _filter_signature(payload: dict[str, Any]) -> str:
    filters = dict(payload.get("filters") or {})
    filters.pop("filter_workers", None)
    return _canonical_hash(
        {
            "format": payload.get("format"),
            "source_type": payload.get("source_type"),
            "filters": filters,
            "summary": payload.get("summary"),
            "disclosures": payload.get("disclosures"),
            "external_html_download_acpt_numbers": payload.get("external_html_download_acpt_numbers"),
        }
    )


def _html_inspection_details(payload: dict[str, Any]) -> dict[str, Any]:
    count_keys = (
        "requested_count",
        "existing_target_html_count",
        "missing_target_html_count",
        "invalid_target_html_count",
        "unexpected_file_count",
        "total_file_count",
    )
    list_keys = (
        "missing_target_acpt_numbers",
        "invalid_target_acpt_numbers",
        "unexpected_files",
    )
    return {
        **{key: int(payload.get(key) or 0) for key in count_keys},
        **{
            key: list(payload.get(key) or [])[:20]
            for key in list_keys
            if payload.get(key)
        },
    }


@sqlite_generation_locked
def _inspect_detail_table(profile: dict[str, Any]) -> dict[str, Any]:
    root = Path(profile["data_root"])
    manifest_path = _table_manifest(profile)
    manifest = _load_sqlite_manifest(manifest_path)
    _validate_sqlite_manifest_counts(
        manifest_path,
        manifest,
        filter_workers=profile["execution"]["local_workers"],
    )
    table_result = filter_disclosures_payload(
        {
            "data_root": str(root),
            "filter_blocks": [],
            "filter_workers": profile["execution"]["local_workers"],
        }
    )
    table_summary = table_result.get("summary") or {}
    manifest_summary = manifest.get("summary") or {}
    source_count = int(manifest_summary.get("source_rows") or 0)
    source_duplicate_count = int(manifest_summary.get("duplicate_rows") or 0)
    manifest_disclosures = int(manifest_summary.get("disclosures") or 0)
    table_count = int(table_summary.get("source_disclosures") or 0)
    table_duplicate_count = int(table_summary.get("duplicate_disclosures") or 0)
    if (
        source_count != manifest_disclosures + source_duplicate_count
        or table_count != manifest_disclosures
        or table_duplicate_count != 0
        or len(table_result.get("disclosures") or []) != manifest_disclosures
    ):
        return _inspection_failure(
            2,
            reason="다운로드한 원본 데이터와 SQLite 파일의 공시 내용이 일치하지 않습니다.",
            details={
                "source_rows": source_count,
                "source_duplicate_rows": source_duplicate_count,
                "table_rows": table_count,
                "table_duplicate_rows": table_duplicate_count,
                "table_records": len(table_result.get("disclosures") or []),
            },
        )
    return _inspection_success(
        2,
        reason="다운로드한 원본 데이터와 변환 기록, 연도별 SQLite 파일의 내용이 모두 일치합니다.",
        details={
            "source_rows": source_count,
            "duplicate_rows": source_duplicate_count,
            "records": len(table_result.get("disclosures") or []),
        },
    )


@sqlite_generation_locked
def _inspect_detail_filter(profile: dict[str, Any]) -> dict[str, Any]:
    root = Path(profile["data_root"])
    output_path = _filter_result_path(profile)
    actual = _read_json_object(output_path)
    if actual is None:
        return _inspection_failure(3, reason="필터 결과 JSON이 없거나 손상되었습니다.")
    selection = profile["decisions"]["s3_selection"]
    try:
        expected = load_filter_workflow_result_payload(
            data_root=root,
            mode=profile["execution"]["mode"],
            condition_blocks=selection["filter_blocks"],
        )
    except ValueError as error:
        return _inspection_failure(3, reason=str(error))
    manifest = _load_sqlite_manifest(_table_manifest(profile))
    current_source_count = int((manifest.get("summary") or {}).get("disclosures") or 0)
    saved_source_count = int((expected.get("summary") or {}).get("source_disclosures") or 0)
    if current_source_count != saved_source_count:
        return _inspection_failure(
            3,
            reason="현재 SQLite 원본 건수와 조건검색 정본의 검사 완료 건수가 다릅니다.",
            details={
                "current_source_records": current_source_count,
                "saved_source_records": saved_source_count,
            },
        )
    if _filter_signature(actual) != _filter_signature(expected):
        return _inspection_failure(
            3,
            reason="조건검색 정본과 04단계 전달 파일의 결과가 다릅니다.",
            details={
                "expected_records": len(expected.get("disclosures") or []),
                "actual_records": len(actual.get("disclosures") or []),
            },
        )
    return _inspection_success(
        3,
        reason="조건검색 정본, 입력 SQLite 건수와 04단계 전달 파일이 일치합니다.",
        details={"records": len(actual.get("disclosures") or [])},
    )


def _inspect_detail_external_html(profile: dict[str, Any]) -> dict[str, Any]:
    root = Path(profile["data_root"])
    mode = profile["execution"]["mode"]
    output_directory = _external_mode_directory(profile)
    compressed_directory = _external_compress_mode_directory(profile)
    expected_acpt_numbers = [
        acpt_no for acpt_no, _year in _active_workspace_disclosure_targets(root, mode)
    ]
    if not expected_acpt_numbers:
        compressed = _read_json_object(
            compressed_directory / "compressed-external-html.json"
        )
        html_files = (
            [
                path
                for path in output_directory.rglob("*.html")
                if not any(
                    part.startswith(".")
                    for part in path.relative_to(output_directory).parts[:-1]
                )
            ]
            if output_directory.is_dir()
            else []
        )
        if compressed == {
            "format": "finiq_disclosure_external_html_docs_v1",
            "summary": {"found_files": 0, "compressed_files": 0},
            "records": [],
        } and not html_files:
            return _inspection_success(
                4,
                reason="현재 필터 대상이 0건이며 외부 HTML 결과도 비어 있습니다.",
                details={"records": 0},
            )
        return _inspection_failure(
            4,
            reason="현재 필터 대상은 0건이지만 외부 HTML 결과가 비어 있지 않습니다.",
        )
    checked = check_disclosure_html_output_directory_payload(
        {
            "data_root": str(root),
            "mode": mode,
            "output_directory": str(output_directory),
        }
    )
    requested = int(checked.get("requested_count") or 0)
    if (
        int(checked.get("missing_target_html_count") or 0)
        or int(checked.get("invalid_target_html_count") or 0)
        or int(checked.get("unexpected_file_count") or 0)
        or int(checked.get("existing_target_html_count") or 0) != requested
    ):
        return _inspection_failure(
            4,
            reason="외부 HTML에 누락·손상 또는 현재 대상이 아닌 파일이 있습니다.",
            details=_html_inspection_details(checked),
        )
    compressed_path = compressed_directory / "compressed-external-html.json"
    verification = _verify_compressed_external_html_files(
        written_files=[str(compressed_path)],
        expected_acpt_numbers=list(checked.get("existing_target_acpt_numbers") or []),
    )
    if not verification.get("passed"):
        return _inspection_failure(
            4,
            reason="외부 HTML 압축 JSON의 대상이 현재 필터 결과와 다릅니다.",
            details=verification,
        )
    saved_compressed = _read_json_object(compressed_path)
    with tempfile.TemporaryDirectory(prefix="finiq-external-inspection-") as temporary:
        compress_disclosure_external_html_payload(
            {
                "input_directory": str(output_directory),
                "output_directory": temporary,
                "parallel_workers": profile["execution"]["local_workers"],
            }
        )
        rebuilt_compressed = _read_json_object(
            Path(temporary) / "compressed-external-html.json"
        )
    if saved_compressed != rebuilt_compressed:
        return _inspection_failure(
            4,
            reason="외부 HTML을 현재 압축 로직으로 다시 계산한 결과와 저장된 JSON이 다릅니다.",
        )
    return _inspection_success(
        4,
        reason="현재 필터 대상의 외부 HTML과 압축 JSON이 모두 완전합니다.",
        details={"records": requested},
    )


def _inspect_detail_internal_html(profile: dict[str, Any]) -> dict[str, Any]:
    root = Path(profile["data_root"])
    checked = check_disclosure_html_output_directory_payload(
        {
            "source_compressed_json_path": str(
                _external_compress_mode_directory(profile)
                / "compressed-external-html.json"
            ),
            "output_directory": str(
                _internal_mode_directory(profile) / ".automation-current"
            ),
        }
    )
    requested = int(checked.get("requested_count") or 0)
    if (
        int(checked.get("missing_target_html_count") or 0)
        or int(checked.get("invalid_target_html_count") or 0)
        or int(checked.get("unexpected_file_count") or 0)
        or int(checked.get("existing_target_html_count") or 0) != requested
    ):
        return _inspection_failure(
            5,
            reason="내부 HTML에 누락·손상 또는 현재 대상이 아닌 파일이 있습니다.",
            details=_html_inspection_details(checked),
        )
    return _inspection_success(
        5,
        reason="현재 외부 HTML 대상의 내부 HTML이 모두 완전합니다.",
        details={"records": requested},
    )


def _inspect_detail_sections(profile: dict[str, Any]) -> dict[str, Any]:
    workspace = _profile_workspace(profile)
    checked = inspect_disclosure_html_section_output_payload(
        {
            "input_directory": str(
                _internal_mode_directory(profile) / ".automation-current"
            ),
            "output_directory": str(
                _sections_mode_directory(profile) / ".automation-current"
            ),
            "workers": profile["execution"]["local_workers"],
        }
    )
    summary = checked.get("summary") or {}
    if not summary.get("integrity_ok"):
        return _inspection_failure(
            6,
            reason="현재 자동 목차 분리 결과와 저장된 HTML이 다릅니다.",
            details={
                "summary": summary,
                "problem_files": list(checked.get("problem_files") or [])[:20],
                "missing_files": list(checked.get("missing_files") or [])[:20],
                "unexpected_files": list(checked.get("unexpected_files") or [])[:20],
                "mismatched_files": list(checked.get("mismatched_files") or [])[:20],
            },
        )
    return _inspection_success(
        6,
        reason="자동 목차 분리 결과와 모든 저장 HTML 내용이 일치합니다.",
        details={"records": int(summary.get("actual_files") or 0)},
    )


def _inspect_detail_parse(profile: dict[str, Any]) -> dict[str, Any]:
    root = Path(profile["data_root"])
    workspace = _profile_workspace(profile)
    mode = profile["execution"]["mode"]
    path = workspace.converted / mode / f"parsed-{mode}.json"
    payload = _read_json_object(path)
    if payload is None or payload.get("format") != "finiq_disclosure_html_parse_v1":
        return _inspection_failure(7, reason="공시원문 변환 결과가 없거나 손상되었습니다.")
    input_directory = (
        _sections_mode_directory(profile) / ".automation-current"
    ).resolve()
    filters = payload.get("filter_settings") or {}
    html_files = (
        _collect_parse_html_files(input_directory, None)
        if input_directory.is_dir()
        else []
    )
    records = list(payload.get("records") or [])
    errors = list(payload.get("errors") or [])
    summary = payload.get("summary") or {}
    expected_acpt_numbers = sorted(path.stem for path in html_files)
    actual_acpt_numbers = sorted(
        str(record.get("acpt_no") or "")
        for record in records
        if isinstance(record, dict)
    )
    valid = (
        payload.get("mode") == mode
        and not payload.get("cancelled")
        and filters.get("filter_blocks") in (None, [])
        and filters.get("record_filters") in (None, [])
        and not errors
        and int(summary.get("found_files") or 0) == len(html_files)
        and int(summary.get("parsed_files") or 0) == len(records)
        and int(summary.get("failed_files") or 0) == 0
        and actual_acpt_numbers == expected_acpt_numbers
    )
    if not valid:
        return _inspection_failure(
            7,
            reason="현재 파서 설정·입력 HTML과 저장된 변환 결과가 일치하지 않습니다.",
            details={
                "expected_files": len(html_files),
                "parsed_files": len(records),
                "failed_files": len(errors),
            },
        )
    if html_files and path.stat().st_mtime_ns < max(item.stat().st_mtime_ns for item in html_files):
        return _inspection_failure(
            7,
            reason="목차 HTML이 변환 결과보다 나중에 수정되어 다시 변환해야 합니다.",
        )
    with tempfile.TemporaryDirectory(prefix="finiq-parse-inspection-") as temporary:
        rebuilt = parse_disclosure_html_payload(
            {
                "data_root": str(root),
                "mode": mode,
                "parser_method": profile["execution"]["parser_method"],
                "input_directory": str(input_directory),
                "output_directory": temporary,
                "filtered_metadata_path": str(_filter_result_path(profile)),
                "compressed_metadata_path": str(
                    _external_compress_mode_directory(profile)
                    / "compressed-external-html.json"
                ),
                "parallel_workers": profile["execution"]["local_workers"],
                "skip_errors": False,
            }
        )
    if payload != rebuilt:
        return _inspection_failure(
            7,
            reason="현재 파서로 다시 계산한 결과와 저장된 변환 결과가 다릅니다.",
            details={
                "expected_records": len(rebuilt.get("records") or []),
                "actual_records": len(records),
            },
        )
    return _inspection_success(
        7,
        reason="변환 설정과 입력 HTML, 저장된 결과가 모두 일치합니다.",
        details={"records": len(records)},
    )


DETAIL_STAGE_INSPECTORS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    1: _inspect_detail_download,
    2: _inspect_detail_table,
    3: _inspect_detail_filter,
    4: _inspect_detail_external_html,
    5: _inspect_detail_internal_html,
    6: _inspect_detail_sections,
    7: _inspect_detail_parse,
}


def inspect_disclosure_workspace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate one stage and every prerequisite against the current profile."""
    profile = normalize_automation_profile(payload)
    try:
        stage = int(payload.get("stage"))
    except (TypeError, ValueError) as exc:
        raise ValueError("stage must be an integer from 1 through 7") from exc
    if stage not in STAGE_NUMBERS:
        raise ValueError("stage must be an integer from 1 through 7")
    checkpoint_chain_valid = all(
        _load_valid_checkpoint(profile, current_stage) is not None
        for current_stage in range(1, stage + 1)
    )
    if checkpoint_chain_valid:
        stage_one = _inspect_automation_download(profile)
        if stage_one["confirmed"]:
            result = _inspection_success(
                stage,
                reason="현재 설정과 일치하는 연속 실행 체크포인트와 산출물을 확인했습니다.",
                details={"source": "automation", "download": stage_one["details"]},
            )
        else:
            result = _inspection_failure(
                stage,
                reason=f"선행 작업 '{STAGE_LABELS[1]}' 확인 실패: {stage_one['reason']}",
                details={"failed_stage": 1, **stage_one.get("details", {})},
            )
    else:
        result = _inspection_failure(stage, reason="검사를 시작하지 못했습니다.")
        for current_stage in range(1, stage + 1):
            try:
                current = DETAIL_STAGE_INSPECTORS[current_stage](profile)
            except Exception as exc:
                current = _inspection_failure(current_stage, reason=str(exc))
            if not current["confirmed"]:
                result = _inspection_failure(
                    stage,
                    reason=(
                        current["reason"]
                        if current_stage == stage
                        else f"선행 작업 '{STAGE_LABELS[current_stage]}' 확인 실패: {current['reason']}"
                    ),
                    details={"failed_stage": current_stage, **current.get("details", {})},
                )
                break
            result = current

    return {
        "format": "finiq_disclosure_workspace_inspection_v1",
        "data_root": profile["data_root"],
        "mode": profile["execution"]["mode"],
        "parser_method": profile["execution"]["parser_method"],
        "stage": result,
    }


def _load_valid_checkpoint(profile: dict[str, Any], stage: int) -> dict[str, Any] | None:
    path = _checkpoint_path(profile, stage)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("format") != AUTOMATION_CHECKPOINT_FORMAT:
        return None
    if payload.get("stage") != stage or payload.get("status") != "succeeded":
        return None
    if payload.get("config_hash") != _stage_config_hash(profile, stage):
        return None
    outputs = _stage_output_paths(profile, stage)
    outputs_valid = all(
        path.is_file() if path.suffix == ".json" else path.is_dir()
        for path in outputs
    )
    if not outputs_valid:
        return None
    if payload.get("output_fingerprint") != _stage_output_fingerprint(profile, stage):
        return None
    if stage == 1 and not _stage_one_windows_valid(profile):
        return None
    owned_directory_checks = {
        4: (
            _external_mode_directory(profile)
            / ".automation-current"
            / "automation-external-html-download.json",
            AUTOMATION_EXTERNAL_FORMAT,
        ),
        5: (
            _internal_mode_directory(profile)
            / ".automation-current"
            / "automation-internal-html-download.json",
            AUTOMATION_INTERNAL_FORMAT,
        ),
        6: (
            _sections_mode_directory(profile)
            / ".automation-current"
            / "automation-sections.json",
            AUTOMATION_SECTIONS_FORMAT,
        ),
    }
    if stage in owned_directory_checks:
        owner_path, owner_format = owned_directory_checks[stage]
        try:
            owner = json.loads(owner_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(owner, dict) or owner.get("format") != owner_format:
            return None
        if stage == 6 and owner.get("upstream_fingerprint") != _stage_output_fingerprint(
            profile, 5
        ):
            return None
    if stage in {4, 5} and not _active_html_outputs_valid(profile, stage):
        return None
    return payload


def build_automation_plan_payload(payload: dict[str, Any]) -> dict[str, Any]:
    profile = normalize_automation_profile(payload)
    trigger = str(payload.get("trigger") or "sync").strip().lower()
    if trigger not in {"sync", "resume", "review"}:
        raise ValueError("trigger must be sync, resume, or review")
    selected = set(profile["execution_mask"])
    prerequisite_available = True
    upstream_processing = False
    stages: list[dict[str, Any]] = []
    for stage in STAGE_NUMBERS:
        enabled = profile["steps"][STAGE_KEYS[stage]]
        checkpoint = _load_valid_checkpoint(profile, stage) if enabled else None
        checkpoint_valid = checkpoint is not None
        if not enabled:
            action = "disabled"
            reason = ""
        elif stage not in selected:
            action = "reuse" if checkpoint_valid else "blocked"
            reason = "" if checkpoint_valid else "이번 실행에 포함되지 않았고 재사용할 완료 결과가 없습니다."
        elif trigger in {"sync", "resume"} and stage == 1:
            action = "process"
            reason = "기존 연도별 다운로드의 1페이지를 KIND와 다시 확인합니다."
        elif checkpoint_valid and not upstream_processing:
            action = "reuse"
            reason = ""
        elif prerequisite_available:
            action = "process"
            reason = ""
        else:
            action = "blocked"
            reason = "유효한 선행 단계 결과가 없습니다."

        stages.append(
            {
                "stage": stage,
                "key": STAGE_KEYS[stage],
                "label": STAGE_LABELS[stage],
                "enabled": enabled,
                "selected": stage in selected,
                "plan_action": action,
                "reason": reason,
                "last_success_at": checkpoint.get("completed_at") if checkpoint else None,
            }
        )
        prerequisite_available = checkpoint_valid or action == "process"
        if action == "process":
            upstream_processing = True

    blocked = [item for item in stages if item["plan_action"] == "blocked"]
    return {
        "format": "finiq_disclosure_automation_plan_v1",
        "profile": profile,
        "profile_hash": _canonical_hash(profile),
        "trigger": trigger,
        "execution_allowed": not blocked,
        "stages": stages,
        "kind_limit": {
            "max_requests_per_minute": KIND_AUTOMATION_MAX_REQUESTS_PER_MINUTE,
            "max_in_flight": 1,
        },
    }


def _window_query(
    profile: dict[str, Any], window_start: date, window_end: date
) -> dict[str, Any]:
    search = profile["decisions"]["s1_search"]
    execution = profile["execution"]
    return {
        "start_date": window_start.isoformat(),
        "end_date": window_end.isoformat(),
        "company_name": search["company_name"],
        "submitter_name": search["submitter_name"],
        "market_label": search["market_label"],
        "securities_label": search["securities_label"],
        "disclosure_type_groups": search["disclosure_type_groups"],
        "page_size": execution["page_size"],
    }


def _window_manifest_path(window_path: Path) -> Path:
    return window_path / "automation-window.json"


def _page_one_snapshot_hash(window_path: Path) -> str:
    candidates = sorted(window_path.glob("*_post_page_00001.body"))
    if len(candidates) != 1:
        raise ValueError(f"KIND 1페이지를 하나만 찾을 수 없습니다: {window_path}")
    body_path = candidates[0]
    return _canonical_hash(
        {
            "pagination": pagination_info(body_path.read_bytes()),
            "rows": disclosure_file_rows(body_path),
        }
    )


def _owned_window_manifest(window_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(_window_manifest_path(window_path).read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"자동화가 만든 다운로드인지 확인할 수 없습니다: {window_path}") from exc
    if not isinstance(payload, dict) or payload.get("format") != AUTOMATION_WINDOW_FORMAT:
        raise ValueError(f"자동화가 만든 다운로드인지 확인할 수 없습니다: {window_path}")
    return payload


def _window_local_page_count(
    profile: dict[str, Any],
    window_path: Path,
    window_start: date,
    window_end: date,
) -> int:
    query = _window_query(profile, window_start, window_end)
    manifest = _owned_window_manifest(window_path)
    if (
        manifest.get("query_hash") != _canonical_hash(query)
        or not bool(manifest.get("complete"))
    ):
        raise ValueError("저장된 검색기간이나 완료 기록이 현재 설정과 다릅니다.")
    snapshot = _require_current_download_input_snapshot(window_path)
    expected_snapshot = _automation_window_snapshot(profile, window_start, window_end)
    if _snapshot_semantics(snapshot) != _snapshot_semantics(expected_snapshot):
        raise ValueError("저장된 검색 설정이 현재 설정과 다릅니다.")
    inspected = inspect_download_directory_pages(
        window_path,
        expected_page_size=profile["execution"]["page_size"],
        require_complete=True,
        validation_parallelism=profile["execution"]["local_workers"],
    )
    total_pages = int(inspected.get("total_pages") or 0)
    if total_pages < 1:
        raise ValueError("저장된 페이지가 없습니다.")
    return total_pages


def _probe_window_page_count(
    profile: dict[str, Any],
    window_start: date,
    window_end: date,
    *,
    progress_callback: ProgressCallback | None,
    cancel_check: CancelCheck,
) -> int:
    windows_root = _profile_workspace(profile).list / ".automation-windows"
    windows_root.mkdir(parents=True, exist_ok=True)
    name = f"{window_start:%Y%m%d}_{window_end:%Y%m%d}"
    probe = windows_root / f".{name}.probe-{uuid.uuid4().hex}"
    query = _window_query(profile, window_start, window_end)
    try:
        result = _run_single(
            {
                **query,
                "output_directory": str(probe),
                "start_page": 1,
                "end_page": 1,
                "wait_seconds": KIND_AUTOMATION_WAIT_SECONDS,
                "timeout": profile["execution"]["timeout"],
                "worker_count": 1,
                "last_report_only": False,
                "log_limit": 20,
            },
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        pagination = result.get("pagination") or {}
        total_pages = int(pagination.get("total_pages") or 0)
        if total_pages < 1:
            raise ValueError(f"KIND 1페이지에서 전체 페이지 수를 확인하지 못했습니다: {name}")
        return total_pages
    finally:
        if probe.exists():
            shutil.rmtree(probe)


def _download_conflict_token(
    profile: dict[str, Any], conflicts: list[dict[str, Any]]
) -> str:
    return _canonical_hash(
        {
            "stage_config": _stage_config_hash(profile, 1),
            "conflicts": [
                {
                    "range": item["range"],
                    "code": item["code"],
                    "saved_pages": item.get("saved_pages"),
                    "kind_pages": item.get("kind_pages"),
                }
                for item in conflicts
            ],
        }
    )


def _inspect_stage_one_downloads(
    profile: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None,
    cancel_check: CancelCheck,
) -> dict[str, Any]:
    search = profile["decisions"]["s1_search"]
    start = date.fromisoformat(search["start_date"])
    end = date.fromisoformat(search["end_date"])
    ranges = _split_yearly_ranges(start, end)
    windows_root = _profile_workspace(profile).list / ".automation-windows"
    windows_root.mkdir(parents=True, exist_ok=True)
    desired_names = {
        f"{window_start:%Y%m%d}_{window_end:%Y%m%d}"
        for window_start, window_end in ranges
    }
    existing = {
        child.name: child
        for child in windows_root.iterdir()
        if child.is_dir() and not child.name.startswith(".")
    }
    conflicts: list[dict[str, Any]] = []
    checked_ranges = 0

    for name in sorted(set(existing) - desired_names):
        _owned_window_manifest(existing[name])
        conflicts.append(
            {
                "range": name,
                "code": "search_range_changed",
                "saved_pages": None,
                "kind_pages": None,
                "reason": "현재 검색기간과 맞지 않는 기존 다운로드입니다.",
            }
        )

    for window_start, window_end in ranges:
        if cancel_check():
            raise RuntimeError("Job cancelled")
        name = f"{window_start:%Y%m%d}_{window_end:%Y%m%d}"
        target = windows_root / name
        if not target.is_dir():
            continue
        try:
            saved_pages = _window_local_page_count(
                profile, target, window_start, window_end
            )
            local_error = ""
        except ValueError as exc:
            _owned_window_manifest(target)
            saved_pages = None
            local_error = str(exc)
        if checked_ranges:
            time.sleep(KIND_AUTOMATION_WAIT_SECONDS)
        kind_pages = _probe_window_page_count(
            profile,
            window_start,
            window_end,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        checked_ranges += 1
        if local_error:
            conflicts.append(
                {
                    "range": name,
                    "code": "saved_download_invalid",
                    "saved_pages": saved_pages,
                    "kind_pages": kind_pages,
                    "reason": f"기존 다운로드를 그대로 사용할 수 없습니다: {local_error}",
                }
            )
        elif saved_pages != kind_pages:
            conflicts.append(
                {
                    "range": name,
                    "code": "page_count_changed",
                    "saved_pages": saved_pages,
                    "kind_pages": kind_pages,
                    "reason": "저장된 페이지 수와 KIND의 현재 페이지 수가 다릅니다.",
                }
            )

    return {
        "ranges": ranges,
        "desired_names": desired_names,
        "conflicts": conflicts,
        "confirmation": _download_conflict_token(profile, conflicts)
        if conflicts
        else "",
        "checked_ranges": checked_ranges,
    }


def _stage_one_windows_valid(profile: dict[str, Any]) -> bool:
    search = profile["decisions"]["s1_search"]
    start = date.fromisoformat(search["start_date"])
    end = date.fromisoformat(search["end_date"])
    windows_root = _profile_workspace(profile).list / ".automation-windows"
    expected_names: set[str] = set()
    for window_start, window_end in _split_yearly_ranges(start, end):
        name = f"{window_start:%Y%m%d}_{window_end:%Y%m%d}"
        expected_names.add(name)
        try:
            _window_local_page_count(
                profile, windows_root / name, window_start, window_end
            )
        except (OSError, ValueError, json.JSONDecodeError):
            return False
    if not windows_root.is_dir():
        return False
    actual_names = {
        path.name
        for path in windows_root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    }
    return actual_names == expected_names


def _replace_owned_window(target: Path, temporary: Path) -> None:
    backup = target.with_name(f".{target.name}.backup-{uuid.uuid4().hex}")
    if target.exists():
        _owned_window_manifest(target)
        os.replace(target, backup)
    try:
        os.replace(temporary, target)
    except Exception:
        if backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _replace_owned_sections(target: Path, temporary: Path) -> None:
    owner_name = "automation-sections.json"
    backup = target.with_name(f".{target.name}.backup-{uuid.uuid4().hex}")
    if target.exists():
        try:
            owner = json.loads((target / owner_name).read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"자동화 소유가 아닌 목차 결과를 교체할 수 없습니다: {target}"
            ) from exc
        if not isinstance(owner, dict) or owner.get("format") != AUTOMATION_SECTIONS_FORMAT:
            raise ValueError(
                f"자동화 소유가 아닌 목차 결과를 교체할 수 없습니다: {target}"
            )
        os.replace(target, backup)
    try:
        os.replace(temporary, target)
    except Exception:
        if backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _replace_owned_html_directory(
    target: Path,
    temporary: Path,
    *,
    owner_name: str,
    owner_format: str,
) -> None:
    backup = target.with_name(f".{target.name}.backup-{uuid.uuid4().hex}")
    if target.exists():
        try:
            owner = json.loads((target / owner_name).read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"자동화 소유가 아닌 HTML 결과를 교체할 수 없습니다: {target}"
            ) from exc
        if not isinstance(owner, dict) or owner.get("format") != owner_format:
            raise ValueError(
                f"자동화 소유가 아닌 HTML 결과를 교체할 수 없습니다: {target}"
            )
        os.replace(target, backup)
    try:
        os.replace(temporary, target)
    except Exception:
        if backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _active_disclosure_targets(filtered_path: Path) -> list[tuple[str, str]]:
    payload = json.loads(filtered_path.read_text("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("filtered.json must contain an object")
    targets: list[tuple[str, str]] = []
    seen: set[str] = set()
    for record in payload.get("disclosures") or []:
        if not isinstance(record, dict):
            continue
        acpt_no = str(record.get("acpt_no") or "")
        if not acpt_no or acpt_no in seen:
            continue
        disclosed_at = str(record.get("disclosed_at") or "")
        year = _year_from_disclosure(acpt_no, {"disclosed_at": disclosed_at})
        targets.append((acpt_no, year))
        seen.add(acpt_no)
    return targets


def _active_workspace_disclosure_targets(
    root: Path, mode: object
) -> list[tuple[str, str]]:
    normalized_mode = validate_workspace_mode(mode)
    filtered_path = (
        resolve_disclosure_workspace(root).filtered
        / normalized_mode
        / "filtered.json"
    )
    if not filtered_path.is_file():
        raise ValueError(f"필터 mode 폴더의 filtered.json을 찾을 수 없습니다: {normalized_mode}")
    return _active_disclosure_targets(filtered_path)


def _active_html_outputs_valid(profile: dict[str, Any], stage: int) -> bool:
    try:
        root = Path(profile["data_root"])
        mode = profile["execution"]["mode"]
        expected_targets = _active_workspace_disclosure_targets(root, mode)
        expected_membership = set(expected_targets)
        current = (
            _external_mode_directory(profile)
            if stage == 4
            else _internal_mode_directory(profile)
        ) / ".automation-current"
        actual_files = sorted(current.rglob("*.html"))
        actual_membership = {(path.stem, path.parent.name) for path in actual_files}
        if actual_membership != expected_membership:
            return False
        validity_workers = resolve_worker_count(
            profile["execution"]["local_workers"],
            item_count=len(actual_files),
            field_name="local_workers",
        )
        if validity_workers == 1:
            html_files_valid = all(_is_valid_html(path) for path in actual_files)
        else:
            with ThreadPoolExecutor(
                max_workers=validity_workers,
                thread_name_prefix="automation-html-check",
            ) as executor:
                html_files_valid = all(executor.map(_is_valid_html, actual_files))
        if not html_files_valid:
            return False
        if stage == 5:
            _manifest_format, _manifest_fingerprint, expected_integrity = (
                _load_html_manifest_integrity(current)
            )
            expected_acpt_numbers = {
                acpt_no for acpt_no, _year in expected_targets
            }
            if set(expected_integrity) != expected_acpt_numbers:
                return False
            actual_integrity, cancelled = _hash_html_files(
                {path.stem: path for path in actual_files}
            )
            if cancelled or actual_integrity != expected_integrity:
                return False
        if stage == 4:
            compressed_payload = json.loads(
                (_external_compress_mode_directory(profile) / "compressed-external-html.json").read_text(
                    "utf-8"
                )
            )
            records = compressed_payload.get("records")
            if not isinstance(records, list):
                return False
            if not expected_targets:
                return records == []
            internal_targets, _ = _collect_internal_targets_from_compressed_payload(
                compressed_payload
            )
            if {target["acpt_no"] for target in internal_targets} != {
                acpt_no for acpt_no, _year in expected_targets
            } or len(internal_targets) != len(expected_targets):
                return False
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return True


def _run_stage_one(
    profile: dict[str, Any],
    *,
    trigger: str,
    progress_callback: ProgressCallback,
    cancel_check: CancelCheck,
) -> dict[str, Any]:
    execution = profile["execution"]
    windows_root = _profile_workspace(profile).list / ".automation-windows"
    windows_root.mkdir(parents=True, exist_ok=True)
    inspected = _inspect_stage_one_downloads(
        profile,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )
    conflicts = inspected["conflicts"]
    confirmation = str(inspected["confirmation"])
    if conflicts and profile.get("download_confirmation") != confirmation:
        return {
            "needs_download_confirmation": True,
            "download_conflicts": conflicts,
            "download_confirmation": confirmation,
            "checked_ranges": inspected["checked_ranges"],
        }

    ranges = inspected["ranges"]
    desired_window_names = inspected["desired_names"]
    forced_names = {
        str(item["range"])
        for item in conflicts
        if item["code"] != "search_range_changed"
    }
    downloaded = 0
    reused = 0
    for index, (window_start, window_end) in enumerate(ranges, start=1):
        if cancel_check():
            raise RuntimeError("Job cancelled")
        name = f"{window_start:%Y%m%d}_{window_end:%Y%m%d}"
        target = windows_root / name
        query = _window_query(profile, window_start, window_end)
        query_hash = _canonical_hash(query)
        if target.is_dir() and name not in forced_names:
            reused += 1
            progress_callback(f"연도별 다운로드 확인 완료 {index}/{len(ranges)}: {name}")
            continue

        temporary = target.with_name(f".{target.name}.part-{uuid.uuid4().hex}")
        if temporary.exists():
            shutil.rmtree(temporary)
        progress_callback(f"연도별 다운로드 {index}/{len(ranges)}: {name}")
        try:
            request_payload = {
                **query,
                "start_page": 1,
                "wait_seconds": KIND_AUTOMATION_WAIT_SECONDS,
                "timeout": execution["timeout"],
                "worker_count": execution["local_workers"],
                "last_report_only": False,
                "log_limit": 20,
            }
            result = _run_single(
                {
                    **request_payload,
                    "output_directory": str(temporary),
                    "end_page": None,
                },
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
            status = result.get("download_status") or {}
            if not status.get("integrity_valid"):
                raise ValueError(f"KIND 연도별 다운로드 검사에 실패했습니다: {name}")

            probe = target.with_name(f".{target.name}.probe-{uuid.uuid4().hex}")
            try:
                time.sleep(KIND_AUTOMATION_WAIT_SECONDS)
                _run_single(
                    {
                        **request_payload,
                        "output_directory": str(probe),
                        "end_page": 1,
                    },
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                )
                changed_during_download = _page_one_snapshot_hash(
                    temporary
                ) != _page_one_snapshot_hash(probe)
            finally:
                if probe.exists():
                    shutil.rmtree(probe)
            if changed_during_download:
                raise ValueError(
                    f"KIND 페이지 정보 또는 본문이 다운로드 중 변경되었습니다: {name}"
                )
            atomic_write_json(
                _window_manifest_path(temporary),
                {
                    "format": AUTOMATION_WINDOW_FORMAT,
                    "query_hash": query_hash,
                    "query": query,
                    "complete": True,
                    "summary": result.get("summary") or {},
                },
            )
            _replace_owned_window(target, temporary)
            downloaded += 1
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    for child in windows_root.iterdir():
        if child.name in desired_window_names:
            continue
        if child.name.startswith(".") and (
            ".part-" in child.name or ".backup-" in child.name
        ):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            continue
        if child.is_dir():
            try:
                owner = json.loads(_window_manifest_path(child).read_text("utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"자동화 다운로드 폴더에 알 수 없는 항목이 있습니다: {child}"
                ) from exc
            if not isinstance(owner, dict) or owner.get("format") != AUTOMATION_WINDOW_FORMAT:
                raise ValueError(
                    f"자동화 다운로드 폴더에 알 수 없는 항목이 있습니다: {child}"
                )
            shutil.rmtree(child)
            continue
        raise ValueError(f"자동화 다운로드 폴더에 알 수 없는 파일이 있습니다: {child}")
    return {
        "ranges": len(ranges),
        "downloaded_ranges": downloaded,
        "reused_ranges": reused,
        "checked_ranges": inspected["checked_ranges"],
        "output_directory": str(windows_root),
    }


def _run_stage(
    stage: int,
    profile: dict[str, Any],
    *,
    trigger: str,
    progress_callback: ProgressCallback,
    cancel_check: CancelCheck,
) -> dict[str, Any]:
    root = Path(profile["data_root"])
    workspace = _profile_workspace(profile)
    execution = profile["execution"]
    if stage == 1:
        return _run_stage_one(
            profile,
            trigger=trigger,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
    if stage == 2:
        return build_disclosure_table_payload(
            {
                "data_root": str(root),
                "root_directory": str(workspace.list / ".automation-windows"),
                "output_path": str(workspace.table),
                "table_name": "disclosures",
                "table_workers": execution["local_workers"],
            },
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
    if stage == 3:
        mode = execution["mode"]
        selection = profile["decisions"]["s3_selection"]
        filter_body = {
            "data_root": str(root),
            "mode": mode,
            "filter_blocks": selection["filter_blocks"],
            "include_external_html_download_acpt_numbers": True,
            "filter_workers": execution["local_workers"],
            "progress_interval": execution["progress_interval"],
        }
        workflow_run = begin_filter_workflow_payload(filter_body)
        filter_body["source_offset"] = workflow_run["source_offset"]
        filter_body["source_expected_count"] = workflow_run[
            "source_expected_count"
        ]
        try:
            incremental_result = filter_disclosures_payload(
                filter_body,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
            mark_filter_workflow_query_completed(
                data_root=root,
                mode=mode,
                run_id=workflow_run["run_id"],
                summary=incremental_result.get("summary"),
            )
            completed = complete_filter_workflow_payload(
                data_root=root,
                mode=mode,
                run_id=workflow_run["run_id"],
                result=incremental_result,
            )
            result = completed["result"]
            atomic_write_json(workspace.filtered / mode / "filtered.json", result)
            return result
        except FilterCancelled as error:
            interrupt_filter_workflow_payload(
                data_root=root,
                mode=mode,
                run_id=workflow_run["run_id"],
                partial_result=error.partial_payload,
            )
            raise
        except Exception as error:
            fail_filter_workflow_payload(
                data_root=root,
                mode=mode,
                run_id=workflow_run["run_id"],
                error=error,
            )
            raise
    if stage == 4:
        mode = execution["mode"]
        targets = _active_workspace_disclosure_targets(root, mode)
        current = _external_mode_directory(profile) / ".automation-current"
        temporary = current.with_name(f".{current.name}.part-{uuid.uuid4().hex}")
        compressed_path = (
            _external_compress_mode_directory(profile)
            / "compressed-external-html.json"
        )
        compressed_temporary = compressed_path.parent / (
            f".{compressed_path.stem}.part-{uuid.uuid4().hex}"
        )
        try:
            temporary.mkdir(parents=True, exist_ok=True)
            compressed_temporary.mkdir(parents=True, exist_ok=True)
            if targets:
                external_html_download_result = download_disclosure_external_html_payload(
                    {
                        "data_root": str(root),
                        "mode": mode,
                        "output_directory": str(temporary),
                        "skip_existing": False,
                        "timeout": execution["timeout"],
                        "wait_seconds": KIND_AUTOMATION_WAIT_SECONDS,
                        "max_requests_per_minute": KIND_AUTOMATION_MAX_REQUESTS_PER_MINUTE,
                        "max_workers": execution["local_workers"],
                        "kind_proxy_urls": execution["kind_proxy_urls"],
                        "progress_interval": execution["progress_interval"],
                        "cancel_token": uuid.uuid4().hex,
                    },
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                )
                if (
                    external_html_download_result.get("cancelled")
                    or external_html_download_result.get("saved_count")
                    != external_html_download_result.get("requested_count")
                ):
                    raise ValueError("외부 HTML 저장이 일부만 완료되었습니다.")
                external_html_compress_result = compress_disclosure_external_html_payload(
                    {
                        "input_directory": str(temporary),
                        "output_directory": str(compressed_temporary),
                        "parallel_workers": execution["local_workers"],
                        "progress_interval": execution["progress_interval"],
                    },
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                )
                if not (
                    external_html_compress_result.get("verification") or {}
                ).get("passed"):
                    raise ValueError("외부 HTML 압축 결과 재검사에 실패했습니다.")
                compressed_payload = json.loads(
                    (compressed_temporary / "compressed-external-html.json").read_text(
                        "utf-8"
                    )
                )
                compressed_acpt_numbers = {
                    str(record.get("acpt_no") or "")
                    for record in compressed_payload.get("records") or []
                    if isinstance(record, dict)
                }
                expected_acpt_numbers = {acpt_no for acpt_no, _year in targets}
                if (
                    compressed_acpt_numbers != expected_acpt_numbers
                    or len(compressed_payload.get("records") or []) != len(targets)
                ):
                    missing = sorted(expected_acpt_numbers - compressed_acpt_numbers)
                    extra = sorted(compressed_acpt_numbers - expected_acpt_numbers)
                    raise ValueError(
                        "외부 HTML 압축 membership이 필터 결과와 다릅니다. "
                        f"누락={missing[:10]}, 추가={extra[:10]}"
                    )
                internal_targets, _ = _collect_internal_targets_from_compressed_payload(
                    compressed_payload
                )
                if (
                    {target["acpt_no"] for target in internal_targets}
                    != expected_acpt_numbers
                    or len(internal_targets) != len(targets)
                ):
                    raise ValueError(
                        "외부 HTML 압축 본문 대상이 필터 결과와 다릅니다."
                    )
            else:
                external_html_download_result = {
                    "requested_count": 0,
                    "saved_count": 0,
                }
                compressed_payload = {
                    "format": "finiq_disclosure_external_html_docs_v1",
                    "summary": {"found_files": 0, "compressed_files": 0},
                    "records": [],
                }
                atomic_write_json(
                    compressed_temporary / "compressed-external-html.json",
                    compressed_payload,
                )
                external_html_compress_result = {
                    "summary": {"found_files": 0, "compressed_files": 0}
                }
            atomic_write_json(
                temporary / "automation-external-html-download.json",
                {
                    "format": AUTOMATION_EXTERNAL_FORMAT,
                    "active_count": len(targets),
                    "complete": True,
                },
            )
            _replace_owned_html_directory(
                current,
                temporary,
                owner_name="automation-external-html-download.json",
                owner_format=AUTOMATION_EXTERNAL_FORMAT,
            )
            atomic_write_json(compressed_path, compressed_payload)
            return {
                "external_html_download": external_html_download_result,
                "external_html_compress": external_html_compress_result,
            }
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
            if compressed_temporary.exists():
                shutil.rmtree(compressed_temporary)
    if stage == 5:
        mode = execution["mode"]
        targets = _active_workspace_disclosure_targets(root, mode)
        current = _internal_mode_directory(profile) / ".automation-current"
        temporary = current.with_name(f".{current.name}.part-{uuid.uuid4().hex}")
        try:
            temporary.mkdir(parents=True, exist_ok=True)
            if targets:
                result = download_disclosure_internal_html_payload(
                    {
                        "source_compressed_json_path": str(
                            _external_compress_mode_directory(profile)
                            / "compressed-external-html.json"
                        ),
                        "output_directory": str(temporary),
                        "skip_existing": False,
                        "timeout": execution["timeout"],
                        "wait_seconds": KIND_AUTOMATION_WAIT_SECONDS,
                        "max_requests_per_minute": KIND_AUTOMATION_CONTENT_REQUESTS_PER_MINUTE,
                        "max_workers": execution["local_workers"],
                        "kind_proxy_urls": execution["kind_proxy_urls"],
                        "progress_interval": execution["progress_interval"],
                        "cancel_token": uuid.uuid4().hex,
                    },
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                    confirm_source_unavailable=True,
                )
                if (
                    result.get("cancelled")
                    or result.get("requested_count") != len(targets)
                    or result.get("saved_count") != result.get("requested_count")
                ):
                    raise ValueError("내부 HTML 저장이 일부만 완료되었습니다.")
            else:
                result = {"requested_count": 0, "saved_count": 0}
            atomic_write_json(
                temporary / "automation-internal-html-download.json",
                {
                    "format": AUTOMATION_INTERNAL_FORMAT,
                    "active_count": len(targets),
                    "complete": True,
                },
            )
            _replace_owned_html_directory(
                current,
                temporary,
                owner_name="automation-internal-html-download.json",
                owner_format=AUTOMATION_INTERNAL_FORMAT,
            )
            result["output_directory"] = str(current)
            return result
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    if stage == 6:
        output_directory = _sections_mode_directory(profile) / ".automation-current"
        temporary = output_directory.with_name(
            f".{output_directory.name}.part-{uuid.uuid4().hex}"
        )
        try:
            result = save_disclosure_html_sections_payload(
                {
                    "input_directory": str(
                        _internal_mode_directory(profile) / ".automation-current"
                    ),
                    "output_directory": str(temporary),
                    "workers": execution["local_workers"],
                    "progress_interval": execution["progress_interval"],
                },
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
            if result.get("cancelled") or not (result.get("summary") or {}).get(
                "integrity_ok"
            ):
                raise ValueError("목차 분리 결과 무결성 검사에 실패했습니다.")
            atomic_write_json(
                temporary / "automation-sections.json",
                {
                    "format": AUTOMATION_SECTIONS_FORMAT,
                    "algorithm": "structural-toc-with-correction-filter-v1",
                    "upstream_fingerprint": _stage_output_fingerprint(profile, 5),
                    "complete": True,
                },
            )
            _replace_owned_sections(output_directory, temporary)
            result["output_directory"] = str(output_directory)
            return result
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    if stage == 7:
        mode = execution["mode"]
        result = parse_disclosure_html_payload(
            {
                "data_root": str(root),
                "mode": mode,
                "parser_method": execution["parser_method"],
                "input_directory": str(
                    _sections_mode_directory(profile) / ".automation-current"
                ),
                "output_directory": str(workspace.converted / mode),
                "filtered_metadata_path": str(_filter_result_path(profile)),
                "compressed_metadata_path": str(
                    _external_compress_mode_directory(profile)
                    / "compressed-external-html.json"
                ),
                "parallel_workers": execution["local_workers"],
                "skip_errors": False,
                "progress_interval": execution["progress_interval"],
            },
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        if result.get("cancelled"):
            raise RuntimeError("Job cancelled")
        return result
    raise ValueError(f"unsupported stage: {stage}")


def run_disclosure_automation_payload(
    payload: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    plan = build_automation_plan_payload(payload)
    if not plan["execution_allowed"]:
        reasons = [
            f"{item['label']}: {item['reason']}"
            for item in plan["stages"]
            if item["plan_action"] == "blocked"
        ]
        raise ValueError("실행 계획이 차단되었습니다. " + " / ".join(reasons))
    profile = plan["profile"]
    trigger = plan["trigger"]
    _prepare_automation_output_directories(profile, plan["stages"])

    def emit(message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)

    def cancelled() -> bool:
        return bool(cancel_check and cancel_check())

    stage_results: list[dict[str, Any]] = []
    for stage_plan in plan["stages"]:
        stage = int(stage_plan["stage"])
        action = stage_plan["plan_action"]
        if cancelled():
            raise RuntimeError("Job cancelled")
        if action in {"disabled", "reuse"}:
            stage_results.append(
                {
                    "stage": stage,
                    "label": stage_plan["label"],
                    "status": "disabled" if action == "disabled" else "reused",
                }
            )
            emit(
                f"{stage_plan['label']}: "
                f"{'사용 안 함' if action == 'disabled' else '재사용'}"
            )
            continue

        emit(f"{stage_plan['label']}: 실행 시작")
        result = _run_stage(
            stage,
            profile,
            trigger=trigger,
            progress_callback=lambda message, label=stage_plan["label"]: emit(
                f"[{label}] {message}"
            ),
            cancel_check=cancelled,
        )
        if stage == 1 and result.get("needs_download_confirmation"):
            stage_results.append(
                {
                    "stage": stage,
                    "label": stage_plan["label"],
                    "status": "needs_download_confirmation",
                    "result": result,
                }
            )
            emit("공시내역 다운로드: 전체 다시 받기 확인 필요")
            return {
                "format": "finiq_disclosure_automation_run_v1",
                "workflow_status": "needs_download_confirmation",
                "profile_hash": plan["profile_hash"],
                "stages": stage_results,
                "download_conflicts": result["download_conflicts"],
                "download_confirmation": result["download_confirmation"],
            }
        checkpoint = {
            "format": AUTOMATION_CHECKPOINT_FORMAT,
            "stage": stage,
            "status": "succeeded",
            "config_hash": _stage_config_hash(profile, stage),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "outputs": [str(path) for path in _stage_output_paths(profile, stage)],
            "output_fingerprint": _stage_output_fingerprint(profile, stage),
            "result_summary": result.get("summary") if isinstance(result, dict) else None,
        }
        atomic_write_json(_checkpoint_path(profile, stage), checkpoint)
        stage_results.append(
            {
                "stage": stage,
                "label": stage_plan["label"],
                "status": "succeeded",
                "completed_at": checkpoint["completed_at"],
            }
        )
        emit(f"{stage_plan['label']}: 완료")

    return {
        "format": "finiq_disclosure_automation_run_v1",
        "workflow_status": "completed",
        "profile_hash": plan["profile_hash"],
        "stages": stage_results,
        "output_path": str(_stage_output_paths(profile, 7)[0])
        if profile["steps"][STAGE_KEYS[7]]
        else "",
    }


__all__ = [
    "AUTOMATION_PROFILE_FORMAT",
    "KIND_AUTOMATION_MAX_REQUESTS_PER_MINUTE",
    "build_automation_plan_payload",
    "normalize_automation_profile",
    "run_disclosure_automation_payload",
]
