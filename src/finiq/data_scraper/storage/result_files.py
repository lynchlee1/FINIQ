"""Helpers for locating and ordering downloaded KIND result pages."""

from __future__ import annotations

import json
import re
from pathlib import Path

_RESULT_PAGE_NUMBER_RE = re.compile(r"_post_page_(?P<page>\d+)\.body$")
KIND_REPAIR_OVERLAY_DIRNAME = ".kind_page_repairs"


def result_page_number(path: str | Path) -> int:
    """Extract the numeric page number from a saved KIND result page path."""
    match = _RESULT_PAGE_NUMBER_RE.search(Path(path).name)
    if match is None:
        return -1
    return int(match.group("page"))


def sorted_result_page_paths(folder: str | Path) -> list[Path]:
    """Return saved KIND result pages ordered by numeric page number."""
    target = Path(folder).resolve()
    return sorted(
        target.glob("*_post_page_*.body"),
        key=lambda path: (result_page_number(path), path.name),
    )


def effective_result_page_paths(folder: str | Path) -> list[Path]:
    """Return original pages with validated repair-overlay replacements applied."""
    target = Path(folder).resolve()
    page_paths: dict[int, list[Path]] = {}
    for path in sorted_result_page_paths(target):
        page_number = result_page_number(path)
        if page_number >= 1:
            page_paths.setdefault(page_number, []).append(path)
    duplicate_pages = sorted(
        page_number for page_number, paths in page_paths.items() if len(paths) > 1
    )
    if duplicate_pages:
        duplicate_text = ", ".join(str(page) for page in duplicate_pages)
        raise ValueError(
            f"{target}: 중복되는 페이지 번호 {duplicate_text}이 있습니다."
        )

    def ordered_paths() -> list[Path]:
        return [path for page in sorted(page_paths) for path in page_paths[page]]

    manifest_path = target / KIND_REPAIR_OVERLAY_DIRNAME / "manifest.json"
    if not manifest_path.is_file():
        return ordered_paths()
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ordered_paths()
    if not isinstance(payload, dict):
        return ordered_paths()
    pages = payload.get("pages")
    if not isinstance(pages, dict):
        return ordered_paths()
    for page_key, raw_entry in pages.items():
        try:
            page_number = int(page_key)
        except (TypeError, ValueError):
            continue
        if not isinstance(raw_entry, dict):
            continue
        relative_path = str(raw_entry.get("page_path") or "").strip()
        if not relative_path:
            continue
        overlay_path = (target / relative_path).resolve()
        try:
            overlay_path.relative_to(target)
        except ValueError:
            continue
        if overlay_path.is_file() and result_page_number(overlay_path) == page_number:
            page_paths[page_number] = [overlay_path]
    return ordered_paths()


__all__ = [
    "KIND_REPAIR_OVERLAY_DIRNAME",
    "effective_result_page_paths",
    "result_page_number",
    "sorted_result_page_paths",
]
