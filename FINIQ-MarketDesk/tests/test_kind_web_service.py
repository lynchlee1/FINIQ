from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from web.service import (
    DISCLOSURE_GROUP_OTHER,
    build_insight_payload,
    filter_disclosures_payload,
    list_classification_files,
    load_company_index_payload,
)
from web.disclosure_html import collect_acpt_numbers_from_json, download_disclosure_html_payload
from web.disclosure_html_parse import PARSER_REGISTRY, parse_disclosure_html_payload
from web.html_parsers.bond_issuance import parse_bond_issuance
from web.html_parsers.common import expand_table, parse_html_document
from web.table_export import build_disclosure_table_payload
from analytics.quanti import list_quanti_stock_codes

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
HTML_PARSERS_DIR = REPO_ROOT / "FINIQ-MarketDesk" / "src" / "web" / "html_parsers"
GUI_HTML_DOWNLOAD_PAGE = REPO_ROOT / "FINIQ-GUI" / "apps" / "market-desk" / "html-download.html"
EXPECTED_PARSE_MODES = {
    "bond_issuance",
    "rights_issuance",
    "shareholder_meeting",
    "asset_transaction",
    "security_transaction",
}


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
                        "title": "전환사채발행결정",
                        "submitter": "테스트전자",
                        "acpt_no": "1",
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
                  <a onclick="openDisclsViewer('20250102000001','')" title="전환사채발행결정">전환사채발행결정</a>
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
    assert payload["disclosures"][0]["company_name"] == "테스트전자"
    assert any(event["unit_label"] == "폴더" and event["completed"] == 1 for event in progress_events)
    assert any(event["unit_label"] == "공시" and event["total"] == 2 for event in progress_events)


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
    assert payload["html_download_acpt_numbers"] == ["20250102000001"]


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


def test_filter_disclosures_payload_can_return_preview_with_full_html_transfer_numbers(tmp_path: Path) -> None:
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
    assert payload["filters"]["return_limit"] == 1
    assert payload["summary"]["matched_disclosures"] == 3
    assert payload["summary"]["returned_disclosures"] == 1
    assert [disclosure["acpt_no"] for disclosure in payload["disclosures"]] == ["3"]
    assert payload["html_download_acpt_numbers"] == ["3", "2", "1"]


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
                    "value": "전환사채발행결정",
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
            "SELECT company_name, disclosed_date, title, acpt_no FROM disclosures ORDER BY acpt_no"
        ).fetchall()
        metadata = dict(connection.execute("SELECT key, value FROM table_metadata").fetchall())
    finally:
        connection.close()

    assert rows[0] == ("테스트전자", "2025-01-02", "전환사채발행결정", "1")
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

    monkeypatch.setattr("web.disclosure_html.download_disclosure_viewer_htmls", fake_download)

    payload = download_disclosure_html_payload(
        {
            "output_directory": str(tmp_path / "viewer_html"),
            "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
        }
    )

    assert payload["requested_count"] == 1
    assert payload["saved_files"] == [str(tmp_path / "viewer_html" / "20250101000001.html")]


def test_download_disclosure_html_payload_accepts_source_json_path(tmp_path: Path, monkeypatch) -> None:
    def fake_download(**kwargs):
        return [Path(kwargs["output_directory"]) / f"{acpt_no}.html" for acpt_no in kwargs["acpt_numbers"]]

    monkeypatch.setattr("web.disclosure_html.download_disclosure_viewer_htmls", fake_download)
    source_json_path = tmp_path / "filtered-disclosures.json"
    source_json_path.write_text(
        json.dumps({"acptNumbers": ["20250101000001", "20250101000002"]}),
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
    assert payload["summary"] == {"found_files": 1, "parsed_files": 1, "failed_files": 0}
    assert payload["records"][0]["acpt_no"] == "20250101000001"
    assert payload["records"][0]["title"] == "Sample Disclosure"
    assert payload["records"][0]["raw_rows"] == [["Field", "Value"]]
    assert stored["format"] == payload["format"]
    assert stored["records"][0]["source_file"] == payload["records"][0]["source_file"]


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
    ui_html = GUI_HTML_DOWNLOAD_PAGE.read_text(encoding="utf-8")

    assert set(PARSER_REGISTRY) == EXPECTED_PARSE_MODES
    for mode in EXPECTED_PARSE_MODES:
        assert mode in readme
        assert f'value="{mode}"' in ui_html


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
    assert parsed["발행금액"] == 40_000_000_000
    assert parsed["발행목적"] == [
        ["시설자금", 0],
        ["영업양수자금", 0],
        ["운영자금", 8_000_000_000],
        ["채무상환자금", 32_000_000_000],
        ["타법인 증권 취득자금", 0],
        ["기타자금", 0],
    ]
    assert parsed["만기일"] == "2031년 05월 08일"
    assert parsed["할증률(%)"] == 5.101
    assert parsed["행사가액"] == 54_315
    assert parsed["행사대상"] == "주식회사 아이티센글로벌 기명식 보통주"
    assert parsed["전환시작일"] == "2027년 05월 08일"
    assert parsed["전환종료일"] == "2031년 04월 29일"
    assert parsed["리픽싱(%)"] == 70
    assert parsed["청약일"] == "2026년 04월 30일"
    assert parsed["납입일"] == "2026년 05월 08일"
    assert parsed["납입방법"] == "현금"
    assert parsed["발행대상자"] == [["아이티씨홀딩스(유)", 40_000_000_000]]
    assert parsed["발행대상자세부엔티티"] == [
        ["아이티씨홀딩스(유)", "임현철", "케이씨지아이혁신성장이에스지제1호사모투자 합자회사"]
    ]


def test_parse_bond_issuance_collects_multiple_target_entity_tables() -> None:
    fixture_path = TESTS_DIR / "fixtures" / "kind_bond_issuance_20260508000981.html"

    parsed = parse_bond_issuance(fixture_path.read_bytes(), file_path=fixture_path)

    assert parsed["발행대상자"] == [
        ["퀸버메자닌1호조합", 2_500_000_000],
        ["주식회사 비에스파트너", 2_000_000_000],
        ["송 준", 1_500_000_000],
    ]
    assert parsed["발행대상자세부엔티티"] == [
        ["퀸버메자닌1호조합", "이기승", "이기승"],
        ["주식회사 비에스파트너", "이기승", "박락호", "소민지"],
    ]


def test_build_insight_payload_groups_disclosures(tmp_path: Path, monkeypatch) -> None:
    fixture_path = _write_classification_fixture(tmp_path)

    monkeypatch.setattr(
        "web.service.fetch_stock_price_history",
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
        "web.service.fetch_stock_price_history",
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

    monkeypatch.setattr("analytics.quanti.pq.ParquetFile", _FakeParquetFile)

    assert list_quanti_stock_codes(quanti_root) == ["000660", "005930"]
