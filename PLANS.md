# Completed Changes Requiring Follow-up

## 2026-08-10 - 다운로드 검사 복원 및 검증 취소 보장

### Purpose

- 실행 중 페이지가 다시 로드되어도 저장된 검사 입력과 polling 작업을 함께 복원한다.
- KIND 검증 중 취소 요청이 들어오면 현재 네트워크 요청 이후 남은 검증을 중단한다.

### Implementation summary

- polling 저장 상태의 복원 완료 여부를 노출하고, 복원이 끝나기 전에는 저장된 검사 컨텍스트를 정리하지 않도록 변경했다.
- KIND 기존 데이터 검증에 취소 콜백을 전달하고 폴더 탐색, 작업 제출, 결과 대기 사이에서 취소를 확인하도록 변경했다.
- 새로고침 복원 순서와 KIND 검증 중 취소를 고정하는 회귀 테스트를 추가했다.

### Verification result

- `.venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -q` 통과: 340 passed, 166 skipped.
- `.venv/bin/python -m pytest tests/market_desk/test_kind_web_app.py -k 'download_inspect_folder_start_route' -q` 통과.
- `npm run build:market-desk` 프로덕션 빌드 및 TypeScript 검사 통과.
- `npm run test:frontend` 통과: 149 passed.

## 2026-08-10 - 다운로드 검사 후 KIND 검증 비동기화

### Purpose

- 폴더 검사 완료 후 KIND 검증이 Next.js 프록시 제한을 넘어 HTTP 500으로 실패하는 문제를 해결한다.

### Implementation summary

- 폴더 검사 백그라운드 작업 안에서 KIND 검증까지 수행하고 완료 결과에 검증 데이터를 포함했다.
- 프론트엔드는 작업 완료 후 동기 검증 API를 다시 호출하지 않고 작업 결과의 검증 데이터를 기존 검사 상태에 반영하도록 변경했다.
- 장시간 검증이 프록시 요청에 묶이지 않는지 확인하는 백엔드·프론트 회귀 테스트를 추가했다.

### Verification result

- `.venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -q` 통과: 338 passed, 166 skipped.
- `.venv/bin/python -m pytest tests/market_desk/test_kind_web_app.py -k 'download_inspect_folder_start_route' -q` 통과.
- `npm run build:market-desk` 프로덕션 빌드 및 TypeScript 검사 통과.
- `npm run test:frontend` 통과: 149 passed.

## 2026-08-10 - 기존 데이터 성공 상태명 통일

### Purpose

- 기존 데이터 검토 화면에서 문제없음을 나타내는 여러 상태명을 하나로 통일한다.

### Implementation summary

- 최종 판정, 단계별 성공 상태, 수동 검사 완료 알림에 공통 `정상` 문구를 적용했다.
- 설명 문장의 비교 결과와 실패 상태인 `불일치`는 진단 의미를 유지했다.
- UI 용어 계약과 회귀 테스트를 공통 성공 상태명에 맞췄다.

### Verification result

- `node --test tests/frontend/downloadStatusColors.test.mjs` 통과.
- `npm run build:market-desk` 프로덕션 빌드 통과.
- 변경 파일 대상 `git diff --check` 통과.

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
