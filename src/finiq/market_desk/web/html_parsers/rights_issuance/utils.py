"""유무상증자 파서 보조 함수 모음."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..common import (
    build_base_record,
    last_value,
    row_contains,
    row_containing,
)

MODE = "rights_issuance"
STOCK_LABELS = {
    "보통주식": ("보통주식", "보통주"),
    "기타주식": ("기타주식", "기타주", "우선주식", "우선주", "종류주식", "종류주"),
}
_RIGHTS_FIELD_NEEDLES = {
    "stock_counts": "신주의 종류와 수",
    "pre_issuance_stock_counts": "증자전",
    "funding_purposes": "자금조달의 목적",
    "issue_method": "증자방식",
    "issue_prices": "신주 발행가액",
    "payment_date": "납입일",
    "delivery_date": "신주권교부예정일",
    "listing_date": "신주의 상장 예정일",
    "allocation_date": "신주배정기준일",
    "allocation_ratio": "1주당 신주배정",
}
_RIGHTS_PRIMARY_FIELD_KINDS = {
    "stock_counts",
    "pre_issuance_stock_counts",
    "funding_purposes",
    "issue_method",
    "issue_prices",
    "allocation_date",
    "allocation_ratio",
}


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
    field_kinds = [_rights_field_kind(row) for row in rows]
    field_kinds = [kind for kind in field_kinds if kind is not None]
    if any(kind in _RIGHTS_PRIMARY_FIELD_KINDS for kind in field_kinds):
        return True
    return len(set(field_kinds)) >= 2


def _is_rights_section_marker_row(row: list[str]) -> bool:
    if len(row) != 1:
        return False
    text = row[0].replace(" ", "")
    return text in {
        "Ⅰ.유상증자",
        "I.유상증자",
        "1.유상증자",
        "Ⅱ.무상증자",
        "II.무상증자",
        "2.무상증자",
    }


def _rights_field_kind(row: list[str]) -> str | None:
    if len(row) < 2:
        return None
    for kind, needle in _RIGHTS_FIELD_NEEDLES.items():
        if row_contains([row[0]], needle):
            return kind
    return None
