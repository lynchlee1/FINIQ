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
_DISCLOSURE_TABLE_SUMMARY_TERMS = ("\ud68c\uc0ac\uba85", "\uacf5\uc2dc\uc81c\ubaa9")
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


def _find_disclosure_results_table(root: html.HtmlElement) -> html.HtmlElement | None:
    """Return the main disclosure results table from a KIND result page."""
    for table_tag in root.xpath("//table"):
        summary = _clean_text(str(table_tag.get("summary") or ""))
        if all(term in summary for term in _DISCLOSURE_TABLE_SUMMARY_TERMS):
            return table_tag
    for table_tag in root.xpath("//table[contains(concat(' ', normalize-space(@class), ' '), ' list ')]"):
        return table_tag
    return None


def _pick_market_and_badges(company_cell: html.HtmlElement) -> tuple[str | None, list[str]]:
    labels = [
        _clean_text(str(image_tag.get("alt") or ""))
        for image_tag in company_cell.xpath(".//img")
    ]
    labels = [label for label in labels if label]
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


def _build_disclosure_row(row_tag: html.HtmlElement) -> dict[str, Any] | None:
    cells = row_tag.xpath("./td")
    if len(cells) < 5:
        return None

    company_cell = cells[2]
    disclosure_cell = cells[3]
    submitter_cell = cells[4]

    company_links = company_cell.xpath(".//a[@id='companysum']") or company_cell.xpath(".//a")
    company_link = company_links[0] if company_links else None
    disclosure_links = disclosure_cell.xpath(".//a")
    disclosure_link = disclosure_links[0] if disclosure_links else None

    company_name = ""
    company_id = None
    if company_link is not None:
        company_name = _clean_text(
            str(company_link.get("title") or _element_text(company_link))
        )
        company_info = companysummary_onclick(company_link.get("onclick"))
        if company_info is not None:
            company_id = company_info.get("company_id")
    if not company_name:
        company_name = _element_text(company_cell)

    market, badges = _pick_market_and_badges(company_cell)
    disclosure_info = (
        disclosure_onclick(disclosure_link.get("onclick")) if disclosure_link is not None else None
    ) or {"acpt_no": None, "doc_no": None}

    title_attr = ""
    title_display = ""
    if disclosure_link is not None:
        title_attr = _clean_text(str(disclosure_link.get("title") or ""))
        title_display = _display_text(disclosure_link)
    title = title_display or title_attr
    if not title:
        title = _display_text(disclosure_cell)
        title_display = title
    title_flags = _title_flags(title_display or title)

    return {
        "row_no": _element_text(cells[0]),
        "company_name": company_name,
        "company_id": company_id,
        "market": market,
        "badges": badges,
        "disclosed_at": _element_text(cells[1]),
        "title": title,
        "title_attr": title_attr,
        "title_base": title_attr,
        "title_display": title_display or title,
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
    except etree.ParserError:
        return []
    table_tag = _find_disclosure_results_table(root)
    if table_tag is None:
        return []

    tbody_tags = table_tag.xpath("./tbody")
    parent_tags: list[html.HtmlElement] = tbody_tags if tbody_tags else [table_tag]

    rows: list[dict[str, Any]] = []
    for parent_tag in parent_tags:
        for row_tag in parent_tag.xpath("./tr"):
            row = _build_disclosure_row(row_tag)
            if row is not None:
                rows.append(row)
    return rows


def disclosure_file_rows(file_path: str | Path) -> list[dict[str, Any]]:
    """Read a KIND result body file and return parsed disclosure rows."""
    return disclosure_rows(Path(file_path).read_bytes())
