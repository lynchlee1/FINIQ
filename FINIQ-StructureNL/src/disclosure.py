"""Parse core fields from DART mezzanine disclosure XML."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from warnings import filterwarnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from lxml import etree

filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

_DATE_RE = re.compile(r"(\d{4})[년.\-/]\s*(\d{1,2})[월.\-/]\s*(\d{1,2})")
_ISSUE_DATE_RE = re.compile(
    r"납입일[^\d]{0,30}(\d{4}[.-]\d{1,2}[.-]\d{1,2}|\d{4}년\s*\d{1,2}월\s*\d{1,2}일)"
)
_CORRECTION_TABLE_RE = re.compile(r"정\s*정\s*전.*정\s*정\s*후|정정사유")
_NON_CONTENT_BODY_TAGS = {"LIBRARY", "CORRECTION", "COVER", "HEAD", "FOOTNOTE"}


def parse_disclosure_file(path: str | Path, *, report_name: str = "") -> dict[str, Any]:
    """Read a DART XML file and parse core disclosure fields."""
    return parse_disclosure_xml(Path(path).read_text(encoding="utf-8"), report_name=report_name)


def parse_disclosure_xml(xml_text: str | bytes, *, report_name: str = "") -> dict[str, Any]:
    """Parse core fields from a DART XML string.

    The output keeps the Korean column names used by the source parser so
    downstream FINIQ modules can map them without another translation layer.
    """
    soup = _parse_xml_with_recovery(xml_text)
    return _parse_soup(soup, report_name=report_name)


def _parse_xml_with_recovery(xml_text: str | bytes) -> BeautifulSoup:
    text = xml_text.decode("utf-8", errors="ignore") if isinstance(xml_text, bytes) else xml_text
    parser = etree.XMLParser(recover=True, encoding="utf-8", huge_tree=True)
    try:
        root = etree.fromstring(text.encode("utf-8", errors="ignore"), parser=parser)
        recovered = etree.tostring(root, encoding="unicode")
        return BeautifulSoup(recovered, "xml")
    except etree.XMLSyntaxError:
        return BeautifulSoup(text, "html.parser")


def _parse_soup(soup: BeautifulSoup, *, report_name: str) -> dict[str, Any]:
    result: dict[str, Any] = {"종류": _infer_security_type(report_name)}
    tables = _collect_body_tables(soup)
    document_text = _combine_document_text(soup)

    issue_date = _extract_issue_date_from_text(document_text)
    if issue_date:
        result["납입일"] = issue_date

    target_table = _find_main_security_table(tables)
    if target_table is None:
        return result

    for row in target_table.find_all(["tr", "TR"]):
        _apply_main_table_row(result, _split_row_text(row.get_text(" | ", strip=True)))

    _populate_maturity_term(result)
    return result


def _infer_security_type(report_name: str) -> str:
    if "전환사채" in report_name:
        return "CB"
    if "교환사채" in report_name:
        return "EB"
    if "신주인수권부사채" in report_name:
        return "BW"
    return "N/A"


def _parse_number(text: str) -> float:
    cleaned = str(text).replace(",", "").replace("원", "").replace("%", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    return float(match.group(0)) if match else -1.0


def _parse_date(text: str) -> str:
    match = _DATE_RE.search(str(text))
    if not match:
        return "-"
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _split_row_text(text: str) -> list[str]:
    return [part.strip() for part in str(text).split("|") if part.strip()]


def _is_within_correction_block(element) -> bool:
    current = element
    while current is not None:
        name = getattr(current, "name", None)
        if isinstance(name, str) and name.lower() == "correction":
            return True
        current = getattr(current, "parent", None)
    return False


def _body_content_roots(soup: BeautifulSoup) -> list[Any]:
    body = soup.find(["BODY", "body"])
    if body is None:
        return [soup]

    children = [child for child in body.children if getattr(child, "name", None)]
    content_children = [
        child
        for child in children
        if str(getattr(child, "name", "")).upper() not in _NON_CONTENT_BODY_TAGS
    ]
    return content_children or [body]


def _collect_body_tables(soup: BeautifulSoup) -> list[Any]:
    tables = []
    for root in _body_content_roots(soup):
        if str(getattr(root, "name", "")).upper() == "TABLE":
            tables.append(root)
        tables.extend(root.find_all(["table", "TABLE"]))
    return [table for table in tables if not _is_within_correction_block(table)]


def _combine_document_text(soup: BeautifulSoup) -> str:
    chunks = []
    for root in _body_content_roots(soup):
        for value in root.find_all(string=True):
            text = value.strip()
            if text and not _is_within_correction_block(value):
                chunks.append(text)
    return " ".join(chunks)


def _find_main_security_table(tables: list[Any]) -> Any | None:
    for table in tables:
        text = table.get_text(" ", strip=True)
        if _CORRECTION_TABLE_RE.search(text):
            continue
        if "사채의 종류" in text and "권면" in text:
            return table
    return None


def _extract_issue_date_from_text(document_text: str) -> str | None:
    match = _ISSUE_DATE_RE.search(document_text or "")
    if match is None:
        return None
    parsed = _parse_date(match.group(1).replace(".", "-"))
    return parsed if parsed != "-" else None


def _value_after_sub_label(row_parts: list[str], sub_label: str, *, fallback_last: bool = True) -> str | None:
    for index, part in enumerate(row_parts[1:], start=1):
        if part == sub_label:
            return row_parts[index + 1] if index + 1 < len(row_parts) else None
    return row_parts[-1] if fallback_last and len(row_parts) > 1 else None


def _apply_main_table_row(result: dict[str, Any], row_parts: list[str]) -> None:
    if not row_parts:
        return

    label = row_parts[0]
    value = row_parts[1] if len(row_parts) > 1 else ""

    if "납입일" in label and value:
        result["납입일"] = _parse_date(value)
    if "사채의 종류" in label and len(row_parts) > 2:
        result["회차"] = row_parts[2]
    if "사채의 권면" in label and value:
        result["발행금액(억)"] = _parse_number(value) / 10**8
    conversion_price = _conversion_price_from_row(row_parts)
    if conversion_price is not None:
        result["전환가액(원)"] = conversion_price
    surface_rate = _value_after_sub_label(row_parts, "표면이자율", fallback_last=False)
    if surface_rate:
        result["표면이율"] = _normalize_percent(surface_rate)
    if "표면이자율" in label and value:
        result["표면이율"] = _normalize_percent(value)
    maturity_rate = _value_after_sub_label(row_parts, "만기이자율", fallback_last=False)
    if maturity_rate:
        result["만기이율"] = _normalize_percent(maturity_rate)
    if "만기이자율" in label and value:
        result["만기이율"] = _normalize_percent(value)
    if _is_price_adjustment_label(label) and value:
        result["리픽싱내용"] = " ".join(row_parts[1:])
    if "사채만기일" in label and value:
        result["만기일"] = _parse_date(value)
    if "시가하락" in label and len(row_parts) > 2:
        parsed = _parse_number(row_parts[2])
        result["리픽싱가격"] = parsed if parsed != -1.0 else "-"
    if _is_target_stock_label(label):
        target_stock = _value_after_sub_label(row_parts, "종류")
        if target_stock:
            result["대상주식"] = target_stock
    if ("청구기간" in label or "행사기간" in label) and len(row_parts) > 2 and "시작일" in row_parts[1]:
        result["전환시작일"] = _parse_date(row_parts[2])
    if label.strip() == "종료일" and value:
        result["전환종료일"] = _parse_date(value)
    if "옵션" in label and value:
        result["옵션사항"] = " ".join(row_parts[1:])


def _is_conversion_price_label(label: str) -> bool:
    return (
        ("전환가액" in label and "원" in label)
        or ("교환가액" in label and "원" in label)
        or ("행사가액" in label and "원" in label)
    )


def _conversion_price_from_row(row_parts: list[str]) -> float | None:
    for index, part in enumerate(row_parts):
        if _is_conversion_price_label(part):
            value_index = index + 1 if index + 1 < len(row_parts) else index
            parsed = _parse_number(row_parts[value_index])
            return parsed if parsed != -1.0 else None
    return None


def _is_price_method_label(label: str) -> bool:
    return any(term in label for term in ("전환가액 결정방법", "교환가액 결정방법", "행사가액 결정방법"))


def _is_price_adjustment_label(label: str) -> bool:
    return any(term in label for term in ("전환가액 조정에", "교환가액 조정에", "행사가액 조정에"))


def _is_target_stock_label(label: str) -> bool:
    return "교환대상" in label or "전환에 따라" in label or "인수권행사에 따라" in label


def _normalize_percent(text: str) -> str:
    try:
        return f"{round(_parse_number(text), 1)}%"
    except Exception:
        return text


def _populate_maturity_term(result: dict[str, Any]) -> None:
    try:
        maturity_date = datetime.strptime(result["만기일"], "%Y-%m-%d")
        issue_date = datetime.strptime(result["납입일"], "%Y-%m-%d")
        result["만기"] = f"{round((maturity_date - issue_date).days / 365.0, 1)}년"
    except Exception:
        result["만기"] = "-"
