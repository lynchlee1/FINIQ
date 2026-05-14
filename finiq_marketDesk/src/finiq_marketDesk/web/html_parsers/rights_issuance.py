"""Parser entrypoint for paid/free capital increase disclosures."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .bond_issuance import _fetch_selected_viewer_body
from .common import build_base_record, clean_text, parse_int

MODE = "rights_issuance"
FUNDING_PURPOSE_LABELS = [
    "시설자금",
    "영업양수자금",
    "운영자금",
    "채무상환자금",
    "타법인 증권 취득자금",
    "기타자금",
]
STOCK_LABELS = ["보통주식", "기타주식"]


def parse_rights_issuance(html_text: str | bytes, *, file_path: str | Path) -> dict[str, Any]:
    """Parse capital increase HTML into the shared v1 architecture record."""
    record = build_base_record(html_text, file_path=file_path, mode=MODE)
    rows = _main_rights_rows(record["raw_tables"])
    if not rows:
        body_html = _fetch_selected_viewer_body(html_text)
        if body_html is not None:
            original_title = record.get("title") or ""
            original_correction_families = record.get("correction_families")
            original_rcept_no = record.get("rcept_no")
            original_acpt_no = record.get("acpt_no")
            record = build_base_record(body_html, file_path=file_path, mode=MODE)
            if not record.get("title"):
                record["title"] = original_title
            if not record.get("correction_families") and original_correction_families:
                record["correction_families"] = original_correction_families
            if not record.get("rcept_no") and original_rcept_no:
                record["rcept_no"] = original_rcept_no
            if original_acpt_no:
                record["acpt_no"] = original_acpt_no
            rows = _main_rights_rows(record["raw_tables"])
    rows = _non_correction_rows(record["raw_tables"]) if rows else []

    record.update(
        {
            "신주의 종류와 수": _stock_values(rows, "신주의 종류와 수"),
            "발행목적": _funding_purposes(rows),
            "발행가액": _stock_values(rows, "신주 발행가액"),
            "기준주가": _stock_values(rows, "기준주가"),
            "증자방식": _last_value(_row_containing(rows, "증자방식")),
            "납입일": _last_value(_row_with_label(rows, "납입일")),
            "신주권교부예정일": _last_value(_row_containing(rows, "신주권교부예정일")),
            "상장예정일": _last_value(_row_containing(rows, "신주의 상장 예정일")),
            "발행대상자": _issue_targets(record["raw_tables"]),
            "발행대상자세부엔티티": _issue_target_entities(record["raw_tables"]),
        }
    )
    return record


def _main_rights_rows(raw_tables: list[dict[str, Any]]) -> list[list[str]]:
    for table in _non_correction_tables(raw_tables):
        rows = table.get("logical_rows") or []
        if (
            any(_row_contains(row, "신주의 종류와 수") for row in rows)
            and any(_row_contains(row, "자금조달의 목적") for row in rows)
            and any(_row_contains(row, "증자방식") for row in rows)
        ):
            return rows
    return []


def _non_correction_tables(raw_tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [table for table in raw_tables if not _is_correction_chapter(table)]


def _non_correction_rows(raw_tables: list[dict[str, Any]]) -> list[list[str]]:
    return [
        row
        for table in _non_correction_tables(raw_tables)
        for row in table.get("logical_rows") or []
    ]


def _is_correction_chapter(table: dict[str, Any]) -> bool:
    chapter_title = clean_text(str(table.get("chapter_title") or "")).replace(" ", "")
    return "정정신고" in chapter_title


def _row_contains(row: list[str], *needles: str) -> bool:
    text = " ".join(row)
    compact_text = text.replace(" ", "")
    return all(needle in text or needle.replace(" ", "") in compact_text for needle in needles)


def _row_containing(rows: list[list[str]], *needles: str) -> list[str]:
    for row in rows:
        if _row_contains(row, *needles):
            return row
    return []


def _normalize_label(value: str) -> str:
    return re.sub(r"^\d+(?:-\d+)?\.\s*", "", clean_text(value))


def _row_with_label(rows: list[list[str]], label: str) -> list[str]:
    for row in rows:
        if any(_normalize_label(value) == label for value in row):
            return row
    return []


def _last_value(row: list[str]) -> str | None:
    return row[-1] if row else None


def _last_int(row: list[str]) -> int | None:
    for value in reversed(row):
        parsed = parse_int(value)
        if parsed is not None:
            return parsed
    return None


def _stock_values(rows: list[list[str]], section_label: str) -> list[list[Any]]:
    values: list[list[Any]] = []
    for stock_label in STOCK_LABELS:
        row = _row_containing(rows, section_label, stock_label)
        parsed = parse_int(_last_value(row), dash_as_zero=True)
        values.append([stock_label, 0 if parsed is None else parsed])
    return values


def _funding_purposes(rows: list[list[str]]) -> list[list[Any]]:
    purposes: list[list[Any]] = []
    for label in FUNDING_PURPOSE_LABELS:
        row = _row_containing(rows, "자금조달의 목적", label)
        value = parse_int(_last_value(row), dash_as_zero=True)
        purposes.append([label, 0 if value is None else value])
    return purposes


def _issue_targets(raw_tables: list[dict[str, Any]]) -> list[list[Any]]:
    for table in _non_correction_tables(raw_tables):
        rows = table.get("logical_rows") or []
        if not rows or not _row_contains(rows[0], "제3자배정 대상자", "배정주식수"):
            continue
        amount_index = _column_index(rows[0], "배정주식수")
        targets: list[list[Any]] = []
        for row in rows[1:]:
            if not row or row[0] == "-":
                continue
            amount = parse_int(row[amount_index]) if amount_index is not None and amount_index < len(row) else _last_int(row)
            if amount is not None:
                targets.append([row[0], amount])
        return targets
    return []


def _column_index(row: list[str], label: str) -> int | None:
    for index, value in enumerate(row):
        if label in value.replace(" ", ""):
            return index
    return None


def _issue_target_entities(raw_tables: list[dict[str, Any]]) -> list[list[str]]:
    entities: list[list[str]] = []
    for table in _non_correction_tables(raw_tables):
        rows = table.get("logical_rows") or []
        if len(rows) < 3 or not _row_contains(rows[0], "명칭", "대표이사", "최대주주"):
            continue
        grouped: dict[str, dict[str, list[str]]] = {}
        for row in rows[2:]:
            if len(row) < 3 or row[0] == "-":
                continue
            values = grouped.setdefault(row[0], {"representatives": [], "major_holders": []})
            representative = row[2]
            if representative != "-" and representative not in values["representatives"]:
                values["representatives"].append(representative)
            if len(row) >= 6:
                major_holder = row[-2]
                if major_holder != "-" and major_holder not in values["major_holders"]:
                    values["major_holders"].append(major_holder)
        for name, values in grouped.items():
            entities.append([name, *values["representatives"], *values["major_holders"]])
    return entities
