"""Shared disclosure-group rules for insight UIs."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Any, Iterable, Mapping, Sequence

DISCLOSURE_GROUP_OTHER = "기타"
DISCLOSURE_GROUP_OTHER_COLOR = "#94a3b8"
_DEFAULT_MARKER_SHAPE = "square"
_DEFAULT_MARKER_POSITION = "inBar"
# Priority : not > and > or
_KEYWORD_OPERATOR_PATTERN = re.compile(
    r"\(|\)|&&|\|\||\b(?:and|or|not)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class DisclosureGroupRule:
    group: str
    color: str
    keywords: tuple[str, ...]
    marker_shape: str = _DEFAULT_MARKER_SHAPE
    marker_position: str = _DEFAULT_MARKER_POSITION
    default_visible: bool = True


DEFAULT_DISCLOSURE_GROUP_RULES: tuple[DisclosureGroupRule, ...] = (
    DisclosureGroupRule(
        group="CB",
        color="#f59e0b",
        keywords=(
            "전환사채발행", 
            "전환사채권발행",
        ),
        marker_shape="circle",
        marker_position="aboveBar",
    ),
    DisclosureGroupRule(
        group="EB",
        color="#8b5cf6",
        keywords=(
            "교환사채발행", 
            "교환사채권발행",
        ),
        marker_shape="circle",
        marker_position="aboveBar",
    ),
    DisclosureGroupRule(
        group="BW",
        color="#06b6d4",
        keywords=(
            "신주인수권부사채발행",
            "신주인수권부사채권발행",
        ),
        marker_shape="circle",
        marker_position="aboveBar",
    ),
    DisclosureGroupRule(
        group="유상증자",
        color="#10b981",
        keywords=(
            "유상증자",
            "유무상증자",
        ),
        marker_shape="arrowUp",
        marker_position="belowBar",
    ),
    DisclosureGroupRule(
        group="주주총회",
        color="#ef4444",
        keywords=(
            "주주총회",
        ),
    ),
)

_DEFAULT_RULES_BY_GROUP = {
    rule.group: rule for rule in DEFAULT_DISCLOSURE_GROUP_RULES
}


def _split_keyword_chunks(raw_keywords: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0

    for char in str(raw_keywords or ""):
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1

        if char == "," and depth == 0:
            chunk = "".join(current).strip()
            if chunk:
                parts.append(chunk)
            current = []
            continue

        current.append(char)

    chunk = "".join(current).strip()
    if chunk:
        parts.append(chunk)
    return parts


def _normalize_keywords(keywords: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_keyword in keywords:
        keyword = str(raw_keyword or "").strip()
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        normalized.append(keyword)
    return tuple(normalized)


@lru_cache(maxsize=None)
def _parse_keyword_expression(expression: str) -> tuple[Any, ...]:
    tokens: list[tuple[str, str]] = []
    current_position = 0
    normalized_expression = str(expression or "").strip()

    for match in _KEYWORD_OPERATOR_PATTERN.finditer(normalized_expression):
        start, end = match.span()
        if start > current_position:
            term = normalized_expression[current_position:start].strip()
            if term:
                tokens.append(("TERM", term))

        operator = match.group(0).lower()
        if operator == "(":
            tokens.append(("LPAREN", "("))
        elif operator == ")":
            tokens.append(("RPAREN", ")"))
        elif operator == "not":
            tokens.append(("NOT", operator))
        elif operator in {"and", "&&"}:
            tokens.append(("AND", operator))
        else:
            tokens.append(("OR", operator))
        current_position = end

    if current_position < len(normalized_expression):
        term = normalized_expression[current_position:].strip()
        if term:
            tokens.append(("TERM", term))

    if not tokens:
        raise ValueError("Keyword expression is empty.")

    index = 0

    def parse_or() -> tuple[Any, ...]:
        nonlocal index
        node = parse_and()
        while index < len(tokens) and tokens[index][0] == "OR":
            index += 1
            node = ("OR", node, parse_and())
        return node

    def parse_and() -> tuple[Any, ...]:
        nonlocal index
        node = parse_not()
        while index < len(tokens) and tokens[index][0] == "AND":
            index += 1
            node = ("AND", node, parse_not())
        return node

    def parse_not() -> tuple[Any, ...]:
        nonlocal index
        if index < len(tokens) and tokens[index][0] == "NOT":
            index += 1
            return ("NOT", parse_not())
        return parse_primary()

    def parse_primary() -> tuple[Any, ...]:
        nonlocal index
        if index >= len(tokens):
            raise ValueError("Keyword expression ended unexpectedly.")

        token_type, token_value = tokens[index]
        if token_type == "LPAREN":
            index += 1
            node = parse_or()
            if index >= len(tokens) or tokens[index][0] != "RPAREN":
                raise ValueError("Keyword expression is missing a closing parenthesis.")
            index += 1
            return node

        if token_type != "TERM":
            raise ValueError(f"Unexpected token in keyword expression: {token_value}")

        index += 1
        return ("TERM", token_value)

    parsed = parse_or()
    if index != len(tokens):
        raise ValueError(f"Unexpected token in keyword expression: {tokens[index][1]}")
    return parsed


def _evaluate_keyword_expression(node: tuple[Any, ...], normalized_title: str) -> bool:
    operator = node[0]
    if operator == "TERM":
        return str(node[1]) in normalized_title
    if operator == "NOT":
        return not _evaluate_keyword_expression(node[1], normalized_title)
    if operator == "AND":
        return _evaluate_keyword_expression(node[1], normalized_title) and _evaluate_keyword_expression(
            node[2], normalized_title
        )
    if operator == "OR":
        return _evaluate_keyword_expression(node[1], normalized_title) or _evaluate_keyword_expression(
            node[2], normalized_title
        )
    raise ValueError(f"Unsupported keyword expression node: {operator}")


def _matches_keyword_expression(normalized_title: str, expression: str) -> bool:
    normalized_expression = str(expression or "").strip()
    if not normalized_expression:
        return False
    try:
        return _evaluate_keyword_expression(
            _parse_keyword_expression(normalized_expression),
            normalized_title,
        )
    except ValueError:
        return normalized_expression in normalized_title


def make_disclosure_group_rule(
    group: str,
    *,
    color: str,
    keywords: Iterable[str],
) -> DisclosureGroupRule:
    normalized_group = str(group or "").strip()
    normalized_keywords = _normalize_keywords(keywords)
    default_rule = _DEFAULT_RULES_BY_GROUP.get(normalized_group)
    return DisclosureGroupRule(
        group=normalized_group,
        color=str(color or "").strip() or DISCLOSURE_GROUP_OTHER_COLOR,
        keywords=normalized_keywords,
        marker_shape=(
            default_rule.marker_shape if default_rule is not None else _DEFAULT_MARKER_SHAPE
        ),
        marker_position=(
            default_rule.marker_position
            if default_rule is not None
            else _DEFAULT_MARKER_POSITION
        ),
        default_visible=default_rule.default_visible if default_rule is not None else True,
    )


def default_disclosure_group_rows(
    group_rules: Sequence[DisclosureGroupRule] = DEFAULT_DISCLOSURE_GROUP_RULES,
) -> list[dict[str, str]]:
    return [
        {
            "group": rule.group,
            "color": rule.color,
            "keywords": "\n".join(rule.keywords),
        }
        for rule in group_rules
    ]


def parse_disclosure_group_rules(
    rows: Iterable[Mapping[str, Any]],
) -> list[DisclosureGroupRule]:
    rules: list[DisclosureGroupRule] = []
    for row in rows:
        group_name = str(row.get("group") or "").strip()
        keyword_lines = str(row.get("keywords") or "")
        keywords = [
            part
            for chunk in keyword_lines.splitlines()
            for part in _split_keyword_chunks(chunk)
        ]
        if not group_name or not keywords:
            continue
        rules.append(
            make_disclosure_group_rule(
                group_name,
                color=str(row.get("color") or "").strip(),
                keywords=keywords,
            )
        )
    return rules


def classify_disclosure_group(
    title: str,
    group_rules: Sequence[DisclosureGroupRule] = DEFAULT_DISCLOSURE_GROUP_RULES,
) -> str:
    normalized = str(title or "").strip()
    for rule in group_rules:
        if any(_matches_keyword_expression(normalized, keyword) for keyword in rule.keywords):
            return rule.group
    return DISCLOSURE_GROUP_OTHER


def disclosure_group_color_map(
    group_rules: Sequence[DisclosureGroupRule] = DEFAULT_DISCLOSURE_GROUP_RULES,
) -> dict[str, str]:
    color_map = {rule.group: rule.color for rule in group_rules}
    color_map[DISCLOSURE_GROUP_OTHER] = DISCLOSURE_GROUP_OTHER_COLOR
    return color_map


def disclosure_group_marker_style(
    group_name: str,
    group_rules: Sequence[DisclosureGroupRule] = DEFAULT_DISCLOSURE_GROUP_RULES,
) -> dict[str, str]:
    for rule in group_rules:
        if rule.group == group_name:
            return {
                "shape": rule.marker_shape,
                "position": rule.marker_position,
            }
    return {
        "shape": _DEFAULT_MARKER_SHAPE,
        "position": _DEFAULT_MARKER_POSITION,
    }

