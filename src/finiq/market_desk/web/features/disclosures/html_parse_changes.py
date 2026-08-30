"""Disclosure parse change-log payload helpers."""

from __future__ import annotations

from finiq.market_desk.web.features.disclosures.html_parse_support import *
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    resolve_disclosure_workspace,
)


def resolve_parse_change_log_output_directory(body: dict[str, Any]) -> Path:
    output_path_raw = str(
        body.get("output_path") or body.get("parse_result_path") or ""
    ).strip()
    if output_path_raw:
        return Path(output_path_raw).expanduser().resolve()

    workspace = resolve_disclosure_workspace(body.get("data_root") or "")
    return workspace.converted_filter_mode(
        body.get("mode"),
        parent_mode=body.get("parent_mode"),
    )

def build_parse_change_log_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Load parse results and return correction-family field changes with generic support."""
    requested_mode = str(body.get("mode") or "").strip()
    output_path = _resolve_parse_result_path(
        resolve_parse_change_log_output_directory(body), requested_mode
    )

    try:
        payload = _get_cached_payload(output_path)
    except Exception as exc:
        # Provide a more user-friendly error if it's a file-not-found issue
        if not output_path.exists():
            msg = f"파싱 결과 파일을 찾을 수 없습니다. 먼저 [HTML 파싱]을 진행해 주세요.\n(예상 경로: {output_path.name})"
            raise ValueError(msg) from exc
        raise

    mode = str(payload.get("mode") or "")
    parser_method = _require_payload_parser_method(payload)
    summary_only = bool(body.get("summary_only"))
    requested_family_id = body.get("family_id")
    changes_only = bool(body.get("changes_only"))

    # Load thresholds from global config
    from finiq.market_desk.web.app import config as app_config

    date_thresholds = {
        **DEFAULT_CHANGE_LOG_DATE_THRESHOLDS,
        **(app_config.change_log_date_thresholds or {}),
    }
    numeric_thresholds = {
        **DEFAULT_CHANGE_LOG_NUMERIC_THRESHOLDS,
        **(app_config.change_log_numeric_thresholds or {}),
    }

    # Get records
    all_records = list(payload.get("records") or [])

    # Identify which records belong to which families
    family_records: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, record in enumerate(all_records, start=1):
        if not isinstance(record, dict):
            continue
        family_id, current_sequence, member_count = _record_family_info(record)
        if (
            not family_id
            or member_count is None
            or member_count < 2
            or current_sequence is None
        ):
            continue
        if requested_family_id and family_id != requested_family_id:
            continue
        family_records.setdefault(family_id, []).append((index, record))

    comparison_fields = list(CHANGE_LOG_COMPARISON_FIELDS.get(parser_method, ()))

    families: list[dict[str, Any]] = []
    # Sort families by family_id descending (latest first) for better responsiveness and early exit
    for family_id, records in sorted(family_records.items(), reverse=True):
        sorted_records = sorted(records, key=lambda item: _sequence_sort_key(item[1]))

        family_changes: list[dict[str, Any]] = []
        for (before_index, before_record), (after_index, after_record) in zip(
            sorted_records, sorted_records[1:]
        ):
            change = _build_record_change(
                parser_method=parser_method,
                before_record=before_record,
                after_record=after_record,
                before_index=before_index,
                after_index=after_index,
                fields=comparison_fields,
            )
            if change is not None:
                family_changes.append(change)

        # Calculate MAJOR changed fields count and names (exclude minor changes based on thresholds)
        changed_field_names = set()
        for change in family_changes:
            for c in change["changes"]:
                f = str(c["field"]).strip()
                # Check if it's a major change based on dynamic thresholds
                if c.get("impact") == "major" and _is_major_change(
                    f,
                    c["before"],
                    c["after"],
                    date_thresholds=date_thresholds,
                    numeric_thresholds=numeric_thresholds,
                ):
                    changed_field_names.add(f)

        total_changed_fields = len(changed_field_names)
        family_severity = (
            "major"
            if total_changed_fields
            else "minor"
            if family_changes
            else "none"
        )

        if changes_only and total_changed_fields == 0:
            continue

        if summary_only and not (requested_family_id == family_id):
            families.append(
                {
                    "family_id": family_id,
                    "record_count": len(sorted_records),
                    "title": sorted_records[-1][1].get("title") or "",
                    "changed_fields": total_changed_fields,
                    "changed_field_names": sorted(list(changed_field_names)),
                    "severity": family_severity,
                    "has_details": False,
                }
            )
        else:
            families.append(
                {
                    "family_id": family_id,
                    "severity": family_severity,
                    "record_count": len(sorted_records),
                    "change_count": len(family_changes),
                    "changed_fields": total_changed_fields,
                    "changed_field_names": sorted(list(changed_field_names)),
                    "records": [
                        _record_reference(record, index=index)
                        for index, record in sorted_records
                    ],
                    "changes": family_changes,
                    "has_details": True,
                }
            )

    visible_families = families
    return {
        "format": "finiq_parse_change_log_v1",
        "mode": mode,
        "source_path": str(output_path),
        "summary": {
            "records": len(all_records),
            "families": len(family_records) if not requested_family_id else "filtered",
            "visible_families": len(visible_families),
            "major_changes": sum(
                1 for family in visible_families if family.get("severity") == "major"
            ),
            "minor_changes": sum(
                1 for family in visible_families if family.get("severity") == "minor"
            ),
        },
        "families": visible_families,
    }




__all__ = [name for name in globals() if not name.startswith("__")]
