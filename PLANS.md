# Completed Changes

## 2026-07-11 — 공시 1–7 자동화·증분 이어받기 설계

### Purpose

- 1·3·6번의 판단 설정으로 1–7번을 자동 계획하면서 각 단계를 개별 toggle/실행할 수
  있는 구조를 정의한다.
- 신규·변경 데이터만 처리하고, KIND의 내림차순 page 이동과 분당 100회 제한에서도
  누락·중복·과도한 재요청을 피하는 이어받기 계약을 정한다.

### Implementation summary

- `docs/disclosure-incremental-workflow-design.md`에 versioned profile, SQLite 실행 원장,
  date-window crawl/audit, entity fingerprint, immutable generation, correction-family
  dependency closure, Stage 6 review flow, KIND 전역 request gateway 설계를 기록했다.
- 자동화 v1은 profile당 Stage 3 selection/parser route 하나, single workflow executor,
  명시 `동기화` trigger로 제한하고 scheduler·분산 queue·multi-stream은 후속 범위로 뒀다.
- `docs/ui-terminology.md`에 `공시 자동화`, `실행 계획`, `동기화`, `판단 필요`,
  `이어서 실행`, 계획 상태와 재검사 상태 용어를 추가했다.
- 런타임 코드는 변경하지 않았다.

### Verification

- 설계 문서의 status, fingerprint, page drift, audit, retry/redirect, resume/review,
  publish invariant를 상호 검토했다.
- 프로젝트 금지 경로인 `resources/`는 읽거나 변경하지 않았다.
- 문서 diff와 Markdown 구조 검사를 완료했다.

## 2026-07-11 — 최종 공시 데이터의 KIND 공시시간 보존

### Purpose

- KIND 공시목록의 `disclosed_at` 날짜·시간을 SoT로 삼아 Stage 7 최종
  `parsed-<mode>.json`의 각 record에 보존한다.
- DART의 날짜 metadata나 parser 반환값이 KIND 공시시간을 덮어쓰지 않게 한다.

### Implementation summary

- `filtered.json.disclosures[].disclosed_at`을 HTML parse metadata index에 포함하고 최종
  `records[].disclosed_at`에 그대로 저장한다.
- legacy 인접 metadata 경로를 유지하면서 canonical workspace에서는
  `03-filter/filtered.json`과 `04-external/compressed-external-html.json`을 명시적으로
  Stage 7에 전달한다.
- 명시한 metadata 파일이 없으면 시간을 조용히 누락하지 않고 실행을 실패시킨다.

### Verification

- `HH:MM` 보존, 저장 JSON 재로드, parser 값보다 KIND 값 우선, canonical workspace의
  Stage 3→7 metadata 연결, 명시 metadata 누락 실패를 합성 fixture로 확인했다.
- 보호된 parser 데이터 구조 문서는 변경하지 않았고 `resources/`는 읽거나 변경하지
  않았다.

## 2026-07-11 — KIND↔DART 연결 및 공시 data workspace 기반

### Purpose

- KIND `acpt_no`/`doc_no`와 OpenDART `rcept_no`를 원문 HTML 다운로드 없이 신뢰 가능한
  evidence로 연결한다.
- DART에 확실히 없는 공시와 조회·매칭하지 못한 공시를 구분한다.
- 기존 1–7 작업이 공통 `<data_root>/01-list` … `07-converted/<mode>` 구조를 선택적으로
  사용할 수 있게 한다.

### Implementation summary

- `OpenDartClient`를 추가해 `corpCode.xml`과 `list.json`만 호출하고, 회사별 pending
  접수일 범위의 전 page를 조회해 날짜, 제목, 정정 여부, 제출인으로 유일한 고신뢰
  후보만 연결한다.
- 연결 결과를 parser record가 아닌 `01-list/dart-links` sidecar에 저장하고
  `matched`, `confirmed_absent`, `unresolved`, `ambiguous`, `lookup_failed` 상태와 query/candidate
  evidence를 보존한다.
- 동일 matched input은 재사용하고, 부재 확인은 기본 7일 cache하며, 회사코드 목록도 7일
  cache한다. DART 원문 HTML과 API key는 artifact에 저장하지 않는다.
- canonical workspace 생성기와 기존 Stage 1–7 handler의 `data_root` 기본 경로 adapter를
  추가했다. 명시한 기존 경로는 그대로 우선한다.
- workspace 준비, DART 연결 direct/background/status/cancel API를 추가하고 JSON write를
  원자적 replace로 전환했다.
- 전체 영속 planner/ledger와 증분 generation publish는 후속 구현 범위로 유지한다.

### Verification

- 회사/날짜/제목 exact match, 정정공시 분리, 연도 경계, 모호 후보, 잘못된 후보 metadata,
  incomplete/API failure, 확정 부재, cache 재사용/만료, 중복 `acpt_no`, 전 page pagination,
  DART HTML 미호출, workspace Stage 1–7 경로를 unit/API test로 확인했다.
- 관련 MarketDesk 회귀 test와 diff/static 검사를 실행했다.
- 프로젝트 금지 경로인 `resources/`는 읽거나 변경하지 않았다.

## 2026-07-11 — 기존 공시 1–7 화면의 canonical workspace 자동 적용

### Purpose

- 기존 공시 상세 workflow에서도 `output_root` 하나만 지정하면 `01-list`부터
  `07-converted/<mode>`까지 입력·출력 경로가 자동 연결되게 한다.
- 사용자 지정 stage 경로는 유지하면서 분할 저장을 기본값으로 적용한다.

### Implementation summary

- 공통 workspace-to-settings mapping을 추가하고, `output_root` 저장 시 stage directory와
  manifest를 생성한 뒤 기존 설정 전체를 canonical 경로로 갱신한다.
- parser mode만 바꾸면 `07-converted/<mode>` 경로만 갱신하고, 같은 요청에 명시한 개별
  stage 경로는 override로 보존한다.
- 기존 1–7 GUI payload에 `data_root`를 연결하고 설정 저장 응답의 전체 mapping을 즉시
  반영한다. Stage 4·5 화면의 연도별 분할 저장 기본값을 활성화했다.
- Stage 2 output을 `02-table` root로 통일하고 Stage 3/DART가 실제
  `*_shards/*.sqlite_manifest.json`을 directory에서 resolve하게 했다.
- Stage 7 실행·미리보기·필터 후보가 canonical Stage 3/4 metadata를 동일하게 읽도록
  연결했다.

### Verification

- root-only 설정 저장, stage directory/manifest 생성, 누락된 legacy 설정 기본값,
  명시 override 보존, parser mode 전환, Stage 1–7 경로 mapping을 합성 임시 경로로
  검증했다.
- 관련 backend 회귀 테스트, Python compile, frontend TypeScript 검사를 실행했다.
- 실제 `resources/`는 읽거나 변경하지 않았다.

## 2026-07-11 — 공시 workspace·DART 연결 correctness review

### Purpose

- 최근 추가한 공시 workspace, DART 연결, KIND 공시시간 보존 코드의 cache 신뢰,
  파일 소유권, 설정 영속성, metadata 완전성 edge case를 검토한다.
- 손상되거나 불완전한 artifact를 재사용하거나 사용자 파일을 덮어쓰는 동작을 차단한다.

### Implementation summary

- OpenDART HTTP/API-status 재시도를 같은 bounded attempt 예산으로 통합하고 실제 요청
  횟수를 query evidence에 반영했다. query count 불일치와 잘못된 후보 날짜는
  `confirmed_absent`로 승격하지 않는다.
- DART cached match는 matcher version, input fingerprint, complete query, 유효한
  `rcept_no`를 모두 확인한 뒤에만 재사용한다. 미래 cache timestamp와 비-object input을
  거부하고, DART 소유가 아닌 manifest·연도 partition·cache 파일은 덮어쓰거나 삭제하지
  않는다.
- workspace manifest의 기존 parser mode를 보존하고, 같은 이름의 비-FINIQ manifest를
  덮어쓰지 않는다.
- 설정 JSON을 임시 파일과 atomic replace로 저장하고, 빈 root/mode와 workspace·disk
  저장 실패 시 in-memory 설정을 rollback한다. frontend의 optimistic 설정도 API 실패 시
  이전 값으로 복구한다.
- canonical Stage 7은 명시한 KIND metadata가 모든 HTML의 유효한 `YYYY-MM-DD HH:MM`
  공시시간을 포함하는지 확인한다. 중복 KIND/external metadata를 거부하고 parse 결과를
  atomic JSON으로 기록한다.

### Verification

- 각 결함을 재현하는 회귀 테스트를 먼저 추가해 실패를 확인한 뒤 수정했다.
- DART cache/output ownership, OpenDART retry/count, workspace manifest, settings rollback,
  KIND 공시시간 coverage·형식·중복과 기존 parse metadata/family 동작을 합성 임시 경로로
  검증했다.
- Python compile, frontend TypeScript 검사와 production build를 실행했다.
- 실제 `resources/`는 읽거나 변경하지 않았다.
