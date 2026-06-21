"""KIND content HTML section splitting helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Callable

from lxml import etree, html

from finiq.market_desk.web.html_parsers.common import decode_html_markup

ProgressCallback = Callable[[str], None]
_TOC_ID_RE = re.compile(r"^toc_(\d+)$")
DEFAULT_REPORT_LIMIT = 50


@dataclass(frozen=True)
class HtmlSection:
    toc_id: str
    index: int
    title: str
    html: str


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _element_html(element: etree._Element) -> str:
    return html.tostring(element, encoding="unicode", method="html")


def _toc_index(toc_id: str, fallback: int) -> int:
    match = _TOC_ID_RE.match(toc_id)
    if match:
        return int(match.group(1))
    return fallback


def _body_direct_children(document: html.HtmlElement) -> list[etree._Element]:
    body_nodes = document.xpath("//body")
    if body_nodes:
        return list(body_nodes[0])
    return list(document)


def _body_attrs(document: html.HtmlElement) -> str:
    body_nodes = document.xpath("//body")
    if not body_nodes:
        return ""
    attrs = []
    for key, value in body_nodes[0].attrib.items():
        if key.lower() == "style":
            continue
        attrs.append(f'{key}="{escape(str(value), quote=True)}"')
    return (" " + " ".join(attrs)) if attrs else ""


def _head_markup(document: html.HtmlElement) -> str:
    head_nodes = document.xpath("//head")
    if not head_nodes:
        return '<meta charset="UTF-8">'
    return "".join(_element_html(child) for child in head_nodes[0])


def _section_title(heading: etree._Element, section_children: list[etree._Element]) -> str:
    title = _clean_text(heading.text_content())
    if title:
        return title
    for child in section_children[1:4]:
        title = _clean_text(child.text_content())
        if title:
            return title
    return ""


def _wrap_section_html(document: html.HtmlElement, section_markup: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        f"{_head_markup(document)}\n"
        "</head>\n"
        f"<body{_body_attrs(document)}>\n"
        f"{section_markup}\n"
        "</body>\n"
        "</html>\n"
    )


def _is_toc_heading(element: etree._Element) -> bool:
    if not isinstance(element.tag, str):
        return False
    if element.tag.lower() != "h2":
        return False
    return bool(_TOC_ID_RE.match(str(element.get("id") or "").strip()))


def _is_legacy_section_heading(element: etree._Element) -> bool:
    if not isinstance(element.tag, str):
        return False
    if element.tag.lower() != "p":
        return False
    class_names = set(str(element.get("class") or "").split())
    if "SECTION-1" not in class_names:
        return False
    return bool(_clean_text(element.text_content()))


def split_content_html_sections(html_markup: str | bytes) -> list[HtmlSection]:
    """Split a KIND content HTML document by top-level TOC headings."""
    parser = html.HTMLParser(encoding="utf-8", recover=True, huge_tree=True)
    document = html.fromstring(decode_html_markup(html_markup), parser=parser)
    children = _body_direct_children(document)
    heading_positions: list[tuple[int, etree._Element]] = []
    for position, child in enumerate(children):
        if _is_toc_heading(child):
            heading_positions.append((position, child))
    if not heading_positions:
        heading_positions = [
            (position, child)
            for position, child in enumerate(children)
            if _is_legacy_section_heading(child)
        ]

    sections: list[HtmlSection] = []
    for order, (start, heading) in enumerate(heading_positions, start=1):
        end = heading_positions[order][0] if order < len(heading_positions) else len(children)
        toc_id = str(heading.get("id") or "").strip() or f"toc_{order}"
        section_children = children[start:end]
        section_markup = "".join(_element_html(child) for child in section_children)
        sections.append(
            HtmlSection(
                toc_id=toc_id,
                index=_toc_index(toc_id, order),
                title=_section_title(heading, section_children),
                html=_wrap_section_html(document, section_markup),
            )
        )
    return sections


def _parse_report_limit(value: Any) -> int:
    if value in (None, ""):
        return DEFAULT_REPORT_LIMIT
    parsed = int(value)
    if parsed < 0:
        msg = "report_limit must be >= 0"
        raise ValueError(msg)
    return parsed


def inspect_disclosure_html_sections_payload(body: dict[str, Any]) -> dict[str, Any]:
    input_directory_raw = str(body.get("input_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()
    if not input_directory.is_dir():
        msg = f"input_directory does not exist: {input_directory}"
        raise ValueError(msg)

    html_files = _collect_html_files(input_directory, _parse_limit(body.get("limit")))
    documents: list[dict[str, Any]] = []
    problem_files: list[dict[str, str]] = []
    files_without_sections = 0
    failed_files = 0
    report_limit = _parse_report_limit(body.get("report_limit"))
    for source_file in html_files:
        try:
            sections = split_content_html_sections(source_file.read_bytes())
        except Exception as exc:
            failed_files += 1
            if len(problem_files) < report_limit:
                problem_files.append({"kind": "read_failed", "source_file": str(source_file), "error": str(exc)})
            continue
        if not sections:
            files_without_sections += 1
            if len(problem_files) < report_limit:
                problem_files.append({"kind": "no_sections", "source_file": str(source_file), "error": ""})
            continue
        documents.append(
            {
                "source_file": str(source_file),
                "source_name": source_file.name,
                "source_relative_path": _relative_source_path(input_directory, source_file),
                "section_count": len(sections),
                "sections": [
                    {"toc_id": section.toc_id, "index": section.index, "title": section.title}
                    for section in sections
                ],
            }
        )

    total_files = len(html_files)
    return {
        "format": "finiq_disclosure_html_section_inspect_v1",
        "input_directory": str(input_directory),
        "summary": {
            "found_files": total_files,
            "documents_with_sections": len(documents),
            "files_without_sections": files_without_sections,
            "failed_files": failed_files,
            "reported_problem_files": len(problem_files),
        },
        "documents": documents,
        "problem_files": problem_files,
    }


def _collect_html_files(input_directory: Path, limit: int | None) -> list[Path]:
    files = sorted(
        (
            path
            for path in input_directory.rglob("*")
            if path.is_file() and path.suffix.lower() == ".html"
        ),
        key=lambda path: _relative_source_path(input_directory, path),
    )
    return files[:limit] if limit is not None else files


def _relative_source_path(input_directory: Path, source_file: Path) -> str:
    return source_file.relative_to(input_directory).as_posix()


def _parse_limit(value: Any) -> int | None:
    if value in (None, ""):
        return None
    parsed = int(value)
    if parsed < 1:
        msg = "limit must be >= 1"
        raise ValueError(msg)
    return parsed


def save_disclosure_html_sections_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    input_directory_raw = str(body.get("input_directory") or "").strip()
    output_directory_raw = str(body.get("output_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    if not output_directory_raw:
        msg = "output_directory is required"
        raise ValueError(msg)

    input_directory = Path(input_directory_raw).expanduser().resolve()
    output_directory = Path(output_directory_raw).expanduser().resolve()
    if not input_directory.is_dir():
        msg = f"input_directory does not exist: {input_directory}"
        raise ValueError(msg)
    if output_directory == input_directory:
        msg = "output_directory must be different from input_directory"
        raise ValueError(msg)

    html_files = _collect_html_files(input_directory, _parse_limit(body.get("limit")))
    output_directory.mkdir(parents=True, exist_ok=True)
    saved_files: list[str] = []
    skipped_files: list[dict[str, str]] = []
    progress_log: list[str] = []

    def emit(message: str) -> None:
        progress_log.append(message)
        if progress_callback is not None:
            progress_callback(message)

    emit(f"목차 분리 대상 HTML {len(html_files)}건을 찾았습니다.")
    for index, source_file in enumerate(html_files, start=1):
        try:
            sections = split_content_html_sections(source_file.read_bytes())
        except Exception as exc:
            skipped_files.append({"source_file": str(source_file), "error": str(exc)})
            emit(f"읽기 실패 {index}/{len(html_files)}: {source_file.name}")
            continue
        if not sections:
            skipped_files.append({"source_file": str(source_file), "error": "no sections found"})
            emit(f"목차 없음 {index}/{len(html_files)}: {source_file.name}")
            continue
        for section in sections:
            section_directory = output_directory / section.toc_id
            output_path = section_directory / source_file.relative_to(input_directory)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(section.html, encoding="utf-8")
            saved_files.append(str(output_path))
        if index == 1 or index == len(html_files) or index % 25 == 0:
            emit(f"목차 저장 중간 확인: {index}/{len(html_files)}건 처리.")

    emit(f"목차 HTML 저장 완료: {len(saved_files)}건")
    return {
        "format": "finiq_disclosure_html_section_save_v2",
        "input_directory": str(input_directory),
        "output_directory": str(output_directory),
        "summary": {
            "found_files": len(html_files),
            "saved_files": len(saved_files),
            "skipped_files": len(skipped_files),
        },
        "saved_files": saved_files,
        "skipped_files": skipped_files,
        "progress_log": progress_log[-200:],
    }
