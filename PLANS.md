# Completed Changes Requiring Follow-up

## 2026-07-12 — 공시 자동화 드래그 범위와 Pending 판단 UI

### Purpose

- 중복된 시작·종료 dropdown 없이 작업 박스를 직접 드래그해 연속 실행 범위를 정한다.
- 범위 밖 판단 설정은 상세 form을 렌더링하지 않고 잠긴 한 줄 카드로 표시한다.
- 원문 준비 이후 목차 조합에 사용자 판단이 필요하면 workflow를 `Pending`으로 표시하고
  기존 `후속 실행`으로 이어간다.

### Implementation summary

- 작업 범위 선택기를 pointer capture 기반의 7개 박스 drag control로 교체했다. 시작점에는
  play icon, 끝점에는 flag icon을 표시하고 범위 사이 작업은 항상 연속 선택한다.
- 검색 조건, 공시 종류, 공시 조건, 목차 조합 판단이 실행 범위 밖이면 기존 제목과 lock
  icon만 있는 비대화형 `DisclosureLockedSettingsCard`로 대체한다.
- 목차 조합 카드는 원문 준비 전 `Pending`을 표시하고, 새 조합을 받은 뒤에는 결정되지 않은
  조합과 작업표 상태를 `Pending`으로 표시한다. 기존 needs-review backend 중단점과
  `후속 실행` 계약은 유지해 worker를 점유한 채 대기하지 않는다.
- 기존 상세 화면과 공용 검색·필터·목차 component는 유지했다.

### Verification

- TypeScript 검사와 MarketDesk production build가 통과했다.
- 자동화 UI 및 navigation 집중 frontend test 9건이 통과했다.
- 실제 브라우저에서 변환부터 내부 저장까지 drag 선택 시 중간 작업이 연속 선택되고 검색
  관련 카드만 잠기는 것을 확인했다. 범위를 목차 분리까지 늘리면 `Pending`이 표시됐고
  browser console 오류는 없었다.
- 전체 frontend test는 88건 중 87건이 통과했다. 남은 1건은 기존
  `html-section-split` settings store 구조분해 기대값 불일치다.
- 실제 `resources/`는 읽거나 변경하지 않았다.
