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

시장, 배지, 공시일, 회사명, 제출인과 제목 조건으로 원문을 저장할 공시를 고른다. 조건과 일치한 항목 중 `acpt_no`가 같은 항목은 같은 공시로 보고 먼저 읽은 항목만 남긴다.

#### Defaults and Exceptions

- 제목 조건 결합 방식이 `or` 또는 `and`가 아니면 실패 처리한다.
- `filter_blocks`가 목록이 아니면 실패 처리한다.
- 조건 블록이 객체가 아니거나 field·연산자·연결자·괄호 수·boolean 제어값이 누락되거나 유효하지 않으면 실패 처리한다. 필드 타입에 없는 연산자면 실패 처리한다.
- 조건 블록 연결자는 `AND`, `XOR`, `OR`를 지원한다. 서로 다른 연결자를 혼합할 때는 각 연산 범위를 괄호로 명시해야 하며, 같은 괄호 범위에 두 종류 이상의 연결자가 있으면 실패 처리한다.
- `between` 연산자에 두 값을 지정하지 않으면 실패 처리한다.
- 공시에 비어 있지 않은 `acpt_no`가 없으면 실패 처리한다.
- 날짜 조건을 사용하는 공시에 공시일이 없으면 실패 처리한다.
- 회사 관계가 없는 공시는 `company_key`, `company_name`, `company_id`가 `null`인 상태로 검색 대상에 포함한다. 회사명 조건에서는 빈 값으로 비교하고 제출인으로 회사를 대신하지 않는다.

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

filter가 정의하는 mode 폴더의 `filter.json`에는 조건, 실행 상태와 결과 요약을 관리한다. 완료 결과 본문은 기존 전달 파일인 `filtered.json`, 중단 결과 본문은 `filter.pending.json`에 저장한다. 실행 중에는 원본을 바꾸지 않고 같은 mode 폴더의 숨김 임시 JSON에서 상태와 증분 결과를 만든다.

#### Defaults and Exceptions

- 새 filter의 초기 상태는 `ready`이며 mode와 조건을 함께 기록한다.
- 같은 mode의 기존 filter와 조건이 같으면 완료·중단 결과를 유지하고, 조건이 달라지면 상태와 결과를 대기로 초기화한다.
- 완료 결과는 `result_file`이 가리키는 `filtered.json`, 중단된 증분 결과는 `pending_file`이 가리키는 `filter.pending.json`에 저장한다. 목록 조회는 이 대용량 파일을 읽지 않는다.
- 모든 건수 검증을 통과한 완료 결과만 원본 JSON으로 원자적으로 교체한다.
- mode 폴더 밖의 이전 형식 파일은 filter 목록에서 제외한다. 기존 `filter.json`에 내장된 `result`와 `pending`은 전용 마이그레이션 명령으로 분리한다.
- 손상됐거나 필요한 상태가 없는 filter를 임의로 고치거나 결과 파일로 대신하지 않고 실패 처리한다.
- mode가 폴더 이름으로 유효하지 않거나 저장된 조건과 실행 요청 조건이 다르면 실패 처리한다.

### Create One-Level Derived Filters

#### Behavior

완료된 기본 필터의 결과에 조건을 추가하는 파생 필터를 한 단계까지 만든다. 파생 필터는 02단계 전체가 아니라 상위 필터의 완료 결과만 입력으로 사용하므로 결과가 항상 상위 결과에 포함된다.

#### Defaults and Exceptions

- 요청의 `mode`는 자식 이름만 담고 `parent_mode`에 상위 기본 필터 이름을 따로 지정한다.
- 상위 필터는 `completed` 상태인 기본 필터만 허용하며 파생 필터를 다시 상위로 지정할 수 없다.
- 파생 필터는 `<data_root>/03-filter/<parent_mode>/subfilters/<mode>`에 저장한다.
- 파생 필터의 `filter.json`에는 `parent_mode`와 실행에 사용한 `parent_result_fingerprint`를 기록한다.
- 상위 결과가 변경되어 fingerprint가 다르거나, 상위 결과가 없거나 완료되지 않았으면 파생 필터를 `stale`로 보고 실행과 후속 작업을 실패 처리한다.
- 상위 결과 오류를 02단계 전체 검색이나 다른 필터 결과로 보완하지 않는다.
- 목록 응답은 기본 필터의 `id`를 `<mode>`, 파생 필터의 `id`를 `<parent_mode>/<mode>`로 구분한다. 화면에는 파생 필터를 `<상위> › <자식>`으로 표시하며 슬래시가 포함된 `id`를 `mode`로 전송하지 않는다. `공시내역 필터링`에서 `상위 필터`가 바로 위에 보일 때는 자식 이름만 표시하고, 목록·검사·이후 단계에서는 `<상위> › <자식>`을 유지한다.

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

조건 입력, 데이터베이스 검색, 결과 기록 순서와 각 단계의 시작·완료·중단 시각과 요약을 기록한다.

#### Defaults and Exceptions

- 실행 중인 filter는 동시에 다시 실행하거나 저장·삭제할 수 없다.
- 클라이언트 연결이 끊기면 지금까지 검사한 증분 결과를 `interrupted`로 저장한다. 검사 전에 끊겨 부분 결과가 없으면 원본은 실행 전 상태를 유지한다.
- 일반 실행 오류는 기존 완료·중단 결과를 유지한 채 `failed` 상태와 오류를 기록한다.
- 진행 단위나 숫자가 없거나 형식이 다르면 실패 처리한다.
- `filter.json`과 `filtered.json`에는 SQLite manifest나 filter JSON의 절대 경로를 기록하지 않는다.
- `filter.json`과 결과·대기 sidecar는 하나의 transaction 기록 아래 함께 게시한다. 게시가 중간에 끊긴 transaction은 다음 첫 읽기에서 기존 파일 묶음으로 복구한 뒤 복구된 문서를 다시 읽는다.
- 전체 검사는 한 파생 필터의 stale·orphan 오류에서 멈추지 않고 각 파생 필터의 상태를 독립적으로 보고한다.

### Share Filter Workflows in the UI

#### Behavior

공시내역 필터링과 공시원문 변환에서는 기본 필터와 파생 필터 목록을 제공한다. `공시원문 외부 저장`, `공시원문 내부 저장`, `공시원문 목차 분리`는 기본 필터만 보여 주며 산출물은 상위 기본 필터의 mode 폴더에 둔다. 공시 자동화는 기본 필터만 제공하고 선택한 기본 필터의 mode와 조건을 실행 입력으로 사용한다.

#### Defaults and Exceptions

- 선택 목록은 `03-filter/<mode>/filter.json`과 한 단계 아래의 `03-filter/<parent_mode>/subfilters/<mode>/filter.json`을 읽는다.
- 화면은 처음 열 때 `공시내역 제목 검색`을 선택한다.
- `기존 데이터 검토`는 `공시내역 제목 검색`과 `공시내역 필터링` 모두에서 첫 카드로 표시하며, 현재 선택한 filter와 관계없이 `03-filter/<mode>/filter.json`을 각각 읽어 설정·처리 단계·결과 무결성을 검사한다.
- 완료되지 않은 폴더는 작업 상태 이름 대신 조건만 저장됐는지, 검색이 중단·실패했는지, 결과를 저장하지 못했는지를 문장으로 표시한다.
- 공시내역 필터링 화면에는 수동 `불러오기` 버튼을 표시하지 않는다.
- 03단계와 후속 단계의 실행 설정에는 선택한 filter의 mode가 들어간다.
- 저장한 mode와 조건이 화면 입력과 같을 때만 검색을 시작한다.
- 새 필터는 `공시 조건`에서 `기본 필터` 또는 `파생 필터`로 선택한다. 파생 필터의 `상위 필터` 목록에는 완료된 기본 필터만 표시한다.
- `조건검색 필터` 목록은 작업공간 `03-filter`에 저장된 필터만 보여 주며 파싱 모드 키를 하드코딩하지 않는다.
- 파생 필터의 저장·실행·삭제 요청은 자식 `mode`와 `parent_mode`를 각각 전송한다.
- 공시 자동화 프로필은 `parent_mode`를 저장하지 않으므로 파생 필터를 선택하거나 JSON에서 불러오지 않는다.
