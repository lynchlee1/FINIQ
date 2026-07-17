"""Helpers for locating and ordering downloaded KIND result pages."""

from __future__ import annotations

import re
from pathlib import Path

_RESULT_PAGE_NUMBER_RE = re.compile(r"_post_page_(?P<page>\d+)\.body$")


def result_page_number(path: str | Path) -> int:
    """Extract the numeric page number from a saved KIND result page path."""
    match = _RESULT_PAGE_NUMBER_RE.search(Path(path).name)
    if match is None:
        raise ValueError(f"Invalid KIND result page filename: {Path(path).name}")
    return int(match.group("page"))


def sorted_result_page_paths(folder: str | Path) -> list[Path]:
    """Return saved KIND result pages ordered by numeric page number."""
    target = Path(folder).resolve()
    return sorted(
        target.glob("*_post_page_*.body"),
        key=lambda path: (result_page_number(path), path.name),
    )


__all__ = [
    "result_page_number",
    "sorted_result_page_paths",
]
