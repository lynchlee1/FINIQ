# HTML 파서 공통 로직 규칙

최종 업데이트: 2026-07-08


## 워크플로우 메타데이터

이 필드들은 HTML 본문 표에서 직접 추출하지 않고 사전 추출된 데이터로 보강하는 항목이다.

| 필드 | 출처 | 설명 |
| --- | --- | --- |
| `correction_families` | `filtered.json` | 정정공시 목록 |
| `rcept_no` | - | DART 내부 공시 코드 |
| `corp_name` | `filtered.json`, `compressed-external-html.json` | 공시 회사명 |
| `상장구분` | `filtered.json`, `compressed-external-html.json` | 코스피, 코스닥, 코넥스, 기타 |

식별자 계약:

| 항목 | 규칙 |
| --- | --- |
| KIND 기준 식별자 | `acpt_no` |
| DART 접수번호 | KIND HTML 워크플로우는 DART `rcept_no`를 만들거나 보강하지 않는다. |
| `mainDoc` | viewer 안의 문서 선택 번호로만 다루며, DART 접수번호로 해석하지 않는다. |
| 복원 금지 | KIND HTML 본문, viewer HTML, `filtered.json`, `compressed-external-html.json`만으로 DART `rcept_no`를 복원하지 않는다. |

## 저장 record 계약

이 필드들은 parser별 `parsed-*.json`의 `records` 항목에 저장된다.

| 필드 | 값 |
| --- | --- |
| `acpt_no` | 확장자를 뺀 파일명에서 `_` 앞에 있는 숫자 부분. 숫자로 시작하지 않으면 빈 문자열 |
| `mode` | parser별 mode 값 |
| `title` | parser 호출자가 주입한 제목. 주입 제목이 없을 때의 fallback은 parser별 문서를 따른다. |

원본 HTML 경로는 preview, errors, warnings, job status 같은 실행/진단 데이터에서만 다룬다.

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
