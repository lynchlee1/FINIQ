# Completed Changes

All completed implementation changes listed in this file have been reviewed and verified to be free of errors, including search regressions, mode splits, chart-focused workspaces, and A-prefix conversion behaviors.

## Disclosure Path Fields Vertical Layout

Purpose: Match the `데이터 경로` layout on `공시원문 목차 분리` and `공시내역 변환` to the other workflow pages by stacking path inputs vertically instead of placing them side by side on desktop.

Implementation summary:
- Changed `공시원문 목차 분리` path fields to full-width `HtmlWorkflowForm` spans so the HTML input path and result path render one per row.
- Removed the desktop two-column grid from `공시내역 변환` data path controls so the Raw JSON input path and SQLite result path stay vertically stacked.
- Added focused frontend regression coverage for both target pages.

Verification:
- Red check: `node --test tests/frontend/pathLayout.test.mjs` failed while `공시원문 목차 분리` used `span: 2` and `공시내역 변환` used `md:grid-cols-2`.
- `node --test tests/frontend/pathLayout.test.mjs`
- `node --test tests/frontend/*.test.mjs`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- `git diff --check -- frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx frontend/finiq_GUI/apps/market-desk/src/app/table/page.tsx tests/frontend/pathLayout.test.mjs`
- Browser QA on `http://127.0.0.1:3003/html-section-split` and `http://127.0.0.1:3003/table`: verified 1280px and 375px viewports have no horizontal overflow and each page's two path inputs share the same X coordinate with increasing Y coordinates.
- Screenshot evidence: `/tmp/finiq-html-section-split-path-layout-desktop.png`, `/tmp/finiq-html-section-split-path-layout-mobile.png`, `/tmp/finiq-table-path-layout-desktop.png`, `/tmp/finiq-table-path-layout-mobile.png`.

## Price Chart Hover OHLCV and Crosshair Readout

Purpose: Add TradingView-style pointer readouts to the FINIQ-owned `주가-공시 차트`, including top-left OHLC, signed price change, percent change, volume, and the existing dashed crosshair price/time labels.

Implementation summary:
- Added a chart overlay readout in `PriceChart` that follows the active crosshair candle and falls back to the latest candle when not hovering.
- Cleared stale hover state when the chart data changes.
- Formatted open, high, low, close, signed change, percent change, and volume using Korean locale-friendly values.
- Preserved the existing FINIQ-owned Canvas crosshair drawing contract for dashed vertical/horizontal guides, right-side price label, and bottom time label.
- Added frontend regression coverage for hover OHLCV readout state/formatting and crosshair label drawing.

Verification:
- `node --test tests/frontend/priceChart.test.mjs`
- `node --test tests/frontend/*.test.mjs`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`

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
- Added a compact `공시 마커 스타일` section to the Chart View condition panel, with one target selector for `전체` or a disclosure group and controls for marker shape, placement, color, size, and line width.
- Restyled the marker-style section as a compact toolbar with a subtle background, tighter controls, and an inline color preview so it does not read as a full extra form block.
- Applied marker style overrides by disclosure `group`, preserving existing per-group marker meaning unless a selected group is explicitly changed.
- Added frontend and backend regression coverage for adjusted prices, category JSON disclosure fallback, short KIND IDs, pane clipping, separate price/volume axes, vertical price panning, manual volume scaling, per-disclosure marker customization, and non-negative automatic price ranges.

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
- Reused the Ontology chart's shortened KIND company ID matching rule so `A064090` analysis can load KIND rows stored as `06409`.
- Added SQLite persistence with a canonical parameter hash and a unique key on source manifest, disclosure ID, ticker, and parameters to prevent duplicate runs.
- Exposed API routes for running analysis and reading stored results from the ontology market-data router.
- Replaced the previous in-memory disclosure backtest panel with a `Triple Barrier 실행` panel and a persisted result table on `공시 분석`.

Verification:
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_triple_barrier.py -v`
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_ontology_graph.py::test_triple_barrier_api_runs_stores_and_reuses_results -v`
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_ontology_graph.py -v`
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_ontology_graph.py::test_triple_barrier_api_matches_short_kind_company_ids -q`
- `node --test tests/frontend/ontologyGraphWorkspace.test.mjs`
- `node --test tests/frontend/ontologyGraphWorkspace.test.mjs tests/frontend/navigation.test.mjs`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Fixture smoke check: `run_triple_barrier_analysis(company_id="A005930", upper_pct=5, lower_pct=3, vertical_days=2)` created 3 SQLite rows, all completed, and reloaded the first row with `touched_barrier="upper"` and `label=1`.
- Real-resource smoke check: `run_triple_barrier_analysis(company_id="A064090", upper_pct=5, lower_pct=3, vertical_days=20)` against copied real KIND shards and real Quantiwise parquet created 1584 SQLite rows: 1389 completed and 195 failed rows with explicit failure status.

## Disclosure Triple Barrier Result Review and KIND Group Runs

Purpose: Improve `공시 분석` for quant analyst workflows by separating Triple Barrier execution from persisted result review and allowing tests to run against a selected `resources/KIND` event category.

Implementation summary:
- Added `실행 설정` and `저장 결과` modes to the disclosure analysis page so analysts can switch between parameter setup and saved-result review.
- Added visible `공시 선택` category buttons backed by `/api/ontology/status` disclosure groups and reused that group for both the visible event list and Triple Barrier run payload.
- Made `저장 결과` an actionable result review screen with selected-company status, row count, DB connection state, reload action, summary cards, and the persisted result table.
- Renamed the event checklist to `검사 대상 이벤트` and added an explicit `저장 결과 요약` area with refreshable persisted results.
- Applied KIND disclosure group filtering inside Triple Barrier disclosure loading, using the same disclosure-title classification rules as the ontology chart.
- Loaded `resources/KIND/<category>/filtered.json` rows for category-scoped Triple Barrier runs so curated category folders can supply events even when SQLite has no matching company rows.
- Scoped each run response to the disclosure IDs calculated in that run so prior saved rows with the same parameter hash do not leak into group-specific result tables.
- Cleared previous run results when the selected disclosure category changes to avoid showing stale category results beside new execution settings.
- Avoided forcing the legacy app `quanti_dir` into Triple Barrier UI runs when the UI omits `quanti_dir`, so the module's real Quantiwise default is used and run summaries match returned rows.

Verification:
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_ontology_graph.py::test_triple_barrier_api_filters_by_disclosure_group -q`
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_ontology_graph.py::test_triple_barrier_api_loads_category_json_disclosures_without_sqlite_rows tests/market_desk/test_ontology_graph.py::test_triple_barrier_api_filters_by_disclosure_group -q`
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_ontology_graph.py::test_triple_barrier_api_omits_config_quanti_dir_when_payload_uses_default tests/market_desk/test_ontology_graph.py::test_triple_barrier_api_loads_category_json_disclosures_without_sqlite_rows tests/market_desk/test_ontology_graph.py::test_triple_barrier_api_filters_by_disclosure_group -q`
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_triple_barrier.py tests/market_desk/test_ontology_graph.py -q`
- `node --test tests/frontend/ontologyGraphWorkspace.test.mjs`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Browser QA on `http://127.0.0.1:3001/graph/analysis`: verified labels `실행 설정`, `저장 결과`, `공시 선택`, `검사 대상 이벤트`, `저장 결과 요약`, and mode toggle aria state changes.
- Browser QA on `http://127.0.0.1:3000/graph/analysis`: searched `A064090`, selected `CB/EB/BW`, ran Triple Barrier, verified run summary `전체 62 / 완료 50 / 실패 12`, then opened `저장 결과` and verified persisted review `결과 행 306 / 전체 306 / 완료 265 / 실패 41`.
- Real-resource smoke check: `A064090` Triple Barrier runs returned `shareholder_meeting` 161 rows, `bond_issuance` 62 rows, and `rights_issuance` 83 rows; saved result review returned 306 total stored rows for the company.

## Disclosure Triple Barrier Split Stock Search

Purpose: Fix `공시 분석` so the Triple Barrier execution flow and saved-result lookup flow use separate stock-search boxes, matching the top mode-button pattern used by `공시원문 외부 저장`.

Implementation summary:
- Moved the `실행 설정` / `저장 결과` mode buttons into the top `공시 분석` header area.
- Removed the shared top stock selector that previously controlled both execution and result review.
- Added an execution-only `실행 종목 선택` box with `실행 대상 검색` inside `Triple Barrier 실행`.
- Added a result-only `결과 종목 선택` box with `저장 결과 검색` and `선택 종목 결과 조회` inside `Triple Barrier 저장 결과`.
- Split React state into `runKeyword` / `selectedRunCompany` and `resultKeyword` / `selectedResultCompany` so result lookup can search `A064090` without first running a test.
- Kept post-run convenience behavior: a successful run still seeds the result selector with the executed stock for immediate review.

Verification:
- `node --test tests/frontend/ontologyGraphWorkspace.test.mjs`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Browser QA on `http://127.0.0.1:3000/graph/analysis`: opened `저장 결과`, searched `A064090` in `결과 종목 선택`, clicked `저장 결과 검색`, and verified `조회 종목: A064090`, `결과 행: 306`, `전체 306 / 완료 265 / 실패 41`. Screenshot: `/tmp/finiq-split-result-search.png`.
- Browser QA on `http://127.0.0.1:3000/graph/analysis`: opened `실행 설정`, searched `A064090` in `실행 종목 선택`, selected `CB/EB/BW`, clicked `Triple Barrier 실행`, and verified `전체 62 / 완료 50 / 실패 12`. Screenshot: `/tmp/finiq-split-run-search.png`.

## Disclosure Analysis Workflow Layout Refactor

Purpose: Make `Ontology/공시 분석` easier to scan by reducing cramped control density, grouping related buttons, and separating the execution workflow from saved-result review.

Implementation summary:
- Grouped `실행 설정` controls into numbered workflow sections: `1. 실행 대상`, `2. 공시 범위`, and `3. Triple Barrier 설정`.
- Moved `공시 선택` and `검사 대상 이벤트` into the same section so disclosure category buttons and event checkboxes read as one scope-selection step.
- Kept Triple Barrier parameter controls and the `Triple Barrier 실행` action together in one bordered parameter section.
- Preserved the lower `저장 결과 요약` and `결과 테이블` review area while keeping `저장 결과` mode as the dedicated persisted-result lookup screen.
- Added frontend regression coverage for the new workflow section order.
- Saved the implementation plan at `docs/superpowers/plans/2026-06-20-disclosure-analysis-layout-refactor.md`.

Verification:
- Red check: `node --test tests/frontend/ontologyGraphWorkspace.test.mjs` failed on missing `1. 실행 대상` before the JSX refactor.
- `node --test tests/frontend/ontologyGraphWorkspace.test.mjs`
- `node --test tests/frontend/*.test.mjs`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Browser QA on `http://127.0.0.1:3001/graph/analysis`: verified `1. 실행 대상`, `2. 공시 범위`, `3. Triple Barrier 설정`, `저장 결과 요약`, and `결과 테이블` render in order.
- Browser QA on `http://127.0.0.1:3001/graph/analysis`: clicked `저장 결과` and verified `aria-pressed="true"` plus `저장 결과 조회` / `결과 종목 선택`.
- Browser QA on 375px mobile viewport: verified the three execution workflow sections render and page-level horizontal overflow is false.
- Screenshot evidence: `/tmp/finiq-disclosure-analysis-desktop.png`, `/tmp/finiq-disclosure-analysis-results.png`, `/tmp/finiq-disclosure-analysis-mobile.png`.

## Disclosure HTML Section Split UI Alignment

Purpose: Align `공시원문 목차 분리` with the surrounding HTML workflow pages so it uses the shared workflow shell, cards, form controls, and right-side action dock behavior.

Implementation summary:
- Replaced hand-rolled path/settings panels with `HtmlWorkflowCard` and `HtmlWorkflowForm` so the page matches `공시원문 외부 저장`, `공시원문 내부 저장`, and `공시원문 변환`.
- Extracted scan summary, `문서별 목차`, `문제 파일`, status, and dock rendering into a route-local component to keep the page focused on settings and API actions.
- Updated the UI text coverage test to include the extracted route-local component.
- Changed `ActionDock` mobile positioning from fixed/sticky overlay behavior to normal mobile layout, while preserving the desktop sticky right rail, so the dock no longer covers form inputs on narrow screens.

Verification:
- `PYTHONPATH=src python3 -m pytest tests/market_desk/test_kind_web_service.py::test_html_parse_modes_are_registered_documented_and_listed_in_ui -q`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- `git diff --check -- frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/page.tsx frontend/finiq_GUI/apps/market-desk/src/app/html-section-split/_components/HtmlSectionSplitResults.tsx frontend/finiq_GUI/apps/market-desk/src/components/ui/ActionDock.tsx tests/market_desk/test_kind_web_service.py`
- Browser QA on `http://localhost:3002/html-section-split`: verified `데이터 경로`, `문서별 목차`, `목차 스캔`, and `목차 저장` render on desktop and mobile.
- Browser QA on 1280px and 375px production viewports: verified page-level horizontal overflow is false and the action dock does not overlap inputs.
- Screenshot evidence: `/tmp/finiq-html-section-split-desktop-prod.png`, `/tmp/finiq-html-section-split-mobile-prod.png`.
