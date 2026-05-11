from finiq_marketDesk.analytics.disclosure_groups import (
    DISCLOSURE_GROUP_OTHER,
    classify_disclosure_group,
    default_disclosure_group_rows,
    disclosure_group_marker_style,
    parse_disclosure_group_rules,
)


def test_default_disclosure_group_rows_include_shareholder_meeting() -> None:
    rows = default_disclosure_group_rows()

    shareholder_meeting_row = next(row for row in rows if row["group"] == "주주총회")
    assert shareholder_meeting_row["keywords"] == "주주총회"


def test_classify_disclosure_group_matches_shareholder_meeting_titles() -> None:
    assert classify_disclosure_group("주주총회소집결의") == "주주총회"
    assert classify_disclosure_group("정기주주총회결과") == "주주총회"
    assert classify_disclosure_group("기타 공시") == DISCLOSURE_GROUP_OTHER


def test_parse_disclosure_group_rules_preserves_known_group_marker_style() -> None:
    rules = parse_disclosure_group_rules(
        [
            {
                "group": "주주총회",
                "color": "#dc2626",
                "keywords": "주주총회\n정기주주총회",
            }
        ]
    )

    assert len(rules) == 1
    assert rules[0].color == "#dc2626"
    assert rules[0].keywords == ("주주총회", "정기주주총회")
    assert disclosure_group_marker_style("주주총회", rules) == {
        "shape": "square",
        "position": "inBar",
    }


def test_classify_disclosure_group_supports_nested_and_or_expressions() -> None:
    rules = parse_disclosure_group_rules(
        [
            {
                "group": "복합이벤트",
                "color": "#2563eb",
                "keywords": "(유상증자 and 결정) or (전환사채 and 발행)",
            }
        ]
    )

    assert classify_disclosure_group("유상증자 결정", rules) == "복합이벤트"
    assert classify_disclosure_group("전환사채 발행", rules) == "복합이벤트"
    assert classify_disclosure_group("유상증자 검토", rules) == DISCLOSURE_GROUP_OTHER


def test_classify_disclosure_group_supports_not_expressions() -> None:
    rules = parse_disclosure_group_rules(
        [
            {
                "group": "확정유상증자",
                "color": "#2563eb",
                "keywords": "유상증자 and not 철회 and not 정정",
            }
        ]
    )

    assert classify_disclosure_group("유상증자 결정", rules) == "확정유상증자"
    assert classify_disclosure_group("유상증자 결정 철회", rules) == DISCLOSURE_GROUP_OTHER
    assert classify_disclosure_group("유상증자 정정 결정", rules) == DISCLOSURE_GROUP_OTHER


def test_classify_disclosure_group_supports_nested_not_with_parentheses() -> None:
    rules = parse_disclosure_group_rules(
        [
            {
                "group": "정상사채발행",
                "color": "#2563eb",
                "keywords": "전환사채 and not (철회 or 정정)",
            }
        ]
    )

    assert classify_disclosure_group("전환사채 발행 결정", rules) == "정상사채발행"
    assert classify_disclosure_group("전환사채 발행 정정", rules) == DISCLOSURE_GROUP_OTHER
    assert classify_disclosure_group("전환사채 발행 철회", rules) == DISCLOSURE_GROUP_OTHER


def test_parse_disclosure_group_rules_splits_commas_only_at_top_level() -> None:
    rules = parse_disclosure_group_rules(
        [
            {
                "group": "복합이벤트",
                "color": "#2563eb",
                "keywords": "(유상증자 and 결정), (전환사채 and 발행) or 교환사채발행",
            }
        ]
    )

    assert rules[0].keywords == (
        "(유상증자 and 결정)",
        "(전환사채 and 발행) or 교환사채발행",
    )
