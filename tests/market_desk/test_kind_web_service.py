from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

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
)
from finiq.market_desk.web.features.disclosures.html_cleanup import (
    check_disclosure_html_output_directory_payload,
    clean_disclosure_html_output_directory_payload,
    write_disclosure_html_manifest_payload,
)
from finiq.market_desk.web.features.disclosures.html_common import (
    HTML_MANIFEST_FILENAME,
    cancel_disclosure_html_download,
    collect_acpt_numbers_from_json,
)
from finiq.market_desk.web.features.disclosures.html_content_download import (
    download_disclosure_html_contents_payload,
)
from finiq.market_desk.web.features.disclosures.html_content_merge import merge_disclosure_content_html_payload
from finiq.market_desk.web.features.disclosures.html_download import (
    download_disclosure_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_external_compress import compress_disclosure_external_html_payload
from finiq.market_desk.web.features.downloads.kind_inspect import inspect_download_output_directory_payload
import finiq.market_desk.web.features.disclosures.html_sections as disclosure_html_sections
from finiq.market_desk.web.features.disclosures.html_parse_changes import (
    build_parse_change_log_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_common import (
    PARSER_REGISTRY,
    cancel_disclosure_html_parse,
    parse_disclosure_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_export import (
    build_parse_export_xlsx,
)
from finiq.market_desk.web.features.disclosures.html_parse_preview import (
    build_parse_filter_candidates_payload,
    build_parse_preview_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_summary import (
    build_bond_parse_summary_payload,
)
from finiq.market_desk.web.features.disclosures.html_sections import (
    DEFAULT_HTML_SECTION_WORKERS,
    HtmlSectionSummary,
    inspect_disclosure_html_sections_payload,
    list_disclosure_html_section_sources_payload,
    parse_html_section_worker_count,
    save_disclosure_html_sections_payload,
    split_disclosure_html_section_source_payload,
    split_content_html_sections,
    summarize_disclosure_html_section_kinds_payload,
)
from finiq.market_desk.web.html_parsers.bond_issuance import parse_bond_issuance
from finiq.market_desk.web.html_parsers.common import (
    expand_table,
    parse_html_document,
    parse_int,
    parse_ints,
)
from finiq.market_desk.web.features.disclosures.table_export import build_disclosure_table_payload
from finiq.market_desk.analytics.quanti import list_quanti_stock_codes
from finiq.market_desk.web.html_parsers.rights_issuance import parse_rights_issuance
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
    title = _RIGHTS_MANIFEST_TITLES.get(fixture_path.stem.split("_", 1)[0])
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
HTML_PARSERS_DIR = REPO_ROOT / "src" / "finiq" / "market_desk" / "web" / "html_parsers"
GUI_APP_DIR = REPO_ROOT / "frontend" / "finiq_GUI" / "apps" / "market-desk" / "src" / "app"
GUI_HTML_DOWNLOAD_PAGE = GUI_APP_DIR / "html-download" / "page.tsx"
GUI_HTML_DOWNLOAD_COMPONENT = GUI_APP_DIR / "html-download" / "_components" / "HtmlDownloadPageView.tsx"
GUI_HTML_CONTENT_DOWNLOAD_PAGE = GUI_APP_DIR / "html-content-download" / "page.tsx"
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


def _nested_sqlite_manifest_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}_shards") / path.name


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


def _trusted_download_input_snapshot(
    *,
    start_date: str = "2026-01-01",
    end_date: str = "2026-05-01",
    page_size: int = 100,
) -> dict[str, object]:
    return {
        "request_headers": {"User-Agent": "pytest"},
        "start_date": start_date,
        "end_date": end_date,
        "page_size": page_size,
        "search_filters": [],
        "disclosure_type_groups": {},
        "last_report_only": False,
        "include_previous_disclosures": None,
    }


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
    fixture_path = tmp_path / "kind.company_classification.sample.json"
    return write_company_classification_artifact(
        fixture_path,
        payload or _classification_fixture_payload(),
        compact=False,
    )


def _write_multiyear_classification_fixture(tmp_path: Path) -> Path:
    payload = _classification_fixture_payload()
    payload["companies"][0]["disclosures"][0]["disclosed_at"] = "2023-01-02 09:00:00"
    payload["companies"][0]["disclosures"][1]["disclosed_at"] = "2024-01-10 09:00:00"
    payload["companies"][0]["disclosures"][2]["disclosed_at"] = "2025-01-15 09:00:00"
    return _write_classification_fixture(tmp_path, payload)


def _write_source_body_fixture(tmp_path: Path) -> Path:
    source_dir = tmp_path / "20250101_20250131"
    source_dir.mkdir()
    (source_dir / "001_post_page_00001.body").write_text(
        """
        <html><body>
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
    fixture_path = _write_classification_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "classification_path": str(fixture_path),
            "title_keyword": "전환사채",
            "start_date": "2025-01-01",
            "end_date": "2025-01-05",
        }
    )

    assert payload["format"] == "kind_disclosure_filter_v1"
    assert payload["summary"]["matched_disclosures"] == 1
    assert payload["disclosures"][0]["acpt_no"] == "1"
    assert payload["disclosures"][0]["company_name"] == "테스트전자"
    assert payload["unique_titles"] == ["[정정]전환사채발행결정"]


def test_filter_disclosures_payload_resolves_classification_from_root_directory(tmp_path: Path) -> None:
    fixture_path = _write_classification_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "root_directory": str(tmp_path),
            "title_keyword": "전환사채",
        }
    )

    assert payload["source_classification_path"] == str(fixture_path.resolve())
    assert payload["summary"]["matched_disclosures"] == 1
    assert payload["disclosures"][0]["acpt_no"] == "1"


def test_filter_disclosures_payload_reads_source_folder_without_classification_json(tmp_path: Path) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    progress_events = []

    payload = filter_disclosures_payload(
        {
            "root_directory": str(source_root),
            "filter_blocks": [
                {
                    "field": "title",
                    "operator": "contains",
                    "value": "전환사채",
                }
            ],
        },
        progress_callback=progress_events.append,
    )

    assert payload["source_type"] == "source_folder"
    assert payload["source_classification_path"] == ""
    assert payload["summary"]["source_body_files"] == 1
    assert payload["summary"]["matched_disclosures"] == 1
    assert payload["disclosures"][0]["acpt_no"] == "20250102000001"
    assert payload["disclosures"][0]["doc_no"] == "20250102009999"
    assert payload["disclosures"][0]["company_name"] == "테스트전자"
    assert payload["disclosures"][0]["title"] == "[정정]전환사채발행결정"
    assert payload["disclosures"][0]["title_attr"] == "전환사채발행결정"
    assert payload["disclosures"][0]["title_flags"] == ["정정"]
    assert payload["disclosures"][0]["is_correction_report"] is True
    assert payload["disclosures"][0]["has_later_correction"] is True
    assert payload["disclosures"][0]["source_page"] == 1
    assert any(event["unit_label"] == "폴더" and event["completed"] == 1 for event in progress_events)
    assert any(event["unit_label"] == "공시" and event["total"] == 2 for event in progress_events)


def test_filter_disclosures_payload_rejects_high_risk_source_root() -> None:
    root = Path(Path.cwd().anchor).resolve()

    with pytest.raises(ValueError, match="high-risk root_directory"):
        filter_disclosures_payload({"root_directory": str(root)})


def test_filter_disclosures_payload_reads_sqlite_manifest_directory(tmp_path: Path) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    sqlite_root = tmp_path / "kind_sqlite"
    output_path = sqlite_root / "kind.sqlite_manifest.json"
    manifest_path = _nested_sqlite_manifest_path(output_path)
    build_disclosure_table_payload(
        {
            "classification_path": str(source_root),
            "output_path": str(output_path),
        }
    )

    payload = filter_disclosures_payload(
        {
            "root_directory": str(sqlite_root),
            "filter_blocks": [
                {
                    "field": "title",
                    "operator": "contains",
                    "value": "전환사채",
                }
            ],
            "include_html_download_acpt_numbers": True,
        }
    )

    assert payload["source_type"] == "sqlite_manifest"
    assert payload["source_sqlite_manifest_path"] == str(manifest_path.resolve())
    assert payload["summary"]["source_disclosures"] == 2
    assert payload["summary"]["matched_disclosures"] == 1
    assert payload["disclosures"][0]["acpt_no"] == "20250102000001"
    assert payload["disclosures"][0]["doc_no"] == "20250102009999"
    assert payload["disclosures"][0]["title"] == "[정정]전환사채발행결정"
    assert payload["disclosures"][0]["title_flags"] == ["정정"]
    assert payload["disclosures"][0]["is_correction_report"] == 1
    assert payload["disclosures"][0]["has_later_correction"] == 1
    assert payload["html_download_acpt_numbers"] == ["20250102000001"]


def test_filter_disclosures_payload_reads_sqlite_manifest_shard_directory(tmp_path: Path) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    sqlite_root = tmp_path / "kind_sqlite"
    output_path = sqlite_root / "kind.sqlite_manifest.json"
    manifest_path = _nested_sqlite_manifest_path(output_path)
    build_disclosure_table_payload(
        {
            "classification_path": str(source_root),
            "output_path": str(output_path),
        }
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for shard in manifest["shards"]:
        shard["path"] = str(tmp_path / "stale" / "kind.sqlite_manifest_shards" / Path(shard["path"]).name)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    payload = filter_disclosures_payload(
        {
            "root_directory": str(sqlite_root / "kind.sqlite_manifest_shards"),
            "filter_blocks": [
                {
                    "field": "title",
                    "operator": "contains",
                    "value": "전환사채",
                }
            ],
        }
    )

    assert payload["source_type"] == "sqlite_manifest"
    assert payload["source_sqlite_manifest_path"] == str(manifest_path.resolve())
    assert payload["summary"]["source_disclosures"] == 2
    assert payload["summary"]["matched_disclosures"] == 1
    assert payload["disclosures"][0]["acpt_no"] == "20250102000001"


def test_filter_disclosures_payload_reads_nested_kind_sqlite_manifest(tmp_path: Path) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    root = tmp_path / "kind_kosdaq"
    sqlite_root = root / "kind_sqlite"
    output_path = sqlite_root / "kind_kosdaq.sqlite_manifest.json"
    manifest_path = _nested_sqlite_manifest_path(output_path)
    build_disclosure_table_payload(
        {
            "classification_path": str(source_root),
            "output_path": str(output_path),
        }
    )

    payload = filter_disclosures_payload(
        {
            "root_directory": str(root),
            "filter_blocks": [
                {
                    "field": "title",
                    "operator": "contains",
                    "value": "전환사채",
                }
            ],
        }
    )

    assert payload["source_type"] == "sqlite_manifest"
    assert payload["source_sqlite_manifest_path"] == str(manifest_path.resolve())
    assert payload["summary"]["source_body_files"] == 0
    assert payload["summary"]["matched_disclosures"] == 1
    assert payload["disclosures"][0]["acpt_no"] == "20250102000001"


def test_filter_disclosures_payload_reads_sqlite_manifest_without_row_no_column(tmp_path: Path) -> None:
    sqlite_root = tmp_path / "kind_sqlite"
    shard_root = sqlite_root / "kind.sqlite_manifest_shards"
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
    manifest_path = shard_root / "kind.sqlite_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_table_manifest_v1",
                "table_name": "disclosures",
                "summary": {"companies": 1, "disclosures": 1, "shards": 1},
                "shards": [
                    {
                        "year": "2025",
                        "relative_path": shard_path.name,
                        "companies": 1,
                        "disclosures": 1,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = filter_disclosures_payload(
        {
            "root_directory": str(sqlite_root),
            "filter_blocks": [
                {
                    "field": "title",
                    "operator": "contains",
                    "value": "전환사채",
                }
            ],
        }
    )

    assert payload["summary"]["matched_disclosures"] == 1
    assert payload["disclosures"][0]["row_no"] is None
    assert payload["disclosures"][0]["acpt_no"] == "1"


def test_filter_disclosures_payload_rejects_direct_legacy_sqlite_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "kind.sqlite_manifest.json"
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

    with pytest.raises(ValueError, match=r"must be inside a \*_shards directory"):
        filter_disclosures_payload({"classification_path": str(manifest_path)})


def test_filter_disclosures_payload_rejects_sqlite_manifest_count_mismatch(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    sqlite_root = tmp_path / "kind_sqlite"
    output_path = sqlite_root / "kind.sqlite_manifest.json"
    manifest_path = _nested_sqlite_manifest_path(output_path)
    build_disclosure_table_payload(
        {
            "classification_path": str(source_root),
            "output_path": str(output_path),
        }
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["shards"][0]["disclosures"] = 3
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="SQLite shard disclosure count mismatch"):
        filter_disclosures_payload({"root_directory": str(sqlite_root)})


def test_filter_disclosures_payload_reports_json_progress(tmp_path: Path) -> None:
    fixture_path = _write_classification_fixture(tmp_path)
    progress_events = []

    payload = filter_disclosures_payload(
        {
            "classification_path": str(fixture_path),
            "progress_interval": 1,
        },
        progress_callback=progress_events.append,
    )

    assert payload["source_type"] == "classification"
    assert payload["summary"]["matched_disclosures"] == 3
    assert any(event["unit_label"] == "JSON 항목" and event["completed"] == 1 for event in progress_events)
    assert any(event["unit_label"] == "공시" and event["total"] == 3 for event in progress_events)


def test_filter_disclosures_payload_supports_title_include_and_exclude_keywords(tmp_path: Path) -> None:
    fixture_path = _write_classification_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "classification_path": str(fixture_path),
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
    fixture_path = _write_classification_fixture(tmp_path, payload)

    filtered_payload = filter_disclosures_payload(
        {
            "classification_path": str(fixture_path),
            "filter_blocks": [
                {
                    "field": "title",
                    "operator": "contains",
                    "value": "공정공시공시내용",
                    "clean_search": True,
                }
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
    fixture_path = _write_classification_fixture(tmp_path, payload)

    filtered_payload = filter_disclosures_payload({"classification_path": str(fixture_path)})

    assert filtered_payload["unique_titles"][0] == "공정공시공시내용"
    assert list(filtered_payload).index("unique_titles") < list(filtered_payload).index("disclosures")


def test_filter_disclosures_payload_can_return_without_limit(tmp_path: Path) -> None:
    fixture_path = _write_classification_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "classification_path": str(fixture_path),
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
    fixture_path = _write_classification_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "classification_path": str(fixture_path),
            "limit_unlimited": True,
            "return_limit": 1,
            "include_html_download_acpt_numbers": True,
        }
    )

    assert payload["filters"]["limit"] is None
    assert payload["filters"]["limit_unlimited"] is True
    assert payload["filters"]["return_limit"] is None
    assert payload["summary"]["matched_disclosures"] == 3
    assert payload["summary"]["returned_disclosures"] == 3
    assert [disclosure["acpt_no"] for disclosure in payload["disclosures"]] == ["3", "2", "1"]
    assert payload["html_download_acpt_numbers"] == ["3", "2", "1"]


def test_filter_disclosures_payload_deduplicates_by_disclosure_identity(tmp_path: Path) -> None:
    payload = _classification_fixture_payload()
    payload["companies"][0]["disclosures"].append(dict(payload["companies"][0]["disclosures"][0]))
    payload["summary"]["disclosures"] = 4
    fixture_path = _write_classification_fixture(tmp_path, payload)

    filtered_payload = filter_disclosures_payload(
        {
            "classification_path": str(fixture_path),
            "include_html_download_acpt_numbers": True,
        }
    )

    assert filtered_payload["summary"]["source_disclosures"] == 4
    assert filtered_payload["summary"]["matched_disclosures"] == 3
    assert filtered_payload["summary"]["returned_disclosures"] == 3
    assert filtered_payload["summary"]["duplicate_disclosures"] == 1
    assert [disclosure["acpt_no"] for disclosure in filtered_payload["disclosures"]] == ["3", "2", "1"]
    assert filtered_payload["unique_titles"] == ["주주총회소집결의", "기타 주요경영사항", "[정정]전환사채발행결정"]
    assert filtered_payload["html_download_acpt_numbers"] == ["3", "2", "1"]


def test_filter_disclosures_payload_supports_title_boolean_expression(tmp_path: Path) -> None:
    fixture_path = _write_classification_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "classification_path": str(fixture_path),
            "title_expression": '"전환사채" AND "발행결정" OR ("주주총회" AND NOT "정정")',
        }
    )

    assert [disclosure["acpt_no"] for disclosure in payload["disclosures"]] == ["3", "1"]


def test_filter_disclosures_payload_supports_field_filter_blocks(tmp_path: Path) -> None:
    fixture_path = _write_classification_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "classification_path": str(fixture_path),
            "filter_blocks": [
                {
                    "field": "title",
                    "operator": "contains",
                    "value": "전환사채",
                },
                {
                    "connector": "OR",
                    "open_count": 1,
                    "field": "market",
                    "operator": "equals",
                    "value": "코스피",
                },
                {
                    "connector": "AND",
                    "field": "title",
                    "operator": "contains",
                    "value": "주주총회",
                    "close_count": 1,
                },
            ],
        }
    )

    assert [disclosure["acpt_no"] for disclosure in payload["disclosures"]] == ["3", "1"]


def test_filter_disclosures_payload_can_ignore_spaces_in_block_values(tmp_path: Path) -> None:
    fixture_path = _write_classification_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "classification_path": str(fixture_path),
            "filter_blocks": [
                {
                    "field": "title",
                    "operator": "contains",
                    "value": "전환 사채 발행",
                    "ignore_spaces": True,
                },
            ],
        }
    )

    assert [disclosure["acpt_no"] for disclosure in payload["disclosures"]] == ["1"]


def test_filter_disclosures_payload_supports_nested_bond_issuance_filter_blocks(tmp_path: Path) -> None:
    fixture_path = _write_classification_fixture(tmp_path)

    payload = filter_disclosures_payload(
        {
            "classification_path": str(fixture_path),
            "filter_blocks": [
                {
                    "open_count": 2,
                    "field": "title",
                    "operator": "contains",
                    "value": "전환사채",
                    "ignore_spaces": True,
                },
                {
                    "connector": "OR",
                    "field": "title",
                    "operator": "contains",
                    "value": "교환사채",
                    "ignore_spaces": True,
                    "close_count": 1,
                },
                {
                    "connector": "OR",
                    "field": "title",
                    "operator": "contains",
                    "value": "신주인수권부사채",
                    "ignore_spaces": True,
                    "close_count": 1,
                },
                {
                    "connector": "AND",
                    "field": "title",
                    "operator": "contains",
                    "value": "발행",
                    "ignore_spaces": True,
                },
            ],
        }
    )

    assert [disclosure["acpt_no"] for disclosure in payload["disclosures"]] == ["1"]


def test_filter_disclosures_payload_supports_exact_match_operator(tmp_path: Path) -> None:
    fixture_path = _write_classification_fixture(tmp_path)

    partial_payload = filter_disclosures_payload(
        {
            "classification_path": str(fixture_path),
            "filter_blocks": [
                {
                    "field": "title",
                    "operator": "exact_match",
                    "value": "전환사채",
                },
            ],
        }
    )
    exact_payload = filter_disclosures_payload(
        {
            "classification_path": str(fixture_path),
            "filter_blocks": [
                    {
                        "field": "title",
                        "operator": "exact_match",
                        "value": "[정정]전환사채발행결정",
                    },
                ],
            }
    )

    assert partial_payload["disclosures"] == []
    assert [disclosure["acpt_no"] for disclosure in exact_payload["disclosures"]] == ["1"]


def test_build_disclosure_table_payload_writes_yearly_sqlite_manifest(tmp_path: Path) -> None:
    fixture_path = _write_classification_fixture(tmp_path)
    output_path = tmp_path / "kind.disclosures.sqlite_manifest.json"
    manifest_path = _nested_sqlite_manifest_path(output_path)

    payload = build_disclosure_table_payload(
        {
            "classification_path": str(fixture_path),
            "output_path": str(output_path),
            "table_name": "disclosures",
        }
    )

    assert payload["format"] == "finiq_disclosure_table_build_v1"
    assert payload["summary"]["companies"] == 1
    assert payload["summary"]["disclosures"] == 3
    assert payload["summary"]["shards"] == 1
    assert not output_path.exists()
    assert manifest_path.exists()
    assert payload["output_path"] == str(manifest_path.resolve())
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["format"] == "finiq_disclosure_table_manifest_v1"
    assert manifest["shards"][0]["year"] == "2025"

    shard_path = Path(manifest["shards"][0]["path"])
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
        0,
        "1",
        "10",
    )
    assert metadata["format"] == "finiq_disclosure_table_sqlite"
    assert metadata["shard_format"] == "finiq_disclosure_table_sqlite_shard"
    assert metadata["shard_year"] == "2025"
    assert metadata["table_name"] == "disclosures"


def test_build_disclosure_table_payload_writes_yearly_shards_in_parallel(tmp_path: Path) -> None:
    fixture_path = _write_multiyear_classification_fixture(tmp_path)
    output_path = tmp_path / "kind.disclosures.sqlite_manifest.json"
    manifest_path = _nested_sqlite_manifest_path(output_path)
    progress_log: list[str] = []

    payload = build_disclosure_table_payload(
        {
            "classification_path": str(fixture_path),
            "output_path": str(output_path),
            "table_name": "disclosures",
            "table_workers": 2,
        },
        progress_callback=progress_log.append,
    )

    assert payload["summary"]["disclosures"] == 3
    assert payload["summary"]["shards"] == 3
    assert [shard["year"] for shard in payload["shards"]] == ["2023", "2024", "2025"]
    assert any("workers=2" in message for message in progress_log)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [shard["year"] for shard in manifest["shards"]] == ["2023", "2024", "2025"]
    for shard in manifest["shards"]:
        shard_path = Path(shard["path"])
        connection = sqlite3.connect(shard_path)
        try:
            row_count = connection.execute("SELECT COUNT(*) FROM disclosures").fetchone()[0]
        finally:
            connection.close()
        assert row_count == 1


def test_build_disclosure_table_payload_cancelled_parallel_shards_skips_manifest(tmp_path: Path) -> None:
    fixture_path = _write_multiyear_classification_fixture(tmp_path)
    output_path = tmp_path / "kind.disclosures.sqlite_manifest.json"
    manifest_path = _nested_sqlite_manifest_path(output_path)
    should_cancel = False

    def progress_callback(message: str) -> None:
        nonlocal should_cancel
        if "샤드 생성 예약" in message:
            should_cancel = True

    def cancel_check() -> bool:
        return should_cancel

    with pytest.raises(RuntimeError, match="Job cancelled"):
        build_disclosure_table_payload(
            {
                "classification_path": str(fixture_path),
                "output_path": str(output_path),
                "table_name": "disclosures",
                "table_workers": 2,
            },
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    assert not output_path.exists()
    assert not manifest_path.exists()


def test_build_disclosure_table_payload_accepts_nested_folder_path(tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "current_shape"
    nested.mkdir(parents=True)
    fixture_path = _write_classification_fixture(nested)

    payload = build_disclosure_table_payload(
        {
            "classification_path": str(nested),
        }
    )

    assert payload["source_classification_path"] == str(fixture_path.resolve())
    assert Path(payload["output_path"]).name == "kind.company_classification.sample.sqlite_manifest.json"
    assert Path(payload["shards"][0]["path"]).name == "2025.sqlite"
    assert payload["summary"]["disclosures"] == 3


def test_build_disclosure_table_payload_rejects_unloaded_classification_disclosures(
    tmp_path: Path,
) -> None:
    payload = _classification_fixture_payload()
    payload["summary"]["disclosures"] = 4
    fixture_path = _write_classification_fixture(tmp_path, payload)

    with pytest.raises(ValueError, match="summary does not match loaded disclosures"):
        build_disclosure_table_payload({"classification_path": str(fixture_path)})


def test_build_disclosure_table_payload_rejects_malformed_disclosure_item(
    tmp_path: Path,
) -> None:
    fixture_path = _write_classification_fixture(tmp_path)
    payload = _classification_fixture_payload()
    payload["companies"][0]["disclosures"].append("not-a-disclosure")
    payload["summary"]["disclosures"] = 4
    with sqlite3.connect(fixture_path) as connection:
        connection.execute(
            "UPDATE metadata SET value = ? WHERE key = 'summary'",
            (json.dumps(payload["summary"], ensure_ascii=False),),
        )
        connection.execute(
            "UPDATE companies SET raw_json = ? WHERE company_key = ?",
            (
                json.dumps(payload["companies"][0], ensure_ascii=False),
                "005930",
            ),
        )

    with pytest.raises(ValueError, match=r"disclosures\[3\] must be an object"):
        build_disclosure_table_payload({"classification_path": str(fixture_path)})


def test_build_disclosure_table_payload_accepts_source_body_folder(tmp_path: Path) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    output_path = tmp_path / "kind.sqlite_manifest.json"
    manifest_path = _nested_sqlite_manifest_path(output_path)

    payload = build_disclosure_table_payload(
        {
            "classification_path": str(source_root),
            "output_path": str(output_path),
        }
    )

    assert payload["source_type"] == "source_folder"
    assert payload["summary"]["disclosures"] == 2
    assert payload["summary"]["shards"] == 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_type"] == "source_folder"
    assert manifest["shards"][0]["year"] == "2025"


def test_build_disclosure_table_payload_recovers_misnested_resource_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "FINIQ"
    source_parent = workspace / "resources" / "kind_kosdaq"
    source_parent.mkdir(parents=True)
    source_root = _write_source_body_fixture(source_parent)
    package_dir = workspace / "finiq.market_desk"
    package_dir.mkdir(parents=True)
    monkeypatch.chdir(package_dir)

    misnested_root = package_dir / "resources" / "kind_kosdaq"
    payload = build_disclosure_table_payload(
        {
            "root_directory": str(misnested_root),
            "classification_path": str(misnested_root),
            "output_path": str(misnested_root / "kind.sqlite_manifest.json"),
        }
    )

    assert payload["source_type"] == "source_folder"
    assert payload["source_path"] == str(source_root.resolve())
    assert payload["output_path"] == str(_nested_sqlite_manifest_path(source_root / "kind.sqlite_manifest.json").resolve())
    assert payload["summary"]["disclosures"] == 2


def test_build_disclosure_table_payload_falls_back_to_root_when_raw_path_is_output_dir(
    tmp_path: Path,
) -> None:
    source_base = tmp_path / "source"
    source_base.mkdir()
    source_root = _write_source_body_fixture(source_base)
    output_dir = tmp_path / "kind_sqlite"

    payload = build_disclosure_table_payload(
        {
            "root_directory": str(source_root),
            "classification_path": str(output_dir),
            "output_path": str(output_dir / "kind.sqlite_manifest.json"),
        }
    )

    assert payload["source_type"] == "source_folder"
    assert payload["source_path"] == str(source_root.resolve())
    assert payload["summary"]["disclosures"] == 2


def test_collect_acpt_numbers_from_json_is_recursive_and_unique() -> None:
    payload = {
        "disclosures": [
            {"acpt_no": "20250101000001"},
            {"nested": {"acptno": "20250101000002"}},
            {"acptNo": "20250101000001"},
        ]
    }

    assert collect_acpt_numbers_from_json(payload) == ["20250101000001", "20250101000002"]


def test_download_disclosure_html_payload_uses_collected_acpt_numbers(tmp_path: Path, monkeypatch) -> None:
    def fake_download(**kwargs):
        return [Path(kwargs["output_directory"]) / f"{acpt_no}.html" for acpt_no in kwargs["acpt_numbers"]]

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.html_download.download_disclosure_viewer_htmls", fake_download)

    payload = download_disclosure_html_payload(
        {
            "output_directory": str(tmp_path / "viewer_html"),
            "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
        }
    )

    assert payload["requested_count"] == 1
    assert payload["saved_files"] == [str(tmp_path / "viewer_html" / "20250101000001.html")]
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["disclosures"][0]["market"] is None


def test_write_disclosure_html_manifest_payload_from_source_json_path(tmp_path: Path) -> None:
    source_json_path = tmp_path / "filtered.json"
    source_json_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    {"acpt_no": "20250101000001", "market": "코스닥"},
                    {"acpt_no": "20250101000002", "market": "유가증권"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output_directory = tmp_path / "converted"

    payload = write_disclosure_html_manifest_payload(
        {
            "output_directory": str(output_directory),
            "source_json_path": str(source_json_path),
        }
    )

    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert payload["requested_count"] == 2
    assert manifest["source_json_path"] == str(source_json_path)
    assert [item["acpt_no"] for item in manifest["disclosures"]] == [
        "20250101000001",
        "20250101000002",
    ]
    assert manifest["disclosures"][0]["market"] == "코스닥"


def test_write_disclosure_html_manifest_payload_from_external_directory_manifest(tmp_path: Path) -> None:
    source_directory = tmp_path / "viewer_html"
    source_directory.mkdir()
    (source_directory / "kind_disclosure_html_manifest.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "source_json_path": "filtered.json",
                "disclosures": [
                    {"acpt_no": "20250101000001", "market": "코스닥"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (source_directory / "20250101000001.html").write_text(
        """
        <html><body>
          <select id="mainDoc">
            <option value="20250101000099|Y" selected="selected">본문</option>
          </select>
        </body></html>
        """,
        encoding="utf-8",
    )

    payload = write_disclosure_html_manifest_payload(
        {
            "output_directory": str(tmp_path / "content_html"),
            "source_directory": str(source_directory),
        }
    )

    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert payload["requested_count"] == 1
    assert manifest["source_json_path"] == str(source_directory.resolve())
    assert manifest["disclosures"][0]["market"] == "코스닥"


def test_download_disclosure_html_contents_payload_saves_body_html(tmp_path: Path, monkeypatch) -> None:
    def fake_download(**kwargs):
        assert kwargs["targets"] == [{"acpt_no": "20250101000001", "doc_no": "20250101000099"}]
        path = Path(kwargs["output_directory"]) / "20250101000001.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<html><body>content</body></html>", encoding="utf-8")
        kwargs["progress_callback"](f"Saved KIND content HTML to: {path}")
        return [path]

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.html_content_download.download_disclosure_content_htmls", fake_download)
    external_dir = tmp_path / "viewer_html"
    external_dir.mkdir()
    (external_dir / "20250101000001.html").write_text(
        """
        <html><body>
          <select id="mainDoc">
            <option value="20250101000099|Y" selected="selected">본문</option>
          </select>
        </body></html>
        """,
        encoding="utf-8",
    )

    payload = download_disclosure_html_contents_payload(
        {
            "output_directory": str(tmp_path / "content_html"),
            "source_directory": str(external_dir),
            "progress_interval": 1,
        }
    )

    assert payload["format"] == "kind_disclosure_html_content_download_v1"
    assert payload["requested_count"] == 1
    assert payload["saved_files"] == [str(tmp_path / "content_html" / "20250101000001.html")]
    assert "HTML 내부 저장 중간 확인: 1/1건 처리." in payload["progress_log"]


def test_download_disclosure_html_contents_payload_rejects_json_only_input(tmp_path: Path) -> None:
    try:
        download_disclosure_html_contents_payload(
            {
                "output_directory": str(tmp_path / "content_html"),
                "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
            }
        )
    except ValueError as exc:
        assert str(exc) == "source_directory or source_compressed_json_path is required"
    else:
        raise AssertionError("expected ValueError")


def test_download_disclosure_html_contents_payload_accepts_compressed_json_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[Path, list[dict[str, str]]]] = []

    def fake_download(**kwargs):
        output_directory = Path(kwargs["output_directory"])
        targets = list(kwargs["targets"])
        calls.append((output_directory, targets))
        return [output_directory / f"{target['acpt_no']}.html" for target in targets]

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.html_content_download.download_disclosure_content_htmls", fake_download)

    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_compress_v1",
                "records": [
                    {
                        "acpt_no": "20250101000001",
                        "year": "2025",
                        "selected_main_doc_no": "20250101000999",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = download_disclosure_html_contents_payload(
        {
            "output_directory": str(tmp_path / "content_html"),
            "source_compressed_json_path": str(compressed_path),
        }
    )

    assert calls == [
        (
            tmp_path / "content_html",
            [{"acpt_no": "20250101000001", "doc_no": "20250101000999"}],
        )
    ]
    assert payload["saved_files"] == [str(tmp_path / "content_html" / "20250101000001.html")]
    assert payload["manifest_path"] == str(tmp_path / "content_html" / "kind_disclosure_html_manifest.json")


def test_download_disclosure_html_payload_accepts_source_json_path(tmp_path: Path, monkeypatch) -> None:
    def fake_download(**kwargs):
        return [Path(kwargs["output_directory"]) / f"{acpt_no}.html" for acpt_no in kwargs["acpt_numbers"]]

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.html_download.download_disclosure_viewer_htmls", fake_download)
    source_json_path = tmp_path / "filtered-disclosures.json"
    source_json_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    {"acpt_no": "20250101000001", "market": "코스닥"},
                    {"acpt_no": "20250101000002", "market": "유가증권"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = download_disclosure_html_payload(
        {
            "output_directory": str(tmp_path / "viewer_html"),
            "source_json_path": str(source_json_path),
        }
    )

    assert payload["requested_count"] == 2
    assert payload["saved_files"] == [
        str(tmp_path / "viewer_html" / "20250101000001.html"),
        str(tmp_path / "viewer_html" / "20250101000002.html"),
    ]
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["source_json_path"] == str(source_json_path)
    assert manifest["disclosures"] == [
        {
            "acpt_no": "20250101000001",
            "market": "코스닥",
            "company_name": None,
            "company_id": None,
            "disclosed_at": None,
            "title": None,
        },
        {
            "acpt_no": "20250101000002",
            "market": "유가증권",
            "company_name": None,
            "company_id": None,
            "disclosed_at": None,
            "title": None,
        },
    ]


def test_download_disclosure_html_payload_accepts_result_directory_source_json_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_download(**kwargs):
        acpt_numbers = list(kwargs["acpt_numbers"])
        calls.append(acpt_numbers)
        return [Path(kwargs["output_directory"]) / f"{acpt_no}.html" for acpt_no in acpt_numbers]

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.html_download.download_disclosure_viewer_htmls", fake_download)
    result_directory = tmp_path / "download_results"
    result_directory.mkdir()
    (result_directory / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=1, total_items=1)
    )

    payload = download_disclosure_html_payload(
        {
            "output_directory": str(tmp_path / "viewer_html"),
            "source_json_path": str(result_directory),
        }
    )

    assert calls == [["20250101000001"]]
    assert payload["requested_count"] == 1
    manifest = json.loads(Path(payload["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["source_json_path"] == str(result_directory.resolve())


def test_clean_disclosure_html_output_directory_accepts_result_directory_source_json_path(
    tmp_path: Path,
) -> None:
    result_directory = tmp_path / "download_results"
    result_directory.mkdir()
    (result_directory / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=1, total_items=1)
    )

    payload = clean_disclosure_html_output_directory_payload(
        {
            "output_directory": str(tmp_path / "viewer_html"),
            "source_json_path": str(result_directory),
            "dry_run": True,
        }
    )

    assert payload["source_type"] == "external"
    assert payload["source_path"] == str(result_directory.resolve())
    assert payload["requested_count"] == 1


def test_check_disclosure_html_output_directory_reports_existing_overlap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import finiq.market_desk.web.features.disclosures.html_common as disclosure_html

    used_workers: list[int] = []
    real_executor = disclosure_html.ThreadPoolExecutor

    def tracking_executor(*args, **kwargs):
        used_workers.append(kwargs.get("max_workers") or args[0])
        return real_executor(*args, **kwargs)

    monkeypatch.setattr(disclosure_html, "cpu_count", lambda: 8)
    monkeypatch.setattr(disclosure_html, "ThreadPoolExecutor", tracking_executor)

    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()
    (output_directory / "20250101000001.html").write_text("<html></html>", encoding="utf-8")

    payload = check_disclosure_html_output_directory_payload(
        {
            "output_directory": str(output_directory),
            "json": {
                "disclosures": [
                    {"acpt_no": "20250101000001"},
                    {"acpt_no": "20250101000002"},
                ]
            },
        }
    )

    assert payload["format"] == "kind_disclosure_html_existing_check_v1"
    assert payload["has_existing"] is True
    assert payload["deleted_count"] == 0
    assert payload["existing_target_html_count"] == 1
    assert payload["missing_target_html_count"] == 1
    assert payload["detected_output_split_by_year"] is False
    assert (output_directory / "20250101000001.html").exists()
    assert used_workers == [2]


def test_check_disclosure_html_output_directory_uses_single_worker_for_single_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import finiq.market_desk.web.features.disclosures.html_common as disclosure_html

    def fail_executor(*args, **kwargs):
        raise AssertionError("single target should not start ThreadPoolExecutor")

    monkeypatch.setattr(disclosure_html, "ThreadPoolExecutor", fail_executor)

    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()
    (output_directory / "20250101000001.html").write_text("<html></html>", encoding="utf-8")

    payload = check_disclosure_html_output_directory_payload(
        {
            "output_directory": str(output_directory),
            "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
        }
    )

    assert payload["has_existing"] is True
    assert payload["existing_target_html_count"] == 1


def test_download_disclosure_html_payload_logs_existing_html_overlap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_download(**kwargs):
        assert kwargs["acpt_numbers"] == ["20250101000002"]
        assert kwargs["skip_existing"] is False
        return [Path(kwargs["output_directory"]) / f"{acpt_no}.html" for acpt_no in kwargs["acpt_numbers"]]

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.html_download.download_disclosure_viewer_htmls", fake_download)
    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()
    (output_directory / "20250101000001.html").write_text("<html></html>", encoding="utf-8")

    payload = download_disclosure_html_payload(
        {
            "output_directory": str(output_directory),
            "json": {
                "disclosures": [
                    {"acpt_no": "20250101000001"},
                    {"acpt_no": "20250101000002"},
                ]
            },
            "skip_existing": True,
            "progress_interval": 1,
        }
    )

    assert "기존 HTML 겹침 확인: 1/2건." in payload["progress_log"]
    assert "새로 저장할 대상: 1건." in payload["progress_log"]
    assert "HTML 저장 중간 확인: 1/2건 처리." in payload["progress_log"]
    assert payload["saved_files"] == [
        str(output_directory / "20250101000001.html"),
        str(output_directory / "20250101000002.html"),
    ]


def test_download_disclosure_html_payload_logs_when_no_existing_html_overlap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_download(**kwargs):
        assert kwargs["acpt_numbers"] == ["20250101000001"]
        assert kwargs["skip_existing"] is False
        return [Path(kwargs["output_directory"]) / f"{acpt_no}.html" for acpt_no in kwargs["acpt_numbers"]]

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.html_download.download_disclosure_viewer_htmls", fake_download)
    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()

    payload = download_disclosure_html_payload(
        {
            "output_directory": str(output_directory),
            "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
            "skip_existing": True,
        }
    )

    assert "기존 HTML 겹침 확인: 0/1건." in payload["progress_log"]
    assert "기존 HTML 겹침 없음: 전체 대상이 새로 저장됩니다." in payload["progress_log"]


def test_check_disclosure_html_output_directory_uses_source_directory_manifest(tmp_path: Path) -> None:
    source_directory = tmp_path / "kind_html"
    output_directory = tmp_path / "kind_html_grouped"
    source_directory.mkdir()
    (source_directory / "20250101000001.html").write_text(
        """
        <select id="mainDoc" name="mainDoc">
          <option value="20250101000001|Y" selected="selected">본문</option>
        </select>
        """,
        encoding="utf-8",
    )
    (source_directory / "kind_disclosure_html_manifest.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "source_json_path": str(tmp_path / "filtered.json"),
                "disclosures": [{"acpt_no": "20250101000001", "company_name": "A"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "2025" / "20250101000001.html").write_text("<html></html>", encoding="utf-8")

    payload = check_disclosure_html_output_directory_payload(
        {
            "output_directory": str(output_directory),
            "source_directory": str(source_directory),
            "source_json_path": str(tmp_path / "wrong-filtered.json"),
            "split_by_year": True,
            "source_split_by_year": False,
            "output_split_by_year": True,
        }
    )

    assert payload["requested_count"] == 1
    assert payload["existing_target_html_count"] == 1
    assert payload["missing_target_html_count"] == 0
    assert payload["deletion_candidate_count"] == 0


def test_download_disclosure_html_payload_rejects_unexpected_resume_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_download(**kwargs):
        raise AssertionError(
            "download should not start when output directory has unexpected files"
        )

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.html_download.download_disclosure_viewer_htmls",
        fake_download,
    )
    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()
    (output_directory / "20250101000001.html").write_text("<html></html>", encoding="utf-8")
    (output_directory / "20240101000001.html").write_text("<html></html>", encoding="utf-8")

    try:
        download_disclosure_html_payload(
            {
                "output_directory": str(output_directory),
                "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
                "skip_existing": True,
            }
        )
    except ValueError as exc:
        assert "HTML 저장 디렉토리에 대상 접수번호 HTML이 아닌 파일이 있습니다" in str(exc)
        assert f"저장 경로: {output_directory}" in str(exc)
        assert "전체 검사 결과" in str(exc)
        assert "- 전체 파일: 2개" in str(exc)
        assert "- 대상 접수번호 HTML: 1개 / 1개" in str(exc)
        assert "문제 파일: 1개" in str(exc)
        assert "20240101000001.html (대상 접수번호 목록에 없는 HTML)" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_clean_disclosure_html_output_directory_deletes_unexpected_external_files(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()
    expected = output_directory / "20250101000001.html"
    unexpected = output_directory / "20240101000001.html"
    expected.write_text("<html></html>", encoding="utf-8")
    unexpected.write_text("<html></html>", encoding="utf-8")

    payload = clean_disclosure_html_output_directory_payload(
        {
            "output_directory": str(output_directory),
            "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
            "delete_confirmed": True,
            "delete_confirmation_text": "확인했습니다.",
        }
    )

    assert payload["source_type"] == "external"
    assert payload["deleted_count"] == 1
    assert payload["deleted_files"] == [
        {
            "path": str(unexpected),
            "name": "20240101000001.html",
            "reason": "대상 접수번호 목록에 없는 HTML",
        }
    ]
    assert expected.exists()
    assert not unexpected.exists()


def test_clean_disclosure_html_output_directory_requires_delete_confirmation(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()
    unexpected = output_directory / "20240101000001.html"
    unexpected.write_text("<html></html>", encoding="utf-8")

    try:
        clean_disclosure_html_output_directory_payload(
            {
                "output_directory": str(output_directory),
                "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
            }
        )
    except ValueError as exc:
        assert '"확인했습니다." 입력과 삭제 허가가 필요합니다' in str(exc)
    else:
        raise AssertionError("expected ValueError")

    assert unexpected.exists()


def test_clean_disclosure_html_output_directory_rejects_high_risk_directory() -> None:
    root = Path(Path.cwd().anchor).resolve()

    with pytest.raises(ValueError, match="high-risk output_directory"):
        clean_disclosure_html_output_directory_payload(
            {
                "output_directory": str(root),
                "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
                "dry_run": True,
            }
        )


def test_clean_disclosure_html_output_directory_dry_run_reports_delete_count(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()
    unexpected = output_directory / "20240101000001.html"
    unexpected.write_text("<html></html>", encoding="utf-8")

    payload = clean_disclosure_html_output_directory_payload(
        {
            "output_directory": str(output_directory),
            "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
            "dry_run": True,
        }
    )

    assert payload["dry_run"] is True
    assert payload["deleted_count"] == 0
    assert payload["deletion_candidate_count"] == 1
    assert payload["deletion_candidates"][0]["name"] == "20240101000001.html"
    assert unexpected.exists()


def test_clean_disclosure_html_output_directory_deletes_unexpected_content_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_directory = tmp_path / "viewer_html"
    source_directory.mkdir()
    output_directory = tmp_path / "viewer_html_contents"
    output_directory.mkdir()
    expected = output_directory / "20250101000001.html"
    unexpected = output_directory / "parsed-old.json"
    expected.write_text("<html></html>", encoding="utf-8")
    unexpected.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.html_content_download._collect_content_cleanup_targets_from_external_directory",
        lambda source, **kwargs: ([{"acpt_no": "20250101000001", "doc_no": "1"}], None),
    )

    payload = clean_disclosure_html_output_directory_payload(
        {
            "output_directory": str(output_directory),
            "source_directory": str(source_directory),
            "delete_confirmed": True,
            "delete_confirmation_text": "확인했습니다.",
        }
    )

    assert payload["source_type"] == "content"
    assert payload["deleted_count"] == 1
    assert payload["deleted_files"][0]["name"] == "parsed-old.json"
    assert payload["deleted_files"][0]["reason"] == "파싱 결과 JSON"
    assert expected.exists()
    assert not unexpected.exists()


def test_clean_disclosure_html_output_directory_deletes_unexpected_split_files(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "viewer_html"
    year_directory = output_directory / "2025"
    year_directory.mkdir(parents=True)
    expected = year_directory / "20250101000001.html"
    unexpected = year_directory / "20240101000001.html"
    expected.write_text("<html></html>", encoding="utf-8")
    unexpected.write_text("<html></html>", encoding="utf-8")

    payload = clean_disclosure_html_output_directory_payload(
        {
            "output_directory": str(output_directory),
            "json": {"disclosures": [{"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"}]},
            "split_by_year": True,
            "delete_confirmed": True,
            "delete_confirmation_text": "확인했습니다.",
        }
    )

    assert payload["split_by_year"] is True
    assert payload["deleted_count"] == 1
    assert payload["deleted_files"][0]["name"] == "2025/20240101000001.html"
    assert expected.exists()
    assert not unexpected.exists()


def test_clean_disclosure_html_output_directory_allows_compressed_external_json(tmp_path: Path) -> None:
    output_directory = tmp_path / "viewer_html"
    output_directory.mkdir()
    expected = output_directory / "20250101000001.html"
    compressed = output_directory / "compressed-external-html.json"
    expected.write_text("<html></html>", encoding="utf-8")
    compressed.write_text("{}", encoding="utf-8")

    payload = clean_disclosure_html_output_directory_payload(
        {
            "output_directory": str(output_directory),
            "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
            "delete_confirmed": True,
            "delete_confirmation_text": "확인했습니다.",
        }
    )

    assert payload["deleted_count"] == 0
    assert payload["unexpected_file_count"] == 0
    assert expected.exists()
    assert compressed.exists()


def test_download_disclosure_html_payload_resumes_split_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[Path, list[str]]] = []

    def fake_download(**kwargs):
        output_directory = Path(kwargs["output_directory"])
        acpt_numbers = list(kwargs["acpt_numbers"])
        calls.append((output_directory, acpt_numbers))
        return [output_directory / f"{acpt_no}.html" for acpt_no in acpt_numbers]

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.html_download.download_disclosure_viewer_htmls", fake_download)

    output_directory = tmp_path / "viewer_html"
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "2025" / "20250101000001.html").write_text("<html></html>", encoding="utf-8")

    payload = download_disclosure_html_payload(
        {
            "output_directory": str(output_directory),
            "json": {
                "disclosures": [
                    {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"},
                    {"acpt_no": "20250101000002", "disclosed_at": "2025-01-02"},
                ]
            },
            "skip_existing": True,
            "split_by_year": True,
        }
    )

    assert calls == [(output_directory / "2025", ["20250101000002"])]
    assert payload["split_by_year"] is True
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
        json.dumps({"page_size": 50}),
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
    assert dry_run_payload["deletion_candidate_count"] == 1
    assert dry_run_payload["deletion_candidates"][0]["name"] == "001_post_page_00001.body"
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
        json.dumps({"page_size": 50}),
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

    assert payload["deleted_count"] == 1
    assert payload["summary"] == {"success": 0, "failed": 0, "total": 0}
    assert not body_path.exists()


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
    (dir_corrupt / "kind_workflow.input.json").write_text(json.dumps({"page_size": 100}), encoding="utf-8")
    write_page(dir_corrupt, 1, 100, 100, html_content=b"<html><body>no paging group</body></html>")

    res = inspect_download_output_directory_payload({
        "mode": "single",
        "output_directory": str(dir_corrupt),
        "page_size": 100,
        "dry_run": True,
    })
    assert res["deletion_candidate_count"] == 1
    assert "무결성 검사 실패" in res["deletion_candidates"][0]["reason"]

    # 2. Duplicate page
    dir_dup = tmp_path / "duplicate"
    dir_dup.mkdir()
    (dir_dup / "kind_workflow.input.json").write_text(json.dumps({"page_size": 100}), encoding="utf-8")
    write_page(dir_dup, 1, 100, 150)
    p2 = dir_dup / "001_post_page_00002.body"
    p2.write_bytes(_build_download_result_page_html(page_number=1, page_size=100, total_items=150))

    res = inspect_download_output_directory_payload({
        "mode": "single",
        "output_directory": str(dir_dup),
        "page_size": 100,
        "dry_run": True,
    })
    assert res["deletion_candidate_count"] == 2
    assert "중복되는 페이지 번호" in res["deletion_candidates"][0]["reason"]

    # 3. Page gap
    dir_gap = tmp_path / "gap"
    dir_gap.mkdir()
    (dir_gap / "kind_workflow.input.json").write_text(json.dumps({"page_size": 100}), encoding="utf-8")
    write_page(dir_gap, 1, 100, 300)
    write_page(dir_gap, 3, 100, 300)

    res = inspect_download_output_directory_payload({
        "mode": "single",
        "output_directory": str(dir_gap),
        "page_size": 100,
        "dry_run": True,
    })
    assert res["deletion_candidate_count"] == 2
    assert "연속적이지 않습니다" in res["deletion_candidates"][0]["reason"]

    # 4. Inconsistent totals
    dir_inc = tmp_path / "inconsistent"
    dir_inc.mkdir()
    (dir_inc / "kind_workflow.input.json").write_text(json.dumps({"page_size": 100}), encoding="utf-8")
    write_page(dir_inc, 1, 100, 150)
    p2 = dir_inc / "001_post_page_00002.body"
    p2.write_bytes(_build_download_result_page_html(page_number=2, page_size=100, total_items=200))

    res = inspect_download_output_directory_payload({
        "mode": "single",
        "output_directory": str(dir_inc),
        "page_size": 100,
        "dry_run": True,
    })
    assert res["deletion_candidate_count"] == 2
    assert "전체 페이지 수 또는 건수가 다릅니다" in res["deletion_candidates"][0]["reason"]

    # 5. Page_size mismatch (metadata vs request)
    dir_ps_meta = tmp_path / "ps_meta"
    dir_ps_meta.mkdir()
    (dir_ps_meta / "kind_workflow.input.json").write_text(json.dumps({"page_size": 100}), encoding="utf-8")
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
    (dir_ps_rows / "kind_workflow.input.json").write_text(json.dumps({"page_size": 100}), encoding="utf-8")
    write_page(dir_ps_rows, 1, 100, 150, html_content=_build_download_result_page_html(page_number=1, page_size=50, total_items=150))

    res = inspect_download_output_directory_payload({
        "mode": "single",
        "output_directory": str(dir_ps_rows),
        "page_size": 100,
        "dry_run": True,
    })
    assert res["deletion_candidate_count"] == 1
    assert "기대값" in res["deletion_candidates"][0]["reason"]

    # 6. Missing snapshot
    dir_missing = tmp_path / "missing_snapshot"
    dir_missing.mkdir()
    write_page(dir_missing, 1, 100, 100)

    res = inspect_download_output_directory_payload({
        "mode": "single",
        "output_directory": str(dir_missing),
        "page_size": 100,
        "dry_run": True,
    })
    assert res["deletion_candidate_count"] == 1
    assert "입력 스냅샷 없이 남아 있는" in res["deletion_candidates"][0]["reason"]

    # 7. Yearly mode
    dir_yearly = tmp_path / "yearly"
    dir_yearly.mkdir()

    dir_2024 = dir_yearly / "20240101_20241231"
    dir_2024.mkdir()
    (dir_2024 / "kind_workflow.input.json").write_text(json.dumps({"page_size": 100}), encoding="utf-8")
    write_page(dir_2024, 1, 100, 100)

    dir_2025 = dir_yearly / "20250101_20251231"
    dir_2025.mkdir()
    (dir_2025 / "kind_workflow.input.json").write_text(json.dumps({"page_size": 100}), encoding="utf-8")
    write_page(dir_2025, 1, 100, 150, html_content=_build_download_result_page_html(page_number=1, page_size=50, total_items=150))

    res = inspect_download_output_directory_payload({
        "mode": "yearly",
        "output_directory": str(dir_yearly),
        "page_size": 100,
        "dry_run": True,
        "start_date": "2024-01-01",
        "end_date": "2025-12-31",
    })
    assert res["deletion_candidate_count"] == 1
    assert "20250101_20251231" in res["deletion_candidates"][0]["path"]
    assert "기대값" in res["deletion_candidates"][0]["reason"]


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


def test_inspect_download_output_directory_rejects_high_risk_directory() -> None:
    root = Path(Path.cwd().anchor).resolve()
    with pytest.raises(ValueError, match="high-risk output_directory"):
        inspect_download_output_directory_payload({
            "mode": "single",
            "output_directory": str(root),
            "page_size": 100,
        })


def test_download_disclosure_html_contents_payload_reads_and_writes_split_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[Path, list[dict[str, str]]]] = []

    def fake_download(**kwargs):
        output_directory = Path(kwargs["output_directory"])
        targets = list(kwargs["targets"])
        calls.append((output_directory, targets))
        return [output_directory / f"{target['acpt_no']}.html" for target in targets]

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.html_content_download.download_disclosure_content_htmls", fake_download)

    external_dir = tmp_path / "viewer_html"
    year_dir = external_dir / "2025"
    year_dir.mkdir(parents=True)
    (year_dir / "20250101000001.html").write_text(
        """
        <html><body>
          <select id="mainDoc">
            <option value="20250101000099|Y" selected="selected">본문</option>
          </select>
        </body></html>
        """,
        encoding="utf-8",
    )

    payload = download_disclosure_html_contents_payload(
        {
            "output_directory": str(tmp_path / "content_html"),
            "source_directory": str(external_dir),
            "split_by_year": True,
        }
    )

    assert calls == [
        (
            tmp_path / "content_html" / "2025",
            [{"acpt_no": "20250101000001", "doc_no": "20250101000099"}],
        )
    ]
    assert payload["split_by_year"] is True
    assert payload["saved_files"] == [str(tmp_path / "content_html" / "2025" / "20250101000001.html")]


def test_download_disclosure_html_contents_payload_allows_separate_source_and_output_split(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[Path, list[dict[str, str]]]] = []

    def fake_download(**kwargs):
        output_directory = Path(kwargs["output_directory"])
        targets = list(kwargs["targets"])
        calls.append((output_directory, targets))
        return [output_directory / f"{target['acpt_no']}.html" for target in targets]

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.html_content_download.download_disclosure_content_htmls", fake_download)

    external_dir = tmp_path / "viewer_html"
    year_dir = external_dir / "2025"
    year_dir.mkdir(parents=True)
    (year_dir / "20250101000001.html").write_text(
        """
        <html><body>
          <select id="mainDoc">
            <option value="20250101000099|Y" selected="selected">본문</option>
          </select>
        </body></html>
        """,
        encoding="utf-8",
    )

    payload = download_disclosure_html_contents_payload(
        {
            "output_directory": str(tmp_path / "content_html"),
            "source_directory": str(external_dir),
            "source_split_by_year": True,
            "output_split_by_year": False,
        }
    )

    assert calls == [
        (
            tmp_path / "content_html",
            [{"acpt_no": "20250101000001", "doc_no": "20250101000099"}],
        )
    ]
    assert payload["source_split_by_year"] is True
    assert payload["output_split_by_year"] is False
    assert payload["saved_files"] == [str(tmp_path / "content_html" / "20250101000001.html")]


def test_download_disclosure_html_contents_payload_explains_missing_source_split(
    tmp_path: Path,
) -> None:
    external_dir = tmp_path / "viewer_html"
    year_dir = external_dir / "2025"
    year_dir.mkdir(parents=True)
    (year_dir / "20250101000001.html").write_text(
        """
        <html><body>
          <select id="mainDoc">
            <option value="20250101000099|Y" selected="selected">본문</option>
          </select>
        </body></html>
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="enable source_split_by_year"):
        download_disclosure_html_contents_payload(
            {
                "output_directory": str(tmp_path / "content_html"),
                "source_directory": str(external_dir),
            }
        )


def test_download_disclosure_html_contents_payload_prefers_compressed_external_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[Path, list[dict[str, str]]]] = []

    def fake_download(**kwargs):
        output_directory = Path(kwargs["output_directory"])
        targets = list(kwargs["targets"])
        calls.append((output_directory, targets))
        return [output_directory / f"{target['acpt_no']}.html" for target in targets]

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.html_content_download.download_disclosure_content_htmls", fake_download)

    external_dir = tmp_path / "viewer_html"
    external_dir.mkdir()
    (external_dir / "compressed-external-html.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_compress_v1",
                "records": [
                    {
                        "acpt_no": "20250101000001",
                        "year": "2025",
                        "selected_main_doc_no": "20250101000999",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = download_disclosure_html_contents_payload(
        {
            "output_directory": str(tmp_path / "content_html"),
            "source_directory": str(external_dir),
        }
    )

    assert calls == [
        (
            tmp_path / "content_html",
            [{"acpt_no": "20250101000001", "doc_no": "20250101000999"}],
        )
    ]
    assert payload["saved_files"] == [str(tmp_path / "content_html" / "20250101000001.html")]


def test_download_disclosure_html_contents_payload_reads_compact_docs_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[Path, list[dict[str, str]]]] = []

    def fake_download(**kwargs):
        output_directory = Path(kwargs["output_directory"])
        targets = list(kwargs["targets"])
        calls.append((output_directory, targets))
        return [output_directory / f"{target['acpt_no']}.html" for target in targets]

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.html_content_download.download_disclosure_content_htmls", fake_download)

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

    payload = download_disclosure_html_contents_payload(
        {
            "output_directory": str(tmp_path / "content_html"),
            "source_directory": str(external_dir),
        }
    )

    assert calls == [
        (
            tmp_path / "content_html",
            [{"acpt_no": "20250101000001", "doc_no": "20250101000999"}],
        )
    ]
    assert payload["saved_files"] == [str(tmp_path / "content_html" / "20250101000001.html")]


def test_merge_disclosure_content_html_payload_writes_single_json(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    input_directory.mkdir()
    (input_directory / "20250101000001.html").write_text("<html>one</html>", encoding="utf-8")
    (input_directory / "20250101000002.html").write_text("<html>two</html>", encoding="utf-8")
    output_path = tmp_path / "merged.json"

    payload = merge_disclosure_content_html_payload(
        {
            "input_directory": str(input_directory),
            "output_path": str(output_path),
        }
    )

    assert payload["summary"] == {"found_files": 2, "merged_files": 2, "written_files": 1}
    assert payload["written_files"] == [str(output_path)]
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["format"] == "finiq_disclosure_content_html_merge_v1"
    assert [record["acpt_no"] for record in saved["records"]] == ["20250101000001", "20250101000002"]
    assert saved["records"][0]["html"] == "<html>one</html>"


def test_split_content_html_sections_uses_toc_boundaries(tmp_path: Path) -> None:
    source_file = tmp_path / "20260422000832.html"
    source_file.write_text(
        """
        <html>
          <head><style>body { width:600px; }</style></head>
          <body bgcolor="#FFFFFF">
            <h2 class="SECTION-1" id="toc_1"><p>주요사항보고서 / 거래소 신고의무 사항</p></h2>
            <table><tr><td>표지 내용</td></tr></table>
            <h2 class="SECTION-1" id="toc_2"><p>전환사채권 발행결정</p></h2>
            <table><tr><td>발행금액</td><td>250,000,000</td></tr></table>
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    sections = split_content_html_sections(source_file.read_bytes())
    section_payload = {section.toc_id: section for section in sections}

    assert [section.toc_id for section in sections] == ["toc_1", "toc_2"]
    assert section_payload["toc_2"].title == "전환사채권 발행결정"
    assert "전환사채권 발행결정" in section_payload["toc_2"].html
    assert "발행금액" in section_payload["toc_2"].html
    assert "주요사항보고서" not in section_payload["toc_2"].html
    assert "표지 내용" not in section_payload["toc_2"].html


def test_split_content_html_sections_ignores_nested_and_non_numeric_toc_headings() -> None:
    sections = split_content_html_sections(
        """
        <html><body>
          <div><h2 id="toc_1"><p>중첩 목차</p></h2><p>중첩 내용</p></div>
          <h2 id="toc_appendix"><p>비정규 목차</p></h2>
          <p>비정규 내용</p>
          <h2 id="toc_2"><p>정규 목차</p></h2>
          <p>정규 내용</p>
        </body></html>
        """
    )

    assert [section.toc_id for section in sections] == ["toc_2"]
    assert sections[0].title == "정규 목차"
    assert "정규 내용" in sections[0].html
    assert "중첩 내용" not in sections[0].html


def test_split_content_html_sections_supports_legacy_section_one_paragraphs() -> None:
    sections = split_content_html_sections(
        """
        <html><body>
          <p class="SECTION-1"><a name="#10">주요경영사항 신고</a></p>
          <table><tr><td>표지 내용</td></tr></table>
          <p class="PGBRK"></p>
          <p class="SECTION-1"><a name="#87">신주인수권부사채 발행결정</a></p>
          <table><tr><td>발행금액 16,000,000,000</td></tr></table>
        </body></html>
        """
    )

    assert [(section.toc_id, section.index, section.title) for section in sections] == [
        ("toc_1", 1, "주요경영사항 신고"),
        ("toc_2", 2, "신주인수권부사채 발행결정"),
    ]
    assert "표지 내용" in sections[0].html
    assert "신주인수권부사채 발행결정" not in sections[0].html
    assert "발행금액 16,000,000,000" in sections[1].html


def test_split_content_html_sections_uses_xforms_title_fallback() -> None:
    sections = split_content_html_sections(
        """
        <html>
          <head><title>:: 70471_주주총회소집결의</title></head>
          <body>
            <div class="xforms">
              <div>
                <div><span>정정신고(보고)</span></div>
                <div class="xforms_title"><div><span>주주총회소집 결의</span></div></div>
                <table><tbody><tr><td><span>1. 일시</span></td></tr></tbody></table>
              </div>
            </div>
          </body>
        </html>
        """
    )

    assert [(section.toc_id, section.index, section.title) for section in sections] == [
        ("toc_1", 1, "정정신고(보고)"),
        ("toc_2", 2, "주주총회소집 결의"),
    ]
    assert 'class="xforms"' in sections[0].html
    assert 'class="xforms"' in sections[1].html
    assert "정정신고(보고)" in sections[0].html
    assert "주주총회소집 결의" not in sections[0].html
    assert "주주총회소집 결의" in sections[1].html
    assert "1. 일시" in sections[1].html
    assert "정정신고" not in sections[1].html


def test_save_disclosure_html_sections_payload_writes_every_toc(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source_directory = input_directory / "2008"
    source_directory.mkdir(parents=True)
    (source_directory / "20260422000832.html").write_text(
        """
        <html><body>
          <h2 class="SECTION-1" id="toc_1"><p>주요사항보고서 / 거래소 신고의무 사항</p></h2>
          <p>표지 내용</p>
          <h2 class="SECTION-1" id="toc_2"><p>전환사채권 발행결정</p></h2>
          <p>발행금액 250,000,000</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    payload = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
        }
    )
    section_html = (output_directory / "2008" / "20260422000832.html").read_text(encoding="utf-8")

    assert payload["summary"] == {
        "found_files": 1,
        "saved_files": 1,
        "skipped_files": 0,
        "expected_files": 1,
        "integrity_ok": True,
        "missing_files": 0,
    }
    assert "주요사항보고서" in section_html
    assert "표지 내용" in section_html
    assert "전환사채권 발행결정" in section_html
    assert "발행금액 250,000,000" in section_html
    assert not (output_directory / "toc_1").exists()
    assert not (output_directory / "2008" / "toc_1").exists()


def test_save_disclosure_html_sections_payload_continues_after_files_without_toc(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source_directory = input_directory / "2008"
    source_directory.mkdir(parents=True)
    (source_directory / "20260421000111.html").write_text(
        "<html><body><p>목차 없는 문서</p></body></html>",
        encoding="utf-8",
    )
    (source_directory / "20260422000832.html").write_text(
        """
        <html><body>
          <h2 id="toc_1"><p>주요사항보고서</p></h2>
          <p>표지 내용</p>
          <h2 id="toc_2"><p>전환사채권 발행결정</p></h2>
          <p>발행금액 250,000,000</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    payload = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
        }
    )

    assert payload["summary"] == {
        "found_files": 2,
        "saved_files": 1,
        "skipped_files": 1,
        "expected_files": 1,
        "integrity_ok": True,
        "missing_files": 0,
    }
    assert (output_directory / "2008" / "20260422000832.html").is_file()
    assert not (output_directory / "2008" / "20260422000832_1.html").exists()
    assert not (output_directory / "2008" / "20260422000832_2.html").exists()
    assert not (output_directory / "2008" / "toc_1").exists()
    assert payload["skipped_files"] == [
        {"source_file": str(source_directory / "20260421000111.html"), "error": "no sections found"}
    ]


def test_inspect_disclosure_html_sections_payload_lists_document_toc_and_problems(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    input_directory.mkdir()
    nested_directory = input_directory / "2025" / "shareholder_meeting"
    nested_directory.mkdir(parents=True)
    (input_directory / "20260422000832.html").write_text(
        """
        <html><body>
          <h2 class="SECTION-1" id="toc_1"><p>주요사항보고서 / 거래소 신고의무 사항</p></h2>
          <p>표지 내용</p>
          <h2 class="SECTION-1" id="toc_2"><p>전환사채권 발행결정</p></h2>
          <p>발행금액 250,000,000</p>
        </body></html>
        """,
        encoding="utf-8",
    )
    (nested_directory / "20260423000533.html").write_text(
        """
        <html><body>
          <h2 class="SECTION-1" id="toc_1"><p>주요사항보고서 / 거래소 신고의무 사항</p></h2>
          <p>표지 내용</p>
        </body></html>
        """,
        encoding="utf-8",
    )
    (input_directory / "20260424000211.html").write_text("<html><body><p>목차 없음</p></body></html>", encoding="utf-8")

    payload = inspect_disclosure_html_sections_payload({"input_directory": str(input_directory), "report_limit": 1})

    assert payload["summary"] == {
        "found_files": 3,
        "documents_with_sections": 2,
        "files_without_sections": 1,
        "failed_files": 0,
        "reported_problem_files": 1,
    }
    documents = sorted(payload["documents"], key=lambda document: document["source_name"])
    assert [document["source_name"] for document in documents] == [
        "20260422000832.html",
        "20260423000533.html",
    ]
    assert [document["source_relative_path"] for document in documents] == [
        "20260422000832.html",
        "2025/shareholder_meeting/20260423000533.html",
    ]
    assert [section["toc_id"] for section in documents[0]["sections"]] == ["toc_1", "toc_2"]
    assert [section["toc_id"] for section in documents[1]["sections"]] == ["toc_1"]
    assert payload["problem_files"] == [
        {
            "kind": "no_sections",
            "source_file": str(input_directory / "20260424000211.html"),
            "error": "",
        }
    ]


def test_inspect_disclosure_html_sections_payload_stops_before_next_file_when_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_directory = tmp_path / "content_html"
    input_directory.mkdir()
    (input_directory / "20260401000001.html").write_text(
        "<html><body><h2 id='toc_1'><p>1</p></h2><p>첫 번째</p></body></html>",
        encoding="utf-8",
    )
    (input_directory / "20260402000001.html").write_text(
        "<html><body><h2 id='toc_1'><p>2</p></h2><p>두 번째</p></body></html>",
        encoding="utf-8",
    )
    checks = 0
    parsed: list[str] = []

    def fake_inspect(markup: bytes) -> list[HtmlSectionSummary]:
        parsed.append(markup.decode("utf-8"))
        return [HtmlSectionSummary(toc_id="toc_1", index=1, title="1")]

    monkeypatch.setattr(disclosure_html_sections, "inspect_content_html_sections", fake_inspect)

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


def test_list_disclosure_html_section_sources_payload_pages_with_current_page_toc_counts(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    input_directory.mkdir()
    for index in range(22):
        section_markup = "<h2 id='toc_1'><p>목차</p></h2>"
        if index == 0:
            section_markup += "<h2 id='toc_2'><p>본문</p></h2>"
        (input_directory / f"202604{index + 1:02d}000001.html").write_text(
            f"<html><body>{section_markup}</body></html>",
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
    }
    assert len(first_page["documents"]) == 20
    assert first_page["documents"][0]["source_name"] == "20260401000001.html"
    assert first_page["documents"][0]["section_count"] == 2
    assert first_page["documents"][1]["section_count"] == 1
    assert "sections" not in first_page["documents"][0]
    assert second_page["summary"] == {
        "page": 2,
        "page_size": 20,
        "returned_files": 2,
        "has_next_page": False,
    }
    assert [document["source_name"] for document in second_page["documents"]] == [
        "20260421000001.html",
        "20260422000001.html",
    ]
    assert [document["section_count"] for document in second_page["documents"]] == [1, 1]


def test_summarize_disclosure_html_section_kinds_payload_counts_unique_toc_sequences(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    input_directory.mkdir()
    nested_directory = input_directory / "2026"
    nested_directory.mkdir()
    for source_file in [
        input_directory / "20260401000001.html",
        nested_directory / "20260402000001.html",
        input_directory / "20260403000001.html",
        input_directory / "20260404000001.html",
    ]:
        source_file.write_text(
            """
            <html><body>
              <h2 id="toc_1"><p>1</p></h2>
              <p>표지</p>
              <h2 id="toc_2"><p>2</p></h2>
              <p>본문</p>
            </body></html>
            """,
            encoding="utf-8",
        )
    (input_directory / "20260405000001.html").write_text(
        """
        <html><body>
          <h2 id="toc_1"><p>1</p></h2>
          <p>표지</p>
        </body></html>
        """,
        encoding="utf-8",
    )
    (input_directory / "20260406000001.html").write_text("<html><body>목차 없음</body></html>", encoding="utf-8")

    payload = summarize_disclosure_html_section_kinds_payload({"input_directory": str(input_directory)})

    assert payload["format"] == "finiq_disclosure_html_section_kind_summary_v1"
    assert payload["summary"] == {
        "found_files": 6,
        "documents_with_sections": 5,
        "files_without_sections": 1,
        "failed_files": 0,
        "unique_kinds": 2,
    }
    assert payload["items"] == [
        {
            "signature": "toc_1 1 toc_2 2",
            "count": 4,
            "section_count": 2,
            "sections": [
                {"toc_id": "toc_1", "index": 1, "title": "1"},
                {"toc_id": "toc_2", "index": 2, "title": "2"},
            ],
            "sample_documents": [
                {
                    "source_file": str(nested_directory / "20260402000001.html"),
                    "source_name": "20260402000001.html",
                    "source_relative_path": "2026/20260402000001.html",
                },
                {
                    "source_file": str(input_directory / "20260401000001.html"),
                    "source_name": "20260401000001.html",
                    "source_relative_path": "20260401000001.html",
                },
                {
                    "source_file": str(input_directory / "20260403000001.html"),
                    "source_name": "20260403000001.html",
                    "source_relative_path": "20260403000001.html",
                },
            ],
        },
        {
            "signature": "toc_1 1",
            "count": 1,
            "section_count": 1,
            "sections": [{"toc_id": "toc_1", "index": 1, "title": "1"}],
            "sample_documents": [
                {
                    "source_file": str(input_directory / "20260405000001.html"),
                    "source_name": "20260405000001.html",
                    "source_relative_path": "20260405000001.html",
                }
            ],
        },
    ]


def test_save_disclosure_html_sections_payload_filters_toc_sections_by_pattern_rule(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source_directory = input_directory / "2008"
    source_directory.mkdir(parents=True)
    (source_directory / "20260401000001.html").write_text(
        """
        <html><body>
          <h2 id="toc_1"><p>1</p></h2>
          <p>표지</p>
          <h2 id="toc_2"><p>2</p></h2>
          <p>본문</p>
        </body></html>
        """,
        encoding="utf-8",
    )
    (source_directory / "20260402000001.html").write_text(
        """
        <html><body>
          <h2 id="toc_1"><p>단독</p></h2>
          <p>단독 본문</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    payload = save_disclosure_html_sections_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "section_save_rules": {"toc_1 1 toc_2 2": ["toc_1"]},
        }
    )

    assert payload["summary"] == {
        "found_files": 2,
        "saved_files": 2,
        "skipped_files": 0,
        "expected_files": 2,
        "integrity_ok": True,
        "missing_files": 0,
    }
    assert (output_directory / "2008" / "20260401000001.html").is_file()
    filtered_html = (output_directory / "2008" / "20260401000001.html").read_text(encoding="utf-8")
    assert "표지" in filtered_html
    assert "본문" not in filtered_html
    assert not (output_directory / "2008" / "20260401000001_1.html").exists()
    assert not (output_directory / "2008" / "20260401000001_2.html").exists()
    assert (output_directory / "2008" / "20260402000001.html").is_file()
    assert not (output_directory / "2008" / "20260402000001_1.html").exists()
    assert not (output_directory / "toc_1").exists()
    assert not (output_directory / "2008" / "toc_1").exists()


def test_save_disclosure_html_sections_payload_preserves_multiple_selected_sections(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source_directory = input_directory / "2008"
    source_directory.mkdir(parents=True)
    (source_directory / "20260401000001.html").write_text(
        """
        <html><body>
          <h2 id="toc_1"><p>1</p></h2>
          <p>표지</p>
          <h2 id="toc_2"><p>2</p></h2>
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


def test_save_disclosure_html_sections_payload_stops_before_next_file_when_cancelled(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source_directory = input_directory / "2008"
    source_directory.mkdir(parents=True)
    (source_directory / "20260401000001.html").write_text(
        "<html><body><h2 id='toc_1'><p>1</p></h2><p>첫 번째</p></body></html>",
        encoding="utf-8",
    )
    (source_directory / "20260402000001.html").write_text(
        "<html><body><h2 id='toc_1'><p>2</p></h2><p>두 번째</p></body></html>",
        encoding="utf-8",
    )
    checks = 0

    def cancel_check() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    payload = save_disclosure_html_sections_payload(
        {"input_directory": str(input_directory), "output_directory": str(output_directory), "workers": 1},
        cancel_check=cancel_check,
    )

    assert payload == {"cancelled": True}
    assert (output_directory / "2008" / "20260401000001.html").is_file()
    assert not (output_directory / "2008" / "20260402000001.html").exists()


def test_split_disclosure_html_section_source_payload_splits_one_selected_file(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    nested_directory = input_directory / "2026"
    nested_directory.mkdir(parents=True)
    source_file = nested_directory / "20260422000832.html"
    source_file.write_text(
        """
        <html><body>
          <h2 id="toc_1"><p>주요사항보고서</p></h2>
          <p>표지 내용</p>
          <h2 id="toc_2"><p>전환사채권 발행결정</p></h2>
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


def test_html_section_worker_count_defaults_to_cpu_cap_and_accepts_payload_value() -> None:
    assert DEFAULT_HTML_SECTION_WORKERS == 8
    assert parse_html_section_worker_count(None) == 8
    assert parse_html_section_worker_count("") == 8
    assert parse_html_section_worker_count("4") == 4

    with pytest.raises(ValueError, match="workers must be >= 1"):
        parse_html_section_worker_count(0)


def test_merge_disclosure_content_html_payload_writes_split_json(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    (input_directory / "2024").mkdir(parents=True)
    (input_directory / "2025").mkdir()
    (input_directory / "2024" / "20240101000001.html").write_text("<html>old</html>", encoding="utf-8")
    (input_directory / "2025" / "20250101000001.html").write_text("<html>new</html>", encoding="utf-8")
    output_directory = tmp_path / "merged"

    payload = merge_disclosure_content_html_payload(
        {
            "input_directory": str(input_directory),
            "output_path": str(output_directory),
            "split_by_year": True,
        }
    )

    assert payload["split_by_year"] is True
    assert payload["summary"] == {"found_files": 2, "merged_files": 2, "written_files": 2}
    assert payload["written_files"] == [
        str(output_directory / "merged-content-html-2024.json"),
        str(output_directory / "merged-content-html-2025.json"),
    ]
    saved_2024 = json.loads((output_directory / "merged-content-html-2024.json").read_text(encoding="utf-8"))
    saved_2025 = json.loads((output_directory / "merged-content-html-2025.json").read_text(encoding="utf-8"))
    assert saved_2024["year"] == "2024"
    assert saved_2024["records"][0]["html"] == "<html>old</html>"
    assert saved_2025["year"] == "2025"
    assert saved_2025["records"][0]["html"] == "<html>new</html>"


def test_compress_disclosure_external_html_payload_writes_compact_json(tmp_path: Path) -> None:
    input_directory = tmp_path / "viewer_html"
    input_directory.mkdir()
    (input_directory / "kind_disclosure_html_manifest.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20250101000001",
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
    (input_directory / "20250101000001.html").write_text(
        """
        <html><body>
          <meta name="description" content="대한민국 대표 기업공시채널 KIND" />
          <script>
            var _TRK_PI = "PDV";
            var _TRK_PN = "20250101000001";
          </script>
          <script src="../js/viewer.js?version=20250307"></script>
          <form name="docdownloadform" id="docdownloadform">
            <input type="hidden" name="docLocPath" id="docLocPath" value="/external/path" />
          </form>
          <input type="hidden" name="acptNo" value="20250101000001" />
          <input type="hidden" name="tempTitle" value="뷰어 제목" />
          <h1 class="ttl">테스트 (123456)</h1>
          <select id="mainDoc">
            <option value="">본문선택</option>
            <option value="20250101000999|Y" selected="selected">본문</option>
          </select>
          <select id="attachedDoc">
            <option value="">첨부문서선택</option>
            <option value="20250101000888">첨부</option>
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
    assert saved["records"][0]["acpt_no"] == "20250101000001"
    assert saved["records"][0]["title"] == "뷰어 제목"
    assert saved["records"][0]["selected_main_doc_no"] == "20250101000999"
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
            "doc_no": "20250101000999",
            "text": "본문",
            "value": "20250101000999|Y",
            "latest_flag": "Y",
            "selected": True,
        },
        {
            "select_id": "attachedDoc",
            "select_name": "",
            "option_index": 1,
            "doc_no": "20250101000888",
            "text": "첨부",
            "value": "20250101000888",
            "latest_flag": None,
            "selected": False,
        },
    ]


def test_compress_disclosure_external_html_payload_reads_split_input(tmp_path: Path) -> None:
    input_directory = tmp_path / "viewer_html"
    (input_directory / "2024").mkdir(parents=True)
    (input_directory / "2025").mkdir(parents=True)
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

    payload = compress_disclosure_external_html_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(tmp_path / "compressed"),
            "split_by_year": True,
            "output_split_by_year": True,
        }
    )

    assert "split_by_year" not in payload
    assert "input_split_by_year" not in payload
    assert "output_split_by_year" not in payload
    assert payload["summary"] == {"found_files": 2, "compressed_files": 2, "written_files": 1}
    assert payload["processing_verification"] == {
        "passed": True,
        "expected_files": 2,
        "processed_files": 2,
        "missing_files": 0,
        "missing_indexes": [],
    }
    assert payload["verification"]["passed"] is True
    assert payload["verification"]["missing_records"] == 0
    output_path = tmp_path / "compressed" / "compressed-external-html.json"
    assert payload["written_files"] == [str(output_path)]
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert "input_directory" not in saved
    assert "output_directory" not in saved
    assert "output_path" not in saved
    assert "split_by_year" not in saved
    assert "input_split_by_year" not in saved
    assert "output_split_by_year" not in saved
    assert "year" not in saved
    assert [record["acpt_no"] for record in saved["records"]] == ["20240101000001", "20250101000001"]
    assert "year" not in saved["records"][0]
    assert saved["records"][1]["docs"][0]["doc_no"] == "20250101000999"


def test_compress_disclosure_external_html_payload_accepts_parallel_workers(tmp_path: Path) -> None:
    input_directory = tmp_path / "viewer_html"
    input_directory.mkdir()
    for acpt_no in ("20250101000001", "20250101000002"):
        (input_directory / f"{acpt_no}.html").write_text(
            f"""
            <html><body>
              <input type="hidden" name="acptNo" value="{acpt_no}" />
              <select id="mainDoc">
                <option value="{acpt_no}999|Y" selected="selected">본문</option>
              </select>
            </body></html>
            """,
            encoding="utf-8",
        )

    payload = compress_disclosure_external_html_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(tmp_path / "compressed"),
            "workers": 2,
        }
    )

    output_path = tmp_path / "compressed" / "compressed-external-html.json"
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["summary"] == {"found_files": 2, "compressed_files": 2, "written_files": 1}
    assert payload["processing_verification"]["passed"] is True
    assert payload["verification"]["passed"] is True
    assert "병렬 처리: 2개 워커" in payload["progress_log"]
    assert [record["acpt_no"] for record in saved["records"]] == ["20250101000001", "20250101000002"]


def test_check_disclosure_html_output_directory_ignores_compressed_json_split_by_year(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_full_target_scan(*args, **kwargs):
        raise AssertionError("existing checks should not scan compressed JSON docs for doc_no")

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.html_content_download._collect_content_targets_from_compressed_payload",
        fail_full_target_scan,
    )

    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "split_by_year": True,
                "records": [
                    {
                        "acpt_no": "20250101000001",
                        "year": "2025",
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
            "output_split_by_year": False,
        }
    )

    assert payload["source_type"] == "content"
    assert payload["output_split_by_year"] is False
    assert payload["detected_output_split_by_year"] is None
    assert payload["requested_count"] == 1


def test_check_disclosure_html_output_directory_prefers_output_directory_split_by_year(
    tmp_path: Path,
) -> None:
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "split_by_year": False,
                "records": [
                    {
                        "acpt_no": "20250101000001",
                        "year": "2025",
                        "selected_main_doc_no": "20250101000999",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_directory = tmp_path / "content_html"
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "2025" / "20250101000001.html").write_text("<html></html>", encoding="utf-8")

    payload = check_disclosure_html_output_directory_payload(
        {
            "source_compressed_json_path": str(compressed_path),
            "output_directory": str(output_directory),
            "output_split_by_year": False,
        }
    )

    assert payload["output_split_by_year"] is True
    assert payload["detected_output_split_by_year"] is True
    assert payload["existing_target_html_count"] == 1


def test_download_disclosure_html_payload_stops_when_cancelled(tmp_path: Path, monkeypatch) -> None:
    def fake_download(**kwargs):
        saved_paths = []
        for acpt_no in kwargs["acpt_numbers"]:
            if kwargs["cancel_check"]():
                break
            saved_paths.append(Path(kwargs["output_directory"]) / f"{acpt_no}.html")
            cancel_disclosure_html_download("cancel-test")
        return saved_paths

    monkeypatch.setattr("finiq.market_desk.web.features.disclosures.html_download.download_disclosure_viewer_htmls", fake_download)

    payload = download_disclosure_html_payload(
        {
            "output_directory": str(tmp_path / "viewer_html"),
            "json": {"acptNumbers": ["20250101000001", "20250101000002"]},
            "cancel_token": "cancel-test",
        }
    )

    assert payload["cancelled"] is True
    assert payload["saved_count"] == 1


def test_parse_disclosure_html_payload_requires_mode(tmp_path: Path) -> None:
    try:
        parse_disclosure_html_payload({"input_directory": str(tmp_path)})
    except ValueError as exc:
        assert str(exc) == "mode is required"
    else:
        raise AssertionError("expected ValueError")


def test_parse_disclosure_html_payload_rejects_unknown_mode(tmp_path: Path) -> None:
    try:
        parse_disclosure_html_payload({"input_directory": str(tmp_path), "mode": "unknown"})
    except ValueError as exc:
        assert "unsupported mode" in str(exc)
        assert "bond_issuance" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_parse_disclosure_html_payload_parses_html_files_and_writes_result(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    (viewer_dir / "20250101000001.html").write_text(
        """
        <html>
          <head><title>Sample Disclosure</title></head>
          <body><p class="SECTION-1">Sample Disclosure</p><table><tr><th>Field</th><td>Value</td></tr></table></body>
        </html>
        """,
        encoding="utf-8",
    )
    (viewer_dir / HTML_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "disclosures": [
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
    output_path = tmp_path / "parsed-bond_issuance.json"

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "bond_issuance",
        }
    )
    stored = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["format"] == "finiq_disclosure_html_parse_v1"
    assert payload["mode"] == "bond_issuance"
    assert payload["summary"] == {"found_files": 1, "parsed_files": 1, "failed_files": 0}
    assert payload["cancelled"] is False
    assert "progress_log" not in payload
    assert payload["records"][0]["acpt_no"] == "20250101000001"
    assert payload["records"][0]["title"] == "Sample Disclosure"
    assert "source_file" not in payload["records"][0]
    assert "raw_rows" not in payload["records"][0]
    assert "raw_tables" not in payload["records"][0]
    assert stored["format"] == payload["format"]
    assert "source_file" not in stored["records"][0]
    assert "progress_log" not in stored


def test_parse_disclosure_html_payload_prefers_download_manifest_market(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    (viewer_dir / "20250101000001.html").write_text(
        """
        <html>
          <head><title>Sample Disclosure</title></head>
          <body><p class="SECTION-1">Sample Disclosure</p>유가증권시장 <table><tr><th>Field</th><td>Value</td></tr></table></body>
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
        }
    )

    assert payload["records"][0]["상장구분"] == "코스닥"
    assert payload["records"][0]["corp_name"] == "테스트발행사"


def test_parse_disclosure_html_payload_does_not_infer_market_from_body(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    (viewer_dir / "20250101000001.html").write_text(
        """
        <html>
          <head><title>Sample Disclosure</title></head>
          <body><p class="SECTION-1">Sample Disclosure</p>유가증권시장 <table><tr><th>Field</th><td>Value</td></tr></table></body>
        </html>
        """,
        encoding="utf-8",
    )

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "bond_issuance",
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
    (input_dir / "20250102000003.html").write_text(
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
    html_file = input_dir / "20250102000002.html"
    html_file.write_text("<html></html>", encoding="utf-8")

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "rcept_no": "20250102009999",
            "source_file": str(Path(file_path).resolve()),
            "mode": "rights_issuance",
            "title": "",
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "rights_issuance", fake_parser)

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(input_dir),
            "output_directory": str(output_dir),
            "mode": "rights_issuance",
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
    (input_dir / "20250102000002.html").write_text("<html></html>", encoding="utf-8")

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "source_file": str(Path(file_path).resolve()),
            "mode": "rights_issuance",
            "title": "",
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "rights_issuance", fake_parser)

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(input_dir),
            "output_directory": str(output_dir),
            "mode": "rights_issuance",
        }
    )

    assert "input_directory" not in payload
    assert "output_path" not in payload
    assert (output_dir / "parsed-rights_issuance.json").is_file()


def test_parse_disclosure_html_payload_requires_output_directory(
    tmp_path: Path, monkeypatch
) -> None:
    input_dir = tmp_path / "viewer_html_contents_sections"
    input_dir.mkdir()
    html_file = input_dir / "20250102000002.html"
    html_file.write_text("<html></html>", encoding="utf-8")

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "rcept_no": "20250102009999",
            "source_file": str(Path(file_path).resolve()),
            "mode": "rights_issuance",
            "title": "",
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "rights_issuance", fake_parser)

    with pytest.raises(ValueError, match="output_directory is required"):
        parse_disclosure_html_payload(
            {
                "input_directory": str(input_dir),
                "mode": "rights_issuance",
            }
        )


def test_parse_disclosure_html_payload_resolves_correction_family_acpt_numbers(
    tmp_path: Path, monkeypatch
) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    first = viewer_dir / "20250101000001.html"
    second = viewer_dir / "20250102000002.html"
    first.write_text("<html></html>", encoding="utf-8")
    second.write_text("<html></html>", encoding="utf-8")

    def fake_parser(html_text, *, file_path):
        acpt_no = Path(file_path).stem
        rcept_no = {
            "20250101000001": "20250101009999",
            "20250102000002": "20250102009999",
        }[acpt_no]
        current_sequence = 0 if acpt_no == "20250101000001" else 1
        return {
            "correction_families": {
                "20250102009999": {
                    "current_sequence": current_sequence,
                    "members": [
                        {
                            "sequence": 0,
                            "acpt_no": acpt_no if current_sequence == 0 else None,
                            "rcept_no": "20250101009999",
                        },
                        {
                            "sequence": 1,
                            "acpt_no": acpt_no if current_sequence == 1 else None,
                            "rcept_no": "20250102009999",
                        },
                    ],
                }
            },
            "rcept_no": rcept_no,
            "acpt_no": acpt_no,
            "source_file": str(Path(file_path).resolve()),
            "mode": "security_transaction",
            "title": "",
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
        }
    )

    for record in payload["records"]:
        family = record["correction_families"]["20250102009999"]
        assert family["members"] == [
            {"sequence": 0, "acpt_no": "20250101000001", "rcept_no": "20250101009999"},
            {"sequence": 1, "acpt_no": "20250102000002", "rcept_no": "20250102009999"},
        ]


def test_parse_disclosure_html_payload_uses_external_html_main_docs_for_corrections(
    tmp_path: Path, monkeypatch
) -> None:
    input_dir = tmp_path / "rights_issuance" / "kind_html_contents_sections"
    input_dir.mkdir(parents=True)
    first = input_dir / "20081210000626.html"
    second = input_dir / "20081211000252.html"
    first.write_text("<html></html>", encoding="utf-8")
    second.write_text("<html></html>", encoding="utf-8")
    (input_dir.parent / "filtered.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "company_key": "03679",
                        "acpt_no": "20081210000626",
                        "company_name": "자강",
                        "market": "코스닥",
                        "disclosed_at": "2008-12-10 18:16",
                        "title": "유상증자결정",
                        "title_base": "유상증자결정",
                        "title_display": "유상증자결정",
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
                        "title_base": "유상증자결정(제3자배정)",
                        "title_display": "[정정]유상증자결정(제3자배정)",
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
            "correction_families": {},
            "rcept_no": None,
            "acpt_no": acpt_no,
            "source_file": str(Path(file_path).resolve()),
            "mode": "rights_issuance",
            "title": "유상증자 결정",
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "rights_issuance", fake_parser)

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(input_dir),
            "output_directory": str(tmp_path),
            "mode": "rights_issuance",
        }
    )

    records = {record["acpt_no"]: record for record in payload["records"]}
    assert all("docs" not in record for record in records.values())
    family = records["20081210000626"]["correction_families"]["20081211000252"]
    assert family["current_sequence"] == 0
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
    parse_path = tmp_path / "parsed-bond_issuance.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "bond_issuance",
                "records": [
                    {
                        "title": "[정정]전환사채권발행결정",
                        "acpt_no": "20250102000002",
                        "rcept_no": "20250102009999",
                        "source_file": "/tmp/20250102000002.html",
                        "correction_families": {
                            "20250102009999": {
                                "current_sequence": 1,
                                "members": [
                                    {"sequence": 0, "acpt_no": None, "rcept_no": "20250101009999"},
                                    {"sequence": 1, "acpt_no": "20250102000002", "rcept_no": "20250102009999"},
                                ],
                            }
                        },
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

    payload = build_bond_parse_summary_payload({"output_path": str(tmp_path)})

    assert payload["format"] == "finiq_bond_parse_summary_v1"
    assert payload["summary"] == {
        "records": 1,
        "visible_records": 1,
        "families": 1,
        "correction_records": 1,
        "latest_records": 1,
    }
    assert payload["records"][0]["family_id"] == "20250102009999"
    assert payload["records"][0]["fields"]["발행금액"] == 1_000_000_000
    assert payload["records"][0]["fields"]["사채발행방법"] == "사모"
    assert payload["records"][0]["fields"]["투자자"] == [["테스트조합", 1_000_000_000]]
    assert "리픽싱(%)" not in payload["records"][0]["fields"]


def test_build_bond_parse_summary_payload_accepts_result_directory(tmp_path: Path) -> None:
    parse_path = tmp_path / "parsed-bond_issuance.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "bond_issuance",
                "records": [
                    {
                        "title": "전환사채권발행결정",
                        "acpt_no": "20250102000002",
                        "source_file": "/tmp/20250102000002.html",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_bond_parse_summary_payload({"output_path": str(tmp_path)})

    assert payload["source_path"] == str(parse_path)
    assert payload["summary"]["records"] == 1


def test_build_bond_parse_summary_payload_rejects_missing_result_file_path(tmp_path: Path) -> None:
    result_path = tmp_path / "parsed-bond_issuance.json"

    with pytest.raises(ValueError, match="output_path must be a directory path"):
        build_bond_parse_summary_payload({"output_path": str(result_path)})

    assert not result_path.exists()


def test_build_bond_parse_summary_payload_includes_source_preview(tmp_path: Path) -> None:
    source_path = tmp_path / "20250102000002.html"
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
    parse_path = tmp_path / "parsed-bond_issuance.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "bond_issuance",
                "records": [
                    {
                        "title": "전환사채권발행결정",
                        "acpt_no": "20250102000002",
                        "rcept_no": "20250102009999",
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
        {"output_path": str(tmp_path), "source_directory": str(tmp_path)}
    )

    preview = payload["records"][0]["source_preview"]
    assert preview["available"] is True
    assert preview["source_file"] == str(source_path)
    assert preview["tables"][0]["rows"][0] == ["1. 사채의 종류", "전환사채"]
    assert preview["tables"][0]["rows"][1] == ["2. 사채의 권면(전자등록)총액", "1,000,000,000"]


def test_build_parse_preview_payload_parses_input_directory(tmp_path: Path) -> None:
    bond_dir = tmp_path / "bond_issuance"
    input_dir = bond_dir / "viewer_html"
    input_dir.mkdir(parents=True)
    (input_dir / "20250102000002.html").write_text(
        """
        <html>
          <head><title>전환사채권발행결정</title></head>
          <body>
            <p class="SECTION-1">전환사채권발행결정</p>
            <table>
              <tr><th>1. 사채의 종류</th><td>전환사채</td></tr>
              <tr><th>2. 사채의 권면총액</th><td>1,000,000,000</td></tr>
            </table>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    (bond_dir / "filtered.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "company_key": "TEST",
                        "acpt_no": "20250101000001",
                        "company_name": "테스트발행사",
                        "market": "코스닥",
                        "disclosed_at": "2025-01-01 09:00",
                        "title": "전환사채권발행결정",
                        "title_base": "전환사채권발행결정",
                        "title_display": "전환사채권발행결정",
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
                        "title_base": "전환사채권발행결정",
                        "title_display": "[정정]전환사채권발행결정",
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
                        "selected_main_doc_no": "20250102009999",
                        "docs": [
                            {
                                "select_id": "mainDoc",
                                "doc_no": "00000000835386",
                                "value": "00000000835386|N",
                                "latest_flag": "N",
                                "selected": False,
                            },
                            {
                                "select_id": "mainDoc",
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
            "limit": 1,
        }
    )

    assert payload["source_kind"] == "input_directory"
    assert payload["summary"] == {"records": 1, "visible_records": 1, "errors": 0}
    assert payload["records"][0]["title"] == "[테스트발행사] 전환사채권발행결정"
    record = payload["records"][0]["parsed_result"]
    assert record["acpt_no"] == "20250102000002"
    assert record["rcept_no"] is None
    assert record["doc_no"] == "20250102009999"
    assert "selected_main_doc_no" not in record
    assert "docs" not in record
    assert record["corp_name"] == "테스트발행사"
    assert record["상장구분"] == "코스닥"
    assert record["correction_families"] == {
        "20250102000002": {
            "current_sequence": 1,
            "members": [
                {
                    "sequence": 0,
                    "acpt_no": "20250101000001",
                    "doc_no": None,
                    "title": "전환사채권발행결정",
                    "disclosed_at": "2025-01-01 09:00",
                    "is_correction_report": False,
                },
                {
                    "sequence": 1,
                    "acpt_no": "20250102000002",
                    "doc_no": None,
                    "title": "[정정]전환사채권발행결정",
                    "disclosed_at": "2025-01-02 09:00",
                    "is_correction_report": True,
                },
            ],
        }
    }
    assert payload["records"][0]["source_preview"]["available"] is True


def test_build_parse_change_log_payload_classifies_major_changes(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.app import config as app_config

    monkeypatch.setattr(app_config, "change_log_date_thresholds", {})
    monkeypatch.setattr(app_config, "change_log_numeric_thresholds", {})

    parse_path = tmp_path / "parsed-rights_issuance.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "rights_issuance",
                "records": [
                    {
                        "title": "유상증자결정",
                        "acpt_no": "20240822000001",
                        "rcept_no": "20240822009999",
                        "source_file": "/tmp/20240822000001.html",
                        "correction_families": {
                            "20240829009999": {
                                "current_sequence": 0,
                                "members": [
                                    {"sequence": 0, "acpt_no": "20240822000001", "rcept_no": "20240822009999"},
                                    {"sequence": 1, "acpt_no": "20240829000001", "rcept_no": "20240829009999"},
                                ],
                            }
                        },
                        "신주의 종류와 수": [["보통주식", 100]],
                        "발행목적": [["운영자금", 1000]],
                        "발행가액": [["보통주식", 1000]],
                        "납입일": "2024년 08월 30일",
                    },
                    {
                        "title": "[정정]유상증자결정",
                        "acpt_no": "20240829000001",
                        "rcept_no": "20240829009999",
                        "source_file": "/tmp/20240829000001.html",
                        "correction_families": {
                            "20240829009999": {
                                "current_sequence": 1,
                                "members": [
                                    {"sequence": 0, "acpt_no": "20240822000001", "rcept_no": "20240822009999"},
                                    {"sequence": 1, "acpt_no": "20240829000001", "rcept_no": "20240829009999"},
                                ],
                            }
                        },
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


def test_build_parse_change_log_payload_accepts_result_folder(tmp_path: Path) -> None:
    parse_path = tmp_path / "parsed-rights_issuance.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "rights_issuance",
                "records": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_parse_change_log_payload({"output_path": str(tmp_path), "mode": "rights_issuance"})

    assert payload["source_path"] == str(parse_path.resolve())


def test_build_parse_change_log_payload_requires_mode_for_result_folder(tmp_path: Path) -> None:
    parse_path = tmp_path / "parsed-bond_issuance.json"
    parse_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "bond_issuance",
                "records": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="mode is required"):
        build_parse_change_log_payload({"output_path": str(tmp_path)})


def test_build_parse_change_log_payload_rejects_missing_result_file_path(tmp_path: Path) -> None:
    result_path = tmp_path / "parsed-bond_issuance.json"

    with pytest.raises(ValueError, match="output_path must be a directory path"):
        build_parse_change_log_payload(
            {"output_path": str(result_path), "mode": "bond_issuance"}
        )

    assert not result_path.exists()


def test_build_parse_export_xlsx_rejects_missing_result_file_path(tmp_path: Path) -> None:
    result_path = tmp_path / "parsed-bond_issuance.json"

    with pytest.raises(ValueError, match="output_path must be a directory path"):
        build_parse_export_xlsx(str(result_path), "bond_issuance")

    assert not result_path.exists()


def test_parse_disclosure_html_payload_stops_when_cancelled(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for index in range(2):
        (viewer_dir / f"2025010100000{index}.html").write_text("<html></html>", encoding="utf-8")

    def fake_parser(html_text, *, file_path):
        cancel_disclosure_html_parse("parse-cancel-test")
        return {
            "acpt_no": Path(file_path).stem,
            "source_file": str(file_path),
            "mode": "security_transaction",
            "title": "",
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "cancel_token": "parse-cancel-test",
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
    html_path = viewer_dir / "20250101000001.html"
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
            "source_file": str(html_path.resolve()),
            "source_name": "20250101000001.html",
            "error_type": "RuntimeError",
            "error": "broken parser",
        }
    ]
    assert "progress_log" not in payload
    assert any("20250101000001.html (RuntimeError) broken parser" in line for line in progress_log)
    assert stored["errors"] == payload["errors"]
    assert "progress_log" not in stored


def test_parse_disclosure_html_payload_warns_when_expected_form_is_missing(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    html_path = viewer_dir / "20250101000001.html"
    html_path.write_text(
        """
        <html>
          <head><title>Different Disclosure Form</title></head>
          <body><p class="SECTION-1">Different Disclosure Form</p><table><tr><th>Field</th><td>Value</td></tr></table></body>
        </html>
        """,
        encoding="utf-8",
    )
    output_path = tmp_path / "parsed-bond_issuance.json"

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "bond_issuance",
        },
        progress_callback=progress_log.append,
    )
    stored = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["summary"]["parsed_files"] == 1
    assert payload["summary"]["failed_files"] == 0
    assert payload["warning_report_counts"] == {
        "count": len(payload["warnings"]),
        "report_count": 1,
        "weak_warning": {"count": 0, "report_count": 0, "reports": {}},
        "medium_warning": {"count": 0, "report_count": 0, "reports": {}},
        "strong_warning": {
            "count": len(payload["warnings"]),
            "report_count": 1,
            "reports": {
                "20250101000001": {
                    "count": len(payload["warnings"]),
                    "warnings": [item["warning"] for item in payload["warnings"]],
                }
            },
        },
    }
    assert payload["warnings"][0] == {
        "index": 1,
        "total": 1,
        "mode": "bond_issuance",
        "source_file": str(html_path.resolve()),
        "source_name": "20250101000001.html",
        "warning": "사채 발행 주요 표를 찾지 못했습니다. HTML 양식이 예상과 달라 일부 필드가 비어 있을 수 있습니다.",
        "level": "strong_warning",
        "warning_code": "bond_main_table_missing",
    }
    assert any(
        item["warning"].startswith("발행금액: 정해진 출처에서 값을 찾지 못했습니다.")
        for item in payload["warnings"]
    )
    assert payload["records"][0]["parse_warnings"] == [
        item["warning"] for item in payload["warnings"]
    ]
    assert "progress_log" not in payload
    assert any("파싱 경고 1/1: 20250101000001.html" in line for line in progress_log)
    assert stored["warning_report_counts"] == payload["warning_report_counts"]
    assert stored["warnings"] == payload["warnings"]
    assert "progress_log" not in stored


def test_parse_disclosure_html_payload_reports_rights_issuance_warnings(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    html_path = viewer_dir / "20250101000001.html"
    html_path.write_text(
        """
        <html>
          <head><title>Other Report</title></head>
          <body><table><tr><td>Field</td><td>Value</td></tr></table></body>
        </html>
        """,
        encoding="utf-8",
    )

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "rights_issuance",
        },
        progress_callback=progress_log.append,
    )

    assert payload["mode"] == "rights_issuance"
    assert payload["warnings"]
    assert payload["warnings"][:2] == [
        {
            "index": 1,
            "total": 1,
            "mode": "rights_issuance",
            "source_file": str(html_path.resolve()),
            "source_name": "20250101000001.html",
            "warning": "주입 제목이 없습니다.",
            "level": "strong_warning",
            "warning_code": "parse_warning",
        },
        {
            "index": 1,
            "total": 1,
            "mode": "rights_issuance",
            "source_file": str(html_path.resolve()),
            "source_name": "20250101000001.html",
            "warning": "주입 제목에서 유상증자/무상증자 유형을 확인하지 못했습니다. 일부 필드가 비어 있을 수 있습니다.",
            "level": "strong_warning",
            "warning_code": "rights_issue_type_missing",
        },
    ]
    strong_warnings = [
        item["warning"]
        for item in payload["warnings"]
        if item["level"] == "strong_warning"
    ]
    assert payload["warning_report_counts"] == {
        "count": len(payload["warnings"]),
        "report_count": 1,
        "weak_warning": {"count": 0, "report_count": 0, "reports": {}},
        "medium_warning": {"count": 0, "report_count": 0, "reports": {}},
        "strong_warning": {
            "count": len(strong_warnings),
            "report_count": 1,
            "reports": {
                "20250101000001": {
                    "count": len(strong_warnings),
                    "warnings": strong_warnings,
                }
            },
        },
    }
    assert "progress_log" not in payload
    assert any("파싱 경고 1/1: 20250101000001.html" in line for line in progress_log)


def test_parse_disclosure_html_payload_logs_success_progress_by_interval(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for index in range(3):
        (viewer_dir / f"2025010100000{index}.html").write_text("<html></html>", encoding="utf-8")

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "source_file": str(Path(file_path).resolve()),
            "mode": "security_transaction",
            "title": "",
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "progress_interval": 2,
        },
        progress_callback=progress_log.append,
    )

    assert "progress_log" not in payload
    assert not any("파싱 중 1/3:" in line for line in progress_log)
    assert not any("파싱 완료 1/3:" in line for line in progress_log)
    assert any("파싱 중간 확인: 이번 실행 2건 처리" in line for line in progress_log)


def test_parse_disclosure_html_payload_defaults_progress_interval_to_1000(
    tmp_path: Path, monkeypatch
) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    (viewer_dir / "20250101000001.html").write_text("<html></html>", encoding="utf-8")

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "source_file": str(Path(file_path).resolve()),
            "mode": "security_transaction",
            "title": "",
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
        },
        progress_callback=progress_log.append,
    )

    assert "progress_log" not in payload
    assert "진행 확인 간격: 1000건" in progress_log


def test_parse_disclosure_html_payload_accepts_parallel_workers(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for index in range(3):
        (viewer_dir / f"2025010100000{index}.html").write_text("<html></html>", encoding="utf-8")

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "source_file": str(Path(file_path).resolve()),
            "mode": "security_transaction",
            "title": "",
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
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
    html_path = viewer_dir / "20250101000001.html"
    html_path.write_text("<html></html>", encoding="utf-8")

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "source_file": str(Path(file_path).resolve()),
            "mode": "security_transaction",
            "title": "",
            "parse_warnings": ["weak warning", "medium warning", "strong warning"],
            "weak_warning": ["weak warning"],
            "medium_warning": ["medium warning"],
            "strong_warning": ["strong warning"],
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
        }
    )

    assert [(item["warning"], item["level"]) for item in payload["warnings"]] == [
        ("weak warning", "weak_warning"),
        ("medium warning", "medium_warning"),
        ("strong warning", "strong_warning"),
    ]
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


def test_parse_disclosure_html_payload_filters_records_by_bond_issue_method(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for name in ("20250101000001", "20250101000002", "20250101000003"):
        (viewer_dir / f"{name}.html").write_text("<html></html>", encoding="utf-8")

    issue_methods = {
        "20250101000001": "공모",
        "20250101000002": "사모",
        "20250101000003": "",
    }

    def fake_parser(html_text, *, file_path):
        acpt_no = Path(file_path).stem
        return {
            "acpt_no": acpt_no,
            "source_file": str(Path(file_path).resolve()),
            "mode": "security_transaction",
            "title": "",
            "사채발행방법": issue_methods[acpt_no],
            "parse_warnings": [f"{acpt_no} warning"],
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "parallel_workers": 2,
            "record_filters": [
                {"field": "사채발행방법", "operator": "in", "value": ["공모"]},
            ],
        },
        progress_callback=progress_log.append,
    )

    assert payload["summary"]["found_files"] == 3
    assert payload["summary"]["parsed_files"] == 1
    assert [record["acpt_no"] for record in payload["records"]] == ["20250101000001"]
    assert [warning["source_name"] for warning in payload["warnings"]] == [
        "20250101000001.html"
    ]
    assert payload["warning_report_counts"] == {
        "count": 1,
        "report_count": 1,
        "weak_warning": {"count": 0, "report_count": 0, "reports": {}},
        "medium_warning": {
            "count": 1,
            "report_count": 1,
            "reports": {
                "20250101000001": {
                    "count": 1,
                    "warnings": ["20250101000001 warning"],
                }
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


def test_parse_disclosure_html_payload_applies_filter_blocks(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for name in ("20250101000001", "20250101000002", "20250101000003"):
        (viewer_dir / f"{name}.html").write_text("<html></html>", encoding="utf-8")

    titles = {
        "20250101000001": "전환사채권발행결정",
        "20250101000002": "주주총회소집공고",
        "20250101000003": "유상증자결정",
    }

    def fake_parser(html_text, *, file_path):
        acpt_no = Path(file_path).stem
        return {
            "acpt_no": acpt_no,
            "source_file": str(Path(file_path).resolve()),
            "mode": "security_transaction",
            "title": titles[acpt_no],
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "parallel_workers": 2,
            "filter_blocks": [
                {"field": "title", "operator": "contains", "value": "증자"}
            ],
        },
        progress_callback=progress_log.append,
    )

    assert payload["summary"]["found_files"] == 3
    assert payload["summary"]["parsed_files"] == 1
    assert [record["acpt_no"] for record in payload["records"]] == ["20250101000003"]
    assert payload["filter_settings"] == {
        "filter_blocks": [
            {"field": "title", "operator": "contains", "value": "증자"}
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
        (viewer_dir / f"2025010100000{index}.html").write_text(
            "<html></html>", encoding="utf-8"
        )

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": Path(file_path).stem,
            "source_file": str(Path(file_path).resolve()),
            "mode": "security_transaction",
            "title": "주주총회소집공고",
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    progress_log: list[str] = []
    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
            "parallel_workers": 1,
            "progress_interval": 2,
            "filter_blocks": [
                {"field": "title", "operator": "contains", "value": "증자"}
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
        (viewer_dir / f"{name}.html").write_text(
            f"<table><tr><td>사채발행방법</td><td>{issue_method}</td></tr></table>",
            encoding="utf-8",
        )

    payload = build_parse_filter_candidates_payload(
        {
            "input_directory": str(viewer_dir),
            "mode": "bond_issuance",
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
                    "source_name": "20250101000001.html",
                    "source_file": str((viewer_dir / "20250101000001.html").resolve()),
                },
                {
                    "acpt_no": "20250101000003",
                    "source_name": "20250101000003.html",
                    "source_file": str((viewer_dir / "20250101000003.html").resolve()),
                },
            ],
        },
        {
            "value": "사모",
            "count": 1,
            "examples": [
                {
                    "acpt_no": "20250101000002",
                    "source_name": "20250101000002.html",
                    "source_file": str((viewer_dir / "20250101000002.html").resolve()),
                },
            ],
        },
    ]


def test_build_parse_filter_candidates_payload_uses_title_for_bonus_rights_issue_method(
    tmp_path: Path, monkeypatch
) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    (viewer_dir / "20250101000001.html").write_text("<html></html>", encoding="utf-8")
    (viewer_dir / HTML_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "disclosures": [
                    {
                        "acpt_no": "20250101000001",
                        "title": "[테스트] 무상증자결정",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def failing_parser(html_text, *, file_path):
        raise RuntimeError("full parser should not run")

    monkeypatch.setitem(PARSER_REGISTRY, "rights_issuance", failing_parser)

    payload = build_parse_filter_candidates_payload(
        {
            "input_directory": str(viewer_dir),
            "mode": "rights_issuance",
            "field": "증자방식",
            "parallel_workers": 1,
        }
    )

    assert payload["summary"] == {"records": 1, "candidates": 1, "errors": 0}
    assert payload["candidates"][0]["value"] == "-"


def test_build_parse_filter_candidates_payload_loads_rights_issue_methods_without_full_parse(
    tmp_path: Path, monkeypatch
) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    (viewer_dir / "20250101000001.html").write_text(
        "<table><tr><td>5. 증자방식</td><td>제3자배정증자</td></tr></table>",
        encoding="utf-8",
    )
    (viewer_dir / "20250101000002.html").write_text(
        "<table><tr><td>5. 증자방식</td><td>일반공모증자</td></tr></table>",
        encoding="utf-8",
    )
    (viewer_dir / "20250101000003.html").write_text(
        "<table><tr><td>5. 증자방식</td><td>제3자배정증자</td></tr></table>",
        encoding="utf-8",
    )

    def failing_parser(html_text, *, file_path):
        raise RuntimeError("full parser should not run")

    monkeypatch.setitem(PARSER_REGISTRY, "rights_issuance", failing_parser)

    payload = build_parse_filter_candidates_payload(
        {
            "input_directory": str(viewer_dir),
            "mode": "rights_issuance",
            "field": "증자방식",
            "parallel_workers": 1,
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
                    "source_name": "20250101000001.html",
                    "source_file": str((viewer_dir / "20250101000001.html").resolve()),
                },
                {
                    "acpt_no": "20250101000003",
                    "source_name": "20250101000003.html",
                    "source_file": str((viewer_dir / "20250101000003.html").resolve()),
                },
            ],
        },
        {
            "value": "일반공모증자",
            "count": 1,
            "examples": [
                {
                    "acpt_no": "20250101000002",
                    "source_name": "20250101000002.html",
                    "source_file": str((viewer_dir / "20250101000002.html").resolve()),
                },
            ],
        },
    ]


def test_parse_disclosure_html_payload_reports_failed_file_when_not_skipping(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    (viewer_dir / "20250101000001.html").write_text("<html></html>", encoding="utf-8")

    def fake_parser(html_text, *, file_path):
        raise RuntimeError("broken parser")

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    with pytest.raises(ValueError) as exc_info:
        parse_disclosure_html_payload(
            {
                "input_directory": str(viewer_dir),
                "output_directory": str(tmp_path),
                "mode": "security_transaction",
                "skip_errors": False,
            }
        )

    message = str(exc_info.value)
    assert "파싱 실패 1/1: 20250101000001.html" in message
    assert "(RuntimeError) broken parser" in message


def test_parse_disclosure_html_payload_applies_limit(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for index in range(3):
        (viewer_dir / f"2025010100000{index}.html").write_text("<html></html>", encoding="utf-8")

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "shareholder_meeting",
            "limit": 2,
        }
    )

    assert payload["summary"]["found_files"] == 2
    assert len(payload["records"]) == 2
    assert {record["mode"] for record in payload["records"]} == {"shareholder_meeting"}


def test_parse_disclosure_html_payload_uses_mode_registry(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    html_path = viewer_dir / "20250101000001.html"
    html_path.write_text("<html></html>", encoding="utf-8")

    def fake_parser(html_text, *, file_path):
        return {
            "acpt_no": "registry-called",
            "source_file": str(file_path),
            "mode": "security_transaction",
            "title": "",
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_directory": str(tmp_path),
            "mode": "security_transaction",
        }
    )

    assert payload["records"][0]["acpt_no"] == "registry-called"


def test_html_parse_modes_are_registered_documented_and_listed_in_ui() -> None:
    readme = (HTML_PARSERS_DIR / "README.md").read_text(encoding="utf-8")
    download_ui_html = GUI_HTML_DOWNLOAD_PAGE.read_text(encoding="utf-8")
    download_component_html = GUI_HTML_DOWNLOAD_COMPONENT.read_text(encoding="utf-8")
    content_download_ui_html = GUI_HTML_CONTENT_DOWNLOAD_PAGE.read_text(encoding="utf-8")
    section_split_page_html = GUI_HTML_SECTION_SPLIT_PAGE.read_text(encoding="utf-8")
    section_split_results_component_html = GUI_HTML_SECTION_SPLIT_RESULTS_COMPONENT.read_text(encoding="utf-8")
    section_split_ui_html = section_split_page_html + section_split_results_component_html
    parse_ui_html = GUI_HTML_PARSE_PAGE.read_text(encoding="utf-8")
    change_log_ui_html = GUI_HTML_CHANGE_LOG_PAGE.read_text(encoding="utf-8")
    utility_ui_html = GUI_UTILITY_PAGE.read_text(encoding="utf-8")

    assert set(PARSER_REGISTRY) == EXPECTED_PARSE_MODES
    for mode in EXPECTED_PARSE_MODES:
        assert mode in readme
        assert mode in parse_ui_html
    assert "/html-parse" in parse_ui_html
    assert "/html-content-download" in parse_ui_html
    assert "공시원문 목차 분리" in section_split_ui_html
    assert "/api/disclosures/html/sections/list" in section_split_ui_html
    assert "/api/disclosures/html/sections/kinds" in section_split_ui_html
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
    assert "목차 조합 모아보기" in section_split_ui_html
    assert "불러오기" in section_split_ui_html
    assert "sectionPatterns" in section_split_ui_html
    assert "maxSectionPatternCount" in section_split_ui_html
    assert "section_save_rules" in section_split_ui_html
    assert "selectedPatternTocIds" in section_split_ui_html
    assert "onTogglePatternSection" in section_split_ui_html
    assert "저장할 목차" in section_split_ui_html
    assert "sample_documents" in section_split_results_component_html
    assert "공시 열기" in section_split_results_component_html
    assert 'target="_blank"' in section_split_results_component_html
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
    assert "content" in content_download_ui_html
    assert "/api/disclosures/html/content-download/start" in download_component_html
    assert "/api/disclosures/html/download/check-existing" in download_component_html
    assert "/api/disclosures/html/content-download/check-existing" in download_component_html
    assert "externalTaskMode" in download_component_html
    assert "contentTaskMode" in download_component_html
    assert "외부 HTML 저장" in download_component_html
    assert "내부 HTML 저장" in download_component_html
    assert "외부 HTML 압축" in download_component_html
    assert "내부 HTML 병합" in download_component_html
    assert "외부 HTML 입력 경로" in download_component_html
    assert "압축 JSON 데이터 경로" in download_component_html
    assert "압축 설정" not in download_component_html
    assert "압축 처리" in download_component_html
    assert "병렬 워커 수" in download_component_html
    assert "parallel_workers" in download_component_html
    assert "외부 HTML 압축 JSON 파일" in download_component_html
    assert "외부 저장 화면의 외부 HTML 압축으로 만든 compressed-external-html.json 파일을 선택하세요." not in download_component_html
    assert "data.has_existing ||" in download_component_html
    assert 'typeof data.detected_output_split_by_year === "boolean"' in download_component_html
    assert "async function readJsonResponse" in download_component_html
    assert "const handleApplyExistingSettings = () => {" not in download_component_html
    assert "setDownloadSplitByYear(existingOutputSplitByYear)" not in download_component_html
    assert "저장 경로 분할저장을" not in download_component_html
    assert "detected_source_split_by_year !== contentSourceSplitByYear" not in download_component_html
    assert "/api/utility/partition-storage/start" not in download_component_html
    assert "분할저장 구조 전환" not in download_component_html
    assert "/api/utility/partition-storage/start" in utility_ui_html
    assert "분할저장 구조 전환" in utility_ui_html
    assert "move: false" in utility_ui_html
    assert "기존 파일 덮어쓰기" not in download_component_html
    assert "기존 원문 저장 범위 감지됨" in download_component_html
    assert "기존 원문 저장 ${formatInteger(existingCount)}건 감지됨" in download_component_html
    assert "기존 메타데이터 기준으로 설정 맞추기" not in download_component_html
    assert "분할저장 설정이 기존 폴더 구조와 다릅니다" in download_component_html
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
    assert parsed["기업명(행사대상)"] == "아이티센글로벌"
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


def test_parse_bond_issuance_does_not_fetch_selected_viewer_body(tmp_path: Path) -> None:
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

    parsed = parse_bond_issuance(wrapper_html.encode("utf-8"), file_path=wrapper_path)

    assert parsed["title"] == ""
    assert parsed["rcept_no"] is None
    assert parsed["correction_families"] == {}
    assert parsed["회차"] is None
    assert parsed["종류"] is None
    assert parsed["발행금액"] is None
    assert parsed["만기일"] is None
    assert parsed["투자자"] == []
    assert parsed["parse_warnings"][0] == (
        "사채 발행 주요 표를 찾지 못했습니다. HTML 양식이 예상과 달라 일부 필드가 비어 있을 수 있습니다."
    )
    assert any(
        warning.startswith("발행금액: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed["parse_warnings"]
    )


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


def test_parse_disclosure_html_payload_injects_manifest_title_for_bond_parser(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    html_path = input_dir / "20250102000009.html"
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
    (input_dir / HTML_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "disclosures": [
                    {
                        "acpt_no": "20250102000009",
                        "title": "[테스트] 교환사채권 발행결정",
                        "company_name": "테스트회사",
                        "market": "코스닥",
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
            "input_directory": str(input_dir),
            "output_directory": str(output_dir),
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


def test_parse_disclosure_html_payload_does_not_recover_title_after_parser(
    tmp_path: Path, monkeypatch
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    html_path = input_dir / "20250102000012.html"
    html_path.write_text("<html><body></body></html>", encoding="utf-8")
    (input_dir / HTML_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "disclosures": [
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
            "rcept_no": None,
            "correction_families": {},
            "상장구분": None,
            "source_file": str(Path(file_path).resolve()),
        }

    monkeypatch.setitem(PARSER_REGISTRY, "bond_issuance", parser_ignoring_title)

    payload = parse_disclosure_html_payload(
        {
            "mode": "bond_issuance",
            "input_directory": str(input_dir),
            "output_directory": str(output_dir),
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


def test_parse_disclosure_html_payload_injects_manifest_title_for_rights_parser(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    html_path = input_dir / "20250102000011.html"
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
    (input_dir / HTML_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "disclosures": [
                    {
                        "acpt_no": "20250102000011",
                        "title": "[테스트] 유상증자결정",
                        "company_name": "테스트회사",
                        "market": "코스닥",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = parse_disclosure_html_payload(
        {
            "mode": "rights_issuance",
            "input_directory": str(input_dir),
            "output_directory": str(output_dir),
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
    assert parsed["기업명(행사대상)"] == "테스트타겟"
    assert parsed["발행금액"] == 5_000_000_000
    assert parsed["발행목적"] == [["운영자금", 5_000_000_000]]
    assert parsed["field_parse_status"]["투자자"] == "source_not_found"
    assert parsed["행사가액"] == 12_500
    assert parsed["납입일"] == "2025년 01월 02일"
    assert parsed["만기일"] == "2028년 01월 02일"
    assert parsed["사채발행방법"] == "사모"
    assert parsed["행사시작일"] == "2026년 01월 02일"
    assert parsed["행사종료일"] == "2027년 12월 02일"
    assert parsed["투자자"] == []
    assert any(
        warning.startswith("투자자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed["parse_warnings"]
    )
    assert not any("발행대상자세부엔티티" in warning for warning in parsed["parse_warnings"])


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


def test_parse_bond_issuance_cleans_standalone_stock_suffix_from_target_company(tmp_path: Path) -> None:
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

    assert parsed["기업명(행사대상)"] == "테스트타겟"


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
        <tr><td>9. 전환에 관한 사항</td><td>전환에 따라 발행할 주식의 종류</td><td>(주)아이에스이커머스 기명식 보통주</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_bond_issuance(
        body_html.encode("utf-8"),
        file_path=fixture_path,
        title="전환사채발행결정",
    )

    assert parsed["기업명(행사대상)"] == "아이에스이커머스"


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
                "기업명(행사대상)": "테스트타겟",
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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

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
    assert parsed["발행가액"] == [["보통주식", 2_000], ["기타주식", 0]]
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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["증자 전 발행주식총수"] == [["보통주식", 100], ["기타주식", 20]]
    assert parsed["field_parse_status"]["증자 전 발행주식총수"] == "parsed"
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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["발행대상자"] == [["테스트조합", 5_806_443]]
    assert not any(
        "배정주식수 합계" in warning and "일치하지 않습니다" in warning
        for warning in parsed.get("parse_warnings", [])
    )


def test_parse_rights_issuance_keeps_duplicate_total_when_not_bottom_issue_target(tmp_path: Path) -> None:
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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["발행대상자"] == [
        ["인수금액 총계", 5_806_443],
        ["테스트조합", 5_806_443],
    ]
    assert any(
        "배정주식수 합계" in warning
        for warning in parsed.get("parse_warnings", [])
    )


def test_parse_rights_issuance_keeps_unsplit_total_like_bottom_issue_target(tmp_path: Path) -> None:
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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["발행대상자"] == [
        ["테스트조합", 5_806_443],
        ["인수금액총계", 5_806_443],
    ]
    assert any(
        "배정주식수 합계" in warning
        for warning in parsed.get("parse_warnings", [])
    )


def test_parse_rights_issuance_ignores_single_digit_roundoff_in_amount_check(
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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert not any(
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
        <tr><td>4. 자금조달의 목적</td><td>타법인유가증권취득자금 (원)</td><td>1,000</td></tr>
        <tr><td>5. 증자방식</td><td>일반공모증자</td></tr>
        <tr><td>6. 신주 발행가액</td><td>보통주식 (원)</td><td>100</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["발행목적"] == [["타법인 증권 취득자금", 1_000]]
    assert not any(
        "자금조달 목적 합계" in warning
        for warning in parsed.get("weak_warning", [])
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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["발행대상자"] == [["투자자A 투자자B", 200]]
    assert not any(
        "배정주식수 합계" in warning
        for warning in parsed.get("weak_warning", [])
    )


def test_parse_rights_issuance_ignores_target_amount_percentage_annotation(
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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["발행대상자"] == [["투자자A", 100_000]]
    assert not any(
        "배정주식수 합계" in warning
        for warning in parsed.get("weak_warning", [])
    )


def test_parse_rights_issuance_keeps_consecutive_ditto_columns_in_target_table(
    tmp_path: Path,
) -> None:
    fixture_path = tmp_path / "20250102000023.html"
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table>
        <tr><td>1. 신주의 종류와 수</td><td>보통주식 (주)</td><td>100,000</td></tr>
        <tr><td>5. 증자방식</td><td>제3자배정증자</td></tr>
      </table>
      <table>
        <tr>
          <th>제3자배정 대상자</th><th>회사 또는 최대주주와의 관계</th><th>선정경위</th>
          <th>증자결정 전후 6월이내 거래내역 및 계획</th><th>배정주식수 (주)</th><th>비 고</th>
        </tr>
        <tr><td>투자자A</td><td>상동</td><td>상동</td><td>상동</td><td>100,000</td><td>-</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["발행대상자"] == [["투자자A", 100_000]]
    assert not any(
        "배정주식수 합계" in warning
        for warning in parsed.get("weak_warning", [])
    )


def test_parse_rights_issuance_keeps_valid_target_table_after_correction_history_marker(
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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["발행대상자"] == [["테스트조합", 10]]
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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["납입일"] is None
    assert parsed["field_parse_status"]["납입일"] == "source_not_found"


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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["발행대상자"] == []
    assert parsed["field_parse_status"]["발행대상자"] == "source_found_empty"
    assert not any(
        warning.startswith("발행대상자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed.get("parse_warnings", [])
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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["발행대상자"] == []
    assert parsed["field_parse_status"]["발행대상자"] == "source_found_empty"
    assert not any(
        warning.startswith("발행대상자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed.get("parse_warnings", [])
    )


def test_parse_rights_issuance_still_extracts_single_named_target_row() -> None:
    fixture_path = Path("20250102000007.html")
    body_html = """
    <html><body>
      <p class="SECTION-1">유상증자결정</p>
      <table><tr><td>5. 증자방식</td><td>제3자배정증자</td></tr></table>
      <table>
        <tr><th>제3자배정 대상자</th><th>배정주식수 (주)</th></tr>
        <tr><td>테스트조합</td><td>1,000</td></tr>
      </table>
    </body></html>
    """

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

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
      <table><tr><td>5. 증자방식</td><td>제3자배정증자</td></tr></table>
    </body></html>
    """

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["발행대상자"] == []
    assert parsed["field_parse_status"]["발행대상자"] == "source_not_found"
    assert any(
        warning.startswith("발행대상자: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed.get("parse_warnings", [])
    )


def test_parse_rights_issuance_warns_when_title_does_not_identify_type(
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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["title"] == ""
    assert parsed["신주의 종류와 수"] == [["보통주식", 0], ["기타주식", 0]]
    assert parsed["증자방식"] is None
    assert "주입 제목이 없습니다." in parsed["parse_warnings"]
    assert "주입 제목이 없습니다." in parsed["strong_warning"]
    assert (
        "주입 제목에서 유상증자/무상증자 유형을 확인하지 못했습니다. 일부 필드가 비어 있을 수 있습니다."
        in parsed["parse_warnings"]
    )
    assert (
        "주입 제목에서 유상증자/무상증자 유형을 확인하지 못했습니다. 일부 필드가 비어 있을 수 있습니다."
        in parsed["strong_warning"]
    )
    assert any(
        warning.startswith("신주의 종류와 수: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed["parse_warnings"]
    )
    assert any(
        warning.startswith("증자방식: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed["parse_warnings"]
    )


def test_parse_rights_issuance_does_not_infer_bonus_type_from_table(
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

    parsed = parse_rights_issuance(body_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["증자방식"] is None
    assert "주입 제목이 없습니다." in parsed["parse_warnings"]
    assert (
        "주입 제목에서 유상증자/무상증자 유형을 확인하지 못했습니다. 일부 필드가 비어 있을 수 있습니다."
        in parsed["parse_warnings"]
    )
    assert any(
        warning.startswith("발행가액: 정해진 출처에서 값을 찾지 못했습니다.")
        for warning in parsed["parse_warnings"]
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
    )

    assert payload["visible_range_end"] == "2025-01-13"
    assert payload["chart"]["markers"][-1]["time"] == "2025-01-13"


def test_list_quanti_stock_codes_accepts_parent_directory(tmp_path: Path, monkeypatch) -> None:
    quanti_root = tmp_path / "Quanti_unified"
    by_item = quanti_root / "by_item"
    by_item.mkdir(parents=True)
    (by_item / "S100310.parquet").write_bytes(b"stub")

    class _FakeSchema:
        names = ["date", "close_005930", "close_000660"]

    class _FakeParquetFile:
        def __init__(self, path: Path) -> None:
            self.path = path
            self.schema_arrow = _FakeSchema()

    monkeypatch.setattr("finiq.market_desk.analytics.quanti.pq.ParquetFile", _FakeParquetFile)

    assert list_quanti_stock_codes(quanti_root) == ["000660", "005930"]


def test_build_quanti_market_history_collapses_wide_market_item(tmp_path: Path) -> None:
    quanti_root = tmp_path / "Quanti_unified"
    by_item = quanti_root / "by_item"
    by_item.mkdir(parents=True)
    market_item = "S999999"
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-05", "2024-01-08"]),
            "테스트전자_005930": ["KOSDAQ", "KOSDAQ", "KOSPI", "KOSPI"],
            "다른회사_000660": ["유가증권", "유가증권", None, None],
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
        {"stock_code": "000660", "market": "코스피", "start_date": date(2024, 1, 2), "end_date": date(2024, 1, 3)},
        {"stock_code": "005930", "market": "코스닥", "start_date": date(2024, 1, 2), "end_date": date(2024, 1, 4)},
        {"stock_code": "005930", "market": "코스피", "start_date": date(2024, 1, 5), "end_date": date(2024, 1, 8)},
    ]
    assert find_market_at(output_path, stock_code="005930", target_date=date(2024, 1, 4)) == "코스닥"
    assert find_market_at(output_path, stock_code="005930", target_date=date(2024, 1, 5)) == "코스피"
    assert find_market_at(output_path, stock_code="000660", target_date=date(2024, 1, 4)) is None


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


def test_check_existing_downloads_empty(tmp_path: Path) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    res = check_existing_downloads(str(tmp_path / "non_existent"))
    assert res == {"has_existing": False}

    res = check_existing_downloads(str(tmp_path))
    assert res == {"has_existing": False}


def test_check_existing_downloads_yearly(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: 100)

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

    res = check_existing_downloads(str(tmp_path))
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


def test_check_existing_downloads_single(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: 100)

    (tmp_path / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    (tmp_path / "kind_workflow.input.json").write_text(
        json.dumps(_trusted_download_input_snapshot(start_date="2026-02-01", end_date="2026-03-01")),
        encoding="utf-8"
    )

    res = check_existing_downloads(str(tmp_path))
    assert res["has_existing"] is True
    assert res["earliest_date"] == "2026-02-01"
    assert res["latest_date"] == "2026-03-01"
    assert res["ranges"][0]["start_date"] == "2026-02-01"
    assert res["ranges"][0]["end_date"] == "2026-03-01"
    assert res["ranges"][0]["status"] == "validated"


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


def test_check_existing_downloads_unverified(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: None)

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
    assert range_info["status"] == "unverified"
    assert range_info["local_count"] == 100
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

    res = check_existing_downloads(str(tmp_path), verify_with_kind=False)
    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "unverified"
    assert range_info["metadata_missing"] is True


def test_detect_existing_downloads_is_metadata_only(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import detect_existing_downloads

    def fail_if_called(*args, **kwargs):
        raise AssertionError("detect must not parse downloaded pages or call KIND")

    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fail_if_called)
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.inspect_download_directory_pages", fail_if_called)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(b"corrupted html")

    res = detect_existing_downloads(
        str(tmp_path),
        current_payload={
            "start_date": "2026-01-01",
            "end_date": "2026-05-01",
            "company_name": "",
            "submitter_name": "",
            "market_label": "검색대상",
            "securities_label": "전체",
            "disclosure_type_groups": {},
            "last_report_only": False,
            "page_size": 100,
        },
    )

    assert res["has_existing"] is True
    assert res["ranges"][0]["metadata_status"] == "missing"
    assert res["ranges"][0]["local_count"] is None
    assert res["ranges"][0]["kind_count"] is None


def test_inspect_folder_repairs_missing_metadata_when_current_payload_matches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from finiq.market_desk.web.features.downloads.kind_inspect import inspect_download_output_directory_payload

    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snapshot: 100)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )

    res = inspect_download_output_directory_payload(
        {
            "mode": "yearly",
            "output_directory": str(tmp_path),
            "start_date": "2026-01-01",
            "end_date": "2026-05-01",
            "company_name": "",
            "submitter_name": "",
            "market_label": "검색대상",
            "securities_label": "전체",
            "disclosure_type_groups": {},
            "last_report_only": False,
            "page_size": 100,
            "dry_run": True,
        }
    )

    assert res["deletion_candidate_count"] == 0
    assert res["download_needed_count"] == 0
    assert (folder / "kind_workflow.input.json").is_file()


def test_inspect_folder_reports_download_needed_for_missing_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from finiq.market_desk.web.features.downloads.kind_inspect import inspect_download_output_directory_payload

    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snapshot: 150)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )

    res = inspect_download_output_directory_payload(
        {
            "mode": "yearly",
            "output_directory": str(tmp_path),
            "start_date": "2026-01-01",
            "end_date": "2026-05-01",
            "company_name": "",
            "submitter_name": "",
            "market_label": "검색대상",
            "securities_label": "전체",
            "disclosure_type_groups": {},
            "last_report_only": False,
            "page_size": 100,
            "dry_run": True,
        }
    )

    assert res["deletion_candidate_count"] == 0
    assert res["download_needed_count"] == 50
    assert res["download_needed_pages"] == 1
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

    res = check_existing_downloads(
        str(tmp_path),
        current_payload={"output_directory": str(tmp_path)},
    )

    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "unverified"
    assert range_info["metadata_missing"] is True
    assert range_info["kind_count"] is None
    assert range_info["error_detail"] == "Missing or obsolete kind_workflow.input.json metadata to verify range against KIND."


def test_check_existing_downloads_treats_obsolete_metadata_as_missing(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads

    def fail_if_called(snapshot):
        raise RuntimeError("Obsolete metadata must not be used for KIND validation")

    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fail_if_called)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    (folder / "kind_workflow.input.json").write_text(
        json.dumps({"start_date": "2026-01-01", "end_date": "2026-05-01", "page_size": 100}),
        encoding="utf-8",
    )

    res = check_existing_downloads(str(tmp_path))

    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "unverified"
    assert range_info["metadata_missing"] is True
    assert range_info["metadata_obsolete"] is True
    assert range_info["kind_count"] is None
    assert range_info["error_detail"] == "Missing or obsolete kind_workflow.input.json metadata to verify range against KIND."


def test_check_existing_downloads_validates_missing_metadata_with_current_payload(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import DISCLOSURE_GROUPS, check_existing_downloads

    seen_snapshots = []
    def fake_kind_count(snapshot):
        seen_snapshots.append(snapshot)
        return 100

    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fake_kind_count)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    suffix, _, items = DISCLOSURE_GROUPS[0]
    code = items[0][0]

    res = check_existing_downloads(
        str(tmp_path),
        current_payload={
            "start_date": "2026-01-01",
            "end_date": "2026-05-01",
            "company_name": "삼성전자",
            "submitter_name": "",
            "market_label": "검색대상",
            "securities_label": "전체",
            "disclosure_type_groups": {suffix: [code]},
            "last_report_only": True,
            "page_size": 100,
        },
    )

    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "validated"
    assert range_info["metadata_missing"] is True
    assert not (folder / "kind_workflow.input.json").exists()
    assert seen_snapshots[0]["start_date"] == "2026-01-01"
    assert seen_snapshots[0]["end_date"] == "2026-05-01"
    assert seen_snapshots[0]["disclosure_type_groups"] == {suffix: [code]}
    assert seen_snapshots[0]["last_report_only"] is True


def test_check_existing_downloads_validates_obsolete_metadata_with_current_payload(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import check_existing_downloads

    seen_snapshots = []
    def fake_kind_count(snapshot):
        seen_snapshots.append(snapshot)
        return 100

    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", fake_kind_count)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )
    (folder / "kind_workflow.input.json").write_text(
        json.dumps({"start_date": "2026-01-01", "end_date": "2026-05-01", "page_size": 100}),
        encoding="utf-8",
    )

    res = check_existing_downloads(
        str(tmp_path),
        current_payload={
            "start_date": "2026-01-01",
            "end_date": "2026-05-01",
            "company_name": "삼성전자",
            "submitter_name": "",
            "market_label": "검색대상",
            "securities_label": "전체",
            "disclosure_type_groups": {},
            "last_report_only": False,
            "page_size": 100,
        },
    )

    assert res["has_existing"] is True
    range_info = res["ranges"][0]
    assert range_info["status"] == "validated"
    assert range_info["metadata_missing"] is True
    assert range_info["metadata_obsolete"] is True
    assert (folder / "kind_workflow.input.json").is_file()
    assert seen_snapshots[0]["start_date"] == "2026-01-01"
    assert seen_snapshots[0]["end_date"] == "2026-05-01"
    assert seen_snapshots[0]["search_filters"] == {"searchCorpName": "삼성전자"}


def test_create_folder_metadata_success(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import create_folder_metadata
    
    # Mock KIND live count to return 100
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: 100)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )

    payload = {
        "output_directory": str(folder),
        "start_date": "2026-01-01",
        "end_date": "2026-05-01",
        "company_name": "",
        "submitter_name": "",
        "market_label": "전체",
        "securities_label": "전체",
        "disclosure_type_groups": {},
        "last_report_only": False,
        "page_size": 100,
        "wait_seconds": 1.0,
        "timeout": 20.0
    }

    res = create_folder_metadata(payload)
    assert res["success"] is True
    assert res["local_count"] == 100
    assert res["kind_count"] == 100
    assert (folder / "kind_workflow.input.json").is_file()


def test_create_folder_metadata_mismatch_and_force(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import create_folder_metadata
    
    # Mock KIND live count to return 120 (local is 100)
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: 120)

    folder = tmp_path / "20260101_20260501"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )

    payload = {
        "output_directory": str(folder),
        "start_date": "2026-01-01",
        "end_date": "2026-05-01",
        "company_name": "",
        "submitter_name": "",
        "market_label": "전체",
        "securities_label": "전체",
        "disclosure_type_groups": {},
        "last_report_only": False,
        "page_size": 100,
        "wait_seconds": 1.0,
        "timeout": 20.0,
        "force": False
    }

    res = create_folder_metadata(payload)
    assert res["success"] is False
    assert res["local_count"] == 100
    assert res["kind_count"] == 120
    assert not (folder / "kind_workflow.input.json").is_file()

    # retry with force: True
    payload["force"] = True
    res = create_folder_metadata(payload)
    assert res["success"] is True
    assert res["local_count"] == 100
    assert res["kind_count"] == 120
    assert (folder / "kind_workflow.input.json").is_file()


def test_create_metadata_route(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.routers.download import create_download_router
    class DummyConfig:
        download_output_directory = None
        output_root = None

    router = create_download_router(DummyConfig())
    route_func = None
    for route in router.routes:
        if getattr(route, "path", None) == "/api/download/create-metadata":
            route_func = route.endpoint
            break
            
    assert route_func is not None

    called_payloads = []
    def mock_create_folder_metadata(payload):
        called_payloads.append(payload)
        return {"success": True}

    monkeypatch.setattr("finiq.market_desk.web.routers.download.create_folder_metadata", mock_create_folder_metadata)

    res = route_func({"output_directory": "/tmp/test", "force": True})
    assert res == {"success": True}
    assert called_payloads[0]["output_directory"] == "/tmp/test"
    assert called_payloads[0]["force"] is True


def test_infer_page_size_from_files(tmp_path: Path) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import _infer_page_size_from_files

    # 1. Empty folder
    assert _infer_page_size_from_files(tmp_path) == 100

    # 2. Folder with pages
    (tmp_path / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=50, total_items=150)
    )
    (tmp_path / "001_post_page_00002.body").write_bytes(
        _build_download_result_page_html(page_number=2, page_size=50, total_items=150)
    )
    (tmp_path / "001_post_page_00003.body").write_bytes(
        _build_download_result_page_html(page_number=3, page_size=50, total_items=150)
    )

    assert _infer_page_size_from_files(tmp_path) == 50


def test_infer_date_range_from_disclosures(tmp_path: Path) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import _infer_date_range_from_disclosures

    # Empty
    assert _infer_date_range_from_disclosures(tmp_path) is None

    # HTML with disclosures
    html_content = """
    <table class="list">
        <tr>
            <td>1</td>
            <td>2026-03-15</td>
            <td>회사A</td>
            <td><a>공시A</a></td>
            <td>제출인A</td>
        </tr>
        <tr>
            <td>2</td>
            <td>2026-04-20</td>
            <td>회사B</td>
            <td><a>공시B</a></td>
            <td>제출인B</td>
        </tr>
    </table>
    """
    (tmp_path / "001_post_page_00001.body").write_text(html_content, encoding="utf-8")

    res = _infer_date_range_from_disclosures(tmp_path)
    assert res == (date(2026, 3, 15), date(2026, 4, 20))


def test_check_existing_downloads_single_missing_metadata(tmp_path: Path, monkeypatch) -> None:
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

    res = check_existing_downloads(str(tmp_path), verify_with_kind=False)
    assert res["has_existing"] is True
    assert res["earliest_date"] == "2026-01-05"
    assert res["latest_date"] == "2026-01-05"
    assert res["ranges"][0]["metadata_missing"] is True
    assert res["ranges"][0]["folder_path"] == str(tmp_path)


def test_create_folder_metadata_with_inferred_page_size(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import create_folder_metadata
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: 150)

    # Local has 3 pages of page_size 50
    (tmp_path / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=50, total_items=150)
    )
    (tmp_path / "001_post_page_00002.body").write_bytes(
        _build_download_result_page_html(page_number=2, page_size=50, total_items=150)
    )
    (tmp_path / "001_post_page_00003.body").write_bytes(
        _build_download_result_page_html(page_number=3, page_size=50, total_items=150)
    )

    payload = {
        "output_directory": str(tmp_path),
        "start_date": "2026-01-01",
        "end_date": "2026-05-01",
        "company_name": "",
        "submitter_name": "",
        "market_label": "전체",
        "securities_label": "전체",
        "disclosure_type_groups": {},
        "last_report_only": False,
        "page_size": 100,  # UI sends 100, but files are actually page_size 50!
        "wait_seconds": 1.0,
        "timeout": 20.0
    }

    res = create_folder_metadata(payload)
    assert res["success"] is True
    # The generated input snapshot should have page_size 50, not 100!
    import json
    metadata = json.loads((tmp_path / "kind_workflow.input.json").read_text(encoding="utf-8"))
    assert metadata["page_size"] == 50


def test_create_folder_metadata_zero_items(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import create_folder_metadata
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: 0)

    # Local has 1 page of page_size 100, but total_items is 0
    (tmp_path / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=0)
    )

    payload = {
        "output_directory": str(tmp_path),
        "start_date": "2026-01-01",
        "end_date": "2026-05-01",
        "company_name": "",
        "submitter_name": "",
        "market_label": "전체",
        "securities_label": "전체",
        "disclosure_type_groups": {},
        "last_report_only": False,
        "page_size": 50,  # UI sends 50
        "wait_seconds": 1.0,
        "timeout": 20.0
    }

    res = create_folder_metadata(payload)
    assert res["success"] is True
    assert res["local_count"] == 0
    assert res["kind_count"] == 0
    import json
    metadata = json.loads((tmp_path / "kind_workflow.input.json").read_text(encoding="utf-8"))
    assert metadata["page_size"] == 50


def test_create_folder_metadata_force_string(tmp_path: Path, monkeypatch) -> None:
    from finiq.market_desk.web.features.downloads.kind_existing import create_folder_metadata
    monkeypatch.setattr("finiq.market_desk.web.features.downloads.kind_existing.get_current_kind_total_count", lambda snap: 120)

    (tmp_path / "001_post_page_00001.body").write_bytes(
        _build_download_result_page_html(page_number=1, page_size=100, total_items=100)
    )

    payload = {
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
        "wait_seconds": 1.0,
        "timeout": 20.0,
        "force": "false"  # String "false"
    }

    # Should fail because "false" means force is False
    res = create_folder_metadata(payload)
    assert res["success"] is False

    payload["force"] = "true"  # String "true"
    res = create_folder_metadata(payload)
    assert res["success"] is True
