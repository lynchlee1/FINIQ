# Internal HTML Download Features

## Purpose

KIND 본문 HTML을 mode와 연도에 따라 나누어 저장한다.

## Features

### Determine Internal HTML Targets

#### Behavior

04단계가 외부 화면에서 확정한 `records[].selected_main_doc_no`를 본문 문서 번호로 사용한다. 저장 연도는 03단계 필터 결과의 `disclosures[].disclosed_at`을 04단계가 `records[].metadata.disclosed_at`으로 전달한 값에서 정한다.

#### Defaults and Exceptions

- 일반 실행 입력은 `compressed-external-html.json`만 허용한다.
- record가 객체가 아니거나 비어 있지 않은 `acpt_no`가 없으면 실패 처리한다.
- `selected_main_doc_no`가 비어 있거나 연도별 외부 HTML의 `mainDoc`에서 직접 선택한 값이 아니면 실패 처리한다.
- `metadata.disclosed_at`이 없거나 유효한 ISO 날짜로 시작하지 않으면 `records[].year`나 `acpt_no`로 저장 연도를 대신하지 않고 실패 처리한다.
- 연도별 외부 HTML을 직접 입력하면 파일이 실제로 들어 있는 4자리 연도 폴더를 저장 연도로 사용한다.
- `records[].acpt_no`가 중복되면 실패 처리한다.

### Download Internal HTML

#### Behavior

선택한 공시에서 받은 KIND 본문 HTML을 원본 식별값과 함께 저장한다.

- 공시 대상은 설정한 `max_workers` 범위에서 병렬 처리한다.
- 각 공시 안의 KIND 요청 순서는 유지하고, 모든 worker와 연도 그룹은 같은 요청 간격 제한기를 공유한다.
- 완료 파일 목록은 입력 공시 순서로 반환한다.

#### Defaults and Exceptions

- 새로 내려받은 본문이 HTML 판별 검사를 통과하지 못하면 방금 저장한 본문 파일을 삭제하고 실패 처리한다.

### Reuse the Parent Filter's Internal HTML

#### Behavior

파생 필터는 상위 기본 필터가 소유한 내부 HTML과 manifest를 그대로 사용한다. 파생 필터의 접수번호 부분집합만 검증하며 본문을 다시 내려받거나 별도 출력 폴더를 만들지 않는다.

#### Defaults and Exceptions

- 현재 상위 결과와 파생 필터의 `parent_result_fingerprint`가 일치해야 한다.
- 파생 대상마다 상위 04단계 record의 `selected_main_doc_no`, 상위 05단계 manifest와 내부 HTML의 해시가 모두 일치해야 한다.
- 상위 산출물이 없거나 미완료·손상 상태이거나 파생 필터가 stale이면 실패 처리한다.
- 누락된 본문을 KIND에서 다시 받거나 파생 필터 전용 05단계 산출물을 만드는 fallback은 사용하지 않는다.

### Reuse Existing Internal HTML

#### Behavior

구조와 원본 hash가 그대로인 기존 본문 HTML은 다시 받지 않는다.

#### Defaults and Exceptions

- HTML 식별 검사를 통과한 파일에서 바이트 수와 SHA-256을 계산해 manifest 기준값과 비교한다.
- `기존 데이터 검토`를 실행하면 현재 대상과 저장 파일 구성을 비교하고 manifest의 기준 hash를 확인한다.
- 기존 HTML의 구조 판별과 SHA-256 계산은 파일을 한 번 순차 읽은 결과로 각각 수행한다.

### Validate Internal HTML Results

#### Behavior

요청 대상과 저장 결과의 `acpt_no` 집합이 같은지 확인한다.

#### Defaults and Exceptions

- 일반 실행 결과에 중복·누락·추가 `acpt_no`가 있으면 실패 처리한다.
- 사용자가 작업을 취소하면 그 뒤 생긴 누락은 허용하되, 중복·추가 `acpt_no`는 계속 검사하고 발견하면 실패 처리한다.
- 다운로드 또는 기준 해시 생성 중 취소되면 manifest를 새로 저장하지 않고 취소 결과를 반환한다.

### Record Internal HTML Provenance

#### Behavior

검증을 통과한 내부 HTML을 같은 `acpt_no`의 원본 공시 metadata와 연결하고, 파일마다 바이트 수와 SHA-256을 manifest에 기록한다.

#### Defaults and Exceptions

- 저장한 `acpt_no`와 연결할 원본 metadata를 확정하지 못하거나 manifest를 저장하지 못하면 실패 처리한다.

### Display Internal HTML Results

#### Behavior

다운로드·검증 결과를 바꾸지 않고 화면에 전달할 범위만 제한한다.

- 실행 결과의 진행 내역은 생성 중부터 최근 100줄만 보관한다.
