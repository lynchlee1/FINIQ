"""Workspace-owned disclosure filter workflow storage."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import threading
from typing import Any
import uuid

from finiq.market_desk.web.features.disclosure_workflow.layout import (
    atomic_write_json,
    resolve_disclosure_workspace,
    validate_workspace_mode,
)

FILTER_WORKFLOW_FORMAT = "finiq_disclosure_filter_workflow"
FILTER_WORKFLOW_DIRECTORY_FORMAT = "finiq_disclosure_filter_workflow_directory"
FILTER_RESULT_FORMAT = "kind_disclosure_filter_v1"
FILTER_INTEGRITY_REPAIR = (
    "02단계 데이터베이스를 초기화하고 01단계부터 다시 실행하세요."
)
FILTER_WORKFLOW_STATUSES = {
    "ready",
    "running",
    "interrupted",
    "completed",
    "failed",
}
FILTER_STEP_STATUSES = {
    "pending",
    "running",
    "interrupted",
    "completed",
    "failed",
}
_WORKFLOWS_LOCK = threading.RLock()
_ACTIVE_RUNS: dict[str, str] = {}


def _integrity_error(message: str) -> ValueError:
    return ValueError(f"{message} {FILTER_INTEGRITY_REPAIR}")


def _workflow_directory(data_root: object) -> Path:
    return resolve_disclosure_workspace(str(data_root or "")).filtered


def _normalize_condition_input(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("filter workflow must be an object")
    condition_blocks = value.get("condition_blocks")
    if not isinstance(condition_blocks, list) or not all(
        isinstance(block, dict) for block in condition_blocks
    ):
        raise ValueError("filter workflow condition_blocks must be a list of objects")
    mode = validate_workspace_mode(value.get("mode"))
    parent_value = value.get("parent_mode")
    parent_mode = (
        validate_workspace_mode(parent_value)
        if parent_value is not None and str(parent_value).strip()
        else None
    )
    if parent_mode == mode:
        raise ValueError("parent_mode must be different from mode")
    normalized = {
        "name": mode,
        "mode": mode,
        "condition_blocks": condition_blocks,
    }
    if parent_mode is not None:
        normalized.update(
            {
                "id": f"{parent_mode}/{mode}",
                "parent_mode": parent_mode,
            }
        )
    else:
        normalized["id"] = mode
    return normalized


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid disclosure filter workflow JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid disclosure filter workflow JSON: {path}")
    return payload


def _required_step(steps: object, name: str) -> dict[str, Any]:
    if not isinstance(steps, dict) or not isinstance(steps.get(name), dict):
        raise ValueError(f"filter workflow steps.{name} must be an object")
    step = dict(steps[name])
    if step.get("status") not in FILTER_STEP_STATUSES:
        raise ValueError(f"filter workflow steps.{name}.status is invalid")
    return step


def _required_count(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    if isinstance(value, float) and (
        not math.isfinite(value) or not value.is_integer()
    ):
        raise ValueError(f"{field} must be an integer")
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if count < 0:
        raise ValueError(f"{field} must be >= 0")
    return count


def _filter_result_counts(payload: dict[str, Any]) -> tuple[int, int, int, int]:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("filter result summary must be an object")
    source_disclosures = _required_count(
        summary.get("source_disclosures"), "summary.source_disclosures"
    )
    source_offset = _required_count(
        summary.get("source_offset"), "summary.source_offset"
    )
    target_disclosures = _required_count(
        summary.get("target_disclosures"), "summary.target_disclosures"
    )
    inspected_disclosures = _required_count(
        summary.get("inspected_disclosures"), "summary.inspected_disclosures"
    )
    if target_disclosures != source_disclosures - source_offset:
        raise _integrity_error(
            "filter result target count does not match source count and offset"
        )
    if inspected_disclosures > target_disclosures:
        raise _integrity_error(
            "filter result inspected count exceeds its target count"
        )
    return (
        source_disclosures,
        source_offset,
        target_disclosures,
        inspected_disclosures,
    )


def _validate_filter_result(
    payload: object,
    *,
    condition_blocks: list[dict[str, Any]],
    require_complete: bool,
) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("format") != FILTER_RESULT_FORMAT:
        raise ValueError("filter workflow result has an invalid format")
    filters = payload.get("filters")
    if not isinstance(filters, dict) or filters.get("filter_blocks") != condition_blocks:
        raise ValueError("filter workflow result conditions do not match the workflow")
    disclosures = payload.get("disclosures")
    if not isinstance(disclosures, list):
        raise ValueError("filter workflow result disclosures must be a list")
    acpt_numbers: list[str] = []
    for index, disclosure in enumerate(disclosures):
        if not isinstance(disclosure, dict):
            raise ValueError(f"filter result disclosures[{index}] must be an object")
        acpt_no = str(disclosure.get("acpt_no") or "").strip()
        if not acpt_no:
            raise ValueError(f"filter result disclosures[{index}].acpt_no is required")
        acpt_numbers.append(acpt_no)
    if len(acpt_numbers) != len(set(acpt_numbers)):
        raise _integrity_error(
            "filter workflow result contains duplicate acpt_no values"
        )

    source_disclosures, source_offset, target_disclosures, inspected_disclosures = (
        _filter_result_counts(payload)
    )
    summary = payload["summary"]
    returned_disclosures = _required_count(
        summary.get("returned_disclosures"), "summary.returned_disclosures"
    )
    unique_acpt_numbers = _required_count(
        summary.get("unique_acpt_numbers"), "summary.unique_acpt_numbers"
    )
    if returned_disclosures != len(disclosures) or unique_acpt_numbers != len(
        disclosures
    ):
        raise _integrity_error(
            "filter workflow result counts do not match disclosures"
        )

    integrity = payload.get("integrity")
    if not isinstance(integrity, dict):
        raise ValueError("filter workflow result integrity must be an object")
    integrity_target = _required_count(
        integrity.get("search_target_disclosures"),
        "integrity.search_target_disclosures",
    )
    integrity_result = _required_count(
        integrity.get("search_result_disclosures"),
        "integrity.search_result_disclosures",
    )
    integrity_inspected = _required_count(
        integrity.get("inspected_disclosures"), "integrity.inspected_disclosures"
    )
    if (
        integrity_target != target_disclosures
        or integrity_result != len(disclosures)
        or integrity_inspected != inspected_disclosures
    ):
        raise _integrity_error(
            "filter workflow result integrity counts do not match"
        )
    if require_complete and (
        integrity.get("complete") is not True
        or integrity.get("passed") is not True
        or inspected_disclosures != target_disclosures
    ):
        raise _integrity_error("filter workflow result integrity did not pass")
    if not require_complete and (
        integrity.get("complete") is not False
        or integrity.get("passed") is not False
    ):
        raise ValueError(
            "interrupted filter result integrity flags must be false"
        )
    if source_offset > source_disclosures:
        raise _integrity_error("filter workflow result source offset is invalid")
    return payload


def _result_source_count(result: object) -> int:
    if not isinstance(result, dict):
        return 0
    summary = result.get("summary")
    if not isinstance(summary, dict):
        return 0
    return _required_count(summary.get("source_disclosures"), "summary.source_disclosures")


def _pending_result(document: dict[str, Any]) -> dict[str, Any] | None:
    pending = document.get("pending")
    if not isinstance(pending, dict):
        return None
    result = pending.get("result")
    return result if isinstance(result, dict) else None


def _read_workflow(
    path: Path,
    *,
    document: dict[str, Any] | None = None,
    load_results: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = _read_json_object(path) if document is None else document
    if not isinstance(payload, dict) or payload.get("format") != FILTER_WORKFLOW_FORMAT:
        raise ValueError(f"Invalid disclosure filter workflow JSON: {path}")
    status = payload.get("status")
    if status not in FILTER_WORKFLOW_STATUSES:
        raise ValueError(f"filter workflow status is invalid: {path}")
    condition_step = _required_step(payload.get("steps"), "condition_input")
    query_step = _required_step(payload.get("steps"), "database_query")
    record_step = _required_step(payload.get("steps"), "record")
    if condition_step.get("status") != "completed":
        raise ValueError(f"filter workflow condition input is incomplete: {path}")
    state = (status, query_step["status"], record_step["status"])
    if state not in {
        ("ready", "pending", "pending"),
        ("running", "running", "pending"),
        ("running", "completed", "running"),
        ("interrupted", "interrupted", "pending"),
        ("interrupted", "completed", "interrupted"),
        ("completed", "completed", "completed"),
        ("failed", "failed", "pending"),
        ("failed", "completed", "failed"),
    }:
        raise ValueError(f"filter workflow step statuses are inconsistent: {path}")
    condition_blocks = condition_step.get("filter_blocks")
    if (
        path.parent.parent.name == "subfilters"
        and path.parents[3].name != "03-filter"
    ):
        raise ValueError("derived filter workflows support only one nesting level")
    path_parent_mode = (
        path.parents[2].name if path.parent.parent.name == "subfilters" else None
    )
    normalized = _normalize_condition_input(
        {
            "mode": path.parent.name,
            "parent_mode": path_parent_mode,
            "condition_blocks": condition_blocks,
        }
    )
    if payload.get("mode") != normalized["mode"]:
        raise ValueError(f"filter workflow mode does not match its directory: {path}")
    if payload.get("parent_mode") != normalized.get("parent_mode"):
        raise ValueError(
            f"filter workflow parent_mode does not match its directory: {path}"
        )
    if normalized.get("parent_mode") is not None:
        fingerprint = str(payload.get("parent_result_fingerprint") or "").strip()
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            raise ValueError(
                "derived filter workflow parent result fingerprint is invalid"
            )
        normalized["parent_result_fingerprint"] = fingerprint

    embedded_result = payload.get("result")
    result_file = str(payload.get("result_file") or "").strip()
    has_result = isinstance(embedded_result, dict) or bool(result_file)
    result = embedded_result
    if load_results and result is None and result_file:
        result = _read_json_object(_workflow_sidecar_path(path, result_file))
    if load_results and result is not None:
        _validate_filter_result(
            result,
            condition_blocks=normalized["condition_blocks"],
            require_complete=True,
        )
        result_fingerprint = _canonical_result_sha256(result)
        stored_fingerprint = str(payload.get("result_fingerprint") or "").strip()
        if stored_fingerprint and stored_fingerprint != result_fingerprint:
            raise ValueError(f"filter workflow result fingerprint is invalid: {path}")
        payload["result"] = result
        payload["_result_file"] = result_file
        payload["_result_fingerprint"] = result_fingerprint
        if normalized.get("parent_mode") is not None and (
            result.get("parent_mode") != normalized["parent_mode"]
            or result.get("parent_result_fingerprint")
            != normalized["parent_result_fingerprint"]
        ):
            raise ValueError(
                "derived filter result provenance does not match the workflow"
            )
    embedded_pending = payload.get("pending")
    pending_file = str(payload.get("pending_file") or "").strip()
    has_pending = isinstance(embedded_pending, dict) or bool(pending_file)
    pending = embedded_pending
    if load_results and pending is None and pending_file:
        pending = _read_json_object(_workflow_sidecar_path(path, pending_file))
    if load_results and pending is not None:
        if not isinstance(pending, dict) or not isinstance(pending.get("result"), dict):
            raise ValueError("filter workflow pending result is invalid")
        _validate_filter_result(
            pending["result"],
            condition_blocks=normalized["condition_blocks"],
            require_complete=False,
        )
        pending_fingerprint = _canonical_payload_sha256(pending)
        stored_fingerprint = str(payload.get("pending_fingerprint") or "").strip()
        if stored_fingerprint and stored_fingerprint != pending_fingerprint:
            raise ValueError(f"filter workflow pending fingerprint is invalid: {path}")
        payload["pending"] = pending
        payload["_pending_file"] = pending_file
        payload["_pending_fingerprint"] = pending_fingerprint
    if status == "ready" and (has_result or has_pending):
        raise ValueError("ready filter workflow must not contain a result")
    if status == "completed" and (not has_result or has_pending):
        raise ValueError("completed filter workflow must contain only a completed result")
    if status == "interrupted" and not has_pending:
        raise ValueError("interrupted filter workflow must contain a pending result")

    workflow = {
        **normalized,
        "status": status,
        "steps": {
            "condition_input": condition_step,
            "database_query": query_step,
            "record": record_step,
        },
    }
    if isinstance(result, dict):
        workflow["result_summary"] = result.get("summary") or {}
        workflow["result_fingerprint"] = payload.get("_result_fingerprint")
    elif has_result:
        workflow["result_summary"] = payload.get("result_summary") or {}
        workflow["result_fingerprint"] = payload.get("result_fingerprint")
    if isinstance(pending, dict):
        pending_result = pending.get("result")
        workflow["pending_summary"] = (
            pending_result.get("summary") if isinstance(pending_result, dict) else {}
        )
    elif has_pending:
        workflow["pending_summary"] = payload.get("pending_summary") or {}
    return payload, workflow


def _read_workflows(
    directory: Path,
    *,
    require_workflow_format: bool = False,
    validate_parent_state: bool = False,
    load_results: bool = True,
) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ValueError(f"Invalid disclosure filter workflow directory: {directory}")
    workflows: list[dict[str, Any]] = []
    paths = [
        *directory.glob("*/filter.json"),
        *directory.glob("*/subfilters/*/filter.json"),
    ]
    for path in paths:
        document = _read_json_object(path)
        if document.get("format") != FILTER_WORKFLOW_FORMAT:
            if require_workflow_format:
                raise ValueError(f"Invalid disclosure filter workflow JSON: {path}")
            continue
        _payload, workflow = _read_workflow(
            path,
            document=document,
            load_results=load_results,
        )
        if validate_parent_state and workflow.get("parent_mode") is not None:
            try:
                if load_results:
                    _require_current_parent(data_root=directory.parent, workflow=workflow)
                else:
                    _require_current_parent_metadata(
                        data_root=directory.parent,
                        workflow=workflow,
                    )
            except ValueError as error:
                if require_workflow_format:
                    raise
                workflow = {
                    **workflow,
                    "status": "failed",
                    "parent_error": str(error),
                }
        workflows.append(workflow)
    return sorted(workflows, key=lambda item: item["id"])


def _new_workflow_document(workflow: dict[str, Any]) -> dict[str, Any]:
    now = _utc_now()
    document = {
        "format": FILTER_WORKFLOW_FORMAT,
        "mode": workflow["mode"],
        "status": "ready",
        "steps": {
            "condition_input": {
                "status": "completed",
                "completed_at": now,
                "filter_blocks": workflow["condition_blocks"],
            },
            "database_query": {"status": "pending"},
            "record": {"status": "pending"},
        },
        "result": None,
        "pending": None,
    }
    if workflow.get("parent_mode") is not None:
        document["parent_mode"] = workflow["parent_mode"]
        document["parent_result_fingerprint"] = workflow["parent_result_fingerprint"]
    return document


def _write_workflow(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = dict(payload)

    result = payload.get("result")
    if isinstance(result, dict):
        result_fingerprint = str(payload.get("_result_fingerprint") or "")
        result_file = str(payload.get("_result_file") or "")
        if not result_fingerprint:
            result_fingerprint = _canonical_result_sha256(result)
        canonical_result_file = "filtered.json"
        result_path = path.with_name(canonical_result_file)
        if result_file != canonical_result_file or not result_path.is_file():
            atomic_write_json(result_path, result)
        result_file = canonical_result_file
        document["result_file"] = result_file
        document["result_fingerprint"] = result_fingerprint
        document["result_summary"] = result.get("summary") or {}
    else:
        document.pop("result_file", None)
        document.pop("result_fingerprint", None)
        document.pop("result_summary", None)
    document.pop("result", None)

    pending = payload.get("pending")
    if isinstance(pending, dict):
        pending_fingerprint = str(payload.get("_pending_fingerprint") or "")
        pending_file = str(payload.get("_pending_file") or "")
        if not pending_fingerprint:
            pending_fingerprint = _canonical_payload_sha256(pending)
        canonical_pending_file = "filter.pending.json"
        pending_path = path.with_name(canonical_pending_file)
        if pending_file != canonical_pending_file or not pending_path.is_file():
            atomic_write_json(pending_path, pending)
        pending_file = canonical_pending_file
        document["pending_file"] = pending_file
        document["pending_fingerprint"] = pending_fingerprint
        pending_result = pending.get("result")
        document["pending_summary"] = (
            pending_result.get("summary") if isinstance(pending_result, dict) else {}
        )
    else:
        document.pop("pending_file", None)
        document.pop("pending_fingerprint", None)
        document.pop("pending_summary", None)
    document.pop("pending", None)

    for key in [key for key in document if key.startswith("_")]:
        document.pop(key, None)
    atomic_write_json(path, document)
    if path.name == "filter.json":
        referenced = {
            str(document.get("result_file") or ""),
            str(document.get("pending_file") or ""),
        }
        canonical_result = path.with_name("filtered.json")
        if canonical_result.name not in referenced:
            canonical_result.unlink(missing_ok=True)
        for pattern in ("filter.result-*.json", "filter.pending-*.json"):
            for sidecar in path.parent.glob(pattern):
                if sidecar.name not in referenced:
                    sidecar.unlink(missing_ok=True)
        fixed_pending = path.with_name("filter.pending.json")
        if fixed_pending.name not in referenced:
            fixed_pending.unlink(missing_ok=True)


def _workflow_sidecar_path(path: Path, file_name: str) -> Path:
    if not file_name or Path(file_name).name != file_name:
        raise ValueError(f"Invalid disclosure filter workflow sidecar: {path}")
    sidecar = path.with_name(file_name)
    if sidecar.suffix != ".json":
        raise ValueError(f"Invalid disclosure filter workflow sidecar: {sidecar}")
    return sidecar


def _canonical_payload_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _set_workflow_result(document: dict[str, Any], result: dict[str, Any] | None) -> None:
    document["result"] = result
    document.pop("_result_file", None)
    document.pop("_result_fingerprint", None)


def _set_workflow_pending(document: dict[str, Any], pending: dict[str, Any] | None) -> None:
    document["pending"] = pending
    document.pop("_pending_file", None)
    document.pop("_pending_fingerprint", None)


def _discard_working_workflow(path: Path) -> None:
    path.unlink(missing_ok=True)
    for sidecar in path.parent.glob(f"{path.stem}.*.json"):
        sidecar.unlink(missing_ok=True)


def _workflow_path(
    data_root: object, mode: object, parent_mode: object = None
) -> Path:
    mode = validate_workspace_mode(mode)
    if parent_mode is None or not str(parent_mode).strip():
        return _workflow_directory(data_root) / mode / "filter.json"
    parent = validate_workspace_mode(parent_mode)
    if parent == mode:
        raise ValueError("parent_mode must be different from mode")
    return _workflow_directory(data_root) / parent / "subfilters" / mode / "filter.json"


def filter_workflow_path(
    data_root: object, mode: object, parent_mode: object = None
) -> Path:
    return _workflow_path(data_root, mode, parent_mode)


def _canonical_result_sha256(result: dict[str, Any]) -> str:
    canonical = json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _completed_parent_result(
    data_root: object, parent_mode: object
) -> tuple[dict[str, Any], str]:
    parent = validate_workspace_mode(parent_mode)
    parent_path = _workflow_path(data_root, parent)
    if not parent_path.is_file():
        raise ValueError(f"Parent filter workflow not found: {parent}")
    document, workflow = _read_workflow(parent_path)
    result = document.get("result")
    if workflow["status"] != "completed" or not isinstance(result, dict):
        raise ValueError(f"Parent filter workflow is not completed: {parent}")
    return result, str(workflow["result_fingerprint"])


def _completed_parent_fingerprint(data_root: object, parent_mode: object) -> str:
    parent = validate_workspace_mode(parent_mode)
    parent_path = _workflow_path(data_root, parent)
    if not parent_path.is_file():
        raise ValueError(f"Parent filter workflow not found: {parent}")
    _document, workflow = _read_workflow(parent_path, load_results=False)
    if workflow["status"] != "completed":
        raise ValueError(f"Parent filter workflow is not completed: {parent}")
    fingerprint = str(workflow.get("result_fingerprint") or "").strip()
    if not fingerprint:
        _document, workflow = _read_workflow(parent_path)
        fingerprint = str(workflow.get("result_fingerprint") or "").strip()
    return fingerprint


def _require_current_parent(
    *, data_root: object, workflow: dict[str, Any]
) -> dict[str, Any] | None:
    parent_mode = workflow.get("parent_mode")
    if parent_mode is None:
        return None
    result, fingerprint = _completed_parent_result(data_root, parent_mode)
    if fingerprint != workflow.get("parent_result_fingerprint"):
        raise ValueError(
            "Derived filter workflow is stale because parent result changed: "
            f"{workflow['id']}"
        )
    return result


def _require_current_parent_metadata(
    *, data_root: object, workflow: dict[str, Any]
) -> None:
    parent_mode = workflow.get("parent_mode")
    if parent_mode is None:
        return
    parent = validate_workspace_mode(parent_mode)
    parent_path = _workflow_path(data_root, parent)
    if not parent_path.is_file():
        raise ValueError(f"Parent filter workflow not found: {parent}")
    _document, parent_workflow = _read_workflow(
        parent_path,
        load_results=False,
    )
    if parent_workflow["status"] != "completed":
        raise ValueError(f"Parent filter workflow is not completed: {parent}")
    fingerprint = parent_workflow.get("result_fingerprint")
    if not fingerprint:
        _document, parent_workflow = _read_workflow(parent_path)
        fingerprint = parent_workflow.get("result_fingerprint")
    if fingerprint != workflow.get("parent_result_fingerprint"):
        raise ValueError(
            "Derived filter workflow is stale because parent result changed: "
            f"{workflow['id']}"
        )


def load_filter_workflow_result_payload(
    *,
    data_root: object,
    mode: object,
    condition_blocks: object,
    parent_mode: object = None,
) -> dict[str, Any]:
    path = _workflow_path(data_root, mode, parent_mode)
    requested = _normalize_condition_input(
        {
            "mode": mode,
            "parent_mode": parent_mode,
            "condition_blocks": condition_blocks,
        }
    )
    with _WORKFLOWS_LOCK:
        if not path.is_file():
            raise ValueError(f"Filter workflow not found: {requested['mode']}")
        document, workflow = _read_workflow(path)
        _require_current_parent(data_root=data_root, workflow=workflow)
        if (
            workflow["mode"] != requested["mode"]
            or workflow["condition_blocks"] != requested["condition_blocks"]
        ):
            raise ValueError("Saved filter workflow conditions do not match the request")
        if workflow["status"] != "completed" or not isinstance(
            document.get("result"), dict
        ):
            raise ValueError(f"Filter workflow is not completed: {requested['mode']}")
        return copy.deepcopy(document["result"])


def _working_path(path: Path, run_id: str) -> Path:
    return path.with_name(f".filter-run-{run_id}.json")


def _active_key(path: Path) -> str:
    return str(path.resolve())


def _require_active_run(path: Path, run_id: str) -> Path:
    if _ACTIVE_RUNS.get(_active_key(path)) != run_id:
        raise ValueError(f"Filter workflow run is not active: {path.parent.name}")
    working_path = _working_path(path, run_id)
    if not working_path.is_file():
        raise ValueError(f"Filter workflow run file is missing: {path.parent.name}")
    return working_path


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(record.get("disclosed_at") or ""),
        str(record.get("company_name") or ""),
        str(record.get("title") or ""),
    )


def _merge_filter_results(
    payloads: list[dict[str, Any]],
    *,
    condition_blocks: list[dict[str, Any]],
    initial_offset: int,
    source_disclosures: int,
    complete: bool,
) -> dict[str, Any]:
    cursor = initial_offset
    disclosures_by_acpt_no: dict[str, dict[str, Any]] = {}
    duplicate_disclosures = 0
    unique_titles: list[str] = []
    seen_titles: set[str] = set()
    latest_payload: dict[str, Any] | None = None

    for payload in payloads:
        validated = _validate_filter_result(
            payload,
            condition_blocks=condition_blocks,
            require_complete=bool((payload.get("integrity") or {}).get("complete")),
        )
        (
            _payload_source_count,
            source_offset,
            _target_count,
            inspected_count,
        ) = _filter_result_counts(validated)
        if source_offset != cursor:
            raise _integrity_error("04단계 처리 구간이 이어지지 않습니다.")
        cursor += inspected_count
        latest_payload = validated
        duplicate_disclosures += _required_count(
            (validated.get("summary") or {}).get("duplicate_disclosures", 0),
            "summary.duplicate_disclosures",
        )
        for title in validated.get("unique_titles") or []:
            normalized_title = str(title or "").strip()
            if normalized_title and normalized_title not in seen_titles:
                seen_titles.add(normalized_title)
                unique_titles.append(normalized_title)
        for disclosure in validated["disclosures"]:
            acpt_no = str(disclosure["acpt_no"])
            if acpt_no in disclosures_by_acpt_no:
                raise _integrity_error(
                    "04단계 신규 구간에 이미 처리한 접수번호가 있습니다. "
                    f"중복 접수번호={acpt_no}."
                )
            disclosures_by_acpt_no[acpt_no] = disclosure

    if complete and cursor != source_disclosures:
        raise _integrity_error(
            "04단계 검색 대상 건수와 검사 완료 건수가 다릅니다. "
            f"검색 대상={source_disclosures}, 검사 완료={cursor}"
        )
    if latest_payload is None:
        raise ValueError("filter workflow did not produce a result")

    disclosures = sorted(
        disclosures_by_acpt_no.values(), key=_record_sort_key, reverse=True
    )
    filters = dict(latest_payload["filters"])
    inspected_disclosures = cursor - initial_offset
    result = {
        "format": FILTER_RESULT_FORMAT,
        "source_type": latest_payload.get("source_type") or "sqlite_manifest",
        "filters": filters,
        "summary": {
            "source_disclosures": source_disclosures,
            "source_body_files": 0,
            "source_offset": initial_offset,
            "target_disclosures": source_disclosures - initial_offset,
            "inspected_disclosures": inspected_disclosures,
            "matched_disclosures": len(disclosures),
            "returned_disclosures": len(disclosures),
            "duplicate_disclosures": duplicate_disclosures,
            "unique_acpt_numbers": len(disclosures),
        },
        "integrity": {
            "complete": complete,
            "passed": complete and cursor == source_disclosures,
            "search_target_disclosures": source_disclosures - initial_offset,
            "search_result_disclosures": len(disclosures),
            "inspected_disclosures": inspected_disclosures,
        },
        "unique_titles": unique_titles,
        "disclosures": disclosures,
        "external_html_download_acpt_numbers": [
            str(disclosure["acpt_no"]) for disclosure in disclosures
        ],
    }
    if complete and source_disclosures - initial_offset != inspected_disclosures:
        raise _integrity_error("filter workflow completion counts do not match")
    return result


def begin_filter_workflow_payload(payload: dict[str, Any]) -> dict[str, Any]:
    path = _workflow_path(
        payload.get("data_root"), payload.get("mode"), payload.get("parent_mode")
    )
    requested = _normalize_condition_input(
        {
            "mode": payload.get("mode"),
            "parent_mode": payload.get("parent_mode"),
            "condition_blocks": payload.get("filter_blocks"),
        }
    )
    with _WORKFLOWS_LOCK:
        if not path.is_file():
            raise ValueError(f"Filter workflow not found: {requested['mode']}")
        document, workflow = _read_workflow(path)
        parent_result = _require_current_parent(
            data_root=payload.get("data_root"), workflow=workflow
        )
        if _active_key(path) in _ACTIVE_RUNS:
            raise ValueError(f"Filter workflow is already running: {requested['mode']}")
        if (
            workflow["mode"] != requested["mode"]
            or workflow["condition_blocks"] != requested["condition_blocks"]
        ):
            raise ValueError("Save the filter conditions before running the workflow")

        committed_result = document.get("result")
        source_offset = _result_source_count(committed_result)
        source_expected_count = (
            _result_source_count(committed_result)
            if isinstance(committed_result, dict)
            else None
        )
        pending_result = _pending_result(document)
        if pending_result is not None:
            source_expected_count = _filter_result_counts(pending_result)[0]
            source_offset += _filter_result_counts(pending_result)[3]

        run_id = uuid.uuid4().hex
        working_path = _working_path(path, run_id)
        working_document = copy.deepcopy(document)
        working_document["status"] = "running"
        working_document["steps"]["database_query"] = {
            "status": "running",
            "run_id": run_id,
            "started_at": _utc_now(),
            "source_offset": source_offset,
        }
        working_document["steps"]["record"] = {"status": "pending"}
        _write_workflow(working_path, working_document)
        _ACTIVE_RUNS[_active_key(path)] = run_id
    response = {
        **workflow,
        "status": "running",
        "path": str(path),
        "run_id": run_id,
        "source_offset": source_offset,
        "source_expected_count": source_expected_count,
    }
    if parent_result is not None:
        response["parent_acpt_numbers"] = [
            str(item["acpt_no"]) for item in parent_result["disclosures"]
        ]
    return response


def mark_filter_workflow_query_completed(
    *, data_root: object, mode: object, run_id: str, summary: object,
    parent_mode: object = None,
) -> dict[str, Any]:
    path = _workflow_path(data_root, mode, parent_mode)
    with _WORKFLOWS_LOCK:
        working_path = _require_active_run(path, run_id)
        document, _workflow = _read_workflow(working_path)
        query_step = document["steps"]["database_query"]
        if document.get("status") != "running" or query_step.get("run_id") != run_id:
            raise ValueError(f"Filter workflow run is not active: {path.parent.name}")
        query_step.update(
            {
                "status": "completed",
                "completed_at": _utc_now(),
                "summary": summary if isinstance(summary, dict) else {},
            }
        )
        document["steps"]["record"] = {
            "status": "running",
            "run_id": run_id,
            "started_at": _utc_now(),
        }
        _write_workflow(working_path, document)
        return _read_workflow(working_path)[1]


def complete_filter_workflow_payload(
    *,
    data_root: object,
    mode: object,
    run_id: str,
    result: object,
    parent_mode: object = None,
) -> dict[str, Any]:
    path = _workflow_path(data_root, mode, parent_mode)
    with _WORKFLOWS_LOCK:
        working_path = _require_active_run(path, run_id)
        document, workflow = _read_workflow(working_path)
        parent_result = _require_current_parent(data_root=data_root, workflow=workflow)
        record_step = document["steps"]["record"]
        if document.get("status") != "running" or record_step.get("run_id") != run_id:
            raise ValueError(f"Filter workflow run is not active: {path.parent.name}")
        current_result = _validate_filter_result(
            result,
            condition_blocks=workflow["condition_blocks"],
            require_complete=True,
        )
        source_disclosures = _filter_result_counts(current_result)[0]
        current_source_offset = _filter_result_counts(current_result)[1]
        result_payloads: list[dict[str, Any]] = []
        committed_result = document.get("result")
        if isinstance(committed_result, dict):
            result_payloads.append(committed_result)
        pending_result = _pending_result(document)
        if pending_result is not None:
            result_payloads.append(pending_result)
        if current_source_offset == 0 and any(
            _result_source_count(payload) != source_disclosures
            for payload in result_payloads
        ):
            result_payloads = []
        result_payloads.append(current_result)
        merged_result = _merge_filter_results(
            result_payloads,
            condition_blocks=workflow["condition_blocks"],
            initial_offset=0,
            source_disclosures=source_disclosures,
            complete=True,
        )
        merged_result["mode"] = workflow["mode"]
        if parent_result is not None:
            parent_acpt_numbers = {
                str(item["acpt_no"]) for item in parent_result["disclosures"]
            }
            child_acpt_numbers = {
                str(item["acpt_no"]) for item in merged_result["disclosures"]
            }
            if not child_acpt_numbers.issubset(parent_acpt_numbers):
                raise _integrity_error(
                    "derived filter result contains disclosures outside its parent"
                )
            merged_result["parent_mode"] = workflow["parent_mode"]
            merged_result["parent_result_fingerprint"] = workflow[
                "parent_result_fingerprint"
            ]

        document["status"] = "completed"
        _set_workflow_result(document, merged_result)
        _set_workflow_pending(document, None)
        record_step.update(
            {
                "status": "completed",
                "completed_at": _utc_now(),
                "summary": merged_result["summary"],
            }
        )
        _write_workflow(path, document)
        _discard_working_workflow(working_path)
        _ACTIVE_RUNS.pop(_active_key(path), None)
        _document, completed_workflow = _read_workflow(path)
        return {**completed_workflow, "result": merged_result}


def interrupt_filter_workflow_payload(
    *,
    data_root: object,
    mode: object,
    run_id: str,
    partial_result: object,
    parent_mode: object = None,
) -> dict[str, Any] | None:
    path = _workflow_path(data_root, mode, parent_mode)
    with _WORKFLOWS_LOCK:
        try:
            working_path = _require_active_run(path, run_id)
            document, workflow = _read_workflow(working_path)
        except ValueError:
            return None
        current_partial = (
            _validate_filter_result(
                partial_result,
                condition_blocks=workflow["condition_blocks"],
                require_complete=False,
            )
            if isinstance(partial_result, dict)
            else None
        )
        if current_partial is None or _filter_result_counts(current_partial)[3] == 0:
            _discard_working_workflow(working_path)
            _ACTIVE_RUNS.pop(_active_key(path), None)
            return None
        source_disclosures, current_source_offset, _, _ = _filter_result_counts(
            current_partial
        )
        committed_result = document.get("result")
        committed_count = _result_source_count(committed_result)
        pending_payloads: list[dict[str, Any]] = []
        previous_pending = _pending_result(document)
        if previous_pending is not None:
            pending_payloads.append(previous_pending)
        prior_payloads = [
            payload
            for payload in [committed_result, previous_pending]
            if isinstance(payload, dict)
        ]
        if current_source_offset == 0 and any(
            _result_source_count(payload) != source_disclosures
            for payload in prior_payloads
        ):
            _set_workflow_result(document, None)
            committed_count = 0
            pending_payloads = []
        pending_payloads.append(current_partial)
        merged_pending = _merge_filter_results(
            pending_payloads,
            condition_blocks=workflow["condition_blocks"],
            initial_offset=committed_count,
            source_disclosures=source_disclosures,
            complete=False,
        )
        document["status"] = "interrupted"
        _set_workflow_pending(
            document,
            {
                "interrupted_at": _utc_now(),
                "result": merged_pending,
            },
        )
        query_step = document["steps"]["database_query"]
        record_step = document["steps"]["record"]
        if query_step.get("status") == "running":
            query_step.update({"status": "interrupted", "interrupted_at": _utc_now()})
            document["steps"]["record"] = {"status": "pending"}
        else:
            record_step.update({"status": "interrupted", "interrupted_at": _utc_now()})
        _write_workflow(path, document)
        _discard_working_workflow(working_path)
        _ACTIVE_RUNS.pop(_active_key(path), None)
        return _read_workflow(path)[1]


def fail_filter_workflow_payload(
    *, data_root: object, mode: object, run_id: str, error: object,
    parent_mode: object = None,
) -> dict[str, Any] | None:
    path = _workflow_path(data_root, mode, parent_mode)
    with _WORKFLOWS_LOCK:
        try:
            working_path = _require_active_run(path, run_id)
            document, _workflow = _read_workflow(working_path)
        except ValueError:
            return None
        query_step = document["steps"]["database_query"]
        record_step = document["steps"]["record"]
        active_step = (
            query_step
            if query_step.get("status") == "running"
            else record_step
            if record_step.get("status") == "running"
            else None
        )
        if active_step is None:
            return None
        document["status"] = "failed"
        active_step.update(
            {
                "status": "failed",
                "failed_at": _utc_now(),
                "error": str(error),
            }
        )
        _write_workflow(path, document)
        _discard_working_workflow(working_path)
        _ACTIVE_RUNS.pop(_active_key(path), None)
        return _read_workflow(path)[1]


def manage_filter_presets_payload(payload: dict[str, Any]) -> dict[str, Any]:
    directory = _workflow_directory(payload.get("data_root"))
    action = str(payload.get("action") or "").strip()
    with _WORKFLOWS_LOCK:
        if action == "list":
            workflows = _read_workflows(
                directory,
                validate_parent_state=True,
                load_results=False,
            )
        elif action == "inspect":
            workflows = _read_workflows(
                directory,
                require_workflow_format=True,
                validate_parent_state=True,
            )
        else:
            workflows = _read_workflows(directory, load_results=False)

        if action == "list":
            pass
        elif action == "inspect":
            pass
        elif action == "save":
            workflow = _normalize_condition_input(payload.get("preset"))
            path = _workflow_path(
                payload.get("data_root"), workflow["mode"], workflow.get("parent_mode")
            )
            if workflow.get("parent_mode") is not None:
                fingerprint = _completed_parent_fingerprint(
                    payload.get("data_root"), workflow["parent_mode"]
                )
                workflow["parent_result_fingerprint"] = fingerprint
            if _active_key(path) in _ACTIVE_RUNS:
                raise ValueError(f"Filter workflow is running: {workflow['name']}")
            preserve_existing = False
            if path.is_file():
                _existing_document, existing = _read_workflow(
                    path,
                    load_results=False,
                )
                preserve_existing = (
                    existing["mode"] == workflow["mode"]
                    and existing["condition_blocks"] == workflow["condition_blocks"]
                    and existing.get("parent_mode") == workflow.get("parent_mode")
                    and existing.get("parent_result_fingerprint")
                    == workflow.get("parent_result_fingerprint")
                )
            if not preserve_existing:
                _write_workflow(path, _new_workflow_document(workflow))
            workflows = [item for item in workflows if item["id"] != workflow["id"]]
            workflows.append(_read_workflow(path, load_results=False)[1])
        elif action == "delete":
            mode = validate_workspace_mode(payload.get("mode"))
            parent_mode = payload.get("parent_mode")
            workflow_path = _workflow_path(payload.get("data_root"), mode, parent_mode)
            if not workflow_path.is_file():
                raise ValueError(f"Filter workflow not found: {mode}")
            if _active_key(workflow_path) in _ACTIVE_RUNS:
                raise ValueError(f"Filter workflow is running: {mode}")
            if parent_mode is None or not str(parent_mode).strip():
                child_paths = sorted(
                    workflow_path.parent.glob("subfilters/*/filter.json")
                )
                if child_paths:
                    raise ValueError(
                        "Cannot delete a parent filter workflow while derived filters "
                        f"exist: {mode}"
                    )
            document = _read_json_object(workflow_path)
            workflow_path.unlink()
            for field in ("result_file", "pending_file"):
                file_name = str(document.get(field) or "").strip()
                if file_name:
                    _workflow_sidecar_path(workflow_path, file_name).unlink(
                        missing_ok=True
                    )
            deleted_id = (
                f"{validate_workspace_mode(parent_mode)}/{mode}"
                if parent_mode is not None and str(parent_mode).strip()
                else mode
            )
            workflows = [item for item in workflows if item["id"] != deleted_id]
        else:
            raise ValueError(
                "filter workflow action must be one of: list, inspect, save, delete"
            )

    return {
        "format": FILTER_WORKFLOW_DIRECTORY_FORMAT,
        "path": str(directory),
        "presets": sorted(workflows, key=lambda item: item["id"]),
    }


def migrate_filter_workflow_storage(data_root: object) -> dict[str, Any]:
    directory = _workflow_directory(data_root)
    if not directory.exists():
        return {"path": str(directory), "migrated": [], "unchanged": []}
    migrated: list[str] = []
    unchanged: list[str] = []
    paths = sorted(
        [
            *directory.glob("*/filter.json"),
            *directory.glob("*/subfilters/*/filter.json"),
        ]
    )
    with _WORKFLOWS_LOCK:
        for path in paths:
            raw = _read_json_object(path)
            if raw.get("format") != FILTER_WORKFLOW_FORMAT:
                continue
            storage_is_current = (
                "result" not in raw
                and "pending" not in raw
                and raw.get("result_file") in (None, "filtered.json")
                and raw.get("pending_file") in (None, "filter.pending.json")
                and not (
                    raw.get("result_file") is None
                    and path.with_name("filtered.json").is_file()
                )
            )
            if storage_is_current:
                _read_workflow(path)
                unchanged.append(str(path))
                continue
            document, _workflow = _read_workflow(path, document=raw)
            _write_workflow(path, document)
            _read_workflow(path)
            migrated.append(str(path))
    return {
        "path": str(directory),
        "migrated": migrated,
        "unchanged": unchanged,
    }
