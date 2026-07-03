"""유무상증자 파서 보조 함수 모음."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..common import (
    build_base_record,
    last_int,
    last_value,
    non_correction_rows,
    non_correction_tables,
    row_containing,
    row_contains,
    row_with_label,
)

MODE = "rights_issuance"


def _main_rights_rows(raw_tables: list[dict[str, Any]]) -> list[list[str]]:
    """본문이 유무상증자 결정 공시임을 나타내는 핵심 테이블을 탐색한다."""
    for table in non_correction_tables(raw_tables):
        rows = table.get("logical_rows") or []
        is_paid_issuance_table = (
            any(row_contains(row, "신주의 종류와 수") for row in rows)
            and any(row_contains(row, "자금조달의 목적") for row in rows)
            and any(row_contains(row, "증자방식") for row in rows)
        )
        is_bonus_issuance_table = (
            any(row_contains(row, "신주의 종류와 수") for row in rows)
            and any(row_contains(row, "신주배정기준일") for row in rows)
            and any(row_contains(row, "신주권교부예정일") for row in rows)
        )
        if is_paid_issuance_table or is_bonus_issuance_table:
            return rows
    return []


@dataclass(frozen=True)
class _RightsParseContext:
    """유무상증자 필드 추출에 사용되는 준비된 데이터."""

    record: dict[str, Any]
    rows: "_RightsRows"

    @property
    def raw_tables(self) -> list[dict[str, Any]]:
        return self.record["raw_tables"]


@dataclass(frozen=True)
class _RightsRows:
    """정규화된 테이블 행(row) 데이터를 쉽게 다루기 위한 래퍼 클래스."""

    values: list[list[str]]

    def containing(self, *needles: str) -> list[str]:
        return row_containing(self.values, *needles)

    def with_label(self, label: str) -> list[str]:
        return row_with_label(self.values, label)

    def last_value(self, *needles: str) -> str | None:
        return last_value(self.containing(*needles))

    def last_labeled_value(self, label: str) -> str | None:
        return last_value(self.with_label(label))

    def last_int(self, *needles: str) -> int | None:
        return last_int(self.containing(*needles))


def _build_rights_parse_context(
    html_text: str | bytes, *, file_path: str | Path
) -> _RightsParseContext:
    """공통 메타데이터를 생성하고 본문 HTML의 주요 행 데이터를 구성한다."""
    record = build_base_record(html_text, file_path=file_path, mode=MODE)
    rows = non_correction_rows(record["raw_tables"])
    return _RightsParseContext(record=record, rows=_RightsRows(rows))
