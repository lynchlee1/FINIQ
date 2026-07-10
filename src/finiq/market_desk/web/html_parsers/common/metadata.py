"""공시 기초 메타데이터 및 공통 레코드 구성 유틸리티."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import parse_html_document
from .tables import extract_tables


def extract_acpt_no(file_path: str | Path) -> str:
    """확장자를 제외한 HTML 파일명 전체를 KIND 접수번호로 사용한다."""
    return Path(file_path).stem


def build_base_record(
    html_markup: str | bytes,
    *,
    file_path: str | Path,
    mode: str,
) -> dict[str, Any]:
    """공시 HTML 파일의 기초가 되는 공통 파싱 레코드를 생성한다.

    유형별 파서는 반환된 레코드 위에 비즈니스 필드를 덧붙이는 구조로 동작한다.
    파싱 과정 전반에서 사용할 수 있도록 원본 테이블 데이터를 포함한다.
    """
    document = parse_html_document(html_markup)
    raw_tables = extract_tables(document)
    acpt_no = extract_acpt_no(file_path)
    return {
        "acpt_no": acpt_no,
        "mode": mode,
        "title": "",
        "상장구분": None,
        "raw_tables": raw_tables,
    }
