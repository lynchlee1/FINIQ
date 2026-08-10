# Completed Changes Requiring Follow-up

## 2026-08-10 - 기존 데이터 검토 단계 버튼 배치 통일

### Purpose

- `현재 설정과 비교`의 복구 동작을 `저장 파일 구성 검사`의 검사 동작과 같은 단계 우측 버튼으로 표시한다.

### Implementation summary

- 불일치 상세 박스 안의 `저장된 설정 적용` 버튼을 제거하고 설정 비교 단계의 `action`으로 옮겼다.
- 불일치 항목 표와 저장 범위 상세는 기존 실패 상세 영역에 그대로 유지했다.
- UI 용어 계약에 두 단계 실행 버튼의 정렬 원칙을 기록하고 회귀 테스트를 추가했다.

### Verification result

- `node --test tests/frontend/downloadStatusColors.test.mjs` 통과.
- `npm run build:market-desk` 프로덕션 빌드 통과.
- 변경 파일 대상 `git diff --check` 통과.
