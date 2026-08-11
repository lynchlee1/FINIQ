"""KIND internal HTML section splitting helpers."""

from __future__ import annotations

import re
import time
from collections import deque
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


def split_internal_html_sections(html_markup: str | bytes) -> list[HtmlSection]:
    """Split a KIND internal HTML document by top-level SECTION headings."""
    document = _parse_internal_html_document(html_markup)
    children = _body_direct_children(document)
    heading_positions: list[tuple[int, etree._Element]] = []
    for position, child in enumerate(children):
        if _is_section_heading(child):
            heading_positions.append((position, child))
    if not heading_positions:
        raise ValueError("canonical SECTION heading is required")
    sections: list[HtmlSection] = []
    for order, (start, heading) in enumerate(heading_positions, start=1):
        end = (
            heading_positions[order][0]
            if order < len(heading_positions)
            else len(children)
        )
        toc_id = f"toc_{order}"
        section_children = children[start:end]
        section_markup = "".join(_element_html(child) for child in section_children)
        sections.append(
            HtmlSection(
                toc_id=toc_id,
                index=order,
                title=_section_title(heading, section_children),
                html=_wrap_section_html(document, section_markup),
            )
        )
    return sections


def inspect_internal_html_sections(html_markup: str | bytes) -> list[HtmlSectionSummary]:
    """Read only top-level SECTION metadata from a KIND internal HTML document."""
    document = _parse_internal_html_document(html_markup)
    children = _body_direct_children(document)
    heading_positions: list[tuple[int, etree._Element]] = []
    for position, child in enumerate(children):
        if _is_section_heading(child):
            heading_positions.append((position, child))
    if not heading_positions:
        raise ValueError("canonical SECTION heading is required")
    sections: list[HtmlSectionSummary] = []
    for order, (start, heading) in enumerate(heading_positions, start=1):
        end = (
            heading_positions[order][0]
            if order < len(heading_positions)
            else len(children)
        )
        toc_id = f"toc_{order}"
        sections.append(
            HtmlSectionSummary(
                toc_id=toc_id,
                index=order,
                title=_section_title(heading, children[start:end]),
            )
        )
    return sections


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


def _selected_section_output(
    source_file: Path,
    section_save_rules: dict[str, set[str]],
) -> dict[str, Any]:
    sections = split_internal_html_sections(source_file.read_bytes())
    signature = _section_signature(_section_dicts_from_split_sections(sections))
    if signature not in section_save_rules:
        return {
            "status": "missing_selection",
            "source_file": str(source_file),
            "error": "missing section selection",
        }
    allowed_toc_ids = section_save_rules[signature]
    selected_sections = [
        section
        for section in sections
        if section.toc_id in allowed_toc_ids
    ]
    return {
        "status": "ok",
        "source_file": str(source_file),
        "content": "\n".join(section.html for section in selected_sections),
        "selected_sections": len(selected_sections),
    }


def _validate_section_save_rule(
    source_file: Path,
    section_save_rules: dict[str, set[str]],
) -> None:
    sections = inspect_internal_html_sections(source_file.read_bytes())
    signature = _section_signature(
        [
            {
                "toc_id": section.toc_id,
                "index": section.index,
                "title": section.title,
            }
            for section in sections
        ]
    )
    if signature not in section_save_rules:
        raise ValueError(f"missing section selection: {source_file}")
    selected_toc_ids = section_save_rules[signature]
    if selected_toc_ids and not any(
        section.toc_id in selected_toc_ids for section in sections
    ):
        raise ValueError(f"section selection matches no sections: {source_file}")


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
    section_save_rules = _section_save_rules(body.get("section_save_rules"))
    results = _map_html_files(
        html_files,
        workers,
        lambda source_file: _selected_section_output(source_file, section_save_rules),
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
    section_save_rules = _section_save_rules(body.get("section_save_rules"))
    emit(
        f"목차 분리 대상 HTML {len(html_files)}건을 찾았습니다. "
        f"파일 탐색 {time.monotonic() - collect_started_at:.1f}초 · "
        f"병렬 처리 {workers}개를 사용합니다."
    )
    validation_started_at = time.monotonic()
    emit("목차 저장 규칙 사전 검사를 시작합니다.")
    for _ in _map_html_files(
        html_files,
        workers,
        lambda source_file: _validate_section_save_rule(
            source_file, section_save_rules
        ),
        cancel_check,
    ):
        pass
    emit(
        "목차 저장 규칙 사전 검사 완료: "
        f"{time.monotonic() - validation_started_at:.1f}초."
    )
    if _cancel_requested(cancel_check):
        return {"cancelled": True}

    output_directory.mkdir(parents=True, exist_ok=True)
    saved_files: list[str] = []
    expected_files: list[str] = []
    skipped_files: list[dict[str, str]] = []

    def save_one(source_file: Path) -> dict[str, Any]:
        selected = _selected_section_output(source_file, section_save_rules)
        if selected["status"] == "missing_selection":
            return {
                "status": "missing_selection",
                "skipped": {
                    "source_file": str(source_file),
                    "error": str(selected["error"]),
                },
                "saved": [],
            }
        if int(selected.get("selected_sections") or 0) == 0:
            source_relative_path = source_file.relative_to(input_directory)
            output_path = output_directory / source_relative_path
            if output_path.is_file():
                output_path.unlink()
            return {
                "status": "no_selected_sections",
                "skipped": {
                    "source_file": str(source_file),
                    "error": "section save rules selected no sections",
                },
                "saved": [],
            }
        source_relative_path = source_file.relative_to(input_directory)
        output_path = output_directory / source_relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(str(selected["content"]), encoding="utf-8")
        return {
            "status": "ok",
            "saved": [str(output_path)],
            "expected": [str(output_path)],
        }

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
            if result["status"] == "missing_selection":
                emit(f"목차 선택 없음 {index}/{len(html_files)}: {source_name}")
            else:
                emit(f"선택 목차 없음 {index}/{len(html_files)}: {source_name}")
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
        "progress_log": list(progress_log),
    }
