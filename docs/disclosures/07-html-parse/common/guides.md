# 공시원문 변환

공시 자동화 07단계에서 변환 유형을 고르고 목차 HTML을 구조화된 결과로 바꾼다.

## 목적

- 목차 HTML과 외부 metadata를 읽어 유형별 공시 결과를 저장한다. 화면에는 preview와 진단 정보도 제공한다.

## 핵심 기능

**`bond_issuance` · 사채발행파싱** — 상세 필드를 지원한다.

**`rights_issuance` · 유무상증자파싱** — 상세 필드를 지원한다. 공통 규칙과 유상·무상·혼합 결과는 [유무상증자 변환 문서](../modes/rights-issuance/README.md)에서 설명한다.

**`shareholder_meeting` · 주주총회파싱** — 원본 표 구조와 안건·선임·사업목적 변경 결과를 만든다.

**`asset_transaction` · 유무형자산거래파싱** — 공통 record와 원본 표 구조만 만든다.

**`security_transaction` · 발행증권거래파싱** — 공통 record와 원본 표 구조만 만든다.

### 연도별 parser 입력 수집

한 실행에서 읽을 HTML 범위를 강제된 저장 구조로 고정한다.

- `<data_root>/06-sections` 바로 아래에 있는 4자리 연도 폴더만 확인한다.

- `<data_root>/06-sections/<year>` 바로 아래의 `*.html`만 읽고 입력 루트, 이름이 다른 폴더, 더 깊은 하위 HTML은 제외한다.

### 공통 HTML 입력 변환

모든 mode가 같은 문자와 표 구조를 입력으로 사용하게 한다.

- HTML을 UTF-8로 읽고 병합된 표를 펼친다.

### 공통 parser 실행

변환한 HTML 입력에서 선택한 mode에 맞는 업무값을 추출한다.

- 선택한 mode parser를 실행하고 공통 식별값, 값별 상태와 warning 규칙을 모든 mode에 동일하게 적용한다.

- 메인 함수와 보조 함수가 맡는 역할은 공시원문 변환 함수에서 설명한다.

### 외부 metadata·family 연결

parser 결과에 붙일 외부값과 correction family를 어디서 읽는지 고정한다.

- metadata는 mode별 `filtered.json`과 `compressed-external-html.json`에서 읽는다.

- title·회사명·시장·공시시각·본문 문서번호를 정해진 출처에서 연결하고 완성된 family만 저장한다.

### 최종 결과 구성·저장

record·family·warning·error와 실행 집계를 JSON 한 파일에 저장한다.

- parser 결과에서 `raw_tables`를 제거한 뒤 metadata·family와 warning을 연결하고 필터를 적용한다.

- 최종 JSON에는 실행 mode와 입력 경로, 필터 조건, 집계, family, record, warning과 error를 기록한다.

- 외부 title은 함수 선언에 `title` 인자가 있는 parser에만 전달한다. 저장 record가 참조하는 family 본문은 최상위 `families`에 한 번만 모은다.

### warning 구조 일관성 확인

parser가 만든 warning 수준과 집계가 서로 일치하는지 최종 payload를 구성하기 전에 확인한다.

- `parse_warnings`와 수준별 목록이 일치하는지 확인한다.

## 사용과 화면

### Preview

저장하기 전에 원문과 변환 결과를 확인한다.

- 표가 길면 앞부분과 생략한 행 수만 보여 준다. 기본 건수는 [공시분석 공통 사양](../../common/reference.md)을 따른다.

- 표 제목은 원문 제목, 변환 결과 제목, 빈 값 순서로 선택한다.

### 필터 후보

결과를 거를 때 사용할 값과 공시를 미리 확인한다.

- 선택한 항목은 모든 입력에서 값별 개수와 접수번호 예시를 계산한다.

- 접수번호 예시를 줄여 보여 주지만 전체 개수는 모두 계산한다. 예시 범위는 [공시분석 공통 사양](../../common/reference.md)을 따른다.

### 변환 오류 표시 범위 제한

변환 실패 결과를 바꾸지 않고 화면에 전달할 예시 범위만 제한한다.

## 작업 안내

### parser 문제 조사하고 추출 규칙 고치기

#### 오류 재현하기

1. 제보받은 변환 유형과 접수번호를 확인한다.
2. 같은 입력으로 변환을 다시 실행한다.
3. [Reference](reference.md)에서 저장 경로를 확인하고 해당 접수번호의 결과와 안내를 찾는다.

#### 원본과 규칙 대조하기

1. 접수번호에 해당하는 06단계 HTML을 연다.
2. `bond_issuance`와 `rights_issuance`는 `resources/KIND/bond_issuance`, `resources/KIND/rights_issuance`에 있는 실제 KIND 파일과도 대조한다.
3. 기대한 값이 어느 표와 칸에 있는지 확인한다.
4. 현재 parser가 그 위치를 어떻게 찾는지 [mode 문서](../modes/README.md)의 변환 유형별 계약과 비교한다.

#### 수정하고 검증하기

1. [함수 Guide](../functions/guides.md)의 책임을 확인하고 해당 변환 유형의 추출 규칙을 고친다.
2. 실제 KIND 파일로 바뀐 결과를 확인한다.
3. test fixture와 합성 HTML로 기존 사례가 그대로 동작하는지 검사한다.
4. 변환을 다시 실행해 제보된 오류가 사라지고 다른 결과가 바뀌지 않았는지 확인한다.
