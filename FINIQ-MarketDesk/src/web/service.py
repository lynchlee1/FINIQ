"""Data services for the custom KIND web UI."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import re
from typing import Any, Callable

import pandas as pd
from lxml import etree, html

from analytics.chart import (
    aggregate_price_dataframe,
    apply_insight_range,
    prepare_disclosure_dataframe,
    prepare_disclosure_points,
    prepare_price_dataframe,
)
from analytics.company import (
    build_company_list_xlsx,
    extract_unique_company_list_rows,
    fetch_stock_price_history,
    infer_stock_code,
)
from analytics.disclosure_groups import (
    DEFAULT_DISCLOSURE_GROUP_RULES,
    DISCLOSURE_GROUP_OTHER,
    DISCLOSURE_GROUP_OTHER_COLOR,
    classify_disclosure_group,
    disclosure_group_color_map,
    disclosure_group_marker_style,
)
from analytics.quanti import fetch_quanti_ohlcv
from data.facade import (
    find_company_classification_files,
    load_company_classification_company_file,
    load_company_classification_file,
    load_company_classification_index_file,
)

def _resolve_workspace_default_path(*relative_parts: str) -> str:
    candidates = [
        Path.cwd(),
        Path.cwd().parent,
        Path(__file__).resolve().parents[3],
        Path(__file__).resolve().parents[2],
    ]
    checked: set[Path] = set()
    for base in candidates:
        if base in checked:
            continue
        checked.add(base)
        candidate = (base / Path(*relative_parts)).resolve()
        if candidate.exists():
            return str(candidate)
    return str((Path.cwd() / Path(*relative_parts)).resolve())


DEFAULT_OUTPUT_ROOT = _resolve_workspace_default_path("resources", "kind")
DEFAULT_QUANTI_DIR = _resolve_workspace_default_path("resources", "database", "by_item")
PRICE_SOURCE_FDR = "fdr"
PRICE_SOURCE_QUANTI = "quanti"
PRICE_SOURCE_LABELS = {
    PRICE_SOURCE_FDR: "FinanceDataReader (일봉)",
    PRICE_SOURCE_QUANTI: "Quanti_unified (수정 OHLCV + VWAP)",
}
INSIGHT_RANGE_OPTIONS = ("검색기간", "1개월", "3개월", "6개월", "1년", "전체")
DISPLAY_FREQUENCY_OPTIONS = ("자동", "일봉", "주봉", "월봉")
KIND_UI_DATE_MIN = date(1990, 1, 1)
MARKER_PLACEMENT = "candle_below"
DISCLOSURE_FILTER_LIMIT_MAX = 10000
_RESULT_PAGE_NUMBER_RE = re.compile(r"_post_page_(?P<page>\d+)\.body$")
_COMPANYSUMMARY_OPEN_RE = re.compile(
    r"companysummary_open\(\s*['\"](?P<company_id>[^'\"]*)['\"]\s*\)"
)
_OPEN_DISCLS_VIEWER_RE = re.compile(
    r"openDisclsViewer\(\s*['\"](?P<acpt_no>[^'\"]*)['\"]\s*,\s*['\"](?P<doc_no>[^'\"]*)['\"]\s*\)"
)


def _company_key(company: dict[str, Any]) -> str:
    return str(company.get("company_key") or company.get("company_id") or company.get("company_name") or "").strip()


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _result_page_number(path: str | Path) -> int:
    match = _RESULT_PAGE_NUMBER_RE.search(Path(path).name)
    if match is None:
        return -1
    return int(match.group("page"))


def _company_disclosure_count(company: dict[str, Any]) -> int:
    disclosure_count = company.get("disclosure_count")
    if disclosure_count is not None:
        return int(disclosure_count)
    return len(company.get("disclosures") or [])


def _classification_option_label(path: Path) -> str:
    parent_name = path.parent.name
    if parent_name == "kind":
        return path.name
    return f"{parent_name} / {path.name}"


def _resolve_display_frequency(option_label: str, candle_count: int) -> str:
    if option_label == "일봉":
        return "day"
    if option_label == "주봉":
        return "week"
    if option_label == "월봉":
        return "month"
    if candle_count <= 180:
        return "day"
    if candle_count <= 520:
        return "week"
    return "month"


def _default_period_from_company(company: dict[str, Any]) -> tuple[date, date]:
    disclosure_dates: list[date] = []
    for disclosure in list(company.get("disclosures") or []):
        disclosed_at = str(disclosure.get("disclosed_at") or "").strip()
        if not disclosed_at:
            continue
        try:
            disclosure_dates.append(date.fromisoformat(disclosed_at.split(" ", 1)[0]))
        except ValueError:
            continue

    if not disclosure_dates:
        today = date.today()
        return today.replace(day=1), today

    latest = max(disclosure_dates)
    return latest.replace(day=1), latest


def _group_color_map() -> dict[str, str]:
    return disclosure_group_color_map(DEFAULT_DISCLOSURE_GROUP_RULES)


def _serialize_company(company: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_key": _company_key(company),
        "company_name": company.get("company_name"),
        "company_id": company.get("company_id"),
        "market": company.get("market"),
        "badges": list(company.get("badges") or []),
        "disclosure_count": _company_disclosure_count(company),
        "first_disclosed_at": company.get("first_disclosed_at"),
        "last_disclosed_at": company.get("last_disclosed_at"),
    }


def _text_contains(value: object, keyword: str) -> bool:
    return not keyword or keyword in str(value or "").casefold()


def _split_keywords(value: object) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else str(value).replace(",", "\n").splitlines()
    return [
        str(item).strip().casefold()
        for item in raw_items
        if str(item).strip()
    ]


def _text_matches_keywords(value: object, keywords: list[str], mode: str) -> bool:
    if not keywords:
        return True
    target = str(value or "").casefold()
    if mode == "and":
        return all(keyword in target for keyword in keywords)
    return any(keyword in target for keyword in keywords)


def _text_excludes_keywords(value: object, keywords: list[str]) -> bool:
    target = str(value or "").casefold()
    return not any(keyword in target for keyword in keywords)


def _tokenize_title_expression(expression: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(expression):
        char = expression[index]
        if char.isspace():
            index += 1
            continue
        if char in "()":
            tokens.append(char)
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            phrase_chars: list[str] = []
            while index < len(expression):
                current = expression[index]
                if current == "\\" and index + 1 < len(expression):
                    phrase_chars.append(expression[index + 1])
                    index += 2
                    continue
                if current == quote:
                    index += 1
                    break
                phrase_chars.append(current)
                index += 1
            else:
                msg = "Unclosed quote in title expression"
                raise ValueError(msg)
            phrase = "".join(phrase_chars).strip()
            if phrase:
                tokens.append(phrase)
            continue

        start = index
        while index < len(expression) and not expression[index].isspace() and expression[index] not in "()":
            index += 1
        token = expression[start:index].strip()
        if token:
            tokens.append(token)
    return tokens


def _title_expression_matches(value: object, expression: str) -> bool:
    normalized_expression = str(expression or "").strip()
    if not normalized_expression:
        return True

    tokens = _tokenize_title_expression(normalized_expression)
    if not tokens:
        return True
    target = str(value or "").casefold()
    position = 0

    def peek() -> str | None:
        return tokens[position] if position < len(tokens) else None

    def consume() -> str:
        nonlocal position
        if position >= len(tokens):
            msg = "Unexpected end of title expression"
            raise ValueError(msg)
        token = tokens[position]
        position += 1
        return token

    def parse_factor() -> bool:
        token = peek()
        if token is None:
            msg = "Unexpected end of title expression"
            raise ValueError(msg)
        if token.casefold() == "not":
            consume()
            return not parse_factor()
        if token == "(":
            consume()
            result = parse_or()
            if peek() != ")":
                msg = "Missing closing parenthesis in title expression"
                raise ValueError(msg)
            consume()
            return result
        if token == ")":
            msg = "Unexpected closing parenthesis in title expression"
            raise ValueError(msg)
        keyword = consume()
        if keyword.casefold() in {"and", "or"}:
            msg = f"Unexpected operator in title expression: {keyword}"
            raise ValueError(msg)
        return keyword.casefold() in target

    def parse_and() -> bool:
        result = parse_factor()
        while peek() is not None and peek().casefold() == "and":
            consume()
            result = parse_factor() and result
        return result

    def parse_or() -> bool:
        result = parse_and()
        while peek() is not None and peek().casefold() == "or":
            consume()
            result = parse_and() or result
        return result

    result = parse_or()
    if position != len(tokens):
        msg = f"Unexpected token in title expression: {tokens[position]}"
        raise ValueError(msg)
    return result


def _parse_boolean_tokens(tokens: list[object]) -> bool:
    position = 0

    def peek() -> object | None:
        return tokens[position] if position < len(tokens) else None

    def consume() -> object:
        nonlocal position
        if position >= len(tokens):
            msg = "Unexpected end of filter blocks"
            raise ValueError(msg)
        token = tokens[position]
        position += 1
        return token

    def parse_factor() -> bool:
        token = peek()
        if token is None:
            msg = "Unexpected end of filter blocks"
            raise ValueError(msg)
        if isinstance(token, str) and token.casefold() == "not":
            consume()
            return not parse_factor()
        if token == "(":
            consume()
            result = parse_or()
            if peek() != ")":
                msg = "Missing closing parenthesis in filter blocks"
                raise ValueError(msg)
            consume()
            return result
        if token == ")":
            msg = "Unexpected closing parenthesis in filter blocks"
            raise ValueError(msg)
        if isinstance(token, str) and token.casefold() in {"and", "or"}:
            msg = f"Unexpected operator in filter blocks: {token}"
            raise ValueError(msg)
        return bool(consume())

    def parse_and() -> bool:
        result = parse_factor()
        while isinstance(peek(), str) and peek().casefold() == "and":
            consume()
            result = parse_factor() and result
        return result

    def parse_or() -> bool:
        result = parse_and()
        while isinstance(peek(), str) and peek().casefold() == "or":
            consume()
            result = parse_and() or result
        return result

    result = parse_or()
    if position != len(tokens):
        msg = f"Unexpected token in filter blocks: {tokens[position]}"
        raise ValueError(msg)
    return result


def _record_field_value(record: dict[str, Any], field: str) -> object:
    normalized_field = str(field or "").strip()
    if normalized_field in {"disclosed_date", "date"}:
        return _date_part(record.get("disclosed_at"))
    if normalized_field in {"acpt_no", "acptno"}:
        return record.get("acpt_no") or record.get("acptno")
    return record.get(normalized_field)


def _split_operator_values(value: object) -> list[str]:
    if isinstance(value, list):
        raw_values = value
    else:
        raw_text = str(value or "").replace("..", "\n").replace(",", "\n")
        raw_values = raw_text.splitlines()
    return [str(item).strip() for item in raw_values if str(item).strip()]


def _remove_whitespace(value: str) -> str:
    return "".join(str(value).split())


def _condition_block_matches(record: dict[str, Any], block: dict[str, Any]) -> bool:
    field = str(block.get("field") or "title").strip()
    operator = str(block.get("operator") or "contains").strip()
    expected = str(block.get("value") or "").strip()
    raw_value = _record_field_value(record, field)
    actual = str(raw_value or "").strip()
    if bool(block.get("ignore_spaces")):
        actual = _remove_whitespace(actual)
        expected = _remove_whitespace(expected)
    actual_folded = actual.casefold()
    expected_folded = expected.casefold()

    if operator == "contains":
        return expected_folded in actual_folded
    if operator == "not_contains":
        return expected_folded not in actual_folded
    if operator == "exact_match":
        return actual == expected
    if operator == "equals":
        return actual_folded == expected_folded
    if operator == "not_equals":
        return actual_folded != expected_folded
    if operator == "starts_with":
        return actual_folded.startswith(expected_folded)
    if operator == "ends_with":
        return actual_folded.endswith(expected_folded)
    if operator == "in":
        values = {item.casefold() for item in _split_operator_values(expected)}
        return actual_folded in values
    if operator == "before":
        return bool(actual and expected and actual < expected)
    if operator == "after":
        return bool(actual and expected and actual > expected)
    if operator == "on_or_before":
        return bool(actual and expected and actual <= expected)
    if operator == "on_or_after":
        return bool(actual and expected and actual >= expected)
    if operator == "between":
        values = _split_operator_values(expected)
        if len(values) < 2:
            msg = "between operator requires two values"
            raise ValueError(msg)
        start, end = values[0], values[1]
        return bool(actual and start <= actual <= end)
    if operator == "exists":
        return bool(actual)
    if operator == "empty":
        return not actual

    msg = f"Unsupported filter operator: {operator}"
    raise ValueError(msg)


def _record_filter_blocks_match(record: dict[str, Any], blocks: object) -> bool:
    if not blocks:
        return True
    if not isinstance(blocks, list):
        msg = "filter_blocks must be a list"
        raise ValueError(msg)

    tokens: list[object] = []
    has_condition = False
    for index, raw_block in enumerate(blocks):
        if not isinstance(raw_block, dict):
            msg = "filter block must be an object"
            raise ValueError(msg)
        expected_value = str(raw_block.get("value") or "").strip()
        operator = str(raw_block.get("operator") or "contains").strip()
        if not expected_value and operator not in {"exists", "empty"}:
            continue
        if has_condition:
            connector = str(raw_block.get("connector") or "AND").strip().upper()
            if connector not in {"AND", "OR"}:
                msg = f"Unsupported filter connector: {connector}"
                raise ValueError(msg)
            tokens.append(connector)
        for _ in range(int(raw_block.get("open_count") or 0)):
            tokens.append("(")
        if bool(raw_block.get("not")):
            tokens.append("NOT")
        tokens.append(_condition_block_matches(record, raw_block))
        for _ in range(int(raw_block.get("close_count") or 0)):
            tokens.append(")")
        has_condition = True

    if not tokens:
        return True
    return _parse_boolean_tokens(tokens)


def _date_part(value: object) -> str:
    return str(value or "").strip().split(" ", 1)[0]


def _normalize_acpt_numbers(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = str(value).replace(",", "\n").splitlines()
    return {
        str(item).strip()
        for item in raw_values
        if str(item).strip()
    }


ProgressCallback = Callable[[dict[str, Any]], None]


def _progress_interval(value: object) -> int:
    try:
        return min(max(int(value or 100), 1), 10000)
    except (TypeError, ValueError):
        return 100


def _emit_progress(
    progress_callback: ProgressCallback | None,
    *,
    source_type: str,
    unit_label: str,
    completed: int,
    total: int,
    records: int,
    force: bool = False,
    progress_interval: int = 100,
) -> None:
    if progress_callback is None or total <= 0:
        return
    if not force and completed % progress_interval != 0 and completed != total:
        return
    progress_callback(
        {
            "source_type": source_type,
            "unit_label": unit_label,
            "completed": completed,
            "total": total,
            "records": records,
        }
    )


def _iter_disclosure_records(
    classification_payload: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
    progress_interval: int = 100,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    companies = list(classification_payload.get("companies") or [])
    for index, company in enumerate(companies, start=1):
        company_key = _company_key(company)
        company_name = company.get("company_name")
        company_id = company.get("company_id")
        market = company.get("market")
        for disclosure in list(company.get("disclosures") or []):
            record = dict(disclosure)
            record.update(
                {
                    "company_key": company_key,
                    "company_name": company_name,
                    "company_id": company_id,
                    "market": market,
                }
            )
            records.append(record)
        _emit_progress(
            progress_callback,
            source_type="classification",
            unit_label="JSON 항목",
            completed=index,
            total=len(companies),
            records=len(records),
            progress_interval=progress_interval,
        )
    return records


def _element_text(node: html.HtmlElement | None) -> str:
    if node is None:
        return ""
    return _clean_text(" ".join(text for text in node.itertext()))


def _companysummary_onclick(onclick_value: object) -> str | None:
    match = _COMPANYSUMMARY_OPEN_RE.search(str(onclick_value or ""))
    if match is None:
        return None
    return match.group("company_id").strip() or None


def _disclosure_onclick(onclick_value: object) -> tuple[str | None, str | None]:
    match = _OPEN_DISCLS_VIEWER_RE.search(str(onclick_value or ""))
    if match is None:
        return (None, None)
    return (
        match.group("acpt_no").strip() or None,
        match.group("doc_no").strip() or None,
    )


def _find_disclosure_results_table(root: html.HtmlElement) -> html.HtmlElement | None:
    for table_tag in root.xpath("//table"):
        summary = _clean_text(table_tag.get("summary"))
        if "회사명" in summary and "공시제목" in summary:
            return table_tag
    tables = root.xpath("//table[contains(concat(' ', normalize-space(@class), ' '), ' list ')]")
    return tables[0] if tables else None


def _build_source_disclosure_row(row_tag: html.HtmlElement) -> dict[str, Any] | None:
    cells = row_tag.xpath("./td")
    if len(cells) < 5:
        return None

    company_cell = cells[2]
    disclosure_cell = cells[3]
    submitter_cell = cells[4]
    company_links = company_cell.xpath(".//a[@id='companysum']") or company_cell.xpath(".//a")
    company_link = company_links[0] if company_links else None
    disclosure_links = disclosure_cell.xpath(".//a")
    disclosure_link = disclosure_links[0] if disclosure_links else None

    company_name = ""
    company_id = None
    if company_link is not None:
        company_name = _clean_text(company_link.get("title") or _element_text(company_link))
        company_id = _companysummary_onclick(company_link.get("onclick"))
    if not company_name:
        company_name = _element_text(company_cell)

    labels = [_clean_text(image_tag.get("alt")) for image_tag in company_cell.xpath(".//img")]
    labels = [label for label in labels if label]
    market = labels[0] if labels else None
    badges = labels[1:] if len(labels) > 1 else []

    acpt_no, doc_no = _disclosure_onclick(disclosure_link.get("onclick") if disclosure_link is not None else None)
    title = ""
    if disclosure_link is not None:
        title = _clean_text(disclosure_link.get("title") or _element_text(disclosure_link))
    if not title:
        title = _element_text(disclosure_cell)

    return {
        "company_key": _clean_text(company_id or company_name),
        "company_name": company_name,
        "company_id": company_id,
        "market": market,
        "badges": badges,
        "disclosed_at": _element_text(cells[1]),
        "title": title,
        "acpt_no": acpt_no,
        "doc_no": doc_no,
        "submitter": _element_text(submitter_cell),
    }


def _parse_source_body_file(file_path: Path) -> list[dict[str, Any]]:
    markup = file_path.read_bytes().decode("utf-8", errors="replace")
    parser = html.HTMLParser(recover=True, huge_tree=True)
    try:
        root = html.document_fromstring(markup, parser=parser)
    except etree.ParserError:
        return []
    table_tag = _find_disclosure_results_table(root)
    if table_tag is None:
        return []

    parent_tags = table_tag.xpath("./tbody") or [table_tag]
    rows: list[dict[str, Any]] = []
    for parent_tag in parent_tags:
        for row_tag in parent_tag.xpath("./tr"):
            row = _build_source_disclosure_row(row_tag)
            if row is not None:
                rows.append(row)
    return rows


def _find_source_body_files(root: Path) -> list[Path]:
    return sorted(
        root.rglob("*_post_page_*.body"),
        key=lambda path: (str(path.parent.relative_to(root)), _result_page_number(path), path.name),
    )


def _iter_source_disclosure_records(
    root_directory: str | Path,
    *,
    progress_callback: ProgressCallback | None = None,
    progress_interval: int = 100,
) -> tuple[list[dict[str, Any]], int]:
    root = Path(root_directory).expanduser().resolve()
    if not root.is_dir():
        msg = f"root_directory is not a directory: {root}"
        raise ValueError(msg)
    body_paths = _find_source_body_files(root)
    folders: dict[Path, list[Path]] = {}
    for body_path in body_paths:
        folders.setdefault(body_path.parent, []).append(body_path)
    records: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, str]] = set()
    for index, folder_path in enumerate(sorted(folders), start=1):
        for body_path in folders[folder_path]:
            for record in _parse_source_body_file(body_path):
                key = (
                    str(record.get("acpt_no") or ""),
                    str(record.get("company_id") or ""),
                    str(record.get("disclosed_at") or ""),
                    str(record.get("title") or ""),
                )
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                records.append(record)
        _emit_progress(
            progress_callback,
            source_type="source_folder",
            unit_label="폴더",
            completed=index,
            total=len(folders),
            records=len(records),
            progress_interval=progress_interval,
        )
    return (records, len(body_paths))


def filter_disclosures_payload(
    body: dict[str, Any],
    *,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Filter a company-classification artifact and return a portable disclosure JSON."""
    classification_path = str(body.get("classification_path") or "").strip()
    root_directory = str(body.get("root_directory") or "").strip()
    if not classification_path:
        if not root_directory:
            msg = "classification_path or root_directory is required"
            raise ValueError(msg)
        classification_path = resolve_default_classification(root_directory) or ""
    source_kind = "classification" if classification_path else "source_folder"

    title_expression = str(body.get("title_expression") or "").strip()
    filter_blocks = body.get("filter_blocks")
    title_keywords = _split_keywords(body.get("title_keywords") or body.get("title_keyword"))
    exclude_title_keywords = _split_keywords(body.get("exclude_title_keywords"))
    title_match_mode = str(body.get("title_match_mode") or "or").strip().casefold()
    if title_match_mode not in {"or", "and"}:
        title_match_mode = "or"
    company_keyword = str(body.get("company_keyword") or "").strip().casefold()
    submitter_keyword = str(body.get("submitter_keyword") or "").strip().casefold()
    market = str(body.get("market") or "전체").strip() or "전체"
    start_date = str(body.get("start_date") or "").strip()
    end_date = str(body.get("end_date") or "").strip()
    acpt_numbers = _normalize_acpt_numbers(body.get("acpt_numbers"))
    limit_unlimited = bool(body.get("limit_unlimited"))
    limit = None if limit_unlimited else int(body.get("limit") or 1000)
    if limit is not None:
        limit = min(max(limit, 1), DISCLOSURE_FILTER_LIMIT_MAX)
    progress_interval = _progress_interval(body.get("progress_interval"))

    body_files = 0
    if classification_path:
        payload = load_company_classification_file(classification_path)
        records = _iter_disclosure_records(
            payload,
            progress_callback=progress_callback,
            progress_interval=progress_interval,
        )
    else:
        records, body_files = _iter_source_disclosure_records(
            root_directory,
            progress_callback=progress_callback,
            progress_interval=progress_interval,
        )
    filtered: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        disclosed_date = _date_part(record.get("disclosed_at"))
        acpt_no = str(record.get("acpt_no") or record.get("acptno") or "").strip()
        matched = True
        if acpt_numbers and acpt_no not in acpt_numbers:
            matched = False
        if matched and market != "전체" and str(record.get("market") or "") != market:
            matched = False
        if matched and start_date and disclosed_date and disclosed_date < start_date:
            matched = False
        if matched and end_date and disclosed_date and disclosed_date > end_date:
            matched = False
        if matched and filter_blocks:
            matched = _record_filter_blocks_match(record, filter_blocks)
        elif matched and title_expression:
            matched = _title_expression_matches(record.get("title"), title_expression)
        elif matched:
            matched = _text_matches_keywords(record.get("title"), title_keywords, title_match_mode)
        if matched and not title_expression:
            matched = _text_excludes_keywords(record.get("title"), exclude_title_keywords)
        if matched:
            matched = _text_contains(record.get("company_name"), company_keyword)
        if matched:
            matched = _text_contains(record.get("submitter"), submitter_keyword)
        if matched:
            filtered.append(record)
        _emit_progress(
            progress_callback,
            source_type=source_kind,
            unit_label="공시",
            completed=index,
            total=len(records),
            records=len(filtered),
            progress_interval=progress_interval,
        )

    filtered.sort(
        key=lambda record: (
            str(record.get("disclosed_at") or ""),
            str(record.get("company_name") or ""),
            str(record.get("title") or ""),
        ),
        reverse=True,
    )
    limited = filtered if limit is None else filtered[:limit]
    return {
        "format": "kind_disclosure_filter_v1",
        "source_type": source_kind,
        "source_classification_path": str(Path(classification_path).resolve()) if classification_path else "",
        "source_root_directory": str(Path(root_directory).expanduser().resolve()) if root_directory else "",
        "filters": {
            "filter_blocks": filter_blocks if isinstance(filter_blocks, list) else [],
            "title_expression": title_expression,
            "title_keywords": title_keywords,
            "exclude_title_keywords": exclude_title_keywords,
            "title_match_mode": title_match_mode,
            "title_keyword": body.get("title_keyword") or "",
            "company_keyword": body.get("company_keyword") or "",
            "submitter_keyword": body.get("submitter_keyword") or "",
            "market": market,
            "start_date": start_date,
            "end_date": end_date,
            "acpt_numbers": sorted(acpt_numbers),
            "limit": limit,
            "limit_unlimited": limit_unlimited,
        },
        "summary": {
            "source_disclosures": len(records),
            "source_body_files": body_files,
            "matched_disclosures": len(filtered),
            "returned_disclosures": len(limited),
            "unique_acpt_numbers": len({str(record.get("acpt_no") or "") for record in limited if record.get("acpt_no")}),
        },
        "disclosures": limited,
    }


def list_classification_files(root_directory: str | Path) -> list[dict[str, str]]:
    root = Path(root_directory).resolve()
    return [
        {
            "path": str(path),
            "name": path.name,
            "label": _classification_option_label(path),
        }
        for path in find_company_classification_files(root)
    ]


def _looks_like_price_directory(path: Path) -> bool:
    if not path.is_dir():
        return False
    if any(path.glob("*.parquet")):
        return True
    return (path / "manifest.json").is_file()


def list_price_source_files(root_directory: str | Path) -> list[dict[str, str]]:
    root = Path(root_directory).resolve()
    if not root.exists():
        return []

    candidates: list[Path] = []
    if _looks_like_price_directory(root):
        candidates.append(root)

    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if _looks_like_price_directory(child):
            candidates.append(child)

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique_candidates.append(candidate)

    return [
        {
            "path": str(path),
            "name": path.name,
            "label": path.name if path.parent == root else str(path.relative_to(root)),
        }
        for path in unique_candidates
    ]


def resolve_default_classification(root_directory: str | Path) -> str | None:
    root = Path(root_directory).resolve()
    files = list_classification_files(root)
    if not files:
        return None
    for preferred_name in ("kind.company_classification.json", "kind.company_classification.sample.json"):
        for file_info in files:
            if Path(file_info["path"]).name == preferred_name:
                return file_info["path"]
    return files[0]["path"]


def resolve_default_price_source(root_directory: str | Path, current_path: str | Path | None = None) -> str | None:
    root = Path(root_directory).resolve()
    current = Path(current_path).resolve() if current_path else None
    files = list_price_source_files(root)
    if not files:
        return None
    if current:
        for file_info in files:
            if Path(file_info["path"]) == current:
                return file_info["path"]
    return files[0]["path"]


def load_company_index_payload(
    classification_path: str | Path,
    *,
    keyword: str = "",
    market: str = "전체",
) -> dict[str, Any]:
    payload = load_company_classification_index_file(classification_path)
    companies = list(payload.get("companies") or [])
    companies = sorted(
        companies,
        key=lambda company: (
            -_company_disclosure_count(company),
            str(company.get("company_name") or ""),
        ),
    )

    normalized_keyword = str(keyword or "").strip().casefold()
    filtered = [
        company
        for company in companies
        if (
            not normalized_keyword
            or normalized_keyword in str(company.get("company_name") or "").casefold()
        )
        and (market == "전체" or str(company.get("market") or "") == market)
    ]
    markets = ["전체"] + sorted(
        {
            str(company.get("market") or "").strip()
            for company in companies
            if str(company.get("market") or "").strip()
        }
    )
    summary = dict(payload.get("summary") or {})
    return {
        "summary": {
            "companies": int(summary.get("companies") or len(companies)),
            "disclosures": int(summary.get("disclosures") or 0),
            "filtered_companies": len(filtered),
        },
        "markets": markets,
        "companies": [_serialize_company(company) for company in filtered],
    }


def _load_price_rows(
    stock_code: str,
    *,
    range_start: date,
    range_end: date,
    price_source: str,
    quanti_dir: str | Path,
) -> list[dict[str, Any]]:
    if price_source == PRICE_SOURCE_QUANTI:
        return fetch_quanti_ohlcv(
            stock_code,
            start_date=range_start,
            end_date=range_end,
            quanti_dir=quanti_dir,
        )
    return fetch_stock_price_history(
        stock_code,
        start_date=range_start,
        end_date=range_end,
    )


def _build_marker_payload(disclosure_points: pd.DataFrame) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    color_map = _group_color_map()
    for row in disclosure_points.to_dict("records"):
        group_name = str(row.get("disclosure_group") or DISCLOSURE_GROUP_OTHER)
        style = disclosure_group_marker_style(group_name, DEFAULT_DISCLOSURE_GROUP_RULES)
        markers.append(
            {
                "time": row.get("trade_day"),
                "position": style["position"],
                "shape": style["shape"],
                "color": color_map.get(group_name, DISCLOSURE_GROUP_OTHER_COLOR),
                "text": group_name,
                "group": group_name,
                "title": row.get("title"),
                "submitter": row.get("submitter"),
                "disclosed_at": row.get("disclosed_at"),
                "acpt_no": row.get("acpt_no"),
            }
        )
    return markers


def _build_candle_payload(price_frame: pd.DataFrame) -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for row in price_frame.to_dict("records"):
        close_value = float(row["close"])
        open_value = float(row["open"])
        candles.append(
            {
                "time": row["trade_day"],
                "open": open_value,
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": close_value,
                "volume": float(row["volume"]),
                "vwap": None if pd.isna(row.get("vwap")) else float(row["vwap"]),
                "color": "#22ab94" if close_value >= open_value else "#f23645",
            }
        )
    return candles


def _build_group_summary(disclosure_frame: pd.DataFrame) -> list[dict[str, Any]]:
    color_map = _group_color_map()
    counts = disclosure_frame["disclosure_group"].value_counts().to_dict()
    groups: list[dict[str, Any]] = []
    for group_name, color in color_map.items():
        count = int(counts.get(group_name) or 0)
        if count == 0:
            continue
        groups.append(
            {
                "name": group_name,
                "color": color,
                "count": count,
                "default_visible": group_name != DISCLOSURE_GROUP_OTHER,
            }
        )
    return groups


def _build_timeline_payload(disclosure_frame: pd.DataFrame) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for row in disclosure_frame.sort_values("disclosed_at_dt", ascending=False).to_dict("records"):
        timeline.append(
            {
                "disclosed_at": row.get("disclosed_at"),
                "group": row.get("disclosure_group"),
                "title": row.get("title"),
                "submitter": row.get("submitter"),
                "acpt_no": row.get("acpt_no"),
                "trade_day": row.get("trade_day"),
            }
        )
    return timeline


def build_insight_payload(
    classification_path: str | Path,
    company_key: str,
    *,
    start_date_iso: str | None = None,
    end_date_iso: str | None = None,
    range_label: str = "검색기간",
    display_frequency_label: str = "자동",
    price_source: str = PRICE_SOURCE_QUANTI,
    quanti_dir: str | Path = DEFAULT_QUANTI_DIR,
    stock_code_override: str = "",
) -> dict[str, Any]:
    classification_resolved = Path(classification_path).resolve()
    company = load_company_classification_company_file(classification_resolved, company_key)
    company_summary = load_company_classification_index_file(classification_resolved)
    company_meta = next(
        (
            item
            for item in list(company_summary.get("companies") or [])
            if _company_key(item) == company_key
        ),
        {},
    )

    inferred_stock_code = infer_stock_code(
        company.get("company_id") or company_meta.get("company_id")
    )
    stock_code = str(stock_code_override or inferred_stock_code or "").strip()
    if stock_code and (not stock_code.isdigit() or len(stock_code) != 6):
        raise ValueError("종목코드는 숫자 6자리여야 합니다.")

    disclosure_frame = prepare_disclosure_dataframe(company)
    default_start, default_end = _default_period_from_company(company)
    manual_start = date.fromisoformat(start_date_iso) if start_date_iso else default_start
    manual_end = date.fromisoformat(end_date_iso) if end_date_iso else default_end
    range_start, range_end = apply_insight_range(
        range_label,
        base_start=manual_start,
        base_end=manual_end,
        disclosure_frame=disclosure_frame,
        ui_date_min=KIND_UI_DATE_MIN,
    )
    grouped_disclosures = disclosure_frame[
        (disclosure_frame["trade_date"] >= pd.Timestamp(range_start))
        & (disclosure_frame["trade_date"] <= pd.Timestamp(range_end))
    ].copy()
    grouped_disclosures["disclosure_group"] = grouped_disclosures["title"].map(
        lambda title: classify_disclosure_group(title, DEFAULT_DISCLOSURE_GROUP_RULES)
    )
    extended_price_end = range_end
    if not grouped_disclosures.empty and "trade_anchor_date" in grouped_disclosures.columns:
        latest_anchor = grouped_disclosures["trade_anchor_date"].max()
        if pd.notna(latest_anchor):
            extended_price_end = max(
                range_end,
                latest_anchor.date() + timedelta(days=7),
            )

    messages: list[str] = []
    price_frame = pd.DataFrame()
    display_frequency = "day"
    display_price_frame = pd.DataFrame()
    disclosure_points = pd.DataFrame()
    visible_range_end = range_end

    if stock_code:
        try:
            price_rows = _load_price_rows(
                stock_code,
                range_start=range_start,
                range_end=extended_price_end,
                price_source=price_source,
                quanti_dir=quanti_dir,
            )
            price_frame = prepare_price_dataframe(price_rows)
        except Exception as exc:  # pragma: no cover - network/runtime edge
            messages.append(f"주가 데이터를 불러오지 못했습니다: {exc}")
    else:
        messages.append("자동 종목코드를 찾지 못해 차트를 표시하지 않았습니다.")

    if not price_frame.empty:
        display_frequency = _resolve_display_frequency(display_frequency_label, len(price_frame))
        display_price_frame = aggregate_price_dataframe(
            price_frame,
            frequency=display_frequency,
        )
        disclosure_points = prepare_disclosure_points(
            grouped_disclosures,
            display_price_frame,
            placement=MARKER_PLACEMENT,
        )
        if not disclosure_points.empty:
            latest_visible_trade_day = pd.to_datetime(
                disclosure_points["trade_day"],
                errors="coerce",
            ).max()
            if pd.notna(latest_visible_trade_day):
                visible_range_end = max(range_end, latest_visible_trade_day.date())
                display_price_frame = display_price_frame[
                    display_price_frame["date"] <= pd.Timestamp(visible_range_end)
                ].copy()
                disclosure_points = prepare_disclosure_points(
                    grouped_disclosures,
                    display_price_frame,
                    placement=MARKER_PLACEMENT,
                )
        grouped_disclosures = grouped_disclosures.merge(
            disclosure_points[["acpt_no", "trade_day"]],
            on="acpt_no",
            how="left",
        )
    elif stock_code and not messages:
        messages.append("선택한 기간에 주가 데이터가 없습니다.")

    frequency_label_map = {"day": "일봉", "week": "주봉", "month": "월봉"}
    return {
        "company": {
            **_serialize_company(company_meta or company),
            "badges": list(company.get("badges") or company_meta.get("badges") or []),
        },
        "classification_path": str(classification_resolved),
        "stock_code": stock_code,
        "inferred_stock_code": inferred_stock_code,
        "manual_start": manual_start.isoformat(),
        "manual_end": manual_end.isoformat(),
        "range_start": range_start.isoformat(),
        "range_end": range_end.isoformat(),
        "visible_range_end": visible_range_end.isoformat(),
        "range_label": range_label,
        "display_frequency": display_frequency,
        "display_frequency_label": frequency_label_map.get(display_frequency, display_frequency),
        "price_source": price_source,
        "price_source_label": PRICE_SOURCE_LABELS.get(price_source, price_source),
        "messages": messages,
        "chart": {
            "candles": _build_candle_payload(display_price_frame),
            "markers": _build_marker_payload(disclosure_points),
            "groups": _build_group_summary(grouped_disclosures),
            "has_vwap": bool(
                not display_price_frame.empty
                and "vwap" in display_price_frame.columns
                and display_price_frame["vwap"].notna().any()
            ),
        },
        "timeline": _build_timeline_payload(grouped_disclosures),
    }


def build_company_list_export(
    classification_path: str | Path,
    *,
    keyword: str = "",
    market: str = "전체",
) -> bytes:
    company_payload = load_company_index_payload(
        classification_path,
        keyword=keyword,
        market=market,
    )
    rows = extract_unique_company_list_rows(company_payload["companies"])
    return build_company_list_xlsx(rows)
