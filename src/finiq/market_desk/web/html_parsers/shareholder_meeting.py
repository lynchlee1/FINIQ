"""Parser entrypoint for shareholder meeting disclosures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import build_base_record

MODE = "shareholder_meeting"


def parse_shareholder_meeting(html_text: str | bytes, *, file_path: str | Path) -> dict[str, Any]:
    """Parse shareholder meeting HTML into the shared v1 architecture record."""
    return build_base_record(html_text, file_path=file_path, mode=MODE)
