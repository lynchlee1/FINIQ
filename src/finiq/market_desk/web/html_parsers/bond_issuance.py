"""Parser entrypoint for debt security issuance disclosures."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import requests

from .common import build_base_record, clean_text, parse_float, parse_html_document, parse_int

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
    document_markup = html_text
    record = build_base_record(html_text, file_path=file_path, mode=MODE)
    rows = _main_bond_rows(record["raw_tables"])
    if not rows:
        body_html = _fetch_selected_viewer_body(html_text)
        if body_html is not None:
            document_markup = body_html
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
            rows = _main_bond_rows(record["raw_tables"])
    document_text = clean_text(" ".join(parse_html_document(document_markup).itertext()))
    is_bond_with_warrant = _is_bond_with_warrant(rows)

    record.update(
        {
            "회차": _value_after(_row_containing(rows, "사채의 종류"), "회차"),
            "발행금액": _last_int(_row_containing(rows, "사채의 권면")),
            "발행목적": _funding_purposes(rows),
            "표면이자율": _interest_rate(rows, "표면이자율"),
            "만기이자율": _interest_rate(rows, "만기이자율", "만기보장수익"),
            "만기일": _last_value(_row_containing(rows, "사채만기일")),
            "할증률(%)": None if is_bond_with_warrant else _premium_rate(document_text),
            "행사가액": _exercise_price(rows),
            "행사대상": _exercise_target(rows),
            "전환시작일": _exercise_period_value(rows, "시작일"),
            "전환종료일": _exercise_period_value(rows, "종료일"),
            "리픽싱(%)": _refixing_rate(rows, document_text),
            "청약일": _last_value(_row_with_label(rows, "청약일")),
            "납입일": _last_value(_row_with_label(rows, "납입일")),
            "납입방법": _payment_method(rows),
            "발행대상자": _issue_targets(record["raw_tables"]),
            "발행대상자세부엔티티": _issue_target_entities(record["raw_tables"]),
        }
    )
    return record


def _main_bond_rows(raw_tables: list[dict[str, Any]]) -> list[list[str]]:
    for table in raw_tables:
        if _is_correction_chapter(table):
            continue
        rows = table.get("logical_rows") or []
        if (
            any(_row_contains(row, "사채의 종류") for row in rows)
            and any(_row_contains(row, "사채의 권면") for row in rows)
            and any(_row_contains(row, "자금조달의 목적") for row in rows)
        ):
            return rows
    return []


def _non_correction_tables(raw_tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [table for table in raw_tables if not _is_correction_chapter(table)]


def _is_correction_chapter(table: dict[str, Any]) -> bool:
    chapter_title = clean_text(str(table.get("chapter_title") or "")).replace(" ", "")
    return "정정신고" in chapter_title


def _fetch_selected_viewer_body(html_text: str | bytes) -> bytes | None:
    document = parse_html_document(html_text)
    selected_values = document.xpath("//select[@id='mainDoc']/option[@selected or @selected='selected']/@value")
    if not selected_values:
        selected_values = document.xpath("//select[@name='mainDoc']/option[@selected or @selected='selected']/@value")
    if not selected_values:
        return None
    doc_no = str(selected_values[0]).split("|", 1)[0].strip()
    if not doc_no:
        return None
    contents_url = f"https://kind.krx.co.kr/common/disclsviewer.do?method=searchContents&docNo={doc_no}"
    contents_response = requests.get(contents_url, timeout=20)
    contents_response.raise_for_status()
    contents_html = contents_response.content
    contents_text = contents_html.decode("utf-8", errors="replace")
    match = re.search(r"parent\.setPath\('[^']*','([^']+)'", contents_text)
    if match is None:
        return None
    response = requests.get(match.group(1), timeout=20)
    response.raise_for_status()
    return response.content


def _row_contains(row: list[str], *needles: str) -> bool:
    text = " ".join(row)
    compact_text = text.replace(" ", "")
    return all(needle in text or needle.replace(" ", "") in compact_text for needle in needles)


def _row_containing(rows: list[list[str]], *needles: str) -> list[str]:
    for row in rows:
        if _row_contains(row, *needles):
            return row
    return []


def _is_bond_with_warrant(rows: list[list[str]]) -> bool:
    return _row_contains(_row_containing(rows, "사채의 종류"), "신주인수권")


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


def _exercise_period_value(rows: list[list[str]], boundary_label: str) -> str | None:
    for period_label in ("전환청구기간", "권리행사기간"):
        value = _last_value(_row_containing(rows, period_label, boundary_label))
        if value is not None:
            return value
    return None


def _exercise_price(rows: list[list[str]]) -> int | None:
    for price_label in ("전환가액 (원/주)", "행사가액 (원/주)"):
        value = _last_int(_row_containing(rows, price_label))
        if value is not None:
            return value
    return None


def _exercise_target(rows: list[list[str]]) -> str | None:
    for target_label in ("전환에 따라", "전환으로 발행할", "인수권행사에 따라"):
        value = _last_value(_row_containing(rows, target_label, "종류"))
        if value is not None:
            return value
    return None


def _payment_method(rows: list[list[str]]) -> str | None:
    for label in ("납입방법", "신주대금 납입방법"):
        value = _last_value(_row_with_label(rows, label))
        if value is not None:
            return value
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


def _refixing_rate(rows: list[list[str]], document_text: str) -> int | None:
    row = _row_containing(rows, "최저 조정가액 근거")
    text = " ".join(row)
    match = re.search(r"100분의\s*(\d+)", text)
    if match:
        return int(match.group(1))
    row = _row_containing(rows, "발행당시 전환가액의", "미만")
    text = " ".join(row)
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if match:
        return int(float(match.group(1)))
    return _refixing_rate_from_adjustment_text(document_text)


def _refixing_rate_from_adjustment_text(document_text: str) -> int | None:
    adjustment_index = -1
    for adjustment_label in ("행사가액 조정", "행사가액의 조정", "전환가액 조정", "전환가액의 조정", "전환가격 조정"):
        adjustment_index = document_text.find(adjustment_label)
        if adjustment_index != -1:
            break
    if adjustment_index == -1:
        return None
    adjustment_text = document_text[adjustment_index : adjustment_index + 2500]
    patterns = (
        r"최저조정가액비율\s*:\s*(\d+(?:\.\d+)?)\s*%",
        r"최저\s*조정한도.{0,160}?(\d+(?:\.\d+)?)\s*%",
        r"조정한도.{0,160}?(\d+(?:\.\d+)?)\s*%\s*이상",
        r"행사가액에\s*(\d+(?:\.\d+)?)\s*%\s*를\s*한도",
    )
    for pattern in patterns:
        match = re.search(pattern, adjustment_text)
        if match:
            return int(float(match.group(1)))
    return None


def _issue_targets(raw_tables: list[dict[str, Any]]) -> list[list[Any]]:
    for table in _non_correction_tables(raw_tables):
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


def _interest_rate(rows: list[list[str]], *labels: str) -> float | None:
    for label in labels:
        row = _row_containing(rows, label)
        if row:
            val = _last_value(row)
            res = parse_float(val)
            if res is not None:
                return res
    return None
