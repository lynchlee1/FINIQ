"""HTML I/O 및 파싱, 뷰어 콘텐츠 복원 유틸리티."""

from __future__ import annotations

from pathlib import Path
from lxml import html


def decode_html_markup(html_markup: str | bytes) -> str:
    """HTML 마크업을 문자열로 디코딩한다.

    과거 KIND 공시는 레거시 인코딩(euc-kr 등)인 경우가 많다. 
    일부 바이트 손실이 있더라도 전체 파싱이 중단되지 않도록 여러 인코딩을 순차적으로 시도한다.
    """
    if isinstance(html_markup, str):
        return html_markup
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return html_markup.decode(encoding)
        except UnicodeDecodeError:
            continue
    return html_markup.decode("utf-8", errors="replace")


def parse_html_document(html_markup: str | bytes) -> html.HtmlElement:
    """불완전한 구조의 HTML을 lxml 문서 객체로 파싱한다.

    뷰어 HTML은 유효한 마크업이 아닐 수 있으므로 `recover=True` 옵션을 통해 
    최대한 유연하게 텍스트 및 테이블을 추출한다.
    """
    parser = html.HTMLParser(encoding="utf-8", recover=True, huge_tree=True)
    decoded = decode_html_markup(html_markup)
    document = html.fromstring(decoded, parser=parser)
    return document


def fetch_selected_viewer_body(
    html_text: str | bytes, *, file_path: str | Path | None = None
) -> bytes | None:
    """뷰어 HTML과 짝을 이루는 실제 본문 HTML 바이트를 로컬 디렉터리에서 찾는다."""
    if not file_path:
        return None

    path = Path(file_path).resolve()
    content_directory_names = ("viewer_html_contents", "kind_html_contents")
    for content_directory_name in content_directory_names:
        content_path = path.parent.parent / content_directory_name / path.name
        if content_path.is_file():
            return content_path.read_bytes()

    return None
