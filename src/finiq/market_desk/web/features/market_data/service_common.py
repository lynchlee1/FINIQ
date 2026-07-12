"""Data services for the custom KIND web UI."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from lxml import etree, html

from finiq.config import KIND_DATA_DIR, PROJECT_ROOT, QUANTI_DIR
from finiq.market_desk.analytics.chart import (
    aggregate_price_dataframe,
    apply_insight_range,
    prepare_disclosure_dataframe,
    prepare_disclosure_points,
    prepare_price_dataframe,
)
from finiq.market_desk.analytics.company import (
    build_company_list_xlsx,
    extract_unique_company_list_rows,
    fetch_stock_price_history,
    infer_stock_code,
)
from finiq.market_desk.analytics.disclosure_groups import (
    DEFAULT_DISCLOSURE_GROUP_RULES,
    DISCLOSURE_GROUP_OTHER,
    DISCLOSURE_GROUP_OTHER_COLOR,
    classify_disclosure_group,
    disclosure_group_color_map,
    disclosure_group_marker_style,
)
from finiq.market_desk.analytics.quanti import fetch_quanti_ohlcv
from finiq.market_desk.analytics.quanti_market_history import (
    build_quanti_market_history,
    load_quanti_item_registry,
    market_item_from_registry,
    market_value_map_from_registry,
)
from finiq.market_desk.data.facade import (
    load_company_classification_company_file,
    load_company_classification_file,
    load_company_classification_index_file,
)
from finiq.market_desk.web.features.market_data.discovery import (
    list_classification_files,
    list_price_source_files,
    resolve_default_classification,
    resolve_default_price_source,
)

DEFAULT_OUTPUT_ROOT = str(KIND_DATA_DIR)
DEFAULT_QUANTI_DIR = str(QUANTI_DIR)
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
_RESULT_PAGE_NUMBER_RE = re.compile(r"_post_page_(?P<page>\d+)\.body$")
_COMPANYSUMMARY_OPEN_RE = re.compile(
    r"companysummary_open\(\s*['\"](?P<company_id>[^'\"]*)['\"]\s*\)"
)
_OPEN_DISCLS_VIEWER_RE = re.compile(
    r"openDisclsViewer\(\s*['\"](?P<acpt_no>[^'\"]*)['\"]\s*,\s*['\"](?P<doc_no>[^'\"]*)['\"]\s*\)"
)
_TITLE_FLAG_RE = re.compile(r"\[([^\[\]]+)\]")
_LATER_CORRECTION_LABEL = "해당보고서 이후에 정정된 보고서 있음"


def _company_key(company: dict[str, Any]) -> str:
    return str(
        company.get("company_key")
        or company.get("company_id")
        or company.get("company_name")
        or ""
    ).strip()


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
    raw_items = (
        value if isinstance(value, list) else str(value).replace(",", "\n").splitlines()
    )
    return [str(item).strip().casefold() for item in raw_items if str(item).strip()]


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
        while (
            index < len(expression)
            and not expression[index].isspace()
            and expression[index] not in "()"
        ):
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
        return record.get("__filter_disclosed_date") or _date_part(
            record.get("disclosed_at")
        )
    if normalized_field in {"acpt_no", "acptno"}:
        return (
            record.get("__filter_acpt_no")
            or record.get("acpt_no")
            or record.get("acptno")
        )
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


def _clean_search_text(value: str) -> str:
    text = str(value or "")
    cleaned: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "(":
            depth = 0
            last_close_index = -1
            scan_index = index
            while scan_index < len(text):
                current = text[scan_index]
                if current == "(":
                    depth += 1
                elif current == ")":
                    depth -= 1
                    last_close_index = scan_index
                    if depth <= 0:
                        scan_index += 1
                        while scan_index < len(text) and text[scan_index] == ")":
                            scan_index += 1
                        break
                scan_index += 1
            else:
                scan_index = (
                    last_close_index + 1 if last_close_index >= 0 else len(text)
                )
            index = scan_index
            continue
        if char == ")":
            index += 1
            continue
        cleaned.append(char)
        index += 1
    return "".join(cleaned)


def _condition_block_matches(record: dict[str, Any], block: dict[str, Any]) -> bool:
    field = str(block.get("field") or "title").strip()
    operator = str(block.get("operator") or "contains").strip()
    expected = str(block.get("value") or "").strip()
    raw_value = _record_field_value(record, field)
    actual = str(raw_value or "").strip()
    if bool(block.get("clean_search")):
        actual = _clean_search_text(actual)
        expected = _clean_search_text(expected)
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
    return {str(item).strip() for item in raw_values if str(item).strip()}


ProgressCallback = Callable[[dict[str, Any]], None]
CancelCheck = Callable[[], bool]




__all__ = [name for name in globals() if not name.startswith("__")]
