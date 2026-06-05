"""유무상증자 파서 추출 로직."""

from __future__ import annotations

from typing import Any

from ..common import (
    parse_int,
    non_correction_tables,
    non_correction_rows,
    row_containing,
    row_contains,
    last_value,
    last_int,
    column_index,
    row_with_label,
)

FUNDING_PURPOSE_LABELS = [
    "시설자금",
    "영업양수자금",
    "운영자금",
    "채무상환자금",
    "타법인 증권 취득자금",
    "기타자금",
]
STOCK_LABELS = ["보통주식", "기타주식"]


class RightsIssuanceExtractor:
    """유무상증자 공시의 실제 필드별 추출 로직을 모아둔 클래스."""

    def __init__(self, raw_tables: list[dict[str, Any]]):
        self.raw_tables = raw_tables
        # 증자 관련 필드는 단일 테이블이 아닌 여러 테이블에 분산되어 있는 경우가 많다.
        # 다중 테이블 간 필드 조회를 위해 정정 신고가 아닌 논리적 행(row)을 모두 병합한다.
        self.non_correction_rows = non_correction_rows(self.raw_tables)

    def get_stock_types_and_counts(self) -> list[list[Any]]:
        return self._stock_values("신주의 종류와 수")

    def get_funding_purposes(self) -> list[list[Any]]:
        """자금조달 목적 항목(시설자금, 운영자금 등)을 일관된 순서로 반환한다."""
        purposes: list[list[Any]] = []
        for label in FUNDING_PURPOSE_LABELS:
            row = row_containing(self.non_correction_rows, "자금조달의 목적", label)
            value = parse_int(last_value(row), dash_as_zero=True)
            purposes.append([label, 0 if value is None else value])
        return purposes

    def get_issue_prices(self) -> list[list[Any]]:
        return self._stock_values("신주 발행가액")

    def get_base_prices(self) -> list[list[Any]]:
        return self._stock_values("기준주가")

    def get_issue_method(self) -> str | None:
        return last_value(row_containing(self.non_correction_rows, "증자방식"))

    def get_payment_date(self) -> str | None:
        return last_value(row_with_label(self.non_correction_rows, "납입일"))

    def get_delivery_date(self) -> str | None:
        return last_value(row_containing(self.non_correction_rows, "신주권교부예정일"))

    def get_listing_date(self) -> str | None:
        return last_value(row_containing(self.non_correction_rows, "신주의 상장 예정일"))

    def get_issue_targets(self) -> list[list[Any]]:
        """제3자 배정 대상자와 배정 주식 수를 추출한다."""
        for table in non_correction_tables(self.raw_tables):
            rows = table.get("logical_rows") or []
            if not rows or not row_contains(rows[0], "제3자배정 대상자", "배정주식수"):
                continue
            amount_idx = column_index(rows[0], "배정주식수")
            targets: list[list[Any]] = []
            for row in rows[1:]:
                if not row or row[0] == "-":
                    continue
                amount = (
                    parse_int(row[amount_idx])
                    if amount_idx is not None and amount_idx < len(row)
                    else last_int(row)
                )
                if amount is not None:
                    targets.append([row[0], amount])
            return targets
        return []

    def get_issue_target_entities(self) -> list[list[str]]:
        """배정 대상자의 명칭, 대표자 및 최대주주 상세 정보를 추출 및 그룹화한다."""
        entities: list[list[str]] = []
        for table in non_correction_tables(self.raw_tables):
            rows = table.get("logical_rows") or []
            if len(rows) < 3 or not row_contains(rows[0], "명칭", "대표이사", "최대주주"):
                continue
            grouped: dict[str, dict[str, list[str]]] = {}
            for row in rows[2:]:
                if len(row) < 3 or row[0] == "-":
                    continue
                values = grouped.setdefault(
                    row[0], {"representatives": [], "major_holders": []}
                )
                representative = row[2]
                if (
                    representative != "-"
                    and representative not in values["representatives"]
                ):
                    values["representatives"].append(representative)
                if len(row) >= 6:
                    major_holder = row[-2]
                    if major_holder != "-" and major_holder not in values["major_holders"]:
                        values["major_holders"].append(major_holder)
            for name, values in grouped.items():
                entities.append(
                    [name, *values["representatives"], *values["major_holders"]]
                )
        return entities

    def _stock_values(self, section_label: str) -> list[list[Any]]:
        """보통주와 기타주식 값을 일관된 순서로 배열하여 반환한다."""
        values: list[list[Any]] = []
        for stock_label in STOCK_LABELS:
            row = row_containing(self.non_correction_rows, section_label, stock_label)
            parsed = parse_int(last_value(row), dash_as_zero=True)
            values.append([stock_label, 0 if parsed is None else parsed])
        return values
