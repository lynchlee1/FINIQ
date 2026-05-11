"""Parser entrypoint for paid/free capital increase disclosures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import build_base_record

MODE = "rights_issuance"


def parse_rights_issuance(html_text: str | bytes, *, file_path: str | Path) -> dict[str, Any]:
    """Parse capital increase HTML into the shared v1 architecture record."""
    return build_base_record(html_text, file_path=file_path, mode=MODE)
