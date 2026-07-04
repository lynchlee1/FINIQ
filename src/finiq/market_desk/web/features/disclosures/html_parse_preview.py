"""Disclosure parse preview payload helpers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from lxml import html as lxml_html

from finiq.market_desk.web.features.disclosures.html_parse_support import *
from finiq.market_desk.web.html_parsers.common import clean_text, element_text

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


def _structured_bond_issue_method_candidate(html_bytes: bytes) -> str | None:
    try:
        document = lxml_html.fromstring(html_bytes.decode("utf-8", errors="ignore"))
    except Exception:
        return None
    for row in document.xpath(".//tr[contains(., '사채발행방법')]"):
        values = [
            clean_text(element_text(cell))
            for cell in row.xpath("./th|./td")
        ]
        values = [value for value in values if value]
        for value in reversed(values):
            if "사채발행방법" not in value.replace(" ", ""):
                return value
    return None


def _filter_candidate_workers(value: Any, total_files: int) -> int:
    if value in (None, ""):
        return min(8, max(1, total_files))
    try:
        requested_workers = int(value)
    except (TypeError, ValueError):
        requested_workers = 8
    return max(1, min(requested_workers, max(1, total_files), 16))


def _extract_filter_candidate_from_file(
    *,
    html_file: Path,
    requested_mode: str,
    field: str,
    parser: ParseFunction,
    metadata_index: dict[str, dict[str, Any]],
) -> str | list[Any] | None:
    html_bytes = html_file.read_bytes()
    if requested_mode == "bond_issuance" and field == "사채발행방법":
        return _structured_bond_issue_method_candidate(html_bytes)
    record = _apply_manifest_metadata(
        _compact_record(parser(html_bytes, file_path=html_file)),
        metadata_index,
        mode=requested_mode,
    )
    return record.get(field)


def build_parse_filter_candidates_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Return available parsed field values from every HTML file in a folder."""
    requested_mode = str(body.get("mode") or "bond_issuance").strip()
    parser = PARSER_REGISTRY.get(requested_mode)
    if parser is None:
        supported_modes = ", ".join(sorted(PARSER_REGISTRY))
        msg = (
            f"unsupported mode: {requested_mode!r}. supported modes: {supported_modes}"
        )
        raise ValueError(msg)

    field = str(body.get("field") or "사채발행방법").strip()
    if not field:
        msg = "field is required"
        raise ValueError(msg)

    input_directory_raw = str(body.get("input_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()
    if not input_directory.is_dir():
        msg = f"input_directory does not exist: {input_directory}"
        raise ValueError(msg)

    html_files = _collect_html_files(input_directory, None)
    metadata_index = _load_html_manifest_metadata_index(input_directory)
    worker_count = _filter_candidate_workers(
        body.get("parallel_workers", body.get("workers")), len(html_files)
    )
    candidate_counts: dict[str, int] = {}
    errors: list[dict[str, Any]] = []
    indexed_files = list(enumerate(html_files, start=1))

    def record_value(value: Any) -> None:
        values = value if isinstance(value, list) else [value]
        for candidate in values:
            text = str(candidate or "").strip()
            if text:
                candidate_counts[text] = candidate_counts.get(text, 0) + 1

    def record_error(index: int, html_file: Path, exc: Exception) -> None:
        errors.append(
            {
                "index": index,
                "source_file": str(html_file),
                "error": str(exc),
            }
        )

    if worker_count > 1:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    _extract_filter_candidate_from_file,
                    html_file=html_file,
                    requested_mode=requested_mode,
                    field=field,
                    parser=parser,
                    metadata_index=metadata_index,
                ): (index, html_file)
                for index, html_file in indexed_files
            }
            for future in as_completed(futures):
                index, html_file = futures[future]
                try:
                    record_value(future.result())
                except Exception as exc:
                    record_error(index, html_file, exc)
    else:
        for index, html_file in indexed_files:
            try:
                record_value(
                    _extract_filter_candidate_from_file(
                        html_file=html_file,
                        requested_mode=requested_mode,
                        field=field,
                        parser=parser,
                        metadata_index=metadata_index,
                    )
                )
            except Exception as exc:
                record_error(index, html_file, exc)

    candidates = [
        {"value": value, "count": count}
        for value, count in sorted(
            candidate_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    return {
        "format": "finiq_parse_filter_candidates_v1",
        "mode": requested_mode,
        "field": field,
        "input_directory": str(input_directory),
        "summary": {
            "records": len(html_files),
            "candidates": len(candidates),
            "errors": len(errors),
        },
        "candidates": candidates,
        "errors": errors,
    }




__all__ = [name for name in globals() if not name.startswith("__")]
