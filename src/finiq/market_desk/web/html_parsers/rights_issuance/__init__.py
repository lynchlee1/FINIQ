"""유무상증자 공시 파서 엔트리포인트."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import RightsIssuanceRecord
from .extractor import RightsIssuanceExtractor
from .utils import _main_rights_rows

from ..common import build_base_record, fetch_selected_viewer_body

MODE = "rights_issuance"

def parse_rights_issuance(
    html_text: str | bytes, *, file_path: str | Path
) -> dict[str, Any]:
    """증자 HTML을 파싱한다."""
    record = build_base_record(html_text, file_path=file_path, mode=MODE)
    rows = _main_rights_rows(record["raw_tables"])
    if not rows:
        # 뷰어 HTML에는 문서 선택기 및 메타데이터만 존재하고 본문이 누락될 수 있다.
        # 동일 폴더 내 본문 HTML이 있다면 이를 파싱하되, 래퍼의 정정 메타데이터와 접수번호는 유지한다.
        body_html = fetch_selected_viewer_body(html_text, file_path=file_path)
        if body_html is not None:
            original_title = record.get("title") or ""
            original_correction_families = record.get("correction_families")
            original_rcept_no = record.get("rcept_no")
            original_acpt_no = record.get("acpt_no")
            record = build_base_record(body_html, file_path=file_path, mode=MODE)
            if not record.get("title"):
                record["title"] = original_title
            if not record.get("correction_families") and original_correction_families:
                record["correction_families"] = original_correction_families
            if not record.get("rcept_no") and original_rcept_no:
                record["rcept_no"] = original_rcept_no
            if original_acpt_no:
                record["acpt_no"] = original_acpt_no
            rows = _main_rights_rows(record["raw_tables"])
    if not rows:
        record["parse_warnings"] = [
            "유무상증자 주요 표를 찾지 못했습니다. HTML 양식이 예상과 달라 일부 필드가 비어 있을 수 있습니다."
        ]

    extractor = RightsIssuanceExtractor(record["raw_tables"] if rows else [])

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
        발행대상자세부엔티티=extractor.get_issue_target_entities(),
    )

    record.update(schema_record.to_dict())
    return record
