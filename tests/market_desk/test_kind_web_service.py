from __future__ import annotations

from datetime import date
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any
import zipfile

import pandas as pd
import pytest

import finiq.market_desk.web.features.disclosures.table_export as table_export_module
import finiq.market_desk.web.features.disclosures.html_common as html_common_module
import finiq.market_desk.web.features.market_data.service_payloads as service_payloads_module
import finiq.market_desk.web.features.market_data.service_sources as service_sources_module
from finiq.config import QUANTI_DIR, STOCK_DATA_DIR
from finiq.data_scraper.workflow import KIND_WORKFLOW_INPUT_FORMAT
from finiq.market_desk.analytics.quanti_market_history import (
    build_quanti_market_history,
    find_market_at,
    load_quanti_item_registry,
    market_item_from_registry,
    market_value_map_from_registry,
)
from finiq.market_desk.analytics.disclosure_groups import DISCLOSURE_GROUP_OTHER
from finiq.market_desk.web.features.market_data.discovery import list_classification_files
from finiq.market_desk.web.features.market_data.service_common import _clean_search_text
from finiq.market_desk.web.features.market_data.service_insight import build_insight_payload
from finiq.market_desk.web.features.market_data.service_payloads import (
    filter_disclosures_payload,
    load_company_index_payload,
    search_disclosure_titles_payload,
)
from finiq.market_desk.web.features.market_data.service_records import (
    FilterCancelled,
    _progress_interval,
)
from finiq.market_desk.web.features.market_data.service_sources import (
    _validate_sqlite_manifest_counts,
)
from finiq.market_desk.web.features.disclosures.html_cleanup import (
    check_disclosure_html_output_directory_payload,
    clean_disclosure_html_output_directory_payload,
    create_external_html_integrity_baseline_payload,
    write_disclosure_html_manifest_payload,
)
from finiq.market_desk.web.features.disclosures.html_common import (
    _render_internal_html_source_unavailable_placeholder,
    cancel_disclosure_html_download,
    collect_acpt_numbers_from_json,
    resolve_disclosure_html_file,
)
from finiq.market_desk.web.features.disclosures.internal_html_download import (
    download_disclosure_internal_html_payload,
)
from finiq.market_desk.web.features.disclosures.external_html_download import (
    download_disclosure_external_html_payload,
)
from finiq.market_desk.web.features.disclosures.external_html_compress import compress_disclosure_external_html_payload
from finiq.market_desk.web.features.downloads.kind_inspect import inspect_download_output_directory_payload
import finiq.market_desk.web.features.disclosures.html_sections as disclosure_html_sections
from finiq.market_desk.web.features.disclosures.html_parse_changes import (
    build_parse_change_log_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_common import (
    PARSER_REGISTRY,
    _collect_html_files,
    _load_html_parse_metadata,
    _metadata_title_for_file,
    _record_parse_warning_items,
    cancel_disclosure_html_parse,
    list_parser_methods_payload,
    parse_disclosure_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_export import (
    build_parse_export_xlsx,
)
from finiq.market_desk.web.features.disclosures.html_parse_preview import (
    build_parse_filter_candidates_payload,
    build_parse_preview_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_support import (
    _compact_source_tables,
)
from finiq.market_desk.web.features.disclosures.html_parse_summary import (
    build_bond_parse_summary_payload,
)
from finiq.market_desk.web.features.disclosures.html_sections import (
    HtmlSectionSummary,
    inspect_disclosure_html_section_output_payload,
    inspect_disclosure_html_sections_payload,
    list_disclosure_html_section_sources_payload,
    parse_html_section_worker_count,
    save_disclosure_html_sections_payload,
    split_disclosure_html_section_source_payload,
    split_internal_html_sections,
    summarize_disclosure_html_section_kinds_payload,
)
from finiq.market_desk.web.html_parsers.bond_issuance import parse_bond_issuance
from finiq.market_desk.web.html_parsers.bond_issuance.extractor import (
    BOND_SECURITY_TYPE_LABELS,
    EXERCISE_PERIOD_LABEL_GROUPS,
    EXERCISE_PRICE_LABEL_GROUPS,
    EXERCISE_TARGET_LABEL_GROUPS,
)
from finiq.market_desk.web.html_parsers.common import (
    expand_table,
    extract_acpt_no,
    parse_html_document,
    parse_int,
    parse_ints,
    row_with_label,
)
from finiq.market_desk.web.features.disclosures.table_export import build_disclosure_table_payload
from finiq.market_desk.analytics.quanti import list_quanti_stock_codes
from finiq.market_desk.web.html_parsers.rights_issuance import parse_rights_issuance
from finiq.market_desk.web.html_parsers.rights_issuance.utils import (
    _is_rights_section_marker_row,
)
from finiq.data_scraper.storage.classification_store import (
    write_company_classification_artifact,
)

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
KIND_RESOURCES_DIR = REPO_ROOT / "resources" / "KIND"
HAS_KIND_RESOURCES = KIND_RESOURCES_DIR.is_dir()
RIGHTS_GROUPED_DIR = (
    KIND_RESOURCES_DIR
    / "rights_issuance"
    / "kind_html_contents_sections_grouped"
)
RIGHTS_FILTERED_PATH = KIND_RESOURCES_DIR / "rights_issuance" / "filtered.json"
_RIGHTS_MANIFEST_TITLES: dict[str, str] | None = None


def _rights_manifest_title(fixture_path: Path) -> str:
    global _RIGHTS_MANIFEST_TITLES
    assert RIGHTS_FILTERED_PATH.is_file()
    if _RIGHTS_MANIFEST_TITLES is None:
        payload = json.loads(RIGHTS_FILTERED_PATH.read_text(encoding="utf-8"))
        _RIGHTS_MANIFEST_TITLES = {
            str(row.get("acpt_no") or ""): str(row.get("title") or "").strip()
            for row in payload["disclosures"]
        }
    title = _RIGHTS_MANIFEST_TITLES.get(fixture_path.stem)
    assert title
    return title


PAID_RIGHTS_ISSUANCE_50_EXAMPLES = [
    "2008/20080825000060.html",
    "2008/20080825000143.html",
    "2008/20080825000155.html",
    "2008/20080825000248.html",
    "2008/20080825000324.html",
    "2008/20080825000337.html",
    "2008/20080825000370.html",
    "2008/20080825000389.html",
    "2008/20080825000448.html",
    "2008/20080826000077.html",
    "2008/20080826000107.html",
    "2008/20080826000122.html",
    "2008/20080826000223.html",
    "2008/20080826000259.html",
    "2008/20080826000345.html",
    "2008/20080826000364.html",
    "2008/20080827000043.html",
    "2008/20080827000091.html",
    "2008/20080827000095.html",
    "2008/20080827000150.html",
    "2008/20080827000199.html",
    "2008/20080827000256.html",
    "2008/20080827000278.html",
    "2008/20080827000283.html",
    "2008/20080827000336.html",
    "2008/20080828000214.html",
    "2008/20080828000319.html",
    "2008/20080829000402.html",
    "2008/20080901000151.html",
    "2008/20080901000322.html",
    "2008/20080901000445.html",
    "2008/20080901000478.html",
    "2008/20080901000589.html",
    "2008/20080901000600.html",
    "2008/20080902000110.html",
    "2008/20080903000038.html",
    "2008/20080903000175.html",
    "2008/20080903000226.html",
    "2008/20080903000313.html",
    "2008/20080903000352.html",
    "2008/20080903000373.html",
    "2008/20080903000392.html",
    "2008/20080904000001.html",
    "2008/20080904000005.html",
    "2008/20080904000007.html",
    "2008/20080904000037.html",
    "2008/20080904000117.html",
    "2008/20080904000153.html",
    "2008/20080904000418.html",
    "2008/20080904000435.html",
]
BONUS_RIGHTS_ISSUANCE_50_EXAMPLES = [
    "2008/20080825000072.html",
    "2008/20080825000101.html",
    "2008/20080827000089.html",
    "2008/20080828000418.html",
    "2008/20080919000057.html",
    "2008/20080919000087.html",
    "2008/20080923000111.html",
    "2008/20081029000157.html",
    "2008/20081031000493.html",
    "2008/20081117000038.html",
    "2008/20081201000375.html",
    "2008/20081210000228.html",
    "2008/20081215000486.html",
    "2008/20081216000162.html",
    "2008/20081216000201.html",
    "2008/20081216000720.html",
    "2008/20081217000448.html",
    "2008/20081223000201.html",
    "2008/20081226000094.html",
    "2009/20090105000045.html",
    "2009/20090119000330.html",
    "2009/20090121000112.html",
    "2009/20090202000321.html",
    "2009/20090203000286.html",
    "2009/20090217000556.html",
    "2009/20090219000109.html",
    "2009/20090220000358.html",
    "2009/20090401000139.html",
    "2009/20090407000077.html",
    "2009/20090414002030.html",
    "2009/20090415002672.html",
    "2009/20090420004502.html",
    "2009/20090422005524.html",
    "2009/20090428008008.html",
    "2009/20090429000500.html",
    "2009/20090511000072.html",
    "2009/20090519000038.html",
    "2009/20090520000048.html",
    "2009/20090601000077.html",
    "2009/20090609000084.html",
    "2009/20090609000120.html",
    "2009/20090624000073.html",
    "2009/20090723000068.html",
    "2009/20090817000088.html",
    "2009/20090820000048.html",
    "2009/20090907000085.html",
    "2009/20090908000063.html",
    "2009/20090921000058.html",
    "2009/20091006000054.html",
    "2009/20091029000067.html",
]
MIXED_RIGHTS_ISSUANCE_50_EXAMPLES = [
    "2008/20081020000088.html",
    "2008/20081113000105.html",
    "2009/20090115000258.html",
    "2009/20090409000111.html",
    "2009/20090414002100.html",
    "2009/20090417003897.html",
    "2009/20090421005143.html",
    "2009/20090429000652.html",
    "2009/20090512000386.html",
    "2009/20090514000328.html",
    "2009/20090518000215.html",
    "2009/20090522000392.html",
    "2009/20090522000408.html",
    "2009/20090602000311.html",
    "2009/20090603000064.html",
    "2009/20090608000211.html",
    "2009/20090609000059.html",
    "2009/20090709000053.html",
    "2009/20090710000644.html",
    "2009/20090724000215.html",
    "2009/20090814000048.html",
    "2009/20090817000109.html",
    "2009/20090824000080.html",
    "2009/20090825000168.html",
    "2009/20090908000304.html",
    "2009/20091012000383.html",
    "2009/20091019000369.html",
    "2009/20091020000083.html",
    "2009/20091105000359.html",
    "2009/20091118000158.html",
    "2009/20091119000019.html",
    "2009/20091120000516.html",
    "2009/20091204000460.html",
    "2009/20091210000149.html",
    "2010/20100113000108.html",
    "2010/20100122000421.html",
    "2010/20100303000087.html",
    "2010/20100304000051.html",
    "2010/20100324000212.html",
    "2010/20100402000097.html",
    "2010/20100416000054.html",
    "2010/20100423000360.html",
    "2010/20100614000199.html",
    "2010/20100618000053.html",
    "2010/20100730000385.html",
    "2010/20100824000091.html",
    "2010/20100824000166.html",
    "2010/20100910000399.html",
    "2010/20100927000095.html",
    "2010/20101004000068.html",
]
HTML_PARSE_MODES_DOC = (
    REPO_ROOT / "docs" / "disclosures" / "07-html-parse" / "modes" / "README.md"
)
GUI_APP_DIR = REPO_ROOT / "frontend" / "finiq_GUI" / "apps" / "market-desk" / "src" / "app"
GUI_EXTERNAL_HTML_DOWNLOAD_PAGE = GUI_APP_DIR / "external-html-download" / "page.tsx"
GUI_EXTERNAL_HTML_DOWNLOAD_COMPONENT = GUI_APP_DIR / "external-html-download" / "_components" / "DisclosureHtmlDownloadPageView.tsx"
GUI_INTERNAL_HTML_DOWNLOAD_PAGE = GUI_APP_DIR / "internal-html-download" / "page.tsx"
GUI_HTML_SECTION_SPLIT_PAGE = GUI_APP_DIR / "html-section-split" / "page.tsx"
GUI_HTML_SECTION_SPLIT_RESULTS_COMPONENT = GUI_APP_DIR / "html-section-split" / "_components" / "HtmlSectionSplitResults.tsx"
GUI_HTML_PARSE_PAGE = GUI_APP_DIR / "html-parse" / "page.tsx"
GUI_HTML_CHANGE_LOG_PAGE = GUI_APP_DIR / "html-change-log" / "page.tsx"
GUI_UTILITY_PAGE = GUI_APP_DIR / "utility" / "page.tsx"
EXPECTED_PARSE_MODES = {
    "bond_issuance",
    "rights_issuance",
    "shareholder_meeting",
    "asset_transaction",
    "security_transaction",
}


def _sqlite_manifest_path(path: Path) -> Path:
    return path.parent / "sqlite_manifest.json"


def _external_workspace_body(
    tmp_path: Path, source_json: dict[str, Any], **body: object
) -> dict[str, object]:
    data_root = tmp_path / "workspace"
    filtered_path = data_root / "03-filter" / "bond_issuance" / "filtered.json"
    filtered_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_source_json = dict(source_json)
    if isinstance(source_json.get("disclosures"), list):
        normalized_source_json["disclosures"] = [
            {
                **disclosure,
                "disclosed_at": disclosure.get("disclosed_at")
                or f"{str(disclosure.get('acpt_no') or '')[:4]}-01-01",
            }
            for disclosure in source_json["disclosures"]
            if isinstance(disclosure, dict)
        ]
    filtered_path.write_text(
        json.dumps(
            {
                "format": "kind_disclosure_filter_v1",
                **normalized_source_json,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {"data_root": str(data_root), "mode": "bond_issuance", **body}


def _build_download_result_page_html(
    *,
    page_number: int,
    page_size: int,
    total_items: int,
) -> bytes:
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    row_count = page_size if page_number < total_pages else total_items - (page_size * (total_pages - 1))
    rows = []
    for row_index in range(row_count):
        item_no = ((page_number - 1) * page_size) + row_index + 1
        rows.append(
            f"""
            <tr>
              <td>{item_no}</td>
              <td>2025-01-01 09:00</td>
              <td><a id="companysum" title="테스트회사" onclick="companysummary_open('000001')">테스트회사</a></td>
              <td><a title="테스트 공시" onclick="openDisclsViewer('20250101000001','')">테스트 공시</a></td>
              <td>테스트제출인</td>
            </tr>
            """
        )
    return (
        f"""
        <html>
          <body>
            <section class="paging-group">
              <div class="paging type-00">
                전체 <em>{total_items}</em>건 : <strong>{page_number}</strong>/{total_pages}
              </div>
            </section>
            <table class="list" summary="번호, 일시, 회사명, 공시제목, 제출인">
              <tbody>{''.join(rows)}</tbody>
            </table>
          </body>
        </html>
        """
    ).encode("utf-8")


def _valid_download_html() -> str:
    return "<html><body>" + ("valid " * 30) + "</body></html>"


def _trusted_download_input_snapshot(
    *,
    start_date: str = "2026-01-01",
    end_date: str = "2026-05-01",
    page_size: int = 100,
) -> dict[str, object]:
    return {
        "format": KIND_WORKFLOW_INPUT_FORMAT,
        "request_headers": {"User-Agent": "pytest"},
        "start_date": start_date,
        "end_date": end_date,
        "page_size": page_size,
        "search_filters": [],
        "disclosure_type_groups": {},
        "last_report_only": False,
        "include_previous_disclosures": None,
        "wait_seconds_between_requests": 1.0,
        "timeout": 20.0,
    }


def _filter_block(**overrides: object) -> dict[str, object]:
    return {
        "connector": "",
        "open_count": 0,
        "close_count": 0,
        "not": False,
        "ignore_spaces": False,
        "clean_search": False,
        **overrides,
    }


def _html_parse_metadata_paths(
    *,
    filtered_path: Path | None = None,
    compressed_path: Path | None = None,
) -> dict[str, str]:
    paths: dict[str, str] = {}
    if filtered_path is not None:
        payload = json.loads(filtered_path.read_text(encoding="utf-8"))
        payload["format"] = "kind_disclosure_filter_v1"
        for disclosure in payload["disclosures"]:
            disclosure.setdefault("disclosed_at", "2025-01-01 09:00")
        filtered_path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        paths["filtered_metadata_path"] = str(filtered_path)
    if compressed_path is not None:
        payload = json.loads(compressed_path.read_text(encoding="utf-8"))
        payload["format"] = "finiq_disclosure_external_html_docs_v1"
        for record in payload["records"]:
            record.setdefault("selected_main_doc_no", f"{record['acpt_no']}01")
            record.setdefault("metadata", {})
        compressed_path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        paths["compressed_metadata_path"] = str(compressed_path)
    return paths


def _html_parse_file(
    input_directory: Path, filename: str, *, year: str | None = None
) -> Path:
    year_directory = input_directory / (year or filename[:4])
    year_directory.mkdir(parents=True, exist_ok=True)
    return year_directory / filename


def _classification_fixture_payload() -> dict[str, object]:
    return {
        "summary": {"companies": 1, "disclosures": 3},
        "companies": [
            {
                "company_name": "테스트전자",
                "company_id": "005930",
                "market": "코스피",
                "badges": ["우량주"],
                "disclosures": [
                    {
                        "disclosed_at": "2025-01-02 09:00:00",
                        "title": "[정정]전환사채발행결정",
                        "title_attr": "전환사채발행결정",
                        "title_base": "전환사채발행결정",
                        "title_display": "[정정]전환사채발행결정",
                        "title_flags": ["정정"],
                        "is_correction_report": True,
                        "has_later_correction": False,
                        "submitter": "테스트전자",
                        "acpt_no": "1",
                        "doc_no": "10",
                    },
                    {
                        "disclosed_at": "2025-01-10 09:00:00",
                        "title": "기타 주요경영사항",
                        "submitter": "테스트전자",
                        "acpt_no": "2",
                    },
                    {
                        "disclosed_at": "2025-01-15 09:00:00",
                        "title": "주주총회소집결의",
                        "submitter": "테스트전자",
                        "acpt_no": "3",
                    },
                ],
            }
        ],
    }


def _write_classification_fixture(
    tmp_path: Path, payload: dict[str, object] | None = None
) -> Path:
    fixture_path = tmp_path / "kind.company_classification.sqlite"
    return write_company_classification_artifact(
        fixture_path,
        payload or _classification_fixture_payload(),
        compact=False,
    )


def _write_filter_manifest_fixture(
    tmp_path: Path, payload: dict[str, object] | None = None
) -> Path:
    source_payload = payload or _classification_fixture_payload()
    rows_by_year: dict[str, list[dict[str, Any]]] = {}
    company_keys: set[str] = set()
    for company in source_payload["companies"]:
        company_key = str(company["company_id"])
        company_keys.add(company_key)
        for row_number, disclosure in enumerate(company["disclosures"], start=1):
            disclosed_at = str(disclosure.get("disclosed_at") or "")
            year = disclosed_at[:4]
            row = {
                "row_no": str(row_number),
                "company_key": company_key,
                "company_name": company.get("company_name"),
                "company_id": company.get("company_id"),
                "company_cell_text": company.get("company_name"),
                "market": company.get("market"),
                "badges_json": json.dumps(company.get("badges") or []),
                "disclosed_at": disclosed_at,
                "disclosed_date": disclosed_at.split(" ", 1)[0],
                "title": disclosure.get("title"),
                "title_attr": disclosure.get("title_attr"),
                "title_base": disclosure.get("title_base"),
                "title_display": disclosure.get("title_display"),
                "title_flags_json": json.dumps(disclosure.get("title_flags") or []),
                "is_correction_report": int(bool(disclosure.get("is_correction_report"))),
                "has_later_correction": int(bool(disclosure.get("has_later_correction"))),
                "acpt_no": disclosure.get("acpt_no"),
                "doc_no": disclosure.get("doc_no"),
                "submitter": disclosure.get("submitter"),
                "source_file": "fixture.body",
                "source_page": 1,
            }
            rows_by_year.setdefault(year, []).append(row)

    table_root = tmp_path / "02-table"
    manifest_path = table_root / "sqlite_manifest.json"
    shards = [
        table_export_module._write_sqlite_shard(
            shard_path=table_root / f"{year}.sqlite",
            rows=rows,
            source_path=tmp_path,
            source_type="source_folder",
            table_name="disclosures",
            shard_year=year,
        )
        for year, rows in sorted(rows_by_year.items())
    ]
    row_count = sum(len(rows) for rows in rows_by_year.values())
    table_export_module._write_manifest(
        manifest_path,
        {
            "format": "finiq_disclosure_table_manifest_v1",
            "schema_version": 3,
            "source_type": "source_folder",
            "source_path": str(tmp_path),
            "manifest_path": str(manifest_path),
            "shard_root": str(table_root),
            "table_name": "disclosures",
            "summary": {
                "companies": len(company_keys),
                "source_rows": row_count,
                "duplicate_rows": 0,
                "disclosures": row_count,
                "unlinked_disclosures": 0,
                "shards": len(shards),
            },
            "pages": [
                {
                    "source_file": "fixture.body",
                    "source_page": 1,
                    "source_rows": row_count,
                    "written_rows": row_count,
                    "duplicate_rows": 0,
                }
            ],
            "shards": shards,
        },
    )
    return manifest_path


def _write_source_body_fixture(tmp_path: Path) -> Path:
    source_dir = tmp_path / "20250101_20250131"
    source_dir.mkdir()
    (source_dir / "kind_workflow.input.json").write_text(
        json.dumps(
            _trusted_download_input_snapshot(
                start_date="2025-01-01",
                end_date="2025-01-31",
            )
        ),
        encoding="utf-8",
    )
    (source_dir / "001_post_page_00001.body").write_text(
        """
        <html><body>
          <section class="paging-group">
            <div class="paging type-00">
              전체 <em>2</em>건 : <strong>1</strong>/1
            </div>
          </section>
          <table summary="회사명 공시제목">
            <tbody>
              <tr>
                <td>1</td>
                <td>2025-01-02 09:00</td>
                <td>
                  <img alt="코스피">
                  <a id="companysum" onclick="companysummary_open('005930'); return false;" title="테스트전자">테스트전자</a>
                </td>
                <td>
                  <a onclick="openDisclsViewer('20250102000001','20250102009999')" title="전환사채발행결정"><font color="#FF8040">[정정]</font>전환사채발행결정<img alt="해당보고서 이후에 정정된 보고서 있음"></a>
                </td>
                <td>테스트전자</td>
              </tr>
              <tr>
                <td>2</td>
                <td>2025-01-03 09:00</td>
                <td>
                  <img alt="코스닥">
                  <a id="companysum" onclick="companysummary_open('000001'); return false;" title="다른회사">다른회사</a>
                </td>
                <td>
                  <a onclick="openDisclsViewer('20250103000001','')" title="주주총회소집결의">주주총회소집결의</a>
                </td>
                <td>다른회사</td>
              </tr>
            </tbody>
          </table>
        </body></html>
        """,
        encoding="utf-8",
    )
    return tmp_path


def test_list_classification_files(tmp_path: Path) -> None:
    fixture_path = _write_classification_fixture(tmp_path)
    files = list_classification_files(tmp_path)
    assert files[0]["path"] == str(fixture_path)
    assert files[0]["name"] == fixture_path.name
    assert files[0]["label"].endswith(fixture_path.name)


def test_load_company_index_payload_filters_market(tmp_path: Path) -> None:
    fixture_path = _write_classification_fixture(tmp_path)
    payload = load_company_index_payload(fixture_path, market="코스피")
    assert payload["summary"]["filtered_companies"] == 1
    assert payload["companies"][0]["company_name"] == "테스트전자"


def test_filter_disclosures_payload_filters_by_title_and_date(tmp_path: Path) -> None:
    manifest_path = _write_filter_manifest_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "title_keywords": "전환사채",
            "start_date": "2025-01-01",
            "end_date": "2025-01-05",
        }
    )

    assert payload["format"] == "kind_disclosure_filter_v1"
    assert payload["summary"]["matched_disclosures"] == 1
    assert payload["disclosures"][0]["acpt_no"] == "1"
    assert payload["disclosures"][0]["company_name"] == "테스트전자"
    assert payload["unique_titles"] == ["[정정]전환사채발행결정"]


def test_search_disclosure_titles_payload_returns_distinct_db_titles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:
    _write_filter_manifest_fixture(tmp_path)
    progress: list[dict[str, object]] = []
    monkeypatch.setattr(
        service_payloads_module,
        "filter_disclosures_payload",
        lambda *_args, **_kwargs: pytest.fail(
            "title search must query SQLite instead of scanning filter results"
        ),
    )

    payload = search_disclosure_titles_payload(
        {
            "data_root": str(tmp_path),
            "filter_workers": 2,
            "progress_interval": 1,
            "filter_blocks": [
                _filter_block(
                    field="title",
                    operator="contains",
                    value="결의",
                )
            ],
        },
        progress_callback=progress.append,
    )

    assert payload["format"] == "finiq_disclosure_title_search_v1"
    assert payload["summary"] == {
        "source_disclosures": 3,
        "matched_disclosures": 1,
        "matched_titles": 1,
    }
    assert payload["titles"] == [
        {"title": "주주총회소집결의", "disclosures": 1}
    ]
    assert payload["filters"]["filter_workers"] == 1
    assert progress[-1]["completed"] == 3
    assert "disclosures" not in payload


def test_search_disclosure_titles_payload_applies_shared_boolean_conditions_in_sqlite(
    tmp_path: Path,
) -> None:
    _write_filter_manifest_fixture(tmp_path)

    payload = search_disclosure_titles_payload(
        {
            "data_root": str(tmp_path),
            "filter_blocks": [
                _filter_block(
                    field="title",
                    operator="contains",
                    value="전환사채",
                    open_count=1,
                ),
                _filter_block(
                    connector="OR",
                    field="title",
                    operator="contains",
                    value="주주총회",
                    close_count=1,
                ),
                _filter_block(
                    connector="AND",
                    field="market",
                    operator="equals",
                    value="코스피",
                ),
            ],
        }
    )

    assert payload["summary"]["matched_disclosures"] == 2
    assert payload["titles"] == [
        {"title": "[정정]전환사채발행결정", "disclosures": 1},
        {"title": "주주총회소집결의", "disclosures": 1},
    ]


def test_filter_disclosures_payload_filters_only_rows_after_source_offset(
    tmp_path: Path,
) -> None:
    _write_filter_manifest_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "source_offset": 2,
            "source_expected_count": 3,
        }
    )

    assert payload["summary"]["source_disclosures"] == 3
    assert payload["summary"]["source_offset"] == 2
    assert payload["summary"]["target_disclosures"] == 1
    assert payload["summary"]["inspected_disclosures"] == 1
    assert [row["acpt_no"] for row in payload["disclosures"]] == ["3"]
    assert payload["integrity"] == {
        "complete": True,
        "passed": True,
        "search_target_disclosures": 1,
        "search_result_disclosures": 1,
        "inspected_disclosures": 1,
    }


@pytest.mark.parametrize("field", ["source_offset", "source_expected_count"])
def test_filter_disclosures_payload_rejects_fractional_incremental_counts(
    tmp_path: Path,
    field: str,
) -> None:
    _write_filter_manifest_fixture(tmp_path)

    with pytest.raises(ValueError, match=rf"{field} must be an integer"):
        filter_disclosures_payload(
            {
                "data_root": str(tmp_path),
                field: 1.5,
            }
        )


def test_filter_disclosures_payload_offset_skips_complete_year_shards(
    tmp_path: Path,
) -> None:
    source = _classification_fixture_payload()
    disclosures = source["companies"][0]["disclosures"]
    disclosures[0]["disclosed_at"] = "2024-01-02 09:00:00"
    disclosures[1]["disclosed_at"] = "2025-01-10 09:00:00"
    disclosures[2]["disclosed_at"] = "2026-01-15 09:00:00"
    _write_filter_manifest_fixture(tmp_path, source)

    payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "source_offset": 2,
            "source_expected_count": 3,
        }
    )

    assert payload["summary"]["target_disclosures"] == 1
    assert [row["acpt_no"] for row in payload["disclosures"]] == ["3"]


@pytest.mark.parametrize("previous_count", [2, 4])
def test_filter_disclosures_payload_retries_from_start_when_source_count_changes(
    tmp_path: Path,
    previous_count: int,
) -> None:
    _write_filter_manifest_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "source_offset": 2,
            "source_expected_count": previous_count,
        }
    )

    assert payload["summary"]["source_offset"] == 0
    assert payload["summary"]["target_disclosures"] == 3
    assert [row["acpt_no"] for row in payload["disclosures"]] == ["3", "2", "1"]


def test_filter_disclosures_payload_returns_integrity_checked_partial_on_cancel(
    tmp_path: Path,
) -> None:
    _write_filter_manifest_fixture(tmp_path)
    checks = 0

    def cancel_check() -> bool:
        nonlocal checks
        checks += 1
        return checks > 2

    with pytest.raises(FilterCancelled) as raised:
        filter_disclosures_payload(
            {"data_root": str(tmp_path)}, cancel_check=cancel_check
        )

    partial = raised.value.partial_payload
    assert partial is not None
    assert partial["summary"]["source_disclosures"] == 3
    assert partial["summary"]["inspected_disclosures"] == 1
    assert partial["integrity"]["complete"] is False
    assert partial["integrity"]["passed"] is False


def test_filter_disclosures_payload_rejects_root_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="root_directory is not supported"):
        filter_disclosures_payload({"root_directory": str(tmp_path)})


def test_filter_disclosures_payload_rejects_source_folder(tmp_path: Path) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    with pytest.raises(ValueError, match="root_directory is not supported"):
        filter_disclosures_payload({"root_directory": str(source_root)})


def test_filter_disclosures_payload_rejects_root_directory_before_path_resolution() -> None:
    root = Path(Path.cwd().anchor).resolve()

    with pytest.raises(ValueError, match="root_directory is not supported"):
        filter_disclosures_payload({"root_directory": str(root)})


def test_filter_disclosures_payload_requires_data_root() -> None:
    with pytest.raises(ValueError, match="data_root is required"):
        filter_disclosures_payload({})


@pytest.mark.parametrize("direct_path", ["02-table", "02-table/sqlite_manifest.json"])
def test_filter_disclosures_payload_rejects_direct_manifest_inputs(
    tmp_path: Path, direct_path: str
) -> None:
    with pytest.raises(ValueError, match="classification_path is not supported"):
        filter_disclosures_payload(
            {"classification_path": str(tmp_path / direct_path)}
        )


def test_filter_disclosures_payload_uses_standard_manifest_name(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    data_root = tmp_path / "workspace"
    sqlite_root = data_root / "02-table"
    requested_path = sqlite_root / "custom.sqlite_manifest.json"
    manifest_path = _sqlite_manifest_path(requested_path)
    build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(requested_path),
        }
    )

    payload = filter_disclosures_payload({"data_root": str(data_root)})

    assert not requested_path.exists()
    assert "source_sqlite_manifest_path" not in payload


def test_filter_disclosures_payload_finds_manifest_from_data_root(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    source_root = data_root / "01-list"
    source_root.mkdir(parents=True)
    _write_source_body_fixture(source_root)
    output_path = data_root / "02-table" / "kind.sqlite_manifest.json"
    manifest_path = _sqlite_manifest_path(output_path)
    build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_path),
        }
    )

    payload = filter_disclosures_payload({"data_root": str(data_root)})

    assert payload["source_type"] == "sqlite_manifest"
    assert "source_sqlite_manifest_path" not in payload
    assert payload["summary"]["source_disclosures"] == 2


def test_filter_disclosures_payload_rejects_missing_manifest_shard_path(tmp_path: Path) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    data_root = tmp_path / "workspace"
    sqlite_root = data_root / "02-table"
    output_path = sqlite_root / "kind.sqlite_manifest.json"
    manifest_path = _sqlite_manifest_path(output_path)
    build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_path),
        }
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for shard in manifest["shards"]:
        shard["relative_path"] = "missing.sqlite"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="연도별 SQLite 파일을 찾을 수 없습니다"):
        filter_disclosures_payload(
            {
                "data_root": str(data_root),
                "filter_blocks": [
                    _filter_block(
                        field="title",
                        operator="contains",
                        value="전환사채",
                    )
                ],
            }
        )


def test_filter_disclosures_payload_does_not_search_nested_kind_sqlite_manifest(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    root = tmp_path / "kind_kosdaq"
    sqlite_root = root / "nested-table"
    output_path = sqlite_root / "kind_kosdaq.sqlite_manifest.json"
    manifest_path = _sqlite_manifest_path(output_path)
    build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_path),
        }
    )

    with pytest.raises(FileNotFoundError, match="02-table/sqlite_manifest.json"):
        filter_disclosures_payload({"data_root": str(root)})


def test_filter_disclosures_payload_rejects_sqlite_manifest_without_row_no_column(
    tmp_path: Path,
) -> None:
    sqlite_root = tmp_path / "02-table"
    shard_root = sqlite_root
    shard_root.mkdir(parents=True)
    shard_path = shard_root / "2025.sqlite"
    connection = sqlite3.connect(shard_path)
    try:
        connection.execute(
            """
            CREATE TABLE disclosures (
                id INTEGER PRIMARY KEY,
                company_key TEXT,
                company_name TEXT,
                company_id TEXT,
                market TEXT,
                disclosed_at TEXT,
                disclosed_date TEXT,
                title TEXT,
                title_attr TEXT,
                title_base TEXT,
                title_display TEXT,
                title_flags_json TEXT NOT NULL DEFAULT '[]',
                is_correction_report INTEGER NOT NULL DEFAULT 0,
                has_later_correction INTEGER NOT NULL DEFAULT 0,
                acpt_no TEXT,
                doc_no TEXT,
                submitter TEXT,
                source_file TEXT,
                source_page INTEGER
            )
            """
        )
        connection.execute(
            """
            INSERT INTO disclosures (
                company_key, company_name, company_id, market, disclosed_at, disclosed_date,
                title, title_attr, title_base, title_display, title_flags_json,
                is_correction_report, has_later_correction, acpt_no, doc_no, submitter,
                source_file, source_page
            )
            VALUES (
                '005930', '테스트전자', '005930', '코스피', '2025-01-02 09:00:00', '2025-01-02',
                '전환사채발행결정', '전환사채발행결정', '전환사채발행결정', '전환사채발행결정', '[]',
                0, 0, '1', '10', '테스트전자', '', 1
            )
            """
        )
        connection.commit()
    finally:
        connection.close()
    manifest_path = shard_root / "sqlite_manifest.json"
    manifest_path.write_text(
        json.dumps(
                {
                    "format": "finiq_disclosure_table_manifest_v1",
                    "schema_version": 3,
                    "table_name": "disclosures",
                    "summary": {
                        "companies": 1,
                        "disclosures": 1,
                        "unlinked_disclosures": 0,
                        "shards": 1,
                    },
                    "shards": [
                            {
                                "year": "2025",
                                "path": str(shard_path),
                                "relative_path": shard_path.name,
                            "companies": 1,
                            "disclosures": 1,
                            "unlinked_disclosures": 0,
                        }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match="SQLite table is missing required column: row_no"
    ):
        filter_disclosures_payload(
            {
                "data_root": str(tmp_path),
                "filter_blocks": [
                    _filter_block(
                        field="title", operator="contains", value="전환사채"
                    )
                ],
            }
        )


def test_filter_disclosures_payload_rejects_nonstandard_sqlite_manifest_name(
    tmp_path: Path,
) -> None:
    table_root = tmp_path / "02-table"
    table_root.mkdir(parents=True)
    manifest_path = table_root / "kind.sqlite_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_table_manifest_v1",
                "table_name": "disclosures",
                "summary": {"companies": 0, "disclosures": 0, "shards": 0},
                "shards": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="02-table/sqlite_manifest.json"):
        filter_disclosures_payload({"data_root": str(tmp_path)})


def test_filter_disclosures_payload_rejects_sqlite_manifest_count_mismatch(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    sqlite_root = tmp_path / "02-table"
    output_path = sqlite_root / "kind.sqlite_manifest.json"
    manifest_path = _sqlite_manifest_path(output_path)
    build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_path),
        }
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 2
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="schema_version must be 3"):
        filter_disclosures_payload({"data_root": str(tmp_path)})

    manifest["schema_version"] = 3
    manifest["shards"][0]["disclosures"] = 3
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="연도별 SQLite 파일의 공시 건수가 다릅니다"):
        filter_disclosures_payload({"data_root": str(tmp_path)})


def test_sqlite_manifest_count_validation_runs_shards_in_parallel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = tmp_path / "sqlite_manifest.json"
    shard_names = ["2024.sqlite3", "2025.sqlite3"]
    for shard_name in shard_names:
        connection = sqlite3.connect(tmp_path / shard_name)
        try:
            connection.execute(
                "CREATE TABLE disclosures (row_no INTEGER, company_key TEXT)"
            )
            connection.execute("INSERT INTO disclosures VALUES (1, 'company-1')")
            connection.commit()
        finally:
            connection.close()

    original_connect = sqlite3.connect
    barrier = threading.Barrier(2)

    class BlockingConnection:
        def __init__(self, path: Path) -> None:
            self.connection = original_connect(path)

        def execute(self, sql: str):
            barrier.wait(timeout=2)
            return self.connection.execute(sql)

        def close(self) -> None:
            self.connection.close()

    monkeypatch.setattr(
        service_sources_module.sqlite3,
        "connect",
        lambda path: BlockingConnection(path),
    )

    _validate_sqlite_manifest_counts(
        manifest_path,
        {
            "schema_version": 3,
            "table_name": "disclosures",
            "summary": {"disclosures": 2, "unlinked_disclosures": 0},
            "shards": [
                {
                    "relative_path": shard_name,
                    "disclosures": 1,
                    "unlinked_disclosures": 0,
                }
                for shard_name in shard_names
            ],
        },
        filter_workers=2,
    )


def test_filter_disclosures_payload_rejects_unaccounted_source_rows(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    sqlite_root = tmp_path / "02-table"
    output_path = sqlite_root / "kind.sqlite_manifest.json"
    manifest_path = _sqlite_manifest_path(output_path)
    build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_path),
        }
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["summary"]["source_rows"] = 3
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="did not account for every source disclosure row"):
        filter_disclosures_payload({"data_root": str(tmp_path)})


def test_filter_disclosures_payload_rejects_unaccounted_page_rows(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    sqlite_root = tmp_path / "02-table"
    output_path = sqlite_root / "kind.sqlite_manifest.json"
    manifest_path = _sqlite_manifest_path(output_path)
    build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_path),
        }
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pages"][0]["written_rows"] = 1
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="page did not account for every source row"):
        filter_disclosures_payload({"data_root": str(tmp_path)})


def test_filter_disclosures_payload_reports_sqlite_progress(tmp_path: Path) -> None:
    fixture_path = _write_filter_manifest_fixture(tmp_path)
    progress_events = []

    payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "progress_interval": 1,
        },
        progress_callback=progress_events.append,
    )

    assert payload["source_type"] == "sqlite_manifest"
    assert payload["summary"]["matched_disclosures"] == 3
    assert any(event["unit_label"] == "공시" and event["total"] == 3 for event in progress_events)


def test_filter_disclosures_payload_supports_title_include_and_exclude_keywords(tmp_path: Path) -> None:
    _write_filter_manifest_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "title_keywords": "전환사채\n주주총회",
            "exclude_title_keywords": "주주총회",
            "title_match_mode": "or",
        }
    )

    assert [disclosure["acpt_no"] for disclosure in payload["disclosures"]] == ["1"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("공정공시(무슨사항에대한공시)공시내용", "공정공시공시내용"),
        ("공정공시((주)삼성전자)공시내용", "공정공시공시내용"),
        ("공정공시((주)삼성전자))공시내용", "공정공시공시내용"),
        ("공정공시(((주)삼성전자)공시내용", "공정공시공시내용"),
    ],
)
def test_clean_search_text_removes_parenthesized_title_fragments(value: str, expected: str) -> None:
    assert _clean_search_text(value) == expected


def test_filter_disclosures_payload_supports_clean_search_title_blocks(tmp_path: Path) -> None:
    payload = _classification_fixture_payload()
    payload["companies"][0]["disclosures"].append(
        {
            "disclosed_at": "2025-01-20 09:00:00",
            "title": "공정공시(((주)삼성전자)공시내용",
            "submitter": "테스트전자",
            "acpt_no": "4",
        }
    )
    payload["summary"]["disclosures"] = 4
    _write_filter_manifest_fixture(tmp_path, payload)

    filtered_payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "filter_blocks": [
                _filter_block(
                    field="title",
                    operator="contains",
                    value="공정공시공시내용",
                    clean_search=True,
                )
            ],
        }
    )

    assert [disclosure["acpt_no"] for disclosure in filtered_payload["disclosures"]] == ["4"]


def test_filter_disclosures_payload_cleans_unique_titles_and_places_them_before_rows(tmp_path: Path) -> None:
    payload = _classification_fixture_payload()
    payload["companies"][0]["disclosures"].append(
        {
            "disclosed_at": "2025-01-20 09:00:00",
            "title": "공정공시((주)삼성전자)공시내용",
            "submitter": "테스트전자",
            "acpt_no": "4",
        }
    )
    payload["summary"]["disclosures"] = 4
    _write_filter_manifest_fixture(tmp_path, payload)

    filtered_payload = filter_disclosures_payload({"data_root": str(tmp_path)})

    assert filtered_payload["unique_titles"][0] == "공정공시공시내용"
    assert list(filtered_payload).index("unique_titles") < list(filtered_payload).index("disclosures")


def test_filter_disclosures_payload_can_return_without_limit(tmp_path: Path) -> None:
    _write_filter_manifest_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "limit": 1,
            "limit_unlimited": True,
        }
    )

    assert payload["filters"]["limit"] is None
    assert payload["filters"]["limit_unlimited"] is True
    assert payload["summary"]["matched_disclosures"] == 3
    assert payload["summary"]["returned_disclosures"] == 3
    assert [disclosure["acpt_no"] for disclosure in payload["disclosures"]] == ["3", "2", "1"]


def test_filter_disclosures_payload_ignores_return_limit(tmp_path: Path) -> None:
    _write_filter_manifest_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "limit_unlimited": True,
            "return_limit": 1,
            "include_external_html_download_acpt_numbers": True,
        }
    )

    assert payload["filters"]["limit"] is None
    assert payload["filters"]["limit_unlimited"] is True
    assert payload["filters"]["return_limit"] is None
    assert payload["summary"]["matched_disclosures"] == 3
    assert payload["summary"]["returned_disclosures"] == 3
    assert [disclosure["acpt_no"] for disclosure in payload["disclosures"]] == ["3", "2", "1"]
    assert payload["external_html_download_acpt_numbers"] == ["3", "2", "1"]


def test_filter_disclosures_payload_deduplicates_by_acpt_no(tmp_path: Path) -> None:
    payload = _classification_fixture_payload()
    duplicate = dict(payload["companies"][0]["disclosures"][0])
    duplicate["disclosed_at"] = "2025-01-03 10:00:00"
    duplicate["title"] = "다른 제목"
    payload["companies"][0]["disclosures"].append(duplicate)
    payload["summary"]["disclosures"] = 4
    _write_filter_manifest_fixture(tmp_path, payload)

    filtered_payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "include_external_html_download_acpt_numbers": True,
        }
    )

    assert filtered_payload["summary"]["source_disclosures"] == 4
    assert filtered_payload["summary"]["matched_disclosures"] == 3
    assert filtered_payload["summary"]["returned_disclosures"] == 3
    assert filtered_payload["summary"]["duplicate_disclosures"] == 1
    assert [disclosure["acpt_no"] for disclosure in filtered_payload["disclosures"]] == ["3", "2", "1"]
    assert filtered_payload["unique_titles"] == ["주주총회소집결의", "기타 주요경영사항", "[정정]전환사채발행결정"]
    assert filtered_payload["external_html_download_acpt_numbers"] == ["3", "2", "1"]


def test_filter_disclosures_payload_rejects_missing_acpt_no(tmp_path: Path) -> None:
    payload = _classification_fixture_payload()
    payload["companies"][0]["disclosures"][0].pop("acpt_no")
    _write_filter_manifest_fixture(tmp_path, payload)

    with pytest.raises(ValueError, match="acpt_no is required"):
        filter_disclosures_payload({"data_root": str(tmp_path)})


def test_filter_disclosures_progress_interval_defaults_to_1000() -> None:
    assert _progress_interval(None) == 1000
    with pytest.raises(ValueError, match="must be an integer"):
        _progress_interval("invalid")


def test_filter_disclosures_payload_supports_title_boolean_expression(tmp_path: Path) -> None:
    _write_filter_manifest_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "title_expression": '"전환사채" AND "발행결정" OR ("주주총회" AND NOT "정정")',
        }
    )

    assert [disclosure["acpt_no"] for disclosure in payload["disclosures"]] == ["3", "1"]


def test_filter_disclosures_payload_supports_field_filter_blocks(tmp_path: Path) -> None:
    _write_filter_manifest_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "filter_blocks": [
                _filter_block(
                    field="title", operator="contains", value="전환사채"
                ),
                _filter_block(
                    connector="OR",
                    open_count=1,
                    field="market",
                    operator="equals",
                    value="코스피",
                ),
                _filter_block(
                    connector="AND",
                    field="title",
                    operator="contains",
                    value="주주총회",
                    close_count=1,
                ),
            ],
        }
    )

    assert [disclosure["acpt_no"] for disclosure in payload["disclosures"]] == ["3", "1"]


def test_disclosure_filters_support_xor_in_records_and_title_search(
    tmp_path: Path,
) -> None:
    _write_filter_manifest_fixture(tmp_path)
    filter_blocks = [
        _filter_block(
            open_count=1,
            field="title",
            operator="contains",
            value="전환사채",
        ),
        _filter_block(
            connector="XOR",
            field="title",
            operator="contains",
            value="기타",
            close_count=1,
        ),
        _filter_block(
            connector="AND",
            field="market",
            operator="equals",
            value="코스피",
        ),
    ]

    filtered = filter_disclosures_payload(
        {"data_root": str(tmp_path), "filter_blocks": filter_blocks}
    )
    searched = search_disclosure_titles_payload(
        {"data_root": str(tmp_path), "filter_blocks": filter_blocks}
    )

    assert [row["acpt_no"] for row in filtered["disclosures"]] == ["2", "1"]
    assert searched["titles"] == [
        {"title": "[정정]전환사채발행결정", "disclosures": 1},
        {"title": "기타 주요경영사항", "disclosures": 1},
    ]


def test_disclosure_filters_reject_mixed_connectors_without_grouping(
    tmp_path: Path,
) -> None:
    _write_filter_manifest_fixture(tmp_path)
    filter_blocks = [
        _filter_block(field="title", operator="contains", value="전환사채"),
        _filter_block(
            connector="XOR",
            field="title",
            operator="contains",
            value="기타",
        ),
        _filter_block(
            connector="AND",
            field="market",
            operator="equals",
            value="코스피",
        ),
    ]

    with pytest.raises(ValueError, match="must be separated by parentheses"):
        filter_disclosures_payload(
            {"data_root": str(tmp_path), "filter_blocks": filter_blocks}
        )
    with pytest.raises(ValueError, match="must be separated by parentheses"):
        search_disclosure_titles_payload(
            {"data_root": str(tmp_path), "filter_blocks": filter_blocks}
        )


def _badge_filter_fixture_payload() -> dict[str, object]:
    return {
        "summary": {"companies": 3, "disclosures": 3},
        "companies": [
            {
                "company_name": "폐지전자",
                "company_id": "11111",
                "market": "코스닥",
                "badges": ["상장폐지", "관리종목"],
                "disclosures": [
                    {
                        "disclosed_at": "2025-01-02 09:00:00",
                        "title": "최대주주변경",
                        "submitter": "폐지전자",
                        "acpt_no": "d1",
                    }
                ],
            },
            {
                "company_name": "삼성전자",
                "company_id": "00593",
                "market": "유가증권",
                "badges": ["V100", "KOSPI200", "KRX300"],
                "disclosures": [
                    {
                        "disclosed_at": "2025-01-03 09:00:00",
                        "title": "현금ㆍ현물배당결정",
                        "submitter": "삼성전자",
                        "acpt_no": "d2",
                    }
                ],
            },
            {
                "company_name": "한국투자증권",
                "company_id": "03049",
                "market": None,
                "badges": [],
                "disclosures": [
                    {
                        "disclosed_at": "2025-01-04 09:00:00",
                        "title": "ETF 추가 ㆍ 변경상장신청서",
                        "submitter": "한국투자증권",
                        "acpt_no": "d3",
                    }
                ],
            },
        ],
    }


def test_filter_disclosures_payload_matches_any_badge(tmp_path: Path) -> None:
    _write_filter_manifest_fixture(tmp_path, _badge_filter_fixture_payload())

    contains_delisted = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "filter_blocks": [
                _filter_block(field="badges", operator="contains", value="상장폐지"),
            ],
        }
    )
    equals_one_of_many = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "filter_blocks": [
                _filter_block(field="badges", operator="equals", value="KOSPI200"),
            ],
        }
    )
    empty_badges = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "filter_blocks": [
                _filter_block(field="badges", operator="empty", value=""),
            ],
        }
    )
    any_of = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "filter_blocks": [
                _filter_block(field="badges", operator="in", value="관리종목, KOSPI200"),
            ],
        }
    )
    searched = search_disclosure_titles_payload(
        {
            "data_root": str(tmp_path),
            "filter_blocks": [
                _filter_block(field="badges", operator="contains", value="상장폐지"),
            ],
        }
    )

    assert [row["acpt_no"] for row in contains_delisted["disclosures"]] == ["d1"]
    assert contains_delisted["disclosures"][0]["badges"] == ["상장폐지", "관리종목"]
    assert [row["acpt_no"] for row in equals_one_of_many["disclosures"]] == ["d2"]
    assert [row["acpt_no"] for row in empty_badges["disclosures"]] == ["d3"]
    assert [row["acpt_no"] for row in any_of["disclosures"]] == ["d2", "d1"]
    assert searched["titles"] == [{"title": "최대주주변경", "disclosures": 1}]


def test_filter_disclosures_payload_rejects_operators_outside_field_type(
    tmp_path: Path,
) -> None:
    _write_filter_manifest_fixture(tmp_path, _badge_filter_fixture_payload())

    with pytest.raises(ValueError, match="operator is invalid"):
        filter_disclosures_payload(
            {
                "data_root": str(tmp_path),
                "filter_blocks": [
                    _filter_block(
                        field="badges",
                        operator="on_or_before",
                        value="2026-01-02",
                    )
                ],
            }
        )
    with pytest.raises(ValueError, match="operator is invalid"):
        search_disclosure_titles_payload(
            {
                "data_root": str(tmp_path),
                "filter_blocks": [
                    _filter_block(
                        field="market",
                        operator="contains",
                        value="유가",
                    )
                ],
            }
        )


def test_filter_disclosures_payload_can_ignore_spaces_in_block_values(tmp_path: Path) -> None:
    _write_filter_manifest_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "filter_blocks": [
                _filter_block(
                    field="title",
                    operator="contains",
                    value="전환 사채 발행",
                    ignore_spaces=True,
                ),
            ],
        }
    )

    assert [disclosure["acpt_no"] for disclosure in payload["disclosures"]] == ["1"]


def test_filter_disclosures_payload_supports_nested_bond_issuance_filter_blocks(tmp_path: Path) -> None:
    _write_filter_manifest_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "filter_blocks": [
                _filter_block(
                    open_count=2,
                    field="title",
                    operator="contains",
                    value="전환사채",
                    ignore_spaces=True,
                ),
                _filter_block(
                    connector="OR",
                    field="title",
                    operator="contains",
                    value="교환사채",
                    ignore_spaces=True,
                    close_count=1,
                ),
                _filter_block(
                    connector="OR",
                    field="title",
                    operator="contains",
                    value="신주인수권부사채",
                    ignore_spaces=True,
                    close_count=1,
                ),
                _filter_block(
                    connector="AND",
                    field="title",
                    operator="contains",
                    value="발행",
                    ignore_spaces=True,
                ),
            ],
        }
    )

    assert [disclosure["acpt_no"] for disclosure in payload["disclosures"]] == ["1"]


def test_filter_disclosures_payload_supports_exact_match_operator(tmp_path: Path) -> None:
    _write_filter_manifest_fixture(tmp_path)

    partial_payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "filter_blocks": [
                _filter_block(
                    field="title", operator="exact_match", value="전환사채"
                ),
            ],
        }
    )
    exact_payload = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "filter_blocks": [
                _filter_block(
                    field="title",
                    operator="exact_match",
                    value="[정정]전환사채발행결정",
                ),
            ],
        }
    )

    assert partial_payload["disclosures"] == []
    assert [disclosure["acpt_no"] for disclosure in exact_payload["disclosures"]] == ["1"]


def test_build_disclosure_table_payload_writes_yearly_sqlite_manifest(tmp_path: Path) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    output_path = tmp_path / "kind.disclosures.sqlite_manifest.json"
    manifest_path = _sqlite_manifest_path(output_path)

    payload = build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_path),
            "table_name": "disclosures",
        }
    )

    assert payload["format"] == "finiq_disclosure_table_build_v1"
    assert payload["summary"]["companies"] == 2
    assert payload["summary"]["disclosures"] == 2
    assert payload["summary"]["unlinked_disclosures"] == 0
    assert payload["summary"]["shards"] == 1
    assert payload["summary"]["schema_version"] == 3
    assert not output_path.exists()
    assert manifest_path.exists()
    assert payload["output_path"] == str(manifest_path.resolve())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["format"] == "finiq_disclosure_table_manifest_v1"
    assert "source_path" not in manifest
    assert "manifest_path" not in manifest
    assert "shard_root" not in manifest
    assert manifest["shards"][0]["year"] == "2025"
    assert "path" not in manifest["shards"][0]

    shard_path = manifest_path.parent / manifest["shards"][0]["relative_path"]
    assert shard_path.parent == manifest_path.parent
    connection = sqlite3.connect(shard_path)
    try:
        rows = connection.execute(
            """
            SELECT company_name, disclosed_date, title, title_attr, title_flags_json,
                   is_correction_report, has_later_correction, acpt_no, doc_no
            FROM disclosures ORDER BY acpt_no
            """
        ).fetchall()
        metadata = dict(connection.execute("SELECT key, value FROM table_metadata").fetchall())
    finally:
        connection.close()

    assert rows[0] == (
        "테스트전자",
        "2025-01-02",
        "[정정]전환사채발행결정",
        "전환사채발행결정",
        '["정정"]',
        1,
        1,
        "20250102000001",
        "20250102009999",
    )
    assert metadata["format"] == "finiq_disclosure_table_sqlite"
    assert metadata["shard_format"] == "finiq_disclosure_table_sqlite_shard"
    assert metadata["shard_year"] == "2025"
    assert metadata["table_name"] == "disclosures"
    assert metadata["unlinked_disclosures"] == "0"


def test_table_build_publish_failure_preserves_previous_shards_and_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    output_root = tmp_path / "02-table"
    first = build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_root),
        }
    )
    manifest_path = Path(first["manifest_path"])
    shard_path = manifest_path.parent / first["shards"][0]["relative_path"]
    old_manifest = manifest_path.read_bytes()
    old_shard = shard_path.read_bytes()
    body_path = next(source_root.rglob("*_post_page_*.body"))
    body_path.write_text(
        body_path.read_text(encoding="utf-8").replace("전환사채발행결정", "교체된제목"),
        encoding="utf-8",
    )

    original_replace = table_export_module.os.replace

    def fail_manifest_publish(source: Path, target: Path) -> None:
        source_path = Path(source)
        if (
            source_path.name == table_export_module.MANIFEST_FILENAME
            and source_path.parent.name.startswith(".finiq-table-build-")
        ):
            raise OSError("simulated manifest publish failure")
        original_replace(source, target)

    monkeypatch.setattr(table_export_module.os, "replace", fail_manifest_publish)

    with pytest.raises(OSError, match="manifest publish failure"):
        build_disclosure_table_payload(
            {
                "root_directory": str(source_root),
                "output_path": str(output_root),
            }
        )

    assert manifest_path.read_bytes() == old_manifest
    assert shard_path.read_bytes() == old_shard
    assert not list(output_root.glob(".finiq-table-build-*"))


def test_table_generation_publish_waits_for_manifest_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    data_root = tmp_path / "workspace"
    output_root = data_root / "02-table"
    first = build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_root),
        }
    )
    manifest_path = Path(first["manifest_path"])
    shard_path = manifest_path.parent / first["shards"][0]["relative_path"]
    old_manifest = manifest_path.read_bytes()
    old_shard = shard_path.read_bytes()
    body_path = next(source_root.rglob("*_post_page_*.body"))
    body_path.write_text(
        body_path.read_text(encoding="utf-8").replace(
            "전환사채발행결정",
            "교체된제목",
        ),
        encoding="utf-8",
    )

    manifest_loaded = threading.Event()
    release_reader = threading.Event()
    publish_waiting = threading.Event()
    original_load = service_payloads_module._load_sqlite_manifest
    original_publish = table_export_module._publish_sqlite_generation

    def pause_after_manifest_load(path: Path) -> dict[str, Any]:
        manifest = original_load(path)
        manifest_loaded.set()
        assert release_reader.wait(timeout=5)
        return manifest

    def track_publish(**kwargs: Any) -> None:
        publish_waiting.set()
        original_publish(**kwargs)

    monkeypatch.setattr(
        service_payloads_module,
        "_load_sqlite_manifest",
        pause_after_manifest_load,
    )
    monkeypatch.setattr(
        table_export_module,
        "_publish_sqlite_generation",
        track_publish,
    )

    reader_result: dict[str, Any] = {}
    failures: list[BaseException] = []

    def read_generation() -> None:
        try:
            reader_result.update(
                filter_disclosures_payload(
                    {"data_root": str(data_root), "filter_blocks": []}
                )
            )
        except BaseException as error:
            failures.append(error)

    def publish_generation() -> None:
        try:
            build_disclosure_table_payload(
                {
                    "root_directory": str(source_root),
                    "output_path": str(output_root),
                }
            )
        except BaseException as error:
            failures.append(error)

    reader = threading.Thread(target=read_generation)
    writer = threading.Thread(target=publish_generation)
    reader.start()
    assert manifest_loaded.wait(timeout=5)
    writer.start()
    assert publish_waiting.wait(timeout=5)

    assert writer.is_alive()
    assert manifest_path.read_bytes() == old_manifest
    assert shard_path.read_bytes() == old_shard

    release_reader.set()
    reader.join(timeout=5)
    writer.join(timeout=5)

    assert not reader.is_alive()
    assert not writer.is_alive()
    assert failures == []
    assert all(
        "교체된제목" not in disclosure["title"]
        for disclosure in reader_result["disclosures"]
    )
    refreshed = filter_disclosures_payload(
        {"data_root": str(data_root), "filter_blocks": []}
    )
    assert any(
        "교체된제목" in disclosure["title"]
        for disclosure in refreshed["disclosures"]
    )


def test_table_build_and_inspection_each_inventory_source_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    output_path = tmp_path / "02-table"
    original_walk = table_export_module.os.walk
    original_inventory_page_number = table_export_module.result_page_number
    original_parser_page_number = service_sources_module._result_page_number
    walk_count = 0
    inventory_page_number_count = 0
    parser_page_number_count = 0

    def tracked_walk(*args: Any, **kwargs: Any):
        nonlocal walk_count
        walk_count += 1
        yield from original_walk(*args, **kwargs)

    def tracked_inventory_page_number(path: Path) -> int:
        nonlocal inventory_page_number_count
        inventory_page_number_count += 1
        return original_inventory_page_number(path)

    def tracked_parser_page_number(path: Path) -> int:
        nonlocal parser_page_number_count
        parser_page_number_count += 1
        return original_parser_page_number(path)

    monkeypatch.setattr(table_export_module.os, "walk", tracked_walk)
    monkeypatch.setattr(
        table_export_module, "result_page_number", tracked_inventory_page_number
    )
    monkeypatch.setattr(
        service_sources_module, "_result_page_number", tracked_parser_page_number
    )

    build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_path),
        }
    )
    assert walk_count == 1
    assert inventory_page_number_count == 1
    assert parser_page_number_count == 0

    walk_count = 0
    inventory_page_number_count = 0
    parser_page_number_count = 0
    inspection = table_export_module.inspect_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_path),
        }
    )
    assert inspection["confirmed"] is True
    assert walk_count == 1
    assert inventory_page_number_count == 1
    assert parser_page_number_count == 0


def test_build_disclosure_table_payload_preserves_unlinked_disclosure(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    body_path = next((tmp_path / "20250101_20250131").glob("*_post_page_*.body"))
    markup = body_path.read_text(encoding="utf-8")
    body_path.write_text(
        markup.replace(
            "</tbody>",
            """
              <tr>
                <td>3</td>
                <td>2025-01-04 09:00</td>
                <td>일괄신고</td>
                <td>
                  <a onclick="openDisclsViewer('20250104000001','')"
                     title="의결권 행사 내역">의결권 행사 내역</a>
                </td>
                <td>유리자산운용</td>
              </tr>
            </tbody>
            """,
        ),
        encoding="utf-8",
    )

    payload = build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(tmp_path / "02-table"),
            "table_name": "disclosures",
        }
    )

    manifest_path = Path(payload["manifest_path"])
    shard_path = manifest_path.parent / payload["shards"][0]["relative_path"]
    connection = sqlite3.connect(shard_path)
    try:
        row = connection.execute(
            """
            SELECT company_key, company_name, company_id, company_cell_text,
                   submitter, acpt_no
            FROM disclosures WHERE acpt_no = '20250104000001'
            """
        ).fetchone()
    finally:
        connection.close()

    assert payload["summary"]["disclosures"] == 3
    assert payload["summary"]["companies"] == 2
    assert payload["summary"]["unlinked_disclosures"] == 1
    assert payload["shards"][0]["unlinked_disclosures"] == 1
    assert row == (
        None,
        None,
        None,
        "일괄신고",
        "유리자산운용",
        "20250104000001",
    )

    filtered = filter_disclosures_payload(
        {
            "data_root": str(tmp_path),
            "acpt_numbers": ["20250104000001"],
        }
    )
    assert len(filtered["disclosures"]) == 1
    assert filtered["disclosures"][0]["company_key"] is None
    assert filtered["disclosures"][0]["company_name"] is None
    assert filtered["disclosures"][0]["company_id"] is None
    assert filtered["disclosures"][0]["company_cell_text"] == "일괄신고"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["shards"][0]["unlinked_disclosures"] = 0
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(
        ValueError,
        match="연도별 SQLite 파일의 회사 미연결 공시 건수가 다릅니다",
    ):
        filter_disclosures_payload({"data_root": str(tmp_path)})


def test_build_disclosure_table_payload_parses_source_pages_in_parallel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    source_root = _write_source_body_fixture(tmp_path)
    first_page = next(source_root.rglob("*_post_page_*.body"))
    second_page = first_page.with_name("001_post_page_00002.body")
    first_markup = first_page.read_text(encoding="utf-8")
    first_page.write_text(
        first_markup.replace("<strong>1</strong>/1", "<strong>1</strong>/2"),
        encoding="utf-8",
    )
    second_page.write_text(
        first_markup
        .replace("<strong>1</strong>/1", "<strong>2</strong>/2")
        .replace("20250102000001", "20250104000001")
        .replace("20250103000001", "20250105000001"),
        encoding="utf-8",
    )
    original_parse = table_export_module._parse_source_body_page_file
    barrier = threading.Barrier(2)

    def synchronized_parse(
        path: Path,
        source_page: int,
    ) -> tuple[list[dict[str, Any]], dict[str, int] | None]:
        barrier.wait(timeout=2)
        return original_parse(path, source_page)

    monkeypatch.setattr(
        table_export_module,
        "_parse_source_body_page_file",
        synchronized_parse,
    )
    progress: list[str] = []

    payload = build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(tmp_path / "02-table"),
            "table_workers": 2,
        },
        progress_callback=progress.append,
    )

    assert payload["summary"]["source_rows"] == 4
    assert payload["summary"]["disclosures"] == 4
    assert "다운로드한 원본 페이지를 병렬로 읽습니다. worker 수=2" in progress


def test_build_disclosure_table_payload_rejects_classification_input(
    tmp_path: Path,
) -> None:
    fixture_path = _write_classification_fixture(tmp_path)

    with pytest.raises(ValueError, match="classification_path is not supported"):
        build_disclosure_table_payload(
            {
                "classification_path": str(fixture_path),
                "output_path": str(tmp_path / "02-table"),
            }
        )


def test_build_disclosure_table_payload_accepts_source_body_folder(tmp_path: Path) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    output_path = tmp_path / "kind.sqlite_manifest.json"
    manifest_path = _sqlite_manifest_path(output_path)

    payload = build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_path),
        }
    )

    assert payload["source_type"] == "source_folder"
    assert payload["summary"]["source_rows"] == 2
    assert payload["summary"]["duplicate_rows"] == 0
    assert payload["summary"]["disclosures"] == 2
    assert payload["summary"]["shards"] == 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_type"] == "source_folder"
    assert manifest["summary"]["source_rows"] == 2
    assert manifest["summary"]["duplicate_rows"] == 0
    assert manifest["shards"][0]["year"] == "2025"


def test_build_disclosure_table_payload_rejects_source_folder_without_metadata(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    next(source_root.rglob("kind_workflow.input.json")).unlink()

    with pytest.raises(ValueError, match="metadata is missing"):
        build_disclosure_table_payload(
            {
            "root_directory": str(source_root),
                "output_path": str(tmp_path / "02-table"),
            }
        )


def test_build_disclosure_table_payload_rejects_invalid_source_metadata(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    next(source_root.rglob("kind_workflow.input.json")).write_text(
        "[]", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="metadata is invalid"):
        build_disclosure_table_payload(
            {
            "root_directory": str(source_root),
                "output_path": str(tmp_path / "02-table"),
            }
        )


def test_build_disclosure_table_payload_ignores_repair_overlay(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    source_folder = next(
        path.parent for path in source_root.rglob("kind_workflow.input.json")
    )
    original_page = source_folder / "001_post_page_00001.body"
    overlay_page = (
        source_folder
        / ".kind_page_repairs"
        / "page_00001"
        / "attempt_001"
        / "001_post_page_00001.body"
    )
    overlay_page.parent.mkdir(parents=True)
    overlay_page.write_text("not a disclosure page", encoding="utf-8")
    (source_folder / ".kind_page_repairs" / "manifest.json").write_text(
        json.dumps(
            {
                "pages": {
                    "1": {
                        "page_path": str(overlay_page.relative_to(source_folder)),
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    payload = build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(tmp_path / "02-table"),
        }
    )

    assert payload["summary"]["source_rows"] == 2
    assert payload["pages"][0]["source_file"] == original_page.relative_to(
        source_root
    ).as_posix()


def test_build_disclosure_table_payload_does_not_reread_failed_source_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "01-list"
    folder = source_root / "20250101_20251231"
    folder.mkdir(parents=True)
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(
            _trusted_download_input_snapshot(
                start_date="2025-01-01",
                end_date="2025-12-31",
                page_size=1,
            )
        ),
        encoding="utf-8",
    )
    page_one = _build_download_result_page_html(
        page_number=1,
        page_size=1,
        total_items=2,
    )
    page_two = _build_download_result_page_html(
        page_number=2,
        page_size=1,
        total_items=2,
    ).replace(b"20250101000001", b"20250101000002")
    (folder / "001_post_page_00001.body").write_bytes(page_one)
    (folder / "002_post_page_00002.body").write_bytes(page_two)
    original_parse = table_export_module._parse_source_body_page_file
    read_counts: dict[int, int] = {1: 0, 2: 0}

    def _parse_with_transient_failure(
        body_path: Path,
        source_page: int,
    ) -> tuple[list[dict[str, Any]], dict[str, int] | None]:
        read_counts[source_page] += 1
        if source_page == 2 and read_counts[source_page] == 1:
            raise OSError("temporary read failure")
        return original_parse(body_path, source_page)

    monkeypatch.setattr(
        table_export_module,
        "_parse_source_body_page_file",
        _parse_with_transient_failure,
    )

    with pytest.raises(OSError, match="temporary read failure"):
        build_disclosure_table_payload(
            {
                "root_directory": str(source_root),
                "output_path": str(tmp_path / "02-table"),
            }
        )

    assert read_counts == {1: 1, 2: 1}


def test_build_disclosure_table_payload_does_not_retry_source_page_without_acpt_no(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "01-list"
    folder = source_root / "20250101_20251231"
    folder.mkdir(parents=True)
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(
            _trusted_download_input_snapshot(
                start_date="2025-01-01",
                end_date="2025-12-31",
                page_size=1,
            )
        ),
        encoding="utf-8",
    )
    valid_page = _build_download_result_page_html(
        page_number=1,
        page_size=1,
        total_items=1,
    )
    (folder / "001_post_page_00001.body").write_bytes(
        valid_page.replace(b"20250101000001", b"")
    )
    original_parse = table_export_module._parse_source_body_page_file
    read_count = 0

    def _count_parse(
        body_path: Path,
        source_page: int,
    ) -> tuple[list[dict[str, Any]], dict[str, int] | None]:
        nonlocal read_count
        read_count += 1
        return original_parse(body_path, source_page)

    monkeypatch.setattr(
        table_export_module,
        "_parse_source_body_page_file",
        _count_parse,
    )

    with pytest.raises(ValueError, match="missing acpt_no"):
        build_disclosure_table_payload(
            {
            "root_directory": str(source_root),
                "output_path": str(tmp_path / "02-table"),
            }
        )

    assert read_count == 1


def test_build_disclosure_table_payload_rejects_metadata_range_without_pages(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    empty_range = source_root / "20250201_20250228"
    empty_range.mkdir()
    (empty_range / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot()),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="공시 결과 페이지가 없습니다"):
        build_disclosure_table_payload(
            {
            "root_directory": str(source_root),
                "output_path": str(tmp_path / "02-table"),
            }
        )


def test_build_disclosure_table_payload_rejects_duplicate_source_page_numbers(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "01-list"
    folder = source_root / "20250101_20251231"
    folder.mkdir(parents=True)
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(
            _trusted_download_input_snapshot(
                start_date="2025-01-01",
                end_date="2025-12-31",
                page_size=1,
            )
        ),
        encoding="utf-8",
    )
    page = _build_download_result_page_html(
        page_number=1,
        page_size=1,
        total_items=1,
    )
    (folder / "001_post_page_00001.body").write_bytes(page)
    (folder / "002_post_page_00001.body").write_bytes(page)

    with pytest.raises(ValueError, match="중복되는 페이지 번호 1"):
        build_disclosure_table_payload(
            {
            "root_directory": str(source_root),
                "output_path": str(tmp_path / "02-table"),
            }
        )


def test_build_disclosure_table_payload_rejects_missing_source_page(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "01-list"
    folder = source_root / "20250101_20251231"
    folder.mkdir(parents=True)
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(
            _trusted_download_input_snapshot(
                start_date="2025-01-01",
                end_date="2025-12-31",
                page_size=1,
            )
        ),
        encoding="utf-8",
    )
    page_one = _build_download_result_page_html(
        page_number=1,
        page_size=1,
        total_items=3,
    )
    page_three = _build_download_result_page_html(
        page_number=3,
        page_size=1,
        total_items=3,
    ).replace(b"20250101000001", b"20250101000003")
    (folder / "001_post_page_00001.body").write_bytes(page_one)
    (folder / "003_post_page_00003.body").write_bytes(page_three)

    with pytest.raises(ValueError, match="페이지 번호가 1부터 연속적이지 않습니다"):
        build_disclosure_table_payload(
            {
                "root_directory": str(source_root),
                "output_path": str(tmp_path / "02-table"),
                "table_workers": 2,
            }
        )


def test_build_and_inspect_disclosure_table_reject_body_page_mismatch(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "01-list"
    folder = source_root / "20250101_20251231"
    folder.mkdir(parents=True)
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(
            _trusted_download_input_snapshot(
                start_date="2025-01-01",
                end_date="2025-12-31",
                page_size=1,
            )
        ),
        encoding="utf-8",
    )
    page_one = _build_download_result_page_html(
        page_number=1,
        page_size=1,
        total_items=2,
    )
    page_two = _build_download_result_page_html(
        page_number=2,
        page_size=1,
        total_items=2,
    ).replace(b"20250101000001", b"20250101000002")
    first_path = folder / "001_post_page_00001.body"
    second_path = folder / "002_post_page_00002.body"
    first_path.write_bytes(page_one)
    mismatched_page_two = page_two.replace(
        b"<strong>2</strong>",
        b"<strong>1</strong>",
    )
    second_path.write_bytes(mismatched_page_two)

    output_path = tmp_path / "02-table"
    mismatch_message = "파일명 페이지=2, BODY 페이지=1로 서로 다릅니다"
    with pytest.raises(ValueError, match=mismatch_message):
        build_disclosure_table_payload(
            {
                "root_directory": str(source_root),
                "output_path": str(output_path),
                "table_workers": 2,
            }
        )

    second_path.write_bytes(page_two.replace(b"<em>2</em>", b"<em>3</em>"))
    with pytest.raises(
        ValueError,
        match="BODY 페이지 사이의 전체 페이지 수 또는 전체 공시 건수가 다릅니다",
    ):
        build_disclosure_table_payload(
            {
                "root_directory": str(source_root),
                "output_path": str(output_path),
                "table_workers": 2,
            }
        )

    second_path.write_bytes(page_two)
    build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_path),
            "table_workers": 2,
        }
    )
    second_path.write_bytes(mismatched_page_two)

    inspection = table_export_module.inspect_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_path),
            "table_workers": 2,
        }
    )

    assert inspection["confirmed"] is False
    assert mismatch_message in inspection["reason"]


def test_build_disclosure_table_payload_deduplicates_source_rows_by_acpt_no(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    body_path = next(source_root.rglob("*_post_page_*.body"))
    body_path.write_text(
        body_path.read_text(encoding="utf-8").replace(
            "20250103000001", "20250102000001"
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "kind.sqlite_manifest.json"
    manifest_path = _sqlite_manifest_path(output_path)

    payload = build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(output_path),
        }
    )

    assert payload["summary"]["source_rows"] == 2
    assert payload["summary"]["duplicate_rows"] == 1
    assert payload["summary"]["disclosures"] == 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["summary"]["source_rows"] == 2
    assert manifest["summary"]["duplicate_rows"] == 1
    assert manifest["summary"]["disclosures"] == 1

    with sqlite3.connect(
        manifest_path.parent / manifest["shards"][0]["relative_path"]
    ) as connection:
        rows = connection.execute(
            "SELECT acpt_no FROM disclosures"
        ).fetchall()

    assert rows == [("20250102000001",)]


def test_sqlite_filter_uses_table_deduplication_result(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    body_path = next(source_root.rglob("*_post_page_*.body"))
    text = body_path.read_text(encoding="utf-8")
    first_start = text.index("<tr>")
    first_end = text.index("</tr>", first_start) + len("</tr>")
    second_start = text.index("<tr>", first_end)
    second_end = text.index("</tr>", second_start) + len("</tr>")
    body_path.write_text(
        text[:second_start] + text[first_start:first_end] + text[second_end:],
        encoding="utf-8",
    )

    table_payload = build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "output_path": str(tmp_path / "02-table"),
        }
    )
    source_payload = filter_disclosures_payload(
        {"data_root": str(tmp_path), "filter_blocks": []}
    )

    assert table_payload["summary"]["source_rows"] == 2
    assert table_payload["summary"]["duplicate_rows"] == 1
    assert source_payload["summary"]["source_disclosures"] == 1
    assert source_payload["summary"]["duplicate_disclosures"] == 0
    assert source_payload["summary"]["matched_disclosures"] == 1


def test_build_disclosure_table_payload_rejects_source_row_without_acpt_no(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    body_path = next(source_root.rglob("*_post_page_*.body"))
    body_path.write_text(
        body_path.read_text(encoding="utf-8").replace(
            "openDisclsViewer('20250103000001','')",
            "openDisclsViewer('','')",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing acpt_no"):
        build_disclosure_table_payload(
            {
                "root_directory": str(source_root),
                "output_path": str(tmp_path / "02-table"),
            }
        )


def test_build_disclosure_table_payload_rejects_missing_source_path(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "missing-source"

    with pytest.raises(FileNotFoundError, match="KIND source directory not found"):
        build_disclosure_table_payload(
            {
                "root_directory": str(missing_root),
                "output_path": str(tmp_path / "02-table"),
            }
        )


def test_build_disclosure_table_payload_rejects_classification_path_with_root(
    tmp_path: Path,
) -> None:
    source_base = tmp_path / "source"
    source_base.mkdir()
    source_root = _write_source_body_fixture(source_base)
    output_dir = tmp_path / "kind_sqlite"

    with pytest.raises(ValueError, match="classification_path is not supported"):
        build_disclosure_table_payload(
            {
                "root_directory": str(source_root),
                "classification_path": str(output_dir),
                "output_path": str(output_dir / "kind.sqlite_manifest.json"),
            }
        )


def test_collect_acpt_numbers_from_json_requires_canonical_records() -> None:
    payload = {
        "disclosures": [
            {"acpt_no": "AB202501010001"},
            {"acpt_no": "20250101000002"},
        ]
    }

    assert collect_acpt_numbers_from_json(payload) == ["AB202501010001", "20250101000002"]

    with pytest.raises(ValueError, match="acpt_no must not be empty"):
        collect_acpt_numbers_from_json({"disclosures": [{"acptNo": "20250101000001"}]})


def test_download_disclosure_external_html_payload_uses_collected_acpt_numbers(tmp_path: Path, monkeypatch) -> None:
    def fake_download(**kwargs):
        assert kwargs["max_retries"] == 5
        paths = []
        for acpt_no in kwargs["acpt_numbers"]:
            path = Path(kwargs["target_output_directories"][acpt_no]) / f"{acpt_no}.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_valid_download_html(), encoding="utf-8")
            paths.append(path)
        return paths

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls", fake_download)

    payload = download_disclosure_external_html_payload(
        _external_workspace_body(
            tmp_path,
            {"disclosures": [{"acpt_no": "20250101000001"}]},
            output_directory=str(tmp_path / "viewer_html"),
        )
    )

    assert payload["requested_count"] == 1
    assert payload["missing_acpt_numbers"] == []
    assert payload["saved_files"] == [
        str(tmp_path / "viewer_html" / "2025" / "20250101000001.html")
    ]
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["disclosures"][0]["market"] is None


def test_write_disclosure_html_manifest_payload_from_workspace_filtered_json(
    tmp_path: Path,
) -> None:
    source_json = {
        "disclosures": [
            {"acpt_no": "20250101000001", "market": "코스닥"},
            {"acpt_no": "20250101000002", "market": "유가증권"},
        ]
    }
    output_directory = tmp_path / "converted"

    payload = write_disclosure_html_manifest_payload(
        _external_workspace_body(
            tmp_path,
            source_json,
            output_directory=str(output_directory),
        )
    )

    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert payload["requested_count"] == 2
    assert "source_json_path" not in manifest
    assert manifest["format"] == "finiq_disclosure_html_manifest_v2"
    assert "source_fingerprint" not in manifest
    assert [item["acpt_no"] for item in manifest["disclosures"]] == [
        "20250101000001",
        "20250101000002",
    ]
    assert manifest["disclosures"][0]["market"] == "코스닥"


def test_write_disclosure_html_manifest_payload_uses_selected_mode_filter_folder(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    for mode, acpt_no in (
        ("bond_issuance", "20250101000001"),
        ("rights_issuance", "20250101000002"),
    ):
        filtered_path = data_root / "03-filter" / mode / "filtered.json"
        filtered_path.parent.mkdir(parents=True)
        filtered_path.write_text(
            json.dumps(
                {
                    "format": "kind_disclosure_filter_v1",
                    "disclosures": [
                        {"acpt_no": acpt_no, "disclosed_at": "2025-01-01"}
                    ],
                }
            ),
            encoding="utf-8",
        )

    payload = write_disclosure_html_manifest_payload(
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "output_directory": str(tmp_path / "converted"),
        }
    )

    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert payload["requested_count"] == 1
    assert "source_json_path" not in manifest
    assert manifest["format"] == "finiq_disclosure_html_manifest_v2"
    assert "source_fingerprint" not in manifest
    assert [record["acpt_no"] for record in manifest["disclosures"]] == [
        "20250101000001",
    ]


def test_write_disclosure_html_manifest_payload_rejects_noncanonical_receipt_list(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "converted"

    with pytest.raises(ValueError, match="disclosures array"):
        write_disclosure_html_manifest_payload(
            _external_workspace_body(
                tmp_path,
                {"acpt_no_list": ["20250101000001"]},
                output_directory=str(output_directory),
            )
        )

    assert not (output_directory / "kind_disclosure_html_manifest.json").exists()


def test_write_disclosure_html_manifest_payload_rejects_source_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="source_directory is not supported"):
        write_disclosure_html_manifest_payload(
            {
                "output_directory": str(tmp_path / "content_html"),
                "source_directory": str(tmp_path / "viewer_html"),
            }
        )


def test_download_disclosure_internal_html_payload_saves_body_html(tmp_path: Path, monkeypatch) -> None:
    download_events: list[None] = []

    def fake_download(**kwargs):
        assert kwargs["targets"] == [{"acpt_no": "20250101000001", "doc_no": "20250101000099"}]
        path = Path(
            kwargs["target_output_directories"]["20250101000001"]
        ) / "20250101000001.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<html><body>content</body></html>", encoding="utf-8")
        kwargs["progress_callback"](f"Saved KIND internal HTML to: {path}")
        return [path]

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls", fake_download)
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [{
                    "acpt_no": "20250101000001",
                    "selected_main_doc_no": "20250101000099",
                    "metadata": {"disclosed_at": "2025-01-01"},
                }],
            }
        ),
        encoding="utf-8",
    )

    payload = download_disclosure_internal_html_payload(
        {
            "output_directory": str(tmp_path / "content_html"),
            "source_compressed_json_path": str(compressed_path),
            "progress_interval": 1,
        },
        download_callback=lambda: download_events.append(None),
    )

    assert payload["format"] == "kind_disclosure_internal_html_download_v1"
    assert payload["requested_count"] == 1
    assert payload["saved_files"] == [
        str(tmp_path / "content_html" / "2025" / "20250101000001.html")
    ]
    assert "HTML 내부 저장 중간 확인: 1/1건 처리." in payload["progress_log"]
    assert len(download_events) == 1
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["disclosures"][0]["source_size_bytes"] > 0
    assert len(manifest["disclosures"][0]["source_sha256"]) == 64


def test_download_disclosure_internal_html_payload_finishes_hashing_after_cancel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_download(**kwargs):
        target = kwargs["targets"][0]
        path = Path(kwargs["output_directory"]) / f"{target['acpt_no']}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_valid_download_html(), encoding="utf-8")
        cancel_disclosure_html_download("cancel-during-hash")
        return [path]

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        fake_download,
    )
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                    {
                        "acpt_no": "20250101000001",
                        "selected_main_doc_no": "20250101000999",
                        "metadata": {"disclosed_at": "2025-01-01"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = download_disclosure_internal_html_payload(
        {
            "output_directory": str(tmp_path / "content_html"),
            "source_compressed_json_path": str(compressed_path),
            "cancel_token": "cancel-during-hash",
        }
    )

    assert payload["cancelled"] is True
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert [item["acpt_no"] for item in manifest["disclosures"]] == [
        "20250101000001"
    ]
    assert any("기준 해시 생성 완료" in line for line in payload["progress_log"])


def test_download_disclosure_internal_html_payload_rejects_json_only_input(tmp_path: Path) -> None:
    try:
        download_disclosure_internal_html_payload(
            {
                "output_directory": str(tmp_path / "content_html"),
                "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
            }
        )
    except ValueError as exc:
        assert str(exc) == "source_compressed_json_path is required"
    else:
        raise AssertionError("expected ValueError")


def test_download_disclosure_internal_html_payload_accepts_compressed_json_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[Path, list[dict[str, str]]]] = []

    def fake_download(**kwargs):
        targets = list(kwargs["targets"])
        calls.append((Path(kwargs["output_directory"]), targets))
        paths = [
            Path(kwargs["target_output_directories"][target["acpt_no"]])
            / f"{target['acpt_no']}.html"
            for target in targets
        ]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_valid_download_html(), encoding="utf-8")
        return paths

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls", fake_download)

    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                        {
                            "acpt_no": "AB202501010001",
                            "selected_main_doc_no": "DOC202501Z",
                            "metadata": {"disclosed_at": "2025-01-01"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = download_disclosure_internal_html_payload(
        {
            "output_directory": str(tmp_path / "content_html"),
            "source_compressed_json_path": str(compressed_path),
        }
    )

    assert calls == [
        (
            tmp_path / "content_html",
            [{"acpt_no": "AB202501010001", "doc_no": "DOC202501Z"}],
        )
    ]
    assert payload["saved_files"] == [
        str(tmp_path / "content_html" / "2025" / "AB202501010001.html")
    ]
    assert payload["manifest_path"] == str(tmp_path / "content_html" / "kind_disclosure_html_manifest.json")
    assert payload["verification"] == {
        "passed": True,
        "complete": True,
        "expected_records": 1,
        "saved_records": 1,
        "missing_records": 0,
        "unexpected_records": 0,
        "duplicate_records": 0,
        "missing_acpt_numbers": [],
        "unexpected_acpt_numbers": [],
        "duplicate_acpt_numbers": [],
    }


def test_download_disclosure_internal_html_payload_rejects_duplicate_compressed_records(
    tmp_path: Path,
) -> None:
    compressed_path = tmp_path / "compressed-external-html.json"
    record = {
        "acpt_no": "20250101000001",
        "selected_main_doc_no": "20250101000999",
    }
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [record, record],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate acpt_no values.*20250101000001"):
        download_disclosure_internal_html_payload(
            {
                "output_directory": str(tmp_path / "content_html"),
                "source_compressed_json_path": str(compressed_path),
            }
        )


def test_download_disclosure_internal_html_payload_requires_selected_main_doc_no(
    tmp_path: Path,
) -> None:
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                    {
                        "acpt_no": "20250101000001",
                        "docs": [
                            {
                                "select_id": "mainDoc",
                                "doc_no": "20250101000999",
                                "selected": True,
                            }
                        ],
                        "main_docs": [{"doc_no": "20250101000888"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="selected main docNo not found"):
        download_disclosure_internal_html_payload(
            {
                "output_directory": str(tmp_path / "content_html"),
                "source_compressed_json_path": str(compressed_path),
            }
        )


def test_download_disclosure_internal_html_payload_does_not_use_legacy_compressed_year(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_download(**kwargs):
        raise AssertionError("invalid compressed year must fail before download")

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        fail_download,
    )
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                        {
                            "acpt_no": "20250101000001",
                            "selected_main_doc_no": "20250101000999",
                            "year": "2025",
                        }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="disclosed_at is required"):
        download_disclosure_internal_html_payload(
            {
                "output_directory": str(tmp_path / "content_html"),
                "source_compressed_json_path": str(compressed_path),
            }
        )


@pytest.mark.parametrize(
    ("returned_acpt_numbers", "mismatch_name"),
    [
        (["20250101000001", "20250101000001"], "duplicates"),
        ([], "missing"),
        (["20250101000001", "20250101000002"], "unexpected"),
    ],
)
def test_download_disclosure_internal_html_payload_rejects_result_membership_mismatch(
    tmp_path: Path,
    monkeypatch,
    returned_acpt_numbers: list[str],
    mismatch_name: str,
) -> None:
    def fake_download(**kwargs):
        output_directory = Path(kwargs["output_directory"])
        return [
            output_directory / f"{acpt_no}.html"
            for acpt_no in returned_acpt_numbers
        ]

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        fake_download,
    )
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                    {
                        "acpt_no": "20250101000001",
                        "selected_main_doc_no": "20250101000999",
                        "metadata": {"disclosed_at": "2025-01-01"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=rf"membership.*{mismatch_name}="):
        download_disclosure_internal_html_payload(
            {
                "output_directory": str(tmp_path / "content_html"),
                "source_compressed_json_path": str(compressed_path),
            }
        )


def test_internal_html_redownload_records_revalidated_kind_source_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acpt_no = "20250101000001"
    doc_no = "20250101000999"
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_payload = {
        "format": "finiq_disclosure_external_html_docs_v1",
        "records": [
            {
                "acpt_no": acpt_no,
                "selected_main_doc_no": doc_no,
                "metadata": {"disclosed_at": "2025-01-01"},
            }
        ],
    }
    compressed_path.write_text(json.dumps(compressed_payload), encoding="utf-8")
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._fetch_internal_html",
        lambda *_args, **_kwargs: b"",
    )
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.wait_for_html_download_request_slot",
        lambda *_args, **_kwargs: False,
    )
    output_directory = tmp_path / "content_html"

    result = download_disclosure_internal_html_payload(
        {
            "output_directory": str(output_directory),
            "source_compressed_json_path": str(compressed_path),
        },
        redownload_unverified_existing=True,
    )

    assert result["verification"]["passed"] is True
    assert result["verification"]["complete"] is True
    assert result["source_unavailable_count"] == 1
    assert result["source_unavailable_acpt_numbers"] == [acpt_no]
    assert any("KIND 원본 없음 확인" in line for line in result["progress_log"])
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["disclosures"][0]["source_unavailable"] == {
        "doc_no": doc_no,
        "reason": "invalid_html",
    }
    assert len(manifest["disclosures"][0]["source_sha256"]) == 64
    placeholder_path = output_directory / "2025" / f"{acpt_no}.html"
    assert placeholder_path.is_file()

    inspection = check_disclosure_html_output_directory_payload(
        {
            "output_directory": str(output_directory),
            "source_compressed_json_path": str(compressed_path),
        }
    )
    assert inspection["missing_target_html_count"] == 0
    assert inspection["download_required_target_html_count"] == 0
    assert inspection["source_unavailable_target_html_count"] == 1
    assert inspection["source_unavailable_target_acpt_numbers"] == [acpt_no]
    import finiq.market_desk.web.features.disclosures.html_common as html_common

    reused_paths, reuse_integrity = html_common._strictly_reuse_parent_html(
        output_directory=output_directory,
        acpt_numbers=[acpt_no],
        source_json=compressed_payload,
    )
    assert reused_paths == [placeholder_path]
    assert reuse_integrity["source_unavailable_target_acpt_numbers"] == [acpt_no]

    sections_directory = tmp_path / "sections"
    section_result = save_disclosure_html_sections_payload(
        {
            "input_directory": str(output_directory),
            "output_directory": str(sections_directory),
        }
    )
    section_placeholder = sections_directory / "2025" / f"{acpt_no}.html"
    assert section_result["summary"]["integrity_ok"] is True
    assert section_result["summary"]["source_unavailable_files"] == 1
    assert section_placeholder.read_bytes() == placeholder_path.read_bytes()
    section_inspection = inspect_disclosure_html_section_output_payload(
        {
            "input_directory": str(output_directory),
            "output_directory": str(sections_directory),
        }
    )
    assert section_inspection["summary"]["integrity_ok"] is True
    assert section_inspection["summary"]["source_unavailable_files"] == 1

    parsed = parse_disclosure_html_payload(
        {
            "input_directory": str(sections_directory),
            "output_directory": str(tmp_path / "parsed"),
            "mode": "saved_filter",
            "parser_method": "bond_issuance",
            "skip_errors": False,
            **_html_parse_metadata_paths(compressed_path=compressed_path),
        }
    )
    assert parsed["summary"] == {
        "found_files": 1,
        "parsed_files": 1,
        "failed_files": 0,
    }
    assert parsed["records"][0]["acpt_no"] == acpt_no
    assert parsed["records"][0]["source_unavailable"] == {
        "doc_no": doc_no,
        "reason": "invalid_html",
    }

    compressed_payload["records"][0]["selected_main_doc_no"] = "20250101000888"
    compressed_path.write_text(json.dumps(compressed_payload), encoding="utf-8")
    changed_source_inspection = check_disclosure_html_output_directory_payload(
        {
            "output_directory": str(output_directory),
            "source_compressed_json_path": str(compressed_path),
        }
    )
    assert changed_source_inspection["missing_target_html_count"] == 0
    assert changed_source_inspection["invalid_target_html_count"] == 1
    assert changed_source_inspection["download_required_target_html_count"] == 1
    assert changed_source_inspection["source_unavailable_target_html_count"] == 0

    compressed_payload["records"][0]["selected_main_doc_no"] = doc_no
    compressed_path.write_text(json.dumps(compressed_payload), encoding="utf-8")
    manifest["disclosures"][0]["source_sha256"] = "0" * 64
    Path(result["manifest_path"]).write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    hash_mismatch_inspection = check_disclosure_html_output_directory_payload(
        {
            "output_directory": str(output_directory),
            "source_compressed_json_path": str(compressed_path),
        }
    )
    assert hash_mismatch_inspection["download_required_target_html_count"] == 1
    assert hash_mismatch_inspection["invalid_target_html_count"] == 1
    assert hash_mismatch_inspection["source_unavailable_target_html_count"] == 0

    def recover_download(**kwargs):
        target = kwargs["targets"][0]
        path = (
            Path(kwargs["target_output_directories"][target["acpt_no"]])
            / f"{target['acpt_no']}.html"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_valid_download_html(), encoding="utf-8")
        return [path]

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        recover_download,
    )
    recovered = download_disclosure_internal_html_payload(
        {
            "output_directory": str(output_directory),
            "source_compressed_json_path": str(compressed_path),
        }
    )
    assert recovered["source_unavailable_count"] == 0
    recovered_manifest = json.loads(
        Path(recovered["manifest_path"]).read_text(encoding="utf-8")
    )
    assert "source_unavailable" not in recovered_manifest["disclosures"][0]


def test_source_unavailable_placeholder_receipt_must_match_filename(
    tmp_path: Path,
) -> None:
    embedded_acpt_no = "20250101000001"
    filename_acpt_no = "20250101000002"
    doc_no = "20250101000999"
    input_directory = tmp_path / "input"
    placeholder_path = input_directory / "2025" / f"{filename_acpt_no}.html"
    placeholder_path.parent.mkdir(parents=True)
    placeholder_path.write_bytes(
        _render_internal_html_source_unavailable_placeholder(
            acpt_no=embedded_acpt_no,
            doc_no=doc_no,
            reason="invalid_html",
        )
    )

    with pytest.raises(ValueError, match="receipt number does not match filename"):
        save_disclosure_html_sections_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(tmp_path / "sections"),
            }
        )

    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                    {
                        "acpt_no": filename_acpt_no,
                        "selected_main_doc_no": doc_no,
                        "metadata": {"disclosed_at": "2025-01-01"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="receipt number does not match filename"):
        parse_disclosure_html_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(tmp_path / "parsed"),
                "mode": "saved_filter",
                "parser_method": "bond_issuance",
                "skip_errors": False,
                **_html_parse_metadata_paths(compressed_path=compressed_path),
            }
        )


def test_failed_placeholder_refresh_reports_membership_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acpt_no = "20250101000001"
    doc_no = "20250101000999"
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                    {
                        "acpt_no": acpt_no,
                        "selected_main_doc_no": doc_no,
                        "metadata": {"disclosed_at": "2025-01-01"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_directory = tmp_path / "content_html"
    placeholder_path = output_directory / "2025" / f"{acpt_no}.html"
    placeholder_path.parent.mkdir(parents=True)
    placeholder_path.write_bytes(
        _render_internal_html_source_unavailable_placeholder(
            acpt_no=acpt_no,
            doc_no=doc_no,
            reason="invalid_html",
        )
    )
    write_disclosure_html_manifest_payload(
        {
            "output_directory": str(output_directory),
            "source_compressed_json_path": str(compressed_path),
        }
    )
    manifest_path = output_directory / "kind_disclosure_html_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["disclosures"][0]["source_unavailable"] = {
        "doc_no": doc_no,
        "reason": "invalid_html",
    }
    manifest["disclosures"][0]["source_sha256"] = "0" * 64
    manifest["disclosures"][0]["source_size_bytes"] = placeholder_path.stat().st_size
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        lambda **_kwargs: [],
    )

    def fail_revalidation(*_args, **_kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._fetch_internal_html",
        fail_revalidation,
    )
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.wait_for_html_download_request_slot",
        lambda *_args, **_kwargs: False,
    )

    with pytest.raises(ValueError, match="membership does not match"):
        download_disclosure_internal_html_payload(
            {
                "output_directory": str(output_directory),
                "source_compressed_json_path": str(compressed_path),
            },
            redownload_unverified_existing=True,
        )


def test_internal_html_redownload_does_not_hide_revalidation_request_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                    {
                        "acpt_no": "20250101000001",
                        "selected_main_doc_no": "20250101000999",
                        "metadata": {"disclosed_at": "2025-01-01"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        lambda **_kwargs: [],
    )

    def fail_revalidation(*_args, **_kwargs):
        raise RuntimeError("request failed")

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._fetch_internal_html",
        fail_revalidation,
    )
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.wait_for_html_download_request_slot",
        lambda *_args, **_kwargs: False,
    )

    with pytest.raises(ValueError, match="membership.*missing="):
        download_disclosure_internal_html_payload(
            {
                "output_directory": str(tmp_path / "content_html"),
                "source_compressed_json_path": str(compressed_path),
            },
            redownload_unverified_existing=True,
        )


def test_download_disclosure_external_html_payload_rejects_source_json_path(
    tmp_path: Path,
) -> None:
    unsupported_source_path = tmp_path / "filtered-disclosures.json"
    with pytest.raises(ValueError, match="source_json_path is not supported"):
        download_disclosure_external_html_payload(
            _external_workspace_body(
                tmp_path,
                {"disclosures": [{"acpt_no": "20250101000001"}]},
                output_directory=str(tmp_path / "viewer_html"),
                source_json_path=str(unsupported_source_path),
            )
        )


def test_download_disclosure_external_html_payload_rejects_result_directory_source_json_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_download(**kwargs):
        acpt_numbers = list(kwargs["acpt_numbers"])
        calls.append(acpt_numbers)
        return [Path(kwargs["output_directory"]) / f"{acpt_no}.html" for acpt_no in acpt_numbers]

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls", fake_download)
    result_directory = tmp_path / "download_results"
    result_directory.mkdir()
    (result_directory / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=1, total_items=1)
    )

    with pytest.raises(ValueError, match="source_json_path is not supported"):
        download_disclosure_external_html_payload(
            {
                "data_root": str(tmp_path / "workspace"),
                "mode": "bond_issuance",
                "output_directory": str(tmp_path / "viewer_html"),
                "source_json_path": str(result_directory),
            }
        )

    assert calls == []


def test_download_disclosure_external_html_payload_rejects_flat_filter_result(
    tmp_path: Path,
) -> None:
    flat_result = tmp_path / "workspace" / "03-filter" / "filtered.json"
    flat_result.parent.mkdir(parents=True)
    flat_result.write_text(
        json.dumps({"disclosures": [{"acpt_no": "20250101000001"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"03-filter/bond_issuance/filtered.json"):
        download_disclosure_external_html_payload(
            {
                "data_root": str(tmp_path / "workspace"),
                "mode": "bond_issuance",
                "output_directory": str(tmp_path / "viewer_html"),
            }
        )


def test_clean_disclosure_external_html_output_directory_rejects_source_json_path(
    tmp_path: Path,
) -> None:
    result_directory = tmp_path / "download_results"
    result_directory.mkdir()
    (result_directory / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=1, total_items=1)
    )

    with pytest.raises(ValueError, match="source_json_path is not supported"):
        clean_disclosure_html_output_directory_payload(
            {
                "data_root": str(tmp_path / "workspace"),
                "mode": "bond_issuance",
                "output_directory": str(tmp_path / "viewer_html"),
                "source_json_path": str(result_directory),
                "dry_run": True,
            }
        )


def test_check_disclosure_external_html_output_directory_reports_existing_overlap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import finiq.concurrency as concurrency
    import finiq.market_desk.web.features.disclosures.html_common as disclosure_html

    used_workers: list[int] = []
    real_executor = disclosure_html.ThreadPoolExecutor

    def tracking_executor(*args, **kwargs):
        used_workers.append(kwargs.get("max_workers") or args[0])
        return real_executor(*args, **kwargs)

    monkeypatch.setattr(concurrency.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(disclosure_html, "ThreadPoolExecutor", tracking_executor)

    output_directory = tmp_path / "viewer_html"
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "2025" / "20250101000001.html").write_text(
        _valid_download_html(), encoding="utf-8"
    )

    payload = check_disclosure_html_output_directory_payload(
        _external_workspace_body(
            tmp_path,
            {
                "disclosures": [
                    {"acpt_no": "20250101000001"},
                    {"acpt_no": "20250101000002"},
                ]
            },
            output_directory=str(output_directory),
        )
    )

    assert payload["format"] == "kind_disclosure_html_existing_check_v1"
    assert payload["has_existing"] is True
    assert payload["deleted_count"] == 0
    assert payload["existing_target_html_count"] == 1
    assert payload["missing_target_html_count"] == 1
    assert (output_directory / "2025" / "20250101000001.html").exists()
    assert used_workers == [2]


def test_check_disclosure_html_output_directory_loads_source_and_inventory_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import finiq.market_desk.web.features.disclosures.html_cleanup as html_cleanup
    import finiq.market_desk.web.features.disclosures.html_common as html_common

    source_loads = 0
    inventories = 0
    real_load = html_cleanup._load_workspace_filtered_payload
    real_inventory = html_common._iter_html_output_files

    def tracked_load(body):
        nonlocal source_loads
        source_loads += 1
        return real_load(body)

    def tracked_inventory(output_directory):
        nonlocal inventories
        inventories += 1
        return real_inventory(output_directory)

    monkeypatch.setattr(html_cleanup, "_load_workspace_filtered_payload", tracked_load)
    monkeypatch.setattr(html_common, "_iter_html_output_files", tracked_inventory)

    output_directory = tmp_path / "viewer_html"
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "2025" / "20250101000001.html").write_text(
        _valid_download_html(), encoding="utf-8"
    )
    check_disclosure_html_output_directory_payload(
        _external_workspace_body(
            tmp_path,
            {"disclosures": [{"acpt_no": "20250101000001"}]},
            output_directory=str(output_directory),
        )
    )

    assert source_loads == 1
    assert inventories == 1


def test_all_external_html_inspection_reuses_parent_file_hashes_for_derived_filter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import finiq.market_desk.web.features.disclosures.html_cleanup as html_cleanup
    import finiq.market_desk.web.features.disclosures.html_common as html_common

    parent_source = {
        "disclosures": [
            {"acpt_no": "20250101000001"},
            {"acpt_no": "20250101000002"},
        ]
    }
    parent_body = _external_workspace_body(tmp_path, parent_source)
    data_root = Path(str(parent_body["data_root"]))
    parent_payload = json.loads(
        (data_root / "03-filter" / "bond_issuance" / "filtered.json").read_text(
            encoding="utf-8"
        )
    )
    child_path = (
        data_root
        / "03-filter"
        / "bond_issuance"
        / "subfilters"
        / "bond_issuance_kosdaq"
        / "filtered.json"
    )
    child_path.parent.mkdir(parents=True)
    child_path.write_text(
        json.dumps(
            {
                "format": "kind_disclosure_filter_v1",
                "parent_mode": "bond_issuance",
                "parent_result_fingerprint": html_common._source_json_fingerprint(
                    parent_payload
                ),
                "disclosures": [parent_payload["disclosures"][0]],
            }
        ),
        encoding="utf-8",
    )

    output_directory = data_root / "04-external-html-download" / "bond_issuance"
    (output_directory / "2025").mkdir(parents=True)
    for acpt_no in ("20250101000001", "20250101000002"):
        (output_directory / "2025" / f"{acpt_no}.html").write_text(
            _valid_download_html(), encoding="utf-8"
        )
    create_external_html_integrity_baseline_payload(
        {
            **parent_body,
            "output_directory": str(output_directory),
            "trust_existing_files": True,
        }
    )

    monkeypatch.setattr(
        html_cleanup,
        "manage_filter_presets_payload",
        lambda _payload: {
            "presets": [
                {"id": "bond_issuance", "mode": "bond_issuance"},
                {
                    "id": "bond_issuance/bond_issuance_kosdaq",
                    "mode": "bond_issuance_kosdaq",
                    "parent_mode": "bond_issuance",
                },
            ]
        },
    )
    hash_calls = 0
    real_validation = html_common._html_file_validation_and_integrity

    def tracked_validation(path):
        nonlocal hash_calls
        hash_calls += 1
        return real_validation(path)

    monkeypatch.setattr(
        html_common,
        "_html_file_validation_and_integrity",
        tracked_validation,
    )

    result = html_cleanup.inspect_all_disclosure_external_html_payload(
        {"data_root": str(data_root)}
    )

    assert result["passed"] is True
    assert result["mode_count"] == 2
    assert hash_calls == 2
    derived_result = result["results"][1]
    direct_result = check_disclosure_html_output_directory_payload(
        html_cleanup.apply_workspace_defaults(
            "external_html_download",
            {
                "data_root": str(data_root),
                "mode": "bond_issuance_kosdaq",
                "parent_mode": "bond_issuance",
            },
        )
    )
    for key, value in direct_result.items():
        assert derived_result[key] == value


def test_all_internal_html_inspection_reuses_parent_file_hashes_for_derived_filter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import finiq.market_desk.web.features.disclosures.html_cleanup as html_cleanup
    import finiq.market_desk.web.features.disclosures.html_common as html_common

    parent_body = _external_workspace_body(
        tmp_path,
        {
            "disclosures": [
                {"acpt_no": "20250101000001"},
                {"acpt_no": "20250101000002"},
            ]
        },
    )
    data_root = Path(str(parent_body["data_root"]))
    parent_payload = json.loads(
        (data_root / "03-filter" / "bond_issuance" / "filtered.json").read_text(
            encoding="utf-8"
        )
    )
    child_path = (
        data_root
        / "03-filter"
        / "bond_issuance"
        / "subfilters"
        / "bond_issuance_kosdaq"
        / "filtered.json"
    )
    child_path.parent.mkdir(parents=True)
    child_path.write_text(
        json.dumps(
            {
                "format": "kind_disclosure_filter_v1",
                "parent_mode": "bond_issuance",
                "parent_result_fingerprint": html_common._source_json_fingerprint(
                    parent_payload
                ),
                "disclosures": [parent_payload["disclosures"][0]],
            }
        ),
        encoding="utf-8",
    )
    compressed_path = (
        data_root
        / "04-external-html-compress"
        / "bond_issuance"
        / "compressed-external-html.json"
    )
    compressed_path.parent.mkdir(parents=True)
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                    {
                        "acpt_no": acpt_no,
                        "selected_main_doc_no": f"{acpt_no[:-2]}99",
                        "metadata": {"disclosed_at": "2025-01-01"},
                    }
                    for acpt_no in ("20250101000001", "20250101000002")
                ],
            }
        ),
        encoding="utf-8",
    )
    output_directory = data_root / "05-internal-html-download" / "bond_issuance"
    (output_directory / "2025").mkdir(parents=True)
    for acpt_no in ("20250101000001", "20250101000002"):
        (output_directory / "2025" / f"{acpt_no}.html").write_text(
            _valid_download_html(), encoding="utf-8"
        )
    html_cleanup.create_internal_html_integrity_baseline_payload(
        {
            "source_compressed_json_path": str(compressed_path),
            "output_directory": str(output_directory),
            "trust_existing_files": True,
        }
    )

    monkeypatch.setattr(
        html_cleanup,
        "manage_filter_presets_payload",
        lambda _payload: {
            "presets": [
                {"id": "bond_issuance", "mode": "bond_issuance"},
                {
                    "id": "bond_issuance/bond_issuance_kosdaq",
                    "mode": "bond_issuance_kosdaq",
                    "parent_mode": "bond_issuance",
                },
            ]
        },
    )
    hash_calls = 0
    real_validation = html_common._html_file_validation_and_integrity

    def tracked_validation(path):
        nonlocal hash_calls
        hash_calls += 1
        return real_validation(path)

    monkeypatch.setattr(
        html_common,
        "_html_file_validation_and_integrity",
        tracked_validation,
    )

    result = html_cleanup.inspect_all_disclosure_internal_html_payload(
        {"data_root": str(data_root)}
    )

    assert result["passed"] is True
    assert result["mode_count"] == 2
    assert hash_calls == 2


def test_check_disclosure_external_html_output_directory_uses_single_worker_for_single_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import finiq.market_desk.web.features.disclosures.html_common as disclosure_html

    def fail_executor(*args, **kwargs):
        raise AssertionError("single target should not start ThreadPoolExecutor")

    monkeypatch.setattr(disclosure_html, "ThreadPoolExecutor", fail_executor)

    output_directory = tmp_path / "viewer_html"
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "2025" / "20250101000001.html").write_text(
        _valid_download_html(), encoding="utf-8"
    )

    payload = check_disclosure_html_output_directory_payload(
        _external_workspace_body(
            tmp_path,
            {"disclosures": [{"acpt_no": "20250101000001"}]},
            output_directory=str(output_directory),
        )
    )

    assert payload["has_existing"] is True
    assert payload["existing_target_html_count"] == 1


def test_download_disclosure_external_html_payload_logs_existing_html_overlap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    download_events: list[None] = []

    def fake_download(**kwargs):
        assert kwargs["acpt_numbers"] == ["20250101000002"]
        assert kwargs["skip_existing"] is False
        paths = []
        for acpt_no in kwargs["acpt_numbers"]:
            path = Path(kwargs["target_output_directories"][acpt_no]) / f"{acpt_no}.html"
            path.write_text(_valid_download_html(), encoding="utf-8")
            kwargs["progress_callback"](f"Saved KIND external HTML to: {path}")
            paths.append(path)
        return paths

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls", fake_download)
    output_directory = tmp_path / "viewer_html"
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "2025" / "20250101000001.html").write_text(
        _valid_download_html(), encoding="utf-8"
    )
    source = {
        "disclosures": [
            {"acpt_no": "20250101000001"},
            {"acpt_no": "20250101000002"},
        ]
    }
    create_external_html_integrity_baseline_payload(
        _external_workspace_body(
            tmp_path,
            source,
            output_directory=str(output_directory),
            trust_existing_files=True,
        )
    )

    payload = download_disclosure_external_html_payload(
        _external_workspace_body(
            tmp_path,
            source,
            output_directory=str(output_directory),
            skip_existing=True,
            progress_interval=1,
        ),
        download_callback=lambda: download_events.append(None),
    )

    assert "기존 HTML 겹침 확인: 1/2건." in payload["progress_log"]
    assert "새로 저장할 대상: 1건." in payload["progress_log"]
    assert "HTML 저장 중간 확인: 1/2건 처리." in payload["progress_log"]
    assert len(download_events) == 1
    assert payload["saved_files"] == [
        str(output_directory / "2025" / "20250101000001.html"),
        str(output_directory / "2025" / "20250101000002.html"),
    ]


def test_download_disclosure_external_html_payload_logs_when_no_existing_html_overlap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_download(**kwargs):
        assert kwargs["acpt_numbers"] == ["20250101000001"]
        assert kwargs["skip_existing"] is False
        paths = []
        for acpt_no in kwargs["acpt_numbers"]:
            path = Path(kwargs["output_directory"]) / f"{acpt_no}.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_valid_download_html(), encoding="utf-8")
            paths.append(path)
        return paths

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls", fake_download)
    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()

    payload = download_disclosure_external_html_payload(
        _external_workspace_body(
            tmp_path,
            {"disclosures": [{"acpt_no": "20250101000001"}]},
            output_directory=str(output_directory),
            skip_existing=True,
        )
    )

    assert "기존 HTML 겹침 확인: 0/1건." in payload["progress_log"]
    assert "기존 HTML 겹침 없음: 전체 대상이 새로 저장됩니다." in payload["progress_log"]


def test_check_disclosure_html_output_directory_rejects_source_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="source_directory is not supported"):
        check_disclosure_html_output_directory_payload(
            {
                "output_directory": str(tmp_path / "content_html"),
                "source_directory": str(tmp_path / "viewer_html"),
            }
        )


def test_download_disclosure_external_html_payload_rejects_unexpected_resume_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_download(**kwargs):
        raise AssertionError(
            "download should not start when output directory has unexpected files"
        )

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls",
        fake_download,
    )
    output_directory = tmp_path / "viewer_html"
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "2024").mkdir()
    (output_directory / "2025" / "20250101000001.html").write_text(
        _valid_download_html(), encoding="utf-8"
    )
    (output_directory / "2024" / "20240101000001.html").write_text(
        "<html></html>", encoding="utf-8"
    )

    try:
        download_disclosure_external_html_payload(
            _external_workspace_body(
                tmp_path,
                {"disclosures": [{"acpt_no": "20250101000001"}]},
                output_directory=str(output_directory),
                skip_existing=True,
            )
        )
    except ValueError as exc:
        assert "HTML 저장 디렉토리에 대상 접수번호 HTML이 아닌 파일이 있습니다" in str(exc)
        assert f"저장 경로: {output_directory}" in str(exc)
        assert "전체 검사 결과" in str(exc)
        assert "- 전체 파일: 2개" in str(exc)
        assert "- 대상 접수번호 HTML: 1개 / 1개" in str(exc)
        assert "문제 파일: 1개" in str(exc)
        assert "2024/20240101000001.html (대상 접수번호 목록에 없는 HTML)" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_download_disclosure_external_html_payload_limits_problem_file_details(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_download(**kwargs):
        raise AssertionError("download should not start with unexpected files")

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls",
        fake_download,
    )
    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()
    for index in range(3):
        (output_directory / f"unexpected-{index}.html").write_text(
            "<html></html>", encoding="utf-8"
        )

    with pytest.raises(ValueError) as exc_info:
        download_disclosure_external_html_payload(
            _external_workspace_body(
                tmp_path,
                {"disclosures": [{"acpt_no": "20250101000001"}]},
                output_directory=str(output_directory),
                skip_existing=True,
                problem_file_limit=2,
            )
        )

    message = str(exc_info.value)
    assert "문제 파일: 3개" in message
    assert "문제 파일 (최대 2개 표시)" in message
    assert "unexpected-0.html" in message
    assert "unexpected-1.html" in message
    assert "unexpected-2.html" not in message
    assert "나머지 1개는 표시하지 않았습니다" in message


def test_clean_disclosure_external_html_output_directory_deletes_unexpected_external_files(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "viewer_html"
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "2024").mkdir()
    expected = output_directory / "2025" / "20250101000001.html"
    unexpected = output_directory / "2024" / "20240101000001.html"
    expected.write_text("<html></html>", encoding="utf-8")
    unexpected.write_text("<html></html>", encoding="utf-8")

    body = _external_workspace_body(
        tmp_path,
        {"disclosures": [{"acpt_no": "20250101000001"}]},
        output_directory=str(output_directory),
    )
    inspected = clean_disclosure_html_output_directory_payload(
        {**body, "dry_run": True}
    )
    payload = clean_disclosure_html_output_directory_payload(
        {
            **body,
            "delete_confirmed": True,
            "delete_confirmation_text": "확인했습니다.",
            "deletion_confirmation": inspected["deletion_confirmation"],
        }
    )

    assert payload["source_type"] == "external"
    assert payload["deleted_count"] == 1
    assert payload["deleted_files"] == [
        {
            "path": str(unexpected),
            "name": "2024/20240101000001.html",
            "reason": "대상 접수번호 목록에 없는 HTML",
        }
    ]
    assert expected.exists()
    assert not unexpected.exists()


def test_clean_disclosure_external_html_output_directory_requires_delete_confirmation(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()
    unexpected = output_directory / "20240101000001.html"
    unexpected.write_text("<html></html>", encoding="utf-8")

    try:
        clean_disclosure_html_output_directory_payload(
            _external_workspace_body(
                tmp_path,
                {"disclosures": [{"acpt_no": "20250101000001"}]},
                output_directory=str(output_directory),
            )
        )
    except ValueError as exc:
        assert '"확인했습니다." 입력과 삭제 허가가 필요합니다' in str(exc)
    else:
        raise AssertionError("expected ValueError")

    assert unexpected.exists()


def test_clean_disclosure_external_html_output_directory_rejects_high_risk_directory(
    tmp_path: Path,
) -> None:
    root = Path(Path.cwd().anchor).resolve()

    with pytest.raises(ValueError, match="high-risk output_directory"):
        clean_disclosure_html_output_directory_payload(
            _external_workspace_body(
                tmp_path,
                {"disclosures": [{"acpt_no": "20250101000001"}]},
                output_directory=str(root),
                dry_run=True,
            )
        )


def test_clean_disclosure_external_html_output_directory_dry_run_reports_delete_count(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()
    unexpected = output_directory / "20240101000001.html"
    unexpected.write_text("<html></html>", encoding="utf-8")

    payload = clean_disclosure_html_output_directory_payload(
        _external_workspace_body(
            tmp_path,
            {"disclosures": [{"acpt_no": "20250101000001"}]},
            output_directory=str(output_directory),
            dry_run=True,
        )
    )

    assert payload["dry_run"] is True
    assert payload["deleted_count"] == 0
    assert payload["deletion_candidate_count"] == 1
    assert payload["deletion_candidates"][0]["name"] == "20240101000001.html"
    assert unexpected.exists()


def test_clean_disclosure_external_html_output_directory_limits_reported_candidates(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()
    for index in range(3):
        (output_directory / f"unexpected-{index}.html").write_text(
            "<html></html>", encoding="utf-8"
        )

    payload = clean_disclosure_html_output_directory_payload(
        _external_workspace_body(
            tmp_path,
            {"disclosures": [{"acpt_no": "20250101000001"}]},
            output_directory=str(output_directory),
            dry_run=True,
            problem_file_limit=2,
        )
    )

    assert payload["deletion_candidate_count"] == 3
    assert len(payload["deletion_candidates"]) == 2
    assert payload["deleted_file_omitted_count"] == 1


def test_clean_disclosure_external_html_output_directory_deletes_unexpected_content_files(
    tmp_path: Path,
) -> None:
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [{
                    "acpt_no": "20250101000001",
                    "selected_main_doc_no": "1",
                    "metadata": {"disclosed_at": "2025-01-01"},
                }],
            }
        ),
        encoding="utf-8",
    )
    output_directory = tmp_path / "content_html"
    (output_directory / "2025").mkdir(parents=True)
    expected = output_directory / "2025" / "20250101000001.html"
    unexpected = output_directory / "parsed-old.json"
    expected.write_text("<html></html>", encoding="utf-8")
    unexpected.write_text("{}", encoding="utf-8")

    body = {
        "output_directory": str(output_directory),
        "source_compressed_json_path": str(compressed_path),
    }
    inspected = clean_disclosure_html_output_directory_payload(
        {**body, "dry_run": True}
    )
    payload = clean_disclosure_html_output_directory_payload(
        {
            **body,
            "delete_confirmed": True,
            "delete_confirmation_text": "확인했습니다.",
            "deletion_confirmation": inspected["deletion_confirmation"],
        }
    )

    assert payload["source_type"] == "content"
    assert payload["deleted_count"] == 1
    assert payload["deleted_files"][0]["name"] == "parsed-old.json"
    assert payload["deleted_files"][0]["reason"] == "파싱 결과 JSON"
    assert expected.exists()
    assert not unexpected.exists()


def test_clean_disclosure_external_html_output_directory_deletes_unexpected_yearly_files(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "viewer_html"
    year_directory = output_directory / "2025"
    year_directory.mkdir(parents=True)
    expected = year_directory / "20250101000001.html"
    unexpected = year_directory / "20240101000001.html"
    expected.write_text("<html></html>", encoding="utf-8")
    unexpected.write_text("<html></html>", encoding="utf-8")

    body = _external_workspace_body(
        tmp_path,
        {
            "disclosures": [
                {
                    "acpt_no": "20250101000001",
                    "disclosed_at": "2025-01-01",
                }
            ]
        },
        output_directory=str(output_directory),
    )
    inspected = clean_disclosure_html_output_directory_payload(
        {**body, "dry_run": True}
    )
    payload = clean_disclosure_html_output_directory_payload(
        {
            **body,
            "delete_confirmed": True,
            "delete_confirmation_text": "확인했습니다.",
            "deletion_confirmation": inspected["deletion_confirmation"],
        }
    )

    assert payload["deleted_count"] == 1
    assert payload["deleted_files"][0]["name"] == "2025/20240101000001.html"
    assert expected.exists()
    assert not unexpected.exists()


def test_clean_disclosure_html_rejects_delete_when_target_limit_changed_after_inspection(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "viewer_html"
    year_directory = output_directory / "2025"
    year_directory.mkdir(parents=True)
    first = year_directory / "20250101000001.html"
    second = year_directory / "20250102000002.html"
    unexpected = year_directory / "20240101000001.html"
    for path in (first, second, unexpected):
        path.write_text("<html></html>", encoding="utf-8")
    body = _external_workspace_body(
        tmp_path,
        {
            "disclosures": [
                {"acpt_no": first.stem, "disclosed_at": "2025-01-01"},
                {"acpt_no": second.stem, "disclosed_at": "2025-01-02"},
            ]
        },
        output_directory=str(output_directory),
    )
    inspected = clean_disclosure_html_output_directory_payload(
        {**body, "dry_run": True}
    )

    with pytest.raises(ValueError, match="changed after inspection"):
        clean_disclosure_html_output_directory_payload(
            {
                **body,
                "limit": 1,
                "delete_confirmed": True,
                "delete_confirmation_text": "확인했습니다.",
                "deletion_confirmation": inspected["deletion_confirmation"],
            }
        )

    assert first.exists()
    assert second.exists()
    assert unexpected.exists()


def test_clean_disclosure_html_rejects_symlinked_year_directory(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()
    outside_directory = tmp_path / "outside"
    outside_directory.mkdir()
    outside_file = outside_directory / "20240101000001.html"
    outside_file.write_text("<html></html>", encoding="utf-8")
    (output_directory / "2025").symlink_to(
        outside_directory,
        target_is_directory=True,
    )
    body = _external_workspace_body(
        tmp_path,
        {
            "disclosures": [
                {
                    "acpt_no": "20250101000001",
                    "disclosed_at": "2025-01-01",
                }
            ]
        },
        output_directory=str(output_directory),
    )

    with pytest.raises(ValueError, match="must not contain symbolic links"):
        clean_disclosure_html_output_directory_payload(
            {**body, "dry_run": True}
        )

    assert outside_file.read_text(encoding="utf-8") == "<html></html>"


def test_clean_disclosure_html_restores_candidates_when_quarantine_move_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_directory = tmp_path / "viewer_html"
    year_directory = output_directory / "2025"
    year_directory.mkdir(parents=True)
    expected = year_directory / "20250101000001.html"
    unexpected = [
        year_directory / "20240101000001.html",
        year_directory / "20240102000002.html",
    ]
    expected.write_text("expected", encoding="utf-8")
    for index, path in enumerate(unexpected, start=1):
        path.write_text(f"unexpected {index}", encoding="utf-8")
    body = _external_workspace_body(
        tmp_path,
        {
            "disclosures": [
                {
                    "acpt_no": expected.stem,
                    "disclosed_at": "2025-01-01",
                }
            ]
        },
        output_directory=str(output_directory),
    )
    inspected = clean_disclosure_html_output_directory_payload(
        {**body, "dry_run": True}
    )
    original_replace = html_common_module.os.replace
    quarantine_moves = 0

    def fail_second_quarantine_move(source: object, target: object) -> None:
        nonlocal quarantine_moves
        target_path = Path(target)
        if target_path.parent.name.startswith(".finiq-html-delete-"):
            quarantine_moves += 1
            if quarantine_moves == 2:
                raise OSError("quarantine move failed")
        original_replace(source, target)

    monkeypatch.setattr(
        html_common_module.os,
        "replace",
        fail_second_quarantine_move,
    )

    with pytest.raises(OSError, match="quarantine move failed"):
        clean_disclosure_html_output_directory_payload(
            {
                **body,
                "delete_confirmed": True,
                "delete_confirmation_text": "확인했습니다.",
                "deletion_confirmation": inspected["deletion_confirmation"],
            }
        )

    assert expected.read_text(encoding="utf-8") == "expected"
    assert [path.read_text(encoding="utf-8") for path in unexpected] == [
        "unexpected 1",
        "unexpected 2",
    ]
    assert not list(output_directory.glob(".finiq-html-delete-*"))


def test_clean_disclosure_external_html_output_directory_allows_compressed_external_json(tmp_path: Path) -> None:
    output_directory = tmp_path / "viewer_html"
    (output_directory / "2025").mkdir(parents=True)
    expected = output_directory / "2025" / "20250101000001.html"
    compressed = output_directory / "compressed-external-html.json"
    expected.write_text("<html></html>", encoding="utf-8")
    compressed.write_text("{}", encoding="utf-8")

    payload = clean_disclosure_html_output_directory_payload(
        _external_workspace_body(
            tmp_path,
            {"disclosures": [{"acpt_no": "20250101000001"}]},
            output_directory=str(output_directory),
            delete_confirmed=True,
            delete_confirmation_text="확인했습니다.",
        )
    )

    assert payload["deleted_count"] == 0
    assert payload["unexpected_file_count"] == 0
    assert expected.exists()
    assert compressed.exists()


def test_download_disclosure_external_html_payload_resumes_yearly_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[Path, list[str]]] = []

    def fake_download(**kwargs):
        acpt_numbers = list(kwargs["acpt_numbers"])
        calls.append((Path(kwargs["output_directory"]), acpt_numbers))
        paths = []
        for acpt_no in acpt_numbers:
            path = Path(kwargs["target_output_directories"][acpt_no]) / f"{acpt_no}.html"
            path.write_text(_valid_download_html(), encoding="utf-8")
            paths.append(path)
        return paths

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls", fake_download)

    output_directory = tmp_path / "viewer_html"
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "2025" / "20250101000001.html").write_text(
        _valid_download_html(), encoding="utf-8"
    )
    source = {
        "disclosures": [
            {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"},
            {"acpt_no": "20250101000002", "disclosed_at": "2025-01-02"},
        ]
    }
    create_external_html_integrity_baseline_payload(
        _external_workspace_body(
            tmp_path,
            source,
            output_directory=str(output_directory),
            trust_existing_files=True,
        )
    )

    payload = download_disclosure_external_html_payload(
        _external_workspace_body(
            tmp_path,
            source,
            output_directory=str(output_directory),
            skip_existing=True,
        )
    )

    assert calls == [(output_directory, ["20250101000002"])]
    assert payload["saved_files"] == [
        str(output_directory / "2025" / "20250101000001.html"),
        str(output_directory / "2025" / "20250101000002.html"),
    ]


def test_inspect_download_output_directory_requires_confirmation_for_mismatch(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "download"
    output_directory.mkdir()
    body_path = output_directory / "001_post_page_00001.body"
    body_path.write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    (output_directory / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(page_size=50)),
        encoding="utf-8",
    )

    dry_run_payload = inspect_download_output_directory_payload(
        {
            "mode": "single",
            "output_directory": str(output_directory),
            "page_size": 50,
            "dry_run": True,
        }
    )

    assert dry_run_payload["deleted_count"] == 0
    assert dry_run_payload["deletion_candidate_count"] == 2
    assert {item["name"] for item in dry_run_payload["deletion_candidates"]} == {
        "001_post_page_00001.body",
        "kind_workflow.input.json",
    }
    assert body_path.exists()

    with pytest.raises(ValueError, match='"확인했습니다." 입력과 삭제 허가가 필요합니다'):
        inspect_download_output_directory_payload(
            {
                "mode": "single",
                "output_directory": str(output_directory),
                "page_size": 50,
                "dry_run": False,
            }
        )

    assert body_path.exists()


def test_inspect_download_output_directory_deletes_confirmed_mismatch(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "download"
    output_directory.mkdir()
    body_path = output_directory / "001_post_page_00001.body"
    body_path.write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    (output_directory / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(page_size=50)),
        encoding="utf-8",
    )

    payload = inspect_download_output_directory_payload(
        {
            "mode": "single",
            "output_directory": str(output_directory),
            "page_size": 50,
            "dry_run": False,
            "delete_confirmed": True,
            "delete_confirmation_text": "확인했습니다.",
        }
    )

    assert payload["deleted_count"] == 2
    assert payload["summary"] == {"success": 0, "failed": 0, "total": 0}
    assert not body_path.exists()
    assert not (output_directory / "kind_workflow.input.json").exists()


def test_inspect_download_output_directory_uses_configured_page_workers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import finiq.concurrency as concurrency
    import finiq.market_desk.web.features.downloads.kind_inspect as kind_inspect

    output_directory = tmp_path / "download"
    output_directory.mkdir()
    (output_directory / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(
            page_number=1,
            page_size=100,
            total_items=1,
        )
    )
    (output_directory / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(page_size=100)),
        encoding="utf-8",
    )
    used_parallelism: list[int | None] = []

    def fake_inspect(
        _folder: Path,
        *,
        expected_page_size: int,
        require_complete: bool,
        validation_parallelism: int | None = None,
    ) -> dict[str, int]:
        assert expected_page_size == 100
        assert require_complete is False
        used_parallelism.append(validation_parallelism)
        return {"downloaded_pages": 1, "total_pages": 1, "total_items": 1}

    monkeypatch.setattr(concurrency, "available_cpu_count", lambda: 4)
    monkeypatch.setattr(kind_inspect, "inspect_download_directory_pages", fake_inspect)

    payload = kind_inspect.inspect_download_output_directory_payload(
        {
            "mode": "single",
            "output_directory": str(output_directory),
            "page_size": 100,
            "worker_count": 3,
            "dry_run": True,
        }
    )

    assert used_parallelism == [3]
    assert payload["summary"] == {"success": 1, "failed": 0, "total": 1}


def test_inspect_download_output_directory_parallelizes_year_folders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import finiq.concurrency as concurrency
    import finiq.market_desk.web.features.downloads.kind_inspect as kind_inspect

    output_directory = tmp_path / "download"
    ranges = [
        ("20250101_20251231", "2025-01-01", "2025-12-31"),
        ("20260101_20261231", "2026-01-01", "2026-12-31"),
    ]
    for folder_name, start_date, end_date in ranges:
        folder = output_directory / folder_name
        folder.mkdir(parents=True)
        (folder / "001_post_page_00001.body").write_bytes(
            _build_download_result_page_html(
                page_number=1,
                page_size=100,
                total_items=1,
            )
        )
        (folder / "kind_workflow.input.json").write_text(
            json.dumps(
                _trusted_download_input_snapshot(
                    start_date=start_date,
                    end_date=end_date,
                    page_size=100,
                )
            ),
            encoding="utf-8",
        )

    barrier = threading.Barrier(2)
    used_parallelism: list[int | None] = []

    def fake_inspect(
        _folder: Path,
        *,
        expected_page_size: int,
        require_complete: bool,
        validation_parallelism: int | None = None,
    ) -> dict[str, int]:
        assert expected_page_size == 100
        assert require_complete is False
        used_parallelism.append(validation_parallelism)
        barrier.wait(timeout=2)
        return {"downloaded_pages": 1, "total_pages": 1, "total_items": 1}

    monkeypatch.setattr(concurrency, "available_cpu_count", lambda: 4)
    monkeypatch.setattr(kind_inspect, "inspect_download_directory_pages", fake_inspect)

    payload = kind_inspect.inspect_download_output_directory_payload(
        {
            "mode": "yearly",
            "output_directory": str(output_directory),
            "start_date": "2025-01-01",
            "end_date": "2026-12-31",
            "page_size": 100,
            "worker_count": 2,
            "dry_run": True,
        }
    )

    assert sorted(used_parallelism) == [1, 1]
    assert payload["summary"] == {"success": 2, "failed": 0, "total": 2}


def test_inspect_download_output_directory_finishes_confirmed_deletion_batch(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "download"
    output_directory.mkdir()
    body_path = output_directory / "001_post_page_00001.body"
    body_path.write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    input_path = output_directory / "kind_workflow.input.json"
    input_path.write_text(
        json.dumps(_trusted_download_input_snapshot(page_size=50)),
        encoding="utf-8",
    )
    cancel_checks = 0

    def cancel_after_deletion_starts() -> bool:
        nonlocal cancel_checks
        cancel_checks += 1
        return cancel_checks >= 4

    payload = inspect_download_output_directory_payload(
        {
            "mode": "single",
            "output_directory": str(output_directory),
            "page_size": 100,
            "dry_run": False,
            "delete_confirmed": True,
            "delete_confirmation_text": "확인했습니다.",
        },
        cancel_check=cancel_after_deletion_starts,
    )

    assert payload["deleted_count"] == 2
    assert not body_path.exists()
    assert not input_path.exists()


def test_inspect_download_output_directory_regression_cases(tmp_path: Path) -> None:
    def write_page(folder: Path, page_number: int, page_size: int, total_items: int, html_content: bytes | None = None) -> Path:
        p = folder / f"001_post_page_{page_number:05d}.body"
        if html_content is None:
            html_content = _build_download_result_page_html(
                page_number=page_number, page_size=page_size, total_items=total_items
            )
        p.write_bytes(html_content)
        return p

    # 1. Corrupt page
    dir_corrupt = tmp_path / "corrupt"
    dir_corrupt.mkdir()
    (dir_corrupt / "kind_workflow.input.json").write_text(json.dumps(_trusted_download_input_snapshot(page_size=100)), encoding="utf-8")
    write_page(dir_corrupt, 1, 100, 100, html_content=b"<html><body>no paging group</body></html>")

    res = inspect_download_output_directory_payload({
        "mode": "single",
        "output_directory": str(dir_corrupt),
        "page_size": 100,
        "dry_run": True,
    })
    assert res["deletion_candidate_count"] == 2
    assert "페이지네이션 정보를 찾지 못했습니다" in res["deletion_candidates"][0]["reason"]

    # 2. Duplicate page
    dir_dup = tmp_path / "duplicate"
    dir_dup.mkdir()
    (dir_dup / "kind_workflow.input.json").write_text(json.dumps(_trusted_download_input_snapshot(page_size=100)), encoding="utf-8")
    write_page(dir_dup, 1, 100, 150)
    p2 = dir_dup / "001_post_page_00002.body"
    p2.write_bytes(_build_download_result_page_html(page_number=1, page_size=100, total_items=150))

    res = inspect_download_output_directory_payload({
        "mode": "single",
        "output_directory": str(dir_dup),
        "page_size": 100,
        "dry_run": True,
    })
    assert res["deletion_candidate_count"] == 3
    assert "중복되는 페이지 번호" in res["deletion_candidates"][0]["reason"]

    # 3. Page gap
    dir_gap = tmp_path / "gap"
    dir_gap.mkdir()
    (dir_gap / "kind_workflow.input.json").write_text(json.dumps(_trusted_download_input_snapshot(page_size=100)), encoding="utf-8")
    write_page(dir_gap, 1, 100, 300)
    write_page(dir_gap, 3, 100, 300)

    res = inspect_download_output_directory_payload({
        "mode": "single",
        "output_directory": str(dir_gap),
        "page_size": 100,
        "dry_run": True,
    })
    assert res["deletion_candidate_count"] == 3
    assert "연속적이지 않습니다" in res["deletion_candidates"][0]["reason"]

    # 4. Inconsistent totals
    dir_inc = tmp_path / "inconsistent"
    dir_inc.mkdir()
    (dir_inc / "kind_workflow.input.json").write_text(json.dumps(_trusted_download_input_snapshot(page_size=100)), encoding="utf-8")
    write_page(dir_inc, 1, 100, 150)
    p2 = dir_inc / "001_post_page_00002.body"
    p2.write_bytes(_build_download_result_page_html(page_number=2, page_size=100, total_items=200))

    res = inspect_download_output_directory_payload({
        "mode": "single",
        "output_directory": str(dir_inc),
        "page_size": 100,
        "dry_run": True,
    })
    assert res["deletion_candidate_count"] == 3
    assert "전체 페이지 수 또는 전체 건수가 서로 다릅니다" in res["deletion_candidates"][0]["reason"]

    # 5. Page_size mismatch (metadata vs request)
    dir_ps_meta = tmp_path / "ps_meta"
    dir_ps_meta.mkdir()
    (dir_ps_meta / "kind_workflow.input.json").write_text(json.dumps(_trusted_download_input_snapshot(page_size=100)), encoding="utf-8")
    write_page(dir_ps_meta, 1, 100, 100)

    res = inspect_download_output_directory_payload({
        "mode": "single",
        "output_directory": str(dir_ps_meta),
        "page_size": 50,
        "dry_run": True,
    })
    assert res["deletion_candidate_count"] == 2
    assert "페이지 크기와 맞지 않는" in res["deletion_candidates"][0]["reason"]

    # 5b. Page_size mismatch (actual rows in html)
    dir_ps_rows = tmp_path / "ps_rows"
    dir_ps_rows.mkdir()
    (dir_ps_rows / "kind_workflow.input.json").write_text(json.dumps(_trusted_download_input_snapshot(page_size=100)), encoding="utf-8")
    write_page(dir_ps_rows, 1, 100, 150, html_content=_build_download_result_page_html(page_number=1, page_size=50, total_items=150))

    res = inspect_download_output_directory_payload({
        "mode": "single",
        "output_directory": str(dir_ps_rows),
        "page_size": 100,
        "dry_run": True,
    })
    assert res["deletion_candidate_count"] == 2
    assert "기대값" in res["deletion_candidates"][0]["reason"]

    # 6. Missing snapshot
    dir_missing = tmp_path / "missing_snapshot"
    dir_missing.mkdir()
    write_page(dir_missing, 1, 100, 100)

    with pytest.raises(ValueError, match="metadata is missing"):
        inspect_download_output_directory_payload({
            "mode": "single",
            "output_directory": str(dir_missing),
            "page_size": 100,
            "dry_run": True,
        })

    # 7. Yearly mode
    dir_yearly = tmp_path / "yearly"
    dir_yearly.mkdir()

    dir_2024 = dir_yearly / "20240101_20241231"
    dir_2024.mkdir()
    (dir_2024 / "kind_workflow.input.json").write_text(json.dumps(_trusted_download_input_snapshot(start_date="2024-01-01", end_date="2024-12-31", page_size=100)), encoding="utf-8")
    write_page(dir_2024, 1, 100, 100)

    dir_2025 = dir_yearly / "20250101_20251231"
    dir_2025.mkdir()
    (dir_2025 / "kind_workflow.input.json").write_text(json.dumps(_trusted_download_input_snapshot(start_date="2025-01-01", end_date="2025-12-31", page_size=100)), encoding="utf-8")
    write_page(dir_2025, 1, 100, 150, html_content=_build_download_result_page_html(page_number=1, page_size=50, total_items=150))

    res = inspect_download_output_directory_payload({
        "mode": "yearly",
        "output_directory": str(dir_yearly),
        "page_size": 100,
        "dry_run": True,
        "start_date": "2024-01-01",
        "end_date": "2025-12-31",
    })
    assert res["deletion_candidate_count"] == 2
    assert "20250101_20251231" in res["deletion_candidates"][0]["path"]
    assert "기대값" in res["deletion_candidates"][0]["reason"]

    # 8. Folder range differs from metadata range
    mismatched_range = dir_yearly / "20260101_20261231"
    mismatched_range.mkdir()
    (mismatched_range / "kind_workflow.input.json").write_text(
        json.dumps(
            _trusted_download_input_snapshot(
                start_date="2025-01-01",
                end_date="2025-12-31",
                page_size=100,
            )
        ),
        encoding="utf-8",
    )
    write_page(mismatched_range, 1, 100, 100)

    res = inspect_download_output_directory_payload({
        "mode": "yearly",
        "output_directory": str(dir_yearly),
        "page_size": 100,
        "dry_run": True,
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
    })
    assert res["deletion_candidate_count"] == 2
    assert "메타데이터 기간 2025-01-01~2025-12-31" in res["deletion_candidates"][0]["reason"]


def test_inspect_folder_job_cancellation(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_common import DownloadCancelled
    from finiq.market_desk.web.features.downloads.kind_jobs import (
        start_inspect_folder_job,
        cancel_download_job,
        get_download_job,
    )
    import time

    def blocking_inspect(payload, progress_callback=None, cancel_check=None):
        for _ in range(200):
            if cancel_check is not None and cancel_check():
                raise DownloadCancelled("Folder inspection cancelled by the user")
            time.sleep(0.01)
        return {"format": "kind_download_folder_cleanup_v1"}

    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_jobs.inspect_download_output_directory_payload",
        blocking_inspect,
    )

    output_dir = tmp_path / "cancel_job"
    output_dir.mkdir()
    (output_dir / "kind_workflow.input.json").write_text(json.dumps({"page_size": 100}), encoding="utf-8")

    payload = {
        "mode": "single",
        "output_directory": str(output_dir),
        "page_size": 100,
        "dry_run": True,
    }

    job = start_inspect_folder_job(payload)
    job_id = job["job_id"]

    cancel_download_job(job_id)

    for _ in range(50):
        status = get_download_job(job_id)
        if status["status"] in {"cancelled", "failed", "completed"}:
            break
        time.sleep(0.05)

    status = get_download_job(job_id)
    assert status["status"] == "cancelled"
    assert any("cancelled" in msg.lower() for msg in status["progress_log"])


def test_inspect_folder_job_honors_cancellation_before_start(
    tmp_path: Path, monkeypatch
) -> None:
    from finiq.market_desk.web.features.downloads.kind_jobs import (
        cancel_download_job,
        start_inspect_folder_job,
    )

    requested_job_id = "55555555555545559555555555555555"
    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_jobs.inspect_download_output_directory_payload",
        lambda *_args, **_kwargs: pytest.fail("cancelled inspection must not start"),
    )

    cancelled = cancel_download_job(requested_job_id)
    started = start_inspect_folder_job(
        {
            "job_id": requested_job_id,
            "mode": "single",
            "output_directory": str(tmp_path),
            "page_size": 100,
            "dry_run": True,
        }
    )

    assert cancelled["status"] == "cancelled"
    assert started["job_id"] == requested_job_id
    assert started["status"] == "cancelled"


def test_inspect_folder_job_runs_kind_verification_in_background(
    tmp_path: Path, monkeypatch
) -> None:
    import threading
    import time

    from finiq.market_desk.web.features.downloads.kind_jobs import (
        get_download_job,
        start_inspect_folder_job,
    )

    def fake_inspect(payload, progress_callback=None, cancel_check=None):
        return {
            "format": "kind_download_folder_cleanup_v1",
            "download_statuses": [
                {"output_directory": payload["output_directory"]}
            ],
        }

    verification_calls = []
    verification_started = threading.Event()
    release_verification = threading.Event()

    def fake_check_existing(
        output_directory,
        *,
        verify_with_kind=True,
        current_payload=None,
        cancel_check=None,
        progress_callback=None,
        parallel_workers=None,
        precomputed_download_statuses=None,
    ):
        verification_calls.append(
            (
                output_directory,
                verify_with_kind,
                current_payload,
                precomputed_download_statuses,
            )
        )
        verification_started.set()
        assert release_verification.wait(timeout=1)
        return {"has_existing": True, "ranges": []}

    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_jobs.inspect_download_output_directory_payload",
        fake_inspect,
    )
    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_jobs.check_existing_downloads",
        fake_check_existing,
    )

    payload = {
        "mode": "single",
        "output_directory": str(tmp_path),
        "page_size": 100,
        "dry_run": True,
    }
    job = start_inspect_folder_job(payload)

    assert verification_started.wait(timeout=1)
    running_job = get_download_job(job["job_id"])
    assert running_job["status"] == "running"
    assert any(
        "KIND 건수 비교 실행 순서를 기다리는 중입니다." in line
        for line in running_job["progress_log"]
    )
    release_verification.set()

    for _ in range(100):
        status = get_download_job(job["job_id"])
        if status["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.01)

    assert status["status"] == "completed"
    assert status["result"]["existing_downloads"] == {
        "has_existing": True,
        "ranges": [],
    }
    assert verification_calls == [
        (
            str(tmp_path),
            True,
            payload,
            [{"output_directory": str(tmp_path)}],
        )
    ]


def test_inspect_folder_job_cancels_during_kind_verification(
    tmp_path: Path, monkeypatch
) -> None:
    import threading
    import time

    from finiq.market_desk.web.features.downloads.kind_common import DownloadCancelled
    from finiq.market_desk.web.features.downloads.kind_jobs import (
        cancel_download_job,
        get_download_job,
        start_inspect_folder_job,
    )

    verification_started = threading.Event()
    release_without_callback = threading.Event()
    received_cancel_checks = []

    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_jobs.inspect_download_output_directory_payload",
        lambda payload, progress_callback=None, cancel_check=None: {
            "format": "kind_download_folder_cleanup_v1"
        },
    )

    def cancellable_check_existing(
        output_directory,
        *,
        verify_with_kind=True,
        current_payload=None,
        cancel_check=None,
        progress_callback=None,
        parallel_workers=None,
        precomputed_download_statuses=None,
    ):
        received_cancel_checks.append(cancel_check)
        verification_started.set()
        if cancel_check is None:
            assert release_without_callback.wait(timeout=1)
            return {"has_existing": False}
        while not cancel_check():
            time.sleep(0.005)
        raise DownloadCancelled()

    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_jobs.check_existing_downloads",
        cancellable_check_existing,
    )

    job = start_inspect_folder_job(
        {
            "mode": "single",
            "output_directory": str(tmp_path),
            "page_size": 100,
            "dry_run": True,
        }
    )
    assert verification_started.wait(timeout=1)
    cancel_download_job(job["job_id"])
    release_without_callback.set()

    for _ in range(100):
        status = get_download_job(job["job_id"])
        if status["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.01)

    assert callable(received_cancel_checks[0])
    assert status["status"] == "cancelled"


def test_check_existing_downloads_honors_immediate_cancellation(tmp_path: Path) -> None:
    from finiq.market_desk.web.features.downloads.kind_common import DownloadCancelled
    from finiq.market_desk.web.features.downloads.kind_existing import (
        check_existing_downloads,
    )

    with pytest.raises(DownloadCancelled):
        check_existing_downloads(str(tmp_path), cancel_check=lambda: True)


def test_check_existing_downloads_preserves_cancellation_during_discovery(
    tmp_path: Path,
) -> None:
    from finiq.market_desk.web.features.downloads.kind_common import DownloadCancelled
    from finiq.market_desk.web.features.downloads.kind_existing import (
        check_existing_downloads,
    )

    (tmp_path / "unrelated").mkdir()
    checks = 0

    def cancel_during_discovery() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 2

    with pytest.raises(DownloadCancelled):
        check_existing_downloads(
            str(tmp_path), cancel_check=cancel_during_discovery
        )


def test_inspect_folder_job_finishes_committed_deletion_after_cancel(
    tmp_path: Path, monkeypatch
) -> None:
    import threading
    import time

    from finiq.market_desk.web.features.downloads.kind_jobs import (
        cancel_download_job,
        get_download_job,
        start_inspect_folder_job,
    )

    deletion_committed = threading.Event()
    release_result = threading.Event()
    verification_cancel_checks = []

    def committed_deletion(payload, progress_callback=None, cancel_check=None):
        deletion_committed.set()
        assert release_result.wait(timeout=1)
        return {
            "format": "kind_download_folder_cleanup_v1",
            "dry_run": False,
            "deleted_count": 1,
            "deleted_files": [{"name": "stale.body", "path": "stale.body"}],
        }

    def verify_remaining(
        output_directory,
        *,
        verify_with_kind=True,
        current_payload=None,
        cancel_check=None,
        progress_callback=None,
        parallel_workers=None,
        precomputed_download_statuses=None,
    ):
        verification_cancel_checks.append(cancel_check)
        return {"has_existing": False}

    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_jobs.inspect_download_output_directory_payload",
        committed_deletion,
    )
    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_jobs.check_existing_downloads",
        verify_remaining,
    )

    job = start_inspect_folder_job(
        {"output_directory": str(tmp_path), "mode": "single", "dry_run": False}
    )
    assert deletion_committed.wait(timeout=1)
    cancel_download_job(job["job_id"])
    release_result.set()

    for _ in range(100):
        status = get_download_job(job["job_id"])
        if status["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.01)

    assert status["status"] == "completed"
    assert status["result"]["deleted_count"] == 1
    assert status["result"]["existing_downloads"] == {"has_existing": False}
    assert verification_cancel_checks == [None]


def test_inspect_folder_job_cancellation_wins_finalization_race(
    tmp_path: Path, monkeypatch
) -> None:
    import threading
    import time

    from finiq.market_desk.web.features.downloads import kind_jobs
    from finiq.market_desk.web.features.downloads.kind_jobs import (
        cancel_download_job,
        get_download_job,
        start_inspect_folder_job,
    )

    final_check_started = threading.Event()
    release_final_check = threading.Event()
    original_is_cancelled = kind_jobs._is_download_cancelled
    checks = 0

    def stale_final_cancel_check(job_id):
        nonlocal checks
        checks += 1
        if checks == 3:
            final_check_started.set()
            assert release_final_check.wait(timeout=1)
            return False
        return original_is_cancelled(job_id)

    monkeypatch.setattr(kind_jobs, "_is_download_cancelled", stale_final_cancel_check)
    monkeypatch.setattr(
        kind_jobs,
        "inspect_download_output_directory_payload",
        lambda payload, progress_callback=None, cancel_check=None: {
            "format": "kind_download_folder_cleanup_v1",
            "dry_run": True,
            "deleted_count": 0,
        },
    )
    monkeypatch.setattr(
        kind_jobs,
        "check_existing_downloads",
        lambda *args, **kwargs: {"has_existing": False},
    )

    job = start_inspect_folder_job(
        {"output_directory": str(tmp_path), "mode": "single", "dry_run": True}
    )
    assert final_check_started.wait(timeout=1)
    cancel_download_job(job["job_id"])
    release_final_check.set()

    for _ in range(100):
        status = get_download_job(job["job_id"])
        if status["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.01)

    assert status["status"] == "cancelled"
    assert status["result"] is None


def test_download_start_is_idempotent_for_completed_inspection(
    tmp_path: Path, monkeypatch
) -> None:
    import threading
    import time

    from finiq.market_desk.web.features.downloads import kind_jobs
    from finiq.market_desk.web.features.downloads.kind_jobs import (
        get_download_job,
        start_download_job,
        start_inspect_folder_job,
    )

    monkeypatch.setattr(
        kind_jobs,
        "inspect_download_output_directory_payload",
        lambda payload, progress_callback=None, cancel_check=None: {
            "format": "kind_download_folder_cleanup_v1",
            "dry_run": True,
            "deleted_count": 0,
        },
    )
    monkeypatch.setattr(
        kind_jobs,
        "check_existing_downloads",
        lambda *args, **kwargs: {"has_existing": False},
    )

    inspection = start_inspect_folder_job(
        {"output_directory": str(tmp_path), "mode": "single", "dry_run": True}
    )
    for _ in range(100):
        inspection_status = get_download_job(inspection["job_id"])
        if inspection_status["status"] == "completed":
            break
        time.sleep(0.01)
    assert inspection_status["status"] == "completed"

    download_started = threading.Event()
    release_download = threading.Event()
    calls = 0

    def blocking_download(payload, progress_callback=None, cancel_check=None):
        nonlocal calls
        calls += 1
        download_started.set()
        assert release_download.wait(timeout=1)
        return {"summary": {}}

    monkeypatch.setattr(kind_jobs, "run_download_action", blocking_download)
    payload = {
        "output_directory": str(tmp_path),
        "mode": "single",
        "inspection_job_id": inspection["job_id"],
    }
    first = start_download_job(dict(payload))
    assert download_started.wait(timeout=1)
    second = start_download_job(dict(payload))

    assert second["job_id"] == first["job_id"]
    assert calls == 1
    release_download.set()
    for _ in range(100):
        download_status = get_download_job(first["job_id"])
        if download_status["status"] == "completed":
            break
        time.sleep(0.01)
    assert download_status["status"] == "completed"


def test_download_job_logs_payload_summary_before_running_action(
    tmp_path: Path, monkeypatch
) -> None:
    import time

    from finiq.market_desk.web.features.downloads.kind_jobs import (
        get_download_job,
        start_download_job,
    )

    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_jobs.run_download_action",
        lambda payload, progress_callback=None, cancel_check=None: {"summary": {}},
    )

    job = start_download_job(
        {
            "mode": "single",
            "output_directory": str(tmp_path),
            "start_date": "2026-01-01",
            "end_date": "2026-01-02",
        }
    )

    for _ in range(50):
        job = get_download_job(job["job_id"])
        if job["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.01)

    assert job["status"] == "completed"
    assert job["error"] is None
    assert any("JOB mode=single" in line for line in job["progress_log"])


def test_download_job_retention_purges_only_terminal_jobs() -> None:
    import finiq.market_desk.web.features.downloads.kind_common as kind_common

    completed_id = "retention-completed"
    running_id = "retention-running"
    try:
        kind_common.configure_download_job_retention(1)
        with kind_common._DOWNLOAD_JOBS_LOCK:
            kind_common._DOWNLOAD_JOBS[completed_id] = kind_common.DownloadJob(
                id=completed_id,
                status="completed",
                updated_at=100.0,
            )
            kind_common._DOWNLOAD_JOBS[running_id] = kind_common.DownloadJob(
                id=running_id,
                status="running",
                updated_at=100.0,
            )
            assert kind_common._purge_expired_download_jobs_locked(now=161.0) == 1
            assert completed_id not in kind_common._DOWNLOAD_JOBS
            assert running_id in kind_common._DOWNLOAD_JOBS
    finally:
        with kind_common._DOWNLOAD_JOBS_LOCK:
            kind_common._DOWNLOAD_JOBS.pop(completed_id, None)
            kind_common._DOWNLOAD_JOBS.pop(running_id, None)
        kind_common.configure_download_job_retention(60)


def test_inspect_download_output_directory_rejects_high_risk_directory() -> None:
    root = Path(Path.cwd().anchor).resolve()
    with pytest.raises(ValueError, match="high-risk output_directory"):
        inspect_download_output_directory_payload({
            "mode": "single",
            "output_directory": str(root),
            "page_size": 100,
        })


def test_download_disclosure_internal_html_payload_reads_and_writes_yearly_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[Path, list[dict[str, str]]]] = []
    spacing_limiter_ids: list[int] = []

    def fake_download(**kwargs):
        targets = list(kwargs["targets"])
        calls.append((Path(kwargs["output_directory"]), targets))
        spacing_limiter_ids.append(id(kwargs["spacing_limiter"]))
        paths = [
            Path(kwargs["target_output_directories"][target["acpt_no"]])
            / f"{target['acpt_no']}.html"
            for target in targets
        ]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_valid_download_html(), encoding="utf-8")
        return paths

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls", fake_download)

    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                    {
                        "acpt_no": "20250101000001",
                        "selected_main_doc_no": "20250101000099",
                        "metadata": {"disclosed_at": "2025-01-01"},
                    },
                    {
                        "acpt_no": "20260101000001",
                        "selected_main_doc_no": "20260101000099",
                        "metadata": {"disclosed_at": "2026-01-01"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = download_disclosure_internal_html_payload(
        {
            "output_directory": str(tmp_path / "content_html"),
            "source_compressed_json_path": str(compressed_path),
        }
    )

    assert calls == [
        (
            tmp_path / "content_html",
            [
                {"acpt_no": "20250101000001", "doc_no": "20250101000099"},
                {"acpt_no": "20260101000001", "doc_no": "20260101000099"},
            ],
        ),
    ]
    assert len(set(spacing_limiter_ids)) == 1
    assert payload["saved_files"] == [
        str(tmp_path / "content_html" / "2025" / "20250101000001.html"),
        str(tmp_path / "content_html" / "2026" / "20260101000001.html"),
    ]


def test_download_disclosure_internal_html_payload_rejects_source_directory(
    tmp_path: Path,
) -> None:
    external_dir = tmp_path / "viewer_html"
    external_dir.mkdir()
    with pytest.raises(ValueError, match="source_directory is not supported"):
        download_disclosure_internal_html_payload(
            {
                "output_directory": str(tmp_path / "content_html"),
                "source_directory": str(external_dir),
            }
        )


def test_download_disclosure_internal_html_payload_uses_selected_main_doc_no_as_sot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[Path, list[dict[str, str]]]] = []

    def fake_download(**kwargs):
        targets = list(kwargs["targets"])
        calls.append((Path(kwargs["output_directory"]), targets))
        paths = [
            Path(kwargs["target_output_directories"][target["acpt_no"]])
            / f"{target['acpt_no']}.html"
            for target in targets
        ]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_valid_download_html(), encoding="utf-8")
        return paths

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls", fake_download)

    external_dir = tmp_path / "viewer_html"
    external_dir.mkdir()
    (external_dir / "compressed-external-html.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                        {
                            "acpt_no": "20250101000001",
                            "selected_main_doc_no": "20250101000000",
                            "metadata": {"disclosed_at": "2025-01-01"},
                            "docs": [
                            {
                                "select_id": "mainDoc",
                                "select_name": "mainDoc",
                                "option_index": 1,
                                "doc_no": "20250101000998",
                                "text": "old",
                                "value": "20250101000998|N",
                                "latest_flag": "N",
                                "selected": False,
                            },
                            {
                                "select_id": "mainDoc",
                                "select_name": "mainDoc",
                                "option_index": 2,
                                "doc_no": "20250101000999",
                                "text": "selected",
                                "value": "20250101000999|Y",
                                "latest_flag": "Y",
                                "selected": True,
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = download_disclosure_internal_html_payload(
        {
            "output_directory": str(tmp_path / "content_html"),
            "source_compressed_json_path": str(
                external_dir / "compressed-external-html.json"
            ),
        }
    )

    assert calls == [
        (
            tmp_path / "content_html",
            [{"acpt_no": "20250101000001", "doc_no": "20250101000000"}],
        )
    ]
    assert payload["saved_files"] == [
        str(tmp_path / "content_html" / "2025" / "20250101000001.html")
    ]


def test_split_internal_html_sections_uses_toc_boundaries(tmp_path: Path) -> None:
    source_file = tmp_path / "20260422000832.html"
    source_file.write_text(
        """
        <html>
          <head><style>body { width:600px; }</style></head>
          <body bgcolor="#FFFFFF">
            <h2 class="SECTION-2" id="ignored-source-id"><p class="SECTION-2">주요사항보고서 / 거래소 신고의무 사항</p></h2>
            <table><tr><td>표지 내용</td></tr></table>
            <h2 class="SECTION-1"><p class="SECTION-1">전환사채권 발행결정</p></h2>
            <table><tr><td>발행금액</td><td>250,000,000</td></tr></table>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    sections = split_internal_html_sections(source_file.read_bytes())
    section_payload = {section.toc_id: section for section in sections}

    assert [section.toc_id for section in sections] == ["toc_1", "toc_2"]
    assert section_payload["toc_2"].title == "전환사채권 발행결정"
    assert "전환사채권 발행결정" in section_payload["toc_2"].html
    assert "발행금액" in section_payload["toc_2"].html
    assert "주요사항보고서" not in section_payload["toc_2"].html
    assert "표지 내용" not in section_payload["toc_2"].html


def test_split_internal_html_sections_uses_direct_section_heading_regardless_of_level_and_id() -> None:
    sections = split_internal_html_sections(
        """
        <html><head></head><body>
          <div><h2 class="SECTION-1" id="toc_1"><p class="SECTION-1">중첩 목차</p></h2><p>중첩 내용</p></div>
          <h2 id="toc_appendix"><p>SECTION class 없는 제목</p></h2>
          <p>비정규 내용</p>
          <h1 class="SECTION-7" id="not-a-toc-id"><p class="SECTION-7">정규 목차</p></h1>
          <p>정규 내용</p>
        </body></html>
        """
    )

    assert [section.toc_id for section in sections] == ["preamble", "toc_1"]
    assert [section.is_toc for section in sections] == [False, True]
    assert sections[0].title == "중첩 목차"
    assert "중첩 내용" in sections[0].html
    assert sections[1].title == "정규 목차"
    assert "정규 내용" in sections[1].html
    assert "중첩 내용" not in sections[1].html


def test_split_internal_html_sections_uses_legacy_section_one_paragraphs() -> None:
    sections = split_internal_html_sections(
        """
        <html><head></head><body>
          <p class="SECTION-1"><a name="#10">주요경영사항 신고</a></p>
          <table><tr><td>표지 내용</td></tr></table>
          <p class="PGBRK"></p>
          <p class="SECTION-1"><a name="#87">신주인수권부사채 발행결정</a></p>
          <table><tr><td>발행금액 16,000,000,000</td></tr></table>
        </body></html>
        """
    )

    assert [section.title for section in sections] == [
        "주요경영사항 신고",
        "신주인수권부사채 발행결정",
    ]
    assert "표지 내용" in sections[0].html
    assert "발행금액" in sections[1].html


def test_split_internal_html_sections_rejects_multiple_direct_xforms_boundaries() -> None:
    with pytest.raises(ValueError, match="one direct XForms document title is required"):
        split_internal_html_sections(
            """
            <html>
              <head><title>:: 70471_주주총회소집결의</title></head>
              <body>
                <div class="xforms">
                  <div>
                    <div><span>정정신고(보고)</span></div>
                    <div class="xforms_title"><div><span>주주총회소집 결의</span></div></div>
                    <table><tbody><tr><td><span>1. 일시</span></td></tr></tbody></table>
                    <div class="xforms_title"><div><span>추가 정보</span></div></div>
                    <table><tbody><tr><td><span>2. 장소</span></td></tr></tbody></table>
                  </div>
                </div>
              </body>
            </html>
            """
        )


def test_split_internal_html_sections_uses_one_main_xforms_boundary() -> None:
    sections = split_internal_html_sections(
        """
        <html>
          <head><title>:: form</title></head>
          <body>
            <div class="xforms">
              <div>
                <div id="LIB_LC000"><div><span>정정신고(보고)</span></div></div>
                <div class="xforms_title"><div><span>주주총회소집 결의</span></div></div>
                <table><tbody><tr><td><span>1. 일시</span></td></tr></tbody></table>
                <div><div><div class="xforms_title"><span>하위 서식</span></div></div></div>
              </div>
            </div>
          </body>
        </html>
        """
    )

    assert [section.title for section in sections] == [
        "정정신고(보고)",
        "주주총회소집 결의",
    ]
    assert [section.kind for section in sections] == ["preamble", "document"]
    assert [section.is_toc for section in sections] == [False, False]
    assert "하위 서식" not in sections[0].html
    assert "하위 서식" in sections[1].html
    assert 'class="xforms"' in sections[1].html


@pytest.mark.parametrize(
    ("markup", "message"),
    [
        (
            "<html><head></head><body><h2 class='SECTION-1' id='toc_1'></h2><div>대체 제목</div></body></html>",
            "TOC boundary title is required",
        ),
    ],
)
def test_split_internal_html_sections_rejects_missing_canonical_structure(
    markup: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        split_internal_html_sections(markup)


def test_split_internal_html_sections_accepts_legacy_kind_fragment() -> None:
    sections = split_internal_html_sections(
        "<P class='section-1'><a name='1'>옛 공시 제목</a></P>"
        "<TABLE><TR><TD><P>옛 공시 본문</P></TD></TR></TABLE>"
    )

    assert len(sections) == 1
    assert sections[0].title == "옛 공시 제목"
    assert sections[0].toc_id == "toc_1"
    assert "옛 공시 본문" in sections[0].html


def test_split_internal_html_sections_rejects_ordinary_paragraph_as_heading_title() -> None:
    with pytest.raises(ValueError, match="TOC boundary title is required"):
        split_internal_html_sections(
            "<html><head></head><body><h2 class='SECTION-1'></h2>"
            "<p>일반 본문</p></body></html>"
        )


def test_split_internal_html_sections_separates_direct_body_text_as_preamble() -> None:
    sections = split_internal_html_sections(
        "<html><head></head><body>\uc815\uc815 \uc2e0\uace0"
        "<h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>\uc5c5\ubb34 \ubcf8\ubb38</p></h2>"
        "<p>\ubcf8\ubb38 \ub0b4\uc6a9</p></body></html>"
    )

    assert [section.toc_id for section in sections] == ["preamble", "toc_1"]
    assert sections[0].title == "\uc815\uc815 \uc2e0\uace0"
    assert "\uc815\uc815 \uc2e0\uace0" in sections[0].html
    assert "\uc815\uc815 \uc2e0\uace0" not in sections[1].html


def test_split_internal_html_sections_rejects_div_as_recovered_heading_title() -> None:
    with pytest.raises(ValueError, match="TOC boundary title is required"):
        split_internal_html_sections(
            "<html><head></head><body><h2 class='SECTION-1'></h2>"
            "<div class='SECTION-1'>\uc9c0\uc6d0\ud558\uc9c0 \uc54a\ub294 \uc81c\ubaa9</div></body></html>"
        )


def test_split_internal_html_sections_preserves_source_toc_hierarchy() -> None:
    sections = split_internal_html_sections(
        """
        <html><head></head><body>
          <p class="CORRECTION">정 정 신 고 (보고)</p>
          <h2 class="SECTION-1" id="toc_1"><p class="SECTION-1">대표이사 등의 확인</p></h2>
          <h1 class="COVER-TITLE" id="toc_2"><p class="COVER-TITLE">증권신고서</p></h1>
          <h2 class="SECTION-1" id="toc_3"><p class="SECTION-1">대표이사 등의 확인</p></h2>
          <h2 class="PART" id="toc_4"><p class="PART">요약정보</p></h2>
          <h3 class="SECTION-2" id="toc_5"><p class="SECTION-2">핵심투자위험</p></h3>
          <h2 class="PART" id="toc_6"><p class="PART">제1부</p></h2>
          <h2 class="SECTION-1" id="toc_7"><p class="SECTION-1">모집 일반사항</p></h2>
          <h3 class="SECTION-2" id="toc_8"><p class="SECTION-2">공모개요</p></h3>
        </body></html>
        """
    )

    assert [section.toc_id for section in sections] == [
        "preamble",
        "toc_1",
        "toc_2",
        "toc_3",
        "toc_4",
        "toc_5",
        "toc_6",
        "toc_7",
        "toc_8",
    ]
    assert [section.kind for section in sections] == [
        "preamble",
        "section",
        "cover",
        "section",
        "part",
        "section",
        "part",
        "section",
        "section",
    ]
    assert [section.level for section in sections] == [0, 1, 0, 1, 0, 2, 0, 1, 2]
    assert [section.parent_toc_id for section in sections] == [
        None,
        None,
        None,
        None,
        None,
        "toc_4",
        None,
        "toc_6",
        "toc_7",
    ]
    assert [section.is_toc for section in sections] == [
        False,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
    ]


def test_split_internal_html_sections_rejects_incomplete_source_toc_ids() -> None:
    with pytest.raises(ValueError, match="every TOC heading must have a source TOC id"):
        split_internal_html_sections(
            """
            <html><head></head><body>
              <h2 class="PART" id="toc_1"><p class="PART">제1부</p></h2>
              <h2 class="SECTION-1"><p class="SECTION-1">본문</p></h2>
            </body></html>
            """
        )


def test_split_internal_html_sections_rejects_mixed_heading_and_xforms() -> None:
    with pytest.raises(ValueError, match="one unambiguous TOC structure is required"):
        split_internal_html_sections(
            "<html><head></head><body>"
            "<h2 class='SECTION-1'>목차</h2>"
            "<div class='xforms'><div><div class='xforms_title'>다른 목차</div>"
            "</div></div></body></html>"
        )


def test_save_disclosure_html_sections_payload_is_automatic_without_selection(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source_directory = input_directory / "2008"
    source_directory.mkdir(parents=True)
    (source_directory / "20260422000832.html").write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p class="SECTION-1">주요사항보고서 / 거래소 신고의무 사항</p></h2>
          <p>표지 내용</p>
          <h2 class="SECTION-1" id="toc_2"><p class="SECTION-1">전환사채권 발행결정</p></h2>
          <p>발행금액 250,000,000</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    result = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
        }
    )

    assert result["summary"]["saved_files"] == 1
    assert (output_directory / "2008" / "20260422000832.html").is_file()
    assert not (output_directory / "toc_1").exists()
    assert not (output_directory / "2008" / "toc_1").exists()


def test_save_disclosure_html_sections_payload_rejects_files_without_toc(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source_directory = input_directory / "2008"
    source_directory.mkdir(parents=True)
    (source_directory / "20260421000111.html").write_text(
        "<html><head></head><body><p>목차 없는 문서</p></body></html>",
        encoding="utf-8",
    )
    (source_directory / "20260422000832.html").write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p class="SECTION-1">주요사항보고서</p></h2>
          <p>표지 내용</p>
          <h2 class="SECTION-2" id="toc_2"><p class="SECTION-2">전환사채권 발행결정</p></h2>
          <p>발행금액 250,000,000</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="supported TOC structure is required"):
        save_disclosure_html_sections_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(output_directory),
                "workers": 1,
                "section_save_rules": {
                    "toc_1 주요사항보고서 toc_2 전환사채권 발행결정": [
                        "toc_1",
                        "toc_2",
                    ]
                },
            }
        )

    assert not list(output_directory.rglob("*.html"))


def test_section_save_rejects_html_outside_year_directory(tmp_path: Path) -> None:
    input_directory = tmp_path / "05-internal-html-download"
    source = input_directory / "bond_issuance" / "2026" / "20260101000001.html"
    source.parent.mkdir(parents=True)
    source.write_text(
        "<html><head></head><body>"
        "<h2 class='SECTION-1'><p class='SECTION-1'>\ubcf8\ubb38</p></h2>"
        "</body></html>",
        encoding="utf-8",
    )
    output_directory = tmp_path / "output"

    with pytest.raises(ValueError, match=r"<YYYY>/<acpt_no>\.html"):
        save_disclosure_html_sections_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(output_directory),
            }
        )

    assert not output_directory.exists()


def test_section_save_rejects_unexpected_existing_html_before_writing(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "input"
    source = input_directory / "2026" / "20260101000001.html"
    source.parent.mkdir(parents=True)
    source.write_text(
        "<html><head></head><body>"
        "<h2 class='SECTION-1'><p class='SECTION-1'>\ubcf8\ubb38</p></h2>"
        "</body></html>",
        encoding="utf-8",
    )
    output_directory = tmp_path / "output"
    stale = output_directory / "2025" / "20250101000001.html"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")

    with pytest.raises(ValueError, match="unexpected existing HTML"):
        save_disclosure_html_sections_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(output_directory),
            }
        )

    assert stale.read_text(encoding="utf-8") == "stale"
    assert not (output_directory / "2026" / source.name).exists()


def test_section_save_rejects_symlinked_output_year_directory(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "input"
    source = input_directory / "2026" / "20260101000001.html"
    source.parent.mkdir(parents=True)
    source.write_text(
        "<html><body><h2 class='SECTION-1'><p class='SECTION-1'>본문</p>"
        "</h2></body></html>",
        encoding="utf-8",
    )
    output_directory = tmp_path / "output"
    output_directory.mkdir()
    outside_directory = tmp_path / "outside"
    outside_directory.mkdir()
    outside_file = outside_directory / source.name
    outside_file.write_text("outside", encoding="utf-8")
    (output_directory / "2026").symlink_to(
        outside_directory,
        target_is_directory=True,
    )

    with pytest.raises(ValueError, match="must not contain symbolic links"):
        save_disclosure_html_sections_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(output_directory),
            }
        )

    assert outside_file.read_text(encoding="utf-8") == "outside"


def test_section_save_limit_allows_existing_output_for_unselected_source(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "input"
    source_directory = input_directory / "2026"
    source_directory.mkdir(parents=True)
    markup = (
        "<html><body><h2 class='SECTION-1'><p class='SECTION-1'>본문</p>"
        "</h2></body></html>"
    )
    first = source_directory / "20260101000001.html"
    second = source_directory / "20260102000002.html"
    first.write_text(markup, encoding="utf-8")
    second.write_text(markup, encoding="utf-8")
    output_directory = tmp_path / "output"
    existing = output_directory / "2026" / second.name
    existing.parent.mkdir(parents=True)
    existing.write_text("existing", encoding="utf-8")

    payload = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "limit": 1,
        }
    )

    assert payload["summary"]["integrity_ok"] is True
    assert payload["summary"]["unexpected_files"] == 0
    assert existing.read_text(encoding="utf-8") == "existing"


def test_section_save_rolls_back_all_outputs_when_publish_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_directory = tmp_path / "input"
    source_directory = input_directory / "2026"
    source_directory.mkdir(parents=True)
    output_directory = tmp_path / "output"
    output_year = output_directory / "2026"
    output_year.mkdir(parents=True)
    names = ["20260101000001.html", "20260102000002.html"]
    for index, name in enumerate(names, start=1):
        (source_directory / name).write_text(
            "<html><body><h2 class='SECTION-1'>"
            f"<p class='SECTION-1'>새 내용 {index}</p></h2></body></html>",
            encoding="utf-8",
        )
        (output_year / name).write_text(f"old {index}", encoding="utf-8")

    original_replace = disclosure_html_sections.os.replace

    def fail_second_publish(source: object, target: object) -> None:
        source_path = Path(source)
        target_path = Path(target)
        if (
            target_path.name == names[1]
            and ".backups" not in source_path.parts
            and any(
                part.startswith(f".{output_directory.name}.part-")
                for part in source_path.parts
            )
        ):
            raise OSError("publish failed")
        original_replace(source, target)

    monkeypatch.setattr(disclosure_html_sections.os, "replace", fail_second_publish)

    with pytest.raises(OSError, match="publish failed"):
        save_disclosure_html_sections_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(output_directory),
            }
        )

    assert [
        (output_year / name).read_text(encoding="utf-8") for name in names
    ] == ["old 1", "old 2"]


def test_section_save_rechecks_unexpected_output_after_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_directory = tmp_path / "input"
    source = input_directory / "2026" / "20260101000001.html"
    source.parent.mkdir(parents=True)
    source.write_text(
        "<html><body><h2 class='SECTION-1'><p class='SECTION-1'>본문</p>"
        "</h2></body></html>",
        encoding="utf-8",
    )
    output_directory = tmp_path / "output"
    stale = output_directory / "2025" / "20250101000001.html"
    original_output = disclosure_html_sections._automatic_section_output

    def create_stale_output(source_file: Path) -> dict[str, Any]:
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text("stale", encoding="utf-8")
        return original_output(source_file)

    monkeypatch.setattr(
        disclosure_html_sections,
        "_automatic_section_output",
        create_stale_output,
    )

    with pytest.raises(ValueError, match="unexpected existing HTML"):
        save_disclosure_html_sections_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(output_directory),
            }
        )

    assert stale.read_text(encoding="utf-8") == "stale"
    assert not (output_directory / "2026" / source.name).exists()


def test_section_save_rolls_back_published_outputs_when_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_directory = tmp_path / "input"
    source_directory = input_directory / "2026"
    source_directory.mkdir(parents=True)
    output_directory = tmp_path / "output"
    output_year = output_directory / "2026"
    output_year.mkdir(parents=True)
    names = ["20260101000001.html", "20260102000002.html"]
    for index, name in enumerate(names, start=1):
        (source_directory / name).write_text(
            "<html><body><h2 class='SECTION-1'>"
            f"<p class='SECTION-1'>새 내용 {index}</p></h2></body></html>",
            encoding="utf-8",
        )
        (output_year / name).write_text(f"old {index}", encoding="utf-8")

    published_once = False
    original_replace = disclosure_html_sections.os.replace

    def track_publish(source: object, target: object) -> None:
        nonlocal published_once
        source_path = Path(source)
        target_path = Path(target)
        original_replace(source, target)
        if (
            target_path.name == names[0]
            and ".backups" not in source_path.parts
            and any(
                part.startswith(f".{output_directory.name}.part-")
                for part in source_path.parts
            )
        ):
            published_once = True

    monkeypatch.setattr(disclosure_html_sections.os, "replace", track_publish)

    payload = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
        },
        cancel_check=lambda: published_once,
    )

    assert payload == {"cancelled": True}
    assert [
        (output_year / name).read_text(encoding="utf-8") for name in names
    ] == ["old 1", "old 2"]


def test_section_save_rejects_output_nested_below_input(tmp_path: Path) -> None:
    input_directory = tmp_path / "input"
    source = input_directory / "2026" / "20260101000001.html"
    source.parent.mkdir(parents=True)
    source.write_text(
        "<html><head></head><body>"
        "<h2 class='SECTION-1'><p class='SECTION-1'>\ubcf8</p></h2>"
        "</body></html>",
        encoding="utf-8",
    )
    output_directory = input_directory / "output"

    with pytest.raises(ValueError, match="must not be inside input_directory"):
        save_disclosure_html_sections_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(output_directory),
            }
        )

    assert not output_directory.exists()


def test_section_save_rejects_duplicate_filename_stems_across_years(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "input"
    markup = (
        "<html><head></head><body>"
        "<h2 class='SECTION-1'><p class='SECTION-1'>본문</p></h2>"
        "</body></html>"
    )
    for year in ("2025", "2026"):
        source = input_directory / year / "20260101000001.html"
        source.parent.mkdir(parents=True)
        source.write_text(markup, encoding="utf-8")
    output_directory = tmp_path / "output"

    with pytest.raises(ValueError, match="duplicate HTML filename stem"):
        save_disclosure_html_sections_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(output_directory),
            }
        )

    assert not output_directory.exists()


def test_section_save_ignores_obsolete_zero_rule_selection(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source = input_directory / "2026" / "20260422000832.html"
    source.parent.mkdir(parents=True)
    stale_output = output_directory / "2026" / source.name
    stale_output.parent.mkdir(parents=True)
    stale_output.write_text("stale", encoding="utf-8")
    source.write_text(
        "<html><head></head><body><h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>주요사항보고서</p></h2><p>본문</p></body></html>",
        encoding="utf-8",
    )

    payload = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "section_save_rules": {"toc_1 주요사항보고서": []},
        }
    )

    assert payload["summary"]["integrity_ok"] is True
    assert payload["summary"]["skipped_files"] == 0
    assert payload["skipped_files"] == []
    assert stale_output.is_file()
    inspected = inspect_disclosure_html_section_output_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "section_save_rules": {"toc_1 주요사항보고서": []},
        }
    )
    assert inspected["summary"]["integrity_ok"] is True


def test_section_save_ignores_obsolete_unknown_selected_toc(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source = input_directory / "2026" / "20260422000832.html"
    source.parent.mkdir(parents=True)
    source.write_text(
        "<html><head></head><body><h2 class='SECTION-1'><p class='SECTION-1'>주요사항보고서</p></h2><p>본문</p></body></html>",
        encoding="utf-8",
    )

    result = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "section_save_rules": {
                "toc_1 주요사항보고서": ["toc_999"]
            },
        }
    )

    assert result["summary"]["saved_files"] == 1
    assert (output_directory / "2026" / source.name).is_file()


def test_inspect_disclosure_html_sections_payload_lists_document_toc(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    current_directory = input_directory / "2026"
    prior_directory = input_directory / "2025"
    current_directory.mkdir(parents=True)
    prior_directory.mkdir(parents=True)
    (current_directory / "20260422000832.html").write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p class="SECTION-1">주요사항보고서 / 거래소 신고의무 사항</p></h2>
          <p>표지 내용</p>
          <h2 class="SECTION-1" id="toc_2"><p class="SECTION-1">전환사채권 발행결정</p></h2>
          <p>발행금액 250,000,000</p>
        </body></html>
        """,
        encoding="utf-8",
    )
    (prior_directory / "20260423000533.html").write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p class="SECTION-1">주요사항보고서 / 거래소 신고의무 사항</p></h2>
          <p>표지 내용</p>
        </body></html>
        """,
        encoding="utf-8",
    )
    payload = inspect_disclosure_html_sections_payload(
        {"input_directory": str(input_directory)}
    )

    assert payload["summary"] == {
        "found_files": 2,
        "documents_with_sections": 2,
        "files_without_sections": 0,
        "failed_files": 0,
        "reported_problem_files": 0,
        "source_unavailable_files": 0,
    }
    documents = sorted(payload["documents"], key=lambda document: document["source_name"])
    assert [document["source_name"] for document in documents] == [
        "20260422000832.html",
        "20260423000533.html",
    ]
    assert [document["source_relative_path"] for document in documents] == [
        "2026/20260422000832.html",
        "2025/20260423000533.html",
    ]
    assert [section["toc_id"] for section in documents[0]["sections"]] == ["toc_1", "toc_2"]
    assert [section["toc_id"] for section in documents[1]["sections"]] == ["toc_1"]
    assert payload["problem_files"] == []


def test_html_section_inspect_and_save_use_requested_progress_interval(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source_directory = input_directory / "2026"
    source_directory.mkdir(parents=True)
    for index in range(1, 4):
        (source_directory / f"2026040{index}000001.html").write_text(
            "<html><head></head><body>"
            "<h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>목차</p></h2>"
            f"<p>본문 {index}</p></body></html>",
            encoding="utf-8",
        )

    inspect_log: list[str] = []
    inspect_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "progress_interval": 2,
        },
        progress_callback=inspect_log.append,
    )
    assert [line for line in inspect_log if "목차 확인 중간 확인" in line] == [
        "목차 확인 중간 확인: 1/3건 처리.",
        "목차 확인 중간 확인: 2/3건 처리.",
        "목차 확인 중간 확인: 3/3건 처리.",
    ]

    save_log: list[str] = []
    save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "progress_interval": 2,
        },
        progress_callback=save_log.append,
    )
    assert [line for line in save_log if "목차 저장 중간 확인" in line] == [
        "목차 저장 중간 확인: 1/3건 처리.",
        "목차 저장 중간 확인: 2/3건 처리.",
        "목차 저장 중간 확인: 3/3건 처리.",
    ]

    with pytest.raises(ValueError, match="progress_interval must be >= 1"):
        inspect_disclosure_html_sections_payload(
            {
                "input_directory": str(input_directory),
                "progress_interval": 0,
            }
        )


def test_inspect_disclosure_html_sections_payload_stops_before_next_file_when_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_directory = tmp_path / "content_html"
    source_directory = input_directory / "2026"
    source_directory.mkdir(parents=True)
    (source_directory / "20260401000001.html").write_text(
        "<html><head></head><body><h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>1</p></h2><p>첫 번째</p></body></html>",
        encoding="utf-8",
    )
    (source_directory / "20260402000001.html").write_text(
        "<html><head></head><body><h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>2</p></h2><p>두 번째</p></body></html>",
        encoding="utf-8",
    )
    checks = 0
    parsed: list[str] = []

    def fake_inspect(markup: bytes) -> list[HtmlSectionSummary]:
        parsed.append(markup.decode("utf-8"))
        return [HtmlSectionSummary(toc_id="toc_1", index=1, title="1")]

    monkeypatch.setattr(disclosure_html_sections, "inspect_internal_html_sections", fake_inspect)

    def cancel_check() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    payload = inspect_disclosure_html_sections_payload(
        {"input_directory": str(input_directory), "workers": 1},
        cancel_check=cancel_check,
    )

    assert payload == {"cancelled": True}
    assert len(parsed) == 1
    assert "첫 번째" in parsed[0]


def test_html_section_summary_propagates_file_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_directory = tmp_path / "content_html"
    source_directory = input_directory / "2026"
    source_directory.mkdir(parents=True)
    (source_directory / "20260401000001.html").write_text(
        "<html><head></head><body><h2 class='SECTION-1' id='toc_1'>목차</h2></body></html>",
        encoding="utf-8",
    )

    def fail_inspection(_markup: bytes) -> list[HtmlSectionSummary]:
        raise OSError("read failed")

    monkeypatch.setattr(
        disclosure_html_sections,
        "inspect_internal_html_sections",
        fail_inspection,
    )

    with pytest.raises(OSError, match="read failed"):
        summarize_disclosure_html_section_kinds_payload(
            {"input_directory": str(input_directory)}
        )


def test_html_section_inspection_reports_files_without_sections(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "content_html"
    source_file = input_directory / "2026" / "20260401000001.html"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("<html><body>broken</body></html>", encoding="utf-8")

    payload = inspect_disclosure_html_sections_payload(
        {"input_directory": str(input_directory), "report_limit": 1}
    )

    assert payload["summary"] == {
        "found_files": 1,
        "documents_with_sections": 0,
        "files_without_sections": 1,
        "failed_files": 0,
        "reported_problem_files": 1,
        "source_unavailable_files": 0,
    }
    assert payload["problem_files"] == [
        {
            "kind": "no_sections",
            "source_file": str(source_file),
            "source_relative_path": f"2026/{source_file.name}",
            "error": "분리할 목차를 찾지 못했습니다.",
        }
    ]


def test_html_section_inspection_counts_source_unavailable_as_expected(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "content_html"
    source_file = input_directory / "2026" / "20260401000001.html"
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(
        _render_internal_html_source_unavailable_placeholder(
            acpt_no=source_file.stem,
            doc_no="20260401000002",
            reason="invalid_html",
        )
    )

    payload = inspect_disclosure_html_sections_payload(
        {"input_directory": str(input_directory)}
    )

    assert payload["summary"] == {
        "found_files": 1,
        "documents_with_sections": 0,
        "files_without_sections": 0,
        "failed_files": 0,
        "reported_problem_files": 0,
        "source_unavailable_files": 1,
    }
    assert payload["problem_files"] == []

    listed = list_disclosure_html_section_sources_payload(
        {"input_directory": str(input_directory)}
    )
    assert listed["summary"]["source_unavailable_files"] == 1
    assert listed["documents"][0]["source_unavailable"]["reason"] == "invalid_html"
    assert listed["documents"][0]["toc_count"] == 0


def test_list_disclosure_html_section_sources_payload_pages_with_current_page_toc_counts(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    source_directory = input_directory / "2026"
    source_directory.mkdir(parents=True)
    for index in range(22):
        section_markup = "<h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>목차</p></h2>"
        if index == 0:
            section_markup += "<h2 class='SECTION-2' id='toc_2'><p class='SECTION-2'>본문</p></h2>"
        (source_directory / f"202604{index + 1:02d}000001.html").write_text(
            f"<html><head></head><body>{section_markup}</body></html>",
            encoding="utf-8",
        )

    first_page = list_disclosure_html_section_sources_payload({"input_directory": str(input_directory)})
    second_page = list_disclosure_html_section_sources_payload(
        {"input_directory": str(input_directory), "page": 2, "page_size": 20}
    )

    assert first_page["format"] == "finiq_disclosure_html_section_source_list_v1"
    assert first_page["summary"] == {
        "page": 1,
        "page_size": 20,
        "returned_files": 20,
        "has_next_page": True,
        "source_unavailable_files": 0,
    }
    assert len(first_page["documents"]) == 20
    assert first_page["documents"][0]["source_name"] == "20260401000001.html"
    assert first_page["documents"][0]["section_count"] == 2
    assert first_page["documents"][0]["toc_count"] == 2
    assert first_page["documents"][1]["section_count"] == 1
    assert first_page["documents"][1]["toc_count"] == 1
    assert "sections" not in first_page["documents"][0]
    assert second_page["summary"] == {
        "page": 2,
        "page_size": 20,
        "returned_files": 2,
        "has_next_page": False,
        "source_unavailable_files": 0,
    }
    assert [document["source_name"] for document in second_page["documents"]] == [
        "20260421000001.html",
        "20260422000001.html",
    ]
    assert [document["section_count"] for document in second_page["documents"]] == [1, 1]


def test_list_disclosure_html_section_sources_ignores_hidden_automation_cache(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "content_html"
    visible = input_directory / "2026" / "20260712000001.html"
    hidden = input_directory / ".automation-current" / "2026" / "20260712000002.html"
    visible.parent.mkdir(parents=True)
    hidden.parent.mkdir(parents=True)
    markup = "<html><head></head><body><h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>목차</p></h2></body></html>"
    visible.write_text(markup, encoding="utf-8")
    hidden.write_text(markup, encoding="utf-8")

    result = list_disclosure_html_section_sources_payload(
        {"input_directory": str(input_directory)}
    )

    assert [item["source_name"] for item in result["documents"]] == [visible.name]


def test_summarize_disclosure_html_section_kinds_payload_uses_workers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    input_directory = tmp_path / "content_html"
    source_directory = input_directory / "2026"
    source_directory.mkdir(parents=True)
    for acpt_no in ("20260401000001", "20260402000001"):
        (source_directory / f"{acpt_no}.html").write_text(
            "<html><head></head><body>"
            "<h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>1</p></h2>"
            "</body></html>",
            encoding="utf-8",
        )
    original = disclosure_html_sections._source_document_with_sections
    barrier = threading.Barrier(2)

    def synchronized_source_document(
        root: Path,
        source_file: Path,
    ) -> dict[str, Any]:
        barrier.wait(timeout=2)
        return original(root, source_file)

    monkeypatch.setattr(
        disclosure_html_sections,
        "_source_document_with_sections",
        synchronized_source_document,
    )
    progress: list[str] = []

    payload = summarize_disclosure_html_section_kinds_payload(
        {"input_directory": str(input_directory), "workers": 2},
        progress_callback=progress.append,
    )

    assert payload["summary"]["found_files"] == 2
    assert "병렬 처리 2개를 사용합니다" in progress[0]


def test_summarize_disclosure_html_section_kinds_payload_counts_unique_toc_sequences(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    source_directory = input_directory / "2026"
    source_directory.mkdir(parents=True)
    for source_file in [
        source_directory / "20260401000001.html",
        source_directory / "20260402000001.html",
        source_directory / "20260403000001.html",
        source_directory / "20260404000001.html",
    ]:
        source_file.write_text(
            """
            <html><head></head><body>
              <h2 class="SECTION-1" id="toc_1"><p class="SECTION-1">1</p></h2>
              <p>표지</p>
              <h2 class="SECTION-2" id="toc_2"><p class="SECTION-2">2</p></h2>
              <p>본문</p>
            </body></html>
            """,
            encoding="utf-8",
        )
    (source_directory / "20260405000001.html").write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p class="SECTION-1">1</p></h2>
          <p>표지</p>
        </body></html>
        """,
        encoding="utf-8",
    )
    payload = summarize_disclosure_html_section_kinds_payload({"input_directory": str(input_directory)})

    assert payload["format"] == "finiq_disclosure_html_section_kind_summary_v1"
    assert payload["summary"] == {
        "found_files": 5,
        "documents_with_sections": 5,
        "files_without_sections": 0,
        "failed_files": 0,
        "unique_kinds": 2,
    }
    assert payload["items"] == [
        {
            "signature": "toc_1 1 toc_2 2",
            "count": 4,
            "section_count": 2,
            "sections": [
                {
                    "toc_id": "toc_1",
                    "index": 1,
                    "title": "1",
                    "kind": "section",
                    "level": 1,
                    "parent_toc_id": None,
                    "is_toc": True,
                },
                {
                    "toc_id": "toc_2",
                    "index": 2,
                    "title": "2",
                    "kind": "section",
                    "level": 2,
                    "parent_toc_id": "toc_1",
                    "is_toc": True,
                },
                ],
                "sample_documents": [
                    {
                        "source_file": str(source_directory / "20260401000001.html"),
                        "source_name": "20260401000001.html",
                        "source_relative_path": "2026/20260401000001.html",
                    },
                    {
                        "source_file": str(source_directory / "20260402000001.html"),
                        "source_name": "20260402000001.html",
                        "source_relative_path": "2026/20260402000001.html",
                    },
                    {
                        "source_file": str(source_directory / "20260403000001.html"),
                        "source_name": "20260403000001.html",
                        "source_relative_path": "2026/20260403000001.html",
                },
            ],
        },
        {
            "signature": "toc_1 1",
            "count": 1,
            "section_count": 1,
            "sections": [
                {
                    "toc_id": "toc_1",
                    "index": 1,
                    "title": "1",
                    "kind": "section",
                    "level": 1,
                    "parent_toc_id": None,
                    "is_toc": True,
                }
            ],
                "sample_documents": [
                    {
                        "source_file": str(source_directory / "20260405000001.html"),
                        "source_name": "20260405000001.html",
                        "source_relative_path": "2026/20260405000001.html",
                }
            ],
        },
    ]


def test_save_disclosure_html_sections_payload_ignores_incomplete_obsolete_rules(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source_directory = input_directory / "2008"
    source_directory.mkdir(parents=True)
    (source_directory / "20260401000001.html").write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p class="SECTION-1">1</p></h2>
          <p>표지</p>
          <h2 class="SECTION-2" id="toc_2"><p class="SECTION-2">2</p></h2>
          <p>본문</p>
        </body></html>
        """,
        encoding="utf-8",
    )
    (source_directory / "20260402000001.html").write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p class="SECTION-1">단독</p></h2>
          <p>단독 본문</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    result = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "section_save_rules": {"toc_1 1 toc_2 2": ["toc_1"]},
        }
    )

    assert result["summary"]["saved_files"] == 2
    assert len(list(output_directory.rglob("*.html"))) == 2


def test_section_output_inspection_reuses_save_selection_and_detects_content_change(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source = input_directory / "2026" / "20260401000001.html"
    source.parent.mkdir(parents=True)
    source.write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p class="SECTION-1">1</p></h2><p>표지</p>
          <h2 class="SECTION-2" id="toc_2"><p class="SECTION-2">2</p></h2><p>본문</p>
        </body></html>
        """,
        encoding="utf-8",
    )
    body = {
        "input_directory": str(input_directory),
        "output_directory": str(output_directory),
        "section_save_rules": {"toc_1 1 toc_2 2": ["toc_2"]},
    }
    save_disclosure_html_sections_payload(body)

    checked = inspect_disclosure_html_section_output_payload(body)

    assert checked["summary"]["integrity_ok"] is True
    assert checked["summary"]["expected_files"] == 1

    (output_directory / "2026" / source.name).write_text("changed", encoding="utf-8")

    changed = inspect_disclosure_html_section_output_payload(body)

    assert changed["summary"]["integrity_ok"] is False
    assert changed["mismatched_files"] == [f"2026/{source.name}"]


def test_section_output_inspection_compares_each_content_before_next_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    input_directory.mkdir()
    output_directory.mkdir()
    source_files = [input_directory / "a.html", input_directory / "b.html"]
    for source_file in source_files:
        source_file.touch()
        (output_directory / source_file.name).touch()

    comparisons: list[str] = []
    original_read_text = Path.read_text

    def tracked_read_text(path: Path, *args: object, **kwargs: object) -> str:
        if path.parent == output_directory:
            comparisons.append(path.name)
            return path.name
        return original_read_text(path, *args, **kwargs)

    def stream_results(*_args: object, **_kwargs: object):
        yield {"status": "ok", "selected_sections": 1, "content": "a.html"}
        assert comparisons == ["a.html"]
        yield {"status": "ok", "selected_sections": 1, "content": "b.html"}

    monkeypatch.setattr(
        disclosure_html_sections,
        "_collect_html_files",
        lambda *_args, **_kwargs: source_files,
    )
    monkeypatch.setattr(disclosure_html_sections, "_map_html_files", stream_results)
    monkeypatch.setattr(Path, "read_text", tracked_read_text)

    checked = inspect_disclosure_html_section_output_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "section_save_rules": {},
        }
    )

    assert checked["summary"]["integrity_ok"] is True
    assert comparisons == ["a.html", "b.html"]


def test_section_output_inspection_stops_before_output_scan_when_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    input_directory.mkdir()
    output_directory.mkdir()
    monkeypatch.setattr(
        disclosure_html_sections,
        "_collect_html_files",
        lambda *_args, **_kwargs: [],
    )

    def reject_output_scan(*_args: object, **_kwargs: object):
        raise AssertionError("cancelled inspection must not scan output files")

    monkeypatch.setattr(Path, "rglob", reject_output_scan)

    checked = inspect_disclosure_html_section_output_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "section_save_rules": {},
        },
        cancel_check=lambda: True,
    )

    assert checked == {"cancelled": True}


def test_section_save_ignores_automation_cache_below_standard_input(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "05-internal-html-download"
    output_directory = tmp_path / "06-sections"
    visible = input_directory / "2026" / "20260101000001.html"
    hidden = input_directory / ".automation-current" / "20260101000002.html"
    visible.parent.mkdir(parents=True)
    hidden.parent.mkdir(parents=True)
    html = "<html><head></head><body><h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>1</p></h2><p>본문</p></body></html>"
    visible.write_text(html)
    hidden.write_text(html)

    result = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "mode": "bond_issuance",
            "section_save_rules": {"toc_1 1": ["toc_1"]},
        }
    )

    assert result["summary"]["found_files"] == 1
    assert result["output_directory"] == str(output_directory / "bond_issuance")
    assert (output_directory / "bond_issuance" / "2026" / visible.name).is_file()
    assert not (output_directory / "2026").exists()
    assert not (output_directory / ".automation-current" / hidden.name).exists()


def test_section_save_discards_correction_preamble_before_bond_parse(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "05-internal-html-download"
    output_directory = tmp_path / "06-sections"
    source_directory = input_directory / "2013"
    source_directory.mkdir(parents=True)
    source_file = source_directory / "20130416000360.html"
    source_file.write_text(
        """
        <html><head></head><body>
          <p class="CORRECTION">정 정 신 고 (보고)</p>
          <table>
            <tr><td>1. 사채의 종류</td><td>회차</td><td>15</td><td>종류</td><td>신주인수권부사채</td></tr>
            <tr><td>2. 사채의 권면총액 (원)</td><td>10,000,000,000</td></tr>
            <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>10,000,000,000</td></tr>
          </table>
          <table>
            <tr><th>발행 대상자명</th><th>발행권면총액 (원)</th></tr>
            <tr><td>정정 전 투자자</td><td>10,000,000,000</td></tr>
          </table>
          <h2 class="SECTION-1"><p class="SECTION-1">주요사항보고서</p></h2>
          <p>표지</p>
          <h2 class="SECTION-1"><p class="SECTION-1">신주인수권부사채권 발행결정</p></h2>
          <table>
            <tr><td>1. 사채의 종류</td><td>회차</td><td>16</td><td>종류</td><td>신주인수권부사채</td></tr>
            <tr><td>2. 사채의 권면총액 (원)</td><td>7,500,000,000</td></tr>
            <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>7,500,000,000</td></tr>
          </table>
          <table>
            <tr><th>발행 대상자명</th><th>발행권면총액 (원)</th></tr>
            <tr><td>이용복</td><td>5,500,000,000</td></tr>
            <tr><td>김태현</td><td>2,000,000,000</td></tr>
          </table>
        </body></html>
        """,
        encoding="utf-8",
    )

    split_sections = split_internal_html_sections(source_file.read_bytes())
    assert [section.title for section in split_sections] == [
        "정 정 신 고 (보고)",
        "주요사항보고서",
        "신주인수권부사채권 발행결정",
    ]

    save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "mode": "bond_issuance",
            "section_save_rules": {
                "toc_1 주요사항보고서 toc_2 신주인수권부사채권 발행결정": [
                    "toc_2"
                ]
            },
        }
    )
    section_file = output_directory / "bond_issuance" / "2013" / source_file.name
    section_html = section_file.read_text(encoding="utf-8")

    assert "정정신고" not in section_html
    assert "정정 전 투자자" not in section_html
    assert "표지" in section_html
    assert section_html.count("사채의 종류") == 1
    assert section_html.count("발행 대상자명") == 1
    parsed = parse_bond_issuance(
        section_html,
        file_path=section_file,
        title="[정정]신주인수권부사채권 발행결정",
    )
    assert parsed["회차"] == "16"
    assert parsed["발행금액"] == 7_500_000_000
    assert parsed["투자자"] == [
        ["이용복", 5_500_000_000],
        ["김태현", 2_000_000_000],
    ]


def test_section_save_never_discards_correction_word_after_first_section(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "05-internal-html-download"
    output_directory = tmp_path / "06-sections"
    source_file = input_directory / "2026" / "20260828000001.html"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p class="SECTION-1">일반공시</p></h2>
          <p>첫 번째 본문</p>
          <h3 class="SECTION-2" id="toc_2"><p class="SECTION-2">정정 관련 참고사항</p></h3>
          <p>두 번째 본문</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    result = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "mode": "bond_issuance",
        }
    )
    output = (
        output_directory / "bond_issuance" / "2026" / source_file.name
    ).read_text(encoding="utf-8")

    assert result["summary"]["removed_correction_sections"] == 0
    assert "일반공시" in output
    assert "정정 관련 참고사항" in output
    assert "두 번째 본문" in output


def test_section_save_removes_direct_text_correction_preamble(tmp_path: Path) -> None:
    input_directory = tmp_path / "input"
    source_file = input_directory / "2026" / "20260828000001.html"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(
        "<html><head></head><body>정정 신고"
        "<h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>업무 본문</p></h2>"
        "<p>본문 내용</p></body></html>",
        encoding="utf-8",
    )
    output_directory = tmp_path / "output"

    result = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
        }
    )
    output = (output_directory / "2026" / source_file.name).read_text(
        encoding="utf-8"
    )

    assert result["summary"]["removed_correction_sections"] == 1
    assert "정정 신고" not in output
    assert "업무 본문" in output
    assert "본문 내용" in output


def test_section_save_preserves_single_legacy_correction_disclosure(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "05-internal-html-download"
    output_directory = tmp_path / "06-sections"
    source_file = input_directory / "1997" / "19970407M00015.html"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(
        "<P class='section-1'><a name='1'>대신개발금융(주) 유상증자 정정공시</P>"
        "<TABLE><TR><TD><P>일정변경이 불가피하여 추후 재공시하겠음</P>"
        "</TD></TR></TABLE>",
        encoding="utf-8",
    )

    result = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "mode": "rights_issuance",
        }
    )
    output = (
        output_directory / "rights_issuance" / "1997" / source_file.name
    ).read_text(encoding="utf-8")

    assert result["summary"]["saved_files"] == 1
    assert result["summary"]["removed_correction_sections"] == 0
    assert "유상증자 정정공시" in output
    assert "일정변경이 불가피" in output


def test_save_disclosure_html_sections_payload_preserves_multiple_selected_sections(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source_directory = input_directory / "2008"
    source_directory.mkdir(parents=True)
    (source_directory / "20260401000001.html").write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p class="SECTION-1">1</p></h2>
          <p>표지</p>
          <h2 class="SECTION-2" id="toc_2"><p class="SECTION-2">2</p></h2>
          <p>본문</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    payload = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "section_save_rules": {"toc_1 1 toc_2 2": ["toc_1", "toc_2"]},
        }
    )
    section_html = (output_directory / "2008" / "20260401000001.html").read_text(encoding="utf-8")

    assert payload["summary"]["saved_files"] == 1
    assert payload["summary"]["expected_files"] == 1
    assert "표지" in section_html
    assert "본문" in section_html
    assert not (output_directory / "2008" / "20260401000001_1.html").exists()
    assert not (output_directory / "2008" / "toc_1").exists()


def test_save_disclosure_html_sections_payload_leaves_output_unchanged_when_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source_directory = input_directory / "2008"
    source_directory.mkdir(parents=True)
    (source_directory / "20260401000001.html").write_text(
        "<html><head></head><body><h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>1</p></h2><p>첫 번째</p></body></html>",
        encoding="utf-8",
    )
    (source_directory / "20260402000001.html").write_text(
        "<html><head></head><body><h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>2</p></h2><p>두 번째</p></body></html>",
        encoding="utf-8",
    )
    rendered_files = 0
    original_output = disclosure_html_sections._automatic_section_output

    def tracked_output(source_file: Path) -> dict[str, Any]:
        nonlocal rendered_files
        result = original_output(source_file)
        rendered_files += 1
        return result

    monkeypatch.setattr(
        disclosure_html_sections,
        "_automatic_section_output",
        tracked_output,
    )

    def cancel_check() -> bool:
        return rendered_files == 1

    payload = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "workers": 1,
            "section_save_rules": {
                "toc_1 1": ["toc_1"],
                "toc_1 2": ["toc_1"],
            },
        },
        cancel_check=cancel_check,
    )

    assert payload == {"cancelled": True}
    assert not (output_directory / "2008" / "20260401000001.html").exists()
    assert not (output_directory / "2008" / "20260402000001.html").exists()


def test_split_disclosure_html_section_source_payload_splits_one_selected_file(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    nested_directory = input_directory / "2026"
    nested_directory.mkdir(parents=True)
    source_file = nested_directory / "20260422000832.html"
    source_file.write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p class="SECTION-1">주요사항보고서</p></h2>
          <p>표지 내용</p>
          <h2 class="SECTION-2" id="toc_2"><p class="SECTION-2">전환사채권 발행결정</p></h2>
          <p>발행금액 250,000,000</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    payload = split_disclosure_html_section_source_payload(
        {"input_directory": str(input_directory), "source_name": "2026/20260422000832.html"}
    )

    assert payload["format"] == "finiq_disclosure_html_section_source_split_v1"
    assert payload["document"]["source_relative_path"] == "2026/20260422000832.html"
    assert [(section["toc_id"], section["title"]) for section in payload["sections"]] == [
        ("toc_1", "주요사항보고서"),
        ("toc_2", "전환사채권 발행결정"),
    ]
    assert "표지 내용" in payload["sections"][0]["html"]
    assert "발행금액 250,000,000" in payload["sections"][1]["html"]


def test_html_section_worker_count_defaults_to_cpu_cap_and_accepts_payload_value(
    monkeypatch,
) -> None:
    import finiq.concurrency as concurrency

    monkeypatch.setattr(concurrency.os, "cpu_count", lambda: 12)

    assert parse_html_section_worker_count(None) == 12
    assert parse_html_section_worker_count("") == 12
    assert parse_html_section_worker_count("4") == 4
    assert parse_html_section_worker_count("20") == 12

    with pytest.raises(ValueError, match="workers must be >= 1"):
        parse_html_section_worker_count(0)


def test_compress_disclosure_external_html_payload_writes_compact_json(tmp_path: Path) -> None:
    input_directory = tmp_path / "viewer_html"
    (input_directory / "2025").mkdir(parents=True)
    (input_directory / "kind_disclosure_html_manifest.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "disclosures": [
                    {
                        "acpt_no": "AB202501010001",
                        "market": "코스닥",
                        "company_name": "테스트",
                        "company_id": "123456",
                        "disclosed_at": "2025-01-01 09:00",
                        "title": "메타 제목",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (input_directory / "2025" / "AB202501010001.html").write_text(
        """
        <html><body>
          <meta name="description" content="대한민국 대표 기업공시채널 KIND" />
          <script>
            var _TRK_PI = "PDV";
            var _TRK_PN = "AB202501010001";
          </script>
          <script src="../js/viewer.js?version=20250307"></script>
          <form name="docdownloadform" id="docdownloadform">
            <input type="hidden" name="docLocPath" id="docLocPath" value="/external/path" />
              </form>
              <input type="hidden" name="acptNo" value="AB202501010001" />
              <input type="hidden" name="tempTitle" value="뷰어 제목" />
          <h1 class="ttl">테스트 (123456)</h1>
          <select id="mainDoc">
            <option value="">본문선택</option>
            <option value="DOC202501Z|Y" selected="selected">본문</option>
          </select>
          <select id="attachedDoc">
            <option value="">첨부문서선택</option>
            <option value="ATTACH2025A">첨부</option>
          </select>
          <select id="orgDisclsId" name="orgDiscls">
            <option value="">기공시선택</option>
            <option value="discls"></option>
          </select>
          <div class="viewrIssue" style="display:none;">
            <p>본 문서는 최종문서가 아니므로, 최종 정정문서를 반드시 확인하시기 바랍니다.</p>
          </div>
          <a href="#viewer" onclick="pdfPrint();return false;"><img src="../images/common/btn_pdf.png" alt="PDF 로 저장" /></a>
          <iframe name="docViewFrm" id="docViewFrm" title="본문"></iframe>
        </body></html>
        """,
        encoding="utf-8",
    )
    output_directory = tmp_path / "compressed"

    payload = compress_disclosure_external_html_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
        }
    )

    assert payload["summary"] == {"found_files": 1, "compressed_files": 1, "written_files": 1}
    assert payload["metadata_check"] == {
        "complete": True,
        "expected_records": 1,
        "matched_records": 1,
        "missing_records": 0,
    }
    assert payload["verification"]["passed"] is True
    assert payload["verification"]["missing_records"] == 0
    assert payload["verification"]["verified_records"] == 1
    output_path = output_directory / "compressed-external-html.json"
    assert payload["written_files"] == [str(output_path)]
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["format"] == "finiq_disclosure_external_html_docs_v1"
    assert "input_directory" not in saved
    assert "output_directory" not in saved
    assert "output_path" not in saved
    assert "html" not in saved["records"][0]
    assert set(saved["records"][0]) == {
        "acpt_no",
        "title",
        "selected_main_doc_no",
        "metadata",
        "docs",
        "source_sha256",
        "source_size_bytes",
    }
    assert saved["records"][0]["acpt_no"] == "AB202501010001"
    assert saved["records"][0]["title"] == "메타 제목"
    assert saved["records"][0]["selected_main_doc_no"] == "DOC202501Z"
    assert saved["records"][0]["metadata"]["market"] == "코스닥"
    assert "external_metadata" not in saved["records"][0]
    assert "main_docs" not in saved["records"][0]
    assert "attached_docs" not in saved["records"][0]
    assert "source_file" not in saved["records"][0]
    assert "year" not in saved["records"][0]
    assert saved["records"][0]["source_size_bytes"] > 0
    assert len(saved["records"][0]["source_sha256"]) == 64
    assert saved["records"][0]["docs"] == [
        {
            "select_id": "mainDoc",
            "select_name": "",
            "option_index": 1,
            "doc_no": "DOC202501Z",
            "text": "본문",
            "value": "DOC202501Z|Y",
            "latest_flag": "Y",
            "selected": True,
        },
        {
            "select_id": "attachedDoc",
            "select_name": "",
            "option_index": 1,
            "doc_no": "ATTACH2025A",
            "text": "첨부",
            "value": "ATTACH2025A",
            "latest_flag": None,
            "selected": False,
        },
    ]


def test_compress_disclosure_external_html_payload_rejects_year_mismatch(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "viewer_html"
    year_directory = input_directory / "2024"
    year_directory.mkdir(parents=True)
    (input_directory / "kind_disclosure_html_manifest.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "disclosures": [
                    {
                        "acpt_no": "AB202501010001",
                        "disclosed_at": "2025-01-01 09:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (year_directory / "AB202501010001.html").write_text(
        "<html></html>", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="year does not match disclosed_at"):
        compress_disclosure_external_html_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(tmp_path / "compressed"),
            }
        )


def test_compress_disclosure_external_html_payload_rejects_mismatched_embedded_acpt_no(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "viewer_html"
    (input_directory / "2025").mkdir(parents=True)
    (input_directory / "kind_disclosure_html_manifest.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "disclosures": [
                    {
                        "acpt_no": "20250101000001",
                        "title": "첫 번째 제목",
                        "disclosed_at": "2025-01-01",
                    },
                    {
                        "acpt_no": "20250101000002",
                        "title": "두 번째 제목",
                        "disclosed_at": "2025-01-01",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    for filename_acpt_no, embedded_acpt_no in (
        ("20250101000001", "20250101000002"),
        ("20250101000002", "20250101000001"),
    ):
        (input_directory / "2025" / f"{filename_acpt_no}.html").write_text(
            f"""
            <html><body>
              <input type="hidden" name="acptNo" value="{embedded_acpt_no}" />
              <select id="mainDoc">
                <option value="20250101000999|Y" selected="selected">본문</option>
              </select>
              <select id="attachedDoc"><option value="20250101000888">첨부</option></select>
            </body></html>
            """,
            encoding="utf-8",
        )
    output_path = tmp_path / "compressed" / "compressed-external-html.json"

    with pytest.raises(ValueError, match="does not match input filename"):
        compress_disclosure_external_html_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(output_path.parent),
            }
        )

    assert not output_path.exists()


def test_compress_disclosure_external_html_payload_rejects_missing_manifest_metadata(tmp_path: Path) -> None:
    input_directory = tmp_path / "viewer_html"
    (input_directory / "2024").mkdir(parents=True)
    (input_directory / "2025").mkdir(parents=True)
    (input_directory / "kind_disclosure_html_manifest.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "disclosures": [
                    {
                        "acpt_no": "20240101000001",
                        "company_name": "테스트",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (input_directory / "2024" / "20240101000001.html").write_text(
        """
        <html><body>
          <input type="hidden" name="acptNo" value="20240101000001" />
          <select id="mainDoc">
            <option value="20240101000999|Y" selected="selected">본문</option>
          </select>
        </body></html>
        """,
        encoding="utf-8",
    )
    (input_directory / "2025" / "20250101000001.html").write_text(
        """
        <html><body>
          <input type="hidden" name="acptNo" value="20250101000001" />
          <select id="mainDoc">
            <option value="20250101000999|Y" selected="selected">본문</option>
          </select>
        </body></html>
        """,
        encoding="utf-8",
    )

    output_path = tmp_path / "compressed" / "compressed-external-html.json"
    with pytest.raises(ValueError, match="metadata.*20250101000001"):
        compress_disclosure_external_html_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(output_path.parent),
            }
        )

    assert not output_path.exists()


def test_compress_disclosure_external_html_payload_accepts_parallel_workers(tmp_path: Path) -> None:
    input_directory = tmp_path / "viewer_html"
    (input_directory / "2025").mkdir(parents=True)
    (input_directory / "kind_disclosure_html_manifest.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "disclosures": [
                    {
                        "acpt_no": "20250101000001",
                        "title": "첫 번째 제목",
                        "disclosed_at": "2025-01-01",
                    },
                    {
                        "acpt_no": "20250101000002",
                        "title": "두 번째 제목",
                        "disclosed_at": "2025-01-01",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    for acpt_no in ("20250101000001", "20250101000002"):
        (input_directory / "2025" / f"{acpt_no}.html").write_text(
            f"""
            <html><body>
              <input type="hidden" name="acptNo" value="{acpt_no}" />
              <select id="mainDoc">
                <option value="{acpt_no}999|Y" selected="selected">본문</option>
              </select>
              <select id="attachedDoc"><option value="{acpt_no}888">첨부</option></select>
            </body></html>
            """,
            encoding="utf-8",
        )

    payload = compress_disclosure_external_html_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(tmp_path / "compressed"),
            "parallel_workers": 2,
        }
    )

    output_path = tmp_path / "compressed" / "compressed-external-html.json"
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"] == {"found_files": 2, "compressed_files": 2, "written_files": 1}
    assert payload["processing_verification"]["passed"] is True
    assert payload["verification"]["passed"] is True
    assert "병렬 처리: 2개 워커" in payload["progress_log"]
    assert [record["acpt_no"] for record in saved["records"]] == ["20250101000001", "20250101000002"]
    assert [record["title"] for record in saved["records"]] == ["첫 번째 제목", "두 번째 제목"]


def test_compress_disclosure_external_html_payload_rejects_source_directory(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="source_directory is not supported"):
        compress_disclosure_external_html_payload(
            {"source_directory": str(tmp_path / "viewer_html")}
        )


def test_check_disclosure_external_html_output_directory_uses_compressed_json_year(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_full_target_scan(*args, **kwargs):
        raise AssertionError("existing checks should not scan compressed JSON docs for doc_no")

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._collect_internal_targets_from_compressed_payload",
        fail_full_target_scan,
    )

    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                    {
                        "acpt_no": "20250101000001",
                        "metadata": {"disclosed_at": "2025-01-01"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_directory = tmp_path / "content_html"
    output_directory.mkdir()

    payload = check_disclosure_html_output_directory_payload(
        {
            "source_compressed_json_path": str(compressed_path),
            "output_directory": str(output_directory),
        }
    )

    assert payload["source_type"] == "content"
    assert payload["requested_count"] == 1


def test_check_disclosure_external_html_output_directory_finds_yearly_output(
    tmp_path: Path,
) -> None:
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                    {
                        "acpt_no": "20250101000001",
                        "selected_main_doc_no": "20250101000999",
                        "metadata": {"disclosed_at": "2025-01-01"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_directory = tmp_path / "content_html"
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "2025" / "20250101000001.html").write_text(
        _valid_download_html(), encoding="utf-8"
    )

    payload = check_disclosure_html_output_directory_payload(
        {
            "source_compressed_json_path": str(compressed_path),
            "output_directory": str(output_directory),
        }
    )

    assert payload["existing_target_html_count"] == 1


def test_download_disclosure_external_html_payload_stops_when_cancelled(tmp_path: Path, monkeypatch) -> None:
    def fake_download(**kwargs):
        saved_paths = []
        for acpt_no in kwargs["acpt_numbers"]:
            if kwargs["cancel_check"]():
                break
            path = Path(kwargs["output_directory"]) / f"{acpt_no}.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_valid_download_html(), encoding="utf-8")
            saved_paths.append(path)
            cancel_disclosure_html_download("cancel-test")
        return saved_paths

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls", fake_download)

    payload = download_disclosure_external_html_payload(
        _external_workspace_body(
            tmp_path,
            {
                "disclosures": [
                    {"acpt_no": "20250101000001"},
                    {"acpt_no": "20250101000002"},
                ]
            },
            output_directory=str(tmp_path / "viewer_html"),
            cancel_token="cancel-test",
        )
    )

    assert payload["cancelled"] is True
    assert payload["saved_count"] == 1


def test_download_disclosure_external_html_payload_keeps_prequeued_cancel_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    download_called = False

    def fake_download(**kwargs):
        nonlocal download_called
        download_called = True
        return []

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls",
        fake_download,
    )
    cancel_disclosure_html_download("prequeued-external-cancel")

    payload = download_disclosure_external_html_payload(
        _external_workspace_body(
            tmp_path,
            {"disclosures": [{"acpt_no": "20250101000001"}]},
            output_directory=str(tmp_path / "viewer_html"),
            cancel_token="prequeued-external-cancel",
        )
    )

    assert download_called is False
    assert payload["cancelled"] is True
    assert payload["saved_count"] == 0
    assert not (tmp_path / "viewer_html").exists()


def test_download_disclosure_internal_html_payload_keeps_prequeued_cancel_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                    {
                        "acpt_no": "20250101000001",
                        "selected_main_doc_no": "20250101000999",
                        "metadata": {"disclosed_at": "2025-01-01"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    download_called = False

    def fake_download(**kwargs):
        nonlocal download_called
        download_called = True
        return []

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        fake_download,
    )
    cancel_disclosure_html_download("prequeued-internal-cancel")

    payload = download_disclosure_internal_html_payload(
        {
            "output_directory": str(tmp_path / "content_html"),
            "source_compressed_json_path": str(compressed_path),
            "cancel_token": "prequeued-internal-cancel",
        }
    )

    assert download_called is False
    assert payload["cancelled"] is True
    assert payload["saved_count"] == 0
    assert not (tmp_path / "content_html").exists()


def test_parse_disclosure_html_payload_requires_mode(tmp_path: Path) -> None:
    try:
        parse_disclosure_html_payload({"input_directory": str(tmp_path)})
    except ValueError as exc:
        assert str(exc) == "mode is required"
    else:
        raise AssertionError("expected ValueError")


def test_parse_disclosure_html_payload_rejects_invalid_record_filter(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="operator is unsupported"):
        parse_disclosure_html_payload(
            {
                "input_directory": str(tmp_path),
                "output_directory": str(tmp_path / "output"),
                "mode": "security_transaction",
                "parser_method": "security_transaction",
                "skip_errors": False,
                "record_filters": [
                    {"field": "title", "operator": "unsupported", "value": "x"}
                ],
            }
        )


def test_parse_disclosure_html_payload_rejects_unknown_parser_method(tmp_path: Path) -> None:
    try:
        parse_disclosure_html_payload(
            {
                "input_directory": str(tmp_path),
                "mode": "saved_filter",
                "parser_method": "unknown",
            }
        )
    except ValueError as exc:
        assert "unsupported parser_method" in str(exc)
        assert "bond_issuance" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_parse_disclosure_html_payload_parses_html_files_and_writes_result(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    _html_parse_file(viewer_dir, "20250101000001.html").write_text(
        """
        <html>
          <head><title>Sample Disclosure</title></head>
          <body><p class="SECTION-1">Sample Disclosure</p><table><tbody>
            <tr><th>1. 사채의 종류</th><td>전환사채</td></tr>
            <tr><th>2. 사채의 권면총액</th><td>1,000,000,000</td></tr>
            <tr><th>3. 자금조달의 목적</th><td>운영자금</td><td>1,000,000,000</td></tr>
          </tbody></table></body>
        </html>
        """,
        encoding="utf-8",
    )
    (tmp_path / "compressed-external-html.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20250101000001",
                        "title": "Sample Disclosure",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (viewer_dir / "ignore.txt").write_text("not html", encoding="utf-8")
    output_path = tmp_path / "parsed-saved_filter.json"

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "saved_filter",
            "parser_method": "bond_issuance",
            "skip_errors": False,
            **_html_parse_metadata_paths(
                compressed_path=tmp_path / "compressed-external-html.json"
            ),
        }
    )
    stored = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["format"] == "finiq_disclosure_html_parse_v1"
    assert payload["mode"] == "saved_filter"
    assert payload["parser_method"] == "bond_issuance"
    assert payload["summary"] == {"found_files": 1, "parsed_files": 1, "failed_files": 0}
    assert payload["cancelled"] is False
    assert "input_directory" not in payload
    assert "progress_log" not in payload
    assert payload["records"][0]["acpt_no"] == "20250101000001"
    assert payload["records"][0]["title"] == "Sample Disclosure"
    assert "source_file" not in payload["records"][0]
    assert "raw_rows" not in payload["records"][0]
    assert "raw_tables" not in payload["records"][0]
    assert stored["format"] == payload["format"]
    assert "input_directory" not in stored
    assert "source_file" not in stored["records"][0]
    assert "progress_log" not in stored


def test_parse_disclosure_html_payload_uses_filtered_metadata_market(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    _html_parse_file(viewer_dir, "20250101000001.html").write_text(
        """
        <html>
          <head><title>Sample Disclosure</title></head>
          <body><p class="SECTION-1">Sample Disclosure</p>유가증권시장 <table><tbody>
            <tr><th>1. 사채의 종류</th><td>전환사채</td></tr>
            <tr><th>2. 사채의 권면총액</th><td>1,000,000,000</td></tr>
            <tr><th>3. 자금조달의 목적</th><td>운영자금</td><td>1,000,000,000</td></tr>
          </tbody></table></body>
        </html>
        """,
        encoding="utf-8",
    )
    (tmp_path / "filtered.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20250101000001",
                        "market": "코스닥",
                        "company_name": "테스트발행사",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "bond_issuance",
            "parser_method": "bond_issuance",
            "skip_errors": False,
            **_html_parse_metadata_paths(filtered_path=tmp_path / "filtered.json"),
        }
    )

    assert payload["records"][0]["상장구분"] == "코스닥"
    assert payload["records"][0]["corp_name"] == "테스트발행사"


def test_parse_disclosure_html_payload_uses_explicit_metadata_path(
    tmp_path: Path, monkeypatch
) -> None:
    input_root = tmp_path / "input"
    source_dir = input_root / "source"
    input_dir = source_dir / "viewer_html"
    input_dir.mkdir(parents=True)
    _html_parse_file(input_dir, "20250101000001.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    _html_parse_file(input_dir, "20250102000002.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    (input_root / "filtered.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20250101000001",
                        "market": "유가증권",
                        "company_name": "루트회사",
                    },
                    {
                        "acpt_no": "20250102000002",
                        "market": "유가증권",
                        "company_name": "루트회사",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (source_dir / "filtered.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20250101000001",
                        "market": "코스닥",
                        "company_name": "일반저장회사",
                    },
                    {
                        "acpt_no": "20250102000002",
                        "market": "코스닥",
                        "company_name": "연도별저장회사",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "bond_issuance",
            "title": "",
        }

    monkeypatch.setitem(PARSER_REGISTRY, "bond_issuance", fake_parser)

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(input_dir),
            "output_directory": str(tmp_path / "output"),
            "mode": "bond_issuance",
            "parser_method": "bond_issuance",
            "skip_errors": False,
            **_html_parse_metadata_paths(
                filtered_path=source_dir / "filtered.json"
            ),
        }
    )

    records = {record["acpt_no"]: record for record in payload["records"]}
    assert records["20250101000001"]["상장구분"] == "코스닥"
    assert records["20250101000001"]["corp_name"] == "일반저장회사"
    assert records["20250102000002"]["상장구분"] == "코스닥"
    assert records["20250102000002"]["corp_name"] == "연도별저장회사"


def test_parse_disclosure_html_payload_ignores_download_manifest_metadata(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    _html_parse_file(viewer_dir, "20250101000001.html").write_text(
        """
        <html>
          <body>
            <table>
              <tr><td>1. 사채의 종류</td><td>회차</td><td>1</td><td>종류</td><td>무기명식 무보증 전환사채</td></tr>
              <tr><td>2. 사채의 권면총액 (원)</td><td>1,000,000,000</td></tr>
              <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>1,000,000,000</td></tr>
            </table>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (viewer_dir / "kind_disclosure_html_manifest.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "disclosures": [
                    {
                        "acpt_no": "20250101000001",
                        "title": "[테스트] 전환사채권 발행결정",
                        "market": "코스닥",
                        "company_name": "테스트발행사",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "bond_issuance",
            "parser_method": "bond_issuance",
            "skip_errors": False,
        }
    )

    record = payload["records"][0]
    assert record["title"] == ""
    assert record["종류"] is None
    assert record["상장구분"] is None
    assert record["corp_name"] is None


def test_parse_disclosure_html_payload_does_not_infer_market_from_body(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    _html_parse_file(viewer_dir, "20250101000001.html").write_text(
        """
        <html>
          <head><title>Sample Disclosure</title></head>
          <body><p class="SECTION-1">Sample Disclosure</p>유가증권시장 <table><tbody>
            <tr><th>1. 사채의 종류</th><td>전환사채</td></tr>
            <tr><th>2. 사채의 권면총액</th><td>1,000,000,000</td></tr>
            <tr><th>3. 자금조달의 목적</th><td>운영자금</td><td>1,000,000,000</td></tr>
          </tbody></table></body>
        </html>
        """,
        encoding="utf-8",
    )

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "bond_issuance",
            "parser_method": "bond_issuance",
            "skip_errors": False,
        }
    )

    assert payload["records"][0]["상장구분"] is None


def test_parse_disclosure_html_payload_recurses_and_uses_bond_metadata_files(tmp_path: Path) -> None:
    bond_dir = tmp_path / "bond_issuance"
    input_dir = bond_dir / "kind_html_contents_grouped_sections"
    year_dir = input_dir / "2025"
    year_dir.mkdir(parents=True)
    (year_dir / "20250102000002.html").write_text(
        """
        <html>
          <body>
            <h2 class="SECTION-1" id="toc_2"></h2><p class="SECTION-1">전환사채권 발행결정</p>
            <table>
              <tr><td>1. 사채의 종류</td><td>회차</td><td>3</td><td>종류</td><td>무기명식 무보증 전환사채</td></tr>
              <tr><td>2. 사채의 권면총액 (원)</td><td>1,000,000,000</td></tr>
              <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>1,000,000,000</td></tr>
              <tr><td>5. 사채만기일</td><td>2028년 01월 02일</td></tr>
              <tr><td>8. 사채발행방법</td><td>사모</td></tr>
              <tr><td>9. 전환에 관한 사항</td><td>전환가액 (원/주)</td><td>1,000</td></tr>
              <tr><td>9. 전환에 관한 사항</td><td>전환에 따라 발행할 주식의 종류</td><td>테스트발행사 기명식 보통주</td></tr>
              <tr><td>9. 전환에 관한 사항</td><td>전환청구기간</td><td>시작일</td><td>2026년 01월 02일</td></tr>
              <tr><td>9. 전환에 관한 사항</td><td>전환청구기간</td><td>종료일</td><td>2027년 12월 02일</td></tr>
              <tr><td>12. 납입일</td><td>2025년 01월 02일</td></tr>
            </table>
            <table>
              <tr><th>발행 대상자명</th><th>발행권면총액(원)</th></tr>
              <tr><td>테스트조합</td><td>1,000,000,000</td></tr>
            </table>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (bond_dir / "filtered.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20250102000002",
                        "company_name": "테스트발행사",
                        "market": "코스닥",
                        "title": "[테스트발행사] 전환사채권발행결정",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (bond_dir / "compressed-external-html.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20250102000002",
                        "title": "[테스트발행사] 전환사채권발행결정",
                        "header": "테스트발행사 (123456)",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(input_dir),
            "output_directory": str(bond_dir),
            "mode": "bond_issuance",
            "parser_method": "bond_issuance",
            "skip_errors": False,
            **_html_parse_metadata_paths(
                filtered_path=bond_dir / "filtered.json",
                compressed_path=bond_dir / "compressed-external-html.json",
            ),
        }
    )

    assert payload["summary"]["found_files"] == 1
    assert "input_directory" not in payload
    assert "output_path" not in payload
    assert (bond_dir / "parsed-bond_issuance.json").is_file()
    stored = json.loads(
        (bond_dir / "parsed-bond_issuance.json").read_text(encoding="utf-8")
    )
    assert "input_directory" not in stored
    assert "output_path" not in stored
    assert not (input_dir / "parsed-bond_issuance.json").exists()
    record = payload["records"][0]
    assert record["acpt_no"] == "20250102000002"
    assert record["title"] == "[테스트발행사] 전환사채권발행결정"
    assert record["corp_name"] == "테스트발행사"
    assert record["상장구분"] == "코스닥"
    assert record["회차"] == "3"
    assert record["종류"] == "CB"
    assert record["발행금액"] == 1_000_000_000
    assert record["행사가액"] == 1000
    assert record["납입일"] == "2025년 01월 02일"
    assert record["만기일"] == "2028년 01월 02일"
    assert record["사채발행방법"] == "사모"
    assert record["행사시작일"] == "2026년 01월 02일"
    assert record["행사종료일"] == "2027년 12월 02일"
    assert record["투자자"] == [["테스트조합", 1_000_000_000]]


def test_parse_disclosure_html_payload_does_not_fallback_to_metadata_display_title(
    tmp_path: Path,
) -> None:
    bond_dir = tmp_path / "bond_issuance"
    input_dir = bond_dir / "kind_html_contents_grouped_sections"
    input_dir.mkdir(parents=True)
    _html_parse_file(input_dir, "20250102000003.html").write_text(
        """
        <html>
          <body>
            <table>
              <tr><td>1. 사채의 종류</td><td>회차</td><td>3</td><td>종류</td><td>무기명식 무보증 전환사채</td></tr>
              <tr><td>2. 사채의 권면총액 (원)</td><td>1,000,000,000</td></tr>
              <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>1,000,000,000</td></tr>
            </table>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (bond_dir / "filtered.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20250102000003",
                        "company_name": "테스트발행사",
                        "market": "코스닥",
                        "title": "",
                        "title_display": "[정정]전환사채권발행결정",
                        "title_attr": "전환사채권발행결정",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(input_dir),
            "output_directory": str(bond_dir),
            "mode": "bond_issuance",
            "parser_method": "bond_issuance",
            "skip_errors": False,
            **_html_parse_metadata_paths(
                filtered_path=bond_dir / "filtered.json"
            ),
        }
    )

    record = payload["records"][0]
    assert record["title"] == ""
    assert record["corp_name"] == "테스트발행사"
    assert record["상장구분"] == "코스닥"
    assert any(
        warning["warning"] == "주입 제목이 없습니다."
        for warning in payload["warnings"]
    )


def test_parse_disclosure_html_payload_writes_parse_to_output_directory(
    tmp_path: Path, monkeypatch
) -> None:
    rights_dir = tmp_path / "rights_issuance"
    input_dir = rights_dir / "kind_html_contents_sections"
    output_dir = tmp_path / "parse_output"
    input_dir.mkdir(parents=True)
    html_file = _html_parse_file(input_dir, "20250102000002.html")
    html_file.write_text("<html></html>", encoding="utf-8")

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "rights_issuance",
            "title": "",
        }

    monkeypatch.setitem(PARSER_REGISTRY, "rights_issuance", fake_parser)

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(input_dir),
            "output_directory": str(output_dir),
            "mode": "rights_issuance",
            "parser_method": "rights_issuance",
            "skip_errors": False,
        }
    )

    assert "input_directory" not in payload
    assert "output_path" not in payload
    assert (output_dir / "parsed-rights_issuance.json").is_file()
    assert not (input_dir / "parsed-rights_issuance.json").exists()


def test_parse_disclosure_html_payload_accepts_dotted_output_directory(
    tmp_path: Path, monkeypatch
) -> None:
    input_dir = tmp_path / "viewer_html"
    output_dir = tmp_path / "project-1.0" / "out"
    input_dir.mkdir()
    _html_parse_file(input_dir, "20250102000002.html").write_text(
        "<html></html>", encoding="utf-8"
    )

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "rights_issuance",
            "title": "",
        }

    monkeypatch.setitem(PARSER_REGISTRY, "rights_issuance", fake_parser)

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(input_dir),
            "output_directory": str(output_dir),
            "mode": "rights_issuance",
            "parser_method": "rights_issuance",
            "skip_errors": False,
        }
    )

    assert "input_directory" not in payload
    assert "output_path" not in payload
    assert (output_dir / "parsed-rights_issuance.json").is_file()


def test_parse_disclosure_html_payload_requires_output_directory(
    tmp_path: Path, monkeypatch
) -> None:
    input_dir = tmp_path / "section_html"
    input_dir.mkdir()
    html_file = _html_parse_file(input_dir, "20250102000002.html")
    html_file.write_text("<html></html>", encoding="utf-8")

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "rights_issuance",
            "title": "",
        }

    monkeypatch.setitem(PARSER_REGISTRY, "rights_issuance", fake_parser)

    with pytest.raises(ValueError, match="output_directory is required"):
        parse_disclosure_html_payload(
            {
                "input_directory": str(input_dir),
                "mode": "rights_issuance",
                "parser_method": "rights_issuance",
                "skip_errors": False,
            }
        )


def test_parse_disclosure_html_payload_does_not_build_family_from_filtered_disclosures(
    tmp_path: Path, monkeypatch
) -> None:
    input_dir = tmp_path / "rights_issuance" / "kind_html_contents_sections"
    input_dir.mkdir(parents=True)
    for acpt_no in (
        "20250101000001",
        "20250102000002",
        "20250103000003",
        "20250104000004",
    ):
        _html_parse_file(input_dir, f"{acpt_no}.html").write_text(
            "<html></html>", encoding="utf-8"
        )

    (input_dir.parent / "filtered.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20250101000001",
                        "company_name": "회사명만있는회사",
                        "title": "유상증자결정",
                        "title_attr": "유상증자결정",
                        "disclosed_at": "2025-01-01 09:00",
                        "is_correction_report": False,
                    },
                    {
                        "acpt_no": "20250102000002",
                        "company_name": "회사명만있는회사",
                        "title": "[정정]유상증자결정",
                        "title_attr": "유상증자결정",
                        "disclosed_at": "2025-01-02 09:00",
                        "is_correction_report": True,
                    },
                    {
                        "acpt_no": "20250103000003",
                        "company_key": "STRICT",
                        "company_name": "계약필드회사",
                        "title": "유상증자결정",
                        "title_base": "유상증자결정",
                        "title_display": "유상증자결정",
                        "disclosed_at": "2025-01-03 09:00",
                        "is_correction_report": False,
                    },
                    {
                        "acpt_no": "20250104000004",
                        "company_key": "STRICT",
                        "company_name": "계약필드회사",
                        "title": "[정정]유상증자결정",
                        "title_base": "유상증자결정",
                        "title_display": "[정정]유상증자결정",
                        "disclosed_at": "2025-01-04 09:00",
                        "is_correction_report": True,
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_parser(html_text, *, file_path, title=None):
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "rights_issuance",
            "title": title or "",
        }

    monkeypatch.setitem(PARSER_REGISTRY, "rights_issuance", fake_parser)

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(input_dir),
            "output_directory": str(tmp_path),
            "mode": "rights_issuance",
            "parser_method": "rights_issuance",
            "skip_errors": False,
        }
    )

    records = {record["acpt_no"]: record for record in payload["records"]}
    assert payload["families"] == {}
    assert "correction_families" not in records["20250101000001"]
    assert "correction_families" not in records["20250102000002"]
    assert "correction_families" not in records["20250103000003"]
    assert "correction_families" not in records["20250104000004"]


def test_parse_disclosure_html_payload_uses_external_html_main_docs_for_corrections(
    tmp_path: Path, monkeypatch
) -> None:
    input_dir = tmp_path / "rights_issuance" / "kind_html_contents_sections"
    input_dir.mkdir(parents=True)
    first = _html_parse_file(input_dir, "20081210000626.html")
    second = _html_parse_file(input_dir, "20081211000252.html")
    first.write_text("<html></html>", encoding="utf-8")
    second.write_text("<html></html>", encoding="utf-8")
    (input_dir.parent / "filtered.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "company_key": "03679",
                        "acpt_no": "20081210000626",
                        "company_name": "자강",
                        "market": "코스닥",
                        "disclosed_at": "2008-12-10 18:16",
                        "title": "유상증자결정",
                        "is_correction_report": False,
                        "has_later_correction": True,
                    },
                    {
                        "company_key": "03679",
                        "acpt_no": "20081211000252",
                        "company_name": "자강",
                        "market": "코스닥",
                        "disclosed_at": "2008-12-11 15:45",
                        "title": "[정정]유상증자결정(제3자배정)",
                        "is_correction_report": True,
                        "has_later_correction": False,
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    main_docs = [
        {
            "select_id": "mainDoc",
            "option_index": 1,
            "doc_no": "20081210001405",
            "text": "유상증자결정 (2008.12.10)",
            "value": "20081210001405|N",
            "latest_flag": "N",
            "selected": False,
        },
        {
            "select_id": "mainDoc",
            "option_index": 2,
            "doc_no": "20081211000613",
            "text": "[정정]유상증자결정 (2008.12.11)",
            "value": "20081211000613|Y",
            "latest_flag": "Y",
            "selected": False,
        },
        {
            "select_id": "attachedDoc",
            "option_index": 1,
            "doc_no": "20081211000614",
            "text": "[정정]이사회의사록 (2008.12.11)",
            "selected": False,
        },
    ]
    (input_dir.parent / "compressed-external-html.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20081210000626",
                        "title": "[자강] 유상증자결정",
                        "header": "자강 (036790)",
                        "selected_main_doc_no": "20081210001405",
                        "docs": [
                            {
                                **doc,
                                "selected": doc["doc_no"] == "20081210001405",
                            }
                            for doc in main_docs
                        ],
                        "metadata": {
                            "acpt_no": "20081210000626",
                            "company_name": "자강",
                            "market": "코스닥",
                            "disclosed_at": "2008-12-10 18:16",
                            "title": "유상증자결정",
                        },
                    },
                    {
                        "acpt_no": "20081211000252",
                        "title": "[자강] 유상증자결정",
                        "header": "자강 (036790)",
                        "selected_main_doc_no": "20081211000613",
                        "docs": [
                            {
                                **doc,
                                "selected": doc["doc_no"] == "20081211000613",
                            }
                            for doc in main_docs
                        ],
                        "metadata": {
                            "acpt_no": "20081211000252",
                            "company_name": "자강",
                            "market": "코스닥",
                            "disclosed_at": "2008-12-11 15:45",
                            "title": "[정정]유상증자결정(제3자배정)",
                        },
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_parser(html_text, *, file_path):
        acpt_no = Path(file_path).stem
        return {
            "acpt_no": acpt_no,
            "mode": "rights_issuance",
            "title": "유상증자 결정",
        }

    monkeypatch.setitem(PARSER_REGISTRY, "rights_issuance", fake_parser)

    metadata_paths = _html_parse_metadata_paths(
        filtered_path=input_dir.parent / "filtered.json",
        compressed_path=input_dir.parent / "compressed-external-html.json",
    )
    metadata_index, families = _load_html_parse_metadata(
        input_dir,
        filtered_metadata_path=Path(metadata_paths["filtered_metadata_path"]),
        compressed_metadata_path=Path(metadata_paths["compressed_metadata_path"]),
    )
    assert all(
        "correction_families" not in metadata
        for metadata in metadata_index.values()
    )
    assert metadata_index["20081210000626"]["family_id"] == "20081211000252"
    assert metadata_index["20081210000626"]["current_sequence"] == 0
    assert metadata_index["20081210000626"]["family_member_count"] == 2
    assert families["20081211000252"]["members"][1]["acpt_no"] == "20081211000252"

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(input_dir),
            "output_directory": str(tmp_path),
            "mode": "rights_issuance",
            "parser_method": "rights_issuance",
            "skip_errors": False,
            **metadata_paths,
        }
    )

    records = {record["acpt_no"]: record for record in payload["records"]}
    assert all("docs" not in record for record in records.values())
    assert all("correction_families" not in record for record in records.values())
    assert records["20081210000626"]["family_id"] == "20081211000252"
    assert records["20081210000626"]["current_sequence"] == 0
    assert records["20081210000626"]["family_member_count"] == 2
    assert records["20081211000252"]["family_id"] == "20081211000252"
    assert records["20081211000252"]["current_sequence"] == 1
    assert records["20081211000252"]["family_member_count"] == 2
    family = payload["families"]["20081211000252"]
    assert family["members"] == [
        {
            "sequence": 0,
            "acpt_no": "20081210000626",
            "doc_no": "20081210001405",
            "title": "유상증자결정 (2008.12.10)",
            "disclosed_at": "2008-12-10 18:16",
            "is_correction_report": False,
        },
        {
            "sequence": 1,
            "acpt_no": "20081211000252",
            "doc_no": "20081211000613",
            "title": "[정정]유상증자결정 (2008.12.11)",
            "disclosed_at": "2008-12-11 15:45",
            "is_correction_report": True,
        },
    ]
    assert all(
        member["doc_no"] != "20081211000614" for member in family["members"]
    )


def test_build_bond_parse_summary_payload_loads_ui_rows(tmp_path: Path) -> None:
    (tmp_path / "06-sections").mkdir()
    output_directory = tmp_path / "07-converted" / "bond_issuance"
    output_directory.mkdir(parents=True)
    parse_path = output_directory / "parsed-bond_issuance.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "bond_issuance",
                "parser_method": "bond_issuance",
                "families": {
                    "20250102000002": {
                        "members": [
                            {"sequence": 0, "acpt_no": "20250101000001"},
                            {"sequence": 1, "acpt_no": "20250102000002"},
                        ],
                    }
                },
                "records": [
                    {
                        "title": "[정정]전환사채권발행결정",
                        "acpt_no": "20250102000002",
                        "family_id": "20250102000002",
                        "current_sequence": 1,
                        "family_member_count": 2,
                        "corp_name": "발행사",
                        "회차": "1",
                        "종류": "CB",
                        "기업명(행사대상)": "대상회사",
                        "상장구분": "코스닥",
                        "발행금액": 1_000_000_000,
                        "행사가액": 1000,
                        "납입일": "2025년 01월 02일",
                        "만기일": "2028년 01월 02일",
                        "사채발행방법": "사모",
                        "행사시작일": "2026년 01월 02일",
                        "행사종료일": "2027년 12월 02일",
                        "투자자": [["테스트조합", 1_000_000_000]],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_bond_parse_summary_payload(
        {
            "input_directory": str(tmp_path / "06-sections"),
            "output_path": str(output_directory),
            "mode": "bond_issuance",
        }
    )

    assert payload["format"] == "finiq_bond_parse_summary_v1"
    assert payload["summary"] == {
        "records": 1,
        "visible_records": 1,
        "families": 1,
        "correction_records": 1,
        "latest_records": 1,
    }
    assert payload["records"][0]["family_id"] == "20250102000002"
    assert payload["records"][0]["fields"]["발행금액"] == 1_000_000_000
    assert payload["records"][0]["fields"]["사채발행방법"] == "사모"
    assert payload["records"][0]["fields"]["투자자"] == [["테스트조합", 1_000_000_000]]
    assert "리픽싱(%)" not in payload["records"][0]["fields"]


def test_build_bond_parse_summary_payload_accepts_result_directory(tmp_path: Path) -> None:
    input_directory = tmp_path / "06-sections"
    input_directory.mkdir()
    output_directory = tmp_path / "07-converted" / "bond_issuance"
    output_directory.mkdir(parents=True)
    parse_path = output_directory / "parsed-bond_issuance.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "bond_issuance",
                "parser_method": "bond_issuance",
                "records": [
                    {
                        "title": "전환사채권발행결정",
                        "acpt_no": "20250102000002",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_bond_parse_summary_payload(
        {
            "input_directory": str(input_directory),
            "output_path": str(output_directory),
            "mode": "bond_issuance",
        }
    )

    assert payload["source_path"] == str(parse_path)
    assert payload["summary"]["records"] == 1


@pytest.mark.parametrize("suffix", [".json", ".txt"])
def test_build_bond_parse_summary_payload_rejects_missing_result_file_path(
    tmp_path: Path, suffix: str
) -> None:
    result_path = tmp_path / f"parsed-bond_issuance{suffix}"

    with pytest.raises(ValueError, match="output_path must be a directory path"):
        build_bond_parse_summary_payload(
            {"output_path": str(result_path), "mode": "bond_issuance"}
        )

    assert not result_path.exists()


def test_build_bond_parse_summary_payload_includes_source_preview(tmp_path: Path) -> None:
    input_directory = tmp_path / "06-sections"
    (input_directory / "2025").mkdir(parents=True)
    source_path = input_directory / "2025" / "20250102000002.html"
    source_path.write_text(
        """
        <html>
          <head><title>전환사채권발행결정</title></head>
          <body>
            <p class="SECTION-1">전환사채권발행결정</p>
            <table>
              <tr><th>1. 사채의 종류</th><td>전환사채</td></tr>
              <tr><th>2. 사채의 권면(전자등록)총액</th><td>1,000,000,000</td></tr>
              <tr><th>3. 자금조달의 목적</th><td>운영자금</td></tr>
            </table>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    output_directory = tmp_path / "07-converted" / "bond_issuance"
    output_directory.mkdir(parents=True)
    parse_path = output_directory / "parsed-bond_issuance.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "bond_issuance",
                "parser_method": "bond_issuance",
                "records": [
                    {
                        "title": "전환사채권발행결정",
                        "acpt_no": "20250102000002",
                        "corp_name": "발행사",
                        "회차": "1",
                        "종류": "CB",
                        "발행금액": 1_000_000_000,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_bond_parse_summary_payload(
        {
            "input_directory": str(input_directory),
            "output_path": str(output_directory),
            "mode": "bond_issuance",
        }
    )

    summary_record = payload["records"][0]
    preview = summary_record["source_preview"]
    assert preview["available"] is True
    assert "source_file" not in summary_record
    assert "source_file" not in preview
    assert preview["tables"][0]["rows"][0] == ["1. 사채의 종류", "전환사채"]
    assert preview["tables"][0]["rows"][1] == ["2. 사채의 권면(전자등록)총액", "1,000,000,000"]


def test_build_bond_parse_summary_payload_uses_workspace_mode_and_parser_method(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "06-sections"
    input_directory.mkdir()
    output_directory = tmp_path / "07-converted" / "saved_filter"
    output_directory.mkdir(parents=True)
    parse_path = output_directory / "parsed-saved_filter.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "saved_filter",
                "parser_method": "bond_issuance",
                "records": [
                    {
                        "title": "전환사채권발행결정",
                        "acpt_no": "20250102000002",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_bond_parse_summary_payload(
        {
            "input_directory": str(input_directory),
            "output_path": str(output_directory),
            "mode": "saved_filter",
        }
    )

    assert payload["source_path"] == str(parse_path)
    assert payload["summary"]["records"] == 1

    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "saved_filter",
                "parser_method": "rights_issuance",
                "records": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="parser_method must be bond_issuance"):
        build_bond_parse_summary_payload(
            {
                "input_directory": str(input_directory),
                "output_path": str(output_directory),
                "mode": "saved_filter",
            }
        )


def test_build_parse_preview_payload_parses_input_directory(tmp_path: Path) -> None:
    bond_dir = tmp_path / "bond_issuance"
    input_dir = bond_dir / "viewer_html"
    (input_dir / "2025").mkdir(parents=True)
    (input_dir / "2025" / "20250102000002.html").write_text(
        """
        <html>
          <head><title>전환사채권발행결정</title></head>
          <body>
            <p class="SECTION-1">전환사채권발행결정</p>
                <table><tbody>
                  <tr><th>1. 사채의 종류</th><td>전환사채</td></tr>
                  <tr><th>2. 사채의 권면총액</th><td>1,000,000,000</td></tr>
                  <tr><th>3. 자금조달의 목적</th><td>운영자금</td><td>1,000,000,000</td></tr>
                </tbody></table>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (bond_dir / "filtered.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "company_key": "TEST",
                        "acpt_no": "20250101000001",
                        "company_name": "테스트발행사",
                        "market": "코스닥",
                        "disclosed_at": "2025-01-01 09:00",
                        "title": "전환사채권발행결정",
                        "is_correction_report": False,
                        "has_later_correction": True,
                    },
                    {
                        "company_key": "TEST",
                        "acpt_no": "20250102000002",
                        "company_name": "테스트발행사",
                        "market": "코스닥",
                        "disclosed_at": "2025-01-02 09:00",
                        "title": "[정정]전환사채권발행결정",
                        "is_correction_report": True,
                        "has_later_correction": False,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (bond_dir / "compressed-external-html.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20250102000002",
                        "title": "[테스트발행사] 전환사채권발행결정",
                        "header": "테스트발행사 (123456)",
                        "doc_no": "00000000835386",
                        "selected_main_doc_no": "20250102009999",
                        "docs": [
                            {
                                "select_id": "mainDoc",
                                "option_index": 1,
                                "doc_no": "00000000835386",
                                "value": "00000000835386|N",
                                "latest_flag": "N",
                                "selected": False,
                            },
                            {
                                "select_id": "mainDoc",
                                "option_index": 2,
                                "doc_no": "20250102009999",
                                "value": "20250102009999|Y",
                                "latest_flag": "Y",
                                "selected": True,
                            },
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_parse_preview_payload(
        {
            "input_directory": str(input_dir),
            "mode": "bond_issuance",
            "parser_method": "bond_issuance",
            "limit": 1,
            **_html_parse_metadata_paths(
                filtered_path=bond_dir / "filtered.json",
                compressed_path=bond_dir / "compressed-external-html.json",
            ),
        }
    )

    assert payload["source_kind"] == "input_directory"
    assert payload["input_directory"] == str(input_dir.resolve())
    assert payload["summary"] == {"records": 1, "visible_records": 1, "errors": 0}
    preview_record = payload["records"][0]
    assert preview_record["title"] == "[테스트발행사] 전환사채권발행결정"
    assert "source_file" not in preview_record
    assert "source_file" not in preview_record["source_preview"]
    record = preview_record["parsed_result"]
    assert record["acpt_no"] == "20250102000002"
    assert "rcept_no" not in record
    assert record["doc_no"] == "20250102009999"
    assert "selected_main_doc_no" not in record
    assert "docs" not in record
    assert record["corp_name"] == "테스트발행사"
    assert record["상장구분"] == "코스닥"
    assert "correction_families" not in record
    assert payload["records"][0]["source_preview"]["available"] is True


def test_compact_source_tables_limits_table_components_and_total_rows() -> None:
    short_tables = [
        {"index": index, "logical_rows": [[str(index)]]}
        for index in range(13)
    ]

    tables, omitted_rows = _compact_source_tables(short_tables)

    assert len(tables) == 12
    assert omitted_rows == 1

    tables, omitted_rows = _compact_source_tables(
        [{"index": 0, "logical_rows": [[str(index)] for index in range(121)]}]
    )

    assert len(tables[0]["rows"]) == 120
    assert tables[0]["omitted_rows"] == 1
    assert omitted_rows == 1


def test_build_parse_change_log_payload_classifies_major_changes(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.app import config as app_config

    monkeypatch.setattr(app_config, "change_log_date_thresholds", {"납입일": 0})
    monkeypatch.setattr(app_config, "change_log_numeric_thresholds", {})

    parse_path = tmp_path / "parsed-rights_issuance.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "rights_issuance",
                "parser_method": "rights_issuance",
                "families": {
                    "20240829000001": {
                        "members": [
                            {"sequence": 0, "acpt_no": "20240822000001"},
                            {"sequence": 1, "acpt_no": "20240829000001"},
                        ],
                    }
                },
                "records": [
                    {
                        "title": "유상증자결정",
                        "acpt_no": "20240822000001",
                        "family_id": "20240829000001",
                        "current_sequence": 0,
                        "family_member_count": 2,
                        "신주의 종류와 수": [["보통주식", 100]],
                        "발행목적": [["운영자금", 1000]],
                        "발행가액": [["보통주식", 1000]],
                        "납입일": "2024년 08월 30일",
                    },
                    {
                        "title": "[정정]유상증자결정",
                        "acpt_no": "20240829000001",
                        "family_id": "20240829000001",
                        "current_sequence": 1,
                        "family_member_count": 2,
                        "신주의 종류와 수": [["보통주식", 100]],
                        "발행목적": [["운영자금", 2000]],
                        "발행가액": [["보통주식", 1000]],
                        "납입일": "2024년 09월 02일",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_parse_change_log_payload(
        {"output_path": str(tmp_path), "mode": "rights_issuance"}
    )

    assert payload["format"] == "finiq_parse_change_log_v1"
    assert payload["mode"] == "rights_issuance"
    assert payload["summary"]["major_changes"] == 1
    assert payload["summary"]["minor_changes"] == 0
    assert payload["families"][0]["severity"] == "major"
    assert payload["families"][0]["changed_fields"] == 2
    assert [change["field"] for change in payload["families"][0]["changes"][0]["changes"]] == ["발행목적", "납입일"]


def test_build_parse_change_log_payload_uses_parser_method_not_workspace_mode(
    tmp_path: Path, monkeypatch
) -> None:
    from finiq.market_desk.web.app import config as app_config

    monkeypatch.setattr(app_config, "change_log_date_thresholds", {"납입일": 0})
    monkeypatch.setattr(app_config, "change_log_numeric_thresholds", {})

    parse_path = tmp_path / "parsed-saved_filter.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "saved_filter",
                "parser_method": "rights_issuance",
                "families": {
                    "20240829000001": {
                        "members": [
                            {"sequence": 0, "acpt_no": "20240822000001"},
                            {"sequence": 1, "acpt_no": "20240829000001"},
                        ],
                    }
                },
                "records": [
                    {
                        "title": "유상증자결정",
                        "acpt_no": "20240822000001",
                        "family_id": "20240829000001",
                        "current_sequence": 0,
                        "family_member_count": 2,
                        "신주의 종류와 수": [["보통주식", 100]],
                        "발행목적": [["운영자금", 1000]],
                        "발행가액": [["보통주식", 1000]],
                        "납입일": "2024년 08월 30일",
                    },
                    {
                        "title": "[정정]유상증자결정",
                        "acpt_no": "20240829000001",
                        "family_id": "20240829000001",
                        "current_sequence": 1,
                        "family_member_count": 2,
                        "신주의 종류와 수": [["보통주식", 100]],
                        "발행목적": [["운영자금", 2000]],
                        "발행가액": [["보통주식", 1000]],
                        "납입일": "2024년 09월 02일",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_parse_change_log_payload(
        {"output_path": str(tmp_path), "mode": "saved_filter"}
    )

    assert payload["mode"] == "saved_filter"
    assert payload["summary"]["major_changes"] == 1
    assert [change["field"] for change in payload["families"][0]["changes"][0]["changes"]] == [
        "발행목적",
        "납입일",
    ]

    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "saved_filter",
                "records": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="parser_method is required"):
        build_parse_change_log_payload(
            {"output_path": str(tmp_path), "mode": "saved_filter"}
        )


def test_build_parse_change_log_payload_applies_default_threshold_to_nested_numeric_fields(
    tmp_path: Path, monkeypatch
) -> None:
    from finiq.market_desk.web.app import config as app_config

    monkeypatch.setattr(app_config, "change_log_date_thresholds", {})
    monkeypatch.setattr(app_config, "change_log_numeric_thresholds", {})
    parse_path = tmp_path / "parsed-rights_issuance.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "rights_issuance",
                "parser_method": "rights_issuance",
                "records": [
                    {
                        "title": "유상증자결정",
                        "acpt_no": "20260701000001",
                        "family_id": "20260702000001",
                        "current_sequence": 0,
                        "family_member_count": 2,
                        "상장구분": "유가증권시장",
                        "신주의 종류와 수": [["보통주식", 100]],
                    },
                    {
                        "title": "[정정]유상증자결정",
                        "acpt_no": "20260702000001",
                        "family_id": "20260702000001",
                        "current_sequence": 1,
                        "family_member_count": 2,
                        "상장구분": "코스닥시장",
                        "신주의 종류와 수": [["보통주식", 101]],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_parse_change_log_payload(
        {
            "output_path": str(tmp_path),
            "mode": "rights_issuance",
            "summary_only": True,
        }
    )

    assert payload["families"][0]["changed_fields"] == 0
    assert payload["families"][0]["severity"] == "minor"
    assert payload["summary"]["major_changes"] == 0
    assert payload["summary"]["minor_changes"] == 1


def test_build_parse_change_log_payload_accepts_result_folder(tmp_path: Path) -> None:
    parse_path = tmp_path / "parsed-rights_issuance.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "rights_issuance",
                "parser_method": "rights_issuance",
                "records": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_parse_change_log_payload({"output_path": str(tmp_path), "mode": "rights_issuance"})

    assert payload["source_path"] == str(parse_path.resolve())


def test_build_parse_change_log_payload_resolves_derived_workspace_result(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    result_directory = (
        data_root
        / "07-converted"
        / "rights_issuance"
        / "subfilters"
        / "rights_issuance_kosdaq"
    )
    result_directory.mkdir(parents=True)
    parse_path = result_directory / "parsed-rights_issuance_kosdaq.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "rights_issuance_kosdaq",
                "parser_method": "rights_issuance",
                "records": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_parse_change_log_payload(
        {
            "data_root": str(data_root),
            "mode": "rights_issuance_kosdaq",
            "parent_mode": "rights_issuance",
        }
    )

    assert payload["source_path"] == str(parse_path.resolve())


def test_build_parse_change_log_payload_requires_mode_for_result_folder(tmp_path: Path) -> None:
    parse_path = tmp_path / "parsed-bond_issuance.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "bond_issuance",
                "parser_method": "bond_issuance",
                "records": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="mode is required"):
        build_parse_change_log_payload({"output_path": str(tmp_path)})


def test_build_parse_change_log_payload_rejects_missing_result_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="파싱 결과 파일을 찾을 수 없습니다"):
        build_parse_change_log_payload(
            {"output_path": str(tmp_path), "mode": "bond_issuance"}
        )


@pytest.mark.parametrize("suffix", [".json", ".txt"])
def test_build_parse_change_log_payload_rejects_missing_result_file_path(
    tmp_path: Path, suffix: str
) -> None:
    result_path = tmp_path / f"parsed-bond_issuance{suffix}"

    with pytest.raises(ValueError, match="output_path must be a directory path"):
        build_parse_change_log_payload(
            {"output_path": str(result_path), "mode": "bond_issuance"}
        )

    assert not result_path.exists()


@pytest.mark.parametrize("suffix", [".json", ".txt"])
def test_build_parse_export_xlsx_rejects_missing_result_file_path(
    tmp_path: Path, suffix: str
) -> None:
    result_path = tmp_path / f"parsed-bond_issuance{suffix}"

    with pytest.raises(ValueError, match="output_path must be a directory path"):
        build_parse_export_xlsx(str(result_path), "bond_issuance")

    assert not result_path.exists()


def test_build_parse_export_xlsx_latest_only_uses_family_reference_fields(
    tmp_path: Path,
) -> None:
    (tmp_path / "parsed-rights_issuance.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "rights_issuance",
                "parser_method": "rights_issuance",
                "families": {
                    "20240829000001": {
                        "members": [
                            {"sequence": 0, "acpt_no": "20240822000001"},
                            {"sequence": 1, "acpt_no": "20240829000001"},
                        ],
                    }
                },
                "records": [
                    {
                        "title": "유상증자결정",
                        "acpt_no": "20240822000001",
                        "family_id": "20240829000001",
                        "current_sequence": 0,
                        "family_member_count": 2,
                    },
                    {
                        "title": "[정정]유상증자결정",
                        "acpt_no": "20240829000001",
                        "family_id": "20240829000001",
                        "current_sequence": 1,
                        "family_member_count": 2,
                    },
                    {
                        "title": "유상증자결정",
                        "acpt_no": "20240901000001",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    xlsx_bytes = build_parse_export_xlsx(
        str(tmp_path), "rights_issuance", latest_only=True
    )

    with zipfile.ZipFile(BytesIO(xlsx_bytes)) as workbook:
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert "20240822000001" not in sheet_xml
    assert "20240829000001" in sheet_xml
    assert "20240901000001" in sheet_xml


def test_parse_disclosure_html_payload_stops_when_cancelled(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for index in range(2):
        _html_parse_file(viewer_dir, f"2025010100000{index}.html").write_text(
            "<html></html>", encoding="utf-8"
        )

    def fake_parser(html_text, *, file_path):
        cancel_disclosure_html_parse("parse-cancel-test")
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "security_transaction",
            "title": "",
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "parser_method": "security_transaction",
            "skip_errors": False,
            "cancel_token": "parse-cancel-test",
            "parallel_workers": 1,
        },
        progress_callback=progress_log.append,
    )

    assert payload["cancelled"] is True
    assert payload["summary"]["found_files"] == 2
    assert payload["summary"]["parsed_files"] == 1
    assert "progress_log" not in payload
    assert any("중지 요청" in line for line in progress_log)


def test_parse_disclosure_html_payload_records_failed_file_details(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    html_path = _html_parse_file(viewer_dir, "20250101000001.html")
    html_path.write_text("<html></html>", encoding="utf-8")
    output_path = tmp_path / "parsed-security_transaction.json"

    def fake_parser(html_text, *, file_path):
        raise RuntimeError("broken parser")

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "parser_method": "security_transaction",
            "skip_errors": True,
        },
        progress_callback=progress_log.append,
    )
    stored = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["summary"]["failed_files"] == 1
    assert payload["errors"] == [
        {
            "index": 1,
            "total": 1,
            "mode": "security_transaction",
            "acpt_no": "20250101000001",
            "error_type": "RuntimeError",
            "error": "broken parser",
        }
    ]
    assert "progress_log" not in payload
    assert any("20250101000001.html (RuntimeError) broken parser" in line for line in progress_log)
    assert stored["errors"] == payload["errors"]
    assert "progress_log" not in stored


def test_parse_disclosure_html_payload_rejects_missing_bond_condition_table(
    tmp_path: Path,
) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    html_path = _html_parse_file(viewer_dir, "20250101000001.html")
    html_path.write_text(
        """
        <html>
          <head><title>Different Disclosure Form</title></head>
          <body><p class="SECTION-1">Different Disclosure Form</p><table><tr><th>Field</th><td>Value</td></tr></table></body>
        </html>
        """,
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="bond issuance condition table is required"):
        parse_disclosure_html_payload(
            {
                "input_directory": str(viewer_dir),
                "output_directory": str(tmp_path),
                "mode": "bond_issuance",
                "parser_method": "bond_issuance",
                "skip_errors": False,
            }
        )


def test_parse_disclosure_html_payload_rejects_missing_rights_title(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    html_path = _html_parse_file(viewer_dir, "20250101000001.html")
    html_path.write_text(
        """
        <html>
          <head><title>Other Report</title></head>
          <body><table><tr><td>Field</td><td>Value</td></tr></table></body>
        </html>
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="rights issuance title is required"):
        parse_disclosure_html_payload(
            {
                "input_directory": str(viewer_dir),
                "output_directory": str(tmp_path),
                "mode": "rights_issuance",
                "parser_method": "rights_issuance",
                "skip_errors": False,
            }
        )


def test_parse_disclosure_html_payload_logs_success_progress_by_interval(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for index in range(3):
        _html_parse_file(viewer_dir, f"2025010100000{index}.html").write_text(
            "<html></html>", encoding="utf-8"
        )

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "security_transaction",
            "title": "",
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "parser_method": "security_transaction",
            "skip_errors": True,
            "progress_interval": 2,
        },
        progress_callback=progress_log.append,
    )

    assert "progress_log" not in payload
    assert not any("파싱 중 1/3:" in line for line in progress_log)
    assert not any("파싱 완료 1/3:" in line for line in progress_log)
    assert any("파싱 중간 확인: 이번 실행 2건 처리" in line for line in progress_log)


def test_parse_disclosure_html_payload_logs_interval_without_partial_saves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for index in range(3):
        _html_parse_file(viewer_dir, f"2025010100000{index}.html").write_text(
            "<html></html>", encoding="utf-8"
        )

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "security_transaction",
            "title": "",
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)
    progress_log: list[str] = []

    parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "parser_method": "security_transaction",
            "skip_errors": False,
            "progress_interval": 2,
        },
        progress_callback=progress_log.append,
    )

    assert "파싱 중간 확인: 이번 실행 2건 처리." in progress_log
    assert not any(
        line.startswith("파싱 중간 확인") and "결과 JSON 저장 완료" in line
        for line in progress_log
    )


def test_parse_disclosure_html_payload_defaults_progress_interval_to_1000(
    tmp_path: Path, monkeypatch
) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    _html_parse_file(viewer_dir, "20250101000001.html").write_text(
        "<html></html>", encoding="utf-8"
    )

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "security_transaction",
            "title": "",
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "parser_method": "security_transaction",
            "skip_errors": False,
        },
        progress_callback=progress_log.append,
    )

    assert "progress_log" not in payload
    assert "진행 확인 간격: 1000건" in progress_log


def test_parse_disclosure_html_payload_accepts_parallel_workers(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for index in range(3):
        _html_parse_file(viewer_dir, f"2025010100000{index}.html").write_text(
            "<html></html>", encoding="utf-8"
        )

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "security_transaction",
            "title": "",
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "parser_method": "security_transaction",
            "skip_errors": True,
            "progress_interval": 2,
            "parallel_workers": 2,
        },
        progress_callback=progress_log.append,
    )

    assert payload["summary"]["parsed_files"] == 3
    assert [record["acpt_no"] for record in payload["records"]] == [
        "20250101000000",
        "20250101000001",
        "20250101000002",
    ]
    assert "progress_log" not in payload
    assert "병렬 처리: 2개 워커" in progress_log
    assert any("파싱 중간 확인: 이번 실행 2건 처리" in line for line in progress_log)


def test_parse_disclosure_html_payload_reports_warning_counts_by_level(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    html_path = _html_parse_file(viewer_dir, "20250101000001.html")
    html_path.write_text("<html></html>", encoding="utf-8")

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "security_transaction",
            "title": "",
            "parse_warnings": ["weak warning", "medium warning", "strong warning"],
            "weak_warning": ["weak warning"],
            "medium_warning": ["medium warning"],
            "strong_warning": ["strong warning"],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "parser_method": "security_transaction",
            "skip_errors": False,
        }
    )

    assert [(item["warning"], item["level"]) for item in payload["warnings"]] == [
        ("weak warning", "weak_warning"),
        ("medium warning", "medium_warning"),
        ("strong warning", "strong_warning"),
    ]
    assert all("source_file" not in item for item in payload["warnings"])
    assert payload["warning_report_counts"] == {
        "count": 3,
        "report_count": 1,
        "weak_warning": {
            "count": 1,
            "report_count": 1,
            "reports": {
                "20250101000001": {
                    "count": 1,
                    "warnings": ["weak warning"],
                }
            },
        },
        "medium_warning": {
            "count": 1,
            "report_count": 1,
            "reports": {
                "20250101000001": {
                    "count": 1,
                    "warnings": ["medium warning"],
                }
            },
        },
        "strong_warning": {
            "count": 1,
            "report_count": 1,
            "reports": {
                "20250101000001": {
                    "count": 1,
                    "warnings": ["strong warning"],
                }
            },
        },
    }


@pytest.mark.parametrize("parallel_workers", [1, 2])
def test_parse_disclosure_html_payload_keeps_warnings_for_filtered_records(
    tmp_path: Path,
    monkeypatch,
    parallel_workers: int,
) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for name in ("20250101000001", "20250101000002", "20250101000003"):
        _html_parse_file(viewer_dir, f"{name}.html").write_text(
            "<html></html>", encoding="utf-8"
        )

    issue_methods = {
        "20250101000001": "공모",
        "20250101000002": "사모",
        "20250101000003": "",
    }

    def fake_parser(html_text, *, file_path):
        acpt_no = Path(file_path).stem
        return {
            "acpt_no": acpt_no,
            "mode": "security_transaction",
            "title": "",
            "사채발행방법": issue_methods[acpt_no],
            "parse_warnings": [f"{acpt_no} warning"],
            "medium_warning": [f"{acpt_no} warning"],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "parser_method": "security_transaction",
            "skip_errors": False,
            "parallel_workers": parallel_workers,
            "record_filters": [
                {"field": "사채발행방법", "operator": "in", "value": ["공모"]},
            ],
        },
        progress_callback=progress_log.append,
    )

    assert payload["summary"]["found_files"] == 3
    assert payload["summary"]["parsed_files"] == 1
    assert [record["acpt_no"] for record in payload["records"]] == ["20250101000001"]
    assert [warning["acpt_no"] for warning in payload["warnings"]] == [
        "20250101000001",
        "20250101000002",
        "20250101000003",
    ]
    assert payload["warning_report_counts"] == {
        "count": 3,
        "report_count": 3,
        "weak_warning": {"count": 0, "report_count": 0, "reports": {}},
        "medium_warning": {
            "count": 3,
            "report_count": 3,
            "reports": {
                "20250101000001": {
                    "count": 1,
                    "warnings": ["20250101000001 warning"],
                },
                "20250101000002": {
                    "count": 1,
                    "warnings": ["20250101000002 warning"],
                },
                "20250101000003": {
                    "count": 1,
                    "warnings": ["20250101000003 warning"],
                },
            },
        },
        "strong_warning": {"count": 0, "report_count": 0, "reports": {}},
    }
    assert payload["filter_settings"] == {
        "filter_blocks": [],
        "record_filters": [
            {"field": "사채발행방법", "operator": "in", "value": ["공모"]},
        ],
    }
    assert "progress_log" not in payload
    assert "필드 필터: 1개 조건 적용" in progress_log
    assert f"병렬 처리: {parallel_workers}개 워커" in progress_log


@pytest.mark.parametrize("parallel_workers", [1, 2])
def test_parse_disclosure_html_payload_discards_warnings_when_filter_fails(
    tmp_path: Path,
    monkeypatch,
    parallel_workers: int,
) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    acpt_numbers = ("20250101000001", "20250101000002")
    for acpt_no in acpt_numbers:
        _html_parse_file(viewer_dir, f"{acpt_no}.html").write_text(
            "<html></html>", encoding="utf-8"
        )

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "security_transaction",
            "title": "",
            "parse_warnings": ["warning"],
            "medium_warning": ["warning"],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    with pytest.raises(ValueError, match="operator is invalid"):
        parse_disclosure_html_payload(
            {
                "input_directory": str(viewer_dir),
                "output_directory": str(tmp_path),
                "mode": "security_transaction",
                "parser_method": "security_transaction",
                "parallel_workers": parallel_workers,
                "skip_errors": True,
                "filter_blocks": [
                    _filter_block(
                        field="title", operator="unsupported", value="x"
                    )
                ],
            }
        )


@pytest.mark.parametrize(
    "record",
    [
        {"parse_warnings": "warning"},
        {"parse_warnings": None},
        {"parse_warnings": []},
        {"weak_warning": []},
        {"parse_warnings": ["warning"]},
        {"weak_warning": ["warning"]},
        {"parse_warnings": [None], "weak_warning": [None]},
        {"parse_warnings": [1], "weak_warning": [1]},
        {"parse_warnings": ["warning"], "weak_warning": [" warning "]},
        {
            "parse_warnings": ["warning"],
            "weak_warning": ["warning"],
            "strong_warning": ["warning"],
        },
        {
            "parse_warnings": ["warning"],
            "weak_warning": ["warning"],
            "critical_warning": ["warning"],
        },
        {
            "parse_warnings": ["warning", "warning"],
            "weak_warning": ["warning"],
        },
    ],
)
def test_record_parse_warning_items_rejects_warning_contract_violations(
    record: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="warning contract violation"):
        _record_parse_warning_items(record)


def test_parse_disclosure_html_payload_applies_filter_blocks(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for name in ("20250101000001", "20250101000002", "20250101000003"):
        _html_parse_file(viewer_dir, f"{name}.html").write_text(
            "<html></html>", encoding="utf-8"
        )

    titles = {
        "20250101000001": "전환사채권발행결정",
        "20250101000002": "주주총회소집공고",
        "20250101000003": "유상증자결정",
    }

    def fake_parser(html_text, *, file_path):
        acpt_no = Path(file_path).stem
        return {
            "acpt_no": acpt_no,
            "mode": "security_transaction",
            "title": titles[acpt_no],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "parser_method": "security_transaction",
            "skip_errors": False,
            "parallel_workers": 2,
            "filter_blocks": [
                _filter_block(field="title", operator="contains", value="증자")
            ],
        },
        progress_callback=progress_log.append,
    )

    assert payload["summary"]["found_files"] == 3
    assert payload["summary"]["parsed_files"] == 1
    assert [record["acpt_no"] for record in payload["records"]] == ["20250101000003"]
    assert payload["filter_settings"] == {
        "filter_blocks": [
            _filter_block(field="title", operator="contains", value="증자")
        ],
        "record_filters": [],
    }
    assert "progress_log" not in payload
    assert "공시 조건: 1개 조건 적용" in progress_log


def test_parse_disclosure_html_payload_counts_serial_filter_exclusions_for_progress(
    tmp_path: Path, monkeypatch
) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for index in range(3):
        _html_parse_file(viewer_dir, f"2025010100000{index}.html").write_text(
            "<html></html>", encoding="utf-8"
        )

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "security_transaction",
            "title": "주주총회소집공고",
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "parser_method": "security_transaction",
            "skip_errors": True,
            "parallel_workers": 1,
            "progress_interval": 2,
            "filter_blocks": [
                _filter_block(field="title", operator="contains", value="증자")
            ],
        },
        progress_callback=progress_log.append,
    )

    assert payload["summary"]["found_files"] == 3
    assert payload["summary"]["parsed_files"] == 0
    assert "progress_log" not in payload
    assert any(
        "파싱 중간 확인: 이번 실행 2건 처리" in line
        for line in progress_log
    )


def test_build_parse_filter_candidates_payload_loads_bond_issue_methods(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for name, issue_method in (
        ("20250101000001", "공모"),
        ("20250101000002", "사모"),
        ("20250101000003", "공모"),
    ):
        _html_parse_file(viewer_dir, f"{name}.html").write_text(
            (
                "<table>"
                "<tr><td>사채의 종류</td><td>회차</td><td>1</td></tr>"
                "<tr><td>사채의 권면</td><td>총액</td><td>100</td></tr>"
                "<tr><td>자금조달의 목적</td><td>운영자금</td><td>100</td></tr>"
                f"<tr><td>사채발행방법</td><td>{issue_method}</td></tr>"
                "</table>"
            ),
            encoding="utf-8",
        )

    payload = build_parse_filter_candidates_payload(
        {
            "input_directory": str(viewer_dir),
            "mode": "bond_issuance",
            "parser_method": "bond_issuance",
            "field": "사채발행방법",
            "parallel_workers": 1,
        }
    )

    assert payload["format"] == "finiq_parse_filter_candidates_v1"
    assert payload["field"] == "사채발행방법"
    assert payload["summary"] == {"records": 3, "candidates": 2, "errors": 0}
    assert payload["candidates"] == [
        {
            "value": "공모",
            "count": 2,
            "examples": [
                {
                    "acpt_no": "20250101000001",
                },
                {
                    "acpt_no": "20250101000003",
                },
            ],
        },
        {
            "value": "사모",
            "count": 1,
            "examples": [
                {
                    "acpt_no": "20250101000002",
                },
            ],
        },
    ]


def test_build_parse_filter_candidates_payload_uses_parser_returned_value(
    tmp_path: Path, monkeypatch
) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    _html_parse_file(viewer_dir, "20250101000001.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    calls = []

    def fake_parser(html_text, *, file_path):
        calls.append(Path(file_path).name)
        return {"증자방식": "-"}

    monkeypatch.setitem(PARSER_REGISTRY, "rights_issuance", fake_parser)

    payload = build_parse_filter_candidates_payload(
        {
            "input_directory": str(viewer_dir),
            "mode": "rights_issuance",
            "parser_method": "rights_issuance",
            "field": "증자방식",
            "parallel_workers": 1,
        }
    )

    assert payload["summary"] == {"records": 1, "candidates": 1, "errors": 0}
    assert payload["candidates"][0]["value"] == "-"
    assert calls == ["20250101000001.html"]


def test_build_parse_filter_candidates_payload_loads_rights_issue_methods(
    tmp_path: Path,
) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    _html_parse_file(viewer_dir, "20250101000001.html").write_text(
        "<table>"
        "<tr><td>1. 신주의 종류와 수</td><td>보통주식</td><td>1</td></tr>"
        "<tr><td>5. 증자방식</td><td>제3자배정증자</td></tr>"
        "</table>",
        encoding="utf-8",
    )
    _html_parse_file(viewer_dir, "20250101000002.html").write_text(
        "<table>"
        "<tr><td>1. 신주의 종류와 수</td><td>보통주식</td><td>1</td></tr>"
        "<tr><td>5. 증자방식</td><td>일반공모증자</td></tr>"
        "</table>",
        encoding="utf-8",
    )
    _html_parse_file(viewer_dir, "20250101000003.html").write_text(
        "<table>"
        "<tr><td>1. 신주의 종류와 수</td><td>보통주식</td><td>1</td></tr>"
        "<tr><td>5. 증자방식</td><td>제3자배정증자</td></tr>"
        "</table>",
        encoding="utf-8",
    )
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": acpt_no,
                        "title": "유상증자결정",
                    }
                    for acpt_no in (
                        "20250101000001",
                        "20250101000002",
                        "20250101000003",
                    )
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_parse_filter_candidates_payload(
        {
            "input_directory": str(viewer_dir),
            "mode": "rights_issuance",
            "parser_method": "rights_issuance",
            "field": "증자방식",
            "parallel_workers": 1,
            **_html_parse_metadata_paths(compressed_path=compressed_path),
        }
    )

    assert payload["format"] == "finiq_parse_filter_candidates_v1"
    assert payload["field"] == "증자방식"
    assert payload["summary"] == {"records": 3, "candidates": 2, "errors": 0}
    assert payload["candidates"] == [
        {
            "value": "제3자배정증자",
            "count": 2,
            "examples": [
                {
                    "acpt_no": "20250101000001",
                },
                {
                    "acpt_no": "20250101000003",
                },
            ],
        },
        {
            "value": "일반공모증자",
            "count": 1,
            "examples": [
                {
                    "acpt_no": "20250101000002",
                },
            ],
        },
    ]


@pytest.mark.parametrize("parallel_workers", [1, 2])
def test_parse_disclosure_html_payload_does_not_save_partial_result_when_not_skipping(
    tmp_path: Path,
    monkeypatch,
    parallel_workers: int,
) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for acpt_no in ("20250101000001", "20250101000002"):
        _html_parse_file(viewer_dir, f"{acpt_no}.html").write_text(
            "<html></html>", encoding="utf-8"
        )
    output_path = tmp_path / "parsed-security_transaction.json"

    def fake_parser(html_text, *, file_path):
        if Path(file_path).stem == "20250101000002":
            raise RuntimeError("broken parser")
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "security_transaction",
            "title": "",
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    with pytest.raises(ValueError) as exc_info:
        parse_disclosure_html_payload(
            {
                "input_directory": str(viewer_dir),
                "output_directory": str(tmp_path),
                "mode": "security_transaction",
                "parser_method": "security_transaction",
                "skip_errors": False,
                "parallel_workers": parallel_workers,
                "progress_interval": 1,
            }
        )

    message = str(exc_info.value)
    assert "파싱 실패 2/2: 20250101000002.html" in message
    assert "(RuntimeError) broken parser" in message
    assert not output_path.exists()


def test_parse_disclosure_html_payload_applies_limit(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for index in range(3):
        _html_parse_file(viewer_dir, f"2025010100000{index}.html").write_text(
            "<html></html>", encoding="utf-8"
        )

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "shareholder_meeting",
            "parser_method": "shareholder_meeting",
            "skip_errors": False,
            "limit": 2,
        }
    )

    assert payload["summary"]["found_files"] == 2
    assert len(payload["records"]) == 2
    assert {record["mode"] for record in payload["records"]} == {"shareholder_meeting"}


def test_parse_disclosure_html_payload_uses_mode_registry(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    html_path = _html_parse_file(viewer_dir, "20250101000001.html")
    html_path.write_text("<html></html>", encoding="utf-8")
    called_paths: list[Path] = []

    def fake_parser(html_text, *, file_path):
        called_paths.append(Path(file_path))
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "security_transaction",
            "title": "",
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "parser_method": "security_transaction",
            "skip_errors": False,
        }
    )

    assert called_paths == [html_path]
    assert payload["records"][0]["acpt_no"] == html_path.stem


def test_html_parser_methods_payload_uses_the_parser_registry() -> None:
    methods = list_parser_methods_payload()["methods"]

    assert {method["key"] for method in methods} == EXPECTED_PARSE_MODES
    assert all(method["label"] and method["description"] for method in methods)


def test_html_parser_methods_are_registered_documented_and_loaded_dynamically() -> None:
    mode_docs = HTML_PARSE_MODES_DOC.read_text(encoding="utf-8")
    download_ui_html = GUI_EXTERNAL_HTML_DOWNLOAD_PAGE.read_text(encoding="utf-8")
    download_component_html = GUI_EXTERNAL_HTML_DOWNLOAD_COMPONENT.read_text(encoding="utf-8")
    internal_html_download_ui_html = GUI_INTERNAL_HTML_DOWNLOAD_PAGE.read_text(encoding="utf-8")
    section_split_page_html = GUI_HTML_SECTION_SPLIT_PAGE.read_text(encoding="utf-8")
    section_split_results_component_html = GUI_HTML_SECTION_SPLIT_RESULTS_COMPONENT.read_text(encoding="utf-8")
    section_split_ui_html = section_split_page_html + section_split_results_component_html
    parse_ui_html = GUI_HTML_PARSE_PAGE.read_text(encoding="utf-8")
    change_log_ui_html = GUI_HTML_CHANGE_LOG_PAGE.read_text(encoding="utf-8")
    utility_ui_html = GUI_UTILITY_PAGE.read_text(encoding="utf-8")

    assert set(PARSER_REGISTRY) == EXPECTED_PARSE_MODES
    for mode in EXPECTED_PARSE_MODES:
        assert mode.replace("_", "-") in mode_docs
        assert mode not in parse_ui_html
    assert "/api/disclosures/html/parse/methods" in parse_ui_html
    assert "/html-parse" in parse_ui_html
    assert "/internal-html-download" in parse_ui_html
    assert "공시원문 목차 분리" in section_split_ui_html
    assert "/api/disclosures/html/sections/list" in section_split_ui_html
    assert "/api/disclosures/html/sections/kinds" not in section_split_ui_html
    assert "/api/disclosures/html/sections/source" in section_split_ui_html
    assert "/api/disclosures/html/sections/source/split" in section_split_ui_html
    assert "/api/disclosures/html/sections/save/start" in section_split_ui_html
    assert "데이터 경로" in section_split_ui_html
    assert "작업 실행" in section_split_ui_html
    assert "소스 불러오기" in section_split_ui_html
    assert "FolderOpen" in section_split_ui_html
    assert "FolderOpen" not in section_split_page_html
    assert "FolderOpen" in section_split_results_component_html
    assert "소스 불러오기" in section_split_results_component_html
    assert "onInspectFolder={inspectFolder}" in section_split_page_html
    assert "소스 새로고침" not in section_split_ui_html
    assert "RefreshCw" not in section_split_ui_html
    assert "startSave" in section_split_ui_html
    assert "Play" in section_split_ui_html
    assert "저장 대상" in section_split_ui_html
    assert "누락 파일" in section_split_ui_html
    assert "UI_TEXT.actions.cancelJob" in section_split_ui_html
    assert "폴더 요약" not in section_split_ui_html
    assert "개별 공시" in section_split_ui_html
    assert "목차 수" in section_split_ui_html
    assert "목차 조합 모아보기" not in section_split_ui_html
    assert "sectionPatterns" not in section_split_ui_html
    assert "section_save_rules" not in section_split_ui_html
    assert "selectedPatternTocIds" not in section_split_ui_html
    assert "onTogglePatternSection" not in section_split_ui_html
    assert "저장할 목차" not in section_split_ui_html
    assert "limit: parseOptionalNumber(limit)" not in section_split_page_html
    assert "align-middle" in section_split_results_component_html
    assert "원문 보기" in section_split_ui_html
    assert "이전" in section_split_ui_html
    assert "다음" in section_split_ui_html
    assert "목차별 보기" in section_split_ui_html
    assert "reviewPanelRef" in section_split_results_component_html
    assert "scrollToReviewPanel" in section_split_results_component_html
    assert "inline-flex gap-1 rounded-md border border-slate-200 p-1 dark:border-[#30363d]" in section_split_results_component_html
    assert "activeReviewView === \"source\" ? \"default\" : \"ghost\"" in section_split_results_component_html
    assert "activeReviewView === \"sections\" ? \"default\" : \"ghost\"" in section_split_results_component_html
    assert "개별 공시에서 원문 보기 또는 목차별 보기를 선택하세요." in section_split_ui_html
    assert "이 공시의 목차 데이터를 아직 불러오지 못했습니다." in section_split_ui_html
    assert "onSplitSelected" not in section_split_ui_html
    assert "페이지에서 최대" not in section_split_ui_html
    assert "scrollIntoView" in section_split_ui_html
    assert "requestAnimationFrame" in section_split_ui_html
    assert "목차 저장" not in section_split_ui_html
    assert "목차 스캔" not in section_split_ui_html
    assert "문서별 목차" not in section_split_ui_html
    assert "문제 파일 표시 수" in section_split_ui_html
    assert "/api/disclosures/html/sections/preview" not in section_split_ui_html
    assert "/api/disclosures/html/sections/render" not in section_split_ui_html
    assert "첫 문서 목차" not in section_split_ui_html
    assert "목차 렌더링" not in section_split_ui_html
    assert "2026 샘플" not in section_split_ui_html
    assert "전체 목차 목록" not in section_split_ui_html
    assert "저장 대상 목차" not in section_split_ui_html
    assert "렌더링 문서" not in section_split_ui_html
    assert "공시원문 외부 저장" in download_component_html
    assert "공시원문 내부 저장" in download_component_html
    assert 'variant="internal"' in internal_html_download_ui_html
    assert "/api/disclosures/internal-html-download/start" in download_component_html
    assert "/api/disclosures/external-html-download/check-existing" in download_component_html
    assert "/api/disclosures/internal-html-download/check-existing" in download_component_html
    assert "externalTaskMode" in download_component_html
    assert "internalTaskMode" not in download_component_html
    assert "외부 HTML 저장" in download_component_html
    assert "외부 HTML 압축" in download_component_html
    assert "내부 HTML 병합" not in download_component_html
    assert "/api/disclosures/internal-html-download/merge/start" not in download_component_html
    assert "작업공간 디렉토리" in download_component_html
    assert "DATA_PATH_LABELS.output" not in download_component_html
    assert 'output_directory: ""' in download_component_html
    assert "압축 설정" not in download_component_html
    assert "압축 처리" in download_component_html
    assert "SETTINGS_LABELS.workerCount" in download_component_html
    assert "parallel_workers" in download_component_html
    assert "외부 HTML 압축 JSON 파일" not in download_component_html
    assert "외부 저장 화면의 외부 HTML 압축으로 만든 compressed-external-html.json 파일을 선택하세요." not in download_component_html
    assert "setExistingData(selectedResult || null)" in download_component_html
    assert "async function readJsonResponse" in download_component_html
    assert "const handleApplyExistingSettings = () => {" not in download_component_html
    assert "setDownloadSplitByYear(existingOutputSplitByYear)" not in download_component_html
    assert "저장 경로 분할저장을" not in download_component_html
    assert "detected_source_split_by_year !== internalSourceSplitByYear" not in download_component_html
    assert "SplitByYearButton" not in download_component_html
    assert "setDownloadSplitByYear" not in download_component_html
    assert "setInternalSourceSplitByYear" not in download_component_html
    assert "setCompressSplitByYear" not in download_component_html
    assert "setMergeSplitByYear" not in download_component_html
    assert "split_by_year" not in download_component_html
    assert "/api/utility/partition-storage/start" not in download_component_html
    assert "분할저장 구조 전환" not in download_component_html
    assert "/api/utility/partition-storage/start" in utility_ui_html
    assert "분할저장 구조 전환" in utility_ui_html
    assert "move: false" in utility_ui_html
    assert "기존 파일 덮어쓰기" not in download_component_html
    # The inspection verdict lives only in the integrity card; the data-path
    # card must not repeat it.
    assert "기존 원문 저장 범위 감지됨" not in download_component_html
    assert "allModeSaveInspectionData" in download_component_html
    assert "상위 필터에 없는 원문" in download_component_html
    assert "상위 필터에서 먼저 저장해야 합니다" in download_component_html
    assert "파생 필터에서는 다시 받을 수 없습니다." in download_component_html
    assert "const saveRedownloadable = showSaveWorkflow && saveRepairTargetCount > 0" in download_component_html
    assert "/api/disclosures/internal-html-download/redownload/start" in download_component_html
    assert "stepState={inspectionStepState}" in download_component_html
    inspection_card_html = (
        REPO_ROOT
        / "frontend"
        / "finiq_GUI"
        / "apps"
        / "market-desk"
        / "src"
        / "components"
        / "data-integrity"
        / "DataIntegrityInspectionCard.tsx"
    ).read_text(encoding="utf-8")
    assert "stepState?: SingleCheckDataIntegrityInspectionState" in inspection_card_html
    assert "never change the card verdict" not in inspection_card_html
    assert "isFileInspectionRunning || !hasCompletedFileInspection" in (
        GUI_APP_DIR / "download" / "page.tsx"
    ).read_text(encoding="utf-8")
    assert "기존 메타데이터 기준으로 설정 맞추기" not in download_component_html
    assert "기존 데이터 경로가 현재 필수 연도별 구조와 다릅니다" not in download_component_html
    assert "분할저장 On/Off를 맞춘 뒤" not in download_component_html
    assert "/html-change-log" in parse_ui_html
    assert "/html-bond-summary" in change_log_ui_html
    assert "변동 불러오기" in change_log_ui_html
    assert "/api/disclosures/html/parse/change-log" in change_log_ui_html
    assert "parseMode" not in download_ui_html
    assert "cancel_token" in parse_ui_html  # In React, we use cancel_token for cancellation


def test_expand_table_expands_rowspan_and_colspan() -> None:
    document = parse_html_document(
        """
        <html><body>
          <table>
            <tr><td rowspan="2">Group</td><td colspan="2">Header</td></tr>
            <tr><td>A</td><td>B</td></tr>
          </table>
        </body></html>
        """
    )

    grid = expand_table(document.xpath("//table")[0])

    assert [[slot["text"] for slot in row] for row in grid] == [
        ["Group", "Header", "Header"],
        ["Group", "A", "B"],
    ]
    assert grid[1][0]["from_span"] is True
    assert grid[0][1]["colspan"] == 2


def test_expand_table_expands_cell_with_rowspan_and_colspan() -> None:
    document = parse_html_document(
        """
        <html><body>
          <table>
            <tr><td rowspan="2" colspan="2">Group</td><td>First</td></tr>
            <tr><td>Second</td></tr>
          </table>
        </body></html>
        """
    )

    grid = expand_table(document.xpath("//table")[0])

    assert [[slot["text"] for slot in row] for row in grid] == [
        ["Group", "Group", "First"],
        ["Group", "Group", "Second"],
    ]
    assert grid[0][0]["rowspan"] == 2
    assert grid[0][0]["colspan"] == 2
    assert grid[1][0]["from_span"] is True
    assert grid[1][1]["from_span"] is True


def test_expand_table_defaults_missing_span_attributes_to_one() -> None:
    document = parse_html_document(
        """
        <html><body>
          <table>
            <tr><td>Label</td><td>Value</td></tr>
          </table>
        </body></html>
        """
    )

    grid = expand_table(document.xpath("//table")[0])

    assert grid[0][0]["rowspan"] == 1
    assert grid[0][0]["colspan"] == 1


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("rowspan", ""),
        ("rowspan", "abc"),
        ("rowspan", "0"),
        ("colspan", "2.0"),
        ("colspan", "-1"),
    ],
)
def test_expand_table_rejects_invalid_span_attributes(
    attribute: str, value: str
) -> None:
    document = parse_html_document(
        f"""
        <html><body>
          <table>
            <tr><td {attribute}="{value}">Broken</td></tr>
          </table>
        </body></html>
        """
    )

    with pytest.raises(ValueError, match=f"invalid {attribute}"):
        expand_table(document.xpath("//table")[0])


def test_parse_int_ignores_spaces_inside_comma_grouped_numbers() -> None:
    assert parse_int("4,000,000,00 0") == 4_000_000_000
    assert parse_int("13, 000,00 0,000") == 13_000_000_000


def test_parse_ints_keeps_adjacent_ungrouped_numbers_separate() -> None:
    assert parse_ints("100 100") == [100, 100]


@pytest.mark.parametrize(
    "numbered_label",
    [
        "1. 납입일",
        "1-1. 납입일",
        "1- 1. 납입일",
        "1 - 1 . 납입일",
        "I. 납입일",
        "II-II. 납입일",
        "Ⅰ. 납입일",
        "Ⅱ-Ⅱ. 납입일",
    ],
)
def test_row_with_label_accepts_one_or_two_level_number_prefixes(
    numbered_label: str,
) -> None:
    row = [numbered_label, "2025년 01월 02일"]

    assert row_with_label([row], "납입일") == row


def test_row_with_label_rejects_number_prefix_deeper_than_two_levels() -> None:
    matching_row = ["9. 납입일", "2025년 01월 02일"]

    assert row_with_label(
        [["1-1-1. 납입일", "잘못된 값"], matching_row], "납입일"
    ) == matching_row


@pytest.mark.parametrize(
    "marker",
    [
        "1. 유상증자",
        "I. 유상증자",
        "Ⅰ. 유상증자",
        "2. 무상증자",
        "II. 무상증자",
        "Ⅱ. 무상증자",
    ],
)
def test_rights_section_marker_accepts_arabic_and_roman_numbers(marker: str) -> None:
    assert _is_rights_section_marker_row([marker]) is True


def test_rights_section_marker_accepts_plain_label() -> None:
    assert _is_rights_section_marker_row(["유상증자"]) is True


def test_rights_section_marker_rejects_unsupported_number_prefix() -> None:
    assert _is_rights_section_marker_row(["1-1-1. 유상증자"]) is False


def test_parse_int_distinguishes_empty_source_from_explicit_dash_zero() -> None:
    assert parse_int("", dash_as_zero=True) is None
    assert parse_int(None, dash_as_zero=True) is None
    assert parse_int("-", dash_as_zero=True) == 0


@pytest.mark.parametrize(
    "filename", ["abc_def.html", "123_456.html", " report .html"]
)
def test_extract_acpt_no_uses_full_filename_stem(filename: str) -> None:
    assert extract_acpt_no(Path(filename)) == Path(filename).stem


def test_resolve_disclosure_html_file_uses_year_directory(tmp_path: Path) -> None:
    stem = "20250102000002"
    source_directory = tmp_path / "2025"
    source_directory.mkdir()
    source_path = source_directory / f"{stem}.html"
    source_path.write_text("<html></html>", encoding="utf-8")

    assert resolve_disclosure_html_file(tmp_path, stem) == source_path.resolve()


def test_resolve_disclosure_html_file_searches_actual_year_folder(tmp_path: Path) -> None:
    stem = "20250102000002"
    source_directory = tmp_path / "2024"
    source_directory.mkdir()
    source_path = source_directory / f"{stem}.html"
    source_path.write_text("<html></html>", encoding="utf-8")

    assert resolve_disclosure_html_file(tmp_path, stem) == source_path.resolve()


def test_collect_html_files_rejects_duplicate_full_stems(tmp_path: Path) -> None:
    first_year_directory = tmp_path / "2024"
    second_year_directory = tmp_path / "2025"
    first_year_directory.mkdir()
    second_year_directory.mkdir()
    (first_year_directory / "abc_def.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    (second_year_directory / "abc_def.html").write_text(
        "<html></html>", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="duplicate HTML filename stem: abc_def"):
        _collect_html_files(tmp_path, None)


def test_collect_html_files_uses_only_four_digit_year_directories(tmp_path: Path) -> None:
    root_html = tmp_path / "root.html"
    named_directory_html = tmp_path / "current" / "named.html"
    nested_html = tmp_path / "2025" / "nested" / "nested.html"
    visible = tmp_path / "2025" / "20250101000001.html"
    named_directory_html.parent.mkdir()
    nested_html.parent.mkdir(parents=True)
    for path in (root_html, named_directory_html, nested_html, visible):
        path.write_text("<html></html>", encoding="utf-8")

    assert _collect_html_files(tmp_path, None) == [visible.resolve()]


def test_collect_html_files_ignores_hidden_automation_directory(tmp_path: Path) -> None:
    visible = tmp_path / "2026" / "20260101000001.html"
    hidden = tmp_path / ".automation-current" / "20260101000002.html"
    visible.parent.mkdir()
    hidden.parent.mkdir()
    visible.write_text("<html></html>")
    hidden.write_text("<html></html>")

    assert _collect_html_files(tmp_path, None) == [visible.resolve()]


def test_metadata_title_lookup_uses_full_filename_stem() -> None:
    metadata_index = {
        "123": {"title": "prefix title"},
        "123_456": {"title": "full stem title"},
        " report ": {"title": "space-preserving title"},
    }

    assert (
        _metadata_title_for_file(Path("123_456.html"), metadata_index)
        == "full stem title"
    )
    assert (
        _metadata_title_for_file(Path(" report .html"), metadata_index)
        == "space-preserving title"
    )


def test_parse_disclosure_html_payload_rejects_empty_metadata_acpt_no(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "viewer_html"
    input_directory.mkdir()
    _html_parse_file(input_directory, " report .html", year="2025").write_text(
        "<html><body></body></html>", encoding="utf-8"
    )
    (tmp_path / "filtered.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "   ",
                        "company_name": "공백식별자회사",
                        "market": "코스닥",
                        "disclosed_at": "2025-01-02 09:00:00",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "compressed-external-html.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "   ",
                        "title": "전환사채권 발행결정",
                        "selected_main_doc_no": "20250102000011",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="acpt_no must not be empty"):
        parse_disclosure_html_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(tmp_path),
                "mode": "bond_issuance",
                "parser_method": "bond_issuance",
                "skip_errors": False,
                **_html_parse_metadata_paths(
                    filtered_path=tmp_path / "filtered.json"
                ),
            }
        )


def test_parse_bond_issuance_extracts_kind_sample_fields() -> None:
    fixture_path = TESTS_DIR / "fixtures" / "kind_bond_issuance_20260508000643.html"

    parsed = parse_bond_issuance(
        fixture_path.read_bytes(),
        file_path=fixture_path,
        title="전환사채권발행결정",
    )

    assert parsed["회차"] == "16"
    assert parsed["종류"] == "CB"
    assert parsed["발행금액"] == 40_000_000_000
    assert parsed["field_parse_status"]["발행금액"] == "parsed"
    assert parsed["field_parse_status"]["발행목적"] == "parsed"
    assert parsed["field_parse_status"]["투자자"] == "parsed"
    assert parsed["발행목적"] == [
        ["운영자금", 8_000_000_000],
        ["채무상환자금", 32_000_000_000],
    ]
    assert parsed["상장구분"] is None
    assert parsed["만기일"] == "2031년 05월 08일"
    assert parsed["사채발행방법"] == "사모"
    assert parsed["행사가액"] == 54_315
    assert parsed["기업명(행사대상)"] == "주식회사 아이티센글로벌 기명식 보통주"
    assert parsed["행사시작일"] == "2027년 05월 08일"
    assert parsed["행사종료일"] == "2031년 04월 29일"
    assert parsed["납입일"] == "2026년 05월 08일"
    assert parsed["투자자"] == [["아이티씨홀딩스(유)", 40_000_000_000]]
    assert "발행대상자세부엔티티" not in parsed
    for removed_field in (
        "할증률(%)",
        "행사대상",
        "전환시작일",
        "전환종료일",
        "리픽싱(%)",
        "청약일",
        "납입방법",
    ):
        assert removed_field not in parsed


@pytest.mark.parametrize(
    ("acpt_no", "expected_issue_amount", "expected_purposes"),
    [
        (
            "20190315001473",
            4_000_000_000,
            [
                ["운영자금", 4_000_000_000],
            ],
        ),
        (
            "20210201001008",
            9_000_000_000,
            [
                ["시설자금", 4_500_000_000],
                ["운영자금", 4_500_000_000],
            ],
        ),
        (
            "20210208001133",
            9_000_000_000,
            [
                ["시설자금", 4_500_000_000],
                ["운영자금", 4_500_000_000],
            ],
        ),
        (
            "20210331002135",
            13_000_000_000,
            [
                ["운영자금", 13_000_000_000],
            ],
        ),
        (
            "20221115000002",
            13_000_000_000,
            [
                ["타법인 증권 취득자금", 13_000_000_000],
            ],
        ),
        (
            "20250407001007",
            4_500_000_000,
            [
                ["운영자금", 4_500_000_000],
            ],
        ),
        (
            "20250724000675",
            5_001_000_000,
            [
                ["운영자금", 4_001_000_000],
                ["채무상환자금", 1_000_000_000],
            ],
        ),
    ],
)
@pytest.mark.skipif(not HAS_KIND_RESOURCES, reason="Local KIND resources are absent")
def test_parse_bond_issuance_reads_split_span_amounts_without_sum_warning(
    acpt_no: str, expected_issue_amount: int, expected_purposes: list[list[object]]
) -> None:
    fixture_path = (
        REPO_ROOT
        / "resources"
        / "KIND"
        / "bond_issuance"
        / "kind_html_contents_grouped_sections"
        / acpt_no[:4]
        / f"{acpt_no}.html"
    )

    parsed = parse_bond_issuance(fixture_path.read_bytes(), file_path=fixture_path)

    assert parsed["발행금액"] == expected_issue_amount
    assert parsed["발행목적"] == expected_purposes
    assert not any(
        "자금조달 목적 합계" in warning
        for warning in parsed.get("parse_warnings", [])
    )


def test_parse_bond_issuance_rejects_html_without_condition_table(
    tmp_path: Path,
) -> None:
    wrapper_path = tmp_path / "20080826000187.html"
    wrapper_html = """
    <html>
      <head><title>[에스브이에이치] [정정]전환사채발행결정</title></head>
      <body>
        <select id="mainDoc">
          <option value="00000000867311|N">전환사채발행결정 (2008.08.18)</option>
          <option value="20080826000555|N" selected="selected">[정정]전환사채발행결정 (2008.08.26)</option>
        </select>
      </body>
    </html>
    """

    with pytest.raises(ValueError, match="bond issuance condition table is required"):
        parse_bond_issuance(wrapper_html.encode("utf-8"), file_path=wrapper_path)


def test_parse_bond_issuance_uses_supplied_title_for_security_type(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000008.html"
    body_html = """
    <html><body>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>1</td><td>종류</td><td>무기명식 무보증 전환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>1,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>1,000,000,000</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="[테스트] 전환사채권 발행결정",
    )

    assert parsed["title"] == "[테스트] 전환사채권 발행결정"
    assert parsed["종류"] == "CB"
    assert parsed["field_parse_status"]["종류"] == "parsed"
    assert not any(
        warning.startswith("종류: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed["parse_warnings"]
    )


def test_parse_disclosure_html_payload_injects_compressed_title_for_bond_parser(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    html_path = _html_parse_file(input_dir, "20250102000009.html")
    html_path.write_text(
        """
        <html><body>
          <table>
            <tr><td>1. 사채의 종류</td><td>회차</td><td>2</td><td>종류</td><td>무기명식 무보증 교환사채</td></tr>
            <tr><td>2. 사채의 권면총액 (원)</td><td>2,000,000,000</td></tr>
            <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>2,000,000,000</td></tr>
          </table>
        </body></html>
        """,
        encoding="utf-8",
    )
    (tmp_path / "filtered.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20250102000009",
                        "company_name": "테스트회사",
                        "market": "코스닥",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "compressed-external-html.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20250102000009",
                        "title": "[테스트] 교환사채권 발행결정",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = parse_disclosure_html_payload(
        {
            "mode": "bond_issuance",
            "parser_method": "bond_issuance",
            "skip_errors": False,
            "input_directory": str(input_dir),
            "output_directory": str(output_dir),
            **_html_parse_metadata_paths(
                filtered_path=tmp_path / "filtered.json",
                compressed_path=tmp_path / "compressed-external-html.json",
            ),
        }
    )

    assert payload["summary"]["parsed_files"] == 1
    record = payload["records"][0]
    assert record["title"] == "[테스트] 교환사채권 발행결정"
    assert record["종류"] == "EB"
    assert record["corp_name"] == "테스트회사"
    assert record["상장구분"] == "코스닥"
    assert not any(
        warning["warning"].startswith("종류: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in payload["warnings"]
    )


def test_parse_disclosure_html_payload_injects_company_name_for_shareholder_parser(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    html_path = _html_parse_file(input_dir, "20250102000013.html")
    html_path.write_text(
        """
        <html><body>
          <span>이사선임 세부내역</span>
          <table>
            <tr><th>성명</th><th>주요경력(현직포함)</th></tr>
            <tr><td>김현재</td><td>현) 보고회사 대표이사</td></tr>
          </table>
        </body></html>
        """,
        encoding="utf-8",
    )
    (tmp_path / "filtered.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20250102000013",
                        "company_name": "보고회사",
                        "market": "코스닥",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "compressed-external-html.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20250102000013",
                        "title": "[보고회사] 정기주주총회소집결의",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = parse_disclosure_html_payload(
        {
            "mode": "shareholder_meeting",
            "parser_method": "shareholder_meeting",
            "skip_errors": False,
            "input_directory": str(input_dir),
            "output_directory": str(output_dir),
            **_html_parse_metadata_paths(
                filtered_path=tmp_path / "filtered.json",
                compressed_path=tmp_path / "compressed-external-html.json",
            ),
        }
    )

    record = payload["records"][0]
    assert record["disclosure_phase"] == "notice"
    assert not any(
        entity["entity_type"] == "organization"
        for entity in record["entities"]
    )
    assert [
        relation["target_ref"]
        for relation in record["relationships"]
        if relation["relationship_type"] == "serves_at"
    ] == ["@reporting_company"]


def test_parse_disclosure_html_payload_does_not_recover_title_after_parser(
    tmp_path: Path, monkeypatch
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    html_path = _html_parse_file(input_dir, "20250102000012.html")
    html_path.write_text("<html><body></body></html>", encoding="utf-8")
    (tmp_path / "compressed-external-html.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20250102000012",
                        "title": "[테스트] 전환사채권 발행결정",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def parser_ignoring_title(html_text, *, file_path, title=None):
        return {
            "acpt_no": Path(file_path).stem,
            "mode": "bond_issuance",
            "title": "",
            "상장구분": None,
        }

    monkeypatch.setitem(PARSER_REGISTRY, "bond_issuance", parser_ignoring_title)

    payload = parse_disclosure_html_payload(
        {
            "mode": "bond_issuance",
            "parser_method": "bond_issuance",
            "skip_errors": False,
            "input_directory": str(input_dir),
            "output_directory": str(output_dir),
            **_html_parse_metadata_paths(
                compressed_path=tmp_path / "compressed-external-html.json"
            ),
        }
    )

    assert payload["records"][0]["title"] == ""


def test_parse_rights_issuance_uses_supplied_title_for_issuance_type(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000010.html"
    body_html = """
    <html><body>
      <table>
        <tr><td>1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>10</td></tr>
        <tr><td>5. 증자방식</td><td>무상증자</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="[테스트] 무상증자결정",
    )

    assert parsed["title"] == "[테스트] 무상증자결정"
    assert "correction_families" not in parsed
    assert "raw_rows" not in parsed
    assert parsed["증자유형"] == "무상증자"
    assert parsed["발행목적"] == "-"
    assert parsed["발행가액"] == "-"
    assert parsed["증자방식"] == "-"
    assert parsed["납입일"] == "-"
    assert parsed["발행대상자"] == "-"
    assert parsed["유상증자"] is None
    assert parsed["무상증자"] is not None
    assert parsed["field_parse_status"]["발행목적"] == "not_applicable"
    assert parsed["field_parse_status"]["발행가액"] == "not_applicable"
    assert parsed["field_parse_status"]["증자방식"] == "not_applicable"
    assert parsed["field_parse_status"]["납입일"] == "not_applicable"
    assert parsed["field_parse_status"]["발행대상자"] == "not_applicable"
    assert "기준주가" not in parsed
    assert "기준주가" not in parsed["field_parse_status"]
    assert "주입 제목에서 유상증자/무상증자 유형을 확인하지 못했습니다." not in (
        parsed.get("strong_warning") or []
    )


def test_parse_disclosure_html_payload_injects_compressed_title_for_rights_parser(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    html_path = _html_parse_file(input_dir, "20250102000011.html")
    html_path.write_text(
        """
        <html><body>
          <table>
            <tr><td>1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>20</td></tr>
            <tr><td>5. 증자방식</td><td>주주배정후 실권주 일반공모</td></tr>
          </table>
        </body></html>
        """,
        encoding="utf-8",
    )
    (tmp_path / "filtered.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20250102000011",
                        "company_name": "테스트회사",
                        "market": "코스닥",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "compressed-external-html.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20250102000011",
                        "title": "[테스트] 유상증자결정",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = parse_disclosure_html_payload(
        {
            "mode": "rights_issuance",
            "parser_method": "rights_issuance",
            "skip_errors": False,
            "input_directory": str(input_dir),
            "output_directory": str(output_dir),
            **_html_parse_metadata_paths(
                filtered_path=tmp_path / "filtered.json",
                compressed_path=tmp_path / "compressed-external-html.json",
            ),
        }
    )

    assert payload["summary"]["parsed_files"] == 1
    record = payload["records"][0]
    assert record["title"] == "[테스트] 유상증자결정"
    assert record["corp_name"] == "테스트회사"
    assert record["상장구분"] == "코스닥"
    assert "상장시장" not in record
    assert record["증자유형"] == "유상증자"
    assert record["유상증자"] is not None
    assert record["무상증자"] is None
    assert not any(
        "주입 제목에서 유상증자/무상증자 유형을 확인하지 못했습니다."
        in warning["warning"]
        for warning in payload["warnings"]
    )


def test_parse_bond_issuance_warns_when_required_detail_tables_are_absent(tmp_path: Path) -> None:
    fixture_path = tmp_path / "20250102000002.html"
    body_html = """
    <html><body>
      <h2 class="SECTION-1" id="toc_2"></h2><p class="SECTION-1">교환사채권 발행결정</p>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>2</td><td>종류</td><td>무기명식 무보증 교환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>5,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>5,000,000,000</td></tr>
        <tr><td>5. 사채만기일</td><td>2028년 01월 02일</td></tr>
        <tr><td>8. 사채발행방법</td><td>사모</td></tr>
        <tr><td>9. 교환에 관한 사항</td><td>교환가액 (원/주)</td><td>12,500</td></tr>
        <tr><td>9. 교환에 관한 사항</td><td>교환대상</td><td>주식회사 테스트타겟 기명식 보통주</td></tr>
        <tr><td>9. 교환에 관한 사항</td><td>교환청구기간</td><td>시작일</td><td>2026년 01월 02일</td></tr>
        <tr><td>9. 교환에 관한 사항</td><td>교환청구기간</td><td>종료일</td><td>2027년 12월 02일</td></tr>
        <tr><td>12. 납입일</td><td>2025년 01월 02일</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="교환사채권 발행결정",
    )

    assert parsed["회차"] == "2"
    assert parsed["종류"] == "EB"
    assert parsed["기업명(행사대상)"] == "주식회사 테스트타겟 기명식 보통주"
    assert parsed["발행금액"] == 5_000_000_000
    assert parsed["발행목적"] == [["운영자금", 5_000_000_000]]
    assert parsed["field_parse_status"]["투자자"] == "source_not_found"
    assert parsed["행사가액"] == 12_500
    assert parsed["납입일"] == "2025년 01월 02일"
    assert parsed["만기일"] == "2028년 01월 02일"
    assert parsed["사채발행방법"] == "사모"
    assert parsed["행사시작일"] == "2026년 01월 02일"
    assert parsed["행사종료일"] == "2027년 12월 02일"
    assert parsed["투자자"] is None
    assert any(
        warning.startswith("투자자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed["parse_warnings"]
    )
    assert (
        "사채 발행 투자자 표를 찾지 못했습니다. HTML 양식이 예상과 달라 투자자 필드가 비어 있을 수 있습니다."
        in parsed["strong_warning"]
    )
    assert not any("발행대상자세부엔티티" in warning for warning in parsed["parse_warnings"])


def test_parse_bond_issuance_saves_empty_source_cells_as_null_with_strong_warnings(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000031.html"
    body_html = """
    <html><body>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td></td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td></td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td></td></tr>
        <tr><td>5. 사채만기일</td><td></td></tr>
      </table>
      <table>
        <tr><th>발행 대상자명</th><th>발행권면총액 (원)</th></tr>
        <tr><td>테스트조합</td><td></td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["회차"] is None
    assert parsed["발행금액"] is None
    assert parsed["발행목적"] is None
    assert parsed["만기일"] is None
    assert parsed["투자자"] is None
    for field_name in ("회차", "발행금액", "발행목적", "만기일", "투자자"):
        assert parsed["field_parse_status"][field_name] == "source_not_found"
        assert any(
            warning.startswith(
                f"{field_name}: 정해진 출처에서 값을 찾지 못했습니다."
            )
            for warning in parsed["strong_warning"]
        )


def test_parse_bond_issuance_keeps_investor_name_when_amount_is_dash(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000007.html"
    body_html = """
    <html><body>
      <h2 class="SECTION-1" id="toc_2"></h2><p class="SECTION-1">전환사채권 발행결정</p>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>3</td><td>종류</td><td>무기명식 무보증 전환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>5,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>5,000,000,000</td></tr>
      </table>
      <table>
        <tr><th>발행 대상자명</th><th>회사 또는 최대주주와의 관계</th><th>발행권면총액 (원)</th></tr>
        <tr><td>테스트조합</td><td>해당사항 없음</td><td>-</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["투자자"] == [["테스트조합", 0]]
    assert parsed["field_parse_status"]["투자자"] == "parsed"
    assert not any(
        warning.startswith("투자자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed["parse_warnings"]
    )
    assert not any(
        warning.startswith("사채 발행 투자자 표를 찾지 못했습니다.")
        for warning in parsed["parse_warnings"]
    )


def test_parse_bond_issuance_reads_investor_amount_from_face_value_column(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000008.html"
    body_html = """
    <html><body>
      <h2 class="SECTION-1" id="toc_2"></h2><p class="SECTION-1">전환사채권 발행결정</p>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>3</td><td>종류</td><td>무기명식 무보증 전환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>5,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>5,000,000,000</td></tr>
      </table>
      <table>
        <tr><th>발행 대상자명</th><th>회사 또는 최대주주와의 관계</th><th>발행권면총액 (원)</th><th>비고</th></tr>
        <tr><td>테스트조합</td><td>2대주주</td><td>5,000,000,000</td><td>1</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["투자자"] == [["테스트조합", 5_000_000_000]]
    assert not any("발행권면총액 합계" in warning for warning in parsed.get("weak_warning", []))


def test_parse_bond_issuance_warns_when_funding_purpose_sum_differs(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000006.html"
    body_html = """
    <html><body>
      <h2 class="SECTION-1" id="toc_2"></h2><p class="SECTION-1">전환사채권 발행결정</p>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>3</td><td>종류</td><td>무기명식 무보증 전환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>5,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>연구개발자금 (원)</td><td>3,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>해외인수자금 (원)</td><td>1,000,000,000</td></tr>
        <tr><td>5. 사채만기일</td><td>2028년 01월 02일</td></tr>
        <tr><td>8. 사채발행방법</td><td>사모</td></tr>
        <tr><td>9. 전환에 관한 사항</td><td>전환가액 (원/주)</td><td>12,500</td></tr>
        <tr><td>9. 전환에 관한 사항</td><td>전환청구기간</td><td>시작일</td><td>2026년 01월 02일</td></tr>
        <tr><td>9. 전환에 관한 사항</td><td>전환청구기간</td><td>종료일</td><td>2027년 12월 02일</td></tr>
        <tr><td>12. 납입일</td><td>2025년 01월 02일</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["발행목적"] == [
        ["연구개발자금", 3_000_000_000],
        ["해외인수자금", 1_000_000_000],
    ]
    assert any(
        warning
        == "발행목적: 자금조달 목적 합계(4,000,000,000)가 발행금액(5,000,000,000)과 일치하지 않습니다."
        for warning in parsed["weak_warning"]
    )


def test_parse_bond_issuance_warns_when_investor_sum_differs(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000009.html"
    body_html = """
    <html><body>
      <h2 class="SECTION-1" id="toc_2"></h2><p class="SECTION-1">전환사채권 발행결정</p>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>3</td><td>종류</td><td>무기명식 무보증 전환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>5,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>5,000,000,000</td></tr>
      </table>
      <table>
        <tr><th>발행 대상자명</th><th>발행권면총액 (원)</th></tr>
        <tr><td>테스트조합</td><td>4,000,000,000</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["투자자"] == [["테스트조합", 4_000_000_000]]
    assert any(
        warning
        == "투자자: 발행권면총액 합계(4,000,000,000)가 발행금액(5,000,000,000)과 일치하지 않습니다."
        for warning in parsed["weak_warning"]
    )


def test_parse_bond_issuance_reads_dash_issue_amount_as_zero(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20090720000320.html"
    body_html = """
    <html><body>
      <h2 class="SECTION-1" id="toc_2"></h2><p class="SECTION-1">전환사채권 발행결정</p>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>-</td><td>종류</td><td>-</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>-</td></tr>
        <tr><td>2-1 (해외발행)</td><td>권면총액 (통화단위)</td><td>-</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>시설자금 (원)</td><td>-</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>-</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>타법인 증권 취득자금 (원)</td><td>-</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>기타자금 (원)</td><td>-</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["발행금액"] == 0
    assert parsed["발행목적"] == []
    assert parsed["field_parse_status"]["발행금액"] == "explicit_zero"
    assert parsed["field_parse_status"]["발행목적"] == "explicit_zero"
    assert not any("발행금액" in warning for warning in parsed["parse_warnings"])
    assert not any("발행목적" in warning for warning in parsed["parse_warnings"])
    assert not any(
        "자금조달 목적 합계" in warning for warning in parsed["parse_warnings"]
    )


@pytest.mark.skipif(not HAS_KIND_RESOURCES, reason="Local KIND resources are absent")
def test_parse_bond_issuance_reads_resource_dash_issue_amount_as_zero() -> None:
    fixture_path = (
        REPO_ROOT
        / "resources"
        / "KIND"
        / "bond_issuance"
        / "kind_html_contents_grouped_sections"
        / "2009"
        / "20090720000320.html"
    )

    parsed = parse_bond_issuance(fixture_path.read_bytes(), file_path=fixture_path)

    assert parsed["발행금액"] == 0
    assert not any("발행금액" in warning for warning in parsed.get("parse_warnings", []))


def test_parse_bond_issuance_preserves_standalone_stock_suffix_in_target_company(tmp_path: Path) -> None:
    fixture_path = tmp_path / "20250102000003.html"
    body_html = """
    <html><body>
      <h2 class="SECTION-1" id="toc_2"></h2><p class="SECTION-1">교환사채권 발행결정</p>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>2</td><td>종류</td><td>무기명식 무보증 교환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>5,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>5,000,000,000</td></tr>
        <tr><td>5. 사채만기일</td><td>2028년 01월 02일</td></tr>
        <tr><td>9. 교환에 관한 사항</td><td>교환가액 (원/주)</td><td>12,500</td></tr>
        <tr><td>9. 교환에 관한 사항</td><td>교환대상</td><td>테스트타겟 주식</td></tr>
        <tr><td>9. 교환에 관한 사항</td><td>교환청구기간</td><td>시작일</td><td>2026년 01월 02일</td></tr>
        <tr><td>9. 교환에 관한 사항</td><td>교환청구기간</td><td>종료일</td><td>2027년 12월 02일</td></tr>
        <tr><td>12. 납입일</td><td>2025년 01월 02일</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["기업명(행사대상)"] == "테스트타겟 주식"


def test_parse_bond_issuance_preserves_stock_word_inside_target_company(tmp_path: Path) -> None:
    fixture_path = tmp_path / "20250102000013.html"
    body_html = """
    <html><body>
      <h2 class="SECTION-1" id="toc_2"></h2><p class="SECTION-1">교환사채권 발행결정</p>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>2</td><td>종류</td><td>무기명식 무보증 교환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>5,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>5,000,000,000</td></tr>
        <tr><td>5. 사채만기일</td><td>2028년 01월 02일</td></tr>
        <tr><td>9. 교환에 관한 사항</td><td>교환가액 (원/주)</td><td>12,500</td></tr>
        <tr><td>9. 교환에 관한 사항</td><td>교환대상</td><td>맛있는주식 주식회사 기명식 보통주</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["기업명(행사대상)"] == "맛있는주식 주식회사 기명식 보통주"


def test_parse_bond_issuance_does_not_read_legacy_section_title_anchor(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20081118000345.html"
    body_html = """
    <html><body>
      <p class="SECTION-1"><a name="#119">신주인수권부사채 발행결정</a></p>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>1</td><td>종류</td><td>무보증신주인수권부사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>3,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>3,000,000,000</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["title"] == ""
    assert parsed["종류"] is None
    assert "주입 제목이 없습니다." in parsed["strong_warning"]
    assert "주입 제목이 없습니다." in parsed["parse_warnings"]


def test_parse_bond_issuance_maps_legacy_conversion_target_and_refixing(tmp_path: Path) -> None:
    fixture_path = tmp_path / "20090506000331.html"
    body_html = """
    <html><body>
      <h2 class="SECTION-1"><p class="SECTION-1">전환사채발행결정</p></h2>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>3</td><td>종류</td><td>무기명식 무보증 전환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>1,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>1,000,000,000</td></tr>
        <tr><td>9. 전환에 관한 사항</td><td>전환가액 (원/주)</td><td>500</td></tr>
        <tr><td>9. 전환에 관한 사항</td><td>전환에 따라 발행할 주식</td><td>종류</td><td>(주)아이에스이커머스 기명식 보통주</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="전환사채발행결정",
    )

    assert parsed["기업명(행사대상)"] == "(주)아이에스이커머스 기명식 보통주"


@pytest.mark.parametrize(
    ("acpt_no", "body_html", "expected"),
    [
        (
            "20080825000412",
            """
            <html><body>
              <h2 class="SECTION-1"><p class="SECTION-1">신주인수권부사채발행결정</p></h2>
              <table>
                <tr><td>1. 사채의 종류</td><td>회차</td><td>5</td><td>종류</td><td>무기명식 무보증 해외 신주인수권부사채</td></tr>
                <tr><td>2. 사채의 권면총액 (원)</td><td>10,515,000,000</td></tr>
                <tr><td>3. 자금조달의 목적</td><td>기타자금 (원)</td><td>10,515,000,000</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>행사가액 (원/주)</td><td>730</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>신주대금 납입방법</td><td>현금납입 또는 사채대용납입</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>인수권행사에 따라 발행할 주식의 종류</td><td>기명식 보통주</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>권리행사기간</td><td>시작일</td><td>2009년 08월 29일</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>권리행사기간</td><td>종료일</td><td>2011년 07월 29일</td></tr>
              </table>
              <p>신주인수권행사가액의 조정에 관한 사항. 행사가액은 최초행사가액의 70%를 하회할 수 없음. 최저조정가액비율 : 70%</p>
            </body></html>
            """,
            {
                "종류": "BW",
                "행사가액": 730,
                "기업명(행사대상)": "기명식 보통주",
                "행사시작일": "2009년 08월 29일",
                "행사종료일": "2011년 07월 29일",
            },
        ),
        (
            "20080826000146",
            """
            <html><body>
              <h2 class="SECTION-1"><p class="SECTION-1">신주인수권부사채발행결정</p></h2>
              <table>
                <tr><td>1. 사채의 종류</td><td>회차</td><td>2</td><td>종류</td><td>무기명식 무보증 신주인수권부사채</td></tr>
                <tr><td>2. 사채의 권면총액 (원)</td><td>3,000,000,000</td></tr>
                <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>3,000,000,000</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>행사가액 (원/주)</td><td>848</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>신주대금 납입방법</td><td>현금 및 대용</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>인수권행사에 따라 발행할 주식의 종류</td><td>기명식 보통주</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>권리행사기간</td><td>시작일</td><td>2009년 08월 26일</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>권리행사기간</td><td>종료일</td><td>2011년 08월 26일</td></tr>
              </table>
              <p>신주인수권 행사가액 조정 등. 행사가액 조정한도는 발행 당시의 행사가액의 70%이상에 해당하는 가액으로 한다.</p>
            </body></html>
            """,
            {
                "종류": "BW",
                "행사가액": 848,
                "기업명(행사대상)": "기명식 보통주",
                "행사시작일": "2009년 08월 26일",
                "행사종료일": "2011년 08월 26일",
            },
        ),
        (
            "20080826000267",
            """
            <html><body>
              <h2 class="SECTION-1"><p class="SECTION-1">신주인수권부사채발행결정</p></h2>
              <table>
                <tr><td>1. 사채의 종류</td><td>회차</td><td>7-1</td><td>종류</td><td>무기명식 이권부 무보증 신주인수권부사채</td></tr>
                <tr><td>2. 사채의 권면총액 (원)</td><td>6,000,000,000</td></tr>
                <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>2,000,000,000</td></tr>
                <tr><td>3. 자금조달의 목적</td><td>기타자금 (원)</td><td>4,000,000,000</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>행사가액 (원/주)</td><td>1,035</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>신주대금 납입방법</td><td>현금납입 또는 사채대용납입</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>인수권행사에 따라 발행할 주식의 종류</td><td>기명식 보통주</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>권리행사기간</td><td>시작일</td><td>2008년 10월 08일</td></tr>
                <tr><td>9. 신주인수권에 관한 사항</td><td>권리행사기간</td><td>종료일</td><td>2010년 08월 08일</td></tr>
              </table>
              <p>행사가액 조정에 관한 사항. 매 3개월마다 산정한 가액이 행사가액에 미달하는 경우 최초 발행당시 산정한 행사가액에 70%를 한도까지로 하여 행사가액을 조정한다.</p>
            </body></html>
            """,
            {
                "종류": "BW",
                "행사가액": 1035,
                "기업명(행사대상)": "기명식 보통주",
                "행사시작일": "2008년 10월 08일",
                "행사종료일": "2010년 08월 08일",
            },
        ),
        (
            "20080826000499",
            """
            <html><body>
              <h2 class="SECTION-1"><p class="SECTION-1">교환사채발행결정</p></h2>
              <table>
                <tr><td>1. 사채의 종류</td><td>회차</td><td>1</td><td>종류</td><td>무기명식 무보증 교환사채</td></tr>
                <tr><td>2. 사채의 권면총액 (원)</td><td>5,000,000,000</td></tr>
                <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>5,000,000,000</td></tr>
                <tr><td>9. 교환에 관한 사항</td><td>교환가액 (원/주)</td><td>12,500</td></tr>
                <tr><td>9. 교환에 관한 사항</td><td>교환대상 주식의 종류</td><td>주식회사 테스트타겟 기명식 보통주</td></tr>
                <tr><td>9. 교환에 관한 사항</td><td>교환청구기간</td><td>시작일</td><td>2026년 01월 01일</td></tr>
                <tr><td>9. 교환에 관한 사항</td><td>교환청구기간</td><td>종료일</td><td>2028년 01월 01일</td></tr>
              </table>
            </body></html>
            """,
            {
                "종류": "EB",
                "행사가액": 12500,
                "기업명(행사대상)": "주식회사 테스트타겟 기명식 보통주",
                "행사시작일": "2026년 01월 01일",
                "행사종료일": "2028년 01월 01일",
            },
        ),
    ],
)
def test_parse_bond_issuance_maps_kind_warrant_resource_examples(
    tmp_path: Path, acpt_no: str, body_html: str, expected: dict[str, object]
) -> None:
    fixture_path = tmp_path / f"{acpt_no}.html"

    title_by_type = {
        "BW": "신주인수권부사채발행결정",
        "EB": "교환사채발행결정",
        "CB": "전환사채발행결정",
    }
    parsed = parse_bond_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title=title_by_type[str(expected["종류"])],
    )

    assert parsed["acpt_no"] == acpt_no
    for key, value in expected.items():
        assert parsed[key] == value


def test_parse_bond_issuance_collects_multiple_issue_targets() -> None:
    fixture_path = TESTS_DIR / "fixtures" / "kind_bond_issuance_20260508000981.html"

    parsed = parse_bond_issuance(fixture_path.read_bytes(), file_path=fixture_path)

    assert parsed["투자자"] == [
        ["퀸버메자닌1호조합", 2_500_000_000],
        ["주식회사 비에스파트너", 2_000_000_000],
        ["송 준", 1_500_000_000],
    ]
    assert "발행대상자세부엔티티" not in parsed


def test_parse_bond_issuance_keeps_one_investor_per_table_cell(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20260821000001.html"
    body_html = """
    <html><body>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>1</td><td>종류</td><td>무보증 전환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>1,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>1,000</td></tr>
      </table>
      <table>
        <tr><th>발행 대상자명</th><th>발행권면총액(원)</th></tr>
        <tr><td>삼성증권 주식회사<br>(본건 펀드의 신탁업자 지위에서)</td><td>1,000</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="전환사채권발행결정",
    )

    assert parsed["투자자"] == [
        ["삼성증권 주식회사 (본건 펀드의 신탁업자 지위에서)", 1_000]
    ]


def test_parse_bond_issuance_excludes_whitespace_separated_total_investor_row(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20220114000448.html"
    body_html = """
    <html><body>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>1</td><td>종류</td><td>무보증 전환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>6,034,378,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>6,034,378,000</td></tr>
      </table>
      <table>
        <tr><th>발행 대상자명</th><th>발행권면(전자등록) 총액(원)</th></tr>
        <tr><td>망토미 빌딩 주식회사</td><td>5,202,050,000</td></tr>
        <tr><td>주식회사 dodo</td><td>832,328,000</td></tr>
        <tr><td>합 계</td><td>6,034,378,000</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="전환사채권발행결정",
    )

    assert parsed["투자자"] == [
        ["망토미 빌딩 주식회사", 5_202_050_000],
        ["주식회사 dodo", 832_328_000],
    ]
    assert not any(
        "발행권면총액 합계" in warning
        for warning in parsed.get("parse_warnings", [])
    )


def test_parse_bond_issuance_reads_legacy_warrant_price_label(tmp_path: Path) -> None:
    fixture_path = tmp_path / "20090615000351.html"
    body_html = """
    <html><body>
      <h2 class="SECTION-1"><p class="SECTION-1">신주인수권부사채 발행결정</p></h2>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>10</td><td>종류</td><td>무기명 무보증 신주인수권부사채</td></tr>
        <tr><td>2. 사채의 권면총액(원)</td><td>4,000,000,000원</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금(원)</td><td>4,000,000,000원</td></tr>
        <tr><td>5. 사채만기일</td><td>2012-06-16</td></tr>
        <tr><td>9. 신주인수권 증권에 관한 사항</td><td>행사가격 (원/주)</td><td>1,450원</td></tr>
        <tr><td>9. 신주인수권 증권에 관한 사항</td><td>권리행사기간</td><td>시작일</td><td>2010-06-16</td></tr>
        <tr><td>9. 신주인수권 증권에 관한 사항</td><td>권리행사기간</td><td>종료일</td><td>2012-05-16</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["행사가액"] == 1_450


def test_parse_bond_issuance_uses_symmetric_cb_eb_bw_target_priority(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20260709000001.html"
    body_html = """
    <html><body>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>1</td><td>종류</td><td>전환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>1,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>1,000,000,000</td></tr>
        <tr><td>9. 교환에 관한 사항</td><td>교환에 따라 발행할 주식의 종류</td><td>교환 대상 주식</td></tr>
        <tr><td>9. 전환에 관한 사항</td><td>전환에 따라 발행할 주식의 종류</td><td>전환 대상 주식</td></tr>
        <tr><td>9. 전환에 관한 사항</td><td>전환가액 (원/주)</td><td>1,000</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="전환사채발행결정",
    )

    assert parsed["기업명(행사대상)"] == "전환 대상 주식"


def test_parse_bond_issuance_does_not_replace_failed_target_from_later_same_label_row(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20260712000002.html"
    body_html = """
    <html><body>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>1</td><td>종류</td><td>전환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>1,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>1,000,000,000</td></tr>
        <tr><td>9. 전환에 관한 사항</td><td>전환대상 관련 참고</td><td>미정</td></tr>
        <tr><td>9. 전환에 관한 사항</td><td>전환대상 주식의 종류</td><td>뒤 행의 주식</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="전환사채발행결정",
    )

    assert parsed["기업명(행사대상)"] == "미정"
    assert parsed["field_parse_status"]["기업명(행사대상)"] == "parsed"


def test_parse_bond_issuance_does_not_replace_empty_first_fixed_row(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20260712000003.html"
    body_html = """
    <html><body>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>1</td><td>종류</td><td>전환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>1,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>1,000,000,000</td></tr>
        <tr><td>5. 사채만기일</td><td></td></tr>
        <tr><td>5. 사채만기</td><td>2030년 01월 01일</td></tr>
        <tr><td>9. 전환에 관한 사항</td><td>전환가액 (원/주)</td><td>미정</td></tr>
        <tr><td>9. 교환에 관한 사항</td><td>교환가액 (원/주)</td><td>2,000</td></tr>
        <tr><td>9. 전환에 관한 사항</td><td>전환청구기간</td><td>시작일</td><td></td></tr>
        <tr><td>9. 교환에 관한 사항</td><td>교환청구기간</td><td>시작일</td><td>2028년 01월 01일</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="전환사채발행결정",
    )

    assert parsed["만기일"] is None
    assert parsed["행사가액"] is None
    assert parsed["행사시작일"] is None


@pytest.mark.parametrize(
    ("title", "expected_matches"),
    [
        ("신주인수권부사채·교환사채·전환사채 발행결정", "CB, EB, BW"),
        ("신주인수권부사채·교환사채 발행결정", "EB, BW"),
    ],
)
def test_parse_bond_issuance_rejects_multiple_security_types_in_title(
    tmp_path: Path,
    title: str,
    expected_matches: str,
) -> None:
    fixture_path = tmp_path / "20260712000001.html"

    body_html = """
    <html><body><table>
      <tr><td>1. 사채의 종류</td><td>회차</td><td>1</td></tr>
      <tr><td>2. 사채의 권면총액 (원)</td><td>1,000</td></tr>
      <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>1,000</td></tr>
    </table></body></html>
    """
    parsed = parse_bond_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title=title,
    )

    assert parsed["종류"] is None
    assert parsed["field_parse_status"]["종류"] == "source_not_found"
    assert (
        f"종류: 주입 제목에서 사채 종류를 둘 이상 확인했습니다. 확인된 종류: {expected_matches}"
        in parsed["strong_warning"]
    )


def test_bond_issuance_type_specific_labels_are_symmetric_cb_eb_bw_triplets() -> None:
    assert tuple(item[0] for item in BOND_SECURITY_TYPE_LABELS) == (
        "CB",
        "EB",
        "BW",
    )
    assert all(
        len(group) == 3
        for groups in (
            EXERCISE_TARGET_LABEL_GROUPS,
            EXERCISE_PRICE_LABEL_GROUPS,
            EXERCISE_PERIOD_LABEL_GROUPS,
        )
        for group in groups
    )


def test_parse_bond_issuance_reads_price_from_strict_numeric_value_cells(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20260709000002.html"
    body_html = """
    <html><body>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>1</td><td>종류</td><td>교환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>1,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>1,000,000,000</td></tr>
        <tr><td>9. 전환에 관한 사항</td><td>전환가액 결정방법</td><td>1) 전환가액 조정 후 70% 이상</td></tr>
        <tr><td>9. 교환에 관한 사항</td><td>교환가액 (원/주)</td><td>3.17원/주</td></tr>
        <tr><td>9. 신주인수권에 관한 사항</td><td>행사가액 (원/주)</td><td>2,000</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="교환사채발행결정",
    )

    assert parsed["행사가액"] == 3.17


def test_parse_bond_issuance_reads_legacy_warrant_exercise_period_label(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20111206000056.html"
    body_html = """
    <html><body>
      <h2 class="SECTION-1"><p class="SECTION-1">해외신주인수권부사채 발행 결정</p></h2>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>1</td><td>종류</td><td>무기명식 무보증 해외 신주인수권부사채</td></tr>
        <tr><td>2. 사채의 권면총액</td><td>원화기준 (원)</td><td>3,150,000,000</td></tr>
        <tr><td>4. 자금조달의 목적</td><td>시설자금 (원)</td><td>3,150,000,000</td></tr>
        <tr><td>6. 사채만기</td><td>2011년 12월 14일</td></tr>
        <tr><td>9. 사채발행방법</td><td>공모</td></tr>
        <tr><td>10. 신주인수권에 관한 사항</td><td>행사가액 (원/주)</td><td>2,874</td></tr>
        <tr><td>10. 신주인수권에 관한 사항</td><td>행사기간</td><td>시작일</td><td>2005년 01월 15일</td></tr>
        <tr><td>10. 신주인수권에 관한 사항</td><td>행사기간</td><td>종료일</td><td>2011년 12월 13일</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["행사시작일"] == "2005년 01월 15일"
    assert parsed["행사종료일"] == "2011년 12월 13일"
    assert parsed["만기일"] == "2011년 12월 14일"
    assert parsed["사채발행방법"] == "공모"
    assert any(
        warning.startswith("투자자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed["parse_warnings"]
    )


@pytest.mark.skipif(not HAS_KIND_RESOURCES, reason="Local KIND resources are absent")
def test_parse_bond_issuance_prefers_krw_face_value_for_overseas_issue() -> None:
    fixture_path = (
        REPO_ROOT
        / "resources"
        / "KIND"
        / "bond_issuance"
        / "kind_html_contents_grouped_sections"
        / "2011"
        / "20111206000056.html"
    )

    parsed = parse_bond_issuance(fixture_path.read_bytes(), file_path=fixture_path)

    assert parsed["발행금액"] == 3_150_000_000
    assert parsed["사채발행방법"] == "공모"
    assert not any(
        "자금조달 목적 합계" in warning
        for warning in parsed.get("parse_warnings", [])
    )


def test_parse_rights_issuance_extracts_kind_stockissue_fields() -> None:
    fixture_path = Path("20240822000349.html")
    body_html = """
    <html><body>
      <h2 class="SECTION-1"><p class="SECTION-1">유상증자결정</p></h2>
      <table>
        <tr><td rowspan="2">1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>2,495,327</td></tr>
        <tr><td>기타주식 (주)</td><td>-</td></tr>
        <tr><td rowspan="6">4. 자금조달의 목적</td><td>시설자금 (원)</td><td>2,002,499,917</td></tr>
        <tr><td>영업양수자금 (원)</td><td>-</td></tr>
        <tr><td>운영자금 (원)</td><td>2,002,499,918</td></tr>
        <tr><td>채무상환자금 (원)</td><td>-</td></tr>
        <tr><td>타법인 증권<br>취득자금 (원)</td><td>-</td></tr>
        <tr><td>기타자금 (원)</td><td>-</td></tr>
        <tr><td colspan="2">5. 증자방식</td><td>제3자배정증자</td></tr>
      </table>
      <table>
        <tr><td rowspan="2">6. 신주 발행가액</td><td>보통주식 (원)</td><td>1,605</td></tr>
        <tr><td>기타주식 (원)</td><td>-</td></tr>
        <tr><td colspan="2">9. 납입일</td><td>2024년 08월 30일</td></tr>
        <tr><td colspan="2">11. 신주권교부예정일</td><td>2023년 10월 04일</td></tr>
        <tr><td colspan="2">12. 신주의 상장 예정일</td><td>2024년 10월 04일</td></tr>
      </table>
      <table>
        <tr>
          <th>제3자배정 대상자</th><th>회사 또는 최대주주와의 관계</th><th>선정경위</th>
          <th>증자결정 전후 6월이내 거래내역 및 계획</th><th>배정주식수 (주)</th><th>비 고</th>
        </tr>
        <tr><td>주식회사 에프앤지</td><td>없음</td><td>회사 경영상의 필요</td><td>-</td><td>2,495,327</td><td>-</td></tr>
      </table>
      <table>
        <tr>
          <th rowspan="2">명칭</th><th rowspan="2">출자자수(명)</th>
          <th colspan="2">대표이사(대표조합원)</th><th colspan="2">업무집행자(업무집행조합원)</th>
          <th colspan="2">최대주주(최대출자자)</th>
        </tr>
        <tr><th>성명</th><th>지분(%)</th><th>성명</th><th>지분(%)</th><th>성명</th><th>지분(%)</th></tr>
        <tr>
          <td rowspan="2">주식회사 에프앤지</td><td rowspan="2">5</td>
          <td>이미란</td><td>-</td><td>이미란</td><td>-</td><td>(주)에스제이씨</td><td>30</td>
        </tr>
        <tr><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["신주의 종류와 수"] == [["보통주식", 2_495_327], ["기타주식", 0]]
    assert parsed["field_parse_status"]["신주의 종류와 수"] == "parsed"
    assert parsed["field_parse_status"]["발행목적"] == "parsed"
    assert parsed["field_parse_status"]["발행대상자"] == "parsed"
    assert parsed["발행목적"] == [
        ["시설자금", 2_002_499_917],
        ["운영자금", 2_002_499_918],
    ]
    assert parsed["발행가액"] == [["보통주식", 1_605], ["기타주식", 0]]
    assert "기준주가" not in parsed
    assert "기준주가" not in parsed["field_parse_status"]
    assert parsed["증자방식"] == "제3자배정증자"
    assert parsed["납입일"] == "2024년 08월 30일"
    assert parsed["신주권교부예정일"] == "2023년 10월 04일"
    assert parsed["상장예정일"] == "2024년 10월 04일"
    assert parsed["발행대상자"] == [["주식회사 에프앤지", 2_495_327]]
    assert "발행대상자세부엔티티" not in parsed


@pytest.mark.skipif(not HAS_KIND_RESOURCES, reason="Local KIND resources are absent")
@pytest.mark.parametrize("relative_path", PAID_RIGHTS_ISSUANCE_50_EXAMPLES)
def test_parse_rights_issuance_paid_examples_have_paid_detail(relative_path: str) -> None:
    fixture_path = RIGHTS_GROUPED_DIR / relative_path

    parsed = parse_rights_issuance(
        fixture_path.read_bytes(),
        file_path=fixture_path,
        title=_rights_manifest_title(fixture_path),
    )

    assert parsed["증자유형"] == "유상증자"
    assert parsed["유상증자"] is not None
    assert parsed["무상증자"] is None
    assert parsed["유상증자"]["신주의 종류와 수"] == parsed["신주의 종류와 수"]
    assert parsed["유상증자"]["발행가액"] == parsed["발행가액"]
    assert parsed["유상증자"]["납입일"] == parsed["납입일"]


@pytest.mark.skipif(not HAS_KIND_RESOURCES, reason="Local KIND resources are absent")
@pytest.mark.parametrize("relative_path", BONUS_RIGHTS_ISSUANCE_50_EXAMPLES)
def test_parse_rights_issuance_bonus_examples_have_bonus_detail(relative_path: str) -> None:
    fixture_path = RIGHTS_GROUPED_DIR / relative_path

    parsed = parse_rights_issuance(
        fixture_path.read_bytes(),
        file_path=fixture_path,
        title=_rights_manifest_title(fixture_path),
    )

    assert parsed["증자유형"] == "무상증자"
    assert parsed["유상증자"] is None
    assert parsed["무상증자"] is not None
    assert parsed["발행목적"] == "-"
    assert parsed["발행가액"] == "-"
    assert parsed["증자방식"] == "-"
    assert parsed["납입일"] == "-"
    assert parsed["발행대상자"] == "-"
    assert parsed["무상증자"]["신주의 종류와 수"] == parsed["신주의 종류와 수"]
    assert parsed["무상증자"]["신주배정기준일"]
    assert parsed["무상증자"]["1주당 신주배정주식수"][0][1]
    assert parsed["field_parse_status"]["발행목적"] == "not_applicable"
    assert parsed["field_parse_status"]["발행가액"] == "not_applicable"
    assert parsed["field_parse_status"]["증자방식"] == "not_applicable"
    assert parsed["field_parse_status"]["납입일"] == "not_applicable"
    assert parsed["field_parse_status"]["발행대상자"] == "not_applicable"
    assert not any(
        warning.startswith(
            ("발행목적:", "발행가액:", "증자방식:", "납입일:", "발행대상자:")
        )
        for warning in parsed.get("strong_warning", [])
    )


@pytest.mark.skipif(not HAS_KIND_RESOURCES, reason="Local KIND resources are absent")
@pytest.mark.parametrize("relative_path", MIXED_RIGHTS_ISSUANCE_50_EXAMPLES)
def test_parse_rights_issuance_mixed_examples_split_paid_and_bonus_details(
    relative_path: str,
) -> None:
    fixture_path = RIGHTS_GROUPED_DIR / relative_path

    parsed = parse_rights_issuance(
        fixture_path.read_bytes(),
        file_path=fixture_path,
        title=_rights_manifest_title(fixture_path),
    )

    assert parsed["증자유형"] == "유무상증자"
    assert parsed["유상증자"] is not None
    assert parsed["무상증자"] is not None
    assert parsed["유상증자"]["신주의 종류와 수"] == parsed["신주의 종류와 수"]
    assert parsed["유상증자"]["발행가액"] == parsed["발행가액"]
    assert parsed["무상증자"]["신주의 종류와 수"][0][1] > 0
    assert parsed["무상증자"]["신주배정기준일"]
    assert parsed["무상증자"]["1주당 신주배정주식수"][0][1]


@pytest.mark.skipif(not HAS_KIND_RESOURCES, reason="Local KIND resources are absent")
def test_parse_rights_issuance_mixed_keeps_paid_flat_fields_and_bonus_section() -> None:
    fixture_path = RIGHTS_GROUPED_DIR / "2008/20081020000088.html"

    parsed = parse_rights_issuance(
        fixture_path.read_bytes(),
        file_path=fixture_path,
        title=_rights_manifest_title(fixture_path),
    )

    assert parsed["증자유형"] == "유무상증자"
    assert parsed["신주의 종류와 수"] == [["보통주식", 20_000_000], ["기타주식", 0]]
    assert parsed["유상증자"]["신주의 종류와 수"] == [
        ["보통주식", 20_000_000],
        ["기타주식", 0],
    ]
    assert parsed["무상증자"]["신주의 종류와 수"] == [
        ["보통주식", 26_253_328],
        ["기타주식", 0],
    ]
    assert parsed["무상증자"]["신주배정기준일"] == "2008년 11월 18일"
    assert parsed["무상증자"]["1주당 신주배정주식수"] == [
        ["보통주식", "0.5000000"],
        ["기타주식", None],
    ]
    assert parsed["무상증자"]["신주권교부예정일"] == "2008년 12월 05일"
    assert parsed["무상증자"]["상장예정일"] == "2008년 12월 08일"


@pytest.mark.skipif(not HAS_KIND_RESOURCES, reason="Local KIND resources are absent")
def test_parse_rights_issuance_extracts_legacy_stock_labels() -> None:
    fixture_path = (
        REPO_ROOT
        / "resources"
        / "KIND"
        / "rights_issuance"
        / "kind_html_contents_sections"
        / "20120419000357.html"
    )

    parsed = parse_rights_issuance(
        fixture_path.read_bytes(),
        file_path=fixture_path,
        title=_rights_manifest_title(fixture_path),
    )

    assert parsed["신주의 종류와 수"] == [["보통주식", 3_600_000], ["기타주식", 0]]
    assert parsed["증자 전 발행주식총수"] == [["보통주식", 12_635_511], ["기타주식", 0]]
    assert parsed["발행가액"] == [["보통주식", 0], ["기타주식", 0]]
    assert parsed["발행목적"] == [
        ["운영자금", 4_200_000_000],
        ["기타자금", 3_000_000_000],
    ]
    assert "기준주가" not in parsed


@pytest.mark.skipif(not HAS_KIND_RESOURCES, reason="Local KIND resources are absent")
def test_parse_rights_issuance_maps_kind_stock_labels_to_other_stock() -> None:
    fixture_path = (
        REPO_ROOT
        / "resources"
        / "KIND"
        / "rights_issuance"
        / "kind_html_contents_sections"
        / "20171212000184.html"
    )

    parsed = parse_rights_issuance(
        fixture_path.read_bytes(),
        file_path=fixture_path,
        title=_rights_manifest_title(fixture_path),
    )

    assert parsed["신주의 종류와 수"] == [["보통주식", 0], ["기타주식", 2_000_000]]
    assert parsed["발행가액"] == [["보통주식", 0], ["기타주식", 5_000]]
    assert parsed.get("strong_warning")
    assert parsed.get("parse_warnings")


def test_parse_rights_issuance_classifies_consistency_warnings_by_level(tmp_path: Path) -> None:
    fixture_path = tmp_path / "20250102000010.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td rowspan="2">1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>10</td></tr>
        <tr><td>기타주식 (주)</td><td>5</td></tr>
        <tr><td rowspan="2">3. 증자전 발행주식총수 (주)</td><td>보통주식 (주)</td><td>100</td></tr>
        <tr><td>기타주식 (주)</td><td>20</td></tr>
        <tr><td rowspan="1">4. 자금조달의 목적</td><td>운영자금 (원)</td><td>2,000</td></tr>
        <tr><td colspan="2">5. 증자방식</td><td>제3자배정증자</td></tr>
        <tr><td rowspan="2">6. 신주 발행가액</td><td>보통주식 (원)</td><td>100</td></tr>
        <tr><td>기타주식 (원)</td><td>100</td></tr>
      </table>
      <table>
        <tr><th>제3자배정 대상자</th><th>배정주식수 (주)</th></tr>
        <tr><td>테스트조합</td><td>10</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["증자 전 발행주식총수"] == [["보통주식", 100], ["기타주식", 20]]
    assert parsed["field_parse_status"]["증자 전 발행주식총수"] == "parsed"
    assert parsed["발행대상자"] == [["테스트조합", 10]]
    assert parsed["field_parse_status"]["발행대상자"] == "parsed"
    assert any("배정주식수 합계" in warning for warning in parsed["weak_warning"])
    assert any("자금조달 목적 합계" in warning for warning in parsed["weak_warning"])
    assert any("0이 아닌 주식 종류가 둘 이상" in warning for warning in parsed["medium_warning"])


def test_parse_rights_issuance_excludes_bottom_duplicate_total_issue_target(tmp_path: Path) -> None:
    fixture_path = tmp_path / "20080908000527.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td rowspan="2">1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>5,806,443</td></tr>
        <tr><td>기타주식 (주)</td><td>0</td></tr>
        <tr><td rowspan="1">4. 자금조달의 목적</td><td>운영자금 (원)</td><td>1,000</td></tr>
        <tr><td colspan="2">5. 증자방식</td><td>제3자배정증자</td></tr>
      </table>
      <table>
        <tr>
          <th>제3자배정 대상자</th><th>회사 또는 최대주주와의 관계</th><th>선정경위</th>
          <th>증자결정 전후 6월이내 거래내역 및 계획</th><th>배정주식수 (주)</th><th>비 고</th>
        </tr>
        <tr><td>테스트조합</td><td>-</td><td>투자 의향과 납입능력을 고려해 선정</td><td>-</td><td>5,806,443</td><td>-</td></tr>
        <tr><td>인수금액 총계</td><td>-</td><td>-</td><td>-</td><td>5,806,443</td><td>-</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["발행대상자"] == [["테스트조합", 5_806_443]]
    assert not any(
        "배정주식수 합계" in warning and "일치하지 않습니다" in warning
        for warning in parsed.get("parse_warnings", [])
    )


def test_parse_rights_issuance_keeps_mismatching_duplicate_target_total(tmp_path: Path) -> None:
    fixture_path = tmp_path / "20250102000011.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td rowspan="2">1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>5,806,443</td></tr>
        <tr><td>기타주식 (주)</td><td>0</td></tr>
        <tr><td colspan="2">5. 증자방식</td><td>제3자배정증자</td></tr>
      </table>
      <table>
        <tr>
          <th>제3자배정 대상자</th><th>회사 또는 최대주주와의 관계</th><th>선정경위</th>
          <th>증자결정 전후 6월이내 거래내역 및 계획</th><th>배정주식수 (주)</th><th>비 고</th>
        </tr>
        <tr><td>인수금액 총계</td><td>-</td><td>-</td><td>-</td><td>5,806,443</td><td>-</td></tr>
        <tr><td>테스트조합</td><td>-</td><td>투자 의향과 납입능력을 고려해 선정</td><td>-</td><td>5,806,443</td><td>-</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["발행대상자"] == [
        ["인수금액 총계", 5_806_443],
        ["테스트조합", 5_806_443],
    ]
    assert parsed["field_parse_status"]["발행대상자"] == "parsed"
    assert any(
        "배정주식수 합계" in warning
        for warning in parsed.get("weak_warning", [])
    )


def test_parse_rights_issuance_keeps_mismatching_unsplit_target_total(tmp_path: Path) -> None:
    fixture_path = tmp_path / "20250102000012.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td rowspan="2">1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>5,806,443</td></tr>
        <tr><td>기타주식 (주)</td><td>0</td></tr>
        <tr><td colspan="2">5. 증자방식</td><td>제3자배정증자</td></tr>
      </table>
      <table>
        <tr><th>제3자배정 대상자</th><th>배정주식수 (주)</th></tr>
        <tr><td>테스트조합</td><td>5,806,443</td></tr>
        <tr><td>인수금액총계</td><td>5,806,443</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["발행대상자"] == [
        ["테스트조합", 5_806_443],
        ["인수금액총계", 5_806_443],
    ]
    assert parsed["field_parse_status"]["발행대상자"] == "parsed"
    assert any(
        "배정주식수 합계" in warning
        for warning in parsed.get("weak_warning", [])
    )


def test_parse_rights_issuance_warns_for_single_digit_amount_difference(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000011.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td>1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>10</td></tr>
        <tr><td>4. 자금조달의 목적</td><td>운영자금 (원)</td><td>1,009</td></tr>
        <tr><td>5. 증자방식</td><td>일반공모증자</td></tr>
        <tr><td>6. 신주 발행가액</td><td>보통주식 (원)</td><td>100</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert any(
        "자금조달 목적 합계" in warning
        for warning in parsed.get("weak_warning", [])
    )


def test_parse_rights_issuance_checks_funding_total_with_issue_price(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000021.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td>1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>10</td></tr>
        <tr><td>4. 자금조달의 목적</td><td>신규사업자금 (원)</td><td>1,000</td></tr>
        <tr><td>5. 증자방식</td><td>일반공모증자</td></tr>
        <tr><td>6. 신주 발행가액</td><td>보통주식 (원)</td><td>100</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["발행목적"] == [["신규사업자금", 1_000]]
    assert not any(
        "자금조달 목적 합계" in warning
        for warning in parsed.get("weak_warning", [])
    )


def test_parse_rights_issuance_keeps_first_explicit_issue_price(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000026.html"
    body_html = """
    <html><body>
      <table>
        <tr><td>1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>10</td></tr>
        <tr><td>6. 신주 발행가액</td><td>보통주식 (원)</td><td>0</td></tr>
        <tr><td>6. 신주 발행가액</td><td>보통주식 (원)</td><td>100</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["발행가액"] == [["보통주식", 0], ["기타주식", None]]
    assert parsed["field_parse_status_detail"]["발행가액"]["보통주식"] == (
        "explicit_zero"
    )


def test_parse_rights_issuance_sums_multiple_target_amounts_in_one_cell(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000022.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td>1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>200,000</td></tr>
        <tr><td>5. 증자방식</td><td>제3자배정증자</td></tr>
      </table>
      <table>
        <tr><th>제3자배정 대상자</th><th>배정주식수 (주)</th></tr>
        <tr><td>투자자A<br/>투자자B</td><td>100,000<br/>100,000</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["발행대상자"] == [["투자자A 투자자B", 200_000]]
    assert not any(
        "배정주식수 합계" in warning
        for warning in parsed.get("weak_warning", [])
    )


def test_parse_rights_issuance_sums_ungrouped_target_amounts_in_one_cell(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000024.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td>1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>200</td></tr>
        <tr><td>5. 증자방식</td><td>제3자배정증자</td></tr>
      </table>
      <table>
        <tr><th>제3자배정 대상자</th><th>배정주식수 (주)</th></tr>
        <tr><td>투자자A<br/>투자자B</td><td>100<br/>100</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["발행대상자"] == [["투자자A 투자자B", 200]]
    assert not any(
        "배정주식수 합계" in warning
        for warning in parsed.get("weak_warning", [])
    )


def test_parse_rights_issuance_does_not_special_case_target_amount_percentage(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000025.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td>1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>100,000</td></tr>
        <tr><td>5. 증자방식</td><td>제3자배정증자</td></tr>
      </table>
      <table>
        <tr><th>제3자배정 대상자</th><th>배정주식수 (주)</th></tr>
        <tr><td>투자자A</td><td>100,000 (100%)</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["발행대상자"] == [["투자자A", 100_100]]
    assert any(
        "배정주식수 합계" in warning
        for warning in parsed.get("weak_warning", [])
    )


def test_parse_rights_issuance_uses_first_target_table_without_total_matching(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000013.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자 결정</p>
      <table>
        <tr><td rowspan="2">1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>10</td></tr>
        <tr><td>기타주식 (주)</td><td>-</td></tr>
        <tr><td rowspan="2">3. 증자전 발행주식총수 (주)</td><td>보통주식 (주)</td><td>100</td></tr>
        <tr><td>기타주식 (주)</td><td>-</td></tr>
        <tr><td>4. 자금조달의 목적</td><td>운영자금 (원)</td><td>1,000</td></tr>
        <tr><td>5. 증자방식</td><td>제3자배정증자</td></tr>
      </table>
      <table>
        <tr><td>6. 신주 발행가액</td><td>보통주식 (원)</td><td>100</td></tr>
        <tr><td>9. 납입일</td><td>2025년 01월 02일</td></tr>
        <tr><td>11. 신주권교부예정일</td><td>2025년 01월 03일</td></tr>
        <tr><td>12. 신주의 상장 예정일</td><td>2025년 01월 04일</td></tr>
      </table>
      <table>
        <tr><td>정정일자</td><td>정정사유</td><td>정정내역</td></tr>
        <tr><td>정정일자</td><td>정정사유</td><td>정정과목</td><td>정정전</td><td>정정후</td></tr>
      </table>
      <table>
        <tr><th>제3자배정 대상자</th><th>배정주식수 (주)</th></tr>
        <tr><td>과거조합</td><td>5</td></tr>
      </table>
      <table>
        <tr><th>제3자배정 대상자</th><th>배정주식수 (주)</th></tr>
        <tr><td>테스트조합</td><td>10</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["발행대상자"] == [["과거조합", 5]]
    assert any(
        "배정주식수 합계" in warning
        for warning in parsed.get("weak_warning", [])
    )
    assert len(parsed["raw_tables"]) == 5


def test_parse_rights_issuance_ignores_non_extraction_correction_history_table(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000014.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자 결정</p>
      <table>
        <tr><td>1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>10</td></tr>
        <tr><td>5. 증자방식</td><td>일반공모증자</td></tr>
      </table>
      <table>
        <tr><td>정정일자</td><td>정정사유</td><td>정정전</td><td>정정후</td></tr>
        <tr><td>납입일</td><td>기재정정</td><td>2025년 01월 01일</td><td>2025년 01월 02일</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["신주의 종류와 수"] == [["보통주식", 10], ["기타주식", None]]
    assert parsed["field_parse_status_detail"]["신주의 종류와 수"] == {
        "보통주식": "parsed",
        "기타주식": "source_not_found",
    }
    assert any(
        warning.startswith(
            "신주의 종류와 수(기타주식): 정해진 출처에서 값을 찾지 못했습니다."
        )
        for warning in parsed["strong_warning"]
    )
    assert parsed["납입일"] is None
    assert parsed["field_parse_status"]["납입일"] == "source_not_found"


def test_parse_rights_issuance_saves_empty_source_cells_as_null_with_strong_warnings(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000032.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td>1. 신주의 종류와 수</td><td>보통주식 (주)</td><td></td></tr>
        <tr><td>4. 자금조달의 목적</td><td>운영자금 (원)</td><td></td></tr>
        <tr><td>5. 증자방식</td><td></td></tr>
        <tr><td>6. 신주 발행가액</td><td>보통주식 (원)</td><td></td></tr>
        <tr><td>9. 납입일</td><td></td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["신주의 종류와 수"] == [["보통주식", None], ["기타주식", None]]
    assert parsed["발행목적"] is None
    assert parsed["증자방식"] is None
    assert parsed["발행가액"] == [["보통주식", None], ["기타주식", None]]
    assert parsed["납입일"] is None
    for field_name in ("신주의 종류와 수", "발행목적", "증자방식", "발행가액", "납입일"):
        assert parsed["field_parse_status"][field_name] == "source_not_found"
        assert any(
            warning.startswith(
                f"{field_name}: 정해진 출처에서 값을 찾지 못했습니다."
            )
            for warning in parsed["strong_warning"]
        )


def test_parse_rights_issuance_classifies_explicit_zero_stock_counts_as_weak_warning(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000012.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td rowspan="2">1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>-</td></tr>
        <tr><td>기타주식 (주)</td><td>-</td></tr>
        <tr><td rowspan="2">3. 증자전 발행주식총수 (주)</td><td>보통주식 (주)</td><td>-</td></tr>
        <tr><td>기타주식 (주)</td><td>-</td></tr>
        <tr><td>4. 자금조달의 목적</td><td>운영자금 (원)</td><td>-</td></tr>
        <tr><td>5. 증자방식</td><td>일반공모증자</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert any(
        warning.startswith("신주의 종류와 수:")
        for warning in parsed["weak_warning"]
    )
    assert parsed["field_parse_status"]["신주의 종류와 수"] == "explicit_zero"
    assert any(
        warning.startswith("증자 전 발행주식총수:")
        for warning in parsed["weak_warning"]
    )
    assert parsed["field_parse_status"]["증자 전 발행주식총수"] == "explicit_zero"
    assert parsed["발행목적"] == []
    assert parsed["field_parse_status"]["발행목적"] == "explicit_zero"


def test_parse_rights_issuance_tracks_stock_count_status_by_stock_type(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000023.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td rowspan="2">1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>10</td></tr>
        <tr><td>기타주식 (주)</td><td>-</td></tr>
        <tr><td rowspan="2">3. 증자전 발행주식총수 (주)</td><td>보통주식 (주)</td><td>100</td></tr>
        <tr><td>기타주식 (주)</td><td>0</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["field_parse_status"]["신주의 종류와 수"] == "parsed"
    assert parsed["field_parse_status_detail"]["신주의 종류와 수"] == {
        "보통주식": "parsed",
        "기타주식": "explicit_zero",
    }
    assert parsed["field_parse_status"]["증자 전 발행주식총수"] == "parsed"
    assert parsed["field_parse_status_detail"]["증자 전 발행주식총수"] == {
        "보통주식": "parsed",
        "기타주식": "explicit_zero",
    }


def test_parse_rights_issuance_strong_warns_for_zero_common_pre_issuance_stock(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000024.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td>1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>10</td></tr>
        <tr><td rowspan="2">3. 증자전 발행주식총수 (주)</td><td>보통주식 (주)</td><td>-</td></tr>
        <tr><td>기타주식 (주)</td><td>20</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["field_parse_status"]["증자 전 발행주식총수"] == "parsed"
    assert parsed["field_parse_status_detail"]["증자 전 발행주식총수"] == {
        "보통주식": "explicit_zero",
        "기타주식": "parsed",
    }
    assert any(
        warning.startswith("증자 전 발행주식총수: 보통주식 수량")
        for warning in parsed["strong_warning"]
    )


@pytest.mark.skipif(not HAS_KIND_RESOURCES, reason="Local KIND resources are absent")
def test_parse_rights_issuance_extracts_bonus_issuance() -> None:
    fixture_path = (
        REPO_ROOT
        / "resources"
        / "KIND"
        / "rights_issuance"
        / "kind_html_contents_sections"
        / "20080825000072.html"
    )

    parsed = parse_rights_issuance(
        fixture_path.read_bytes(),
        file_path=fixture_path,
        title=_rights_manifest_title(fixture_path),
    )

    assert parsed["증자유형"] == "무상증자"
    assert parsed["신주의 종류와 수"] == [["보통주식", 3_560_000], ["기타주식", 0]]
    assert parsed["발행목적"] == "-"
    assert parsed["발행가액"] == "-"
    assert parsed["증자방식"] == "-"
    assert parsed["납입일"] == "-"
    assert parsed["발행대상자"] == "-"
    assert parsed["신주권교부예정일"] == "2008년 10월 01일"
    assert parsed["상장예정일"] == "2008년 10월 02일"
    assert parsed["유상증자"] is None
    assert parsed["무상증자"] == {
        "신주의 종류와 수": [["보통주식", 3_560_000], ["기타주식", 0]],
        "증자 전 발행주식총수": [["보통주식", 4_440_000], ["기타주식", 0]],
        "신주배정기준일": "2008년 09월 11일",
        "1주당 신주배정주식수": [["보통주식", "0.8149112"], ["기타주식", None]],
        "신주권교부예정일": "2008년 10월 01일",
        "상장예정일": "2008년 10월 02일",
    }
    assert parsed["field_parse_status"]["발행목적"] == "not_applicable"
    assert parsed["field_parse_status"]["발행가액"] == "not_applicable"
    assert parsed["field_parse_status"]["증자방식"] == "not_applicable"
    assert parsed["field_parse_status"]["납입일"] == "not_applicable"
    assert parsed["field_parse_status"]["발행대상자"] == "not_applicable"
    assert not any(
        warning.startswith(
            ("발행목적:", "발행가액:", "증자방식:", "납입일:", "발행대상자:")
        )
        for warning in parsed.get("strong_warning", [])
    )


@pytest.mark.skipif(not HAS_KIND_RESOURCES, reason="Local KIND resources are absent")
def test_parse_rights_issuance_marks_single_compressed_dash_target_row_as_undisclosed() -> None:
    fixture_path = (
        REPO_ROOT
        / "resources"
        / "KIND"
        / "rights_issuance"
        / "kind_html_contents_sections"
        / "20230224000621.html"
    )

    parsed = parse_rights_issuance(
        fixture_path.read_bytes(),
        file_path=fixture_path,
        title=_rights_manifest_title(fixture_path),
    )

    assert parsed["증자방식"] == "제3자배정증자"
    assert parsed["발행대상자"] == [["-", 0]]
    assert parsed["field_parse_status"]["발행대상자"] == "explicit_zero"
    assert not any(
        warning.startswith("발행대상자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed.get("parse_warnings", [])
    )


@pytest.mark.skipif(not HAS_KIND_RESOURCES, reason="Local KIND resources are absent")
def test_parse_rights_issuance_marks_single_dash_target_row_as_undisclosed() -> None:
    fixture_path = (
        REPO_ROOT
        / "resources"
        / "KIND"
        / "rights_issuance"
        / "kind_html_contents_sections"
        / "20100219000571.html"
    )

    parsed = parse_rights_issuance(
        fixture_path.read_bytes(),
        file_path=fixture_path,
        title=_rights_manifest_title(fixture_path),
    )

    assert parsed["발행대상자"] == [["-", 0]]
    assert parsed["field_parse_status"]["발행대상자"] == "explicit_zero"
    assert not any(
        warning.startswith("발행대상자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed.get("parse_warnings", [])
    )


def test_parse_rights_issuance_marks_multiple_dash_target_rows_as_one_undisclosed() -> None:
    fixture_path = Path("20250102000005.html")
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table><tr><td>5. 증자방식</td><td>제3자배정증자</td></tr></table>
      <table>
        <tr><th>제3자배정 대상자</th><th>배정주식수 (주)</th></tr>
        <tr><td>-</td><td>-</td></tr>
        <tr><td>-</td><td>-</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["발행대상자"] == [["-", 0]]
    assert parsed["field_parse_status"]["발행대상자"] == "explicit_zero"
    assert not any(
        warning.startswith("발행대상자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed.get("parse_warnings", [])
    )


@pytest.mark.skipif(not HAS_KIND_RESOURCES, reason="Local KIND resources are absent")
def test_parse_rights_issuance_marks_real_multiple_dash_target_rows_as_one_undisclosed() -> None:
    fixture_path = (
        REPO_ROOT
        / "resources"
        / "KIND"
        / "rights_issuance"
        / "kind_html_contents_sections"
        / "20161004000005.html"
    )

    parsed = parse_rights_issuance(
        fixture_path.read_bytes(),
        file_path=fixture_path,
        title=_rights_manifest_title(fixture_path),
    )

    assert parsed["발행대상자"] == [["-", 0]]
    assert parsed["field_parse_status"]["발행대상자"] == "explicit_zero"
    assert not any(
        warning.startswith("발행대상자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed.get("parse_warnings", [])
    )


def test_parse_rights_issuance_does_not_mark_dash_name_with_amount_as_undisclosed() -> None:
    fixture_path = Path("20250102000006.html")
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table><tr><td>5. 증자방식</td><td>제3자배정증자</td></tr></table>
      <table>
        <tr><th>제3자배정 대상자</th><th>배정주식수 (주)</th></tr>
        <tr><td>-</td><td>1,000</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["발행대상자"] is None
    assert parsed["field_parse_status"]["발행대상자"] == "source_not_found"
    assert any(
        warning.startswith("발행대상자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed.get("strong_warning", [])
    )


def test_parse_rights_issuance_does_not_mark_non_dash_placeholder_as_undisclosed() -> None:
    fixture_path = Path("20250102000008.html")
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table><tr><td>5. 증자방식</td><td>제3자배정증자</td></tr></table>
      <table>
        <tr><th>제3자배정 대상자</th><th>배정주식수 (주)</th></tr>
        <tr><td>미정</td><td>-</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["발행대상자"] is None
    assert parsed["field_parse_status"]["발행대상자"] == "source_not_found"
    assert any(
        warning.startswith("발행대상자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed.get("strong_warning", [])
    )


def test_parse_rights_issuance_still_extracts_single_named_target_row() -> None:
    fixture_path = Path("20250102000007.html")
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td>1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>1,000</td></tr>
        <tr><td>5. 증자방식</td><td>제3자배정증자</td></tr>
      </table>
      <table>
        <tr><th>제3자배정 대상자</th><th>배정주식수 (주)</th></tr>
        <tr><td>테스트조합</td><td>1,000</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["발행대상자"] == [["테스트조합", 1_000]]
    assert parsed["field_parse_status"]["발행대상자"] == "parsed"
    assert not any(
        warning.startswith("발행대상자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed.get("parse_warnings", [])
    )


def test_parse_rights_issuance_warns_when_third_party_target_table_is_absent() -> None:
    fixture_path = Path("20250102000009.html")
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td>1. 신주의 종류와 수</td><td>보통주식</td><td>1,000</td></tr>
        <tr><td>5. 증자방식</td><td>제3자배정증자</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="유상증자결정",
    )

    assert parsed["발행대상자"] is None
    assert parsed["field_parse_status"]["발행대상자"] == "source_not_found"
    assert any(
        warning.startswith("발행대상자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed.get("strong_warning", [])
    )


def test_parse_rights_issuance_rejects_missing_or_unknown_title(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000004.html"
    body_html = """
    <html><body>
      <table>
        <tr><td>임의 표</td><td>값</td></tr>
      </table>
    </body></html>
    """

    with pytest.raises(ValueError, match="rights issuance title is required"):
        parse_rights_issuance(
            body_html.encode("utf-8"),
            file_path=fixture_path,
        )

    with pytest.raises(
        ValueError,
        match="must identify paid, bonus, or mixed issuance",
    ):
        parse_rights_issuance(
            body_html.encode("utf-8"),
            file_path=fixture_path,
            title="기타공시",
        )


def test_parse_rights_issuance_rejects_unknown_title_instead_of_inferring_from_table(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000005.html"
    body_html = """
    <html><body>
      <table>
        <tr><td rowspan="2">1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>10</td></tr>
        <tr><td>기타주식 (주)</td><td>-</td></tr>
        <tr><td colspan="2">3. 신주배정기준일</td><td>2025년 01월 02일</td></tr>
        <tr><td colspan="2">8. 신주권교부예정일</td><td>2025년 01월 03일</td></tr>
      </table>
    </body></html>
    """

    with pytest.raises(
        ValueError,
        match="must identify paid, bonus, or mixed issuance",
    ):
        parse_rights_issuance(
            body_html.encode("utf-8"),
            file_path=fixture_path,
            title="기타공시",
        )


def test_build_insight_payload_groups_disclosures(tmp_path: Path, monkeypatch) -> None:
    fixture_path = _write_classification_fixture(tmp_path)

    monkeypatch.setattr(
        "finiq.market_desk.web.features.market_data.service_insight.fetch_stock_price_history",
        lambda stock_code, start_date, end_date: [
            {"date": "2025-01-02", "open": 100, "high": 110, "low": 95, "close": 108, "volume": 1000},
            {"date": "2025-01-03", "open": 108, "high": 111, "low": 101, "close": 103, "volume": 1200},
            {"date": "2025-01-10", "open": 103, "high": 118, "low": 100, "close": 115, "volume": 1500},
            {"date": "2025-01-15", "open": 115, "high": 119, "low": 112, "close": 118, "volume": 900},
        ],
    )

    payload = build_insight_payload(
        fixture_path,
        "005930",
        start_date_iso="2025-01-01",
        end_date_iso="2025-01-31",
        price_source="fdr",
        stock_code_override="005930",
    )

    assert payload["company"]["company_name"] == "테스트전자"
    assert payload["chart"]["candles"][-1]["close"] == 118.0
    groups = {group["name"] for group in payload["chart"]["groups"]}
    assert "CB" in groups
    assert "주주총회" in groups
    assert DISCLOSURE_GROUP_OTHER in groups
    assert len(payload["chart"]["markers"]) == 3
    shareholder_meeting_marker = next(
        marker for marker in payload["chart"]["markers"] if marker["group"] == "주주총회"
    )
    assert shareholder_meeting_marker["shape"] == "square"
    assert shareholder_meeting_marker["position"] == "inBar"


def test_build_insight_payload_extends_visible_range_for_after_close_disclosure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    payload = _classification_fixture_payload()
    payload["companies"][0]["disclosures"] = [
        {
            "disclosed_at": "2025-01-10 20:01:00",
            "title": "장후 공시",
            "submitter": "테스트전자",
            "acpt_no": "after-close",
        }
    ]
    fixture_path = _write_classification_fixture(tmp_path, payload)
    monkeypatch.setattr(
        "finiq.market_desk.web.features.market_data.service_insight.fetch_stock_price_history",
        lambda stock_code, start_date, end_date: [
            {"date": "2025-01-10", "open": 100, "high": 110, "low": 95, "close": 108, "volume": 1000},
            {"date": "2025-01-13", "open": 108, "high": 118, "low": 101, "close": 116, "volume": 1400},
        ],
    )

    payload = build_insight_payload(
        fixture_path,
        "005930",
        start_date_iso="2025-01-10",
        end_date_iso="2025-01-10",
        price_source="fdr",
        stock_code_override="005930",
    )

    assert payload["visible_range_end"] == "2025-01-13"
    assert payload["chart"]["markers"][-1]["time"] == "2025-01-13"


def test_build_insight_payload_requires_stock_code_override(tmp_path: Path) -> None:
    fixture_path = _write_classification_fixture(tmp_path)

    with pytest.raises(ValueError, match="종목코드를 입력해야 합니다"):
        build_insight_payload(
            fixture_path,
            "005930",
            start_date_iso="2025-01-01",
            end_date_iso="2025-01-31",
            price_source="fdr",
            stock_code_override="",
        )


def test_default_stock_data_path_is_database_00_stock() -> None:
    assert STOCK_DATA_DIR.name == "00-stock"
    assert STOCK_DATA_DIR.parent.name == "database"
    assert QUANTI_DIR == STOCK_DATA_DIR / "by_item"


def test_list_quanti_stock_codes_accepts_parent_directory(tmp_path: Path, monkeypatch) -> None:
    quanti_root = tmp_path / "Quanti_unified"
    by_item = quanti_root / "by_item"
    by_item.mkdir(parents=True)
    (by_item / "S100310.parquet").write_bytes(b"stub")

    class _FakeSchema:
        names = ["date", "close_005930", "close_00A660"]

    class _FakeParquetFile:
        def __init__(self, path: Path) -> None:
            self.path = path
            self.schema_arrow = _FakeSchema()

    monkeypatch.setattr("finiq.market_desk.analytics.quanti.pq.ParquetFile", _FakeParquetFile)

    assert list_quanti_stock_codes(quanti_root) == ["005930", "00A660"]


def test_build_quanti_market_history_collapses_wide_market_item(tmp_path: Path) -> None:
    quanti_root = tmp_path / "Quanti_unified"
    by_item = quanti_root / "by_item"
    by_item.mkdir(parents=True)
    market_item = "S999999"
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-05", "2024-01-08"]),
            "테스트전자_005930": ["KOSDAQ", "KOSDAQ", "KOSPI", "KOSPI"],
            "다른회사_00A660": ["유가증권", "유가증권", None, None],
        }
    ).to_parquet(by_item / f"{market_item}.parquet", index=False)
    output_path = quanti_root / "market_history.parquet"

    summary = build_quanti_market_history(
        quanti_dir=quanti_root,
        market_item_code=market_item,
        output_path=output_path,
    )
    history = pd.read_parquet(output_path).sort_values(["stock_code", "start_date"])

    assert summary["stock_count"] == 2
    assert summary["interval_count"] == 3
    assert history[["stock_code", "market", "start_date", "end_date"]].to_dict("records") == [
        {"stock_code": "005930", "market": "코스닥", "start_date": date(2024, 1, 2), "end_date": date(2024, 1, 4)},
        {"stock_code": "005930", "market": "코스피", "start_date": date(2024, 1, 5), "end_date": date(2024, 1, 8)},
        {"stock_code": "00A660", "market": "코스피", "start_date": date(2024, 1, 2), "end_date": date(2024, 1, 3)},
    ]
    assert find_market_at(output_path, stock_code="005930", target_date=date(2024, 1, 4)) == "코스닥"
    assert find_market_at(output_path, stock_code="005930", target_date=date(2024, 1, 5)) == "코스피"
    assert find_market_at(output_path, stock_code="00A660", target_date=date(2024, 1, 4)) is None


def test_build_quanti_market_history_rejects_unknown_market_values(tmp_path: Path) -> None:
    by_item = tmp_path / "by_item"
    by_item.mkdir()
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"]),
            "테스트전자_005930": ["UNKNOWN_MARKET"],
        }
    ).to_parquet(by_item / "S999999.parquet", index=False)

    with pytest.raises(ValueError, match="not present in value_map"):
        build_quanti_market_history(
            quanti_dir=by_item,
            market_item_code="S999999",
            output_path=tmp_path / "market_history.parquet",
        )


def test_quanti_market_registry_helpers_load_market_item_and_values(tmp_path: Path) -> None:
    registry_path = tmp_path / "item_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "items": {
                    "S999999": {
                        "name": "시장구분",
                        "kind": "market",
                        "values": {"1": "코스피", "2": "코스닥"},
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    registry = load_quanti_item_registry(registry_path)
    item_code = market_item_from_registry(registry)

    assert item_code == "S999999"
    assert market_value_map_from_registry(registry, item_code)["2"] == "코스닥"
    assert market_value_map_from_registry(
        {item_code: {"name": "시장구분", "kind": "market"}}, item_code
    ) == {}


def test_check_existing_downloads_empty(tmp_path: Path) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    res = check_existing_downloads(str(tmp_path / "non_existent"))
    assert res == {"has_existing": False}

    res = check_existing_downloads(str(tmp_path))
    assert res == {"has_existing": False}

    (tmp_path / "20260230_20261231").mkdir()
    res = check_existing_downloads(str(tmp_path), verify_with_kind=False)
    assert res == {"has_existing": False}


def test_check_existing_downloads_reports_validation_exception_as_stale(
    tmp_path: Path, monkeypatch
) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads

    folder = tmp_path / "20260101_20260131"
    folder.mkdir()
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(
            _trusted_download_input_snapshot(
                start_date="2026-01-01", end_date="2026-01-31"
            )
        ),
        encoding="utf-8",
    )
    (folder / "001_post_page_00001.body").write_bytes(b"not inspected")
    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_existing._validate_single_folder",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("validation exploded")),
    )

    result = check_existing_downloads(str(tmp_path))

    assert result["has_existing"] is True
    assert result["earliest_date"] == "2026-01-01"
    assert result["latest_date"] == "2026-01-31"
    assert result["ranges"][0]["status"] == "stale"
    assert "validation exploded" in result["ranges"][0]["error_detail"]

def test_check_existing_downloads_yearly(tmp_path: Path, monkeypatch) -> None:
    import finiq.market_desk.web.features.downloads.kind_existing as kind_existing
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    query_state = {"active": 0, "maximum": 0}
    query_state_lock = threading.Lock()

    def current_count(_snapshot: dict[str, Any]) -> int:
        with query_state_lock:
            query_state["active"] += 1
            query_state["maximum"] = max(
                query_state["maximum"], query_state["active"]
            )
        time.sleep(0.03)
        with query_state_lock:
            query_state["active"] -= 1
        return 100

    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count",
        current_count,
    )
    original_inspect = kind_existing.inspect_download_directory_pages
    used_page_workers: list[int | None] = []

    def inspect_with_worker_capture(*args: Any, **kwargs: Any) -> dict[str, int]:
        used_page_workers.append(kwargs.get("validation_parallelism"))
        return original_inspect(*args, **kwargs)

    monkeypatch.setattr(
        kind_existing,
        "inspect_download_directory_pages",
        inspect_with_worker_capture,
    )

    folder1 = tmp_path / "20260101_20260501"
    folder1.mkdir()
    (folder1 / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    (folder1 / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(start_date="2026-01-01", end_date="2026-05-01")),
        encoding="utf-8"
    )

    folder2 = tmp_path / "20260502_20260601"
    folder2.mkdir()
    (folder2 / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    (folder2 / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(start_date="2026-05-02", end_date="2026-06-01")),
        encoding="utf-8"
    )

    progress_log = []
    res = check_existing_downloads(
        str(tmp_path),
        progress_callback=progress_log.append,
        parallel_workers=2,
    )
    assert res["has_existing"] is True
    assert res["earliest_date"] == "2026-01-01"
    assert res["latest_date"] == "2026-06-01"
    assert len(res["ranges"]) == 2
    assert res["ranges"][0]["start_date"] == "2026-01-01"
    assert res["ranges"][0]["end_date"] == "2026-05-01"
    assert res["ranges"][0]["status"] == "validated"
    assert res["ranges"][1]["start_date"] == "2026-05-02"
    assert res["ranges"][1]["end_date"] == "2026-06-01"
    assert res["ranges"][1]["status"] == "validated"
    assert progress_log[0] == (
        "KIND 현재 건수와 로컬 파일 비교 시작: 2개 범위, 2개 워커."
    )
    assert sum("개 범위 완료" in line for line in progress_log) == 2
    assert progress_log[-1] == "KIND 현재 건수와 로컬 파일 비교 완료."
    assert used_page_workers == [1, 1]
    assert query_state["maximum"] == 1


def test_check_existing_downloads_reuses_unchanged_folder_inspection(
    tmp_path: Path, monkeypatch
) -> None:
    import finiq.market_desk.web.features.downloads.kind_existing as kind_existing
    from finiq.market_desk.web.features.downloads.kind_existing import (
        check_existing_downloads,
    )
    from finiq.market_desk.web.features.downloads.kind_inspect import (
        inspect_download_output_directory_payload,
    )

    folder = tmp_path / "20260101_20261231"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(
            page_number=1, page_size=100, total_items=100
        )
    )
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(
            _trusted_download_input_snapshot(
                start_date="2026-01-01", end_date="2026-12-31"
            )
        ),
        encoding="utf-8",
    )
    inspection = inspect_download_output_directory_payload(
        {
            "mode": "yearly",
            "output_directory": str(tmp_path),
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "page_size": 100,
            "dry_run": True,
        }
    )

    monkeypatch.setattr(
        kind_existing,
        "get_current_kind_total_count",
        lambda _snapshot: 100,
    )
    monkeypatch.setattr(
        kind_existing,
        "inspect_download_directory_pages",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unchanged files must not be parsed twice")
        ),
    )

    result = check_existing_downloads(
        str(tmp_path),
        precomputed_download_statuses=inspection["download_statuses"],
    )

    assert result["ranges"][0]["status"] == "validated"
    assert result["ranges"][0]["local_count"] == 100


def test_check_existing_downloads_rechecks_changed_folder(
    tmp_path: Path, monkeypatch
) -> None:
    import finiq.market_desk.web.features.downloads.kind_existing as kind_existing
    from finiq.market_desk.web.features.downloads.kind_existing import (
        check_existing_downloads,
    )
    from finiq.market_desk.web.features.downloads.kind_inspect import (
        inspect_download_output_directory_payload,
    )

    folder = tmp_path / "20260101_20261231"
    folder.mkdir()
    body_path = folder / "001_post_page_00001.body"
    body_path.write_bytes(
        _build_download_result_page_html(
            page_number=1, page_size=100, total_items=100
        )
    )
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(
            _trusted_download_input_snapshot(
                start_date="2026-01-01", end_date="2026-12-31"
            )
        ),
        encoding="utf-8",
    )
    inspection = inspect_download_output_directory_payload(
        {
            "mode": "yearly",
            "output_directory": str(tmp_path),
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "page_size": 100,
            "dry_run": True,
        }
    )
    body_path.write_bytes(body_path.read_bytes() + b"\n")

    original_inspect = kind_existing.inspect_download_directory_pages
    inspection_calls = 0

    def inspect_with_count(*args, **kwargs):
        nonlocal inspection_calls
        inspection_calls += 1
        return original_inspect(*args, **kwargs)

    monkeypatch.setattr(
        kind_existing,
        "get_current_kind_total_count",
        lambda _snapshot: 100,
    )
    monkeypatch.setattr(
        kind_existing,
        "inspect_download_directory_pages",
        inspect_with_count,
    )

    result = check_existing_downloads(
        str(tmp_path),
        precomputed_download_statuses=inspection["download_statuses"],
    )

    assert inspection_calls == 1
    assert result["ranges"][0]["status"] == "validated"


def test_check_existing_downloads_keeps_completeness_check_for_reused_result(
    tmp_path: Path, monkeypatch
) -> None:
    import finiq.market_desk.web.features.downloads.kind_existing as kind_existing
    from finiq.market_desk.web.features.downloads.kind_existing import (
        check_existing_downloads,
    )
    from finiq.market_desk.web.features.downloads.kind_inspect import (
        inspect_download_output_directory_payload,
    )

    folder = tmp_path / "20260101_20261231"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(
            page_number=1, page_size=100, total_items=200
        )
    )
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(
            _trusted_download_input_snapshot(
                start_date="2026-01-01", end_date="2026-12-31"
            )
        ),
        encoding="utf-8",
    )
    inspection = inspect_download_output_directory_payload(
        {
            "mode": "yearly",
            "output_directory": str(tmp_path),
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "page_size": 100,
            "dry_run": True,
        }
    )

    monkeypatch.setattr(
        kind_existing,
        "get_current_kind_total_count",
        lambda _snapshot: 200,
    )
    monkeypatch.setattr(
        kind_existing,
        "inspect_download_directory_pages",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("stable incomplete files must use the first result")
        ),
    )

    result = check_existing_downloads(
        str(tmp_path),
        precomputed_download_statuses=inspection["download_statuses"],
    )

    assert result["ranges"][0]["status"] == "stale"
    assert "저장된 페이지는 1개" in result["ranges"][0]["error_detail"]
    assert "페이지네이션은 2페이지" in result["ranges"][0]["error_detail"]


def test_check_existing_downloads_preserves_each_range_filter_match(
    tmp_path: Path, monkeypatch
) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads

    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count",
        lambda snap: 100,
    )

    first_folder = tmp_path / "20260101_20260501"
    first_folder.mkdir()
    (first_folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    (first_folder / "kind_workflow.input.json").write_text(
        json.dumps(
            _trusted_download_input_snapshot(
                start_date="2026-01-01", end_date="2026-05-01"
            )
        ),
        encoding="utf-8",
    )

    second_folder = tmp_path / "20260502_20260601"
    second_folder.mkdir()
    (second_folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    second_snapshot = _trusted_download_input_snapshot(
        start_date="2026-05-02", end_date="2026-06-01"
    )
    second_snapshot["search_filters"] = [["marketType", "1"]]
    (second_folder / "kind_workflow.input.json").write_text(
        json.dumps(second_snapshot), encoding="utf-8"
    )

    res = check_existing_downloads(
        str(tmp_path),
        current_payload={
            "company_name": "",
            "submitter_name": "",
            "market_label": "전체",
            "securities_label": "전체",
            "disclosure_type_groups": {},
            "last_report_only": False,
        },
    )

    assert [item["filters_match"] for item in res["ranges"]] == [True, False]
    assert [item["metadata_status"] for item in res["ranges"]] == ["ok", "mismatch"]


def test_existing_download_filters_ignore_disclosure_code_order() -> None:
    from finiq.market_desk.web.features.downloads.kind_common import (
        _filters_payloads_match,
    )

    common = {
        "company_name": "",
        "submitter_name": "",
        "market_label": "전체",
        "securities_label": "전체",
        "last_report_only": False,
    }

    assert _filters_payloads_match(
        {**common, "disclosure_type_groups": {"01": ["0161", "0172"]}},
        {**common, "disclosure_type_groups": {"01": ["0172", "0161"]}},
    )
    assert _filters_payloads_match(
        {**common, "disclosure_type_groups": {}},
        {**common, "disclosure_type_groups": {"01": []}},
    )


def test_existing_downloads_reject_folder_metadata_date_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import (
        check_existing_downloads,
        detect_existing_downloads,
    )

    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count",
        lambda snap: (_ for _ in ()).throw(
            AssertionError("date mismatch must stop before querying KIND")
        ),
    )
    folder = tmp_path / "20260101_20261231"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(
            _trusted_download_input_snapshot(
                start_date="2025-01-01", end_date="2025-12-31"
            )
        ),
        encoding="utf-8",
    )

    detected = detect_existing_downloads(str(tmp_path))
    verified = check_existing_downloads(str(tmp_path))

    assert detected["ranges"][0]["status"] == "stale"
    assert verified["ranges"][0]["status"] == "stale"
    assert "differs from metadata date range" in detected["ranges"][0]["error_detail"]
    assert "differs from metadata date range" in verified["ranges"][0]["error_detail"]


def test_check_existing_downloads_single(tmp_path: Path, monkeypatch) -> None:
    import finiq.market_desk.web.features.downloads.kind_existing as kind_existing
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: 100)
    original_inspect = kind_existing.inspect_download_directory_pages
    used_page_workers: list[int | None] = []

    def inspect_with_worker_capture(*args: Any, **kwargs: Any) -> dict[str, int]:
        used_page_workers.append(kwargs.get("validation_parallelism"))
        return original_inspect(*args, **kwargs)

    monkeypatch.setattr(
        kind_existing,
        "inspect_download_directory_pages",
        inspect_with_worker_capture,
    )

    (tmp_path / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    (tmp_path / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(start_date="2026-02-01", end_date="2026-03-01")),
        encoding="utf-8"
    )

    res = check_existing_downloads(str(tmp_path), parallel_workers=2)
    assert res["has_existing"] is True
    assert res["earliest_date"] == "2026-02-01"
    assert res["latest_date"] == "2026-03-01"
    assert res["ranges"][0]["start_date"] == "2026-02-01"
    assert res["ranges"][0]["end_date"] == "2026-03-01"
    assert res["ranges"][0]["status"] == "validated"
    assert used_page_workers == [2]


def test_check_existing_downloads_validated(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: 100)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(start_date="2026-01-01", end_date="2026-05-01")),
        encoding="utf-8"
    )

    res = check_existing_downloads(str(tmp_path))
    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "validated"
    assert range_info["local_count"] == 100
    assert range_info["kind_count"] == 100
    assert range_info["error_detail"] is None


def test_check_existing_downloads_stale(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: 120)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(start_date="2026-01-01", end_date="2026-05-01")),
        encoding="utf-8"
    )

    res = check_existing_downloads(str(tmp_path))
    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "stale"
    assert range_info["local_count"] == 100
    assert range_info["kind_count"] == 120
    assert "differs from local count" in range_info["error_detail"]


def test_check_existing_downloads_stale_when_kind_count_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Local files must not be inspected after the KIND count request fails")

    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: None)
    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_existing.inspect_download_directory_pages",
        fail_if_called,
    )

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(start_date="2026-01-01", end_date="2026-05-01")),
        encoding="utf-8"
    )

    res = check_existing_downloads(str(tmp_path))
    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "stale"
    assert range_info["local_count"] is None
    assert range_info["kind_count"] is None
    assert "Failed to fetch current count" in range_info["error_detail"]


def test_check_existing_downloads_corrupted_local(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: 100)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    # Write a corrupted body file (non-HTML text so pagination detection returns None)
    (folder / "001_post_page_00001.body").write_bytes(b"corrupted html")
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(start_date="2026-01-01", end_date="2026-05-01")),
        encoding="utf-8"
    )

    res = check_existing_downloads(str(tmp_path))
    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "stale"
    assert range_info["local_count"] is None
    assert range_info["kind_count"] == 100
    assert "local count is null" in range_info["error_detail"]


def test_check_existing_downloads_missing_pages(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: 200)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    # Write page 1 and page 3, but page 2 is missing. Expected page size is 100, total items is 200.
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=200)
    )
    (folder / "001_post_page_00003.body").write_bytes(
        _build_download_result_page_html(page_number=3, page_size=100, total_items=200)
    )
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(start_date="2026-01-01", end_date="2026-05-01", page_size=100)),
        encoding="utf-8"
    )

    res = check_existing_downloads(str(tmp_path))
    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "stale"
    assert "Page completeness check failed" in range_info["error_detail"]


def test_check_existing_downloads_fast_validated(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    
    # We monkeypatch get_current_kind_total_count to raise an error to prove it is NOT called
    def fail_if_called(snap):
        raise RuntimeError("Should not be called in fast validation mode")
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fail_if_called)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    # Write page 1. Expected page size is 100, total items is 100, total pages is 1.
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(start_date="2026-01-01", end_date="2026-05-01", page_size=100)),
        encoding="utf-8"
    )

    res = check_existing_downloads(str(tmp_path), verify_with_kind=False)
    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "unverified"
    assert range_info["local_count"] == 100
    assert range_info["kind_count"] is None
    assert range_info["error_detail"] == "KIND verification skipped (fast check mode)."


def test_check_existing_downloads_fast_missing_pages(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    
    # We monkeypatch get_current_kind_total_count to raise an error to prove it is NOT called
    def fail_if_called(snap):
        raise RuntimeError("Should not be called in fast validation mode")
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fail_if_called)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    # Write page 1 and page 3, page 2 is missing. Expected page size is 100, total items is 300, total pages is 3.
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=300)
    )
    (folder / "001_post_page_00003.body").write_bytes(
        _build_download_result_page_html(page_number=3, page_size=100, total_items=300)
    )
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(start_date="2026-01-01", end_date="2026-05-01", page_size=100)),
        encoding="utf-8"
    )

    res = check_existing_downloads(str(tmp_path), verify_with_kind=False)
    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "stale"
    assert "Page numbers are not contiguous" in range_info["error_detail"] or "Page completeness check failed" in range_info["error_detail"]


def test_check_existing_downloads_fast_corrupted_local(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    
    # We monkeypatch get_current_kind_total_count to raise an error to prove it is NOT called
    def fail_if_called(snap):
        raise RuntimeError("Should not be called in fast validation mode")
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fail_if_called)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    # Write corrupted last page (non-HTML text)
    (folder / "001_post_page_00001.body").write_bytes(b"corrupted html")
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(start_date="2026-01-01", end_date="2026-05-01", page_size=100)),
        encoding="utf-8"
    )

    res = check_existing_downloads(str(tmp_path), verify_with_kind=False)
    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "stale"
    assert "Page completeness check failed" in range_info["error_detail"]


def test_check_existing_downloads_fast_corrupted_non_last_page(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads

    # We monkeypatch get_current_kind_total_count to raise an error to prove it is NOT called
    def fail_if_called(snap):
        raise RuntimeError("Should not be called in fast validation mode")
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fail_if_called)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    # Page 1 is corrupted, Page 2 is valid
    (folder / "001_post_page_00001.body").write_bytes(b"corrupted html")
    (folder / "001_post_page_00002.body").write_bytes(
        _build_download_result_page_html(page_number=2, page_size=100, total_items=200)
    )
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(start_date="2026-01-01", end_date="2026-05-01", page_size=100)),
        encoding="utf-8"
    )

    res = check_existing_downloads(str(tmp_path), verify_with_kind=False)
    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "unverified"
    assert range_info["error_detail"] == "KIND verification skipped (fast check mode)."


def test_check_existing_downloads_route_verify_with_kind_parsing(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.routers.download import create_download_router
    class DummyConfig:
        download_output_directory = None
        output_root = None
    
    router = create_download_router(DummyConfig())
    route_func = None
    for route in router.routes:
        if getattr(route, "path", None) == "/api/download/check-existing":
            route_func = route.endpoint
            break
            
    assert route_func is not None

    called_verify_with_kind = []
    called_current_payloads = []
    def mock_check_existing(path, *, verify_with_kind=True, current_payload=None):
        called_verify_with_kind.append(verify_with_kind)
        called_current_payloads.append(current_payload)
        return {"has_existing": False}

    monkeypatch.setattr("finiq.market_desk.web.routers.download.check_existing_downloads", mock_check_existing)

    # test JSON boolean false
    route_func({"output_directory": "/tmp", "verify_with_kind": False, "company_name": "삼성전자"})
    assert called_verify_with_kind[-1] is False
    assert called_current_payloads[-1]["company_name"] == "삼성전자"

    # test string boolean "false"
    route_func({"output_directory": "/tmp", "verify_with_kind": "false"})
    assert called_verify_with_kind[-1] is False

    # test string boolean "0"
    route_func({"output_directory": "/tmp", "verify_with_kind": "0"})
    assert called_verify_with_kind[-1] is False

    # test string boolean "no"
    route_func({"output_directory": "/tmp", "verify_with_kind": "no"})
    assert called_verify_with_kind[-1] is False

    # test JSON boolean true
    route_func({"output_directory": "/tmp", "verify_with_kind": True})
    assert called_verify_with_kind[-1] is True

    # test string boolean "true"
    route_func({"output_directory": "/tmp", "verify_with_kind": "true"})
    assert called_verify_with_kind[-1] is True

    # test default
    route_func({"output_directory": "/tmp"})
    assert called_verify_with_kind[-1] is True


def test_check_existing_downloads_fast_row_count_mismatch(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads

    # We monkeypatch get_current_kind_total_count to raise an error to prove it is NOT called
    def fail_if_called(snap):
        raise RuntimeError("Should not be called in fast validation mode")
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fail_if_called)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    
    # Page 1 has correct pagination info but only 1 row (1 openDisclsViewer) when 100 are expected
    html_content = """
    <html>
        <body>
            <div class="paging">
                전체 <em>200</em> 건 : <strong>1</strong>/2
            </div>
            <table summary="회사명, 공시제목">
                <tr>
                    <td>1</td>
                    <td>2026-01-01</td>
                    <td>회사A</td>
                    <td><a onclick="openDisclsViewer('123', '456')">공시A</a></td>
                    <td>제출인A</td>
                </tr>
            </table>
        </body>
    </html>
    """
    (folder / "001_post_page_00001.body").write_text(html_content, encoding="euc-kr")

    # Page 2 is valid
    (folder / "001_post_page_00002.body").write_bytes(
        _build_download_result_page_html(page_number=2, page_size=100, total_items=200)
    )

    (folder / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(start_date="2026-01-01", end_date="2026-05-01", page_size=100)),
        encoding="utf-8"
    )

    res = check_existing_downloads(str(tmp_path), verify_with_kind=False)
    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "unverified"
    assert range_info["error_detail"] == "KIND verification skipped (fast check mode)."
    assert range_info["metadata_missing"] is False


def test_check_existing_downloads_detects_metadata_missing(tmp_path: Path) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    # Notice kind_workflow.input.json is intentionally missing

    with pytest.raises(ValueError, match="metadata is missing"):
        check_existing_downloads(str(tmp_path), verify_with_kind=False)


def test_detect_existing_downloads_is_metadata_only(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import detect_existing_downloads

    def fail_if_called(*args, **kwargs):
        raise AssertionError("detect must not parse downloaded pages or call KIND")

    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fail_if_called)
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.inspect_download_directory_pages", fail_if_called)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(b"corrupted html")
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot()), encoding="utf-8"
    )

    res = detect_existing_downloads(
        str(tmp_path),
        current_payload={
            "start_date": "2026-01-01",
            "end_date": "2026-05-01",
            "company_name": "",
            "submitter_name": "",
            "market_label": "전체",
            "securities_label": "전체",
            "disclosure_type_groups": {},
            "last_report_only": False,
            "page_size": 100,
        },
    )

    assert res["has_existing"] is True
    assert res["ranges"][0]["status"] == "unverified"
    assert res["ranges"][0]["metadata_status"] == "ok"
    assert res["ranges"][0]["filters_match"] is True
    assert res["saved_filters"]["market_label"] == "전체"
    assert res["saved_filters_consistent"] is True
    assert res["ranges"][0]["start_date"] == "2026-01-01"
    assert res["ranges"][0]["end_date"] == "2026-05-01"
    assert res["ranges"][0]["local_count"] is None
    assert res["ranges"][0]["kind_count"] is None


def test_detect_existing_downloads_reports_inconsistent_saved_filters(
    tmp_path: Path,
) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import detect_existing_downloads

    first = tmp_path / "20260101_20260501"
    second = tmp_path / "20260502_20261231"
    first.mkdir()
    second.mkdir()
    for folder in (first, second):
        (folder / "001_post_page_00001.body").write_bytes(b"metadata-only")

    first_snapshot = _trusted_download_input_snapshot()
    second_snapshot = _trusted_download_input_snapshot(
        start_date="2026-05-02",
        end_date="2026-12-31",
    )
    second_snapshot["search_filters"] = [["searchCorpName", "다른 회사"]]
    (first / "kind_workflow.input.json").write_text(
        json.dumps(first_snapshot), encoding="utf-8"
    )
    (second / "kind_workflow.input.json").write_text(
        json.dumps(second_snapshot, ensure_ascii=False), encoding="utf-8"
    )

    res = detect_existing_downloads(str(tmp_path))

    assert res["has_existing"] is True
    assert res["saved_filters_consistent"] is False


def test_inspect_folder_rejects_missing_metadata_without_repair(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from finiq.market_desk.web.features.downloads.kind_inspect import inspect_download_output_directory_payload

    def fail_if_called(snapshot):
        raise AssertionError("Missing metadata must not be reconstructed or queried")

    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fail_if_called)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )

    with pytest.raises(ValueError, match="metadata is missing"):
        inspect_download_output_directory_payload(
            {
                "mode": "yearly",
                "output_directory": str(tmp_path),
                "start_date": "2026-01-01",
                "end_date": "2026-05-01",
                "company_name": "",
                "submitter_name": "",
                "market_label": "전체",
                "securities_label": "전체",
                "disclosure_type_groups": {},
                "last_report_only": False,
                "page_size": 100,
                "dry_run": True,
            }
        )

    assert not (folder / "kind_workflow.input.json").exists()


def test_inspect_folder_rejects_metadata_without_page_size(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from finiq.market_desk.web.features.downloads.kind_inspect import inspect_download_output_directory_payload

    def fail_if_called(snapshot):
        raise AssertionError("Invalid metadata must not be reconstructed or queried")

    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fail_if_called)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    snapshot = _trusted_download_input_snapshot(
        start_date="2026-01-01", end_date="2026-05-01", page_size=100
    )
    snapshot.pop("page_size")
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(snapshot), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="missing required fields: page_size"):
        inspect_download_output_directory_payload(
            {
                "mode": "yearly",
                "output_directory": str(tmp_path),
                "start_date": "2026-01-01",
                "end_date": "2026-05-01",
                "company_name": "",
                "submitter_name": "",
                "market_label": "전체",
                "securities_label": "전체",
                "disclosure_type_groups": {},
                "last_report_only": False,
                "page_size": 100,
                "dry_run": True,
            }
        )

    assert (folder / "kind_workflow.input.json").is_file()


def test_check_existing_downloads_does_not_infer_missing_metadata_from_incomplete_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads

    def fail_if_called(snapshot):
        raise RuntimeError("Incomplete current payload must not be used for KIND validation")

    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fail_if_called)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )

    with pytest.raises(ValueError, match="metadata is missing"):
        check_existing_downloads(
            str(tmp_path),
            current_payload={"output_directory": str(tmp_path)},
        )


def test_check_existing_downloads_rejects_obsolete_metadata(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads

    def fail_if_called(snapshot):
        raise RuntimeError("Obsolete metadata must not be used for KIND validation")

    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fail_if_called)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    snapshot = _trusted_download_input_snapshot()
    snapshot["format"] = "finiq_kind_workflow_input_v0"
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(snapshot), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="metadata format is obsolete"):
        check_existing_downloads(str(tmp_path))


def test_detect_existing_downloads_rejects_corrupted_metadata(tmp_path: Path) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import detect_existing_downloads

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(b"corrupted html")
    (folder / "kind_workflow.input.json").write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="metadata is corrupted"):
        detect_existing_downloads(str(tmp_path))


def test_download_status_rejects_missing_metadata_before_reading_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from finiq.market_desk.web.features.downloads import kind_api

    (tmp_path / "001_post_page_00001.body").write_bytes(b"not parsed")
    monkeypatch.setattr(
        kind_api,
        "_download_integrity_status",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("body must not be read before metadata validation")
        ),
    )

    with pytest.raises(ValueError, match="metadata is missing"):
        kind_api.build_download_status_payload({"output_directory": str(tmp_path)})


def test_check_existing_downloads_rejects_missing_date_range_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads

    def fail_if_called(snapshot):
        raise AssertionError("Invalid metadata must not be completed from the current request")

    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fail_if_called)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    snapshot = _trusted_download_input_snapshot(
        start_date="2026-01-01", end_date="2026-05-01", page_size=100
    )
    snapshot.pop("start_date")
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(snapshot), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="missing required fields: start_date"):
        check_existing_downloads(
            str(tmp_path),
            current_payload={
                "start_date": "2026-01-01",
                "end_date": "2026-05-01",
                "company_name": "삼성전자",
                "submitter_name": "",
                "market_label": "전체",
                "securities_label": "전체",
                "disclosure_type_groups": {},
                "last_report_only": True,
                "page_size": 100,
            },
        )


def test_create_metadata_route_is_not_registered() -> None:
    from finiq.market_desk.web.routers.download import create_download_router
    class DummyConfig:
        download_output_directory = None
        output_root = None

    router = create_download_router(DummyConfig())
    assert all(
        getattr(route, "path", None) != "/api/download/create-metadata"
        for route in router.routes
    )


def test_check_existing_downloads_single_missing_metadata_fails(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: 100)

    html_content = """
    <table class="list">
        <tr>
            <td>1</td>
            <td>2026-01-05</td>
            <td>회사A</td>
            <td><a>공시A</a></td>
            <td>제출인A</td>
        </tr>
    </table>
    """
    (tmp_path / "001_post_page_00001.body").write_text(html_content, encoding="utf-8")

    with pytest.raises(ValueError, match="metadata is missing"):
        check_existing_downloads(str(tmp_path), verify_with_kind=False)
