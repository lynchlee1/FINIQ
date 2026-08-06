# 공시원문 변환 Cases

## 처리 계약

### 복구 동작

#### 파일별 parsing 실패 제외

요청에서 명시한 실패 정책에 따라 실패 파일을 제외하고 나머지 입력을 계속 처리한다.
- `skip_errors=True`일 때만 실패한 파일에서 일부 결과와 warning을 버리고 다음 파일을 처리한다.
- `skip_errors=True`이면 `progress_interval`마다 현재 record·warning·error를 결과 JSON에 중간 저장한다.
- `errors[]`에는 선택 순서와 전체 수, mode, 파일명에서 읽은 `acpt_no`, `error_type`, 오류 문장을 기록한다.
- 이 규칙은 파일 단위 parsing 실패에만 적용한다. metadata·family index, 최종 payload 또는 저장 실패에는 적용하지 않는다.

### 중단 조건

#### HTML 구조 오류가 나면 변환 중단

문자·표 구조를 확정하지 못한 원문을 임의로 보정하지 않는다.
- UTF-8 decode가 실패하면 다른 문자셋을 시도하지 않고 오류로 처리한다.
- `rowspan`이나 `colspan` 값이 유효한 양의 정수가 아니면 실패 처리한다.

#### 실행 입력 오류가 나면 중단

실행 범위와 실패 처리 정책이 불명확한 요청을 시작하지 않는다.
- `filter_blocks`가 목록이 아니면 실패 처리한다.
- `skip_errors`는 불리언으로 명시해야 하며 없거나 다른 형식이면 실패 처리한다.
- 확장자를 뺀 파일명이 같은 입력이 둘 이상이면 실행을 시작하지 않는다.
- metadata를 사용하려면 `filtered_metadata_path`와 `compressed_metadata_path`를 직접 지정해야 하며 인접 파일을 탐색하지 않는다.
- `filtered_metadata_path`를 직접 지정하면 선택한 모든 HTML에서 `disclosed_at`이 `YYYY-MM-DD HH:MM` 형식이어야 한다.
- 압축 metadata에서 record마다 `metadata` 객체가 있어야 하며 family 구성원에 `disclosed_at`이 없으면 실패 처리한다.

#### warning 구조 오류가 나면 중단

서로 모순인 warning 수준과 집계를 저장하지 않는다.
- 같은 warning 목록에 중복이나 빈 문장이 있거나 수준이 빠졌거나 둘 이상 지정됐으면 실패 처리한다.
- `parse_warnings`와 수준별 목록이 일치하지 않아도 보정하지 않고 실패 처리한다.

#### 파일 하나를 parsing하지 못하면 전체 중단

파일 제외를 허용하지 않은 실행에서 일부 결과를 저장하지 않는다.
- `skip_errors=False`이면 parser signature 검사나 파일 하나를 parsing하다 실패해도 전체 실행을 중단하고 결과를 저장하지 않는다.

#### 결과를 구성하지 못하면 전체 중단

식별자나 family가 불완전한 payload를 만들지 않는다.
- 파일명에서 확장자를 뺀 값이 중복되거나 metadata·family index 또는 최종 payload 구성이 실패하면 `skip_errors`와 관계없이 전체 실행을 중단한다.

#### 결과를 저장하지 못하면 전체 중단

완성된 payload를 안전하게 저장하지 못하면 결과를 게시하지 않는다.
- 최종 payload 저장이 실패하면 `skip_errors`와 관계없이 전체 실행을 중단한다.

## 화면과 서비스 계약

### 복구 동작

#### 원문 표 preview 일부 실패

원문 표를 보여 주지 못해도 변환 결과는 보여 준다.
- 변환 결과가 이미 만들어진 뒤 부가 원문 표를 찾거나 읽지 못한 경우에만 이유를 표시하고 변환 결과는 유지한다.

### 중단 조건

#### 화면 입력 오류가 나면 중단

잘못된 진행 상태와 안내를 임의로 고치지 않는다.
- 진행 알림 간격이 정수가 아니거나 1보다 작으면 실패 처리한다.
- 안내 수준, 코드, 접수번호나 예시 형식이 잘못되면 실패 처리한다.

#### preview·후보를 만들지 못하면 중단

실패한 원문을 빼고 일부 결과만 보여 주지 않는다.
- preview 입력 원문 하나라도 읽거나 변환하지 못하면 실패 처리한다. 변환을 마친 뒤 부가 원문 표만 표시하지 못하면 변환 결과만 보여 준다.
- 필터 후보를 만들 때 원문 하나라도 실패하면 일부 후보를 반환하지 않는다.

## 조건부 동작

### 회사명 metadata 연결

- `bond_issuance`와 `rights_issuance`는 metadata에 회사명이 있으면 `corp_name`도 저장한다.

### 최종 결과 구성·저장

- `raw_tables`는 parser를 직접 분석할 때만 쓰며 저장 record에서는 제거한다. `raw_rows`는 만들지 않는다.

- 저장 record에는 parser가 반환한 `title`, `acpt_no`, `상장구분`, 유형별 값이 남는다. metadata에 값이 있으면 `doc_no`, `disclosed_at`을 연결하고 완성한 family에는 `family_id`, `current_sequence`, `family_member_count`를 기록한다.

- `acpt_no`와 metadata 연결 key에는 `Path(file_path).stem` 전체를 사용한다. 밑줄을 기준으로 자르거나 숫자인지 검사해 다른 값으로 바꾸지 않는다.

- parser와 Web workflow는 `rcept_no`, `source_file`, 빈 `correction_families`를 만들지 않는다.

- 입력 루트는 최상위 `input_directory`에 한 번만 기록한다. record·warning·error·preview에는 파일 경로나 파일명을 넣지 않고 `acpt_no`로 원본을 식별한다. `source_preview`도 바깥 record에 있는 `acpt_no`를 반복하지 않는다.

### 공통 HTML 입력 변환

- 병합 셀을 펼친 `positional_rows`는 열 위치를 보존한다. parser가 라벨을 찾는 `logical_rows`는 빈 칸과 같은 글이 연속된 칸을 제거하고 그 결과가 빈 행도 제외한다.

### warning 구조 일관성 확인

- 같은 warning 목록에 중복·빈 문장·수준 누락·복수 수준 지정이 없는지 확인한다.

### Preview

- preview는 변환 결과와 원문 표 일부를 함께 보여 준다. 원본과 저장 결과는 바꾸지 않는다.

### 필터 후보

- 후보는 화면에서 이어서 쓸 필터 입력일 뿐, 저장한 변환 결과는 바꾸지 않는다.
