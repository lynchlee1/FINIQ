"""Parser entrypoint for tangible/intangible asset transaction disclosures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import build_base_record

MODE = "asset_transaction"


def parse_asset_transaction(html_text: str | bytes, *, file_path: str | Path) -> dict[str, Any]:
    """Parse asset transaction HTML into the shared v1 architecture record."""
    return build_base_record(html_text, file_path=file_path, mode=MODE)
