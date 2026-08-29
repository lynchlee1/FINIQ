# 05 공시원문 내부 저장

## 목적

KIND 본문 HTML을 mode와 연도에 따라 나누어 저장한다.

## 단계 계약

공통 실행·재사용 규칙은 [공시 처리 공통 계약](common.md)을 따른다. 아래에는 05단계의 추가 조건만 적는다.

### 내부 HTML 대상 결정

04단계가 외부 화면에서 확정한 `records[].selected_main_doc_no`를 본문 문서 번호로 사용한다. 저장 연도는 03단계 필터 결과의 `disclosures[].disclosed_at`을 04단계가 `records[].metadata.disclosed_at`으로 전달한 값에서 정한다.

#### 제약과 분기

- 일반 실행 입력은 `compressed-external-html.json`만 허용한다.

#### 중단 조건

- record가 객체가 아니거나 비어 있지 않은 `acpt_no`가 없으면 실패 처리한다.
- `selected_main_doc_no`가 비어 있거나 `records[].docs`에 `selected=true`인 `mainDoc`이 정확히 하나가 아니거나, 그 `doc_no`와 `selected_main_doc_no`가 다르면 다운로드 전에 실패 처리한다.
- `metadata.disclosed_at`이 없거나 유효한 ISO 날짜로 시작하지 않으면 `records[].year`나 `acpt_no`로 저장 연도를 대신하지 않고 실패 처리한다.
- `records[].acpt_no`가 중복되면 실패 처리한다.

### 내부 HTML 다운로드

선택한 공시에서 받은 KIND 본문 HTML을 원본 식별값과 함께 저장한다.

- 각 공시 안의 KIND 요청 순서는 같은 컴퓨터 안에서 유지한다.
- 완료 파일 목록은 입력 공시 순서로 반환한다.

#### 제약과 분기

- 새로 받은 본문은 기존 파일 옆의 고유한 임시 파일에 저장한다. 임시 파일이 HTML 판별 검사를 통과할 때만 기존 본문과 원자적으로 교체하며, 실패하면 임시 파일만 삭제하고 기존 정상 본문과 manifest를 유지한다.
- 프록시 경로에서 저장하지 못한 대상은 직접 연결로 한 번 더 다운로드한다. 자동화·복구가 원본 없음 확인을 요청한 경우에는 모든 다운로드 경로 뒤에도 남은 대상을 같은 공식 KIND 문서에서 직접 재검증한다. 본문 경로가 없을 때만 해당 접수번호의 정상 저장 위치에 규격화된 빈 원문 HTML을 만들고 `KIND 원본 없음` 사유를 manifest와 작업 로그에 기록한다. 유효하지 않은 HTML과 연결·HTTP 오류는 실패로 유지하며 기존 정상 본문과 manifest를 보존한다.
- 다운로드 경로의 fallback은 한 단계뿐이다. 프록시 경로에서 마치지 못한 요청만 직접 연결로 넘긴다. 같은 연결에서 연결 오류나 timeout이 나면 정해진 횟수만큼 다시 요청하며, 다른 parser·selector·원본은 쓰지 않는다.
- 프록시 대상의 직접 연결 재시도는 같은 실행에서 직접 연결이 사용한 요청 간격과 분당 요청 이력을 이어받는다. 처음부터 직접 연결에 배정된 대상은 이 fallback으로 다시 보내지 않는다.
- 마지막 직접 재검증은 다른 원본을 찾는 fallback이 아니다. 다운로드 결과만으로는 KIND가 본문 경로를 제공하지 않은 경우와 일시적인 연결 실패를 구분할 수 없다. 같은 공식 KIND 문서를 한 번 확인해 본문 경로가 없다는 사실을 확정하며, 이 확인 없이는 빈 원문을 만들지 않는다.

### 상위 필터의 내부 HTML 재사용

파생 필터는 상위 기본 필터의 내부 HTML과 manifest를 사용한다.

#### 중단 조건

- 상위 04단계 record의 `selected_main_doc_no`, 상위 05단계 manifest와 내부 HTML 해시가 파생 대상과 일치하지 않으면 재사용을 중단한다.

### 기존 내부 HTML 재사용

#### 제약과 분기

- `기존 데이터 검토`는 선택 필터와 관계없이 모든 기본·파생 모드의 대상과 저장 파일 구성을 비교하고 manifest의 기준 hash를 확인한다. 한 모드라도 미저장·손상·해시 불일치·기준 없음이 있으면 전체 판정은 `사용 불가`다. 현재 `selected_main_doc_no`와 빈 원문 파일의 규격·hash·manifest 사유가 모두 일치하는 `KIND 원본 없음`은 저장 건수에 포함해 별도로 집계하며 전체 판정을 막지 않는다.
- 검사는 아직 없는 stage 디렉터리를 만들지 않는다.
- 검사는 한 행만 사용하며 모드별 `정상`·`사용 불가` 결과와 전체 집계를 같은 카드에 표시한다. 다시 받을 대상이 있으면 같은 행의 `검사하기`를 `재다운로드`로 바꾸고 별도 행을 추가하지 않는다.
- 재다운로드 수는 파생 모드를 중복 합산하지 않고 기본 모드 소유분만 집계한다. 문제가 있는 기본 모드의 누락·손상·해시 불일치·기준 없음 파일만 다시 받고 검증된 파일은 건너뛴다.
- 재다운로드가 끝나면 서버가 모든 모드를 다시 검사하고, 화면은 같은 검사 행과 모드별 목록에 최종 결과를 유지한다. 한 기본 모드가 실패해도 나머지 복구 대상 모드는 계속 처리하고 실패 모드를 함께 보고한다.
- `KIND 원본 없음`은 파일명의 접수번호와 파일 안의 접수번호·문서 번호·사유가 manifest와 모두 일치하는 동안 재사용한다. 04단계가 선택한 문서 번호가 바뀌거나 빈 원문의 규격·hash가 달라지면 이전 기록을 무효 처리하고 새 문서를 다시 받는다. 무효 처리된 빈 원문을 다시 받지 못하면 이전 원본 없음 기록을 유지하지 않는다.

### 내부 HTML 결과 검증

요청 대상과 저장 결과의 `acpt_no` 집합이 같은지 확인한다.

#### 제약과 분기

- 재검증으로 확정한 빈 원문도 요청한 접수번호의 실제 HTML 파일이어야 한다. 파일 없이 manifest 예외만 남겨 누락을 통과시키지 않는다.
- 사용자가 작업을 취소하면 그 뒤 생긴 누락은 허용하되, 중복·추가 `acpt_no`는 계속 검사하고 발견하면 실패 처리한다.
- 다운로드 중 취소되면 이미 저장을 마친 HTML의 기준 hash 생성을 끝내고 그 파일만 담은 부분 manifest를 원자적으로 저장한 뒤 취소 결과를 반환한다. 아직 저장하지 못한 대상은 manifest에 넣지 않는다.

#### 중단 조건

- 일반 실행 결과에 중복·누락·추가 `acpt_no`가 있으면 실패 처리한다.
- 일반 실행의 대상-결과 집합 검증이 실패하면 기존 정상 manifest를 새 부분 manifest로 덮어쓰지 않는다.

### 내부 HTML 출처 기록

#### 제약과 분기

- `KIND 원본 없음` 빈 원문도 일반 원문과 같은 방식으로 바이트 수와 SHA-256을 기록한다. 문서 번호와 누락 사유도 함께 남긴다.

#### 중단 조건

- manifest를 저장하지 못하면 실패 처리한다.

## 파일과 저장 형식

- `<data_root>/04-external-html-compress/<mode>/compressed-external-html.json`을 입력으로 받아 `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`에 본문 HTML을, `<data_root>/05-internal-html-download/<mode>/kind_disclosure_html_manifest.json`에 원본 연결 정보를 저장한다.
- 파생 필터 `<parent_mode>/<mode>`는 상위 `<data_root>/04-external-html-compress/<parent_mode>/compressed-external-html.json`과 `<data_root>/05-internal-html-download/<parent_mode>` 산출물을 사용한다. 자식 `mode`나 `subfilters/<mode>`의 05단계 출력 폴더는 만들지 않는다.

### `<data_root>/04-external-html-compress/<mode>/compressed-external-html.json`

- 입력 형식은 [04단계](04-external-html.md)의 `compressed-external-html.json` 계약을 따른다.

## 로컬 프록시 설정

Proton VPN 앱 자체는 시스템 기본 경로 하나만 만든다. 여러 IP 경로를 함께 쓰려면 Proton 계정에서 경로마다 서로 다른 WireGuard 설정 파일을 내려받고, 각 파일을 별도 `wireproxy` 프로세스로 실행한다. 비밀키가 들어 있는 WireGuard 설정 파일은 프로젝트에 저장하거나 커밋하지 않는다.

WireGuard 설정을 직접 복사하지 않고 불러오는 최소 `wireproxy` 설정은 다음과 같다.

```ini
WGConfig = /absolute/path/to/proton-route-1.conf

[http]
BindAddress = 127.0.0.1:25001
```

두 번째 설정은 다른 Proton WireGuard 파일과 포트 `25002`를 사용한다. `com.finiq.wireproxy.routeN`은 포트 `25000 + N`을 사용하고 등록 범위는 1~7이다. FINIQ는 저장된 프록시 URL의 실제 포트로 이 범위에 해당하는 LaunchAgent만 실행한다. 다른 localhost 포트는 사용자가 관리하는 프록시로 보고 lifecycle 대상에 넣지 않는다.

```shell
wireproxy -c /absolute/path/to/wireproxy-route-1.conf
wireproxy -c /absolute/path/to/wireproxy-route-2.conf
```

준비된 프록시는 실행 중인 FINIQ 서버에 저장한다.

```shell
curl -X POST http://127.0.0.1:8765/api/settings \
  -H 'Content-Type: application/json' \
  -d '{"kind_proxy_urls":["http://127.0.0.1:25001","http://127.0.0.1:25002"]}'
```

설정 뒤의 04·05단계 저장 작업부터 직접 연결과 등록된 프록시를 함께 사용한다. FINIQ 백엔드는 시작할 때 설정 URL의 포트와 일치하는 `com.finiq.wireproxy.routeN` LaunchAgent를 실행하고 종료할 때 함께 정지한다. 시작 도중 한 경로라도 실패하면 앞서 실행한 경로를 정지하고 백엔드 시작을 중단한다. FINIQ는 WireGuard 비밀키를 읽지 않는다.

### `<data_root>/05-internal-html-download/<mode>/<YYYY>/<acpt_no>.html`

- KIND에서 받은 공시 본문 HTML을 원본 구조로 보존한 출력 파일이다.
- `<YYYY>`는 입력 record의 `metadata.disclosed_at` 연도다.

### `<data_root>/05-internal-html-download/<mode>/kind_disclosure_html_manifest.json`

- [공통 HTML manifest 계약](common.md#html-manifest)을 따른다.
- 파생 필터 작업은 상위 manifest와 HTML 중 자식 `filtered.json`의 `acpt_no` 부분집합만 검증해 사용하며 `selected_main_doc_no`도 상위 04단계 record와 일치해야 한다.
