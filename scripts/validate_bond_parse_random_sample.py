"""Validate bond issuance parsing against random grouped-section HTML files."""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from finiq.market_desk.web.features.disclosures.html_parse_common import (  # noqa: E402
    _apply_parse_metadata,
    _load_html_parse_metadata,
)
from finiq.market_desk.web.html_parsers.bond_issuance import parse_bond_issuance  # noqa: E402
from finiq.market_desk.web.html_parsers.common import (  # noqa: E402
    clean_text,
    parse_html_document,
    row_contains,
)
from finiq.market_desk.web.html_parsers.common.tables import extract_tables  # noqa: E402
from finiq.market_desk.web.html_parsers.common.text import parse_int  # noqa: E402

DEFAULT_INPUT_DIRECTORY = (
    PROJECT_ROOT
    / "resources"
    / "KIND"
    / "bond_issuance"
    / "kind_html_contents_grouped_sections"
)
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "tmp" / "bond_parse_random_sample_report.json"

REQUIRED_FIELDS = (
    "acpt_no",
    "title",
    "corp_name",
    "회차",
    "종류",
    "기업명(행사대상)",
    "상장구분",
    "발행금액",
    "행사가액",
    "납입일",
    "만기일",
    "사채발행방법",
    "행사시작일",
    "행사종료일",
    "투자자",
)

FIELD_KEYWORDS = {
    "corp_name": ("SECTION-1",),
    "회차": ("사채의 종류", "회차"),
    "종류": ("SECTION-1", "사채의 종류"),
    "기업명(행사대상)": ("교환대상", "전환에 따라", "전환으로 발행할", "인수권행사에 따라"),
    "상장구분": ("코스닥시장", "유가증권시장", "코넥스시장"),
    "발행금액": ("사채의 권면",),
    "행사가액": ("전환가액", "교환가액", "행사가액"),
    "납입일": ("납입일",),
    "만기일": ("사채만기일", "사채만기"),
    "사채발행방법": ("사채발행방법",),
    "행사시작일": ("전환청구기간", "교환청구기간", "권리행사기간", "시작일"),
    "행사종료일": ("전환청구기간", "교환청구기간", "권리행사기간", "종료일"),
    "투자자": ("특정인에 대한 대상자별 사채발행내역", "발행 대상자명", "발행권면"),
}


def _is_missing(value: Any) -> bool:
    return value in (None, "", [])


def _html_text(path: Path) -> str:
    document = parse_html_document(path.read_bytes())
    return clean_text(" ".join(document.itertext()))


def _context_for_missing_fields(path: Path, missing_fields: list[str]) -> dict[str, list[str]]:
    text = _html_text(path)
    contexts: dict[str, list[str]] = {}
    for field in missing_fields:
        field_contexts: list[str] = []
        for keyword in FIELD_KEYWORDS.get(field, ()):
            for match in re.finditer(re.escape(keyword), text):
                start = max(match.start() - 120, 0)
                end = min(match.end() + 220, len(text))
                snippet = text[start:end]
                if snippet not in field_contexts:
                    field_contexts.append(snippet)
                if len(field_contexts) >= 3:
                    break
            if len(field_contexts) >= 3:
                break
        contexts[field] = field_contexts
    return contexts


def _source_status_for_investors(path: Path) -> str:
    document = parse_html_document(path.read_bytes())
    for table in extract_tables(document):
        rows = table.get("logical_rows") or []
        if not rows or not row_contains(rows[0], "발행 대상자명", "발행권면"):
            continue
        for row in rows[1:]:
            if not row or row[0] in {"-", "합계", "총계", "계"}:
                continue
            if any(parse_int(value) is not None for value in row):
                return "source_has_values"
        return "source_table_without_values"
    return "source_table_absent"


def _missing_classification(path: Path, missing_fields: list[str]) -> dict[str, str]:
    classification: dict[str, str] = {}
    for field in missing_fields:
        if field == "투자자":
            classification[field] = _source_status_for_investors(path)
        else:
            classification[field] = "required_scalar_missing"
    return classification


def _unexpected_missing_fields(classification: dict[str, str]) -> list[str]:
    return [
        field
        for field, status in classification.items()
        if status in {"source_has_values", "required_scalar_missing"}
    ]


def _parse_one(path: Path, metadata_index: dict[str, dict[str, str]]) -> dict[str, Any]:
    acpt_no = path.stem
    metadata = metadata_index.get(acpt_no)
    if metadata is None:
        raise ValueError(f"metadata is required for acpt_no={acpt_no}")
    title = str(metadata.get("title") or "").strip()
    if not title:
        raise ValueError(f"title metadata is required for acpt_no={acpt_no}")
    record = parse_bond_issuance(path.read_bytes(), file_path=path, title=title)
    return _apply_parse_metadata(
        record,
        metadata_index,
        reporting_company_field="corp_name",
    )


def validate_sample(
    input_directory: Path,
    *,
    sample_size: int,
    seed: int,
    filtered_metadata_path: Path,
    compressed_metadata_path: Path,
) -> dict[str, Any]:
    html_files = sorted(path for path in input_directory.rglob("*.html") if path.is_file())
    if len(html_files) < sample_size:
        msg = f"sample_size {sample_size} exceeds available html files {len(html_files)}"
        raise ValueError(msg)

    rng = random.Random(seed)
    sample = rng.sample(html_files, sample_size)
    metadata_index, _ = _load_html_parse_metadata(
        input_directory,
        filtered_metadata_path=filtered_metadata_path,
        compressed_metadata_path=compressed_metadata_path,
    )

    records: list[dict[str, Any]] = []
    missing_records: list[dict[str, Any]] = []
    field_missing_counts = {field: 0 for field in REQUIRED_FIELDS}

    for index, path in enumerate(sample, start=1):
        record = _parse_one(path, metadata_index)
        missing_fields = [field for field in REQUIRED_FIELDS if _is_missing(record.get(field))]
        for field in missing_fields:
            field_missing_counts[field] += 1

        item = {
            "index": index,
            "acpt_no": record.get("acpt_no"),
            "title": record.get("title"),
            "missing_fields": missing_fields,
            "parse_warnings": record.get("parse_warnings") or [],
        }
        records.append(item)
        if missing_fields:
            classification = _missing_classification(path, missing_fields)
            missing_records.append(
                {
                    **item,
                    "missing_classification": classification,
                    "unexpected_missing_fields": _unexpected_missing_fields(classification),
                    "source_context": _context_for_missing_fields(path, missing_fields),
                }
            )

    unexpected_missing_records = [
        record for record in missing_records if record["unexpected_missing_fields"]
    ]
    return {
        "format": "finiq_bond_parse_random_sample_validation_v1",
        "input_directory": str(input_directory),
        "sample_size": sample_size,
        "seed": seed,
        "summary": {
            "available_files": len(html_files),
            "sampled_files": len(sample),
            "complete_records": sample_size - len(missing_records),
            "records_with_missing_fields": len(missing_records),
            "records_with_unexpected_missing_fields": len(unexpected_missing_records),
            "field_missing_counts": field_missing_counts,
        },
        "records": records,
        "missing_records": missing_records,
        "unexpected_missing_records": unexpected_missing_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-directory", type=Path, default=DEFAULT_INPUT_DIRECTORY)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260629)
    parser.add_argument("--filtered-metadata", type=Path, required=True)
    parser.add_argument("--compressed-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    payload = validate_sample(
        args.input_directory.expanduser().resolve(),
        sample_size=args.sample_size,
        seed=args.seed,
        filtered_metadata_path=args.filtered_metadata.expanduser().resolve(),
        compressed_metadata_path=args.compressed_metadata.expanduser().resolve(),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote validation report: {args.output}")
    return 1 if payload["unexpected_missing_records"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
