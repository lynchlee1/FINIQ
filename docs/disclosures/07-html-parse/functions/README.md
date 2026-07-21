### **1. Summary**

#### **기능 요약**
- 공시원문 변환의 메인 함수와 보조 함수가 맡는 기능을 구분해 설명한다.

#### **세부 설명**
- 메인 함수는 변환 실행, preview, 필터 후보 생성과 저장 결과 조회를 담당한다.
- 보조 함수는 HTML·표 해석, metadata·family 연결, warning과 최종 payload 구성을 담당한다.
- 단계 입출력과 공통 중단 규칙은 [공시원문 변환](../README.md), mode별 업무값은 각 mode README를 따른다.

### **2. Core**

#### **Feature**

**[Input Handling] 변환 실행 입력 준비 기능**

- **목적:** 메인 함수가 처리할 HTML 범위와 mode parser를 확정한다.
- `parse_disclosure_html_payload()`는 입력값을 검증하고 mode parser를 선택한다.
- 입력은 `input_directory/<year>/<acpt_no>.html`만 사용하며 `<year>`는 4자리 숫자 폴더다.
<br>

**[Input Handling] HTML·표 입력 변환 보조 함수 기능**
- **목적:** 모든 mode가 같은 문자와 표 구조를 사용하게 한다.
- byte 입력은 UTF-8로 읽고 복구 가능한 HTML DOM으로 만든다.
- 표의 `rowspan`과 `colspan`을 펼쳐 원래 위치와 실제 검색 위치를 함께 보존한다.
<br>

**[Input Handling] metadata 입력 보조 함수 기능**

- **목적:** 외부 정보와 correction family를 만들 입력의 출처를 고정한다.
- metadata는 지정된 `filtered.json`과 `compressed-external-html.json`에서만 읽는다.
- 파일명의 stem을 연결 key로 사용해 metadata index를 만든다.
<br>

**[Core Processing] 변환 실행 메인 함수 기능**

- **목적:** 확정한 HTML 전체를 같은 조건으로 변환해 하나의 결과로 저장한다.
- `parse_disclosure_html_payload()`는 HTML을 순서대로 처리한다.
- parser 결과에 metadata와 family를 연결하고 warning·error·집계를 포함한 JSON을 저장한다.
<br>

**[Core Processing] mode parser 메인 함수 기능**
- **목적:** 공시 유형별 업무값을 공통 record에 추가한다.
- `parse_bond_issuance()`, `parse_rights_issuance()`, `parse_shareholder_meeting()`, `parse_asset_transaction()`, `parse_security_transaction()` 중 선택한 mode의 함수만 실행한다.
- 각 함수는 공통 식별값과 표 구조에 mode별 값을 추가하며 상세 추출 규칙은 해당 mode README를 따른다.
- 직접 parser 결과의 `raw_tables`는 최종 JSON을 저장하기 전에 제거한다.
<br>

**[Core Processing] 값 추출 공통 보조 함수 기능**

- **목적:** 입력 표에서 결과 field를 찾고 변환할 때 같은 규칙을 사용한다.
- 행 이름 검색, 공백 정리와 숫자 변환은 공통 규칙을 사용한다.
<br>

**[Core Processing] metadata·family 연결 보조 함수 기능**

- **목적:** 정해진 외부값과 완성된 correction family만 parser 결과에 연결한다.
- title·회사명·시장·공시시각·본문 문서번호를 정해진 metadata 출처에서 연결한다.
- correction family가 완성된 경우에만 record에 family 참조를 추가하고 참조되는 family 본문을 최상위에 저장한다.
<br>

**[Core Processing] warning 보조 함수 기능**

- **목적:** 확인이 필요한 문제를 일관된 구조로 검증하고 집계한다.
- parser warning의 수준과 code를 검증한 뒤 공시별·수준별 건수를 집계한다.
<br>

**[Core Processing] payload 보조 함수 기능**

- **목적:** 검증된 변환 결과를 최종 저장 구조로 구성한다.
- 성공 record, family, warning, error, 필터 조건과 실행 집계를 최종 payload로 구성한다.
- 저장 결과에서 제외된 성공 record의 warning도 최상위 warning 집계에는 남긴다.
<br>

#### **Fallback**

- 없음.

#### **Shutdown**

**[Input Handling] 함수 입력 오류시 중단하기**
- **목적:** 메인 함수와 보조 함수가 해석할 수 없는 입력을 임의로 바꾸지 않는다.
- 필수 경로·mode·필터·실행 옵션이 없거나 형식이 다르면 메인 함수를 실패 처리한다.
- HTML·metadata 구조가 공통 입력 계약과 다르면 해당 결과를 만들지 않는다.
<br>

**[Core Processing] 보조 결과 구조 오류시 중단하기**

- **목적:** family나 warning 중간 결과가 공통 계약과 다르면 최종 payload를 만들지 않는다.
- family·warning 구조가 공통 계약과 다르면 해당 결과를 만들지 않는다.
- 세부 중단 조건은 [공시원문 변환의 Core Shutdown](../README.md#shutdown)을 따른다.
<br>

### **3. Serving**

#### **Feature**

**[Input Handling] 변환 취소 메인 함수 기능**
- **목적:** 실행 중인 변환을 취소한다.
- `cancel_disclosure_html_parse()`가 취소 요청을 전달한다.
<br>

**[Input Handling] 조회 메인 함수 기능**
- **목적:** 저장 전후 결과를 화면이나 파일로 확인한다.
- `build_parse_preview_payload()`는 변환 결과와 원문 표 미리보기를 만든다.
- `build_parse_filter_candidates_payload()`는 값별 개수와 접수번호 예시를 만든다.
- 다른 조회 함수는 사채 요약, 정정 내역과 Excel 결과를 만든다.

#### **Fallback**

- 없음.

#### **Shutdown**

- 없음.
