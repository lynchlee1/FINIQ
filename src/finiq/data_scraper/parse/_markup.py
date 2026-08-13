"""HTML decode, lxml recovery parse, and shared BeautifulSoup helpers."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup, Tag, UnicodeDammit
from lxml import etree


def normalize_html_attribute_value(value: Any) -> Any:
    """HTML 속성 값을 JSON serialization에 맞는 형태로 바꾼다."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if value is None:
        return None
    return str(value)


def get_tag_attributes(tag: Tag) -> dict[str, Any]:
    """태그의 속성을 string 중심 dict로 추출한다."""
    return {str(key): normalize_html_attribute_value(value) for key, value in tag.attrs.items()}


def decode_html_markup(html_markup: str | bytes) -> str:
    """HTML 입력을 안전한 string markup으로 decode한다."""
    if isinstance(html_markup, str):
        return html_markup
    dammit = UnicodeDammit(html_markup, is_html=True)
    if dammit.unicode_markup is not None:
        return dammit.unicode_markup
    raise ValueError("Unable to decode HTML markup")


def parse_html_with_recovery(html_markup: str | bytes) -> BeautifulSoup:
    """깨진 HTML도 최대한 복구해서 BeautifulSoup로 파싱한다.

    KIND 응답은 종종 완전한 XHTML이 아니므로,
    lxml recovery parser를 먼저 거쳐 후속 serialization이 가능한 형태로 맞춘다.
    """
    decoded_markup = decode_html_markup(html_markup)
    parser = etree.HTMLParser(recover=True, huge_tree=True)
    root = etree.HTML(decoded_markup, parser=parser)
    if root is None:
        raise ValueError("Failed to parse HTML document")
    recovered_markup = etree.tostring(root, encoding="unicode", method="html")
    return BeautifulSoup(recovered_markup, "lxml")


def _tag_text(tag: Tag) -> str:
    """태그의 표시용 텍스트를 정리해서 반환한다."""
    return tag.get_text(separator=" ", strip=True)


def _tag_inner_html(tag: Tag) -> str:
    """태그 내부 HTML만 잘라서 반환한다."""
    return tag.decode_contents().strip()


def _clean_text(value: str | None) -> str:
    """공백이 섞인 텍스트를 화면 기준 문자열로 정리한다."""
    return " ".join((value or "").split())
