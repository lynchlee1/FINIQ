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
    payload = _load_parse_payload(output_path)
    if payload.get("mode") != "bond_issuance":
        msg = "parse result mode must be bond_issuance"
        raise ValueError(msg)
    input_directory_raw = str(payload.get("input_directory") or "").strip()
    if not input_directory_raw:
        msg = "parse result input_directory is required"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()

    limit = _parse_limit(body.get("limit"))
    records = list(payload.get("records") or [])
    total_count = len(records)
    if limit is not None:
        records = records[:limit]

    summary_records: list[dict[str, Any]] = []
    payload_families = payload.get("families")
    all_families = payload_families if isinstance(payload_families, dict) else {}
    families: dict[str, Any] = {}
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            continue
        family_id, current_sequence, member_count = _record_family_info(record)
        if family_id and family_id in all_families and family_id not in families:
            families[family_id] = all_families[family_id]
        summary_records.append(
            {
                "index": index,
                "title": record.get("title") or "",
                "acpt_no": record.get("acpt_no") or "",
                "doc_no": record.get("doc_no") or "",
                "family_id": family_id,
                "current_sequence": current_sequence,
                "family_member_count": member_count,
                "fields": {field: record.get(field) for field in BOND_SUMMARY_FIELDS},
                "source_preview": _load_source_preview(
                    record,
                    mode="bond_issuance",
                    input_directory=input_directory,
                ),
            }
        )

    return {
        "format": "finiq_bond_parse_summary_v1",
        "source_path": str(output_path),
        "input_directory": str(input_directory),
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




__all__ = [name for name in globals() if not name.startswith("__")]
