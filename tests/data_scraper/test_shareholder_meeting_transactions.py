"""Golden reductions for explicitly named shareholder-meeting transactions."""

from __future__ import annotations

from typing import Any

import pytest
from bs4 import BeautifulSoup

from finiq.data_scraper.parse.domain.shareholder_meeting_stakeholders import (
    extract_transaction_mentions,
)
from finiq.data_scraper.parse.domain.shareholder_meeting import (
    extract_shareholder_meeting_details,
)


def _soup(
    value: str,
    *,
    label: str = "5. 기타 투자판단에 참고할 사항",
) -> BeautifulSoup:
    return BeautifulSoup(
        f"""
        <html><body><table>
          <tr><td>{label}</td></tr>
          <tr><td>{value}</td></tr>
        </table></body></html>
        """,
        "html.parser",
    )


def _agenda(
    *,
    agenda_ref: str,
    title: str,
    remarks: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    raw_text = " | ".join(value for value in (title, remarks) if value)
    return {
        "agenda_ref": agenda_ref,
        "title": title,
        "remarks": remarks,
        "status": status,
        "evidence": {
            "section_title": "주주총회 안건 세부내역",
            "table_index": 2,
            "row_index": 3,
            "field": "회의목적사항",
            "raw_text": raw_text,
        },
    }


def test_20260316000503_expands_only_explicit_share_transfer_parties() -> None:
    raw_text = (
        "- 상기 의안은 당사의 최대주주인 이니셜 1호 투자조합 외 2인"
        "(㈜비덴트, 강지연)이 ㈜와비사비홀딩스와 2025년 12월 24일 "
        "체결한 주식매매계약에 따른 경영권 양도를 목적으로 합니다."
    )

    mentions = extract_transaction_mentions(_soup(raw_text), [], [], "notice")

    assert [
        (mention["name"], mention["entity_type"], mention["relationship_type"])
        for mention in mentions
    ] == [
        ("이니셜 1호 투자조합", "organization", "transferor_of"),
        ("㈜비덴트", "organization", "transferor_of"),
        ("강지연", "person", "transferor_of"),
        ("이니셜 1호 투자조합", "organization", "shareholder_of"),
        ("㈜와비사비홀딩스", "organization", "transferee_of"),
    ]
    assert all(
        mention["target_ref"] == "@reporting_company"
        and mention["evidence"]["raw_text"] == raw_text
        for mention in mentions
    )
    shareholder = next(
        mention for mention in mentions if mention["relationship_type"] == "shareholder_of"
    )
    assert shareholder["attributes"] == {
        "disclosure_phase": "notice",
        "maximum": True,
        "is_current": True,
    }
    assert not any("외 2인" in mention["name"] for mention in mentions)


def test_20230315002241_extracts_directed_share_transfer_contract() -> None:
    mentions = extract_transaction_mentions(
        _soup(
            "- 2022년 7월 19일 최대주주인 SK스퀘어(주)는 보유주식 "
            "7,600,649주(총 발행주식의 28.4%)를 제이앤더블유파트너스(주)에게 "
            "양도하는 주식양수도 계약을 체결하였습니다."
        ),
        [],
        [],
        "notice",
    )

    assert [(mention["name"], mention["relationship_type"]) for mention in mentions] == [
        ("SK스퀘어(주)", "transferor_of"),
        ("SK스퀘어(주)", "shareholder_of"),
        ("제이앤더블유파트너스(주)", "transferee_of"),
    ]
    assert all(mention["entity_type"] == "organization" for mention in mentions)
    historical_shareholder = next(
        mention for mention in mentions if mention["relationship_type"] == "shareholder_of"
    )
    assert historical_shareholder["attributes"] == {
        "disclosure_phase": "notice",
        "maximum": True,
    }


def test_explicit_person_transfer_parties_are_typed_as_people() -> None:
    mentions = extract_transaction_mentions(
        _soup(
            "홍길동은 보유 주식 10,000주를 김민수에게 양도하는 "
            "주식매매계약을 체결하였습니다."
        ),
        [],
        [],
        "notice",
    )

    assert [(mention["name"], mention["entity_type"]) for mention in mentions] == [
        ("홍길동", "person"),
        ("김민수", "person"),
    ]


def test_20260119000577_extracts_only_labelled_third_party_allottee() -> None:
    mentions = extract_transaction_mentions(
        _soup(
            "1) 신주 발행 방식<br>"
            "- 상법 및 당사 정관에 따른 제3자배정 방식<br>"
            "2) 배정대상자<br>"
            "- 당사 최대주주인 헤일로 마이크로일렉트로닉스 "
            "인터내셔널 코퍼레이션<br>"
            "3) 발행목적<br>"
            "- 재무구조개선 및 운영자금 확보"
        ),
        [],
        [],
        "notice",
    )

    assert mentions == [
        {
            "name": "헤일로 마이크로일렉트로닉스 인터내셔널 코퍼레이션",
            "entity_type": "organization",
            "relationship_type": "proposed_allottee_of",
            "target_ref": "@reporting_company",
            "attributes": {"disclosure_phase": "notice"},
            "evidence": {
                "section_title": "기타 투자판단에 참고할 사항",
                "table_index": 0,
                "row_index": 1,
                "field": "기타 투자판단에 참고할 사항",
                "raw_text": (
                    "2) 배정대상자 - 당사 최대주주인 헤일로 "
                    "마이크로일렉트로닉스 인터내셔널 코퍼레이션"
                ),
            },
        },
        {
            "name": "헤일로 마이크로일렉트로닉스 인터내셔널 코퍼레이션",
            "entity_type": "organization",
            "relationship_type": "shareholder_of",
            "target_ref": "@reporting_company",
            "attributes": {
                "disclosure_phase": "notice",
                "maximum": True,
                "is_current": True,
            },
            "evidence": {
                "section_title": "기타 투자판단에 참고할 사항",
                "table_index": 0,
                "row_index": 1,
                "field": "기타 투자판단에 참고할 사항",
                "raw_text": (
                    "2) 배정대상자 - 당사 최대주주인 헤일로 "
                    "마이크로일렉트로닉스 인터내셔널 코퍼레이션"
                ),
            },
        },
    ]


def test_20260407001104_and_20260225000875_extract_named_merger_targets() -> None:
    agenda_records = [
        _agenda(
            agenda_ref="agenda:0",
            title="합병 승인의 건",
            remarks="당사가 파라택시스코리아를 흡수합병",
        )
    ]
    business_changes = [
        {
            "category": "사업목적 추가",
            "reason": "(주)기프트레터 합병 및 사업확장을 위한 사업목적 추가",
        },
        {
            "category": "사업목적 변경",
            "reason": "(주)기프트레터 합병 및 사업확장을 위한 사업목적 추가",
        },
    ]

    mentions = extract_transaction_mentions(
        _soup("-"), agenda_records, business_changes, "notice"
    )

    assert [(mention["name"], mention["relationship_type"]) for mention in mentions] == [
        ("파라택시스코리아", "merger_target_of"),
        ("(주)기프트레터", "merger_target_of"),
    ]
    assert all(
        mention["entity_type"] == "organization"
        and mention["target_ref"] == "@reporting_company"
        and mention["attributes"] == {"disclosure_phase": "notice"}
        and mention["evidence"]["raw_text"]
        for mention in mentions
    )
    assert mentions[0]["evidence"]["field"] == "비고"
    assert mentions[1]["evidence"] == {
        "section_title": "사업목적 변경 세부내역",
        "field": "이유",
        "raw_text": "(주)기프트레터 합병 및 사업확장을 위한 사업목적 추가",
    }


def test_20160808_absorption_merger_excludes_legal_role_qualifier() -> None:
    """Reduced from KIND disclosures 20160808000455 and 20160809000430."""
    agenda_records = [
        _agenda(
            agenda_ref="agenda:0",
            title="합병 승인의 건",
            remarks=(
                "코스닥시장 상장법인인 당사가 비상장법인인 "
                "에이피우주항공 주식회사를 흡수합병"
            ),
        )
    ]

    mentions = extract_transaction_mentions(
        _soup("-"), agenda_records, [], "notice"
    )

    assert [
        (mention["name"], mention["relationship_type"])
        for mention in mentions
    ] == [("에이피우주항공 주식회사", "merger_target_of")]


def test_unnamed_legal_role_is_not_a_merger_target() -> None:
    agenda_records = [
        _agenda(
            agenda_ref="agenda:0",
            title="합병 승인의 건",
            remarks="당사가 비상장법인을 흡수합병",
        )
    ]

    mentions = extract_transaction_mentions(
        _soup("-"), agenda_records, [], "notice"
    )

    assert not any(
        mention["relationship_type"] == "merger_target_of"
        for mention in mentions
    )


def test_explicit_agenda_merger_counterparty_grammars() -> None:
    """Reduced from 20080901000350, 20101126000109, and 20081203000362."""
    agenda_records = [
        _agenda(
            agenda_ref="agenda:0",
            title="(주)리메텍과의 합병계약 승인의 건",
        ),
        _agenda(
            agenda_ref="agenda:1",
            title="피합병 법인 : (주)포비스네트웍",
        ),
        _agenda(
            agenda_ref="agenda:2",
            title="(주)플렉스컴 흡수합병계약 승인의 건",
        ),
    ]

    mentions = extract_transaction_mentions(
        _soup("-"), agenda_records, [], "notice"
    )

    assert [
        mention["name"]
        for mention in mentions
        if mention["relationship_type"] == "merger_target_of"
    ] == ["(주)리메텍", "(주)포비스네트웍", "(주)플렉스컴"]


def test_labelled_merger_target_stops_before_result_delimiters() -> None:
    """Reduced from KIND 20101126000109, 20151027000272,
    20151116000269, and 20161028000156.
    """
    agenda_records = [
        _agenda(
            agenda_ref="agenda:0",
            title=(
                "제1호의안 : 합병계약서 승인의 건 --> 원안대로 승인 가결 "
                "(피합병 법인 : (주)포비스네트웍)"
            ),
        ),
        _agenda(
            agenda_ref="agenda:1",
            title=(
                "제1호 의안: 합병 승인의 건 (존속법인:포인트아이㈜, "
                "피합병법인: ㈜아이오케이컴퍼니) ▶ 원안대로 승인"
            ),
        ),
        _agenda(
            agenda_ref="agenda:2",
            title="(2) 피합병법인 : 주식회사 칸메드 ▶ 원안대로 승인",
        ),
        _agenda(
            agenda_ref="agenda:3",
            title=(
                "제1호 의안: 합병 승인의 건 - 존속법인:㈜ 에스피지, "
                "소멸법인:㈜ 성신 => 원안대로 승인"
            ),
        ),
    ]

    mentions = extract_transaction_mentions(
        _soup("-"), agenda_records, [], "result"
    )

    assert [
        mention["name"]
        for mention in mentions
        if mention["relationship_type"] == "merger_target_of"
    ] == [
        "(주)포비스네트웍",
        "㈜아이오케이컴퍼니",
        "주식회사 칸메드",
        "㈜ 성신",
    ]


def test_two_party_merger_requires_exact_reporting_company_side() -> None:
    """Reduced from KIND disclosure 20081126000092."""
    agenda_records = [
        _agenda(
            agenda_ref="agenda:0",
            title="동화기업(주)와 동화케미칼(주)의 합병계약 승인의 건",
        )
    ]

    matched = extract_transaction_mentions(
        _soup("-"),
        agenda_records,
        [],
        "notice",
        reporting_company_name="동화기업",
    )
    unmatched = extract_transaction_mentions(
        _soup("-"),
        agenda_records,
        [],
        "notice",
        reporting_company_name="제3의회사",
    )

    assert [
        mention["name"]
        for mention in matched
        if mention["relationship_type"] == "merger_target_of"
    ] == ["동화케미칼(주)"]
    assert not any(
        mention["relationship_type"] == "merger_target_of"
        for mention in unmatched
    )


def test_two_party_prefix_markers_consume_the_genitive_outside_the_name() -> None:
    """Reduced from KIND disclosures 20260120000626 and 20260220001282."""
    mentions = extract_transaction_mentions(
        _soup("-"),
        [
            _agenda(
                agenda_ref="agenda:0",
                title="(주)소룩스와 (주)아리바이오의 합병 승인의 건",
            )
        ],
        [],
        "notice",
        reporting_company_name="소룩스",
    )

    assert [
        mention["name"]
        for mention in mentions
        if mention["relationship_type"] == "merger_target_of"
    ] == ["(주)아리바이오"]

    particle_mentions = extract_transaction_mentions(
        _soup("-"),
        [
            _agenda(
                agenda_ref="agenda:0",
                title="(주)알파와 (주)베타와의 합병계약 승인의 건",
            )
        ],
        [],
        "notice",
        reporting_company_name="(주)알파",
    )
    assert [
        mention["name"]
        for mention in particle_mentions
        if mention["relationship_type"] == "merger_target_of"
    ] == ["(주)베타"]


@pytest.mark.parametrize(
    "title",
    [
        "합병계약 승인의 건",
        "피합병법인: 미정",
        "(주)알파와 (주)베타 및 (주)감마의 합병계약 승인의 건",
    ],
)
def test_ambiguous_or_unnamed_agenda_mergers_create_no_target(title: str) -> None:
    mentions = extract_transaction_mentions(
        _soup("-"),
        [_agenda(agenda_ref="agenda:0", title=title)],
        [],
        "notice",
        reporting_company_name="(주)알파",
    )

    assert not any(
        mention["relationship_type"] == "merger_target_of"
        for mention in mentions
    )


@pytest.mark.parametrize(
    "title",
    [
        "(주)계열회사와의 합병계약 승인의 건",
        "(주)소규모와의 합병계약 승인의 건",
        "(주)20210727와의 합병계약 승인의 건",
        "피합병 법인 : (주)알파, (주)베타",
        "피합병 법인 : (주)알파 및 (주)베타",
        "피합병 법인 : (주)알파 외 2개사",
        "피합병 법인 : (주)알파 등 3개사",
        "피합병 법인 : (주)알파와 관계회사",
        "(주)알파 외 2개사와의 합병계약 승인의 건",
        "(주)알파 등 3개사 흡수합병계약 승인의 건",
        "당사가 (주)알파, (주)베타를 흡수합병",
        "당사가 (주)알파와 (주)베타를 흡수합병",
        "당사가 알파와 베타를 흡수합병",
        "당사가 (주)알파와 관계회사를 흡수합병",
    ],
)
def test_agenda_merger_rejects_generic_or_ambiguous_marked_targets(
    title: str,
) -> None:
    mentions = extract_transaction_mentions(
        _soup("-"),
        [_agenda(agenda_ref="agenda:0", title=title)],
        [],
        "notice",
        reporting_company_name="(주)알파",
    )

    assert not any(
        mention["relationship_type"] == "merger_target_of"
        for mention in mentions
    )


def test_20251209000323_links_named_stake_transactions_to_each_agenda() -> None:
    agenda_records = [
        _agenda(
            agenda_ref="agenda:0",
            title="제1호의안: 자회사 핑장소재기술유한공사 지분 양도의 건",
            status="passed",
        ),
        _agenda(
            agenda_ref="agenda:1",
            title=(
                "제2호의안: 제3자배정 유상증자를 통한 "
                "GeneVision AI Technology Holdings Ltd. 지분 100% 인수의 건"
            ),
            status="passed",
        ),
    ]

    mentions = extract_transaction_mentions(_soup("-"), agenda_records, [], "result")

    assert [
        (
            mention["name"],
            mention["relationship_type"],
            mention["target_ref"],
            mention["attributes"],
        )
        for mention in mentions
    ] == [
        (
            "핑장소재기술유한공사",
            "divestment_target_of",
            "agenda:0",
            {"disclosure_phase": "result", "outcome": "passed"},
        ),
        (
            "GeneVision AI Technology Holdings Ltd.",
            "acquisition_target_of",
            "agenda:1",
            {"disclosure_phase": "result", "outcome": "passed"},
        ),
    ]
    assert all(mention["entity_type"] == "organization" for mention in mentions)


def test_unnamed_and_generic_transaction_language_is_not_inferred() -> None:
    mentions = extract_transaction_mentions(
        _soup(
            "본 건 임시주주총회는 최대주주변경을 수반하는 주식양수도계약에 "
            "따라 매수인 요청 안건 상정을 위해 개최 예정이었습니다."
        ),
        [
            _agenda(agenda_ref="agenda:0", title="M&A 추진 승인의 건"),
            _agenda(agenda_ref="agenda:1", title="합병계약 승인의 건"),
            _agenda(agenda_ref="agenda:2", title="지분 인수의 건"),
        ],
        [
            {"category": "사업목적 추가", "reason": "합병에 따른 사업목적 추가"},
            {"category": "사업목적 추가", "reason": "사업부문 합병 및 경영효율성 제고"},
            {
                "category": "사업목적 추가",
                "reason": "사업확장을 위한 합병계약 승인",
                "content": "가상회사 합병",
            },
            {
                "category": "사업목적 추가",
                "reason": "사업확장을 위한 (주)가상회사 합병",
            },
        ],
        "notice",
    )

    assert mentions == []


def test_allottee_label_requires_explicit_third_party_allocation_context() -> None:
    mentions = extract_transaction_mentions(
        _soup(
            "임직원 주식보상 계획<br>"
            "배정대상자: 우리사주조합<br>"
            "부여 수량은 추후 결정"
        ),
        [],
        [],
        "notice",
    )

    assert mentions == []


def test_generic_subsidiary_roles_are_not_transaction_entities() -> None:
    mentions = extract_transaction_mentions(
        BeautifulSoup("<html><body></body></html>", "html.parser"),
        [
            _agenda(
                agenda_ref="agenda:0",
                title="당사가 완전자회사인 종속회사를 흡수합병하는 건",
            ),
            _agenda(
                agenda_ref="agenda:1",
                title="당사 종속회사 지분 인수의 건",
            ),
        ],
        [],
        "notice",
    )

    assert mentions == []


def test_business_reason_excludes_legal_merger_modifier_from_party_name() -> None:
    mentions = extract_transaction_mentions(
        BeautifulSoup("<html><body></body></html>", "html.parser"),
        [],
        [
            {
                "reason": "(주)제이와이피퍼블리싱 소규모 합병에 따른 사업목적 추가",
                "evidence": {
                    "section_title": "사업목적 변경 세부내역",
                    "table_index": 1,
                    "row_index": 2,
                    "field": "이유",
                    "raw_text": "(주)제이와이피퍼블리싱 소규모 합병에 따른 사업목적 추가",
                },
            }
        ],
        "notice",
    )

    assert [(mention["name"], mention["relationship_type"]) for mention in mentions] == [
        ("(주)제이와이피퍼블리싱", "merger_target_of")
    ]


@pytest.mark.parametrize(
    ("reason", "expected_name"),
    [
        (
            "(주)제니스월드 흡수합병에 따른 사업목적 추가",
            "(주)제니스월드",
        ),
        (
            "종속회사(일진전자산업) 흡수합병에 따른 사업목적 추가",
            "일진전자산업",
        ),
        (
            "주식회사 한국글로벌제약 흡수합병간 사업목적 승계를 위한 추가",
            "주식회사 한국글로벌제약",
        ),
        (
            "흡수합병한 (주)선진지주의 사업목적을 추가",
            "(주)선진지주",
        ),
        (
            "- 옐로우캡 흡수합병에 따른 택배업 관련 사업목적 추가",
            "옐로우캡",
        ),
        (
            "(주)알파와의 흡수합병에 따른 사업목적 추가",
            "(주)알파",
        ),
        (
            "주식회사 도원산업과 소규모합병에 따른 사업목적 추가",
            "주식회사 도원산업",
        ),
        (
            "(주)케이지티지와의 소규모합병에 따른 사업목적 추가",
            "(주)케이지티지",
        ),
        (
            "2021.07.27 합병 예정인 (주)씨엠코와의 합병에 의한 사업 목적 추가",
            "(주)씨엠코",
        ),
        (
            "KD엠텍과의 합병에 의한 사업목적 추가",
            "KD엠텍",
        ),
        (
            "이엔에이치와의 합병으로 인한 사업목적 추가",
            "이엔에이치",
        ),
        (
            "평전궤도(주)와의 합병및 철스크랩 판매에 따른 업종추가 등",
            "평전궤도(주)",
        ),
        (
            "합병으로 인한 피합병회사(주식회사 대성마이맥)의 목적사업 추가",
            "주식회사 대성마이맥",
        ),
        (
            "합병으로인한 피합병회사(주식회사대성마이맥)의 목적사업 추가",
            "주식회사대성마이맥",
        ),
        (
            "현 당사는 아트시스템과 소규모 합병 중에 있으며, "
            "아트시스템의 사업 목적 추가 하였습니다.",
            "아트시스템",
        ),
        (
            "디에스티(주)와의 합병 대비",
            "디에스티(주)",
        ),
        (
            "피합병법인 (주)원익테라세미콘 정관상의 사업목적 반영",
            "(주)원익테라세미콘",
        ),
        (
            "'18년 10월 피합병회사(씨제이디지털뮤직)의 사업목적사항 추가",
            "씨제이디지털뮤직",
        ),
        (
            "2월 16일 합병완료된 (구)PK풍력의 사업목적을 추가",
            "PK풍력",
        ),
        (
            "합병 후 소멸법인인 주식회사 비투엔의 업무 영위를 위한 정관 변경",
            "주식회사 비투엔",
        ),
        (
            "합병 후 소멸법인 (주)에스에이티의 업무 영위를 위한 정관 변경",
            "(주)에스에이티",
        ),
        (
            "소멸법인 (주)미래자원엠엘의 정관일체의 반영",
            "(주)미래자원엠엘",
        ),
        (
            "소멸법인(주) 정다운의 정관 일체의 반영",
            "(주) 정다운",
        ),
        (
            "소멸법인 켐트로스의 정관일체의 반영",
            "켐트로스",
        ),
        (
            "(주)인터파크INT와 (주)인터파크투어의 합병 결정에 따라 "
            "투어부문의 사업목적사항을 (주)인터파크INT 사업목적에 추가함.",
            "(주)인터파크투어",
        ),
    ],
)
def test_business_reason_extracts_explicit_absorption_merger_party(
    reason: str,
    expected_name: str,
) -> None:
    """Reduced from 20260311001268/20260330000405 and 20260324000861."""
    mentions = extract_transaction_mentions(
        BeautifulSoup("<html><body></body></html>", "html.parser"),
        [],
        [{"category": "사업목적 추가", "reason": reason}],
        "notice",
    )

    assert [(mention["name"], mention["relationship_type"]) for mention in mentions] == [
        (expected_name, "merger_target_of")
    ]
    assert mentions[0]["evidence"]["raw_text"] == reason


@pytest.mark.parametrize(
    "reason",
    [
        "계열회사 흡수합병에 따른 사업목적추가",
        "종속회사(완전자회사) 흡수합병에 따른 사업목적 추가",
        "영업부문 흡수합병에 따른 사업목적 추가",
        "완전자회사A 흡수합병에 따른 사업목적 추가",
        "신설회사 흡수합병에 따른 사업목적 추가",
        "소멸회사 흡수합병에 따른 사업목적 추가",
        "피흡수회사 흡수합병에 따른 사업목적 추가",
        "대상회사 흡수합병에 따른 사업목적 추가",
        "사업회사 흡수합병에 따른 사업목적 추가",
        "존속회사 흡수합병에 따른 사업목적 추가",
        "관계사 흡수합병에 따른 사업목적 추가",
        "계열사 흡수합병에 따른 사업목적 추가",
        "종속법인 흡수합병에 따른 사업목적 추가",
        "소규모 합병으로 인한 사업목적 추가",
        "2021.07.27 합병으로 인한 사업목적 추가",
        "관계기업과의 합병으로 인한 사업목적 추가",
        "사업부와의 합병으로 인한 사업목적 추가",
        "2021년7월27일과의 합병으로 인한 사업목적 추가",
        "20210727과의 합병으로 인한 사업목적 추가",
        "(주)알파와 (주)베타 합병에 따른 사업목적 추가",
        "(주)알파와 (주)베타의 합병 결정에 따라 사업목적 추가",
        "(주)알파와 (주)베타의 합병 결정에 따라 (주)감마 사업목적에 추가함",
        "(주)알파 흡수합병을 하지 않기로 한 사업목적 변경",
        "(주)알파 흡수합병 무산 후 사업목적 추가",
        "(주)알파 흡수합병 백지화에 따른 사업목적 변경",
        "(주)알파 흡수합병 검토가 아닌 단순 사업제휴 관련 사업목적 추가",
        "주식회사 도원산업과 소규모합병이 아닌 단순 사업제휴 관련 사업목적 추가",
        "KD엠텍과의 합병 계획을 폐기하여 사업목적 추가",
        "(주)계열회사와의 합병으로 인한 사업목적 추가",
        "대상회사(주)와의 합병으로 인한 사업목적 추가",
        "(주)소규모와의 합병으로 인한 사업목적 추가",
        "피합병회사(관계회사, 주식회사 정상법인)의 목적사업 추가",
        "피합병회사(주식회사 알파 외 1개사)의 목적사업 추가",
        "피합병회사(주식회사 알파 및 주식회사 베타)의 목적사업 추가",
        "피합병회사(주식회사 알파, 기타 주식회사 베타)의 목적사업 추가",
        "피합병회사(주식회사 알파 등 2개사)의 목적사업 추가",
        "피합병회사(주식회사 알파를 포함한 2개사)의 목적사업 추가",
        "피합병회사(주식회사 알파 포함 2개사)의 목적사업 추가",
        "피합병회사(주식회사 알파를 포함한 다수)의 목적사업 추가",
        "피합병회사(주식회사 알파 포함한 다수)의 목적사업 추가",
        "피합병회사(주식회사 알파 외다수)의 목적사업 추가",
        "피합병회사(주식회사 알파 등다수)의 목적사업 추가",
        "피합병회사(주식회사 알파 2개 법인)의 목적사업 추가",
        "피합병회사(주식회사 알파 2개 회사)의 목적사업 추가",
        "피합병회사(주식회사 알파 외 다수)의 목적사업 추가",
        "피합병회사(주식회사 알파 등)의 목적사업 추가",
        "소멸법인 정관 일체 반영",
        "소멸법인 (주)알파의 정관 일체 반영을 폐기",
        "피합병회사(주식회사 알파)의 목적사업 추가를 취소",
        "(주)20210727와의 합병으로 인한 사업목적 추가",
        "(주)2021년7월27일과의 합병으로 인한 사업목적 추가",
        "기업과의 합병으로 인한 사업목적 추가",
        "(주)기업과의 합병으로 인한 사업목적 추가",
        "(주)알파와 (주) 알파의 합병 결정에 따라 (주)알파 사업목적에 추가함",
        "(주)알파와 ㈜알파의 합병 결정에 따라 (주)알파 사업목적에 추가함",
        "(주)알파와 알파(주)의 합병 결정에 따라 (주)알파 사업목적에 추가함",
        "주식회사 알파와 (주)알파의 합병 결정에 따라 ㈜알파 사업목적에 추가함",
        "타기업과의 합병으로 인한 사업목적 추가",
        "상대기업과의 합병으로 인한 사업목적 추가",
        "일반기업과의 합병으로 인한 사업목적 추가",
        "해당기업과의 합병으로 인한 사업목적 추가",
    ],
)
def test_business_reason_does_not_entityize_ambiguous_or_negated_merger(
    reason: str,
) -> None:
    """The first case is reduced from 20110318000850."""
    mentions = extract_transaction_mentions(
        BeautifulSoup("<html><body></body></html>", "html.parser"),
        [],
        [{"reason": reason}],
        "notice",
    )

    assert mentions == []


def test_business_reason_splits_only_an_explicit_absorbed_company_roster() -> None:
    reason = (
        "합병으로 인한 피합병회사(주식회사 한우리열린교육, "
        "주식회사 강남대성기숙학원)의 목적사업 추가"
    )

    nested_marker_reason = (
        "합병으로 인한 피합병회사((주)알파, (주)베타)의 목적사업 추가"
    )
    nested_mentions = extract_transaction_mentions(
        BeautifulSoup("<html><body></body></html>", "html.parser"),
        [],
        [{"reason": nested_marker_reason}],
        "notice",
    )

    assert [mention["name"] for mention in nested_mentions] == [
        "(주)알파",
        "(주)베타",
    ]

    mentions = extract_transaction_mentions(
        BeautifulSoup("<html><body></body></html>", "html.parser"),
        [],
        [{"reason": reason}],
        "notice",
    )

    assert [mention["name"] for mention in mentions] == [
        "주식회사 한우리열린교육",
        "주식회사 강남대성기숙학원",
    ]
    assert all(
        mention["relationship_type"] == "merger_target_of"
        and mention["evidence"]["raw_text"] == reason
        for mention in mentions
    )


@pytest.mark.parametrize(
    ("reason", "expected_name"),
    [
        (
            "(주)알파와 (주)베타의 합병 결정에 따라 "
            "(주)알파 사업목적에 추가함",
            "(주)베타",
        ),
        (
            "(주)알파와 (주)베타의 합병 결정에 따라 "
            "(주)베타 사업목적에 추가함",
            "(주)알파",
        ),
        (
            "(주)알파와 주식회사 베타의 합병 결정에 따라 "
            "㈜알파 사업목적에 추가함",
            "주식회사 베타",
        ),
    ],
)
def test_business_reason_uses_the_repeated_merger_recipient_for_direction(
    reason: str,
    expected_name: str,
) -> None:
    mentions = extract_transaction_mentions(
        BeautifulSoup("<html><body></body></html>", "html.parser"),
        [],
        [{"reason": reason}],
        "notice",
    )

    assert [mention["name"] for mention in mentions] == [expected_name]


def test_empty_or_unconfirmed_allottee_labels_do_not_create_entities() -> None:
    mentions = extract_transaction_mentions(
        _soup(
            "2) 배정대상자<br>"
            "3) 발행목적<br>"
            "- 재무구조 개선<br>"
            "배정대상자: 미정<br>"
            "배정대상자는 추후 이사회에서 확정"
        ),
        [],
        [],
        "notice",
    )

    assert mentions == []


def test_transaction_reference_text_requires_the_exact_section_contract() -> None:
    mentions = extract_transaction_mentions(
        _soup(
            "최대주주인 홍길동은 보유주식을 김민수에게 양도하는 "
            "주식양수도계약을 체결했습니다.",
            label="5. 기타 참고사항",
        ),
        [],
        [],
        "notice",
    )

    assert mentions == []


def test_transaction_mentions_join_the_document_local_contract() -> None:
    result = extract_shareholder_meeting_details(
        """
        <html><body>
          <table>
            <tr><th>번호</th><th>회의목적사항</th><th>가결여부</th></tr>
            <tr>
              <td>1</td>
              <td>GeneVision AI Technology Holdings Ltd. 지분 100% 인수의 건</td>
              <td>가결</td>
            </tr>
          </table>
          <table>
            <tr><td>5. 기타 투자판단에 참고할 사항</td></tr>
            <tr><td>
              최대주주인 홍길동은 보유 주식을 미래홀딩스(주)에게 양도하는
              주식매매계약을 체결하였습니다.
            </td></tr>
          </table>
          <span>사업목적 변경 세부내역</span>
          <table>
            <tr><th>구분</th><th>내용</th><th>이유</th></tr>
            <tr><td>사업목적 추가</td><td>신사업</td><td>(주)기프트레터 합병 및 사업확장</td></tr>
          </table>
        </body></html>
        """,
        mode="RESULT",
    )

    entities = {
        entity["entity_ref"]: (entity["name"], entity["entity_type"])
        for entity in result["entities"]
    }
    transaction_relations = {
        (
            entities[relation["source_ref"]],
            relation["relationship_type"],
            relation["target_ref"],
        )
        for relation in result["relationships"]
        if relation["relationship_type"]
        in {
            "transferor_of",
            "transferee_of",
            "shareholder_of",
            "merger_target_of",
            "acquisition_target_of",
        }
    }
    assert transaction_relations == {
        (("홍길동", "person"), "transferor_of", "@reporting_company"),
        (("홍길동", "person"), "shareholder_of", "@reporting_company"),
        (("미래홀딩스(주)", "organization"), "transferee_of", "@reporting_company"),
        (("(주)기프트레터", "organization"), "merger_target_of", "@reporting_company"),
        (
            ("GeneVision AI Technology Holdings Ltd.", "organization"),
            "acquisition_target_of",
            "agenda:0",
        ),
    }
    assert all(
        relation["evidence"]["raw_text"]
        for relation in result["relationships"]
        if relation["relationship_type"] in {item[1] for item in transaction_relations}
    )
