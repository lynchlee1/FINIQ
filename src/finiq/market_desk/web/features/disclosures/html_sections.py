"""KIND internal HTML section splitting helpers."""

from __future__ import annotations

import re
import time
from collections import deque
from copy import deepcopy
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, TypeVar

from lxml import etree, html

from finiq.concurrency import resolve_worker_count
from finiq.market_desk.web.html_parsers.common import decode_html_markup

ProgressCallback = Callable[[str], None]
_SECTION_CLASS_RE = re.compile(r"^SECTION-\d+$")
_HEADING_TAGS = {f"h{level}" for level in range(1, 7)}
_CORRECTION_TITLE_TOKEN = "정정"
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


@dataclass(frozen=True)
class _HtmlSectionPlan:
    start: int
    end: int
    title: str


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _element_html(element: etree._Element) -> str:
    return html.tostring(element, encoding="unicode", method="html")


def _element_children(element: etree._Element) -> list[etree._Element]:
    return [child for child in element if isinstance(child.tag, str)]


def _parse_internal_html_document(html_markup: str | bytes) -> html.HtmlElement:
    decoded_markup = decode_html_markup(html_markup)
    if re.search(r"<head(?:\s|>)", decoded_markup, flags=re.IGNORECASE) is None:
        raise ValueError("HTML head is required")
    if re.search(r"<body(?:\s|>)", decoded_markup, flags=re.IGNORECASE) is None:
        raise ValueError("HTML body is required")
    parser = html.HTMLParser(encoding="utf-8", recover=True, huge_tree=True)
    return html.fromstring(decoded_markup, parser=parser)


def _body_direct_children(document: html.HtmlElement) -> list[etree._Element]:
    body_nodes = document.xpath("//body")
    if not body_nodes:
        raise ValueError("HTML body is required")
    return list(body_nodes[0])


def _body_attrs(document: html.HtmlElement) -> str:
    body_nodes = document.xpath("//body")
    if not body_nodes:
        raise ValueError("HTML body is required")
    attrs = []
    for key, value in body_nodes[0].attrib.items():
        if key.lower() == "style":
            continue
        attrs.append(f'{key}="{escape(str(value), quote=True)}"')
    return (" " + " ".join(attrs)) if attrs else ""


def _head_markup(document: html.HtmlElement) -> str:
    head_nodes = document.xpath("//head")
    if not head_nodes:
        raise ValueError("HTML head is required")
    return "".join(_element_html(child) for child in head_nodes[0])


def _section_title(
    heading: etree._Element, section_children: list[etree._Element]
) -> str:
    title = _clean_text(heading.text_content())
    if not title and len(section_children) > 1:
        first_content = section_children[1]
        if isinstance(first_content.tag, str) and first_content.tag.lower() == "p":
            title = _clean_text(first_content.text_content())
    if not title:
        raise ValueError("SECTION heading title is required")
    return title


def _first_text_fragment(elements: Iterable[etree._Element]) -> str:
    for element in elements:
        for fragment in element.itertext():
            title = _clean_text(fragment)
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


def _is_section_heading(element: etree._Element) -> bool:
    if not isinstance(element.tag, str):
        return False
    if element.tag.lower() not in _HEADING_TAGS:
        return False
    return any(
        _SECTION_CLASS_RE.match(class_name)
        for class_name in str(element.get("class") or "").split()
    )


def _is_section_paragraph(element: etree._Element) -> bool:
    if not isinstance(element.tag, str) or element.tag.lower() != "p":
        return False
    return any(
        _SECTION_CLASS_RE.match(class_name)
        for class_name in str(element.get("class") or "").split()
    )


def _has_class(element: etree._Element, class_name: str) -> bool:
    return class_name in str(element.get("class") or "").split()


def _section_container_and_boundaries(
    document: html.HtmlElement,
) -> tuple[etree._Element, list[tuple[int, etree._Element]], str]:
    body_nodes = document.xpath("//body")
    if not body_nodes:
        raise ValueError("HTML body is required")
    body = body_nodes[0]
    body_children = _element_children(body)

    heading_boundaries = [
        (position, child)
        for position, child in enumerate(body_children)
        if _is_section_heading(child)
    ]
    if heading_boundaries:
        return body, heading_boundaries, "heading"

    paragraph_boundaries = [
        (position, child)
        for position, child in enumerate(body_children)
        if _is_section_paragraph(child)
    ]
    if paragraph_boundaries:
        return body, paragraph_boundaries, "paragraph"

    xforms_wrappers = [child for child in body_children if _has_class(child, "xforms")]
    if len(xforms_wrappers) != 1:
        raise ValueError("supported TOC structure is required")
    wrapper_children = _element_children(xforms_wrappers[0])
    if len(wrapper_children) != 1:
        raise ValueError("XForms content wrapper is required")
    container = wrapper_children[0]
    container_children = _element_children(container)
    xforms_boundaries = [
        (position, child)
        for position, child in enumerate(container_children)
        if child.tag.lower() == "div" and _has_class(child, "xforms_title")
    ]
    if len(xforms_boundaries) != 1:
        raise ValueError("one direct XForms TOC boundary is required")
    return container, xforms_boundaries, "xforms"


def _section_plans(
    document: html.HtmlElement,
) -> tuple[etree._Element, list[_HtmlSectionPlan]]:
    container, boundaries, structure = _section_container_and_boundaries(document)
    children = _element_children(container)
    plans: list[_HtmlSectionPlan] = []
    first_boundary = boundaries[0][0]
    preamble_title = _first_text_fragment(children[:first_boundary])
    if preamble_title:
        plans.append(
            _HtmlSectionPlan(start=0, end=first_boundary, title=preamble_title)
        )

    for order, (start, boundary) in enumerate(boundaries):
        end = boundaries[order + 1][0] if order + 1 < len(boundaries) else len(children)
        section_children = children[start:end]
        if structure == "heading":
            title = _section_title(boundary, section_children)
        else:
            title = _clean_text(boundary.text_content())
            if not title:
                raise ValueError("SECTION boundary title is required")
        plans.append(_HtmlSectionPlan(start=start, end=end, title=title))
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
    cloned_children = _element_children(cloned_container)
    for index in range(len(cloned_children) - 1, -1, -1):
        if index < plan.start or index >= plan.end:
            cloned_container.remove(cloned_children[index])
    return "<!DOCTYPE html>\n" + html.tostring(
        cloned_document, encoding="unicode", method="html"
    )


def _is_correction_section_title(title: str) -> bool:
    return _CORRECTION_TITLE_TOKEN in re.sub(r"\s+", "", title)


def split_internal_html_sections(html_markup: str | bytes) -> list[HtmlSection]:
    """Split every structural TOC section before any correction filtering."""
    document = _parse_internal_html_document(html_markup)
    container, plans = _section_plans(document)
    return [
        HtmlSection(
            toc_id=f"toc_{index}",
            index=index,
            title=plan.title,
            html=_render_section_plan(document, container, plan),
        )
        for index, plan in enumerate(plans, start=1)
    ]


def inspect_internal_html_sections(html_markup: str | bytes) -> list[HtmlSectionSummary]:
    """Read every structural TOC title without rendering section HTML."""
    document = _parse_internal_html_document(html_markup)
    _container, plans = _section_plans(document)
    return [
        HtmlSectionSummary(toc_id=f"toc_{index}", index=index, title=plan.title)
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
    sections = inspect_internal_html_sections(source_file.read_bytes())
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


def _section_patterns(documents: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
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

    collect_started_at = time.monotonic()
    if progress_callback is not None:
        progress_callback("입력 폴더에서 목차 확인 대상 HTML을 찾습니다.")
    html_files = _collect_html_files(input_directory, _parse_limit(body.get("limit")))
    workers = parse_html_section_worker_count(body.get("workers"))

    def emit(message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)

    def inspect_one(source_file: Path) -> dict[str, Any]:
        sections = inspect_internal_html_sections(source_file.read_bytes())
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
        f"목차 확인 대상 HTML {len(html_files)}건을 찾았습니다. "
        f"파일 탐색 {time.monotonic() - collect_started_at:.1f}초 · "
        f"병렬 처리 {workers}개를 사용합니다."
    )
    results = _map_html_files(html_files, workers, inspect_one, cancel_check)
    documents: list[dict[str, Any]] = []
    for index, result in enumerate(results, start=1):
        if _cancel_requested(cancel_check):
            return {"cancelled": True}
        documents.append(result["document"])
        if index == 1 or index == len(html_files) or index % 100 == 0:
            emit(f"목차 확인 중간 확인: {index}/{len(html_files)}건 처리.")

    total_files = len(html_files)
    return {
        "format": "finiq_disclosure_html_section_inspect_v1",
        "input_directory": str(input_directory),
        "summary": {
            "found_files": total_files,
            "documents_with_sections": len(documents),
            "files_without_sections": 0,
            "failed_files": 0,
            "reported_problem_files": 0,
        },
        "documents": documents,
        "problem_files": [],
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
    cloned_children = _element_children(cloned_container)
    for index in range(len(cloned_children) - 1, -1, -1):
        if index in excluded_indexes:
            cloned_container.remove(cloned_children[index])
    return "<!DOCTYPE html>\n" + html.tostring(
        cloned_document, encoding="unicode", method="html"
    )


def _automatic_section_output(source_file: Path) -> dict[str, Any]:
    document = _parse_internal_html_document(source_file.read_bytes())
    container, plans = _section_plans(document)
    correction_plans = [
        plan for plan in plans if _is_correction_section_title(plan.title)
    ]
    if len(correction_plans) > 1:
        raise ValueError(f"multiple correction sections: {source_file}")
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
    }


def _validate_automatic_section_output(source_file: Path) -> None:
    document = _parse_internal_html_document(source_file.read_bytes())
    _container, plans = _section_plans(document)
    correction_count = sum(
        1 for plan in plans if _is_correction_section_title(plan.title)
    )
    if correction_count > 1:
        raise ValueError(f"multiple correction sections: {source_file}")
    if len(plans) == correction_count:
        raise ValueError(f"business section is required: {source_file}")


def inspect_disclosure_html_section_output_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Rebuild and compare each expected section output without retaining contents."""
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
    results = _map_html_files(
        html_files,
        workers,
        _automatic_section_output,
        cancel_check,
    )
    if _cancel_requested(cancel_check):
        return {"cancelled": True}

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
    expected_relative_paths: set[str] = set()
    problems: list[dict[str, str]] = []
    missing_files: list[str] = []
    mismatched_files: list[str] = []
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
    unexpected_files = sorted(set(actual_paths) - expected_relative_paths)
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

    progress_log: deque[str] = deque(maxlen=200)

    def emit(message: str) -> None:
        progress_log.append(message)
        if progress_callback is not None:
            progress_callback(message)

    collect_started_at = time.monotonic()
    emit("입력 폴더에서 목차 분리 대상 HTML을 찾습니다.")
    html_files = _collect_html_files(input_directory, _parse_limit(body.get("limit")))
    workers = parse_html_section_worker_count(body.get("workers"))
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

    output_directory.mkdir(parents=True, exist_ok=True)
    saved_files: list[str] = []
    expected_files: list[str] = []
    skipped_files: list[dict[str, str]] = []
    removed_correction_sections = 0

    def save_one(source_file: Path) -> dict[str, Any]:
        selected = _automatic_section_output(source_file)
        source_relative_path = source_file.relative_to(input_directory)
        output_path = output_directory / source_relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(str(selected["content"]), encoding="utf-8")
        return {
            "status": "ok",
            "saved": [str(output_path)],
            "expected": [str(output_path)],
            "removed_correction_sections": int(
                selected["removed_correction_sections"]
            ),
        }

    results = _map_html_files(html_files, workers, save_one, cancel_check)
    for index, result in enumerate(results, start=1):
        if _cancel_requested(cancel_check):
            return {"cancelled": True}
        if result["status"] == "ok":
            saved_files.extend(result["saved"])
            expected_files.extend(result["expected"])
            removed_correction_sections += int(
                result.get("removed_correction_sections") or 0
            )
        else:
            skipped_files.append(result["skipped"])
            source_name = Path(result["skipped"]["source_file"]).name
            emit(f"목차 저장 제외 {index}/{len(html_files)}: {source_name}")
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
            "removed_correction_sections": removed_correction_sections,
        },
        "saved_files": saved_files,
        "expected_files": expected_files,
        "missing_files": missing_files,
        "skipped_files": skipped_files,
        "progress_log": list(progress_log),
    }
