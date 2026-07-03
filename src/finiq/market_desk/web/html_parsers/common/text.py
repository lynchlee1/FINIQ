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
    text = clean_text(value)
    if dash_as_zero and text in {"", "-"}:
        return 0
    match = re.search(r"-?\d[\d,]*", text)
    if match is None:
        return None
    return int(match.group(0).replace(",", ""))


def parse_float(value: str | None) -> float | None:
    """문자열에서 소수점 데이터를 찾아 실수(float)형으로 변환한다."""
    text = clean_text(value)
    match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(match.group(0)) if match else None
