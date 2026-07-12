"""Safe compatibility orchestrator for the seven disclosure stages.

The existing stage implementations remain the source of truth.  This module adds a
small, fixed seven-stage coordinator, date-windowed KIND discovery, and durable
stage checkpoints for the new Web UI.  It intentionally is not a generic DAG.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from finiq.data_scraper.core.client import _is_valid_html
from finiq.data_scraper.parse import disclosure_file_rows

from finiq.market_desk.web.features.disclosures.html_content_download import (
    _collect_content_targets_from_compressed_payload,
    download_disclosure_html_contents_payload,
)
from finiq.market_desk.web.features.disclosures.html_download import (
    download_disclosure_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_external_compress import (
    compress_disclosure_external_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_common import (
    parse_disclosure_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_sections import (
    save_disclosure_html_sections_payload,
    summarize_disclosure_html_section_kinds_payload,
)
from finiq.market_desk.web.features.disclosures.table_export import (
    build_disclosure_table_payload,
)
from finiq.market_desk.web.features.downloads.kind_runner import _run_single
from finiq.market_desk.web.features.market_data.service_payloads import (
    filter_disclosures_payload,
)

from .layout import (
    atomic_write_json,
    prepare_disclosure_workspace_payload,
    resolve_disclosure_workspace,
)


AUTOMATION_PROFILE_FORMAT = "finiq_disclosure_automation_profile_v1"
AUTOMATION_CHECKPOINT_FORMAT = "finiq_disclosure_automation_checkpoint_v1"
AUTOMATION_WINDOW_FORMAT = "finiq_disclosure_automation_window_v1"
AUTOMATION_SECTIONS_FORMAT = "finiq_disclosure_automation_sections_v1"
AUTOMATION_EXTERNAL_FORMAT = "finiq_disclosure_automation_external_v1"
AUTOMATION_INTERNAL_FORMAT = "finiq_disclosure_automation_internal_v1"
STAGE_NUMBERS = tuple(range(1, 8))
STAGE_KEYS = {
    1: "s1_download",
    2: "s2_table",
    3: "s3_filter",
    4: "s4_external_html",
    5: "s5_content_html",
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
MUTABLE_LOOKBACK_DAYS = 7

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
    section_rules = raw_sections.get("section_save_rules") or {}
    if not isinstance(section_rules, dict):
        raise ValueError("section_save_rules must be an object")
    normalized_section_rules: dict[str, list[str]] = {}
    for signature, toc_ids in section_rules.items():
        signature_text = str(signature or "").strip()
        if not signature_text or not isinstance(toc_ids, list):
            continue
        normalized_section_rules[signature_text] = list(
            dict.fromkeys(
                str(toc_id).strip()
                for toc_id in toc_ids
                if str(toc_id).strip()
            )
        )

    execution = payload.get("execution") or {}
    if not isinstance(execution, dict):
        raise ValueError("execution must be an object")
    parser_mode = str(execution.get("parser_mode") or "bond_issuance").strip()
    if parser_mode not in {"bond_issuance", "rights_issuance"}:
        raise ValueError("unsupported parser_mode")

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
                "unmatched_policy": "needs_review",
                "section_save_rules": normalized_section_rules,
            },
        },
        "execution": {
            "parser_mode": parser_mode,
            "page_size": _positive_int(
                execution.get("page_size"), "page_size", 100, 100
            ),
            "timeout": _positive_int(execution.get("timeout"), "timeout", 20, 120),
            "local_workers": _positive_int(
                execution.get("local_workers"), "local_workers", 4, 32
            ),
            "mutable_lookback_days": MUTABLE_LOOKBACK_DAYS,
            "max_requests_per_minute": KIND_AUTOMATION_MAX_REQUESTS_PER_MINUTE,
            "split_by_year": True,
        },
    }


def _automation_root(profile: dict[str, Any]) -> Path:
    return Path(profile["data_root"]) / ".finiq" / "disclosure-automation"


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
        semantic["s6_sections"] = decisions["s6_sections"]
        semantic["parser_mode"] = profile["execution"]["parser_mode"]
    return _canonical_hash(semantic)


def _stage_output_paths(profile: dict[str, Any], stage: int) -> list[Path]:
    root = Path(profile["data_root"])
    mode = profile["execution"]["parser_mode"]
    paths = {
        1: [root / "01-list" / ".automation-windows"],
        2: [root / "02-table"],
        3: [root / "03-filter" / "filtered.json"],
        4: [
            root / "04-external" / "compressed-external-html.json",
            root / "04-external" / ".automation-current",
        ],
        5: [root / "05-internal" / ".automation-current"],
        6: [root / "06-sections" / ".automation-current"],
        7: [root / "07-converted" / mode / f"parsed-{mode}.json"],
    }
    return paths[stage]


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
            Path(profile["data_root"])
            / "04-external"
            / ".automation-current"
            / "automation-external.json",
            AUTOMATION_EXTERNAL_FORMAT,
        ),
        5: (
            Path(profile["data_root"])
            / "05-internal"
            / ".automation-current"
            / "automation-internal.json",
            AUTOMATION_INTERNAL_FORMAT,
        ),
        6: (
            Path(profile["data_root"])
            / "06-sections"
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
        checkpoint = _load_valid_checkpoint(profile, stage)
        checkpoint_valid = checkpoint is not None
        if not enabled:
            action = "disabled"
            reason = ""
        elif stage not in selected:
            action = "reuse" if checkpoint_valid else "blocked"
            reason = "" if checkpoint_valid else "이번 실행에 포함되지 않았고 재사용할 완료 결과가 없습니다."
        elif trigger == "sync" and stage == 1:
            action = "process"
            reason = "최근 날짜 window를 다시 확인합니다."
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


def _window_ranges(start: date, end: date) -> list[tuple[date, date, bool]]:
    mutable_start = max(start, end - timedelta(days=MUTABLE_LOOKBACK_DAYS - 1))
    ranges: list[tuple[date, date, bool]] = []
    cursor = start
    while cursor < mutable_start:
        month_end = date(
            cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1]
        )
        chunk_end = min(month_end, mutable_start - timedelta(days=1), end)
        ranges.append((cursor, chunk_end, False))
        cursor = chunk_end + timedelta(days=1)
    while cursor <= end:
        ranges.append((cursor, cursor, True))
        cursor += timedelta(days=1)
    return ranges


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


def _window_file_summary(window_path: Path) -> tuple[int, int]:
    files = list(window_path.rglob("*_post_page_*.body"))
    return len(files), sum(path.stat().st_size for path in files)


def _window_body_hash(window_path: Path) -> str:
    digest = hashlib.sha256()
    for body_path in sorted(window_path.rglob("*.body")):
        digest.update(body_path.relative_to(window_path).as_posix().encode("utf-8"))
        with body_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _page_one_semantic_hash(window_path: Path) -> str:
    candidates = sorted(window_path.glob("*_post_page_00001.body"))
    if len(candidates) != 1:
        raise ValueError(f"KIND window page 1을 하나만 찾을 수 없습니다: {window_path}")
    return _canonical_hash(disclosure_file_rows(candidates[0]))


def _owned_window_matches(window_path: Path, query_hash: str) -> bool:
    try:
        payload = json.loads(_window_manifest_path(window_path).read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not (
        isinstance(payload, dict)
        and payload.get("format") == AUTOMATION_WINDOW_FORMAT
        and payload.get("query_hash") == query_hash
        and bool(payload.get("complete"))
    ):
        return False
    try:
        file_count, total_bytes = _window_file_summary(window_path)
    except OSError:
        return False
    return (
        file_count == payload.get("body_file_count")
        and total_bytes == payload.get("body_total_bytes")
        and _window_body_hash(window_path) == payload.get("data_hash")
    )


def _stage_one_windows_valid(profile: dict[str, Any]) -> bool:
    search = profile["decisions"]["s1_search"]
    start = date.fromisoformat(search["start_date"])
    end = date.fromisoformat(search["end_date"])
    windows_root = Path(profile["data_root"]) / "01-list" / ".automation-windows"
    expected_names: set[str] = set()
    for window_start, window_end, _mutable in _window_ranges(start, end):
        name = f"{window_start:%Y%m%d}_{window_end:%Y%m%d}"
        expected_names.add(name)
        query_hash = _canonical_hash(_window_query(profile, window_start, window_end))
        if not _owned_window_matches(windows_root / name, query_hash):
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
        manifest_path = _window_manifest_path(target)
        try:
            owner = json.loads(manifest_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"자동화 소유가 아닌 window를 교체할 수 없습니다: {target}") from exc
        if not isinstance(owner, dict) or owner.get("format") != AUTOMATION_WINDOW_FORMAT:
            raise ValueError(f"자동화 소유가 아닌 window를 교체할 수 없습니다: {target}")
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
        year = disclosed_at[:4] if len(disclosed_at) >= 4 and disclosed_at[:4].isdigit() else acpt_no[:4]
        if len(year) != 4 or not year.isdigit():
            year = "unknown"
        targets.append((acpt_no, year))
        seen.add(acpt_no)
    return targets


def _copy_reusable_active_html(
    current: Path, temporary: Path, targets: list[tuple[str, str]]
) -> int:
    if not current.is_dir():
        return 0
    copied = 0
    for acpt_no, year in targets:
        source = current / year / f"{acpt_no}.html"
        if not source.is_file() or not _is_valid_html(source):
            continue
        destination = temporary / year / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, destination)
        except OSError:
            shutil.copy2(source, destination)
        copied += 1
    return copied


def _active_html_outputs_valid(profile: dict[str, Any], stage: int) -> bool:
    try:
        root = Path(profile["data_root"])
        expected_targets = _active_disclosure_targets(
            root / "03-filter" / "filtered.json"
        )
        expected_membership = set(expected_targets)
        current = (
            root
            / ("04-external" if stage == 4 else "05-internal")
            / ".automation-current"
        )
        actual_files = sorted(current.rglob("*.html"))
        actual_membership = {(path.stem, path.parent.name) for path in actual_files}
        if actual_membership != expected_membership or any(
            not _is_valid_html(path) for path in actual_files
        ):
            return False
        if stage == 4:
            compressed_payload = json.loads(
                (root / "04-external" / "compressed-external-html.json").read_text(
                    "utf-8"
                )
            )
            records = compressed_payload.get("records")
            if not isinstance(records, list):
                return False
            if not expected_targets:
                return records == []
            content_targets, _ = _collect_content_targets_from_compressed_payload(
                compressed_payload
            )
            if {target["acpt_no"] for target in content_targets} != {
                acpt_no for acpt_no, _year in expected_targets
            } or len(content_targets) != len(expected_targets):
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
    search = profile["decisions"]["s1_search"]
    execution = profile["execution"]
    start = date.fromisoformat(search["start_date"])
    end = date.fromisoformat(search["end_date"])
    windows_root = Path(profile["data_root"]) / "01-list" / ".automation-windows"
    windows_root.mkdir(parents=True, exist_ok=True)
    refreshed = 0
    reused = 0
    changed = 0
    ranges = _window_ranges(start, end)
    desired_window_names = {
        f"{window_start:%Y%m%d}_{window_end:%Y%m%d}"
        for window_start, window_end, _mutable in ranges
    }
    for index, (window_start, window_end, mutable) in enumerate(ranges, start=1):
        if cancel_check():
            raise RuntimeError("Job cancelled")
        name = f"{window_start:%Y%m%d}_{window_end:%Y%m%d}"
        target = windows_root / name
        query = _window_query(profile, window_start, window_end)
        query_hash = _canonical_hash(query)
        should_refresh = trigger == "sync" and mutable
        if _owned_window_matches(target, query_hash) and not should_refresh:
            reused += 1
            progress_callback(f"window 재사용 {index}/{len(ranges)}: {name}")
            continue

        temporary = target.with_name(f".{target.name}.part-{uuid.uuid4().hex}")
        if temporary.exists():
            shutil.rmtree(temporary)
        progress_callback(f"window 수집 {index}/{len(ranges)}: {name}")
        try:
            previous_hash = ""
            if _owned_window_matches(target, query_hash):
                try:
                    previous_payload = json.loads(
                        _window_manifest_path(target).read_text("utf-8")
                    )
                    previous_hash = str(previous_payload.get("data_hash") or "")
                except (OSError, json.JSONDecodeError):
                    previous_hash = ""
            request_payload = {
                **query,
                "start_page": 1,
                "wait_seconds": KIND_AUTOMATION_WAIT_SECONDS,
                "timeout": execution["timeout"],
                "worker_count": 1,
                "last_report_only": False,
                "log_limit": 20,
            }
            result: dict[str, Any] | None = None
            for attempt in range(1, 4):
                if temporary.exists():
                    shutil.rmtree(temporary)
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
                    raise ValueError(f"KIND window 무결성 검사에 실패했습니다: {name}")

                probe = target.with_name(
                    f".{target.name}.probe-{uuid.uuid4().hex}"
                )
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
                    stable = _page_one_semantic_hash(temporary) == _page_one_semantic_hash(
                        probe
                    )
                finally:
                    if probe.exists():
                        shutil.rmtree(probe)
                if stable:
                    break
                progress_callback(
                    f"window page 이동 감지, 전체 재시도 {attempt}/3: {name}"
                )
            else:
                raise ValueError(
                    f"KIND window page 1이 세 번 연속 안정되지 않았습니다: {name}"
                )
            assert result is not None
            status = result.get("download_status") or {}
            data_hash = _window_body_hash(temporary)
            body_file_count, body_total_bytes = _window_file_summary(temporary)
            atomic_write_json(
                _window_manifest_path(temporary),
                {
                    "format": AUTOMATION_WINDOW_FORMAT,
                    "query_hash": query_hash,
                    "query": query,
                    "complete": True,
                    "data_hash": data_hash,
                    "body_file_count": body_file_count,
                    "body_total_bytes": body_total_bytes,
                    "summary": result.get("summary") or {},
                },
            )
            _replace_owned_window(target, temporary)
            refreshed += 1
            if not previous_hash or previous_hash != data_hash:
                changed += 1
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
                    f"자동화 window 경로에 소유하지 않은 항목이 있습니다: {child}"
                ) from exc
            if not isinstance(owner, dict) or owner.get("format") != AUTOMATION_WINDOW_FORMAT:
                raise ValueError(
                    f"자동화 window 경로에 소유하지 않은 항목이 있습니다: {child}"
                )
            shutil.rmtree(child)
            continue
        raise ValueError(f"자동화 window 경로에 예상하지 않은 파일이 있습니다: {child}")
    return {
        "windows": len(ranges),
        "refreshed_windows": refreshed,
        "reused_windows": reused,
        "changed_windows": changed,
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
                "classification_path": str(root / "01-list" / ".automation-windows"),
                "output_path": str(root / "02-table"),
                "table_name": "disclosures",
                "table_workers": execution["local_workers"],
            },
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
    if stage == 3:
        result = filter_disclosures_payload(
            {
                "classification_path": str(root / "02-table"),
                "filter_blocks": profile["decisions"]["s3_selection"]["filter_blocks"],
                "include_html_download_acpt_numbers": True,
                "filter_workers": execution["local_workers"],
                "progress_interval": 100,
            },
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        atomic_write_json(root / "03-filter" / "filtered.json", result)
        return result
    if stage == 4:
        filtered_path = root / "03-filter" / "filtered.json"
        targets = _active_disclosure_targets(filtered_path)
        current = root / "04-external" / ".automation-current"
        temporary = current.with_name(f".{current.name}.part-{uuid.uuid4().hex}")
        compressed_path = root / "04-external" / "compressed-external-html.json"
        try:
            temporary.mkdir(parents=True, exist_ok=True)
            reused = _copy_reusable_active_html(current, temporary, targets)
            if targets:
                download_result = download_disclosure_html_payload(
                    {
                        "source_json_path": str(filtered_path),
                        "output_directory": str(temporary),
                        "split_by_year": True,
                        "skip_existing": True,
                        "timeout": execution["timeout"],
                        "wait_seconds": KIND_AUTOMATION_WAIT_SECONDS,
                        "max_requests_per_minute": KIND_AUTOMATION_MAX_REQUESTS_PER_MINUTE,
                        "max_workers": 1,
                        "progress_interval": 25,
                        "cancel_token": uuid.uuid4().hex,
                    },
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
                )
                if download_result.get("cancelled") or download_result.get(
                    "saved_count"
                ) != download_result.get("requested_count"):
                    raise ValueError("외부 HTML 저장이 일부만 완료되었습니다.")
                compress_result = compress_disclosure_external_html_payload(
                    {
                        "input_directory": str(temporary),
                        "output_directory": str(temporary),
                        "input_split_by_year": True,
                        "workers": execution["local_workers"],
                    },
                    progress_callback=progress_callback,
                )
                if not (compress_result.get("verification") or {}).get("passed"):
                    raise ValueError("외부 HTML 압축 결과 재검사에 실패했습니다.")
                compressed_payload = json.loads(
                    (temporary / "compressed-external-html.json").read_text("utf-8")
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
                content_targets, _ = _collect_content_targets_from_compressed_payload(
                    compressed_payload
                )
                if (
                    {target["acpt_no"] for target in content_targets}
                    != expected_acpt_numbers
                    or len(content_targets) != len(targets)
                ):
                    raise ValueError(
                        "외부 HTML 압축 본문 대상이 필터 결과와 다릅니다."
                    )
            else:
                download_result = {
                    "requested_count": 0,
                    "saved_count": 0,
                    "reused_count": 0,
                }
                compressed_payload = {
                    "format": "finiq_disclosure_external_html_docs_v1",
                    "summary": {"found_files": 0, "compressed_files": 0},
                    "records": [],
                }
                atomic_write_json(
                    temporary / "compressed-external-html.json", compressed_payload
                )
                compress_result = {
                    "summary": {"found_files": 0, "compressed_files": 0}
                }
            atomic_write_json(
                temporary / "automation-external.json",
                {
                    "format": AUTOMATION_EXTERNAL_FORMAT,
                    "active_count": len(targets),
                    "reused_count": reused,
                    "complete": True,
                },
            )
            _replace_owned_html_directory(
                current,
                temporary,
                owner_name="automation-external.json",
                owner_format=AUTOMATION_EXTERNAL_FORMAT,
            )
            atomic_write_json(compressed_path, compressed_payload)
            return {"download": download_result, "compress": compress_result}
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    if stage == 5:
        filtered_path = root / "03-filter" / "filtered.json"
        targets = _active_disclosure_targets(filtered_path)
        current = root / "05-internal" / ".automation-current"
        temporary = current.with_name(f".{current.name}.part-{uuid.uuid4().hex}")
        try:
            temporary.mkdir(parents=True, exist_ok=True)
            reused = _copy_reusable_active_html(current, temporary, targets)
            if targets:
                result = download_disclosure_html_contents_payload(
                    {
                        "source_compressed_json_path": str(
                            root / "04-external" / "compressed-external-html.json"
                        ),
                        "output_directory": str(temporary),
                        "source_split_by_year": False,
                        "output_split_by_year": True,
                        "skip_existing": True,
                        "timeout": execution["timeout"],
                        "wait_seconds": KIND_AUTOMATION_WAIT_SECONDS,
                        "max_requests_per_minute": KIND_AUTOMATION_CONTENT_REQUESTS_PER_MINUTE,
                        "progress_interval": 25,
                        "cancel_token": uuid.uuid4().hex,
                    },
                    progress_callback=progress_callback,
                    cancel_check=cancel_check,
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
                temporary / "automation-internal.json",
                {
                    "format": AUTOMATION_INTERNAL_FORMAT,
                    "active_count": len(targets),
                    "reused_count": reused,
                    "complete": True,
                },
            )
            _replace_owned_html_directory(
                current,
                temporary,
                owner_name="automation-internal.json",
                owner_format=AUTOMATION_INTERNAL_FORMAT,
            )
            result["output_directory"] = str(current)
            return result
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    if stage == 6:
        pattern_result = summarize_disclosure_html_section_kinds_payload(
            {
                "input_directory": str(root / "05-internal" / ".automation-current"),
            },
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        if pattern_result.get("cancelled"):
            raise RuntimeError("Job cancelled")
        pattern_summary = pattern_result.get("summary") or {}
        if (
            int(pattern_summary.get("files_without_sections") or 0)
            or int(pattern_summary.get("failed_files") or 0)
        ):
            raise ValueError(
                "목차 조합 확인에 실패한 공시원문이 있습니다. "
                f"전체={pattern_summary.get('found_files', 0)}, "
                f"목차 없음={pattern_summary.get('files_without_sections', 0)}, "
                f"읽기 실패={pattern_summary.get('failed_files', 0)}"
            )
        rules = profile["decisions"]["s6_sections"]["section_save_rules"]
        unknown = [
            item
            for item in pattern_result.get("items") or []
            if str(item.get("signature") or "") not in rules
        ]
        if unknown:
            return {
                "needs_review": True,
                "review_patterns": unknown,
                "summary": pattern_result.get("summary") or {},
            }
        output_directory = root / "06-sections" / ".automation-current"
        temporary = output_directory.with_name(
            f".{output_directory.name}.part-{uuid.uuid4().hex}"
        )
        try:
            result = save_disclosure_html_sections_payload(
                {
                    "input_directory": str(root / "05-internal" / ".automation-current"),
                    "output_directory": str(temporary),
                    "workers": execution["local_workers"],
                    "section_save_rules": rules,
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
                    "rules_hash": _canonical_hash(rules),
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
        mode = execution["parser_mode"]
        result = parse_disclosure_html_payload(
            {
                "data_root": str(root),
                "mode": mode,
                "input_directory": str(root / "06-sections" / ".automation-current"),
                "output_directory": str(root / "07-converted" / mode),
                "filtered_metadata_path": str(root / "03-filter" / "filtered.json"),
                "compressed_metadata_path": str(
                    root / "04-external" / "compressed-external-html.json"
                ),
                "parallel_workers": execution["local_workers"],
                "skip_errors": False,
                "progress_interval": 25,
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
    prepare_disclosure_workspace_payload(
        {
            "data_root": profile["data_root"],
            "modes": [profile["execution"]["parser_mode"]],
        }
    )

    def emit(message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)

    def cancelled() -> bool:
        return bool(cancel_check and cancel_check())

    stage_results: list[dict[str, Any]] = []
    stage_one_changed: bool | None = None
    for stage_plan in plan["stages"]:
        stage = int(stage_plan["stage"])
        action = stage_plan["plan_action"]
        if cancelled():
            raise RuntimeError("Job cancelled")
        if (
            action == "process"
            and stage > 1
            and stage_one_changed is False
            and _load_valid_checkpoint(profile, stage) is not None
        ):
            action = "reuse"
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
        if stage == 1:
            stage_one_changed = int(result.get("changed_windows") or 0) > 0
        if stage == 6 and result.get("needs_review"):
            stage_results.append(
                {
                    "stage": stage,
                    "label": stage_plan["label"],
                    "status": "needs_review",
                    "result": result,
                }
            )
            emit("공시원문 목차 분리: 판단 필요")
            return {
                "format": "finiq_disclosure_automation_run_v1",
                "workflow_status": "needs_review",
                "profile_hash": plan["profile_hash"],
                "stages": stage_results,
                "review_patterns": result["review_patterns"],
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
