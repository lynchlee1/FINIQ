"""KIND internal HTML section splitting helpers."""

from __future__ import annotations

import os
import re
import tempfile
import time
from collections import deque
from copy import deepcopy
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, TypeVar

from lxml import etree, html

from finiq.concurrency import resolve_worker_count
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
    validate_workspace_mode,
)
from finiq.market_desk.web.features.disclosures.html_common import (
    _internal_html_source_unavailable_placeholder_file,
)
from finiq.market_desk.web.html_parsers.common import decode_html_markup

ProgressCallback = Callable[[str], None]
_SOURCE_TOC_ID_RE = re.compile(r"^toc_(\d+)$", flags=re.IGNORECASE)
_HEADING_TAGS = {f"h{level}" for level in range(1, 7)}
# Post-split classification only; structural boundary detection must not use text.
_CORRECTION_TITLE_TOKEN = "정정"
_SECTIONS_STAGE_NAME = "06-sections"
DEFAULT_HTML_SECTION_PAGE_SIZE = 20
DEFAULT_HTML_SECTION_PROBLEM_REPORT_LIMIT = 50
T = TypeVar("T")


class _NoHtmlSectionsError(ValueError):
    pass


class _SectionSaveCancelled(Exception):
    pass


@dataclass(frozen=True)
class HtmlSection:
    toc_id: str
    index: int
    title: str
    html: str
    kind: str = "section"
    level: int = 1
    parent_toc_id: str | None = None
    is_toc: bool = True


@dataclass(frozen=True)
class HtmlSectionSummary:
    toc_id: str
    index: int
    title: str
    kind: str = "section"
    level: int = 1
    parent_toc_id: str | None = None
    is_toc: bool = True


@dataclass(frozen=True)
class _HtmlTocBoundary:
    position: int
    element: etree._Element
    toc_id: str
    kind: str
    level: int
    is_toc: bool


@dataclass(frozen=True)
class _HtmlSectionPlan:
    start: int
    end: int
    title: str
    toc_id: str
    kind: str
    level: int
    parent_toc_id: str | None
    is_toc: bool


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _element_children(element: etree._Element) -> list[etree._Element]:
    return [child for child in element if isinstance(child.tag, str)]


def _parse_internal_html_document(html_markup: str | bytes) -> html.HtmlElement:
    decoded_markup = decode_html_markup(html_markup)
    parser = html.HTMLParser(encoding="utf-8", recover=True, huge_tree=True)
    return html.document_fromstring(decoded_markup, parser=parser)


def _boundary_title(
    heading: etree._Element,
    section_children: list[etree._Element],
    *,
    kind: str,
    level: int,
) -> str:
    title = _clean_text(heading.text_content())
    if not title and len(section_children) > 1:
        first_content = section_children[1]
        first_role = _toc_element_role(first_content)
        if (
            isinstance(first_content.tag, str)
            and first_content.tag.lower() == "p"
            and first_role == (kind, level)
        ):
            title = _clean_text(first_content.text_content())
    if not title:
        raise ValueError("TOC boundary title is required")
    return title


def _first_text_fragment(elements: Iterable[etree._Element]) -> str:
    for element in elements:
        for fragment in element.itertext():
            title = _clean_text(fragment)
            if title:
                return title
    return ""


def _toc_element_role(element: etree._Element) -> tuple[str, int] | None:
    class_names = [
        class_name.upper()
        for class_name in str(element.get("class") or "").split()
    ]
    roles: list[tuple[str, int]] = []
    if "COVER-TITLE" in class_names:
        roles.append(("cover", 0))
    if "PART" in class_names:
        roles.append(("part", 0))
    roles.extend(
        ("section", int(match.group(1)))
        for class_name in class_names
        if (match := re.fullmatch(r"SECTION-(\d+)", class_name)) is not None
    )
    if len(roles) > 1:
        raise ValueError("one TOC hierarchy class is required")
    return roles[0] if roles else None


def _is_toc_heading(element: etree._Element) -> bool:
    return (
        isinstance(element.tag, str)
        and element.tag.lower() in _HEADING_TAGS
        and _toc_element_role(element) is not None
    )


def _is_section_paragraph(element: etree._Element) -> bool:
    if not isinstance(element.tag, str) or element.tag.lower() != "p":
        return False
    role = _toc_element_role(element)
    return role is not None and role[0] == "section"


def _has_class(element: etree._Element, class_name: str) -> bool:
    return class_name in str(element.get("class") or "").split()


def _section_container_and_boundaries(
    document: html.HtmlElement,
) -> tuple[etree._Element, list[_HtmlTocBoundary], str]:
    body_nodes = document.xpath("//body")
    if not body_nodes:
        raise ValueError("HTML body is required")
    body = body_nodes[0]
    body_children = _element_children(body)
    xforms_wrappers = [child for child in body_children if _has_class(child, "xforms")]

    source_toc_elements = [
        (position, child, _SOURCE_TOC_ID_RE.fullmatch(str(child.get("id") or "")))
        for position, child in enumerate(body_children)
        if _SOURCE_TOC_ID_RE.fullmatch(str(child.get("id") or "")) is not None
    ]
    if source_toc_elements:
        if xforms_wrappers:
            raise ValueError("one unambiguous TOC structure is required")
        source_numbers: list[int] = []
        boundaries: list[_HtmlTocBoundary] = []
        for position, element, source_match in source_toc_elements:
            if not _is_toc_heading(element) or source_match is None:
                raise ValueError("supported source TOC heading is required")
            kind, level = _toc_element_role(element) or ("", 0)
            source_numbers.append(int(source_match.group(1)))
            boundaries.append(
                _HtmlTocBoundary(
                    position=position,
                    element=element,
                    toc_id=str(element.get("id")),
                    kind=kind,
                    level=level,
                    is_toc=True,
                )
            )
        if source_numbers != sorted(set(source_numbers)):
            raise ValueError("source TOC ids must be unique and ascending")
        unlinked_headings = [
            child
            for child in body_children
            if _is_toc_heading(child)
            and _SOURCE_TOC_ID_RE.fullmatch(str(child.get("id") or "")) is None
        ]
        if unlinked_headings:
            raise ValueError("every TOC heading must have a source TOC id")
        return body, boundaries, "source_toc"

    heading_elements = [
        (position, child)
        for position, child in enumerate(body_children)
        if _is_toc_heading(child)
    ]
    if heading_elements:
        if xforms_wrappers:
            raise ValueError("one unambiguous TOC structure is required")
        boundaries = []
        for index, (position, element) in enumerate(heading_elements, start=1):
            kind, level = _toc_element_role(element) or ("", 0)
            boundaries.append(
                _HtmlTocBoundary(
                    position=position,
                    element=element,
                    toc_id=f"toc_{index}",
                    kind=kind,
                    level=level,
                    is_toc=True,
                )
            )
        return body, boundaries, "heading"

    paragraph_elements = [
        (position, child)
        for position, child in enumerate(body_children)
        if _is_section_paragraph(child)
    ]
    if paragraph_elements:
        if xforms_wrappers:
            raise ValueError("one unambiguous TOC structure is required")
        return body, [
            _HtmlTocBoundary(
                position=position,
                element=element,
                toc_id=f"toc_{index}",
                kind="section",
                level=(_toc_element_role(element) or ("section", 1))[1],
                is_toc=True,
            )
            for index, (position, element) in enumerate(paragraph_elements, start=1)
        ], "paragraph"

    if not xforms_wrappers:
        raise _NoHtmlSectionsError("supported TOC structure is required")
    if len(xforms_wrappers) != 1:
        raise ValueError("supported TOC structure is required")
    wrapper_children = _element_children(xforms_wrappers[0])
    if len(wrapper_children) != 1:
        raise ValueError("XForms content wrapper is required")
    container = wrapper_children[0]
    container_children = _element_children(container)
    xforms_elements = [
        (position, child)
        for position, child in enumerate(container_children)
        if child.tag.lower() == "div" and _has_class(child, "xforms_title")
    ]
    if len(xforms_elements) != 1:
        raise ValueError("one direct XForms document title is required")
    position, element = xforms_elements[0]
    return container, [
        _HtmlTocBoundary(
            position=position,
            element=element,
            toc_id="document",
            kind="document",
            level=0,
            is_toc=False,
        )
    ], "xforms"


def _section_plans(
    document: html.HtmlElement,
) -> tuple[etree._Element, list[_HtmlSectionPlan]]:
    container, boundaries, structure = _section_container_and_boundaries(document)
    children = _element_children(container)
    plans: list[_HtmlSectionPlan] = []
    first_boundary = boundaries[0].position
    preamble_title = _clean_text(container.text) or _first_text_fragment(
        children[:first_boundary]
    )
    if preamble_title:
        plans.append(
            _HtmlSectionPlan(
                start=0,
                end=first_boundary,
                title=preamble_title,
                toc_id="preamble",
                kind="preamble",
                level=0,
                parent_toc_id=None,
                is_toc=False,
            )
        )

    hierarchy: dict[int, str] = {}
    for order, boundary in enumerate(boundaries):
        start = boundary.position
        end = (
            boundaries[order + 1].position
            if order + 1 < len(boundaries)
            else len(children)
        )
        section_children = children[start:end]
        if structure in {"heading", "source_toc"}:
            title = _boundary_title(
                boundary.element,
                section_children,
                kind=boundary.kind,
                level=boundary.level,
            )
        else:
            title = _clean_text(boundary.element.text_content())
            if not title:
                raise ValueError("TOC boundary title is required")

        if boundary.kind in {"cover", "document"}:
            hierarchy.clear()
            parent_toc_id = None
        else:
            parent_toc_id = next(
                (
                    hierarchy[level]
                    for level in sorted(hierarchy, reverse=True)
                    if level < boundary.level
                ),
                None,
            )
            hierarchy = {
                level: toc_id
                for level, toc_id in hierarchy.items()
                if level < boundary.level
            }
            hierarchy[boundary.level] = boundary.toc_id
        plans.append(
            _HtmlSectionPlan(
                start=start,
                end=end,
                title=title,
                toc_id=boundary.toc_id,
                kind=boundary.kind,
                level=boundary.level,
                parent_toc_id=parent_toc_id,
                is_toc=boundary.is_toc,
            )
        )
    return container, plans


def _render_section_plan(
    document: html.HtmlElement,
    container: etree._Element,
    plan: _HtmlSectionPlan,
) -> str:
    cloned_document = deepcopy(document)
    container_path = document.getroottree().getpath(container)
    cloned_containers = cloned_document.getroottree().xpath(container_path)
    if len(cloned_containers) != 1:
        raise ValueError("section container clone is required")
    cloned_container = cloned_containers[0]
    if plan.kind != "preamble":
        cloned_container.text = None
    cloned_children = _element_children(cloned_container)
    for index in range(len(cloned_children) - 1, -1, -1):
        if index < plan.start or index >= plan.end:
            cloned_container.remove(cloned_children[index])
    return "<!DOCTYPE html>\n" + html.tostring(
        cloned_document, encoding="unicode", method="html"
    )


def _is_correction_section_title(title: str) -> bool:
    return _CORRECTION_TITLE_TOKEN in re.sub(r"\s+", "", title)


def _leading_correction_plan(
    plans: list[_HtmlSectionPlan],
) -> _HtmlSectionPlan | None:
    if len(plans) > 1 and _is_correction_section_title(plans[0].title):
        return plans[0]
    return None


def split_internal_html_sections(html_markup: str | bytes) -> list[HtmlSection]:
    """Split every structural TOC section before any correction filtering."""
    document = _parse_internal_html_document(html_markup)
    container, plans = _section_plans(document)
    return [
        HtmlSection(
            toc_id=plan.toc_id,
            index=index,
            title=plan.title,
            html=_render_section_plan(document, container, plan),
            kind=plan.kind,
            level=plan.level,
            parent_toc_id=plan.parent_toc_id,
            is_toc=plan.is_toc,
        )
        for index, plan in enumerate(plans, start=1)
    ]


def inspect_internal_html_sections(html_markup: str | bytes) -> list[HtmlSectionSummary]:
    """Read every structural TOC title without rendering section HTML."""
    document = _parse_internal_html_document(html_markup)
    _container, plans = _section_plans(document)
    return [
        HtmlSectionSummary(
            toc_id=plan.toc_id,
            index=index,
            title=plan.title,
            kind=plan.kind,
            level=plan.level,
            parent_toc_id=plan.parent_toc_id,
            is_toc=plan.is_toc,
        )
        for index, plan in enumerate(plans, start=1)
    ]


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


def _parse_problem_report_limit(value: Any) -> int:
    if value in (None, ""):
        return DEFAULT_HTML_SECTION_PROBLEM_REPORT_LIMIT
    parsed = int(value)
    if parsed < 1:
        raise ValueError("report_limit must be >= 1")
    return parsed


def _parse_section_progress_interval(value: Any, *, default: int) -> int:
    if value in (None, ""):
        return default
    parsed = int(value)
    if parsed < 1:
        raise ValueError("progress_interval must be >= 1")
    return parsed


def _inspection_error_message(exc: Exception) -> str:
    messages = {
        "HTML body is required": "HTML 문서에 <body> 요소가 없습니다.",
        "supported TOC structure is required": (
            "지원하는 목차 구조(SECTION, COVER, PART 또는 XForms)를 "
            "찾지 못했습니다."
        ),
        "one unambiguous TOC structure is required": (
            "서로 다른 목차 구조가 함께 있어 하나로 판단할 수 없습니다."
        ),
        "TOC boundary title is required": "목차 제목이 비어 있습니다.",
    }
    message = str(exc)
    return messages.get(message, message)


def parse_html_section_worker_count(value: Any) -> int:
    return resolve_worker_count(value, field_name="workers")


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


def _collect_html_file_page(
    input_directory: Path, page: int, page_size: int
) -> tuple[list[Path], bool]:
    start = (page - 1) * page_size
    stop = start + page_size + 1
    selected = _collect_html_files(input_directory, None)[start:stop]
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
    source_unavailable = _internal_html_source_unavailable_placeholder_file(source_file)
    if source_unavailable is not None:
        return {
            **_source_document(input_directory, source_file),
            "section_count": 0,
            "toc_count": 0,
            "sections": [],
            "source_unavailable": source_unavailable,
        }
    sections = inspect_internal_html_sections(source_file.read_bytes())
    return {
        **_source_document(input_directory, source_file),
        "section_count": len(sections),
        "toc_count": sum(section.is_toc for section in sections),
        "sections": [
            {
                "toc_id": section.toc_id,
                "index": section.index,
                "title": section.title,
                "kind": section.kind,
                "level": section.level,
                "parent_toc_id": section.parent_toc_id,
                "is_toc": section.is_toc,
            }
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
        "toc_count": int(document["toc_count"]),
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


def _count_section_pattern(
    counts: dict[str, dict[str, Any]], document: dict[str, Any]
) -> None:
    sections = list(document.get("sections") or [])
    if not sections:
        return
    signature = _section_signature(sections)
    if not signature:
        return
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


def _sorted_section_patterns(
    counts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        counts.values(),
        key=lambda item: (
            -int(item["count"]),
            int(item["section_count"]),
            str(item["signature"]),
        ),
    )


def _section_patterns(documents: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, dict[str, Any]] = {}
    for document in documents:
        _count_section_pattern(counts, document)
    return _sorted_section_patterns(counts)


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
            "toc_count": int(document["toc_count"]),
            "source_unavailable": document.get("source_unavailable"),
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
            "source_unavailable_files": sum(
                bool(document.get("source_unavailable"))
                for document in documents_with_sections
            ),
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

    workers = parse_html_section_worker_count(body.get("workers"))
    collect_started_at = time.monotonic()
    if progress_callback is not None:
        progress_callback(
            "입력 폴더에서 목차 조합 확인 대상 HTML을 찾습니다. "
            f"병렬 처리 {workers}개를 사용합니다."
        )
    html_files = _collect_html_files(input_directory, _parse_limit(body.get("limit")))
    if progress_callback is not None:
        progress_callback(
            f"목차 조합 확인 대상 HTML {len(html_files)}건을 찾았습니다. "
            f"파일 탐색 {time.monotonic() - collect_started_at:.1f}초 · "
            f"병렬 처리 {workers}개를 사용합니다."
        )
    results = _map_html_files(
        html_files,
        workers,
        lambda source_file: _source_document_with_sections(
            input_directory, source_file
        ),
        cancel_check,
    )
    document_count = 0

    def iter_documents():
        nonlocal document_count
        for index, document in enumerate(results, start=1):
            if cancel_check is not None and cancel_check():
                return
            document_count = index
            if progress_callback is not None and (
                index == 1 or index == len(html_files) or index % 100 == 0
            ):
                progress_callback(
                    f"목차 조합 확인 중: {index}/{len(html_files)}건 처리."
                )
            yield document

    items = _section_patterns(iter_documents())
    if cancel_check is not None and cancel_check():
        return {"cancelled": True}
    return {
        "format": "finiq_disclosure_html_section_kind_summary_v1",
        "input_directory": str(input_directory),
        "summary": {
            "found_files": len(html_files),
            "documents_with_sections": document_count,
            "files_without_sections": 0,
            "failed_files": 0,
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
    sections = split_internal_html_sections(source_file.read_bytes())
    return {
        "format": "finiq_disclosure_html_section_source_split_v1",
        "input_directory": str(input_directory),
        "document": _source_document(input_directory, source_file),
        "section_count": len(sections),
        "toc_count": sum(section.is_toc for section in sections),
        "sections": [
            {
                "toc_id": section.toc_id,
                "index": section.index,
                "title": section.title,
                "kind": section.kind,
                "level": section.level,
                "parent_toc_id": section.parent_toc_id,
                "is_toc": section.is_toc,
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

    collect_started_at = time.monotonic()
    if progress_callback is not None:
        progress_callback("입력 폴더에서 목차 확인 대상 HTML을 찾습니다.")
    html_files = _collect_html_files(input_directory, _parse_limit(body.get("limit")))
    workers = parse_html_section_worker_count(body.get("workers"))
    report_limit = _parse_problem_report_limit(body.get("report_limit"))
    progress_interval = _parse_section_progress_interval(
        body.get("progress_interval"), default=100
    )

    def emit(message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)

    def inspect_one(source_file: Path) -> dict[str, Any]:
        source_relative_path = _relative_source_path(input_directory, source_file)
        source_unavailable = _internal_html_source_unavailable_placeholder_file(
            source_file
        )
        if source_unavailable is not None:
            return {
                "status": "source_unavailable",
                "source_file": str(source_file),
                "source_relative_path": source_relative_path,
                "source_unavailable": source_unavailable,
            }
        try:
            sections = inspect_internal_html_sections(source_file.read_bytes())
        except _NoHtmlSectionsError:
            return {
                "status": "no_sections",
                "problem": {
                    "kind": "no_sections",
                    "source_file": str(source_file),
                    "source_relative_path": source_relative_path,
                    "error": "분리할 목차를 찾지 못했습니다.",
                },
            }
        except (OSError, UnicodeError, ValueError, etree.Error) as exc:
            return {
                "status": "read_failed",
                "problem": {
                    "kind": "read_failed",
                    "source_file": str(source_file),
                    "source_relative_path": source_relative_path,
                    "error": _inspection_error_message(exc),
                },
            }
        if not sections:
            return {
                "status": "no_sections",
                "problem": {
                    "kind": "no_sections",
                    "source_file": str(source_file),
                    "source_relative_path": source_relative_path,
                    "error": "분리할 목차를 찾지 못했습니다.",
                },
            }
        return {
            "status": "ok",
            "document": {
                "source_file": str(source_file),
                "source_name": source_file.name,
                "source_relative_path": source_relative_path,
                "section_count": len(sections),
                "toc_count": sum(section.is_toc for section in sections),
                "sections": [
                    {
                        "toc_id": section.toc_id,
                        "index": section.index,
                        "title": section.title,
                        "kind": section.kind,
                        "level": section.level,
                        "parent_toc_id": section.parent_toc_id,
                        "is_toc": section.is_toc,
                    }
                    for section in sections
                ],
            },
        }

    emit(
        f"목차 확인 대상 HTML {len(html_files)}건을 찾았습니다. "
        f"파일 탐색 {time.monotonic() - collect_started_at:.1f}초 · "
        f"병렬 처리 {workers}개를 사용합니다."
    )
    results = _map_html_files(html_files, workers, inspect_one, cancel_check)
    documents: list[dict[str, Any]] = []
    problem_files: list[dict[str, str]] = []
    failed_files = 0
    files_without_sections = 0
    source_unavailable_files = 0
    for index, result in enumerate(results, start=1):
        if _cancel_requested(cancel_check):
            return {"cancelled": True}
        if result["status"] == "ok":
            documents.append(result["document"])
        elif result["status"] == "source_unavailable":
            source_unavailable_files += 1
        else:
            if result["status"] == "no_sections":
                files_without_sections += 1
            else:
                failed_files += 1
            if len(problem_files) < report_limit:
                problem_files.append(result["problem"])
        if (
            index == 1
            or index == len(html_files)
            or index % progress_interval == 0
        ):
            emit(f"목차 확인 중간 확인: {index}/{len(html_files)}건 처리.")

    total_files = len(html_files)
    emit(
        "목차 확인 완료: "
        f"정상 {len(documents)}건, KIND 원본 없음 {source_unavailable_files}건, "
        f"목차 없음 {files_without_sections}건, 읽기 실패 {failed_files}건."
    )
    return {
        "format": "finiq_disclosure_html_section_inspect_v1",
        "input_directory": str(input_directory),
        "summary": {
            "found_files": total_files,
            "documents_with_sections": len(documents),
            "files_without_sections": files_without_sections,
            "failed_files": failed_files,
            "reported_problem_files": len(problem_files),
            "source_unavailable_files": source_unavailable_files,
        },
        "documents": documents,
        "problem_files": problem_files,
    }


def _collect_html_files(input_directory: Path, limit: int | None) -> list[Path]:
    resolved_root = input_directory.resolve()
    files: list[Path] = []
    invalid_paths: list[str] = []
    for path in input_directory.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".html":
            continue
        relative_path = path.relative_to(input_directory)
        if any(part.startswith(".") for part in relative_path.parts[:-1]):
            continue
        resolved_path = path.resolve()
        try:
            resolved_relative_path = resolved_path.relative_to(resolved_root)
        except ValueError:
            invalid_paths.append(relative_path.as_posix())
            continue
        if not (
            len(resolved_relative_path.parts) == 2
            and len(resolved_relative_path.parts[0]) == 4
            and resolved_relative_path.parts[0].isdigit()
        ):
            invalid_paths.append(relative_path.as_posix())
            continue
        files.append(resolved_path)
    if invalid_paths:
        invalid_paths.sort()
        raise ValueError(
            "section input HTML must be stored at "
            f"<YYYY>/<acpt_no>.html: {invalid_paths[0]}"
        )
    files.sort(key=lambda path: _relative_source_path(resolved_root, path))
    stems: set[str] = set()
    for path in files:
        if path.stem in stems:
            raise ValueError(f"duplicate HTML filename stem: {path.stem}")
        stems.add(path.stem)
    return files[:limit] if limit is not None else files


def _relative_source_path(input_directory: Path, source_file: Path) -> str:
    return source_file.relative_to(input_directory).as_posix()


def _collect_output_html_paths(output_directory: Path) -> dict[str, Path]:
    if not output_directory.is_dir():
        return {}
    paths: dict[str, Path] = {}
    for root_raw, directory_names, filenames in os.walk(
        output_directory,
        followlinks=False,
    ):
        root = Path(root_raw)
        for name in [*directory_names, *filenames]:
            path = root / name
            if path.is_symlink():
                raise ValueError(
                    f"section output must not contain symbolic links: {path}"
                )
        relative_root = root.relative_to(output_directory)
        if any(part.startswith(".") for part in relative_root.parts):
            directory_names[:] = []
            continue
        directory_names[:] = [
            name for name in directory_names if not name.startswith(".")
        ]
        for filename in filenames:
            path = root / filename
            if path.suffix.lower() != ".html" or not path.is_file():
                continue
            paths[path.relative_to(output_directory).as_posix()] = path
    return paths


def _section_output_path(
    output_directory: Path,
    relative_path: Path,
) -> Path:
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("section output path must stay inside output_directory")
    current = output_directory
    for part in relative_path.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(
                f"section output must not contain symbolic links: {current}"
            )
    return current


def _publish_staged_section_outputs(
    *,
    staging_directory: Path,
    output_directory: Path,
    staged_results: list[dict[str, Any]],
    expected_relative_paths: set[str],
    all_expected_relative_paths: set[str],
    cancel_check: Callable[[], bool] | None,
) -> None:
    unexpected = sorted(
        set(_collect_output_html_paths(output_directory))
        - all_expected_relative_paths
    )
    if unexpected:
        raise ValueError(
            "output_directory contains unexpected existing HTML: "
            f"{unexpected[0]}"
        )

    backup_directory = staging_directory / ".backups"
    entries: list[dict[str, Any]] = []
    try:
        output_directory.mkdir(parents=True, exist_ok=True)
        for result in staged_results:
            if _cancel_requested(cancel_check):
                raise _SectionSaveCancelled
            relative_path = Path(str(result["relative_path"]))
            output_path = _section_output_path(output_directory, relative_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            backup_path: Path | None = None
            if output_path.exists():
                backup_path = backup_directory / relative_path
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(output_path, backup_path)
            entry = {
                "output": output_path,
                "backup": backup_path,
                "published": False,
            }
            entries.append(entry)
            os.replace(Path(result["staged"]), output_path)
            entry["published"] = True

        if _cancel_requested(cancel_check):
            raise _SectionSaveCancelled
        actual_paths = _collect_output_html_paths(output_directory)
        missing = sorted(expected_relative_paths - set(actual_paths))
        unexpected = sorted(set(actual_paths) - all_expected_relative_paths)
        if missing or unexpected:
            problem = missing[0] if missing else unexpected[0]
            raise ValueError(
                f"section output integrity check failed: {problem}"
            )
    except Exception:
        for entry in reversed(entries):
            output_path = Path(entry["output"])
            backup_path = entry["backup"]
            if entry["published"] and output_path.exists():
                output_path.unlink()
            if isinstance(backup_path, Path) and backup_path.exists():
                output_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(backup_path, output_path)
        raise


def _resolve_sections_output_directory(
    body: dict[str, Any], output_directory: Path
) -> Path:
    stage = (
        output_directory
        if output_directory.name == _SECTIONS_STAGE_NAME
        else output_directory.parent
        if output_directory.parent.name == _SECTIONS_STAGE_NAME
        else None
    )
    if stage is None:
        return output_directory
    parent_mode = body.get("parent_mode")
    mode = parent_mode if parent_mode not in (None, "") else body.get("mode")
    if not str(mode or "").strip():
        raise ValueError(
            "06-sections HTML must be stored at <mode>/<YYYY>/<acpt_no>.html"
        )
    expected = (stage / validate_workspace_mode(mode)).resolve()
    if output_directory != expected:
        raise ValueError(
            f"output_directory must use the owner mode directory: {expected}"
        )
    return output_directory


def _reject_year_directly_under_sections_stage(output_path: Path) -> None:
    year_directory = output_path.parent
    if (
        len(year_directory.name) == 4
        and year_directory.name.isdigit()
        and year_directory.parent.name == _SECTIONS_STAGE_NAME
    ):
        raise ValueError(
            "06-sections HTML must be stored at <mode>/<YYYY>/<acpt_no>.html"
        )


def _parse_limit(value: Any) -> int | None:
    if value in (None, ""):
        return None
    parsed = int(value)
    if parsed < 1:
        msg = "limit must be >= 1"
        raise ValueError(msg)
    return parsed


def _render_without_section_plans(
    document: html.HtmlElement,
    container: etree._Element,
    excluded_plans: list[_HtmlSectionPlan],
) -> str:
    excluded_indexes = {
        index
        for plan in excluded_plans
        for index in range(plan.start, plan.end)
    }
    cloned_document = deepcopy(document)
    container_path = document.getroottree().getpath(container)
    cloned_containers = cloned_document.getroottree().xpath(container_path)
    if len(cloned_containers) != 1:
        raise ValueError("section container clone is required")
    cloned_container = cloned_containers[0]
    if any(plan.kind == "preamble" for plan in excluded_plans):
        cloned_container.text = None
    cloned_children = _element_children(cloned_container)
    for index in range(len(cloned_children) - 1, -1, -1):
        if index in excluded_indexes:
            cloned_container.remove(cloned_children[index])
    return "<!DOCTYPE html>\n" + html.tostring(
        cloned_document, encoding="unicode", method="html"
    )


def _automatic_section_output(source_file: Path) -> dict[str, Any]:
    source_unavailable = _internal_html_source_unavailable_placeholder_file(source_file)
    if source_unavailable is not None:
        return {
            "status": "ok",
            "source_file": str(source_file),
            "content": source_file.read_text(encoding="utf-8"),
            "selected_sections": 1,
            "removed_correction_sections": 0,
            "source_unavailable": source_unavailable,
            "sections": [],
        }
    document = _parse_internal_html_document(source_file.read_bytes())
    container, plans = _section_plans(document)
    correction_plan = _leading_correction_plan(plans)
    correction_plans = [correction_plan] if correction_plan is not None else []
    selected_sections = len(plans) - len(correction_plans)
    if selected_sections < 1:
        raise ValueError(f"business section is required: {source_file}")
    return {
        "status": "ok",
        "source_file": str(source_file),
        "content": _render_without_section_plans(
            document, container, correction_plans
        ),
        "selected_sections": selected_sections,
        "removed_correction_sections": len(correction_plans),
        "sections": [
            {
                "toc_id": plan.toc_id,
                "index": index,
                "title": plan.title,
                "kind": plan.kind,
                "level": plan.level,
                "parent_toc_id": plan.parent_toc_id,
                "is_toc": plan.is_toc,
                "will_remove": plan is correction_plan,
            }
            for index, plan in enumerate(plans, start=1)
        ],
    }


def _validate_automatic_section_output(source_file: Path) -> None:
    if _internal_html_source_unavailable_placeholder_file(source_file) is not None:
        return
    document = _parse_internal_html_document(source_file.read_bytes())
    _container, plans = _section_plans(document)
    correction_count = int(_leading_correction_plan(plans) is not None)
    if len(plans) == correction_count:
        raise ValueError(f"business section is required: {source_file}")


def inspect_disclosure_html_section_output_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Rebuild and compare each expected section output without retaining contents."""
    if str(body.get("data_root") or "").strip():
        body = apply_workspace_defaults("section_save", body)
    input_directory_raw = str(body.get("input_directory") or "").strip()
    output_directory_raw = str(body.get("output_directory") or "").strip()
    if not input_directory_raw:
        raise ValueError("input_directory is required")
    if not output_directory_raw:
        raise ValueError("output_directory is required")
    input_directory = Path(input_directory_raw).expanduser().resolve()
    output_directory = _resolve_sections_output_directory(
        body, Path(output_directory_raw).expanduser().resolve()
    )
    if not input_directory.is_dir():
        raise ValueError(f"input_directory does not exist: {input_directory}")

    all_html_files = _collect_html_files(input_directory, None)
    limit = _parse_limit(body.get("limit"))
    html_files = all_html_files[:limit] if limit is not None else all_html_files
    all_expected_relative_paths = {
        _relative_source_path(input_directory, source_file)
        for source_file in all_html_files
    }
    workers = parse_html_section_worker_count(body.get("workers"))
    results = _map_html_files(
        html_files,
        workers,
        _automatic_section_output,
        cancel_check,
    )
    if _cancel_requested(cancel_check):
        return {"cancelled": True}

    actual_paths = _collect_output_html_paths(output_directory)
    expected_relative_paths: set[str] = set()
    problems: list[dict[str, str]] = []
    missing_files: list[str] = []
    mismatched_files: list[str] = []
    source_unavailable_files = 0
    for source_file, result in zip(html_files, results):
        if result["status"] != "ok":
            problems.append(
                {
                    "source_file": str(source_file),
                    "error": str(result.get("error") or result["status"]),
                }
            )
            continue
        if int(result.get("selected_sections") or 0) == 0:
            continue
        if result.get("source_unavailable"):
            source_unavailable_files += 1
        relative_path = _relative_source_path(input_directory, source_file)
        expected_relative_paths.add(relative_path)
        actual_path = actual_paths.get(relative_path)
        if actual_path is None:
            missing_files.append(relative_path)
        elif actual_path.read_text(encoding="utf-8") != str(result["content"]):
            mismatched_files.append(relative_path)
    if _cancel_requested(cancel_check):
        return {"cancelled": True}

    missing_files.sort()
    mismatched_files.sort()
    unexpected_files = sorted(set(actual_paths) - all_expected_relative_paths)
    integrity_ok = not (
        problems or missing_files or unexpected_files or mismatched_files
    )
    if progress_callback is not None:
        progress_callback(
            "목차 분리 결과 검사 완료: "
            f"예상 {len(expected_relative_paths)}건, 누락 {len(missing_files)}건, "
            f"내용 불일치 {len(mismatched_files)}건"
        )
    return {
        "format": "finiq_disclosure_html_section_output_inspection_v1",
        "input_directory": str(input_directory),
        "output_directory": str(output_directory),
        "summary": {
            "found_files": len(html_files),
            "expected_files": len(expected_relative_paths),
            "actual_files": len(actual_paths),
            "problem_files": len(problems),
            "missing_files": len(missing_files),
            "unexpected_files": len(unexpected_files),
            "mismatched_files": len(mismatched_files),
            "integrity_ok": integrity_ok,
            "source_unavailable_files": source_unavailable_files,
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
    if str(body.get("data_root") or "").strip():
        body = apply_workspace_defaults("section_save", body)
    input_directory_raw = str(body.get("input_directory") or "").strip()
    output_directory_raw = str(body.get("output_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    if not output_directory_raw:
        msg = "output_directory is required"
        raise ValueError(msg)

    input_directory = Path(input_directory_raw).expanduser().resolve()
    output_directory = _resolve_sections_output_directory(
        body, Path(output_directory_raw).expanduser().resolve()
    )
    if not input_directory.is_dir():
        msg = f"input_directory does not exist: {input_directory}"
        raise ValueError(msg)
    if output_directory == input_directory:
        msg = "output_directory must be different from input_directory"
        raise ValueError(msg)
    if output_directory.is_relative_to(input_directory):
        raise ValueError("output_directory must not be inside input_directory")
    if input_directory.is_relative_to(output_directory):
        raise ValueError("input_directory must not be inside output_directory")
    if output_directory.exists() and not output_directory.is_dir():
        raise ValueError(f"output_directory is not a directory: {output_directory}")

    progress_log: deque[str] = deque(maxlen=200)

    def emit(message: str) -> None:
        progress_log.append(message)
        if progress_callback is not None:
            progress_callback(message)

    collect_started_at = time.monotonic()
    emit("입력 폴더에서 목차 분리 대상 HTML을 찾습니다.")
    all_html_files = _collect_html_files(input_directory, None)
    limit = _parse_limit(body.get("limit"))
    html_files = all_html_files[:limit] if limit is not None else all_html_files
    expected_relative_paths = {
        _relative_source_path(input_directory, source_file)
        for source_file in html_files
    }
    all_expected_relative_paths = {
        _relative_source_path(input_directory, source_file)
        for source_file in all_html_files
    }
    unexpected_existing = sorted(
        set(_collect_output_html_paths(output_directory))
        - all_expected_relative_paths
    )
    if unexpected_existing:
        raise ValueError(
            "output_directory contains unexpected existing HTML: "
            f"{unexpected_existing[0]}"
        )
    workers = parse_html_section_worker_count(body.get("workers"))
    progress_interval = _parse_section_progress_interval(
        body.get("progress_interval"), default=25
    )
    emit(
        f"목차 분리 대상 HTML {len(html_files)}건을 찾았습니다. "
        f"파일 탐색 {time.monotonic() - collect_started_at:.1f}초 · "
        f"병렬 처리 {workers}개를 사용합니다."
    )
    validation_started_at = time.monotonic()
    emit("목차 구조와 정정 section 사전 검사를 시작합니다.")
    for _ in _map_html_files(
        html_files,
        workers,
        _validate_automatic_section_output,
        cancel_check,
    ):
        pass
    emit(
        "목차 구조와 정정 section 사전 검사 완료: "
        f"{time.monotonic() - validation_started_at:.1f}초."
    )
    if _cancel_requested(cancel_check):
        return {"cancelled": True}

    saved_files: list[str] = []
    expected_files: list[str] = []
    skipped_files: list[dict[str, str]] = []
    section_pattern_counts: dict[str, dict[str, Any]] = {}
    removed_correction_sections = 0
    source_unavailable_files = 0
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output_directory.name}.part-",
        dir=output_directory.parent,
    ) as temporary_directory:
        staging_directory = Path(temporary_directory)

        def save_one(source_file: Path) -> dict[str, Any]:
            selected = _automatic_section_output(source_file)
            source_relative_path = source_file.relative_to(input_directory)
            staged_path = staging_directory / source_relative_path
            output_path = _section_output_path(
                output_directory,
                source_relative_path,
            )
            _reject_year_directly_under_sections_stage(output_path)
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_text(str(selected["content"]), encoding="utf-8")
            return {
                "status": "ok",
                "staged": staged_path,
                "relative_path": source_relative_path.as_posix(),
                "source_file": str(source_file),
                "source_name": source_file.name,
                "source_relative_path": source_relative_path.as_posix(),
                "sections": selected["sections"],
                "saved": [str(output_path)],
                "expected": [str(output_path)],
                "removed_correction_sections": int(
                    selected["removed_correction_sections"]
                ),
                "source_unavailable": bool(selected.get("source_unavailable")),
            }

        staged_results: list[dict[str, Any]] = []
        results = _map_html_files(html_files, workers, save_one, cancel_check)
        for index, result in enumerate(results, start=1):
            if _cancel_requested(cancel_check):
                return {"cancelled": True}
            _count_section_pattern(section_pattern_counts, result)
            result.pop("sections")
            staged_results.append(result)
            saved_files.extend(result["saved"])
            expected_files.extend(result["expected"])
            removed_correction_sections += int(
                result.get("removed_correction_sections") or 0
            )
            source_unavailable_files += int(bool(result.get("source_unavailable")))
            if (
                index == 1
                or index == len(html_files)
                or index % progress_interval == 0
            ):
                emit(f"목차 저장 중간 확인: {index}/{len(html_files)}건 처리.")
        if _cancel_requested(cancel_check):
            return {"cancelled": True}
        try:
            _publish_staged_section_outputs(
                staging_directory=staging_directory,
                output_directory=output_directory,
                staged_results=staged_results,
                expected_relative_paths=expected_relative_paths,
                all_expected_relative_paths=all_expected_relative_paths,
                cancel_check=cancel_check,
            )
        except _SectionSaveCancelled:
            return {"cancelled": True}

    missing_files = [path for path in expected_files if not Path(path).is_file()]
    unexpected_files = sorted(
        set(_collect_output_html_paths(output_directory))
        - all_expected_relative_paths
    )
    if missing_files or unexpected_files:
        problem = missing_files[0] if missing_files else unexpected_files[0]
        raise ValueError(f"section output integrity check failed: {problem}")
    emit(f"목차 HTML 저장 완료: {len(saved_files)}건")
    emit(
        f"무결성 검사 완료: 저장 대상 {len(expected_files)}건, "
        f"저장 완료 {len(saved_files)}건, 누락 {len(missing_files)}건, "
        f"예상 밖 파일 {len(unexpected_files)}건"
    )
    section_patterns = _sorted_section_patterns(section_pattern_counts)
    return {
        "format": "finiq_disclosure_html_section_save_v2",
        "input_directory": str(input_directory),
        "output_directory": str(output_directory),
        "summary": {
            "found_files": len(html_files),
            "saved_files": len(saved_files),
            "skipped_files": len(skipped_files),
            "expected_files": len(expected_files),
            "integrity_ok": True,
            "missing_files": len(missing_files),
            "unexpected_files": len(unexpected_files),
            "removed_correction_sections": removed_correction_sections,
            "source_unavailable_files": source_unavailable_files,
        },
        "saved_files": saved_files,
        "expected_files": expected_files,
        "missing_files": missing_files,
        "unexpected_files": unexpected_files,
        "skipped_files": skipped_files,
        "section_patterns": section_patterns,
        "progress_log": list(progress_log),
    }
