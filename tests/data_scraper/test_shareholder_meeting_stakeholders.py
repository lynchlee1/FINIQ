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


def test_20260310001873_extracts_explicit_voting_manager() -> None:
    mentions = extract_stakeholder_mentions(
        _soup(
            """
            1. 보고사항 : 제27기 감사보고, 영업보고, 내부회계관리제도 운영실태보고<br>
            2. 당사는 상법 제368조의4에 따라 금번 제27기 정기주주총회에 전자투표제도를 활용할 예정이며 이 제도의 관리업무는 KB국민은행에 위탁할 예정입니다.<br>
            3. 제9호 의안은 조건에 따라 자동 폐기됩니다.
            """
        )
    )

    assert len(mentions) == 1
    assert mentions[0] == {
        "name": "KB국민은행",
        "entity_type": "organization",
        "relationship_type": "electronic_voting_manager_for",
        "target_ref": "@meeting",
        "attributes": {
            "action": "entrusted",
            "delegation_status": "planned",
            "services": ["electronic_voting"],
        },
        "evidence": {
            "section_title": "기타 투자판단에 참고할 사항",
            "table_index": 0,
            "row_index": 1,
            "field": "기타 투자판단에 참고할 사항",
            "raw_text": (
                "2. 당사는 상법 제368조의4에 따라 금번 제27기 정기주주총회에 "
                "전자투표제도를 활용할 예정이며 이 제도의 관리업무는 KB국민은행에 "
                "위탁할 예정입니다."
            ),
        },
    }


@pytest.mark.parametrize(
    ("value", "name", "services"),
    [
        (
            "당사는 제26기 정기주주총회에서 전자투표제도 및 "
            "전자위임장제도를 도입하였습니다.<br>"
            "- 전자투표 시스템 : 삼성증권 전자투표시스템 "
            "(http://vote.samsungpop.com)<br>"
            "- 전자투표 행사기간 : 2026년 3월 17일 ~ 3월 26일",
            "삼성증권",
            ["electronic_voting", "electronic_proxy"],
        ),
        (
            "당 회사는 제41기 정기주주총회에서 주주가 총회에 출석하지 않고 "
            "전자적 방법으로 의결권을 행사할 수 있습니다.<br>"
            "http://vote.samsungpop.com(삼성증권 전자투표시스템)<br>"
            "전자투표 행사기간: 2026.03.21 ~ 2026.03.30",
            "삼성증권",
            ["electronic_voting"],
        ),
        (
            "당사는 제14기 정기주주총회에서 전자투표제도를 도입하였습니다.<br>"
            "- 전자투표 시스템 : 한국예탁결제원 전자투표시스템<br>"
            "- 인터넷주소 : https://evote.ksd.or.kr<br>"
            "- 전자투표 행사기간 : 2026년 3월 19일 ~ 3월 30일",
            "한국예탁결제원",
            ["electronic_voting"],
        ),
        (
            "당사는 제35기 정기주주총회에서 전자투표제도를 활용하기로 "
            "하였습니다.<br>"
            "전자투표ㆍ전자위임장권유시스템(삼성증권)<br>"
            "인터넷 주소: http://vote.samsungpop.com<br>"
            "전자투표 행사: 2026년 3월 21일 ~ 2026년 3월 30일",
            "삼성증권",
            ["electronic_voting", "electronic_proxy"],
        ),
        (
            "당사는 전자투표제도를 이번 주주총회에서 활용하기로 "
            "결의하였습니다.<br>"
            "전자투표 시스템 인터넷 주소: https://vote.samsungpop.com<br>"
            "전자투표 행사기간: 2026년 3월 17일 ~ 2026년 3월 26일<br>"
            "삼성증권 전자투표서비스 이용약관 제13조",
            "삼성증권",
            ["electronic_voting"],
        ),
        (
            "상기 주주총회에서 전자적 방법으로 의결권을 행사할 수 있음"
            "(전자투표제도 도입)<br>"
            "http://evote.ksd.or.kr(한국예탁결제원 전자투표시스템)<br>"
            "전자투표 행사기간: 2018년 3월 20일 ～ 3월 29일",
            "한국예탁결제원",
            ["electronic_voting"],
        ),
        (
            "당 회사는 이번 주주총회에서 전자적 방법으로 의결권을 행사할 수 "
            "있음(전자투표제도 도입)<br>"
            "http://vote.samsungpop.com(삼성증권 전자투표시스템)<br>"
            "주주총회일 10일 전(3월20일)부터 주주총회 전일"
            "(3월29일 17시까지_공휴일 포함)<br>행사 가능.",
            "삼성증권",
            ["electronic_voting"],
        ),
    ],
)
def test_named_voting_system_provider_requires_current_meeting_use_context(
    value: str,
    name: str,
    services: list[str],
) -> None:
    """Reduced from current receipts and historical 20180227000264/20200313002660."""
    mentions = extract_stakeholder_mentions(_soup(value))

    assert [(mention["name"], mention["relationship_type"]) for mention in mentions] == [
        (name, "electronic_voting_system_provider_for")
    ]
    assert mentions[0]["attributes"] == {
        "usage_status": "active",
        "services": services,
    }


def test_voting_manager_takes_precedence_over_same_provider_mention() -> None:
    """Reduced from 20260304000686; one source assertion must not make two edges."""
    mentions = extract_stakeholder_mentions(
        _soup(
            "이번 주주총회에 한국예탁결제원 전자투표시스템을 활용하며 "
            "전자투표 행사기간은 2026년 3월 10일부터 3월 19일까지입니다.<br>"
            "이 제도의 관리업무를 한국예탁결제원에 위탁하였습니다."
        )
    )

    assert [(mention["name"], mention["relationship_type"]) for mention in mentions] == [
        ("한국예탁결제원", "electronic_voting_manager_for")
    ]


@pytest.mark.parametrize(
    ("value", "name", "action"),
    [
        (
            "금번 주주총회에서 전자투표로 의결권 행사가 가능합니다.<br>"
            "전자투표 관리기관: 한국예탁결제원",
            "한국예탁결제원",
            "declared",
        ),
        (
            "우리회사는 전자투표제도를 삼성증권에 위임하였으며 "
            "https://vote.samsungpop.com에서 의결권을 행사할 수 있습니다.",
            "삼성증권",
            "entrusted",
        ),
    ],
)
def test_direct_voting_manager_grammar_binds_the_named_institution(
    value: str,
    name: str,
    action: str,
) -> None:
    """Reduced from manager receipts 20260306000892 and 20260309000498."""
    mentions = extract_stakeholder_mentions(_soup(value))

    assert [(mention["name"], mention["attributes"]["action"]) for mention in mentions] == [
        (name, action)
    ]


def test_adjacent_clauses_can_jointly_name_voting_manager() -> None:
    mentions = extract_stakeholder_mentions(
        _soup(
            "이번 주주총회에 전자투표제도를 활용합니다.<br>"
            "이 제도의 관리업무는 한국예탁결제원에 위탁합니다."
        )
    )

    assert [(mention["name"], mention["relationship_type"]) for mention in mentions] == [
        ("한국예탁결제원", "electronic_voting_manager_for")
    ]


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


def test_20260312000748_extracts_nearest_unsuffixed_korean_manager_name() -> None:
    mentions = extract_stakeholder_mentions(
        _soup(
            "- 당사는 상법 제368조의4에 따라 전자투표제도를 활용할 예정이며 "
            "이 제도의 관리업무는 IR큐더스에 위탁할 예정입니다."
        )
    )

    assert [(mention["name"], mention["attributes"]) for mention in mentions] == [
        (
            "IR큐더스",
            {
                "action": "entrusted",
                "delegation_status": "planned",
                "services": ["electronic_voting"],
            },
        )
    ]


def test_named_external_auditor_opinion_is_a_current_role_declaration() -> None:
    mentions = extract_stakeholder_mentions(
        _soup("외부감사인(이정회계법인)의 감사의견은 적정입니다.")
    )

    assert [(mention["name"], mention["attributes"]) for mention in mentions] == [
        ("이정회계법인", {"state": "current"})
    ]


def test_raw_institution_spelling_is_preserved_without_correction() -> None:
    mentions = extract_stakeholder_mentions(
        _soup("전자투표제도의 관리업무를 케이비국민은헁에 위탁합니다.")
    )

    assert [mention["name"] for mention in mentions] == ["케이비국민은헁"]


def test_active_proxy_and_voting_delegation_records_both_services() -> None:
    mentions = extract_stakeholder_mentions(
        _soup(
            "전자투표제도와 전자위임장제도의 관리업무를 "
            "한국예탁결제원에 위탁하였습니다."
        )
    )

    assert mentions[0]["attributes"] == {
        "action": "entrusted",
        "delegation_status": "active",
        "services": ["electronic_voting", "electronic_proxy"],
    }


def test_line_wrapped_joint_delegation_keeps_both_services() -> None:
    mentions = extract_stakeholder_mentions(
        _soup(
            "전자투표제도와 관련 법령에 따른<br>"
            "전자위임장 권유제도를 활용하기로 결의하였고<br>"
            "이 두 제도의 관리업무를 한국예탁결제원에 위탁할 예정입니다."
        )
    )

    assert mentions[0]["attributes"] == {
        "action": "entrusted",
        "delegation_status": "planned",
        "services": ["electronic_voting", "electronic_proxy"],
    }


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


def test_completed_voting_delegation_does_not_capture_next_unrelated_delegation() -> None:
    """Reduced from 20260305000989 and 20260310000763."""
    mentions = extract_stakeholder_mentions(
        _soup(
            "전자투표제도의 관리업무는 한국예탁결제원에 위탁할 예정입니다.<br>"
            "주주총회 변경 결정 권한을 대표이사에게 위임합니다."
        )
    )

    assert [(mention["name"], mention["relationship_type"]) for mention in mentions] == [
        ("한국예탁결제원", "electronic_voting_manager_for")
    ]


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
