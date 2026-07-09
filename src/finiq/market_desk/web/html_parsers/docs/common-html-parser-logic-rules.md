# 공통 로직 규칙
최종 업데이트: 2026-07-09

### 문서 작성 규칙
1. **이번 패치에서 명시적으로 수정 대상으로 지정되지 않은 문서 내 내용은 변경하지 않는다.**
- 오탈자, 표현 개선, 구조 정리처럼 사소해 보이는 수정이라도 사용자의 명시적 요청이 없는 한 임의로 고치지 않는다. 
- 수정이 필요하다고 판단되는 경우에는 먼저 변경 사유와 범위를 설명하고 사용자 승인을 받은 뒤 진행한다.

### 프로젝트 규칙
1. **Fallback을 새로 만들기 전에는 반드시 사용자에게 승인을 요청한다.**
- 사용자의 명시적 허가 없이 예외사항을 임의로 추측하거나, 기존 요구사항을 우회하는 대체 로직을 생성하지 않는다. 
- 예외 처리가 필요하다고 판단되는 경우에는 그 이유와 예상 영향을 설명한 뒤 사용자 확인을 받은 후 진행한다.

### 외부 HTML 연결 규칙
1. **기본 규칙**
- 외부 HTML 데이터를 이용한 필드 보강은 `filtered.json`과 `compressed-external-html.json`을 유일한 SoC로 사용한다.
- 절대로 `kind_disclosure_html_manifest.json`에 의존하지 않는다.
- `filtered.json`·`compressed-external-html.json`는 입력 디렉토리보다 한 단계 위에 있는 부모 디렉토리에 존재한다. 
- DART 공시코드인 `rcept_no`는 저장하거나 사용하지 않는다.
2. **공시 제목**
- 공시 제목은 외부 소스로부터 주입한 `filtered.json.title` 단일 필드를 유일한 SoC로 사용한다.
  - `title_display`·`title_attr`을 사용한 fallback 로직을 만들지 않는다.
3. **공시 코드**
- `doc_no`는 `selected_main_doc_no` 단일 필드만 사용한다. 
  - `item.doc_no`를 사용한 fallback 로직을 만들지 않는다.
- `acpt_no`는 입력 HTML 파일명을 유일한 SoC로 사용한다.
- `filtered.json`·`compressed-external-html.json`의 `acpt_no`는 메타데이터를 연결할 key로만 사용하며, record의 `acpt_no`에 영향을 주지 않는다. 
4. **기업명**
- `corp_name`은 `filtered.json`의 `company_name`을 유일한 SoC로 사용한다.
  - `compressed-external-html.json`·`header`를 사용한 fallback 로직을 만들지 않는다.
5. **정정공시**
- 정정공시 내 제목은 `compressed-external-html.json`의 `mainDoc.text`를 `title`에 저장한다.
  - `title_display`·`title_base`·`metadata.title`·`record.title`을 사용한 fallback 로직을 만들지 않는다.
- 정정공시 묶음 내 각 제목들은 `compressed-external-html.json`의 `mainDoc.text`를 유일한 SoC로 사용한다.
  - `filtered.json`의 `company_key`·`title_base`·`title_display`·`title`을 사용한 fallback 로직을 만들지 않는다.

### 내부 HTML 파싱 규칙
1. **기본 규칙**
- `rowspan`·`colspan`에 잘못된 값이 있는 경우 조용히 보정하지 않고 실패로 드러낸다.
- 원문 미리보기는 원본 HTML 파일을 직접 읽어 테이블 preview를 만든다.
- change-log 비교 대상 필드는 공시 유형별 `CHANGE_LOG_COMPARISON_FIELDS`에 명시한다.
2. **디코딩**
- 디코딩은 utf-8, cp949, euc-kr, utf-8(errors="replace") 순서로 시도한다.
- lxml.html.HTMLParser(recover=True)로 깨진 HTML을 복구한다.
### 공시원문 변환
- `상장구분`은 `filtered.json`의 `market`을 사용한다.
- 원문에서 추출한 회사명·대상명은 법인 형태나 주식 종류 표현을 임의 제거하지 않고 원문 값을 보존한다.
- 공시원문 변환 metadata 보강은 `kind_disclosure_html_manifest.json`을 읽지 않는다.
  - 메타데이터 파일은 항상 입력 디렉토리의 한 단계 위 디렉토리에 둔다.
  - 예: `bond_issuance/kind_html_contents_grouped_sections`를 입력하면 `bond_issuance/filtered.json`과 `bond_issuance/compressed-external-html.json`만 읽는다.
  - 각 디렉토리 안에서는 `filtered.json`을 먼저 읽고 `compressed-external-html.json`을 나중에 읽는다.
  - 같은 `acpt_no`와 같은 metadata key가 여러 번 발견되면 나중에 병합한 값이 저장된다.
- 정정공시 묶음은 `compressed-external-html.json`의 `mainDoc` 선택지에서 만든다.
  - member 제목은 `mainDoc.text`를 `title`로 저장한다.
  - parsed JSON 최상위 `families`에는 family별 `members`만 저장한다.
  - 각 record에는 `family_id`, `current_sequence`, `family_member_count`만 저장한다.
- 저장 record에는 `source_file`을 저장하지 않는다. 실행 중 preview, errors, warnings, job status에서는 진단용으로 사용할 수 있다.
- 저장 결과 summary에서 원문 preview가 필요하면 요청의 `source_directory`와 record의 `acpt_no`로 원본 HTML 파일을 찾는다.
  - 먼저 `source_directory/<acpt_no>.html`을 확인한다.
  - 없으면 `source_directory` 아래에서 `<acpt_no>*.html`을 찾고, 파일 stem의 `_` 앞부분이 `acpt_no`와 같은 첫 파일을 사용한다.
- skip_errors=True인 경우 파싱 실패 시 전체 작업을 중단하지 않고 errors에 기록한다.
- change-log는 `CHANGE_LOG_COMPARISON_FIELDS`에 정의된 필드만 비교한다. 정의가 없는 mode는 비교 필드가 빈 목록이다.

#### 사채발행파싱 (bond_issuance)
- 사채 발행금액 행에서 `원화기준 포함` 행을 우선하고, 없으면 첫 `사채의 권면` 행을 사용한다.
  - 해외발행의 경우에서 원화기준 권면을 우선하기 위함이다.
- 행사 대상 주식 관련 문구는 `교환대상` 행을 먼저 확인하고, 없으면 `전환에 따라`·`전환으로 발행할`·`인수권행사에 따라`와 `종류`가 함께 있는 행을 확인한다.
- 행사가액은 `전환가액` -> `교환가액` -> `행사가액` -> `행사가격` 순서로 확인한다.
- 만기일은 `사채만기일` -> `사채만기` 순서로 확인한다.
- 행사기간은 `전환청구기간` -> `교환청구기간` -> `권리행사기간` -> `행사기간` 순서로 확인한다.

#### 유무상증자파싱 (rights_issuance)
- 제3자배정 대상자 표에서 `배정주식수` 열을 찾지 못하면 행의 마지막 숫자를 배정주식수로 읽는다.
- 후보 대상자 표가 여러 개이고 신주 합계와 일치하는 표가 없으면, 값이 있는 첫 후보 표를 사용하고 합계 불일치 경고로 드러낸다.
- 유무상증자(`mixed`)에서 무상증자 섹션 기준 행을 찾지 못하면 유상 상세 객체는 전체 추출 대상 행을 사용하고 무상 상세 객체는 빈 행 목록을 사용한다.
- 상세 객체의 `1주당 신주배정주식수`는 주식 종류별 값을 찾지 못한 경우 해당 행의 마지막 값을 `보통주식` 값으로 저장한다.
- 주식 수량형 필드는 원천 값을 찾지 못하면 0을 저장하고, 원문에서 0 또는 대시를 읽은 경우 상태가 있는 필드에는 `explicit_zero`로 기록한다.

## 워크플로우 메타데이터

이 필드들은 HTML 본문 표에서 직접 추출하지 않고 사전 추출된 데이터로 보강하는 항목이다.

| 필드 | 출처 | 설명 |
| --- | --- | --- |
| `families` | `compressed-external-html.json` | 외부 HTML `mainDoc` 선택지에 명시된 정정공시 묶음. parsed JSON 최상위에 한 번만 저장하며, member 제목은 `mainDoc.text`를 `title`로 저장 |
| `family_id` / `current_sequence` / `family_member_count` | `families` | record가 어떤 정정 묶음의 몇 번째 공시인지 표시하는 얇은 참조 필드 |
| `doc_no` | `filtered.json`, `compressed-external-html.json` | `selected_main_doc_no`에서 읽은 KIND viewer 본문 문서 선택 번호 |
| `corp_name` | `filtered.json` | 공시 회사명. 현재 `bond_issuance`, `rights_issuance` 저장 record에 보강 |
| `상장구분` | `filtered.json`, `compressed-external-html.json` | 코스피, 코스닥, 코넥스, 기타 |

식별자 계약:

| 항목 | 규칙 |
| --- | --- |
| KIND 기준 식별자 | `acpt_no` |
| DART 접수번호 | KIND HTML 워크플로우는 DART `rcept_no`를 만들거나 보강하지 않는다. |
| `mainDoc` | viewer 안의 문서 선택 번호로만 다루며, DART 접수번호로 해석하지 않는다. |
| `selected_main_doc_no` | `doc_no`의 단일 출처로 사용하고 parsed record에는 저장하지 않는다. |
| `doc_no` | `selected_main_doc_no` 값만 저장한다. 다른 `doc_no` 필드로 대체하지 않는다. |
| 복원 금지 | KIND HTML 본문, viewer HTML, `filtered.json`, `compressed-external-html.json`만으로 DART `rcept_no`를 복원하지 않는다. |

## 저장 record 계약

이 필드들은 parser별 `parsed-*.json`의 `records` 항목에 저장된다.

| 필드 | 값 |
| --- | --- |
| `acpt_no` | 확장자를 뺀 파일명에서 `_` 앞에 있는 숫자 부분. 숫자로 시작하지 않으면 빈 문자열 |
| `mode` | parser별 mode 값 |
| `title` | 웹 파싱 저장 record에서는 호출자가 parser에 주입한 제목만 사용한다. metadata 보강 단계에서 빈 제목을 다시 채우지 않는다. 주입 제목이 없으면 빈 문자열과 `strong_warning`을 남긴다. |
| `family_id` | 정정공시 묶음에 속한 경우 최상위 `families`의 키 |
| `current_sequence` | 정정공시 묶음 안에서 현재 record의 순번 |
| `family_member_count` | 정정공시 묶음의 전체 member 수 |
| `상장구분` | 주변 metadata에서 보강. 없으면 `null` |
| `doc_no` | 주변 metadata에서 산출되는 경우에만 저장 |

정정공시 묶음 전체는 record마다 반복 저장하지 않고 parsed JSON 최상위 `families`에 저장한다.

원본 HTML 경로는 preview, errors, warnings, job status 같은 실행/진단 데이터에서만 다룬다.

`corp_name`은 공시 주체 회사명이다. HTML 본문에서 언급되는 회사명이 아니며,
현재 `bond_issuance`, `rights_issuance` record에만 저장한다.

## 원문 구조 계약

이 필드들은 parser가 필드 추출에 사용하지만, 웹 파싱 저장 단계에서 `records`에
남기지 않는다.

| 필드 | 값 | 저장 여부 |
| --- | --- | --- |
| `raw_tables` | HTML의 모든 표를 행/셀 구조로 정리한 값 | 저장하지 않음 |
| `raw_rows` | 모든 표의 행을 한 목록으로 합친 값 | 저장하지 않음 |

`raw_tables`와 `raw_rows`는 개별 `parse_*()` 함수의 직접 반환값에는 포함될 수 있다.
`parse_disclosure_html_payload()`가 저장 JSON을 만들 때는 제거한다. 실제 필드 추출에
전체 행을 쓸지, 선별한 표의 행을 쓸지는 parser별 문서를 따른다.

## 상태 코드 계약

| 코드 | 공통 의미 | 사용 기준 |
| --- | --- | --- |
| `parsed` | 값을 찾았다. | 정상 추출 |
| `explicit_zero` | 원문에서 0 또는 대시를 읽어 0으로 해석했다. | 원천은 있으나 값이 0/대시인 경우 |
| `source_not_found` | 정해진 위치에서 값을 찾지 못했다. | 원천 행/표/판정 단서 누락 |

parser별로 필요한 경우 추가 상태 코드를 정의할 수 있다. 추가 상태 코드는 개별 문서의
`상태와 경고` 섹션에 표로 적는다.

## 경고 출력 계약

| 출력 필드 | 공통 의미 |
| --- | --- |
| `field_parse_status` | 필드별 상태 코드 |
| `parse_warnings` | 모든 경고를 한 곳에 모은 목록 |
| `weak_warning` | 추출은 됐지만 값 사이의 관계가 맞지 않는 경우 |
| `medium_warning` | parser별 중간 수준 경고 |
| `strong_warning` | 정해진 위치에서 필드 값을 찾지 못했거나 핵심 판정에 실패한 경우 |

공통 처리 원칙:

| 항목 | 규칙 |
| --- | --- |
| `parse_warnings` 포함 대상 | 원천 누락, 핵심 판정 실패, 검증 실패 |
| 검증 규칙 | 대상, 허용 오차, `warning_code`는 parser별 문서를 따른다. |
| 후처리 책임 | 원천 테이블을 다시 찾지 않고, 추출 단계가 넘긴 원천 존재 여부와 명시적 0 여부로 상태/경고를 만든다. |

## 개별 문서 작성 형식

parser별 문서는 아래 목차를 맞춘다.

1. `한눈에 보기`
2. `공통 규칙 override`
3. `처리 흐름`
4. `모듈 책임`
5. `출력 필드`
6. `표 추출 규칙`
7. `상태와 경고`
