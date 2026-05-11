"""KIND disclosure viewer HTML parsing helpers for the web UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from finiq_marketDesk.web.html_parsers import (
    parse_asset_transaction,
    parse_bond_issuance,
    parse_rights_issuance,
    parse_security_transaction,
    parse_shareholder_meeting,
)

ParseFunction = Callable[[str | bytes], dict[str, Any]]

PARSER_REGISTRY = {
    "bond_issuance": parse_bond_issuance,
    "rights_issuance": parse_rights_issuance,
    "shareholder_meeting": parse_shareholder_meeting,
    "asset_transaction": parse_asset_transaction,
    "security_transaction": parse_security_transaction,
}


def _parse_limit(value: Any) -> int | None:
    if value in (None, ""):
        return None
    parsed = int(value)
    if parsed < 1:
        msg = "limit must be >= 1"
        raise ValueError(msg)
    return parsed


def _collect_html_files(input_directory: Path, limit: int | None) -> list[Path]:
    files = sorted(path for path in input_directory.iterdir() if path.is_file() and path.suffix.lower() == ".html")
    return files[:limit] if limit is not None else files


def parse_disclosure_html_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Parse downloaded KIND viewer HTML files with the selected mode parser."""
    mode = str(body.get("mode") or "").strip()
    if not mode:
        msg = "mode is required"
        raise ValueError(msg)
    parser = PARSER_REGISTRY.get(mode)
    if parser is None:
        supported_modes = ", ".join(sorted(PARSER_REGISTRY))
        msg = f"unsupported mode: {mode!r}. supported modes: {supported_modes}"
        raise ValueError(msg)

    input_directory_raw = str(body.get("input_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()
    if not input_directory.is_dir():
        msg = f"input_directory does not exist: {input_directory}"
        raise ValueError(msg)

    output_path_raw = str(body.get("output_path") or "").strip()
    if output_path_raw:
        output_path = Path(output_path_raw).expanduser().resolve()
    else:
        output_path = input_directory / f"parsed-{mode}.json"

    limit = _parse_limit(body.get("limit"))
    skip_errors = bool(body.get("skip_errors", True))
    html_files = _collect_html_files(input_directory, limit)

    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for html_file in html_files:
        try:
            records.append(parser(html_file.read_bytes(), file_path=html_file))
        except Exception as exc:
            if not skip_errors:
                raise
            errors.append({"source_file": str(html_file), "error": str(exc)})

    payload = {
        "format": "finiq_disclosure_html_parse_v1",
        "mode": mode,
        "input_directory": str(input_directory),
        "output_path": str(output_path),
        "summary": {
            "found_files": len(html_files),
            "parsed_files": len(records),
            "failed_files": len(errors),
        },
        "records": records,
        "errors": errors,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
