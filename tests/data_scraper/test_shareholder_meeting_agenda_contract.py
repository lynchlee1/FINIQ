"""Selection and tokenization contract for shareholder-meeting agendas."""

from __future__ import annotations

from typing import Any

from finiq.data_scraper.parse.domain.shareholder_meeting import (
    extract_shareholder_meeting_details,
)


def _extract(internal_html: str, *, mode: str) -> dict[str, Any]:
    return extract_shareholder_meeting_details(
        f"<html><body>{internal_html}</body></html>",
        mode=mode,
    )


def test_first_matching_structured_schema_is_fixed_even_when_empty() -> None:
    result = _extract(
        """
        <table class="first">
          <tr><th>번호</th><th>회의목적사항</th></tr>
        </table>
        <table class="second">
          <tr><th>번호</th><th>회의목적사항</th></tr>
          <tr><td>1</td><td>뒤 구조화 안건</td></tr>
        </table>
        <table><tr><td>3. 의안 주요내용</td><td>제1호 의안: 레거시 안건</td></tr></table>
        """,
        mode="NOTICE",
    )

    assert result["agenda_records"] == []
    assert result["agendas"] == []


def test_structured_placeholder_row_does_not_create_an_agenda() -> None:
    result = _extract(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th></tr>
          <tr><td>-</td><td>-</td></tr>
        </table>
        """,
        mode="NOTICE",
    )

    assert result["agenda_records"] == []
    assert result["agendas"] == []


def test_first_populated_structured_schema_does_not_merge_later_sources() -> None:
    result = _extract(
        """
        <table class="first">
          <tr><th>번호</th><th>회의목적사항</th></tr>
          <tr><td>1</td><td>첫 구조화 안건</td></tr>
        </table>
        <table class="second">
          <tr><th>번호</th><th>회의목적사항</th></tr>
          <tr><td>2</td><td>뒤 구조화 안건</td></tr>
        </table>
        <table><tr><td>3. 의안 주요내용</td><td>제3호 의안: 레거시 안건</td></tr></table>
        """,
        mode="NOTICE",
    )

    assert [(row["number"], row["title"]) for row in result["agenda_records"]] == [
        ("1", "첫 구조화 안건")
    ]


def test_flat_structured_schema_fixes_its_title_column_before_reading_rows() -> None:
    result = _extract(
        """
        <table>
          <tr><th>번호</th><th>안건</th><th>회의목적사항</th></tr>
          <tr><td>1</td><td>대체하면 안 되는 값</td><td>고정 제목 열의 안건</td></tr>
          <tr><td>2</td><td></td><td>같은 제목 열의 둘째 안건</td></tr>
        </table>
        """,
        mode="NOTICE",
    )

    assert [record["title"] for record in result["agenda_records"]] == [
        "고정 제목 열의 안건",
        "같은 제목 열의 둘째 안건",
    ]


def test_unrelated_grouped_headers_do_not_replace_the_agenda_title_column() -> None:
    result = _extract(
        """
        <table>
          <tr>
            <th rowspan="2">번호</th><th rowspan="2">회의목적사항</th>
            <th colspan="2">표결 결과</th>
          </tr>
          <tr><th>찬성률</th><th>반대율</th></tr>
          <tr><td>1</td><td>고정된 안건 제목</td><td>90</td><td>10</td></tr>
        </table>
        """,
        mode="RESULT",
    )

    assert [record["title"] for record in result["agenda_records"]] == [
        "고정된 안건 제목"
    ]


def test_legacy_label_requires_two_direct_row_cells() -> None:
    result = _extract(
        """
        <table>
          <tr><div>
            <td>3. 의안 주요내용</td>
            <td>제1호 의안: descendant selector 오염 안건</td>
          </div></tr>
        </table>
        """,
        mode="NOTICE",
    )

    assert result["agenda_records"] == []


def test_legacy_label_rejects_rows_with_more_than_two_direct_cells() -> None:
    result = _extract(
        """
        <table>
          <tr>
            <td>3. 의안 주요내용</td>
            <td>제1호 의안: 잘못 수용된 안건</td>
            <td>별도 비고</td>
          </tr>
        </table>
        <table>
          <tr><td>3. 의안 주요내용</td><td>제2호 의안: 뒤 구제 안건</td></tr>
        </table>
        """,
        mode="NOTICE",
    )

    assert result["agenda_records"] == []


def test_first_exact_section_heading_is_not_replaced_after_schema_failure() -> None:
    result = _extract(
        """
        <table><tr><td><span>이사선임 세부내역</span></td></tr></table>
        <span>이사선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>출생년월</th></tr>
          <tr><td>뒤후보</td><td>1970-01</td></tr>
        </table>
        """,
        mode="NOTICE",
    )

    assert result["elections"] == []
    assert result["entities"] == []


def test_first_canonical_meeting_date_row_is_not_replaced() -> None:
    result = _extract(
        """
        <table>
          <tr><td>일시</td><td>미정</td></tr>
          <tr><td>주주총회예정일</td><td>2026년 3월 30일</td></tr>
        </table>
        """,
        mode="NOTICE",
    )

    assert result["meeting_date"] is None


def test_legacy_nested_table_row_uses_its_own_table_coordinates() -> None:
    result = _extract(
        """
        <table>
          <tr><td>레이아웃</td><td>
            <table>
              <tr><td>3. 의안 주요내용</td><td>제1호 의안: 안쪽 표 안건</td></tr>
            </table>
          </td></tr>
        </table>
        """,
        mode="NOTICE",
    )

    assert [row["title"] for row in result["agenda_records"]] == [
        "제1호 의안: 안쪽 표 안건"
    ]
    assert result["agenda_records"][0]["evidence"]["table_index"] == 1
    assert result["agenda_records"][0]["evidence"]["row_index"] == 0


def test_structured_nested_table_uses_only_its_direct_rows_and_cells() -> None:
    result = _extract(
        """
        <table id="layout">
          <tr><td>
            <table id="agenda">
              <tr><th>번호</th><th>회의목적사항</th></tr>
              <tr><td>1</td><td>이사 선임의 건</td></tr>
            </table>
          </td></tr>
        </table>
        """,
        mode="NOTICE",
    )

    assert [(row["number"], row["title"]) for row in result["agenda_records"]] == [
        ("1", "이사 선임의 건")
    ]
    assert result["agenda_records"][0]["evidence"]["table_index"] == 1


def test_correction_labels_do_not_override_the_canonical_legacy_phase() -> None:
    result = _extract(
        """
        <table>
          <tr><th>정정항목</th><th>정정전</th><th>정정후</th></tr>
          <tr><td>결의사항</td><td>구 결과</td><td>삭제</td></tr>
        </table>
        <table>
          <tr><td>3. 의안 주요내용</td><td>제1호 의안: 현재 소집 안건</td></tr>
        </table>
        """,
        mode="NOTICE",
    )

    assert result["disclosure_phase"] == "notice"
    assert [row["title"] for row in result["agenda_records"]] == [
        "제1호 의안: 현재 소집 안건"
    ]


def test_missing_canonical_mode_does_not_infer_phase_from_document_shape() -> None:
    result = _extract(
        """
        <table><tr><td>주주총회일자</td><td>2026년 3월 30일</td></tr></table>
        <table><tr><td>1. 결의사항</td><td>제1호 의안: 현재 결과 안건</td></tr></table>
        """,
        mode="",
    )

    assert result["disclosure_phase"] == "unknown"
    assert result["meeting_date"] is None
    assert result["agenda_records"] == []


def test_legacy_nested_result_subagendas_keep_candidates_and_outcomes() -> None:
    """Golden reduced from KIND disclosure 20260224000928."""
    result = _extract(
        """
        <table><tr><td>1. 결의사항</td><td>
          나. 부의안건<br/>
          (2) 제2호 의안: 이사선임의 건<br/>
          * 제2-01호 의안: 사내이사 이재영 선임의 건(이사회 추천)<br/>
          - 원안대로 가결<br/>
          * 제2-02호 의안: 사내이사 최범수 선임의 건(이사회 추천)<br/>
          - 원안대로 가결<br/>
          * 제2-03호 의안: 사내이사 유성무 선임의 건(이사회 추천)<br/>
          - 부결<br/>
          * 제2-04호 의안: 사내이사 David Kung 선임의 건(이사회 추천)<br/>
          - 부결<br/>
          * 제2-05호 의안: 사외이사 김윤석 선임의 건(이사회 추천)<br/>
          - 원안대로 가결<br/>
          * 제2-06호 의안: 사외이사 차운영 선임의 건(이사회 추천)<br/>
          - 부결
        </td></tr></table>
        """,
        mode="RESULT",
    )

    records = result["agenda_records"]
    assert [row["number"] for row in records] == [
        "2-01",
        "2-02",
        "2-03",
        "2-04",
        "2-05",
        "2-06",
    ]
    assert [row["status"] for row in records] == [
        "passed",
        "passed",
        "rejected",
        "rejected",
        "passed",
        "rejected",
    ]
    assert [row["candidate"] for row in records] == [
        "이재영",
        "최범수",
        "유성무",
        "David Kung",
        "김윤석",
        "차운영",
    ]
    people = {
        entity["entity_ref"]: entity["name"]
        for entity in result["entities"]
        if entity["entity_type"] == "person"
    }
    candidate_relations = [
        relation
        for relation in result["relationships"]
        if relation["relationship_type"] == "candidate_for"
    ]
    assert {people[relation["source_ref"]] for relation in candidate_relations} == {
        "이재영",
        "최범수",
        "유성무",
        "David Kung",
        "김윤석",
        "차운영",
    }
    elected_relations = [
        relation
        for relation in result["relationships"]
        if relation["relationship_type"] == "elected_as"
    ]
    assert {people[relation["source_ref"]] for relation in elected_relations} == {
        "이재영",
        "최범수",
        "김윤석",
    }
    assert {relation["attributes"]["outcome"] for relation in elected_relations} == {
        "passed"
    }


def test_numbered_titles_with_terminal_outcomes_are_new_agendas() -> None:
    """Golden reduced from KIND disclosure 20260123000326."""
    result = _extract(
        """
        <table><tr><td>1. 결의사항</td><td>
          - 제1호 의안 : 정관 일부 변경의 건<br/>
          제1-1호 의안 : 제17조(주주명부의 폐쇄) (부결)<br/>
          제1-2호 의안 : 제26조(소집지) (가결)<br/>
          제1-9호 의안 : 제49조(감사위원회 대표의 선임) (가결)<br/>
          제1-10호 의안 : 제54조(사업연도) (부결)<br/>
          - 제2호 의안 이사 선임의 건<br/>
          제2-1호 의안 : 사내이사 김병준 선임의 건 (부결)<br/>
          제2-2호 의안 : 사내이사 인태경 선임의 건 (부결)<br/>
          제2-3호 의안 : 사외이사 왕현철 선임의 건 (부결)<br/>
          제2-4호 의안 : 사외이사 최호석 선임의 건 (부결)<br/>
          - 제3호 의안 분리선출에 따라 감사위원이 되는 사외이사 김한민 선임의 건 (부결)<br/>
          - 제4호 의안 : 자본 감소의 건(10:1) (가결)
        </td></tr></table>
        """,
        mode="RESULT",
    )

    assert [row["number"] for row in result["agenda_records"]] == [
        "1-1",
        "1-2",
        "1-9",
        "1-10",
        "2-1",
        "2-2",
        "2-3",
        "2-4",
        "3",
        "4",
    ]
    assert [row["status"] for row in result["agenda_records"]] == [
        "rejected",
        "passed",
        "passed",
        "rejected",
        "rejected",
        "rejected",
        "rejected",
        "rejected",
        "rejected",
        "passed",
    ]

    people = {
        entity["entity_ref"]: entity["name"]
        for entity in result["entities"]
        if entity["entity_type"] == "person"
    }
    roles = {
        (people[relation["source_ref"]], relation["attributes"]["office_type"])
        for relation in result["relationships"]
        if relation["relationship_type"] == "candidate_for"
    }
    assert roles == {
        ("김병준", "director"),
        ("인태경", "director"),
        ("왕현철", "outside_director"),
        ("최호석", "outside_director"),
        ("김한민", "audit_committee_member"),
        ("김한민", "outside_director"),
    }
    assert not any(
        relation["relationship_type"] == "elected_as"
        for relation in result["relationships"]
    )


def test_terminal_rejections_do_not_merge_directors_into_auditor() -> None:
    """Golden reduced from KIND disclosure 20260227000609."""
    result = _extract(
        """
        <table><tr><td>1. 결의사항</td><td>
          제1호 의안 : 이사 선임의 건<br/>
          제1-1호 의안 : 사내이사 김종일 선임의 건 (부결)<br/>
          제1-2호 의안 : 사내이사 김민철 선임의 건 (부결)<br/>
          제1-3호 의안 : 사내이사 정환 선임의 건 (부결)<br/>
          제2호 의안 : 상근감사 홍사균 선임의 건 (부결)
        </td></tr></table>
        """,
        mode="RESULT",
    )

    assert [
        (row["number"], row["candidate"], row["status"])
        for row in result["agenda_records"]
    ] == [
        ("1-1", "김종일", "rejected"),
        ("1-2", "김민철", "rejected"),
        ("1-3", "정환", "rejected"),
        ("2", "홍사균", "rejected"),
    ]
    people = {
        entity["entity_ref"]: entity["name"]
        for entity in result["entities"]
        if entity["entity_type"] == "person"
    }
    roles = {
        people[relation["source_ref"]]: relation["attributes"]["office_type"]
        for relation in result["relationships"]
        if relation["relationship_type"] == "candidate_for"
    }
    assert roles == {
        "김종일": "director",
        "김민철": "director",
        "정환": "director",
        "홍사균": "auditor",
    }
    assert not any(
        relation["relationship_type"] == "elected_as"
        for relation in result["relationships"]
    )


def test_legacy_section_state_supports_ordinal_and_bullet_tokens() -> None:
    result = _extract(
        """
        <table><tr><td>3. 의안 주요내용</td><td>
          1. 보고사항<br/>
          ① 감사보고<br/>
          2. 부의안건<br/>
          1) 제1호 의안: 재무제표 승인의 건<br/>
          ② 정관 일부 변경의 건<br/>
          3. 이사 보수한도 승인의 건<br/>
          - 감사 보수한도 승인의 건
        </td></tr></table>
        """,
        mode="NOTICE",
    )

    assert [(row["number"], row["title"]) for row in result["agenda_records"]] == [
        ("1", "1) 제1호 의안: 재무제표 승인의 건"),
        ("2", "② 정관 일부 변경의 건"),
        ("3", "3. 이사 보수한도 승인의 건"),
        (None, "- 감사 보수한도 승인의 건"),
    ]


def test_parenthesized_ordinals_start_only_after_legacy_agenda_section() -> None:
    """Reduced from KIND notices 20260126000552, 20260126000586,
    20260212000319, 20260212000468, 20260212001137, and 20260212001300.
    """
    result = _extract(
        """
        <table><tr><td>3. 의안 주요내용</td><td>
          가. 보고사항<br/>
          (1) 감사의 감사보고<br/>
          (2) 영업보고<br/>
          (3) 내부회계관리제도 운영실태 보고<br/>
          나. 의결사항<br/>
          (1) 제3기 재무제표 및 이익잉여금처분계산서(안) 승인의 건<br/>
          (2) 이사 보수한도액 승인의 건<br/>
          (3) 감사 보수한도액 승인의 건
        </td></tr></table>
        """,
        mode="NOTICE",
    )

    assert [
        (row["number"], row["title"]) for row in result["agenda_records"]
    ] == [
        ("1", "(1) 제3기 재무제표 및 이익잉여금처분계산서(안) 승인의 건"),
        ("2", "(2) 이사 보수한도액 승인의 건"),
        ("3", "(3) 감사 보수한도액 승인의 건"),
    ]


def test_empty_legacy_proposal_marker_takes_title_and_outcome_from_next_line() -> None:
    """Reduced from KIND result 20260130000481."""
    result = _extract(
        """
        <table><tr><td>1. 결의사항</td><td>
          제1호의안:<br/>
          영업양수 승인의 건 →원안대로 승인
        </td></tr></table>
        """,
        mode="RESULT",
    )

    assert [
        (row["number"], row["title"], row["result_raw"], row["status"])
        for row in result["agenda_records"]
    ] == [
        (
            "1",
            "제1호의안: 영업양수 승인의 건 →원안대로 승인",
            "원안대로 승인",
            "passed",
        )
    ]


def test_inline_sibling_tokens_split_without_splitting_backward_references() -> None:
    result = _extract(
        """
        <table><tr><td>3. 의안 주요내용</td><td>
          제1-3호 의안: 제1-1호, 제1-2호 의안 이외의 정관 변경의 건<br/>
          제2호 의안: 정관 변경의 건<br/>
          제2-1호 의안: 소집지 변경의 건 제2-2호 의안: 의결권 변경의 건
        </td></tr></table>
        """,
        mode="NOTICE",
    )

    assert [row["number"] for row in result["agenda_records"]] == [
        "1-3",
        "2-1",
        "2-2",
    ]
    assert "제1-1호, 제1-2호 의안 이외" in result["agenda_records"][0]["title"]
