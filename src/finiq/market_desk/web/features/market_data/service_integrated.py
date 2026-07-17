"""Integrated provider payload wrappers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from finiq.market_desk.analytics.company import (
    build_company_list_xlsx,
    extract_unique_company_list_rows,
)
from finiq.market_desk.analytics.quanti_integrated import (
    convert_quanti_excel_to_parquet,
    merge_quanti_by_item_datasets,
)
from finiq.market_desk.analytics.quanti_market_history import (
    build_quanti_market_history,
    load_quanti_item_registry,
    market_item_from_registry,
    market_value_map_from_registry,
)
from finiq.market_desk.web.features.market_data.service_payloads import load_company_index_payload

ProgressCallback = Callable[[str], None]


def _emit(callback: ProgressCallback | None, message: str) -> None:
    if callback:
        callback(message)


def build_company_list_export(
    classification_path: str | Path,
    *,
    keyword: str = "",
    market: str = "전체",
) -> bytes:
    company_payload = load_company_index_payload(
        classification_path,
        keyword=keyword,
        market=market,
    )
    rows = extract_unique_company_list_rows(company_payload["companies"])
    return build_company_list_xlsx(rows)


def run_integrated_convert_payload(
    payload: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    return convert_quanti_excel_to_parquet(
        payload.get("source_directory", ""),
        payload.get("output_directory", ""),
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )


def run_integrated_merge_payload(
    payload: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    input_dirs = payload.get("input_directories")
    if not isinstance(input_dirs, list) or not input_dirs:
        raise ValueError("input_directories must be a non-empty array")
    return merge_quanti_by_item_datasets(
        input_dirs,
        payload.get("output_directory", ""),
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )


def run_integrated_market_history_payload(
    payload: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    quanti_dir = str(payload.get("quanti_dir") or "").strip()
    output_path = str(payload.get("output_path") or "").strip()
    item_registry_path = str(payload.get("item_registry_path") or "").strip()

    if not quanti_dir or not output_path or not item_registry_path:
        msg = "quanti_dir, output_path, and item_registry_path are required"
        raise ValueError(msg)

    _emit(progress_callback, "Loading item registry...")
    registry = load_quanti_item_registry(item_registry_path)
    market_item_code = market_item_from_registry(registry)
    value_map = market_value_map_from_registry(registry, market_item_code)

    _emit(progress_callback, f"Building market history from {market_item_code}...")
    return build_quanti_market_history(
        quanti_dir=quanti_dir,
        market_item_code=market_item_code,
        output_path=output_path,
        value_map=value_map,
        cancel_check=cancel_check,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
