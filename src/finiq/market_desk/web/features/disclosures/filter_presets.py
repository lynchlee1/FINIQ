"""Workspace-owned disclosure filter workflow storage."""

from __future__ import annotations

from datetime import datetime, timezone
import json
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
FILTER_WORKFLOW_STATUSES = {"ready", "running", "completed", "failed"}
FILTER_STEP_STATUSES = {"pending", "running", "completed", "failed"}
_WORKFLOWS_LOCK = threading.RLock()


def _workflow_directory(data_root: object) -> Path:
    return resolve_disclosure_workspace(str(data_root or "")).filtered


def _normalize_name(value: object, *, field: str = "name") -> str:
    name = str(value or "").strip()
    if name.lower().endswith(".json"):
        name = name[:-5].strip()
    if not name:
        raise ValueError(f"filter workflow {field} is required")
    if name in {".", ".."} or "/" in name or "\\" in name or "\0" in name:
        raise ValueError(f"filter workflow {field} must be a JSON file name")
    return name


def _normalize_condition_input(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("filter workflow must be an object")
    condition_blocks = value.get("condition_blocks")
    if not isinstance(condition_blocks, list) or not all(
        isinstance(block, dict) for block in condition_blocks
    ):
        raise ValueError("filter workflow condition_blocks must be a list of objects")
    return {
        "name": _normalize_name(value.get("name")),
        "mode": validate_workspace_mode(value.get("mode")),
        "condition_blocks": condition_blocks,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_format_header(path: Path) -> object:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid disclosure filter workflow JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid disclosure filter workflow JSON: {path}")
    return payload.get("format")


def _required_step(steps: object, name: str) -> dict[str, Any]:
    if not isinstance(steps, dict) or not isinstance(steps.get(name), dict):
        raise ValueError(f"filter workflow steps.{name} must be an object")
    step = dict(steps[name])
    if step.get("status") not in FILTER_STEP_STATUSES:
        raise ValueError(f"filter workflow steps.{name}.status is invalid")
    return step


def _read_workflow(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid disclosure filter workflow JSON: {path}") from exc
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
        ("completed", "completed", "completed"),
        ("failed", "failed", "pending"),
        ("failed", "completed", "failed"),
    }:
        raise ValueError(f"filter workflow step statuses are inconsistent: {path}")
    condition_blocks = condition_step.get("filter_blocks")
    normalized = _normalize_condition_input(
        {
            "name": path.stem,
            "mode": payload.get("mode"),
            "condition_blocks": condition_blocks,
        }
    )
    return payload, {
        **normalized,
        "status": status,
        "steps": {
            "condition_input": condition_step,
            "database_query": query_step,
            "record": record_step,
        },
    }


def _read_workflows(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ValueError(f"Invalid disclosure filter workflow directory: {directory}")
    workflows: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        if _read_format_header(path) != FILTER_WORKFLOW_FORMAT:
            continue
        _payload, workflow = _read_workflow(path)
        workflows.append(workflow)
    return sorted(workflows, key=lambda item: item["name"])


def _new_workflow_document(workflow: dict[str, Any]) -> dict[str, Any]:
    now = _utc_now()
    return {
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
    }


def _write_workflow(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(path, payload)


def _workflow_path(data_root: object, name: object) -> Path:
    return _workflow_directory(data_root) / f"{_normalize_name(name)}.json"


def begin_filter_workflow_payload(payload: dict[str, Any]) -> dict[str, Any]:
    workspace = resolve_disclosure_workspace(str(payload.get("data_root") or ""))
    path = workspace.filtered / f"{_normalize_name(payload.get('workflow_name'))}.json"
    requested = _normalize_condition_input(
        {
            "name": path.stem,
            "mode": payload.get("mode"),
            "condition_blocks": payload.get("filter_blocks"),
        }
    )
    with _WORKFLOWS_LOCK:
        if not path.is_file():
            raise ValueError(f"Filter workflow not found: {path.stem}")
        document, workflow = _read_workflow(path)
        if workflow["status"] == "running":
            raise ValueError(f"Filter workflow is already running: {path.stem}")
        if (
            workflow["mode"] != requested["mode"]
            or workflow["condition_blocks"] != requested["condition_blocks"]
        ):
            raise ValueError("Save the filter conditions before running the workflow")
        run_id = uuid.uuid4().hex
        document["status"] = "running"
        document["steps"]["database_query"] = {
            "status": "running",
            "run_id": run_id,
            "started_at": _utc_now(),
            "source_path": str(workspace.table / "sqlite_manifest.json"),
        }
        document["steps"]["record"] = {"status": "pending"}
        _write_workflow(path, document)
    return {**workflow, "path": str(path), "run_id": run_id}


def mark_filter_workflow_query_completed(
    *, data_root: object, name: object, run_id: str, summary: object
) -> dict[str, Any]:
    path = _workflow_path(data_root, name)
    with _WORKFLOWS_LOCK:
        document, _workflow = _read_workflow(path)
        query_step = document["steps"]["database_query"]
        if document.get("status") != "running" or query_step.get("run_id") != run_id:
            raise ValueError(f"Filter workflow run is not active: {path.stem}")
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
        _write_workflow(path, document)
        return _read_workflow(path)[1]


def complete_filter_workflow_payload(
    *, data_root: object, name: object, run_id: str, result_path: object, summary: object
) -> dict[str, Any]:
    path = _workflow_path(data_root, name)
    normalized_result_path = str(result_path or "").strip()
    if not normalized_result_path:
        raise ValueError("filter workflow result path is required")
    with _WORKFLOWS_LOCK:
        document, _workflow = _read_workflow(path)
        record_step = document["steps"]["record"]
        if document.get("status") != "running" or record_step.get("run_id") != run_id:
            raise ValueError(f"Filter workflow run is not active: {path.stem}")
        document["status"] = "completed"
        record_step.update(
            {
                "status": "completed",
                "completed_at": _utc_now(),
                "path": normalized_result_path,
                "summary": summary if isinstance(summary, dict) else {},
            }
        )
        _write_workflow(path, document)
        return _read_workflow(path)[1]


def fail_filter_workflow_payload(
    *, data_root: object, name: object, run_id: str, error: object
) -> dict[str, Any] | None:
    path = _workflow_path(data_root, name)
    with _WORKFLOWS_LOCK:
        try:
            document, _workflow = _read_workflow(path)
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
        if (
            document.get("status") != "running"
            or active_step is None
            or active_step.get("run_id") != run_id
        ):
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
        return _read_workflow(path)[1]


def manage_filter_presets_payload(payload: dict[str, Any]) -> dict[str, Any]:
    directory = _workflow_directory(payload.get("data_root"))
    action = str(payload.get("action") or "").strip()
    with _WORKFLOWS_LOCK:
        workflows = _read_workflows(directory)

        if action == "list":
            pass
        elif action == "save":
            workflow = _normalize_condition_input(payload.get("preset"))
            path = directory / f"{workflow['name']}.json"
            if path.is_file():
                _existing_document, existing = _read_workflow(path)
                if existing["status"] == "running":
                    raise ValueError(f"Filter workflow is running: {workflow['name']}")
            _write_workflow(path, _new_workflow_document(workflow))
            workflows = [item for item in workflows if item["name"] != workflow["name"]]
            workflows.append(_read_workflow(path)[1])
        elif action == "rename":
            name = _normalize_name(payload.get("name"))
            new_name = _normalize_name(payload.get("new_name"), field="new_name")
            source_path = directory / f"{name}.json"
            target_path = directory / f"{new_name}.json"
            if not source_path.is_file():
                raise ValueError(f"Filter workflow not found: {name}")
            _document, existing = _read_workflow(source_path)
            if existing["status"] == "running":
                raise ValueError(f"Filter workflow is running: {name}")
            if source_path != target_path and target_path.exists():
                raise ValueError(f"Filter workflow already exists: {new_name}")
            source_path.rename(target_path)
            workflows = [
                {**item, "name": new_name} if item["name"] == name else item
                for item in workflows
            ]
        elif action == "delete":
            name = _normalize_name(payload.get("name"))
            workflow_path = directory / f"{name}.json"
            if not workflow_path.is_file():
                raise ValueError(f"Filter workflow not found: {name}")
            _document, existing = _read_workflow(workflow_path)
            if existing["status"] == "running":
                raise ValueError(f"Filter workflow is running: {name}")
            workflow_path.unlink()
            workflows = [item for item in workflows if item["name"] != name]
        else:
            raise ValueError("filter workflow action must be one of: list, save, rename, delete")

    return {
        "format": FILTER_WORKFLOW_DIRECTORY_FORMAT,
        "path": str(directory),
        "presets": sorted(workflows, key=lambda item: item["name"]),
    }
