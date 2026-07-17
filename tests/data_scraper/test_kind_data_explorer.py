"""Tests for KIND downloaded-data explorer helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from finiq.data_scraper.workflow import KIND_WORKFLOW_INPUT_FORMAT
from finiq.data_scraper.data.explorer import (
    build_result_folder_records,
    detect_pagination,
    extract_unique_disclosure_titles,
    find_result_folders,
    load_folder_disclosure_rows,
    load_folder_simpletable_rows,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
DISCLOSURE_RESULTS_HTML = """
<table class="list" summary="번호, 일시, 회사명, 공시제목, 제출인">
  <tbody>
    <tr>
      <td>1</td>
      <td>2024-01-15 12:00</td>
      <td>
        <a id="companysum" title="테스트회사" onclick="companysummary_open('005930')">테스트회사</a>
        <img alt="유가증권" />
      </td>
      <td>
        <a title="테스트 공시" onclick="openDisclsViewer('20240115000001','')">테스트 공시</a>
      </td>
      <td>테스트제출인</td>
    </tr>
    <tr>
      <td>2</td>
      <td>2024-01-16 09:00</td>
      <td>
        <a id="companysum" title="테스트회사" onclick="companysummary_open('005930')">테스트회사</a>
        <img alt="유가증권" />
        <img alt="관리종목" />
      </td>
      <td>
        <a title="추가 공시" onclick="openDisclsViewer('20240116000002','20240116000099')">추가 공시</a>
      </td>
      <td>테스트제출인</td>
    </tr>
  </tbody>
</table>
"""


def _workflow_input(start_date: str, end_date: str) -> dict[str, object]:
    return {
        "format": KIND_WORKFLOW_INPUT_FORMAT,
        "request_headers": {"User-Agent": "pytest"},
        "start_date": start_date,
        "end_date": end_date,
        "page_size": 100,
        "search_filters": [],
        "disclosure_type_groups": {},
        "last_report_only": False,
        "include_previous_disclosures": None,
        "wait_seconds_between_requests": 0,
        "timeout": 20,
    }


def test_find_result_folders_discovers_nested_download_directories(tmp_path: Path) -> None:
    first = tmp_path / "20240101_20240131"
    second = tmp_path / "nested" / "20240201_20240228"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    (first / "001_post_page_00001.body").write_bytes(FIXTURES_DIR.joinpath("kind_response.html").read_bytes())
    (second / "001_post_page_00001.body").write_bytes(FIXTURES_DIR.joinpath("kind_response.html").read_bytes())

    discovered = find_result_folders(tmp_path)

    assert discovered == [first.resolve(), second.resolve()]


def test_load_folder_rows_and_pagination_from_downloaded_bodies(tmp_path: Path) -> None:
    folder = tmp_path / "20240101_20240131"
    folder.mkdir()
    body_markup = DISCLOSURE_RESULTS_HTML.encode("utf-8")
    paging_markup = """
    <section class="paging-group">
      <div class="paging type-00">
        전체 <em>101</em>건 : <strong>2</strong>/3
      </div>
    </section>
    """.encode("utf-8")

    (folder / "001_post_page_00001.body").write_bytes(body_markup)
    (folder / "002_post_page_00002.body").write_bytes(body_markup + paging_markup)

    disclosure_rows = load_folder_disclosure_rows(folder)
    simpletable_rows = load_folder_simpletable_rows(folder)
    pagination = detect_pagination(folder)

    assert disclosure_rows
    assert disclosure_rows[0]["company_name"] == "테스트회사"
    assert simpletable_rows
    assert pagination == {
        "total_items": 101,
        "current_page": 2,
        "total_pages": 3,
        "downloaded_pages": 2,
        "latest_file": "002_post_page_00002.body",
    }


def test_extract_unique_disclosure_titles_preserves_first_seen_order() -> None:
    titles = extract_unique_disclosure_titles(
        [
            {"title": "  유상증자 결정  "},
            {"title": "유상증자 결정"},
            {"title": "타법인 주식 취득 결정"},
            {"title": ""},
            {"title": None},
            {"title": "타법인   주식   취득 결정"},
        ]
    )

    assert titles == [
        "유상증자 결정",
        "타법인 주식 취득 결정",
    ]


def test_build_result_folder_records_includes_saved_input_dates(tmp_path: Path) -> None:
    folder = tmp_path / "20240101_20240131"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(FIXTURES_DIR.joinpath("kind_response.html").read_bytes())
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(_workflow_input("2024-01-01", "2024-01-31")),
        encoding="utf-8",
    )

    records = build_result_folder_records(tmp_path)

    assert records == [
        {
            "folder_path": str(folder.resolve()),
            "folder_name": "20240101_20240131",
            "body_files": 1,
            "downloaded_pages": 1,
            "total_pages": 1,
            "total_items": 2,
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "page_size": 100,
            "latest_file": "001_post_page_00001.body",
        }
    ]


def test_build_result_folder_records_supports_parallel_folder_scan(tmp_path: Path) -> None:
    first = tmp_path / "20240101_20240131"
    second = tmp_path / "nested" / "20240201_20240229"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    for folder, start_date, end_date in (
        (first, "2024-01-01", "2024-01-31"),
        (second, "2024-02-01", "2024-02-29"),
    ):
        (folder / "001_post_page_00001.body").write_bytes(FIXTURES_DIR.joinpath("kind_response.html").read_bytes())
        (folder / "kind_workflow.input.json").write_text(
            json.dumps(_workflow_input(start_date, end_date)),
            encoding="utf-8",
        )

    records = build_result_folder_records(tmp_path, parallelism=2)

    assert [record["folder_name"] for record in records] == [
        "20240101_20240131",
        "nested/20240201_20240229",
    ]
    assert [record["end_date"] for record in records] == ["2024-01-31", "2024-02-29"]


def test_build_result_folder_records_rejects_missing_metadata(tmp_path: Path) -> None:
    folder = tmp_path / "20240101_20240131"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(
        FIXTURES_DIR.joinpath("kind_response.html").read_bytes()
    )

    with pytest.raises(ValueError, match="metadata is missing"):
        build_result_folder_records(tmp_path)


def test_detect_pagination_uses_numeric_page_order_for_four_digit_pages(tmp_path: Path) -> None:
    folder = tmp_path / "20240101_20241231"
    folder.mkdir()
    page_999 = """
    <section class="paging-group">
      <div class="paging type-00">
        전체 <em>100000</em>건 : <strong>999</strong>/1000
      </div>
    </section>
    """.encode("utf-8")
    page_1000 = """
    <section class="paging-group">
      <div class="paging type-00">
        전체 <em>100000</em>건 : <strong>1000</strong>/1000
      </div>
    </section>
    """.encode("utf-8")

    (folder / "999_post_page_00999.body").write_bytes(DISCLOSURE_RESULTS_HTML.encode("utf-8") + page_999)
    (folder / "1000_post_page_01000.body").write_bytes(DISCLOSURE_RESULTS_HTML.encode("utf-8") + page_1000)

    pagination = detect_pagination(folder)

    assert pagination == {
        "total_items": 100000,
        "current_page": 1000,
        "total_pages": 1000,
        "downloaded_pages": 2,
        "latest_file": "1000_post_page_01000.body",
    }


def test_build_result_folder_records_rejects_missing_pagination(tmp_path: Path) -> None:
    folder = tmp_path / "20240101_20240131"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_text(
        "<html><body>broken result page</body></html>",
        encoding="utf-8",
    )
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(_workflow_input("2024-01-01", "2024-01-31")),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="pagination not found"):
        build_result_folder_records(tmp_path)
