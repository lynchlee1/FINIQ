"""Helpers for locating and ordering downloaded KIND result pages."""

from __future__ import annotations

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


__all__ = ["KIND_REPAIR_OVERLAY_DIRNAME", "result_page_number", "sorted_result_page_paths"]
