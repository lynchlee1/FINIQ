"""Build and query market-history intervals from Quantiwise by_item parquet."""

from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import re
from typing import Any, Callable

import pandas as pd
import pyarrow.parquet as pq

from finiq.market_desk.analytics.quanti import _resolve_quanti_dir

DEFAULT_MARKET_VALUE_MAP: dict[str, str] = {
    "KOSPI": "코스피",
    "유가증권": "코스피",
    "유가증권시장": "코스피",
    "코스피": "코스피",
    "KOSDAQ": "코스닥",
    "코스닥": "코스닥",
    "코스닥시장": "코스닥",
    "KONEX": "코넥스",
    "코넥스": "코넥스",
    "코넥스시장": "코넥스",
}


def load_quanti_item_registry(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load an item registry JSON.

    The registry may be either ``{"S000000": {...}}`` or ``{"items": {"S000000": {...}}}``.
    """
    registry_path = Path(path).expanduser().resolve()
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("items"), dict):
        payload = payload["items"]
    if not isinstance(payload, dict):
        msg = f"item registry must be a JSON object: {registry_path}"
        raise ValueError(msg)
    return {
        str(item_code).strip().upper(): dict(meta)
        for item_code, meta in payload.items()
        if isinstance(meta, dict)
    }


def market_item_from_registry(registry: dict[str, dict[str, Any]]) -> str:
    """Return the only registry item whose kind is ``market``."""
    matches = [
        item_code
        for item_code, meta in registry.items()
        if str(meta.get("kind") or "").strip().casefold() == "market"
    ]
    if len(matches) != 1:
        msg = f"market item must be exactly one, got: {matches}"
        raise ValueError(msg)
    return matches[0]


def market_value_map_from_registry(
    registry: dict[str, dict[str, Any]],
    item_code: str,
) -> dict[str, str]:
    """Return normalized market value mapping for a registry item."""
    meta = registry.get(str(item_code).strip().upper())
    if meta is None:
        msg = f"market item is not present in registry: {item_code}"
        raise ValueError(msg)
    values = meta.get("values")
    if values is None:
        return dict(DEFAULT_MARKET_VALUE_MAP)
    if not isinstance(values, dict):
        msg = f"registry values for {item_code} must be an object"
        raise ValueError(msg)
    return {str(raw).strip(): str(normalized).strip() for raw, normalized in values.items()}


def build_quanti_market_history(
    *,
    quanti_dir: str | Path,
    market_item_code: str,
    output_path: str | Path,
    value_map: dict[str, str] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Collapse a wide Quantiwise market item into interval rows and write parquet."""
    by_item_dir = _resolve_quanti_dir(quanti_dir)
    item_code = str(market_item_code).strip().upper()
    item_path = by_item_dir / f"{item_code}.parquet"
    if not item_path.is_file():
        msg = f"market item parquet does not exist: {item_path}"
        raise ValueError(msg)

    schema_names = pq.ParquetFile(item_path).schema_arrow.names
    if "date" not in schema_names:
        msg = f"market item parquet is missing date column: {item_path}"
        raise ValueError(msg)

    entity_columns = [name for name in schema_names if name != "date" and _stock_code_from_column(name)]
    if not entity_columns:
        msg = f"market item parquet has no stock-code columns: {item_path}"
        raise ValueError(msg)

    market_values = dict(DEFAULT_MARKET_VALUE_MAP)
    if value_map:
        market_values.update({str(raw).strip(): str(value).strip() for raw, value in value_map.items()})

    frame = pd.read_parquet(item_path, columns=["date", *entity_columns])
    frame["date"] = pd.to_datetime(frame["date"]).dt.date

    rows: list[dict[str, Any]] = []
    unknown_values: dict[str, set[str]] = {}
    for column in entity_columns:
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        stock_code = _stock_code_from_column(column)

        if stock_code is None:
            continue
        series = (
            frame[["date", column]]
            .dropna(subset=[column])
            .sort_values("date")
            .drop_duplicates(subset=["date"], keep="last")
        )
        if series.empty:
            continue

        normalized_pairs: list[tuple[date, str]] = []
        for raw_date, raw_value in series.itertuples(index=False, name=None):
            raw_key = str(raw_value).strip()
            market = market_values.get(raw_key)
            if not market:
                unknown_values.setdefault(column, set()).add(raw_key)
                continue
            normalized_pairs.append((raw_date, market))

        if not normalized_pairs:
            continue
        rows.extend(_collapse_market_pairs(stock_code, column, item_code, normalized_pairs))

    if unknown_values:
        examples = [
            f"{column}: {', '.join(sorted(values)[:5])}"
            for column, values in sorted(unknown_values.items())[:10]
        ]
        msg = "market item contains values not present in value_map: " + "; ".join(examples)
        raise ValueError(msg)

    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    history = pd.DataFrame(
        rows,
        columns=["stock_code", "entity_column", "market", "start_date", "end_date", "source_item"],
    )
    if not history.empty:
        history = history.sort_values(["stock_code", "start_date", "end_date", "market"])
    history.to_parquet(output, index=False)

    return {
        "format": "finiq_quanti_market_history_v1",
        "source_item": item_code,
        "source_path": str(item_path),
        "output_path": str(output),
        "stock_count": int(history["stock_code"].nunique()) if not history.empty else 0,
        "interval_count": len(history),
    }


def find_market_at(
    market_history_path: str | Path,
    *,
    stock_code: str,
    target_date: date,
) -> str | None:
    """Return the market interval containing ``target_date`` for ``stock_code``."""
    normalized_stock_code = _normalize_stock_code(stock_code)
    history_path = Path(market_history_path).expanduser().resolve()
    if not history_path.is_file():
        return None
    frame = pd.read_parquet(
        history_path,
        filters=[
            ("stock_code", "=", normalized_stock_code),
            ("start_date", "<=", target_date),
            ("end_date", ">=", target_date),
        ],
        columns=["stock_code", "market", "start_date", "end_date"],
    )
    if frame.empty:
        return None
    frame = frame.sort_values(["start_date", "end_date"])
    return str(frame.iloc[-1]["market"])


def _collapse_market_pairs(
    stock_code: str,
    entity_column: str,
    item_code: str,
    pairs: list[tuple[date, str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start_date, current_market = pairs[0]
    previous_date = start_date

    for observed_date, market in pairs[1:]:
        if market == current_market:
            previous_date = observed_date
            continue
        rows.append(
            {
                "stock_code": stock_code,
                "entity_column": entity_column,
                "market": current_market,
                "start_date": start_date,
                "end_date": observed_date - timedelta(days=1),
                "source_item": item_code,
            }
        )
        start_date = observed_date
        current_market = market
        previous_date = observed_date

    rows.append(
        {
            "stock_code": stock_code,
            "entity_column": entity_column,
            "market": current_market,
            "start_date": start_date,
            "end_date": previous_date,
            "source_item": item_code,
        }
    )
    return rows


def _normalize_stock_code(stock_code: str) -> str:
    digits = re.sub(r"\D+", "", str(stock_code))
    if len(digits) != 6:
        msg = f"stock_code must contain exactly 6 digits: {stock_code!r}"
        raise ValueError(msg)
    return digits


def _stock_code_from_column(column: str) -> str | None:
    normalized = str(column).strip().upper()
    if normalized.startswith("A") and len(normalized) == 7 and normalized[1:].isdigit():
        return normalized[1:]
    if normalized.isdigit() and len(normalized) == 6:
        return normalized
    match = re.search(r"(?:^|_)([0-9]{6})$", normalized)
    return match.group(1) if match else None


__all__ = [
    "DEFAULT_MARKET_VALUE_MAP",
    "build_quanti_market_history",
    "find_market_at",
    "load_quanti_item_registry",
    "market_item_from_registry",
    "market_value_map_from_registry",
]
