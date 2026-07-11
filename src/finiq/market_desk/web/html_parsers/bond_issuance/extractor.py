"""사채 발행 파서 추출 로직."""

from __future__ import annotations

import re
from typing import Any

from ..common import (
    clean_text,
    parse_int,
    row_contains,
)
from .utils import (
    _BondParseContext,
    _BondRows,
    _clean_funding_purpose_label,
)

EXERCISE_TARGET_LABELS = (
    "전환대상",
    "교환대상",
    "인수권행사대상",
    "전환에 따라",
    "교환에 따라",
    "인수권행사에 따라",
    "전환으로 발행할",
    "교환으로 발행할",
    "인수권행사로 발행할",
)

EXERCISE_PRICE_LABELS = (
    "전환가액",
    "교환가액",
    "행사가액",
    "전환가격",
    "교환가격",
    "행사가격",
)

EXERCISE_PERIOD_LABELS = (
    "전환청구기간",
    "교환청구기간",
    "권리행사기간",
    "행사기간",
)

BOND_FIELD_EXTRACTION_RULES = {
    "회차": "메인 표 > '1. 사채의 종류' 행 > '회차' 오른쪽 셀",
    "종류": "제목 > '전환사채'|'교환사채'|'신주인수권부사채' 포함 여부",
    "기업명(행사대상)": (
        "메인 표 > 교환/전환/인수권 행사 대상 주식 종류 행 > 마지막 값"
    ),
    "발행금액": "메인 표 > '사채의 권면' 행 > 라벨 오른쪽 값 셀의 마지막 숫자",
    "발행목적": "메인 표 > '자금조달의 목적' 행 > 목적명 + 마지막 숫자",
    "행사가액": (
        "메인 표 > 전환/교환/행사가액 또는 가격 행 > 라벨 오른쪽 숫자 값"
    ),
    "납입일": "메인 표 > '납입일' 라벨 행 > 마지막 값",
    "만기일": "메인 표 > '사채만기일'|'사채만기' 행 > 마지막 값",
    "사채발행방법": "메인 표 > '사채발행방법' 행 > 마지막 값",
    "행사시작일": (
        "메인 표 > '전환청구기간'|'교환청구기간'|'권리행사기간'|'행사기간' 행 > '시작일' 값"
    ),
    "행사종료일": (
        "메인 표 > '전환청구기간'|'교환청구기간'|'권리행사기간'|'행사기간' 행 > '종료일' 값"
    ),
    "투자자": (
        "'특정인에 대한 대상자별 사채발행내역' 표 > 발행 대상자명 + 발행권면총액"
    ),
}


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
            self._append_warning(
                "사채 발행 주요 표를 찾지 못했습니다. HTML 양식이 예상과 달라 일부 필드가 비어 있을 수 있습니다."
            )

    def extract_round_from_bond_type_row(self) -> str | None:
        value = self.rows.value_after("사채의 종류", "회차")
        self._set_value_status("회차", value)
        return value

    def extract_security_type_from_title(self, title: str) -> str | None:
        """공시 제목을 기반으로 CB/EB/BW 여부를 판별한다."""
        text = title
        if "신주인수권부사채" in text:
            value = "BW"
        elif "교환사채" in text:
            value = "EB"
        elif "전환사채" in text:
            value = "CB"
        else:
            value = None
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
            value = _target_stock_value(self.rows.values, target_label)
            if value is not None:
                return value
        for target_label in EXERCISE_TARGET_LABELS:
            value = _target_stock_value_after_adjacent_kind_cell(
                self.rows.values, target_label
            )
            if value is not None:
                return value
        return None

    def extract_issue_amount_from_bond_face_value_row(self) -> int | None:
        row = self._issue_amount_row()
        value = self._last_int_after_first_cell(row)
        if value is None:
            status = "source_not_found"
        elif value == 0:
            status = "explicit_zero"
        else:
            status = "parsed"
        self._set_field_status("발행금액", status)
        return value

    def _issue_amount_row(self) -> list[str]:
        return _issue_amount_row(self.rows.values)

    def _last_int_after_first_cell(self, row: list[str]) -> int | None:
        for cell in reversed(row[1:]):
            parsed = parse_int(cell, dash_as_zero=True)
            if parsed is not None:
                return parsed
        return None

    def extract_funding_purposes_from_funding_purpose_rows(
        self,
    ) -> list[list[Any]] | None:
        """자금조달 목적 행에 적힌 목적명과 금액을 표에 나온 순서대로 추출한다."""
        purposes: list[list[Any]] = []
        found_amount_source = False
        for row in self.rows.values:
            if not row_contains(row, "자금조달의 목적"):
                continue
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
        return _clean_funding_purpose_label(value)

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
    ) -> int | float | None:
        """전환/교환/신주인수권 행사가액을 추출한다."""
        value = None
        for price_label in EXERCISE_PRICE_LABELS:
            value = _strict_price_value_after_label(self.rows.values, price_label)
            if value is not None:
                break
        self._set_value_status("행사가액", value)
        return value

    def extract_payment_date_from_payment_date_row(self) -> str | None:
        value = self.rows.last_labeled_value("납입일")
        self._set_value_status("납입일", value)
        return value

    def extract_maturity_date_from_bond_maturity_row(self) -> str | None:
        value = self.rows.last_value("사채만기일")
        if value is None:
            value = self.rows.last_value("사채만기")
        self._set_value_status("만기일", value)
        return value

    def extract_issue_method_from_bond_issue_method_row(self) -> str | None:
        value = self.rows.last_value("사채발행방법")
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
            value = self.rows.last_value(period_label, boundary_label)
            if value is not None:
                return value
        return None

    def extract_investors_from_specific_person_bond_issue_table(
        self,
    ) -> list[list[Any]] | None:
        """사채 발행 대상자(인수자)와 배정 권면액을 추출한다."""
        for rows in self._specific_person_bond_issue_table_rows():
            header = rows[0]
            name_index = _first_header_index(header, "발행 대상자명")
            amount_index = _first_header_index(header, "발행권면")
            if name_index is None or amount_index is None:
                continue
            targets: list[list[Any]] = []
            for row in rows[1:]:
                target_name = row[name_index] if name_index < len(row) else ""
                target_name = clean_text(target_name)
                if not row or target_name in {"", "-", "합계", "총계", "계"}:
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
        source_tables: list[list[list[str]]] = []
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
                    source_tables.append(rows)
        return source_tables

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


def _issue_amount_row(rows: list[list[str]]) -> list[str]:
    amount_rows = [row for row in rows if row_contains(row, "사채의 권면")]
    for row in amount_rows:
        if row_contains(row, "원화기준"):
            return row
    return amount_rows[0] if amount_rows else []


def _first_header_index(row: list[str], label: str) -> int | None:
    for index, cell in enumerate(row):
        if row_contains([cell], label):
            return index
    return None


def _target_stock_value(rows: list[list[str]], label: str) -> str | None:
    compact_label = _compact(label)
    for row in rows:
        for index, cell in enumerate(row[:-1]):
            compact_cell = _compact(cell)
            if compact_label not in compact_cell:
                continue
            if "대상" in compact_label and not (
                compact_cell == compact_label
                or "종류" in compact_cell
                or "유가증권" in compact_cell
            ):
                continue
            if "대상" not in compact_label and "종류" not in compact_cell:
                continue
            return row[index + 1]
        for cell in row:
            value = _target_stock_value_inside_cell(cell, label)
            if value is not None:
                return value
    return None


def _target_stock_value_after_adjacent_kind_cell(
    rows: list[list[str]], label: str
) -> str | None:
    compact_label = _compact(label)
    if "대상" in compact_label:
        return None
    for row in rows:
        for index, cell in enumerate(row[:-2]):
            if compact_label not in _compact(cell):
                continue
            if _compact(row[index + 1]) == "종류":
                return row[index + 2]
    return None


def _target_stock_value_inside_cell(cell: str, label: str) -> str | None:
    label_pattern = r"\s*".join(map(re.escape, _compact(label)))
    suffix_pattern = r"(?:종류|유가증권)" if "대상" in _compact(label) else r"종류"
    pattern = re.compile(
        rf"{label_pattern}[^:：]{{0,40}}{suffix_pattern}\s*[:：]\s*(?P<value>.+)"
    )
    match = pattern.search(cell)
    if match is None:
        return None
    value = _trim_inline_target_value(match.group("value"))
    if not value or len(value) > 120:
        return None
    return value


def _trim_inline_target_value(value: str) -> str | None:
    text = clean_text(value)
    text = re.split(
        r"\s+(?:\(\d+\)|\d+\)|\d+\.\s|[가-하]\.|\d+\s*[①②③④⑤⑥⑦⑧⑨⑩]|[①②③④⑤⑥⑦⑧⑨⑩])",
        text,
        maxsplit=1,
    )[0]
    text = clean_text(text.strip(" .;:：-/"))
    return text or None


def _strict_price_value_after_label(
    rows: list[list[str]], label: str
) -> int | float | None:
    compact_label = _compact(label)
    for row in rows:
        for index, cell in enumerate(row):
            compact_cell = _compact(cell)
            if compact_label not in compact_cell:
                continue
            if _is_exercise_price_explanation_cell(compact_cell):
                continue
            value = _last_strict_price_value(row[index + 1 :])
            if value is not None:
                return value
    return None


def _is_exercise_price_explanation_cell(compact_cell: str) -> bool:
    return any(word in compact_cell for word in ("결정방법", "조정", "한도"))


def _last_strict_price_value(values: list[str]) -> int | float | None:
    for value in reversed(values):
        parsed = _parse_strict_price_value(value)
        if parsed is not None:
            return parsed
    return None


def _parse_strict_price_value(value: str | None) -> int | float | None:
    text = clean_text(value)
    if not text:
        return None
    text = re.sub(r"\(\s*원\s*(?:/\s*주)?\s*\)", "", text)
    text = re.sub(r"\s*원\s*(?:/\s*주)?\s*$", "", text)
    text = clean_text(text)
    if not re.fullmatch(r"\d[\d,\s]*(?:\.\d+)?", text):
        return None
    numeric_text = re.sub(r"\s+", "", text).replace(",", "")
    if "." in numeric_text:
        return float(numeric_text)
    return int(numeric_text)


def _compact(value: str) -> str:
    return clean_text(value).replace(" ", "")
