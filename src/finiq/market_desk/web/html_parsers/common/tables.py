"""테이블 탐색, 병합 해제 및 정제 유틸리티."""

from __future__ import annotations

from typing import Any

from lxml import etree, html

from .text import clean_text, element_text


def _span_size(cell: etree._Element, attribute_name: str) -> int:
    """셀의 rowspan 또는 colspan 속성값을 양의 정수로 읽어온다."""
    raw_value = cell.get(attribute_name)
    if raw_value is None:
        return 1
    try:
        value = int(str(raw_value).strip())
    except ValueError:
        msg = f"invalid {attribute_name}: {raw_value!r}"
        raise ValueError(msg) from None
    if value < 1:
        msg = f"invalid {attribute_name}: {raw_value!r}"
        raise ValueError(msg)
    return value


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
    """단일 테이블 셀에 해당하는 정규화된 논리적 그리드 슬롯을 생성한다.

    병합(span)된 셀이 여러 슬롯을 차지할 때 원본 HTML의 좌표를 유지하여
    디버깅을 돕고 논리적 행 구조를 일관되게 유지한다.
    """
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
    """병합(rowspan/colspan)된 셀을 모든 해당 위치에 복사하여 테이블을 평면화한다.

    시각적 테이블을 단순한 그리드 형태로 변환하여, 파서가 HTML 레이아웃 차이에
    구애받지 않고 일관된 검색 및 추출을 수행할 수 있도록 한다.
    """
    active_spans: dict[int, tuple[int, etree._Element, int, int, int, int]] = {}
    grid: list[list[dict[str, Any]]] = []

    for row_index, row in enumerate(table.xpath(".//tr")):
        expanded_row: list[dict[str, Any]] = []
        col_index = 0
        source_col = 0
        consumed_active_cols: set[int] = set()

        def append_active_span() -> bool:
            """이전 행에서 이어져 내려오는 rowspan 데이터를 현재 열에 할당한다."""
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
            # 셀 파싱에 앞서, 현재 행의 선행 열을 차지하는 활성 rowspan 데이터를 채운다.
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
                    # 병합된 셀이 후속 행에도 영향을 미치므로 상태를 추적한다.
                    # 여러 열에 걸친 경우 개별 열마다 저장하여 향후 병합 셀과 일반 셀의 충돌을 방지한다.
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

        while append_active_span():
            pass

        if any(slot["text"] for slot in expanded_row):
            grid.append(expanded_row)

        next_active_spans: dict[
            int, tuple[int, etree._Element, int, int, int, int]
        ] = {}
        for active_col, (
            remaining,
            span_cell,
            source_row,
            span_source_col,
            rowspan,
            colspan,
        ) in active_spans.items():
            # 실제로 사용된 span 데이터에 한해서만 남은 행 수를 차감한다.
            # 깨진 마크업으로 인해 누락이 발생하더라도 병합 구조를 최대한 유지한다.
            next_remaining = (
                remaining - 1 if active_col in consumed_active_cols else remaining
            )
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
    """행 데이터에서 빈 값 및 연속된 중복 값을 제거하여 압축한다.

    테이블 평면화로 인해 의도적으로 반복된 라벨 노이즈를 제거하면서도
    핵심 정보의 순서는 유지하여 분석 가독성을 높인다.
    """
    compressed: list[str] = []
    for value in row:
        cleaned = clean_text(value)
        if not cleaned:
            continue
        if compressed and compressed[-1] == cleaned:
            continue
        compressed.append(cleaned)
    return compressed


def extract_tables(document: html.HtmlElement) -> list[dict[str, Any]]:
    """문서 내 모든 테이블을 평면화된 그리드 및 정규화된 논리 행(row) 형태로 반환한다.

    `cells`는 전체 형태가 보존된 디버깅용 데이터이며,
    `positional_rows`는 열 위치를 보존하고 `logical_rows`는 라벨 검색용으로 압축한다.
    """
    tables: list[dict[str, Any]] = []
    for table_index, table in enumerate(document.xpath("//table")):
        grid = expand_table(table)
        positional_rows = [
            [clean_text(slot["text"]) for slot in row] for row in grid
        ]
        logical_rows = [
            compress_repeated_texts([slot["text"] for slot in row]) for row in grid
        ]
        logical_rows = [row for row in logical_rows if row]
        tables.append(
            {
                "index": table_index,
                "chapter_title": _nearest_chapter_title(table),
                "cells": grid,
                "positional_rows": positional_rows,
                "logical_rows": logical_rows,
            }
        )
    return tables


def extract_table_rows(document: html.HtmlElement) -> list[list[str]]:
    """문서 내 모든 테이블의 행(row) 데이터를 정규화된 텍스트 리스트로 반환한다."""
    rows: list[list[str]] = []
    for table in extract_tables(document):
        rows.extend(table["logical_rows"])
    return rows


def _nearest_chapter_title(table: etree._Element) -> str:
    """원문 미리보기에 표시할 가장 가까운 상위 섹션 제목을 탐색한다."""
    chapter_nodes = table.xpath(
        "preceding::*["
        "self::h1 or self::h2 or self::h3 or self::h4 or self::h5 or self::h6 or "
        "(self::p and contains(concat(' ', normalize-space(@class), ' '), ' CORRECTION ')) or "
        "(self::p and contains(concat(' ', normalize-space(@class), ' '), ' SECTION-')) or "
        "(self::p and contains(concat(' ', normalize-space(@class), ' '), ' COVER-TITLE '))"
        "][1]"
    )
    if not chapter_nodes:
        return ""
    return element_text(chapter_nodes[0])
