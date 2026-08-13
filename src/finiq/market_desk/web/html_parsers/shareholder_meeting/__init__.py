"""주주총회 공시 파서 엔트리포인트."""
from __future__ import annotations
from pathlib import Path
from typing import Any

from finiq.data_scraper.parse.domain.shareholder_meeting import (
    extract_shareholder_meeting_details,
    shareholder_meeting_mode_from_title,
)
from ..common import build_base_record

MODE = "shareholder_meeting"

def parse_shareholder_meeting(
    html_text: str | bytes,
    *,
    file_path: str | Path,
    title: str | None = None,
    reporting_company_name: str | None = None,
) -> dict[str, Any]:
    """주주총회 HTML을 공통 v1 아키텍처 레코드로 파싱한다."""
    record = build_base_record(html_text, file_path=file_path, mode=MODE)
    
    # 웹 파서와 스크래퍼 간의 레이아웃 해석 일관성을 위해, 
    # 주주총회 전용 필드 추출 로직은 data-scraper 도메인 모듈에 위임한다.
    return {
        **record,
        **extract_shareholder_meeting_details(
            html_text,
            mode=shareholder_meeting_mode_from_title(title),
            reporting_company_name=reporting_company_name,
        ),
    }
