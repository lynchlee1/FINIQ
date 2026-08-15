"""Golden cases for explicitly named shareholder-meeting stakeholders."""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from finiq.data_scraper.parse.domain.shareholder_meeting_stakeholders import (
    extract_stakeholder_mentions,
)


def _soup(value: str, *, label: str = "5. 기타 투자판단에 참고할 사항") -> BeautifulSoup:
    return BeautifulSoup(
        f"""
        <html><body><table>
          <tr><td>{label}</td></tr>
          <tr><td>{value}</td></tr>
        </table></body></html>
        """,
        "html.parser",
    )


def test_first_reference_note_source_is_not_replaced() -> None:
    soup = BeautifulSoup(
        """
        <table>
          <tr><td>5. 기타 투자판단에 참고할 사항</td></tr>
          <tr><td>-</td></tr>
          <tr><td>5. 기타 투자판단에 참고할 사항</td></tr>
          <tr><td>외부감사인 선임 : 삼일회계법인 선임</td></tr>
        </table>
        """,
        "lxml",
    )

    assert extract_stakeholder_mentions(soup) == []


def test_20260310001962_extracts_explicitly_appointed_external_auditor() -> None:
    mentions = extract_stakeholder_mentions(
        _soup(
            """
            제11기 주주총회 보고사항<br>
            - 감사보고<br>
            - 제11기 영업보고<br>
            - 제11기 내부회계 운영실태보고<br>
            - 외부감사인 선임 보고 : 삼일회계법인 선임(제12기~제14기)
            """
        )
    )

    assert mentions == [
        {
            "name": "삼일회계법인",
            "entity_type": "organization",
            "relationship_type": "external_auditor_of",
            "target_ref": "@reporting_company",
            "attributes": {"state": "current", "action": "appointed"},
            "evidence": {
                "section_title": "기타 투자판단에 참고할 사항",
                "table_index": 0,
                "row_index": 1,
                "field": "기타 투자판단에 참고할 사항",
                "raw_text": "- 외부감사인 선임 보고 : 삼일회계법인 선임(제12기~제14기)",
            },
        }
    ]


def test_20260316001346_labels_former_and_current_auditors() -> None:
    mentions = extract_stakeholder_mentions(
        _soup(
            """
            - 주주총회 보고사항 : 감사보고, 영업보고, 내부회계관리제도 운영실태보고<br>
            - 외부감사인 변경 : 한울회계법인에서 대주회계법인으로 변경하였습니다.
            """
        )
    )

    assert [(mention["name"], mention["attributes"]) for mention in mentions] == [
        ("한울회계법인", {"state": "former", "action": "replaced"}),
        ("대주회계법인", {"state": "current", "action": "appointed"}),
    ]
    assert all(
        mention["relationship_type"] == "external_auditor_of"
        and mention["target_ref"] == "@reporting_company"
        for mention in mentions
    )


@pytest.mark.parametrize(
    "value",
    [
        "전자투표제도의 관리업무를 KB국민은행에 위탁할 예정입니다.",
        "전자투표 관리기관: 한국예탁결제원",
        "당사는 이번 주주총회에서 전자투표제도를 활용합니다.<br>"
        "삼성증권 전자투표시스템 https://vote.samsungpop.com<br>"
        "전자투표 행사기간: 2026년 3월 17일 ~ 2026년 3월 26일",
    ],
)
def test_electronic_voting_institutions_are_not_extracted(value: str) -> None:
    assert extract_stakeholder_mentions(_soup(value)) == []


def test_table_tag_can_be_used_as_the_current_soup() -> None:
    soup = _soup("외부감사인 선임 : 삼일회계법인 선임")
    table = soup.find("table")
    assert table is not None

    mentions = extract_stakeholder_mentions(table)

    assert len(mentions) == 1
    assert mentions[0]["evidence"]["table_index"] == 0


def test_20260220000684_extracts_arrow_auditor_transition() -> None:
    mentions = extract_stakeholder_mentions(
        _soup(
            "- 외부감사인 변경<br>"
            "제22기(2025.01.01~2025.12.31) 삼정회계법인<br>"
            "→ 제23기~제25기(2026.01.01~2028.12.31) 삼일회계법인"
        )
    )

    assert [(mention["name"], mention["attributes"]) for mention in mentions] == [
        ("삼정회계법인", {"state": "former", "action": "replaced"}),
        ("삼일회계법인", {"state": "current", "action": "appointed"}),
    ]


def test_20260306000529_uses_adjacent_designation_clause() -> None:
    mentions = extract_stakeholder_mentions(
        _soup(
            "4. 외부감사인 선임(지정)보고<br>"
            "- 당사는 외감법에 의거 금융감독원으로부터 2026년~2028년 "
            "사업연도까지 삼덕회계법인을 감사인으로 지정받아 회계감사 계약을 "
            "체결하였습니다."
        )
    )

    assert [(mention["name"], mention["attributes"]) for mention in mentions] == [
        ("삼덕회계법인", {"state": "current", "action": "designated"})
    ]


def test_20260320000996_marks_reselected_auditor_as_reappointed() -> None:
    mentions = extract_stakeholder_mentions(
        _soup(
            "①감사보고, ②영업보고, ③내부회계관리제도 운영실태보고, "
            "④외부감사인 선임보고<br>"
            "- 당사는 제27기부터 제29기까지의 외부감사인으로 "
            "태성회계법인을 재선정하였음."
        )
    )

    assert [(mention["name"], mention["attributes"]) for mention in mentions] == [
        ("태성회계법인", {"state": "current", "action": "reappointed"})
    ]


def test_20260327000683_extracts_explicit_existing_and_new_auditors() -> None:
    mentions = extract_stakeholder_mentions(
        _soup(
            "- 당사의 기존 외부감사인인 현대회계법인과의 감사 계약이 종료되어 "
            "제15기부터 제17기까지 외부감사인으로 대주회계법인을 선임하였습니다."
        )
    )

    assert [(mention["name"], mention["attributes"]) for mention in mentions] == [
        ("현대회계법인", {"state": "former", "action": "replaced"}),
        ("대주회계법인", {"state": "current", "action": "appointed"}),
    ]


def test_20260327001010_links_generic_report_to_named_accounting_auditor() -> None:
    mentions = extract_stakeholder_mentions(
        _soup(
            "금번 정기주주총회의 보고사항은 감사보고, 영업보고 및 "
            "외부감사인선임보고입니다.<br>"
            "당사는 당기 회계감사인을 삼도회계법인으로 변경하였습니다."
        )
    )

    assert [(mention["name"], mention["attributes"]) for mention in mentions] == [
        ("삼도회계법인", {"state": "current", "action": "appointed"})
    ]


def test_20260331001529_same_firm_reappointment_has_no_former_relation() -> None:
    mentions = extract_stakeholder_mentions(
        _soup(
            "- 당사의 기존 외부감사인인 삼덕회계법인과의 감사 계약이 종료되어 "
            "제29기부터 제31기까지 외부감사인으로 삼덕회계법인을 재선임하였습니다."
        )
    )

    assert [(mention["name"], mention["attributes"]) for mention in mentions] == [
        ("삼덕회계법인", {"state": "current", "action": "reappointed"})
    ]


def test_named_external_auditor_opinion_is_a_current_role_declaration() -> None:
    mentions = extract_stakeholder_mentions(
        _soup("외부감사인(이정회계법인)의 감사의견은 적정입니다.")
    )

    assert [(mention["name"], mention["attributes"]) for mention in mentions] == [
        ("이정회계법인", {"state": "current"})
    ]


@pytest.mark.parametrize(
    "value",
    [
        "외부감사인 선임보고가 있습니다.",
        "삼일회계법인이 감사의견을 제출했습니다.",
        "전자투표제도 세부사항은 https://vote.example.com을 참고하세요.",
        "이번 주주총회에 전자투표제도를 도입합니다. "
        "삼성증권 전자투표시스템을 참고하세요.",
        "삼성증권 전자투표서비스 이용약관과 https://vote.samsungpop.com을 "
        "참고하세요.",
        "이번 주주총회에 전자투표제도를 도입하며 전자투표 행사기간을 "
        "별도로 안내합니다. 삼성증권 전자투표시스템을 사용합니다.",
        "보고서 관리업무를 삼성증권에 위탁합니다.",
        "이번 주주총회에서 전자투표제도를 활용합니다.<br>"
        "주차 관리업무는 미래에셋증권에 위탁합니다.",
        "이번 주주총회에서 전자투표제도를 활용하지 않기로 하였습니다.<br>"
        "삼성증권 전자투표시스템 https://vote.samsungpop.com<br>"
        "전자투표 행사기간: 2026년 3월 1일 ~ 2026년 3월 10일",
        "이번 주주총회에서는 전자적 방법으로 의결권을 행사하지 않습니다.<br>"
        "삼성증권 전자투표시스템 https://vote.samsungpop.com<br>"
        "전자투표 행사기간: 2026년 3월 1일 ~ 2026년 3월 10일",
        "이번 주주총회에서는 전자적 방법으로 의결권을 행사할 수 없습니다.<br>"
        "삼성증권 전자투표시스템 https://vote.samsungpop.com<br>"
        "전자투표 행사기간: 2026년 3월 1일 ~ 2026년 3월 10일",
        "전자투표제도의 관리업무를 삼성증권에 위탁하지 않기로 하였습니다.",
        "전자투표제도의 관리업무를 삼성증권에 위탁하지 아니하기로 하였습니다.",
        "전자투표제도의 관리업무를 삼성증권에 위탁할 수 없습니다.",
        "전자투표제도의 관리업무를 삼성증권에 위탁할 예정이 없습니다.",
        "전자투표제도의 관리업무를 대표이사에게 위임합니다.",
        "전자투표 관리기관: 대표이사",
        "전자투표 관리기관: 없음",
        "전자투표 관리기관: 미정",
        "이번 주주총회에서 전자투표제도를 도입하였습니다.<br>"
        "삼성증권 전자투표시스템 https://vote.samsungpop.com<br>"
        "주주총회일 10일 전(3월20일)부터 주주총회 전일(3월29일) "
        "행사 가능하지 않습니다.",
        "외부감사인의 의견은 적정입니다.",
        "외부회계법인인 삼일회계법인이 보고서를 제출했습니다.",
    ],
)
def test_unnamed_or_unasserted_stakeholders_are_not_inferred(value: str) -> None:
    assert extract_stakeholder_mentions(_soup(value)) == []


def test_similar_but_noncontract_section_label_is_ignored() -> None:
    soup = _soup(
        "외부감사인 선임 : 삼일회계법인 선임",
        label="5. 기타 참고사항",
    )

    assert extract_stakeholder_mentions(soup) == []


def test_correction_ancestor_is_ignored() -> None:
    soup = BeautifulSoup(
        """
        <table>
          <tr><td>정정항목</td><td>정정전</td><td>정정후</td></tr>
          <tr><td colspan="3"><table>
            <tr><td>5. 기타 투자판단에 참고할 사항</td></tr>
            <tr><td>외부감사인 선임 : 삼일회계법인 선임</td></tr>
          </table></td></tr>
        </table>
        """,
        "html.parser",
    )

    assert extract_stakeholder_mentions(soup) == []
