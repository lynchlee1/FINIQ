# 2026-06-17 Quantiwise 변환 결과 Parquet 미리보기

## Purpose
- `Quantiwise - 변환하기`에서 변환 완료 후 생성된 Parquet를 다시 읽어 실행 결과를 바로 확인할 수 있게 한다.
- 실행 결과 표 양식은 `Quantiwise - 미리보기`의 Sheet 미리보기 표와 맞춘다.

## Implementation Summary
- 생성된 Sheet Parquet 하나를 읽는 `read_asset_parquet_preview`와 `/api/assets/parquet/preview` API를 추가했다.
- 변환 완료 payload의 첫 Parquet를 자동 선택하고, `작업 실행` 카드의 실행 버튼 아래에서 다른 Parquet도 선택해 미리볼 수 있게 했다.
- Parquet 미리보기 payload와 UI는 `columns`, `preview_columns`, `rows`, 계정/상태/행/기간 메타데이터를 사용해 기존 Sheet 미리보기와 같은 표 구조를 쓴다.
- `docs/ui-terminology.md`와 `docs/assets-excel-conversion.md`에 실행 결과 미리보기 용어와 동작을 기록했다.

## Verification
- Passed: `python3 -m pytest tests/test_assets_excel.py tests/market_desk/test_server.py -q`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: `npm run build -w @finiq/app-market-desk --` from `frontend/`.
- Passed: in-app Browser check on `http://127.0.0.1:3000/utility/assets-excel/convert` for page title, run card, run/cancel buttons, and no console errors.
- Note: the same build command fails from the repository root because there is no root `package.json`; the actual npm workspace root is `frontend/`.

# 2026-06-17 Ontology Quant Platform Workspace

## Purpose
- Ontology page에 전문 퀀트 애널리스트 플랫폼으로 확장할 핵심 기능 5개를 새 feature surface로 추가한다.
- 새로 추가하는 샘플 데이터는 TEST DATA로 명확히 표시하고, `resources/`와 분리된 frontend source fixture로 둔다.
- Ontology 화면의 정보 구조와 시각적 밀도를 개선한다.

## Implementation Summary
- `/graph`에 `Quant Platform Workspace`를 추가해 `Research Data Store`, `Factor & Signal Research`, `Point-in-Time Backtesting`, `Portfolio Construction & Risk`, `Research Runs & Reports`를 표시하게 했다.
- Ontology 전용 테스트 fixture를 `frontend/finiq_GUI/apps/market-desk/src/app/graph/test-data/quantPlatformFeatures.ts`에 만들고, 화면에 source path와 `resources/` 미사용 경계를 표시했다.
- 테스트 데이터 스냅샷, research pipeline, feature 상세 패널, research run 표를 추가했다.
- 데모 graph viewer에 optional `TEST DATA` badge와 source label props를 추가해 `/graph`의 demo graph도 테스트 데이터임을 표시했다.
- `docs/ui-terminology.md`에 Ontology feature 용어와 `TEST DATA` badge 기준을 추가했다.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: in-app Browser check on `http://127.0.0.1:3000/graph` confirming all 5 feature names, TEST DATA labels, resource boundary text, and no console errors.
- Passed: responsive browser check at `390x900` with no horizontal overflow and visible TEST DATA/resource boundary text.

# 2026-06-14 Quantiwise 계정명 파일명 및 계정 ID 매핑

## Purpose
- Sheet Parquet 출력 파일명을 `<계정명>_<시작일>_<종료일>` 형식으로 바꾼다.
- 계정명은 언더바 없는 lower camel case로 사용한다.
- 계정명과 `S00001` 형식 ID를 연결하는 매핑 산출물을 만든다.

## Implementation Summary
- Sheet 계정명을 `stock_price` 같은 snake_case에서 `close`, `nxtHigh`, `tradingHaltFlag` 같은 lower camel case로 바꿨다.
- 기존 snake_case 계정명은 `legacy_account_name` metadata로 보존했다.
- 출력 파일명을 `close_20200101_20200102.parquet`처럼 계정명과 Sheet 날짜 구간으로 만들게 했다.
- 계정명과 ID를 연결하는 `account_mapping.parquet`를 생성하고 manifest/payload에도 `account_mapping`을 포함했다.
- 결과 탐색 표에 계정 ID 컬럼을 추가했다.

## Verification
- Passed: `python3 -m pytest tests/test_assets_excel.py -q`.
- Passed: `python3 -m pytest tests/market_desk/test_job_cancellation.py -q`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
