# 2026-06-18 Quantiwise Parquet 기업목록 hash 파일명

## Purpose
- 같은 계정과 날짜 범위를 가진 Sheet가 종목코드 목록만 다를 때 같은 Parquet 파일명으로 충돌하지 않게 한다.
- 파일명 생성이 재현 가능하도록 wide 컬럼 순서의 종목코드 목록을 SHA256 hash 입력으로 고정한다.

## Implementation Summary
- 계정 Parquet 파일명을 `<accountName>_<date_start>_<date_end>_<companiesHash>.parquet` 형식으로 바꿨다.
- `companiesHash`는 Parquet wide 컬럼 순서의 종목코드를 순서대로 이어붙인 문자열의 SHA256 hex 값이다.
- 변환 preview, 실제 변환, 병합 결과 파일명 생성에 같은 hash 알고리즘을 적용했다.
- 백엔드와 프론트엔드의 account-name fallback parser가 새 hash 파일명과 기존 legacy 파일명을 모두 인식하게 했다.
- 같은 계정/날짜지만 종목코드 목록이 다른 Sheet가 서로 다른 Parquet로 저장되는 regression test를 추가했다.

## Verification
- Passed: `python3 -m pytest tests/test_assets_excel.py -q`.
- Passed: `python3 -m py_compile src/finiq/data/assets_excel.py`.
- Passed: `python3 -m pytest tests/market_desk/test_server.py -q`.
- Passed: `frontend/node_modules/.bin/tsc --noEmit -p frontend/finiq_GUI/apps/market-desk/tsconfig.json`.
- Passed: `npm run build -w @finiq/app-market-desk --` from `frontend/`.
