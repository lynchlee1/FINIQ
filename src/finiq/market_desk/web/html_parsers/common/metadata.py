"""공시 기초 메타데이터 및 공통 레코드 구성 유틸리티."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lxml import html

from .io import parse_html_document
from .tables import extract_tables
from .text import clean_text, element_text


def _first_text(document: html.HtmlElement, xpath: str) -> str:
    for value in document.xpath(xpath):
        text = (
            element_text(value)
            if hasattr(value, "itertext")
            else clean_text(str(value))
        )
        if text:
            return text
    return ""


def extract_title(document: html.HtmlElement) -> str:
    """공시 제목을 SECTION-1 후보와 HTML title에서 추출한다."""
    return _first_text(
        document,
        "//p[contains(concat(' ', normalize-space(@class), ' '), ' SECTION-1 ')]",
    ) or _first_text(document, "//title/text()")


def extract_acpt_no(file_path: str | Path) -> str:
    """HTML 파일명을 기반으로 KIND 접수번호를 추론한다."""
    stem = Path(file_path).stem
    candidate = stem.split("_", 1)[0]
    return candidate if candidate.isdigit() else ""


def preserve_viewer_metadata(
    record: dict[str, Any], viewer_record: dict[str, Any]
) -> None:
    """본문 HTML 파싱 시 래퍼 HTML의 고유 메타데이터를 유지한다."""
    if not record.get("title"):
        record["title"] = viewer_record.get("title") or ""
    if not record.get("correction_families") and viewer_record.get(
        "correction_families"
    ):
        record["correction_families"] = viewer_record["correction_families"]
    if not record.get("rcept_no") and viewer_record.get("rcept_no"):
        record["rcept_no"] = viewer_record["rcept_no"]
    if viewer_record.get("acpt_no"):
        record["acpt_no"] = viewer_record["acpt_no"]


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
        "correction_families": {},
        "rcept_no": None,
        "acpt_no": acpt_no,
        "source_file": str(Path(file_path).resolve()),
        "mode": mode,
        "title": extract_title(document),
        "상장시장": None,
        "raw_tables": raw_tables,
        "raw_rows": [row for table in raw_tables for row in table["logical_rows"]],
    }
