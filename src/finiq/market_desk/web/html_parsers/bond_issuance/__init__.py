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
        record_dict["parse_warnings"] = [
            "사채 발행 주요 표를 찾지 못했습니다. HTML 양식이 예상과 달라 일부 필드가 비어 있을 수 있습니다."
        ]

    extractor = BondIssuanceExtractor(context)
    title = record_dict.get("title") or ""
    listing_market = record_dict.pop("상장시장", None)

    schema_record = BondIssuanceRecord(
        기업명_발행사=record_dict.get("기업명(발행사)"),
        회차=extractor.get_round_number(),
        종류=extractor.get_security_type(title),
        기업명_행사대상=extractor.get_target_company_name(),
        상장구분=listing_market,
        발행금액=extractor.get_issue_amount(),
        행사가액=extractor.get_exercise_price(),
        납입일=extractor.get_payment_date(),
        만기일=extractor.get_maturity_date(),
        행사시작일=extractor.get_exercise_period_start(),
        행사종료일=extractor.get_exercise_period_end(),
        투자자=extractor.get_issue_targets(),
        발행대상자세부엔티티=extractor.get_issue_target_entities(),
    )

    record_dict.update(schema_record.to_dict())
    return record_dict
