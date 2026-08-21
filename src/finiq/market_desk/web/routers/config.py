from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from finiq.concurrency import available_cpu_count
from finiq.config import (
    build_disclosure_workspace_path_settings,
    normalize_path,
    save_settings,
)
from finiq.market_desk.web.features.market_data.discovery import (
    list_classification_files,
    list_price_source_files,
    resolve_default_classification,
    resolve_default_price_source,
)
from finiq.market_desk.web.features.market_data.service_common import (
    DISPLAY_FREQUENCY_OPTIONS,
    INSIGHT_RANGE_OPTIONS,
    PRICE_SOURCE_FDR,
    PRICE_SOURCE_LABELS,
    PRICE_SOURCE_QUANTI,
)
from finiq.market_desk.web.features.downloads.kind_common import (
    configure_download_job_retention,
)
from finiq.market_desk.web.jobs import job_manager, normalize_job_retention_minutes
class SettingsUpdate(BaseModel):
    output_root: Optional[str] = None
    quanti_dir: Optional[str] = None
    price_root_directory: Optional[str] = None
    selected_classification_path: Optional[str] = None
    sqlite_source_path: Optional[str] = None
    download_output_directory: Optional[str] = None
    disclosure_separate_output_directory: Optional[bool] = None
    sqlite_output_directory: Optional[str] = None
    external_html_output_directory: Optional[str] = None
    internal_html_output_directory: Optional[str] = None
    html_section_split_output_directory: Optional[str] = None
    external_html_transfer_directory: Optional[str] = None
    html_parse_output_directory: Optional[str] = None
    html_parse_result_path: Optional[str] = None
    html_parse_mode: Optional[str] = None
    html_parser_method: Optional[str] = None
    integrated_merge_input_path: Optional[str] = None
    integrated_merge_output_path: Optional[str] = None
    integrated_history_item_registry_path: Optional[str] = None
    integrated_history_output_path: Optional[str] = None
    asset_excel_source_directory: Optional[str] = None
    asset_excel_output_directory: Optional[str] = None
    asset_excel_merge_input_directory: Optional[str] = None
    asset_excel_merge_output_directory: Optional[str] = None
    asset_excel_merge_same_directory: Optional[bool] = None
    asset_excel_cleanup_merged_items: Optional[bool] = None
    asset_excel_duplicate_scan_recursive: Optional[bool] = None
    asset_excel_account_mappings: Optional[list[dict[str, Any]]] = None
    external_html_compressed_json_path: Optional[str] = None
    external_html_compress_input_directory: Optional[str] = None
    external_html_compress_output_directory: Optional[str] = None
    integrated_data_values: Optional[dict[str, str]] = None
    change_log_date_thresholds: Optional[dict[str, float]] = None
    change_log_numeric_thresholds: Optional[dict[str, float]] = None
    job_retention_minutes: Optional[int] = None


class FileDialogRequest(BaseModel):
    mode: str = "file"
    title: str = "경로 선택"
    default_path: str = ""


def _normalize_file_dialog_mode(mode: str) -> str:
    normalized = str(mode or "file").strip().lower()
    if normalized in {"dir", "folder", "directory"}:
        return "folder"
    if normalized in {"file", "save"}:
        return normalized
    raise HTTPException(status_code=400, detail=f"Unsupported file dialog mode: {mode}")


def _choose_finder_path(*, mode: str, title: str, default_path: str = "") -> str:
    if sys.platform != "darwin":
        raise HTTPException(status_code=400, detail="Finder path selection is only available on macOS.")
    normalized_mode = _normalize_file_dialog_mode(mode)

    path = Path(default_path).expanduser()
    default_directory = path.parent if path.suffix else path
    while not default_directory.exists() and default_directory != default_directory.parent:
        default_directory = default_directory.parent
    if not default_directory.exists():
        default_directory = Path.home()

    default_name = path.name if path.suffix else ""

    script = r'''
on run argv
  set dialogTitle to item 1 of argv
  set modeName to item 2 of argv
  set defaultDirectory to item 3 of argv
  set defaultName to item 4 of argv
  set defaultLocation to POSIX file defaultDirectory

  if modeName is "folder" then
    set chosenPath to choose folder with prompt dialogTitle default location defaultLocation
  else if modeName is "save" then
    if defaultName is "" then
      set defaultName to "untitled"
    end if
    set chosenPath to choose file name with prompt dialogTitle default name defaultName default location defaultLocation
  else
    set chosenPath to choose file with prompt dialogTitle default location defaultLocation
  end if

  return POSIX path of chosenPath
end run
'''
    result = subprocess.run(
        ["osascript", "-e", script, title, normalized_mode, str(default_directory), default_name],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "User canceled" in stderr or "사용자가 취소" in stderr:
            return ""
        raise HTTPException(status_code=500, detail=stderr or "Finder path selection failed")
    return result.stdout.strip()


ChooseFinderPath = Callable[..., str]


def create_config_router(config: Any, choose_finder_path: ChooseFinderPath = _choose_finder_path) -> APIRouter:
    router = APIRouter()

    def config_payload(*, include_discovery: bool = False) -> dict[str, Any]:
        price_root = config.price_root_directory or str(Path(config.quanti_dir).expanduser().parent)
        workspace_defaults = (
            build_disclosure_workspace_path_settings(
                config.output_root,
                mode=config.html_parse_mode,
            )
            if str(config.output_root).strip() and str(config.html_parse_mode).strip()
            else {}
        )

        def workspace_value(key: str, configured: str) -> str:
            return configured or workspace_defaults.get(key, "")

        payload = {
            "parallel_worker_count": available_cpu_count(),
            "output_root": config.output_root,
            "quanti_dir": config.quanti_dir,
            "price_root_directory": price_root,
            "download_output_directory": workspace_value(
                "download_output_directory", config.download_output_directory
            ),
            "disclosure_separate_output_directory": bool(
                getattr(config, "disclosure_separate_output_directory", False)
            ),
            "sqlite_output_directory": workspace_value(
                "sqlite_output_directory", config.sqlite_output_directory
            ),
            "external_html_output_directory": workspace_value(
                "external_html_output_directory", config.external_html_output_directory
            ),
            "internal_html_output_directory": workspace_value(
                "internal_html_output_directory", config.internal_html_output_directory
            ),
            "html_section_split_output_directory": workspace_value(
                "html_section_split_output_directory",
                config.html_section_split_output_directory,
            ),
            "external_html_transfer_directory": workspace_value(
                "external_html_transfer_directory", config.external_html_transfer_directory
            ),
            "html_parse_output_directory": workspace_value(
                "html_parse_output_directory", config.html_parse_output_directory
            ),
            "html_parse_result_path": workspace_value(
                "html_parse_result_path", config.html_parse_result_path
            ),
            "html_parse_mode": config.html_parse_mode,
            "html_parser_method": config.html_parser_method,
            "price_files": [],
            "selected_price_path": config.quanti_dir,
            "classification_files": [],
            "selected_classification_path": config.selected_classification_path,
            "sqlite_source_path": workspace_value(
                "sqlite_source_path", config.sqlite_source_path
            ),
            "integrated_merge_input_path": config.integrated_merge_input_path,
            "integrated_merge_output_path": config.integrated_merge_output_path,
            "integrated_history_item_registry_path": config.integrated_history_item_registry_path,
            "integrated_history_output_path": config.integrated_history_output_path,
            "asset_excel_source_directory": config.asset_excel_source_directory,
            "asset_excel_output_directory": config.asset_excel_output_directory,
            "asset_excel_merge_input_directory": config.asset_excel_merge_input_directory,
            "asset_excel_merge_output_directory": config.asset_excel_merge_output_directory,
            "asset_excel_merge_same_directory": config.asset_excel_merge_same_directory,
            "asset_excel_cleanup_merged_items": config.asset_excel_cleanup_merged_items,
            "asset_excel_duplicate_scan_recursive": config.asset_excel_duplicate_scan_recursive,
            "asset_excel_account_mappings": config.asset_excel_account_mappings,
            "external_html_compressed_json_path": workspace_value(
                "external_html_compressed_json_path",
                config.external_html_compressed_json_path,
            ),
            "external_html_compress_input_directory": workspace_value(
                "external_html_compress_input_directory",
                config.external_html_compress_input_directory,
            ),
            "external_html_compress_output_directory": workspace_value(
                "external_html_compress_output_directory",
                config.external_html_compress_output_directory,
            ),
            "integrated_data_values": config.integrated_data_values,
            "change_log_date_thresholds": config.change_log_date_thresholds,
            "change_log_numeric_thresholds": config.change_log_numeric_thresholds,
            "job_retention_minutes": config.job_retention_minutes,
            "range_options": list(INSIGHT_RANGE_OPTIONS),
            "display_frequency_options": list(DISPLAY_FREQUENCY_OPTIONS),
            "price_sources": [
                {"key": PRICE_SOURCE_QUANTI, "label": PRICE_SOURCE_LABELS[PRICE_SOURCE_QUANTI]},
                {"key": PRICE_SOURCE_FDR, "label": PRICE_SOURCE_LABELS[PRICE_SOURCE_FDR]},
            ],
        }

        if include_discovery:
            payload["price_files"] = list_price_source_files(price_root)
            payload["selected_price_path"] = resolve_default_price_source(price_root, config.quanti_dir)
            payload["classification_files"] = list_classification_files(config.output_root)
            payload["selected_classification_path"] = config.selected_classification_path or resolve_default_classification(config.output_root)

        return payload

    @router.get("/api/config")
    async def get_config(response: Response, include_discovery: bool = False):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return config_payload(include_discovery=include_discovery)

    @router.post("/api/settings")
    async def save_app_settings(update: SettingsUpdate):
        payload = {
            key: value
            for key, value in update.model_dump(exclude_unset=True).items()
            if value is not None
        }
        if "output_root" in payload and not str(payload["output_root"]).strip():
            raise HTTPException(status_code=400, detail="output_root cannot be blank")
        if "html_parse_mode" in payload and not str(
            payload["html_parse_mode"]
        ).strip():
            raise HTTPException(status_code=400, detail="html_parse_mode cannot be blank")
        if "html_parser_method" in payload and not str(
            payload["html_parser_method"]
        ).strip():
            raise HTTPException(status_code=400, detail="html_parser_method cannot be blank")
        if "job_retention_minutes" in payload:
            try:
                payload["job_retention_minutes"] = normalize_job_retention_minutes(
                    payload["job_retention_minutes"]
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        current_settings = {}
        for key in config.__slots__:
            val = getattr(config, key)
            if isinstance(val, (str, int, float, bool, dict, list)):
                current_settings[key] = val
        original_settings = dict(current_settings)

        def restore_original_settings() -> None:
            for original_key, original_value in original_settings.items():
                setattr(config, original_key, original_value)

        for key, value in payload.items():
            if isinstance(value, bool):
                normalized = value
            elif key == "job_retention_minutes":
                normalized = int(value)
            elif key in {"html_parse_mode", "html_parser_method"}:
                normalized = str(value).strip()
            elif key in (
                "integrated_data_values",
                "change_log_date_thresholds",
                "change_log_numeric_thresholds",
                "asset_excel_account_mappings",
            ) and isinstance(value, (dict, list)):
                normalized = value
            else:
                normalized = normalize_path(str(value))
            setattr(config, key, normalized)
            current_settings[key] = normalized

        workspace_setting_changed = (
            "output_root" in payload or "html_parse_mode" in payload
        )
        if (
            workspace_setting_changed
            and str(config.output_root or "").strip()
            and str(config.html_parse_mode or "").strip()
        ):
            parse_mode = str(config.html_parse_mode).strip()
            try:
                workspace_settings = build_disclosure_workspace_path_settings(
                    config.output_root, mode=parse_mode
                )
            except ValueError as exc:
                restore_original_settings()
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            keys_to_update = (
                workspace_settings
                if "output_root" in payload
                else {
                    key: workspace_settings[key]
                    for key in (
                        "external_html_output_directory",
                        "external_html_compress_input_directory",
                        "external_html_compress_output_directory",
                        "external_html_compressed_json_path",
                        "internal_html_output_directory",
                        "html_parse_output_directory",
                        "html_parse_result_path",
                    )
                }
            )
            for key, value in keys_to_update.items():
                if key in payload:
                    continue
                setattr(config, key, value)
                current_settings[key] = value

        try:
            save_settings(config.settings_path, current_settings)
        except OSError as exc:
            restore_original_settings()
            raise HTTPException(
                status_code=500, detail="Failed to save settings"
            ) from exc
        if "job_retention_minutes" in payload:
            job_manager.set_retention_minutes(config.job_retention_minutes)
            configure_download_job_retention(config.job_retention_minutes)
        return config_payload()

    @router.post("/api/file-dialog")
    async def file_dialog(req: FileDialogRequest):
        path = await asyncio.to_thread(
            choose_finder_path,
            mode=req.mode,
            title=req.title,
            default_path=req.default_path,
        )
        return {"path": path, "cancelled": not bool(path)}

    return router
