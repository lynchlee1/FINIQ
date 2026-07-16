"""Common data utilities for FINIQ."""

from __future__ import annotations

from pathlib import Path

def find_company_classification_files(root_directory: str | Path) -> list[Path]:
    """Return prebuilt company-classification artifacts under *root_directory*."""
    import os
    import re
    root = Path(root_directory).resolve()
    if not root.is_dir():
        return []
    paths: list[Path] = []

    date_pattern = re.compile(r"^\d{8}_\d{8}$")
    exclude_names = {
        ".finiq",
        ".git",
        ".github",
        "node_modules",
        "frontend",
        "assets"
    }

    for current_root, dirs, files in os.walk(root):
        dirs[:] = [
            d for d in dirs
            if d not in exclude_names and not date_pattern.match(d)
        ]
        
        for file in files:
            if "company_classification" not in file:
                continue
            path = Path(current_root) / file
            if path.suffix.lower() != ".sqlite":
                continue
            paths.append(path)
            
    return sorted(list(set(paths)))

def company_classification_path(root_directory: str | Path) -> Path:
    """Return the canonical company-classification SQLite path."""
    return Path(root_directory).resolve() / "kind.company_classification.sqlite"
