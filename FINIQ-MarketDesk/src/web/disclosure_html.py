"""KIND disclosure viewer HTML download helpers for the web UI."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

_DATASCRAPER_SRC = Path(__file__).resolve().parents[3] / "FINIQ-DataScraper" / "src"
if _DATASCRAPER_SRC.is_dir():
    data_scraper_path = str(_DATASCRAPER_SRC)
    if data_scraper_path not in sys.path:
        sys.path.insert(0, data_scraper_path)

from core.client import download_disclosure_viewer_htmls
from core.constants import DEFAULT_REQUEST_HEADERS

ACPT_NUMBER_KEYS = {"acpt_no", "acptno", "acptNo", "acpt_no_list", "acptNumbers"}


def collect_acpt_numbers_from_json(value: Any) -> list[str]:
    """Collect unique KIND receipt numbers from nested JSON-like data."""
    numbers: list[str] = []
    seen: set[str] = set()

    def add(raw_value: object) -> None:
        normalized = str(raw_value or "").strip()
        if not normalized or not normalized.isdigit() or normalized in seen:
            return
        seen.add(normalized)
        numbers.append(normalized)

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key in ACPT_NUMBER_KEYS:
                    if isinstance(child, list):
                        for child_item in child:
                            add(child_item)
                    else:
                        add(child)
                visit(child)
            return
        if isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return numbers


def download_disclosure_html_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Download KIND viewer HTML files for receipt numbers found in the request JSON."""
    output_directory = str(body.get("output_directory") or "").strip()
    if not output_directory:
        msg = "output_directory is required"
        raise ValueError(msg)

    source_json = body.get("json")
    if source_json is None:
        source_json = body.get("payload")
    if source_json is None:
        msg = "json is required"
        raise ValueError(msg)

    acpt_numbers = collect_acpt_numbers_from_json(source_json)
    if not acpt_numbers:
        msg = "No acpt_no values found in JSON"
        raise ValueError(msg)

    limit = body.get("limit")
    if limit not in (None, ""):
        parsed_limit = int(limit)
        if parsed_limit < 1:
            msg = "limit must be >= 1"
            raise ValueError(msg)
        acpt_numbers = acpt_numbers[:parsed_limit]

    progress_log: list[str] = []
    saved_paths = download_disclosure_viewer_htmls(
        output_directory=Path(output_directory).expanduser().resolve(),
        request_headers=DEFAULT_REQUEST_HEADERS,
        acpt_numbers=acpt_numbers,
        timeout=float(body.get("timeout") or 20.0),
        wait_seconds_between_requests=float(body.get("wait_seconds") or 0.0),
        max_requests_per_minute=int(body.get("max_requests_per_minute") or 90),
        skip_existing=bool(body.get("skip_existing", True)),
        progress_callback=progress_log.append,
    )
    return {
        "format": "kind_disclosure_html_download_v1",
        "output_directory": str(Path(output_directory).expanduser().resolve()),
        "requested_count": len(acpt_numbers),
        "saved_count": len(saved_paths),
        "acpt_numbers": acpt_numbers,
        "saved_files": [str(path) for path in saved_paths],
        "progress_log": progress_log[-100:],
    }
