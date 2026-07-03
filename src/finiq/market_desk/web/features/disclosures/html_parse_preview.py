"""Disclosure parse preview payload helpers."""

from __future__ import annotations

from finiq.market_desk.web.features.disclosures.html_parse_support import *

def build_parse_preview_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Return a few reports with source-table preview and parsed JSON for the UI."""
    requested_mode = str(body.get("mode") or "").strip()
    if not requested_mode:
        msg = "mode is required"
        raise ValueError(msg)
    parser = PARSER_REGISTRY.get(requested_mode)
    if parser is None:
        supported_modes = ", ".join(sorted(PARSER_REGISTRY))
        msg = (
            f"unsupported mode: {requested_mode!r}. supported modes: {supported_modes}"
        )
        raise ValueError(msg)

    limit = _parse_limit(body.get("limit")) or 3
    output_path_raw = str(
        body.get("output_path") or body.get("parse_result_path") or ""
    ).strip()
    if output_path_raw:
        output_path = _resolve_parse_result_path(
            Path(output_path_raw).expanduser().resolve(), requested_mode
        )
        if output_path.is_file():
            payload = _get_cached_payload(output_path)
            mode = str(payload.get("mode") or requested_mode)
            if mode != requested_mode:
                msg = f"parse result mode must be {requested_mode}"
                raise ValueError(msg)
            records = [
                record
                for record in list(payload.get("records") or [])
                if isinstance(record, dict)
            ]
            visible_records = records[:limit]
            return {
                "format": "finiq_parse_preview_v1",
                "mode": mode,
                "source_kind": "result_json",
                "source_path": str(output_path),
                "summary": {
                    "records": len(records),
                    "visible_records": len(visible_records),
                },
                "records": [
                    _build_preview_record(record, index=index, mode=mode)
                    for index, record in enumerate(visible_records, start=1)
                ],
            }

    input_directory_raw = str(body.get("input_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required when output_path does not point to a result JSON"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()
    if not input_directory.is_dir():
        msg = f"input_directory does not exist: {input_directory}"
        raise ValueError(msg)

    html_files = _collect_html_files(input_directory, limit)
    metadata_index = _load_html_manifest_metadata_index(input_directory)
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, html_file in enumerate(html_files, start=1):
        try:
            records.append(
                _apply_manifest_metadata(
                    _compact_record(
                        parser(html_file.read_bytes(), file_path=html_file)
                    ),
                    metadata_index,
                    mode=requested_mode,
                )
            )
        except Exception as exc:
            errors.append(
                {
                    "index": index,
                    "source_file": str(html_file),
                    "error": str(exc),
                }
            )

    return {
        "format": "finiq_parse_preview_v1",
        "mode": requested_mode,
        "source_kind": "input_directory",
        "source_path": str(input_directory),
        "summary": {
            "records": len(html_files),
            "visible_records": len(records),
            "errors": len(errors),
        },
        "records": [
            _build_preview_record(record, index=index, mode=requested_mode)
            for index, record in enumerate(
                _resolve_correction_family_acpt_numbers(records),
                start=1,
            )
        ],
        "errors": errors,
    }




__all__ = [name for name in globals() if not name.startswith("__")]
