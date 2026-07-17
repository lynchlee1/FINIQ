"""Small KIND HTML/JS fragments: viewer page, onclick, searchContents paths."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from ._markup import _clean_text, decode_html_markup, parse_html_with_recovery

_PAGINATION_RE = re.compile(
    r"전체\s*<em>([\d,]+)</em>\s*건\s*:\s*<strong>([\d,]+)</strong>/([\d,]+)(?=[^\d,]|$)"
)


def pagination_info(html_markup: str | bytes) -> dict[str, int] | None:
    """KIND 결과 페이지 HTML에서 페이지네이션 정보를 추출한다.

    Returns ``{"total_items": 10653, "current_page": 2, "total_pages": 107}``
    or ``None`` if the pagination section is not found.
    """
    text = decode_html_markup(html_markup)
    match = _PAGINATION_RE.search(text)
    if match is None:
        return None
    return {
        "total_items": int(match.group(1).replace(",", "")),
        "current_page": int(match.group(2).replace(",", "")),
        "total_pages": int(match.group(3).replace(",", "")),
    }


_OPEN_DISCLS_VIEWER_RE = re.compile(
    r"openDisclsViewer\(\s*['\"](?P<acpt_no>[^'\"]*)['\"]\s*,\s*['\"](?P<doc_no>[^'\"]*)['\"]\s*\)"
)
_SET_PATH_RE = re.compile(
    r"parent\.setPath\(\s*'(?P<toc_loc_path>[^']*)'\s*,\s*'(?P<doc_loc_path>[^']*)'\s*,\s*"
    r"'(?P<doc_server_path>[^']*)'\s*,\s*'(?P<form_upclss_cd>[^']*)'\s*,\s*"
    r"'(?P<snd_loc_tp_cd>[^']*)'\s*\)"
)


def disclosure_onclick(onclick_value: str | None) -> dict[str, str | None] | None:
    """`openDisclsViewer(...)` onclick에서 KIND 접수번호와 문서번호를 추출한다."""
    if onclick_value is None:
        return None
    match = _OPEN_DISCLS_VIEWER_RE.search(str(onclick_value))
    if match is None:
        return None
    acpt_no = match.group("acpt_no").strip() or None
    doc_no = match.group("doc_no").strip() or None
    return {
        "acpt_no": acpt_no,
        "doc_no": doc_no,
    }


def _parse_viewer_doc_option(
    option_tag: Tag,
    *,
    select_id: str,
    select_name: str,
    option_index: int,
) -> dict[str, Any]:
    """뷰어 select option 1개를 문서 메타데이터로 정리한다."""
    raw_value = str(option_tag.get("value") or "").strip()
    doc_no = raw_value
    latest_flag = ""
    is_latest = None
    if "|" in raw_value:
        doc_no, latest_flag = raw_value.split("|", 1)
        latest_flag = latest_flag.strip().upper()
        if latest_flag:
            is_latest = latest_flag == "Y"

    doc_no = doc_no.strip()
    return {
        "select_id": select_id,
        "select_name": select_name,
        "option_index": option_index,
        "doc_no": doc_no,
        "label": _clean_text(option_tag.get_text(separator=" ", strip=True)),
        "value": raw_value,
        "latest_flag": latest_flag or None,
        "selected": option_tag.has_attr("selected"),
        "is_latest": is_latest,
    }


def _parse_viewer_doc_select(soup: BeautifulSoup, select_id: str) -> list[dict[str, Any]]:
    """뷰어 select box에서 실제 문서 option들만 추출한다."""
    select_tag = soup.find("select", id=select_id)
    if not isinstance(select_tag, Tag):
        return []

    documents: list[dict[str, Any]] = []
    select_name = str(select_tag.get("name") or "").strip()
    for option_index, option_tag in enumerate(select_tag.find_all("option")):
        document = _parse_viewer_doc_option(
            option_tag,
            select_id=select_id,
            select_name=select_name,
            option_index=option_index,
        )
        documents.append(document)
    return documents


def viewer_html(
    html_markup: str | bytes,
    *,
    require_complete_metadata: bool = False,
) -> dict[str, Any]:
    """KIND 공시 뷰어 HTML에서 acptNo와 본문/첨부 docNo 목록을 추출한다."""
    soup = parse_html_with_recovery(html_markup)

    header_tag = soup.find("h1", class_="ttl")
    acpt_no_input = soup.find("input", attrs={"name": "acptNo"})
    title_input = soup.find("input", attrs={"name": "tempTitle"})

    main_docs = _parse_viewer_doc_select(soup, "mainDoc")
    attached_docs = _parse_viewer_doc_select(soup, "attachedDoc")

    acpt_no = (
        str(acpt_no_input.get("value") or "").strip()
        if isinstance(acpt_no_input, Tag)
        else ""
    )
    if require_complete_metadata:
        if not acpt_no:
            raise ValueError("KIND viewer acptNo is required")
        for select_id, documents in (
            ("mainDoc", main_docs),
            ("attachedDoc", attached_docs),
        ):
            if not isinstance(soup.find("select", id=select_id), Tag):
                raise ValueError(f"KIND viewer {select_id} select is required")
            if not documents:
                raise ValueError(f"KIND viewer {select_id} options are required")
            invalid_option_indexes = [
                str(document["option_index"])
                for document in documents
                if not str(document.get("doc_no") or "").strip()
            ]
            if invalid_option_indexes:
                raise ValueError(
                    f"KIND viewer {select_id} option docNo is required: "
                    + ", ".join(invalid_option_indexes)
                )

    selected_main_doc_no = next(
        (document["doc_no"] for document in main_docs if document.get("selected")),
        None,
    )
    if require_complete_metadata and not selected_main_doc_no:
        raise ValueError("KIND viewer selected mainDoc is required")

    return {
        "acpt_no": acpt_no or None,
        "header": _clean_text(header_tag.get_text(separator=" ", strip=True))
        if isinstance(header_tag, Tag)
        else "",
        "title": str(title_input.get("value") or "").strip() if isinstance(title_input, Tag) else "",
        "main_docs": main_docs,
        "attached_docs": attached_docs,
        "selected_main_doc_no": selected_main_doc_no,
    }


def dart_main_doc_no(html_markup: str | bytes) -> str | None:
    """KIND 뷰어 HTML에서 기본 본문에 해당하는 DART 접수번호(docNo)를 반환한다."""
    parsed = viewer_html(html_markup)
    return parsed.get("selected_main_doc_no")


def search_paths(html_markup: str | bytes) -> dict[str, str] | None:
    """`searchContents` 응답 HTML에서 실제 문서 경로와 송신처 코드를 추출한다."""
    html_text = decode_html_markup(html_markup)
    match = _SET_PATH_RE.search(html_text)
    if match is None:
        return None
    return {
        "toc_loc_path": match.group("toc_loc_path"),
        "doc_loc_path": match.group("doc_loc_path"),
        "doc_server_path": match.group("doc_server_path"),
        "form_upclss_cd": match.group("form_upclss_cd"),
        "snd_loc_tp_cd": match.group("snd_loc_tp_cd"),
    }
