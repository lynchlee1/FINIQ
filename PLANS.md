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
