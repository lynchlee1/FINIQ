"""Canonical filesystem layout for the seven disclosure workflow stages."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from finiq.config import PROJECT_ROOT, build_disclosure_workspace_path_settings

WORKSPACE_FORMAT = "finiq_disclosure_workspace_v1"
WORKSPACE_MANIFEST_FILENAME = "disclosure-workspace.json"
_MODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True, slots=True)
class DisclosureWorkspace:
    root: Path
    list: Path
    table: Path
    filtered: Path
    external: Path
    internal: Path
    sections: Path
    converted: Path

    def external_mode(self, mode: str) -> Path:
        return self.external / validate_workspace_mode(mode)

    def converted_mode(self, mode: str) -> Path:
        return self.converted / validate_workspace_mode(mode)

    def paths_payload(self, modes: list[str] | None = None) -> dict[str, Any]:
        normalized_modes = sorted({validate_workspace_mode(mode) for mode in modes or []})
        return {
            "root": str(self.root),
            "list": str(self.list),
            "table": str(self.table),
            "filter": str(self.filtered),
            "external_root": str(self.external),
            "external": {
                mode: str(self.external_mode(mode)) for mode in normalized_modes
            },
            "internal": str(self.internal),
            "sections": str(self.sections),
            "converted_root": str(self.converted),
            "converted": {
                mode: str(self.converted_mode(mode)) for mode in normalized_modes
            },
        }


def validate_workspace_mode(mode: object) -> str:
    normalized = str(mode or "").strip()
    if not normalized or _MODE_RE.fullmatch(normalized) is None:
        raise ValueError(
            "mode must start with an alphanumeric character and contain only letters, numbers, '.', '_' or '-'"
        )
    return normalized


def _validate_workspace_root(root: Path) -> None:
    risky_roots = {
        Path(root.anchor).resolve(),
        Path.home().resolve(),
        PROJECT_ROOT.resolve(),
    }
    if root in risky_roots:
        raise ValueError(f"Refusing to use high-risk data_root: {root}")
    if root.exists() and not root.is_dir():
        raise ValueError(f"data_root is not a directory: {root}")


def resolve_disclosure_workspace(
    data_root: str | Path, *, create: bool = False
) -> DisclosureWorkspace:
    raw = str(data_root or "").strip()
    if not raw:
        raise ValueError("data_root is required")
    root = Path(raw).expanduser().resolve()
    _validate_workspace_root(root)
    workspace = DisclosureWorkspace(
        root=root,
        list=root / "01-list",
        table=root / "02-table",
        filtered=root / "03-filter",
        external=root / "04-external-html-download",
        internal=root / "05-internal-html-download",
        sections=root / "06-sections",
        converted=root / "07-converted",
    )
    if create:
        for directory in (
            workspace.list,
            workspace.table,
            workspace.filtered,
            workspace.external,
            workspace.internal,
            workspace.sections,
            workspace.converted,
        ):
            directory.mkdir(parents=True, exist_ok=True)
    return workspace


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.part-{uuid.uuid4().hex}")
    try:
        with temporary_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        temporary_path.unlink(missing_ok=True)


def _existing_workspace_modes(manifest_path: Path, *, root: Path) -> list[str]:
    if not manifest_path.exists():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Existing path is not a FINIQ disclosure workspace: {manifest_path}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("format") != WORKSPACE_FORMAT:
        raise ValueError(
            f"Existing path is not a FINIQ disclosure workspace: {manifest_path}"
        )
    manifest_root = Path(str(payload.get("data_root") or "")).expanduser().resolve()
    if manifest_root != root:
        raise ValueError(
            f"Disclosure workspace manifest belongs to another data_root: {manifest_root}"
        )
    modes = payload.get("modes")
    if not isinstance(modes, list):
        raise ValueError(f"Disclosure workspace manifest has invalid modes: {manifest_path}")
    return [validate_workspace_mode(mode) for mode in modes]


def prepare_disclosure_workspace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    modes_value = payload.get("modes") or []
    if not isinstance(modes_value, list):
        raise ValueError("modes must be a list")
    requested_modes = {validate_workspace_mode(mode) for mode in modes_value}
    workspace = resolve_disclosure_workspace(payload.get("data_root") or "")
    manifest_path = workspace.root / WORKSPACE_MANIFEST_FILENAME
    modes = sorted(
        requested_modes
        | set(_existing_workspace_modes(manifest_path, root=workspace.root))
    )
    workspace = resolve_disclosure_workspace(workspace.root, create=True)
    for mode in modes:
        workspace.external_mode(mode).mkdir(parents=True, exist_ok=True)
        workspace.converted_mode(mode).mkdir(parents=True, exist_ok=True)

    manifest = {
        "format": WORKSPACE_FORMAT,
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_root": str(workspace.root),
        "modes": modes,
        "paths": workspace.paths_payload(modes),
    }
    atomic_write_json(manifest_path, manifest)
    return {**manifest, "manifest_path": str(manifest_path)}


def disclosure_workspace_settings(
    data_root: str | Path, *, mode: object
) -> dict[str, str]:
    workspace = resolve_disclosure_workspace(data_root)
    normalized_mode = validate_workspace_mode(mode)
    return build_disclosure_workspace_path_settings(
        workspace.root, mode=normalized_mode
    )


def _set_default(payload: dict[str, Any], key: str, value: object) -> None:
    if not str(payload.get(key) or "").strip():
        payload[key] = value


def apply_workspace_defaults(kind: str, body: dict[str, Any]) -> dict[str, Any]:
    """Fill missing stage paths from ``data_root`` without blocking overrides."""
    payload = dict(body)
    data_root = str(payload.get("data_root") or "").strip()
    if not data_root:
        return payload
    workspace = resolve_disclosure_workspace(data_root, create=True)
    normalized_kind = str(kind or "").strip()

    if normalized_kind == "kind_download":
        # The download detail page accepts the workspace root. Raw KIND files
        # always live in the first canonical stage below that root.
        if payload.get("separate_output_directory"):
            _set_default(payload, "output_directory", str(workspace.list))
        else:
            payload["output_directory"] = str(workspace.list)
    elif normalized_kind == "table_build":
        _set_default(payload, "root_directory", str(workspace.list))
        _set_default(payload, "output_path", str(workspace.table))
    elif normalized_kind == "filter":
        payload["mode"] = validate_workspace_mode(payload.get("mode"))
        _set_default(payload, "external_html_transfer_path", str(workspace.filtered))
    elif normalized_kind == "external_html_download":
        mode = validate_workspace_mode(payload.get("mode"))
        payload.pop("json", None)
        payload.pop("payload", None)
        payload.pop("source_json_path", None)
        _set_default(payload, "output_directory", str(workspace.external_mode(mode)))
    elif normalized_kind == "external_html_compress":
        mode = validate_workspace_mode(payload.get("mode"))
        _set_default(payload, "input_directory", str(workspace.external_mode(mode)))
        _set_default(payload, "output_directory", str(workspace.external_mode(mode)))
    elif normalized_kind == "internal_html_download":
        mode = validate_workspace_mode(payload.get("mode"))
        if not str(payload.get("source_compressed_json_path") or "").strip():
            _set_default(
                payload,
                "source_compressed_json_path",
                str(workspace.external_mode(mode) / "compressed-external-html.json"),
            )
        _set_default(payload, "output_directory", str(workspace.internal))
    elif normalized_kind == "internal_html_merge":
        _set_default(payload, "input_directory", str(workspace.internal))
        _set_default(payload, "output_directory", str(workspace.internal / "merged"))
    elif normalized_kind in {"section_inspect", "section_kinds", "section_list"}:
        _set_default(payload, "input_directory", str(workspace.internal))
    elif normalized_kind == "section_save":
        _set_default(payload, "input_directory", str(workspace.internal))
        _set_default(payload, "output_directory", str(workspace.sections))
    elif normalized_kind == "parse":
        mode = validate_workspace_mode(payload.get("mode"))
        _set_default(payload, "input_directory", str(workspace.sections))
        _set_default(payload, "output_directory", str(workspace.converted_mode(mode)))
        _set_default(
            payload,
            "filtered_metadata_path",
            str(workspace.filtered / mode / "filtered.json"),
        )
        _set_default(
            payload,
            "compressed_metadata_path",
            str(workspace.external_mode(mode) / "compressed-external-html.json"),
        )
    return payload


__all__ = [
    "DisclosureWorkspace",
    "apply_workspace_defaults",
    "atomic_write_json",
    "disclosure_workspace_settings",
    "prepare_disclosure_workspace_payload",
    "resolve_disclosure_workspace",
    "validate_workspace_mode",
]
