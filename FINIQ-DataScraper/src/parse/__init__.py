"""Parse KIND HTML: disclosure list tables, viewer page, script snippets."""

from ._disclosures import companysummary_onclick, disclosure_file_rows, disclosure_rows
from ._snippets import (
    dart_main_doc_no,
    disclosure_onclick,
    pagination_info,
    search_paths,
    viewer_html,
)
from ._tables import ParseMode, file_to_json, html_to_json

__all__ = [
    "ParseMode",
    "companysummary_onclick",
    "dart_main_doc_no",
    "disclosure_file_rows",
    "disclosure_onclick",
    "disclosure_rows",
    "file_to_json",
    "html_to_json",
    "pagination_info",
    "search_paths",
    "viewer_html",
]
