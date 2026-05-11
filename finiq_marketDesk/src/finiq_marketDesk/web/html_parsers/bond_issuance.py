"""Parser entrypoint for debt security issuance disclosures."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .common import build_base_record, clean_text, parse_html_document, parse_int

MODE = "bond_issuance"
FUNDING_PURPOSE_LABELS = [
    "시설자금",
    "영업양수자금",
    "운영자금",
    "채무상환자금",
    "타법인 증권 취득자금",
    "기타자금",
]


def parse_bond_issuance(html_text: str | bytes, *, file_path: str | Path) -> dict[str, Any]:
    """Parse debt issuance HTML into the shared v1 architecture record."""
    record = build_base_record(html_text, file_path=file_path, mode=MODE)
    rows = _main_bond_rows(record["raw_tables"])
    document_text = clean_text(" ".join(parse_html_document(html_text).itertext()))

    record.update(
        {
            "회차": _value_after(_row_containing(rows, "사채의 종류"), "회차"),
            "발행금액": _last_int(_row_containing(rows, "사채의 권면")),
            "발행목적": _funding_purposes(rows),
            "만기일": _last_value(_row_containing(rows, "사채만기일")),
            "할증률(%)": _premium_rate(document_text),
            "행사가액": _last_int(_row_containing(rows, "전환가액 (원/주)")),
            "행사대상": _last_value(_row_containing(rows, "전환에 따라", "종류")),
            "전환시작일": _last_value(_row_containing(rows, "전환청구기간", "시작일")),
            "전환종료일": _last_value(_row_containing(rows, "전환청구기간", "종료일")),
            "리픽싱(%)": _refixing_rate(rows),
            "청약일": _last_value(_row_with_label(rows, "청약일")),
            "납입일": _last_value(_row_with_label(rows, "납입일")),
            "납입방법": _last_value(_row_with_label(rows, "납입방법")),
            "발행대상자": _issue_targets(record["raw_tables"]),
            "발행대상자세부엔티티": _issue_target_entities(record["raw_tables"]),
        }
    )
    return record


def _main_bond_rows(raw_tables: list[dict[str, Any]]) -> list[list[str]]:
    for table in raw_tables:
        rows = table.get("logical_rows") or []
        if any(_row_contains(row, "사채의 종류") for row in rows):
            return rows
    return []


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


def _value_after(row: list[str], label: str) -> str | None:
    for index, value in enumerate(row):
        if value == label and index + 1 < len(row):
            return row[index + 1]
    return None


def _last_value(row: list[str]) -> str | None:
    return row[-1] if row else None


def _last_int(row: list[str]) -> int | None:
    for value in reversed(row):
        parsed = parse_int(value)
        if parsed is not None:
            return parsed
    return None


def _funding_purposes(rows: list[list[str]]) -> list[list[Any]]:
    purposes: list[list[Any]] = []
    for label in FUNDING_PURPOSE_LABELS:
        row = _row_containing(rows, "자금조달의 목적", label)
        value = parse_int(_last_value(row), dash_as_zero=True)
        purposes.append([label, 0 if value is None else value])
    return purposes


def _premium_rate(document_text: str) -> float | None:
    for match in re.finditer(r"\[?(\d+(?:\.\d+)?)\]?\s*%", document_text):
        value = float(match.group(1))
        if value > 100:
            return round(value - 100, 3)
    return None


def _refixing_rate(rows: list[list[str]]) -> int | None:
    row = _row_containing(rows, "최저 조정가액 근거")
    text = " ".join(row)
    match = re.search(r"100분의\s*(\d+)", text)
    if match:
        return int(match.group(1))
    row = _row_containing(rows, "발행당시 전환가액의", "미만")
    text = " ".join(row)
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    return int(float(match.group(1))) if match else None


def _issue_targets(raw_tables: list[dict[str, Any]]) -> list[list[Any]]:
    for table in raw_tables:
        rows = table.get("logical_rows") or []
        if not rows or not _row_contains(rows[0], "발행 대상자명", "발행권면"):
            continue
        targets: list[list[Any]] = []
        for row in rows[1:]:
            if not row or row[0] == "-":
                continue
            amount = _last_int(row)
            if amount is not None:
                targets.append([row[0], amount])
        return targets
    return []


def _issue_target_entities(raw_tables: list[dict[str, Any]]) -> list[list[str]]:
    entities: list[list[str]] = []
    for table in raw_tables:
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
