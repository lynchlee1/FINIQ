"""Parse KIND disclosure result tables into company-classified row records."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lxml import etree, html

from ._markup import _clean_text, decode_html_markup
from ._snippets import disclosure_onclick

_COMPANYSUMMARY_OPEN_RE = re.compile(
    r"companysummary_open\(\s*['\"](?P<company_id>[^'\"]*)['\"]\s*\)"
)
_TITLE_FLAG_RE = re.compile(r"\[([^\[\]]+)\]")
_LATER_CORRECTION_LABEL = "해당보고서 이후에 정정된 보고서 있음"


def companysummary_onclick(onclick_value: str | None) -> dict[str, str | None] | None:
    """Extract the KIND company identifier from `companysummary_open(...)`."""
    if onclick_value is None:
        return None
    match = _COMPANYSUMMARY_OPEN_RE.search(str(onclick_value))
    if match is None:
        return None
    company_id = match.group("company_id").strip() or None
    return {"company_id": company_id}


def _pick_market_and_badges(company_cell: html.HtmlElement) -> tuple[str | None, list[str]]:
    labels: list[str] = []
    for image_tag in company_cell.xpath(".//img"):
        label = _clean_text(str(image_tag.get("alt") or ""))
        if not label:
            raise ValueError("KIND company image is missing a non-empty alt label")
        labels.append(label)
    if not labels:
        return None, []
    return labels[0], labels[1:]


def _element_text(node: html.HtmlElement | None) -> str:
    if node is None:
        return ""
    return _clean_text(" ".join(text for text in node.itertext()))


def _display_text(node: html.HtmlElement | None) -> str:
    if node is None:
        return ""
    return _clean_text(node.text_content())


def _title_flags(title: str) -> list[str]:
    flags: list[str] = []
    for match in _TITLE_FLAG_RE.finditer(title):
        flag = _clean_text(match.group(1))
        if flag and flag not in flags:
            flags.append(flag)
    return flags


def _has_later_correction(disclosure_cell: html.HtmlElement) -> bool:
    return any(
        _clean_text(str(image_tag.get("alt") or "")) == _LATER_CORRECTION_LABEL
        for image_tag in disclosure_cell.xpath(".//img")
    )


def _build_disclosure_row(row_tag: html.HtmlElement) -> dict[str, Any]:
    cells = row_tag.xpath("./td")
    if len(cells) < 5:
        raise ValueError("KIND disclosure result row has fewer than 5 cells")

    company_cell = cells[2]
    disclosure_cell = cells[3]
    submitter_cell = cells[4]

    company_links = company_cell.xpath(".//a[@id='companysum']")
    if len(company_links) > 1:
        raise ValueError("KIND disclosure row must not contain multiple companysum links")
    disclosure_links = disclosure_cell.xpath(
        ".//a[contains(@onclick, 'openDisclsViewer')]"
    )
    if len(disclosure_links) != 1:
        raise ValueError("KIND disclosure row must contain exactly one disclosure link")
    disclosure_link = disclosure_links[0]

    company_cell_text = _display_text(company_cell)
    company_name: str | None = None
    company_id: str | None = None
    if company_links:
        company_link = company_links[0]
        company_name = _clean_text(str(company_link.get("title") or ""))
        if not company_name:
            raise ValueError("KIND company link is missing a non-empty title")
        company_info = companysummary_onclick(company_link.get("onclick"))
        company_id = (
            company_info.get("company_id") if company_info is not None else None
        )
        if not company_id:
            raise ValueError("KIND company link is missing company_id")

    market, badges = _pick_market_and_badges(company_cell)
    disclosure_info = disclosure_onclick(disclosure_link.get("onclick"))
    if disclosure_info is None or not disclosure_info.get("acpt_no"):
        raise ValueError("KIND disclosure link is missing acpt_no")

    title_attr = _clean_text(str(disclosure_link.get("title") or ""))
    title_display = _display_text(disclosure_link)
    if not title_display:
        raise ValueError("KIND disclosure link has no displayed title")
    title = title_display
    title_flags = _title_flags(title_display)

    return {
        "row_no": _element_text(cells[0]),
        "company_name": company_name,
        "company_id": company_id,
        "company_cell_text": company_cell_text,
        "market": market,
        "badges": badges,
        "disclosed_at": _element_text(cells[1]),
        "title": title,
        "title_attr": title_attr,
        "title_base": title_attr,
        "title_display": title_display,
        "title_flags": title_flags,
        "is_correction_report": "정정" in title_flags,
        "has_later_correction": _has_later_correction(disclosure_cell),
        "acpt_no": disclosure_info.get("acpt_no"),
        "doc_no": disclosure_info.get("doc_no"),
        "submitter": _element_text(submitter_cell),
    }


def disclosure_rows(html_markup: str | bytes) -> list[dict[str, Any]]:
    """Parse a KIND result page and return one structured record per disclosure row."""
    decoded_markup = decode_html_markup(html_markup)
    parser = html.HTMLParser(recover=True, huge_tree=True)
    try:
        root = html.document_fromstring(decoded_markup, parser=parser)
    except etree.ParserError as exc:
        raise ValueError("Failed to parse KIND disclosure result page") from exc
    table_tags = root.xpath(
        "//table[contains(@summary, '회사명') and contains(@summary, '공시제목')]"
    )
    if len(table_tags) != 1:
        raise ValueError("KIND disclosure result table is missing or ambiguous")
    table_tag = table_tags[0]

    tbody_tags = table_tag.xpath("./tbody")
    if len(tbody_tags) != 1:
        raise ValueError("KIND disclosure result table must contain exactly one tbody")

    rows: list[dict[str, Any]] = []
    for row_index, row_tag in enumerate(tbody_tags[0].xpath("./tr"), start=1):
        try:
            rows.append(_build_disclosure_row(row_tag))
        except ValueError as exc:
            raise ValueError(f"KIND disclosure result row {row_index}: {exc}") from exc
    return rows


def disclosure_file_rows(file_path: str | Path) -> list[dict[str, Any]]:
    """Read a KIND result body file and return parsed disclosure rows."""
    path = Path(file_path)
    try:
        return disclosure_rows(path.read_bytes())
    except ValueError as exc:
        raise ValueError(f"{exc}: {path}") from exc
