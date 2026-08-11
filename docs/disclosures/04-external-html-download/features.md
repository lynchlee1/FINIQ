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
- 기존 HTML의 구조 판별과 SHA-256 계산은 파일을 한 번 순차 읽은 결과로 각각 수행한다.

### Build Compressed External HTML Records

#### Behavior

공시와 문서를 식별하고 문서 선택 결과를 재현하는 정보만 압축 record에 저장한다. `acpt_no`는 HTML 파일명에서 확장자를 뺀 값을 사용하고, 외부 화면에서 선택한 본문 문서 번호는 `selected_main_doc_no`에 저장한다. 필터 결과의 공시 metadata는 `records[].metadata`에 그대로 전달한다.

#### Defaults and Exceptions

- 압축할 폴더는 `input_directory`로만 받고 worker 수는 `parallel_workers`로만 받는다.
- 외부 HTML 안에 `acptNo`, `mainDoc`, `attachedDoc` 또는 각 select의 option 목록이 없으면 실패 처리한다.
- 외부 HTML에서 읽은 `acptNo`가 파일명과 다르면 실패 처리하며, 빈 `acptNo`를 파일명으로 대신하지 않는다.
- 외부 HTML의 `<YYYY>` 폴더와 manifest metadata의 `disclosed_at` 연도가 다르면 실패 처리한다.
- 문서 option 값이나 문서 번호가 비어 있거나 선택한 본문 문서 번호를 찾지 못하면 실패 처리한다.
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
