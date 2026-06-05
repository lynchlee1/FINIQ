"""Extract metadata from KIND disclosure viewer HTML."""

from __future__ import annotations

import re
from typing import Any

from ._snippets import viewer_html

_COMPANY_HEADER_RE = re.compile(r"^(.*?)(?:\s*\(([\dA-Za-z]+)\))?$")

def extract_viewer_metadata(html_markup: str | bytes) -> dict[str, Any]:
    """외부 뷰어 프레임 HTML에서 공시 메타데이터(회사명, 종목코드, 접수번호 등)를 추출한다."""
    parsed = viewer_html(html_markup)
    
    header = parsed.get("header", "")
    company_name = ""
    stock_code = None
    
    match = _COMPANY_HEADER_RE.match(header)
    if match:
        company_name = match.group(1).strip()
        stock_code = match.group(2)
        
    # Get submission date from the selected main doc if available
    submission_date = None
    main_docs = parsed.get("main_docs", [])
    for doc in main_docs:
        if doc.get("selected"):
            label = doc.get("label", "")
            # e.g., "임시주주총회결과 (2018.01.02)"
            date_match = re.search(r"\((20\d{2}\.\d{2}\.\d{2})\)", label)
            if date_match:
                submission_date = date_match.group(1)
            break
            
    return {
        "acpt_no": parsed.get("acpt_no"),
        "company_name": company_name,
        "stock_code": stock_code,
        "title": parsed.get("title"),
        "doc_no": parsed.get("selected_main_doc_no"),
        "submission_date": submission_date,
    }
