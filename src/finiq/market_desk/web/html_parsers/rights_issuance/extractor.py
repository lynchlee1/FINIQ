"""유무상증자 파서 추출 로직."""

from __future__ import annotations

import re
from typing import Any

from ..common import (
    column_index,
    parse_int,
    parse_ints,
    row_contains,
)
from .utils import STOCK_LABELS, _RightsParseContext

RIGHTS_FIELD_EXTRACTION_RULES = {
    "신주의 종류와 수": "메인 표 > '신주의 종류와 수' 행 > 주식 종류별 마지막 숫자",
    "증자 전 발행주식총수": "메인 표 > '증자전 발행주식총수' 행 > 주식 종류별 마지막 숫자",
    "발행목적": "메인 표 > '자금조달의 목적' 행 > 목적별 마지막 숫자",
    "발행가액": "메인 표 > '신주 발행가액' 행 > 주식 종류별 마지막 숫자",
    "증자방식": "메인 표 > '증자방식' 행 > 마지막 값",
    "납입일": "메인 표 > '납입일' 라벨 행 > 마지막 값",
    "신주권교부예정일": "메인 표 > '신주권교부예정일' 라벨 행 > 마지막 값",
    "상장예정일": "메인 표 > '신주의 상장 예정일'|'신주의 상장예정일' 라벨 행 > 마지막 값",
    "발행대상자": "'제3자배정 대상자' 표 > 대상자명 + 배정주식수",
}
FUNDING_PURPOSE_LABELS = [
    ("시설자금", ("시설자금",)),
    ("영업양수자금", ("영업양수자금",)),
    ("운영자금", ("운영자금",)),
    ("채무상환자금", ("채무상환자금",)),
    (
        "타법인 증권 취득자금",
        ("타법인 증권 취득자금", "타법인유가증권취득자금"),
    ),
    ("기타자금", ("기타자금",)),
]
ISSUE_TARGET_TOTAL_LABEL_TOKENS = {"계", "합계", "소계", "총계"}
STOCK_STATUS_DETAIL_FIELDS = {"신주의 종류와 수", "증자 전 발행주식총수"}
ISSUANCE_TYPE_LABELS = {
    "paid": "유상증자",
    "bonus": "무상증자",
    "mixed": "유무상증자",
    "unknown": "unknown",
}


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
        self.field_parse_status_detail: dict[str, dict[str, str]] = {}

    def get_stock_types_and_counts(self) -> list[list[Any]]:
        """신주의 종류별 발행 수량을 보통주/기타주식 순서로 추출한다."""
        return self._stock_values("신주의 종류와 수", warn_when_all_missing=True)

    def get_pre_issuance_stock_counts(self) -> list[list[Any]]:
        """증자 전 발행주식총수를 주식 종류별로 추출한다."""
        return self._stock_values(
            "증자전 발행주식총수",
            warning_field_name="증자 전 발행주식총수",
        )

    def get_funding_purposes(self) -> list[list[Any]] | str:
        """자금조달 목적 항목(시설자금, 운영자금 등)을 일관된 순서로 반환한다."""
        if self.context.issuance_type == "bonus":
            self._set_field_status("발행목적", "not_applicable")
            return "-"
        purposes: list[list[Any]] = []
        found_purpose_amount = False
        for label, source_labels in FUNDING_PURPOSE_LABELS:
            row = self._funding_purpose_row(source_labels)
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
            self._warn_if_missing("발행목적", None)
        return purposes

    def validate_consistency(
        self,
        *,
        stock_counts: list[list[Any]],
        pre_issuance_stock_counts: list[list[Any]],
        funding_purposes: list[list[Any]] | str,
        issue_prices: list[list[Any]] | str,
        issue_targets: list[list[Any]] | str,
    ) -> None:
        """추출 필드 간 합계 검증 경고를 레벨별로 분류한다."""
        stock_total = self._sum_amounts(stock_counts)
        target_total = self._sum_amounts(issue_targets)
        if (
            not self._is_not_applicable("발행대상자")
            and issue_targets
            and target_total != stock_total
        ):
            self._append_warning(
                f"발행대상자: 배정주식수 합계({target_total:,})가 신주의 종류와 수 합계({stock_total:,})와 일치하지 않습니다.",
                level="weak",
            )

        funding_total = self._sum_amounts(funding_purposes)
        stock_value_total = self._stock_value_total(stock_counts, issue_prices)
        if (
            not self._is_not_applicable("발행목적")
            and not self._is_not_applicable("발행가액")
            and funding_purposes
            and stock_value_total is not None
            and abs(stock_value_total - funding_total) > 9
        ):
            self._append_warning(
                f"발행목적: 신주의 종류와 수와 발행가액의 곱({stock_value_total:,})이 자금조달 목적 합계({funding_total:,})와 일치하지 않습니다.",
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
        if (
            stock_counts
            and stock_total == 0
            and self.field_parse_status.get("신주의 종류와 수") == "explicit_zero"
        ):
            self._append_warning(
                "신주의 종류와 수: 모든 주식 종류의 수량이 0입니다.",
                level="weak",
            )
        pre_issuance_stock_total = self._sum_amounts(pre_issuance_stock_counts)
        if (
            pre_issuance_stock_counts
            and pre_issuance_stock_total == 0
            and self.field_parse_status.get("증자 전 발행주식총수") == "explicit_zero"
        ):
            self._append_warning(
                "증자 전 발행주식총수: 모든 주식 종류의 수량이 0입니다.",
                level="weak",
            )
        pre_issuance_status_detail = self.field_parse_status_detail.get(
            "증자 전 발행주식총수", {}
        )
        if pre_issuance_status_detail.get("보통주식") == "explicit_zero":
            self._append_warning(
                "증자 전 발행주식총수: 보통주식 수량이 원문에서 0 또는 대시로 명시되었습니다.",
                level="strong",
            )

    def get_issue_prices(self) -> list[list[Any]] | str:
        """신주 발행가액을 주식 종류별로 추출한다."""
        if self.context.issuance_type == "bonus":
            self._set_field_status("발행가액", "not_applicable")
            return "-"
        return self._stock_values(
            "신주 발행가액",
            warning_field_name="발행가액",
        )

    def get_issue_method(self) -> str | None:
        """증자방식을 추출한다."""
        if self.context.issuance_type == "bonus":
            self._set_field_status("증자방식", "not_applicable")
            return "-"
        value = self.rows.last_value("증자방식")
        self._warn_if_missing("증자방식", value)
        if value is not None:
            self._set_field_status("증자방식", "parsed")
        return value

    def get_payment_date(self) -> str | None:
        """납입일을 추출한다."""
        if self.context.issuance_type == "bonus":
            self._set_field_status("납입일", "not_applicable")
            return "-"
        value = self.rows.last_value("납입일")
        self._warn_if_missing("납입일", value)
        self._set_field_status(
            "납입일", "parsed" if value is not None else "source_not_found"
        )
        return value

    def get_delivery_date(self) -> str | None:
        """신주권교부예정일을 추출한다."""
        value = self.rows.last_value("신주권교부예정일")
        self._warn_if_missing("신주권교부예정일", value)
        self._set_field_status(
            "신주권교부예정일", "parsed" if value is not None else "source_not_found"
        )
        return value

    def get_listing_date(self) -> str | None:
        """신주의 상장 예정일을 추출한다."""
        value = self.rows.last_value("신주의 상장 예정일")
        self._warn_if_missing("상장예정일", value)
        self._set_field_status(
            "상장예정일", "parsed" if value is not None else "source_not_found"
        )
        return value

    def get_issue_targets(
        self, *, stock_counts: list[list[Any]]
    ) -> list[list[Any]] | str:
        """제3자 배정 대상자와 배정 주식 수를 추출한다."""
        if self.context.issuance_type == "bonus":
            self._set_field_status("발행대상자", "not_applicable")
            return "-"
        stock_total = self._sum_amounts(stock_counts)
        fallback_targets: list[list[Any]] | None = None
        found_empty_target_table = False
        for table in self.context.extraction_tables:
            logical_rows = table["logical_rows"]
            if not logical_rows or not row_contains(
                logical_rows[0], "제3자배정 대상자", "배정주식수"
            ):
                continue
            rows = table["positional_rows"]
            target_idx = column_index(rows[0], "제3자배정대상자")
            amount_idx = column_index(rows[0], "배정주식수")
            if (
                target_idx is None
                or amount_idx is None
                or target_idx == amount_idx
            ):
                continue
            data_rows = rows[1:]
            if self._is_undisclosed_issue_target_rows(
                data_rows, target_idx, amount_idx
            ):
                self._set_field_status("발행대상자", "explicit_zero")
                return [["-", 0]]
            targets: list[list[Any]] = []
            for row in data_rows:
                if target_idx >= len(row) or amount_idx >= len(row):
                    continue
                target = row[target_idx]
                if not target or target == "-":
                    continue
                amount = self._issue_target_amount(row[amount_idx])
                if amount is not None:
                    targets.append([target, amount])
            targets = self._exclude_bottom_duplicate_total_target(
                targets,
                stock_total=stock_total,
            )
            if targets:
                if self._sum_amounts(targets) == stock_total:
                    self._set_field_status("발행대상자", "parsed")
                    return targets
                if fallback_targets is None:
                    fallback_targets = targets
                continue
            found_empty_target_table = True
        if fallback_targets is not None:
            self._set_field_status("발행대상자", "parsed")
            return fallback_targets
        if found_empty_target_table:
            self._set_field_status("발행대상자", "source_found_empty")
            return []
        issue_method = self.get_issue_method()
        title = str(self.context.record.get("title") or "")
        if issue_method and "제3자배정" in issue_method and "종속회사" not in title:
            self._warn_if_missing("발행대상자", None)
        return []

    def build_type_details(
        self,
        *,
        stock_counts: list[list[Any]],
        pre_issuance_stock_counts: list[list[Any]],
        funding_purposes: list[list[Any]] | str,
        issue_prices: list[list[Any]] | str,
        issue_method: str | None,
        payment_date: str | None,
        delivery_date: str | None,
        listing_date: str | None,
        issue_targets: list[list[Any]] | str,
    ) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
        """증자 유형별 상세 블록을 기존 flat 필드와 별도로 구성한다."""
        issuance_type = self.context.issuance_type
        issuance_label = ISSUANCE_TYPE_LABELS[issuance_type]
        paid_detail = None
        bonus_detail = None
        if issuance_type in {"paid", "mixed"}:
            paid_rows = self._rows_for_issuance_section("paid")
            paid_detail = {
                "신주의 종류와 수": stock_counts,
                "증자 전 발행주식총수": pre_issuance_stock_counts,
                "발행목적": funding_purposes,
                "발행가액": issue_prices,
                "증자방식": issue_method,
                "신주배정기준일": self._section_last_value(paid_rows, "신주배정기준일"),
                "1주당 신주배정주식수": self._section_stock_text_values(
                    paid_rows, "1주당 신주배정"
                ),
                "납입일": payment_date,
                "신주권교부예정일": delivery_date,
                "상장예정일": listing_date,
                "발행대상자": issue_targets,
            }
        if issuance_type in {"bonus", "mixed"}:
            bonus_rows = self._rows_for_issuance_section("bonus")
            bonus_detail = {
                "신주의 종류와 수": self._section_stock_int_values(
                    bonus_rows, "신주의 종류와 수"
                ),
                "증자 전 발행주식총수": self._section_stock_int_values(
                    bonus_rows, "증자전 발행주식총수"
                ),
                "신주배정기준일": self._section_last_value(
                    bonus_rows, "신주배정기준일"
                ),
                "1주당 신주배정주식수": self._section_stock_text_values(
                    bonus_rows, "1주당 신주배정"
                ),
                "신주권교부예정일": self._section_last_value(
                    bonus_rows, "신주권교부예정일"
                ),
                "상장예정일": self._section_last_value(
                    bonus_rows, "신주의 상장 예정일"
                ),
            }
        return issuance_label, paid_detail, bonus_detail

    def _is_undisclosed_issue_target_rows(
        self, data_rows: list[list[str]], target_idx: int, amount_idx: int
    ) -> bool:
        if not data_rows:
            return False
        for row in data_rows:
            if target_idx >= len(row) or amount_idx >= len(row):
                return False
            if row[target_idx].strip() != "-":
                return False
            amount = self._issue_target_amount(row[amount_idx])
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

    def _issue_target_amount(self, value: str) -> int | None:
        amount_text = re.sub(r"-?\d[\d,]*(?:\.\d+)?\s*%", "", value)
        amounts = parse_ints(amount_text)
        if not amounts:
            return None
        return sum(amounts)

    def _has_issue_target_total_label_token(self, value: object) -> bool:
        return any(
            token in ISSUE_TARGET_TOTAL_LABEL_TOKENS
            for token in str(value).strip().split()
        )

    def _rows_for_issuance_section(self, section: str) -> list[list[str]]:
        rows = self.rows.values
        if self.context.issuance_type == "mixed":
            bonus_index = self._bonus_section_index(rows)
            if bonus_index is None:
                return rows if section == "paid" else []
            if section == "paid":
                return rows[:bonus_index]
            return rows[bonus_index + 1 :]
        if self.context.issuance_type == section:
            return rows
        return []

    def _bonus_section_index(self, rows: list[list[str]]) -> int | None:
        for index, row in enumerate(rows):
            if row_contains(row, "무상증자") and not row_contains(row, "유무상증자"):
                return index
        return None

    def _section_last_value(self, rows: list[list[str]], *needles: str) -> str | None:
        for row in rows:
            if row_contains(row, *needles):
                return row[-1]
        return None

    def _section_stock_int_values(
        self, rows: list[list[str]], section_label: str
    ) -> list[list[Any]]:
        values: list[list[Any]] = []
        for output_label, source_labels in STOCK_LABELS.items():
            parsed = self._section_stock_int_value(rows, section_label, source_labels)
            values.append([output_label, 0 if parsed is None else parsed])
        return values

    def _section_stock_int_value(
        self,
        rows: list[list[str]],
        section_label: str,
        source_labels: tuple[str, ...],
    ) -> int | None:
        dash_seen = False
        for row in rows:
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

    def _section_stock_text_values(
        self, rows: list[list[str]], section_label: str
    ) -> list[list[Any]]:
        by_label = {
            output_label: self._section_stock_text_value(
                rows, section_label, source_labels
            )
            for output_label, source_labels in STOCK_LABELS.items()
        }
        if all(value is None for value in by_label.values()):
            fallback = self._section_last_value(rows, section_label)
            if fallback not in (None, "", "-"):
                by_label["보통주식"] = fallback
        return [[label, by_label[label]] for label in STOCK_LABELS]

    def _section_stock_text_value(
        self,
        rows: list[list[str]],
        section_label: str,
        source_labels: tuple[str, ...],
    ) -> str | None:
        for row in rows:
            if not row_contains(row, section_label):
                continue
            for index, cell in enumerate(row):
                if not any(label in cell.replace(" ", "") for label in source_labels):
                    continue
                if index + 1 >= len(row):
                    continue
                value = row[index + 1].strip()
                if value and value != "-":
                    return value
        return None

    def _stock_values(
        self,
        section_label: str,
        *,
        warning_field_name: str | None = None,
        warn_when_all_missing: bool = True,
    ) -> list[list[Any]]:
        """보통주와 기타주식 값을 일관된 순서로 배열하여 반환한다."""
        values: list[list[Any]] = []
        item_statuses: dict[str, str] = {}
        for output_label, source_labels in STOCK_LABELS.items():
            parsed, item_status = self._stock_value_with_status(
                section_label, source_labels
            )
            item_statuses[output_label] = item_status
            values.append([output_label, 0 if parsed is None else parsed])
        field_name = warning_field_name or section_label
        if field_name in STOCK_STATUS_DETAIL_FIELDS:
            self.field_parse_status_detail[field_name] = item_statuses
        if any(value > 0 for _, value in values):
            self._set_field_status(field_name, "parsed")
        elif any(status == "explicit_zero" for status in item_statuses.values()):
            self._set_field_status(field_name, "explicit_zero")
        elif not warn_when_all_missing:
            self._set_field_status(field_name, "not_applicable")
        else:
            self._set_field_status(field_name, "source_not_found")
        if warn_when_all_missing and all(
            status == "source_not_found" for status in item_statuses.values()
        ):
            self._warn_if_missing(field_name, None)
        return values

    def _funding_purpose_row(self, source_labels: tuple[str, ...]) -> list[str]:
        for source_label in source_labels:
            row = self.rows.containing("자금조달의 목적", source_label)
            if row:
                return row
        return []

    def _stock_value(
        self, section_label: str, source_labels: tuple[str, ...]
    ) -> int | None:
        """지정 구간에서 주식 종류 라벨 바로 다음 값을 숫자로 변환한다."""
        return self._stock_value_with_status(section_label, source_labels)[0]

    def _stock_value_with_status(
        self, section_label: str, source_labels: tuple[str, ...]
    ) -> tuple[int | None, str]:
        """지정 구간에서 주식 종류 라벨 바로 다음 값을 숫자와 상태로 변환한다."""
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
                return parsed, "parsed"
        if dash_seen:
            return 0, "explicit_zero"
        return None, "source_not_found"

    def _stock_value_total(
        self, stock_counts: list[list[Any]], issue_prices: list[list[Any]] | str
    ) -> int | None:
        if isinstance(issue_prices, str):
            return None
        issue_price_by_label = {
            str(item[0]): self._item_amount(item) for item in issue_prices if item
        }
        total = 0
        matched = False
        for item in stock_counts:
            if not item:
                continue
            label = str(item[0])
            if label not in issue_price_by_label:
                continue
            if issue_price_by_label[label] <= 0:
                continue
            matched = True
            total += self._item_amount(item) * issue_price_by_label[label]
        return total if matched else None

    def _sum_amounts(self, rows: list[list[Any]] | str) -> int:
        if isinstance(rows, str):
            return 0
        return sum(self._item_amount(row) for row in rows)

    def _item_amount(self, row: list[Any]) -> int:
        if not row:
            return 0
        value = row[-1]
        return value if isinstance(value, int) else 0

    def _is_not_applicable(self, field_name: str) -> bool:
        return self.field_parse_status.get(field_name) == "not_applicable"

    def _warn_if_missing(self, field_name: str, value: object | None) -> None:
        if value not in (None, "", []):
            return
        rule = RIGHTS_FIELD_EXTRACTION_RULES[field_name]
        warning = f"{field_name}: 정해진 출처에서 값을 찾지 못했습니다. 출처: {rule}"
        self._set_field_status(field_name, "source_not_found")
        self._append_warning(warning, level="strong")

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
