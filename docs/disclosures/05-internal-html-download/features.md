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
- HTML wrapper가 없는 과거 KIND 본문은 앞쪽 공백을 제외한 첫 태그가 `<P>`이고 본문에 `<TABLE>`이 있을 때만 유효한 legacy fragment로 인정한다. 일반 HTML·KIND viewer 식별자와 이 형식에 해당하지 않는 응답은 거부한다.
- 프록시 경로에서 저장하지 못한 대상은 직접 연결로 한 번 더 다운로드한다. 자동화·복구가 원본 없음 확인을 요청한 경우에는 모든 다운로드 경로 뒤에도 남은 대상을 같은 공식 KIND 문서에서 직접 재검증한다. 이때도 본문 경로가 없거나 유효한 HTML이 아니면 해당 접수번호의 정상 저장 위치에 규격화된 빈 원문 HTML을 만들고 `KIND 원본 없음` 사유를 manifest와 작업 로그에 기록한다. 연결·HTTP 오류는 기존처럼 실패로 유지한다.
- 다운로드 경로의 fallback은 한 단계뿐이다. 프록시 경로에서 마치지 못한 요청만 직접 연결로 넘긴다. 같은 연결에서 연결 오류나 timeout이 나면 정해진 횟수만큼 다시 요청하며, 다른 parser·selector·원본은 쓰지 않는다.
- 프록시 대상의 직접 연결 재시도는 같은 실행에서 직접 연결이 사용한 요청 간격과 분당 요청 이력을 이어받는다. 처음부터 직접 연결에 배정된 대상은 이 fallback으로 다시 보내지 않는다.
- 마지막 직접 재검증은 다른 원본을 찾는 fallback이 아니다. 다운로드 결과만으로는 KIND가 본문 경로를 제공하지 않은 경우와 일시적인 연결 실패를 구분할 수 없다. 같은 공식 KIND 문서를 한 번 확인해 빈 원문을 만들 수 있는 두 사유만 확정한다. 이 확인이 없으면 원본 부재를 입증할 수 없어 빈 원문을 만들지 않는다.

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
- `기존 데이터 검토`는 선택 필터와 관계없이 모든 기본·파생 모드의 대상과 저장 파일 구성을 비교하고 manifest의 기준 hash를 확인한다. 한 모드라도 미저장·손상·해시 불일치·기준 없음이 있으면 전체 판정은 `사용 불가`다. 현재 `selected_main_doc_no`와 빈 원문 파일의 규격·hash·manifest 사유가 모두 일치하는 `KIND 원본 없음`은 저장 건수에 포함해 별도로 집계하며 전체 판정을 막지 않는다.
- 검사는 아직 없는 stage 디렉터리를 만들지 않는다.
- 검사는 한 행만 사용하며 모드별 `정상`·`사용 불가` 결과와 전체 집계를 같은 카드에 표시한다. 다시 받을 대상이 있으면 같은 행의 `검사하기`를 `재다운로드`로 바꾸고 별도 행을 추가하지 않는다.
- 재다운로드 수는 파생 모드를 중복 합산하지 않고 기본 모드 소유분만 집계한다. 문제가 있는 기본 모드의 누락·손상·해시 불일치·기준 없음 파일만 다시 받고 검증된 파일은 건너뛴다.
- 재다운로드가 끝나면 서버가 모든 모드를 다시 검사하고, 화면은 같은 검사 행과 모드별 목록에 최종 결과를 유지한다. 한 기본 모드가 실패해도 나머지 복구 대상 모드는 계속 처리하고 실패 모드를 함께 보고한다.
- `KIND 원본 없음`은 파일명의 접수번호와 파일 안의 접수번호·문서 번호·사유가 manifest와 모두 일치하는 동안 재사용한다. 04단계가 선택한 문서 번호가 바뀌거나 빈 원문의 규격·hash가 달라지면 이전 기록을 무효 처리하고 새 문서를 다시 받는다. 무효 처리된 빈 원문을 다시 받지 못하면 이전 원본 없음 기록을 유지하지 않는다.
- 파생 필터의 검사는 상위 폴더에서 자식 접수번호 부분집합만 대조하고, 없는 원문은 미저장 건수로 보고한다. 상위 폴더의 다른 파일은 대상 외 파일로 보지 않는다.
- 파생 필터에서 미저장·손상·해시 불일치는 재사용 불가다. 이 화면에서 KIND를 다시 받지 않는다.
- 기존 HTML의 구조 판별과 SHA-256 계산은 파일을 한 번 순차 읽은 결과로 각각 수행한다.

### Validate Internal HTML Results

#### Behavior

요청 대상과 저장 결과의 `acpt_no` 집합이 같은지 확인한다.

#### Defaults and Exceptions

- 일반 실행 결과에 중복·누락·추가 `acpt_no`가 있으면 실패 처리한다.
- 재검증으로 확정한 빈 원문도 요청한 접수번호의 실제 HTML 파일이어야 한다. 파일 없이 manifest 예외만 남겨 누락을 통과시키지 않는다.
- 사용자가 작업을 취소하면 그 뒤 생긴 누락은 허용하되, 중복·추가 `acpt_no`는 계속 검사하고 발견하면 실패 처리한다.
- 다운로드 중 취소되면 이미 저장을 마친 HTML의 기준 hash 생성을 끝내고 그 파일만 담은 부분 manifest를 원자적으로 저장한 뒤 취소 결과를 반환한다. 아직 저장하지 못한 대상은 manifest에 넣지 않는다.

### Record Internal HTML Provenance

#### Behavior

검증을 통과한 내부 HTML을 같은 `acpt_no`의 원본 공시 metadata와 연결하고, 파일마다 바이트 수와 SHA-256을 manifest에 기록한다.

#### Defaults and Exceptions

- 저장한 `acpt_no`와 연결할 원본 metadata를 확정하지 못하거나 manifest를 저장하지 못하면 실패 처리한다.
- `KIND 원본 없음` 빈 원문도 일반 원문과 같은 방식으로 바이트 수와 SHA-256을 기록한다. 문서 번호와 누락 사유도 함께 남긴다.

### Display Internal HTML Results

#### Behavior

다운로드·검증 결과를 바꾸지 않고 화면에 전달할 범위만 제한한다.

- 실행 결과의 진행 내역은 생성 중부터 최근 100줄만 보관한다.
