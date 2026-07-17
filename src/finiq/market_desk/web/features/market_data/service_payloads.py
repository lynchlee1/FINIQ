"""Market-data filter and company-index payload builders."""

from __future__ import annotations

from finiq.market_desk.web.features.disclosure_workflow.layout import (
    resolve_disclosure_workspace,
)
from finiq.market_desk.web.features.market_data.service_sources import *

def filter_disclosures_payload(
    body: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    """Filter the canonical workspace SQLite manifest."""
    if cancel_check is not None and cancel_check():
        raise FilterCancelled("filter cancelled")
    classification_path = str(body.get("classification_path") or "").strip()
    root_directory = str(body.get("root_directory") or "").strip()
    data_root = str(body.get("data_root") or "").strip()
    if classification_path:
        raise ValueError("classification_path is not supported; use data_root")
    if root_directory:
        raise ValueError("root_directory is not supported; use data_root")
    if not data_root:
        raise ValueError("data_root is required")
    sqlite_manifest_path = _resolve_sqlite_manifest_path(
        resolve_disclosure_workspace(data_root).table / "sqlite_manifest.json"
    )
    source_kind = "sqlite_manifest"

    title_expression = str(body.get("title_expression") or "").strip()
    filter_blocks = body.get("filter_blocks")
    title_keywords = _split_keywords(body.get("title_keywords"))
    exclude_title_keywords = _split_keywords(body.get("exclude_title_keywords"))
    title_match_mode = str(body.get("title_match_mode") or "or").strip().casefold()
    if title_match_mode not in {"or", "and"}:
        raise ValueError("title_match_mode must be one of: or, and")
    filter_blocks = _validate_filter_blocks([] if filter_blocks is None else filter_blocks)
    company_keyword = str(body.get("company_keyword") or "").strip().casefold()
    submitter_keyword = str(body.get("submitter_keyword") or "").strip().casefold()
    market = str(body.get("market") or "전체").strip() or "전체"
    start_date = str(body.get("start_date") or "").strip()
    end_date = str(body.get("end_date") or "").strip()
    acpt_numbers = _normalize_acpt_numbers(body.get("acpt_numbers"))
    limit = None
    limit_unlimited = True
    include_external_html_download_acpt_numbers = bool(
        body.get("include_external_html_download_acpt_numbers")
    )
    progress_interval = _progress_interval(body.get("progress_interval"))
    filter_workers = _resolve_filter_workers(body.get("filter_workers"), None)

    sqlite_manifest = _load_sqlite_manifest(sqlite_manifest_path)
    _validate_sqlite_manifest_counts(sqlite_manifest_path, sqlite_manifest)
    records = _iter_sqlite_manifest_disclosure_records(
        sqlite_manifest_path, sqlite_manifest
    )
    total_records = _sqlite_manifest_total_disclosures(sqlite_manifest)
    filtered: list[dict[str, Any]] = []
    external_html_download_acpt_heap: list[tuple[tuple[str, str, str], int, str]] = []
    seen_disclosure_keys: set[tuple[str, str, str, str]] = set()
    matched_count = 0
    duplicate_count = 0
    inspected_count = 0
    for index, record in enumerate(records, start=1):
        if cancel_check is not None and cancel_check():
            raise FilterCancelled("filter cancelled")
        inspected_count = index
        disclosed_date = str(record.get("__filter_disclosed_date") or "")
        acpt_no = str(record.get("__filter_acpt_no") or "")
        if (start_date or end_date) and not disclosed_date:
            raise ValueError("disclosed_at is required when a date filter is used")
        matched = True
        if acpt_numbers and acpt_no not in acpt_numbers:
            matched = False
        if matched and market != "전체" and str(record.get("market") or "") != market:
            matched = False
        if matched and start_date and disclosed_date < start_date:
            matched = False
        if matched and end_date and disclosed_date > end_date:
            matched = False
        if matched and filter_blocks:
            matched = _record_filter_blocks_match(record, filter_blocks)
        elif matched and title_expression:
            matched = _title_expression_matches(record.get("title"), title_expression)
        elif matched:
            title_folded = str(record.get("__filter_title_cf") or "")
            if title_keywords and title_match_mode == "and":
                matched = all(keyword in title_folded for keyword in title_keywords)
            elif title_keywords:
                matched = any(keyword in title_folded for keyword in title_keywords)
        if matched and not title_expression:
            title_folded = str(record.get("__filter_title_cf") or "")
            matched = not any(
                keyword in title_folded for keyword in exclude_title_keywords
            )
        if matched:
            matched = not company_keyword or company_keyword in str(
                record.get("__filter_company_cf") or ""
            )
        if matched:
            matched = not submitter_keyword or submitter_keyword in str(
                record.get("__filter_submitter_cf") or ""
            )
        if matched:
            dedup_key = _disclosure_dedup_key(record)
            if dedup_key in seen_disclosure_keys:
                duplicate_count += 1
                _emit_progress(
                    progress_callback,
                    source_type=source_kind,
                    unit_label="공시",
                    completed=index,
                    total=total_records,
                    records=matched_count,
                    progress_interval=progress_interval,
                )
                continue
            seen_disclosure_keys.add(dedup_key)
            matched_count += 1
            if include_external_html_download_acpt_numbers and acpt_no:
                external_html_download_acpt_heap.append(
                    (_record_sort_key(record), index, acpt_no)
                )
            filtered.append(record)
        _emit_progress(
            progress_callback,
            source_type=source_kind,
            unit_label="공시",
            completed=index,
            total=total_records,
            records=matched_count,
            progress_interval=progress_interval,
        )

    if inspected_count != total_records:
        msg = (
            "SQLite filter did not inspect every manifest disclosure: "
            f"manifest={sqlite_manifest_path}, inspected={inspected_count}, expected={total_records}"
        )
        raise ValueError(msg)

    filtered.sort(key=_record_sort_key, reverse=True)
    public_limited = [_public_disclosure_record(record) for record in filtered]
    payload = {
        "format": "kind_disclosure_filter_v1",
        "source_type": source_kind,
        "source_sqlite_manifest_path": str(sqlite_manifest_path),
        "filters": {
            "filter_blocks": filter_blocks,
            "title_expression": title_expression,
            "title_keywords": title_keywords,
            "exclude_title_keywords": exclude_title_keywords,
            "title_match_mode": title_match_mode,
            "company_keyword": body.get("company_keyword") or "",
            "submitter_keyword": body.get("submitter_keyword") or "",
            "market": market,
            "start_date": start_date,
            "end_date": end_date,
            "acpt_numbers": sorted(acpt_numbers),
            "limit": limit,
            "limit_unlimited": limit_unlimited,
            "return_limit": None,
            "filter_workers": filter_workers,
        },
        "summary": {
            "source_disclosures": total_records,
            "source_body_files": 0,
            "matched_disclosures": matched_count,
            "returned_disclosures": len(public_limited),
            "duplicate_disclosures": duplicate_count,
            "unique_acpt_numbers": len(
                {
                    str(record.get("acpt_no") or "")
                    for record in public_limited
                    if record.get("acpt_no")
                }
            ),
        },
        "unique_titles": _unique_disclosure_titles(public_limited),
        "disclosures": public_limited,
    }
    if include_external_html_download_acpt_numbers:
        payload["external_html_download_acpt_numbers"] = [
            item[2] for item in sorted(external_html_download_acpt_heap, reverse=True)
        ]
    return payload


def load_company_index_payload(
    classification_path: str | Path,
    *,
    keyword: str = "",
    market: str = "전체",
) -> dict[str, Any]:
    payload = load_company_classification_index_file(classification_path)
    companies = list(payload.get("companies") or [])
    companies = sorted(
        companies,
        key=lambda company: (
            -_company_disclosure_count(company),
            str(company.get("company_name") or ""),
        ),
    )

    normalized_keyword = str(keyword or "").strip().casefold()
    filtered = [
        company
        for company in companies
        if (
            not normalized_keyword
            or normalized_keyword in str(company.get("company_name") or "").casefold()
        )
        and (market == "전체" or str(company.get("market") or "") == market)
    ]
    markets = ["전체"] + sorted(
        {
            str(company.get("market") or "").strip()
            for company in companies
            if str(company.get("market") or "").strip()
        }
    )
    summary = dict(payload.get("summary") or {})
    summary_company_count = summary.get("companies")
    return {
        "summary": {
            "companies": int(len(companies) if summary_company_count is None else summary_company_count),
            "disclosures": int(summary.get("disclosures") or 0),
            "filtered_companies": len(filtered),
        },
        "markets": markets,
        "companies": [_serialize_company(company) for company in filtered],
    }




__all__ = [name for name in globals() if not name.startswith("__")]
