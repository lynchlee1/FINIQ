"""유무상증자 파서 보조 함수 모음."""

from __future__ import annotations

from typing import Any

from ..common import non_correction_tables, row_contains


def _main_rights_rows(raw_tables: list[dict[str, Any]]) -> list[list[str]]:
    """본문이 유무상증자 결정 공시임을 나타내는 핵심 테이블을 탐색한다."""
    for table in non_correction_tables(raw_tables):
        rows = table.get("logical_rows") or []
        if (
            any(row_contains(row, "신주의 종류와 수") for row in rows)
            and any(row_contains(row, "자금조달의 목적") for row in rows)
            and any(row_contains(row, "증자방식") for row in rows)
        ):
            return rows
    return []
