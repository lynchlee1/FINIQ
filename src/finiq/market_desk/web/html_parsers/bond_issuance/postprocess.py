"""사채 발행 파서 후처리 로직."""

from __future__ import annotations

from typing import Any

from .extractor import BOND_FIELD_EXTRACTION_RULES

_MAIN_TABLE_WARNING = (
    "사채 발행 주요 표를 찾지 못했습니다. HTML 양식이 예상과 달라 일부 필드가 비어 있을 수 있습니다."
)


def apply_bond_issuance_postprocess(
    record: dict[str, Any],
    *,
    main_rows: list[list[str]],
    has_funding_purpose_amount_source: bool,
    has_investor_source_table: bool,
) -> None:
    """최종 record에 파싱 상태, 경고, 검증 결과를 추가한다."""
    if not main_rows:
        _append_warning(record, _MAIN_TABLE_WARNING, level="strong")

    field_parse_status = _build_field_parse_status(
        record,
        has_funding_purpose_amount_source=has_funding_purpose_amount_source,
        has_investor_source_table=has_investor_source_table,
    )
    if field_parse_status:
        record["field_parse_status"] = field_parse_status

    for field_name, status in field_parse_status.items():
        if status == "source_not_found":
            rule = BOND_FIELD_EXTRACTION_RULES[field_name]
            warning = f"{field_name}: 정해진 출처에서 값을 찾지 못했습니다. 출처: {rule}"
            _append_warning(record, warning, level="strong")

    _append_funding_purpose_sum_warning(record)


def _build_field_parse_status(
    record: dict[str, Any],
    *,
    has_funding_purpose_amount_source: bool,
    has_investor_source_table: bool,
) -> dict[str, str]:
    status: dict[str, str] = {}
    for field_name in BOND_FIELD_EXTRACTION_RULES:
        if field_name == "발행금액":
            status[field_name] = _issue_amount_status(record.get(field_name))
        elif field_name == "발행목적":
            status[field_name] = _funding_purpose_status(
                record.get(field_name),
                has_funding_purpose_amount_source,
            )
        elif field_name == "투자자":
            status[field_name] = _investor_status(
                record.get(field_name),
                has_investor_source_table,
            )
        else:
            status[field_name] = _default_status(record.get(field_name))
    return status


def _default_status(value: Any) -> str:
    return "source_not_found" if value in (None, "", []) else "parsed"


def _issue_amount_status(value: Any) -> str:
    if value is None:
        return "source_not_found"
    return "explicit_zero" if value == 0 else "parsed"


def _funding_purpose_status(value: Any, has_amount_source: bool) -> str:
    if value:
        return "parsed"
    if has_amount_source:
        return "explicit_zero"
    return "source_not_found"


def _investor_status(value: Any, has_source_table: bool) -> str:
    if value:
        return "parsed"
    if has_source_table:
        return "explicit_zero"
    return "source_not_found"


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
