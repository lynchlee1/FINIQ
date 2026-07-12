"""KIND content HTML section splitting helpers."""

from __future__ import annotations

import re
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

from lxml import etree, html

from finiq.market_desk.web.html_parsers.common import decode_html_markup

ProgressCallback = Callable[[str], None]
_TOC_ID_RE = re.compile(r"^toc_(\d+)$")
DEFAULT_REPORT_LIMIT = 50
DEFAULT_HTML_SECTION_WORKERS = 8
DEFAULT_HTML_SECTION_PAGE_SIZE = 20
T = TypeVar("T")


@dataclass(frozen=True)
class HtmlSection:
    toc_id: str
    index: int
    title: str
    html: str


@dataclass(frozen=True)
class HtmlSectionSummary:
    toc_id: str
    index: int
    title: str


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _element_html(element: etree._Element) -> str:
    return html.tostring(element, encoding="unicode", method="html")


def _element_start_tag(element: etree._Element) -> str:
    if not isinstance(element.tag, str):
        return ""
    attrs = "".join(
        f' {key}="{escape(str(value), quote=True)}"'
        for key, value in element.attrib.items()
    )
    return f"<{element.tag}{attrs}>"


def _element_end_tag(element: etree._Element) -> str:
    if not isinstance(element.tag, str):
        return ""
    return f"</{element.tag}>"


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


def _section_title(
    heading: etree._Element, section_children: list[etree._Element]
) -> str:
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


def _has_class(element: etree._Element, class_name: str) -> bool:
    return class_name in set(str(element.get("class") or "").split())


def _first_clean_text(element: etree._Element) -> str:
    for text in element.xpath(".//text()[normalize-space()]"):
        cleaned = _clean_text(text)
        if cleaned:
            return cleaned
    return ""


def _xforms_leading_correction_section(
    section_children: list[etree._Element],
) -> tuple[str, list[etree._Element]] | None:
    for child in section_children:
        title = _first_clean_text(child)
        if not title:
            continue
        if title.startswith("정정신고"):
            return title, section_children
        return None
    return None


def _xforms_title_sections(
    document: html.HtmlElement,
) -> list[tuple[str, list[etree._Element]]]:
    title_nodes = document.xpath(
        '//*[contains(concat(" ", normalize-space(@class), " "), " xforms_title ")]'
    )
    sections: list[tuple[str, list[etree._Element]]] = []
    correction_parent_ids: set[int] = set()
    for title_node in title_nodes:
        title = _clean_text(title_node.text_content())
        if not title:
            continue
        parent = title_node.getparent()
        if parent is None:
            sections.append((title, [title_node]))
            continue
        siblings = list(parent)
        start = siblings.index(title_node)
        parent_id = id(parent)
        if start > 0 and parent_id not in correction_parent_ids:
            correction_section = _xforms_leading_correction_section(siblings[:start])
            if correction_section is not None:
                sections.append(correction_section)
            correction_parent_ids.add(parent_id)
        end = len(siblings)
        for position in range(start + 1, len(siblings)):
            if _has_class(siblings[position], "xforms_title"):
                end = position
                break
        sections.append((title, siblings[start:end]))
    return sections


def _xforms_section_markup(section_children: list[etree._Element]) -> str:
    section_markup = "".join(_element_html(child) for child in section_children)
    if not section_children:
        return section_markup

    ancestors: list[etree._Element] = []
    for ancestor in section_children[0].iterancestors():
        ancestors.append(ancestor)
        if _has_class(ancestor, "xforms"):
            wrappers = list(reversed(ancestors))
            return (
                "".join(_element_start_tag(wrapper) for wrapper in wrappers)
                + section_markup
                + "".join(_element_end_tag(wrapper) for wrapper in reversed(wrappers))
            )
    return section_markup


def _split_xforms_sections(document: html.HtmlElement) -> list[HtmlSection]:
    sections: list[HtmlSection] = []
    for order, (title, section_children) in enumerate(
        _xforms_title_sections(document), start=1
    ):
        section_markup = _xforms_section_markup(section_children)
        toc_id = f"toc_{order}"
        sections.append(
            HtmlSection(
                toc_id=toc_id,
                index=order,
                title=title,
                html=_wrap_section_html(document, section_markup),
            )
        )
    return sections


def _inspect_xforms_sections(document: html.HtmlElement) -> list[HtmlSectionSummary]:
    return [
        HtmlSectionSummary(toc_id=f"toc_{order}", index=order, title=title)
        for order, (title, _section_children) in enumerate(
            _xforms_title_sections(document), start=1
        )
    ]


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
    if not heading_positions:
        return _split_xforms_sections(document)

    sections: list[HtmlSection] = []
    for order, (start, heading) in enumerate(heading_positions, start=1):
        end = (
            heading_positions[order][0]
            if order < len(heading_positions)
            else len(children)
        )
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


def inspect_content_html_sections(html_markup: str | bytes) -> list[HtmlSectionSummary]:
    """Read only top-level TOC metadata from a KIND content HTML document."""
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
    if not heading_positions:
        return _inspect_xforms_sections(document)

    sections: list[HtmlSectionSummary] = []
    for order, (start, heading) in enumerate(heading_positions, start=1):
        end = (
            heading_positions[order][0]
            if order < len(heading_positions)
            else len(children)
        )
        toc_id = str(heading.get("id") or "").strip() or f"toc_{order}"
        sections.append(
            HtmlSectionSummary(
                toc_id=toc_id,
                index=_toc_index(toc_id, order),
                title=_section_title(heading, children[start:end]),
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


def _parse_page(value: Any) -> int:
    if value in (None, ""):
        return 1
    parsed = int(value)
    if parsed < 1:
        msg = "page must be >= 1"
        raise ValueError(msg)
    return parsed


def _parse_page_size(value: Any) -> int:
    if value in (None, ""):
        return DEFAULT_HTML_SECTION_PAGE_SIZE
    parsed = int(value)
    if parsed < 1:
        msg = "page_size must be >= 1"
        raise ValueError(msg)
    return parsed


def parse_html_section_worker_count(value: Any) -> int:
    if value in (None, ""):
        return DEFAULT_HTML_SECTION_WORKERS
    parsed = int(value)
    if parsed < 1:
        msg = "workers must be >= 1"
        raise ValueError(msg)
    return min(parsed, DEFAULT_HTML_SECTION_WORKERS)


def _cancel_requested(cancel_check: Callable[[], bool] | None) -> bool:
    return bool(cancel_check is not None and cancel_check())


def _map_html_files(
    html_files: list[Path],
    workers: int,
    callback: Callable[[Path], T],
    cancel_check: Callable[[], bool] | None = None,
) -> Iterator[T]:
    if workers <= 1 or len(html_files) <= 1:
        for source_file in html_files:
            if _cancel_requested(cancel_check):
                return
            yield callback(source_file)
        return
    with ThreadPoolExecutor(max_workers=workers) as executor:
        source_iter = iter(html_files)
        pending: deque[Future[T]] = deque()

        def submit_next() -> bool:
            if _cancel_requested(cancel_check):
                return False
            try:
                source_file = next(source_iter)
            except StopIteration:
                return False
            pending.append(executor.submit(callback, source_file))
            return True

        for _ in range(min(workers, len(html_files))):
            if not submit_next():
                break

        while pending:
            future = pending.popleft()
            yield future.result()
            if _cancel_requested(cancel_check):
                for pending_future in pending:
                    pending_future.cancel()
                return
            submit_next()


def _iter_html_files(input_directory: Path):
    for child in sorted(input_directory.iterdir(), key=lambda path: path.name):
        if child.is_dir():
            if child.name.startswith("."):
                continue
            yield from _iter_html_files(child)
        elif child.is_file() and child.suffix.lower() == ".html":
            yield child


def _collect_html_file_page(
    input_directory: Path, page: int, page_size: int
) -> tuple[list[Path], bool]:
    start = (page - 1) * page_size
    stop = start + page_size + 1
    selected: list[Path] = []
    for index, source_file in enumerate(_iter_html_files(input_directory)):
        if index < start:
            continue
        if index >= stop:
            break
        selected.append(source_file)
    return selected[:page_size], len(selected) > page_size


def _source_document(input_directory: Path, source_file: Path) -> dict[str, str]:
    return {
        "source_file": str(source_file),
        "source_name": source_file.name,
        "source_relative_path": _relative_source_path(input_directory, source_file),
    }


def _source_document_with_sections(
    input_directory: Path, source_file: Path
) -> dict[str, Any]:
    sections = inspect_content_html_sections(source_file.read_bytes())
    return {
        **_source_document(input_directory, source_file),
        "section_count": len(sections),
        "sections": [
            {"toc_id": section.toc_id, "index": section.index, "title": section.title}
            for section in sections
        ],
    }


def _source_document_with_section_count(
    input_directory: Path, source_file: Path
) -> dict[str, str | int]:
    document = _source_document_with_sections(input_directory, source_file)
    return {
        "source_file": str(document["source_file"]),
        "source_name": str(document["source_name"]),
        "source_relative_path": str(document["source_relative_path"]),
        "section_count": int(document["section_count"]),
    }


def _section_signature(sections: list[dict[str, Any]]) -> str:
    return " ".join(
        " ".join(
            part
            for part in [
                str(section.get("toc_id") or ""),
                str(section.get("title") or ""),
            ]
            if part
        ).strip()
        for section in sections
    ).strip()


def _section_patterns(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for document in documents:
        sections = list(document.get("sections") or [])
        if not sections:
            continue
        signature = _section_signature(sections)
        if not signature:
            continue
        item = counts.setdefault(
            signature,
            {
                "signature": signature,
                "count": 0,
                "section_count": len(sections),
                "sections": sections,
                "sample_documents": [],
            },
        )
        item["count"] += 1
        if len(item["sample_documents"]) < 3:
            item["sample_documents"].append(
                {
                    "source_file": str(document.get("source_file") or ""),
                    "source_name": str(document.get("source_name") or ""),
                    "source_relative_path": str(
                        document.get("source_relative_path") or ""
                    ),
                }
            )
    return sorted(
        counts.values(),
        key=lambda item: (
            -int(item["count"]),
            int(item["section_count"]),
            str(item["signature"]),
        ),
    )


def _section_save_rules(value: Any) -> dict[str, set[str]]:
    if not isinstance(value, dict):
        return {}
    rules: dict[str, set[str]] = {}
    for signature, toc_ids in value.items():
        signature_text = str(signature or "").strip()
        if not signature_text or not isinstance(toc_ids, list):
            continue
        rules[signature_text] = {
            str(toc_id).strip() for toc_id in toc_ids if str(toc_id).strip()
        }
    return rules


def _section_dicts_from_split_sections(
    sections: list[HtmlSection],
) -> list[dict[str, Any]]:
    return [
        {"toc_id": section.toc_id, "index": section.index, "title": section.title}
        for section in sections
    ]


def _resolve_html_source_file(
    input_directory_raw: str, source_name_raw: str
) -> tuple[Path, Path]:
    input_directory = Path(input_directory_raw).expanduser().resolve()
    source_name = source_name_raw.strip()
    source_file = (input_directory / source_name).resolve()
    try:
        source_file.relative_to(input_directory)
    except ValueError:
        msg = "HTML source file not found"
        raise FileNotFoundError(msg)
    if source_file.suffix.lower() != ".html" or not source_file.is_file():
        msg = "HTML source file not found"
        raise FileNotFoundError(msg)
    return input_directory, source_file


def list_disclosure_html_section_sources_payload(
    body: dict[str, Any],
) -> dict[str, Any]:
    input_directory_raw = str(body.get("input_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()
    if not input_directory.is_dir():
        msg = f"input_directory does not exist: {input_directory}"
        raise ValueError(msg)

    page = _parse_page(body.get("page"))
    page_size = _parse_page_size(body.get("page_size"))
    html_files, has_next_page = _collect_html_file_page(
        input_directory, page, page_size
    )
    documents_with_sections = [
        _source_document_with_sections(input_directory, source_file)
        for source_file in html_files
    ]
    documents = [
        {
            "source_file": str(document["source_file"]),
            "source_name": str(document["source_name"]),
            "source_relative_path": str(document["source_relative_path"]),
            "section_count": int(document["section_count"]),
        }
        for document in documents_with_sections
    ]
    return {
        "format": "finiq_disclosure_html_section_source_list_v1",
        "input_directory": str(input_directory),
        "summary": {
            "page": page,
            "page_size": page_size,
            "returned_files": len(html_files),
            "has_next_page": has_next_page,
        },
        "documents": documents,
        "section_patterns": _section_patterns(documents_with_sections),
    }


def summarize_disclosure_html_section_kinds_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    input_directory_raw = str(body.get("input_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()
    if not input_directory.is_dir():
        msg = f"input_directory does not exist: {input_directory}"
        raise ValueError(msg)

    html_files = _collect_html_files(input_directory, _parse_limit(body.get("limit")))
    if progress_callback is not None:
        progress_callback(f"목차 조합 확인 대상 HTML {len(html_files)}건을 찾았습니다.")
    documents: list[dict[str, Any]] = []
    files_without_sections = 0
    failed_files = 0
    for index, source_file in enumerate(html_files, start=1):
        if cancel_check is not None and cancel_check():
            return {"cancelled": True}
        try:
            document = _source_document_with_sections(input_directory, source_file)
        except Exception:
            failed_files += 1
            continue
        if int(document["section_count"]) <= 0:
            files_without_sections += 1
            continue
        documents.append(document)
        if progress_callback is not None and (
            index == 1 or index == len(html_files) or index % 100 == 0
        ):
            progress_callback(f"목차 조합 확인 중: {index}/{len(html_files)}건 처리.")

    items = _section_patterns(documents)
    return {
        "format": "finiq_disclosure_html_section_kind_summary_v1",
        "input_directory": str(input_directory),
        "summary": {
            "found_files": len(html_files),
            "documents_with_sections": len(documents),
            "files_without_sections": files_without_sections,
            "failed_files": failed_files,
            "unique_kinds": len(items),
        },
        "items": items,
    }


def split_disclosure_html_section_source_payload(
    body: dict[str, Any],
) -> dict[str, Any]:
    input_directory, source_file = _resolve_html_source_file(
        str(body.get("input_directory") or "").strip(),
        str(body.get("source_name") or ""),
    )
    sections = split_content_html_sections(source_file.read_bytes())
    return {
        "format": "finiq_disclosure_html_section_source_split_v1",
        "input_directory": str(input_directory),
        "document": _source_document(input_directory, source_file),
        "section_count": len(sections),
        "sections": [
            {
                "toc_id": section.toc_id,
                "index": section.index,
                "title": section.title,
                "html": section.html,
            }
            for section in sections
        ],
    }


def inspect_disclosure_html_sections_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    input_directory_raw = str(body.get("input_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()
    if not input_directory.is_dir():
        msg = f"input_directory does not exist: {input_directory}"
        raise ValueError(msg)

    html_files = _collect_html_files(input_directory, _parse_limit(body.get("limit")))
    workers = parse_html_section_worker_count(body.get("workers"))
    files_without_sections = 0
    failed_files = 0
    report_limit = _parse_report_limit(body.get("report_limit"))

    def emit(message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)

    def inspect_one(source_file: Path) -> dict[str, Any]:
        try:
            sections = inspect_content_html_sections(source_file.read_bytes())
        except Exception as exc:
            return {
                "status": "read_failed",
                "problem": {
                    "kind": "read_failed",
                    "source_file": str(source_file),
                    "error": str(exc),
                },
            }
        if not sections:
            return {
                "status": "no_sections",
                "problem": {
                    "kind": "no_sections",
                    "source_file": str(source_file),
                    "error": "",
                },
            }
        return {
            "status": "ok",
            "document": {
                "source_file": str(source_file),
                "source_name": source_file.name,
                "source_relative_path": _relative_source_path(
                    input_directory, source_file
                ),
                "section_count": len(sections),
                "sections": [
                    {
                        "toc_id": section.toc_id,
                        "index": section.index,
                        "title": section.title,
                    }
                    for section in sections
                ],
            },
        }

    emit(
        f"목차 확인 대상 HTML {len(html_files)}건을 찾았습니다. 병렬 처리 {workers}개를 사용합니다."
    )
    results = _map_html_files(html_files, workers, inspect_one, cancel_check)
    documents: list[dict[str, Any]] = []
    problem_files: list[dict[str, str]] = []
    for index, result in enumerate(results, start=1):
        if _cancel_requested(cancel_check):
            return {"cancelled": True}
        if result["status"] == "ok":
            documents.append(result["document"])
        elif result["status"] == "read_failed":
            failed_files += 1
            if len(problem_files) < report_limit:
                problem_files.append(result["problem"])
        else:
            files_without_sections += 1
            if len(problem_files) < report_limit:
                problem_files.append(result["problem"])
        if index == 1 or index == len(html_files) or index % 100 == 0:
            emit(f"목차 확인 중간 확인: {index}/{len(html_files)}건 처리.")

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
            if path.is_file()
            and path.suffix.lower() == ".html"
            and not any(
                part.startswith(".")
                for part in path.relative_to(input_directory).parts[:-1]
            )
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


def _selected_section_output(
    source_file: Path,
    section_save_rules: dict[str, set[str]],
) -> dict[str, Any]:
    try:
        sections = split_content_html_sections(source_file.read_bytes())
    except Exception as exc:
        return {
            "status": "read_failed",
            "source_file": str(source_file),
            "error": str(exc),
        }
    if not sections:
        return {
            "status": "no_sections",
            "source_file": str(source_file),
            "error": "no sections found",
        }
    signature = _section_signature(_section_dicts_from_split_sections(sections))
    allowed_toc_ids = section_save_rules.get(signature)
    selected_sections = [
        section
        for section in sections
        if allowed_toc_ids is None or section.toc_id in allowed_toc_ids
    ]
    return {
        "status": "ok",
        "source_file": str(source_file),
        "content": "\n".join(section.html for section in selected_sections),
        "selected_sections": len(selected_sections),
    }


def inspect_disclosure_html_section_output_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Rebuild expected section output in memory and compare every saved HTML."""
    input_directory_raw = str(body.get("input_directory") or "").strip()
    output_directory_raw = str(body.get("output_directory") or "").strip()
    if not input_directory_raw:
        raise ValueError("input_directory is required")
    if not output_directory_raw:
        raise ValueError("output_directory is required")
    input_directory = Path(input_directory_raw).expanduser().resolve()
    output_directory = Path(output_directory_raw).expanduser().resolve()
    if not input_directory.is_dir():
        raise ValueError(f"input_directory does not exist: {input_directory}")

    html_files = _collect_html_files(input_directory, _parse_limit(body.get("limit")))
    workers = parse_html_section_worker_count(body.get("workers"))
    section_save_rules = _section_save_rules(body.get("section_save_rules"))
    results = _map_html_files(
        html_files,
        workers,
        lambda source_file: _selected_section_output(source_file, section_save_rules),
        cancel_check,
    )
    if _cancel_requested(cancel_check):
        return {"cancelled": True}

    expected: dict[str, str] = {}
    problems: list[dict[str, str]] = []
    for source_file, result in zip(html_files, results):
        if result["status"] != "ok":
            problems.append(
                {
                    "source_file": str(source_file),
                    "error": str(result.get("error") or result["status"]),
                }
            )
            continue
        if int(result.get("selected_sections") or 0) > 0:
            expected[_relative_source_path(input_directory, source_file)] = str(
                result["content"]
            )

    actual_paths = (
        {
            path.relative_to(output_directory).as_posix(): path
            for path in output_directory.rglob("*.html")
            if path.is_file()
            and not any(
                part.startswith(".")
                for part in path.relative_to(output_directory).parts[:-1]
            )
        }
        if output_directory.is_dir()
        else {}
    )
    missing_files = sorted(set(expected) - set(actual_paths))
    unexpected_files = sorted(set(actual_paths) - set(expected))
    mismatched_files = sorted(
        relative_path
        for relative_path in set(expected) & set(actual_paths)
        if actual_paths[relative_path].read_text(encoding="utf-8")
        != expected[relative_path]
    )
    integrity_ok = not (
        problems or missing_files or unexpected_files or mismatched_files
    )
    if progress_callback is not None:
        progress_callback(
            "목차 분리 결과 검사 완료: "
            f"예상 {len(expected)}건, 누락 {len(missing_files)}건, "
            f"내용 불일치 {len(mismatched_files)}건"
        )
    return {
        "format": "finiq_disclosure_html_section_output_inspection_v1",
        "input_directory": str(input_directory),
        "output_directory": str(output_directory),
        "summary": {
            "found_files": len(html_files),
            "expected_files": len(expected),
            "actual_files": len(actual_paths),
            "problem_files": len(problems),
            "missing_files": len(missing_files),
            "unexpected_files": len(unexpected_files),
            "mismatched_files": len(mismatched_files),
            "integrity_ok": integrity_ok,
        },
        "problem_files": problems,
        "missing_files": missing_files,
        "unexpected_files": unexpected_files,
        "mismatched_files": mismatched_files,
    }


def save_disclosure_html_sections_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
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
    workers = parse_html_section_worker_count(body.get("workers"))
    section_save_rules = _section_save_rules(body.get("section_save_rules"))
    output_directory.mkdir(parents=True, exist_ok=True)
    saved_files: list[str] = []
    expected_files: list[str] = []
    skipped_files: list[dict[str, str]] = []
    progress_log: list[str] = []

    def emit(message: str) -> None:
        progress_log.append(message)
        if progress_callback is not None:
            progress_callback(message)

    def save_one(source_file: Path) -> dict[str, Any]:
        selected = _selected_section_output(source_file, section_save_rules)
        if selected["status"] == "read_failed":
            return {
                "status": "read_failed",
                "skipped": {
                    "source_file": str(source_file),
                    "error": str(selected["error"]),
                },
                "saved": [],
            }
        if selected["status"] == "no_sections":
            return {
                "status": "no_sections",
                "skipped": {
                    "source_file": str(source_file),
                    "error": "no sections found",
                },
                "saved": [],
            }
        if int(selected.get("selected_sections") or 0) == 0:
            return {"status": "ok", "saved": [], "expected": []}
        source_relative_path = source_file.relative_to(input_directory)
        output_path = output_directory / source_relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(str(selected["content"]), encoding="utf-8")
        return {
            "status": "ok",
            "saved": [str(output_path)],
            "expected": [str(output_path)],
        }

    emit(
        f"목차 분리 대상 HTML {len(html_files)}건을 찾았습니다. 병렬 처리 {workers}개를 사용합니다."
    )
    results = _map_html_files(html_files, workers, save_one, cancel_check)
    for index, result in enumerate(results, start=1):
        if _cancel_requested(cancel_check):
            return {"cancelled": True}
        if result["status"] == "ok":
            saved_files.extend(result["saved"])
            expected_files.extend(result["expected"])
        else:
            skipped_files.append(result["skipped"])
            source_name = Path(result["skipped"]["source_file"]).name
            if result["status"] == "read_failed":
                emit(f"읽기 실패 {index}/{len(html_files)}: {source_name}")
            else:
                emit(f"목차 없음 {index}/{len(html_files)}: {source_name}")
        if index == 1 or index == len(html_files) or index % 25 == 0:
            emit(f"목차 저장 중간 확인: {index}/{len(html_files)}건 처리.")

    missing_files = [path for path in expected_files if not Path(path).is_file()]
    emit(f"목차 HTML 저장 완료: {len(saved_files)}건")
    emit(
        f"무결성 검사 완료: 저장 대상 {len(expected_files)}건, 저장 완료 {len(saved_files)}건, 누락 {len(missing_files)}건"
    )
    return {
        "format": "finiq_disclosure_html_section_save_v2",
        "input_directory": str(input_directory),
        "output_directory": str(output_directory),
        "summary": {
            "found_files": len(html_files),
            "saved_files": len(saved_files),
            "skipped_files": len(skipped_files),
            "expected_files": len(expected_files),
            "integrity_ok": len(saved_files) == len(expected_files)
            and not missing_files,
            "missing_files": len(missing_files),
        },
        "saved_files": saved_files,
        "expected_files": expected_files,
        "missing_files": missing_files,
        "skipped_files": skipped_files,
        "progress_log": progress_log[-200:],
    }
