# 2026-06-17 Quantiwise 계정-ID 매핑 편집

## Purpose
- `Quantiwise - 변환하기`에서 Sheet별 `account_id`와 `account_name` 매핑을 사용자가 편집, 추가, 삭제할 수 있게 한다.
- 사용자가 조정한 매핑이 변환 미리보기와 실제 변환 산출물의 `account_mapping.parquet`, manifest, output metadata에 반영되게 한다.
- Parquet 파일명이 `<accountName>_<YYYYMMDD>_<YYYYMMDD>.parquet` 형식이라 시작일/종료일 구분과 헷갈리지 않도록 `account_id`와 `account_name`에 `_`를 금지한다.

## Implementation Summary
- assets Excel 변환 요청 payload에 `account_mappings`를 추가하고, 값이 제공되면 기본 Sheet 계정 registry 대신 해당 목록을 사용하게 했다.
- 기본 `계정-ID 매핑` 조회 API를 추가했다.
- 변환 화면에 Sheet, ID, 계정, 기존 계정 컬럼을 가진 편집 가능한 매핑 표와 추가/삭제 버튼을 추가했다.
- 빈 필수값과 중복 Sheet/ID는 실행 전에 UI에서 막고, 백엔드에서도 동일하게 거부하게 했다.
- `account_id`와 `account_name`에 `_`가 포함되면 UI와 백엔드에서 실행을 막게 했다.
- 관련 용어와 Quantiwise 변환 문서를 갱신했다.

## Verification
- Passed: `python3 -m py_compile src/finiq/data/assets_excel.py src/finiq/market_desk/web/routers/assets_excel.py src/finiq/market_desk/web/app.py`.
- Passed: `python3 -m pytest tests/test_assets_excel.py -q` (30 tests).
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: `npm --prefix frontend/finiq_GUI/apps/market-desk run build`.
- Passed: `curl -I http://localhost:3000/utility/assets-excel/convert`.

# 2026-06-17 Quantiwise 변환 결과 메시지 및 manifest 축약

## Purpose
- `Quantiwise - 변환하기` 화면의 기존 결과 감지 경고 문구를 제거한다.
- 변환 완료 결과에서 건너뛴 Sheet 개수만이 아니라 파일, Sheet, 이유를 확인할 수 있게 한다.
- `manifest.json`에 긴 날짜 목록과 샘플 행을 저장하지 않고 날짜 구간은 시작일/종료일만 기록한다.

## Implementation Summary
- 변환 화면의 기존 결과 감지 경고 블록을 제거했다.
- 변환 완료 상태와 job 로그에 `건너뛴 Sheet 상세`를 추가하고, 완료 후 결과 표도 실제 job 결과의 skipped 목록을 보게 했다.
- 품질 payload에서 `sample_rows` 생성을 제거하고 결과 UI의 `최근 샘플` 영역을 제거했다.
- `date_index` metadata를 제거하고 `date_segments`를 `start`/`end`만 남기도록 축약했다.
- `docs/assets-excel-conversion.md`와 regression tests를 새 metadata 계약에 맞게 갱신했다.

## Verification
- Passed: `python3 -m py_compile src/finiq/data/assets_excel.py`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Not run: 실제 Quantiwise 리소스 변환 실행은 사용자가 금지했으므로 수행하지 않았다.
