# 2026-06-18 MarketDesk page title alignment

## Purpose
- Make the top MarketDesk title match the active page title instead of broad workflow labels like `공시데이터 구축`.
- Keep Quantiwise page titles consistent with the `Quantiwise - ...` pattern.

## Implementation Summary
- Added a route-title helper that resolves the current page from existing workflow step labels.
- Updated the Topbar to render that resolved page title and mirror it into `document.title`.
- Renamed the Quantiwise conversion workflow/page title to `Quantiwise - Parquet 변환하기` and recorded the term in `docs/ui-terminology.md`.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.

# 2026-06-18 Quantiwise duplicate Parquet cleanup

## Purpose
- Add a `중복 검사하기` action to `Quantiwise - 병합하기` for same-account Parquet files covered by a more complete same-account Parquet.
- Delete only files whose date/code/value cells are losslessly included in the file kept as canonical.

## Implementation Summary
- Added backend duplicate cleanup logic for `병합 대상 경로` and its immediate `merged` folder.
- Compared same-account Parquet files by ordered date rows, stock-code columns, and non-null cell values instead of relying on filename equality.
- Added metadata-based date/row/column prefilters so impossible subset directions skip full cell comparison.
- Changed duplicate scanning to inspect only direct Parquet files by default, with `내부까지 검사` enabling recursive subfolder scanning.
- Treated exact duplicates and strict supersets as deletion-safe, keeping the more complete file and deleting the covered file after confirmation.
- Added dry-run and confirmed-delete job APIs under `/api/assets/parquet/duplicates`.
- Added merge-page UI for `중복 검사하기`, delete confirmation, candidate display, deleted summary, mismatched reporting, and raw inspection result display in the right alert dock.
- Updated UI terminology and Quantiwise conversion docs.

## Verification
- Passed: `python3 -m pytest tests/test_assets_excel.py -q` including date-range subset, stock-code subset, exact duplicate, and overlapping conflict cases.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: `python3 -m py_compile src/finiq/data/assets_excel.py src/finiq/market_desk/web/routers/assets_excel.py src/finiq/market_desk/web/app.py`.
- Passed: `python3 -m pytest tests/market_desk/test_server.py -q`.
- Passed: `npm run build -w @finiq/app-market-desk --` from `frontend/`.
- Dry-run on `resources/Quantiwise/parquetCalamine`: deletion candidates `1`, mismatched duplicates `0`; the less complete `close_20091230_20260417_...de0d.parquet` is covered by `...de0d__2.parquet`.

# 2026-06-18 Quantiwise merge cleanup archive collision

## Purpose
- Fix merge jobs failing when `병합된 요소 정리하기` tries to move a selected Parquet file into `merged/` and a previous archive with the same filename already exists.
- Preserve existing archived Parquet files instead of overwriting them.

## Implementation Summary
- Added cleanup archive destination selection that keeps the original archive name when free and otherwise uses `__2`, `__3`, etc.
- Kept cleanup scoped to successful merges only; validation failures still leave selected source files in place.
- Added a regression test for an existing `merged/` archive with the same source filename.
- Documented the archive suffix behavior in `docs/assets-excel-conversion.md`.

## Verification
- Passed: `python3 -m pytest tests/test_assets_excel.py -q`.
- Passed: `python3 -m pytest tests/market_desk/test_server.py -q`.
- Passed: `npm run build -w @finiq/app-market-desk --` from `frontend/`.

# 2026-06-18 Quantiwise Parquet preview UI cleanup

## Purpose
- Remove redundant file-selection helper text from `Quantiwise - Parquet 미리보기`.
- Stop showing generated Parquet filenames in grouped Parquet tables when account, date interval, and SHA256 identify the same output.

## Implementation Summary
- Removed the metadata summary strip directly below the Parquet preview file selector.
- Replaced the visible filename column in `Parquet 모아보기` and `병합대상 모아보기` with `구간 시작`, `구간 종료`, and `SHA256`.
- Kept filenames as internal values for preview selection and merge checkbox behavior.
- Used filename parsing only as a fallback when existing Parquet rows do not include footer metadata fields in the API payload.

## Verification
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
