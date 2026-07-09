# HTML 파서 공통 로직 규칙

최종 업데이트: 2026-07-09


## Fallback 최소화 원칙
- `rowspan` · `colspan`에 잘못된 값이 있는 경우 조용히 보정하지 않고 실패 또는 경고로 드러낸다.
- 공시 제목은 외부 소스로부터 주입한 제목을 단일 SoC로 사용하며, `SECTION-1` · `<title>`을 사용한 fallback 로직을 만들지 않는다.
- 메타데이터 제목은 `title` 단일 필드만 사용하며, `title_display` · `title_attr`을 사용한 fallback 로직을 만들지 않는다.
- `doc_no`는 `selected_main_doc_no` 단일 필드만 사용하며, `item.doc_no`를 사용한 fallback 로직을 만들지 않는다.
- DART 공시코드인 `rcept_no`는 parser base record, workflow metadata, 저장 record, preview, summary, change-log, export 어디에서도 만들거나 보존하거나 표시하지 않는다.
- 공시원문 변환 metadata는 `filtered.json`과 `compressed-external-html.json`만 사용한다. `kind_disclosure_html_manifest.json`에 의존하지 않는다.
- 원문에서 추출한 회사명·대상명은 법인 형태나 주식 종류 표현을 임의 제거하지 않고 원문 값을 보존한다.
- 원문 미리보기는 record의 `source_file`을 이용해 파싱한다. wrapper HTML은 사용하지 않는다.
- skip_errors=True인 경우 에러가 발생해도 파싱을 계속한다. 

### 정정공시 핸들링
- 정정공시 내 제목은 `compressed-external-html.json`의 `mainDoc.text`를 `title`에 저장하며, `title_display` · `title_base` · `metadata.title` · `record.title`을 사용한 fallback 로직을 만들지 않는다.
- 정정공시 묶음은 `compressed-external-html.json`의 `mainDoc` 선택지에 명시된 관계로 만든다. `filtered.json`의 `company_key` · `title_base` · `title_display` · `title`로 묶음을 추론하는 fallback 로직을 만들지 않는다.

## Intended fallbacks
### HTML 파싱
- 디코딩을 utf-8 -> cp949 -> euc-kr -> utf-8(errors="replace") 순서로 시도한다.
- lxml.HTMLParser(recover=True)로 깨진 HTML을 복구한다.
- DART 공시코드인 rcept_no는 저장 및 사용하지 않는다.

### 공시원문 변환
- 공시원문 변환시 절대로 `kind_disclosure_html_manifest.json`을 참고해서는 안된다.
  - 외부 데이터 보강은 온전히 `filtered.json` · `compressed-external-html.json`에만 의존해야 한다.
  - 메타데이터는 공시원문을 연도별로 저장한 경우(`dir/yyyy/<acpt_no>.html`) grandparent 디렉토리에 존재하며, 한번에 저장한 경우(`dir/<acpt_no>.html`) parent 디렉토리에 존재한다.
  - 따라서, 메타데이터 파일 탐색은 parent -> grandparent 순서로 `filtered.json` · `compressed-external-html.json`을 찾는다. (input -> parent -> grandparent 순서가 아님에 유의하라.)
- skip_errors=True인 경우 파싱 실패 시 전체 작업을 중단하지 않고 errors에 기록한다.

#### 사채발행파싱 (bond_issuance)
- 사채 발행금액 행에서 `원화기준 포함` 행을 우선하고, 없으면 첫 `사채의 권면` 행을 사용한다.
  - 해외발행의 경우에서 원화기준 권면을 우선하기 위함이다.


- 만기일: 사채만기일 -> 사채만기 순서로 확인

## 워크플로우 메타데이터

이 필드들은 HTML 본문 표에서 직접 추출하지 않고 사전 추출된 데이터로 보강하는 항목이다.

| 필드 | 출처 | 설명 |
| --- | --- | --- |
| `correction_families` | `compressed-external-html.json` | 외부 HTML `mainDoc` 선택지에 명시된 정정공시 묶음. member 제목은 `mainDoc.text`를 `title`로 저장 |
| `doc_no` | `compressed-external-html.json` | KIND viewer 본문 문서 선택 번호 |
| `corp_name` | `filtered.json`, `compressed-external-html.json` | 공시 회사명. 현재 `bond_issuance`, `rights_issuance` 저장 record에 보강 |
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
| `correction_families` | 정정공시 묶음. 없으면 빈 객체 |
| `상장구분` | 주변 metadata에서 보강. 없으면 `null` |
| `doc_no` | 주변 metadata에서 산출되는 경우에만 저장 |

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
