import os
import sys
import json
import urllib.request
from bs4 import BeautifulSoup
import re

sys.path.append("/Users/wonwoolee/Documents/GitHub/FINIQ/src")
from finiq.data_scraper.parse._snippets import dart_main_doc_no

kind_html_dir = "/Users/wonwoolee/Documents/GitHub/FINIQ/samples/kind_html"
kind_contents_dir = "/Users/wonwoolee/Documents/GitHub/FINIQ/samples/kind_html_contents"

files = os.listdir(kind_html_dir)
files = [f for f in files if f.endswith('.html')]

results = []

def get_dart_title(rcp_no):
    if not rcp_no:
        return None
    url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcp_no}"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req).read().decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        title = soup.find('title')
        if title:
            return title.text.strip()
    except Exception as e:
        pass
    return None

for filename in files:
    ext_path = os.path.join(kind_html_dir, filename)
    int_path = os.path.join(kind_contents_dir, filename)
    
    with open(ext_path, 'r', encoding='utf-8') as f:
        ext_html = f.read()
        ext_soup = BeautifulSoup(ext_html, 'html.parser')
    with open(int_path, 'r', encoding='utf-8') as f:
        int_soup = BeautifulSoup(f, 'html.parser')
        
    data = {}
    
    # 1. 외부 HTML 메타 정보
    # 기업명 및 종목코드
    h1 = ext_soup.find('h1', class_='ttl')
    data['기업명_및_종목코드'] = h1.text.strip() if h1 else ""
    
    # 공시 제목
    tempTitle = ext_soup.find('input', {'id': 'tempTitle'})
    data['공시_제목'] = tempTitle['value'] if tempTitle else ""
    
    # 문서 접수 번호
    acptNo = ext_soup.find('input', {'id': 'acptNo'})
    receipt_no = acptNo['value'] if acptNo else ""
    data['문서_접수_번호'] = receipt_no
    
    # DART 확인 (프로젝트의 dart_main_doc_no 함수 적용)
    dart_doc_no = dart_main_doc_no(ext_html)
    
    if dart_doc_no:
        dart_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={dart_doc_no}"
        dart_title = get_dart_title(dart_doc_no)
        data['DART_링크'] = dart_url
        data['DART_접수번호'] = dart_doc_no
        data['DART_제목확인'] = "일치" if dart_title and data['공시_제목'] in dart_title else f"불일치 (DART 제목: {dart_title})"
    else:
        data['DART_링크'] = "DART 번호 매핑 불가"
        data['DART_접수번호'] = ""
        data['DART_제목확인'] = "확인 불가"
    
    # 공시 제출 일자
    mainDoc = ext_soup.find('select', {'id': 'mainDoc'})
    if mainDoc:
        opt = mainDoc.find('option', selected=True)
        if not opt:
            opts = mainDoc.find_all('option')
            if len(opts) > 1:
                opt = opts[1]
        if opt:
            m = re.search(r'\((\d{4}\.\d{2}\.\d{2})\)', opt.text)
            if m:
                data['공시_제출_일자'] = m.group(1)
            else:
                data['공시_제출_일자'] = receipt_no[:8] if receipt_no else ""
    else:
        data['공시_제출_일자'] = receipt_no[:8] if receipt_no else ""
        
    # 공시 수정 내역 (기공시)
    orgDiscls = ext_soup.find('select', {'id': 'orgDisclsId'})
    mod_history = []
    if orgDiscls:
        for o in orgDiscls.find_all('option'):
            if o.get('value') and o.get('value') != "discls" and o.text.strip() != "기공시선택":
                mod_history.append(o.text.strip())
    data['공시_수정_내역'] = mod_history if mod_history else "없음"
    
    # 2. 내부 HTML 주주총회 핵심 데이터
    meeting_date = ""
    agendas = ""
    related_docs = []
    
    tds = int_soup.find_all('td')
    for i, td in enumerate(tds):
        text = td.text.strip()
        if "2. 주주총회 일자" in text:
            if i + 1 < len(tds):
                meeting_date = tds[i+1].text.strip()
        elif "1. 결의사항" in text:
            if i + 1 < len(tds):
                agendas = tds[i+1].text.strip().replace('\n', ' ').replace('\r', '')
                agendas = re.sub(r'\s+', ' ', agendas)
        elif "관련공시" in text:
            if i + 1 < len(tds):
                links = tds[i+1].find_all('a')
                for a in links:
                    doc_title = a.text.strip()
                    href = a.get('href', '')
                    m = re.search(r'acptno=(\d+)', href)
                    rno = m.group(1) if m else ""
                    related_docs.append({"제목": doc_title, "접수번호": rno})
                    
    data['주주총회_개최_일자'] = meeting_date
    data['안건_및_가결_여부'] = agendas
    data['관련공시_내역'] = related_docs
    
    # 3. 임원 선임 세부 내역
    executives = []
    headers = []
    for span in int_soup.find_all('span'):
        if "선임 세부내역" in span.text:
            table = span.find_next('table')
            if table:
                rows = table.find_all('tr')
                if rows:
                    header_tds = rows[0].find_all('td')
                    headers = [htd.text.strip() for htd in header_tds]
                    
                    for row in rows[1:]:
                        cols = row.find_all('td')
                        if len(cols) == len(headers):
                            exec_info = {}
                            for col_idx, col in enumerate(cols):
                                exec_info[headers[col_idx]] = col.text.strip()
                            
                            filtered_exec = {
                                "성명": exec_info.get("성명", ""),
                                "출생년월": exec_info.get("출생년월", ""),
                                "선임구분": exec_info.get("신규선임여부", "")
                            }
                            if filtered_exec["성명"]:
                                executives.append(filtered_exec)
    data['임원선임_세부내역'] = executives
    
    results.append(data)

with open("/Users/wonwoolee/Documents/GitHub/FINIQ/samples/parsed_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("Updated parser script generated parsed_results.json")
