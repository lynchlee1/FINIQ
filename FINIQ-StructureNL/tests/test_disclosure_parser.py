from disclosure import parse_disclosure_xml


def test_parse_core_cb_fields_from_dart_xml():
    xml = """
    <DOCUMENT>
      <BODY>
        <SECTION-1>
          <P>전환사채권 발행결정</P>
          <TABLE>
            <TR><TD>1. 사채의 종류</TD><TD>회차</TD><TD>3</TD><TD>종류</TD><TD>무기명식 이권부 무보증 사모전환사채</TD></TR>
            <TR><TD>2. 사채의 권면(전자등록)총액 (원)</TD><TD>10,000,000,000</TD></TR>
            <TR><TD>6. 이자율에 관한 사항</TD><TD>표면이자율</TD><TD>1.0%</TD></TR>
            <TR><TD>만기이자율</TD><TD>3.0%</TD></TR>
            <TR><TD>7. 사채만기일</TD><TD>2029년 06월 30일</TD></TR>
            <TR><TD>9. 전환에 관한 사항</TD><TD>전환가액 (원/주)</TD><TD>5,000</TD></TR>
            <TR><TD>전환에 따라 발행할 주식</TD><TD>종류</TD><TD>기명식 보통주</TD></TR>
            <TR><TD>전환청구기간</TD><TD>시작일</TD><TD>2027.07.01</TD></TR>
            <TR><TD>종료일</TD><TD>2029.05.30</TD></TR>
            <TR><TD>10. 납입일</TD><TD>2026-06-30</TD></TR>
            <TR><TD>20. 옵션에 관한 사항</TD><TD>조기상환청구권 있음</TD></TR>
          </TABLE>
        </SECTION-1>
      </BODY>
    </DOCUMENT>
    """

    parsed = parse_disclosure_xml(xml, report_name="주요사항보고서(전환사채권 발행결정)")

    assert parsed["종류"] == "CB"
    assert parsed["회차"] == "3"
    assert parsed["발행금액(억)"] == 100.0
    assert parsed["표면이율"] == "1.0%"
    assert parsed["만기이율"] == "3.0%"
    assert parsed["만기일"] == "2029-06-30"
    assert parsed["전환가액(원)"] == 5000.0
    assert parsed["대상주식"] == "기명식 보통주"
    assert parsed["전환시작일"] == "2027-07-01"
    assert parsed["전환종료일"] == "2029-05-30"
    assert parsed["납입일"] == "2026-06-30"
    assert parsed["옵션사항"] == "조기상환청구권 있음"
    assert parsed["만기"] == "3.0년"


def test_skip_correction_table_and_parse_body_table():
    xml = """
    <DOCUMENT>
      <BODY>
        <CORRECTION>
          <TABLE><TR><TD>정 정 전</TD><TD>정 정 후</TD></TR></TABLE>
        </CORRECTION>
        <TABLE>
          <TR><TD>1. 사채의 종류</TD><TD>회차</TD><TD>1</TD></TR>
          <TR><TD>2. 사채의 권면총액 (원)</TD><TD>1,000,000,000</TD></TR>
        </TABLE>
      </BODY>
    </DOCUMENT>
    """

    parsed = parse_disclosure_xml(xml, report_name="주요사항보고서(신주인수권부사채권 발행결정)")

    assert parsed["종류"] == "BW"
    assert parsed["회차"] == "1"
    assert parsed["발행금액(억)"] == 10.0
