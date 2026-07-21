### **1. Summary**

#### **기능 요약**
- 목차 HTML과 외부 metadata를 읽어 유형별 공시 결과를 저장하고 preview와 진단 정보를 제공하는 기능이다.

#### **세부 설명**
- `/html-parse`에서 변환 유형을 선택해 parsing하거나 preview할 때 적용한다.
- 입력 HTML은 `<data_root>/06-sections/<year>/<acpt_no>.html`에서 읽으며 `<year>`는 4자리 숫자 폴더다. metadata는 `<data_root>/03-filter/<mode>/filtered.json`과 `<data_root>/04-external-html-download/<mode>/compressed-external-html.json`에서 읽는다.
- 결과는 `<data_root>/07-converted/<mode>/parsed-<mode>.json`에 저장한다. 원본 HTML은 수정하지 않는다.

```text
<data_root>/
├── 03-filter/<mode>/filtered.json
├── 04-external-html-download/<mode>/compressed-external-html.json
├── 06-sections/<year>/<acpt_no>.html
└── 07-converted/<mode>/parsed-<mode>.json
```

### **2. Core**

#### **Feature**

**[Input Handling] 연도별 parser 입력 수집 기능**
- **목적:** 한 실행에서 읽을 HTML 범위를 강제된 저장 구조로 고정한다.
- `<data_root>/06-sections` 바로 아래의 4자리 연도 폴더만 확인한다.
- 각 연도 폴더 바로 아래의 `*.html`만 읽고 입력 루트, 다른 이름의 폴더와 더 깊은 하위 HTML은 제외한다.
<br>

**[Input Handling] 공통 HTML 입력 변환 기능**

- **목적:** 모든 mode가 같은 문자와 표 구조를 입력으로 사용하게 한다.
- HTML을 UTF-8로 읽고 병합된 표를 펼친다.
- 병합 셀을 펼친 `positional_rows`는 열 위치를 보존한다. parser가 라벨을 찾는 `logical_rows`는 빈 칸과 같은 글이 연속된 칸을 제거하고, 그 결과가 빈 행도 제외한다.
<br>

**[Core Processing] 공통 parser 실행 기능**

- **목적:** 변환된 HTML 입력에서 선택한 mode의 업무값을 추출한다.
- 선택한 mode parser를 실행하고 공통 식별값, 값별 상태와 warning 규칙을 모든 mode에 동일하게 적용한다.
- 메인 함수와 보조 함수의 역할은 [공시원문 변환 함수](./functions/README.md)에서 설명한다.
<br>

**[Core Processing] 외부 metadata·family 연결 기능**
- **목적:** parser 결과에 붙는 외부값과 correction family의 출처를 고정한다.
- metadata는 mode별 `filtered.json`과 `compressed-external-html.json`에서 읽는다.
- title·회사명·시장·공시시각·본문 문서번호를 정해진 출처에서 연결하고 완성된 family만 저장한다.
<br>

**[Core Processing] 최종 결과 구성·저장 기능**
- **목적:** record·family·warning·error와 실행 집계를 하나의 JSON으로 저장한다.
- parser 결과에서 `raw_tables`를 제거한 뒤 metadata·family와 warning을 연결하고 필터를 적용한다.
- 최종 JSON에는 실행 mode와 입력 경로, 필터 조건, 집계, family, record, warning과 error를 기록한다.
<br>

**[Core Processing] warning 구조 일관성 확인 기능**

- **목적:** parser가 만든 warning의 수준과 집계가 서로 일치하는지 최종 payload 구성 전에 확인한다.
- 같은 warning 목록에 중복·빈 문장·수준 누락·복수 수준 지정이 없는지 확인한다.
- `parse_warnings`와 수준별 목록이 일치하는지 확인한다.
<br>

#### **Fallback**

**[Core Processing] 파일별 parsing 실패 제외 기능**

- **목적:** 요청에서 명시한 실패 정책에 따라 실패 파일을 제외하고 나머지 입력을 계속 처리한다.
- `skip_errors=True`일 때만 실패한 파일의 일부 결과와 warning을 버리고 다음 파일을 처리한다.
- `errors[]`에는 선택 순서와 전체 수, mode, 파일명에서 읽은 `acpt_no`, `error_type`, 오류 문장을 기록한다.
- 이 규칙은 파일 단위 parsing 실패에만 적용한다. metadata·family index, 최종 payload 또는 저장 실패에는 적용하지 않는다.
<br>

#### **Shutdown**

**[Input Handling] HTML 구조 오류시 변환 중단하기**
- **목적:** 문자·표 구조를 확정하지 못한 원문을 임의로 보정하지 않는다.
- UTF-8 decode가 실패하면 다른 문자셋을 시도하지 않고 오류로 처리한다.
- `rowspan`이나 `colspan` 값이 유효한 양의 정수가 아니면 실패 처리한다.
<br>

**[Input Handling] 실행 입력 오류시 중단하기**
- **목적:** 실행 범위와 실패 처리 정책이 불명확한 요청을 시작하지 않는다.
- `filter_blocks`가 목록이 아니면 실패 처리한다.
- `skip_errors`는 불리언으로 명시해야 하며 없거나 다른 형식이면 실패 처리한다.
- 확장자를 뺀 파일명이 같은 입력이 둘 이상이면 실행을 시작하지 않는다.
- metadata를 사용하려면 `filtered_metadata_path`와 `compressed_metadata_path`를 직접 지정해야 하며 인접 파일을 탐색하지 않는다.
- `filtered_metadata_path`를 직접 지정하면 선택한 모든 HTML의 `disclosed_at`이 `YYYY-MM-DD HH:MM` 형식이어야 한다.
- 압축 metadata의 각 record는 `metadata` 객체를 가져야 하며 family 구성원의 `disclosed_at`이 없으면 실패 처리한다.
<br>

**[Core Processing] warning 구조 오류시 중단하기**
- **목적:** 서로 모순되는 warning 수준과 집계를 저장하지 않는다.
- 같은 warning 목록의 중복·빈 문장·수준 누락·복수 수준 지정은 실패 처리한다.
- `parse_warnings`와 수준별 목록이 일치하지 않아도 보정하지 않고 실패 처리한다.
<br>

**[Core Processing] 파일별 parsing 실패시 전체 중단하기**

- **목적:** 파일 제외를 허용하지 않은 실행에서 일부 결과를 저장하지 않는다.
- `skip_errors=False`이면 parser signature 검사나 파일 하나의 parsing이 실패해도 전체 실행을 중단하고 결과를 저장하지 않는다.
<br>

**[Core Processing] 결과 구성 실패시 전체 중단하기**

- **목적:** 식별자나 family가 불완전한 payload를 만들지 않는다.
- 파일명의 확장자를 뺀 값이 중복되거나 metadata·family index 또는 최종 payload 구성이 실패하면 `skip_errors`와 관계없이 전체 실행을 중단한다.
<br>

**[Core Processing] 결과 저장 실패시 전체 중단하기**

- **목적:** 완성된 payload를 안전하게 저장하지 못하면 결과를 게시하지 않는다.
- 최종 payload 저장이 실패하면 `skip_errors`와 관계없이 전체 실행을 중단한다.
<br>

### **3. Serving**

#### **Feature**

**[Input Handling] Preview 기능**
- **목적:** 저장하기 전에 원문과 변환 결과를 확인한다.
- preview는 변환 결과와 원문 표 일부를 함께 보여 준다. 원본과 저장 결과는 바꾸지 않는다.
- 기본으로 3건을 보여 준다. 표가 길면 앞부분과 생략한 행 수만 보여 준다.
- 표 제목은 원문 제목, 변환 결과 제목, 빈 값 순서로 선택한다.
<br>

**[Input Handling] 필터 후보 기능**
- **목적:** 결과를 거를 때 사용할 값과 공시를 미리 확인한다.
- 선택한 항목의 값별 개수와 접수번호 예시를 모든 입력에서 계산한다.
- 접수번호는 값별로 20개만 보여 주지만 전체 개수는 모두 계산한다.
- 후보는 화면의 후속 필터 입력일 뿐 저장된 변환 결과를 바꾸지 않는다.
<br>

**[Input Handling] 변환 오류 표시 범위 제한 기능**
- **목적:** 변환 실패 결과를 바꾸지 않고 화면에 전달할 예시 범위만 제한한다.
- 공시 시각 오류는 종류별로 접수번호 10개만 보여 준다.
<br>

#### **Fallback**

**[Input Handling] 원문 표 preview 일부 실패 기능**

- **목적:** 원문 표를 보여 주지 못해도 변환 결과는 보여 준다.
- 변환 결과가 이미 만들어진 뒤 부가 원문 표를 찾거나 읽지 못한 경우에만 이유를 표시하고 변환 결과는 유지한다.
<br>

#### **Shutdown**

**[Input Handling] Serving 입력 오류시 중단하기**
- **목적:** 잘못된 진행 상태와 안내를 임의로 고치지 않는다.
- 진행 알림 간격이 정수가 아니거나 1보다 작으면 실패 처리한다.
- 안내 수준, 코드, 접수번호나 예시 형식이 잘못되면 실패 처리한다.
<br>

**[Input Handling] preview·후보 생성 실패시 중단하기**
- **목적:** 실패한 원문을 빼고 일부 결과만 보여 주지 않는다.
- Core preview 입력 원문 하나라도 읽거나 변환하지 못하면 실패 처리한다. 변환 완료 뒤 부가 원문 표만 표시하지 못하는 경우는 Serving Fallback이다.
- 필터 후보를 만들 때 원문 하나라도 실패하면 일부 후보를 반환하지 않는다.
