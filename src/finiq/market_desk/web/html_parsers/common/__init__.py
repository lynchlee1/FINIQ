"""KIND 공시 파서 공통 헬퍼 패키지.

`common.py`가 거대해짐에 따라 역할별(텍스트 정제, 테이블 추출, 로우 탐색, 메타데이터 등)로 
모듈을 세분화하고, 본 `__init__.py`에서 모두 취합하여 외부에는 기존과 동일한 인터페이스를 제공합니다.
"""

from __future__ import annotations

from .text import (
    clean_text,
    element_text,
    parse_int,
    parse_float,
)
from .io import (
    decode_html_markup,
    parse_html_document,
    fetch_selected_viewer_body,
)
from .rows import (
    row_contains,
    row_containing,
    normalize_label,
    row_with_label,
    value_after,
    last_value,
    last_int,
    column_index,
)
from .tables import (
    expand_table,
    compress_repeated_texts,
    extract_tables,
    extract_table_rows,
    is_correction_chapter,
    non_correction_tables,
    non_correction_rows,
)
from .metadata import (
    extract_title,
    extract_acpt_no,
    preserve_viewer_metadata,
    build_base_record,
)

__all__ = [
    "decode_html_markup",
    "clean_text",
    "element_text",
    "parse_int",
    "parse_float",
    "parse_html_document",
    "fetch_selected_viewer_body",
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
    "preserve_viewer_metadata",
    "build_base_record",
]
