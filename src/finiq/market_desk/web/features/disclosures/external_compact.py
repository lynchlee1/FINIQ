"""Compact KIND external HTML into metadata records."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from finiq.concurrency import resolve_worker_count
from finiq.data_scraper.parse._snippets import viewer_html


def _compact_external_viewer_html(html_markup: str | bytes) -> dict[str, Any]:
    """KIND viewer wrapper HTML에서 저장 가치가 있는 외부 메타데이터만 추출한다."""
    html_bytes = (
        html_markup.encode("utf-8") if isinstance(html_markup, str) else html_markup
    )
    parsed = viewer_html(html_markup, require_complete_metadata=True)

    return {
        "acpt_no": parsed.get("acpt_no"),
        "selected_main_doc_no": parsed.get("selected_main_doc_no"),
        "documents": _compact_document_options(parsed),
        "source_sha256": hashlib.sha256(html_bytes).hexdigest(),
        "source_size_bytes": len(html_bytes),
    }


def _compact_document_options(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for source_key in ("main_docs", "attached_docs"):
        for document in parsed.get(source_key) or []:
            if not isinstance(document, dict):
                continue
            doc_no = str(document.get("doc_no") or "").strip()
            if not doc_no:
                continue
            documents.append(
                {
                    "select_id": str(document.get("select_id") or ""),
                    "select_name": str(document.get("select_name") or ""),
                    "option_index": int(document["option_index"]),
                    "doc_no": doc_no,
                    "text": document.get("label") or "",
                    "value": document.get("value") or "",
                    "latest_flag": document.get("latest_flag"),
                    "selected": bool(document.get("selected")),
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
    if embedded_acpt_no != acpt_no:
        raise ValueError(
            f"External HTML acpt_no {embedded_acpt_no} does not match "
            f"input filename {html_path.name}"
        )
    selected_main_doc_no = str(parsed.get("selected_main_doc_no") or "").strip()
    if not selected_main_doc_no:
        raise ValueError(f"External HTML selected main docNo not found: {html_path.name}")
    record = {
        "acpt_no": acpt_no,
        "title": "",
        "selected_main_doc_no": selected_main_doc_no,
        "metadata": {},
        "docs": parsed.get("documents") or [],
        "source_sha256": parsed.get("source_sha256") or "",
        "source_size_bytes": parsed.get("source_size_bytes") or 0,
    }
    return index, year, acpt_no, record


def _external_html_compress_workers(body: dict[str, Any], total_files: int) -> int:
    if "workers" in body:
        raise ValueError("workers is not supported; use parallel_workers")
    raw_workers = body.get("parallel_workers")
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
