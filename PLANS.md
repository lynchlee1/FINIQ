# Completed Changes

All completed implementation changes listed in this file have been reviewed and verified to be free of errors, including search regressions, mode splits, chart-focused workspaces, and A-prefix conversion behaviors.

## Price Chart Adjusted Prices and Separate Axes

Purpose: Fix the 주가-공시 차트 rendering where raw split-unadjusted prices distorted long-range charts, the price series could enter the volume area, and disclosure markers were unavailable when SQLite had no rows but category JSON files did.

Implementation summary:
- Preferred `adjOpen`, `adjHigh`, `adjLow`, `adjClose`, and `adjVolume` Quantiwise Parquet files over raw OHLCV files when both are available.
- Applied explicit price-series scale margins so candles/lines render in the upper price pane.
- Kept volume bars in the lower pane, clipped price/marker drawing to the price pane, and moved the volume-axis labels to a dedicated left-side axis.
- Added a category JSON disclosure fallback for `resources/KIND/*/filtered.json` when the SQLite manifest has no company rows for the selected stock.
- Added frontend and backend regression coverage for adjusted prices, category JSON disclosure fallback, pane clipping, and separate price/volume axes.

Verification:
- `node --test tests/frontend/priceChart.test.mjs`
- `node --test tests/frontend/*.test.mjs`
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_ontology_graph.py -q`
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_ontology_graph.py tests/market_desk/test_kind_web_app.py -q`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Real-resource smoke check: `build_ontology_company_panel(company_id="A005930", display_frequency_label="일봉")` returned 6482 candles with adjusted first candle `open=5200, high=5560, low=5050, close=5320`; local KIND resources still returned 0 삼성전자 markers because no exact `005930` or `삼성전자` rows exist in the configured SQLite/category JSON resources.
