"""Helpers for processing parsed company disclosures and daily price history."""

from __future__ import annotations

from io import BytesIO
from datetime import date
import re
from typing import Any
from xml.sax.saxutils import escape
import zipfile

import pandas as pd

_A_STOCK_CODE_RE = re.compile(r"^A\d{6}$")
_ALNUM_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{5,6}$")


def infer_stock_code(company_id: str | None) -> str | None:
    """Infer a 6-digit stock code from a KIND company identifier when possible."""
    if company_id is None:
        return None

    normalized = str(company_id).strip()
    if not normalized or not normalized.isdigit():
        return None
    if len(normalized) == 6:
        return normalized
    if len(normalized) == 5:
        return f"{normalized}0"
    if len(normalized) < 5:
        return normalized.zfill(6)
    return None


def format_stock_code_for_export(company_id: str | None) -> str:
    """Return an Excel-friendly stock code in KIND chart-code form with ``A`` prefix."""
    normalized = str(company_id or "").strip().upper()
    if not normalized:
        return ""
    if _A_STOCK_CODE_RE.fullmatch(normalized):
        return normalized

    inferred = infer_stock_code(normalized)
    if inferred is not None:
        return f"A{inferred}"

    if _ALNUM_STOCK_CODE_RE.fullmatch(normalized):
        return f"A{normalized}"
    return ""


def _merge_company_flags(existing_flags: str, incoming_badges: Any) -> str:
    merged_flags: list[str] = []
    seen_flags: set[str] = set()

    for value in [*(existing_flags.split(",") if existing_flags else []), *(incoming_badges or [])]:
        flag = str(value).strip()
        if not flag or flag in seen_flags:
            continue
        seen_flags.add(flag)
        merged_flags.append(flag)

    return ", ".join(merged_flags)


def _normalize_market_for_export(market: Any) -> str:
    return str(market or "").strip()


def extract_unique_company_list_rows(
    companies: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Return unique company rows for Excel export."""
    extracted_rows: list[dict[str, str]] = []
    row_indexes_by_key: dict[tuple[str, str], int] = {}

    for company in companies:
        company_name = str(company.get("company_name") or "").strip()
        stock_code = format_stock_code_for_export(company.get("company_id"))
        dedup_key = (company_name, stock_code)
        if not company_name:
            continue
        if dedup_key in row_indexes_by_key:
            row_index = row_indexes_by_key[dedup_key]
            existing_market = extracted_rows[row_index].get("시장구분", "")
            if not existing_market:
                extracted_rows[row_index]["시장구분"] = _normalize_market_for_export(
                    company.get("market")
                )
            extracted_rows[row_index]["플래그"] = _merge_company_flags(
                extracted_rows[row_index].get("플래그", ""),
                company.get("badges"),
            )
            continue

        row_indexes_by_key[dedup_key] = len(extracted_rows)
        extracted_rows.append(
            {
                "기업명": company_name,
                "주식코드": stock_code,
                "시장구분": _normalize_market_for_export(company.get("market")),
                "플래그": _merge_company_flags("", company.get("badges")),
            }
        )

    return extracted_rows


def _xlsx_column_name(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def build_company_list_xlsx(rows: list[dict[str, str]]) -> bytes:
    """Build a minimal XLSX workbook for company-list export without extra deps."""
    headers = ["기업명", "주식코드", "시장구분", "플래그"]
    workbook_rows = [headers, *[[row.get(header, "") for header in headers] for row in rows]]

    sheet_rows_xml: list[str] = []
    for row_number, row_values in enumerate(workbook_rows, start=1):
        cell_xml: list[str] = []
        for column_number, value in enumerate(row_values, start=1):
            cell_ref = f"{_xlsx_column_name(column_number)}{row_number}"
            cell_xml.append(
                f'<c r="{cell_ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
            )
        sheet_rows_xml.append(f'<row r="{row_number}">{"".join(cell_xml)}</row>')

    dimension_ref = f"A1:{_xlsx_column_name(len(headers))}{max(1, len(workbook_rows))}"
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dimension_ref}"/>'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        '<cols>'
        '<col min="1" max="1" width="24" customWidth="1"/>'
        '<col min="2" max="2" width="18" customWidth="1"/>'
        '<col min="3" max="3" width="14" customWidth="1"/>'
        '<col min="4" max="4" width="22" customWidth="1"/>'
        "</cols>"
        f'<sheetData>{"".join(sheet_rows_xml)}</sheetData>'
        f'<autoFilter ref="{dimension_ref}"/>'
        "</worksheet>"
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="회사리스트" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )

    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as workbook_zip:
        workbook_zip.writestr("[Content_Types].xml", content_types_xml)
        workbook_zip.writestr("_rels/.rels", root_rels_xml)
        workbook_zip.writestr("xl/workbook.xml", workbook_xml)
        workbook_zip.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        workbook_zip.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return output.getvalue()


def _load_finance_data_reader_module() -> Any:
    try:
        import FinanceDataReader as fdr  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised via caller behavior
        msg = "FinanceDataReader is required. Install with `pip install -e \".[web]\"`."
        raise RuntimeError(msg) from exc
    return fdr


def _normalize_fdr_price_frame(price_frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Normalize a FinanceDataReader dataframe into lowercase OHLCV rows."""
    if price_frame.empty:
        return []

    normalized = price_frame.reset_index().copy()
    rename_map = {
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    normalized = normalized.rename(columns=rename_map)

    required_columns = ["date", "open", "high", "low", "close", "volume"]
    missing_columns = [column for column in required_columns if column not in normalized.columns]
    if missing_columns:
        msg = f"FinanceDataReader payload missing columns: {', '.join(missing_columns)}"
        raise ValueError(msg)

    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    for column in required_columns[1:]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized = normalized.dropna(subset=required_columns).sort_values("date")
    if normalized.empty:
        return []

    for column in required_columns[1:]:
        normalized[column] = normalized[column].astype("int64")
    normalized["date"] = normalized["date"].dt.strftime("%Y-%m-%d")
    return normalized[required_columns].to_dict(orient="records")


def fetch_stock_price_history(
    stock_code: str,
    *,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Fetch daily OHLCV price history via FinanceDataReader.

    FinanceDataReader public docs/source currently provide a clear daily-data path.
    This helper intentionally stays on daily bars and does not expose intraday data.
    """
    normalized_code = str(stock_code).strip()
    if not normalized_code:
        return []

    fdr = _load_finance_data_reader_module()
    symbols_to_try = [normalized_code, f"KRX-DELISTING:{normalized_code}"]
    last_error: Exception | None = None

    for symbol in symbols_to_try:
        try:
            frame = fdr.DataReader(
                symbol,
                start_date.isoformat(),
                end_date.isoformat(),
            )
            rows = _normalize_fdr_price_frame(frame)
        except Exception as exc:  # pragma: no cover - fallback path depends on runtime
            last_error = exc
            continue
        if rows:
            return rows

    if last_error is not None:
        raise RuntimeError(f"FinanceDataReader price lookup failed for {normalized_code}.") from last_error
    return []


__all__ = [
    "build_company_list_xlsx",
    "extract_unique_company_list_rows",
    "fetch_stock_price_history",
    "format_stock_code_for_export",
    "infer_stock_code",
]
