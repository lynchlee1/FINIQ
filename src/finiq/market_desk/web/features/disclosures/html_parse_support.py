"""Shared disclosure parse result presentation helpers."""

from __future__ import annotations

from finiq.market_desk.web.features.disclosures.html_parse_common import *

def _record_family_info(record: dict[str, Any]) -> tuple[str, int | None, int | None]:
    families = record.get("correction_families")
    if not isinstance(families, dict) or not families:
        return ("", None, None)
    family_id = str(next(iter(families)))
    family = families.get(family_id)
    if not isinstance(family, dict):
        return (family_id, None, None)
    current_sequence_raw = family.get("current_sequence")
    current_sequence = (
        current_sequence_raw if isinstance(current_sequence_raw, int) else None
    )
    members = family.get("members")
    member_count = len(members) if isinstance(members, list) else None
    return (family_id, current_sequence, member_count)


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
                "chapter_title": table.get("chapter_title") or "",
                "rows": visible_rows,
                "omitted_rows": max(len(rows) - len(visible_rows), 0),
            }
        )
    return tables, max(total_rows - included_rows, 0)


def _load_source_preview(record: dict[str, Any], *, mode: str) -> dict[str, Any]:
    source_file = str(record.get("source_file") or "").strip()
    if not source_file:
        return {
            "available": False,
            "source_file": "",
            "error": "source_file is missing",
        }

    path = Path(source_file).expanduser().resolve()
    if not path.is_file():
        return {
            "available": False,
            "source_file": str(path),
            "error": "source_file does not exist",
        }

    try:
        source_bytes = path.read_bytes()
        source_record = build_base_record(source_bytes, file_path=path, mode=mode)

        tables, omitted_rows = _compact_source_tables(
            source_record.get("raw_tables") or []
        )
        return {
            "available": True,
            "source_file": str(path),
            "title": source_record.get("title") or record.get("title") or "",
            "tables": tables,
            "omitted_rows": omitted_rows,
        }
    except Exception as exc:
        return {
            "available": False,
            "source_file": str(path),
            "error": str(exc),
        }


def _build_preview_record(
    record: dict[str, Any], *, index: int, mode: str
) -> dict[str, Any]:
    compact_record = _compact_record(record)
    return {
        "index": index,
        "title": record.get("title") or "",
        "acpt_no": record.get("acpt_no") or "",
        "rcept_no": record.get("rcept_no") or "",
        "source_file": record.get("source_file") or "",
        "source_preview": _load_source_preview(record, mode=mode),
        "parsed_result": compact_record,
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
        "source_file": record.get("source_file") or "",
        "acpt_no": record.get("acpt_no") or "",
        "rcept_no": record.get("rcept_no") or "",
        "family_id": family_id,
        "current_sequence": current_sequence,
        "family_member_count": member_count,
    }


def _sequence_sort_key(record: dict[str, Any]) -> tuple[int, str]:
    _, current_sequence, _ = _record_family_info(record)
    sequence = current_sequence if current_sequence is not None else 0
    return (sequence, str(record.get("rcept_no") or record.get("acpt_no") or ""))


def _get_all_value_fields(records: list[dict[str, Any]]) -> list[str]:
    """Dynamically discover all fields present in the records, excluding metadata."""
    all_fields = set()
    for record in records:
        all_fields.update(record.keys())

    # Filter out metadata and sort for consistency
    value_fields = sorted([f for f in all_fields if f not in METADATA_FIELDS])
    return value_fields


def _build_record_change(
    *,
    mode: str,
    before_record: dict[str, Any],
    after_record: dict[str, Any],
    before_index: int,
    after_index: int,
    fields: list[str] | None = None,
) -> dict[str, Any] | None:
    # Use provided fields or fallback to mode-specific or discover dynamic
    if not fields:
        fields = list(
            CHANGE_LOG_FIELDS.get(
                mode, _get_all_value_fields([before_record, after_record])
            )
        )

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
    if num_threshold is not None:
        n1 = _parse_numeric_value(before)
        n2 = _parse_numeric_value(after)
        import math

        if not math.isnan(n1) and not math.isnan(n2) and n2 != 0:
            diff_percent = abs((n2 - n1) / n2) * 100
            if diff_percent <= num_threshold:
                return False

    return True


def _get_cached_payload(path: Path) -> dict[str, Any]:
    path = path.resolve()
    path_str = str(path)
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return {}

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
