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
from finiq.market_desk.web.service import (
    DISCLOSURE_GROUP_OTHER,
    _clean_search_text,
    build_insight_payload,
    filter_disclosures_payload,
    list_classification_files,
    load_company_index_payload,
)
from finiq.market_desk.web.disclosure_html import (
    cancel_disclosure_html_download,
    clean_disclosure_html_output_directory_payload,
    collect_acpt_numbers_from_json,
    compress_disclosure_external_html_payload,
    download_disclosure_html_contents_payload,
    download_disclosure_html_payload,
    merge_disclosure_content_html_payload,
)
from finiq.market_desk.web.download import inspect_download_output_directory_payload
from finiq.market_desk.web.disclosure_html_parse import (
    PARSER_REGISTRY,
    build_bond_parse_summary_payload,
    build_parse_change_log_payload,
    cancel_disclosure_html_parse,
    parse_disclosure_html_payload,
)
from finiq.market_desk.web.html_parsers.bond_issuance import parse_bond_issuance
from finiq.market_desk.web.html_parsers.common import expand_table, parse_html_document
from finiq.market_desk.web.table_export import build_disclosure_table_payload
from finiq.market_desk.analytics.quanti import list_quanti_stock_codes
from finiq.market_desk.web.html_parsers.rights_issuance import parse_rights_issuance

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
HTML_PARSERS_DIR = REPO_ROOT / "src" / "finiq" / "market_desk" / "web" / "html_parsers"
GUI_APP_DIR = REPO_ROOT / "frontend" / "finiq_GUI" / "apps" / "market-desk" / "src" / "app"
GUI_HTML_DOWNLOAD_PAGE = GUI_APP_DIR / "html-download" / "page.tsx"
GUI_HTML_DOWNLOAD_COMPONENT = GUI_APP_DIR / "html-download" / "_components" / "HtmlDownloadPageView.tsx"
GUI_HTML_CONTENT_DOWNLOAD_PAGE = GUI_APP_DIR / "html-content-download" / "page.tsx"
GUI_HTML_PARSE_PAGE = GUI_APP_DIR / "html-parse" / "page.tsx"
GUI_HTML_CHANGE_LOG_PAGE = GUI_APP_DIR / "html-change-log" / "page.tsx"
EXPECTED_PARSE_MODES = {
    "bond_issuance",
    "rights_issuance",
    "shareholder_meeting",
    "asset_transaction",
    "security_transaction",
}


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


def _write_classification_fixture(tmp_path: Path) -> Path:
    payload = {
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
    fixture_path = tmp_path / "kind.company_classification.sample.json"
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return fixture_path


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
    build_disclosure_table_payload(
        {
            "classification_path": str(source_root),
            "output_path": str(sqlite_root / "kind.sqlite_manifest.json"),
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
    assert payload["source_sqlite_manifest_path"] == str((sqlite_root / "kind.sqlite_manifest.json").resolve())
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
    manifest_path = sqlite_root / "kind.sqlite_manifest.json"
    build_disclosure_table_payload(
        {
            "classification_path": str(source_root),
            "output_path": str(manifest_path),
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
    manifest_path = sqlite_root / "kind_kosdaq.sqlite_manifest.json"
    build_disclosure_table_payload(
        {
            "classification_path": str(source_root),
            "output_path": str(manifest_path),
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
    manifest_path = sqlite_root / "kind.sqlite_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_table_manifest_v1",
                "table_name": "disclosures",
                "summary": {"companies": 1, "disclosures": 1, "shards": 1},
                "shards": [
                    {
                        "year": "2025",
                        "path": str(shard_path),
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


def test_filter_disclosures_payload_rejects_sqlite_manifest_count_mismatch(
    tmp_path: Path,
) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    sqlite_root = tmp_path / "kind_sqlite"
    manifest_path = sqlite_root / "kind.sqlite_manifest.json"
    build_disclosure_table_payload(
        {
            "classification_path": str(source_root),
            "output_path": str(manifest_path),
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
    fixture_path = _write_classification_fixture(tmp_path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["companies"][0]["disclosures"].append(
        {
            "disclosed_at": "2025-01-20 09:00:00",
            "title": "공정공시(((주)삼성전자)공시내용",
            "submitter": "테스트전자",
            "acpt_no": "4",
        }
    )
    payload["summary"]["disclosures"] = 4
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

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
    fixture_path = _write_classification_fixture(tmp_path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["companies"][0]["disclosures"].append(
        {
            "disclosed_at": "2025-01-20 09:00:00",
            "title": "공정공시((주)삼성전자)공시내용",
            "submitter": "테스트전자",
            "acpt_no": "4",
        }
    )
    payload["summary"]["disclosures"] = 4
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

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
    fixture_path = _write_classification_fixture(tmp_path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["companies"][0]["disclosures"].append(dict(payload["companies"][0]["disclosures"][0]))
    payload["summary"]["disclosures"] = 4
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

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
    assert output_path.exists()
    manifest = json.loads(output_path.read_text(encoding="utf-8"))
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
    fixture_path = _write_classification_fixture(tmp_path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["summary"]["disclosures"] = 4
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="summary does not match loaded disclosures"):
        build_disclosure_table_payload({"classification_path": str(fixture_path)})


def test_build_disclosure_table_payload_rejects_malformed_disclosure_item(
    tmp_path: Path,
) -> None:
    fixture_path = _write_classification_fixture(tmp_path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["companies"][0]["disclosures"].append("not-a-disclosure")
    payload["summary"]["disclosures"] = 4
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match=r"disclosures\[3\] must be an object"):
        build_disclosure_table_payload({"classification_path": str(fixture_path)})


def test_build_disclosure_table_payload_accepts_source_body_folder(tmp_path: Path) -> None:
    source_root = _write_source_body_fixture(tmp_path)
    output_path = tmp_path / "kind.sqlite_manifest.json"

    payload = build_disclosure_table_payload(
        {
            "classification_path": str(source_root),
            "output_path": str(output_path),
        }
    )

    assert payload["source_type"] == "source_folder"
    assert payload["summary"]["disclosures"] == 2
    assert payload["summary"]["shards"] == 1
    manifest = json.loads(output_path.read_text(encoding="utf-8"))
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
    assert payload["output_path"] == str((source_root / "kind.sqlite_manifest.json").resolve())
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

    monkeypatch.setattr("finiq.market_desk.web.disclosure_html.download_disclosure_viewer_htmls", fake_download)

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


def test_download_disclosure_html_contents_payload_saves_body_html(tmp_path: Path, monkeypatch) -> None:
    def fake_download(**kwargs):
        assert kwargs["targets"] == [{"acpt_no": "20250101000001", "doc_no": "20250101000099"}]
        path = Path(kwargs["output_directory"]) / "20250101000001.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<html><body>content</body></html>", encoding="utf-8")
        kwargs["progress_callback"](f"Saved KIND content HTML to: {path}")
        return [path]

    monkeypatch.setattr("finiq.market_desk.web.disclosure_html.download_disclosure_content_htmls", fake_download)
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
        assert str(exc) == "source_directory is required"
    else:
        raise AssertionError("expected ValueError")


def test_download_disclosure_html_payload_accepts_source_json_path(tmp_path: Path, monkeypatch) -> None:
    def fake_download(**kwargs):
        return [Path(kwargs["output_directory"]) / f"{acpt_no}.html" for acpt_no in kwargs["acpt_numbers"]]

    monkeypatch.setattr("finiq.market_desk.web.disclosure_html.download_disclosure_viewer_htmls", fake_download)
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

    monkeypatch.setattr("finiq.market_desk.web.disclosure_html.download_disclosure_viewer_htmls", fake_download)
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


def test_download_disclosure_html_payload_logs_existing_html_overlap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_download(**kwargs):
        assert kwargs["acpt_numbers"] == ["20250101000002"]
        assert kwargs["skip_existing"] is False
        return [Path(kwargs["output_directory"]) / f"{acpt_no}.html" for acpt_no in kwargs["acpt_numbers"]]

    monkeypatch.setattr("finiq.market_desk.web.disclosure_html.download_disclosure_viewer_htmls", fake_download)
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

    monkeypatch.setattr("finiq.market_desk.web.disclosure_html.download_disclosure_viewer_htmls", fake_download)
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


def test_download_disclosure_html_payload_rejects_unexpected_resume_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fake_download(**kwargs):
        raise AssertionError(
            "download should not start when output directory has unexpected files"
        )

    monkeypatch.setattr(
        "finiq.market_desk.web.disclosure_html.download_disclosure_viewer_htmls",
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
        "finiq.market_desk.web.disclosure_html._collect_content_targets_from_external_directory",
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

    monkeypatch.setattr("finiq.market_desk.web.disclosure_html.download_disclosure_viewer_htmls", fake_download)

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
    from finiq.market_desk.web.download import (
        start_inspect_folder_job,
        cancel_download_job,
        get_download_job,
        DownloadCancelled,
    )
    import time

    def blocking_inspect(payload, progress_callback=None, cancel_check=None):
        for _ in range(200):
            if cancel_check is not None and cancel_check():
                raise DownloadCancelled("Folder inspection cancelled by the user")
            time.sleep(0.01)
        return {"format": "kind_download_folder_cleanup_v1"}

    monkeypatch.setattr(
        "finiq.market_desk.web.download.inspect_download_output_directory_payload",
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

    monkeypatch.setattr("finiq.market_desk.web.disclosure_html.download_disclosure_content_htmls", fake_download)

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

    monkeypatch.setattr("finiq.market_desk.web.disclosure_html.download_disclosure_content_htmls", fake_download)

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

    monkeypatch.setattr("finiq.market_desk.web.disclosure_html.download_disclosure_content_htmls", fake_download)

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
          <input type="hidden" name="acptNo" value="20250101000001" />
          <input type="hidden" name="tempTitle" value="뷰어 제목" />
          <h1 class="ttl">테스트 (123456)</h1>
          <select id="mainDoc">
            <option value="20250101000999|Y" selected="selected">본문</option>
          </select>
          <select id="attachedDoc">
            <option value="20250101000888">첨부</option>
          </select>
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
    assert saved["format"] == "finiq_disclosure_external_html_compress_v1"
    assert "html" not in saved["records"][0]
    assert saved["records"][0]["acpt_no"] == "20250101000001"
    assert saved["records"][0]["title"] == "뷰어 제목"
    assert saved["records"][0]["selected_main_doc_no"] == "20250101000999"
    assert saved["records"][0]["attached_docs"][0]["doc_no"] == "20250101000888"
    assert saved["records"][0]["metadata"]["market"] == "코스닥"


def test_compress_disclosure_external_html_payload_reads_split_input(tmp_path: Path) -> None:
    input_directory = tmp_path / "viewer_html"
    (input_directory / "2025").mkdir(parents=True)
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
        }
    )

    assert payload["split_by_year"] is True
    assert payload["summary"]["compressed_files"] == 1
    assert payload["verification"]["passed"] is True
    assert payload["verification"]["missing_records"] == 0
    output_path = tmp_path / "compressed" / "2025" / "compressed-external-html.json"
    assert payload["written_files"] == [str(output_path)]
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["records"][0]["year"] == "2025"


def test_download_disclosure_html_payload_stops_when_cancelled(tmp_path: Path, monkeypatch) -> None:
    def fake_download(**kwargs):
        saved_paths = []
        for acpt_no in kwargs["acpt_numbers"]:
            if kwargs["cancel_check"]():
                break
            saved_paths.append(Path(kwargs["output_directory"]) / f"{acpt_no}.html")
            cancel_disclosure_html_download("cancel-test")
        return saved_paths

    monkeypatch.setattr("finiq.market_desk.web.disclosure_html.download_disclosure_viewer_htmls", fake_download)

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
          <body><table><tr><th>Field</th><td>Value</td></tr></table></body>
        </html>
        """,
        encoding="utf-8",
    )
    (viewer_dir / "ignore.txt").write_text("not html", encoding="utf-8")
    output_path = tmp_path / "parsed.json"

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_path": str(output_path),
            "mode": "bond_issuance",
        }
    )
    stored = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["format"] == "finiq_disclosure_html_parse_v1"
    assert payload["mode"] == "bond_issuance"
    assert payload["summary"] == {"found_files": 1, "parsed_files": 1, "failed_files": 0, "resumed_files": 0}
    assert payload["cancelled"] is False
    assert "파싱 대상 HTML 1건" in payload["progress_log"][0]
    assert payload["progress_log"][-1].startswith("파싱 결과 JSON 저장 완료:")
    assert payload["records"][0]["acpt_no"] == "20250101000001"
    assert payload["records"][0]["title"] == "Sample Disclosure"
    assert "raw_rows" not in payload["records"][0]
    assert "raw_tables" not in payload["records"][0]
    assert stored["format"] == payload["format"]
    assert stored["records"][0]["source_file"] == payload["records"][0]["source_file"]
    assert stored["progress_log"] == payload["progress_log"]


def test_parse_disclosure_html_payload_prefers_download_manifest_market(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    (viewer_dir / "20250101000001.html").write_text(
        """
        <html>
          <head><title>Sample Disclosure</title></head>
          <body>유가증권시장 <table><tr><th>Field</th><td>Value</td></tr></table></body>
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
            "mode": "bond_issuance",
            "resume": False,
        }
    )

    assert payload["records"][0]["상장구분"] == "코스닥"
    assert payload["records"][0]["기업명(발행사)"] == "테스트발행사"


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
            "mode": "security_transaction",
            "resume": False,
        }
    )

    for record in payload["records"]:
        family = record["correction_families"]["20250102009999"]
        assert family["members"] == [
            {"sequence": 0, "acpt_no": "20250101000001", "rcept_no": "20250101009999"},
            {"sequence": 1, "acpt_no": "20250102000002", "rcept_no": "20250102009999"},
        ]


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
                        "기업명(발행사)": "발행사",
                        "회차": "1",
                        "종류": "CB",
                        "기업명(행사대상)": "대상회사",
                        "상장구분": "코스닥",
                        "발행금액": 1_000_000_000,
                        "행사가액": 1000,
                        "납입일": "2025년 01월 02일",
                        "만기일": "2028년 01월 02일",
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

    payload = build_bond_parse_summary_payload({"output_path": str(parse_path)})

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
    assert payload["records"][0]["fields"]["투자자"] == [["테스트조합", 1_000_000_000]]
    assert "리픽싱(%)" not in payload["records"][0]["fields"]


def test_build_bond_parse_summary_payload_includes_source_preview(tmp_path: Path) -> None:
    source_path = tmp_path / "20250102000002.html"
    source_path.write_text(
        """
        <html>
          <head><title>전환사채권발행결정</title></head>
          <body>
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
                        "source_file": str(source_path),
                        "기업명(발행사)": "발행사",
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

    payload = build_bond_parse_summary_payload({"output_path": str(parse_path)})

    preview = payload["records"][0]["source_preview"]
    assert preview["available"] is True
    assert preview["source_file"] == str(source_path)
    assert preview["tables"][0]["rows"][0] == ["1. 사채의 종류", "전환사채"]
    assert preview["tables"][0]["rows"][1] == ["2. 사채의 권면(전자등록)총액", "1,000,000,000"]


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

    payload = build_parse_change_log_payload({"output_path": str(parse_path)})

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

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "mode": "security_transaction",
            "cancel_token": "parse-cancel-test",
        }
    )

    assert payload["cancelled"] is True
    assert payload["summary"]["found_files"] == 2
    assert payload["summary"]["parsed_files"] == 1
    assert any("중지 요청" in line for line in payload["progress_log"])


def test_parse_disclosure_html_payload_records_failed_file_details(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    html_path = viewer_dir / "20250101000001.html"
    html_path.write_text("<html></html>", encoding="utf-8")
    output_path = tmp_path / "parsed.json"

    def fake_parser(html_text, *, file_path):
        raise RuntimeError("broken parser")

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_path": str(output_path),
            "mode": "security_transaction",
            "skip_errors": True,
        }
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
    assert any("20250101000001.html (RuntimeError) broken parser" in line for line in payload["progress_log"])
    assert stored["errors"] == payload["errors"]


def test_parse_disclosure_html_payload_warns_when_expected_form_is_missing(tmp_path: Path) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    html_path = viewer_dir / "20250101000001.html"
    html_path.write_text(
        """
        <html>
          <head><title>Different Disclosure Form</title></head>
          <body><table><tr><th>Field</th><td>Value</td></tr></table></body>
        </html>
        """,
        encoding="utf-8",
    )
    output_path = tmp_path / "parsed.json"

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_path": str(output_path),
            "mode": "bond_issuance",
            "resume": False,
        }
    )
    stored = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["summary"]["parsed_files"] == 1
    assert payload["summary"]["failed_files"] == 0
    assert payload["warnings"] == [
        {
            "index": 1,
            "total": 1,
            "mode": "bond_issuance",
            "source_file": str(html_path.resolve()),
            "source_name": "20250101000001.html",
            "warning": "사채 발행 주요 표를 찾지 못했습니다. HTML 양식이 예상과 달라 일부 필드가 비어 있을 수 있습니다.",
        }
    ]
    assert payload["records"][0]["parse_warnings"] == [payload["warnings"][0]["warning"]]
    assert any("파싱 경고 1/1: 20250101000001.html" in line for line in payload["progress_log"])
    assert stored["warnings"] == payload["warnings"]


def test_parse_disclosure_html_payload_checkpoints_and_resumes(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    first = viewer_dir / "20250101000001.html"
    second = viewer_dir / "20250101000002.html"
    first.write_text("<html></html>", encoding="utf-8")
    second.write_text("<html></html>", encoding="utf-8")
    output_path = tmp_path / "parsed.json"
    calls: list[str] = []

    def fake_parser(html_text, *, file_path):
        calls.append(Path(file_path).name)
        if Path(file_path).name == second.name and len(calls) == 2:
            raise RuntimeError("stop after checkpoint")
        return {
            "acpt_no": Path(file_path).stem,
            "source_file": str(Path(file_path).resolve()),
            "mode": "security_transaction",
            "title": "",
            "raw_rows": [],
        }

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    try:
        parse_disclosure_html_payload(
            {
                "input_directory": str(viewer_dir),
                "output_path": str(output_path),
                "mode": "security_transaction",
                "skip_errors": False,
                "progress_interval": 1,
            }
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")

    checkpoint = json.loads(output_path.read_text(encoding="utf-8"))
    assert [record["source_file"] for record in checkpoint["records"]] == [str(first.resolve())]

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_path": str(output_path),
            "mode": "security_transaction",
            "progress_interval": 1,
            "resume": True,
        }
    )

    assert payload["summary"]["resumed_files"] == 1
    assert payload["summary"]["parsed_files"] == 2
    assert calls == [first.name, second.name, second.name]
    assert any("이어하기 건너뜀 중간 확인: 1/1건" in line for line in payload["progress_log"])


def test_parse_disclosure_html_payload_logs_resume_skips_by_interval(tmp_path: Path, monkeypatch) -> None:
    viewer_dir = tmp_path / "viewer_html"
    viewer_dir.mkdir()
    for index in range(3):
        (viewer_dir / f"2025010100000{index}.html").write_text("<html></html>", encoding="utf-8")
    output_path = tmp_path / "parsed.json"
    output_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_parse_v1",
                "mode": "security_transaction",
                "records": [
                    {"source_file": str((viewer_dir / "20250101000000.html").resolve())},
                    {"source_file": str((viewer_dir / "20250101000001.html").resolve())},
                    {"source_file": str((viewer_dir / "20250101000002.html").resolve())},
                ],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )

    def fake_parser(html_text, *, file_path):
        raise AssertionError("resume should skip every file")

    monkeypatch.setitem(PARSER_REGISTRY, "security_transaction", fake_parser)

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "output_path": str(output_path),
            "mode": "security_transaction",
            "progress_interval": 2,
            "resume": True,
        }
    )

    assert not any("이어하기 건너뜀 1/3:" in line for line in payload["progress_log"])
    assert not any("이어하기 건너뜀 2/3:" in line for line in payload["progress_log"])
    assert any("이어하기 건너뜀 중간 확인: 2/3건" in line for line in payload["progress_log"])
    assert any("이어하기 건너뜀 완료: 3/3건" in line for line in payload["progress_log"])


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

    payload = parse_disclosure_html_payload(
        {
            "input_directory": str(viewer_dir),
            "mode": "security_transaction",
            "progress_interval": 2,
        }
    )

    assert not any("파싱 중 1/3:" in line for line in payload["progress_log"])
    assert not any("파싱 완료 1/3:" in line for line in payload["progress_log"])
    assert any("파싱 중간 확인: 이번 실행 2건 처리" in line for line in payload["progress_log"])


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
            "mode": "security_transaction",
        }
    )

    assert payload["records"][0]["acpt_no"] == "registry-called"


def test_html_parse_modes_are_registered_documented_and_listed_in_ui() -> None:
    readme = (HTML_PARSERS_DIR / "README.md").read_text(encoding="utf-8")
    download_ui_html = GUI_HTML_DOWNLOAD_PAGE.read_text(encoding="utf-8")
    download_component_html = GUI_HTML_DOWNLOAD_COMPONENT.read_text(encoding="utf-8")
    content_download_ui_html = GUI_HTML_CONTENT_DOWNLOAD_PAGE.read_text(encoding="utf-8")
    parse_ui_html = GUI_HTML_PARSE_PAGE.read_text(encoding="utf-8")
    change_log_ui_html = GUI_HTML_CHANGE_LOG_PAGE.read_text(encoding="utf-8")

    assert set(PARSER_REGISTRY) == EXPECTED_PARSE_MODES
    for mode in EXPECTED_PARSE_MODES:
        assert mode in readme
        assert mode in parse_ui_html
    assert "/html-parse" in parse_ui_html
    assert "/html-content-download" in parse_ui_html
    assert "공시원문 외부 저장" in download_component_html
    assert "공시원문 내부 저장" in download_component_html
    assert "content" in content_download_ui_html
    assert "/api/disclosures/html/content-download/start" in download_component_html
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


def test_parse_bond_issuance_extracts_kind_sample_fields() -> None:
    fixture_path = TESTS_DIR / "fixtures" / "kind_bond_issuance_20260508000643.html"

    parsed = parse_bond_issuance(fixture_path.read_bytes(), file_path=fixture_path)

    assert parsed["회차"] == "16"
    assert parsed["종류"] == "CB"
    assert parsed["발행금액"] == 40_000_000_000
    assert parsed["상장구분"] == "기타"
    assert parsed["만기일"] == "2031년 05월 08일"
    assert parsed["행사가액"] == 54_315
    assert parsed["기업명(행사대상)"] == "아이티센글로벌"
    assert parsed["행사시작일"] == "2027년 05월 08일"
    assert parsed["행사종료일"] == "2031년 04월 29일"
    assert parsed["납입일"] == "2026년 05월 08일"
    assert parsed["투자자"] == [["아이티씨홀딩스(유)", 40_000_000_000]]
    assert parsed["발행대상자세부엔티티"] == [
        ["아이티씨홀딩스(유)", "임현철", "케이씨지아이혁신성장이에스지제1호사모투자 합자회사"]
    ]
    for removed_field in ("발행목적", "할증률(%)", "행사대상", "전환시작일", "전환종료일", "리픽싱(%)", "청약일", "납입방법"):
        assert removed_field not in parsed


def test_parse_bond_issuance_resolves_selected_viewer_body(monkeypatch, tmp_path: Path) -> None:
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
    body_html = """
    <html><body>
      <p class="CORRECTION">정 정 신 고 (보고)</p>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>9</td><td>종류</td><td>무기명 무보증 전환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>15,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>0</td></tr>
      </table>
      <h2 class="SECTION-1"><p class="SECTION-1">전환사채발행결정</p></h2>
      <table>
        <tr><td>1. 사채의 종류</td><td>회차</td><td>9</td><td>종류</td><td>무기명 무보증 전환사채</td></tr>
        <tr><td>2. 사채의 권면총액 (원)</td><td>15,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>시설자금 (원)</td><td>-</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>운영자금 (원)</td><td>4,000,000,000</td></tr>
        <tr><td>3. 자금조달의 목적</td><td>기타자금 (원)</td><td>11,000,000,000</td></tr>
        <tr><td>5. 사채만기일</td><td>2011년 10월 01일</td></tr>
      </table>
    </body></html>
    """

    monkeypatch.setattr(
        "finiq.market_desk.web.html_parsers.bond_issuance.utils.fetch_selected_viewer_body",
        lambda html_text, **kwargs: body_html.encode("utf-8"),
    )

    parsed = parse_bond_issuance(wrapper_html.encode("utf-8"), file_path=wrapper_path)

    assert parsed["title"] == "[에스브이에이치] [정정]전환사채발행결정"
    assert parsed["rcept_no"] == "20080826000555"
    assert parsed["correction_families"] == {
        "20080826000555": {
            "current_sequence": 1,
            "members": [
                {"sequence": 0, "acpt_no": None, "rcept_no": "00000000867311"},
                {"sequence": 1, "acpt_no": "20080826000187", "rcept_no": "20080826000555"},
            ],
        }
    }
    assert parsed["회차"] == "9"
    assert parsed["종류"] == "CB"
    assert parsed["발행금액"] == 15_000_000_000
    assert parsed["만기일"] == "2011년 10월 01일"
    assert parsed["투자자"] == []


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

    parsed = parse_bond_issuance(body_html.encode("utf-8"), file_path=fixture_path)

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
    monkeypatch, tmp_path: Path, acpt_no: str, body_html: str, expected: dict[str, object]
) -> None:
    fixture_path = tmp_path / f"{acpt_no}.html"
    fixture_path.write_text(
        "<html><body><select id='mainDoc'><option value='DOC001|Y' selected>main</option></select></body></html>",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "finiq.market_desk.web.html_parsers.bond_issuance.utils.fetch_selected_viewer_body",
        lambda html_text, **kwargs: body_html.encode("utf-8"),
    )

    parsed = parse_bond_issuance(fixture_path.read_bytes(), file_path=fixture_path)

    assert parsed["acpt_no"] == acpt_no
    for key, value in expected.items():
        assert parsed[key] == value


def test_parse_bond_issuance_collects_multiple_target_entity_tables() -> None:
    fixture_path = TESTS_DIR / "fixtures" / "kind_bond_issuance_20260508000981.html"

    parsed = parse_bond_issuance(fixture_path.read_bytes(), file_path=fixture_path)

    assert parsed["투자자"] == [
        ["퀸버메자닌1호조합", 2_500_000_000],
        ["주식회사 비에스파트너", 2_000_000_000],
        ["송 준", 1_500_000_000],
    ]
    assert parsed["발행대상자세부엔티티"] == [
        ["퀸버메자닌1호조합", "이기승", "이기승"],
        ["주식회사 비에스파트너", "이기승", "박락호", "소민지"],
    ]


def test_parse_rights_issuance_extracts_kind_stockissue_fields(monkeypatch) -> None:
    fixture_path = Path("20240822000349.html")
    wrapper_html = "<html><body><select id='mainDoc'><option value='DOC001|Y' selected>main</option></select></body></html>"
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
        <tr><td rowspan="2">7. 기준주가</td><td>보통주식 (원)</td><td>1,783</td></tr>
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
    monkeypatch.setattr(
        "finiq.market_desk.web.html_parsers.rights_issuance.fetch_selected_viewer_body",
        lambda html_text, **kwargs: body_html.encode("utf-8"),
    )

    parsed = parse_rights_issuance(wrapper_html.encode("utf-8"), file_path=fixture_path)

    assert parsed["신주의 종류와 수"] == [["보통주식", 2_495_327], ["기타주식", 0]]
    assert parsed["발행목적"] == [
        ["시설자금", 2_002_499_917],
        ["영업양수자금", 0],
        ["운영자금", 2_002_499_918],
        ["채무상환자금", 0],
        ["타법인 증권 취득자금", 0],
        ["기타자금", 0],
    ]
    assert parsed["발행가액"] == [["보통주식", 1_605], ["기타주식", 0]]
    assert parsed["기준주가"] == [["보통주식", 1_783], ["기타주식", 0]]
    assert parsed["증자방식"] == "제3자배정증자"
    assert parsed["납입일"] == "2024년 08월 30일"
    assert parsed["신주권교부예정일"] == "2023년 10월 04일"
    assert parsed["상장예정일"] == "2024년 10월 04일"
    assert parsed["발행대상자"] == [["주식회사 에프앤지", 2_495_327]]
    assert parsed["발행대상자세부엔티티"] == [["주식회사 에프앤지", "이미란", "(주)에스제이씨"]]


def test_build_insight_payload_groups_disclosures(tmp_path: Path, monkeypatch) -> None:
    fixture_path = _write_classification_fixture(tmp_path)

    monkeypatch.setattr(
        "finiq.market_desk.web.service.fetch_stock_price_history",
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
    fixture_path = _write_classification_fixture(tmp_path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    payload["companies"][0]["disclosures"] = [
        {
            "disclosed_at": "2025-01-10 20:01:00",
            "title": "장후 공시",
            "submitter": "테스트전자",
            "acpt_no": "after-close",
        }
    ]
    fixture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        "finiq.market_desk.web.service.fetch_stock_price_history",
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
