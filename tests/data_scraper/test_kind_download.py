"""Tests for saving KIND search results."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pytest

from finiq.data_scraper.core.client import (
    download_disclosure_viewer_htmls,
    download_pages,
    fetch_disclosure_viewer_html,
    fetch_search_page,
)
from finiq.data_scraper.core.payload import build_search_form
from finiq.data_scraper.workflow import (
    KindWorkflow,
    download_kind_viewer_htmls_from_result_folder,
    inspect_download_directory_pages,
    run_download,
)

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html, */*; q=0.01",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://kind.krx.co.kr/disclosure/details.do?method=searchDetailsMain",
    "Origin": "https://kind.krx.co.kr",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}


def get_form_values(form_data: list[tuple[str, str]], key: str) -> list[str]:
    return [value for current_key, value in form_data if current_key == key]


def get_form_value(form_data: list[tuple[str, str]], key: str) -> str:
    values = get_form_values(form_data, key)
    assert values, f"missing form field: {key}"
    assert len(values) == 1, f"expected one value for {key}, got {values!r}"
    return values[0]


def build_result_page_html(
    *,
    page_number: int,
    page_size: int,
    total_items: int,
) -> bytes:
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    if page_number < total_pages:
        row_count = page_size
    else:
        row_count = total_items - (page_size * (total_pages - 1))
    rows = []
    for row_index in range(row_count):
        item_no = ((page_number - 1) * page_size) + row_index + 1
        rows.append(
            f"""
            <tr>
              <td>{item_no}</td>
              <td>2024-01-{(item_no % 28) + 1:02d} 09:00</td>
              <td>
                <a id="companysum" title="테스트회사{item_no}" onclick="companysummary_open('{item_no:06d}')">테스트회사{item_no}</a>
                <img alt="유가증권" />
              </td>
              <td>
                <a title="테스트 공시 {item_no}" onclick="openDisclsViewer('202401{item_no:08d}','')">테스트 공시 {item_no}</a>
              </td>
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
              <tbody>
                {''.join(rows)}
              </tbody>
            </table>
          </body>
        </html>
        """
    ).encode("utf-8")


@dataclass
class FakeResponse:
    status_code: int
    url: str
    content: bytes
    text: str
    ok: bool = True

    def raise_for_status(self) -> None:
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeCookies:
    def get_dict(self) -> dict[str, str]:
        return {"session": "fake"}


class FakeSession:
    def __init__(self, *, total_items_multiplier: int = 3) -> None:
        self.total_items_multiplier = total_items_multiplier
        self.cookies = FakeCookies()
        self.get_calls: list[dict[str, object]] = []
        self.post_calls: list[dict[str, object]] = []

    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> FakeResponse:
        self.get_calls.append({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse(
            status_code=200,
            url=url,
            content=b"main-body",
            text="main-body",
        )

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: list[tuple[str, str]],
        timeout: float,
    ) -> FakeResponse:
        self.post_calls.append(
            {"url": url, "headers": headers, "data": data, "timeout": timeout}
        )
        page = int(get_form_value(data, "pageIndex"))
        page_size = int(get_form_value(data, "currentPageSize"))
        total_items = page_size * self.total_items_multiplier
        content = build_result_page_html(
            page_number=page,
            page_size=page_size,
            total_items=total_items,
        )
        return FakeResponse(
            status_code=200,
            url=url,
            content=content,
            text=content.decode("utf-8"),
        )


class ViewerFakeSession:
    def __init__(self) -> None:
        self.cookies = FakeCookies()
        self.get_calls: list[dict[str, object]] = []

    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> FakeResponse:
        self.get_calls.append({"url": url, "headers": headers, "timeout": timeout})
        content = f"<html><body>{url}</body></html>".encode("utf-8")
        return FakeResponse(
            status_code=200,
            url=url,
            content=content,
            text=content.decode("utf-8"),
        )


class BrokenPageSizeSession(FakeSession):
    def __init__(self) -> None:
        super().__init__()

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        data: list[tuple[str, str]],
        timeout: float,
    ) -> FakeResponse:
        self.post_calls.append(
            {"url": url, "headers": headers, "data": data, "timeout": timeout}
        )
        page = int(get_form_value(data, "pageIndex"))
        page_size = int(get_form_value(data, "currentPageSize"))
        content = build_result_page_html(
            page_number=page,
            page_size=max(1, page_size - 10),
            total_items=page_size * 3,
        )
        return FakeResponse(
            status_code=200,
            url=url,
            content=content,
            text=content.decode("utf-8"),
        )


def test_download_pages_saves_requested_page_range_and_filters(
    tmp_path: Path,
) -> None:
    session = FakeSession()
    download_pages(
        output_directory=tmp_path,
        request_headers=REQUEST_HEADERS,
        start_date="2024-01-01",
        end_date="2024-12-31",
        start_page=2,
        end_page=3,
        search_filters={"searchCorpName": "삼성전자", "marketType": "", "reportNm": "사업보고서"},
        page_size=50,
        wait_seconds_between_requests=0,
        timeout=5,
        session=session,
    )

    assert (tmp_path / "000_mainGET.body").read_bytes() == b"main-body"
    assert (tmp_path / "002_post_page_00002.body").exists()
    assert (tmp_path / "003_post_page_00003.body").exists()
    assert not (tmp_path / "001_post_page_00001.body").exists()

    first_post = session.post_calls[0]
    assert first_post["headers"] == REQUEST_HEADERS
    assert get_form_value(first_post["data"], "searchCorpName") == "삼성전자"
    assert get_form_value(first_post["data"], "reportNm") == "사업보고서"
    assert get_form_value(first_post["data"], "marketType") == ""
    assert get_form_value(first_post["data"], "disclosureType01") == ""
    assert get_form_value(first_post["data"], "pageIndex") == "2"
    assert get_form_value(first_post["data"], "currentPageSize") == "50"


def test_download_pages_rejects_invalid_page_range(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="end_page must be >= start_page"):
        download_pages(
            output_directory=tmp_path,
            request_headers=REQUEST_HEADERS,
            start_date="2024-01-01",
            end_date="2024-12-31",
            start_page=3,
            end_page=2,
        )


def test_build_search_form_supports_structured_disclosure_filters() -> None:
    request_data = build_search_form(
        page_number=1,
        page_size=15,
        start_date="2020-01-01",
        end_date="2022-12-31",
        disclosure_type_groups={1: "0119", "02": ["0120", "0121"]},
        last_report_only=True,
        include_previous_disclosures=False,
    )

    assert get_form_value(request_data, "method") == "searchDetailsSub"
    assert get_form_value(request_data, "currentPageSize") == "15"
    assert get_form_value(request_data, "pageIndex") == "1"
    assert get_form_value(request_data, "fromDate") == "2020-01-01"
    assert get_form_value(request_data, "toDate") == "2022-12-31"
    assert get_form_value(request_data, "disclosureType01") == "0119|"
    assert get_form_value(request_data, "pDisclosureType01") == "0119|"
    assert get_form_values(request_data, "disclosureTypeArr01") == ["0119"]
    assert get_form_value(request_data, "disclosureType02") == "0120|0121|"
    assert get_form_value(request_data, "pDisclosureType02") == "0120|0121|"
    assert get_form_values(request_data, "disclosureTypeArr02") == ["0120", "0121"]
    assert get_form_value(request_data, "lastReport") == "T"
    assert get_form_value(request_data, "bfrDsclsType") == ""


def test_build_search_form_accepts_new_disclosure_group_suffixes() -> None:
    request_data = build_search_form(
        page_number=1,
        page_size=15,
        start_date="2020-01-01",
        end_date="2022-12-31",
        disclosure_type_groups={"21": ["9001", "9002"]},
    )

    assert get_form_value(request_data, "disclosureType21") == "9001|9002|"
    assert get_form_value(request_data, "pDisclosureType21") == "9001|9002|"
    assert get_form_values(request_data, "disclosureTypeArr21") == ["9001", "9002"]


def test_build_search_form_omits_optional_fields_by_default() -> None:
    request_data = build_search_form(
        page_number=1,
        page_size=15,
        start_date="2020-01-01",
        end_date="2022-12-31",
    )

    assert not get_form_values(request_data, "lastReport")
    assert not get_form_values(request_data, "bfrDsclsType")


def test_build_search_form_allows_raw_filter_overrides() -> None:
    request_data = build_search_form(
        page_number=3,
        page_size=30,
        start_date="2021-01-01",
        end_date="2021-01-31",
        disclosure_type_groups={1: "0119"},
        last_report_only=True,
        search_filters={
            "disclosureType01": "0999|",
            "pDisclosureType01": "0999|",
            "disclosureTypeArr01": ["0999", "1999"],
            "lastReport": "",
            "marketType": "KOSDAQ",
        },
    )

    assert get_form_value(request_data, "disclosureType01") == "0999|1999|"
    assert get_form_value(request_data, "pDisclosureType01") == "0999|1999|"
    assert get_form_values(request_data, "disclosureTypeArr01") == ["0999", "1999"]
    assert get_form_value(request_data, "lastReport") == ""
    assert get_form_value(request_data, "marketType") == "KOSDAQ"
    assert get_form_value(request_data, "pageIndex") == "3"
    assert get_form_value(request_data, "currentPageSize") == "30"


def test_download_pages_accepts_structured_payload_options(tmp_path: Path) -> None:
    session = FakeSession()
    download_pages(
        output_directory=tmp_path,
        request_headers=REQUEST_HEADERS,
        start_date="2020-01-01",
        end_date="2022-12-31",
        disclosure_type_groups={1: "0119"},
        last_report_only=True,
        include_previous_disclosures=False,
        page_size=15,
        wait_seconds_between_requests=0,
        timeout=5,
        session=session,
    )

    first_post = session.post_calls[0]
    assert get_form_value(first_post["data"], "disclosureType01") == "0119|"
    assert get_form_value(first_post["data"], "pDisclosureType01") == "0119|"
    assert get_form_values(first_post["data"], "disclosureTypeArr01") == ["0119"]
    assert get_form_value(first_post["data"], "lastReport") == "T"
    assert get_form_value(first_post["data"], "bfrDsclsType") == ""
    assert get_form_value(first_post["data"], "currentPageSize") == "15"


def test_download_pages_reports_progress_messages(tmp_path: Path) -> None:
    session = FakeSession()
    progress_messages: list[str] = []

    download_pages(
        output_directory=tmp_path,
        request_headers=REQUEST_HEADERS,
        start_date="2024-01-01",
        end_date="2024-12-31",
        start_page=2,
        end_page=3,
        wait_seconds_between_requests=0,
        timeout=5,
        session=session,
        progress_callback=progress_messages.append,
    )

    assert progress_messages == [
        "Fetching KIND search page...",
        f"Saved KIND search page to: {tmp_path / '000_mainGET.body'}",
        "Fetching results page 2 (1/2)...",
        f"Saved results page 2 (1/2) to: {tmp_path / '002_post_page_00002.body'}",
        "Fetching results page 3 (2/2)...",
        f"Saved results page 3 (2/2) to: {tmp_path / '003_post_page_00003.body'}",
    ]


def test_fetch_search_page_refreshes_main_get_body(tmp_path: Path) -> None:
    session = FakeSession()

    output_path = fetch_search_page(
        output_directory=tmp_path,
        request_headers=REQUEST_HEADERS,
        timeout=5,
        session=session,
    )

    assert output_path == tmp_path / "000_mainGET.body"
    assert output_path.read_bytes() == b"main-body"
    assert len(session.get_calls) == 1


def test_fetch_disclosure_viewer_html_saves_kind_viewer_page(tmp_path: Path) -> None:
    session = ViewerFakeSession()

    output_path = fetch_disclosure_viewer_html(
        output_directory=tmp_path,
        request_headers=REQUEST_HEADERS,
        acpt_no="20260108000150",
        doc_no="20260324000592",
        timeout=5,
        session=session,
    )

    assert output_path == tmp_path / "20260108000150_20260324000592.html"
    assert b"acptno=20260108000150" in output_path.read_bytes()
    assert b"docno=20260324000592" in output_path.read_bytes()
    assert len(session.get_calls) == 1
    assert session.get_calls[0]["headers"] == REQUEST_HEADERS


def test_download_disclosure_viewer_htmls_rate_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = ViewerFakeSession()
    sleep_calls: list[float] = []
    monkeypatch.setattr("finiq.data_scraper.core.client.time.sleep", sleep_calls.append)

    # Request 3 items with max_requests_per_minute=2
    # First 2 should pass immediately, 3rd should wait.
    saved_paths = download_disclosure_viewer_htmls(
        output_directory=tmp_path,
        request_headers=REQUEST_HEADERS,
        acpt_numbers=["20260108000150", "20260318000871", "20260401001020"],
        timeout=5,
        session=session,
        max_requests_per_minute=2,
    )

    assert [path.name for path in saved_paths] == [
        "20260108000150.html",
        "20260318000871.html",
        "20260401001020.html",
    ]
    assert len(session.get_calls) == 3
    # At least one sleep call should have occurred for the 3rd request
    assert len(sleep_calls) > 0
    assert all(s == 0.1 for s in sleep_calls)


def test_download_disclosure_viewer_htmls_rejects_rates_over_kind_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_requests_per_minute"):
        download_disclosure_viewer_htmls(
            output_directory=tmp_path,
            request_headers=REQUEST_HEADERS,
            acpt_numbers=["20260108000150"],
            max_requests_per_minute=101,
        )


def test_download_kind_viewer_htmls_from_result_folder_collects_acpt_numbers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_folder = tmp_path / "results"
    result_folder.mkdir()
    (result_folder / "001_post_page_00001.body").write_bytes(
        build_result_page_html(page_number=1, page_size=2, total_items=2)
    )
    session = ViewerFakeSession()
    monkeypatch.setattr("finiq.data_scraper.core.client.time.sleep", lambda seconds: None)

    result = download_kind_viewer_htmls_from_result_folder(
        result_folder,
        request_headers=REQUEST_HEADERS,
        timeout=5,
        session=session,
        max_requests_per_minute=90,
    )

    assert result["output_directory"] == str(result_folder / "viewer_html")
    assert result["acpt_numbers"] == ["20240100000001", "20240100000002"]
    assert [Path(path).name for path in result["saved_files"]] == [
        "20240100000001.html",
        "20240100000002.html",
    ]
    assert len(session.get_calls) == 2


def test_kind_workflow_can_store_inputs_without_saving(tmp_path: Path) -> None:
    workflow = KindWorkflow()

    result = workflow.run(
        output_directory=tmp_path,
        request_headers=REQUEST_HEADERS,
        start_date="2024-01-01",
        end_date="2024-12-31",
        start_page=2,
        end_page=3,
        disclosure_type_groups={"01": ["0119", "0120"]},
        last_report_only=True,
        page_size=50,
        save=False,
    )

    configured_input = workflow.get_input()
    assert configured_input.output_directory == tmp_path.resolve()
    assert configured_input.request_headers == REQUEST_HEADERS
    assert configured_input.disclosure_type_groups == {"01": ["0119", "0120"]}
    assert result["saved_files"] == []
    assert get_form_value(result["request_data"], "pageIndex") == "2"
    assert get_form_value(result["request_data"], "disclosureType01") == "0119|0120|"


def test_kind_workflow_can_save_results_from_stored_inputs(tmp_path: Path) -> None:
    workflow = KindWorkflow()
    session = FakeSession()

    workflow.configure(
        output_directory=tmp_path,
        request_headers=REQUEST_HEADERS,
        start_date="2024-01-01",
        end_date="2024-12-31",
        start_page=1,
        end_page=2,
        disclosure_type_groups={"01": ["0119"]},
        last_report_only=True,
        wait_seconds_between_requests=0,
        timeout=5,
    )
    result = workflow.save_search_results(session=session)

    assert (tmp_path / "000_mainGET.body").read_bytes() == b"main-body"
    assert (tmp_path / "001_post_page_00001.body").exists()
    assert (tmp_path / "002_post_page_00002.body").exists()
    assert len(result["saved_files"]) == 3
    assert get_form_value(result["request_data"], "lastReport") == "T"
    assert Path(result["input_snapshot_path"]).exists()
    assert Path(result["checkpoint_path"]).exists()

    checkpoint_payload = json.loads(Path(result["checkpoint_path"]).read_text(encoding="utf-8"))
    assert checkpoint_payload["completed"] is True
    assert checkpoint_payload["last_saved_page"] == 2
    assert checkpoint_payload["saved_files"][-1].endswith("002_post_page_00002.body")


def test_run_download_saves_and_returns_summary(tmp_path: Path) -> None:
    session = FakeSession()

    result = run_download(
        output_directory=tmp_path,
        request_headers=REQUEST_HEADERS,
        start_date="2024-01-01",
        end_date="2024-12-31",
        start_page=1,
        end_page=1,
        search_filters={"searchCorpName": "삼성전자"},
        wait_seconds_between_requests=0,
        timeout=5,
        save=True,
        session=session,
    )

    assert (tmp_path / "000_mainGET.body").exists()
    assert (tmp_path / "001_post_page_00001.body").exists()
    assert result["input"]["search_filters"] == [("searchCorpName", "삼성전자")]
    assert get_form_value(result["request_data"], "searchCorpName") == "삼성전자"


def test_kind_workflow_writes_input_snapshot_and_checkpoint_incrementally(
    tmp_path: Path,
) -> None:
    workflow = KindWorkflow()
    session = FakeSession()
    observed_checkpoint_pages: list[int | None] = []

    workflow.configure(
        output_directory=tmp_path,
        request_headers=REQUEST_HEADERS,
        start_date="2024-01-01",
        end_date="2024-12-31",
        start_page=1,
        end_page=2,
        wait_seconds_between_requests=0,
        timeout=5,
    )

    def on_saved_file(
        output_path: Path,
        page_number: int | None,
        request_data: list[tuple[str, str]] | None,
    ) -> None:
        del output_path, request_data
        checkpoint_payload = json.loads(
            (tmp_path / "kind_workflow.checkpoint.json").read_text(encoding="utf-8")
        )
        observed_checkpoint_pages.append(checkpoint_payload["last_saved_page"])
        assert checkpoint_payload["completed"] is False
        assert len(checkpoint_payload["saved_files"]) >= 1
        assert checkpoint_payload["last_saved_page"] == page_number

    result = workflow.save_search_results(
        session=session,
        saved_file_callback=on_saved_file,
    )

    input_payload = json.loads(Path(result["input_snapshot_path"]).read_text(encoding="utf-8"))
    assert input_payload["start_page"] == 1
    assert input_payload["end_page"] == 2

    checkpoint_payload = json.loads(Path(result["checkpoint_path"]).read_text(encoding="utf-8"))
    assert observed_checkpoint_pages == [None, 1, 2]
    assert checkpoint_payload["completed"] is True
    assert checkpoint_payload["last_saved_page"] == 2


def test_kind_workflow_stops_when_existing_folder_has_different_locked_page_size(
    tmp_path: Path,
) -> None:
    session = FakeSession()
    (tmp_path / "kind_workflow.input.json").write_text(
        json.dumps(
            {
                "page_size": 100,
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "001_post_page_00001.body").write_bytes(
        build_result_page_html(page_number=1, page_size=100, total_items=300)
    )

    workflow = KindWorkflow()
    workflow.configure(
        output_directory=tmp_path,
        request_headers=REQUEST_HEADERS,
        start_date="2024-01-01",
        end_date="2024-12-31",
        start_page=1,
        end_page=1,
        page_size=50,
        wait_seconds_between_requests=0,
        timeout=5,
    )

    with pytest.raises(ValueError, match="고정 페이지 크기와 현재 요청이 다릅니다"):
        workflow.save_search_results(session=session)

    saved_input = json.loads((tmp_path / "kind_workflow.input.json").read_text(encoding="utf-8"))
    assert saved_input["page_size"] == 100
    assert len(session.post_calls) == 0


def test_inspect_download_directory_pages_requires_complete_when_requested(
    tmp_path: Path,
) -> None:
    (tmp_path / "001_post_page_00001.body").write_bytes(
        build_result_page_html(page_number=1, page_size=100, total_items=300)
    )
    (tmp_path / "002_post_page_00002.body").write_bytes(
        build_result_page_html(page_number=2, page_size=100, total_items=300)
    )

    with pytest.raises(ValueError, match="저장된 페이지 수와 페이지네이션의 전체 페이지 수가 다릅니다"):
        inspect_download_directory_pages(
            tmp_path,
            expected_page_size=100,
            require_complete=True,
            validation_parallelism=2,
        )


def test_inspect_download_directory_pages_detects_pagination_mismatch(
    tmp_path: Path,
) -> None:
    (tmp_path / "001_post_page_00001.body").write_bytes(
        build_result_page_html(page_number=1, page_size=100, total_items=300)
    )
    (tmp_path / "002_post_page_00002.body").write_bytes(
        build_result_page_html(page_number=2, page_size=100, total_items=250)
    )

    with pytest.raises(ValueError, match="전체 페이지 수 또는 전체 건수가 서로 다릅니다"):
        inspect_download_directory_pages(
            tmp_path,
            expected_page_size=100,
            require_complete=False,
            validation_parallelism=2,
        )


def test_kind_workflow_stops_when_downloaded_page_breaks_locked_page_size(
    tmp_path: Path,
) -> None:
    workflow = KindWorkflow()
    session = BrokenPageSizeSession()

    workflow.configure(
        output_directory=tmp_path,
        request_headers=REQUEST_HEADERS,
        start_date="2024-01-01",
        end_date="2024-12-31",
        start_page=1,
        end_page=1,
        page_size=50,
        wait_seconds_between_requests=0,
        timeout=5,
    )

    with pytest.raises(ValueError, match="페이지 무결성 검사 실패"):
        workflow.save_search_results(session=session)

    assert not (tmp_path / "001_post_page_00001.body").exists()
