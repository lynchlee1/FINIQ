# Review Findings

## Provider and Graph Fallback Simplification

Purpose: Remove unimplemented integrated-data provider abstraction, graph-viewer local fallback storage, and dummy company graph fallback behavior.

Implementation summary:
- Removed the integrated provider registry and unimplemented FDR provider, then wired integrated conversion and merge directly to the Quantiwise implementation.
- Removed the `/api/integrated-data/providers` route because provider selection is no longer part of the supported backend contract.
- Removed graph-viewer localStorage graph fallback mode; graph mutations now require the backend API.
- Replaced dummy company graph fallback data with explicit 404/500 responses and a visible load error state.

Verification:
- `PYTHONPATH=src .venv/bin/python - <<'PY' ... import service_integrated ... PY` (Passed)
- `PYTHONPATH=src .venv/bin/python -m py_compile src/finiq/market_desk/web/features/market_data/service_integrated.py src/finiq/market_desk/web/features/market_data/service_common.py src/finiq/market_desk/web/routers/market_data.py src/finiq/market_desk/web/app.py` (Passed)
- `pytest tests/market_desk/test_classification_sqlite.py tests/data_scraper/test_kind_company_classification.py` (Passed)
- `npm run build -w @finiq/graph-viewer` (Passed)
- `npm run build -w @finiq/app-market-desk` (Passed)

## 2026-07-05 - Web Service Tests After SQLite Classification Migration

Purpose: Keep the intentional legacy JSON fallback removal while making the web service tests and source detection honor the SQLite classification artifact contract.

Implementation summary:
- Treated direct JSON classification fallback removal as intentional SQLite-only behavior.
- Updated web service classification fixtures to create artifacts through `write_company_classification_artifact()` instead of raw JSON writes.
- Updated fixture mutation tests to rewrite SQLite artifacts through the writer, or directly corrupt SQLite `raw_json` only where the test needs a malformed loaded artifact.
- Fixed SQLite manifest detection so binary `.sqlite` classification files are not decoded as JSON manifests.

Verification:
- `.venv/bin/pytest tests/market_desk/test_kind_web_service.py -q` (Passed, 188 tests)
- `.venv/bin/pytest tests/market_desk/test_classification_sqlite.py tests/market_desk/test_kind_web_service.py -q` (Passed, 191 tests)
- `.venv/bin/python -m py_compile src/finiq/market_desk/web/features/market_data/service_sources.py src/finiq/data_scraper/storage/classification_store.py` (Passed)

## 2026-07-05 - Bond Issuance Dash Issue Amount Parse Result

Purpose: Ensure bond issuance rows with an explicit `-` face value are treated as a zero issue amount, not as a missing-source warning.

Implementation summary:
- Added a resource-backed regression test for `20090720000320.html`, where `2. 사채의 권면총액 (원)` has a literal `-` value.
- Regenerated the local ignored `resources/KIND/bond_issuance/parsed-bond_issuance.json` with the current parser so explicit dash values are reflected as `0`.

Verification:
- `PYTHONPATH=src .venv/bin/python -m pytest tests/market_desk/test_kind_web_service.py -k 'dash_issue_amount' -q` (Passed, 2 tests)
- `resources/KIND/bond_issuance/parsed-bond_issuance.json` check: `20090720000320.html` has `발행금액 == 0`, no `발행금액` warning, and total `발행금액: 정해진 출처` warnings are `0`.
