"""HTML I/O 및 파싱, 뷰어 콘텐츠 복원 유틸리티."""

from __future__ import annotations

from lxml import html


def decode_html_markup(html_markup: str | bytes) -> str:
    """UTF-8 HTML 마크업을 문자열로 디코딩한다."""
    if isinstance(html_markup, str):
        return html_markup
    return html_markup.decode("utf-8")


def parse_html_document(html_markup: str | bytes) -> html.HtmlElement:
    """불완전한 구조의 HTML을 lxml 문서 객체로 파싱한다.

    뷰어 HTML은 유효한 마크업이 아닐 수 있으므로 `recover=True` 옵션을 통해
    최대한 유연하게 텍스트 및 테이블을 추출한다.
    """
    parser = html.HTMLParser(encoding="utf-8", recover=True, huge_tree=True)
    decoded = decode_html_markup(html_markup)
    document = html.fromstring(decoded, parser=parser)
    return document
