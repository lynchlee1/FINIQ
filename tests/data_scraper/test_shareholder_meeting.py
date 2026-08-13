import os
import json
import pytest
from bs4 import BeautifulSoup
from finiq.data_scraper.parse.domain.shareholder_meeting import parse_shareholder_meeting

KIND_HTML_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "samples", "kind_html"
)
KIND_CONTENTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "samples", "kind_html_contents"
)
GOLDEN_SOURCE_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "fixtures",
    "shareholder_meeting",
    "golden",
    "sources",
)

def test_parse_shareholder_meeting_all_samples() -> None:
    """기존 샘플 중 주주총회 공시를 성공적으로 파싱하고 안건이 리스트로 반환되는지 확인한다."""
    if not os.path.exists(KIND_HTML_DIR) or not os.path.exists(KIND_CONTENTS_DIR):
        pytest.skip("Sample directories not found")

    files = [f for f in os.listdir(KIND_HTML_DIR) if f.endswith(".html")]
    assert len(files) > 0, "No sample files found"

    parsed_files = 0
    for filename in files:
        ext_path = os.path.join(KIND_HTML_DIR, filename)
        int_path = os.path.join(KIND_CONTENTS_DIR, filename)

        with open(ext_path, "r", encoding="utf-8") as f:
            ext_html = f.read()
        with open(int_path, "r", encoding="utf-8") as f:
            int_html = f.read()

        soup = BeautifulSoup(ext_html, "html.parser")
        title_input = soup.find("input", attrs={"name": "tempTitle"})
        title = str(title_input.get("value") or "") if title_input else ""
        clean_title = title.replace(" ", "")
        if not (
            "주주총회소집결의" in clean_title
            or "주주총회소집공고" in clean_title
            or "주주총회결과" in clean_title
        ):
            continue

        # Parse should not raise any exceptions
        result = parse_shareholder_meeting(ext_html, int_html)
        parsed_files += 1

        # Basic validations
        assert "metadata" in result
        assert "mode" in result
        assert result["mode"] in ["NOTICE", "RESULT"]
        
        # Agendas should be a list of strings
        assert "agendas" in result
        assert isinstance(result["agendas"], list)
        for agenda in result["agendas"]:
            assert isinstance(agenda, str)
            assert agenda.strip() == agenda  # No leading/trailing spaces
        
        # Elections should be a list of dictionaries
        assert "elections" in result
        assert isinstance(result["elections"], list)

    assert parsed_files > 0, "No shareholder meeting sample files found"

def test_parse_shareholder_meeting_unsupported_title() -> None:
    """지원하지 않는 공시 제목이 들어올 경우 ValueError를 발생시키는지 확인한다."""
    mock_ext_html = '''
    <html>
        <body>
            <h1 class="ttl">가짜회사 (000000)</h1>
            <input name="tempTitle" value="[가짜회사] 분기보고서 (2025.01)"/>
            <input name="acptNo" value="20250101000000"/>
        </body>
    </html>
    '''
    mock_int_html = '<html><body><table></table></body></html>'
    
    with pytest.raises(ValueError, match="Unexpected shareholder meeting disclosure type"):
        parse_shareholder_meeting(mock_ext_html, mock_int_html)

def test_parse_shareholder_meeting_edge_case() -> None:
    """안건이 제대로 추출되는지 엣지 케이스를 테스트한다."""
    mock_ext_html = '''
    <html>
        <body>
            <h1 class="ttl">테스트 (000000)</h1>
            <input name="tempTitle" value="[테스트] 주주총회소집결의"/>
            <input name="acptNo" value="20250101000000"/>
        </body>
    </html>
    '''
    mock_int_html = '''
    <html>
        <body>
            <table>
                <tr>
                    <td>1. 일시</td>
                    <td>2025년 3월 15일</td>
                </tr>
                <tr>
                    <td>3. 의안 주요내용</td>
                    <td>
                        제1호 의안 : 이사 선임의 건<br/>
                        제2호 의안 : 정관 일부 변경의 건<br/>
                    </td>
                </tr>
            </table>
        </body>
    </html>
    '''
    
    result = parse_shareholder_meeting(mock_ext_html, mock_int_html)
    assert result["mode"] == "NOTICE"
    assert result["agendas"] == ["제1호 의안 : 이사 선임의 건", "제2호 의안 : 정관 일부 변경의 건"]


def test_parse_shareholder_meeting_extracts_detailed_sections() -> None:
    source_dir = os.path.join(GOLDEN_SOURCE_DIR, "20180102000452")
    ext_path = os.path.join(source_dir, "external.html")
    int_path = os.path.join(source_dir, "internal.html")

    with open(ext_path, "r", encoding="utf-8") as f:
        ext_html = f.read()
    with open(int_path, "r", encoding="utf-8") as f:
        int_html = f.read()

    result = parse_shareholder_meeting(ext_html, int_html)

    assert result["agenda_items"][0] == "제1-1호의 의안 : 사내이사 박화영 선임의 건"
    assert len(result["director_elections"]) == 4
    assert result["director_elections"][0]["성명"] == "박화영"
    assert result["director_elections"][0]["주요경력(현직포함)"]
    assert len(result["outside_director_elections"]) == 2
    assert result["outside_director_elections"][0]["이사 등으로 재직 중인 다른 법인명(직위)"] == "주식회사 엔에스엔(감사)"
    assert result["auditor_elections"] == []
    business_changes = [
        {key: value for key, value in change.items() if key != "evidence"}
        for change in result["business_purpose_changes"]
    ]
    assert business_changes == [
        {"category": "사업목적 추가", "reason": "-", "content": "-"},
        {
            "category": "사업목적 변경",
            "reason": "사업목적 추가 및 재배열",
            "before": result["business_purpose_changes"][1]["before"],
            "after": result["business_purpose_changes"][1]["after"],
        },
        {"category": "사업목적 삭제", "reason": "-", "content": "-"},
    ]
    assert all(
        change["evidence"]["section_title"] == "사업목적 변경 세부내역"
        and change["evidence"]["table_index"] >= 0
        and change["evidence"]["row_index"] >= 1
        for change in result["business_purpose_changes"]
    )
    assert "의약품 제조 및 판매업" in result["business_purpose_changes"][1]["before"]
    assert "의약품의 제조, 매매 및 소분업" in result["business_purpose_changes"][1]["after"]


def test_parse_shareholder_meeting_extracts_auditor_details() -> None:
    source_dir = os.path.join(GOLDEN_SOURCE_DIR, "20180102000266")
    ext_path = os.path.join(source_dir, "external.html")
    int_path = os.path.join(source_dir, "internal.html")

    with open(ext_path, "r", encoding="utf-8") as f:
        ext_html = f.read()
    with open(int_path, "r", encoding="utf-8") as f:
        int_html = f.read()

    result = parse_shareholder_meeting(ext_html, int_html)

    assert len(result["auditor_elections"]) == 1
    assert result["auditor_elections"][0]["성명"] == "안성일"
    assert result["auditor_elections"][0]["상근여부"] == "상근"

import random

def generate_test_cases():
    cases = []
    random.seed(42)  # For deterministic tests
    for i in range(200):
        mode = "NOTICE" if i % 2 == 0 else "RESULT"
        title = f"[테스트] 주주총회소집결의 {i}" if mode == "NOTICE" else f"[테스트] 주주총회결과 {i}"
        
        agenda_target_text = "3. 의안 주요내용" if mode == "NOTICE" else "1. 결의사항"
        
        ext_html = f'''
        <html>
            <body>
                <h1 class="ttl">테스트회사 (000{i:03d})</h1>
                <input name="tempTitle" value="{title}"/>
                <input name="acptNo" value="20250101000{i:03d}"/>
            </body>
        </html>
        '''
        
        spaces = " " * random.randint(1, 5)
        brs = "<br/>\n" * random.randint(1, 3)
        extra_tags_start = "<span><b>" if random.choice([True, False]) else "<div>"
        extra_tags_end = "</b></span>" if extra_tags_start == "<span><b>" else "</div>"
        
        agenda_1_title = f"제1호 의안 : 테스트 안건 {i}-1"
        agenda_1_result = "-> 원안 가결" if random.choice([True, False]) else ""
        agenda_1_full = f"{agenda_1_title} {agenda_1_result}".strip()
        
        agenda_2_title = f"제2호 의안 : 테스트 안건 {i}-2"
        agenda_2_result = "-> 원안 부결" if random.choice([True, False]) else ""
        agenda_2_full = f"{agenda_2_title} {agenda_2_result}".strip()
        
        expected_list = [agenda_1_full, agenda_2_full]
        
        agenda_html = f'''
            {extra_tags_start}{agenda_1_title}{extra_tags_end}{spaces}{brs}
            {spaces}{agenda_1_result}{brs if agenda_1_result else ""}
            {extra_tags_start}{agenda_2_title}{extra_tags_end}{brs}
            {spaces}{agenda_2_result}
        '''
        
        int_html = f'''
        <html>
            <body>
                <table border="{random.randint(0,1)}">
                    <tr>
                        <td>{spaces}{agenda_target_text}{spaces}</td>
                        <td>{agenda_html}</td>
                    </tr>
                </table>
            </body>
        </html>
        '''
        
        cases.append((ext_html, int_html, mode, expected_list))
    return cases

@pytest.mark.parametrize("ext_html, int_html, expected_mode, expected_agendas", generate_test_cases())
def test_parse_shareholder_meeting_generated(ext_html, int_html, expected_mode, expected_agendas) -> None:
    """사용자 요청에 따라 파서의 안정성을 검증하기 위해 200개의 자동 생성 테스트 케이스를 통과시킨다."""
    result = parse_shareholder_meeting(ext_html, int_html)
    assert result["mode"] == expected_mode
    assert result["agendas"] == expected_agendas
