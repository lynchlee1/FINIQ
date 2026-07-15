"""Compact KIND external HTML into metadata records."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from bs4 import Tag

from finiq.concurrency import resolve_worker_count
from finiq.data_scraper.parse._markup import (
    _clean_text,
    parse_html_with_recovery,
)
from finiq.data_scraper.parse._snippets import viewer_html


def _compact_option_tag(option_tag: Tag) -> dict[str, Any]:
    value = str(option_tag.get("value") or "").strip()
    doc_no = value
    latest_flag = None
    if "|" in value:
        doc_no, latest_flag = value.split("|", 1)
    return {
        "text": _clean_text(option_tag.get_text(separator=" ", strip=True)),
        "value": value,
        "doc_no": doc_no.strip(),
        "latest_flag": latest_flag.strip().upper() if latest_flag else None,
        "selected": option_tag.has_attr("selected"),
    }


def _compact_select_tag(select_tag: Tag) -> dict[str, Any]:
    return {
        "id": str(select_tag.get("id") or "").strip(),
        "name": str(select_tag.get("name") or "").strip(),
        "options": [
            _compact_option_tag(option_tag)
            for option_tag in select_tag.find_all("option")
            if isinstance(option_tag, Tag)
        ],
    }


def _compact_external_viewer_html(html_markup: str | bytes) -> dict[str, Any]:
    """KIND viewer wrapper HTML에서 저장 가치가 있는 외부 메타데이터만 추출한다."""
    html_bytes = (
        html_markup.encode("utf-8") if isinstance(html_markup, str) else html_markup
    )
    parsed = viewer_html(html_markup)
    soup = parse_html_with_recovery(html_markup)

    return {
        "acpt_no": parsed.get("acpt_no"),
        "selected_main_doc_no": parsed.get("selected_main_doc_no"),
        "selects": [
            _compact_select_tag(select_tag)
            for select_tag in soup.find_all("select")
            if isinstance(select_tag, Tag)
            and str(select_tag.get("id") or "").strip()
            in {"mainDoc", "attachedDoc"}
        ],
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
    acpt_no = html_path.stem
    embedded_acpt_no = str(parsed.get("acpt_no") or "").strip()
    if embedded_acpt_no and embedded_acpt_no != acpt_no:
        raise ValueError(
            f"External HTML acpt_no {embedded_acpt_no} does not match "
            f"input filename {html_path.name}"
        )
    record = {
        "acpt_no": acpt_no,
        "title": "",
        "selected_main_doc_no": parsed.get("selected_main_doc_no"),
        "metadata": {},
        "docs": _compact_document_options(parsed.get("selects") or []),
        "source_sha256": parsed.get("source_sha256") or "",
        "source_size_bytes": parsed.get("source_size_bytes") or 0,
    }
    return index, year, acpt_no, record


def _external_html_compress_workers(body: dict[str, Any], total_files: int) -> int:
    raw_workers = body.get("parallel_workers", body.get("workers"))
    return resolve_worker_count(
        raw_workers,
        item_count=total_files,
        field_name="parallel_workers",
    )


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
