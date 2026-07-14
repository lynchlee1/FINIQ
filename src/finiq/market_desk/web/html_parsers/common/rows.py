"""논리적 행(row) 기반 필드 검색 및 추출 유틸리티."""

from __future__ import annotations

import re

from .text import clean_text, parse_int


def row_contains(row: list[str], *needles: str) -> bool:
    """행 데이터가 모든 검색어를 포함하는지 확인한다."""
    text = " ".join(row)
    compact_text = text.replace(" ", "")
    return all(
        needle in text or needle.replace(" ", "") in compact_text for needle in needles
    )


def row_containing(rows: list[list[str]], *needles: str) -> list[str]:
    """모든 검색어를 포함하는 첫 번째 행을 반환하며, 없으면 빈 리스트를 반환한다."""
    for row in rows:
        if row_contains(row, *needles):
            return row
    return []


def normalize_label(value: str) -> str:
    """공백을 제거한 뒤 맨 앞의 한 단계 또는 두 단계 숫자·로마자 번호를 제거한다."""
    compact_value = value.replace(" ", "")
    number = r"(?:\d+|[ivxlcdm]+|[\u2160-\u217f]+)"
    return re.sub(
        rf"^{number}(?:-{number})?\.",
        "",
        compact_value,
        flags=re.IGNORECASE,
    )


def row_with_label(rows: list[list[str]], label: str) -> list[str]:
    """번호가 제거된 라벨이 주어진 라벨과 정확히 일치하는 행을 반환한다."""
    compact_label = label.replace(" ", "")
    for row in rows:
        if any(
            normalize_label(clean_text(value)) == compact_label for value in row
        ):
            return row
    return []


def value_after(row: list[str], label: str) -> str | None:
    """동일한 행에서 특정 라벨 바로 우측에 위치한 셀 값을 반환한다."""
    for index, value in enumerate(row):
        if value == label and index + 1 < len(row):
            return row[index + 1]
    return None


def last_value(row: list[str]) -> str | None:
    """라벨/값 형태의 행에서 마지막 셀 데이터를 반환한다."""
    return row[-1] if row else None


def last_int(row: list[str]) -> int | None:
    """숫자 데이터는 주로 행의 끝에 위치하므로, 오른쪽부터 탐색하여 첫 번째 숫자를 반환한다."""
    for value in reversed(row):
        parsed = parse_int(value)
        if parsed is not None:
            return parsed
    return None


def column_index(row: list[str], label: str) -> int | None:
    """공백 제거 라벨을 기반으로 해당 열(column)의 인덱스를 찾는다."""
    for index, value in enumerate(row):
        if label in value.replace(" ", ""):
            return index
    return None
