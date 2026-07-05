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
from .utils import STOCK_LABELS, _RightsParseContext

RIGHTS_FIELD_EXTRACTION_RULES = {
    "신주의 종류와 수": "메인 표 > '신주의 종류와 수' 행 > 주식 종류별 마지막 숫자",
    "증자 전 발행주식총수": "메인 표 > '증자전 발행주식총수' 행 > 주식 종류별 마지막 숫자",
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
ISSUE_TARGET_TOTAL_LABEL_TOKENS = {"계", "합계", "소계", "총계"}


class RightsIssuanceExtractor:
    """유무상증자 공시의 실제 필드별 추출 로직을 모아둔 클래스."""

    def __init__(self, context: _RightsParseContext):
        self.context = context
        self.rows = context.rows
        self.warnings: list[str] = []
        self.weak_warnings: list[str] = []
        self.medium_warnings: list[str] = []
        self.strong_warnings: list[str] = []
        self.field_parse_status: dict[str, str] = {}

    def get_stock_types_and_counts(self) -> list[list[Any]]:
        """신주의 종류별 발행 수량을 보통주/기타주식 순서로 추출한다."""
        return self._stock_values("신주의 종류와 수", warn_when_all_missing=True)

    def get_pre_issuance_stock_counts(self) -> list[list[Any]]:
        """증자 전 발행주식총수를 주식 종류별로 추출한다."""
        return self._stock_values(
            "증자전 발행주식총수",
            warning_field_name="증자 전 발행주식총수",
        )

    def get_funding_purposes(self) -> list[list[Any]]:
        """자금조달 목적 항목(시설자금, 운영자금 등)을 일관된 순서로 반환한다."""
        purposes: list[list[Any]] = []
        found_purpose_amount = False
        for label in FUNDING_PURPOSE_LABELS:
            row = self.rows.containing("자금조달의 목적", label)
            value = parse_int(row[-1], dash_as_zero=True) if row else None
            if value is not None:
                found_purpose_amount = True
            if value:
                purposes.append([label, value])
        if found_purpose_amount:
            self._set_field_status(
                "발행목적", "parsed" if purposes else "explicit_zero"
            )
        else:
            self._set_field_status("발행목적", "source_not_found")
        return purposes

    def validate_consistency(
        self,
        *,
        stock_counts: list[list[Any]],
        funding_purposes: list[list[Any]],
        base_prices: list[list[Any]],
        issue_targets: list[list[Any]],
    ) -> None:
        """추출 필드 간 합계 검증 경고를 레벨별로 분류한다."""
        stock_total = self._sum_amounts(stock_counts)
        target_total = self._sum_amounts(issue_targets)
        if issue_targets and target_total != stock_total:
            self._append_warning(
                f"발행대상자: 배정주식수 합계({target_total:,})가 신주의 종류와 수 합계({stock_total:,})와 일치하지 않습니다.",
                level="weak",
            )

        funding_total = self._sum_amounts(funding_purposes)
        stock_value_total = self._stock_value_total(stock_counts, base_prices)
        if (
            funding_purposes
            and stock_value_total is not None
            and abs(stock_value_total - funding_total) > 9
        ):
            self._append_warning(
                f"발행목적: 신주의 종류와 수와 기준주가의 곱({stock_value_total:,})이 자금조달 목적 합계({funding_total:,})와 일치하지 않습니다.",
                level="weak",
            )

        nonzero_stock_types = [
            item for item in stock_counts if self._item_amount(item) > 0
        ]
        if len(nonzero_stock_types) > 1:
            labels = ", ".join(str(item[0]) for item in nonzero_stock_types)
            self._append_warning(
                f"신주의 종류와 수: 0이 아닌 주식 종류가 둘 이상입니다. 종류: {labels}",
                level="medium",
            )
        if stock_counts and stock_total == 0:
            self._append_warning(
                "신주의 종류와 수: 모든 주식 종류의 수량이 0입니다.",
                level="medium",
            )

    def get_issue_prices(self) -> list[list[Any]]:
        """신주 발행가액을 주식 종류별로 추출한다."""
        return self._stock_values(
            "신주 발행가액",
            warning_field_name="발행가액",
            warn_when_all_missing=not (
                self.context.issuance_type == "bonus"
                or self.rows.last_value("증자방식") == "해당사항없음"
            ),
        )

    def get_base_prices(self) -> list[list[Any]]:
        """기준주가를 주식 종류별로 추출한다."""
        return self._stock_values("기준주가")

    def get_issue_method(self) -> str | None:
        """증자방식을 추출하고 무상증자 공시는 제목 기반 분류값으로 보완한다."""
        value = self.rows.last_value("증자방식")
        if value is None and self.context.issuance_type == "bonus":
            value = "무상증자"
        self._warn_if_missing("증자방식", value)
        if value is not None:
            self._set_field_status("증자방식", "parsed")
        return value

    def get_payment_date(self) -> str | None:
        """납입일을 추출하되 선택 필드인 공시에서는 누락 경고를 생략한다."""
        value = self.rows.last_value("납입일")
        if not (
            self.context.issuance_type == "bonus"
            or self.rows.last_value("증자방식") == "해당사항없음"
        ):
            self._warn_if_missing("납입일", value)
        self._set_field_status(
            "납입일", "parsed" if value is not None else "source_not_found"
        )
        return value

    def get_delivery_date(self) -> str | None:
        """신주권교부예정일을 추출한다."""
        value = self.rows.last_value("신주권교부예정일")
        self._set_field_status(
            "신주권교부예정일", "parsed" if value is not None else "source_not_found"
        )
        return value

    def get_listing_date(self) -> str | None:
        """신주의 상장 예정일을 추출한다."""
        value = self.rows.last_value("신주의 상장 예정일")
        self._set_field_status(
            "상장예정일", "parsed" if value is not None else "source_not_found"
        )
        return value

    def get_issue_targets(self, *, stock_counts: list[list[Any]]) -> list[list[Any]]:
        """제3자 배정 대상자와 배정 주식 수를 추출한다."""
        for table in non_correction_tables(self.context.raw_tables):
            rows = table.get("logical_rows") or []
            if not rows or not row_contains(rows[0], "제3자배정 대상자", "배정주식수"):
                continue
            amount_idx = column_index(rows[0], "배정주식수")
            data_rows = rows[1:]
            if self._is_undisclosed_issue_target_rows(data_rows, amount_idx):
                self._set_field_status("발행대상자", "explicit_zero")
                return [["-", 0]]
            targets: list[list[Any]] = []
            for row in data_rows:
                if not row or row[0] == "-":
                    continue
                amount_from_declared_column = (
                    amount_idx is not None and amount_idx < len(row)
                )
                amount = (
                    parse_int(row[amount_idx])
                    if amount_from_declared_column
                    else last_int(row)
                )
                if amount is not None:
                    targets.append([row[0], amount])
            targets = self._exclude_bottom_duplicate_total_target(
                targets,
                stock_total=self._sum_amounts(stock_counts),
            )
            if targets:
                self._set_field_status("발행대상자", "parsed")
                return targets
            self._set_field_status("발행대상자", "source_found_empty")
            return []
        issue_method = self.get_issue_method()
        title = str(self.context.record.get("title") or "")
        if issue_method and "제3자배정" in issue_method and "종속회사" not in title:
            self._warn_if_missing("발행대상자", None)
        return []

    def _is_undisclosed_issue_target_rows(
        self, data_rows: list[list[str]], amount_idx: int | None
    ) -> bool:
        if not data_rows:
            return False
        for row in data_rows:
            if not row or row[0].strip() != "-":
                return False
            amount = (
                parse_int(row[amount_idx])
                if amount_idx is not None and amount_idx < len(row)
                else last_int(row)
            )
            if amount is not None:
                return False
        return True

    def _exclude_bottom_duplicate_total_target(
        self,
        targets: list[list[Any]],
        *,
        stock_total: int,
    ) -> list[list[Any]]:
        if len(targets) < 2 or stock_total <= 0:
            return targets
        if not self._has_issue_target_total_label_token(targets[-1][0]):
            return targets
        target_total = self._sum_amounts(targets)
        bottom_amount = self._item_amount(targets[-1])
        if target_total == stock_total * 2 and bottom_amount == stock_total:
            return targets[:-1]
        return targets

    def _has_issue_target_total_label_token(self, value: object) -> bool:
        return any(
            token in ISSUE_TARGET_TOTAL_LABEL_TOKENS
            for token in str(value).strip().split()
        )

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
        field_name = warning_field_name or section_label
        if any(value > 0 for _, value in values):
            self._set_field_status(field_name, "parsed")
        elif missing_count < len(STOCK_LABELS):
            self._set_field_status(field_name, "explicit_zero")
        else:
            self._set_field_status(field_name, "source_not_found")
        if warn_when_all_missing and missing_count == len(STOCK_LABELS):
            self._warn_if_missing(field_name, None)
        return values

    def _stock_value(
        self, section_label: str, source_labels: tuple[str, ...]
    ) -> int | None:
        """지정 구간에서 주식 종류 라벨 바로 다음 값을 숫자로 변환한다."""
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

    def _stock_value_total(
        self, stock_counts: list[list[Any]], base_prices: list[list[Any]]
    ) -> int | None:
        base_price_by_label = {
            str(item[0]): self._item_amount(item) for item in base_prices if item
        }
        total = 0
        matched = False
        for item in stock_counts:
            if not item:
                continue
            label = str(item[0])
            if label not in base_price_by_label:
                continue
            if base_price_by_label[label] <= 0:
                continue
            matched = True
            total += self._item_amount(item) * base_price_by_label[label]
        return total if matched else None

    def _sum_amounts(self, rows: list[list[Any]]) -> int:
        return sum(self._item_amount(row) for row in rows)

    def _item_amount(self, row: list[Any]) -> int:
        if not row:
            return 0
        value = row[-1]
        return value if isinstance(value, int) else 0

    def _warn_if_missing(self, field_name: str, value: object | None) -> None:
        if value not in (None, "", []):
            return
        rule = RIGHTS_FIELD_EXTRACTION_RULES[field_name]
        warning = f"{field_name}: 정해진 출처에서 값을 찾지 못했습니다. 출처: {rule}"
        self._set_field_status(field_name, "source_not_found")
        self._append_warning(warning, level="medium")

    def _set_field_status(self, field_name: str, status: str) -> None:
        self.field_parse_status[field_name] = status

    def _append_warning(self, warning: str, *, level: str) -> None:
        target = {
            "weak": self.weak_warnings,
            "medium": self.medium_warnings,
            "strong": self.strong_warnings,
        }[level]
        if warning not in target:
            target.append(warning)
        if warning not in self.warnings:
            self.warnings.append(warning)
