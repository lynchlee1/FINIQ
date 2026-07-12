"""Disclosure parse preview payload helpers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from finiq.concurrency import bounded_as_completed
from finiq.market_desk.web.features.disclosures.html_parse_support import *

def _parse_with_metadata_title(
    parser: ParseFunction,
    html_bytes: bytes,
    *,
    html_file: Path,
    metadata_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    parser_kwargs: dict[str, Any] = {"file_path": html_file}
    title = _metadata_title_for_file(html_file, metadata_index)
    if title and _parser_accepts_title(parser):
        parser_kwargs["title"] = title
    return parser(html_bytes, **parser_kwargs)


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
    filter_blocks = _parse_filter_blocks(body.get("filter_blocks"))
    input_directory_raw = str(body.get("input_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()
    if not input_directory.is_dir():
        msg = f"input_directory does not exist: {input_directory}"
        raise ValueError(msg)

    html_files = _collect_html_files(input_directory, None)
    filtered_metadata_path, compressed_metadata_path = _parse_metadata_paths(body)
    metadata_index, _ = _load_html_parse_metadata(
        input_directory,
        filtered_metadata_path=filtered_metadata_path,
        compressed_metadata_path=compressed_metadata_path,
    )
    _validate_explicit_kind_disclosed_at_metadata(
        html_files,
        metadata_index,
        filtered_metadata_path,
    )
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, html_file in enumerate(html_files, start=1):
        try:
            html_bytes = html_file.read_bytes()
            record = _apply_parse_metadata(
                _record_without_raw_tables(
                    _parse_with_metadata_title(
                        parser,
                        html_bytes,
                        html_file=html_file,
                        metadata_index=metadata_index,
                    )
                ),
                metadata_index,
                mode=requested_mode,
            )
            if _record_matches_filter_blocks(record, filter_blocks):
                records.append(record)
                if len(records) >= limit:
                    break
        except Exception as exc:
            errors.append(
                {
                    "index": index,
                    "acpt_no": html_file.stem,
                    "error": str(exc),
                }
            )

    return {
        "format": "finiq_parse_preview_v1",
        "mode": requested_mode,
        "source_kind": "input_directory",
        "input_directory": str(input_directory),
        "summary": {
            "records": len(html_files),
            "visible_records": len(records),
            "errors": len(errors),
        },
        "records": [
            _build_preview_record(
                record,
                index=index,
                mode=requested_mode,
                input_directory=input_directory,
            )
            for index, record in enumerate(records, start=1)
        ],
        "errors": errors,
    }


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
    parser: ParseFunction,
    requested_mode: str,
    field: str,
    metadata_index: dict[str, dict[str, Any]],
) -> str | list[Any] | None:
    html_bytes = html_file.read_bytes()
    record = _apply_parse_metadata(
        _record_without_raw_tables(
            _parse_with_metadata_title(
                parser,
                html_bytes,
                html_file=html_file,
                metadata_index=metadata_index,
            )
        ),
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
    filtered_metadata_path, compressed_metadata_path = _parse_metadata_paths(body)
    metadata_index, _ = _load_html_parse_metadata(
        input_directory,
        filtered_metadata_path=filtered_metadata_path,
        compressed_metadata_path=compressed_metadata_path,
    )
    _validate_explicit_kind_disclosed_at_metadata(
        html_files,
        metadata_index,
        filtered_metadata_path,
    )
    worker_count = _filter_candidate_workers(
        body.get("parallel_workers", body.get("workers")), len(html_files)
    )
    candidate_counts: dict[str, int] = {}
    candidate_examples: dict[str, list[dict[str, str]]] = {}
    errors: list[dict[str, Any]] = []
    indexed_files = list(enumerate(html_files, start=1))

    def record_value(value: Any, html_file: Path) -> None:
        values = value if isinstance(value, list) else [value]
        for candidate in values:
            text = str(candidate or "").strip()
            if text:
                candidate_counts[text] = candidate_counts.get(text, 0) + 1
                examples = candidate_examples.setdefault(text, [])
                if len(examples) < 20:
                    examples.append(
                        {
                            "acpt_no": html_file.stem,
                        }
                    )

    def record_error(index: int, html_file: Path, exc: Exception) -> None:
        errors.append(
            {
                "index": index,
                "acpt_no": html_file.stem,
                "error": str(exc),
            }
        )

    if worker_count > 1:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            completed = bounded_as_completed(
                executor,
                indexed_files,
                lambda item: executor.submit(
                    _extract_filter_candidate_from_file,
                    html_file=item[1],
                    parser=parser,
                    requested_mode=requested_mode,
                    field=field,
                    metadata_index=metadata_index,
                ),
                max_pending=worker_count * 2,
            )
            for future, (index, html_file) in completed:
                try:
                    record_value(future.result(), html_file)
                except Exception as exc:
                    record_error(index, html_file, exc)
    else:
        for index, html_file in indexed_files:
            try:
                record_value(
                    _extract_filter_candidate_from_file(
                        html_file=html_file,
                        parser=parser,
                        requested_mode=requested_mode,
                        field=field,
                        metadata_index=metadata_index,
                    ),
                    html_file,
                )
            except Exception as exc:
                record_error(index, html_file, exc)

    candidates = [
        {"value": value, "count": count, "examples": candidate_examples.get(value, [])}
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
