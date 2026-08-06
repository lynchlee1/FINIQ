# 공시원문 변환 동작

## 자료 흐름

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

## 변환 유형

**`bond_issuance` · 사채발행파싱** — 상세 필드를 지원한다. 세부 규칙은 [사채발행 변환](../modes/bond-issuance/behavior.md)에서 설명한다.

**`rights_issuance` · 유무상증자파싱** — 상세 필드를 지원한다. 공통 규칙과 유상·무상·혼합 결과는 [유무상증자 변환 문서](../modes/rights-issuance/README.md)에서 설명한다.

**`shareholder_meeting` · 주주총회파싱** — 원본 표 구조와 안건·선임·사업목적 변경 결과를 만든다. 세부 규칙은 [주주총회 변환](../modes/shareholder-meeting/behavior.md)에서 설명한다.

**`asset_transaction` · 유무형자산거래파싱** — 공통 record와 원본 표 구조만 만든다.

**`security_transaction` · 발행증권거래파싱** — 공통 record와 원본 표 구조만 만든다.

마지막 두 유형의 공통 계약은 [원본 표 변환](../modes/raw-table/behavior.md), 함수별 책임은 [공시원문 변환 함수](../functions/behavior.md)에서 확인한다.

## 처리 계약

### 정상 동작

#### 연도별 parser 입력 수집

한 실행에서 읽을 HTML 범위를 강제된 저장 구조로 고정한다.
- `<data_root>/06-sections` 바로 아래에 있는 4자리 연도 폴더만 확인한다.
- `<data_root>/06-sections/<year>` 바로 아래의 `*.html`만 읽고 입력 루트, 이름이 다른 폴더, 더 깊은 하위 HTML은 제외한다.

#### 공통 HTML 입력 변환

모든 mode가 같은 문자와 표 구조를 입력으로 사용하게 한다.
- HTML을 UTF-8로 읽고 병합된 표를 펼친다.
- 병합 셀을 펼친 `positional_rows`는 열 위치를 보존한다. parser가 라벨을 찾는 `logical_rows`는 빈 칸과 같은 글이 연속된 칸을 제거하고 그 결과가 빈 행도 제외한다.

#### 공통 parser 실행

변환한 HTML 입력에서 선택한 mode에 맞는 업무값을 추출한다.
- 선택한 mode parser를 실행하고 공통 식별값, 값별 상태와 warning 규칙을 모든 mode에 동일하게 적용한다.
- 메인 함수와 보조 함수가 맡는 역할은 공시원문 변환 함수에서 설명한다.

#### 외부 metadata·family 연결

parser 결과에 붙일 외부값과 correction family를 어디서 읽는지 고정한다.
- metadata는 mode별 `filtered.json`과 `compressed-external-html.json`에서 읽는다.
- title·회사명·시장·공시시각·본문 문서번호를 정해진 출처에서 연결하고 완성된 family만 저장한다.

#### 최종 결과 구성·저장

record·family·warning·error와 실행 집계를 JSON 한 파일에 저장한다.
- parser 결과에서 `raw_tables`를 제거한 뒤 metadata·family와 warning을 연결하고 필터를 적용한다.
- 최종 JSON에는 실행 mode와 입력 경로, 필터 조건, 집계, family, record, warning과 error를 기록한다.
- `raw_tables`는 parser를 직접 분석할 때만 쓰며 저장 record에서는 제거한다. `raw_rows`는 만들지 않는다.
- `acpt_no`와 metadata 연결 key에는 `Path(file_path).stem` 전체를 사용한다. 밑줄을 기준으로 자르거나 숫자인지 검사해 다른 값으로 바꾸지 않는다.
- 저장 record에는 parser가 반환한 `title`, `acpt_no`, `상장구분`, 유형별 값이 남는다. metadata에 값이 있으면 `doc_no`, `disclosed_at`을 연결하고 완성한 family에는 `family_id`, `current_sequence`, `family_member_count`를 기록한다.
- 외부 title은 함수 선언에 `title` 인자가 있는 parser에만 전달한다. 저장 record가 참조하는 family 본문은 최상위 `families`에 한 번만 모은다.
- `bond_issuance`와 `rights_issuance`는 metadata에 회사명이 있을 때 `corp_name`도 저장한다.
- parser와 Web workflow는 `rcept_no`, `source_file`, 빈 `correction_families`를 만들지 않는다.
- 입력 루트는 최상위 `input_directory`에 한 번만 기록한다. record·warning·error·preview에는 파일 경로나 파일명을 넣지 않고 `acpt_no`로 원본을 식별한다. `source_preview`도 바깥 record에 있는 `acpt_no`를 반복하지 않는다.

#### warning 구조 일관성 확인

parser가 만든 warning 수준과 집계가 서로 일치하는지 최종 payload를 구성하기 전에 확인한다.
- 같은 warning 목록에 중복·빈 문장·수준 누락·복수 수준 지정이 없는지 확인한다.
- `parse_warnings`와 수준별 목록이 일치하는지 확인한다.

## 화면과 서비스 계약

### 정상 동작

#### Preview

저장하기 전에 원문과 변환 결과를 확인한다.
- preview는 변환 결과와 원문 표 일부를 함께 보여 준다. 원본과 저장 결과는 바꾸지 않는다.
- 표가 길면 앞부분과 생략한 행 수만 보여 준다. 기본 건수는 [공시분석 공통 동작](../../common/behavior.md)을 따른다.
- 표 제목은 원문 제목, 변환 결과 제목, 빈 값 순서로 선택한다.

#### 필터 후보

결과를 거를 때 사용할 값과 공시를 미리 확인한다.
- 선택한 항목은 모든 입력에서 값별 개수와 접수번호 예시를 계산한다.
- 접수번호 예시를 줄여 보여 주지만 전체 개수는 모두 계산한다. 예시 범위는 [공시분석 공통 동작](../../common/behavior.md)을 따른다.
- 후보는 화면에서 이어서 쓸 필터 입력일 뿐, 저장한 변환 결과는 바꾸지 않는다.

#### 변환 오류 표시 범위 제한

변환 실패 결과를 바꾸지 않고 화면에 전달할 예시 범위만 제한한다.
- 공시 시각 오류 예시는 [공시분석 공통 동작](../../common/behavior.md)을 따른다.
