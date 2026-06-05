"""사채 발행 파서 보조 함수 모음."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..common import (
    build_base_record,
    fetch_selected_viewer_body,
    preserve_viewer_metadata,
    row_containing,
    row_with_label,
    value_after,
    last_value,
    last_int,
    row_contains,
    is_correction_chapter,
)

MODE = "bond_issuance"


@dataclass(frozen=True)
class _BondParseContext:
    """사채 필드 추출에 사용되는 준비된 데이터.

    `record`: 공통 메타데이터와 원본 테이블.
    `rows`: span 병합이 해제되어 정규화된 사채 발행 주요 테이블.
    """

    record: dict[str, Any]
    rows: "_BondRows"

    @property
    def raw_tables(self) -> list[dict[str, Any]]:
        return self.record["raw_tables"]


@dataclass(frozen=True)
class _BondRows:
    """정규화된 테이블 행(row) 데이터를 쉽게 다루기 위한 래퍼 클래스."""

    values: list[list[str]]

    def containing(self, *needles: str) -> list[str]:
        return row_containing(self.values, *needles)

    def with_label(self, label: str) -> list[str]:
        return row_with_label(self.values, label)

    def value_after(
        self, row_needle: str, label: str, *additional_needles: str
    ) -> str | None:
        return value_after(self.containing(row_needle, *additional_needles), label)

    def last_value(self, *needles: str) -> str | None:
        return last_value(self.containing(*needles))

    def last_labeled_value(self, label: str) -> str | None:
        return last_value(self.with_label(label))

    def last_int(self, *needles: str) -> int | None:
        return last_int(self.containing(*needles))


def _build_bond_parse_context(
    html_text: str | bytes, *, file_path: str | Path
) -> _BondParseContext:
    """공통 메타데이터를 생성하고 본문 HTML 및 주요 행 데이터를 구성한다."""
    record = build_base_record(html_text, file_path=file_path, mode=MODE)
    rows = _main_bond_rows(record["raw_tables"])
    if not rows:
        body_html = fetch_selected_viewer_body(html_text, file_path=file_path)
        if body_html is not None:
            viewer_record = record
            record = build_base_record(body_html, file_path=file_path, mode=MODE)
            preserve_viewer_metadata(record, viewer_record)
            rows = _main_bond_rows(record["raw_tables"])
    return _BondParseContext(record=record, rows=_BondRows(rows))


def _main_bond_rows(raw_tables: list[dict[str, Any]]) -> list[list[str]]:
    """정정 공시가 아닌 사채 발행 결정의 메인 테이블을 찾는다."""
    for table in raw_tables:
        if is_correction_chapter(table):
            continue
        rows = table.get("logical_rows") or []
        if (
            any(row_contains(row, "사채의 종류") for row in rows)
            and any(row_contains(row, "사채의 권면") for row in rows)
            and any(row_contains(row, "자금조달의 목적") for row in rows)
        ):
            return rows
    return []
