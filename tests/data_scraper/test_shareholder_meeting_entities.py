"""Golden cases for shareholder-meeting entity and relationship extraction.

The fixtures are deliberately small, but retain the table shapes and wording seen
in KIND disclosures.  Expected entities and outcomes were labelled from those
examples before being encoded here.
"""

from __future__ import annotations

from typing import Any

from finiq.data_scraper.parse.domain.shareholder_meeting import parse_shareholder_meeting


def _external_html(*, title: str, acpt_no: str = "20260327002490") -> str:
    return f"""
    <html><body>
      <h1 class="ttl">테스트회사 (123456)</h1>
      <input name="tempTitle" value="[테스트회사] {title}" />
      <input name="acptNo" value="{acpt_no}" />
    </body></html>
    """


def _parse(internal_html: str, *, title: str) -> dict[str, Any]:
    return parse_shareholder_meeting(
        _external_html(title=title),
        f"<html><body>{internal_html}</body></html>",
    )


def _entity(result: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [entity for entity in result["entities"] if entity["name"] == name]
    assert len(matches) == 1, (name, matches)
    return matches[0]


def _relations(
    result: dict[str, Any],
    relationship_type: str,
    *,
    source_ref: str | None = None,
) -> list[dict[str, Any]]:
    relations = [
        relation
        for relation in result["relationships"]
        if relation["relationship_type"] == relationship_type
    ]
    if source_ref is not None:
        relations = [
            relation for relation in relations if relation["source_ref"] == source_ref
        ]
    return relations


def _assert_semantic_shapes(result: dict[str, Any]) -> None:
    for entity in result["entities"]:
        assert entity["entity_ref"]
        assert entity["entity_type"] in {"person", "organization"}
        assert entity["name"]
        assert isinstance(entity["attributes"], dict)
        assert entity["mentions"]

    for relation in result["relationships"]:
        assert relation["source_ref"]
        assert relation["target_ref"]
        assert isinstance(relation["attributes"], dict)
        assert isinstance(relation["evidence"], dict)
        assert relation["evidence"]["raw_text"]


def test_modern_result_agenda_extracts_outcomes_and_candidate_relations() -> None:
    result = _parse(
        """
        <table>
          <tr><td>주주총회 일자</td><td>2026-03-27</td></tr>
        </table>
        <table>
          <tr>
            <th rowspan="2">번호</th><th rowspan="2">결의구분</th>
            <th colspan="2">회의목적사항</th><th rowspan="2">가결여부</th>
            <th colspan="3">의결권 행사 현황</th><th rowspan="2">비고</th>
          </tr>
          <tr><th>안건</th><th>후보자</th><th>찬성률</th><th>반대율</th><th>기권율</th></tr>
          <tr>
            <td>4-1</td><td>보통결의</td><td>사내이사 선임의 건</td><td>김방희</td>
            <td>가결</td><td>98.1%</td><td>1.4%</td><td>0.5%</td><td>-</td>
          </tr>
          <tr>
            <td>4-2</td><td>보통결의</td><td>사내이사 선임의 건</td><td>이환무</td>
            <td>부결</td><td>42.0%</td><td>57.0%</td><td>1.0%</td><td>-</td>
          </tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert result["disclosure_phase"] == "result"
    assert result["meeting_date"] == "2026-03-27"
    assert [record["status"] for record in result["agenda_records"]] == [
        "passed",
        "rejected",
    ]

    passed = _entity(result, "김방희")
    rejected = _entity(result, "이환무")
    for person in (passed, rejected):
        candidates = _relations(
            result, "candidate_for", source_ref=person["entity_ref"]
        )
        assert len(candidates) == 1
        assert candidates[0]["target_ref"] == "@reporting_company"
        assert candidates[0]["attributes"]["office_type"] == "director"
        assert len(_relations(result, "subject_of", source_ref=person["entity_ref"])) == 1

    elected = _relations(result, "elected_as", source_ref=passed["entity_ref"])
    assert len(elected) == 1
    assert elected[0]["attributes"]["office_type"] == "director"
    assert not _relations(result, "elected_as", source_ref=rejected["entity_ref"])
    assert len(_relations(result, "includes", source_ref="@meeting")) == 2
    _assert_semantic_shapes(result)


def test_notice_candidate_is_not_treated_as_current_officer() -> None:
    result = _parse(
        """
        <table><tr><td>일시</td><td>2026년 3월 11일 오전 9시</td></tr></table>
        <span>감사선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>출생년월</th><th>신규선임여부</th><th>주요경력(현직포함)</th></tr>
          <tr><td>이정철</td><td>1971-03</td><td>신규</td><td>회계사</td></tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    assert result["disclosure_phase"] == "notice"
    assert result["meeting_date"] == "2026-03-11"
    person = _entity(result, "이정철")
    candidate = _relations(result, "candidate_for", source_ref=person["entity_ref"])
    assert len(candidate) == 1
    assert candidate[0]["attributes"]["office_type"] == "auditor"
    assert not _relations(result, "elected_as", source_ref=person["entity_ref"])


def test_notice_removal_subjects_are_not_current_termination_facts() -> None:
    """Reduced from 20260112000592 and roster receipt 20260211001835."""
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th></tr>
          <tr><td>1</td><td>사외이사 김명구의 해임의 건</td></tr>
          <tr><td>1-1</td><td>사외이사 공훈의 해임의 건</td></tr>
          <tr><td>2</td><td>기타비상무이사 Hugues Dusseaux의 해임의 건</td></tr>
          <tr>
            <td>3</td>
            <td>감사위원회 위원 전원 해임의 건 (전준성, 김재상, 허수진)</td>
          </tr>
          <tr><td>3-1</td><td>감사위원회 위원 전원 해임의 건</td></tr>
          <tr><td>3-2</td><td>감사위원회 위원 전원 해임의 건 (주주제안 안건)</td></tr>
          <tr><td>3-3</td><td>감사위원회 위원 전원 해임의 건 (주주 제안)</td></tr>
          <tr><td>3-4</td><td>감사위원회 위원 전원 해임의 건 (임시 안건)</td></tr>
          <tr><td>3-5</td><td>감사위원회 위원 전원 해임의 건 (주주제안, 임시안건)</td></tr>
          <tr><td>4</td><td>감사위원 선·해임시 의결권 제한 강화의 건</td></tr>
          <tr><td>5</td><td>장병흔대표이사 해임의 건</td></tr>
          <tr><td>6</td><td>조종환사외이사 해임의 건</td></tr>
        </table>
        """,
        title="임시주주총회소집결의",
    )

    assert {entity["name"] for entity in result["entities"]} == {
        "김명구",
        "공훈의",
        "Hugues Dusseaux",
        "전준성",
        "김재상",
        "허수진",
        "장병흔",
        "조종환",
    }
    assert not _relations(result, "candidate_for")
    assert not _relations(result, "removed_from")
    subjects = _relations(result, "subject_of")
    assert len(subjects) == 8
    assert {relation["attributes"]["action"] for relation in subjects} == {
        "removal"
    }
    assert {
        tuple(relation["attributes"]["office_types"])
        for relation in subjects
    } == {
        ("outside_director",),
        ("director",),
        ("audit_committee_member",),
    }


def test_result_only_creates_passed_removal_and_resignation_facts() -> None:
    """Reduced from 20260224000004, 20260313002213, and 20260327003214."""
    result = _parse(
        """
        <table>
          <tr>
            <th>번호</th><th>회의목적사항</th><th>가결여부</th><th>비고</th>
          </tr>
          <tr><td>1</td><td>사내이사 황재우 해임의 건</td><td>가결</td><td>-</td></tr>
          <tr><td>2</td><td>감사 최승민 해임의 건</td><td>부결</td><td>-</td></tr>
          <tr><td>3</td><td>사내이사(전득영) 사임의 건</td><td>가결</td><td>-</td></tr>
          <tr><td>4</td><td>사외이사 오영표 사임의 건</td><td>부결</td><td>-</td></tr>
          <tr><td>5</td><td>사내이사 드미트리 쿠리쉬 해임의 건</td><td>가결</td><td>-</td></tr>
          <tr><td>6</td><td>김용열 이사 해임의 건</td><td>가결</td><td>-</td></tr>
          <tr><td>7</td><td>박존찬형이사 해임의 건</td><td>가결</td><td>-</td></tr>
          <tr><td>8</td><td>사내이사 해임의 건</td><td>가결</td><td>-</td></tr>
          <tr><td>9</td><td>사내이사 사임의 건</td><td>가결</td><td>-</td></tr>
          <tr><td>10</td><td>장병흔대표이사 해임의 건</td><td>가결</td><td>-</td></tr>
        </table>
        """,
        title="임시주주총회결과",
    )

    people = {entity["name"]: entity for entity in result["entities"]}
    assert set(people) == {
        "황재우",
        "최승민",
        "전득영",
        "오영표",
        "드미트리 쿠리쉬",
        "김용열",
        "박존찬형",
        "장병흔",
    }
    assert not _relations(result, "candidate_for")
    assert not _relations(result, "elected_as")

    removed = _relations(result, "removed_from")
    assert {
        relation["source_ref"] for relation in removed
    } == {
        people["황재우"]["entity_ref"],
        people["드미트리 쿠리쉬"]["entity_ref"],
        people["김용열"]["entity_ref"],
        people["박존찬형"]["entity_ref"],
        people["장병흔"]["entity_ref"],
    }
    assert all(
        relation["attributes"]
        == {
            "office_type": "director",
            "disclosure_phase": "result",
            "outcome": "passed",
        }
        for relation in removed
    )
    resigned = _relations(result, "resigned_from")
    assert len(resigned) == 1
    assert resigned[0]["source_ref"] == people["전득영"]["entity_ref"]
    assert resigned[0]["attributes"]["office_type"] == "director"

    subjects = _relations(result, "subject_of")
    assert len(subjects) == 8
    assert {
        (people_name, relation["attributes"]["action"], relation["attributes"]["outcome"])
        for people_name, person in people.items()
        for relation in subjects
        if relation["source_ref"] == person["entity_ref"]
    } == {
        ("황재우", "removal", "passed"),
        ("최승민", "removal", "rejected"),
        ("전득영", "resignation", "passed"),
        ("오영표", "resignation", "rejected"),
        ("드미트리 쿠리쉬", "removal", "passed"),
        ("김용열", "removal", "passed"),
        ("박존찬형", "removal", "passed"),
        ("장병흔", "removal", "passed"),
    }


def test_auditor_compensation_typo_does_not_create_a_person() -> None:
    """Reduced from 20260312002120 and results 20260327001021/01521."""
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>가결여부</th></tr>
          <tr><td>5</td><td>감사 보수한도 승인선임의 건</td><td>가결</td></tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert result["entities"] == []
    assert not _relations(result, "subject_of")


def test_nonactive_termination_name_forms_keep_scope_without_clause_entities() -> None:
    """Reduced from 20180309001014, 20110831000406, and 20230127000900."""
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th></tr>
          <tr><td>1</td><td>박존찬형이사 해임의 건</td></tr>
          <tr><td>2</td><td>서장원감사 해임의 건</td></tr>
          <tr><td>3</td><td>대표이사 양재원 이사 해임의 건</td></tr>
          <tr><td>4</td><td>사외이사 정동수 이사 해임의 건</td></tr>
          <tr><td>5</td><td>사외이사 김동윤 이사 해임의 건</td></tr>
          <tr>
            <td>6</td>
            <td>사임서 제출로 인한 감사 해임건에 대한 의안 폐지</td>
          </tr>
          <tr><td>7</td><td>비강근감사 해임의 건(이영준)</td></tr>
        </table>
        """,
        title="임시주주총회소집결의",
    )

    people = {entity["name"]: entity for entity in result["entities"]}
    assert set(people) == {"박존찬형", "서장원", "양재원", "정동수", "김동윤"}
    subjects = _relations(result, "subject_of")
    assert len(subjects) == 5
    offices = {
        name: next(
            relation["attributes"]["office_types"][0]
            for relation in subjects
            if relation["source_ref"] == person["entity_ref"]
        )
        for name, person in people.items()
    }
    assert offices == {
        "박존찬형": "director",
        "서장원": "auditor",
        "양재원": "director",
        "정동수": "outside_director",
        "김동윤": "outside_director",
    }
    assert not _relations(result, "removed_from")


def test_rejected_compact_auditor_removal_stays_a_nonactive_subject() -> None:
    """Reduced from 20110504000372."""
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>가결여부</th></tr>
          <tr><td>4</td><td>문형철 감사해임의 건</td><td>부결</td></tr>
        </table>
        """,
        title="임시주주총회결과",
    )

    person = _entity(result, "문형철")
    subjects = _relations(result, "subject_of", source_ref=person["entity_ref"])
    assert len(subjects) == 1
    assert subjects[0]["attributes"] == {
        "action": "removal",
        "office_types": ["auditor"],
        "disclosure_phase": "result",
        "outcome": "rejected",
    }
    assert not _relations(result, "removed_from")


def test_audit_committee_role_and_outside_role_deduplicate_same_person() -> None:
    result = _parse(
        """
        <table><tr><td>일시</td><td>2026-03-25 10:00</td></tr></table>
        <span>사외이사선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>출생년월</th><th>임기</th><th>신규선임여부</th></tr>
          <tr><td>최종학</td><td>1967-08</td><td>3년</td><td>신규</td></tr>
        </table>
        <span>감사위원선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>출생년월</th><th>사외이사여부</th><th>신규선임여부</th></tr>
          <tr><td>최종학</td><td>1967-08</td><td>사외이사인 감사위원</td><td>신규</td></tr>
          <tr><td>유호선</td><td>1974-04</td><td>사외이사가 아닌 감사위원</td><td>신규</td></tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    assert [row["name"] for row in result["audit_committee_elections"]] == [
        "최종학",
        "유호선",
    ]
    people = [entity for entity in result["entities"] if entity["entity_type"] == "person"]
    assert [person["name"] for person in people].count("최종학") == 1
    assert {person["name"] for person in people} == {"최종학", "유호선"}

    jonghak = _entity(result, "최종학")
    jonghak_roles = {
        relation["attributes"]["office_type"]
        for relation in _relations(
            result, "candidate_for", source_ref=jonghak["entity_ref"]
        )
    }
    assert jonghak_roles == {"outside_director", "audit_committee_member"}
    hoseon = _entity(result, "유호선")
    assert {
        relation["attributes"]["office_type"]
        for relation in _relations(
            result, "candidate_for", source_ref=hoseon["entity_ref"]
        )
    } == {"audit_committee_member"}


def test_multi_office_agenda_uses_one_shared_election_birth_identity() -> None:
    from finiq.data_scraper.parse.domain.shareholder_meeting_semantics import (
        extract_semantic_contract,
    )

    title = "분리선출에 따라 감사위원이 되는 사외이사 김한민 선임의 건"
    entities, _ = extract_semantic_contract(
        agenda_records=[
            {
                "agenda_ref": "agenda:1",
                "title": title,
                "candidate": "김한민",
                "evidence": {"field": "회의목적사항", "raw_text": title},
            }
        ],
        elections=[
            {
                "name": "김한민",
                "birth_month": "1982-02",
                "section_type": office_type,
                "evidence": {"field": "성명", "raw_text": "김한민 1982-02"},
            }
            for office_type in ("outside_director", "audit_committee_member")
        ],
        disclosure_phase="notice",
    )

    people = [entity for entity in entities if entity["name"] == "김한민"]
    assert len(people) == 1
    assert people[0]["attributes"]["birth_month"] == "1982-02"
    assert {mention["field"] for mention in people[0]["mentions"]} >= {
        "후보자",
        "성명",
    }


def test_generic_agenda_candidate_uses_one_document_local_birth_identity() -> None:
    from finiq.data_scraper.parse.domain.shareholder_meeting_semantics import (
        extract_semantic_contract,
    )

    title = "김장재 중임의 건"
    entities, relationships = extract_semantic_contract(
        agenda_records=[
            {
                "agenda_ref": "agenda:1",
                "title": title,
                "candidate": "김장재",
                "evidence": {"field": "회의목적사항", "raw_text": title},
            }
        ],
        elections=[
            {
                "name": "김장재",
                "birth_month": "1970-01",
                "section_type": "director",
                "evidence": {"field": "성명", "raw_text": "김장재 1970-01"},
            }
        ],
        disclosure_phase="notice",
    )

    people = [entity for entity in entities if entity["name"] == "김장재"]
    assert len(people) == 1
    assert people[0]["attributes"]["birth_month"] == "1970-01"
    assert {mention["field"] for mention in people[0]["mentions"]} == {
        "후보자",
        "성명",
    }
    assert any(
        relation["source_ref"] == people[0]["entity_ref"]
        and relation["relationship_type"] == "subject_of"
        and relation["attributes"]["action"] == "agenda_candidate"
        for relation in relationships
    )


def test_birthless_election_row_uses_one_document_local_birth_identity() -> None:
    from finiq.data_scraper.parse.domain.shareholder_meeting_semantics import (
        extract_semantic_contract,
    )

    entities, _ = extract_semantic_contract(
        agenda_records=[],
        elections=[
            {
                "name": "김한민",
                "birth_month": birth_month,
                "section_type": office_type,
                "evidence": {
                    "field": "성명",
                    "raw_text": f"김한민 {birth_month or '생년월 없음'}",
                },
            }
            for birth_month, office_type in (
                ("1982-02", "outside_director"),
                ("", "audit_committee_member"),
            )
        ],
        disclosure_phase="notice",
    )

    people = [entity for entity in entities if entity["name"] == "김한민"]
    assert len(people) == 1
    assert people[0]["attributes"]["birth_month"] == "1982-02"
    assert len(people[0]["mentions"]) == 2


def test_birthless_election_row_is_suppressed_when_birth_identity_is_ambiguous() -> None:
    from finiq.data_scraper.parse.domain.shareholder_meeting_semantics import (
        extract_semantic_contract,
    )

    entities, _ = extract_semantic_contract(
        agenda_records=[],
        elections=[
            {
                "name": "동명이인",
                "birth_month": birth_month,
                "section_type": office_type,
                "evidence": {
                    "field": "성명",
                    "raw_text": f"동명이인 {birth_month or '생년월 없음'}",
                },
            }
            for birth_month, office_type in (
                ("1970-01", "director"),
                ("1980-02", "outside_director"),
                ("", "audit_committee_member"),
            )
        ],
        disclosure_phase="notice",
    )

    people = [entity for entity in entities if entity["name"] == "동명이인"]
    assert {person["attributes"]["birth_month"] for person in people} == {
        "1970-01",
        "1980-02",
    }


def test_correction_table_section_label_does_not_shadow_current_section() -> None:
    result = _parse(
        """
        <table class="correction-comparison">
          <tr><th colspan="3">4. 정정사항</th></tr>
          <tr><th>정정항목</th><th>정정전</th><th>정정후</th></tr>
          <tr><td>1. 일시</td><td>2026-03-01</td><td>2026-03-30</td></tr>
          <tr><td><span>사외이사선임 세부내역</span></td><td>후보 변경 전</td><td>후보 변경 후</td></tr>
        </table>
        <table class="superseded-detail">
          <tr><th>성명</th><th>출생년월</th><th>신규선임여부</th></tr>
          <tr><td>구후보</td><td>1960-01</td><td>신규</td></tr>
        </table>
        <span>사외이사선임 세부내역</span>
        <table class="current-detail">
          <tr><th>성명</th><th>출생년월</th><th>신규선임여부</th></tr>
          <tr><td>김재섭</td><td>1970-02</td><td>신규</td></tr>
        </table>
        <table>
          <tr><td rowspan="2">1. 일시</td><td>날짜</td><td>2026-03-30</td></tr>
          <tr><td>시간</td><td>오전 9시</td></tr>
        </table>
        """,
        title="정기주주총회소집결의(정정)",
    )

    assert [row["name"] for row in result["outside_director_elections"]] == [
        "김재섭"
    ]
    assert result["meeting_date"] == "2026-03-30"
    assert {entity["name"] for entity in result["entities"]} == {"김재섭"}


def test_other_company_br_lines_become_distinct_organizations_and_roles() -> None:
    result = _parse(
        """
        <span>사외이사선임 세부내역</span>
        <table>
          <tr>
            <th>성명</th><th>출생년월</th><th>신규선임여부</th>
            <th>이사 등으로 재직 중인 다른 법인명(직위)</th>
          </tr>
          <tr>
            <td>장원태</td><td>1975-05</td><td>신규</td>
            <td>비시드파트너스(주) 대표이사<br/>더시드그룹 사내이사<br/>비브릭(주) 대표이사</td>
          </tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    person = _entity(result, "장원태")
    organization_names = {
        entity["name"]
        for entity in result["entities"]
        if entity["entity_type"] == "organization"
    }
    assert organization_names == {
        "비시드파트너스(주)",
        "더시드그룹",
        "비브릭(주)",
    }
    roles = _relations(result, "serves_at", source_ref=person["entity_ref"])
    assert {relation["attributes"]["position"] for relation in roles} == {
        "대표이사",
        "사내이사",
    }
    assert {relation["target_ref"] for relation in roles} == {
        _entity(result, name)["entity_ref"] for name in organization_names
    }


def test_explicit_current_major_career_lines_create_precise_serves_at_relations() -> None:
    """Reduced from KIND disclosures 20260109000278 and 20260106000409."""
    result = _parse(
        """
        <span>이사선임 세부내역</span>
        <table>
          <tr>
            <th>성명</th><th>출생년월</th><th>주요경력(현직포함)</th>
          </tr>
          <tr>
            <td>성영철</td><td>1968-01</td>
            <td>전) ㈜이렘 부사장<br/>현) ㈜알엔투테크놀로지 대표이사</td>
          </tr>
          <tr>
            <td>이재호</td><td>1970-07</td>
            <td>현) 대한감정평가법인 이사</td>
          </tr>
          <tr>
            <td>한정수</td><td>1986-01</td>
            <td>
              현)주식회사 비츠조명 대표이사<br/>
              현)마케팅회사 위드잇 사외이사<br/>
              현)마케팅회사 티엣지웨이브 사외이사
            </td>
          </tr>
          <tr>
            <td>김성환</td><td>1982-06</td>
            <td>현) ㈜알엔투테크놀로지 재직</td>
          </tr>
          <tr>
            <td>김지성</td><td>1982-08</td>
            <td>현) 회계법인 베율 딜 본부</td>
          </tr>
          <tr><td>박현대</td><td>1975-01</td><td>현대자동차㈜ 대표이사 사장</td></tr>
          <tr><td>최현우</td><td>1976-02</td><td>- 현우산업 부사장</td></tr>
          <tr><td>이무표</td><td>1977-03</td><td>현) 바이오플러스 부회장</td></tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    organizations = {
        entity["name"]
        for entity in result["entities"]
        if entity["entity_type"] == "organization"
    }
    assert organizations == {
        "㈜알엔투테크놀로지",
        "대한감정평가법인",
        "주식회사 비츠조명",
        "마케팅회사 위드잇",
        "마케팅회사 티엣지웨이브",
    }
    people = {
        entity["entity_ref"]: entity["name"]
        for entity in result["entities"]
        if entity["entity_type"] == "person"
    }
    organizations_by_ref = {
        entity["entity_ref"]: entity["name"]
        for entity in result["entities"]
        if entity["entity_type"] == "organization"
    }
    assert {
        (
            people[relation["source_ref"]],
            organizations_by_ref[relation["target_ref"]],
            relation["attributes"]["position"],
        )
        for relation in _relations(result, "serves_at")
    } == {
        ("성영철", "㈜알엔투테크놀로지", "대표이사"),
        ("이재호", "대한감정평가법인", "이사"),
        ("한정수", "주식회사 비츠조명", "대표이사"),
        ("한정수", "마케팅회사 위드잇", "사외이사"),
        ("한정수", "마케팅회사 티엣지웨이브", "사외이사"),
    }
    assert all(
        relation["evidence"]["field"] == "주요경력(현직포함)"
        and relation["evidence"]["raw_text"].startswith("현")
        for relation in _relations(result, "serves_at")
    )


def test_major_career_reporting_company_uses_reserved_company_ref() -> None:
    result = _parse(
        """
        <span>이사선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>주요경력(현직포함)</th></tr>
          <tr><td>김현재</td><td>현) 테스트회사 대표이사<br>현) (주)테스트회사 경영지원부 이사</td></tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    person = _entity(result, "김현재")
    assert not any(
        entity["entity_type"] == "organization"
        for entity in result["entities"]
    )
    relations = _relations(result, "serves_at", source_ref=person["entity_ref"])
    assert {relation["target_ref"] for relation in relations} == {
        "@reporting_company"
    }
    assert {relation["attributes"]["position"] for relation in relations} == {
        "대표이사",
        "이사",
    }


def test_major_career_rejects_department_token_inside_organization_name() -> None:
    result = _parse(
        """
        <span>이사선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>주요경력(현직포함)</th></tr>
          <tr>
            <td>김철수</td>
            <td>
              現) (주)넥슨코리아 개발 부사장<br>
              現) (주)로보로보 경영지원부 이사<br>
              現) (주)알파와 (주)베타 대표이사<br>
              現) (주)알파·(주)베타 대표이사<br>
              現) (주)알파 &amp; (주)베타 대표이사<br>
              現) 인덕회계법인·태평양법무법인 이사<br>
              現) 미래에셋증권·삼성증권 이사<br>
              現) 국민은행·신한은행 이사<br>
              現) KB증권과 NH투자증권 이사<br>
              現) 알파파트너스·베타파트너스 이사<br>
              現) (주)알파와 베타 대표이사<br>
              現) (주)알파·베타 대표이사<br>
              現) 법인영업 이사<br>
              現) 증권영업 부사장<br>
              現) 그룹전략 이사<br>
              現) 공사관리 이사<br>
              現) 캐피탈영업 이사<br>
              現) (주)BMK&amp;SUN 대표이사<br>
              現) (주)중앙판교개발 대표이사
            </td>
          </tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    serves_at = _relations(result, "serves_at")
    organizations_by_ref = {
        entity["entity_ref"]: entity["name"]
        for entity in result["entities"]
        if entity["entity_type"] == "organization"
    }
    assert {
        (organizations_by_ref[relation["target_ref"]], relation["attributes"]["position"])
        for relation in serves_at
    } == {
        ("(주)BMK&SUN", "대표이사"),
        ("(주)중앙판교개발", "대표이사"),
    }


def test_other_company_strips_explicit_current_employment_period() -> None:
    """Reduced from KIND disclosure 20260310000583."""
    result = _parse(
        """
        <span>사외이사선임 세부내역</span>
        <table>
          <tr>
            <th>성명</th>
            <th>이사 등으로 재직 중인 다른 법인명(직위)</th>
          </tr>
          <tr>
            <td>이경주</td>
            <td>- 2022년 3월- 현재 :KX Innovation (감사)</td>
          </tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    organization = _entity(result, "KX Innovation")
    relation = _relations(result, "serves_at")[0]
    assert relation["target_ref"] == organization["entity_ref"]
    assert relation["attributes"]["position"] == "감사"


def test_other_company_is_authoritative_for_duplicate_major_career_role() -> None:
    result = _parse(
        """
        <span>사외이사선임 세부내역</span>
        <table>
          <tr>
            <th>성명</th><th>주요경력(현직포함)</th>
            <th>이사 등으로 재직 중인 다른 법인명(직위)</th>
          </tr>
          <tr>
            <td>김한민</td>
            <td>현) 인덕회계법인 이사</td>
            <td>인덕회계법인 이사</td>
          </tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    person = _entity(result, "김한민")
    relations = _relations(result, "serves_at", source_ref=person["entity_ref"])
    assert len(relations) == 1
    assert relations[0]["evidence"]["field"] == "other_company"


def test_placeholder_names_are_rejected_but_english_person_name_is_kept() -> None:
    result = _parse(
        """
        <span>이사선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>출생년월</th><th>신규선임여부</th></tr>
          <tr><td>미정</td><td>-</td><td>신규</td></tr>
          <tr><td>-</td><td>-</td><td>신규</td></tr>
          <tr><td>성명</td><td>-</td><td>신규</td></tr>
          <tr><td>해당 없음</td><td>-</td><td>신규</td></tr>
          <tr><td>선임예정</td><td>-</td><td>신규</td></tr>
          <tr><td>David Emery</td><td>-</td><td>신규</td></tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    assert [row["name"] for row in result["director_elections"]] == ["David Emery"]
    assert {entity["name"] for entity in result["entities"]} == {"David Emery"}
    assert _entity(result, "David Emery")["entity_type"] == "person"


def test_structured_candidate_br_lines_are_distinct_people() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>후보자</th><th>가결여부</th></tr>
          <tr>
            <td>1</td><td>사내이사 선임의 건</td>
            <td>김철수<br>이영희</td><td>가결</td>
          </tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert result["agenda_records"][0]["candidate"] == "김철수, 이영희"
    assert {entity["name"] for entity in result["entities"]} == {
        "김철수",
        "이영희",
    }
    assert len(_relations(result, "elected_as")) == 2


def test_detailed_rows_disambiguate_multi_candidate_multi_office_agenda() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>후보자</th><th>가결여부</th></tr>
          <tr>
            <td>1</td><td>이사 및 감사 선임의 건</td>
            <td>김철수<br>이영희</td><td>가결</td>
          </tr>
        </table>
        <span>이사선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>출생년월</th></tr>
          <tr><td>김철수</td><td>1970-01</td></tr>
        </table>
        <span>감사선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>출생년월</th></tr>
          <tr><td>이영희</td><td>1971-02</td></tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    roles_by_name = {}
    for name in ("김철수", "이영희"):
        person = _entity(result, name)
        roles_by_name[name] = {
            relation["attributes"]["office_type"]
            for relation in _relations(
                result,
                "elected_as",
                source_ref=person["entity_ref"],
            )
        }
    assert roles_by_name == {
        "김철수": {"director"},
        "이영희": {"auditor"},
    }


def test_multi_candidate_agenda_does_not_substitute_general_offices() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>후보자</th><th>가결여부</th></tr>
          <tr>
            <td>1</td><td>이사 및 감사 선임의 건</td>
            <td>김철수<br>이영희</td><td>가결</td>
          </tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert not _relations(result, "candidate_for")
    assert not _relations(result, "elected_as")
    subjects = _relations(result, "subject_of")
    assert len(subjects) == 2
    assert all(relation["attributes"]["office_types"] == [] for relation in subjects)


def test_legacy_single_cell_fallback_normalizes_passed_rejected_and_withdrawn() -> None:
    result = _parse(
        """
        <table>
          <tr><td>주주총회 일자</td><td>2023-03-30</td></tr>
          <tr>
            <td>1. 결의사항</td>
            <td>
              제1호 의안 : 윤태영 사내이사 선임의 건<br/>
              → 원안대로 가결<br/>
              제2호 의안 : 송종국 사외이사 선임의 건<br/>
              → 부결<br/>
              제3호 의안 : 홍남기 사외이사 선임의 건<br/>
              → 후보자 사퇴로 안건 철회
            </td>
          </tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert [record["status"] for record in result["agenda_records"]] == [
        "passed",
        "rejected",
        "withdrawn",
    ]
    assert [record["source"] for record in result["agenda_records"]] == [
        "legacy_labeled_cell",
        "legacy_labeled_cell",
        "legacy_labeled_cell",
    ]

    yoon = _entity(result, "윤태영")
    song = _entity(result, "송종국")
    hong = _entity(result, "홍남기")
    assert len(_relations(result, "elected_as", source_ref=yoon["entity_ref"])) == 1
    assert not _relations(result, "elected_as", source_ref=song["entity_ref"])
    assert not _relations(result, "elected_as", source_ref=hong["entity_ref"])
    assert len(_relations(result, "subject_of", source_ref=yoon["entity_ref"])) == 1
    assert len(_relations(result, "subject_of", source_ref=song["entity_ref"])) == 1
    assert len(_relations(result, "subject_of", source_ref=hong["entity_ref"])) == 1


def test_legacy_named_chair_candidates_ignore_shareholder_proposers() -> None:
    result = _parse(
        """
        <table>
          <tr>
            <td rowspan="2">1. 일시</td><td>날짜</td><td>2018-07-04</td>
          </tr>
          <tr><td>시간</td><td>오전 9시</td></tr>
          <tr>
            <td>3. 의안 주요내용</td>
            <td colspan="2">
              제1호 의안: 임시의장 최윤근 선임의 건(정영숙 외 3인 주주 제안)<br/>
              임시의장 김만환 선임의 건(이희철 주주 제안)
            </td>
          </tr>
        </table>
        """,
        title="임시주주총회소집결의",
    )

    assert result["meeting_date"] == "2018-07-04"
    assert {entity["name"] for entity in result["entities"]} == {
        "최윤근",
        "김만환",
    }
    assert len(_relations(result, "subject_of")) == 2
    assert not _relations(result, "proposed")
    assert not any(entity["name"] == "외 3인" for entity in result["entities"])


def test_stock_option_beneficiaries_are_not_extracted() -> None:
    result = _parse(
        """
        <table>
          <tr><td>주주총회 일자</td><td>2025-03-26</td></tr>
          <tr>
            <td>1. 결의사항</td>
            <td>
              제2-1호 의안: [부여대상자: 이수민] 주식매수선택권 부여의 건<br/>
              =&gt; 원안대로 가결<br/>
              제2-2호 의안: [부여대상자: 최경환] 주식매수선택권 부여의 건<br/>
              =&gt; 부결
            </td>
          </tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert not any(
        entity["name"] in {"이수민", "최경환"}
        for entity in result["entities"]
    )
    assert not _relations(result, "option_granted_by")
    assert not any(
        relation["attributes"].get("action") == "stock_option_grant"
        for relation in result["relationships"]
    )


def test_same_name_people_are_matched_by_office_and_birth_month() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>결의구분</th><th>회의목적사항</th><th>가결여부</th></tr>
          <tr><td>3-1</td><td>보통</td><td>사내이사 이성희 선임의 건</td><td>가결</td></tr>
          <tr><td>3-2</td><td>보통</td><td>사외이사 이성희 선임의 건</td><td>가결</td></tr>
        </table>
        <span>이사선임 세부내역</span>
        <table><tr><th>성명</th><th>출생년월</th></tr><tr><td>이성희</td><td>1975-04</td></tr></table>
        <span>사외이사선임 세부내역</span>
        <table><tr><th>성명</th><th>출생년월</th></tr><tr><td>이성희</td><td>1954-09</td></tr></table>
        """,
        title="정기주주총회결과",
    )

    people = [entity for entity in result["entities"] if entity["name"] == "이성희"]
    assert {person["attributes"]["birth_month"] for person in people} == {
        "1975-04",
        "1954-09",
    }
    roles_by_birth = {
        person["attributes"]["birth_month"]: {
            relation["attributes"]["office_type"]
            for relation in _relations(result, "elected_as", source_ref=person["entity_ref"])
        }
        for person in people
    }
    assert roles_by_birth == {
        "1975-04": {"director"},
        "1954-09": {"outside_director"},
    }


def test_negated_pass_wording_does_not_create_active_election() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>결의구분</th><th>회의목적사항</th><th>가결여부</th></tr>
          <tr><td>1</td><td>보통</td><td>사내이사 김철수 선임의 건</td><td>가결되지 않음</td></tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert result["agenda_records"][0]["status"] == "rejected"
    person = _entity(result, "김철수")
    assert not _relations(result, "elected_as", source_ref=person["entity_ref"])


def test_legacy_numbered_list_prefixes_do_not_merge_distinct_agendas() -> None:
    result = _parse(
        """
        <table><tr><td>3. 의안 주요내용</td><td>
          (1) 제1호 의안: 재무제표 승인의 건<br/>
          (2) 제2호 의안: 정관 변경의 건<br/>
          제3-1호 의안: 사내이사 김철수 선임의 건<br/>
          ○ 제4호 의안: 이사 보수한도 승인의 건
        </td></tr></table>
        """,
        title="정기주주총회소집결의",
    )

    assert [record["number"] for record in result["agenda_records"]] == [
        "1",
        "2",
        "3-1",
        "4",
    ]


def test_nested_correction_agenda_table_is_not_a_current_snapshot() -> None:
    result = _parse(
        """
        <table>
          <tr><th>정정항목</th><th>정정전</th><th>정정후</th></tr>
          <tr><td>안건</td><td>
            <table>
              <tr><th>번호</th><th>회의목적사항</th></tr>
              <tr><td>1</td><td>구 안건</td></tr>
            </table>
          </td><td>변경</td></tr>
        </table>
        <table>
          <tr><th>번호</th><th>회의목적사항</th></tr>
          <tr><td>1</td><td>현행 안건</td></tr>
        </table>
        """,
        title="정기주주총회소집결의(정정)",
    )

    assert result["agendas"] == ["현행 안건"]


def test_section_lookup_stops_at_the_next_recognized_heading() -> None:
    result = _parse(
        """
        <span>이사선임 세부내역</span>
        <span>사외이사선임 세부내역</span>
        <table><tr><th>성명</th><th>출생년월</th></tr><tr><td>김외부</td><td>1970-01</td></tr></table>
        """,
        title="정기주주총회소집결의",
    )

    assert result["director_elections"] == []
    assert [row["name"] for row in result["outside_director_elections"]] == ["김외부"]


def test_known_headers_are_canonicalized_without_alternate_selectors() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번 호</th><th>회 의 목 적 사 항</th><th>가 결 여 부</th></tr>
          <tr><td>1</td><td>사내이사 김철수 선임의 건</td><td>가결</td></tr>
        </table>
        <span>이사선임 세부내역</span>
        <table><tr><th>성 명</th><th>출 생 년 월</th></tr><tr><td>김철수</td><td>1970-01</td></tr></table>
        """,
        title="정기주주총회결과",
    )

    assert result["agenda_records"][0]["status"] == "passed"
    assert result["director_elections"][0]["birth_month"] == "1970-01"
    assert len(_relations(result, "elected_as")) == 1


def test_explicit_parenthesized_latin_alias_merges_with_agenda_name() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>가결여부</th></tr>
          <tr><td>1</td><td>사외이사 천양 선임의 건</td><td>가결</td></tr>
        </table>
        <span>사외이사선임 세부내역</span>
        <table><tr><th>성명</th><th>출생년월</th></tr><tr><td>천양 (CHENYANG)</td><td>1984-03</td></tr></table>
        """,
        title="정기주주총회결과",
    )

    person = _entity(result, "천양")
    assert person["attributes"] == {
        "birth_month": "1984-03",
        "aliases": ["CHENYANG"],
    }
    assert len(_relations(result, "elected_as", source_ref=person["entity_ref"])) == 1


def test_shareholder_proposal_label_without_a_named_proposer_creates_no_entity() -> None:
    result = _parse(
        """
        <table><tr><td>3. 의안 주요내용</td><td>
          제1호 의안: 자기주식 취득의 건(취득 예정 금액 : 금 50억 원_주주제안)<br/>
          제2호 의안: 자기주식 매입 승인의 건(150억원(주주제안))
        </td></tr></table>
        """,
        title="정기주주총회소집결의",
    )

    assert result["entities"] == []
    assert not _relations(result, "proposed")


def test_single_detail_candidate_matches_single_unnamed_role_agenda() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>가결여부</th></tr>
          <tr><td>3</td><td>기타 비상무이사 선임의 건</td><td>가결</td></tr>
        </table>
        <span>이사선임 세부내역</span>
        <table><tr><th>성명</th><th>출생년월</th></tr><tr><td>허정호</td><td>1979-02</td></tr></table>
        """,
        title="정기주주총회결과",
    )

    person = _entity(result, "허정호")
    elected = _relations(result, "elected_as", source_ref=person["entity_ref"])
    assert len(elected) == 1
    assert elected[0]["attributes"]["outcome"] == "passed"


def test_role_only_agenda_grammar_does_not_create_people() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>가결여부</th></tr>
          <tr><td>1</td><td>감사위원이 되는 사외이사 선임의 건</td><td>가결</td></tr>
          <tr><td>2</td><td>감사위원 분리선임 인원 상향의 건</td><td>가결</td></tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert result["entities"] == []
    assert not _relations(result, "candidate_for")
    assert not _relations(result, "elected_as")


def test_audit_committee_role_chains_do_not_become_people() -> None:
    """Reduced from KIND disclosures 20260311000752 and 20260309000934."""
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th></tr>
          <tr><td>1</td><td>감사위원회 위원 선임의 건</td></tr>
          <tr><td>1-1</td><td>감사위원회 위원 양규원 신규선임의 건</td></tr>
          <tr><td>2</td><td>감사위원겸 사외이사 선임의 건</td></tr>
          <tr><td>2-1</td><td>감사위원겸 사외이사 박정호 선임의 건</td></tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    assert {
        entity["name"]
        for entity in result["entities"]
        if entity["entity_type"] == "person"
    } == {"양규원", "박정호"}
    assert {
        relation["attributes"]["office_type"]
        for relation in _relations(
            result,
            "candidate_for",
            source_ref=_entity(result, "양규원")["entity_ref"],
        )
    } == {"audit_committee_member"}
    assert {
        relation["attributes"]["office_type"]
        for relation in _relations(
            result,
            "candidate_for",
            source_ref=_entity(result, "박정호")["entity_ref"],
        )
    } == {"audit_committee_member", "outside_director"}


def test_split_other_company_and_position_match_one_multiline_statement() -> None:
    result = _parse(
        """
        <span>사외이사선임 세부내역</span>
        <table>
          <tr>
            <th>성명</th><th>출생년월</th>
            <th>이사 등으로 재직 중인 다른 법인명(직위)</th>
          </tr>
          <tr>
            <td>김외부</td><td>1970-01</td>
            <td>대원제약 주식회사<br/>사외이사(감사위원)</td>
          </tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    person = _entity(result, "김외부")
    organization = _entity(result, "대원제약 주식회사")
    relation = _relations(result, "serves_at", source_ref=person["entity_ref"])[0]
    assert relation["target_ref"] == organization["entity_ref"]
    assert relation["attributes"]["position"] == "사외이사(감사위원)"


def test_split_role_word_does_not_create_an_other_company() -> None:
    result = _parse(
        """
        <span>사외이사선임 세부내역</span>
        <table>
          <tr>
            <th>성명</th><th>출생년월</th>
            <th>이사 등으로 재직 중인 다른 법인명(직위)</th>
          </tr>
          <tr>
            <td>김경계</td><td>1970-01</td>
            <td>캠패니언그라운드 사내<br/>이사</td>
          </tr>
          <tr>
            <td>이경계</td><td>1971-02</td>
            <td>테스트회사 비상근<br/>감사</td>
          </tr>
          <tr>
            <td>박경계</td><td>1972-03</td>
            <td>테스트회사 부<br/>사장</td>
          </tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    for name in ("김경계", "이경계", "박경계"):
        person = _entity(result, name)
        assert not _relations(result, "serves_at", source_ref=person["entity_ref"])


def test_other_company_position_sequences_start_at_the_first_role() -> None:
    """Reduced from the repeated 2026 composite-position disclosures."""
    result = _parse(
        """
        <span>사외이사선임 세부내역</span>
        <table>
          <tr>
            <th>성명</th><th>출생년월</th>
            <th>이사 등으로 재직 중인 다른 법인명(직위)</th>
          </tr>
          <tr><td>신동우</td><td>1960-01</td><td>㈜나노 대표이사 회장</td></tr>
          <tr><td>김성철</td><td>1961-02</td><td>現 KT 사외이사 및 감사위원</td></tr>
          <tr>
            <td>양규원</td><td>1962-03</td>
            <td>승일 사외이사 및 감사위원장(2026년 3월 최종 임기만료 예정)</td>
          </tr>
          <tr><td>김봉진</td><td>1963-04</td><td>㈜일렉트로엠 사외이사 및 감사위원</td></tr>
          <tr><td>박희준</td><td>1964-05</td><td>두산퓨얼셀 사외이사 및 감사위원</td></tr>
          <tr><td>이건주</td><td>1965-06</td><td>태양 사외이사 및 감사위원</td></tr>
          <tr>
            <td>임상미</td><td>1966-07</td>
            <td>- 쿠팡파이난셜 주식회사(사외이사, 감사위원회 위원장)</td>
          </tr>
          <tr>
            <td>선우희연</td><td>1967-08</td>
            <td>(주)슈피겐코리아(사외이사, 감사위원장)</td>
          </tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    entities = {entity["entity_ref"]: entity["name"] for entity in result["entities"]}
    serves_at = {
        (entities[relation["source_ref"]], entities[relation["target_ref"]]):
        relation["attributes"]["position"]
        for relation in _relations(result, "serves_at")
    }
    assert serves_at == {
        ("신동우", "㈜나노"): "대표이사 회장",
        ("김성철", "KT"): "사외이사 및 감사위원",
        ("양규원", "승일"): "사외이사 및 감사위원장",
        ("김봉진", "㈜일렉트로엠"): "사외이사 및 감사위원",
        ("박희준", "두산퓨얼셀"): "사외이사 및 감사위원",
        ("이건주", "태양"): "사외이사 및 감사위원",
        ("임상미", "쿠팡파이난셜 주식회사"): "사외이사, 감사위원회 위원장",
        ("선우희연", "(주)슈피겐코리아"): "사외이사, 감사위원장",
    }


def test_automatic_disposal_is_not_treated_as_a_passed_result() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>가결여부</th><th>비고</th></tr>
          <tr><td>1</td><td>사내이사 김철수 선임의 건</td><td>미결</td><td>자동 폐기</td></tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert result["agenda_records"][0]["status"] == "not_tabled"
    person = _entity(result, "김철수")
    assert not _relations(result, "elected_as", source_ref=person["entity_ref"])


def test_external_auditor_is_kept_while_voting_manager_is_excluded() -> None:
    result = _parse(
        """
        <table>
          <tr><td>5. 기타 투자판단에 참고할 사항</td></tr>
          <tr><td>
            외부감사인 선임 보고 : 삼일회계법인 선임<br/>
            이번 주주총회에 전자투표제도를 활용하며 이 제도의 관리업무는
            KB국민은행에 위탁할 예정입니다.
          </td></tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    auditor = _entity(result, "삼일회계법인")
    assert auditor["entity_type"] == "organization"
    assert not any(entity["name"] == "KB국민은행" for entity in result["entities"])
    assert _relations(
        result, "external_auditor_of", source_ref=auditor["entity_ref"]
    )[0]["target_ref"] == "@reporting_company"
    assert not _relations(result, "electronic_voting_manager_for")
    _assert_semantic_shapes(result)


def test_named_voting_system_provider_is_excluded() -> None:
    """Reduced from 20260316002584."""
    result = _parse(
        """
        <table>
          <tr><td>5. 기타 투자판단에 참고할 사항</td></tr>
          <tr><td>
            당사는 제35기 정기주주총회에서 전자투표제도를 활용하기로 하였습니다.<br/>
            전자투표ㆍ전자위임장권유시스템(삼성증권)<br/>
            인터넷 주소: http://vote.samsungpop.com<br/>
            전자투표 행사: 2026년 3월 21일 ~ 2026년 3월 30일
          </td></tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    assert not any(entity["name"] == "삼성증권" for entity in result["entities"])
    assert not _relations(result, "electronic_voting_system_provider_for")
    _assert_semantic_shapes(result)


def test_candidate_approval_and_appointment_grammar_excludes_compensation() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>가결여부</th></tr>
          <tr><td>1</td><td>사외이사 이동원 후보 승인의 건</td><td>가결</td></tr>
          <tr><td>2</td><td>감사 보수한도 승인의 건</td><td>가결</td></tr>
          <tr><td>3</td><td>감사 송채훈 선임의 건</td><td>가결</td></tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert {entity["name"] for entity in result["entities"]} == {"이동원", "송채훈"}
    assert {
        relation["attributes"]["office_type"]
        for relation in _relations(result, "elected_as")
    } == {"outside_director", "auditor"}


def test_passed_vote_followed_by_refused_appointment_is_not_active() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>가결여부</th><th>비고</th></tr>
          <tr>
            <td>3-4</td><td>사외이사 한권석 선임의 건</td><td>가결</td>
            <td>원안대로 승인되었으나 본인이 취임승낙을 철회함</td>
          </tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert result["agenda_records"][0]["status"] == "passed"
    person = _entity(result, "한권석")
    candidate = _relations(result, "candidate_for", source_ref=person["entity_ref"])
    assert len(candidate) == 1
    assert candidate[0]["attributes"]["outcome"] == "passed"
    assert candidate[0]["attributes"]["candidate_status"] == "withdrawn"
    subject = _relations(result, "subject_of", source_ref=person["entity_ref"])
    assert subject[0]["attributes"]["candidate_status"] == "withdrawn"
    assert not _relations(result, "elected_as", source_ref=person["entity_ref"])


def test_named_withdrawal_suppresses_only_that_candidate() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>후보자</th><th>가결여부</th><th>비고</th></tr>
          <tr>
            <td>3</td><td>사외이사 선임의 건</td><td>김철수, 박영희</td><td>가결</td>
            <td>김철수 후보자가 취임승낙을 철회함</td>
          </tr>
        </table>
        <span>사외이사선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>출생년월</th></tr>
          <tr><td>김철수</td><td>1970-01</td></tr>
          <tr><td>박영희</td><td>1972-02</td></tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert result["agenda_records"][0]["status"] == "passed"
    withdrawn = _entity(result, "김철수")
    elected = _entity(result, "박영희")
    withdrawn_candidate = _relations(
        result,
        "candidate_for",
        source_ref=withdrawn["entity_ref"],
    )[0]
    assert withdrawn_candidate["attributes"]["candidate_status"] == "withdrawn"
    assert not _relations(result, "elected_as", source_ref=withdrawn["entity_ref"])
    assert "candidate_status" not in _relations(
        result,
        "candidate_for",
        source_ref=elected["entity_ref"],
    )[0]["attributes"]
    assert len(_relations(result, "elected_as", source_ref=elected["entity_ref"])) == 1


def test_unnamed_withdrawal_does_not_choose_between_multiple_candidates() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>후보자</th><th>가결여부</th><th>비고</th></tr>
          <tr>
            <td>3</td><td>사외이사 선임의 건</td><td>정하나, 이둘</td><td>가결</td>
            <td>본인이 취임승낙을 철회함</td>
          </tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert result["agenda_records"][0]["status"] == "passed"
    for name in ("정하나", "이둘"):
        person = _entity(result, name)
        candidate = _relations(
            result,
            "candidate_for",
            source_ref=person["entity_ref"],
        )[0]
        assert "candidate_status" not in candidate["attributes"]
        assert len(_relations(result, "elected_as", source_ref=person["entity_ref"])) == 1


def test_named_withdrawal_keeps_the_remaining_detailed_candidate_active() -> None:
    """Reduced from KIND disclosure 20260331003952."""
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>가결여부</th><th>비고</th></tr>
          <tr>
            <td>4</td>
            <td>감사위원회 위원이 되는 사외이사 선임의 건 (박기수, 여윤미)</td>
            <td>가결</td>
            <td>안건 가결후 박기수 후보자 취임의사 철회, 여윤미 후보자만 취임 예정</td>
          </tr>
        </table>
        <span>사외이사선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>출생년월</th><th>신규선임여부</th></tr>
          <tr><td>여윤미</td><td>1968-02</td><td>재선임</td></tr>
        </table>
        <span>감사위원선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>출생년월</th><th>신규선임여부</th></tr>
          <tr><td>여윤미</td><td>1968-02</td><td>재선임</td></tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert result["agenda_records"][0]["status"] == "passed"
    assert not any(entity["name"] == "박기수" for entity in result["entities"])
    person = _entity(result, "여윤미")
    elected_roles = {
        relation["attributes"]["office_type"]
        for relation in _relations(result, "elected_as", source_ref=person["entity_ref"])
    }
    assert elected_roles == {"outside_director", "audit_committee_member"}
    subject = _relations(result, "subject_of", source_ref=person["entity_ref"])
    assert len(subject) == 1
    assert set(subject[0]["attributes"]["office_types"]) == {
        "outside_director",
        "audit_committee_member",
    }
    assert "office_type" not in subject[0]["attributes"]


def test_short_election_name_does_not_match_a_longer_agenda_candidate() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>가결여부</th></tr>
          <tr><td>1</td><td>사외이사 김민수 선임의 건</td><td>가결</td></tr>
        </table>
        <span>사외이사선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>출생년월</th></tr>
          <tr><td>김민</td><td>1970-01</td></tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    agenda_candidate = _entity(result, "김민수")
    detailed_candidate = _entity(result, "김민")
    assert len(
        _relations(result, "elected_as", source_ref=agenda_candidate["entity_ref"])
    ) == 1
    assert not _relations(
        result,
        "elected_as",
        source_ref=detailed_candidate["entity_ref"],
    )
    assert not _relations(
        result,
        "subject_of",
        source_ref=detailed_candidate["entity_ref"],
    )


def test_invalid_calendar_meeting_date_is_not_emitted() -> None:
    result = _parse(
        """
        <table><tr><td>1. 일시</td><td>2026년 13월 40일</td></tr></table>
        """,
        title="정기주주총회소집결의",
    )

    assert result["meeting_date"] is None


def test_inline_other_company_keeps_spaced_employment_mode_with_auditor_role() -> None:
    result = _parse(
        """
        <span>사외이사선임 세부내역</span>
        <table>
          <tr>
            <th>성명</th><th>출생년월</th>
            <th>이사 등으로 재직 중인 다른 법인명(직위)</th>
          </tr>
          <tr>
            <td>이창수</td><td>1954-10</td>
            <td>주식회사 알레르망 비상근 감사</td>
          </tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    person = _entity(result, "이창수")
    organization = _entity(result, "주식회사 알레르망")
    relation = _relations(result, "serves_at", source_ref=person["entity_ref"])[0]
    assert relation["target_ref"] == organization["entity_ref"]
    assert relation["attributes"]["position"] == "비상근 감사"


def test_shareholder_proposal_candidate_is_a_candidate_not_the_proposer() -> None:
    """Reduced from KIND disclosures 20260225000885 and 20260326001457."""
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>가결여부</th></tr>
          <tr>
            <td>6</td><td>감사 선임의 건(주주 제안:후보자 박주현)</td><td>미결</td>
          </tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    person = _entity(result, "박주현")
    assert len(_relations(result, "candidate_for", source_ref=person["entity_ref"])) == 1
    assert len(_relations(result, "subject_of", source_ref=person["entity_ref"])) == 1
    assert not _relations(result, "proposed")
    assert not _relations(result, "elected_as", source_ref=person["entity_ref"])


def test_explicit_shareholder_proposer_list_is_not_extracted() -> None:
    """Reduced from KIND disclosures 20260311001748 and 20260330001464."""
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>가결여부</th></tr>
          <tr>
            <td>3</td>
            <td>정관 일부 변경의 건(주주제안_강태범,장정석,박종원)</td>
            <td>부결</td>
          </tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert not any(
        entity["name"] in {"강태범", "장정석", "박종원"}
        for entity in result["entities"]
    )
    assert not _relations(result, "proposed")


def test_correction_after_reference_note_does_not_extract_proposer() -> None:
    """Reduced from KIND disclosure 20100210000221."""
    result = _parse(
        """
        <table>
          <tr><th>정정항목</th><th>정정전</th><th>정정후</th></tr>
          <tr>
            <td>5. 기타 투자판단에 참고할 사항</td>
            <td>이사선임 후보자 중 구후보는 주주제안(제안자:구제안자)에 의한 후보자임.</td>
            <td>
              이사선임 후보자 중 김민성, 장원환, 문혜강 이상 3명은 주주제안(제안자:조규관)에 의한 후보자임.<br/>
              감사선임 후보자 중 김봉갑은 주주제안(제안인:조규관)에 의한 후보자임.
            </td>
          </tr>
        </table>
        <table>
          <tr><th>번호</th><th>회의목적사항</th></tr>
          <tr><td>4</td><td>이사 선임의 건</td></tr>
          <tr><td>5</td><td>감사 선임의 건</td></tr>
        </table>
        <span>이사선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>생년월일</th></tr>
          <tr><td>김민성</td><td>1962-05-01</td></tr>
          <tr><td>장원환</td><td>1968-02-26</td></tr>
          <tr><td>문혜강</td><td>1955-05-07</td></tr>
        </table>
        <span>감사선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>생년월일</th></tr>
          <tr><td>김봉갑</td><td>1951-04-15</td></tr>
        </table>
        """,
        title="정기주주총회소집결의(정정)",
    )

    assert {entity["name"] for entity in result["entities"]} >= {
        "김민성",
        "장원환",
        "문혜강",
        "김봉갑",
    }
    assert not any(
        entity["name"] in {"조규관", "구제안자"}
        for entity in result["entities"]
    )
    assert not _relations(result, "proposed")


def test_correction_proposer_surfaces_are_not_extracted() -> None:
    result = _parse(
        """
        <table>
          <tr><th>정정항목</th><th>정정전</th><th>변경후</th></tr>
          <tr>
            <td>5. 기타 투자판단에 참고할 사항</td><td>-</td>
            <td>이사선임 후보자 중 김민성은 주주제안(제안자:오헤더)에 의한 후보자임.</td>
          </tr>
        </table>
        <table>
          <tr><th>정정항목</th><th>정정전</th><th>정정후</th></tr>
          <tr>
            <td>이사선임 세부내역</td><td>-</td>
            <td>이사선임 후보자 중 김민성은 주주제안(제안자:오항목)에 의한 후보자임.</td>
          </tr>
          <tr>
            <td>5. 기타 투자판단에 참고할 사항</td><td>-</td>
            <td>김민성 관련 주주제안(제안자:임의문구)에 의한 후보자 안내</td>
          </tr>
          <tr>
            <td>5. 기타 투자판단에 참고할 사항</td><td>-</td>
            <td>이사선임 후보자 중 김민성은 주주제안(제안자:안건모호)에 의한 후보자임.</td>
          </tr>
          <tr>
            <td>5. 기타 투자판단에 참고할 사항</td><td>-</td>
            <td>이사선임 후보자 중 없는후보는 주주제안(제안자:서미정)에 의한 후보자임.</td>
          </tr>
        </table>
        <table>
          <tr><th>번호</th><th>회의목적사항</th></tr>
          <tr><td>1</td><td>이사 선임의 건</td></tr>
          <tr><td>2</td><td>이사 추가 선임의 건</td></tr>
        </table>
        <span>이사선임 세부내역</span>
        <table>
          <tr><th>성명</th><th>생년월일</th></tr>
          <tr><td>김민성</td><td>1962-05-01</td></tr>
        </table>
        """,
        title="정기주주총회소집결의(정정)",
    )

    assert not _relations(result, "proposed")
    assert not any(
        entity["name"] in {"오헤더", "오항목", "임의문구", "안건모호", "서미정"}
        for entity in result["entities"]
    )


def test_explicit_proposer_surfaces_are_not_extracted() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th></tr>
          <tr><td>1</td><td>정관 변경의 건(주주제안-감사 박주현)</td></tr>
          <tr><td>2</td><td>자기주식 취득의 건(주주제안-취득 예정 금액)</td></tr>
          <tr><td>3</td><td>정관 변경의 건(주주제안-감사후보자 박주현)</td></tr>
          <tr>
            <td>4</td>
            <td>정관 변경의 건(주주제안-리우 쥬 호우,John Smith,(주)알파,박주현 외 3명)</td>
          </tr>
          <tr><td>5</td><td>정관 변경의 건(주주제안-주식회사 취득 예정 금액)</td></tr>
          <tr><td>6</td><td>정관 변경의 건(주주제안-주식회사 사외이사 박주현)</td></tr>
          <tr><td>7</td><td>정관 변경의 건(주주제안-취득금액,예정금액,(주)취득금액)</td></tr>
          <tr><td>8</td><td>정관 변경의 건(주주제안-후보박주현,박주현후보,선임박주현,감사박주현,이사박주현)</td></tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    assert not result["entities"]
    assert not _relations(result, "proposed")


def test_candidate_grammar_excludes_role_and_cause_clauses() -> None:
    """Reduced from malformed candidate surfaces found in the 2026 KIND corpus."""
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th></tr>
          <tr><td>1</td><td>이강인 후보의 감사 선임의 건</td></tr>
          <tr><td>2</td><td>감사위원이 되는 이사 선임의 건</td></tr>
          <tr><td>3</td><td>사외이사 선임의 건(사외이사 백승권 사임에 따른 신규선임)</td></tr>
          <tr><td>4</td><td>정관 일부 변경 - 이사의 의무 추가 및 독립이사 선임의 건</td></tr>
          <tr><td>5</td><td>상근감사 신광현 임기 만료에 따른 중임의 건</td></tr>
          <tr><td>6</td><td>비상근감사 안정원 재 선임의 건</td></tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    assert {
        entity["name"]
        for entity in result["entities"]
        if entity["entity_type"] == "person"
    } == {"이강인", "신광현", "안정원"}


def test_candidate_surfaces_strip_leading_office_and_action_clauses() -> None:
    """Reduced from KIND receipts 20260304001385, 20260310000544,
    20260310000620, 20260316002584, 20260325000350, 20260326003653,
    20260327000582, 20260327001774, and 20260331000731.
    """
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>후보자</th><th>가결여부</th></tr>
          <tr><td>1</td><td>감사위원이 되는 사외이사 선임의 건(후보자 : 사외이사 신강식)</td><td></td><td>가결</td></tr>
          <tr><td>2</td><td>사내이사 선임의 건(후보자 : 사내이사 유형민)</td><td></td><td>가결</td></tr>
          <tr><td>3</td><td>사내이사 선임의 건(후보자 : 사내이사 박캘빈병관)</td><td></td><td>가결</td></tr>
          <tr><td>4</td><td>감사 선임의 건 감사 요코타 타카히사 재선임의 건</td><td></td><td>가결</td></tr>
          <tr><td>5</td><td>4.감사선임의건 비상임감사 박기완 신규선임의건</td><td></td><td>가결</td></tr>
          <tr><td>6</td><td>이사 선임의 건 (후보자:사내이사 이태규)</td><td></td><td>가결</td></tr>
          <tr><td>7</td><td>사외이사 선임의 건</td><td>김 민 수</td><td>가결</td></tr>
          <tr><td>8</td><td>사외이사 선임의 건</td><td>John Paul Smith</td><td>가결</td></tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    people = {
        entity["name"]
        for entity in result["entities"]
        if entity["entity_type"] == "person"
    }
    assert people == {
        "신강식",
        "유형민",
        "박캘빈병관",
        "요코타 타카히사",
        "박기완",
        "이태규",
        "김 민 수",
        "John Paul Smith",
    }
    assert {
        _entity(result, name)["entity_ref"]
        for name in people
    } == {
        relation["source_ref"] for relation in _relations(result, "elected_as")
    }


def test_role_derived_candidate_clause_is_not_a_person() -> None:
    """Reduced from KIND notice 20260316002280."""
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th></tr>
          <tr><td>1</td><td>감사의원회 의원이 되는 사외이사 선임의 건</td></tr>
        </table>
        """,
        title="정기주주총회소집결의",
    )

    assert not [
        entity for entity in result["entities"] if entity["entity_type"] == "person"
    ]
    assert not _relations(result, "candidate_for")


def test_candidate_sources_collect_independently_and_ignore_attribute_alias() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>후보자</th><th>가결여부</th></tr>
          <tr>
            <td>1</td><td>사외이사 박표기 선임의 건(후보자: 김라벨)</td>
            <td>이구조</td><td>가결</td>
          </tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert {
        entity["name"]
        for entity in result["entities"]
        if entity["entity_type"] == "person"
    } == {"이구조", "박표기", "김라벨"}

    from finiq.data_scraper.parse.domain.shareholder_meeting_semantics import (
        extract_semantic_contract,
    )

    entities, relationships = extract_semantic_contract(
        agenda_records=[
            {
                "agenda_ref": "agenda:1",
                "title": "사외이사 선임의 건",
                "attributes": {"후보자": "김대체"},
                "evidence": {"raw_text": "사외이사 선임의 건"},
            }
        ],
        elections=[],
        disclosure_phase="notice",
    )
    assert entities == []
    assert not [
        relation
        for relation in relationships
        if relation["relationship_type"] == "candidate_for"
    ]


def test_canonical_candidate_rejects_title_backtracking_prefix() -> None:
    """Reduced from seven 2026 notices/results whose names end in 재."""
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>후보자</th><th>가결여부</th></tr>
          <tr><td>1</td><td>사외이사 이원재 선임의 건</td><td>이원재</td><td>가결</td></tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    assert {
        entity["name"]
        for entity in result["entities"]
        if entity["entity_type"] == "person"
    } == {"이원재"}
    assert {relation["relationship_type"] for relation in result["relationships"]} >= {
        "candidate_for",
        "subject_of",
        "elected_as",
    }


def test_stock_option_sources_are_not_semantic_entities() -> None:
    from finiq.data_scraper.parse.domain.shareholder_meeting_semantics import (
        extract_semantic_contract,
    )

    entities, relationships = extract_semantic_contract(
        agenda_records=[
            {
                "agenda_ref": "agenda:1",
                "title": "[부여대상자: 김중복] 주식매수선택권 부여의 건",
                "candidate": "김중복, 이정규",
                "attributes": {"후보자": "박대체"},
                "status": "passed",
                "evidence": {
                    "raw_text": "[부여대상자: 김중복] 주식매수선택권 부여의 건"
                },
            }
        ],
        elections=[],
        disclosure_phase="result",
    )

    assert not entities
    assert [relation["relationship_type"] for relation in relationships] == [
        "includes"
    ]


def test_named_election_requires_one_compatible_name_evidenced_agenda() -> None:
    from finiq.data_scraper.parse.domain.shareholder_meeting_semantics import (
        extract_semantic_contract,
    )

    entities, relationships = extract_semantic_contract(
        agenda_records=[
            {
                "agenda_ref": "agenda:1",
                "title": "사외이사 선임 김중복 후보 검토",
                "status": "passed",
                "evidence": {"raw_text": "사외이사 선임 김중복 후보 검토"},
            },
            {
                "agenda_ref": "agenda:2",
                "title": "김중복 후보 검토 및 선임",
                "status": "rejected",
                "evidence": {"raw_text": "김중복 후보 검토 및 선임"},
            },
        ],
        elections=[
            {
                "name": "김중복",
                "birth_month": "1970-01",
                "section_type": "outside_director",
                "evidence": {"raw_text": "김중복 1970-01"},
            }
        ],
        disclosure_phase="result",
    )

    person_ref = next(
        entity["entity_ref"] for entity in entities if entity["name"] == "김중복"
    )
    assert not [
        relation
        for relation in relationships
        if relation["source_ref"] == person_ref
        and relation["relationship_type"] in {"elected_as", "subject_of"}
    ]
    candidate = next(
        relation
        for relation in relationships
        if relation["source_ref"] == person_ref
        and relation["relationship_type"] == "candidate_for"
    )
    assert candidate["attributes"]["outcome"] is None


def test_subagenda_without_role_does_not_inherit_parent_office() -> None:
    result = _parse(
        """
        <table>
          <tr><th>번호</th><th>회의목적사항</th><th>가결여부</th></tr>
          <tr><td>3</td><td>사외이사 선임의 건</td><td>가결</td></tr>
          <tr><td>3-1</td><td>후보자: 김하위</td><td>가결</td></tr>
        </table>
        """,
        title="정기주주총회결과",
    )

    person = _entity(result, "김하위")
    assert not _relations(result, "candidate_for", source_ref=person["entity_ref"])
    assert not _relations(result, "elected_as", source_ref=person["entity_ref"])
    assert len(_relations(result, "subject_of", source_ref=person["entity_ref"])) == 1
