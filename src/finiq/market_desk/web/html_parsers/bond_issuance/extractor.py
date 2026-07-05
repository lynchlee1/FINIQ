"""사채 발행 파서 추출 로직."""

from __future__ import annotations

import re
from typing import Any

from ..common import clean_text, last_int, non_correction_tables, parse_int, row_contains
from .utils import _BondParseContext

BOND_FIELD_EXTRACTION_RULES = {
    "회차": "메인 표 > '1. 사채의 종류' 행 > '회차' 오른쪽 셀",
    "종류": "제목 > '전환사채'|'교환사채'|'신주인수권부사채' 포함 여부",
    "기업명(행사대상)": "메인 표 > 교환/전환/인수권 행사 대상 주식 종류 행 > 마지막 값",
    "발행금액": "메인 표 > '사채의 권면' 행 > 라벨 오른쪽 값 셀의 마지막 숫자",
    "발행목적": "메인 표 > '자금조달의 목적' 행 > 목적명 + 마지막 숫자",
    "행사가액": "메인 표 > '전환가액'|'교환가액'|'행사가액'|'행사가격' 행 > 마지막 숫자",
    "납입일": "메인 표 > '납입일' 라벨 행 > 마지막 값",
    "만기일": "메인 표 > '사채만기일'|'사채만기' 행 > 마지막 값",
    "사채발행방법": "메인 표 > '사채발행방법' 행 > 마지막 값",
    "행사시작일": "메인 표 > '전환청구기간'|'교환청구기간'|'권리행사기간'|'행사기간' 행 > '시작일' 값",
    "행사종료일": "메인 표 > '전환청구기간'|'교환청구기간'|'권리행사기간'|'행사기간' 행 > '종료일' 값",
    "투자자": "'특정인에 대한 대상자별 사채발행내역' 표 > 발행 대상자명 + 발행권면총액",
}


class BondIssuanceExtractor:
    """사채 발행 공시의 실제 필드별 추출 로직을 모아둔 클래스."""

    def __init__(self, context: _BondParseContext):
        self.context = context
        self.rows = context.rows
        self.warnings: list[str] = []
        self.weak_warnings: list[str] = []
        self.medium_warnings: list[str] = []
        self.strong_warnings: list[str] = []
        self.field_parse_status: dict[str, str] = {}

    def extract_round_from_bond_type_row(self) -> str | None:
        value = self.rows.value_after("사채의 종류", "회차")
        self._warn_if_missing("회차", value)
        if value is not None:
            self._set_field_status("회차", "parsed")
        return value

    def extract_security_type_from_title(self, title: str) -> str | None:
        """공시 제목을 기반으로 CB/EB/BW 여부를 판별한다."""
        text = title
        if "신주인수권부사채" in text:
            self._set_field_status("종류", "parsed")
            return "BW"
        if "교환사채" in text:
            self._set_field_status("종류", "parsed")
            return "EB"
        if "전환사채" in text:
            self._set_field_status("종류", "parsed")
            return "CB"
        self._warn_if_missing("종류", None)
        return None

    def extract_target_company_name_from_exercise_target_stock_row(self) -> str | None:
        """대상 주식 문구에서 불필요한 법인 형태 및 주식 종류 표현을 제거하여 순수 회사명만 남긴다."""
        target_text = self._extract_exercise_target_stock_text_from_main_rows()
        text = clean_text(target_text)
        if not text:
            self._warn_if_missing("기업명(행사대상)", None)
            return None
        self._set_field_status("기업명(행사대상)", "parsed")
        cleaned = text
        replacements = (
            r"\(주\)",
            r"㈜",
            r"주식회사",
            r"기명식",
            r"무기명식",
            r"보통주식?",
            r"보통주?",
            r"주식",
        )
        for pattern in replacements:
            cleaned = re.sub(pattern, " ", cleaned)
        cleaned = clean_text(cleaned.strip(" -_/·,"))
        return cleaned or text

    def _extract_exercise_target_stock_text_from_main_rows(self) -> str | None:
        """전환/교환/신주인수권 행사로 발행될 대상 주식 관련 문구를 추출한다."""
        exchange_target = self.rows.last_value("교환대상")
        if exchange_target is not None:
            return exchange_target
        for target_label in (
            "전환에 따라",
            "전환으로 발행할",
            "인수권행사에 따라",
        ):
            value = self.rows.last_value(target_label, "종류")
            if value is not None:
                return value
        return None

    def extract_issue_amount_from_bond_face_value_row(self) -> int | None:
        row = self._issue_amount_row()
        value = self._last_int_after_first_cell(row)
        self._warn_if_missing("발행금액", value)
        if value is not None:
            self._set_field_status(
                "발행금액", "explicit_zero" if value == 0 else "parsed"
            )
        return value

    def _issue_amount_row(self) -> list[str]:
        rows = [row for row in self.rows.values if row_contains(row, "사채의 권면")]
        for row in rows:
            if row_contains(row, "원화기준"):
                return row
        for row in rows:
            if row_contains(row, "(원)"):
                return row
        return rows[0] if rows else []

    def _last_int_after_first_cell(self, row: list[str]) -> int | None:
        for cell in reversed(row[1:]):
            parsed = parse_int(cell, dash_as_zero=True)
            if parsed is not None:
                return parsed
        return None

    def extract_funding_purposes_from_funding_purpose_rows(
        self, issue_amount: int | None
    ) -> list[list[Any]]:
        """자금조달 목적 행에 적힌 목적명과 금액을 표에 나온 순서대로 추출한다."""
        purposes: list[list[Any]] = []
        found_purpose_amount = False
        for row in self.rows.values:
            if not row_contains(row, "자금조달의 목적"):
                continue
            label = self._funding_purpose_label(row)
            amount = self._funding_purpose_amount(row)
            if label and amount is not None:
                found_purpose_amount = True
            if label and amount:
                purposes.append([label, amount])

        if not found_purpose_amount:
            self._warn_if_missing("발행목적", None)
        else:
            self._set_field_status(
                "발행목적", "parsed" if purposes else "explicit_zero"
            )
        if purposes and issue_amount is not None:
            total = sum(amount for _, amount in purposes)
            if total != issue_amount:
                self._append_warning(
                    f"발행목적: 자금조달 목적 합계({total:,})가 발행금액({issue_amount:,})과 일치하지 않습니다.",
                    level="weak",
                )
        return purposes

    def _funding_purpose_label(self, row: list[str]) -> str | None:
        purpose_index = self._funding_purpose_index(row)
        if purpose_index is None or purpose_index + 1 >= len(row):
            return None
        return self._clean_funding_purpose_label(row[purpose_index + 1])

    def _funding_purpose_index(self, row: list[str]) -> int | None:
        for index, cell in enumerate(row):
            if row_contains([cell], "자금조달의 목적"):
                return index
        return None

    def _clean_funding_purpose_label(self, value: str) -> str | None:
        label = clean_text(value)
        label = re.sub(r"\(\s*원\s*\)", "", label)
        label = re.sub(r"\s*원$", "", label)
        label = clean_text(label.strip(" -_/·,"))
        return label or None

    def _funding_purpose_amount(self, row: list[str]) -> int | None:
        purpose_index = self._funding_purpose_index(row)
        if purpose_index is None:
            return None
        for cell in reversed(row[purpose_index + 2 :]):
            parsed = parse_int(cell, dash_as_zero=True)
            if parsed is not None:
                return parsed
        return None

    def extract_exercise_price_from_conversion_exchange_or_warrant_price_row(
        self,
    ) -> int | None:
        """전환/교환/신주인수권 행사가액을 추출한다."""
        for price_label in ("전환가액", "교환가액", "행사가액", "행사가격"):
            value = self.rows.last_int(price_label, "원")
            if value is not None:
                self._set_field_status("행사가액", "parsed")
                return value
        self._warn_if_missing("행사가액", None)
        return None

    def extract_payment_date_from_payment_date_row(self) -> str | None:
        value = self.rows.last_labeled_value("납입일")
        self._warn_if_missing("납입일", value)
        if value is not None:
            self._set_field_status("납입일", "parsed")
        return value

    def extract_maturity_date_from_bond_maturity_row(self) -> str | None:
        value = self.rows.last_value("사채만기일")
        if value is None:
            value = self.rows.last_value("사채만기")
        self._warn_if_missing("만기일", value)
        if value is not None:
            self._set_field_status("만기일", "parsed")
        return value

    def extract_issue_method_from_bond_issue_method_row(self) -> str | None:
        value = self.rows.last_value("사채발행방법")
        self._warn_if_missing("사채발행방법", value)
        if value is not None:
            self._set_field_status("사채발행방법", "parsed")
        return value

    def extract_exercise_period_start_from_claim_period_row(self) -> str | None:
        value = self._extract_exercise_period_value_from_claim_period_row("시작일")
        self._warn_if_missing("행사시작일", value)
        if value is not None:
            self._set_field_status("행사시작일", "parsed")
        return value

    def extract_exercise_period_end_from_claim_period_row(self) -> str | None:
        value = self._extract_exercise_period_value_from_claim_period_row("종료일")
        self._warn_if_missing("행사종료일", value)
        if value is not None:
            self._set_field_status("행사종료일", "parsed")
        return value

    def _extract_exercise_period_value_from_claim_period_row(
        self, boundary_label: str
    ) -> str | None:
        """전환/교환/권리행사 청구기간의 시작일 또는 종료일을 추출한다."""
        for period_label in (
            "전환청구기간",
            "교환청구기간",
            "권리행사기간",
            "행사기간",
        ):
            value = self.rows.last_value(period_label, boundary_label)
            if value is not None:
                return value
        return None

    def extract_investors_from_specific_person_bond_issue_table(
        self,
    ) -> list[list[Any]]:
        """사채 발행 대상자(인수자)와 배정 권면액을 추출한다."""
        for table in non_correction_tables(self.context.raw_tables):
            rows = table.get("logical_rows") or []
            if not rows or not row_contains(rows[0], "발행 대상자명", "발행권면"):
                continue
            targets: list[list[Any]] = []
            for row in rows[1:]:
                if not row or row[0] in {"-", "합계", "총계", "계"}:
                    continue
                amount = last_int(row)
                if amount is not None:
                    targets.append([row[0], amount])
            self._set_field_status("투자자", "parsed" if targets else "explicit_zero")
            return targets
        self._warn_if_missing("투자자", None)
        return []

    def _warn_if_missing(self, field_name: str, value: object | None) -> None:
        if value not in (None, "", []):
            return
        rule = BOND_FIELD_EXTRACTION_RULES[field_name]
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
