"""사채 발행 파서 보조 함수 모음."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..common import (
    build_base_record,
    clean_text,
    last_int,
    last_value,
    row_containing,
    row_with_label,
    value_after,
)

MODE = "bond_issuance"
_EXERCISE_TARGET_COMPANY_NAME_REPLACEMENTS = (
    r"\(주\)",
    r"㈜",
    r"주식회사",
    r"기명식",
    r"무기명식",
    r"보통주식?",
    r"보통주?",
    r"주식",
)


def _clean_exercise_target_company_name(value: str) -> str | None:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    for pattern in _EXERCISE_TARGET_COMPANY_NAME_REPLACEMENTS:
        cleaned = re.sub(pattern, " ", cleaned)
    cleaned = clean_text(cleaned.strip(" -_/·,"))
    return cleaned or clean_text(value)


def _clean_funding_purpose_label(value: str) -> str | None:
    label = clean_text(value)
    label = re.sub(r"\(\s*원\s*\)", "", label)
    label = re.sub(r"\s*원$", "", label)
    label = clean_text(label.strip(" -_/·,"))
    return label or None


@dataclass(frozen=True)
class _BondParseContext:
    """사채 필드 추출에 사용되는 준비된 데이터.

    `record`: 공통 메타데이터와 원본 테이블.
    """

    record: dict[str, Any]

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
    """공통 메타데이터를 생성하고 본문 HTML의 주요 행 데이터를 구성한다."""
    record = build_base_record(
        html_text,
        file_path=file_path,
        mode=MODE,
    )
    return _BondParseContext(record=record)
