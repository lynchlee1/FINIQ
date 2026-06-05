"""Load adjusted OHLCV + VWAP from Quanti_unified by_item parquet files."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

# item code → field name
_ITEM_MAP: dict[str, str] = {
    "S100310": "open",    # 수정시가
    "S100300": "close",   # 수정주가
    "S100320": "high",    # 수정고가
    "S100330": "low",     # 수정저가
    "S100950": "volume",  # 수정거래량
    "S101200": "amount",  # 거래대금 (VWAP 계산용)
}


def _resolve_quanti_dir(quanti_dir: str | Path) -> Path:
    """Accept either the by_item directory itself or its parent folder."""
    quanti_path = Path(quanti_dir)
    if (quanti_path / "by_item").is_dir():
        return quanti_path / "by_item"
    return quanti_path


def _find_column(schema_names: list[str], stock_code: str) -> str | None:
    """Return the first column name ending with ``_<stock_code>``."""
    suffix = f"_{stock_code}"
    for name in schema_names:
        if name.endswith(suffix):
            return name
    return None


def list_quanti_stock_codes(quanti_dir: str | Path = "resources/database/by_item") -> list[str]:
    """Return all 6-digit stock codes available in the Quanti dataset."""
    quanti_path = _resolve_quanti_dir(quanti_dir)
    probe_code = next(iter(_ITEM_MAP))
    probe_file = quanti_path / f"{probe_code}.parquet"
    if not probe_file.exists():
        return []
    pf = pq.ParquetFile(probe_file)
    names = pf.schema_arrow.names
    codes: list[str] = []
    for name in names:
        if name == "date":
            continue
        parts = name.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 6:
            codes.append(parts[1])
    return sorted(set(codes))


def fetch_quanti_ohlcv(
    stock_code: str,
    *,
    start_date: date,
    end_date: date,
    quanti_dir: str | Path = "resources/database/by_item",
) -> list[dict[str, Any]]:
    """Return adjusted OHLCV + VWAP rows from Quanti parquet files.

    Each returned dict has keys: date, open, high, low, close, volume, vwap.
    ``vwap`` is None when 거래대금 or volume data is unavailable.
    """
    quanti_path = _resolve_quanti_dir(quanti_dir)
    series_map: dict[str, pd.Series] = {}

    for item_code, field in _ITEM_MAP.items():
        fpath = quanti_path / f"{item_code}.parquet"
        if not fpath.exists():
            return []

        pf = pq.ParquetFile(fpath)
        schema_names: list[str] = pf.schema_arrow.names
        col = _find_column(schema_names, stock_code)
        if col is None:
            # Stock not listed in this item — treat as unavailable
            return []

        table = pf.read(columns=["date", col])
        df = table.to_pandas()
        df["date"] = pd.to_datetime(df["date"])
        s = df.set_index("date")[col]
        s.name = field
        series_map[field] = s

    if not series_map:
        return []

    combined = pd.DataFrame(series_map)
    combined = combined.loc[
        (combined.index >= pd.Timestamp(start_date))
        & (combined.index <= pd.Timestamp(end_date))
    ]
    combined = combined.dropna(subset=["open", "close", "high", "low", "volume"])
    combined = combined.sort_index()

    if combined.empty:
        return []

    # VWAP = 거래대금 / 수정거래량
    if "amount" in combined.columns:
        combined["vwap"] = (combined["amount"] / combined["volume"]).round(0)
    else:
        combined["vwap"] = float("nan")

    rows: list[dict[str, Any]] = []
    for ts, row in combined.iterrows():
        vwap_val = row.get("vwap")
        rows.append(
            {
                "date": ts.strftime("%Y-%m-%d"),  # type: ignore[union-attr]
                "open": int(row["open"]),
                "high": int(row["high"]),
                "low": int(row["low"]),
                "close": int(row["close"]),
                "volume": int(row["volume"]),
                "vwap": int(vwap_val) if pd.notna(vwap_val) else None,
            }
        )
    return rows


__all__ = [
    "fetch_quanti_ohlcv",
    "list_quanti_stock_codes",
]
