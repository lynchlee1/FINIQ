"""Real-data helpers for the Ontology Graph View."""

from __future__ import annotations

from collections import Counter
from datetime import date
import json
import math
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from finiq.config import PROJECT_ROOT
from finiq.market_desk.analytics.chart import (
    aggregate_price_dataframe,
    prepare_disclosure_dataframe,
    prepare_disclosure_points,
    prepare_price_dataframe,
)
from finiq.market_desk.analytics.disclosure_groups import (
    DEFAULT_DISCLOSURE_GROUP_RULES,
    DISCLOSURE_GROUP_OTHER,
    DISCLOSURE_GROUP_OTHER_COLOR,
    classify_disclosure_group,
    disclosure_group_color_map,
    disclosure_group_marker_style,
)

DEFAULT_KIND_MANIFEST_PATH = (
    PROJECT_ROOT
    / "resources"
    / "KIND_DISCTABLE_FULL.sqlite_manifest_shards"
    / "KIND_DISCTABLE_FULL.sqlite_manifest.json"
)
DEFAULT_QUANTIWISE_PARQUET_DIR = PROJECT_ROOT / "resources" / "Quantiwise" / "parquetCalamine"
TABLE_NAME_DEFAULT = "disclosures"
OHLCV_ITEMS = ("open", "high", "low", "close", "volume")
ITEM_FILE_CANDIDATES = {
    "open": ("open",),
    "high": ("high",),
    "low": ("low",),
    "close": ("close",),
    "volume": ("volume", "adjVolume"),
}


def _resolve_path(path: str | Path | None, default: Path) -> Path:
    if path is None or str(path).strip() == "":
        return default
    return Path(path).expanduser().resolve()


def _load_manifest(manifest_path: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    path = _resolve_path(manifest_path, DEFAULT_KIND_MANIFEST_PATH)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != "finiq_disclosure_table_manifest_v1":
        raise ValueError(f"Not a FINIQ disclosure SQLite manifest: {path}")
    return path, payload


def _shard_path(manifest_path: Path, shard: dict[str, Any]) -> Path:
    raw_path = str(shard.get("path") or "").strip()
    if raw_path:
        path = Path(raw_path)
        if path.is_absolute() and path.exists():
            return path
    relative_path = str(shard.get("relative_path") or "").strip()
    if relative_path:
        return (manifest_path.parent / relative_path).resolve()
    year = str(shard.get("year") or "").strip()
    return (manifest_path.parent / f"{year}.sqlite").resolve()


def _iter_shards(
    manifest_path: Path,
    manifest: dict[str, Any],
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[tuple[str, Path]]:
    start_year = start_date.year if start_date else None
    end_year = end_date.year if end_date else None
    shards: list[tuple[str, Path]] = []
    for shard in list(manifest.get("shards") or []):
        year_text = str(shard.get("year") or "").strip()
        if year_text.isdigit():
            year = int(year_text)
            if start_year is not None and year < start_year:
                continue
            if end_year is not None and year > end_year:
                continue
        shards.append((year_text, _shard_path(manifest_path, shard)))
    return sorted(shards, key=lambda item: item[0])


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _stock_column(company_id: str) -> str:
    raw = str(company_id or "").strip().upper()
    if raw.startswith("A"):
        return raw
    digits = "".join(char for char in raw if char.isdigit())
    return f"A{digits.zfill(6)}"


def _kind_company_id(company_id: str) -> str:
    digits = "".join(char for char in str(company_id or "") if char.isdigit())
    return digits.zfill(6) if digits else ""


def _display_stock_code(company_id: str) -> str:
    digits = "".join(char for char in str(company_id or "") if char.isdigit())
    return f"A{digits.zfill(6)}" if digits else ""


def _find_item_file(quanti_dir: Path, item: str) -> Path | None:
    for prefix in ITEM_FILE_CANDIDATES.get(item, (item,)):
        matches = sorted(quanti_dir.glob(f"{prefix}_*.parquet"))
        if matches:
            return matches[0]
    return None


def _available_item_files(quanti_dir: Path) -> dict[str, Path]:
    return {
        item: path
        for item in OHLCV_ITEMS
        if (path := _find_item_file(quanti_dir, item)) is not None
    }


def _quanti_mapping_codes(quanti_dir: Path) -> set[str]:
    mapping_path = quanti_dir / "code_name_mapping.parquet"
    if not mapping_path.exists():
        return set()
    frame = pd.read_parquet(mapping_path, columns=["code"])
    return {str(code).strip().upper() for code in frame["code"].dropna().tolist()}


def _has_price_data(quanti_codes: set[str], company_id: str) -> bool:
    return _stock_column(company_id) in quanti_codes


def _parse_date(value: str | date | None, fallback: date) -> date:
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return fallback
    return date.fromisoformat(text)


def build_ontology_status(
    *,
    manifest_path: str | Path | None = None,
    quanti_dir: str | Path | None = None,
) -> dict[str, Any]:
    messages: list[str] = []
    resolved_manifest = _resolve_path(manifest_path, DEFAULT_KIND_MANIFEST_PATH)
    resolved_quanti = _resolve_path(quanti_dir, DEFAULT_QUANTIWISE_PARQUET_DIR)
    manifest: dict[str, Any] = {}
    shard_years: list[str] = []
    if resolved_manifest.exists():
        _, manifest = _load_manifest(resolved_manifest)
        shard_years = [
            str(shard.get("year") or "")
            for shard in list(manifest.get("shards") or [])
            if str(shard.get("year") or "").strip()
        ]
    else:
        messages.append(f"KIND SQLite manifest not found: {resolved_manifest}")

    available_items: list[str] = []
    mapped_companies = 0
    if resolved_quanti.exists():
        available_items = sorted(_available_item_files(resolved_quanti).keys())
        mapped_companies = len(_quanti_mapping_codes(resolved_quanti))
    else:
        messages.append(f"Quantiwise Parquet directory not found: {resolved_quanti}")

    return {
        "kind": {
            "manifest_path": str(resolved_manifest),
            "summary": dict(manifest.get("summary") or {}),
            "shard_years": shard_years,
        },
        "quantiwise": {
            "directory": str(resolved_quanti),
            "available_items": available_items,
            "mapped_companies": mapped_companies,
        },
        "messages": messages,
    }


def search_ontology_companies(
    *,
    manifest_path: str | Path | None = None,
    quanti_dir: str | Path | None = None,
    keyword: str = "",
    market: str = "전체",
    limit: int = 30,
) -> dict[str, Any]:
    resolved_manifest, manifest = _load_manifest(manifest_path)
    resolved_quanti = _resolve_path(quanti_dir, DEFAULT_QUANTIWISE_PARQUET_DIR)
    quanti_codes = _quanti_mapping_codes(resolved_quanti)
    table_name = str(manifest.get("table_name") or TABLE_NAME_DEFAULT)
    normalized_keyword = str(keyword or "").strip()
    normalized_market = str(market or "전체").strip()
    rows: list[dict[str, Any]] = []

    for _, shard_path in _iter_shards(resolved_manifest, manifest):
        if not shard_path.exists():
            continue
        connection = _connect(shard_path)
        try:
            clauses = ["company_id IS NOT NULL", "company_id != ''"]
            params: list[Any] = []
            if normalized_keyword:
                clauses.append("(company_name LIKE ? OR company_id LIKE ?)")
                pattern = f"%{normalized_keyword}%"
                params.extend([pattern, pattern])
            if normalized_market and normalized_market != "전체":
                clauses.append("market = ?")
                params.append(normalized_market)
            where_clause = " AND ".join(clauses)
            query = f"""
                SELECT
                    company_id,
                    company_name,
                    market,
                    COUNT(*) AS disclosure_count,
                    MIN(disclosed_date) AS first_disclosed_date,
                    MAX(disclosed_date) AS last_disclosed_date
                FROM {table_name}
                WHERE {where_clause}
                GROUP BY company_id, company_name, market
            """
            rows.extend(dict(row) for row in connection.execute(query, params).fetchall())
        finally:
            connection.close()

    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("company_id") or ""),
            str(row.get("company_name") or ""),
            str(row.get("market") or ""),
        )
        current = merged.get(key)
        if current is None:
            merged[key] = dict(row)
            continue
        current["disclosure_count"] = int(current["disclosure_count"]) + int(row["disclosure_count"])
        current["first_disclosed_date"] = min(
            str(current.get("first_disclosed_date") or ""),
            str(row.get("first_disclosed_date") or ""),
        )
        current["last_disclosed_date"] = max(
            str(current.get("last_disclosed_date") or ""),
            str(row.get("last_disclosed_date") or ""),
        )

    companies = [
        {
            "company_id": _display_stock_code(str(row.get("company_id") or "")),
            "stock_code": _display_stock_code(str(row.get("company_id") or "")),
            "company_name": str(row.get("company_name") or ""),
            "market": str(row.get("market") or ""),
            "disclosure_count": int(row.get("disclosure_count") or 0),
            "first_disclosed_date": str(row.get("first_disclosed_date") or ""),
            "last_disclosed_date": str(row.get("last_disclosed_date") or ""),
            "has_price_data": _has_price_data(quanti_codes, str(row.get("company_id") or "")),
        }
        for row in merged.values()
    ]
    companies.sort(key=lambda item: (-item["disclosure_count"], item["company_name"], item["company_id"]))
    return {
        "companies": companies[: max(int(limit or 30), 1)],
        "total": len(companies),
        "keyword": normalized_keyword,
        "market": normalized_market or "전체",
    }


def _load_disclosures(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    company_id: str,
    start_date: date,
    end_date: date,
    title_keyword: str = "",
    market: str = "전체",
) -> list[dict[str, Any]]:
    table_name = str(manifest.get("table_name") or TABLE_NAME_DEFAULT)
    rows: list[dict[str, Any]] = []
    title_keyword = str(title_keyword or "").strip()
    market = str(market or "전체").strip()
    for _, shard_path in _iter_shards(manifest_path, manifest, start_date=start_date, end_date=end_date):
        if not shard_path.exists():
            continue
        connection = _connect(shard_path)
        try:
            clauses = [
                "company_id = ?",
                "disclosed_date >= ?",
                "disclosed_date <= ?",
            ]
            params: list[Any] = [_kind_company_id(company_id), start_date.isoformat(), end_date.isoformat()]
            if title_keyword:
                clauses.append("(title LIKE ? OR title_display LIKE ?)")
                pattern = f"%{title_keyword}%"
                params.extend([pattern, pattern])
            if market and market != "전체":
                clauses.append("market = ?")
                params.append(market)
            query = f"""
                SELECT
                    company_id,
                    company_name,
                    market,
                    disclosed_at,
                    disclosed_date,
                    title,
                    title_display,
                    acpt_no,
                    doc_no,
                    submitter
                FROM {table_name}
                WHERE {" AND ".join(clauses)}
                ORDER BY disclosed_at ASC, acpt_no ASC
            """
            rows.extend(dict(row) for row in connection.execute(query, params).fetchall())
        finally:
            connection.close()
    return rows


def _load_quanti_ohlcv(
    *,
    quanti_dir: Path,
    company_id: str,
    start_date: date,
    end_date: date,
) -> tuple[list[dict[str, Any]], list[str]]:
    item_files = _available_item_files(quanti_dir)
    missing = [item for item in OHLCV_ITEMS if item not in item_files]
    if missing:
        return [], [f"Quantiwise item is missing: {missing[0]}"]

    stock_column = _stock_column(company_id)
    series_map: dict[str, pd.Series] = {}
    for item, path in item_files.items():
        parquet_file = pq.ParquetFile(path)
        if stock_column not in parquet_file.schema_arrow.names:
            return [], [f"Quantiwise column is missing: {stock_column}"]
        table = parquet_file.read(columns=["date", stock_column])
        frame = table.to_pandas()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        series = pd.to_numeric(frame.set_index("date")[stock_column], errors="coerce")
        series.name = item
        series_map[item] = series

    combined = pd.DataFrame(series_map)
    combined = combined.loc[
        (combined.index >= pd.Timestamp(start_date))
        & (combined.index <= pd.Timestamp(end_date))
    ]
    combined = combined.dropna(subset=list(OHLCV_ITEMS)).sort_index()
    rows: list[dict[str, Any]] = []
    for timestamp, row in combined.iterrows():
        rows.append(
            {
                "date": timestamp.strftime("%Y-%m-%d"),
                "open": _json_number(row["open"]),
                "high": _json_number(row["high"]),
                "low": _json_number(row["low"]),
                "close": _json_number(row["close"]),
                "volume": _json_number(row["volume"]),
            }
        )
    return rows, []


def _json_number(value: Any) -> int | float:
    number = float(value)
    if not math.isfinite(number):
        return 0
    if number.is_integer():
        return int(number)
    return number


def _build_candles(price_frame: pd.DataFrame) -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for row in price_frame.to_dict("records"):
        close_value = float(row["close"])
        open_value = float(row["open"])
        candles.append(
            {
                "time": row["trade_day"],
                "open": open_value,
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": close_value,
                "volume": float(row["volume"]),
                "color": "#22ab94" if close_value >= open_value else "#f23645",
            }
        )
    return candles


def _build_markers(disclosure_points: pd.DataFrame) -> list[dict[str, Any]]:
    color_map = disclosure_group_color_map(DEFAULT_DISCLOSURE_GROUP_RULES)
    markers: list[dict[str, Any]] = []
    for row in disclosure_points.to_dict("records"):
        group_name = str(row.get("disclosure_group") or DISCLOSURE_GROUP_OTHER)
        style = disclosure_group_marker_style(group_name, DEFAULT_DISCLOSURE_GROUP_RULES)
        markers.append(
            {
                "time": row.get("trade_day"),
                "position": style["position"],
                "shape": style["shape"],
                "color": color_map.get(group_name, DISCLOSURE_GROUP_OTHER_COLOR),
                "text": group_name,
                "group": group_name,
                "title": row.get("title"),
                "submitter": row.get("submitter"),
                "disclosed_at": row.get("disclosed_at"),
                "acpt_no": row.get("acpt_no"),
            }
        )
    return markers


def _build_groups(disclosure_frame: pd.DataFrame) -> list[dict[str, Any]]:
    if disclosure_frame.empty:
        return []
    color_map = disclosure_group_color_map(DEFAULT_DISCLOSURE_GROUP_RULES)
    counts = disclosure_frame["disclosure_group"].value_counts().to_dict()
    return [
        {
            "name": group_name,
            "color": color_map.get(group_name, DISCLOSURE_GROUP_OTHER_COLOR),
            "count": int(count),
            "default_visible": group_name != DISCLOSURE_GROUP_OTHER,
        }
        for group_name, count in counts.items()
    ]


def _build_timeline(disclosure_frame: pd.DataFrame) -> list[dict[str, Any]]:
    if disclosure_frame.empty:
        return []
    timeline: list[dict[str, Any]] = []
    for row in disclosure_frame.sort_values("disclosed_at_dt", ascending=False).to_dict("records"):
        timeline.append(
            {
                "disclosed_at": row.get("disclosed_at"),
                "group": row.get("disclosure_group"),
                "title": row.get("title"),
                "submitter": row.get("submitter"),
                "acpt_no": row.get("acpt_no"),
                "trade_day": _json_text(row.get("trade_day")),
            }
        )
    return timeline


def _json_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)


def _non_empty_trade_days(disclosure_frame: pd.DataFrame) -> list[str]:
    if disclosure_frame.empty or "trade_day" not in disclosure_frame.columns:
        return []
    return [
        value
        for value in (_json_text(raw_value) for raw_value in disclosure_frame["trade_day"].tolist())
        if value
    ]


def _after_close_count(disclosure_frame: pd.DataFrame) -> int:
    if disclosure_frame.empty or "trade_anchor_date" not in disclosure_frame.columns:
        return 0
    return int((disclosure_frame["trade_anchor_date"] > disclosure_frame["trade_date"]).sum())


def build_ontology_company_panel(
    *,
    manifest_path: str | Path | None = None,
    quanti_dir: str | Path | None = None,
    company_id: str,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
    title_keyword: str = "",
    market: str = "전체",
    display_frequency_label: str = "자동",
) -> dict[str, Any]:
    today = date.today()
    has_manual_start = bool(str(start_date or "").strip())
    has_manual_end = bool(str(end_date or "").strip())
    query_start = _parse_date(start_date, date(1900, 1, 1))
    query_end = _parse_date(end_date, today)
    stock_code = _display_stock_code(str(company_id))
    resolved_manifest, manifest = _load_manifest(manifest_path)
    resolved_quanti = _resolve_path(quanti_dir, DEFAULT_QUANTIWISE_PARQUET_DIR)
    disclosure_rows = _load_disclosures(
        manifest_path=resolved_manifest,
        manifest=manifest,
        company_id=stock_code,
        start_date=query_start,
        end_date=query_end,
        title_keyword=title_keyword,
        market=market,
    )
    company = {
        "company_id": stock_code,
        "company_name": disclosure_rows[0]["company_name"] if disclosure_rows else "",
        "market": disclosure_rows[0]["market"] if disclosure_rows else "",
        "disclosures": [
            {
                "disclosed_at": row.get("disclosed_at"),
                "title": row.get("title_display") or row.get("title"),
                "submitter": row.get("submitter"),
                "acpt_no": row.get("acpt_no"),
                "doc_no": row.get("doc_no"),
            }
            for row in disclosure_rows
        ],
    }
    disclosure_frame = prepare_disclosure_dataframe(company)
    if not disclosure_frame.empty:
        disclosure_frame["disclosure_group"] = disclosure_frame["title"].map(
            lambda title: classify_disclosure_group(title, DEFAULT_DISCLOSURE_GROUP_RULES)
        )

    price_rows, messages = _load_quanti_ohlcv(
        quanti_dir=resolved_quanti,
        company_id=stock_code,
        start_date=query_start,
        end_date=query_end,
    )
    if messages:
        return _empty_company_panel(company, range_start=query_start, range_end=query_end, messages=messages)

    price_frame = prepare_price_dataframe(price_rows)
    if price_frame.empty:
        return _empty_company_panel(
            company,
            range_start=query_start,
            range_end=query_end,
            messages=["선택한 기간에 주가 데이터가 없습니다."],
        )

    frequency = _resolve_frequency(display_frequency_label, len(price_frame))
    display_price_frame = aggregate_price_dataframe(price_frame, frequency=frequency)
    disclosure_points = prepare_disclosure_points(
        disclosure_frame,
        display_price_frame,
        placement="candle_below",
    )
    if not disclosure_frame.empty and not disclosure_points.empty:
        disclosure_frame = disclosure_frame.merge(
            disclosure_points[["acpt_no", "trade_day"]],
            on="acpt_no",
            how="left",
        )
    elif "trade_day" not in disclosure_frame.columns:
        disclosure_frame["trade_day"] = ""
    if not disclosure_frame.empty:
        disclosure_frame["trade_day"] = disclosure_frame["trade_day"].map(_json_text)

    group_counts = Counter(disclosure_frame["disclosure_group"].tolist()) if not disclosure_frame.empty else Counter()
    trade_days = _non_empty_trade_days(disclosure_frame)
    available_dates = [pd.Timestamp(value).date() for value in price_frame["trade_day"].tolist()]
    available_dates.extend(date.fromisoformat(row["disclosed_date"]) for row in disclosure_rows if row.get("disclosed_date"))
    range_start = query_start if has_manual_start or not available_dates else min(available_dates)
    range_end = query_end if has_manual_end or not available_dates else max(available_dates)
    return {
        "company": {
            "company_id": stock_code,
            "stock_code": stock_code,
            "company_name": company["company_name"],
            "market": company["market"],
        },
        "range_start": range_start.isoformat(),
        "range_end": range_end.isoformat(),
        "display_frequency": frequency,
        "chart": {
            "candles": _build_candles(display_price_frame),
            "markers": _build_markers(disclosure_points),
            "groups": _build_groups(disclosure_frame),
        },
        "timeline": _build_timeline(disclosure_frame),
        "summary": {
            "visible_candles": int(len(display_price_frame)),
            "visible_disclosures": int(len(disclosure_frame)),
            "after_close_disclosures": _after_close_count(disclosure_frame),
            "first_disclosure": min(trade_days) if trade_days else "",
            "last_disclosure": max(trade_days) if trade_days else "",
            "top_groups": [
                {"name": name, "count": int(count)}
                for name, count in group_counts.most_common(5)
            ],
        },
        "messages": [],
    }


def _resolve_frequency(display_frequency_label: str, candle_count: int) -> str:
    if display_frequency_label == "일봉":
        return "day"
    if display_frequency_label == "5일봉":
        return "5day"
    if display_frequency_label == "20일봉":
        return "20day"
    if display_frequency_label == "월봉":
        return "month"
    if candle_count <= 180:
        return "day"
    if candle_count <= 520:
        return "week"
    return "month"


def _empty_company_panel(
    company: dict[str, Any],
    *,
    range_start: date,
    range_end: date,
    messages: list[str],
) -> dict[str, Any]:
    return {
        "company": {
            "company_id": _display_stock_code(str(company.get("company_id") or "")),
            "stock_code": _display_stock_code(str(company.get("company_id") or "")),
            "company_name": str(company.get("company_name") or ""),
            "market": str(company.get("market") or ""),
        },
        "range_start": range_start.isoformat(),
        "range_end": range_end.isoformat(),
        "display_frequency": "day",
        "chart": {"candles": [], "markers": [], "groups": []},
        "timeline": [],
        "summary": {
            "visible_candles": 0,
            "visible_disclosures": 0,
            "after_close_disclosures": 0,
            "first_disclosure": "",
            "last_disclosure": "",
            "top_groups": [],
        },
        "messages": messages,
    }


__all__ = [
    "DEFAULT_KIND_MANIFEST_PATH",
    "DEFAULT_QUANTIWISE_PARQUET_DIR",
    "build_ontology_company_panel",
    "build_ontology_status",
    "search_ontology_companies",
]
