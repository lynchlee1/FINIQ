# 2026-06-17 Quantiwise Sheet 즉시 임시 저장

## Purpose
- `Quantiwise - 변환하기`에서 모든 Sheet DataFrame을 메모리에 모은 뒤 저장하는 구조를 줄인다.
- Sheet별 독립 Parquet 저장 계약에 맞게 Excel 병렬 처리 중 Sheet를 읽는 즉시 임시 Parquet로 저장한다.
- 실패/취소 시 최종 경로에 부분 결과를 남기지 않는 기존 원자적 승격 흐름은 유지한다.

## Implementation Summary
- 실제 변환 실행 경로에 `_scan_and_write_asset_excel_parquet`를 추가해 Excel 파일 단위 병렬 worker가 Sheet를 읽고 바로 데이터 경로 아래 `.quanti_parquet_write_*` 임시 폴더에 저장하게 했다.
- Sheet frame은 임시 저장과 품질 샘플 산출 후 버리고, manifest에 필요한 metadata와 mapping만 유지한다.
- 모든 worker가 성공한 뒤 기존 출력 파일명/중복 suffix 규칙을 적용해 임시 Parquet를 최종 경로로 승격한다.
- 변환 로그에 `임시 데이터 경로`, `임시 저장`, 최종 `[저장 N/M]` 단계를 남기게 했다.
- 취소 테스트를 새 스트리밍 저장 지점 기준으로 바꿨고, `docs/assets-excel-conversion.md`의 저장 계약 설명을 갱신했다.

## Verification
- Passed: `python3 -m pytest tests/test_assets_excel.py tests/market_desk/test_job_cancellation.py tests/market_desk/test_server.py -q`.
- Passed: `python3 -m py_compile src/finiq/data/assets_excel.py`.

# 2026-06-17 Quantiwise 변환 결과 Parquet 미리보기

## Purpose
- `Quantiwise - 변환하기`에서 변환 완료 후 생성된 Parquet를 다시 읽어 바로 확인할 수 있게 한다.
- 미리보기 양식은 `Quantiwise - 미리보기`의 `Sheet 읽기/미리보기` 카드와 맞춘다.

## Implementation Summary
- 생성된 Sheet Parquet 하나를 읽는 `read_asset_parquet_preview`와 `/api/assets/parquet/preview` API를 추가했다.
- `작업 실행` 카드 아래에 `Sheet 읽기/미리보기` 카드를 추가하고, `파일`/`Sheet` 선택 영역과 빈 상태 박스를 `Quantiwise - 미리보기`와 같은 구조로 맞췄다.
- Parquet 미리보기 payload와 UI는 `columns`, `preview_columns`, `rows`, 계정/상태/행/기간 메타데이터를 사용해 기존 Sheet 미리보기와 같은 표 구조를 쓴다.
- `docs/assets-excel-conversion.md`에 변환 후 Parquet 미리보기 동작을 기록했다.

## Verification
- Passed: `python3 -m pytest tests/test_assets_excel.py tests/market_desk/test_server.py -q`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: `npm run build -w @finiq/app-market-desk --` from `frontend/`.
- Passed: in-app Browser check on `http://127.0.0.1:3000/utility/assets-excel/convert` for page title, run card, run/cancel buttons, `Sheet 읽기/미리보기` card under the buttons, `파일`/`Sheet` controls, `Sheet를 선택하세요.` empty state, and no console errors.
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
