"""File discovery helpers for MarketDesk configuration."""

from __future__ import annotations

from pathlib import Path

from finiq.market_desk.data.facade import find_company_classification_files


def _classification_option_label(path: Path) -> str:
    parent_name = path.parent.name
    if parent_name == "kind":
        return path.name
    return f"{parent_name} / {path.name}"


def list_classification_files(root_directory: str | Path) -> list[dict[str, str]]:
    root = Path(root_directory).resolve()
    return [
        {
            "path": str(path),
            "name": path.name,
            "label": _classification_option_label(path),
        }
        for path in find_company_classification_files(root)
    ]


def _looks_like_price_directory(path: Path) -> bool:
    if not path.is_dir():
        return False
    if any(path.glob("*.parquet")):
        return True
    return (path / "manifest.json").is_file()


def list_price_source_files(root_directory: str | Path) -> list[dict[str, str]]:
    root = Path(root_directory).resolve()
    if not root.exists():
        return []

    candidates: list[Path] = []
    if _looks_like_price_directory(root):
        candidates.append(root)

    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if _looks_like_price_directory(child):
            candidates.append(child)

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique_candidates.append(candidate)

    return [
        {
            "path": str(path),
            "name": path.name,
            "label": path.name if path.parent == root else str(path.relative_to(root)),
        }
        for path in unique_candidates
    ]


def resolve_default_classification(root_directory: str | Path) -> str | None:
    root = Path(root_directory).resolve()
    files = list_classification_files(root)
    if not files:
        return None
    for preferred_name in ("kind.company_classification.json", "kind.company_classification.sample.json"):
        for file_info in files:
            if Path(file_info["path"]).name == preferred_name:
                return file_info["path"]
    return files[0]["path"]


def resolve_default_price_source(root_directory: str | Path, current_path: str | Path | None = None) -> str | None:
    root = Path(root_directory).resolve()
    current = Path(current_path).resolve() if current_path else None
    files = list_price_source_files(root)
    if not files:
        return None
    if current:
        for file_info in files:
            if Path(file_info["path"]) == current:
                return file_info["path"]
    return files[0]["path"]
