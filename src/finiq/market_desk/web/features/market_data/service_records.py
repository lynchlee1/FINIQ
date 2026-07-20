"""Disclosure record loading and preparation helpers."""

from __future__ import annotations

from finiq.concurrency import resolve_worker_count
from finiq.market_desk.web.features.market_data.service_common import *

class FilterCancelled(Exception):
    """Raised when a streaming filter request is abandoned by the client."""

    def __init__(
        self,
        message: str,
        *,
        partial_payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.partial_payload = partial_payload


def _resolve_filter_workers(value: object, item_count: int | None) -> int:
    return resolve_worker_count(
        value,
        item_count=item_count,
        field_name="filter_workers",
    )


def _progress_interval(value: object) -> int:
    if value in (None, ""):
        return 1000
    if isinstance(value, bool):
        raise ValueError("progress_interval must be an integer")
    try:
        interval = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("progress_interval must be an integer") from exc
    if interval < 1 or interval > 10000:
        raise ValueError("progress_interval must be between 1 and 10000")
    return interval


def _emit_progress(
    progress_callback: ProgressCallback | None,
    *,
    source_type: str,
    unit_label: str,
    completed: int,
    total: int,
    records: int,
    force: bool = False,
    progress_interval: int = 1000,
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
    acpt_no = str(record.get("__filter_acpt_no") or "").strip()
    if not acpt_no:
        raise ValueError("acpt_no is required for every disclosure")
    return (acpt_no, "", "", "")


def _prepare_filter_record(record: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(record)
    acpt_no = str(prepared.get("acpt_no") or "").strip()
    if not acpt_no:
        raise ValueError("acpt_no is required for every disclosure")
    disclosed_at = str(prepared.get("disclosed_at") or "")
    title = str(prepared.get("title") or "")
    company_name = str(prepared.get("company_name") or "")
    submitter = str(prepared.get("submitter") or "")
    prepared["__filter_disclosed_date"] = disclosed_at.strip().split(" ", 1)[0]
    prepared["__filter_acpt_no"] = acpt_no
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


__all__ = [name for name in globals() if not name.startswith("__")]
