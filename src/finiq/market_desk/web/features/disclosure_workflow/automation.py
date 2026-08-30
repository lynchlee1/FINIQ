"""Sequential coordinator for the disclosure detail-page workflows.

Each stage uses the same service and canonical output as its detail page. The
automation layer owns only the execution order and resumable checkpoints.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from finiq.concurrency import resolve_worker_count
from finiq.data_scraper.core.kind_computers import normalize_kind_proxy_urls
from finiq.market_desk.sqlite_generation import sqlite_generation_locked
from finiq.market_desk.web.features.disclosures.external_compact import (
    _verify_compressed_external_html_files,
)
from finiq.market_desk.web.features.disclosures.external_html_compress import (
    compress_disclosure_external_html_payload,
)
from finiq.market_desk.web.features.disclosures.external_html_download import (
    download_disclosure_external_html_payload,
)
from finiq.market_desk.web.features.disclosures.filter_presets import (
    filter_workflow_path,
    load_filter_workflow_result_payload,
    run_filter_workflow_payload,
)
from finiq.market_desk.web.features.disclosures.html_cleanup import (
    check_disclosure_html_output_directory_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_common import (
    PARSER_REGISTRY,
    inspect_disclosure_html_parse_payload,
    parse_disclosure_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_sections import (
    inspect_disclosure_html_section_output_payload,
    save_disclosure_html_sections_payload,
)
from finiq.market_desk.web.features.disclosures.internal_html_download import (
    download_disclosure_internal_html_payload,
)
from finiq.market_desk.web.features.disclosures.table_export import (
    build_disclosure_table_payload,
    inspect_disclosure_table_payload,
)
from finiq.market_desk.web.features.downloads.kind_api import run_download_action
from finiq.market_desk.web.features.downloads.kind_common import (
    DownloadInputMetadataError,
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

from .layout import (
    DisclosureWorkspace,
    atomic_write_json,
    resolve_disclosure_workspace,
    validate_workspace_mode,
)


AUTOMATION_PROFILE_FORMAT = "finiq_disclosure_automation_profile_v1"
AUTOMATION_CHECKPOINT_FORMAT = "finiq_disclosure_automation_checkpoint_v1"
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
NO_MATCHING_DISCLOSURES_MESSAGE = "조건에 맞는 공시 없음"
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
    end_date_text = str(raw_search.get("end_date") or "").strip()
    end_date = date.today() if not end_date_text else _iso_date(end_date_text, "end_date")
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    if bool(raw_search.get("last_report_only")):
        raise ValueError("공시 자동화에서는 최종보고서만 옵션을 사용할 수 없습니다.")

    disclosure_groups = raw_search.get("disclosure_type_groups") or {}
    if not isinstance(disclosure_groups, dict):
        raise ValueError("disclosure_type_groups must be an object")
    normalized_groups = {
        str(key): sorted({str(code).strip() for code in value if str(code).strip()})
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
            "s3_selection": {"filter_blocks": filter_blocks},
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
                execution.get("local_workers"), field_name="local_workers"
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
    return _profile_workspace(profile).external_mode(profile["execution"]["mode"])


def _external_compress_mode_directory(profile: dict[str, Any]) -> Path:
    return _profile_workspace(profile).external_compress_mode(
        profile["execution"]["mode"]
    )


def _internal_mode_directory(profile: dict[str, Any]) -> Path:
    return _profile_workspace(profile).internal_mode(profile["execution"]["mode"])


def _sections_mode_directory(profile: dict[str, Any]) -> Path:
    return _profile_workspace(profile).sections_mode(profile["execution"]["mode"])


def _prepare_automation_output_directories(
    profile: dict[str, Any], stages: list[dict[str, Any]]
) -> None:
    workspace = _profile_workspace(profile)
    mode = profile["execution"]["mode"]
    directories = {
        1: workspace.list,
        2: workspace.table,
        3: workspace.filtered / mode,
        4: workspace.external_compress_mode(mode),
        5: workspace.internal_mode(mode),
        6: workspace.sections_mode(mode),
        7: workspace.converted_mode(mode),
    }
    for stage_plan in stages:
        if stage_plan["plan_action"] != "process":
            continue
        stage = int(stage_plan["stage"])
        if stage == 4:
            workspace.external_mode(mode).mkdir(parents=True, exist_ok=True)
        directories[stage].mkdir(parents=True, exist_ok=True)


def _checkpoint_path(profile: dict[str, Any], stage: int) -> Path:
    return _automation_root(profile) / "checkpoints" / f"stage-{stage}.json"


def _stage_config_hash(profile: dict[str, Any], stage: int) -> str:
    decisions = profile["decisions"]
    semantic: dict[str, Any] = {"stage": stage}
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
    paths = {
        1: [workspace.list],
        2: [workspace.table],
        3: [
            filter_workflow_path(workspace.root, mode),
            workspace.filtered / mode / "filtered.json",
        ],
        4: [
            workspace.external_compress_mode(mode) / "compressed-external-html.json",
            workspace.external_mode(mode),
        ],
        5: [workspace.internal_mode(mode)],
        6: [workspace.sections_mode(mode)],
        7: [workspace.converted_mode(mode) / f"parsed-{mode}.json"],
    }
    try:
        return paths[stage]
    except KeyError as exc:
        raise ValueError(f"unsupported stage: {stage}") from exc


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


def _inspection(
    stage: int,
    confirmed: bool,
    *,
    reason: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "label": STAGE_LABELS[stage],
        "confirmed": confirmed,
        "reason": reason,
        "details": details or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _inspection_success(
    stage: int, *, reason: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return _inspection(stage, True, reason=reason, details=details)


def _inspection_failure(
    stage: int, *, reason: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return _inspection(stage, False, reason=reason, details=details)


def _detail_download_payload(profile: dict[str, Any]) -> dict[str, Any]:
    search = profile["decisions"]["s1_search"]
    return {
        "data_root": profile["data_root"],
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
        "parallel_strategy": "years",
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


def _expected_download_ranges(profile: dict[str, Any]) -> list[tuple[date, date, Path]]:
    payload = _detail_download_payload(profile)
    root = Path(payload["output_directory"])
    return [
        (start, end, root / f"{start:%Y%m%d}_{end:%Y%m%d}")
        for start, end in _split_yearly_ranges(
            date.fromisoformat(payload["start_date"]),
            date.fromisoformat(payload["end_date"]),
        )
    ]


def _inspect_detail_download(profile: dict[str, Any]) -> dict[str, Any]:
    payload = _detail_download_payload(profile)
    expected_ranges = _expected_download_ranges(profile)
    total_local = 0
    total_kind = 0
    for range_start, range_end, folder in expected_ranges:
        if not folder.is_dir():
            return _inspection_failure(
                1,
                reason=f"{folder.name} 다운로드 폴더가 없습니다.",
                details={"missing_folder": folder.name},
            )
        snapshot = _require_current_download_input_snapshot(folder)
        expected_snapshot = _download_input_snapshot_from_payload(
            payload,
            start=range_start,
            end=range_end,
            page_size=int(payload["page_size"]),
        )
        if _snapshot_semantics(snapshot) != _snapshot_semantics(expected_snapshot):
            return _inspection_failure(
                1,
                reason=f"{folder.name}의 다운로드 설정이 현재 실행 설정과 다릅니다.",
            )
        with KIND_NETWORK_JOB_LOCK:
            existing = check_existing_downloads(
                str(folder),
                verify_with_kind=True,
                current_payload=payload,
                parallel_workers=profile["execution"]["local_workers"],
            )
        statuses = list(existing.get("ranges") or [])
        if len(statuses) != 1 or statuses[0].get("status") != "validated":
            reason = (
                str(statuses[0].get("error_detail"))
                if statuses
                else "다운로드 결과를 확인할 수 없습니다."
            )
            return _inspection_failure(
                1, reason=reason, details={"failed_ranges": statuses}
            )
        total_local += int(statuses[0].get("local_count") or 0)
        total_kind += int(statuses[0].get("kind_count") or 0)
    return _inspection_success(
        1,
        reason="현재 검색 설정과 일치하며 모든 저장 건수를 KIND와 확인했습니다.",
        details={
            "ranges": len(expected_ranges),
            "local_count": total_local,
            "kind_count": total_kind,
        },
    )


def _filter_result_path(profile: dict[str, Any]) -> Path:
    workspace = _profile_workspace(profile)
    return workspace.filtered / profile["execution"]["mode"] / "filtered.json"


def _filter_result_is_empty(
    profile: dict[str, Any], result: dict[str, Any] | None = None
) -> bool:
    if result is None:
        result = load_filter_workflow_result_payload(
            data_root=Path(profile["data_root"]),
            mode=profile["execution"]["mode"],
            condition_blocks=profile["decisions"]["s3_selection"]["filter_blocks"],
        )
    disclosures = result.get("disclosures")
    if not isinstance(disclosures, list):
        raise ValueError("filter workflow result disclosures must be a list")
    return not disclosures


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
            "external_html_download_acpt_numbers": payload.get(
                "external_html_download_acpt_numbers"
            ),
        }
    )


@sqlite_generation_locked
def _inspect_detail_table(profile: dict[str, Any]) -> dict[str, Any]:
    workspace = _profile_workspace(profile)
    checked = inspect_disclosure_table_payload(
        {
            "root_directory": str(workspace.list),
            "output_path": str(workspace.table),
            "table_workers": profile["execution"]["local_workers"],
        }
    )
    if not checked.get("confirmed"):
        return _inspection_failure(
            2,
            reason=str(checked.get("reason") or "공시내역 변환 결과 검사에 실패했습니다."),
            details={"manifest_path": checked.get("manifest_path")},
        )
    return _inspection_success(
        2,
        reason=str(checked["reason"]),
        details=dict(checked.get("summary") or {}),
    )


@sqlite_generation_locked
def _inspect_detail_filter(profile: dict[str, Any]) -> dict[str, Any]:
    actual = _read_json_object(_filter_result_path(profile))
    if actual is None:
        return _inspection_failure(3, reason="필터 결과 JSON이 없거나 손상되었습니다.")
    try:
        expected = load_filter_workflow_result_payload(
            data_root=Path(profile["data_root"]),
            mode=profile["execution"]["mode"],
            condition_blocks=profile["decisions"]["s3_selection"]["filter_blocks"],
        )
    except ValueError as error:
        return _inspection_failure(3, reason=str(error))
    if _filter_signature(actual) != _filter_signature(expected):
        return _inspection_failure(
            3, reason="조건검색 정본과 다음 단계 전달 파일의 결과가 다릅니다."
        )
    return _inspection_success(
        3,
        reason="조건검색 정본과 다음 단계 전달 파일이 일치합니다.",
        details={"records": len(actual.get("disclosures") or [])},
    )


def _html_inspection_details(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: payload.get(key)
        for key in (
            "requested_count",
            "existing_target_html_count",
            "missing_target_html_count",
            "invalid_target_html_count",
            "unexpected_file_count",
            "missing_target_acpt_numbers",
            "invalid_target_acpt_numbers",
            "unexpected_files",
        )
        if payload.get(key) not in (None, [], 0)
    }


def _inspect_detail_external_html(profile: dict[str, Any]) -> dict[str, Any]:
    output_directory = _external_mode_directory(profile)
    checked = check_disclosure_html_output_directory_payload(
        {
            "data_root": profile["data_root"],
            "mode": profile["execution"]["mode"],
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
    compressed_path = (
        _external_compress_mode_directory(profile) / "compressed-external-html.json"
    )
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
    saved = _read_json_object(compressed_path)
    with tempfile.TemporaryDirectory(prefix="finiq-external-inspection-") as temporary:
        compress_disclosure_external_html_payload(
            {
                "input_directory": str(output_directory),
                "output_directory": temporary,
                "parallel_workers": profile["execution"]["local_workers"],
            }
        )
        rebuilt = _read_json_object(Path(temporary) / "compressed-external-html.json")
    if saved != rebuilt:
        return _inspection_failure(
            4, reason="현재 외부 HTML을 압축한 결과와 저장된 JSON이 다릅니다."
        )
    return _inspection_success(
        4,
        reason="현재 필터 대상의 외부 HTML과 압축 JSON이 모두 완전합니다.",
        details={"records": requested},
    )


def _inspect_detail_internal_html(profile: dict[str, Any]) -> dict[str, Any]:
    checked = check_disclosure_html_output_directory_payload(
        {
            "source_compressed_json_path": str(
                _external_compress_mode_directory(profile)
                / "compressed-external-html.json"
            ),
            "output_directory": str(_internal_mode_directory(profile)),
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
    checked = inspect_disclosure_html_section_output_payload(
        {
            "input_directory": str(_internal_mode_directory(profile)),
            "output_directory": str(_sections_mode_directory(profile)),
            "workers": profile["execution"]["local_workers"],
        }
    )
    summary = checked.get("summary") or {}
    if not summary.get("integrity_ok"):
        return _inspection_failure(
            6,
            reason="현재 목차 분리 결과와 저장된 HTML이 다릅니다.",
            details={"summary": summary},
        )
    return _inspection_success(
        6,
        reason="목차 분리 결과와 모든 저장 HTML 내용이 일치합니다.",
        details={"records": int(summary.get("actual_files") or 0)},
    )


def _inspect_detail_parse(profile: dict[str, Any]) -> dict[str, Any]:
    mode = profile["execution"]["mode"]
    workspace = _profile_workspace(profile)
    checked = inspect_disclosure_html_parse_payload(
        {
            "data_root": profile["data_root"],
            "mode": mode,
            "parser_method": profile["execution"]["parser_method"],
            "input_directory": str(workspace.sections_mode(mode)),
            "output_directory": str(workspace.converted_mode(mode)),
            "filtered_metadata_path": str(_filter_result_path(profile)),
            "compressed_metadata_path": str(
                workspace.external_compress_mode(mode)
                / "compressed-external-html.json"
            ),
            "parallel_workers": profile["execution"]["local_workers"],
            "skip_errors": False,
        }
    )
    if not checked.get("confirmed"):
        return _inspection_failure(
            7,
            reason=str(checked.get("reason") or "공시원문 변환 결과 검사에 실패했습니다."),
        )
    return _inspection_success(
        7,
        reason=str(checked["reason"]),
        details=dict(checked.get("summary") or {}),
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
    profile = normalize_automation_profile(payload)
    try:
        stage = int(payload.get("stage"))
    except (TypeError, ValueError) as exc:
        raise ValueError("stage must be an integer from 1 through 7") from exc
    if stage not in STAGE_NUMBERS:
        raise ValueError("stage must be an integer from 1 through 7")
    result = _inspection_failure(stage, reason="검사를 시작하지 못했습니다.")
    for current_stage in range(1, stage + 1):
        try:
            current = DETAIL_STAGE_INSPECTORS[current_stage](profile)
        except Exception as error:
            current = _inspection_failure(current_stage, reason=str(error))
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
    payload = _read_json_object(_checkpoint_path(profile, stage))
    if payload is None:
        return None
    if (
        payload.get("format") != AUTOMATION_CHECKPOINT_FORMAT
        or payload.get("stage") != stage
        or payload.get("status") != "succeeded"
        or payload.get("config_hash") != _stage_config_hash(profile, stage)
        or payload.get("output_fingerprint")
        != _stage_output_fingerprint(profile, stage)
    ):
        return None
    if not all(path.exists() for path in _stage_output_paths(profile, stage)):
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
            action, reason = "disabled", ""
        elif stage not in selected:
            action = "reuse" if checkpoint_valid else "blocked"
            reason = "" if checkpoint_valid else "이번 실행에 포함되지 않았고 재사용할 완료 결과가 없습니다."
        elif stage == 1 and trigger in {"sync", "resume"}:
            action, reason = "process", "공시내역 다운로드 페이지와 같은 실행 경로를 시작합니다."
        elif checkpoint_valid and not upstream_processing:
            action, reason = "reuse", ""
        elif prerequisite_available:
            action, reason = "process", ""
        else:
            action, reason = "blocked", "유효한 선행 단계 결과가 없습니다."
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


def _download_conflict_token(
    profile: dict[str, Any], conflicts: list[dict[str, Any]]
) -> str:
    return _canonical_hash(
        {"stage_config": _stage_config_hash(profile, 1), "conflicts": conflicts}
    )


def _inspect_stage_one_downloads(
    profile: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None,
    cancel_check: CancelCheck,
) -> dict[str, Any]:
    payload = _detail_download_payload(profile)
    conflicts: list[dict[str, Any]] = []
    checked_ranges = 0
    for _range_start, _range_end, folder in _expected_download_ranges(profile):
        if cancel_check():
            raise RuntimeError("Job cancelled")
        if not folder.is_dir() or not list(folder.glob("*_post_page_*.body")):
            continue
        checked_ranges += 1
        try:
            existing = check_existing_downloads(
                str(folder),
                verify_with_kind=True,
                current_payload=payload,
                cancel_check=cancel_check,
                progress_callback=progress_callback,
                parallel_workers=profile["execution"]["local_workers"],
            )
        except DownloadInputMetadataError as error:
            conflicts.append(
                {
                    "range": folder.name,
                    "code": "saved_download_invalid",
                    "saved_count": None,
                    "kind_count": None,
                    "reason": str(error),
                }
            )
            continue
        statuses = list(existing.get("ranges") or [])
        status = statuses[0] if len(statuses) == 1 else {}
        if status.get("status") == "validated" and status.get("filters_match", True):
            continue
        local_count = status.get("local_count")
        kind_count = status.get("kind_count")
        conflicts.append(
            {
                "range": folder.name,
                "code": (
                    "kind_count_changed"
                    if local_count is not None
                    and kind_count is not None
                    and local_count != kind_count
                    else "saved_download_invalid"
                ),
                "saved_count": local_count,
                "kind_count": kind_count,
                "reason": str(
                    status.get("error_detail")
                    or "기존 다운로드를 현재 설정으로 재사용할 수 없습니다."
                ),
            }
        )
    return {
        "conflicts": conflicts,
        "confirmation": _download_conflict_token(profile, conflicts)
        if conflicts
        else "",
        "checked_ranges": checked_ranges,
    }


def _run_stage_one(
    profile: dict[str, Any],
    *,
    trigger: str,
    progress_callback: ProgressCallback,
    cancel_check: CancelCheck,
) -> dict[str, Any]:
    del trigger
    inspected = _inspect_stage_one_downloads(
        profile,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )
    conflicts = inspected["conflicts"]
    confirmation = inspected["confirmation"]
    if conflicts and profile.get("download_confirmation") != confirmation:
        return {
            "needs_download_confirmation": True,
            "download_conflicts": conflicts,
            "download_confirmation": confirmation,
        }
    result = run_download_action(
        _detail_download_payload(profile),
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )
    return {**result, "checked_ranges": inspected["checked_ranges"]}


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
    mode = execution["mode"]
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
                "root_directory": str(workspace.list),
                "output_path": str(workspace.table),
                "table_name": "disclosures",
                "table_workers": execution["local_workers"],
            },
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
    if stage == 3:
        filter_body = {
            "data_root": str(root),
            "mode": mode,
            "filter_blocks": profile["decisions"]["s3_selection"]["filter_blocks"],
            "include_external_html_download_acpt_numbers": True,
            "filter_workers": execution["local_workers"],
            "progress_interval": execution["progress_interval"],
        }
        return run_filter_workflow_payload(
            filter_body,
            filter_payload_builder=filter_disclosures_payload,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
    if stage == 4:
        download_result = download_disclosure_external_html_payload(
            {
                "data_root": str(root),
                "mode": mode,
                "output_directory": str(workspace.external_mode(mode)),
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
        if download_result.get("cancelled"):
            raise RuntimeError("Job cancelled")
        compress_result = compress_disclosure_external_html_payload(
            {
                "input_directory": str(workspace.external_mode(mode)),
                "output_directory": str(workspace.external_compress_mode(mode)),
                "parallel_workers": execution["local_workers"],
                "progress_interval": execution["progress_interval"],
            },
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        return {
            "external_html_download": download_result,
            "external_html_compress": compress_result,
        }
    if stage == 5:
        result = download_disclosure_internal_html_payload(
            {
                "data_root": str(root),
                "mode": mode,
                "source_compressed_json_path": str(
                    workspace.external_compress_mode(mode)
                    / "compressed-external-html.json"
                ),
                "output_directory": str(workspace.internal_mode(mode)),
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
        )
        if result.get("cancelled"):
            raise RuntimeError("Job cancelled")
        return result
    if stage == 6:
        result = save_disclosure_html_sections_payload(
            {
                "data_root": str(root),
                "mode": mode,
                "input_directory": str(workspace.internal_mode(mode)),
                "output_directory": str(workspace.sections_mode(mode)),
                "workers": execution["local_workers"],
                "progress_interval": execution["progress_interval"],
            },
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        if result.get("cancelled"):
            raise RuntimeError("Job cancelled")
        return result
    if stage == 7:
        result = parse_disclosure_html_payload(
            {
                "data_root": str(root),
                "mode": mode,
                "parser_method": execution["parser_method"],
                "input_directory": str(workspace.sections_mode(mode)),
                "output_directory": str(workspace.converted_mode(mode)),
                "filtered_metadata_path": str(_filter_result_path(profile)),
                "compressed_metadata_path": str(
                    workspace.external_compress_mode(mode)
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

    def complete_without_downstream_stages(
        remaining_stages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        for remaining in remaining_stages:
            status = (
                "disabled"
                if remaining["plan_action"] == "disabled"
                else "skipped"
            )
            stage_results.append(
                {
                    "stage": int(remaining["stage"]),
                    "label": remaining["label"],
                    "status": status,
                }
            )
            if status == "skipped":
                emit(f"{remaining['label']}: 건너뜀 ({NO_MATCHING_DISCLOSURES_MESSAGE})")
        return {
            "format": "finiq_disclosure_automation_run_v1",
            "workflow_status": "completed",
            "completion_reason": NO_MATCHING_DISCLOSURES_MESSAGE,
            "profile_hash": plan["profile_hash"],
            "stages": stage_results,
            "output_path": "",
        }

    stage_results: list[dict[str, Any]] = []
    for stage_index, stage_plan in enumerate(plan["stages"]):
        stage = int(stage_plan["stage"])
        action = stage_plan["plan_action"]
        if cancelled():
            raise RuntimeError("Job cancelled")
        if action in {"disabled", "reuse"}:
            status = "disabled" if action == "disabled" else "reused"
            stage_results.append(
                {"stage": stage, "label": stage_plan["label"], "status": status}
            )
            emit(f"{stage_plan['label']}: {'사용 안 함' if action == 'disabled' else '재사용'}")
            if (
                stage == 3
                and action == "reuse"
                and _filter_result_is_empty(profile)
            ):
                return complete_without_downstream_stages(
                    plan["stages"][stage_index + 1 :]
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
            emit("공시내역 다운로드: 다시 받기 확인 필요")
            return {
                "format": "finiq_disclosure_automation_run_v1",
                "workflow_status": "needs_download_confirmation",
                "profile_hash": plan["profile_hash"],
                "stages": stage_results,
                "download_conflicts": result["download_conflicts"],
                "download_confirmation": result["download_confirmation"],
            }
        stage_three_empty = stage == 3 and _filter_result_is_empty(profile, result)
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
        if stage_three_empty:
            return complete_without_downstream_stages(
                plan["stages"][stage_index + 1 :]
            )

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
    "inspect_disclosure_workspace_payload",
    "normalize_automation_profile",
    "run_disclosure_automation_payload",
]
