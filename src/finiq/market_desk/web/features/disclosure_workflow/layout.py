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

from finiq.config import PROJECT_ROOT

WORKSPACE_FORMAT = "finiq_disclosure_workspace_v1"
WORKSPACE_MANIFEST_FILENAME = "disclosure-workspace.json"
STAGE_LINK_FORMAT = "finiq_stage_link_v1"
STAGE_LINK_FILENAME = "finiq-stage-link.json"
DISCLOSURE_STAGE_NAMES = (
    "01-list",
    "02-table",
    "03-filter",
    "04-external-html-download",
    "04-external-html-compress",
    "05-internal-html-download",
    "06-sections",
    "07-converted",
)
_MODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True, slots=True)
class DisclosureWorkspace:
    root: Path
    create_on_access: bool = False

    def stage_directory(self, stage_name: str) -> Path:
        directory = _resolve_stage_directory(
            self.root, _validate_stage_name(stage_name)
        )
        if self.create_on_access:
            directory.mkdir(parents=True, exist_ok=True)
        return directory

    @property
    def list(self) -> Path:
        return self.stage_directory("01-list")

    @property
    def table(self) -> Path:
        return self.stage_directory("02-table")

    @property
    def filtered(self) -> Path:
        return self.stage_directory("03-filter")

    @property
    def external(self) -> Path:
        return self.stage_directory("04-external-html-download")

    @property
    def external_compress(self) -> Path:
        return self.stage_directory("04-external-html-compress")

    @property
    def internal(self) -> Path:
        return self.stage_directory("05-internal-html-download")

    @property
    def sections(self) -> Path:
        return self.stage_directory("06-sections")

    @property
    def converted(self) -> Path:
        return self.stage_directory("07-converted")

    def external_mode(self, mode: str) -> Path:
        return self.external / validate_workspace_mode(mode)

    def external_compress_mode(self, mode: str) -> Path:
        return self.external_compress / validate_workspace_mode(mode)

    def internal_mode(self, mode: str) -> Path:
        return self.internal / validate_workspace_mode(mode)

    def sections_mode(self, mode: str) -> Path:
        return self.sections / validate_workspace_mode(mode)

    def converted_mode(self, mode: str) -> Path:
        return self.converted / validate_workspace_mode(mode)

    def converted_filter_mode(self, mode: str, *, parent_mode: object = None) -> Path:
        normalized_mode = validate_workspace_mode(mode)
        if parent_mode in (None, ""):
            return self.converted / normalized_mode
        normalized_parent_mode = validate_workspace_mode(parent_mode)
        if normalized_parent_mode == normalized_mode:
            raise ValueError("parent_mode must differ from mode")
        return self.converted / normalized_parent_mode / "subfilters" / normalized_mode

    def filter_mode(self, mode: str, *, parent_mode: object = None) -> Path:
        normalized_mode = validate_workspace_mode(mode)
        if parent_mode in (None, ""):
            return self.filtered / normalized_mode
        normalized_parent_mode = validate_workspace_mode(parent_mode)
        if normalized_parent_mode == normalized_mode:
            raise ValueError("parent_mode must differ from mode")
        return self.filtered / normalized_parent_mode / "subfilters" / normalized_mode

    def external_owner_mode(self, mode: str, *, parent_mode: object = None) -> Path:
        owner_mode = mode if parent_mode in (None, "") else parent_mode
        return self.external_mode(validate_workspace_mode(owner_mode))

    def external_compress_owner_mode(
        self, mode: str, *, parent_mode: object = None
    ) -> Path:
        owner_mode = mode if parent_mode in (None, "") else parent_mode
        return self.external_compress_mode(validate_workspace_mode(owner_mode))

    def internal_owner_mode(self, mode: str, *, parent_mode: object = None) -> Path:
        owner_mode = mode if parent_mode in (None, "") else parent_mode
        return self.internal_mode(validate_workspace_mode(owner_mode))

    def sections_owner_mode(self, mode: str, *, parent_mode: object = None) -> Path:
        owner_mode = mode if parent_mode in (None, "") else parent_mode
        return self.sections_mode(validate_workspace_mode(owner_mode))

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
            "external_compress_root": str(self.external_compress),
            "external_compress": {
                mode: str(self.external_compress_mode(mode))
                for mode in normalized_modes
            },
            "internal_root": str(self.internal),
            "internal": {
                mode: str(self.internal_mode(mode)) for mode in normalized_modes
            },
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


def _resolve_stage_directory(root: Path, stage_name: str) -> Path:
    local_directory = root / stage_name
    link_path = local_directory / STAGE_LINK_FILENAME
    if not link_path.exists():
        return local_directory
    if not link_path.is_file():
        raise ValueError(f"Stage link is not a file: {link_path}")
    try:
        payload = json.loads(link_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Stage link is not valid JSON: {link_path}") from exc
    if not isinstance(payload, dict) or payload.get("format") != STAGE_LINK_FORMAT:
        raise ValueError(f"Stage link has an invalid format: {link_path}")
    if payload.get("schema_version") != 1:
        raise ValueError(f"Stage link has an unsupported schema version: {link_path}")
    target_text = str(payload.get("target_workspace") or "").strip()
    if not target_text:
        raise ValueError(f"Stage link target_workspace is required: {link_path}")
    target_root = Path(target_text).expanduser()
    if not target_root.is_absolute():
        target_root = root / target_root
    target_root = target_root.resolve()
    _validate_workspace_root(target_root)
    if not target_root.is_dir():
        raise ValueError(f"Stage link target workspace does not exist: {target_root}")
    target_directory = target_root / stage_name
    if not target_directory.is_dir():
        raise ValueError(f"Stage link target directory does not exist: {target_directory}")
    if (target_directory / STAGE_LINK_FILENAME).exists():
        raise ValueError(f"Chained stage links are not supported: {target_directory}")
    return target_directory.resolve()


def _validate_stage_name(stage_name: object) -> str:
    normalized = str(stage_name or "").strip()
    if normalized not in DISCLOSURE_STAGE_NAMES:
        raise ValueError(f"Unsupported disclosure stage: {normalized}")
    return normalized


def _stage_link_status(root: Path, stage_name: str) -> dict[str, Any]:
    local_directory = root / stage_name
    link_path = local_directory / STAGE_LINK_FILENAME
    if not link_path.exists():
        return {
            "stage": stage_name,
            "linked": False,
            "valid": True,
            "local_directory": str(local_directory),
            "target_workspace": None,
            "resolved_directory": str(local_directory),
            "error": None,
        }
    target_workspace: str | None = None
    try:
        payload = json.loads(link_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            target_text = str(payload.get("target_workspace") or "").strip()
            if target_text:
                target_root = Path(target_text).expanduser()
                if not target_root.is_absolute():
                    target_root = root / target_root
                target_workspace = str(target_root.resolve())
        resolved_directory = _resolve_stage_directory(root, stage_name)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return {
            "stage": stage_name,
            "linked": True,
            "valid": False,
            "local_directory": str(local_directory),
            "target_workspace": target_workspace,
            "resolved_directory": "",
            "error": str(exc),
        }
    return {
        "stage": stage_name,
        "linked": True,
        "valid": True,
        "local_directory": str(local_directory),
        "target_workspace": target_workspace,
        "resolved_directory": str(resolved_directory),
        "error": None,
    }


def manage_disclosure_stage_links_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_root = str(payload.get("data_root") or "").strip()
    if not raw_root:
        raise ValueError("data_root is required")
    root = Path(raw_root).expanduser().resolve()
    _validate_workspace_root(root)
    action = str(payload.get("action") or "list").strip()

    if action == "set":
        stage_name = _validate_stage_name(payload.get("stage"))
        target_text = str(payload.get("target_workspace") or "").strip()
        if not target_text:
            raise ValueError("target_workspace is required")
        target_root = Path(target_text).expanduser()
        if not target_root.is_absolute():
            target_root = root / target_root
        target_root = target_root.resolve()
        _validate_workspace_root(target_root)
        if target_root == root:
            raise ValueError("target_workspace must differ from data_root")
        if not target_root.is_dir():
            raise ValueError(f"Stage link target workspace does not exist: {target_root}")
        target_directory = target_root / stage_name
        target_directory.mkdir(parents=True, exist_ok=True)
        if (target_directory / STAGE_LINK_FILENAME).exists():
            raise ValueError(f"Chained stage links are not supported: {target_directory}")
        local_directory = root / stage_name
        if local_directory.exists() and not local_directory.is_dir():
            raise ValueError(f"Stage path is not a directory: {local_directory}")
        local_directory.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            local_directory / STAGE_LINK_FILENAME,
            {
                "format": STAGE_LINK_FORMAT,
                "schema_version": 1,
                "target_workspace": str(target_root),
            },
        )
    elif action == "remove":
        stage_name = _validate_stage_name(payload.get("stage"))
        link_path = root / stage_name / STAGE_LINK_FILENAME
        if not link_path.is_file():
            raise ValueError(f"Stage link does not exist: {link_path}")
        link_path.unlink()
    elif action != "list":
        raise ValueError(f"Unsupported stage link action: {action}")

    return {
        "data_root": str(root),
        "stages": [
            _stage_link_status(root, stage_name)
            for stage_name in DISCLOSURE_STAGE_NAMES
        ],
    }


def resolve_disclosure_workspace(
    data_root: str | Path, *, create: bool = False
) -> DisclosureWorkspace:
    raw = str(data_root or "").strip()
    if not raw:
        raise ValueError("data_root is required")
    root = Path(raw).expanduser().resolve()
    _validate_workspace_root(root)
    return DisclosureWorkspace(root=root, create_on_access=create)


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
        workspace.external_compress_mode(mode).mkdir(parents=True, exist_ok=True)
        workspace.internal_mode(mode).mkdir(parents=True, exist_ok=True)
        workspace.sections_mode(mode).mkdir(parents=True, exist_ok=True)
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
    external_path = workspace.external_mode(normalized_mode)
    external_compress_path = workspace.external_compress_mode(normalized_mode)
    converted_path = workspace.converted_mode(normalized_mode)
    return {
        "download_output_directory": str(workspace.list),
        "sqlite_source_path": str(workspace.list),
        "sqlite_output_directory": str(workspace.table),
        "external_html_transfer_directory": str(workspace.filtered),
        "external_html_output_directory": str(external_path),
        "external_html_compress_input_directory": str(external_path),
        "external_html_compress_output_directory": str(external_compress_path),
        "external_html_compressed_json_path": str(
            external_compress_path / "compressed-external-html.json"
        ),
        "internal_html_output_directory": str(
            workspace.internal_mode(normalized_mode)
        ),
        "html_section_split_output_directory": str(
            workspace.sections_mode(normalized_mode)
        ),
        "html_parse_output_directory": str(converted_path),
        "html_parse_result_path": str(
            converted_path / f"parsed-{normalized_mode}.json"
        ),
    }


def _set_default(payload: dict[str, Any], key: str, value: object) -> None:
    if not str(payload.get(key) or "").strip():
        payload[key] = value


def _set_stage_path(
    payload: dict[str, Any], key: str, value: object, *, linked: bool
) -> None:
    if linked:
        payload[key] = value
    else:
        _set_default(payload, key, value)


def _stage_is_linked(workspace: DisclosureWorkspace, stage_name: str) -> bool:
    return workspace.stage_directory(stage_name) != workspace.root / stage_name


def _is_under_workspace_sections(
    workspace: DisclosureWorkspace, path: object
) -> bool:
    raw = str(path or "").strip()
    if not raw:
        return False
    resolved = Path(raw).expanduser().resolve()
    stage = workspace.sections.resolve()
    return resolved == stage or stage in resolved.parents


def _assign_sections_mode_directory(
    payload: dict[str, Any],
    key: str,
    workspace: DisclosureWorkspace,
    *,
    mode: object,
    parent_mode: object,
    linked: bool,
) -> None:
    provided = str(payload.get(key) or "").strip()
    if linked or not provided or _is_under_workspace_sections(workspace, provided):
        payload[key] = str(
            workspace.sections_owner_mode(mode, parent_mode=parent_mode)
        )


def apply_workspace_defaults(
    kind: str,
    body: dict[str, Any],
    *,
    create_workspace: bool = True,
) -> dict[str, Any]:
    """Fill missing stage paths from ``data_root`` without blocking overrides."""
    payload = dict(body)
    data_root = str(payload.get("data_root") or "").strip()
    if not data_root:
        return payload
    workspace = resolve_disclosure_workspace(data_root, create=create_workspace)
    normalized_kind = str(kind or "").strip()
    parent_mode = body.get("parent_mode")

    if normalized_kind == "kind_download":
        # The download detail page accepts the workspace root. Raw KIND files
        # always live in the first canonical stage below that root.
        if payload.get("separate_output_directory") and not _stage_is_linked(
            workspace, "01-list"
        ):
            _set_default(payload, "output_directory", str(workspace.list))
        else:
            payload["output_directory"] = str(workspace.list)
    elif normalized_kind == "table_build":
        _set_stage_path(
            payload,
            "root_directory",
            str(workspace.list),
            linked=_stage_is_linked(workspace, "01-list"),
        )
        _set_stage_path(
            payload,
            "output_path",
            str(workspace.table),
            linked=_stage_is_linked(workspace, "02-table"),
        )
    elif normalized_kind == "filter":
        if str(payload.get("classification_path") or "").strip():
            raise ValueError("classification_path is not supported; use data_root")
        if str(payload.get("root_directory") or "").strip():
            raise ValueError("root_directory is not supported; use data_root")
        payload["mode"] = validate_workspace_mode(payload.get("mode"))
        _set_stage_path(
            payload,
            "external_html_transfer_path",
            str(workspace.filtered),
            linked=_stage_is_linked(workspace, "03-filter"),
        )
    elif normalized_kind in {
        "external_html_download",
        "external_html_integrity_baseline",
    }:
        mode = validate_workspace_mode(payload.get("mode"))
        _set_stage_path(
            payload,
            "output_directory",
            str(workspace.external_owner_mode(mode, parent_mode=parent_mode)),
            linked=_stage_is_linked(workspace, "04-external-html-download"),
        )
    elif normalized_kind == "external_html_compress":
        mode = validate_workspace_mode(payload.get("mode"))
        input_directory = workspace.external_owner_mode(mode, parent_mode=parent_mode)
        output_directory = workspace.external_compress_owner_mode(
            mode, parent_mode=parent_mode
        )
        _set_stage_path(
            payload,
            "input_directory",
            str(input_directory),
            linked=_stage_is_linked(workspace, "04-external-html-download"),
        )
        _set_stage_path(
            payload,
            "output_directory",
            str(output_directory),
            linked=_stage_is_linked(workspace, "04-external-html-compress"),
        )
    elif normalized_kind in {
        "internal_html_download",
        "internal_html_integrity_baseline",
    }:
        mode = validate_workspace_mode(payload.get("mode"))
        external_compress_owner = workspace.external_compress_owner_mode(
            mode, parent_mode=parent_mode
        )
        internal_owner = workspace.internal_owner_mode(mode, parent_mode=parent_mode)
        _set_stage_path(
            payload,
            "source_compressed_json_path",
            str(external_compress_owner / "compressed-external-html.json"),
            linked=_stage_is_linked(workspace, "04-external-html-compress"),
        )
        _set_stage_path(
            payload,
            "output_directory",
            str(internal_owner),
            linked=_stage_is_linked(workspace, "05-internal-html-download"),
        )
    elif normalized_kind in {"section_inspect", "section_kinds", "section_list"}:
        internal_linked = _stage_is_linked(workspace, "05-internal-html-download")
        if internal_linked or not str(payload.get("input_directory") or "").strip():
            mode = validate_workspace_mode(payload.get("mode"))
            _set_stage_path(
                payload,
                "input_directory",
                str(workspace.internal_owner_mode(mode, parent_mode=parent_mode)),
                linked=internal_linked,
            )
    elif normalized_kind == "section_save":
        internal_linked = _stage_is_linked(workspace, "05-internal-html-download")
        if internal_linked or not str(payload.get("input_directory") or "").strip():
            mode = validate_workspace_mode(payload.get("mode"))
            _set_stage_path(
                payload,
                "input_directory",
                str(workspace.internal_owner_mode(mode, parent_mode=parent_mode)),
                linked=internal_linked,
            )
        _assign_sections_mode_directory(
            payload,
            "output_directory",
            workspace,
            mode=payload.get("mode"),
            parent_mode=parent_mode,
            linked=_stage_is_linked(workspace, "06-sections"),
        )
    elif normalized_kind == "parse":
        mode = validate_workspace_mode(payload.get("mode"))
        _assign_sections_mode_directory(
            payload,
            "input_directory",
            workspace,
            mode=mode,
            parent_mode=parent_mode,
            linked=_stage_is_linked(workspace, "06-sections"),
        )
        _set_stage_path(
            payload,
            "output_directory",
            str(
                workspace.converted_filter_mode(
                    mode,
                    parent_mode=parent_mode,
                )
            ),
            linked=_stage_is_linked(workspace, "07-converted"),
        )
        _set_stage_path(
            payload,
            "filtered_metadata_path",
            str(
                workspace.filter_mode(mode, parent_mode=parent_mode)
                / "filtered.json"
            ),
            linked=_stage_is_linked(workspace, "03-filter"),
        )
        _set_stage_path(
            payload,
            "compressed_metadata_path",
            str(
                workspace.external_compress_owner_mode(mode, parent_mode=parent_mode)
                / "compressed-external-html.json"
            ),
            linked=_stage_is_linked(workspace, "04-external-html-compress"),
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
