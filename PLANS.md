# Completed Changes

All completed implementation changes listed in this file have been reviewed and verified to be free of errors, including search regressions, mode splits, chart-focused workspaces, and A-prefix conversion behaviors.

## Price Chart Adjusted Prices and Separate Axes

Purpose: Fix the 주가-공시 차트 rendering where raw split-unadjusted prices distorted long-range charts, the price series could enter the volume area, volume scaling was not manually adjustable, and disclosure markers were unavailable when KIND used short company IDs or only category JSON files had rows.

Implementation summary:
- Preferred `adjOpen`, `adjHigh`, `adjLow`, `adjClose`, and `adjVolume` Quantiwise Parquet files over raw OHLCV files when both are available.
- Applied explicit price-series scale margins so candles/lines render in the upper price pane.
- Kept volume bars in the lower pane, clipped price/marker drawing to the price pane, and moved the volume-axis labels to a dedicated left-side axis.
- Added price-pane vertical dragging by translating pointer Y movement into `manualPriceRange` movement while keeping volume bars on the same shared time range; manual panning/zooming can move the visible price range below zero for close inspection.
- Added manual volume-axis scaling from the dedicated left volume axis, with drag, wheel zoom, and double-click reset behavior.
- Prevented automatic price-range padding from pushing non-negative stock prices below zero.
- Added a category JSON disclosure fallback for `resources/KIND/*/filtered.json` when the SQLite manifest has no company rows for the selected stock.
- Matched KIND disclosure rows that use shortened trailing-zero company IDs such as `06409` for `A064090`.
- Added right settings controls for `공시 마커 위치` and `공시 마커 모양`, including chart-top, chart-bottom, candle-relative, and basic shape overrides.
- Added frontend and backend regression coverage for adjusted prices, category JSON disclosure fallback, short KIND IDs, pane clipping, separate price/volume axes, vertical price panning, manual volume scaling, marker customization, and non-negative automatic price ranges.

Verification:
- `node --test tests/frontend/priceChart.test.mjs`
- `node --test tests/frontend/*.test.mjs`
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_ontology_graph.py -q`
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_ontology_graph.py tests/market_desk/test_kind_web_app.py -q`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Real-resource smoke check: `build_ontology_company_panel(company_id="A005930", display_frequency_label="일봉")` returned 6482 candles with adjusted first candle `open=5200, high=5560, low=5050, close=5320`; local KIND resources still returned 0 삼성전자 markers because no exact `005930` or `삼성전자` rows exist in the configured SQLite/category JSON resources.
- Real-resource smoke check: `build_ontology_company_panel(company_id="A064090", display_frequency_label="일봉")` returned 5758 candles, 1564 chart markers, 1584 timeline rows, and top disclosure groups `기타`, `주주총회`, `유상증자`, `CB`, `BW`.

## Disclosure Triple Barrier Labeling

Purpose: Let the existing `공시 분석` page run Triple Barrier Method labeling from disclosure event times, persist the results, and reload them for later backtests or model training.

Implementation summary:
- Added a reusable Triple Barrier calculation module that combines disclosure events with Quantiwise OHLCV prices and supports disclosure-date or disclosure-timestamp event bases.
- Implemented close-price and intraday high/low barrier modes, upper/lower/vertical barrier parameters, label generation, return storage, and failed-row reporting.
- Validated event basis, price basis, positive barrier percentages, and positive vertical trading-day horizons before execution.
- Marked same-row intraday upper/lower touches as failed rows instead of storing an unsupported first-touch label when OHLC data cannot identify sequence.
- Added SQLite persistence with a canonical parameter hash and a unique key on source manifest, disclosure ID, ticker, and parameters to prevent duplicate runs.
- Exposed API routes for running analysis and reading stored results from the ontology market-data router.
- Replaced the previous in-memory disclosure backtest panel with a `Triple Barrier 실행` panel and a persisted result table on `공시 분석`.

Verification:
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_triple_barrier.py -v`
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_ontology_graph.py::test_triple_barrier_api_runs_stores_and_reuses_results -v`
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_ontology_graph.py -v`
- `node --test tests/frontend/ontologyGraphWorkspace.test.mjs`
- `node --test tests/frontend/ontologyGraphWorkspace.test.mjs tests/frontend/navigation.test.mjs`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Fixture smoke check: `run_triple_barrier_analysis(company_id="A005930", upper_pct=5, lower_pct=3, vertical_days=2)` created 3 SQLite rows, all completed, and reloaded the first row with `touched_barrier="upper"` and `label=1`.
