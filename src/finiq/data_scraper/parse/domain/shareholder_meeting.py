"""Shareholder-meeting disclosure parser."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from bs4 import Tag

from .._markup import parse_html_with_recovery
from ..metadata import extract_viewer_metadata
from .shareholder_meeting_semantics import extract_semantic_contract
from .shareholder_meeting_stakeholders import (
    extract_stakeholder_mentions,
    extract_transaction_mentions,
)


ELECTION_SECTION_TYPES = {
    "이사선임 세부내역": "director",
    "사외이사선임 세부내역": "outside_director",
    "감사선임 세부내역": "auditor",
    "감사위원선임 세부내역": "audit_committee_member",
}
_SECTION_TITLES = {*ELECTION_SECTION_TYPES, "사업목적 변경 세부내역"}

_PLACEHOLDER_NAME_RE = re.compile(
    r"^(?:-|성명|해당(?:사항)?없음|(?:후보자?)?(?:미정|미확정)|"
    r"(?:후보자?|선임)?예정(?:자)?)$"
)
_PLACEHOLDER_AGENDA_RE = re.compile(
    r"^(?:-|해당(?:사항)?없음|없음|미정|미확정|추후(?:결정|확정))$"
)
_CORRECTION_HEADERS = {"정정항목", "정정전", "정정후"}
_LEGACY_AGENDA_TOKEN_RE = re.compile(
    r"^\s*(?:"
    r"(?:(?:\(\s*\d+\s*\)|\d+\s*[.)]|[가-하]\s*[.)]|[①-⑳]|[*○●⊙ㅇ◆◇□■└·ㆍ-]\s*[.]?)\s*)*"
    r"[\[<【(]?\s*(?:(?:제\s*)?(?P<proposal>\d+(?:\s*[-－.]\s*\d+)*)\s*호(?:\s*의\s*안)?|"
    r"제\s*(?P<short_proposal>\d+(?:\s*[-－.]\s*\d+)*)\s*안|"
    r"안건\s*(?P<agenda_number>\d+(?:\s*[-－.]\s*\d+)*))"
    r"\s*[\]>】)]?\s*[:：.]?\s*(?P<explicit_title>.*)|"
    r"(?P<hierarchical>\d+(?:\s*[-－.]\s*\d+)+)\s*(?:[.)]\s*)?"
    r"(?P<hierarchical_title>.+)|"
    r"\(\s*(?P<parenthesized>\d+)\s*\)\s*(?P<parenthesized_title>.+)|"
    r"(?P<ordinal>\d+(?:\s*[-－.]\s*\d+)*)\s*[.)]\s*(?P<ordinal_title>.+)|"
    r"(?P<circled>[①-⑳])\s*(?P<circled_title>.+)|"
    r"(?P<letter>[가-하])\s*[.)]\s*(?P<letter_title>.+)|"
    r"(?P<bullet>[*○●⊙ㅇ◆◇□■└·ㆍ-])\s*(?P<bullet_title>.+)"
    r")$"
)
_CIRCLED_NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_LEGACY_REPORT_SECTIONS = {"보고사항", "보고안건", "보고의안"}
_LEGACY_AGENDA_SECTIONS = {
    "부의안건",
    "부의사항",
    "부의의안",
    "결의사항",
    "의결사항",
    "의결의안",
    "결의안건",
    "의결안건",
    "심의의안",
    "안건",
}
_LEGACY_CANDIDATE_RE = re.compile(
    r"(?:사내이사|사외이사|독립이사|기타\s*비상무이사|비상무이사|비상임이사|"
    r"감사위원|감사)\s*"
    r"(?P<name>[가-힣]{2,5}|[A-Za-z]+(?:\s+[A-Za-z]+){0,3})\s*"
    r"(?:신규\s*)?(?:선임|재선임)"
)
_INLINE_LEGACY_AGENDA_NUMBER_RE = re.compile(
    r"(?:제\s*)?\d+(?:\s*[-－.]\s*\d+)*\s*호(?:\s*의\s*안)?|"
    r"제\s*\d+(?:\s*[-－.]\s*\d+)*\s*안|"
    r"안건\s*\d+(?:\s*[-－.]\s*\d+)*\s*[:：]"
)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _compact(value: Any) -> str:
    return re.sub(r"[\s\[\]【】「」]", "", str(value or ""))


def _normalized_row_label(value: Any) -> str:
    label = _clean_text(value)
    label = re.sub(r"^\s*\d+\s*[.)]\s*", "", label)
    return re.sub(r"\s+", "", label)


def _cell_value(cell: Tag) -> dict[str, Any]:
    lines = [
        _clean_text(line)
        for line in cell.get_text("\n", strip=True).splitlines()
        if _clean_text(line)
    ]
    return {
        "text": _clean_text(cell.get_text(" ", strip=True)),
        "lines": lines,
        "colspan": max(int(cell.get("colspan", 1)), 1),
        "rowspan": max(int(cell.get("rowspan", 1)), 1),
    }


def _expanded_table(table: Tag) -> list[list[dict[str, Any] | None]]:
    """Expand spans while retaining each source cell's line boundaries."""
    rows = table.find_all("tr")
    if not rows:
        return []
    max_cols = max(
        (
            sum(max(int(cell.get("colspan", 1)), 1) for cell in row.find_all(["th", "td"]))
            for row in rows
        ),
        default=0,
    )
    if max_cols == 0:
        return []
    grid: list[list[dict[str, Any] | None]] = [
        [None for _ in range(max_cols)] for _ in rows
    ]
    for row_index, row in enumerate(rows):
        column_index = 0
        for cell in row.find_all(["th", "td"]):
            while column_index < max_cols and grid[row_index][column_index] is not None:
                column_index += 1
            if column_index >= max_cols:
                break
            value = _cell_value(cell)
            for row_offset in range(value["rowspan"]):
                for column_offset in range(value["colspan"]):
                    target_row = row_index + row_offset
                    target_column = column_index + column_offset
                    if target_row < len(grid) and target_column < max_cols:
                        grid[target_row][target_column] = value
            column_index += value["colspan"]
    return grid


def _row_texts(row: list[dict[str, Any] | None]) -> list[str]:
    return [str(cell.get("text") or "") if cell is not None else "" for cell in row]


def _table_index(soup: Any, table: Tag) -> int:
    for index, candidate in enumerate(soup.find_all("table")):
        if candidate is table:
            return index
    return -1


def _is_correction_table(table: Tag) -> bool:
    grid = _expanded_table(table)
    return any(
        _CORRECTION_HEADERS
        <= {_compact(text) for text in _row_texts(row) if _compact(text)}
        for row in grid
    )


def _inside_correction_table(tag: Tag) -> bool:
    return any(_is_correction_table(parent) for parent in tag.find_parents("table"))


def _correction_after_reference_sources(soup: Any) -> list[dict[str, Any]]:
    """Return authoritative reference-note cells from exact correction tables."""
    sources: list[dict[str, Any]] = []
    expected_headers = ["정정항목", "정정전", "정정후"]
    for table in soup.find_all("table"):
        table_index = _table_index(soup, table)
        direct_rows = [
            (row_index, row)
            for row_index, row in enumerate(table.find_all("tr"))
            if row.find_parent("table") is table
        ]
        header_position = next(
            (
                position
                for position, (_, row) in enumerate(direct_rows)
                if [
                    _clean_text(cell.get_text(" ", strip=True))
                    for cell in row.find_all(["th", "td"], recursive=False)
                ]
                == expected_headers
            ),
            None,
        )
        if header_position is None:
            continue
        for row_index, row in direct_rows[header_position + 1 :]:
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) != 3 or any(cell.find("table") is not None for cell in cells):
                continue
            if (
                _normalized_row_label(cells[0].get_text(" ", strip=True))
                != "기타투자판단에참고할사항"
            ):
                continue
            after = _cell_value(cells[2])
            text = str(after.get("text") or "")
            lines = [str(line) for line in after.get("lines", []) if str(line)]
            if not text or not lines:
                continue
            sources.append(
                {
                    "source_type": "correction_after_reference_note",
                    "text": text,
                    "lines": lines,
                    "evidence": {
                        "section_title": "정정사항",
                        "table_index": table_index,
                        "row_index": row_index,
                        "column_index": 2,
                        "field": "정정후",
                        "raw_text": text,
                    },
                }
            )
    return sources


def _heading_text(span: Tag) -> str:
    return _clean_text(span.get_text(" ", strip=True))


def _independent_section_table(
    soup: Any,
    section_title: str,
    *,
    required_headers: set[str],
) -> Tag | None:
    span = next(
        (
            candidate
            for candidate in soup.find_all("span")
            if _heading_text(candidate) == section_title
            and not _inside_correction_table(candidate)
        ),
        None,
    )
    if span is None or span.find_parent(["td", "th"]) is not None:
        return None
    table = span.find_next("table")
    if (
        not isinstance(table, Tag)
        or _inside_correction_table(table)
        or _is_correction_table(table)
    ):
        return None
    for between in span.next_elements:
        if between is table:
            break
        if (
            isinstance(between, Tag)
            and between.name == "span"
            and between.find_parent(["td", "th"]) is None
            and _heading_text(between) in _SECTION_TITLES
        ):
            return None
    grid = _expanded_table(table)
    if not grid:
        return None
    headers = {_compact(text) for text in _row_texts(grid[0])}
    return table if required_headers <= headers else None


def _unique_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique: list[str] = []
    canonical_headers = {
        "번호",
        "결의구분",
        "회의목적사항",
        "안건",
        "후보자",
        "가결여부",
        "비고",
        "성명",
        "출생년월",
        "임기",
        "신규선임여부",
        "상근여부",
        "사외이사여부",
        "주요경력(현직포함)",
        "이사등으로재직중인다른법인명(직위)",
        "구분",
        "내용",
        "이유",
    }
    canonical_by_compact = {_compact(header): header for header in canonical_headers}
    canonical_by_compact["이사등으로재직중인다른법인명(직위)"] = (
        "이사 등으로 재직 중인 다른 법인명(직위)"
    )
    for header in headers:
        header = canonical_by_compact.get(_compact(header), header) or "unknown"
        count = seen.get(header, 0)
        unique.append(header if count == 0 else f"{header}_{count}")
        seen[header] = count + 1
    return unique


def _table_records(table: Tag) -> list[tuple[int, dict[str, str], list[dict[str, Any] | None]]]:
    grid = _expanded_table(table)
    if not grid:
        return []
    headers = _unique_headers(_row_texts(grid[0]))
    records: list[tuple[int, dict[str, str], list[dict[str, Any] | None]]] = []
    for row_index, row in enumerate(grid[1:], start=1):
        values = _row_texts(row)
        if not any(values):
            continue
        records.append((row_index, dict(zip(headers, values)), row))
    return records


def _valid_person_name(value: str) -> tuple[str, str | None] | None:
    name = _clean_text(value)
    employment_mode = None
    mode_match = re.fullmatch(r"(?P<name>.+?)\s*\((?P<mode>상근|비상근)\)", name)
    if mode_match is not None:
        name = _clean_text(mode_match.group("name"))
        employment_mode = mode_match.group("mode")
    compact_name = _compact(name).casefold()
    if not compact_name or _PLACEHOLDER_NAME_RE.fullmatch(compact_name) is not None:
        return None
    return name, employment_mode


def _election_record(
    row: dict[str, str],
    *,
    source_row: list[dict[str, Any] | None],
    row_index: int,
    table_index: int,
    section_title: str,
    section_type: str,
) -> dict[str, Any] | None:
    parsed_name = _valid_person_name(row.get("성명", ""))
    if parsed_name is None:
        return None
    name, employment_mode = parsed_name
    headers = _unique_headers(list(row))
    major_career_header = "주요경력(현직포함)"
    major_career_column_index = (
        headers.index(major_career_header) if major_career_header in headers else -1
    )
    major_career_cell = (
        source_row[major_career_column_index]
        if 0 <= major_career_column_index < len(source_row)
        else None
    )
    major_career_lines = (
        [str(line) for line in major_career_cell.get("lines", [])]
        if major_career_cell is not None
        else []
    )
    other_header = "이사 등으로 재직 중인 다른 법인명(직위)"
    other_column_index = headers.index(other_header) if other_header in headers else -1
    other_cell = (
        source_row[other_column_index]
        if 0 <= other_column_index < len(source_row)
        else None
    )
    other_company_lines = (
        [str(line) for line in other_cell.get("lines", [])]
        if other_cell is not None
        else []
    )
    raw_text = " | ".join(value for value in _row_texts(source_row) if value)
    evidence = {
        "section_title": section_title,
        "table_index": table_index,
        "row_index": row_index,
        "field": "성명",
        "raw_text": raw_text,
    }
    record: dict[str, Any] = {
        "section_title": section_title,
        "section_type": section_type,
        **row,
        "name": name,
        "birth_month": row.get("출생년월", ""),
        "term": row.get("임기", ""),
        "is_new": row.get("신규선임여부", ""),
        "is_full_time": row.get("상근여부", ""),
        "major_career": row.get(major_career_header, ""),
        "major_career_lines": major_career_lines,
        "major_career_evidence": {
            **evidence,
            "field": major_career_header,
            "raw_text": "\n".join(major_career_lines)
            or row.get(major_career_header, ""),
        },
        "other_company": row.get(other_header, ""),
        "other_company_lines": other_company_lines,
        "other_company_evidence": {
            **evidence,
            "field": other_header,
            "raw_text": "\n".join(other_company_lines) or row.get(other_header, ""),
        },
        "evidence": evidence,
    }
    if employment_mode is not None:
        record["employment_mode"] = employment_mode
    return record


def _extract_elections(soup: Any) -> dict[str, list[dict[str, Any]]]:
    elections_by_type: dict[str, list[dict[str, Any]]] = {
        "director": [],
        "outside_director": [],
        "auditor": [],
        "audit_committee_member": [],
    }
    for section_title, section_type in ELECTION_SECTION_TYPES.items():
        table = _independent_section_table(
            soup,
            section_title,
            required_headers={"성명"},
        )
        if table is None:
            continue
        table_index = _table_index(soup, table)
        for row_index, row, source_row in _table_records(table):
            record = _election_record(
                row,
                source_row=source_row,
                row_index=row_index,
                table_index=table_index,
                section_title=section_title,
                section_type=section_type,
            )
            if record is not None:
                elections_by_type[section_type].append(record)
    return elections_by_type


def _effective_agenda_headers(
    grid: list[list[dict[str, Any] | None]],
) -> tuple[list[str], int, int] | None:
    if not grid:
        return None
    first = _row_texts(grid[0])
    compact_first = {_compact(value) for value in first}
    if not {"번호", "회의목적사항"} <= compact_first:
        return None
    has_grouped_header = any(
        cell is not None and (cell["rowspan"] > 1 or cell["colspan"] > 1)
        for cell in grid[0]
    )
    if has_grouped_header and len(grid) > 1:
        second = _row_texts(grid[1])
        headers = [
            second[index]
            if second[index] and _compact(second[index]) != _compact(first[index])
            else first[index]
            for index in range(len(first))
        ]
        unique_headers = _unique_headers(headers)
        title_index = (
            unique_headers.index("안건")
            if "안건" in unique_headers
            else next(
                index
                for index, value in enumerate(first)
                if _compact(value) == "회의목적사항"
            )
        )
        return unique_headers, 2, title_index
    unique_headers = _unique_headers(first)
    return unique_headers, 1, unique_headers.index("회의목적사항")


def _normalized_status(result_raw: str, remarks: str = "") -> str | None:
    result_text = _compact(result_raw)
    combined_text = _compact(f"{result_raw} {remarks}")
    if re.search(r"(?:안건|의안)(?:을|를)?철회", combined_text):
        return "withdrawn"
    if re.search(
        r"불상정|미상정|자동폐기|(?:안건|의안)(?:을|를)?폐기",
        combined_text,
    ):
        return "not_tabled"
    if re.search(r"부결|미가결|가결(?:되지|되지않|안됨|아니)", result_text):
        return "rejected"
    if re.search(r"(?:원안(?:대로)?\s*)?가결(?:됨)?$|원안(?:대로)?승인(?:됨)?$|승인(?:됨|되었음)$", result_text):
        return "passed"
    if "미결" in result_text:
        return "unresolved"
    return None


def _structured_agenda_records(
    soup: Any,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    for table in soup.find_all("table"):
        if _inside_correction_table(table) or _is_correction_table(table):
            continue
        grid = _expanded_table(table)
        parsed_headers = _effective_agenda_headers(grid)
        if parsed_headers is None:
            continue
        headers, data_start, agenda_title_index = parsed_headers
        table_index = _table_index(soup, table)
        records: list[dict[str, Any]] = []
        for row_index, row in enumerate(grid[data_start:], start=data_start):
            values = _row_texts(row)
            row_dict = dict(zip(headers, values))
            number = _clean_text(row_dict.get("번호"))
            title = _clean_text(values[agenda_title_index])
            if (
                not number
                or _compact(number) in {"번호", "찬성률"}
                or not title
                or _PLACEHOLDER_AGENDA_RE.fullmatch(_compact(title)) is not None
            ):
                continue
            candidate = _clean_text(row_dict.get("후보자"))
            if "후보자" in headers:
                candidate_cell = row[headers.index("후보자")]
                if candidate_cell is not None:
                    candidate_lines = [
                        _clean_text(line)
                        for line in candidate_cell.get("lines", [])
                        if _clean_text(line)
                    ]
                    if len(candidate_lines) > 1:
                        candidate = ", ".join(dict.fromkeys(candidate_lines))
            result_raw = _clean_text(row_dict.get("가결여부"))
            remarks = _clean_text(row_dict.get("비고"))
            attributes = {
                key: value
                for key, value in row_dict.items()
                if value
                and key
                not in {
                    "번호",
                    "안건",
                    "회의목적사항",
                    "회의목적사항_1",
                    "결의구분",
                    "후보자",
                    "가결여부",
                    "비고",
                }
            }
            raw_text = " | ".join(value for value in values if value)
            is_result_table = "가결여부" in headers
            records.append(
                {
                    "agenda_ref": f"agenda:{len(records)}",
                    "number": number,
                    "title": title,
                    "resolution_type": _clean_text(row_dict.get("결의구분")) or None,
                    "candidate": candidate or None,
                    "result_raw": result_raw or None,
                    "status": _normalized_status(result_raw, remarks) if is_result_table else None,
                    "remarks": remarks or None,
                    "source": "structured_agenda_table",
                    "attributes": attributes,
                    "evidence": {
                        "section_title": "주주총회 안건 세부내역",
                        "table_index": table_index,
                        "row_index": row_index,
                        "field": "회의목적사항",
                        "raw_text": raw_text,
                    },
                }
            )
        phase = "result" if "가결여부" in headers else "notice"
        return records, phase, True
    return [], None, False


def _legacy_agenda_lines(cell: Tag) -> list[str]:
    physical_lines = [
        _clean_text(line)
        for line in cell.get_text("\n", strip=True).splitlines()
        if _clean_text(line) and _clean_text(line) != "-"
    ]
    return [
        segment
        for line in physical_lines
        for segment in _split_inline_legacy_agendas(line)
    ]


def _legacy_section_kind(line: str) -> str | None:
    section = _compact(line).strip("<>(){}:：")
    section = re.sub(
        r"^(?:\(\s*\d+\s*\)|\d+\s*[.)]|[가-하]\s*[.)]|[-※])",
        "",
        section,
    ).strip("<>(){}:：")
    if section in _LEGACY_REPORT_SECTIONS:
        return "report"
    if section in _LEGACY_AGENDA_SECTIONS:
        return "agenda"
    return None


def _normalized_agenda_number(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("－", "-").replace(".", "-")


def _legacy_agenda_start(
    line: str,
    *,
    agenda_section_active: bool,
) -> tuple[str | None, str] | None:
    match = _LEGACY_AGENDA_TOKEN_RE.match(line)
    if match is None:
        return None

    explicit_number = next(
        (
            match.group(group)
            for group in ("proposal", "short_proposal", "agenda_number")
            if match.group(group)
        ),
        None,
    )
    if explicit_number is not None:
        return (
            _normalized_agenda_number(explicit_number),
            _clean_text(match.group("explicit_title")),
        )

    if not agenda_section_active:
        return None
    if match.group("hierarchical"):
        return (
            _normalized_agenda_number(match.group("hierarchical")),
            _clean_text(match.group("hierarchical_title")),
        )
    if match.group("parenthesized"):
        return (
            _normalized_agenda_number(match.group("parenthesized")),
            _clean_text(match.group("parenthesized_title")),
        )
    if match.group("ordinal"):
        return (
            _normalized_agenda_number(match.group("ordinal")),
            _clean_text(match.group("ordinal_title")),
        )
    if match.group("circled"):
        return (
            str(_CIRCLED_NUMBERS.index(match.group("circled")) + 1),
            _clean_text(match.group("circled_title")),
        )
    if match.group("letter"):
        return match.group("letter"), _clean_text(match.group("letter_title"))

    bullet_title = _clean_text(match.group("bullet_title"))
    if re.search(r"의\s*건|승인|선임|변경", bullet_title) is None:
        return None
    return None, bullet_title


def _agenda_number_parts(number: str | None) -> tuple[int, ...] | None:
    if not number or re.fullmatch(r"\d+(?:-\d+)*", number) is None:
        return None
    return tuple(int(part) for part in number.split("-"))


def _agenda_number_follows(current: str | None, following: str | None) -> bool:
    current_parts = _agenda_number_parts(current)
    following_parts = _agenda_number_parts(following)
    if current_parts is None or following_parts is None:
        return False
    if (
        len(following_parts) > len(current_parts)
        and following_parts[: len(current_parts)] == current_parts
    ):
        return True
    if following_parts[0] > current_parts[0]:
        return True
    return (
        len(following_parts) == len(current_parts)
        and following_parts[:-1] == current_parts[:-1]
        and following_parts[-1] > current_parts[-1]
    )


def _split_inline_legacy_agendas(line: str) -> list[str]:
    marker_starts: list[int] = []
    for match in _INLINE_LEGACY_AGENDA_NUMBER_RE.finditer(line):
        start = match.start()
        while start > 0 and line[start - 1] in " \t[<【(*○●⊙ㅇ◆◇□■└·ㆍ-.":
            start -= 1
        if start not in marker_starts:
            marker_starts.append(start)
    if len(marker_starts) < 2:
        return [line]

    first = _legacy_agenda_start(line[marker_starts[0] :], agenda_section_active=True)
    if first is None:
        return [line]
    current_number = first[0]
    segment_start = 0
    segments: list[str] = []
    for marker_start in marker_starts[1:]:
        agenda_start = _legacy_agenda_start(
            line[marker_start:],
            agenda_section_active=True,
        )
        if agenda_start is None or not _agenda_number_follows(
            current_number,
            agenda_start[0],
        ):
            continue
        segment = _clean_text(line[segment_start:marker_start])
        if segment:
            segments.append(segment)
        segment_start = marker_start
        current_number = agenda_start[0]
    tail = _clean_text(line[segment_start:])
    if tail:
        segments.append(tail)
    return segments or [line]


def _is_legacy_outcome_line(line: str) -> bool:
    return _normalized_status(line) is not None or re.match(
        r"^\s*(?:→|⇒|=>|->)", line
    ) is not None


def _is_child_agenda(parent_number: str | None, child_number: str | None) -> bool:
    return bool(
        parent_number
        and child_number
        and child_number.startswith(f"{parent_number}-")
    )


def _legacy_candidate(title: str) -> str | None:
    match = _LEGACY_CANDIDATE_RE.search(title)
    return _clean_text(match.group("name")) if match is not None else None


def _split_legacy_inline_outcome(title: str) -> tuple[str, str | None]:
    match = re.match(
        r"^(?P<title>.*?)(?:"
        r"(?:→|⇒|=>|->)\s*(?P<arrow>.+)|"
        r"\(\s*(?P<parenthesized>[^()]*)\s*\)|"
        r"\s+-\s+(?P<hyphenated>.+)"
        r")\s*$",
        title,
    )
    if match is None:
        return title, None
    result = next(
        (
            _clean_text(match.group(group))
            for group in ("arrow", "parenthesized", "hyphenated")
            if match.group(group)
        ),
        "",
    )
    if match.group("arrow") is None and _normalized_status(result) is None:
        return title, None
    return _clean_text(match.group("title")), result


def _legacy_agenda_records(soup: Any, phase: str) -> list[dict[str, Any]]:
    if phase not in {"notice", "result"}:
        return []
    preferred_labels = (
        {"결의사항", "기타결의사항"}
        if phase == "result"
        else {"의안주요내용", "결의사항"}
    )
    for table in soup.find_all("table"):
        if _inside_correction_table(table) or _is_correction_table(table):
            continue
        table_index = _table_index(soup, table)
        for row_index, tr in enumerate(table.find_all("tr")):
            if tr.find_parent("table") is not table:
                continue
            cells = tr.find_all(["th", "td"], recursive=False)
            if not cells:
                continue
            label = _normalized_row_label(cells[0].get_text(" ", strip=True))
            if label not in preferred_labels:
                continue
            if len(cells) != 2:
                return []
            lines = _legacy_agenda_lines(cells[1])
            agenda_section_active = True
            records: list[dict[str, Any]] = []
            current_raw_lines: list[str] = []
            current_title_lines: list[str] = []
            current_result_lines: list[str] = []
            current_number: str | None = None

            def flush() -> None:
                if not current_raw_lines or not any(current_title_lines):
                    return
                raw_text = " ".join(current_raw_lines)
                title_text = " ".join(current_title_lines)
                result_text = (
                    " ".join(current_result_lines) if phase == "result" else ""
                )
                records.append(
                    {
                        "agenda_ref": f"agenda:{len(records)}",
                        "number": current_number,
                        "title": raw_text,
                        "resolution_type": None,
                        "candidate": _legacy_candidate(title_text),
                        "result_raw": result_text or None,
                        "status": _normalized_status(result_text),
                        "remarks": None,
                        "source": "legacy_labeled_cell",
                        "attributes": {},
                        "evidence": {
                            "section_title": cells[0].get_text(" ", strip=True),
                            "table_index": table_index,
                            "row_index": row_index,
                            "field": label,
                            "raw_text": raw_text,
                        },
                    }
                )

            for line in lines:
                section_kind = _legacy_section_kind(line)
                if section_kind is not None:
                    flush()
                    current_raw_lines = []
                    current_title_lines = []
                    current_result_lines = []
                    current_number = None
                    agenda_section_active = section_kind == "agenda"
                    continue

                agenda_start = _legacy_agenda_start(
                    line,
                    agenda_section_active=agenda_section_active,
                )
                if agenda_start is not None:
                    new_number, new_title = agenda_start
                    if not (
                        _is_child_agenda(current_number, new_number)
                        and not current_result_lines
                    ):
                        flush()
                    current_number = new_number
                    current_raw_lines = [line]
                    current_title_lines = []
                    current_result_lines = []
                    title_text, inline_result = _split_legacy_inline_outcome(
                        new_title
                    )
                    if title_text:
                        current_title_lines.append(title_text)
                    if phase == "result" and inline_result:
                        current_result_lines.append(inline_result)
                elif (
                    phase == "result"
                    and current_raw_lines
                    and current_title_lines
                    and _is_legacy_outcome_line(line)
                ):
                    current_raw_lines.append(line)
                    current_result_lines.append(line)
                elif current_raw_lines:
                    current_raw_lines.append(line)
                    if phase == "result" and current_result_lines:
                        current_result_lines.append(line)
                    else:
                        title_text, inline_result = _split_legacy_inline_outcome(line)
                        if title_text:
                            current_title_lines.append(title_text)
                        if phase == "result" and inline_result:
                            current_result_lines.append(inline_result)
            flush()
            return records
    return []


def _resolve_phase(*, mode: str | None) -> str:
    normalized_mode = _compact(mode).upper()
    if normalized_mode in {"NOTICE", "RESULT"}:
        return normalized_mode.lower()
    return "unknown"


def shareholder_meeting_mode_from_title(title: str | None) -> str | None:
    normalized_title = _compact(title)
    if "주주총회결과" in normalized_title:
        return "RESULT"
    if "주주총회소집결의" in normalized_title or "주주총회소집공고" in normalized_title:
        return "NOTICE"
    return None


def _meeting_date(soup: Any, phase: str) -> str | None:
    if phase not in {"notice", "result"}:
        return None
    result_labels = {"주주총회일자", "주주총회일자(시간)"}
    notice_labels = {"일시", "주주총회예정일", "주주총회예정일자"}
    labels = result_labels if phase == "result" else notice_labels
    for table in soup.find_all("table"):
        if _inside_correction_table(table) or _is_correction_table(table):
            continue
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"], recursive=False)
            if not cells:
                continue
            label = _normalized_row_label(cells[0].get_text(" ", strip=True))
            if label not in labels:
                continue
            if len(cells) < 2:
                return None
            value = " ".join(
                _clean_text(cell.get_text(" ", strip=True)) for cell in cells[1:]
            )
            match = re.search(
                r"(?P<year>(?:19|20)\d{2})\s*[년./-]\s*"
                r"(?P<month>\d{1,2})\s*[월./-]\s*(?P<day>\d{1,2})\s*일?",
                value,
            )
            if match is not None:
                try:
                    return date(
                        int(match.group("year")),
                        int(match.group("month")),
                        int(match.group("day")),
                    ).isoformat()
                except ValueError:
                    return None
            return None
    return None


def _business_purpose_change_record(
    row: dict[str, str],
    *,
    evidence: dict[str, Any],
) -> dict[str, Any] | None:
    category = row.get("구분", "")
    content = row.get("내용", "")
    content_after = row.get("내용_1", "")
    reason = row.get("이유", "")
    if not category or content in {"변경전", "내용"}:
        return None
    record: dict[str, Any] = {
        "category": category,
        "reason": reason,
        "evidence": evidence,
    }
    if category == "사업목적 변경":
        record["before"] = content
        record["after"] = content_after
    else:
        record["content"] = content
    return record


def _extract_business_purpose_changes(soup: Any) -> list[dict[str, Any]]:
    table = _independent_section_table(
        soup,
        "사업목적 변경 세부내역",
        required_headers={"구분", "내용"},
    )
    if table is None:
        return []
    changes = []
    table_index = _table_index(soup, table)
    for row_index, row, _ in _table_records(table):
        reason = _clean_text(row.get("이유"))
        record = _business_purpose_change_record(
            row,
            evidence={
                "section_title": "사업목적 변경 세부내역",
                "table_index": table_index,
                "row_index": row_index,
                "field": "이유",
                "raw_text": reason,
            },
        )
        if record is not None:
            changes.append(record)
    return changes


def extract_shareholder_meeting_details(
    internal_html: str | bytes,
    *,
    mode: str | None = None,
    reporting_company_name: str | None = None,
) -> dict[str, Any]:
    soup = parse_html_with_recovery(internal_html)
    agenda_records, _structured_phase, structured_schema_matched = (
        _structured_agenda_records(soup)
    )
    disclosure_phase = _resolve_phase(mode=mode)
    if not structured_schema_matched:
        agenda_records = _legacy_agenda_records(soup, disclosure_phase)

    elections_by_type = _extract_elections(soup)
    elections = [
        *elections_by_type["director"],
        *elections_by_type["outside_director"],
        *elections_by_type["auditor"],
        *elections_by_type["audit_committee_member"],
    ]
    business_purpose_changes = _extract_business_purpose_changes(soup)
    correction_sources = _correction_after_reference_sources(soup)
    explicit_mentions = extract_stakeholder_mentions(soup)
    explicit_mentions.extend(
        extract_transaction_mentions(
            soup,
            agenda_records,
            business_purpose_changes,
            disclosure_phase,
            reporting_company_name=reporting_company_name,
        )
    )
    entities, relationships = extract_semantic_contract(
        agenda_records=agenda_records,
        elections=elections,
        disclosure_phase=disclosure_phase,
        explicit_mentions=explicit_mentions,
        correction_sources=correction_sources,
        reporting_company_name=reporting_company_name,
    )
    agendas = [str(record["title"]) for record in agenda_records]
    return {
        "disclosure_phase": disclosure_phase,
        "meeting_date": _meeting_date(soup, disclosure_phase),
        "agendas": agendas,
        "agenda_items": agendas,
        "agenda_records": agenda_records,
        "elections": elections,
        "director_elections": elections_by_type["director"],
        "outside_director_elections": elections_by_type["outside_director"],
        "auditor_elections": elections_by_type["auditor"],
        "audit_committee_elections": elections_by_type["audit_committee_member"],
        "entities": entities,
        "relationships": relationships,
        "business_purpose_changes": business_purpose_changes,
    }


def parse_shareholder_meeting(external_html: str | bytes, internal_html: str | bytes) -> dict[str, Any]:
    """Combine viewer metadata with shareholder-meeting document details."""
    metadata = extract_viewer_metadata(external_html)
    title = str(metadata.get("title") or "")
    mode = shareholder_meeting_mode_from_title(title)
    if mode is None:
        raise ValueError(f"Unexpected shareholder meeting disclosure type in title: {title}")
    details = extract_shareholder_meeting_details(
        internal_html,
        mode=mode,
        reporting_company_name=str(metadata.get("company_name") or ""),
    )
    return {"metadata": metadata, "mode": mode, **details}
