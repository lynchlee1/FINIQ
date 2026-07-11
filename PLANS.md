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
