"""유무상증자 파서 보조 함수 모음."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..common import (
    build_base_record,
    last_value,
    normalize_label,
    row_contains,
    row_containing,
)

MODE = "rights_issuance"
STOCK_LABELS = {
    "보통주식": ("보통주식", "보통주"),
    "기타주식": ("기타주식", "기타주", "우선주식", "우선주", "종류주식", "종류주"),
}
_RIGHTS_PRIMARY_FIELD_LABELS = ("신주의 종류와 수", "신주 발행가액")


def _rights_issuance_type(title: str) -> str:
    """공시 제목만 사용해 증자 유형을 판정한다."""
    compact_title = title.replace(" ", "")
    if "유무상증자" in compact_title:
        return "mixed"
    if "무상증자" in compact_title:
        return "bonus"
    if "유상증자" in compact_title:
        return "paid"
    return "unknown"


@dataclass(frozen=True)
class _RightsParseContext:
    """유무상증자 필드 추출에 사용되는 준비된 데이터."""

    record: dict[str, Any]
    rows: "_RightsRows"
    issuance_type: str
    extraction_tables: list[dict[str, Any]]

    @property
    def raw_tables(self) -> list[dict[str, Any]]:
        return self.record["raw_tables"]


@dataclass(frozen=True)
class _RightsRows:
    """정규화된 테이블 행(row) 데이터를 쉽게 다루기 위한 래퍼 클래스."""

    values: list[list[str]]

    def containing(self, *needles: str) -> list[str]:
        return row_containing(self.values, *needles)

    def last_value(self, *needles: str) -> str | None:
        row = self.containing(*needles)
        return last_value(row) if len(row) > 1 else None


def _build_rights_parse_context(
    html_text: str | bytes, *, file_path: str | Path, title: str | None = None
) -> _RightsParseContext:
    """공통 메타데이터를 생성하고 본문 HTML의 주요 행 데이터를 구성한다."""
    record = build_base_record(html_text, file_path=file_path, mode=MODE)
    supplied_title = str(title or "").strip()
    record["title"] = supplied_title
    extraction_tables = _rights_extraction_tables(record["raw_tables"])
    rows = [
        row
        for table in extraction_tables
        for row in table.get("logical_rows") or []
    ]
    issuance_type = _rights_issuance_type(supplied_title)
    return _RightsParseContext(
        record=record,
        rows=_RightsRows(rows),
        issuance_type=issuance_type,
        extraction_tables=extraction_tables,
    )


def _rights_extraction_tables(raw_tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """필드 추출에 필요한 라벨이나 표 헤더가 있는 table만 선택한다."""
    return [
        table
        for table in raw_tables
        if _is_rights_extraction_table(table.get("logical_rows") or [])
    ]


def _is_rights_extraction_table(rows: list[list[str]]) -> bool:
    """유무상증자 필드 추출에 쓰이는 table인지 식별한다."""
    if not rows:
        return False
    if any(_is_rights_section_marker_row(row) for row in rows):
        return True
    if row_contains(rows[0], "제3자배정 대상자", "배정주식수"):
        return True
    return any(
        len(row) >= 2
        and any(row_contains([row[0]], label) for label in _RIGHTS_PRIMARY_FIELD_LABELS)
        for row in rows
    )


def _is_rights_section_marker_row(row: list[str]) -> bool:
    if len(row) != 1:
        return False
    text = row[0].replace(" ", "")
    normalized = normalize_label(text)
    return normalized != text and normalized in {"유상증자", "무상증자"}
