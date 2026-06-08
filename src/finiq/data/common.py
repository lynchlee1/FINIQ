"""Common data utilities for FINIQ."""

from __future__ import annotations

from pathlib import Path

def find_company_classification_files(root_directory: str | Path) -> list[Path]:
    """Return prebuilt company-classification artifacts under *root_directory*."""
    root = Path(root_directory).resolve()
    if not root.is_dir():
        return []
    paths: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "company_classification" not in path.name:
            continue
        if path.name.endswith(".partial.json"):
            continue
        suffix = path.suffix.lower()
        if suffix not in {".json", ".sqlite", ".sqlite3", ".db"}:
            continue
        if suffix == ".json" and path.with_suffix(".sqlite").is_file():
            continue
        paths.append(path)
    return sorted(paths)

def company_classification_path(root_directory: str | Path) -> Path:
    """Return the default company-classification JSON path for *root_directory*."""
    return Path(root_directory).resolve() / "kind.company_classification.json"
