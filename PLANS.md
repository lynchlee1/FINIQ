# Completed Changes

## 2026-07-09 Parse result file-looking path rejection

- Purpose: 공시원문 변환 결과 경로 입력에서 존재하지 않는 파일형 경로가 결과 디렉터리처럼 해석되지 않도록 한다.
- Implementation: `_resolve_parse_result_path()`가 기존 파일뿐 아니라 존재하지 않으면서 확장자가 있는 경로도 `output_path must be a directory path`로 거부하도록 변경했다. 채권 요약/변경 로그/내보내기 호출자가 `.json` 및 다른 확장자 파일형 경로를 거부하는 회귀 테스트를 추가했다.
- Verification: `.venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k "bond_parse_summary or parse_change_log or parse_export_xlsx"` 통과. `.venv/bin/python -m py_compile src/finiq/market_desk/web/features/disclosures/html_parse_common.py src/finiq/market_desk/web/features/disclosures/html_parse_export.py tests/market_desk/test_kind_web_service.py` 통과.
