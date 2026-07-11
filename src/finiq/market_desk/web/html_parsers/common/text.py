"""문자열 정제 및 숫자 변환 유틸리티."""

from __future__ import annotations

import re

from lxml import etree


def clean_text(value: str | None) -> str:
    """문자열 내의 연속된 공백을 단일 공백으로 압축한다."""
    return " ".join((value or "").split())


def element_text(element: etree._Element) -> str:
    """lxml 요소(element) 내부의 모든 텍스트를 추출하여 정규화한다."""
    return clean_text(" ".join(element.itertext()))


def parse_int(value: str | None, *, dash_as_zero: bool = False) -> int | None:
    """쉼표가 포함된 문자열을 정수(int)형으로 변환한다."""
    text = _remove_grouping_spaces(clean_text(value))
    if dash_as_zero and text == "-":
        return 0
    match = re.search(r"-?\d[\d,]*", text)
    if match is None:
        return None
    return int(match.group(0).replace(",", ""))


def parse_ints(value: str | None) -> list[int]:
    """문자열 안의 모든 쉼표 정수를 순서대로 반환한다."""
    text = _remove_grouping_spaces(clean_text(value))
    return [int(match.replace(",", "")) for match in re.findall(r"-?\d[\d,]*", text)]


def _remove_grouping_spaces(value: str) -> str:
    """HTML span 분리로 생긴 쉼표 숫자 내부 공백만 제거한다."""
    def repl(match):
        seq = match.group(0)
        merged = seq.replace(" ", "")
        if "," in seq and re.match(r"^-?\d{1,3}(,\d{3})+$", merged):
            return merged
        return seq

    return re.sub(r"-?\d[\d,\s]*\d|-?\d", repl, value)
