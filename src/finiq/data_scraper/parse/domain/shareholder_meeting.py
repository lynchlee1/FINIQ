"""Shareholder meeting disclosure parser."""

from __future__ import annotations

import re
from typing import Any

from bs4 import Tag

from .._markup import parse_html_with_recovery
from ..metadata import extract_viewer_metadata
from ..table_dict import parse_table_to_dicts


ELECTION_SECTION_TYPES = {
    "이사선임 세부내역": "director",
    "사외이사선임 세부내역": "outside_director",
    "감사선임 세부내역": "auditor",
}


def _clean_agenda_text(text: str) -> list[str]:
    """텍스트에서 공백과 줄바꿈을 정리하고 안건 목록을 추출한다."""
    lines = text.split('\n')
    cleaned_lines = []
    
    # 안건의 시작을 나타내는 패턴 (예: 제1호, ·안건, -제1호, 가., [부의안건] 등)
    agenda_markers = re.compile(r'^(제\s*\d+[\-\d]*\s*호|·?\s*안건|\-?\s*제\s*\d|가\.|나\.|\[|<)')
    
    for line in lines:
        cleaned_line = line.strip()
        cleaned_line = cleaned_line.replace('\xa0', ' ').replace('&nbsp;', ' ')
        cleaned_line = re.sub(r'\s+', ' ', cleaned_line).strip()
        
        if not cleaned_line or cleaned_line == '-':
            continue
            
        if not cleaned_lines or agenda_markers.match(cleaned_line):
            cleaned_lines.append(cleaned_line)
        else:
            cleaned_lines[-1] += ' ' + cleaned_line
            
    return cleaned_lines


def _section_table(soup: Any, section_title: str) -> Tag | None:
    for span in soup.find_all("span"):
        title = re.sub(r"\s+", " ", span.get_text(" ", strip=True)).strip()
        if title == section_title:
            table = span.find_next("table")
            return table if isinstance(table, Tag) else None
    return None


def _election_record(row: dict[str, str], *, section_title: str, section_type: str) -> dict[str, str]:
    record = {
        "section_title": section_title,
        "section_type": section_type,
        **row,
        "name": row.get("성명", ""),
        "birth_month": row.get("출생년월", ""),
        "term": row.get("임기", ""),
        "is_new": row.get("신규선임여부", ""),
        "is_full_time": row.get("상근여부", ""),
        "major_career": row.get("주요경력(현직포함)", ""),
        "other_company": row.get("이사 등으로 재직 중인 다른 법인명(직위)", ""),
    }
    return record


def _extract_elections(soup: Any) -> dict[str, list[dict[str, str]]]:
    elections_by_type: dict[str, list[dict[str, str]]] = {
        "director": [],
        "outside_director": [],
        "auditor": [],
    }

    for section_title, section_type in ELECTION_SECTION_TYPES.items():
        table = _section_table(soup, section_title)
        if table is None:
            continue
        for row in parse_table_to_dicts(table):
            name = row.get("성명", "")
            if not name or name == "-":
                continue
            elections_by_type[section_type].append(
                _election_record(row, section_title=section_title, section_type=section_type)
            )

    return elections_by_type


def _business_purpose_change_record(row: dict[str, str]) -> dict[str, str] | None:
    category = row.get("구분", "")
    content = row.get("내용", "")
    content_after = row.get("내용_1", "")
    reason = row.get("이유", "")

    if not category or content in {"변경전", "내용"}:
        return None

    record = {
        "category": category,
        "reason": reason,
    }
    if category == "사업목적 변경":
        record["before"] = content
        record["after"] = content_after
    else:
        record["content"] = content
    return record


def _extract_business_purpose_changes(soup: Any) -> list[dict[str, str]]:
    table = _section_table(soup, "사업목적 변경 세부내역")
    if table is None:
        return []

    changes = []
    for row in parse_table_to_dicts(table):
        record = _business_purpose_change_record(row)
        if record is not None:
            changes.append(record)
    return changes


def extract_shareholder_meeting_details(
    internal_html: str | bytes,
    *,
    mode: str | None = None,
) -> dict[str, Any]:
    soup = parse_html_with_recovery(internal_html)

    agendas = []
    tds = soup.find_all("td")
    for i, td in enumerate(tds):
        text = td.get_text(strip=True)
        is_result_agenda = (mode in {None, "RESULT"}) and "1. 결의사항" in text
        is_notice_agenda = (mode in {None, "NOTICE"}) and (
            "3. 의안 주요내용" in text or "결의사항" in text
        )
        if (is_result_agenda or is_notice_agenda) and i + 1 < len(tds):
            raw_text = tds[i+1].get_text(separator='\n')
            agendas = _clean_agenda_text(raw_text)
            break

    elections_by_type = _extract_elections(soup)
    elections = [
        *elections_by_type["director"],
        *elections_by_type["outside_director"],
        *elections_by_type["auditor"],
    ]

    return {
        "agendas": agendas,
        "agenda_items": agendas,
        "elections": elections,
        "director_elections": elections_by_type["director"],
        "outside_director_elections": elections_by_type["outside_director"],
        "auditor_elections": elections_by_type["auditor"],
        "business_purpose_changes": _extract_business_purpose_changes(soup),
    }


def parse_shareholder_meeting(external_html: str | bytes, internal_html: str | bytes) -> dict[str, Any]:
    """외부 메타데이터와 내부 HTML의 테이블 정보를 결합하여 주주총회 정보를 추출한다."""
    
    # 1. 메타데이터 추출
    metadata = extract_viewer_metadata(external_html)
    
    # 2. 공시 종류 식별 (모드 설정)
    title = metadata.get("title", "") or ""
    # Remove spaces for easier keyword matching
    clean_title = title.replace(" ", "")
    if "주주총회소집결의" in clean_title or "주주총회소집공고" in clean_title:
        mode = "NOTICE"
    elif "주주총회결과" in clean_title:
        mode = "RESULT"
    else:
        raise ValueError(f"Unexpected shareholder meeting disclosure type in title: {title}")
    
    details = extract_shareholder_meeting_details(internal_html, mode=mode)
                    
    return {
        "metadata": metadata,
        "mode": mode,
        **details,
    }
