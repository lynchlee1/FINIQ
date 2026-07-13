"""Pure helpers for company insight chart data preparation."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

RANGE_LABEL_TO_DAYS = {
    "1개월": 30,
    "3개월": 90,
    "6개월": 180,
    "1년": 365,
}

MARKER_PLACEMENTS = {
    "x_axis_below",
    "x_axis_above",
    "candle_center",
    "candle_above",
    "candle_below",
}


def prepare_disclosure_dataframe(company: dict[str, Any]) -> pd.DataFrame:
    """Convert one company disclosure bundle into a normalized dataframe."""
    disclosure_rows = list(company.get("disclosures") or [])
    if not disclosure_rows:
        return pd.DataFrame(
            columns=[
                "disclosed_at",
                "title",
                "submitter",
                "acpt_no",
                "doc_no",
                "disclosed_at_dt",
                "trade_date",
            ]
        )

    frame = pd.DataFrame(disclosure_rows)
    frame["disclosed_at_dt"] = pd.to_datetime(frame["disclosed_at"], errors="coerce")
    frame = frame.dropna(subset=["disclosed_at_dt"]).sort_values("disclosed_at_dt")
    frame["trade_date"] = frame["disclosed_at_dt"].dt.normalize()
    after_close = (
        (frame["disclosed_at_dt"].dt.hour > MARKET_CLOSE_HOUR)
        | (
            (frame["disclosed_at_dt"].dt.hour == MARKET_CLOSE_HOUR)
            & (frame["disclosed_at_dt"].dt.minute >= MARKET_CLOSE_MINUTE)
        )
    )
    frame["trade_anchor_date"] = frame["trade_date"]
    frame.loc[after_close, "trade_anchor_date"] = (
        frame.loc[after_close, "trade_anchor_date"] + pd.Timedelta(days=1)
    )
    return frame


def apply_insight_range(
    range_label: str,
    *,
    base_start: date,
    base_end: date,
    disclosure_frame: pd.DataFrame,
    ui_date_min: date,
) -> tuple[date, date]:
    """Resolve the selected chart range into explicit start/end dates."""
    end_value = max(base_start, base_end)
    if range_label == "전체" and not disclosure_frame.empty:
        earliest = disclosure_frame["trade_date"].min()
        if pd.notna(earliest):
            return min(base_start, earliest.date()), end_value

    days = RANGE_LABEL_TO_DAYS.get(range_label)
    if days is None:
        return base_start, end_value

    start_value = end_value - timedelta(days=days - 1)
    return max(ui_date_min, start_value), end_value


def prepare_price_dataframe(price_rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Normalize OHLCV rows and enrich them for chart rendering.

    Each row may optionally carry a ``vwap`` key (int or None).  When present,
    the resulting DataFrame will include a numeric ``vwap`` column suitable for
    overlaying a VWAP line on the candlestick chart.
    """
    if not price_rows:
        return pd.DataFrame(
            columns=[
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "vwap",
                "trade_day",
                "trade_label",
                "candle_color",
                "body_bottom",
                "body_top",
            ]
        )

    frame = pd.DataFrame(price_rows).copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    if "vwap" in frame.columns:
        frame["vwap"] = pd.to_numeric(frame["vwap"], errors="coerce")
    else:
        frame["vwap"] = float("nan")

    frame = frame.dropna(subset=["date", "open", "high", "low", "close", "volume"])
    frame = frame.sort_values("date").reset_index(drop=True)
    frame["trade_day"] = frame["date"].dt.strftime("%Y-%m-%d")
    frame["trade_label"] = frame["date"].dt.strftime("%y.%m.%d")
    frame["candle_color"] = frame.apply(
        lambda row: "#16a34a" if row["close"] >= row["open"] else "#dc2626",
        axis=1,
    )
    frame["body_bottom"] = frame[["open", "close"]].min(axis=1)
    frame["body_top"] = frame[["open", "close"]].max(axis=1)
    return frame


def aggregate_price_dataframe(
    price_frame: pd.DataFrame,
    *,
    frequency: str,
) -> pd.DataFrame:
    """Aggregate normalized price data into multi-day, weekly, or monthly candles."""
    normalized = str(frequency).strip().lower()
    if price_frame.empty or normalized in {"day", "daily", "d"}:
        return price_frame.copy()

    multi_day_map = {
        "3day": 3,
        "3d": 3,
        "5day": 5,
        "5d": 5,
        "7day": 7,
        "7d": 7,
        "20day": 20,
        "20d": 20,
    }
    period = multi_day_map.get(normalized)
    if period is not None:
        frame = price_frame.copy().sort_values("date").reset_index(drop=True)
        frame["_period"] = [index // period for index in range(len(frame))]
        aggregated = frame.groupby("_period", as_index=False).agg(
            {
                "date": "last",
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "vwap": "mean",
            }
        )
        aggregated = aggregated.drop(columns=["_period"]).dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        aggregated["trade_day"] = aggregated["date"].dt.strftime("%Y-%m-%d")
        aggregated["trade_label"] = aggregated["date"].dt.strftime("%y.%m.%d")
        aggregated["candle_color"] = aggregated.apply(
            lambda row: "#16a34a" if row["close"] >= row["open"] else "#dc2626",
            axis=1,
        )
        aggregated["body_bottom"] = aggregated[["open", "close"]].min(axis=1)
        aggregated["body_top"] = aggregated[["open", "close"]].max(axis=1)
        return aggregated

    freq_map = {
        "week": "W-FRI",
        "weekly": "W-FRI",
        "w": "W-FRI",
        "month": "ME",
        "monthly": "ME",
        "m": "ME",
    }
    pandas_frequency = freq_map.get(normalized)
    if pandas_frequency is None:
        msg = f"Unsupported price aggregation frequency: {frequency}"
        raise ValueError(msg)

    frame = price_frame.copy()
    frame = frame.sort_values("date").set_index("date")
    aggregated = frame.resample(pandas_frequency).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "vwap": "mean",
        }
    )
    aggregated = aggregated.dropna(subset=["open", "high", "low", "close"]).reset_index()
    aggregated["trade_day"] = aggregated["date"].dt.strftime("%Y-%m-%d")
    aggregated["trade_label"] = aggregated["date"].dt.strftime("%y.%m.%d")
    aggregated["candle_color"] = aggregated.apply(
        lambda row: "#16a34a" if row["close"] >= row["open"] else "#dc2626",
        axis=1,
    )
    aggregated["body_bottom"] = aggregated[["open", "close"]].min(axis=1)
    aggregated["body_top"] = aggregated[["open", "close"]].max(axis=1)
    return aggregated


def _marker_offset(price_frame: pd.DataFrame) -> float:
    if price_frame.empty:
        return 1.0
    low_value = float(price_frame["low"].min())
    high_value = float(price_frame["high"].max())
    return max((high_value - low_value) * 0.035, 1.0)


def _marker_price_for_row(
    row: pd.Series,
    *,
    placement: str,
    axis_floor: float,
    offset: float,
) -> float:
    if placement == "x_axis_below":
        return axis_floor - (offset * 1.15)
    if placement == "x_axis_above":
        return axis_floor + (offset * 0.9)
    if placement == "candle_center":
        return (float(row["open"]) + float(row["close"])) / 2.0
    if placement == "candle_above":
        return float(row["high"]) + offset
    return float(row["low"]) - offset


def prepare_disclosure_points(
    disclosure_frame: pd.DataFrame,
    price_frame: pd.DataFrame,
    *,
    placement: str,
) -> pd.DataFrame:
    """Attach each disclosure to the nearest visible candle and marker position."""
    if placement not in MARKER_PLACEMENTS:
        msg = f"Unsupported marker placement: {placement}"
        raise ValueError(msg)
    if disclosure_frame.empty or price_frame.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "trade_day",
                "open",
                "high",
                "low",
                "close",
                "marker_price",
                "title",
                "submitter",
                "disclosed_at",
                "acpt_no",
                "trade_anchor_date",
            ]
        )

    merged = pd.merge_asof(
        disclosure_frame.sort_values("trade_anchor_date"),
        price_frame[
            ["date", "trade_day", "open", "high", "low", "close"]
        ].sort_values("date"),
        left_on="trade_anchor_date",
        right_on="date",
        direction="forward",
    )
    merged = merged.dropna(subset=["open", "high", "low", "close"]).copy()
    merged = merged.drop(columns=["date"])
    merged["date"] = merged["trade_anchor_date"]

    offset = _marker_offset(price_frame)
    axis_floor = float(price_frame["low"].min())
    merged["marker_price"] = merged.apply(
        _marker_price_for_row,
        axis=1,
        placement=placement,
        axis_floor=axis_floor,
        offset=offset,
    )
    return merged


__all__ = [
    "aggregate_price_dataframe",
    "MARKER_PLACEMENTS",
    "RANGE_LABEL_TO_DAYS",
    "apply_insight_range",
    "prepare_disclosure_dataframe",
    "prepare_disclosure_points",
    "prepare_price_dataframe",
]
