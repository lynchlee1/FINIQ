# Completed Changes

## Ontology Graph View Real Data Refactor

Purpose: Replace the `/graph` page's frontend-only `TEST DATA` quant workspace with a real-data Ontology Graph View that plots and analyzes KIND disclosure events together with Quantiwise price data.

Current context:
- `/graph` now renders `OntologyGraphWorkspace` and no longer imports the synthetic quant platform panel or graph fixture fallback.
- Quantiwise price data is available as Wide Parquet under `resources/Quantiwise/parquetCalamine`, including OHLCV-like account files and `code_name_mapping.parquet`.
- KIND disclosure table shards are available under `resources/KIND_DISCTABLE_FULL.sqlite_manifest_shards`, with manifest `KIND_DISCTABLE_FULL.sqlite_manifest.json` and yearly SQLite `disclosures` tables.
- Existing `/api/insight` still serves company detail pages; the real-data `/graph` surface uses the dedicated `/api/ontology/*` endpoints.

Chosen scope:
- The first production version focuses on a company/event research workspace: select a company, date range, and disclosure title filters, then view price candles with disclosure markers, event timeline, and analysis summary.
- Market-wide discovery can be added later through the search/status rail; full cross-sectional factor research/backtesting remains out of this refactor.
- Test fixture labels, synthetic dataset cards, and `TEST DATA` badges are removed from `/graph`.

Candidate approach:
- Add backend read/query helpers for the KIND SQLite manifest shards and Quantiwise Parquet catalog.
- Add narrow API endpoints for `/graph` data needs: dataset status, company search, company event-price panel, and lightweight disclosure summary.
- Refactor `/graph` into a production analysis surface with persistent controls, a price/disclosure plot, timeline/details, and a compact graph/event relationship panel.
- Keep changes surgical: avoid changing unrelated workflow navigation or the existing company detail page unless shared types/helpers are needed.

Verification target:
- Backend tests cover SQLite shard querying, Quantiwise Parquet catalog loading, and combined event-price payload behavior.
- Frontend tests cover removal of fixture/test-data copy and rendering of real-data loading/error/empty states.
- Build check: `npm --prefix frontend/finiq_GUI/apps/market-desk run build`.

### Scope Options

1. Company-centered event workspace (recommended)
   - User flow: search/select company -> choose date range and disclosure filters -> inspect price candles with KIND disclosure markers -> review event timeline and analysis summary.
   - Pros: directly matches the new ability to plot disclosures and prices together, reuses existing chart helpers, keeps the refactor deliverable testable.
   - Cons: does not yet provide full market-wide factor research or backtesting.

2. Market-wide disclosure discovery workspace
   - User flow: search all disclosure shards -> inspect title/date/market distributions -> open a selected company/event.
   - Pros: makes the 1.4M-row KIND shard corpus visible immediately.
   - Cons: weakly exercises price plotting, and the graph view would still need a second company-analysis surface.

3. Full quant platform workspace
   - User flow: market discovery + company event chart + factor diagnostics + research run panels.
   - Pros: closest to the old synthetic "Quant Platform Workspace" concept.
   - Cons: too broad for one safe refactor; high risk of replacing fake cards with shallow real-looking cards.

Decision for implementation unless revised: use option 1, with a compact search/status rail so option 2 can be added later without restructuring.

### Proposed User Experience

The `/graph` route becomes a single production research surface named `Graph View`.

Top control band:
- Data status: Quantiwise Parquet path, KIND SQLite manifest path, date coverage, available price items, disclosure row count, company count.
- Company search: company name, company ID, market, and disclosure count. Selecting a row drives the chart.
- Query controls: start date, end date, disclosure title keyword, market, frequency (`자동`, `일봉`, `주봉`, `월봉`).

Main analysis band:
- Left: price/disclosure plot using existing `PriceChart` rendering, with OHLCV candles from Quantiwise and markers from KIND disclosure rows.
- Right: event timeline sorted newest first, grouped by disclosure group where possible, with title, date/time, submitter, acceptance number, and marker trade day.

Bottom analysis band:
- Summary metrics with decision value only: visible candles, visible disclosures, first/last disclosure, top disclosure groups, after-close disclosures shifted to next trading day.
- Event relationship view: replace the synthetic graph fallback with a small real event graph for the selected company/date window. Nodes are company, disclosure groups, individual high-signal disclosures, and price movement buckets; edges connect company -> group -> disclosure -> price response window. If this graph cannot be made meaningful from current structured fields, omit it rather than showing fake ontology nodes.

Removed from `/graph`:
- `TEST DATA` badge and all synthetic quant platform copy.
- `OntologyQuantPlatformPanel` fixture cards.
- `local-api-graph` dummy fallback as the default graph source.
- `exampleGraphData` fallback for the `/graph` route.

### Backend Design

Create focused read helpers instead of overloading `/api/insight`.

Planned module:
- `src/finiq/market_desk/analytics/ontology_graph.py`

Responsibilities:
- Resolve and validate `resources/KIND_DISCTABLE_FULL.sqlite_manifest_shards/KIND_DISCTABLE_FULL.sqlite_manifest.json`.
- Read only required yearly SQLite shards for a requested date range.
- Search companies from SQLite rows using `company_name`, `company_id`, and `market`.
- Load Quantiwise Wide Parquet OHLCV data from `resources/Quantiwise/parquetCalamine`.
- Normalize Quantiwise company codes: SQLite `company_id` values appear as 5-digit strings in observed rows; Quantiwise mapping stores values like `A000020`. The helper should derive `A` + zero-padded 6-digit code for Parquet columns where needed and return the display stock code separately.
- Reuse existing chart helpers where they fit: `prepare_price_dataframe`, `aggregate_price_dataframe`, `prepare_disclosure_points`, `classify_disclosure_group`, `disclosure_group_color_map`.

Planned router additions in `src/finiq/market_desk/web/routers/market_data.py`:
- `GET /api/ontology/status`
  - Returns source paths, manifest summary, shard years, Quantiwise item coverage, and missing-source messages.
- `GET /api/ontology/companies`
  - Query params: `keyword`, `market`, `limit`.
  - Returns companies sorted by recent disclosure count, with `company_id`, `company_name`, `market`, `disclosure_count`, `first_disclosed_date`, `last_disclosed_date`, and `has_price_data`.
- `GET /api/ontology/company-panel`
  - Query params: `company_id`, `start_date`, `end_date`, `title_keyword`, `market`, `display_frequency`.
  - Returns company metadata, candles, disclosure markers, group summary, timeline, summary metrics, and messages.

Default source paths:
- KIND manifest: `resources/KIND_DISCTABLE_FULL.sqlite_manifest_shards/KIND_DISCTABLE_FULL.sqlite_manifest.json`.
- Quantiwise path: `resources/Quantiwise/parquetCalamine`.
- The API can accept explicit override paths later, but this refactor should not add new path inputs to the UI unless needed for verification.

### Frontend Design

Replace the current `/graph` composition:
- Remove `OntologyQuantPlatformPanel` from `frontend/finiq_GUI/apps/market-desk/src/app/graph/page.tsx`.
- Add a production component under `frontend/finiq_GUI/apps/market-desk/src/app/graph/OntologyGraphWorkspace.tsx`.
- Keep `WorkflowPageShell workflowId="ontology"` and the existing navigation labels unless a terminology update is approved.

Frontend component responsibilities:
- Fetch `/api/ontology/status` on load and show a compact status row.
- Fetch `/api/ontology/companies` as the search input changes, with a conservative debounce or explicit search button.
- Fetch `/api/ontology/company-panel` when the selected company or filters change.
- Render empty states that point to missing source data or no matching company, not sample data.
- Use existing `PriceChart` if it handles the required marker payload. If the current chart is too limited, extend it minimally for marker labels and dark-mode-safe colors.

Terminology to add/update in `docs/ui-terminology.md` before UI labels change:
- Ontology real-data workspace: `Graph View`.
- Ontology data status: `데이터 상태`.
- Ontology company search: `회사 검색`.
- Ontology event timeline: `공시 타임라인`.
- Ontology event-price chart: `주가-공시 차트`.
- Ontology analysis summary: `분석 요약`.
- Remove or deprecate the Ontology `TEST DATA` term once no page uses it.

### Test Plan

Backend tests:
- Add `tests/market_desk/test_ontology_graph.py`.
- Fixture: temporary SQLite manifest shard directory with two yearly shard DBs and a small disclosure table matching the observed schema.
- Fixture: temporary Quantiwise Parquet directory with `open`, `high`, `low`, `close`, `volume`, and `code_name_mapping.parquet` files using the current Wide Format contract.
- Test status payload reports manifest/shard and Parquet coverage.
- Test company search returns matched companies with disclosure counts and price availability.
- Test company panel aligns disclosures to candles and shifts after-close disclosures to the next trading day through existing chart helper behavior.
- Test missing Quantiwise item returns a useful message and an empty candle list rather than synthetic fallback.

Frontend tests:
- Add or extend frontend tests so `/graph` no longer contains `TEST DATA`, `Synthetic`, or `Export disabled for test data`.
- Test the workspace renders loading, empty, and populated states from mocked `fetch` responses.
- Test company selection sends the selected `company_id` to `/api/ontology/company-panel`.

Manual verification:
- `python3 -m pytest tests/market_desk/test_ontology_graph.py tests/market_desk/test_kind_insight_chart.py`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Start the MarketDesk dev server and inspect `/graph` at desktop and mobile widths.
- Confirm real source paths are shown and no synthetic graph/test-data copy is visible.

### Implementation Guardrails

- Do not run heavy full-dataset conversions or writes. This feature reads existing SQLite and Parquet resources only.
- Do not refactor unrelated workflow navigation, right dock, or Quantiwise conversion pages.
- Do not delete existing fixture files until no active route imports them; removing imports and route usage is required first.
- Do not add decorative summary boxes. Every summary value must help decide whether the visible analysis is usable.
- Keep full cross-sectional factor/backtesting features out of this refactor.

Implementation summary:
- Added `src/finiq/market_desk/analytics/ontology_graph.py` to read the KIND SQLite manifest shards, search companies, load Quantiwise Wide Parquet OHLCV data from `resources/Quantiwise/parquetCalamine`, and build combined chart/timeline/summary payloads.
- Added `/api/ontology/status`, `/api/ontology/companies`, and `/api/ontology/company-panel` to the MarketDesk API.
- Replaced `/graph` with `OntologyGraphWorkspace`, a real-data company event workspace with `데이터 상태`, `회사 검색`, `주가-공시 차트`, `분석 요약`, and `공시 타임라인`.
- Removed the obsolete `/graph` synthetic quant platform fixture panel and its `test-data/quantPlatformFeatures.ts` source.
- Added Ontology real-data UI terminology and tests covering backend data contracts, API routes, and fixture removal from the graph page.

Verification:
- `python3 -m pytest tests/market_desk/test_ontology_graph.py tests/market_desk/test_kind_insight_chart.py -q`
- `node --test tests/frontend/*.test.mjs`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Real-resource smoke check: `build_ontology_status()` read 1,436,807 KIND disclosures and all required Quantiwise items; `build_ontology_company_panel(company_id="10100", 2024-01-01..2024-12-31, 월봉)` returned 12 candles, 177 markers, and no messages.
- Running-app proxy check: `curl http://127.0.0.1:3000/api/ontology/status` returned the real KIND manifest summary and Quantiwise item coverage through the Next rewrite to FastAPI.

## Ontology Graph View One-Box Rows

Purpose: Adjust `Graph View` for the constrained MarketDesk content width, where the global margins and left workflow sidebar leave too little room for side-by-side panels.

Implementation summary:
- Refactored `OntologyGraphWorkspace` from responsive multi-column panel grids into a vertical stack: `주가-공시 차트`, `데이터 상태`, `회사 검색`, `분석 요약`, and `공시 타임라인` each occupy their own row.
- Replaced separate status and summary mini-cards with compact detail rows inside their parent cards.
- Simplified timeline rows from grid columns into a single vertical row layout.
- Added a frontend static test that rejects responsive grid-column layout and the removed mini-card helper components on the Ontology workspace.

Verification:
- `node --test tests/frontend/*.test.mjs`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`

## Ontology Graph View Stability And Mode Split

Purpose: Fix the `/api/ontology/company-panel` HTTP 500 for real `06090` data and reduce the vertical settings burden on the constrained `Graph View` content area.

Plan:
- Backend: reproduce the real `06090` failure, add a regression test for JSON-safe panel payloads when disclosures cannot be mapped to a visible candle, and normalize unmatched timeline marker dates.
- Frontend: keep the one-box-per-row rule, but split the workspace into `분석`, `회사`, and `데이터` modes so the default screen does not render every control panel vertically.
- Frontend: keep `분석 조건` inside the analysis card as compact controls and move company search/data status behind explicit mode buttons.
- Verification: run the focused backend regression, frontend static tests, backend ontology tests, and the MarketDesk build. Do not run the separate Tasks workflow.

Implementation summary:
- Fixed the `06090` company-panel 500 by converting unmatched disclosure `trade_day` values from pandas `NaN` to JSON-safe empty strings before timeline serialization.
- Added a backend regression test that inserts an after-close disclosure beyond the available price candles and asserts the panel payload can be serialized with `allow_nan=False`.
- Split `OntologyGraphWorkspace` into `분석`, `회사`, and `데이터` modes. The default `분석` mode shows the chart, compact `분석 조건`, summary, and timeline; company search and source status no longer occupy vertical space until selected.
- Added Ontology UI terminology and frontend static coverage for the mode split while preserving the one-box-per-row layout rule.

Verification:
- `python3 -m pytest tests/market_desk/test_ontology_graph.py::test_build_ontology_company_panel_returns_json_safe_timeline_for_unmatched_markers -q`
- `python3 -m pytest tests/market_desk/test_ontology_graph.py tests/market_desk/test_kind_insight_chart.py -q`
- `node --test tests/frontend/ontologyGraphWorkspace.test.mjs`
- `node --test tests/frontend/*.test.mjs`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Real-route smoke check: `GET /api/ontology/company-panel?company_id=06090&start_date=2026-01-01&end_date=2026-06-19&title_keyword=&market=전체&display_frequency=자동` returned HTTP 200 with 72 candles and 40 markers.

## Graph View Price Chart Interaction Upgrade

Purpose: Upgrade the `Graph View` `주가-공시 차트` with FINIQ-owned chart code so the graph has professional trading-chart interactions without any external chart runtime, logo, or attribution requirement.

Implementation summary:
- Removed the `lightweight-charts` runtime dependency and restored the local `src/lib/charts.ts` renderer as FINIQ-owned chart code.
- Kept the existing `PriceChart` props and crosshair callback contract so both `Graph View` and company detail pages receive the chart without caller changes.
- Added right price-axis drag scaling, price-axis wheel zoom, and price-axis double-click reset to the local canvas renderer.
- Preserved user viewport across resize and marker/data refresh after the initial fit instead of forcing `fitContent()` on every resize.
- Kept disclosure markers on the candlestick series via the local `createSeriesMarkers` wrapper.
- Added frontend tests for no external logo-obligation dependency, interaction support, and viewport preservation.

Verification:
- `node --test tests/frontend/priceChart.test.mjs`
- `node --test tests/frontend/*.test.mjs`

## Graph View Chart-Focused Workspace

Purpose: Remove low-value `회사 검색` and `데이터 상태` top modes from `Graph View`, align the top selector with the compact workflow menu pattern used by `공시원문 외부 저장`, and make the `주가-공시 차트` easier to view at full size.

Implementation summary:
- Replaced the large `분석`/`회사`/`데이터` mode cards with a compact top selector for `차트` and `공시 타임라인`.
- Moved company lookup into the right `설정` dock as `회사 선택`, keeping the function available without making it a primary workspace mode.
- Removed the visible data-status mode from the Graph View workspace; source/readiness problems still surface through messages and the right notification/activity dock.
- Added an app-level chart fullscreen overlay with `전체화면` and `전체화면 닫기`, reusing the same FINIQ-owned `PriceChart` renderer instead of any third-party branded runtime.
- Updated Ontology UI terminology and frontend static coverage for the new labels and removed mode names.

Verification:
- `node --test tests/frontend/ontologyGraphWorkspace.test.mjs`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Browser smoke check on `http://127.0.0.1:3001/graph`: `Graph View`, `차트`, `공시 타임라인`, and active `전체화면` button are visible; `회사 검색` and `데이터 상태` are not visible on the page.
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`

## Graph View Chart Zoom Sensitivity

Purpose: Reduce the default `주가-공시 차트` zoom sensitivity and make it adjustable from the `Graph View` right settings panel.

Implementation summary:
- Added a `zoomSensitivity` option to `PriceChart` and the FINIQ-owned canvas chart renderer.
- Changed wheel zoom factors to use a clamped sensitivity value, with the new default set lower than the prior fixed zoom step.
- Added the `Graph View` right `설정` dock with `확대/축소 민감도` controls.
- Provided both a range slider and a percent number input so users can make coarse or precise adjustments.
- Added UI terminology and frontend tests for the new setting and chart option propagation.

Verification:
- `node --test tests/frontend/*.test.mjs`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
- Browser check on `http://localhost:3001/graph`: settings dock opened, `확대/축소 민감도` controls rendered, number input `35` synced the slider to `0.35`, chart canvas loaded, and no localhost console errors appeared.

## Graph View Settings Input Tone

Purpose: Align the `Graph View` right settings panel sensitivity number input with the existing input text/background styling.

Implementation summary:
- Added the existing dark input class pattern to the `확대/축소 민감도` percent input.
- Added frontend static coverage so the settings input keeps the same dark background, border, and text tone as other MarketDesk inputs.

Verification:
- `node --test tests/frontend/ontologyGraphWorkspace.test.mjs`
- `node --test tests/frontend/*.test.mjs`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`

## Graph View Full-Range Disclosure Analysis

Purpose: Make `Graph View` focus on stock selection, default the `주가-공시 차트` to the full available date range, and replace the low-value `분석 요약` area with usable disclosure timeline and analysis surfaces.

Implementation summary:
- Changed Ontology company identifiers and stock labels to the `A000000` format while keeping Kind queries compatible with numeric company IDs.
- Made company panels default to the full available price/disclosure range when no manual date range is provided.
- Removed the visible `분석 조건` box and moved stock selection into the top chart toolbar.
- Removed the chart/timeline mode switch so the top toolbar only changes the active stock.
- Replaced `분석 요약` with `공시 타임라인`, and placed `공시 분석` in the former timeline area below it.
- Added a first-pass Triple Barrier Method analysis table using 5% upper/lower barriers and a 20-trading-day horizon.
- Updated Ontology UI terminology and regression coverage for full-range defaults, A-code selection, and disclosure analysis labels.

Verification:
- `node --test tests/frontend/ontologyGraphWorkspace.test.mjs`
- `python3 -m pytest tests/market_desk/test_ontology_graph.py -q`
- `npm --prefix frontend/finiq_GUI/apps/market-desk run build`
