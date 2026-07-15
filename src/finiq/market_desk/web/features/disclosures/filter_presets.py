"""Workspace-owned disclosure condition preset storage."""

from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Any

from finiq.market_desk.web.features.disclosure_workflow.layout import (
    atomic_write_json,
    resolve_disclosure_workspace,
    validate_workspace_mode,
)

FILTER_PRESETS_FORMAT = "finiq_disclosure_filter_presets_v1"
FILTER_PRESETS_FILENAME = "presets.json"
_PRESETS_LOCK = threading.RLock()


def _preset_path(data_root: object) -> Path:
    return resolve_disclosure_workspace(str(data_root or "")).filtered / FILTER_PRESETS_FILENAME


def _normalize_name(value: object, *, field: str = "name") -> str:
    name = str(value or "").strip()
    if not name:
        raise ValueError(f"preset {field} is required")
    return name


def _normalize_preset(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("preset must be an object")
    condition_blocks = value.get("condition_blocks")
    if not isinstance(condition_blocks, list) or not all(
        isinstance(block, dict) for block in condition_blocks
    ):
        raise ValueError("preset condition_blocks must be a list of objects")
    return {
        "name": _normalize_name(value.get("name")),
        "mode": validate_workspace_mode(value.get("mode")),
        "condition_blocks": condition_blocks,
    }


def _read_presets(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid disclosure filter presets.json: {path}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("format") != FILTER_PRESETS_FORMAT
        or not isinstance(payload.get("presets"), list)
    ):
        raise ValueError(f"Invalid disclosure filter presets.json: {path}")
    presets = [_normalize_preset(item) for item in payload["presets"]]
    names = [item["name"] for item in presets]
    if len(names) != len(set(names)):
        raise ValueError(f"Duplicate preset names in presets.json: {path}")
    return sorted(presets, key=lambda item: item["name"])


def _write_presets(path: Path, presets: list[dict[str, Any]]) -> None:
    atomic_write_json(
        path,
        {
            "format": FILTER_PRESETS_FORMAT,
            "presets": sorted(presets, key=lambda item: item["name"]),
        },
    )


def manage_filter_presets_payload(payload: dict[str, Any]) -> dict[str, Any]:
    path = _preset_path(payload.get("data_root"))
    action = str(payload.get("action") or "").strip()
    with _PRESETS_LOCK:
        presets = _read_presets(path)

        if action == "list":
            pass
        elif action == "save":
            preset = _normalize_preset(payload.get("preset"))
            presets = [item for item in presets if item["name"] != preset["name"]]
            presets.append(preset)
            _write_presets(path, presets)
        elif action == "rename":
            name = _normalize_name(payload.get("name"))
            new_name = _normalize_name(payload.get("new_name"), field="new_name")
            if not any(item["name"] == name for item in presets):
                raise ValueError(f"Preset not found: {name}")
            if name != new_name and any(item["name"] == new_name for item in presets):
                raise ValueError(f"Preset already exists: {new_name}")
            presets = [
                {**item, "name": new_name} if item["name"] == name else item
                for item in presets
            ]
            _write_presets(path, presets)
        elif action == "delete":
            name = _normalize_name(payload.get("name"))
            if not any(item["name"] == name for item in presets):
                raise ValueError(f"Preset not found: {name}")
            presets = [item for item in presets if item["name"] != name]
            _write_presets(path, presets)
        else:
            raise ValueError("preset action must be one of: list, save, rename, delete")

    return {
        "format": FILTER_PRESETS_FORMAT,
        "path": str(path),
        "presets": sorted(presets, key=lambda item: item["name"]),
    }
