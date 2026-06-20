# Triple Barrier Disclosure Analysis Design

## Purpose

Add real Triple Barrier Method execution to the existing `공시 분석` page. The feature must let a user select disclosure events for a stock, configure barrier parameters, calculate labels from Quantiwise price data, store the results, and reload those results later for backtests or model training.

## Current Context

The current `공시 분석` page at `frontend/finiq_GUI/apps/market-desk/src/app/graph/analysis/DisclosureAnalysisWorkspace.tsx` runs a frontend-only backtest through `frontend/finiq_GUI/apps/market-desk/src/lib/disclosureBacktests.ts`. That code uses fixed constants for upper barrier, lower barrier, and horizon. It does not persist results.

The backend already has the data required to run this server-side:

- KIND disclosure SQLite manifest loading in `src/finiq/market_desk/analytics/ontology_graph.py`.
- Quantiwise OHLCV parquet loading in `src/finiq/market_desk/analytics/ontology_graph.py`.
- Ontology API routes in `src/finiq/market_desk/web/routers/market_data.py`.

## Recommended Architecture

Create a dedicated backend Triple Barrier analysis module and expose it through the existing MarketDesk API. Store results in a separate SQLite database named `triple_barrier_results.sqlite` next to the selected KIND SQLite manifest. Do not modify KIND source shards.

This keeps source disclosures immutable, makes generated labels easy to reuse, and avoids mixing analysis output with ingestion artifacts.

## Backend Components

### Analysis Module

Create `src/finiq/market_desk/analytics/triple_barrier.py`.

Responsibilities:

- Load disclosure events for a selected stock using the same manifest conventions as Ontology.
- Optionally narrow execution to selected disclosure IDs.
- Load daily OHLCV rows from Quantiwise parquet.
- Normalize event time from either `disclosed_date` or `disclosed_at`.
- Calculate Triple Barrier labels from configurable parameters.
- Persist and query results from the result SQLite database.

The calculation core should be a small pure function that accepts normalized disclosure rows, normalized price rows, and parameter values. It should not depend on FastAPI.

### API Routes

Add routes to `create_market_data_router`:

- `POST /api/ontology/triple-barrier/run`
- `GET /api/ontology/triple-barrier/results`

`POST /run` calculates and stores results for the selected company and parameter set. `GET /results` returns stored rows for the selected company and optional parameter filters.

## Data Model

Create table `triple_barrier_results` in `triple_barrier_results.sqlite`.

Fields:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `source_manifest_path TEXT NOT NULL`
- `disclosure_id TEXT NOT NULL`
- `ticker TEXT NOT NULL`
- `company_name TEXT NOT NULL`
- `event_datetime TEXT NOT NULL`
- `event_price REAL`
- `upper_pct REAL NOT NULL`
- `lower_pct REAL NOT NULL`
- `vertical_days INTEGER NOT NULL`
- `upper_price REAL`
- `lower_price REAL`
- `vertical_datetime TEXT`
- `touched_barrier TEXT NOT NULL`
- `touched_datetime TEXT`
- `touched_price REAL`
- `return_pct REAL`
- `label INTEGER`
- `price_source TEXT NOT NULL`
- `event_time_basis TEXT NOT NULL`
- `price_basis TEXT NOT NULL`
- `calculation_params_json TEXT NOT NULL`
- `parameter_hash TEXT NOT NULL`
- `status TEXT NOT NULL`
- `error_message TEXT NOT NULL DEFAULT ''`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Unique key:

- `(source_manifest_path, disclosure_id, ticker, parameter_hash)`

This prevents duplicate execution for the same disclosure and parameter combination while allowing the same disclosure to be labeled with different settings.

Allowed `touched_barrier` values:

- `upper`
- `lower`
- `vertical`
- `error`

Allowed `status` values:

- `pending`
- `completed`
- `failed`

## Parameter Hash

Generate `parameter_hash` from canonical JSON containing:

- `event_time_basis`
- `price_basis`
- `upper_pct`
- `lower_pct`
- `vertical_days`
- `price_source`

Use sorted keys and stable numeric values. Hash with SHA-256.

## Calculation Rules

Inputs:

- `upper_pct`: percent value such as `5` for `+5%`.
- `lower_pct`: percent value such as `3` for `-3%`.
- `vertical_days`: number of trading rows after the event row.
- `event_time_basis`: `disclosed_date` or `disclosed_at`.
- `price_basis`: `close` or `intraday`.

Event price:

- Use the first available trading day whose date is on or after the event date.
- For `price_basis=close`, use that row's close as `event_price`.
- For `price_basis=intraday`, still use close as event entry price, but use high/low to determine barrier touches.

Barrier prices:

- `upper_price = event_price * (1 + upper_pct / 100)`
- `lower_price = event_price * (1 - lower_pct / 100)`

Barrier scan:

- Scan trading rows after the event row through `event_index + vertical_days`.
- If `price_basis=close`, upper/lower touches are tested against close.
- If `price_basis=intraday`, upper touches are tested against high and lower touches against low.
- The first touched barrier wins.
- If upper and lower are both touched on the same row, choose upper first. Daily OHLCV cannot determine intraday order, so this tie rule must be explicit and test-covered.

Labels:

- Upper first: `touched_barrier=upper`, `label=1`.
- Lower first: `touched_barrier=lower`, `label=-1`.
- Neither before vertical barrier: `touched_barrier=vertical`, `label=0`.
- Missing disclosure/price data: `touched_barrier=error`, `status=failed`, `label` is null, and `error_message` explains the failure.

Return:

- For upper/lower, use `(touched_price - event_price) / event_price * 100`.
- For vertical, use the vertical row's close price and store that return.

## UI Design

Update `DisclosureAnalysisWorkspace.tsx` from a frontend-only backtest view to an API-backed execution workspace.

Inputs:

- `종목 선택`: existing company search and select behavior.
- `공시 목록 선택`: default to all loaded disclosures for the selected stock and group, with row selection available when the user wants to run only part of the list.
- `이벤트 기준일`: options `공시일` and `공시시각`.
- `가격 기준`: options `종가 기준` and `장중 고가/저가 기준`.
- `Upper barrier`: numeric percent input, default `5`.
- `Lower barrier`: numeric percent input, default `3`.
- `Vertical barrier`: select or numeric input for trading days, default `20`, with common choices `5`, `10`, `20`.
- Run button: `Triple Barrier 실행`.

Status:

- Show loading state while the run API is active.
- Show total/completed/failed counts after execution.
- Show API error text when execution fails.

Result table columns:

- 공시 ID
- 종목코드
- 종목명
- 공시일
- 이벤트 가격
- upper barrier 가격
- lower barrier 가격
- vertical barrier 날짜
- 최초 도달 barrier
- 최초 도달 날짜
- 최초 도달 가격
- 수익률
- label
- 계산 상태
- 에러 메시지

The table should render stored API results, not client-only calculations.

## API Payloads

Run request:

```json
{
  "manifest_path": "",
  "quanti_dir": "",
  "company_id": "A005930",
  "market": "전체",
  "disclosure_group": "전체",
  "disclosure_ids": [],
  "event_time_basis": "disclosed_date",
  "price_basis": "intraday",
  "upper_pct": 5,
  "lower_pct": 3,
  "vertical_days": 20
}
```

Run response:

```json
{
  "summary": {
    "total": 0,
    "completed": 0,
    "failed": 0,
    "reused": 0,
    "created": 0
  },
  "result_db_path": "",
  "parameter_hash": "",
  "rows": []
}
```

Results response:

```json
{
  "summary": {
    "total": 0,
    "completed": 0,
    "failed": 0
  },
  "result_db_path": "",
  "rows": []
}
```

## Testing Strategy

Use TDD for implementation.

Backend tests:

- Pure calculation labels upper, lower, and vertical outcomes correctly.
- Intraday mode uses high/low for touches.
- Close mode uses close for touches.
- Missing price rows create failed rows with `touched_barrier=error`.
- Parameter hash is stable for equivalent parameter JSON.
- SQLite storage enforces unique `(source_manifest_path, disclosure_id, ticker, parameter_hash)`.
- `POST /api/ontology/triple-barrier/run` stores rows and does not duplicate rows on identical rerun.
- `GET /api/ontology/triple-barrier/results` returns stored rows.

Frontend tests:

- `DisclosureAnalysisWorkspace.tsx` calls `/api/ontology/triple-barrier/run`.
- The page includes required controls and result table columns.
- The page no longer depends on frontend-only `runDisclosureBacktest` for persisted results.

## Documentation

Update:

- `docs/ui-terminology.md` with Triple Barrier execution terms if new UI labels are introduced.
- `PLANS.md` after code changes are complete with purpose, implementation summary, and verification result.

## Out of Scope

- Intraday minute-level sequencing. Current Quantiwise data is daily OHLCV, so same-day upper/lower tie resolution is explicit but not intraday-accurate.
- Background job queueing. Initial implementation can run synchronously because the existing page works on a selected stock and visible disclosure set.
- Model training and backtest UI. The stored result schema is designed for reuse, but training workflows are not part of this change.
