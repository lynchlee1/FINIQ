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

- 공시 대상은 직접 연결과 `kind_proxy_urls`에 명시한 localhost HTTP 프록시로 나눈 뒤 전체 `max_workers`를 각 연결에 배정해 병렬 처리한다.
- 각 연결은 별도 HTTP 세션, 분당 요청 한도와 요청 간격을 사용한다.
- 각 공시 안의 KIND 요청 순서는 같은 컴퓨터 안에서 유지한다.
- 완료 파일 목록은 입력 공시 순서로 반환한다.

#### Defaults and Exceptions

- 프록시 주소가 없으면 0번 직접 연결 한 개만 사용한다. 현재 CPU 개수보다 하나 적은 수의 프록시를 추가할 수 있고, 직접 연결을 포함한 전체 경로 수는 현재 CPU 개수와 같다.
- 모든 연도의 대상을 한 실행에서 처리해 요청 간격과 분당 한도가 연도 경계에서 초기화되지 않게 한다.
- 새로 내려받은 본문이 HTML 판별 검사를 통과하지 못하면 방금 저장한 본문 파일을 삭제하고 실패 처리한다.
- 재다운로드에서도 저장하지 못한 대상은 직접 연결로 한 번 더 조회한다. 이 재검증에서도 KIND가 본문 경로를 주지 않거나 유효한 HTML을 반환하지 않으면 `KIND 원본 없음`으로 manifest와 작업 로그에 기록하고, 연결·HTTP 오류는 기존처럼 실패로 유지한다.

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
- `기존 데이터 검토`를 실행하면 선택 필터와 무관하게 모든 기본·파생 모드의 대상과 저장 파일 구성을 비교하고 manifest의 기준 hash를 확인한다. 한 모드라도 미저장·손상·해시 불일치·기준 없음이 있으면 전체 판정은 `사용 불가`다. 현재 `selected_main_doc_no`와 일치하는 `KIND 원본 없음` 기록은 미저장 대상과 분리해 표시하며 전체 판정을 막지 않는다.
- 검사는 아직 없는 stage 디렉터리를 만들지 않는다.
- 검사는 한 행만 사용하며 모드별 `정상`·`사용 불가` 결과와 전체 집계를 같은 카드에 표시한다. 다시 받을 대상이 있으면 같은 행의 `검사하기`를 `재다운로드`로 바꾸고 별도 행을 추가하지 않는다.
- 재다운로드 수는 파생 모드를 중복 합산하지 않고 기본 모드 소유분만 집계한다. 문제가 있는 기본 모드의 누락·손상·해시 불일치·기준 없음 파일만 다시 받고 검증된 파일은 건너뛴다.
- 재다운로드가 끝나면 서버가 모든 모드를 다시 검사하고, 화면은 같은 검사 행과 모드별 목록에 최종 결과를 유지한다. 한 기본 모드가 실패해도 나머지 복구 대상 모드는 계속 처리하고 실패 모드를 함께 보고한다.
- `KIND 원본 없음`은 접수번호와 문서 번호가 같은 동안 재사용한다. 04단계가 선택한 문서 번호가 바뀌면 이전 기록을 재사용하지 않고 새 문서를 다시 받는다.
- 파생 필터의 검사는 상위 폴더에서 자식 접수번호 부분집합만 대조하고, 없는 원문은 미저장 건수로 보고한다. 상위 폴더의 다른 파일은 대상 외 파일로 보지 않는다.
- 파생 필터에서 미저장·손상·해시 불일치는 재사용 불가다. 이 화면에서 KIND를 다시 받지 않는다.
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
