from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from finiq.market_desk.web.features.disclosures.filter_presets import (
    _canonical_result_sha256,
)
from finiq.market_desk.web.features.market_data.service_common import (
    _clean_search_text,
)


def canonical_filter_result(
    payload: dict[str, Any],
    *,
    mode: str,
    parent_mode: str | None = None,
    parent_result_fingerprint: str | None = None,
) -> dict[str, Any]:
    disclosures: list[dict[str, Any]] = []
    for item in payload.get("disclosures") or []:
        disclosure = dict(item)
        acpt_no = str(disclosure.get("acpt_no") or "").strip()
        company_name = disclosure.get("company_name")
        company_id = disclosure.get("company_id")
        company_key = disclosure.get("company_key")
        if company_key is None and (company_name is not None or company_id is not None):
            company_key = f"fixture:{acpt_no}"
        if company_key is None:
            company_name = None
            company_id = None
        disclosure.update(
            {
                "acpt_no": acpt_no,
                "title": str(disclosure.get("title") or ""),
                "disclosed_at": str(
                    disclosure.get("disclosed_at") or "2025-01-01"
                ),
                "company_key": company_key,
                "company_name": company_name,
                "company_id": company_id,
                "company_cell_text": disclosure.get("company_cell_text")
                if "company_cell_text" in disclosure
                else company_name or "",
            }
        )
        disclosures.append(disclosure)

    acpt_numbers = [str(item["acpt_no"]) for item in disclosures]
    unique_titles = list(
        dict.fromkeys(
            title
            for title in (
                _clean_search_text(str(item.get("title") or "")).strip()
                for item in disclosures
            )
            if title
        )
    )
    count = len(disclosures)
    result = {
        "format": "kind_disclosure_filter_v1",
        "source_type": "sqlite_manifest",
        "source_fingerprint": hashlib.sha256(
            json.dumps(acpt_numbers, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "mode": mode,
        "filters": {"filter_blocks": []},
        "summary": {
            "source_disclosures": count,
            "source_body_files": 0,
            "source_offset": 0,
            "target_disclosures": count,
            "inspected_disclosures": count,
            "matched_disclosures": count,
            "returned_disclosures": count,
            "duplicate_disclosures": 0,
            "unique_acpt_numbers": count,
        },
        "integrity": {
            "complete": True,
            "passed": True,
            "search_target_disclosures": count,
            "search_result_disclosures": count,
            "inspected_disclosures": count,
        },
        "unique_titles": unique_titles,
        "external_html_download_acpt_numbers": acpt_numbers,
        "disclosures": disclosures,
    }
    if parent_mode is not None:
        result["parent_mode"] = parent_mode
        result["parent_result_fingerprint"] = parent_result_fingerprint
    return result


def publish_completed_filter_result(
    data_root: Path,
    *,
    mode: str,
    payload: dict[str, Any],
    parent_mode: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    parent_fingerprint = None
    if parent_mode is not None:
        parent_payload = json.loads(
            (data_root / "03-filter" / parent_mode / "filtered.json").read_text(
                encoding="utf-8"
            )
        )
        parent_fingerprint = _canonical_result_sha256(parent_payload)
    result = canonical_filter_result(
        payload,
        mode=mode,
        parent_mode=parent_mode,
        parent_result_fingerprint=parent_fingerprint,
    )
    mode_directory = (
        data_root / "03-filter" / mode
        if parent_mode is None
        else data_root / "03-filter" / parent_mode / "subfilters" / mode
    )
    mode_directory.mkdir(parents=True, exist_ok=True)
    filtered_path = mode_directory / "filtered.json"
    filtered_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    workflow = {
        "format": "finiq_disclosure_filter_workflow",
        "mode": mode,
        "status": "completed",
        "steps": {
            "condition_input": {"status": "completed", "filter_blocks": []},
            "database_query": {"status": "completed"},
            "record": {"status": "completed"},
        },
        "result_file": "filtered.json",
        "result_fingerprint": _canonical_result_sha256(result),
        "result_summary": result["summary"],
    }
    if parent_mode is not None:
        workflow["parent_mode"] = parent_mode
        workflow["parent_result_fingerprint"] = parent_fingerprint
    (mode_directory / "filter.json").write_text(
        json.dumps(workflow, ensure_ascii=False), encoding="utf-8"
    )
    return filtered_path, result
