"""Common data utilities for FINIQ."""

from __future__ import annotations

from pathlib import Path

def find_company_classification_files(root_directory: str | Path) -> list[Path]:
    """Return prebuilt company-classification JSON files under *root_directory*."""
    root = Path(root_directory).resolve()
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.rglob("*.json")
        if "company_classification" in path.name
        and not path.name.endswith(".partial.json")
    )

def company_classification_path(root_directory: str | Path) -> Path:
    """Return the default company-classification JSON path for *root_directory*."""
    return Path(root_directory).resolve() / "kind.company_classification.json"
