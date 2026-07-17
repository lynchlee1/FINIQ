"""Extract tables from KIND list HTML and emit JSON by parse mode."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from bs4 import BeautifulSoup, Tag

from ._markup import get_tag_attributes, parse_html_with_recovery, _tag_inner_html, _tag_text

ParseMode = Literal["tables", "cells", "rows", "simpletable"]
_TABLE_SECTION_NAMES = ("thead", "tbody", "tfoot")


def _serialize_link(link_tag: Tag) -> dict[str, Any]:
    """링크 태그를 JSON 친화적인 structure로 serialize한다."""
    return {
        "text": _tag_text(link_tag),
        "href": link_tag.get("href"),
        "attrs": get_tag_attributes(link_tag),
    }


def _serialize_cell(cell_tag: Tag) -> dict[str, Any]:
    """셀 태그 1개를 텍스트, 속성, 링크 정보로 serialize한다."""
    return {
        "tag": cell_tag.name,
        "text": _tag_text(cell_tag),
        "html": _tag_inner_html(cell_tag),
        "attrs": get_tag_attributes(cell_tag),
        "links": [_serialize_link(link_tag) for link_tag in cell_tag.find_all("a")],
    }


def _serialize_row(row_tag: Tag) -> dict[str, Any]:
    """행 태그 1개를 셀 목록 중심 structure로 serialize한다."""
    return {
        "attrs": get_tag_attributes(row_tag),
        "cells": [
            _serialize_cell(cell_tag)
            for cell_tag in row_tag.find_all(["th", "td"], recursive=False)
        ],
    }


def _serialize_rows(parent_tag: Tag) -> list[dict[str, Any]]:
    """부모 태그 바로 아래의 행들만 serialize한다."""
    return [
        _serialize_row(row_tag)
        for row_tag in parent_tag.find_all("tr", recursive=False)
    ]


def _collect_table_sections(table_tag: Tag) -> dict[str, list[dict[str, Any]]]:
    """테이블의 명시적인 section별 행을 모아 표준 structure로 정리한다."""
    sections = {section_name: [] for section_name in _TABLE_SECTION_NAMES}
    for section_name in _TABLE_SECTION_NAMES:
        for section_tag in table_tag.find_all(section_name, recursive=False):
            sections[section_name].extend(_serialize_rows(section_tag))
    return sections


def _serialize_table(table_tag: Tag, table_index: int) -> dict[str, Any]:
    """테이블 태그 1개를 전체 serialization structure로 변환한다."""
    caption_tag = table_tag.find("caption", recursive=False)
    colgroup_tag = table_tag.find("colgroup", recursive=False)
    return {
        "index": table_index,
        "attrs": get_tag_attributes(table_tag),
        "caption": _tag_text(caption_tag) if caption_tag else "",
        "colgroup_html": _tag_inner_html(colgroup_tag) if colgroup_tag else "",
        "sections": _collect_table_sections(table_tag),
        "html": str(table_tag),
    }


def _extract_table_data_from_soup(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """문서 안의 모든 테이블을 순서대로 serialize한다."""
    return [
        _serialize_table(table_tag, table_index)
        for table_index, table_tag in enumerate(soup.find_all("table"))
    ]


def _extract_first_link_onclick(cell_data: dict[str, Any]) -> str | None:
    """셀의 첫 링크에서 `onclick` 값만 뽑아낸다."""
    links = cell_data.get("links") or []
    if not links:
        return None
    link_attributes = links[0].get("attrs") or {}
    onclick_value = link_attributes.get("onclick")
    if onclick_value is None:
        return None
    if isinstance(onclick_value, list):
        return str(onclick_value[0]) if onclick_value else None
    return str(onclick_value)


def _iter_table_body_rows(
    table_data: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """각 테이블의 `tbody` 행 목록을 순서대로 꺼낸다."""
    return [table.get("sections", {}).get("tbody", []) for table in table_data]


def _build_flat_cell_list(table_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """테이블 structure를 셀 단위 flat list로 바꾼다."""
    flat_cells: list[dict[str, Any]] = []
    for body_rows in _iter_table_body_rows(table_data):
        for row_index, row_data in enumerate(body_rows):
            for cell_index, cell_data in enumerate(row_data.get("cells", [])):
                flat_cells.append(
                    {
                        "row_index": row_index,
                        "cell_index": cell_index,
                        **cell_data,
                    }
                )
    return flat_cells


def _build_flat_row_list(table_data: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """테이블 structure를 간단한 행 단위 list로 바꾼다.

    각 셀에는 화면 텍스트와 첫 링크의 `onclick`만 남겨서,
    후속 처리에서 표 데이터를 가볍게 다루기 쉽게 만든다.
    """
    flat_rows: list[list[dict[str, Any]]] = []
    for body_rows in _iter_table_body_rows(table_data):
        for row_data in body_rows:
            row_index = len(flat_rows)
            flat_rows.append(
                [
                    {
                        "row_index": row_index,
                        "cell_index": cell_index,
                        "text": cell_data.get("text", ""),
                        "links": _extract_first_link_onclick(cell_data),
                    }
                    for cell_index, cell_data in enumerate(row_data.get("cells", []))
                ]
            )
    return flat_rows


def _build_simple_table(table_data: list[dict[str, Any]]) -> list[list[str]]:
    """`tbody` 행만 모아 원래 열 수의 셀 텍스트 목록으로 만든다."""
    text_rows: list[list[str]] = []
    for body_rows in _iter_table_body_rows(table_data):
        for row_data in body_rows:
            text_rows.append(
                [str(cell_data.get("text", "")) for cell_data in row_data.get("cells", [])]
            )
    return text_rows


def _build_json_output(table_data: list[dict[str, Any]], mode: ParseMode) -> dict[str, Any]:
    """요청한 parsing mode에 맞는 최종 JSON structure를 만든다."""
    if mode == "tables":
        return {"tables": table_data}
    if mode == "cells":
        return {"cells": _build_flat_cell_list(table_data)}
    if mode == "rows":
        return {"rows": _build_flat_row_list(table_data)}
    if mode == "simpletable":
        return {"simpletable": _build_simple_table(table_data)}
    msg = f"unsupported parse mode: {mode!r}"
    raise ValueError(msg)


def html_to_json(
    html_markup: str | bytes,
    *,
    mode: ParseMode = "tables",
) -> dict[str, Any]:
    """KIND HTML markup을 JSON serialization 가능한 structure로 변환한다.

    입력 HTML을 복구 파싱한 뒤,
    필요에 따라 테이블 전체 structure, flat 셀/행 structure,
    또는 원래 행별 열 수를 유지한 `list[list[str]]` (`simpletable`)로 내보낸다.
    """
    soup = parse_html_with_recovery(html_markup)
    table_data = _extract_table_data_from_soup(soup)
    return _build_json_output(table_data, mode)


def file_to_json(
    file_path: str | Path,
    *,
    mode: ParseMode = "tables",
) -> dict[str, Any]:
    """KIND HTML file을 읽어서 JSON structure로 변환한다."""
    html_file_path = Path(file_path)
    html_markup = html_file_path.read_bytes()
    return html_to_json(html_markup, mode=mode)
