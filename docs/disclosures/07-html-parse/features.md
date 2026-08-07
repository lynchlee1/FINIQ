# Disclosure HTML Parse Features

## Purpose

목차 HTML과 외부 metadata를 읽어 선택한 mode의 구조화 결과를 저장하고 preview와 진단 정보를 제공한다.

## Features

### Collect Annual Parser Inputs

#### Behavior

- `<data_root>/06-sections` 바로 아래의 4자리 연도 폴더와 그 바로 아래의 `*.html`만 읽는다.
- 입력 루트, 이름이 다른 폴더와 더 깊은 하위 HTML은 제외한다.
- `parse_disclosure_html_payload()`가 필수 경로, mode, 필터와 실행 옵션을 검증하고 mode parser를 선택한다.

#### Defaults and Exceptions

- `filter_blocks`가 목록이 아니면 실패 처리한다.
- `skip_errors`는 불리언으로 명시해야 하며 없거나 다른 형식이면 실패 처리한다.
- 확장자를 뺀 파일명이 같은 입력이 둘 이상이면 실행을 시작하지 않는다.
- metadata를 사용하려면 `filtered_metadata_path`와 `compressed_metadata_path`를 직접 지정해야 하며 인접 파일을 탐색하지 않는다.
- `filtered_metadata_path`를 지정하면 선택한 모든 HTML의 `disclosed_at`이 `YYYY-MM-DD HH:MM` 형식이어야 한다.
- 압축 metadata의 각 record에는 `metadata` 객체가 있어야 하며 family 구성원에 `disclosed_at`이 없으면 실패 처리한다.

### Transform Common HTML Input

#### Behavior

- HTML byte 입력을 UTF-8로 읽고 DOM으로 만든 뒤 병합된 표를 펼친다.
- `positional_rows`는 병합 셀을 펼친 열 위치를 보존한다.
- `logical_rows`는 빈 칸과 연속한 같은 값의 칸을 제거하고 그 결과가 빈 행도 제외한다.
- 행 이름 검색, 공백 정리와 숫자 변환은 모든 mode에서 같은 공통 규칙을 사용한다.

#### Defaults and Exceptions

- UTF-8 decode가 실패하면 다른 문자셋을 시도하지 않고 오류로 처리한다.
- `rowspan`이나 `colspan`이 유효한 양의 정수가 아니면 실패 처리한다.
- HTML·metadata 구조가 공통 입력 계약과 다르면 해당 결과를 만들지 않는다.

### Run the Selected Mode Parser

#### Behavior

- `features/disclosures/html_parse_common.py`의 `PARSER_REGISTRY`에서 선택한 mode parser를 찾는다.
- `parse_bond_issuance()`, `parse_rights_issuance()`, `parse_shareholder_meeting()`, `parse_asset_transaction()`, `parse_security_transaction()` 중 선택한 함수만 실행한다.
- 공통 식별값, 값별 상태와 warning 규칙에 mode별 업무값을 추가한다.
- 외부 title은 함수 선언에 `title` 인자가 있는 parser에만 전달한다.

#### Defaults and Exceptions

- parser signature 검사나 파일 parsing이 실패하고 `skip_errors=False`이면 전체 실행을 중단하고 결과를 저장하지 않는다.

### Connect Metadata and Correction Families

#### Behavior

- 지정된 `filtered.json`과 `compressed-external-html.json`에서 title·회사명·시장·공시시각·본문 문서번호를 연결한다.
- 파일명 stem 전체를 `acpt_no`와 metadata 연결 key로 사용하며 밑줄로 자르거나 숫자인지 검사하지 않는다.
- 완성된 correction family만 record에 연결하고 family 본문은 최상위 `families`에 한 번만 둔다.
- `bond_issuance`와 `rights_issuance`는 metadata에 회사명이 있으면 `corp_name`도 저장한다.

#### Defaults and Exceptions

- metadata·family index 구성이 실패하면 `skip_errors`와 관계없이 전체 실행을 중단한다.

### Build and Save the Final Payload

#### Behavior

- 성공 record, family, warning, error, 필터 조건과 실행 집계를 JSON 하나로 구성한다.
- 저장 record에는 parser가 반환한 `title`, `acpt_no`, `상장구분`과 mode별 값이 남는다.
- metadata에 값이 있으면 `doc_no`, `disclosed_at`을 연결하고 family에는 `family_id`, `current_sequence`, `family_member_count`를 기록한다.
- parser가 직접 반환한 `raw_tables`는 분석할 때만 사용하고 저장 record에서는 제거하며 `raw_rows`는 만들지 않는다.
- `rcept_no`, `source_file`, 빈 `correction_families`는 만들지 않는다.
- 입력 루트는 최상위 `input_directory`에 한 번만 기록하고 record·warning·error·preview는 `acpt_no`로 원본을 식별한다.
- `source_preview`는 바깥 record의 `acpt_no`를 반복하지 않는다.
- 저장 결과에서 제외한 성공 record의 warning도 최상위 warning 집계에는 남긴다.

#### Defaults and Exceptions

- 식별자 중복, 최종 payload 구성 실패 또는 저장 실패가 발생하면 `skip_errors`와 관계없이 전체 실행을 중단한다.

### Continue after Per-file Parse Errors

#### Behavior

- `skip_errors=True`일 때만 실패 파일의 일부 결과와 warning을 버리고 다음 파일을 처리한다.
- `progress_interval`마다 현재 record·warning·error를 결과 JSON에 중간 저장한다.
- `errors[]`에는 선택 순서와 전체 수, mode, 파일명에서 읽은 `acpt_no`, `error_type`, 오류 문장을 기록한다.

#### Defaults and Exceptions

- 이 동작은 파일 단위 parsing 실패에만 적용하며 metadata·family index, 최종 payload 구성 또는 저장 실패에는 적용하지 않는다.

### Validate Warning Consistency

#### Behavior

- parser warning의 수준과 code를 검증하고 공시별·수준별 건수를 집계한다.
- `parse_warnings`와 수준별 목록이 일치하는지 최종 payload 구성 전에 확인한다.

#### Defaults and Exceptions

- 같은 warning 목록에 중복·빈 문장·수준 누락·복수 수준 지정이 있거나 두 목록이 일치하지 않으면 보정하지 않고 실패 처리한다.

### Preview Parse Results

#### Behavior

- `build_parse_preview_payload()`가 변환 결과와 원문 표 일부를 함께 보여 주며 원본과 저장 결과는 바꾸지 않는다.
- 긴 표는 앞부분과 생략한 행 수만 보여 주고, 표 제목은 원문 제목·변환 결과 제목·빈 값 순서로 선택한다.

#### Defaults and Exceptions

- preview 입력 원문 하나라도 읽거나 변환하지 못하면 실패 처리한다.
- 변환 결과를 만든 뒤 부가 원문 표만 찾거나 읽지 못하면 이유를 표시하고 변환 결과는 유지한다.

### Build Filter Candidates

#### Behavior

- `build_parse_filter_candidates_payload()`가 선택한 항목의 값별 개수와 접수번호 예시를 모든 입력에서 계산한다.
- 접수번호 예시는 일부만 보여 주고 전체 개수는 모두 계산하며 저장 결과는 바꾸지 않는다.

#### Defaults and Exceptions

- 원문 하나라도 실패하면 일부 후보를 반환하지 않는다.

### Control and Inspect Parse Runs

#### Behavior

- `cancel_disclosure_html_parse()`가 실행 중인 변환에 취소 요청을 전달한다.
- 조회 함수는 사채 요약, 정정 내역과 Excel 결과를 만든다.

#### Defaults and Exceptions

- 진행 알림 간격이 정수가 아니거나 1보다 작으면 실패 처리한다.
- 안내 수준, code, 접수번호나 예시 형식이 잘못되면 실패 처리한다.

### Build Shared Raw Table Results

#### Behavior

- `asset_transaction`과 `security_transaction`은 공통 식별값과 원본 `raw_tables`를 만드는 같은 입력·결과 흐름을 사용한다.
- 두 parser의 mode 전용 schema는 빈 객체다.

#### Defaults and Exceptions

- mode 전용 업무값, `field_parse_status`와 parser warning은 만들지 않는다.

### Investigate Parser Problems

#### Behavior

1. 제보받은 mode와 접수번호를 확인하고 같은 입력으로 변환을 다시 실행한다.
2. 저장 결과와 안내를 찾고 해당 06단계 HTML을 연다.
3. `bond_issuance`와 `rights_issuance`는 `resources/KIND/bond_issuance`, `resources/KIND/rights_issuance`의 실제 KIND 파일과도 대조한다.
4. 기대값의 표와 칸을 현재 mode parser의 추출 규칙과 비교한다.
5. 해당 parser의 함수 책임을 확인해 규칙을 고치고 실제 KIND 파일, test fixture와 합성 HTML로 검증한다.
6. 변환을 다시 실행해 제보된 오류가 사라지고 다른 결과가 바뀌지 않았는지 확인한다.
