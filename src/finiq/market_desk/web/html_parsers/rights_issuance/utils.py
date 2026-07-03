"""유무상증자 파서 보조 함수 모음."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..common import (
    build_base_record,
    last_value,
    non_correction_rows,
    row_containing,
)

MODE = "rights_issuance"


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
        return last_value(self.containing(*needles))


def _build_rights_parse_context(
    html_text: str | bytes, *, file_path: str | Path
) -> _RightsParseContext:
    """공통 메타데이터를 생성하고 본문 HTML의 주요 행 데이터를 구성한다."""
    record = build_base_record(html_text, file_path=file_path, mode=MODE)
    rows = non_correction_rows(record["raw_tables"])
    issuance_type = _rights_issuance_type(str(record.get("title") or ""))
    return _RightsParseContext(
        record=record,
        rows=_RightsRows(rows),
        issuance_type=issuance_type,
    )
