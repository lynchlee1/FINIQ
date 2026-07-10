# HTML 파서 공통 예외 처리 규칙

공통 table, base record, 저장 payload의 필드 구조는
[HTML 파서 공통 데이터 구조](./common-html-parser-data-structure.md)를 따른다.
공통 parsing 동작은
[HTML 파서 공통 로직 규칙](./common-html-parser-logic-rules.md)을 따른다.

이 문서에서는 세 가지 결과를 구분한다.

- 상태는 한 필드의 값을 찾았는지 설명한다.
- warning은 확인할 문제가 있지만 해당 record를 저장할 수 있다는 뜻이다.
- error는 해당 HTML 파일의 record를 만들지 못했다는 뜻이다.

worker는 HTML 파일을 하나씩 맡아 처리하는 실행 단위이다. worker를 여러 개 쓰면 여러 파일을 동시에 처리할 수 있다.

### 필드 상태 전달
1. **공통 상태 형식**
- parser는 `field_parse_status` 객체에 `필드명: 상태` 형식으로 필드별 결과를 기록할 수 있다.
- 공통으로 사용하는 상태의 뜻은 아래와 같다.

| 상태 | 쉬운 설명 | 세부 판정 |
|---|---|---|
| `parsed` | parser가 정한 위치에서 값을 읽었다. | parser별 문서 |
| `explicit_zero` | 값의 원천은 있지만 0, 대시 또는 빈 결과를 parser 규칙에 따라 명시적 0에 해당하는 결과로 해석했다. | parser별 문서 |
| `source_not_found` | parser가 정한 출처에서 저장할 수 있는 값을 얻지 못했다. 출처 누락뿐 아니라 빈 값이나 숫자 변환 실패도 개별 parser 규칙에 따라 포함될 수 있다. | parser별 문서 |

- 저장 결과가 0이나 빈 값처럼 같아 보여도, 원문에서 0을 읽은 `explicit_zero`와 사용할 값을 얻지 못한 `source_not_found`는 다른 상태이다.
  - 의도 : 저장값만 보면 구분하기 어려운 정상 추출, 명시적 0, 사용할 값을 얻지 못한 경우를 따로 확인하게 한다.
2. **parser별 추가 상태**
- 공시 유형에 따라 `not_applicable`, `source_found_empty` 같은 추가 상태를 사용할 수 있다.
- 추가 상태의 정확한 조건은 해당 parser 문서에서 정의한다.
- `field_parse_status_detail`도 필요한 parser만 사용하며, 예를 들어 하나의 필드 안에서 주식 종류별 상태를 따로 기록할 수 있다.
  - 의도 : 공통 형식은 공유하되 공시 유형마다 다른 업무 의미를 공통 코드가 임의로 해석하지 않게 한다.

### parser warning 수집
1. **parser가 반환하는 목록**
- parser는 모든 경고를 모은 `parse_warnings`와 수준별 목록인 `weak_warning`, `medium_warning`, `strong_warning`을 반환할 수 있다.
- warning의 구체적인 발생 조건은 개별 parser 문서에서 정의한다.

| 수준 | 공통 workflow에서의 의미 |
|---|---|
| `weak_warning` | parser가 약한 수준으로 분류한 warning |
| `medium_warning` | parser가 중간 수준으로 분류했거나 수준을 정하지 못한 warning |
| `strong_warning` | parser가 강한 수준으로 분류한 warning |

- 수준 이름만 공통이며, 어떤 문제가 어느 수준인지는 개별 parser가 결정한다.
  - 의도 : 공시 유형별 판단은 유지하면서 최종 payload의 warning 모양은 같게 만든다.
2. **중복 제거와 수준 결정**
- 공통 workflow는 같은 warning 문자열을 한 파일에서 한 번만 수집한다.
- 수준은 `weak_warning` → `medium_warning` → `strong_warning` 순서로 목록을 확인해 처음 발견한 수준을 사용한다.
- `parse_warnings`에만 있고 수준별 목록에는 없는 warning은 `medium_warning`으로 분류한다.
- 알 수 없는 수준 이름도 최종 집계에서는 `medium_warning`으로 처리한다.
  - 의도 : 같은 문장을 여러 목록에 넣어도 최종 warning이 반복되지 않게 하고, 수준 없는 warning도 빠뜨리지 않는다.
3. **filter와 warning**
- parser 성공 후 외부 metadata를 연결한 record가 모든 filter를 통과할 때만 그 record와 warning을 최종 payload에 넣는다.
- filter에서 제외된 record의 warning은 `warnings[]`와 warning 집계에 포함하지 않는다.
  - 의도 : 최종 `records[]`에 없는 공시의 warning이 결과 건수에 섞이지 않게 한다.

### workflow warning 구조
1. **warnings 항목**
- 최종 payload의 `warnings[]`에서 warning 하나는 아래 필드를 가진다.

| 필드 | 값 |
|---|---|
| `index` | 정렬된 전체 입력 파일에서 현재 파일의 1부터 시작하는 순서 |
| `total` | 처리 대상으로 선택한 전체 HTML 파일 수 |
| `mode` | 실행한 parser mode |
| `source_file` | 입력 HTML의 절대 경로 |
| `source_name` | 입력 HTML 파일명 |
| `warning` | 사람이 읽는 경고 문장 |
| `level` | `weak_warning`, `medium_warning`, `strong_warning` 중 하나 |
| `warning_code` | 프로그램이 구분하기 위한 짧은 code |

  - 의도 : 사람이 원인을 읽을 수 있고 프로그램도 수준과 종류를 일정한 값으로 구분할 수 있게 한다.
2. **warning code 변환**
- 공통 workflow는 warning 문자열을 아래 순서의 규칙으로 code로 바꾼다.

| warning 조건 | `warning_code` |
|---|---|
| 사채 메인 table 누락 문장과 정확히 일치 | `bond_main_table_missing` |
| 유무상증자 유형 판정 실패 문장과 정확히 일치 | `rights_issue_type_missing` |
| `발행목적: 자금조달 목적 합계`로 시작 | `bond_funding_purpose_sum_mismatch` |
| `투자자: 발행권면총액 합계`로 시작 | `bond_investor_sum_mismatch` |
| `: 정해진 출처에서 값을 찾지 못했습니다.`를 포함 | `source_not_found:<첫 콜론 앞의 필드명>` |
| 위 규칙에 해당하지 않음 | `parse_warning` |

- 공통 workflow는 code를 정하기 위해 원문 table을 다시 검사하지 않고 parser가 반환한 warning 문자열만 사용한다.
  - 의도 : parser의 추출 판단과 workflow의 출력 변환 책임을 분리한다.
3. **warning_report_counts**
- `warning_report_counts.count`는 최종 warning 항목의 전체 수이고 `report_count`는 warning이 하나 이상인 서로 다른 report 번호 수이다.
- `weak_warning`, `medium_warning`, `strong_warning` 아래에도 같은 방식으로 수준별 `count`, `report_count`, `reports`를 기록한다.
- 파일을 구분하는 report 번호는 `source_name`에서 확장자를 제거한 값이다.
  - 의도 : warning 문장 수와 warning이 발생한 공시 수를 따로 확인하게 한다.

### 파일별 parsing error
1. **skip_errors=True**
- HTML 파일을 읽거나 parser를 실행하거나 parser 반환값의 내부 필드·metadata·warning을 처리하는 도중 파일별 예외가 나면 그 파일의 record는 저장하지 않는다.
- 예외를 `errors[]`에 기록하고 다음 파일을 계속 처리한다.
- worker를 여러 개 쓰는 병렬 실행에서는 worker가 반환한 결과에 filter를 적용하고 최종 목록에 넣는 단계가 파일별 예외 처리 밖에 있다. 이 단계의 예외는 `skip_errors=True`여도 전체 실행 오류로 전달한다.
- error 하나는 아래 필드를 가진다.

| 필드 | 값 |
|---|---|
| `index` | 현재 파일의 1부터 시작하는 입력 순서 |
| `total` | 전체 처리 대상 HTML 파일 수 |
| `mode` | 실행한 parser mode |
| `source_file` | 입력 HTML의 절대 경로 |
| `source_name` | 입력 HTML 파일명 |
| `error_type` | 발생한 예외 class 이름 |
| `error` | 예외 message |

  - 의도 : 일부 파일이 깨져도 대량 실행을 이어 가면서 실패한 파일과 원인을 남긴다.
2. **skip_errors=False**
- 첫 번째 파일별 parsing 예외에서 전체 실행을 중단하고 `ValueError`로 전달한다.
- message에는 파일 순서, 파일명, 원래 예외 class 이름과 message가 포함된다.
- 중단된 실행은 정상적인 최종 payload를 반환하지 않는다.
  - 의도 : 호출자가 하나의 실패도 허용하지 않는 실행 방식을 명시적으로 선택할 수 있게 한다.
3. **skip_errors가 적용되지 않는 오류**
- mode, 입력·출력 디렉토리, `limit`, 진행 간격 같은 실행 옵션 검증은 파일 처리 전에 끝난다.
- 외부 metadata JSON 읽기와 정정공시 family 구성도 파일 처리 전에 끝난다.
- 따라서 이 단계의 오류는 `skip_errors=True`여도 파일별 `errors[]`로 바꾸지 않고 전체 실행 오류로 전달한다.
- JSON 문법이 잘못된 외부 metadata나 정수로 바꿀 수 없는 `option_index`가 여기에 해당한다.
  - 의도 : 모든 파일에 공통으로 영향을 주는 설정·metadata 문제를 한 파일의 문제처럼 숨기지 않는다.

### 병렬 처리, 저장, 중지
1. **결과 순서**
- worker가 여러 개여도 완료된 결과를 바로 저장하지 않고 입력 순서가 된 결과부터 `records[]`, `warnings[]`, `errors[]`에 반영한다.
- 앞 파일이 늦게 끝나면 뒤 파일의 완료 결과는 잠시 기다린다.
  - 의도 : 컴퓨터의 처리 속도 차이와 관계없이 같은 입력에서 같은 결과 순서를 유지한다.
2. **중간 저장**
- 성공 record, filter에서 제외된 record, error를 모두 포함해 이번 실행에서 처리 완료한 파일 수를 센다.
- 이 수가 `progress_interval`의 배수가 될 때 현재까지의 payload를 출력 JSON에 저장한다.
- 실행이 끝나면 같은 경로에 최종 payload를 다시 저장한다.
  - 의도 : 긴 실행 중에도 일정한 파일 수마다 현재 결과를 확인할 수 있게 한다.
3. **중지 요청**
- worker 하나로 처리할 때 `cancel_token`으로 중지 요청을 받으면 다음 파일을 시작하지 않는다. 다만 중지 요청 당시 이미 처리 중인 파일은 끝까지 처리하고 그 결과가 최종 payload에 포함될 수 있다.
- worker를 여러 개 쓰는 병렬 실행은 중지를 확인한 뒤 새 파일을 worker에게 넘기지 않는다. 다만 중지 전에 이미 넘겨서 실행 중인 파일은 끝까지 처리하고 그 결과가 최종 payload에 포함될 수 있다.
- 이때 payload의 `cancelled`는 `true`가 된다.
- 중지는 parsing error로 기록하지 않는다.
  - 의도 : 사용자가 작업을 멈춘 경우와 HTML 처리 실패를 구분한다.

### 미리보기와 필터 후보의 오류 처리
1. **parse preview**
- preview 생성 중 한 HTML 파일의 parsing이 실패하면 간단한 `index`, `source_file`, `error`를 preview의 `errors[]`에 넣고 다음 파일을 계속 확인한다.
- preview는 본 실행의 `skip_errors` 옵션을 사용하지 않는다.
  - 의도 : 일부 미리보기 후보가 깨져도 요청한 개수만큼 다른 성공 record를 찾을 수 있게 한다.
2. **source preview**
- 미리보기 대상 record의 `source_file`이 비어 있거나 파일이 없거나 원문 table 재구성에 실패하면 `source_preview.available`을 `false`로 반환한다.
- 가능한 경우 `error`에 이유를 넣고, 해당 record의 나머지 미리보기 응답은 유지한다.
  - 의도 : 원문 table 표시 실패와 이미 parsing된 업무 필드 결과를 분리한다.
3. **필터 후보 생성**
- 모든 HTML에서 필드 후보값을 모으는 중 개별 파일이 실패하면 그 파일을 후보 응답의 `errors[]`에 기록하고 나머지 파일은 계속 처리한다.
  - 의도 : 일부 파일의 실패 때문에 다른 파일에서 정상적으로 읽은 후보값까지 버리지 않는다.
