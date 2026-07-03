"""유무상증자 공시 파서 엔트리포인트."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .extractor import RightsIssuanceExtractor
from .models import RightsIssuanceRecord
from .utils import _build_rights_parse_context


def parse_rights_issuance(
    html_text: str | bytes, *, file_path: str | Path
) -> dict[str, Any]:
    """증자 HTML을 파싱한다."""
    context = _build_rights_parse_context(html_text, file_path=file_path)
    record = context.record
    if context.issuance_type == "unknown":
        record["parse_warnings"] = [
            "공시 제목에서 유상증자/무상증자 유형을 확인하지 못했습니다. 일부 필드가 비어 있을 수 있습니다."
        ]

    extractor = RightsIssuanceExtractor(context)

    schema_record = RightsIssuanceRecord(
        신주의_종류와_수=extractor.get_stock_types_and_counts(),
        발행목적=extractor.get_funding_purposes(),
        발행가액=extractor.get_issue_prices(),
        기준주가=extractor.get_base_prices(),
        증자방식=extractor.get_issue_method(),
        납입일=extractor.get_payment_date(),
        신주권교부예정일=extractor.get_delivery_date(),
        상장예정일=extractor.get_listing_date(),
        발행대상자=extractor.get_issue_targets(),
    )

    record.update(schema_record.to_dict())
    if extractor.warnings:
        record["parse_warnings"] = [
            *record.get("parse_warnings", []),
            *extractor.warnings,
        ]
    return record
