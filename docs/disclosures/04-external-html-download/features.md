# External HTML Download Features

## Purpose

선택한 공시의 KIND 외부 HTML을 연도별로 저장하고, 문서 선택에 필요한 정보를 JSON 파일 하나로 압축한다.

## Features

### Download External HTML

#### Behavior

선택한 mode의 필터 결과에 기록된 공시만 내려받아 문서 선택 정보와 원본 식별값을 보존한다. 외부 HTML은 문서 선택 화면이며 실제 본문 HTML은 05단계에서 별도로 받는다.

#### Defaults and Exceptions

- 다운로드 대상은 `data_root`와 `mode`로만 정한다.
- 필터 입력을 읽을 수 없거나 대상이 없으면 실패 처리한다.
- 각 대상은 중복되지 않은 비어 있지 않은 `acpt_no`와 ISO 날짜로 시작하는 `disclosed_at`을 가져야 한다.
- `<YYYY>`는 필터 결과의 `disclosures[].disclosed_at` 연도에서 정한다. 호환 field나 중첩된 값을 탐색하지 않으며 `acpt_no`에서 연도를 추론하지 않는다.
- 원본 화면 전체는 압축 JSON에 복사하지 않고 연도별 HTML 파일로 보존한다.

### Reuse the Parent Filter's External HTML

#### Behavior

파생 필터는 상위 기본 필터가 소유한 외부 HTML, manifest와 압축 문서 선택 정보를 그대로 사용한다. 파생 필터의 접수번호 부분집합만 상위 산출물과 대조하고 다시 내려받거나 별도 출력 폴더를 만들지 않는다.
파생 필터의 압축 실행도 상위 `compressed-external-html.json`에서 자기 멤버십과 원문 hash/size를 검증만 하며 파일을 다시 쓰지 않는다.

#### Defaults and Exceptions

- 파생 필터의 `parent_result_fingerprint`가 현재 상위 결과와 같아야 한다.
- 파생 필터의 모든 `acpt_no`가 상위 `filtered.json`, manifest와 `compressed-external-html.json`에 존재하고 각 해시 검증을 통과해야 한다.
- 상위 산출물이 없거나 미완료·손상 상태이거나 파생 필터가 stale이면 실패 처리한다.
- 누락된 항목을 KIND에서 다시 받거나 파생 필터 전용 04단계 산출물을 만드는 fallback은 사용하지 않는다.

### Retry Failed External HTML Downloads

#### Behavior

실패한 공시만 기본 5회까지 다시 요청한다.

#### Defaults and Exceptions

- 재시도 뒤에도 실패한 `acpt_no`는 최종 누락 목록에 남긴다.

### Reuse Existing External HTML

#### Behavior

구조와 원본 hash가 그대로인 기존 외부 HTML은 다시 받지 않는다.

#### Defaults and Exceptions

- 현재 파일에서 계산한 바이트 수와 SHA-256을 manifest에 기록된 값과 비교한다.
- `기존 데이터 검토`를 실행하면 현재 대상과 저장 파일 구성을 비교하고 manifest의 기준 hash를 확인한다.
- 기존 원문 무결성과 미저장 원문 수는 같은 검사 요청에서 계산한다. 첫 행에만 `검사하기`를 두고 미저장 원문 행은 검사 전 `대기`로 표시하며, 두 행 모두 독립 단계 순번을 표시하지 않는다.
- 상단 `정상`은 카드의 모든 단계가 통과한 뒤에만 붙는다. `미저장 원문 다운로드`가 남아 있으면 상단은 `검사 중`이고, 통과한 원문 검사 줄은 `정상`일 수 있다.
- 파생 필터의 검사는 상위 폴더에서 자식 접수번호 부분집합만 대조하고, 없는 원문은 미저장 건수로 보고한다. 상위 폴더의 다른 파일은 대상 외 파일로 보지 않는다.
- 파생 필터에서 미저장·손상·해시 불일치는 재사용 불가다. 이 화면에서 KIND를 다시 받지 않는다.
- 기존 HTML의 구조 판별과 SHA-256 계산은 파일을 한 번 순차 읽은 결과로 각각 수행한다.

### Build Compressed External HTML Records

#### Behavior

공시와 문서를 식별하고 문서 선택 결과를 재현하는 정보만 압축 record에 저장한다. `acpt_no`는 HTML 파일명에서 확장자를 뺀 값을 사용하고, 외부 화면에서 선택한 본문 문서 번호는 `selected_main_doc_no`에 저장한다. 필터 결과의 공시 metadata는 `records[].metadata`에 그대로 전달한다.

#### Defaults and Exceptions

- 압축할 폴더는 `input_directory`로만 받고 worker 수는 `parallel_workers`로만 받는다.
- 외부 HTML 안에 `acptNo`, `mainDoc`, `attachedDoc` 또는 각 select의 option 목록이 없으면 실패 처리한다.
- 외부 HTML에서 읽은 `acptNo`가 파일명과 다르면 실패 처리하며, 빈 `acptNo`를 파일명으로 대신하지 않는다.
- 외부 HTML의 `<YYYY>` 폴더와 manifest metadata의 `disclosed_at` 연도가 다르면 실패 처리한다.
- 첫 option이 선택되지 않은 정식 `본문선택` 또는 `첨부문서선택` 안내 option이면 빈 값과 빈 문서 번호를 허용하고 압축 record의 `docs`에서는 제외한다. 그 밖의 빈 option 값·문서 번호와 선택한 본문 문서 번호 누락은 실패 처리한다.
- 첨부문서가 없는 공시는 `첨부문서선택` 안내 option만 있어도 허용한다.
- 제목은 01단계 KIND 조건검색에서 받은 값만 쓰고 외부 HTML의 `<title>`이나 머리글로 보완하지 않는다.

### Record External HTML Provenance

#### Behavior

각 외부 HTML의 바이트 수와 SHA-256을 압축 record와 manifest에 기록하고, 같은 `acpt_no`의 원본 공시 metadata와 연결한다.

#### Defaults and Exceptions

- 저장한 `acpt_no`와 같은 원본 공시 metadata를 확정하지 못하면 manifest를 만들지 않고 실패 처리한다.

### Validate Compressed External HTML Results

#### Behavior

요청한 HTML, worker 결과와 저장한 압축 JSON의 `acpt_no` 집합이 같은지 확인한다. 압축 JSON을 저장한 뒤 파일, JSON 객체와 `records` 목록을 다시 읽어 검증한다.

#### Defaults and Exceptions

- worker 결과나 저장한 JSON에 중복·누락·추가 `acpt_no`가 있으면 실패 처리한다.

### Use a Separate Output Path

#### Behavior

표준 작업공간 밖에 외부 HTML과 압축 JSON을 저장할 수 있도록 각각의 입력·출력 경로를 받는다.

### Display External HTML Results

#### Behavior

다운로드·검증 결과를 바꾸지 않고 화면에 전달할 범위만 제한한다.

#### Defaults and Exceptions

- 회사명이나 종목 코드를 읽지 못하면 빈 값으로 둔다.
- 본문 문서 번호나 제출일을 읽지 못해도 다른 값으로 대신하지 않는다.
- 실행 결과의 진행 내역은 생성 중부터 최근 100줄만 보관한다.
