# 2026-06-14 Quantiwise 작업 실행 버튼 표준화

## Purpose
- Quantiwise 변환/병합 화면의 실행 버튼 영역을 `공시내역 다운로드`의 `작업 실행` 카드 패턴과 맞춘다.

## Implementation Summary
- Quantiwise 변환/병합 실행 카드에 `Run` eyebrow와 `작업 실행` 제목을 적용했다.
- 실행/중단 버튼을 `grid gap-3 md:grid-cols-2`와 `w-full` 버튼 형태로 맞췄다.
- 변환/병합별 버튼명을 `실행`으로 통일하고, 기능 맥락은 페이지 제목에서 제공하게 했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: in-app Browser check on `http://localhost:3000/utility/assets-excel/convert` and `/merge` confirming `Run`, `작업 실행`, `실행`, and `작업 중단` render in the run card.

# 2026-06-14 Quantiwise 변환 전 확인 자동화

## Purpose
- `Quantiwise - 변환하기`에서 별도 확인 버튼을 누른 뒤 다시 변환을 눌러야 하는 흐름을 줄인다.

## Implementation Summary
- `Quantiwise 변환` 실행 시 저장 없이 Excel Sheet/계정 매핑, skipped Sheet, 충돌, 기존 출력 여부를 자동 확인하게 했다.
- 별도 `변환 전 확인` 버튼을 제거하고, 선택/옵션이 바뀌었을 때도 실행 시 다시 확인하도록 안내한다.
- 변환 전 확인에서 값 충돌이 발견되면 실제 변환을 시작하지 않고 충돌 확인을 요청한다.
- `docs/ui-terminology.md`와 `docs/assets-excel-conversion.md`에도 같은 용어를 반영했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: in-app Browser check on `http://localhost:3000/utility/assets-excel/convert` confirming the standalone `변환 전 확인` button is gone and `Quantiwise 변환` remains.

# 2026-06-14 Quantiwise 사이드바 위계 분리

## Purpose
- `외부 데이터 변환`과 같은 사이드바 위계에 `Quantiwise` 그룹을 만든다.
- `Quantiwise` 아래에는 `미리보기`, `저장하기` 항목을 둔다.

## Implementation Summary
- 공시데이터 구축 사이드바에서 `Quantiwise - 미리보기`, `Quantiwise - 저장하기`를 `외부 데이터 변환` 그룹에서 분리했다.
- 새 `Quantiwise` 그룹의 하위 항목은 각각 `미리보기`, `저장하기`로 표시하고 기존 라우트는 유지했다.
- `docs/ui-terminology.md`에 Quantiwise 사이드바 그룹과 하위 항목 용어를 추가했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-14 Quantiwise 미리보기/저장하기 분리 및 데이터 경로 라벨 통일

## Purpose
- Quantiwise 기능을 `Quantiwise - 미리보기`와 `Quantiwise - 저장하기`로 분리한다.
- Quantiwise 저장은 개별 파일 선택 없이 원본 데이터 경로 아래 전체 Excel을 대상으로 실행한다.
- 화면의 `저장 경로`/`저장 폴더` 라벨을 더 범용적인 `데이터 경로`로 통일한다.

## Implementation Summary
- `/utility/assets-excel`은 `Quantiwise - 미리보기`, `/utility/assets-excel/save`는 `Quantiwise - 저장하기`로 라우트와 사이드바 항목을 분리했다.
- Quantiwise 화면에서 개별 파일 체크박스, 전체 선택/해제, 파일명 필터를 제거했다.
- Quantiwise API와 프론트 요청에 `source_directory`를 추가해 사용자가 고른 원본 데이터 경로를 기준으로 목록, Sheet 미리보기, 사전 점검, 저장을 수행하게 했다.
- 저장하기는 `source_directory` 아래 전체 Excel 파일을 대상으로 사전 점검/변환한다.
- 주요 화면 라벨의 `저장 경로`/`저장 폴더` 표현을 `데이터 경로`로 바꿨다.
- `docs/ui-terminology.md`와 `docs/assets-excel-conversion.md`에 새 명칭과 경로 기반 실행 규칙을 반영했다.

## Verification
- Passed: `python3 -m pytest tests/test_assets_excel.py -q`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-14 우측 실행 현황/알림 역할 분리

## Purpose
- 우측 `실행 현황`과 `알림` 패널의 역할을 분리해 페이지마다 같은 아이콘이 다른 의미로 보이는 문제를 줄인다.

## Implementation Summary
- `실행 현황`은 정상적인 실행 상태, 텍스트 로그, 진행 메시지, 완료 결과를 보여주는 영역으로 사용한다.
- `알림`은 오류, 경고, 삭제 확인, 사용자 조치가 필요한 항목처럼 주의가 필요한 내용만 보여주는 영역으로 사용한다.
- 페이지별 실행 내용이 서로 달라 `작업 상태`, `진행 요약` 같은 고정 칸을 강제하지 않는다.
- 공시내역 다운로드처럼 텍스트 출력 중심의 실행 현황 UI를 기준으로 삼고, 필요한 페이지부터 같은 패널 역할 기준을 적용한다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: in-app Browser check on `http://localhost:3000/download` for `실행 현황` and `알림` panel rendering.

# 2026-06-14 우측 실행 현황/알림 deep inspection 보강

## Purpose
- 우측 `실행 현황` 내부 UI를 공시내역 다운로드처럼 텍스트 출력 중심으로 더 강하게 통일한다.
- `알림` 패널에서 정상 상태 로그가 반복 표시되지 않도록 오류, 경고, 삭제 확인, 사용자 조치 필요 항목만 남긴다.

## Deep Inspection
- 1차: 전체 `ActionDock` 사용처와 `/download`의 직접 구현 패널을 조사해 13개 공통 사용처와 1개 직접 구현 패널을 확인했다.
- 2차: `실행 현황`에 남아 있던 카드형 요약, `작업 상태` 고정 라벨, 일반 div 요약을 식별했다.
- 3차: `알림` 패널에서 `JobStatusLogger`가 재사용되어 정상 상태 로그가 알림처럼 보일 수 있는 지점을 식별했다.

## Implementation Summary
- 홈, 회사 그래프, Quantiwise 변환/병합, HTML 파싱, 공시내역 다운로드, 테이블 생성 화면의 `실행 현황`을 텍스트 출력 중심으로 맞췄다.
- `/download`와 `/html-parse`의 `실행 결과 요약` 카드와 `작업 상태` 고정 라벨을 제거했다.
- Quantiwise 변환/병합의 실행 요약 박스를 줄바꿈 텍스트로 바꿔 `JobStatusLogger` 안에 표시하게 했다.
- `알림` 패널에서 정상 상태 로그 박스를 제거하고 오류/경고/확인 필요 메시지만 표시하게 했다.
- `docs/ui-terminology.md`에 우측 패널 용어 기준을 추가했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: source inspection for no remaining `activityTitle`, `실행 결과 요약`, `작업 상태` activity label, or notification `JobStatusLogger` fallback in the target pages.
- Passed: in-app Browser check on `http://localhost:3000/utility/assets-excel/convert` for `실행 현황` text output, `알림 없음`, and no console errors.
- Note: `http://localhost:3000/download` and `http://localhost:3000/html-parse` stayed on `옵션을 불러오는 중입니다...` in the current runtime, so their rendered dock panels could not be browser-verified in this pass.
