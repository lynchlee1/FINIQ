"""FINIQ project configuration and path management."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from dataclasses import dataclass

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
RESOURCES_DIR = PROJECT_ROOT / "resources"
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
    "sqlite_manifest_path",
    "html_output_directory",
    "html_transfer_directory",
    "html_parse_result_path",
    "html_parse_mode",
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
    sqlite_manifest_path: str = ""
    html_output_directory: str = ""
    html_transfer_directory: str = ""
    html_parse_result_path: str = ""
    html_parse_mode: str = ""

def get_default_settings_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "finiq.data_scraper" / "appdata.json"

def normalize_path(value: str) -> str:
    return str(Path(value).expanduser().resolve())

def load_settings(settings_path: str | Path) -> dict[str, str]:
    path = Path(settings_path)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    settings: dict[str, str] = {}
    for key in SAVED_SETTINGS_KEYS:
        value = payload.get(key)
        if not value or not isinstance(value, str):
            continue
        if key == "html_parse_mode":
            settings[key] = value
        else:
            settings[key] = normalize_path(value)
    return settings

def save_settings(settings_path: str | Path, settings: dict[str, Any]):
    path = Path(settings_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean_settings = {k: v for k, v in settings.items() if k in SAVED_SETTINGS_KEYS}
    path.write_text(json.dumps(clean_settings, indent=2, ensure_ascii=False), encoding="utf-8")

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
        sqlite_manifest_path=settings.get("sqlite_manifest_path", str(KIND_DATA_DIR / "manifest.json")),
        html_output_directory=settings.get("html_output_directory", str(KIND_DATA_DIR / "html")),
        html_transfer_directory=settings.get("html_transfer_directory", str(KIND_DATA_DIR / "transfer")),
        html_parse_result_path=settings.get("html_parse_result_path", str(KIND_DATA_DIR / "parsed")),
        html_parse_mode=settings.get("html_parse_mode", "bond_issuance"),
    )
