"""Tests for KIND HTML JSON conversion."""

from __future__ import annotations

from pathlib import Path

import pytest

from finiq.data_scraper.parse import (
    dart_main_doc_no,
    disclosure_rows,
    disclosure_onclick,
    file_to_json,
    html_to_json,
    pagination_info,
    search_paths,
    viewer_html,
)
from finiq.data_scraper.parse import _markup

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_disclosure_rows_rejects_missing_results_table() -> None:
    with pytest.raises(ValueError, match="result table is missing or ambiguous"):
        disclosure_rows("<html><body>no disclosure table</body></html>")


def test_disclosure_rows_rejects_class_only_results_table() -> None:
    html = """
    <table class="list">
      <tbody><tr><td>1</td></tr></tbody>
    </table>
    """

    with pytest.raises(ValueError, match="result table is missing or ambiguous"):
        disclosure_rows(html)


def test_disclosure_rows_rejects_results_table_without_tbody() -> None:
    html = """
    <table summary="번호, 시간, 회사명, 공시제목, 제출인">
      <tr><td>1</td></tr>
    </table>
    """

    with pytest.raises(ValueError, match="exactly one tbody"):
        disclosure_rows(html)


def test_disclosure_rows_rejects_multiple_results_tables() -> None:
    html = """
    <table summary="회사명 공시제목"><tbody></tbody></table>
    <table summary="회사명 공시제목"><tbody></tbody></table>
    """

    with pytest.raises(ValueError, match="result table is missing or ambiguous"):
        disclosure_rows(html)


def test_disclosure_rows_rejects_short_body_row() -> None:
    html = """
    <table summary="회사명 공시제목">
      <tbody><tr><td>1</td></tr></tbody>
    </table>
    """

    with pytest.raises(ValueError, match="fewer than 5 cells"):
        disclosure_rows(html)


def test_decode_html_markup_rejects_undecodable_bytes(monkeypatch) -> None:
    class UndetectedMarkup:
        unicode_markup = None

    monkeypatch.setattr(_markup, "UnicodeDammit", lambda *args, **kwargs: UndetectedMarkup())

    with pytest.raises(UnicodeDecodeError):
        _markup.decode_html_markup(b"\xff")


def test_parse_html_with_recovery_rejects_empty_document(monkeypatch) -> None:
    monkeypatch.setattr(_markup.etree, "HTML", lambda *args, **kwargs: None)

    with pytest.raises(ValueError, match="Failed to parse HTML document"):
        _markup.parse_html_with_recovery("<html></html>")


def test_html_to_json_collects_all_table_cells() -> None:
    html = """
    <html><body>
      <table class="list">
        <caption>목록</caption>
        <thead><tr><th>회사명</th><th>제목</th></tr></thead>
        <tbody>
          <tr>
            <td><a href="/corp/1" title="회사A">회사A</a></td>
            <td>공시 제목</td>
          </tr>
        </tbody>
      </table>
    </body></html>
    """
    data = html_to_json(html)
    assert len(data["tables"]) == 1
    table = data["tables"][0]
    assert table["caption"] == "목록"
    assert table["sections"]["thead"][0]["cells"][0]["text"] == "회사명"
    first_cell = table["sections"]["tbody"][0]["cells"][0]
    assert first_cell["text"] == "회사A"
    assert first_cell["links"][0]["href"] == "/corp/1"


def test_file_to_json_reads_sample() -> None:
    sample_path = FIXTURES_DIR / "kind_response.html"
    data = file_to_json(sample_path)

    assert data["tables"]
    first_table = data["tables"][0]
    assert "sections" in first_table
    assert any(row["cells"] for row in first_table["sections"]["tbody"])
    assert "번호" in str(first_table["attrs"].get("summary", ""))


def test_html_to_json_recovers_from_malformed_html() -> None:
    malformed = """
    <section>
      <table>
        <tbody>
          <tr><td>1<td><a href="/x">링크
          <tr><td>2</td><td>정상
    """
    data = html_to_json(malformed)
    assert data["tables"]
    rows = data["tables"][0]["sections"]["tbody"]
    assert rows
    assert rows[0]["cells"][0]["text"] == "1"


def test_html_to_json_cells_mode() -> None:
    html = """
    <table>
      <tbody>
        <tr><td>A</td><td>B</td></tr>
      </tbody>
    </table>
    """
    data = html_to_json(html, mode="cells")
    assert "cells" in data
    assert "tables" not in data
    assert data["cells"][0]["text"] == "A"
    assert data["cells"][1]["text"] == "B"
    assert "table_index" not in data["cells"][0]


def test_html_to_json_simpletable_mode_rectangular() -> None:
    html = """
    <table>
      <tbody>
        <tr>
          <td>A</td>
          <td>B</td>
        </tr>
        <tr>
          <td>짧음</td>
        </tr>
      </tbody>
    </table>
    """
    data = html_to_json(html, mode="simpletable")
    assert "simpletable" in data
    grid = data["simpletable"]
    assert grid == [["A", "B"], ["짧음", ""]]
    assert all(len(row) == len(grid[0]) for row in grid)


def test_html_to_json_rows_mode() -> None:
    html = """
    <table>
      <tbody>
        <tr>
          <td><a href="#" onclick="openX('1'); return false;">회사</a></td>
          <td>제목만</td>
        </tr>
      </tbody>
    </table>
    """
    data = html_to_json(html, mode="rows")
    assert "rows" in data
    assert "tables" not in data
    assert len(data["rows"]) == 1
    row0 = data["rows"][0]
    assert len(row0) == 2
    assert set(row0[0].keys()) == {"row_index", "cell_index", "text", "links"}
    assert row0[0]["row_index"] == 0
    assert row0[0]["cell_index"] == 0
    assert row0[0]["text"] == "회사"
    assert row0[0]["links"] == "openX('1'); return false;"
    assert row0[1]["row_index"] == 0
    assert row0[1]["cell_index"] == 1
    assert row0[1]["text"] == "제목만"
    assert row0[1]["links"] is None


def test_file_to_json_rows_mode_sample() -> None:
    data = file_to_json(FIXTURES_DIR / "kind_response.html", mode="rows")
    assert data["rows"]
    first = data["rows"][0][0]
    assert set(first.keys()) == {"row_index", "cell_index", "text", "links"}
    assert first["row_index"] == 0
    assert first["cell_index"] == 0
    assert first["text"].isdigit()


def test_pagination_info_parses_comma_separated_page_counts() -> None:
    html = """
    <section class="paging-group">
      <div class="paging type-00">
        전체 <em>101,536</em>건 : <strong>1</strong>/1,016&nbsp;&nbsp;&nbsp;
      </div>
    </section>
    """

    assert pagination_info(html) == {
        "total_items": 101536,
        "current_page": 1,
        "total_pages": 1016,
    }


def test_pagination_info_parses_comma_separated_current_page() -> None:
    html = """
    <section class="paging-group">
      <div class="paging type-00">
        전체 <em>101,536</em>건 : <strong>1,016</strong>/1,016
      </div>
    </section>
    """

    assert pagination_info(html) == {
        "total_items": 101536,
        "current_page": 1016,
        "total_pages": 1016,
    }


def test_disclosure_onclick_extracts_acpt_and_doc_numbers() -> None:
    parsed = disclosure_onclick("openDisclsViewer('20260408001327','')")
    assert parsed == {
        "acpt_no": "20260408001327",
        "doc_no": None,
    }


def test_viewer_html_extracts_selected_main_docno() -> None:
    html = """
    <html><body>
      <form name="frm">
        <input type="hidden" name="acptNo" value="20250123000279" />
        <input type="hidden" name="tempTitle" value="[현대자동차] 현금ㆍ현물 배당 결정" />
      </form>
      <h1 class="ttl type-99 fleft">현대자동차 (005380)</h1>
      <select id="mainDoc" name="mainDoc">
        <option value="">본문선택</option>
        <option value="20250120002372|Y" selected="selected">현금ㆍ현물 배당 결정 (2025.01.23)</option>
      </select>
      <select id="attachedDoc" name="attachedDoc">
        <option>첨부문서선택</option>
        <option value="20250120002373">배당 관련 참고자료 (2025.01.23)</option>
      </select>
    </body></html>
    """

    parsed = viewer_html(html)

    assert parsed["acpt_no"] == "20250123000279"
    assert parsed["title"] == "[현대자동차] 현금ㆍ현물 배당 결정"
    assert parsed["header"] == "현대자동차 (005380)"
    assert parsed["selected_main_doc_no"] == "20250120002372"
    assert parsed["main_docs"] == [
        {
            "doc_no": "20250120002372",
            "label": "현금ㆍ현물 배당 결정 (2025.01.23)",
            "selected": True,
            "is_latest": True,
        }
    ]
    assert parsed["attached_docs"] == [
        {
            "doc_no": "20250120002373",
            "label": "배당 관련 참고자료 (2025.01.23)",
            "selected": False,
            "is_latest": None,
        }
    ]


def test_dart_main_doc_no_returns_selected_docno() -> None:
    html = """
    <select id="mainDoc" name="mainDoc">
      <option value="">본문선택</option>
      <option value="20260312002268|Y" selected="selected">참고서류 (2026.03.12)</option>
    </select>
    """
    assert dart_main_doc_no(html) == "20260312002268"


def test_search_paths_extracts_doc_path_and_sender_code() -> None:
    html = """
    <script type="text/javascript">
      parent.setPath(
        'https://kind.krx.co.kr/external/2025/03/21/000889/20250321003451/11011_toc.htm',
        'https://kind.krx.co.kr/external/2025/03/21/000889/20250321003451/11011.htm',
        '/external/2025/03/21/000889/20250321003451/11011',
        '05',
        '20'
      );
    </script>
    """
    assert search_paths(html) == {
        "toc_loc_path": "https://kind.krx.co.kr/external/2025/03/21/000889/20250321003451/11011_toc.htm",
        "doc_loc_path": "https://kind.krx.co.kr/external/2025/03/21/000889/20250321003451/11011.htm",
        "doc_server_path": "/external/2025/03/21/000889/20250321003451/11011",
        "form_upclss_cd": "05",
        "snd_loc_tp_cd": "20",
    }
