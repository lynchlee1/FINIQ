# Completed Changes

All completed implementation changes listed in this file have been reviewed and verified to be free of errors, including search regressions, mode splits, chart-focused workspaces, and A-prefix conversion behaviors.

## Chart View Direct Stock-Code Fallback

Purpose: Fix Chart View showing no data when `A005930` is entered and the KIND company search has no matching disclosure rows, even though Quantiwise price data exists for the stock code.

Implementation summary:
- Added a Chart View fallback company for `A000000` stock-code inputs when `/api/ontology/companies` returns no company rows.
- Kept existing company-search behavior unchanged when matches are returned; the fallback only lets the existing company-panel API load price data directly by stock code.
- Added frontend regression coverage for the empty-search direct stock-code path.

Verification:
- `node --test tests/frontend/ontologyGraphWorkspace.test.mjs`
- `node --test tests/frontend/*.test.mjs`
- `python3 -m pytest tests/market_desk/test_ontology_graph.py -q`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Real-resource smoke check: `search_ontology_companies(keyword="005930")` returned 0 rows, while `build_ontology_company_panel(company_id="A005930", display_frequency_label="일봉")` returned 6482 candles, 0 markers, no messages, and stock code `A005930`.
