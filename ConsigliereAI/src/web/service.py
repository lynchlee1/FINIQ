"""Data services for the custom KIND web UI."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from analytics.chart import (
    aggregate_price_dataframe,
    apply_insight_range,
    prepare_disclosure_dataframe,
    prepare_disclosure_points,
    prepare_price_dataframe,
)
from analytics.company import (
    build_company_list_xlsx,
    extract_unique_company_list_rows,
    fetch_stock_price_history,
    infer_stock_code,
)
from analytics.disclosure_groups import (
    DEFAULT_DISCLOSURE_GROUP_RULES,
    DISCLOSURE_GROUP_OTHER,
    DISCLOSURE_GROUP_OTHER_COLOR,
    classify_disclosure_group,
    disclosure_group_color_map,
    disclosure_group_marker_style,
)
from analytics.quanti import fetch_quanti_ohlcv
from data.facade import (
    find_company_classification_files,
    load_company_classification_company_file,
    load_company_classification_index_file,
)

def _resolve_workspace_default_path(*relative_parts: str) -> str:
    candidates = [
        Path.cwd(),
        Path.cwd().parent,
        Path(__file__).resolve().parents[3],
        Path(__file__).resolve().parents[2],
    ]
    checked: set[Path] = set()
    for base in candidates:
        if base in checked:
            continue
        checked.add(base)
        candidate = (base / Path(*relative_parts)).resolve()
        if candidate.exists():
            return str(candidate)
    return str((Path.cwd() / Path(*relative_parts)).resolve())


DEFAULT_OUTPUT_ROOT = _resolve_workspace_default_path("resources", "kind")
DEFAULT_QUANTI_DIR = _resolve_workspace_default_path("resources", "database", "by_item")
PRICE_SOURCE_FDR = "fdr"
PRICE_SOURCE_QUANTI = "quanti"
PRICE_SOURCE_LABELS = {
    PRICE_SOURCE_FDR: "FinanceDataReader (일봉)",
    PRICE_SOURCE_QUANTI: "Quanti_unified (수정 OHLCV + VWAP)",
}
INSIGHT_RANGE_OPTIONS = ("검색기간", "1개월", "3개월", "6개월", "1년", "전체")
DISPLAY_FREQUENCY_OPTIONS = ("자동", "일봉", "주봉", "월봉")
KIND_UI_DATE_MIN = date(1990, 1, 1)
MARKER_PLACEMENT = "candle_below"


def _company_key(company: dict[str, Any]) -> str:
    return str(company.get("company_key") or company.get("company_id") or company.get("company_name") or "").strip()


def _company_disclosure_count(company: dict[str, Any]) -> int:
    disclosure_count = company.get("disclosure_count")
    if disclosure_count is not None:
        return int(disclosure_count)
    return len(company.get("disclosures") or [])


def _classification_option_label(path: Path) -> str:
    parent_name = path.parent.name
    if parent_name == "kind":
        return path.name
    return f"{parent_name} / {path.name}"


def _resolve_display_frequency(option_label: str, candle_count: int) -> str:
    if option_label == "일봉":
        return "day"
    if option_label == "주봉":
        return "week"
    if option_label == "월봉":
        return "month"
    if candle_count <= 180:
        return "day"
    if candle_count <= 520:
        return "week"
    return "month"


def _default_period_from_company(company: dict[str, Any]) -> tuple[date, date]:
    disclosure_dates: list[date] = []
    for disclosure in list(company.get("disclosures") or []):
        disclosed_at = str(disclosure.get("disclosed_at") or "").strip()
        if not disclosed_at:
            continue
        try:
            disclosure_dates.append(date.fromisoformat(disclosed_at.split(" ", 1)[0]))
        except ValueError:
            continue

    if not disclosure_dates:
        today = date.today()
        return today.replace(day=1), today

    latest = max(disclosure_dates)
    return latest.replace(day=1), latest


def _group_color_map() -> dict[str, str]:
    return disclosure_group_color_map(DEFAULT_DISCLOSURE_GROUP_RULES)


def _serialize_company(company: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_key": _company_key(company),
        "company_name": company.get("company_name"),
        "company_id": company.get("company_id"),
        "market": company.get("market"),
        "badges": list(company.get("badges") or []),
        "disclosure_count": _company_disclosure_count(company),
        "first_disclosed_at": company.get("first_disclosed_at"),
        "last_disclosed_at": company.get("last_disclosed_at"),
    }


def list_classification_files(root_directory: str | Path) -> list[dict[str, str]]:
    root = Path(root_directory).resolve()
    return [
        {
            "path": str(path),
            "name": path.name,
            "label": _classification_option_label(path),
        }
        for path in find_company_classification_files(root)
    ]


def _looks_like_price_directory(path: Path) -> bool:
    if not path.is_dir():
        return False
    if any(path.glob("*.parquet")):
        return True
    return (path / "manifest.json").is_file()


def list_price_source_files(root_directory: str | Path) -> list[dict[str, str]]:
    root = Path(root_directory).resolve()
    if not root.exists():
        return []

    candidates: list[Path] = []
    if _looks_like_price_directory(root):
        candidates.append(root)

    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if _looks_like_price_directory(child):
            candidates.append(child)

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique_candidates.append(candidate)

    return [
        {
            "path": str(path),
            "name": path.name,
            "label": path.name if path.parent == root else str(path.relative_to(root)),
        }
        for path in unique_candidates
    ]


def resolve_default_classification(root_directory: str | Path) -> str | None:
    root = Path(root_directory).resolve()
    files = list_classification_files(root)
    if not files:
        return None
    for preferred_name in ("kind.company_classification.json", "kind.company_classification.sample.json"):
        for file_info in files:
            if Path(file_info["path"]).name == preferred_name:
                return file_info["path"]
    return files[0]["path"]


def resolve_default_price_source(root_directory: str | Path, current_path: str | Path | None = None) -> str | None:
    root = Path(root_directory).resolve()
    current = Path(current_path).resolve() if current_path else None
    files = list_price_source_files(root)
    if not files:
        return None
    if current:
        for file_info in files:
            if Path(file_info["path"]) == current:
                return file_info["path"]
    return files[0]["path"]


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
    return {
        "summary": {
            "companies": int(summary.get("companies") or len(companies)),
            "disclosures": int(summary.get("disclosures") or 0),
            "filtered_companies": len(filtered),
        },
        "markets": markets,
        "companies": [_serialize_company(company) for company in filtered],
    }


def _load_price_rows(
    stock_code: str,
    *,
    range_start: date,
    range_end: date,
    price_source: str,
    quanti_dir: str | Path,
) -> list[dict[str, Any]]:
    if price_source == PRICE_SOURCE_QUANTI:
        return fetch_quanti_ohlcv(
            stock_code,
            start_date=range_start,
            end_date=range_end,
            quanti_dir=quanti_dir,
        )
    return fetch_stock_price_history(
        stock_code,
        start_date=range_start,
        end_date=range_end,
    )


def _build_marker_payload(disclosure_points: pd.DataFrame) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    color_map = _group_color_map()
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


def _build_candle_payload(price_frame: pd.DataFrame) -> list[dict[str, Any]]:
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
                "vwap": None if pd.isna(row.get("vwap")) else float(row["vwap"]),
                "color": "#22ab94" if close_value >= open_value else "#f23645",
            }
        )
    return candles


def _build_group_summary(disclosure_frame: pd.DataFrame) -> list[dict[str, Any]]:
    color_map = _group_color_map()
    counts = disclosure_frame["disclosure_group"].value_counts().to_dict()
    groups: list[dict[str, Any]] = []
    for group_name, color in color_map.items():
        count = int(counts.get(group_name) or 0)
        if count == 0:
            continue
        groups.append(
            {
                "name": group_name,
                "color": color,
                "count": count,
                "default_visible": group_name != DISCLOSURE_GROUP_OTHER,
            }
        )
    return groups


def _build_timeline_payload(disclosure_frame: pd.DataFrame) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for row in disclosure_frame.sort_values("disclosed_at_dt", ascending=False).to_dict("records"):
        timeline.append(
            {
                "disclosed_at": row.get("disclosed_at"),
                "group": row.get("disclosure_group"),
                "title": row.get("title"),
                "submitter": row.get("submitter"),
                "acpt_no": row.get("acpt_no"),
                "trade_day": row.get("trade_day"),
            }
        )
    return timeline


def build_insight_payload(
    classification_path: str | Path,
    company_key: str,
    *,
    start_date_iso: str | None = None,
    end_date_iso: str | None = None,
    range_label: str = "검색기간",
    display_frequency_label: str = "자동",
    price_source: str = PRICE_SOURCE_QUANTI,
    quanti_dir: str | Path = DEFAULT_QUANTI_DIR,
    stock_code_override: str = "",
) -> dict[str, Any]:
    classification_resolved = Path(classification_path).resolve()
    company = load_company_classification_company_file(classification_resolved, company_key)
    company_summary = load_company_classification_index_file(classification_resolved)
    company_meta = next(
        (
            item
            for item in list(company_summary.get("companies") or [])
            if _company_key(item) == company_key
        ),
        {},
    )

    inferred_stock_code = infer_stock_code(
        company.get("company_id") or company_meta.get("company_id")
    )
    stock_code = str(stock_code_override or inferred_stock_code or "").strip()
    if stock_code and (not stock_code.isdigit() or len(stock_code) != 6):
        raise ValueError("종목코드는 숫자 6자리여야 합니다.")

    disclosure_frame = prepare_disclosure_dataframe(company)
    default_start, default_end = _default_period_from_company(company)
    manual_start = date.fromisoformat(start_date_iso) if start_date_iso else default_start
    manual_end = date.fromisoformat(end_date_iso) if end_date_iso else default_end
    range_start, range_end = apply_insight_range(
        range_label,
        base_start=manual_start,
        base_end=manual_end,
        disclosure_frame=disclosure_frame,
        ui_date_min=KIND_UI_DATE_MIN,
    )
    grouped_disclosures = disclosure_frame[
        (disclosure_frame["trade_date"] >= pd.Timestamp(range_start))
        & (disclosure_frame["trade_date"] <= pd.Timestamp(range_end))
    ].copy()
    grouped_disclosures["disclosure_group"] = grouped_disclosures["title"].map(
        lambda title: classify_disclosure_group(title, DEFAULT_DISCLOSURE_GROUP_RULES)
    )
    extended_price_end = range_end
    if not grouped_disclosures.empty and "trade_anchor_date" in grouped_disclosures.columns:
        latest_anchor = grouped_disclosures["trade_anchor_date"].max()
        if pd.notna(latest_anchor):
            extended_price_end = max(
                range_end,
                latest_anchor.date() + timedelta(days=7),
            )

    messages: list[str] = []
    price_frame = pd.DataFrame()
    display_frequency = "day"
    display_price_frame = pd.DataFrame()
    disclosure_points = pd.DataFrame()
    visible_range_end = range_end

    if stock_code:
        try:
            price_rows = _load_price_rows(
                stock_code,
                range_start=range_start,
                range_end=extended_price_end,
                price_source=price_source,
                quanti_dir=quanti_dir,
            )
            price_frame = prepare_price_dataframe(price_rows)
        except Exception as exc:  # pragma: no cover - network/runtime edge
            messages.append(f"주가 데이터를 불러오지 못했습니다: {exc}")
    else:
        messages.append("자동 종목코드를 찾지 못해 차트를 표시하지 않았습니다.")

    if not price_frame.empty:
        display_frequency = _resolve_display_frequency(display_frequency_label, len(price_frame))
        display_price_frame = aggregate_price_dataframe(
            price_frame,
            frequency=display_frequency,
        )
        disclosure_points = prepare_disclosure_points(
            grouped_disclosures,
            display_price_frame,
            placement=MARKER_PLACEMENT,
        )
        if not disclosure_points.empty:
            latest_visible_trade_day = pd.to_datetime(
                disclosure_points["trade_day"],
                errors="coerce",
            ).max()
            if pd.notna(latest_visible_trade_day):
                visible_range_end = max(range_end, latest_visible_trade_day.date())
                display_price_frame = display_price_frame[
                    display_price_frame["date"] <= pd.Timestamp(visible_range_end)
                ].copy()
                disclosure_points = prepare_disclosure_points(
                    grouped_disclosures,
                    display_price_frame,
                    placement=MARKER_PLACEMENT,
                )
        grouped_disclosures = grouped_disclosures.merge(
            disclosure_points[["acpt_no", "trade_day"]],
            on="acpt_no",
            how="left",
        )
    elif stock_code and not messages:
        messages.append("선택한 기간에 주가 데이터가 없습니다.")

    frequency_label_map = {"day": "일봉", "week": "주봉", "month": "월봉"}
    return {
        "company": {
            **_serialize_company(company_meta or company),
            "badges": list(company.get("badges") or company_meta.get("badges") or []),
        },
        "classification_path": str(classification_resolved),
        "stock_code": stock_code,
        "inferred_stock_code": inferred_stock_code,
        "manual_start": manual_start.isoformat(),
        "manual_end": manual_end.isoformat(),
        "range_start": range_start.isoformat(),
        "range_end": range_end.isoformat(),
        "visible_range_end": visible_range_end.isoformat(),
        "range_label": range_label,
        "display_frequency": display_frequency,
        "display_frequency_label": frequency_label_map.get(display_frequency, display_frequency),
        "price_source": price_source,
        "price_source_label": PRICE_SOURCE_LABELS.get(price_source, price_source),
        "messages": messages,
        "chart": {
            "candles": _build_candle_payload(display_price_frame),
            "markers": _build_marker_payload(disclosure_points),
            "groups": _build_group_summary(grouped_disclosures),
            "has_vwap": bool(
                not display_price_frame.empty
                and "vwap" in display_price_frame.columns
                and display_price_frame["vwap"].notna().any()
            ),
        },
        "timeline": _build_timeline_payload(grouped_disclosures),
    }


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
