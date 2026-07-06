"""사채 발행 공시 파서 엔트리포인트."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import BondIssuanceRecord
from .extractor import BondIssuanceExtractor
from .utils import _build_bond_parse_context


def parse_bond_issuance(
    html_text: str | bytes, *, file_path: str | Path
) -> dict[str, Any]:
    """사채 발행 HTML을 파싱한다."""
    context = _build_bond_parse_context(html_text, file_path=file_path)
    record_dict = context.record
    if not context.rows.values:
        warning = "사채 발행 주요 표를 찾지 못했습니다. HTML 양식이 예상과 달라 일부 필드가 비어 있을 수 있습니다."
        record_dict["parse_warnings"] = [warning]
        record_dict["strong_warning"] = [warning]

    extractor = BondIssuanceExtractor(context)
    title = record_dict.get("title") or ""
    listing_market = record_dict.pop("상장시장", None)
    issue_amount = extractor.extract_issue_amount_from_bond_face_value_row()

    schema_record = BondIssuanceRecord(
        기업명_발행사=record_dict.get("기업명(발행사)"),
        회차=extractor.extract_round_from_bond_type_row(),
        종류=extractor.extract_security_type_from_title(title),
        기업명_행사대상=(
            extractor.extract_target_company_name_from_exercise_target_stock_row()
        ),
        상장구분=listing_market,
        발행금액=issue_amount,
        발행목적=extractor.extract_funding_purposes_from_funding_purpose_rows(
            issue_amount
        ),
        행사가액=(
            extractor.extract_exercise_price_from_conversion_exchange_or_warrant_price_row()
        ),
        납입일=extractor.extract_payment_date_from_payment_date_row(),
        만기일=extractor.extract_maturity_date_from_bond_maturity_row(),
        사채발행방법=extractor.extract_issue_method_from_bond_issue_method_row(),
        행사시작일=extractor.extract_exercise_period_start_from_claim_period_row(),
        행사종료일=extractor.extract_exercise_period_end_from_claim_period_row(),
        투자자=extractor.extract_investors_from_specific_person_bond_issue_table(),
    )

    record_dict.update(schema_record.to_dict())
    if extractor.warnings:
        record_dict.setdefault("parse_warnings", []).extend(extractor.warnings)
    if extractor.weak_warnings:
        record_dict["weak_warning"] = extractor.weak_warnings
    if extractor.medium_warnings:
        record_dict["medium_warning"] = [
            *record_dict.get("medium_warning", []),
            *extractor.medium_warnings,
        ]
    if extractor.strong_warnings:
        record_dict["strong_warning"] = [
            *record_dict.get("strong_warning", []),
            *extractor.strong_warnings,
        ]
    if extractor.field_parse_status:
        record_dict["field_parse_status"] = extractor.field_parse_status
    return record_dict
