"""사채 발행 파서 보조 함수 모음."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..common import (
    build_base_record,
    clean_text,
    normalize_label,
)

MODE = "bond_issuance"


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

    def matching_rows(
        self,
        label_cell: int,
        labels: tuple[str, ...],
        *,
        starts_with: bool = False,
        additional_label_cells: tuple[tuple[int, tuple[str, ...]], ...] = (),
    ) -> list[list[str]]:
        """고정 위치의 정규화된 라벨이 일치하는 행만 반환한다."""
        return [
            row
            for row in self.values
            if _label_cell_matches(
                row,
                label_cell,
                labels,
                starts_with=starts_with,
            )
            and all(
                _label_cell_matches(row, cell_number, cell_labels)
                for cell_number, cell_labels in additional_label_cells
            )
        ]

    def first_row_at(
        self,
        label_cell: int,
        labels: tuple[str, ...],
        *,
        starts_with: bool = False,
        additional_label_cells: tuple[tuple[int, tuple[str, ...]], ...] = (),
    ) -> list[str]:
        """고정 위치의 라벨이 일치하는 첫 행을 반환한다."""
        rows = self.matching_rows(
            label_cell,
            labels,
            starts_with=starts_with,
            additional_label_cells=additional_label_cells,
        )
        return rows[0] if rows else []

    def last_value_at(
        self,
        label_cell: int,
        labels: tuple[str, ...],
        *,
        starts_with: bool = False,
        additional_label_cells: tuple[tuple[int, tuple[str, ...]], ...] = (),
    ) -> str | None:
        """고정 위치의 라벨이 일치하는 첫 행의 맨 오른쪽 값을 반환한다."""
        row = self.first_row_at(
            label_cell,
            labels,
            starts_with=starts_with,
            additional_label_cells=additional_label_cells,
        )
        required_label_cell = max(
            (label_cell, *(cell_number for cell_number, _ in additional_label_cells))
        )
        return row[-1] if len(row) > required_label_cell else None


def _label_cell_matches(
    row: list[str],
    cell_number: int,
    labels: tuple[str, ...],
    *,
    starts_with: bool = False,
) -> bool:
    index = cell_number - 1
    if index < 0 or index >= len(row):
        return False
    value = normalize_label(clean_text(row[index]))
    normalized_labels = tuple(normalize_label(label) for label in labels)
    if starts_with:
        return any(value.startswith(label) for label in normalized_labels)
    return value in normalized_labels


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
