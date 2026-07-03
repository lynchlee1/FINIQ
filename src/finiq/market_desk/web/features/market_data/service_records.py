"""Disclosure record loading and preparation helpers."""

from __future__ import annotations

from finiq.market_desk.web.features.market_data.service_common import *

class FilterCancelled(Exception):
    """Raised when a streaming filter request is abandoned by the client."""


def _resolve_filter_workers(value: object, item_count: int) -> int:
    if item_count <= 1:
        return max(1, item_count)
    try:
        requested = int(value or 0)
    except (TypeError, ValueError):
        requested = 0
    if requested < 1:
        requested = min(8, os.cpu_count() or 1)
    return max(1, min(requested, item_count, 32))


def _progress_interval(value: object) -> int:
    try:
        return min(max(int(value or 100), 1), 10000)
    except (TypeError, ValueError):
        return 100


def _emit_progress(
    progress_callback: ProgressCallback | None,
    *,
    source_type: str,
    unit_label: str,
    completed: int,
    total: int,
    records: int,
    force: bool = False,
    progress_interval: int = 100,
) -> None:
    if progress_callback is None or total <= 0:
        return
    if not force and completed % progress_interval != 0 and completed != total:
        return
    progress_callback(
        {
            "source_type": source_type,
            "unit_label": unit_label,
            "completed": completed,
            "total": total,
            "records": records,
        }
    )


def _iter_disclosure_records(
    classification_payload: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
    progress_interval: int = 100,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    companies = list(classification_payload.get("companies") or [])
    for index, company in enumerate(companies, start=1):
        company_key = _company_key(company)
        company_name = company.get("company_name")
        company_id = company.get("company_id")
        market = company.get("market")
        for disclosure in list(company.get("disclosures") or []):
            record = dict(disclosure)
            record.update(
                {
                    "company_key": company_key,
                    "company_name": company_name,
                    "company_id": company_id,
                    "market": market,
                }
            )
            records.append(record)
        _emit_progress(
            progress_callback,
            source_type="classification",
            unit_label="JSON 항목",
            completed=index,
            total=len(companies),
            records=len(records),
            progress_interval=progress_interval,
        )
    return records


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str, str]:
    cached_key = record.get("__filter_sort_key")
    if isinstance(cached_key, tuple) and len(cached_key) == 3:
        return cached_key
    return (
        str(record.get("disclosed_at") or ""),
        str(record.get("company_name") or ""),
        str(record.get("title") or ""),
    )


def _disclosure_dedup_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(record.get("acpt_no") or record.get("acptno") or "").strip(),
        str(record.get("company_id") or "").strip(),
        str(record.get("disclosed_at") or "").strip(),
        str(record.get("title") or "").strip(),
    )


def _prepare_filter_record(record: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(record)
    disclosed_at = str(prepared.get("disclosed_at") or "")
    title = str(prepared.get("title") or "")
    company_name = str(prepared.get("company_name") or "")
    submitter = str(prepared.get("submitter") or "")
    prepared["__filter_disclosed_date"] = disclosed_at.strip().split(" ", 1)[0]
    prepared["__filter_acpt_no"] = str(
        prepared.get("acpt_no") or prepared.get("acptno") or ""
    ).strip()
    prepared["__filter_title_cf"] = title.casefold()
    prepared["__filter_company_cf"] = company_name.casefold()
    prepared["__filter_submitter_cf"] = submitter.casefold()
    prepared["__filter_sort_key"] = (disclosed_at, company_name, title)
    return prepared


def _public_disclosure_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if not str(key).startswith("__filter_")
    }


def _unique_disclosure_titles(records: list[dict[str, Any]]) -> list[str]:
    titles: list[str] = []
    seen_titles: set[str] = set()
    for record in records:
        title = _clean_search_text(str(record.get("title") or "")).strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        titles.append(title)
    return titles


def _classification_cache_key(classification_path: str | Path) -> tuple[str, int, int]:
    target = Path(classification_path).expanduser().resolve()
    stat_result = target.stat()
    return (str(target), stat_result.st_mtime_ns, stat_result.st_size)


@lru_cache(maxsize=8)
def _load_classification_records_cached(
    classification_path: str,
    modified_ns: int,
    file_size: int,
) -> tuple[tuple[dict[str, Any], ...], int]:
    payload = load_company_classification_file(classification_path)
    records = [
        _prepare_filter_record(record) for record in _iter_disclosure_records(payload)
    ]
    return (tuple(records), len(list(payload.get("companies") or [])))


def _load_classification_disclosure_records(
    classification_path: str | Path,
    *,
    progress_callback: ProgressCallback | None = None,
) -> list[dict[str, Any]]:
    cache_key = _classification_cache_key(classification_path)
    cached_records, company_count = _load_classification_records_cached(*cache_key)
    records = list(cached_records)
    _emit_progress(
        progress_callback,
        source_type="classification",
        unit_label="JSON 항목",
        completed=company_count,
        total=company_count,
        records=len(records),
        force=True,
    )
    return records




__all__ = [name for name in globals() if not name.startswith("__")]
