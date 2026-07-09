"""Disclosure parse summary payload helpers."""

from __future__ import annotations

from finiq.market_desk.web.features.disclosures.html_parse_support import *

def build_bond_parse_summary_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Load a bond_issuance parse result JSON and return UI-ready summary rows."""
    output_path_raw = str(
        body.get("output_path") or body.get("parse_result_path") or ""
    ).strip()
    if not output_path_raw:
        msg = "output_path is required"
        raise ValueError(msg)
    output_path = _resolve_parse_result_path(
        Path(output_path_raw).expanduser().resolve(), "bond_issuance"
    )
    source_directory_raw = str(
        body.get("source_directory") or body.get("input_directory") or ""
    ).strip()
    source_directory = (
        Path(source_directory_raw).expanduser().resolve()
        if source_directory_raw
        else None
    )
    payload = _load_parse_payload(output_path)
    if payload.get("mode") != "bond_issuance":
        msg = "parse result mode must be bond_issuance"
        raise ValueError(msg)

    limit = _parse_limit(body.get("limit"))
    records = [
        _compact_record(record) if isinstance(record, dict) else record
        for record in list(payload.get("records") or [])
    ]
    total_count = len(records)
    if limit is not None:
        records = records[:limit]

    summary_records: list[dict[str, Any]] = []
    families: dict[str, Any] = {}
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            continue
        family_id, current_sequence, member_count = _record_family_info(record)
        for family_key, family in (record.get("correction_families") or {}).items():
            if str(family_key) and str(family_key) not in families:
                families[str(family_key)] = family
        summary_records.append(
            {
                "index": index,
                "title": record.get("title") or "",
                "source_file": _source_file_for_record(record, source_directory),
                "acpt_no": record.get("acpt_no") or "",
                "family_id": family_id,
                "current_sequence": current_sequence,
                "family_member_count": member_count,
                "fields": {field: record.get(field) for field in BOND_SUMMARY_FIELDS},
                "source_preview": _load_source_preview(
                    _record_with_source_file(record, source_directory),
                    mode="bond_issuance",
                ),
            }
        )

    return {
        "format": "finiq_bond_parse_summary_v1",
        "source_path": str(output_path),
        "summary": {
            "records": total_count,
            "visible_records": len(summary_records),
            "families": len(families),
            "correction_records": sum(
                1
                for record in summary_records
                if (record.get("current_sequence") or 0) > 0
            ),
            "latest_records": sum(
                1
                for record in summary_records
                if record.get("family_member_count") is not None
                and record.get("current_sequence")
                == record.get("family_member_count") - 1
            ),
        },
        "families": families,
        "records": summary_records,
    }


def _record_with_source_file(
    record: dict[str, Any], source_directory: Path | None
) -> dict[str, Any]:
    if record.get("source_file"):
        return record
    source_file = _source_file_for_record(record, source_directory)
    if not source_file:
        return record
    updated_record = dict(record)
    updated_record["source_file"] = source_file
    return updated_record


def _source_file_for_record(
    record: dict[str, Any], source_directory: Path | None
) -> str:
    source_file = str(record.get("source_file") or "").strip()
    if source_file:
        return source_file
    if source_directory is None or not source_directory.is_dir():
        return ""
    acpt_no = str(record.get("acpt_no") or "").strip()
    if not acpt_no:
        return ""
    exact_path = source_directory / f"{acpt_no}.html"
    if exact_path.is_file():
        return str(exact_path.resolve())
    for path in sorted(source_directory.rglob(f"{acpt_no}*.html")):
        if path.is_file() and path.stem.split("_", 1)[0] == acpt_no:
            return str(path.resolve())
    return ""




__all__ = [name for name in globals() if not name.startswith("__")]
