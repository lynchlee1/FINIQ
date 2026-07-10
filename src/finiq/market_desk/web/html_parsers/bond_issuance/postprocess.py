"""사채 발행 파서 후처리 로직."""

from __future__ import annotations

from typing import Any


def apply_bond_issuance_postprocess(record: dict[str, Any]) -> None:
    """추출이 끝난 필드 사이의 합계 불일치를 검증한다."""
    _append_funding_purpose_sum_warning(record)
    _append_investor_sum_warning(record)


def _append_funding_purpose_sum_warning(record: dict[str, Any]) -> None:
    purposes = record.get("발행목적") or []
    issue_amount = record.get("발행금액")
    if not purposes or issue_amount is None:
        return
    total = sum(amount for _, amount in purposes)
    if total == issue_amount:
        return
    _append_warning(
        record,
        f"발행목적: 자금조달 목적 합계({total:,})가 발행금액({issue_amount:,})과 일치하지 않습니다.",
        level="weak",
    )


def _append_investor_sum_warning(record: dict[str, Any]) -> None:
    investors = record.get("투자자") or []
    issue_amount = record.get("발행금액")
    if not investors or issue_amount is None:
        return
    total = sum(amount for _, amount in investors)
    if total == issue_amount:
        return
    _append_warning(
        record,
        f"투자자: 발행권면총액 합계({total:,})가 발행금액({issue_amount:,})과 일치하지 않습니다.",
        level="weak",
    )


def _append_warning(record: dict[str, Any], warning: str, *, level: str) -> None:
    level_key = {
        "weak": "weak_warning",
        "medium": "medium_warning",
        "strong": "strong_warning",
    }[level]
    _append_unique(record.setdefault(level_key, []), warning)
    _append_unique(record.setdefault("parse_warnings", []), warning)


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
