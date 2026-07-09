"""유무상증자 공시 파서 엔트리포인트."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .extractor import RightsIssuanceExtractor
from .models import RightsIssuanceRecord
from .utils import _build_rights_parse_context


def parse_rights_issuance(
    html_text: str | bytes, *, file_path: str | Path, title: str | None = None
) -> dict[str, Any]:
    """증자 HTML을 파싱한다."""
    context = _build_rights_parse_context(
        html_text, file_path=file_path, title=title
    )
    record = context.record
    if not record.get("title"):
        _append_strong_warning(record, "주입 제목이 없습니다.")
    if context.issuance_type == "unknown":
        warning = "주입 제목에서 유상증자/무상증자 유형을 확인하지 못했습니다. 일부 필드가 비어 있을 수 있습니다."
        _append_strong_warning(record, warning)

    extractor = RightsIssuanceExtractor(context)
    stock_counts = extractor.get_stock_types_and_counts()
    pre_issuance_stock_counts = extractor.get_pre_issuance_stock_counts()
    funding_purposes = extractor.get_funding_purposes()
    issue_prices = extractor.get_issue_prices()
    issue_method = extractor.get_issue_method()
    payment_date = extractor.get_payment_date()
    delivery_date = extractor.get_delivery_date()
    listing_date = extractor.get_listing_date()
    issue_targets = extractor.get_issue_targets(stock_counts=stock_counts)
    extractor.validate_consistency(
        stock_counts=stock_counts,
        pre_issuance_stock_counts=pre_issuance_stock_counts,
        funding_purposes=funding_purposes,
        issue_prices=issue_prices,
        issue_targets=issue_targets,
    )
    issuance_type, paid_detail, bonus_detail = extractor.build_type_details(
        stock_counts=stock_counts,
        pre_issuance_stock_counts=pre_issuance_stock_counts,
        funding_purposes=funding_purposes,
        issue_prices=issue_prices,
        issue_method=issue_method,
        payment_date=payment_date,
        delivery_date=delivery_date,
        listing_date=listing_date,
        issue_targets=issue_targets,
    )

    schema_record = RightsIssuanceRecord(
        증자유형=issuance_type,
        신주의_종류와_수=stock_counts,
        증자_전_발행주식총수=pre_issuance_stock_counts,
        발행목적=funding_purposes,
        발행가액=issue_prices,
        증자방식=issue_method,
        납입일=payment_date,
        신주권교부예정일=delivery_date,
        상장예정일=listing_date,
        발행대상자=issue_targets,
        유상증자=paid_detail,
        무상증자=bonus_detail,
    )

    record.update(schema_record.to_dict())
    if extractor.warnings:
        record["parse_warnings"] = [
            *record.get("parse_warnings", []),
            *extractor.warnings,
        ]
    if extractor.weak_warnings:
        record["weak_warning"] = extractor.weak_warnings
    if extractor.medium_warnings:
        record["medium_warning"] = [
            *record.get("medium_warning", []),
            *extractor.medium_warnings,
        ]
    if extractor.strong_warnings:
        record["strong_warning"] = [
            *record.get("strong_warning", []),
            *extractor.strong_warnings,
        ]
    if extractor.field_parse_status:
        record["field_parse_status"] = extractor.field_parse_status
    if extractor.field_parse_status_detail:
        record["field_parse_status_detail"] = extractor.field_parse_status_detail
    return record


def _append_strong_warning(record: dict[str, Any], warning: str) -> None:
    for key in ("strong_warning", "parse_warnings"):
        values = record.setdefault(key, [])
        if warning not in values:
            values.append(warning)
