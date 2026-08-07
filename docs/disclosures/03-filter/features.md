# Disclosure Filtering Features

## Purpose

연도별 SQLite에서 제목 후보를 조회하고 검색 조건에 맞는 공시를 원문 저장 대상으로 고른다.

## Features

### Validate SQLite Input

#### Behavior

변환 결과가 원본 행을 빠짐없이 설명하는지 확인한 뒤 조건을 적용한다.

#### Defaults and Exceptions

- 입력은 `data_root`로 지정한 작업공간의 `02-table/sqlite_manifest.json`만 사용한다.
- manifest가 없거나 FINIQ SQLite manifest 형식이 아니면 실패 처리한다.
- manifest가 가리키는 SQLite 조각이 없거나 필수 열이 없으면 실패 처리한다.
- manifest의 연도별 저장 행 수 합과 전체 저장 행 수가 다르거나, 실제 SQLite 행 수와 manifest의 저장 행 수가 다르면 실패 처리한다.
- 페이지별 또는 전체 원본 행 수가 저장 행 수와 중복 행 수의 합과 다르면 실패 처리한다.

### Determine the Incremental Search Range

#### Behavior

같은 조건으로 이미 완료한 02단계 행을 반복 검색하지 않고, 완료 결과의 원본 검사 건수를 다음 실행의 시작 위치로 사용한다.

#### Defaults and Exceptions

- 02단계 원본 건수가 이전에 확인한 건수와 같을 때만 저장된 시작 위치부터 검색한다.
- 중단 결과가 있으면 중단 전에 검사한 행 수까지 시작 위치에 더해 나머지 행을 검색한다.
- 현재 원본 공시 건수가 완료 또는 중단 결과에 저장된 이전 확인 건수와 다르면 저장된 증분 결과를 사용하지 않고 원본 전체를 처음부터 다시 검색한다.
- 저장된 결과를 이어서 검색할 때는 02단계가 기존 행 순서를 유지한다는 운영 전제를 사용한다.
- 과거 멤버십 hash는 저장하지 않고 건수로 검증하므로, 건수가 같은 원본 교체는 식별하지 못한다. 해당 변경이 의심되면 02단계 데이터베이스를 초기화하고 01단계부터 다시 실행한다.

### Filter Disclosures

#### Behavior

시장, 공시일, 회사명, 제출인과 제목 조건으로 원문을 저장할 공시를 고른다. 조건과 일치한 항목 중 `acpt_no`가 같은 항목은 같은 공시로 보고 먼저 읽은 항목만 남긴다.

#### Defaults and Exceptions

- 제목 조건 결합 방식이 `or` 또는 `and`가 아니면 실패 처리한다.
- `filter_blocks`가 목록이 아니면 실패 처리한다.
- 조건 블록이 객체가 아니거나 field·연산자·연결자·괄호 수·boolean 제어값이 누락되거나 유효하지 않으면 실패 처리한다.
- 조건 블록 연결자는 `AND`, `XOR`, `OR`를 지원한다. 서로 다른 연결자를 혼합할 때는 각 연산 범위를 괄호로 명시해야 하며, 같은 괄호 범위에 두 종류 이상의 연결자가 있으면 실패 처리한다.
- `between` 연산자에 두 값을 지정하지 않으면 실패 처리한다.
- 공시에 비어 있지 않은 `acpt_no`가 없으면 실패 처리한다.
- 날짜 조건을 사용하는 공시에 공시일이 없으면 실패 처리한다.

### Search Disclosure Titles

#### Behavior

연도별 SQLite에 같은 조건을 적용하고 원문 제목별 공시 건수를 조회한다. `sqlite_manifest.json`이 가리키는 SQLite를 직접 조회하고 제목별 `COUNT(DISTINCT acpt_no)`를 합쳐 결과를 만든다.

#### Defaults and Exceptions

- 조회 결과는 작업 상태에만 보관하며 `03-filter` 파일을 만들거나 바꾸지 않는다.
- 제목 조회는 비동기 작업으로 실행하며 작업 ID, 진행 내역과 완료 결과를 보관한다.
- 취소 요청을 받으면 SQLite 조회를 끝내고 취소 상태를 기록한다.

### Normalize Search Text

#### Behavior

`clean_search=true`인 조건은 검색 대상과 입력값에서 괄호와 괄호 안의 내용을 제거한 뒤 비교한다. 화면의 제목 후보도 같은 기준으로 묶어 표시한다.

#### Defaults and Exceptions

- 닫히지 않은 괄호가 나오면 그 위치부터 끝까지 제거한다.

### Save Filter Workflows

#### Behavior

filter가 정의하는 mode 폴더의 `filter.json`에 조건, 실행 상태, 완료 결과 또는 중단 결과를 관리한다. 실행 중에는 원본을 바꾸지 않고 같은 mode 폴더의 숨김 임시 JSON에서 상태와 증분 결과를 만든다.

#### Defaults and Exceptions

- 새 filter의 초기 상태는 `ready`이며 mode와 조건을 함께 기록한다.
- 같은 mode의 기존 filter와 조건이 같으면 완료·중단 결과를 유지하고, 조건이 달라지면 상태와 결과를 대기로 초기화한다.
- 완료 목록은 `result`, 중단된 증분 목록은 `pending.result`에 저장한다.
- 모든 건수 검증을 통과한 완료 결과만 원본 JSON으로 원자적으로 교체한다.
- mode 폴더 밖의 이전 형식 파일은 filter 목록에서 제외하며 자동으로 바꾸지 않는다.
- 손상됐거나 필요한 상태가 없는 filter를 임의로 고치거나 결과 파일로 대신하지 않고 실패 처리한다.
- mode가 폴더 이름으로 유효하지 않거나 저장된 조건과 실행 요청 조건이 다르면 실패 처리한다.

### Save Mode-Specific Results

#### Behavior

원본 workflow에 병합된 전체 결과를 04단계가 읽을 수 있도록 mode별 전달 파일로 저장한다.

#### Defaults and Exceptions

- 별도 결과 경로는 파일이 아니라 폴더를 지정하고 그 아래에 `<mode>/filtered.json`을 만든다.
- mode가 없거나 폴더 이름에 사용할 수 없는 값이면 실패 처리한다.
- 결과 경로가 없거나 JSON 파일 경로를 직접 지정하면 실패 처리한다.

### Validate Filter Result Counts

#### Behavior

증분 검색을 마친 뒤 다음 관계를 확인한다.

- `원본 건수 - 시작 위치 = 검색 대상 건수`
- `검사 완료 건수 = 검색 대상 건수`
- `결과 건수 = 실제 결과 배열 길이`

#### Defaults and Exceptions

- 증분 구간이 이전 검사 완료 위치와 이어지지 않거나 병합 뒤 건수가 실제 데이터와 다르면 실패 처리하고 초기화 오류를 안내한다.

### Manage Filter Workflow Execution

#### Behavior

조건 입력, 데이터베이스 검색, 결과 기록 순서와 각 단계의 시작·완료·중단 시각, 입력 경로, 원본 JSON 경로와 요약을 기록한다.

#### Defaults and Exceptions

- 실행 중인 filter는 동시에 다시 실행하거나 저장·삭제할 수 없다.
- 클라이언트 연결이 끊기면 지금까지 검사한 증분 결과를 `interrupted`로 저장한다. 검사 전에 끊겨 부분 결과가 없으면 원본은 실행 전 상태를 유지한다.
- 일반 실행 오류는 기존 완료·중단 결과를 유지한 채 `failed` 상태와 오류를 기록한다.
- 진행 단위나 숫자가 없거나 형식이 다르면 실패 처리한다.

### Share Filter Workflows in the UI

#### Behavior

공시내역 필터링, 공시원문 변환과 공시 자동화에서 같은 mode별 조건검색 filter 목록을 제공하고, 선택한 filter의 mode와 조건을 실행 입력으로 사용한다.

#### Defaults and Exceptions

- 선택 목록은 `03-filter/<mode>/filter.json`만 읽는다.
- 공시내역 필터링 화면에는 수동 `불러오기` 버튼을 표시하지 않는다.
- 03단계와 후속 단계의 실행 설정에는 선택한 filter의 mode가 들어간다.
- 저장한 mode와 조건이 화면 입력과 같을 때만 검색을 시작한다.
