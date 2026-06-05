"""Shareholder meeting disclosure parser."""

from __future__ import annotations

from typing import Any
from bs4 import BeautifulSoup

from .._markup import parse_html_with_recovery
from ..metadata import extract_viewer_metadata
from ..table_dict import parse_table_to_dicts

def parse_shareholder_meeting(external_html: str | bytes, internal_html: str | bytes) -> dict[str, Any]:
    """외부 메타데이터와 내부 HTML의 테이블 정보를 결합하여 주주총회 정보를 추출한다."""
    
    # 1. 메타데이터 추출
    metadata = extract_viewer_metadata(external_html)
    
    # 2. 내부 HTML 파싱 및 테이블 추출
    soup = parse_html_with_recovery(internal_html)
    tables = soup.find_all("table")
    
    elections = []
    
    for table in tables:
        table_dicts = parse_table_to_dicts(table)
        if not table_dicts:
            continue
            
        # 첫 번째 행(딕셔너리)의 키들을 확인하여 선임 내역 테이블인지 식별
        first_row_keys = list(table_dicts[0].keys())
        
        # '성명' 컬럼이 있는 테이블이라면 이사/감사 선임 테이블로 간주
        if "성명" in first_row_keys:
            for row in table_dicts:
                name = row.get("성명")
                if name and name != "-":
                    elections.append({
                        "name": name,
                        "birth_month": row.get("출생년월", ""),
                        "term": row.get("임기", ""),
                        "is_new": row.get("신규선임여부", ""),
                        "is_full_time": row.get("상근여부", ""),
                    })
                    
    return {
        "metadata": metadata,
        "elections": elections
    }
