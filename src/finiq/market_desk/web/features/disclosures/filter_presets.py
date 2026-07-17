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

FILTER_PRESET_FORMAT = "finiq_disclosure_filter_preset_v1"
FILTER_PRESET_DIRECTORY_FORMAT = "finiq_disclosure_filter_preset_directory_v1"
FILTER_RESULT_FORMATS = {
    "kind_disclosure_filter_v1",
    "kind_disclosure_filter_transfer_v1",
}
FILTER_PRESET_MODES = (
    "bond_issuance",
    "rights_issuance",
    "shareholder_meeting",
    "asset_transaction",
    "security_transaction",
)
_FILTER_HEADER_LIMIT = 1024 * 1024
_FILTER_HEADER_CHUNK_SIZE = 64 * 1024
_PRESETS_LOCK = threading.RLock()


def _preset_directory(data_root: object) -> Path:
    return resolve_disclosure_workspace(str(data_root or "")).filtered


def _normalize_name(value: object, *, field: str = "name") -> str:
    name = str(value or "").strip()
    if name.lower().endswith(".json"):
        name = name[:-5].strip()
    if not name:
        raise ValueError(f"preset {field} is required")
    if name in {".", ".."} or "/" in name or "\\" in name or "\0" in name:
        raise ValueError(f"preset {field} must be a JSON file name")
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


def _decode_filter_header(path: Path) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    buffer = ""
    position = 0
    values: dict[str, Any] = {}

    try:
        with path.open("r", encoding="utf-8") as source:
            def decode_value() -> tuple[Any, int]:
                nonlocal buffer
                while True:
                    try:
                        return decoder.raw_decode(buffer, position)
                    except json.JSONDecodeError as exc:
                        chunk = source.read(_FILTER_HEADER_CHUNK_SIZE)
                        if not chunk or len(buffer) + len(chunk) > _FILTER_HEADER_LIMIT:
                            raise ValueError(f"Invalid disclosure filter preset JSON: {path}") from exc
                        buffer += chunk

            buffer = source.read(_FILTER_HEADER_CHUNK_SIZE)
            if not buffer:
                raise ValueError(f"Invalid disclosure filter preset JSON: {path}")
            while position < len(buffer) and buffer[position].isspace():
                position += 1
            if position >= len(buffer) or buffer[position] != "{":
                raise ValueError(f"Invalid disclosure filter preset JSON: {path}")
            position += 1

            while "format" not in values or "filters" not in values:
                while position < len(buffer) and buffer[position].isspace():
                    position += 1
                key, position = decode_value()
                if not isinstance(key, str):
                    raise ValueError(f"Invalid disclosure filter preset JSON: {path}")
                while position < len(buffer) and buffer[position].isspace():
                    position += 1
                if position >= len(buffer) or buffer[position] != ":":
                    raise ValueError(f"Invalid disclosure filter preset JSON: {path}")
                position += 1
                while position < len(buffer) and buffer[position].isspace():
                    position += 1
                value, position = decode_value()
                if key in {"format", "mode", "filters"}:
                    values[key] = value
                while position < len(buffer) and buffer[position].isspace():
                    position += 1
                if position >= len(buffer):
                    chunk = source.read(_FILTER_HEADER_CHUNK_SIZE)
                    if not chunk or len(buffer) + len(chunk) > _FILTER_HEADER_LIMIT:
                        raise ValueError(f"Invalid disclosure filter preset JSON: {path}")
                    buffer += chunk
                if buffer[position] == ",":
                    position += 1
                elif buffer[position] != "}":
                    raise ValueError(f"Invalid disclosure filter preset JSON: {path}")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid disclosure filter preset JSON: {path}") from exc

    return values


def _mode_from_document(path: Path, payload: dict[str, Any]) -> str:
    if payload.get("mode"):
        return validate_workspace_mode(payload["mode"])
    for mode in FILTER_PRESET_MODES:
        if path.stem == mode or path.stem.startswith(f"{mode}_"):
            return mode
    raise ValueError(f"Disclosure filter preset mode is required: {path}")


def _read_preset(path: Path) -> dict[str, Any]:
    payload = _decode_filter_header(path)
    if payload.get("format") not in FILTER_RESULT_FORMATS | {FILTER_PRESET_FORMAT}:
        raise ValueError(f"Invalid disclosure filter preset JSON: {path}")
    filters = payload.get("filters")
    filter_blocks = filters.get("filter_blocks") if isinstance(filters, dict) else None
    return _normalize_preset({
        "name": path.stem,
        "mode": _mode_from_document(path, payload),
        "condition_blocks": filter_blocks,
    })


def _read_presets(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ValueError(f"Invalid disclosure filter preset directory: {directory}")
    return sorted(
        (_read_preset(path) for path in directory.glob("*.json")),
        key=lambda item: item["name"],
    )


def _write_preset(path: Path, preset: dict[str, Any]) -> None:
    atomic_write_json(
        path,
        {
            "format": FILTER_PRESET_FORMAT,
            "mode": preset["mode"],
            "filters": {"filter_blocks": preset["condition_blocks"]},
        },
    )


def manage_filter_presets_payload(payload: dict[str, Any]) -> dict[str, Any]:
    directory = _preset_directory(payload.get("data_root"))
    action = str(payload.get("action") or "").strip()
    with _PRESETS_LOCK:
        presets = _read_presets(directory)

        if action == "list":
            pass
        elif action == "save":
            preset = _normalize_preset(payload.get("preset"))
            _write_preset(directory / f"{preset['name']}.json", preset)
            presets = [item for item in presets if item["name"] != preset["name"]]
            presets.append(preset)
        elif action == "rename":
            name = _normalize_name(payload.get("name"))
            new_name = _normalize_name(payload.get("new_name"), field="new_name")
            source_path = directory / f"{name}.json"
            target_path = directory / f"{new_name}.json"
            if not source_path.is_file():
                raise ValueError(f"Preset not found: {name}")
            if source_path != target_path and target_path.exists():
                raise ValueError(f"Preset already exists: {new_name}")
            source_path.rename(target_path)
            presets = [
                {**item, "name": new_name} if item["name"] == name else item
                for item in presets
            ]
        elif action == "delete":
            name = _normalize_name(payload.get("name"))
            preset_path = directory / f"{name}.json"
            if not preset_path.is_file():
                raise ValueError(f"Preset not found: {name}")
            preset_path.unlink()
            presets = [item for item in presets if item["name"] != name]
        else:
            raise ValueError("preset action must be one of: list, save, rename, delete")

    return {
        "format": FILTER_PRESET_DIRECTORY_FORMAT,
        "path": str(directory),
        "presets": sorted(presets, key=lambda item: item["name"]),
    }
