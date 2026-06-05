"""사채 발행 파서 추출 로직."""

from __future__ import annotations

import re
from typing import Any

from ..common import clean_text, last_int, non_correction_tables, row_contains
from .utils import _BondParseContext


class BondIssuanceExtractor:
    """사채 발행 공시의 실제 필드별 추출 로직을 모아둔 클래스."""

    def __init__(self, context: _BondParseContext):
        self.context = context
        self.rows = context.rows

    def get_round_number(self) -> str | None:
        return self.rows.value_after("사채의 종류", "회차")

    def get_security_type(self, title: str) -> str | None:
        """공시 제목 및 사채 종류 행 텍스트를 기반으로 CB/EB/BW 여부를 판별한다."""
        bond_text = " ".join(self.rows.containing("사채의 종류"))
        text = f"{title} {bond_text}"
        if "신주인수권부사채" in text:
            return "BW"
        if "교환사채" in text:
            return "EB"
        if "전환사채" in text:
            return "CB"
        return None

    def get_target_company_name(self) -> str | None:
        """대상 주식 문구에서 불필요한 법인 형태 및 주식 종류 표현을 제거하여 순수 회사명만 남긴다."""
        target_text = self._exercise_target()
        text = clean_text(target_text)
        if not text:
            return None
        cleaned = text
        replacements = (
            r"\(주\)",
            r"㈜",
            r"주식회사",
            r"기명식",
            r"무기명식",
            r"보통주식?",
            r"보통주?"
            r"주식",
        )
        for pattern in replacements:
            cleaned = re.sub(pattern, " ", cleaned)
        cleaned = clean_text(cleaned.strip(" -_/·,"))
        return cleaned or text

    def _exercise_target(self) -> str | None:
        """전환/교환/신주인수권 행사로 발행될 대상 주식 관련 문구를 추출한다."""
        for target_label in (
            "교환대상",
            "전환에 따라",
            "전환으로 발행할",
            "인수권행사에 따라",
        ):
            value = self.rows.last_value(target_label, "종류")
            if value is not None:
                return value
        return None

    def get_issue_amount(self) -> int | None:
        return self.rows.last_int("사채의 권면")

    def get_exercise_price(self) -> int | None:
        """전환/교환/신주인수권 행사가액을 추출한다."""
        for price_label in ("전환가액", "교환가액", "행사가액"):
            value = self.rows.last_int(price_label, "원")
            if value is not None:
                return value
        return None

    def get_payment_date(self) -> str | None:
        return self.rows.last_labeled_value("납입일")

    def get_maturity_date(self) -> str | None:
        return self.rows.last_value("사채만기일")

    def get_exercise_period_start(self) -> str | None:
        return self._exercise_period_value("시작일")

    def get_exercise_period_end(self) -> str | None:
        return self._exercise_period_value("종료일")

    def _exercise_period_value(self, boundary_label: str) -> str | None:
        """전환/교환/권리행사 청구기간의 시작일 또는 종료일을 추출한다."""
        for period_label in ("전환청구기간", "교환청구기간", "권리행사기간"):
            value = self.rows.last_value(period_label, boundary_label)
            if value is not None:
                return value
        return None

    def get_issue_targets(self) -> list[list[Any]]:
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
            return targets
        return []

    def get_issue_target_entities(self) -> list[list[str]]:
        """발행 대상자의 명칭, 대표자, 최대주주 정보를 추출하여 그룹화한다."""
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
