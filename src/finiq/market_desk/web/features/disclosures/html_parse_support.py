"""Shared disclosure parse result presentation helpers."""

from __future__ import annotations

import re

from finiq.market_desk.web.features.disclosures.html_common import (
    resolve_disclosure_html_file,
)
from finiq.market_desk.web.features.disclosures.html_parse_common import *

def _record_family_info(record: dict[str, Any]) -> tuple[str, int | None, int | None]:
    family_id = str(record.get("family_id") or "")
    current_sequence = record.get("current_sequence")
    member_count = record.get("family_member_count")
    return (
        family_id,
        current_sequence if isinstance(current_sequence, int) else None,
        member_count if isinstance(member_count, int) else None,
    )


def _compact_source_tables(
    raw_tables: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    tables: list[dict[str, Any]] = []
    included_rows = 0
    total_rows = 0
    for table in raw_tables:
        rows = table.get("logical_rows") or []
        if not isinstance(rows, list):
            continue
        total_rows += len(rows)
        if (
            len(tables) >= SOURCE_PREVIEW_MAX_TABLES
            or included_rows >= SOURCE_PREVIEW_MAX_ROWS
        ):
            continue
        remaining_rows = SOURCE_PREVIEW_MAX_ROWS - included_rows
        visible_rows = rows[:remaining_rows]
        included_rows += len(visible_rows)
        tables.append(
            {
                "index": table.get("index"),
                "rows": visible_rows,
                "omitted_rows": max(len(rows) - len(visible_rows), 0),
            }
        )
    return tables, max(total_rows - included_rows, 0)


def _load_source_preview(
    record: dict[str, Any],
    *,
    mode: str,
    input_directory: Path,
) -> dict[str, Any]:
    path = resolve_disclosure_html_file(
        input_directory,
        str(record.get("acpt_no") or ""),
    )
    if path is None:
        return {
            "available": False,
            "error": "source HTML does not exist",
        }

    try:
        source_bytes = path.read_bytes()
        source_record = build_base_record(source_bytes, file_path=path, mode=mode)

        tables, omitted_rows = _compact_source_tables(
            source_record.get("raw_tables") or []
        )
        return {
            "available": True,
            "title": source_record.get("title") or record.get("title") or "",
            "tables": tables,
            "omitted_rows": omitted_rows,
        }
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
        }


def _build_preview_record(
    record: dict[str, Any],
    *,
    index: int,
    mode: str,
    input_directory: Path,
) -> dict[str, Any]:
    parsed_result = dict(record)
    return {
        "index": index,
        "title": record.get("title") or "",
        "acpt_no": record.get("acpt_no") or "",
        "source_preview": _load_source_preview(
            record,
            mode=mode,
            input_directory=input_directory,
        ),
        "parsed_result": parsed_result,
    }


def _json_stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _field_changed(before: Any, after: Any) -> bool:
    return _json_stable(before) != _json_stable(after)


def _record_reference(record: dict[str, Any], *, index: int) -> dict[str, Any]:
    family_id, current_sequence, member_count = _record_family_info(record)
    return {
        "index": index,
        "title": record.get("title") or "",
        "acpt_no": record.get("acpt_no") or "",
        "doc_no": record.get("doc_no") or "",
        "family_id": family_id,
        "current_sequence": current_sequence,
        "family_member_count": member_count,
    }


def _sequence_sort_key(record: dict[str, Any]) -> tuple[int, str]:
    _, current_sequence, _ = _record_family_info(record)
    sequence = current_sequence if current_sequence is not None else 0
    return (sequence, str(record.get("acpt_no") or ""))


def _build_record_change(
    *,
    mode: str,
    before_record: dict[str, Any],
    after_record: dict[str, Any],
    before_index: int,
    after_index: int,
    fields: list[str] | None = None,
) -> dict[str, Any] | None:
    if not fields:
        fields = list(CHANGE_LOG_COMPARISON_FIELDS.get(mode, ()))

    changes: list[dict[str, Any]] = []
    major_fields = MAJOR_CHANGE_FIELDS.get(mode, set())

    for field in fields:
        before_value = before_record.get(field)
        after_value = after_record.get(field)

        if not _field_changed(before_value, after_value):
            continue

        changes.append(
            {
                "field": field,
                "impact": "major" if field in major_fields else "minor",
                "before": before_value,
                "after": after_value,
            }
        )

    if not changes:
        return None

    severity = "major" if any(c["impact"] == "major" for c in changes) else "minor"
    return {
        "severity": severity,
        "changed_fields": len(changes),
        "major_fields": sum(1 for change in changes if change["impact"] == "major"),
        "minor_fields": sum(1 for change in changes if change["impact"] == "minor"),
        "before": _record_reference(before_record, index=before_index),
        "after": _record_reference(after_record, index=after_index),
        "changes": changes,
    }


def _parse_korean_date(date_str: Any) -> float:
    if not date_str or not isinstance(date_str, str):
        return float("nan")
    match = re.search(r"(\d{4})\s*[년.-]\s*(\d{1,2})\s*[월.-]\s*(\d{1,2})", date_str)
    if match:
        from datetime import datetime

        try:
            return (
                datetime(
                    int(match.group(1)), int(match.group(2)), int(match.group(3))
                ).timestamp()
                * 1000
            )
        except ValueError:
            return float("nan")
    clean = re.sub(r"[^\d]", "", date_str)
    if len(clean) == 8:
        from datetime import datetime

        try:
            return (
                datetime(int(clean[:4]), int(clean[4:6]), int(clean[6:8])).timestamp()
                * 1000
            )
        except ValueError:
            return float("nan")
    return float("nan")


def _parse_numeric_value(val: Any) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if not isinstance(val, str):
        return float("nan")
    match = re.search(r"-?\d+\.?\d*", val.replace(",", ""))
    return float(match.group(0)) if match else float("nan")


def _numeric_signature(value: Any) -> tuple[Any, list[float]]:
    """Return a stable nonnumeric shape and ordered numeric leaves."""
    import math

    if isinstance(value, bool):
        return ("literal", value), []
    if isinstance(value, (int, float, str)):
        parsed = _parse_numeric_value(value)
        if not math.isnan(parsed):
            return ("number",), [parsed]
        return ("literal", value), []
    if isinstance(value, list):
        shapes: list[Any] = []
        numbers: list[float] = []
        for item in value:
            shape, item_numbers = _numeric_signature(item)
            shapes.append(shape)
            numbers.extend(item_numbers)
        return ("list", tuple(shapes)), numbers
    if isinstance(value, dict):
        shapes = []
        numbers = []
        for key in sorted(value):
            shape, item_numbers = _numeric_signature(value[key])
            shapes.append((key, shape))
            numbers.extend(item_numbers)
        return ("dict", tuple(shapes)), numbers
    return ("literal", _json_stable(value)), []


def _numeric_change_within_threshold(
    before: Any, after: Any, threshold: float
) -> bool:
    before_shape, before_values = _numeric_signature(before)
    after_shape, after_values = _numeric_signature(after)
    if (
        before_shape != after_shape
        or not before_values
        or len(before_values) != len(after_values)
    ):
        return False
    for before_value, after_value in zip(before_values, after_values):
        if after_value == 0:
            if before_value != after_value:
                return False
            continue
        difference = abs((after_value - before_value) / after_value) * 100
        if difference > threshold:
            return False
    return True


def _is_major_change(
    field: str,
    before: Any,
    after: Any,
    *,
    date_thresholds: dict[str, float],
    numeric_thresholds: dict[str, float],
) -> bool:
    if _json_stable(before) == _json_stable(after):
        return False

    if field == "회차":
        return False

    date_threshold = date_thresholds.get(field)
    if date_threshold is not None:
        d1 = _parse_korean_date(before)
        d2 = _parse_korean_date(after)
        import math

        if not math.isnan(d1) and not math.isnan(d2):
            if abs(d1 - d2) <= date_threshold * 24 * 3600 * 1000:
                return False

    num_threshold = numeric_thresholds.get(field)
    if num_threshold is not None and _numeric_change_within_threshold(
        before, after, num_threshold
    ):
        return False

    return True


def _get_cached_payload(path: Path) -> dict[str, Any]:
    path = path.resolve()
    path_str = str(path)
    mtime = path.stat().st_mtime

    with _CACHE_LOCK:
        cached = _PARSE_CACHE.get(path_str)
        if cached and cached["mtime"] == mtime:
            return cached["payload"]

    payload = _load_parse_payload(path)

    with _CACHE_LOCK:
        if len(_PARSE_CACHE) > 10:
            _PARSE_CACHE.clear()
        _PARSE_CACHE[path_str] = {"mtime": mtime, "payload": payload}

    return payload




__all__ = [name for name in globals() if not name.startswith("__")]
