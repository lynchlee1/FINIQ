from __future__ import annotations

import json
from pathlib import Path

import pytest

from finiq.data_scraper.data.facade import load_company_classification_file
from finiq.data_scraper.parse import (
    companysummary_onclick,
    disclosure_file_rows,
    disclosure_rows,
)
from finiq.data_scraper.storage.classification_store import (
    company_classification_partial_path,
    folder_partial_signature,
    load_company_classification_artifact,
)
import finiq.data_scraper.workflow.workflow as workflow_module
from finiq.data_scraper.workflow import (
    KIND_WORKFLOW_INPUT_FORMAT,
    diagnose_kind_company_classification_integrity,
    export_kind_company_classification,
    export_kind_mode_folders,
)

def _results_page(rows_html: str, pagination_markup: str = "") -> str:
    if not pagination_markup:
        row_count = rows_html.count("<tr")
        pagination_markup = (
            '<section class="paging-group"><div class="paging type-00">'
            f"전체 <em>{row_count}</em>건 : <strong>1</strong>/1"
            "</div></section>"
        )
    return f"""
    <html><body>
      <table class="list type-00" summary="번호, 시간, 회사명, 공시제목, 제출인, 차트/주가">
        <tbody>
          {rows_html}
        </tbody>
      </table>
      {pagination_markup}
    </body></html>
    """


def _row_html(
    *,
    number: int,
    disclosed_at: str,
    company_name: str,
    company_id: str | None,
    market: str | None,
    badges: list[str] | None,
    title: str,
    acpt_no: str,
    doc_no: str | None,
    submitter: str,
) -> str:
    badge_images = ""
    image_labels = [market] if market else []
    image_labels.extend(badges or [])
    for label in image_labels:
        badge_images += f"<img alt='{label}' /> "

    company_link = (
        f"<a id='companysum' href='#companysum' onclick=\"companysummary_open('{company_id}'); return false;\" "
        f"title='{company_name}'>{company_name}</a>"
        if company_id
        else company_name
    )
    doc_no_value = doc_no or ""
    return f"""
    <tr>
      <td>{number}</td>
      <td>{disclosed_at}</td>
      <td>{badge_images}{company_link}</td>
      <td><a href="#viewer" onclick="openDisclsViewer('{acpt_no}','{doc_no_value}')"
             title="{title}">{title}</a></td>
      <td>{submitter}</td>
      <td></td>
    </tr>
    """


def _write_workflow_input(
    folder: Path,
    *,
    start_date: str = "2026-01-01",
    end_date: str = "2026-01-31",
    page_size: int = 100,
) -> None:
    payload: dict[str, object] = {
        "format": KIND_WORKFLOW_INPUT_FORMAT,
        "request_headers": {"User-Agent": "pytest"},
        "start_date": start_date,
        "end_date": end_date,
        "page_size": page_size,
        "search_filters": [],
        "disclosure_type_groups": {},
        "last_report_only": None,
        "include_previous_disclosures": None,
        "wait_seconds_between_requests": 0,
        "timeout": 5,
    }
    (folder / "kind_workflow.input.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_disclosure_rows_extract_company_market_badges_and_doc_numbers() -> None:
    html = _results_page(
        _row_html(
            number=1,
            disclosed_at="2026-01-02 20:02",
            company_name="레이저옵텍",
            company_id="19955",
            market="코스닥",
            badges=["관리종목", "KOSDAQ150"],
            title="[투자주의]소수계좌 거래집중 종목",
            acpt_no="20260102000687",
            doc_no="20260102000688",
            submitter="시장감시위원회",
        )
    )

    parsed = disclosure_rows(html)

    assert len(parsed) == 1
    assert companysummary_onclick("companysummary_open('19955'); return false;") == {
        "company_id": "19955"
    }
    assert parsed[0] == {
        "row_no": "1",
        "company_name": "레이저옵텍",
        "company_id": "19955",
        "company_cell_text": "레이저옵텍",
        "market": "코스닥",
        "badges": ["관리종목", "KOSDAQ150"],
        "disclosed_at": "2026-01-02 20:02",
        "title": "[투자주의]소수계좌 거래집중 종목",
        "title_attr": "[투자주의]소수계좌 거래집중 종목",
        "title_base": "[투자주의]소수계좌 거래집중 종목",
        "title_display": "[투자주의]소수계좌 거래집중 종목",
        "title_flags": ["투자주의"],
        "is_correction_report": False,
        "has_later_correction": False,
        "acpt_no": "20260102000687",
        "doc_no": "20260102000688",
        "submitter": "시장감시위원회",
    }


def test_disclosure_rows_keeps_disclosure_without_company_relation() -> None:
    html = _results_page(
        _row_html(
            number=1,
            disclosed_at="2026-01-02 20:02",
            company_name="일괄신고",
            company_id=None,
            market=None,
            badges=None,
            title="집합투자업자 의결권 행사 내역",
            acpt_no="20260102000687",
            doc_no=None,
            submitter="유리자산운용",
        )
    )

    parsed = disclosure_rows(html)

    assert parsed[0]["company_name"] is None
    assert parsed[0]["company_id"] is None
    assert parsed[0]["company_cell_text"] == "일괄신고"
    assert parsed[0]["submitter"] == "유리자산운용"
    assert parsed[0]["acpt_no"] == "20260102000687"


def test_disclosure_rows_rejects_multiple_company_relations(tmp_path: Path) -> None:
    html = _results_page(
        """
        <tr>
          <td>1</td>
          <td>2026-01-02 20:02</td>
          <td>
            <a id="companysum" onclick="companysummary_open('1')" title="회사1">회사1</a>
            <a id="companysum" onclick="companysummary_open('2')" title="회사2">회사2</a>
          </td>
          <td><a onclick="openDisclsViewer('20260102000687','')">공시</a></td>
          <td>제출인</td>
        </tr>
        """
    )

    with pytest.raises(
        ValueError,
        match="row 1: KIND disclosure row must not contain multiple companysum links",
    ):
        disclosure_rows(html)

    body_path = tmp_path / "001_post_page_00001.body"
    body_path.write_text(html, encoding="utf-8")
    with pytest.raises(ValueError) as exc_info:
        disclosure_file_rows(body_path)
    assert "row 1" in str(exc_info.value)
    assert str(body_path) in str(exc_info.value)

    _write_workflow_input(tmp_path)
    with pytest.raises(ValueError) as workflow_exc_info:
        diagnose_kind_company_classification_integrity(tmp_path, parallelism=1)
    assert "row 1" in str(workflow_exc_info.value)
    assert str(body_path) in str(workflow_exc_info.value)


def test_disclosure_rows_preserves_display_title_flags_and_later_correction() -> None:
    html = _results_page(
        """
        <tr>
          <td>7</td>
          <td>2026-01-02 20:02</td>
          <td><img alt="코스닥"><a id="companysum" onclick="companysummary_open('19955')" title="레이저옵텍">레이저옵텍</a></td>
          <td>
            <a href="#viewer" onclick="openDisclsViewer('20260102000687','20260102000688')" title="주주총회소집결의"><font color="#FF8040">[정정]</font>주주총회소집결의<img alt="해당보고서 이후에 정정된 보고서 있음"></a>
          </td>
          <td>레이저옵텍</td>
        </tr>
        """
    )

    parsed = disclosure_rows(html)[0]

    assert parsed["row_no"] == "7"
    assert parsed["title"] == "[정정]주주총회소집결의"
    assert parsed["title_attr"] == "주주총회소집결의"
    assert parsed["title_display"] == "[정정]주주총회소집결의"
    assert parsed["title_flags"] == ["정정"]
    assert parsed["is_correction_report"] is True
    assert parsed["has_later_correction"] is True
    assert parsed["doc_no"] == "20260102000688"


def test_export_kind_company_classification_recurses_and_merges_same_company(
    tmp_path: Path,
) -> None:
    folder_a = tmp_path / "20260101_20260101"
    folder_b = tmp_path / "nested" / "20260102_20260102"
    extra_folder = tmp_path / "ignored"
    for folder in (folder_a, folder_b, extra_folder):
        folder.mkdir(parents=True)
        _write_workflow_input(folder)

    (folder_a / "000_mainGET.body").write_text("main", encoding="utf-8")
    (folder_b / "000_mainGET.body").write_text("main", encoding="utf-8")

    (folder_a / "001_post_page_00001.body").write_text(
        _results_page(
            "\n".join(
                [
                    _row_html(
                        number=1,
                        disclosed_at="2026-01-01 09:00",
                        company_name="에이컴퍼니",
                        company_id="A001",
                        market="코스닥",
                        badges=["관리종목"],
                        title="주요사항보고서",
                        acpt_no="20260101000001",
                        doc_no=None,
                        submitter="에이컴퍼니",
                    ),
                    _row_html(
                        number=2,
                        disclosed_at="2026-01-01 10:00",
                        company_name="비컴퍼니",
                        company_id="B001",
                        market="유가증권",
                        badges=[],
                        title="타법인주식및출자증권취득결정",
                        acpt_no="20260101000002",
                        doc_no=None,
                        submitter="비컴퍼니",
                    ),
                ]
            )
        ),
        encoding="utf-8",
    )
    (folder_b / "001_post_page_00001.body").write_text(
        _results_page(
            "\n".join(
                [
                    _row_html(
                        number=1,
                        disclosed_at="2026-01-02 11:00",
                        company_name="에이컴퍼니",
                        company_id="A001",
                        market="코스닥",
                        badges=["KOSDAQ150"],
                        title="정정신고서제출요구",
                        acpt_no="20260102000003",
                        doc_no="20260102000004",
                        submitter="에이컴퍼니",
                    ),
                    _row_html(
                        number=2,
                        disclosed_at="2026-01-02 13:00",
                        company_name="씨컴퍼니",
                        company_id="C001",
                        market=None,
                        badges=[],
                        title="주주총회소집결의",
                        acpt_no="20260102000005",
                        doc_no=None,
                        submitter="씨컴퍼니",
                    ),
                ]
            )
        ),
        encoding="utf-8",
    )
    (extra_folder / "001_post_page_00001.body").write_text(
        _results_page(
            _row_html(
                number=1,
                disclosed_at="2026-01-03 09:00",
                company_name="추가대상",
                company_id="IGNORED",
                market="코스닥",
                badges=[],
                title="포함되어야함",
                acpt_no="20260103000001",
                doc_no=None,
                submitter="추가대상",
            )
        ),
        encoding="utf-8",
    )

    result = export_kind_company_classification(
        tmp_path,
        compact=False,
        parallelism=2,
    )

    assert result.source_folders == 3
    assert result.body_files == 3
    assert result.companies == 4
    assert result.disclosures == 5
    assert result.unlinked_disclosures == 0

    output_path = tmp_path / "kind.company_classification.sqlite"
    index_payload = load_company_classification_artifact(output_path)
    payload = load_company_classification_file(output_path)

    assert index_payload["format"] == "company_classification_index_v2"
    assert payload["summary"] == {
        "source_folders": 3,
        "body_files": 3,
        "companies": 4,
        "disclosures": 5,
        "unlinked_disclosures": 0,
    }
    assert [company["company_name"] for company in payload["companies"]] == [
        "비컴퍼니",
        "씨컴퍼니",
        "에이컴퍼니",
        "추가대상",
    ]

    merged_company = payload["companies"][2]
    assert merged_company["company_id"] == "A001"
    assert merged_company["market"] == "코스닥"
    assert merged_company["badges"] == ["관리종목", "KOSDAQ150"]
    assert len(merged_company["disclosures"]) == 2
    assert merged_company["disclosures"][0]["disclosed_at"] == "2026-01-01 09:00"
    assert merged_company["disclosures"][0]["title"] == "주요사항보고서"
    assert merged_company["disclosures"][0]["acpt_no"] == "20260101000001"
    assert merged_company["disclosures"][0]["doc_no"] is None
    assert merged_company["disclosures"][0]["submitter"] == "에이컴퍼니"
    assert "source_folder" not in merged_company["disclosures"][0]
    assert merged_company["disclosures"][0]["source_file"].endswith("001_post_page_00001.body")
    assert merged_company["disclosures"][0]["source_page"] == 1
    assert "page_number" not in merged_company["disclosures"][0]
    assert payload["companies"][3]["company_id"] == "IGNORED"


def test_export_kind_company_classification_counts_unlinked_disclosures(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "broken"
    folder.mkdir()
    _write_workflow_input(folder)
    (folder / "000_mainGET.body").write_text("main", encoding="utf-8")
    (folder / "001_post_page_00001.body").write_text(
        _results_page(
            """
            <tr>
              <td>1</td>
              <td>2026-01-01 09:00</td>
              <td></td>
              <td><a href="#viewer" onclick="openDisclsViewer('20260101000001','')"
                     title="회사 정보 누락">회사 정보 누락</a></td>
              <td>제출인</td>
              <td></td>
            </tr>
            """
        ),
        encoding="utf-8",
    )

    result = export_kind_company_classification(tmp_path)
    report = diagnose_kind_company_classification_integrity(tmp_path)

    assert result.companies == 0
    assert result.disclosures == 0
    assert result.unlinked_disclosures == 1
    assert report.parsed_disclosures == 1
    assert report.classified_disclosures == 0
    assert report.unlinked_disclosures == 1


def test_export_kind_mode_folders_supports_parallel_folder_exports(tmp_path: Path) -> None:
    folder_a = tmp_path / "20260101_20260101"
    folder_b = tmp_path / "20260102_20260102"
    folder_a.mkdir()
    folder_b.mkdir()

    for folder, title in ((folder_a, "공시 A"), (folder_b, "공시 B")):
        (folder / "001_post_page_00001.body").write_text(
            _results_page(
                _row_html(
                    number=1,
                    disclosed_at="2026-01-01 09:00",
                    company_name="테스트회사",
                    company_id="T001",
                    market="코스닥",
                    badges=[],
                    title=title,
                    acpt_no="20260101000001",
                    doc_no=None,
                    submitter="테스트회사",
                )
            ),
            encoding="utf-8",
        )

    results = export_kind_mode_folders(
        [folder_b, folder_a],
        parse_mode="simpletable",
        compact=False,
        parallelism=2,
    )

    assert [result.folder for result in results] == ["20260102_20260102", "20260101_20260101"]
    assert all(result.body_files == 1 for result in results)
    assert all(result.records > 0 for result in results)

    for folder in (folder_a, folder_b):
        payload = json.loads((folder / f"{folder.name}.simpletable.json").read_text(encoding="utf-8"))
        assert "simpletable" in payload
        assert payload["simpletable"]


def test_export_kind_company_classification_deduplicates_overlapping_disclosures(
    tmp_path: Path,
) -> None:
    folder_a = tmp_path / "20260101_20260131"
    folder_b = tmp_path / "20260115_20260215"
    folder_a.mkdir()
    folder_b.mkdir()
    _write_workflow_input(folder_a)
    _write_workflow_input(folder_b)

    duplicate_row = _row_html(
        number=1,
        disclosed_at="2026-01-20 09:00",
        company_name="에이컴퍼니",
        company_id="A001",
        market="코스닥",
        badges=["관리종목"],
        title="주요사항보고서",
        acpt_no="20260120000001",
        doc_no="20260120000002",
        submitter="에이컴퍼니",
    )
    extra_row = _row_html(
        number=2,
        disclosed_at="2026-02-01 09:00",
        company_name="에이컴퍼니",
        company_id="A001",
        market="코스닥",
        badges=["KOSDAQ150"],
        title="정정신고서제출요구",
        acpt_no="20260201000003",
        doc_no=None,
        submitter="에이컴퍼니",
    )

    (folder_a / "000_mainGET.body").write_text("main", encoding="utf-8")
    (folder_b / "000_mainGET.body").write_text("main", encoding="utf-8")
    (folder_a / "001_post_page_00001.body").write_text(_results_page(duplicate_row), encoding="utf-8")
    (folder_b / "001_post_page_00001.body").write_text(
        _results_page("\n".join([duplicate_row, extra_row])),
        encoding="utf-8",
    )

    result = export_kind_company_classification(
        tmp_path,
        compact=False,
        parallelism=2,
    )

    assert result.companies == 1
    assert result.disclosures == 2

    index_payload = load_company_classification_artifact(tmp_path / "kind.company_classification.sqlite")
    payload = load_company_classification_file(tmp_path / "kind.company_classification.sqlite")
    assert index_payload["format"] == "company_classification_index_v2"
    assert payload["summary"]["disclosures"] == 2
    disclosures = payload["companies"][0]["disclosures"]
    assert [row["acpt_no"] for row in disclosures] == [
        "20260120000001",
        "20260201000003",
    ]
    assert all("doc_no" in row for row in disclosures)
    assert all("source_file" in row for row in disclosures)
    assert all("source_page" in row for row in disclosures)


def test_export_kind_company_classification_detects_incomplete_folder_when_validating(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "20260101_20260131"
    folder.mkdir()
    _write_workflow_input(folder)
    (folder / "000_mainGET.body").write_text("main", encoding="utf-8")
    paging_markup = """
    <section class="paging-group">
      <div class="paging type-00">
        전체 <em>150</em>건 : <strong>1</strong>/2
      </div>
    </section>
    """
    (folder / "001_post_page_00001.body").write_text(
        _results_page(
            _row_html(
                number=1,
                disclosed_at="2026-01-01 09:00",
                company_name="에이컴퍼니",
                company_id="A001",
                market="코스닥",
                badges=[],
                title="주요사항보고서",
                acpt_no="20260101000001",
                doc_no=None,
                submitter="에이컴퍼니",
            ),
            pagination_markup=paging_markup,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="회사별 분류 저장을 중단했습니다. 페이지 무결성 검사를 통과하지 못했습니다."):
        export_kind_company_classification(tmp_path)


def test_company_classification_rejects_missing_metadata_before_body_or_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "20260101_20260131"
    folder.mkdir()
    (folder / "001_post_page_00001.body").write_bytes(b"must not be parsed")
    monkeypatch.setattr(
        workflow_module,
        "load_folder_partial_cache",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("cache must not be read before metadata validation")
        ),
    )

    with pytest.raises(ValueError, match="metadata is missing"):
        export_kind_company_classification(tmp_path)


def test_export_kind_company_classification_detects_non_last_page_under_100_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "20260101_20260131"
    folder.mkdir()
    (folder / "000_mainGET.body").write_text("main", encoding="utf-8")
    _write_workflow_input(folder)
    paging_markup = """
    <section class="paging-group">
      <div class="paging type-00">
        전체 <em>250</em>건 : <strong>1</strong>/3
      </div>
    </section>
    """
    rows_html = "\n".join(
        _row_html(
            number=index,
            disclosed_at="2026-01-01 09:00",
            company_name=f"테스트회사{index}",
            company_id=f"{index:05d}",
            market="코스닥",
            badges=[],
            title="주요사항보고서",
            acpt_no=f"2026010100{index:04d}",
            doc_no=None,
            submitter=f"테스트회사{index}",
        )
        for index in range(1, 100)
    )
    (folder / "001_post_page_00001.body").write_text(
        _results_page(rows_html, pagination_markup=paging_markup),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="1페이지의 행 수가 99건으로 기대값 100건과 다릅니다"):
        export_kind_company_classification(tmp_path)


def test_diagnose_kind_company_classification_reports_integrity_errors_without_repair(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "20260101_20260131"
    folder.mkdir()
    _write_workflow_input(folder)
    paging_markup = """
    <section class="paging-group">
      <div class="paging type-00">
        전체 <em>250</em>건 : <strong>1</strong>/3
      </div>
    </section>
    """
    rows_html = "\n".join(
        _row_html(
            number=index,
            disclosed_at="2026-01-01 09:00",
            company_name=f"테스트회사{index}",
            company_id=f"{index:05d}",
            market="코스닥",
            badges=[],
            title="주요사항보고서",
            acpt_no=f"2026010100{index:04d}",
            doc_no=None,
            submitter=f"테스트회사{index}",
        )
        for index in range(1, 100)
    )
    (folder / "001_post_page_00001.body").write_text(
        _results_page(rows_html, pagination_markup=paging_markup),
        encoding="utf-8",
    )

    report = diagnose_kind_company_classification_integrity(tmp_path)

    assert any("1페이지의 행 수가 99건으로 기대값 100건과 다릅니다" in error for error in report.integrity_errors)


def test_export_kind_company_classification_reuses_partial_cache_when_folder_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "20260101_20260101"
    folder.mkdir()
    _write_workflow_input(folder)
    (folder / "000_mainGET.body").write_text("main", encoding="utf-8")
    duplicate_row = _row_html(
        number=1,
        disclosed_at="2026-01-01 09:00",
        company_name="에이컴퍼니",
        company_id="A001",
        market="코스닥",
        badges=[],
        title="주요사항보고서",
        acpt_no="20260101000001",
        doc_no=None,
        submitter="에이컴퍼니",
    )
    (folder / "001_post_page_00001.body").write_text(
        _results_page(duplicate_row + duplicate_row),
        encoding="utf-8",
    )

    first = export_kind_company_classification(tmp_path, compact=False)
    assert first.disclosures == 1
    assert company_classification_partial_path(folder).exists()

    def _unexpected_parse(_: str | bytes) -> list[dict[str, object]]:
        raise AssertionError("partial cache should prevent reparsing unchanged folders")

    monkeypatch.setattr(workflow_module, "disclosure_rows", _unexpected_parse)
    second = export_kind_company_classification(tmp_path, compact=False)
    assert second.disclosures == 1
