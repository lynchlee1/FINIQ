"""사채 발행 공시 파서 엔트리포인트."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .extractor import BondIssuanceExtractor
from .models import BondIssuanceRecord
from .postprocess import apply_bond_issuance_postprocess
from .utils import _build_bond_parse_context


def parse_bond_issuance(
    html_text: str | bytes, *, file_path: str | Path, title: str | None = None
) -> dict[str, Any]:
    """사채 발행 HTML을 파싱한다."""
    context = _build_bond_parse_context(html_text, file_path=file_path)
    record_dict = context.record
    extractor = BondIssuanceExtractor(context)

    supplied_title = str(title or "").strip()
    record_dict["title"] = supplied_title
    title = record_dict.get("title") or ""
    listing_market = record_dict.get("상장구분")
    schema_record = BondIssuanceRecord(
        corp_name=record_dict.get("corp_name"),
        회차=extractor.extract_round_from_bond_type_row(),
        종류=extractor.extract_security_type_from_title(title),
        기업명_행사대상=(
            extractor.extract_target_company_name_from_exercise_target_stock_row()
        ),
        상장구분=listing_market,
        발행금액=extractor.extract_issue_amount_from_bond_face_value_row(),
        발행목적=extractor.extract_funding_purposes_from_funding_purpose_rows(),
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
    if extractor.field_parse_status:
        record_dict["field_parse_status"] = extractor.field_parse_status
    if extractor.warnings:
        record_dict["parse_warnings"] = extractor.warnings
    if extractor.strong_warnings:
        record_dict["strong_warning"] = extractor.strong_warnings
    apply_bond_issuance_postprocess(record_dict)
    if not supplied_title:
        _append_strong_warning(record_dict, "주입 제목이 없습니다.")
    return record_dict


def _append_strong_warning(record: dict[str, Any], warning: str) -> None:
    for key in ("strong_warning", "parse_warnings"):
        values = record.setdefault(key, [])
        if warning not in values:
            values.append(warning)
