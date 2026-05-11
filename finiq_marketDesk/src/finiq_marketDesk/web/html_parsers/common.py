"""Shared helpers for KIND disclosure viewer HTML parsers."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from lxml import etree, html


def decode_html_markup(html_markup: str | bytes) -> str:
    """Return HTML markup as text with forgiving byte decoding."""
    if isinstance(html_markup, str):
        return html_markup
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return html_markup.decode(encoding)
        except UnicodeDecodeError:
            continue
    return html_markup.decode("utf-8", errors="replace")


def parse_html_document(html_markup: str | bytes) -> html.HtmlElement:
    """Parse imperfect viewer HTML into an lxml document."""
    parser = html.HTMLParser(encoding="utf-8", recover=True, huge_tree=True)
    decoded = decode_html_markup(html_markup)
    document = html.fromstring(decoded, parser=parser)
    return document


def clean_text(value: str | None) -> str:
    """Collapse whitespace in display text."""
    return " ".join((value or "").split())


def element_text(element: etree._Element) -> str:
    """Extract normalized text from an lxml element."""
    return clean_text(" ".join(element.itertext()))


def parse_int(value: str | None, *, dash_as_zero: bool = False) -> int | None:
    """Parse a comma-formatted integer from text."""
    text = clean_text(value)
    if dash_as_zero and text in {"", "-"}:
        return 0
    match = re.search(r"-?\d[\d,]*", text)
    if match is None:
        return None
    return int(match.group(0).replace(",", ""))


def parse_float(value: str | None) -> float | None:
    """Parse a decimal number from text."""
    text = clean_text(value)
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(match.group(0)) if match else None


def extract_title(document: html.HtmlElement) -> str:
    """Extract the best available disclosure title from viewer HTML."""
    for xpath in (
        "//meta[translate(@property, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='og:title']/@content",
        "//meta[translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='title']/@content",
        "//title/text()",
        "//*[@title]/@title",
        "//h1/text()",
        "//h2/text()",
    ):
        values = document.xpath(xpath)
        for value in values:
            title = clean_text(str(value))
            if title:
                return title
    return ""


def extract_acpt_no(file_path: str | Path) -> str:
    """Infer KIND receipt number from a viewer HTML filename."""
    stem = Path(file_path).stem
    candidate = stem.split("_", 1)[0]
    return candidate if candidate.isdigit() else ""


def extract_table_rows(document: html.HtmlElement) -> list[list[str]]:
    """Return all table rows as normalized cell text."""
    rows: list[list[str]] = []
    for table in extract_tables(document):
        rows.extend(table["logical_rows"])
    return rows


def _span_size(cell: etree._Element, attribute_name: str) -> int:
    raw_value = cell.get(attribute_name)
    try:
        value = int(str(raw_value or "1"))
    except ValueError:
        return 1
    return max(value, 1)


def _cell_slot(
    cell: etree._Element,
    *,
    row_index: int,
    col_index: int,
    source_row: int,
    source_col: int,
    rowspan: int,
    colspan: int,
    from_span: bool,
) -> dict[str, Any]:
    return {
        "text": element_text(cell),
        "row_index": row_index,
        "col_index": col_index,
        "source_row": source_row,
        "source_col": source_col,
        "rowspan": rowspan,
        "colspan": colspan,
        "from_span": from_span,
    }


def expand_table(table: etree._Element) -> list[list[dict[str, Any]]]:
    """Expand a table grid so rowspan/colspan cells appear in every occupied slot."""
    active_spans: dict[int, tuple[int, etree._Element, int, int, int, int]] = {}
    grid: list[list[dict[str, Any]]] = []

    for row_index, row in enumerate(table.xpath(".//tr")):
        expanded_row: list[dict[str, Any]] = []
        col_index = 0
        source_col = 0
        consumed_active_cols: set[int] = set()

        def append_active_span() -> bool:
            nonlocal col_index
            span = active_spans.get(col_index)
            if span is None:
                return False
            consumed_active_cols.add(col_index)
            _, span_cell, source_row, span_source_col, rowspan, colspan = span
            expanded_row.append(
                _cell_slot(
                    span_cell,
                    row_index=row_index,
                    col_index=col_index,
                    source_row=source_row,
                    source_col=span_source_col,
                    rowspan=rowspan,
                    colspan=colspan,
                    from_span=True,
                )
            )
            col_index += 1
            return True

        for cell in row.xpath("./th|./td"):
            while append_active_span():
                pass

            rowspan = _span_size(cell, "rowspan")
            colspan = _span_size(cell, "colspan")
            for offset in range(colspan):
                expanded_row.append(
                    _cell_slot(
                        cell,
                        row_index=row_index,
                        col_index=col_index + offset,
                        source_row=row_index,
                        source_col=source_col,
                        rowspan=rowspan,
                        colspan=colspan,
                        from_span=False,
                    )
                )
                if rowspan > 1:
                    active_spans[col_index + offset] = (
                        rowspan - 1,
                        cell,
                        row_index,
                        source_col,
                        rowspan,
                        colspan,
                    )
            col_index += colspan
            source_col += 1

        while active_spans and col_index <= max(active_spans):
            if not append_active_span():
                expanded_row.append(
                    {
                        "text": "",
                        "row_index": row_index,
                        "col_index": col_index,
                        "source_row": row_index,
                        "source_col": source_col,
                        "rowspan": 1,
                        "colspan": 1,
                        "from_span": False,
                    }
                )
                col_index += 1

        if any(slot["text"] for slot in expanded_row):
            grid.append(expanded_row)

        next_active_spans: dict[int, tuple[int, etree._Element, int, int, int, int]] = {}
        for active_col, (remaining, span_cell, source_row, span_source_col, rowspan, colspan) in active_spans.items():
            next_remaining = remaining - 1 if active_col in consumed_active_cols else remaining
            if next_remaining > 0:
                next_active_spans[active_col] = (
                    next_remaining,
                    span_cell,
                    source_row,
                    span_source_col,
                    rowspan,
                    colspan,
                )
        active_spans = next_active_spans

    return grid


def compress_repeated_texts(row: list[str]) -> list[str]:
    """Drop empty and consecutive duplicate values from an expanded row."""
    compressed: list[str] = []
    for value in row:
        cleaned = clean_text(value)
        if not cleaned or (compressed and compressed[-1] == cleaned):
            continue
        compressed.append(cleaned)
    return compressed


def extract_tables(document: html.HtmlElement) -> list[dict[str, Any]]:
    """Return all tables with raw span-aware cells and normalized logical rows."""
    tables: list[dict[str, Any]] = []
    for table_index, table in enumerate(document.xpath("//table")):
        grid = expand_table(table)
        logical_rows = [
            compress_repeated_texts([slot["text"] for slot in row])
            for row in grid
        ]
        logical_rows = [row for row in logical_rows if row]
        tables.append(
            {
                "index": table_index,
                "cells": grid,
                "logical_rows": logical_rows,
            }
        )
    return tables


def build_base_record(html_markup: str | bytes, *, file_path: str | Path, mode: str) -> dict[str, Any]:
    """Build the shared architecture-level parse record for a disclosure HTML file."""
    document = parse_html_document(html_markup)
    raw_tables = extract_tables(document)
    return {
        "acpt_no": extract_acpt_no(file_path),
        "source_file": str(Path(file_path).resolve()),
        "mode": mode,
        "title": extract_title(document),
        "raw_tables": raw_tables,
        "raw_rows": [row for table in raw_tables for row in table["logical_rows"]],
    }
