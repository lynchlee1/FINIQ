"""사채 발행 파서 추출 로직."""

from __future__ import annotations

import re
from typing import Any

from ..common import (
    clean_text,
    normalize_label,
    parse_int,
    row_contains,
)
from .utils import (
    _BondParseContext,
    _BondRows,
    _clean_funding_purpose_label,
)

BOND_SECURITY_TYPE_LABELS = (
    ("CB", "전환사채"),
    ("EB", "교환사채"),
    ("BW", "신주인수권부사채"),
)

# 각 묶음은 의미가 같은 CB, EB, BW label을 이 순서로 유지한다.
EXERCISE_TARGET_LABEL_GROUPS = (
    ("전환대상", "교환대상", "인수권행사대상"),
    ("전환에 따라", "교환에 따라", "인수권행사에 따라"),
    ("전환으로 발행할", "교환으로 발행할", "인수권행사로 발행할"),
)
EXERCISE_PRICE_LABEL_GROUPS = (
    ("전환가액", "교환가액", "행사가액"),
    ("전환가격", "교환가격", "행사가격"),
)
EXERCISE_PERIOD_LABEL_GROUPS = (
    ("전환청구기간", "교환청구기간", "권리행사기간"),
)
EXERCISE_TARGET_LABELS = tuple(
    label for group in EXERCISE_TARGET_LABEL_GROUPS for label in group
) + ("신주인수권행사에 따라",)
EXERCISE_PRICE_LABELS = tuple(
    label for group in EXERCISE_PRICE_LABEL_GROUPS for label in group
)
EXERCISE_PERIOD_LABELS = (
    *(label for group in EXERCISE_PERIOD_LABEL_GROUPS for label in group),
    "행사기간",
)

BOND_FIELD_EXTRACTION_RULES = {
    "회차": "메인 표 > N=2 '회차' 행 > N=3 값",
    "종류": "제목 > '전환사채'|'교환사채'|'신주인수권부사채' 포함 여부",
    "기업명(행사대상)": (
        "메인 표 > N=2 교환/전환/인수권 행사 대상 주식 종류 행 > 마지막 값"
    ),
    "발행금액": "메인 표 > N=1 '사채의 권면' 또는 N=2 '원화기준 (원)' 행 > 마지막 값",
    "발행목적": "메인 표 > N=1 '자금조달의 목적' 행 > N=2 목적명 + 마지막 값",
    "행사가액": (
        "메인 표 > N=2 전환/교환/행사가액 또는 가격 행 > 마지막 값"
    ),
    "납입일": "메인 표 > N=1 '납입일' 행 > 마지막 값",
    "만기일": "메인 표 > N=1 '사채만기일'|'사채만기' 행 > 마지막 값",
    "사채발행방법": "메인 표 > N=1 '사채발행방법' 행 > 마지막 값",
    "행사시작일": (
        "메인 표 > N=2 행사기간 + N=3 '시작일' 행 > 마지막 값"
    ),
    "행사종료일": (
        "메인 표 > N=2 행사기간 + N=3 '종료일' 행 > 마지막 값"
    ),
    "투자자": (
        "'특정인에 대한 대상자별 사채발행내역' 표 > 발행 대상자명 + 발행권면총액"
    ),
}
INVESTOR_TABLE_MISSING_WARNING = (
    "사채 발행 투자자 표를 찾지 못했습니다. "
    "HTML 양식이 예상과 달라 투자자 필드가 비어 있을 수 있습니다."
)


def _main_bond_rows(raw_tables: list[dict[str, Any]]) -> list[list[str]]:
    """사채 발행 결정의 메인 테이블을 찾는다."""
    for table in raw_tables:
        rows = table.get("logical_rows") or []
        if all(
            any(row_contains(row, label) for row in rows)
            for label in ("사채의 종류", "사채의 권면", "자금조달의 목적")
        ):
            return rows
    return []


class BondIssuanceExtractor:
    """사채 발행 공시의 실제 필드별 추출 로직을 모아둔 클래스."""

    def __init__(self, context: _BondParseContext):
        self.context = context
        self.rows = _BondRows(_main_bond_rows(context.raw_tables))
        self.warnings: list[str] = []
        self.strong_warnings: list[str] = []
        self.field_parse_status: dict[str, str] = {}
        if not self.rows.values:
            raise ValueError("bond issuance condition table is required")

    def extract_round_from_bond_type_row(self) -> str | None:
        row = self.rows.first_row_at(2, ("회차",))
        value = row[2] if len(row) > 2 else None
        self._set_value_status("회차", value)
        return value

    def extract_security_type_from_title(self, title: str) -> str | None:
        """공시 제목을 기반으로 CB/EB/BW 여부를 판별한다."""
        matched_types = [
            security_type
            for security_type, label in BOND_SECURITY_TYPE_LABELS
            if label in title
        ]
        value = matched_types[0] if len(matched_types) == 1 else None
        if len(matched_types) > 1:
            self._append_warning(
                "종류: 주입 제목에서 사채 종류를 둘 이상 확인했습니다. "
                f"확인된 종류: {', '.join(matched_types)}"
            )
        self._set_value_status("종류", value)
        return value

    def extract_target_company_name_from_exercise_target_stock_row(self) -> str | None:
        """대상 주식 문구를 원문 기준으로 추출한다."""
        target_text = self._extract_exercise_target_stock_text_from_main_rows()
        text = clean_text(target_text)
        value = text or None
        self._set_value_status("기업명(행사대상)", value)
        return value

    def _extract_exercise_target_stock_text_from_main_rows(self) -> str | None:
        """전환/교환/신주인수권 행사로 발행될 대상 주식 관련 문구를 추출한다."""
        for target_label in EXERCISE_TARGET_LABELS:
            row = self.rows.first_row_at(
                2,
                (target_label,),
                starts_with=True,
            )
            if row:
                return row[-1] if len(row) > 2 else None
        return None

    def extract_issue_amount_from_bond_face_value_row(self) -> int | None:
        row = self.rows.first_row_at(2, ("원화기준 (원)",))
        label_cell = 2
        if not row:
            row = self.rows.first_row_at(
                1,
                ("사채의 권면",),
                starts_with=True,
            )
            label_cell = 1
        raw_value = row[-1] if len(row) > label_cell else None
        value = parse_int(raw_value, dash_as_zero=True)
        if value is None:
            status = "source_not_found"
        elif value == 0:
            status = "explicit_zero"
        else:
            status = "parsed"
        self._set_field_status("발행금액", status)
        return value

    def extract_funding_purposes_from_funding_purpose_rows(
        self,
    ) -> list[list[Any]] | None:
        """자금조달 목적 행에 적힌 목적명과 금액을 표에 나온 순서대로 추출한다."""
        purposes: list[list[Any]] = []
        found_amount_source = False
        for row in self.rows.matching_rows(1, ("자금조달의 목적",)):
            label = self._funding_purpose_label(row)
            amount = self._funding_purpose_amount(row)
            if amount is not None:
                found_amount_source = True
            if label and amount:
                purposes.append([label, amount])
        if purposes:
            status = "parsed"
        elif found_amount_source:
            status = "explicit_zero"
        else:
            status = "source_not_found"
        self._set_field_status("발행목적", status)
        return None if status == "source_not_found" else purposes

    def _funding_purpose_label(self, row: list[str]) -> str | None:
        if len(row) < 2:
            return None
        return self._clean_funding_purpose_label(row[1])

    def _clean_funding_purpose_label(self, value: str) -> str | None:
        return _clean_funding_purpose_label(value)

    def _funding_purpose_amount(self, row: list[str]) -> int | None:
        return parse_int(row[-1], dash_as_zero=True) if len(row) > 2 else None

    def extract_exercise_price_from_conversion_exchange_or_warrant_price_row(
        self,
    ) -> int | float | None:
        """전환/교환/신주인수권 행사가액을 추출한다."""
        value = None
        for price_label in EXERCISE_PRICE_LABELS:
            row = self.rows.first_row_at(
                2,
                (f"{price_label} (원/주)",),
            )
            if row:
                raw_value = row[-1] if len(row) > 2 else None
                value = _parse_price_value(raw_value)
                break
        self._set_value_status("행사가액", value)
        return value

    def extract_payment_date_from_payment_date_row(self) -> str | None:
        value = self.rows.last_value_at(1, ("납입일",))
        self._set_value_status("납입일", value)
        return value

    def extract_maturity_date_from_bond_maturity_row(self) -> str | None:
        value = None
        for label in ("사채만기일", "사채만기"):
            row = self.rows.first_row_at(1, (label,))
            if row:
                value = row[-1] if len(row) > 1 else None
                break
        self._set_value_status("만기일", value)
        return value

    def extract_issue_method_from_bond_issue_method_row(self) -> str | None:
        value = self.rows.last_value_at(1, ("사채발행방법",))
        self._set_value_status("사채발행방법", value)
        return value

    def extract_exercise_period_start_from_claim_period_row(self) -> str | None:
        value = self._extract_exercise_period_value_from_claim_period_row("시작일")
        self._set_value_status("행사시작일", value)
        return value

    def extract_exercise_period_end_from_claim_period_row(self) -> str | None:
        value = self._extract_exercise_period_value_from_claim_period_row("종료일")
        self._set_value_status("행사종료일", value)
        return value

    def _extract_exercise_period_value_from_claim_period_row(
        self, boundary_label: str
    ) -> str | None:
        """전환/교환/권리행사 청구기간의 시작일 또는 종료일을 추출한다."""
        for period_label in EXERCISE_PERIOD_LABELS:
            row = self.rows.first_row_at(
                2,
                (period_label,),
                additional_label_cells=((3, (boundary_label,)),),
            )
            if row:
                return row[-1] if len(row) > 3 else None
        return None

    def extract_investors_from_specific_person_bond_issue_table(
        self,
    ) -> list[list[Any]] | None:
        """사채 발행 대상자(인수자)와 배정 권면액을 추출한다."""
        source_tables = self._specific_person_bond_issue_table_rows()
        if not source_tables:
            self._append_warning(INVESTOR_TABLE_MISSING_WARNING)
        for rows in source_tables:
            header = rows[0]
            name_index = _first_header_index(header, "발행 대상자명")
            amount_index = _first_header_index(header, "발행권면")
            if name_index is None or amount_index is None:
                continue
            targets: list[list[Any]] = []
            for row in rows[1:]:
                target_name = row[name_index] if name_index < len(row) else ""
                target_name = clean_text(target_name)
                normalized_target_name = normalize_label(target_name)
                if not row or normalized_target_name in {
                    "",
                    "-",
                    "합계",
                    "총계",
                    "소계",
                    "계",
                }:
                    continue
                amount_cell = row[amount_index] if amount_index < len(row) else ""
                amount = parse_int(amount_cell, dash_as_zero=True)
                if amount is not None:
                    targets.append([target_name, amount])
            self._set_field_status(
                "투자자", "parsed" if targets else "source_not_found"
            )
            return targets or None
        self._set_field_status("투자자", "source_not_found")
        return None

    def _specific_person_bond_issue_table_rows(self) -> list[list[list[str]]]:
        for table in self.context.raw_tables:
            logical_rows = table["logical_rows"]
            if logical_rows and row_contains(
                logical_rows[0], "발행 대상자명", "발행권면"
            ):
                rows = table["positional_rows"]
                name_index = _first_header_index(rows[0], "발행 대상자명")
                amount_index = _first_header_index(rows[0], "발행권면")
                if (
                    name_index is not None
                    and amount_index is not None
                    and name_index != amount_index
                ):
                    return [rows]
        return []

    def _set_value_status(self, field_name: str, value: Any) -> None:
        status = "source_not_found" if value in (None, "", []) else "parsed"
        self._set_field_status(field_name, status)

    def _set_field_status(self, field_name: str, status: str) -> None:
        self.field_parse_status[field_name] = status
        if status == "source_not_found":
            rule = BOND_FIELD_EXTRACTION_RULES[field_name]
            self._append_warning(
                f"{field_name}: 정해진 출처에서 값을 찾지 못했습니다. 출처: {rule}"
            )

    def _append_warning(self, warning: str) -> None:
        if warning not in self.strong_warnings:
            self.strong_warnings.append(warning)
        if warning not in self.warnings:
            self.warnings.append(warning)


def _first_header_index(row: list[str], label: str) -> int | None:
    for index, cell in enumerate(row):
        if row_contains([cell], label):
            return index
    return None


def _parse_price_value(value: str | None) -> int | float | None:
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"-?\d[\d,\s]*(?:\.\d+)?", text)
    if match is None:
        return None
    numeric_text = re.sub(r"\s+", "", match.group(0)).replace(",", "")
    if "." in numeric_text:
        return float(numeric_text)
    return int(numeric_text)
