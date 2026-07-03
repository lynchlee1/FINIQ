"""유무상증자 파서 추출 로직."""

from __future__ import annotations

from typing import Any

from ..common import (
    column_index,
    last_int,
    non_correction_tables,
    parse_int,
    row_contains,
)
from .utils import _RightsParseContext

RIGHTS_FIELD_EXTRACTION_RULES = {
    "신주의 종류와 수": "메인 표 > '신주의 종류와 수' 행 > 주식 종류별 마지막 숫자",
    "발행목적": "메인 표 > '자금조달의 목적' 행 > 목적별 마지막 숫자",
    "발행가액": "메인 표 > '신주 발행가액' 행 > 주식 종류별 마지막 숫자",
    "기준주가": "메인 표 > '기준주가' 행 > 주식 종류별 마지막 숫자",
    "증자방식": "메인 표 > '증자방식' 행 > 마지막 값",
    "납입일": "메인 표 > '납입일' 라벨 행 > 마지막 값",
    "신주권교부예정일": "메인 표 > '신주권교부예정일' 라벨 행 > 마지막 값",
    "상장예정일": "메인 표 > '신주의 상장 예정일'|'신주의 상장예정일' 라벨 행 > 마지막 값",
    "발행대상자": "'제3자배정 대상자' 표 > 대상자명 + 배정주식수",
}
FUNDING_PURPOSE_LABELS = [
    "시설자금",
    "영업양수자금",
    "운영자금",
    "채무상환자금",
    "타법인 증권 취득자금",
    "기타자금",
]
STOCK_LABELS = {
    "보통주식": ("보통주식", "보통주"),
    "기타주식": ("기타주식", "기타주", "우선주식", "우선주"),
}


class RightsIssuanceExtractor:
    """유무상증자 공시의 실제 필드별 추출 로직을 모아둔 클래스."""

    def __init__(self, context: _RightsParseContext):
        self.context = context
        self.rows = context.rows
        self.warnings: list[str] = []

    def is_bonus_issuance(self) -> bool:
        title = str(self.context.record.get("title") or "")
        return "무상증자" in title

    def is_subsidiary_disclosure(self) -> bool:
        title = str(self.context.record.get("title") or "")
        return "종속회사" in title

    def has_not_applicable_issue_method(self) -> bool:
        return self.rows.last_value("증자방식") == "해당사항없음"

    def price_and_payment_are_optional(self) -> bool:
        return self.is_bonus_issuance() or self.has_not_applicable_issue_method()

    def get_stock_types_and_counts(self) -> list[list[Any]]:
        return self._stock_values("신주의 종류와 수", warn_when_all_missing=True)

    def get_funding_purposes(self) -> list[list[Any]]:
        """자금조달 목적 항목(시설자금, 운영자금 등)을 일관된 순서로 반환한다."""
        purposes: list[list[Any]] = []
        for label in FUNDING_PURPOSE_LABELS:
            row = self.rows.containing("자금조달의 목적", label)
            value = parse_int(row[-1], dash_as_zero=True) if row else None
            purposes.append([label, 0 if value is None else value])
        return purposes

    def get_issue_prices(self) -> list[list[Any]]:
        return self._stock_values(
            "신주 발행가액",
            warning_field_name="발행가액",
            warn_when_all_missing=not self.price_and_payment_are_optional(),
        )

    def get_base_prices(self) -> list[list[Any]]:
        return self._stock_values("기준주가")

    def get_issue_method(self) -> str | None:
        value = self.rows.last_value("증자방식")
        if value is None and self.is_bonus_issuance():
            value = "무상증자"
        self._warn_if_missing("증자방식", value)
        return value

    def get_payment_date(self) -> str | None:
        value = self.rows.last_labeled_value("납입일")
        if not self.price_and_payment_are_optional():
            self._warn_if_missing("납입일", value)
        return value

    def get_delivery_date(self) -> str | None:
        value = self.rows.last_labeled_value("신주권교부예정일")
        return value

    def get_listing_date(self) -> str | None:
        value = self.rows.last_labeled_value("신주의 상장 예정일")
        if value is None:
            value = self.rows.last_labeled_value("신주의 상장예정일")
        return value

    def get_issue_targets(self) -> list[list[Any]]:
        """제3자 배정 대상자와 배정 주식 수를 추출한다."""
        for table in non_correction_tables(self.context.raw_tables):
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
        issue_method = self.get_issue_method()
        if (
            issue_method
            and "제3자배정" in issue_method
            and not self.is_subsidiary_disclosure()
        ):
            self._warn_if_missing("발행대상자", None)
        return []

    def get_issue_target_entities(self) -> list[list[str]]:
        """배정 대상자의 명칭, 대표자 및 최대주주 상세 정보를 추출 및 그룹화한다."""
        entities: list[list[str]] = []
        for table in non_correction_tables(self.context.raw_tables):
            rows = table.get("logical_rows") or []
            if len(rows) < 3 or not row_contains(
                rows[0], "명칭", "대표이사", "최대주주"
            ):
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
                    if (
                        major_holder != "-"
                        and major_holder not in values["major_holders"]
                    ):
                        values["major_holders"].append(major_holder)
            for name, values in grouped.items():
                entities.append(
                    [name, *values["representatives"], *values["major_holders"]]
                )
        return entities

    def _stock_values(
        self,
        section_label: str,
        *,
        warning_field_name: str | None = None,
        warn_when_all_missing: bool = False,
    ) -> list[list[Any]]:
        """보통주와 기타주식 값을 일관된 순서로 배열하여 반환한다."""
        values: list[list[Any]] = []
        missing_count = 0
        for output_label, source_labels in STOCK_LABELS.items():
            parsed = self._stock_value(section_label, source_labels)
            if parsed is None:
                missing_count += 1
            values.append([output_label, 0 if parsed is None else parsed])
        if warn_when_all_missing and missing_count == len(STOCK_LABELS):
            self._warn_if_missing(warning_field_name or section_label, None)
        return values

    def _stock_value(
        self, section_label: str, source_labels: tuple[str, ...]
    ) -> int | None:
        dash_seen = False
        for row in self.rows.values:
            if not row_contains(row, section_label):
                continue
            for index, cell in enumerate(row):
                if not any(label in cell.replace(" ", "") for label in source_labels):
                    continue
                if index + 1 >= len(row):
                    continue
                parsed = parse_int(row[index + 1], dash_as_zero=True)
                if parsed is None:
                    continue
                if parsed == 0:
                    dash_seen = True
                    continue
                return parsed
        return 0 if dash_seen else None

    def _warn_if_missing(self, field_name: str, value: object | None) -> None:
        if value not in (None, "", []):
            return
        rule = RIGHTS_FIELD_EXTRACTION_RULES[field_name]
        warning = f"{field_name}: 정해진 출처에서 값을 찾지 못했습니다. 출처: {rule}"
        if warning not in self.warnings:
            self.warnings.append(warning)
