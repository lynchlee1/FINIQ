"""KIND 공시 파서 공통 헬퍼 패키지.

`common.py`가 거대해짐에 따라 역할별(텍스트 정제, 테이블 추출, 로우 탐색, 메타데이터 등)로
모듈을 세분화하고, 본 `__init__.py`에서 모두 취합하여 외부에는 기존과 동일한 인터페이스를 제공합니다.
"""

from __future__ import annotations

from .io import (
    decode_html_markup,
    parse_html_document,
)
from .metadata import (
    build_base_record,
    extract_acpt_no,
    extract_title,
)
from .rows import (
    column_index,
    last_int,
    last_value,
    normalize_label,
    row_containing,
    row_contains,
    row_with_label,
    value_after,
)
from .tables import (
    compress_repeated_texts,
    expand_table,
    extract_table_rows,
    extract_tables,
    is_correction_chapter,
    non_correction_rows,
    non_correction_tables,
)
from .text import (
    clean_text,
    element_text,
    parse_float,
    parse_int,
    parse_ints,
)

__all__ = [
    "decode_html_markup",
    "clean_text",
    "element_text",
    "parse_int",
    "parse_ints",
    "parse_float",
    "parse_html_document",
    "row_contains",
    "row_containing",
    "normalize_label",
    "row_with_label",
    "value_after",
    "last_value",
    "last_int",
    "column_index",
    "expand_table",
    "compress_repeated_texts",
    "extract_tables",
    "extract_table_rows",
    "is_correction_chapter",
    "non_correction_tables",
    "non_correction_rows",
    "extract_title",
    "extract_acpt_no",
    "build_base_record",
]
