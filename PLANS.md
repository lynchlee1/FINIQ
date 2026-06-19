# Completed Changes

## Quantiwise Parquet Convert Excel Selection

Purpose: Allow `Quantiwise - Parquet 변환하기` to run against only selected Excel files instead of always converting every Excel file under the source path.

Implementation summary: Added a selectable `대상 파일` table in the convert UI, defaulting to all discovered Excel files. Conversion is disabled when no file is selected, and the selected relative paths are sent as `selected_files` in the conversion job payload. The backend conversion result now echoes `selected_files`, and the Quantiwise conversion docs/UI terminology were updated to match the new contract.

Verification:
- `python3 -m pytest tests/test_assets_excel.py`
- `python3 -m pytest tests/market_desk/test_server.py`
- `npm run build -w @finiq/app-market-desk --`
