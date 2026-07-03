"""Compact KIND external viewer HTML into metadata records."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from os import cpu_count
from pathlib import Path
from typing import Any

from bs4 import Comment, Tag

from finiq.data_scraper.parse._markup import (
    _clean_text,
    get_tag_attributes,
    parse_html_with_recovery,
)
from finiq.data_scraper.parse._snippets import viewer_html

_SIMPLE_SCRIPT_VAR_RE = re.compile(
    r"\bvar\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?P<value>'[^']*'|\"[^\"]*\"|[-]?\d+(?:\.\d+)?)\s*;"
)
_TEXT_BLOCK_TAGS = {
    "button",
    "caption",
    "dd",
    "dt",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "label",
    "li",
    "p",
    "span",
    "td",
    "th",
}


def _compact_tag(tag: Tag, *, text: bool = False) -> dict[str, Any]:
    record: dict[str, Any] = {"attrs": get_tag_attributes(tag)}
    if text:
        record["text"] = _clean_text(tag.get_text(separator=" ", strip=True))
    return record


def _compact_option_tag(option_tag: Tag) -> dict[str, Any]:
    value = str(option_tag.get("value") or "").strip()
    doc_no = value
    latest_flag = None
    if "|" in value:
        doc_no, latest_flag = value.split("|", 1)
    return {
        "attrs": get_tag_attributes(option_tag),
        "text": _clean_text(option_tag.get_text(separator=" ", strip=True)),
        "value": value,
        "doc_no": doc_no.strip(),
        "latest_flag": latest_flag.strip().upper() if latest_flag else None,
        "selected": option_tag.has_attr("selected"),
    }


def _compact_select_tag(select_tag: Tag) -> dict[str, Any]:
    return {
        "attrs": get_tag_attributes(select_tag),
        "id": str(select_tag.get("id") or "").strip(),
        "name": str(select_tag.get("name") or "").strip(),
        "options": [
            _compact_option_tag(option_tag)
            for option_tag in select_tag.find_all("option")
            if isinstance(option_tag, Tag)
        ],
    }


def _direct_text(tag: Tag) -> str:
    return _clean_text(
        " ".join(
            str(item)
            for item in tag.find_all(string=True, recursive=False)
            if not isinstance(item, Comment)
        )
    )


def _compact_anchor_tag(anchor_tag: Tag) -> dict[str, Any]:
    return {
        "attrs": get_tag_attributes(anchor_tag),
        "text": _clean_text(anchor_tag.get_text(separator=" ", strip=True)),
        "images": [
            _compact_tag(image_tag)
            for image_tag in anchor_tag.find_all("img")
            if isinstance(image_tag, Tag)
        ],
    }


def _compact_script_tag(script_tag: Tag) -> dict[str, Any]:
    script_text = (
        "" if script_tag.get("src") else _clean_text(script_tag.get_text() or "")
    )
    return {
        "attrs": get_tag_attributes(script_tag),
        "text": script_text,
        "variables": _extract_simple_script_variables(script_tag.get_text() or "")
        if script_text
        else [],
    }


def _compact_text_block(tag: Tag) -> dict[str, Any] | None:
    text = _direct_text(tag)
    if not text:
        return None
    return {
        "tag": tag.name,
        "attrs": get_tag_attributes(tag),
        "text": text,
    }


def _extract_simple_script_variables(script_text: str) -> list[dict[str, str]]:
    variables: list[dict[str, str]] = []
    for match in _SIMPLE_SCRIPT_VAR_RE.finditer(script_text):
        value = match.group("value").strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        variables.append({"name": match.group("name"), "value": value})
    return variables


def _compact_external_viewer_html(html_markup: str | bytes) -> dict[str, Any]:
    """KIND viewer wrapper HTML에서 저장 가치가 있는 외부 메타데이터만 추출한다."""
    html_bytes = (
        html_markup.encode("utf-8") if isinstance(html_markup, str) else html_markup
    )
    parsed = viewer_html(html_markup)
    soup = parse_html_with_recovery(html_markup)

    title_tag = soup.find("title")
    header_tag = soup.find("h1", class_="ttl")
    forms: list[dict[str, Any]] = []
    for form_tag in soup.find_all("form"):
        if not isinstance(form_tag, Tag):
            continue
        forms.append(
            {
                "attrs": get_tag_attributes(form_tag),
                "inputs": [
                    _compact_tag(input_tag)
                    for input_tag in form_tag.find_all("input")
                    if isinstance(input_tag, Tag)
                ],
                "selects": [
                    _compact_select_tag(select_tag)
                    for select_tag in form_tag.find_all("select")
                    if isinstance(select_tag, Tag)
                ],
                "textareas": [
                    _compact_tag(textarea_tag, text=True)
                    for textarea_tag in form_tag.find_all("textarea")
                    if isinstance(textarea_tag, Tag)
                ],
                "buttons": [
                    _compact_tag(button_tag, text=True)
                    for button_tag in form_tag.find_all("button")
                    if isinstance(button_tag, Tag)
                ],
            }
        )

    script_variables: list[dict[str, str]] = []
    for script_tag in soup.find_all("script"):
        if not isinstance(script_tag, Tag) or script_tag.get("src"):
            continue
        script_variables.extend(
            _extract_simple_script_variables(script_tag.get_text() or "")
        )

    text_blocks: list[dict[str, Any]] = []
    for text_tag in soup.find_all(_TEXT_BLOCK_TAGS):
        if not isinstance(text_tag, Tag):
            continue
        text_block = _compact_text_block(text_tag)
        if text_block is not None:
            text_blocks.append(text_block)

    title = parsed.get("title") or ""
    if not title and isinstance(title_tag, Tag):
        title = _clean_text(title_tag.get_text())

    return {
        "acpt_no": parsed.get("acpt_no"),
        "title": title,
        "header": parsed.get("header")
        or (
            _clean_text(header_tag.get_text(separator=" ", strip=True))
            if isinstance(header_tag, Tag)
            else ""
        ),
        "selected_main_doc_no": parsed.get("selected_main_doc_no"),
        "main_docs": parsed.get("main_docs") or [],
        "attached_docs": parsed.get("attached_docs") or [],
        "meta": [
            get_tag_attributes(meta_tag)
            for meta_tag in soup.find_all("meta")
            if isinstance(meta_tag, Tag) and get_tag_attributes(meta_tag)
        ],
        "forms": forms,
        "inputs": [
            _compact_tag(input_tag)
            for input_tag in soup.find_all("input")
            if isinstance(input_tag, Tag)
        ],
        "selects": [
            _compact_select_tag(select_tag)
            for select_tag in soup.find_all("select")
            if isinstance(select_tag, Tag)
        ],
        "links": [
            _compact_anchor_tag(anchor_tag)
            for anchor_tag in soup.find_all("a")
            if isinstance(anchor_tag, Tag)
        ],
        "frames": [
            _compact_tag(frame_tag)
            for frame_tag in soup.find_all(["iframe", "frame"])
            if isinstance(frame_tag, Tag)
        ],
        "resources": [
            _compact_tag(resource_tag)
            for resource_tag in soup.find_all(
                ["link", "img", "object", "embed", "source"]
            )
            if isinstance(resource_tag, Tag)
        ],
        "scripts": [
            _compact_script_tag(script_tag)
            for script_tag in soup.find_all("script")
            if isinstance(script_tag, Tag)
        ],
        "text_blocks": text_blocks,
        "script_variables": script_variables,
        "source_sha256": hashlib.sha256(html_bytes).hexdigest(),
        "source_size_bytes": len(html_bytes),
    }


def _compact_document_options(selects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for select_record in selects:
        select_id = str(select_record.get("id") or "").strip()
        select_name = str(select_record.get("name") or "").strip()
        if select_id not in {"mainDoc", "attachedDoc"}:
            continue
        for option_index, option in enumerate(select_record.get("options") or []):
            if not isinstance(option, dict):
                continue
            doc_no = str(option.get("doc_no") or "").strip()
            if not doc_no:
                continue
            documents.append(
                {
                    "select_id": select_id,
                    "select_name": select_name,
                    "option_index": option_index,
                    "doc_no": doc_no,
                    "text": option.get("text") or "",
                    "value": option.get("value") or "",
                    "latest_flag": option.get("latest_flag"),
                    "selected": bool(option.get("selected")),
                }
            )
    return documents


def _compress_external_html_file(
    args: tuple[int, str, Path],
) -> tuple[int, str, str, dict[str, Any]]:
    index, year, html_path = args
    parsed = _compact_external_viewer_html(html_path.read_bytes())
    acpt_no = str(parsed.get("acpt_no") or html_path.stem).strip()
    record = {
        "acpt_no": acpt_no,
        "title": parsed.get("title") or parsed.get("header") or "",
        "header": parsed.get("header") or "",
        "selected_main_doc_no": parsed.get("selected_main_doc_no"),
        "metadata": {},
        "docs": _compact_document_options(parsed.get("selects") or []),
        "source_sha256": parsed.get("source_sha256") or "",
        "source_size_bytes": parsed.get("source_size_bytes") or 0,
    }
    return index, year, acpt_no, record


def _external_html_compress_workers(body: dict[str, Any], total_files: int) -> int:
    raw_workers = body.get("parallel_workers", body.get("workers"))
    if raw_workers is not None:
        try:
            requested_workers = int(raw_workers)
        except (TypeError, ValueError):
            requested_workers = 1
        return max(1, min(requested_workers, total_files))
    return max(1, min(total_files, cpu_count() or 1))


def _verify_compressed_external_html_files(
    *,
    written_files: list[str],
    expected_acpt_numbers: list[str],
) -> dict[str, Any]:
    expected = set(expected_acpt_numbers)
    verified_acpt_numbers: list[str] = []
    missing_files: list[str] = []
    invalid_files: list[dict[str, str]] = []

    for written_file in written_files:
        path = Path(written_file)
        if not path.is_file():
            missing_files.append(written_file)
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            invalid_files.append({"path": written_file, "error": str(exc)})
            continue
        records = payload.get("records")
        if not isinstance(records, list):
            invalid_files.append(
                {"path": written_file, "error": "records is not a list"}
            )
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            acpt_no = str(record.get("acpt_no") or "").strip()
            if acpt_no:
                verified_acpt_numbers.append(acpt_no)

    verified = set(verified_acpt_numbers)
    verified_counts = Counter(verified_acpt_numbers)
    duplicate_acpt_numbers = sorted(
        acpt_no for acpt_no, count in verified_counts.items() if count > 1
    )
    missing_acpt_numbers = sorted(expected - verified)
    unexpected_acpt_numbers = sorted(verified - expected)
    passed = (
        not missing_files
        and not invalid_files
        and not missing_acpt_numbers
        and not unexpected_acpt_numbers
        and not duplicate_acpt_numbers
    )

    return {
        "passed": passed,
        "expected_records": len(expected_acpt_numbers),
        "verified_records": len(verified_acpt_numbers),
        "missing_records": len(missing_acpt_numbers),
        "unexpected_records": len(unexpected_acpt_numbers),
        "duplicate_records": len(duplicate_acpt_numbers),
        "missing_files": missing_files,
        "invalid_files": invalid_files,
        "missing_acpt_numbers": missing_acpt_numbers,
        "unexpected_acpt_numbers": unexpected_acpt_numbers,
        "duplicate_acpt_numbers": duplicate_acpt_numbers,
    }
