"""FINIQ project configuration and path management."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field

def _resolve_workspace_root() -> Path:
    """Resolve the project root directory."""
    cwd = Path.cwd()
    if (cwd / "src" / "finiq").exists():
        return cwd
    this_file = Path(__file__).resolve()
    potential_root = this_file.parents[2]
    if (potential_root / "src" / "finiq").exists():
        return potential_root
    return cwd

PROJECT_ROOT = _resolve_workspace_root()
ASSETS_DIR = PROJECT_ROOT / "assets"
RESOURCES_DIR = PROJECT_ROOT / "resources"
QUANTIWISE_EXCEL_DIR = RESOURCES_DIR / "Quantiwise"
KIND_DATA_DIR = RESOURCES_DIR / "kind"
DATABASE_DIR = RESOURCES_DIR / "database"
QUANTI_DIR = DATABASE_DIR / "by_item"

SAVED_SETTINGS_KEYS = (
    "output_root",
    "quanti_dir",
    "price_root_directory",
    "selected_classification_path",
    "sqlite_source_path",
    "download_output_directory",
    "sqlite_output_directory",
    "sqlite_manifest_path",
    "html_output_directory",
    "html_content_output_directory",
    "html_transfer_directory",
    "html_parse_result_path",
    "html_parse_mode",
    "integrated_merge_input_path",
    "integrated_merge_output_path",
    "integrated_history_item_registry_path",
    "integrated_history_output_path",
    "asset_excel_source_directory",
    "asset_excel_output_directory",
    "asset_excel_merge_input_directory",
    "asset_excel_merge_output_directory",
    "asset_excel_account_mappings",
    "html_download_source_path",
    "html_merge_output_path",
    "html_content_compressed_json_path",
    "html_external_compress_input_directory",
    "html_external_compress_output_directory",
    "integrated_data_values",
    "change_log_date_thresholds",
    "change_log_numeric_thresholds",
    "condition_presets",
)

@dataclass(slots=True)
class AppConfig:
    output_root: str
    quanti_dir: str
    host: str = "127.0.0.1"
    port: int = 8765
    settings_path: str = ""
    price_root_directory: str = ""
    selected_classification_path: str = ""
    sqlite_source_path: str = ""
    download_output_directory: str = ""
    sqlite_output_directory: str = ""
    sqlite_manifest_path: str = ""
    html_output_directory: str = ""
    html_content_output_directory: str = ""
    html_transfer_directory: str = ""
    html_parse_result_path: str = ""
    html_parse_mode: str = ""
    integrated_merge_input_path: str = ""
    integrated_merge_output_path: str = ""
    integrated_history_item_registry_path: str = ""
    integrated_history_output_path: str = ""
    asset_excel_source_directory: str = ""
    asset_excel_output_directory: str = ""
    asset_excel_merge_input_directory: str = ""
    asset_excel_merge_output_directory: str = ""
    asset_excel_account_mappings: list[dict[str, Any]] = field(default_factory=list)
    html_download_source_path: str = ""
    html_merge_output_path: str = ""
    html_content_compressed_json_path: str = ""
    html_external_compress_input_directory: str = ""
    html_external_compress_output_directory: str = ""
    integrated_data_values: dict[str, str] = field(default_factory=dict)
    change_log_date_thresholds: dict[str, float] = field(default_factory=dict)
    change_log_numeric_thresholds: dict[str, float] = field(default_factory=dict)
    condition_presets: list[dict[str, Any]] = field(default_factory=list)

def get_default_settings_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "finiq.data_scraper" / "appdata.json"

def normalize_path(value: str) -> str:
    if not value or not str(value).strip():
        return ""
    try:
        return str(Path(value).expanduser().resolve())
    except Exception:
        return str(value)

def load_settings(settings_path: str | Path) -> dict[str, Any]:
    path = Path(settings_path)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    
    settings: dict[str, Any] = {}
    for key in SAVED_SETTINGS_KEYS:
        if key not in payload:
            continue
        
        value = payload[key]
        if key == "html_parse_mode":
            settings[key] = str(value)
        elif isinstance(value, dict):
            settings[key] = value
        elif isinstance(value, str):
            settings[key] = normalize_path(value)
        else:
            settings[key] = value
    return settings

def save_settings(settings_path: str | Path, settings: dict[str, Any]):
    path = Path(settings_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        clean_settings = {}
        for key in SAVED_SETTINGS_KEYS:
            if key in settings:
                clean_settings[key] = settings[key]
        path.write_text(json.dumps(clean_settings, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"Error saving settings to {path}: {e}")

def init_config() -> AppConfig:
    settings_path = get_default_settings_path()
    settings = load_settings(settings_path)
    
    output_root = settings.get("output_root", str(KIND_DATA_DIR))
    quanti_dir = settings.get("quanti_dir", str(QUANTI_DIR))
    
    return AppConfig(
        output_root=output_root,
        quanti_dir=quanti_dir,
        settings_path=str(settings_path),
        price_root_directory=settings.get("price_root_directory", str(KIND_DATA_DIR / "price")),
        selected_classification_path=settings.get("selected_classification_path", str(KIND_DATA_DIR / "classification" / "all_companies.json")),
        sqlite_source_path=settings.get("sqlite_source_path", str(KIND_DATA_DIR / "kind_disclosures.sqlite")),
        download_output_directory=settings.get("download_output_directory", output_root),
        sqlite_output_directory=settings.get("sqlite_output_directory", output_root),
        sqlite_manifest_path=settings.get("sqlite_manifest_path", str(KIND_DATA_DIR / "manifest.json")),
        html_output_directory=settings.get("html_output_directory", str(KIND_DATA_DIR / "html")),
        html_content_output_directory=settings.get("html_content_output_directory", str(KIND_DATA_DIR / "html_contents")),
        html_transfer_directory=settings.get("html_transfer_directory", str(KIND_DATA_DIR / "transfer")),
        html_parse_result_path=settings.get("html_parse_result_path", str(KIND_DATA_DIR / "parsed")),
        html_parse_mode=settings.get("html_parse_mode", "bond_issuance"),
        integrated_merge_input_path=settings.get("integrated_merge_input_path", ""),
        integrated_merge_output_path=settings.get("integrated_merge_output_path", ""),
        integrated_history_item_registry_path=settings.get("integrated_history_item_registry_path", ""),
        integrated_history_output_path=settings.get("integrated_history_output_path", ""),
        asset_excel_source_directory=settings.get("asset_excel_source_directory", ""),
        asset_excel_output_directory=settings.get("asset_excel_output_directory", ""),
        asset_excel_merge_input_directory=settings.get("asset_excel_merge_input_directory", ""),
        asset_excel_merge_output_directory=settings.get("asset_excel_merge_output_directory", ""),
        asset_excel_account_mappings=settings.get("asset_excel_account_mappings", []),
        html_download_source_path=settings.get("html_download_source_path", ""),
        html_merge_output_path=settings.get("html_merge_output_path", ""),
        html_content_compressed_json_path=settings.get("html_content_compressed_json_path", ""),
        html_external_compress_input_directory=settings.get("html_external_compress_input_directory", ""),
        html_external_compress_output_directory=settings.get("html_external_compress_output_directory", ""),
        integrated_data_values=settings.get("integrated_data_values", {}),
        change_log_date_thresholds=settings.get("change_log_date_thresholds", {}),
        change_log_numeric_thresholds=settings.get("change_log_numeric_thresholds", {}),
        condition_presets=settings.get("condition_presets", []),
    )
