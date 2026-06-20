# Triple Barrier Disclosure Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build real Triple Barrier Method execution on the existing `공시 분석` page, with configurable parameters, backend calculation, SQLite persistence, duplicate prevention, and result lookup.

**Architecture:** Add `src/finiq/market_desk/analytics/triple_barrier.py` as the backend boundary for calculation, data loading, storage, and API payload construction. Add API routes under the existing MarketDesk ontology router. Replace the current frontend-only backtest view with an API-backed execution panel and stored result table.

**Tech Stack:** Python 3.11+, FastAPI, sqlite3, pandas, pyarrow parquet through existing project usage, Next.js 16 canary app router, React 19, TypeScript, Node built-in test runner.

## Global Constraints

- Store results in a separate SQLite database named `triple_barrier_results.sqlite` next to the selected KIND SQLite manifest.
- Do not modify KIND source shards.
- Use `source_manifest_path, disclosure_id, ticker, parameter_hash` as the uniqueness boundary.
- Support `event_time_basis` values `disclosed_date` and `disclosed_at`.
- Support `price_basis` values `close` and `intraday`.
- Default UI values: upper barrier `5`, lower barrier `3`, vertical barrier `20`.
- The result table must render stored API results, not client-only calculations.
- Update `docs/ui-terminology.md` before adding new UI labels.
- Update `PLANS.md` after code changes are complete with purpose, implementation summary, and verification result.
- Keep changes surgical; do not refactor unrelated chart or ontology files.

---

## File Structure

- Create `src/finiq/market_desk/analytics/triple_barrier.py`: normalized dataclasses, parameter hashing, pure Triple Barrier calculation, SQLite storage, data loading orchestration, API response builders.
- Modify `src/finiq/market_desk/web/routers/market_data.py`: add request models and two routes for run/results.
- Modify `frontend/finiq_GUI/apps/market-desk/src/app/graph/analysis/DisclosureAnalysisWorkspace.tsx`: replace local backtest execution with API-backed controls and stored result table.
- Modify `docs/ui-terminology.md`: add Triple Barrier execution labels under Ontology Workflow.
- Modify `PLANS.md`: append final implementation and verification summary after implementation.
- Create `tests/market_desk/test_triple_barrier.py`: pure calculation and SQLite storage tests.
- Modify `tests/market_desk/test_ontology_graph.py`: add API route tests using existing fixture helpers.
- Modify `tests/frontend/ontologyGraphWorkspace.test.mjs`: assert the analysis page calls the new API and exposes required controls/table columns.

---

### Task 1: Pure Triple Barrier Calculation

**Files:**
- Create: `src/finiq/market_desk/analytics/triple_barrier.py`
- Create: `tests/market_desk/test_triple_barrier.py`

**Interfaces:**
- Consumes: no project-specific interfaces.
- Produces:
  - `@dataclass(frozen=True) class TripleBarrierDisclosure`
  - `@dataclass(frozen=True) class TripleBarrierPrice`
  - `@dataclass(frozen=True) class TripleBarrierParams`
  - `@dataclass(frozen=True) class TripleBarrierResult`
  - `build_parameter_hash(params: TripleBarrierParams) -> tuple[str, str]`
  - `calculate_triple_barrier_rows(disclosures: list[TripleBarrierDisclosure], prices: list[TripleBarrierPrice], params: TripleBarrierParams, *, source_manifest_path: str) -> list[TripleBarrierResult]`

- [ ] **Step 1: Write the failing calculation tests**

Create `tests/market_desk/test_triple_barrier.py` with this initial content:

```python
from __future__ import annotations

from finiq.market_desk.analytics.triple_barrier import (
    TripleBarrierDisclosure,
    TripleBarrierParams,
    TripleBarrierPrice,
    build_parameter_hash,
    calculate_triple_barrier_rows,
)


def _disclosure(acpt_no: str = "20250102000001", disclosed_at: str = "2025-01-02 09:10") -> TripleBarrierDisclosure:
    return TripleBarrierDisclosure(
        disclosure_id=acpt_no,
        ticker="A005930",
        company_name="테스트전자",
        event_datetime=disclosed_at,
        disclosed_date=disclosed_at[:10],
    )


def _prices() -> list[TripleBarrierPrice]:
    return [
        TripleBarrierPrice(date="2025-01-02", open=100, high=101, low=99, close=100, volume=1000),
        TripleBarrierPrice(date="2025-01-03", open=101, high=106, low=100, close=102, volume=1100),
        TripleBarrierPrice(date="2025-01-06", open=102, high=103, low=96, close=97, volume=1200),
        TripleBarrierPrice(date="2025-01-07", open=97, high=98, low=94, close=95, volume=1300),
    ]


def test_intraday_mode_labels_upper_when_high_touches_first() -> None:
    params = TripleBarrierParams(
        event_time_basis="disclosed_date",
        price_basis="intraday",
        upper_pct=5,
        lower_pct=3,
        vertical_days=3,
        price_source="quantiwise",
    )

    rows = calculate_triple_barrier_rows([_disclosure()], _prices(), params, source_manifest_path="/kind/manifest.json")

    assert len(rows) == 1
    row = rows[0]
    assert row.status == "completed"
    assert row.touched_barrier == "upper"
    assert row.label == 1
    assert row.event_price == 100
    assert row.upper_price == 105
    assert row.lower_price == 97
    assert row.touched_datetime == "2025-01-03"
    assert row.touched_price == 105
    assert row.return_pct == 5


def test_close_mode_ignores_intraday_high_and_labels_lower_on_close() -> None:
    params = TripleBarrierParams(
        event_time_basis="disclosed_date",
        price_basis="close",
        upper_pct=5,
        lower_pct=3,
        vertical_days=3,
        price_source="quantiwise",
    )

    rows = calculate_triple_barrier_rows([_disclosure()], _prices(), params, source_manifest_path="/kind/manifest.json")

    row = rows[0]
    assert row.status == "completed"
    assert row.touched_barrier == "lower"
    assert row.label == -1
    assert row.touched_datetime == "2025-01-06"
    assert row.touched_price == 97
    assert row.return_pct == -3


def test_vertical_barrier_labels_zero_and_stores_vertical_return() -> None:
    params = TripleBarrierParams(
        event_time_basis="disclosed_date",
        price_basis="close",
        upper_pct=20,
        lower_pct=20,
        vertical_days=2,
        price_source="quantiwise",
    )

    rows = calculate_triple_barrier_rows([_disclosure()], _prices(), params, source_manifest_path="/kind/manifest.json")

    row = rows[0]
    assert row.status == "completed"
    assert row.touched_barrier == "vertical"
    assert row.label == 0
    assert row.vertical_datetime == "2025-01-06"
    assert row.touched_datetime == "2025-01-06"
    assert row.touched_price == 97
    assert row.return_pct == -3


def test_missing_price_creates_failed_error_row() -> None:
    params = TripleBarrierParams(
        event_time_basis="disclosed_date",
        price_basis="intraday",
        upper_pct=5,
        lower_pct=3,
        vertical_days=20,
        price_source="quantiwise",
    )

    rows = calculate_triple_barrier_rows([_disclosure(disclosed_at="2030-01-02 09:10")], _prices(), params, source_manifest_path="/kind/manifest.json")

    row = rows[0]
    assert row.status == "failed"
    assert row.touched_barrier == "error"
    assert row.label is None
    assert "price" in row.error_message.lower()


def test_parameter_hash_is_stable_for_equivalent_params() -> None:
    params = TripleBarrierParams(
        event_time_basis="disclosed_date",
        price_basis="intraday",
        upper_pct=5.0,
        lower_pct=3.0,
        vertical_days=20,
        price_source="quantiwise",
    )

    first_hash, first_json = build_parameter_hash(params)
    second_hash, second_json = build_parameter_hash(params)

    assert first_hash == second_hash
    assert first_json == second_json
    assert "disclosed_date" in first_json
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
pytest tests/market_desk/test_triple_barrier.py -v
```

Expected: FAIL during import with `ModuleNotFoundError: No module named 'finiq.market_desk.analytics.triple_barrier'`.

- [ ] **Step 3: Implement the minimal calculation module**

Create `src/finiq/market_desk/analytics/triple_barrier.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from typing import Any


@dataclass(frozen=True)
class TripleBarrierDisclosure:
    disclosure_id: str
    ticker: str
    company_name: str
    event_datetime: str
    disclosed_date: str


@dataclass(frozen=True)
class TripleBarrierPrice:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


@dataclass(frozen=True)
class TripleBarrierParams:
    event_time_basis: str
    price_basis: str
    upper_pct: float
    lower_pct: float
    vertical_days: int
    price_source: str = "quantiwise"


@dataclass(frozen=True)
class TripleBarrierResult:
    source_manifest_path: str
    disclosure_id: str
    ticker: str
    company_name: str
    event_datetime: str
    event_price: float | None
    upper_pct: float
    lower_pct: float
    vertical_days: int
    upper_price: float | None
    lower_price: float | None
    vertical_datetime: str
    touched_barrier: str
    touched_datetime: str
    touched_price: float | None
    return_pct: float | None
    label: int | None
    price_source: str
    event_time_basis: str
    price_basis: str
    calculation_params_json: str
    parameter_hash: str
    status: str
    error_message: str = ""
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""


def _stable_number(value: float) -> float | int:
    number = float(value)
    return int(number) if number.is_integer() else number


def build_parameter_hash(params: TripleBarrierParams) -> tuple[str, str]:
    payload = {
        "event_time_basis": params.event_time_basis,
        "lower_pct": _stable_number(params.lower_pct),
        "price_basis": params.price_basis,
        "price_source": params.price_source,
        "upper_pct": _stable_number(params.upper_pct),
        "vertical_days": int(params.vertical_days),
    }
    params_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(params_json.encode("utf-8")).hexdigest(), params_json


def _event_date(disclosure: TripleBarrierDisclosure, params: TripleBarrierParams) -> str:
    if params.event_time_basis == "disclosed_at":
        return str(disclosure.event_datetime or disclosure.disclosed_date)[:10]
    return str(disclosure.disclosed_date or disclosure.event_datetime)[:10]


def _round_price(value: float | None) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), 10)


def _round_return(value: float | None) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), 10)


def _error_result(
    disclosure: TripleBarrierDisclosure,
    params: TripleBarrierParams,
    *,
    source_manifest_path: str,
    parameter_hash: str,
    params_json: str,
    message: str,
) -> TripleBarrierResult:
    return TripleBarrierResult(
        source_manifest_path=source_manifest_path,
        disclosure_id=disclosure.disclosure_id,
        ticker=disclosure.ticker,
        company_name=disclosure.company_name,
        event_datetime=disclosure.event_datetime,
        event_price=None,
        upper_pct=float(params.upper_pct),
        lower_pct=float(params.lower_pct),
        vertical_days=int(params.vertical_days),
        upper_price=None,
        lower_price=None,
        vertical_datetime="",
        touched_barrier="error",
        touched_datetime="",
        touched_price=None,
        return_pct=None,
        label=None,
        price_source=params.price_source,
        event_time_basis=params.event_time_basis,
        price_basis=params.price_basis,
        calculation_params_json=params_json,
        parameter_hash=parameter_hash,
        status="failed",
        error_message=message,
    )


def calculate_triple_barrier_rows(
    disclosures: list[TripleBarrierDisclosure],
    prices: list[TripleBarrierPrice],
    params: TripleBarrierParams,
    *,
    source_manifest_path: str,
) -> list[TripleBarrierResult]:
    parameter_hash, params_json = build_parameter_hash(params)
    sorted_prices = sorted(prices, key=lambda row: row.date)
    results: list[TripleBarrierResult] = []
    for disclosure in disclosures:
        event_day = _event_date(disclosure, params)
        event_index = next((index for index, price in enumerate(sorted_prices) if price.date >= event_day), -1)
        if event_index < 0:
            results.append(
                _error_result(
                    disclosure,
                    params,
                    source_manifest_path=source_manifest_path,
                    parameter_hash=parameter_hash,
                    params_json=params_json,
                    message=f"No price row found on or after event date {event_day}",
                )
            )
            continue

        event_price_row = sorted_prices[event_index]
        event_price = float(event_price_row.close)
        if event_price <= 0:
            results.append(
                _error_result(
                    disclosure,
                    params,
                    source_manifest_path=source_manifest_path,
                    parameter_hash=parameter_hash,
                    params_json=params_json,
                    message=f"Invalid event price for {event_day}",
                )
            )
            continue

        upper_price = event_price * (1 + float(params.upper_pct) / 100)
        lower_price = event_price * (1 - float(params.lower_pct) / 100)
        last_index = min(len(sorted_prices) - 1, event_index + int(params.vertical_days))
        vertical_row = sorted_prices[last_index]
        touched_barrier = "vertical"
        touched_row = vertical_row
        touched_price = float(vertical_row.close)
        label = 0

        for price in sorted_prices[event_index + 1 : last_index + 1]:
            upper_value = float(price.high if params.price_basis == "intraday" else price.close)
            lower_value = float(price.low if params.price_basis == "intraday" else price.close)
            if upper_value >= upper_price:
                touched_barrier = "upper"
                touched_row = price
                touched_price = upper_price if params.price_basis == "intraday" else float(price.close)
                label = 1
                break
            if lower_value <= lower_price:
                touched_barrier = "lower"
                touched_row = price
                touched_price = lower_price if params.price_basis == "intraday" else float(price.close)
                label = -1
                break

        results.append(
            TripleBarrierResult(
                source_manifest_path=source_manifest_path,
                disclosure_id=disclosure.disclosure_id,
                ticker=disclosure.ticker,
                company_name=disclosure.company_name,
                event_datetime=disclosure.event_datetime,
                event_price=_round_price(event_price),
                upper_pct=float(params.upper_pct),
                lower_pct=float(params.lower_pct),
                vertical_days=int(params.vertical_days),
                upper_price=_round_price(upper_price),
                lower_price=_round_price(lower_price),
                vertical_datetime=vertical_row.date,
                touched_barrier=touched_barrier,
                touched_datetime=touched_row.date,
                touched_price=_round_price(touched_price),
                return_pct=_round_return(((touched_price - event_price) / event_price) * 100),
                label=label,
                price_source=params.price_source,
                event_time_basis=params.event_time_basis,
                price_basis=params.price_basis,
                calculation_params_json=params_json,
                parameter_hash=parameter_hash,
                status="completed",
            )
        )
    return results
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
pytest tests/market_desk/test_triple_barrier.py -v
```

Expected: PASS all 5 tests.

- [ ] **Step 5: Commit**

```bash
git add tests/market_desk/test_triple_barrier.py src/finiq/market_desk/analytics/triple_barrier.py
git commit -m "feat: add triple barrier calculation"
```

---

### Task 2: SQLite Result Storage

**Files:**
- Modify: `src/finiq/market_desk/analytics/triple_barrier.py`
- Modify: `tests/market_desk/test_triple_barrier.py`

**Interfaces:**
- Consumes: `TripleBarrierResult` from Task 1.
- Produces:
  - `default_result_db_path(manifest_path: str | Path) -> Path`
  - `init_triple_barrier_db(db_path: str | Path) -> None`
  - `save_triple_barrier_results(db_path: str | Path, rows: list[TripleBarrierResult]) -> dict[str, int]`
  - `load_triple_barrier_results(db_path: str | Path, *, ticker: str = "", parameter_hash: str = "") -> list[TripleBarrierResult]`

- [ ] **Step 1: Write the failing storage test**

Append this test to `tests/market_desk/test_triple_barrier.py`:

```python
from pathlib import Path
import sqlite3


def test_sqlite_storage_prevents_duplicate_disclosure_parameter_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "triple_barrier_results.sqlite"
    params = TripleBarrierParams(
        event_time_basis="disclosed_date",
        price_basis="intraday",
        upper_pct=5,
        lower_pct=3,
        vertical_days=3,
        price_source="quantiwise",
    )
    rows = calculate_triple_barrier_rows([_disclosure()], _prices(), params, source_manifest_path="/kind/manifest.json")

    first = save_triple_barrier_results(db_path, rows)
    second = save_triple_barrier_results(db_path, rows)
    stored = load_triple_barrier_results(db_path, ticker="A005930")

    assert first == {"created": 1, "reused": 0}
    assert second == {"created": 0, "reused": 1}
    assert len(stored) == 1
    assert stored[0].disclosure_id == "20250102000001"
    assert stored[0].parameter_hash == rows[0].parameter_hash

    with sqlite3.connect(db_path) as connection:
        index_rows = connection.execute("PRAGMA index_list(triple_barrier_results)").fetchall()
    assert any(row[2] for row in index_rows)
```

Update the import block in the same file:

```python
from finiq.market_desk.analytics.triple_barrier import (
    TripleBarrierDisclosure,
    TripleBarrierParams,
    TripleBarrierPrice,
    build_parameter_hash,
    calculate_triple_barrier_rows,
    load_triple_barrier_results,
    save_triple_barrier_results,
)
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
pytest tests/market_desk/test_triple_barrier.py::test_sqlite_storage_prevents_duplicate_disclosure_parameter_rows -v
```

Expected: FAIL with `ImportError` for `load_triple_barrier_results` or `save_triple_barrier_results`.

- [ ] **Step 3: Implement SQLite storage functions**

Append these functions and constants to `src/finiq/market_desk/analytics/triple_barrier.py`:

```python
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


RESULT_TABLE = "triple_barrier_results"


def default_result_db_path(manifest_path: str | Path) -> Path:
    return Path(manifest_path).expanduser().resolve().parent / "triple_barrier_results.sqlite"


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_triple_barrier_db(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS triple_barrier_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_manifest_path TEXT NOT NULL,
                disclosure_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                company_name TEXT NOT NULL,
                event_datetime TEXT NOT NULL,
                event_price REAL,
                upper_pct REAL NOT NULL,
                lower_pct REAL NOT NULL,
                vertical_days INTEGER NOT NULL,
                upper_price REAL,
                lower_price REAL,
                vertical_datetime TEXT,
                touched_barrier TEXT NOT NULL,
                touched_datetime TEXT,
                touched_price REAL,
                return_pct REAL,
                label INTEGER,
                price_source TEXT NOT NULL,
                event_time_basis TEXT NOT NULL,
                price_basis TEXT NOT NULL,
                calculation_params_json TEXT NOT NULL,
                parameter_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(source_manifest_path, disclosure_id, ticker, parameter_hash)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_triple_barrier_results_ticker
            ON triple_barrier_results(ticker, parameter_hash, event_datetime)
            """
        )


def _row_values(row: TripleBarrierResult, now_text: str) -> tuple[Any, ...]:
    return (
        row.source_manifest_path,
        row.disclosure_id,
        row.ticker,
        row.company_name,
        row.event_datetime,
        row.event_price,
        row.upper_pct,
        row.lower_pct,
        row.vertical_days,
        row.upper_price,
        row.lower_price,
        row.vertical_datetime,
        row.touched_barrier,
        row.touched_datetime,
        row.touched_price,
        row.return_pct,
        row.label,
        row.price_source,
        row.event_time_basis,
        row.price_basis,
        row.calculation_params_json,
        row.parameter_hash,
        row.status,
        row.error_message,
        now_text,
        now_text,
    )


def save_triple_barrier_results(db_path: str | Path, rows: list[TripleBarrierResult]) -> dict[str, int]:
    init_triple_barrier_db(db_path)
    created = 0
    reused = 0
    now_text = _utc_now_text()
    with sqlite3.connect(db_path) as connection:
        for row in rows:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO triple_barrier_results (
                    source_manifest_path, disclosure_id, ticker, company_name, event_datetime,
                    event_price, upper_pct, lower_pct, vertical_days, upper_price, lower_price,
                    vertical_datetime, touched_barrier, touched_datetime, touched_price,
                    return_pct, label, price_source, event_time_basis, price_basis,
                    calculation_params_json, parameter_hash, status, error_message,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _row_values(row, now_text),
            )
            if cursor.rowcount:
                created += 1
            else:
                reused += 1
    return {"created": created, "reused": reused}


def _result_from_sqlite(row: sqlite3.Row) -> TripleBarrierResult:
    return TripleBarrierResult(
        id=int(row["id"]),
        source_manifest_path=str(row["source_manifest_path"]),
        disclosure_id=str(row["disclosure_id"]),
        ticker=str(row["ticker"]),
        company_name=str(row["company_name"]),
        event_datetime=str(row["event_datetime"]),
        event_price=row["event_price"],
        upper_pct=float(row["upper_pct"]),
        lower_pct=float(row["lower_pct"]),
        vertical_days=int(row["vertical_days"]),
        upper_price=row["upper_price"],
        lower_price=row["lower_price"],
        vertical_datetime=str(row["vertical_datetime"] or ""),
        touched_barrier=str(row["touched_barrier"]),
        touched_datetime=str(row["touched_datetime"] or ""),
        touched_price=row["touched_price"],
        return_pct=row["return_pct"],
        label=row["label"],
        price_source=str(row["price_source"]),
        event_time_basis=str(row["event_time_basis"]),
        price_basis=str(row["price_basis"]),
        calculation_params_json=str(row["calculation_params_json"]),
        parameter_hash=str(row["parameter_hash"]),
        status=str(row["status"]),
        error_message=str(row["error_message"] or ""),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def load_triple_barrier_results(
    db_path: str | Path,
    *,
    ticker: str = "",
    parameter_hash: str = "",
) -> list[TripleBarrierResult]:
    path = Path(db_path)
    if not path.exists():
        return []
    clauses: list[str] = []
    params: list[Any] = []
    if ticker:
        clauses.append("ticker = ?")
        params.append(ticker)
    if parameter_hash:
        clauses.append("parameter_hash = ?")
        params.append(parameter_hash)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            f"""
            SELECT *
            FROM triple_barrier_results
            {where_sql}
            ORDER BY event_datetime ASC, disclosure_id ASC
            """,
            params,
        ).fetchall()
    return [_result_from_sqlite(row) for row in rows]
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
pytest tests/market_desk/test_triple_barrier.py -v
```

Expected: PASS all tests.

- [ ] **Step 5: Commit**

```bash
git add tests/market_desk/test_triple_barrier.py src/finiq/market_desk/analytics/triple_barrier.py
git commit -m "feat: persist triple barrier results"
```

---

### Task 3: Backend Orchestration and API Routes

**Files:**
- Modify: `src/finiq/market_desk/analytics/triple_barrier.py`
- Modify: `src/finiq/market_desk/web/routers/market_data.py`
- Modify: `tests/market_desk/test_ontology_graph.py`

**Interfaces:**
- Consumes:
  - `calculate_triple_barrier_rows(...)`
  - `save_triple_barrier_results(...)`
  - existing helper patterns in `ontology_graph.py`
- Produces:
  - `run_triple_barrier_analysis(...) -> dict[str, Any]`
  - `get_triple_barrier_results_payload(...) -> dict[str, Any]`
  - API route `POST /api/ontology/triple-barrier/run`
  - API route `GET /api/ontology/triple-barrier/results`

- [ ] **Step 1: Write failing API tests**

Append this test to `tests/market_desk/test_ontology_graph.py`:

```python
def test_triple_barrier_api_runs_stores_and_reuses_results(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)
    api = FastAPI()
    api.include_router(
        create_market_data_router(
            AppConfig(output_root=str(tmp_path), quanti_dir=str(quanti_dir)),
        )
    )
    client = TestClient(api)

    payload = {
        "manifest_path": str(manifest_path),
        "quanti_dir": str(quanti_dir),
        "company_id": "A005930",
        "market": "전체",
        "disclosure_group": "전체",
        "disclosure_ids": ["20250102000001"],
        "event_time_basis": "disclosed_date",
        "price_basis": "intraday",
        "upper_pct": 5,
        "lower_pct": 3,
        "vertical_days": 2,
    }

    first = client.post("/api/ontology/triple-barrier/run", json=payload)
    second = client.post("/api/ontology/triple-barrier/run", json=payload)
    listed = client.get(
        "/api/ontology/triple-barrier/results",
        params={
            "manifest_path": str(manifest_path),
            "company_id": "A005930",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert listed.status_code == 200
    assert first.json()["summary"]["created"] == 1
    assert first.json()["summary"]["reused"] == 0
    assert second.json()["summary"]["created"] == 0
    assert second.json()["summary"]["reused"] == 1
    assert first.json()["summary"]["completed"] == 1
    assert first.json()["rows"][0]["disclosure_id"] == "20250102000001"
    assert first.json()["rows"][0]["ticker"] == "A005930"
    assert first.json()["rows"][0]["label"] == 1
    assert listed.json()["summary"]["total"] == 1
    assert listed.json()["rows"][0]["parameter_hash"] == first.json()["parameter_hash"]
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
pytest tests/market_desk/test_ontology_graph.py::test_triple_barrier_api_runs_stores_and_reuses_results -v
```

Expected: FAIL with HTTP 404 for `/api/ontology/triple-barrier/run`.

- [ ] **Step 3: Add orchestration helpers**

Append these imports near the top of `src/finiq/market_desk/analytics/triple_barrier.py`:

```python
import pandas as pd
import pyarrow.parquet as pq

from finiq.market_desk.analytics.ontology_graph import (
    DEFAULT_KIND_MANIFEST_PATH,
    DEFAULT_QUANTIWISE_PARQUET_DIR,
)
```

Append this API-facing code to the same file:

```python
def result_to_dict(row: TripleBarrierResult) -> dict[str, Any]:
    return {
        "id": row.id,
        "source_manifest_path": row.source_manifest_path,
        "disclosure_id": row.disclosure_id,
        "ticker": row.ticker,
        "company_name": row.company_name,
        "event_datetime": row.event_datetime,
        "event_price": row.event_price,
        "upper_pct": row.upper_pct,
        "lower_pct": row.lower_pct,
        "vertical_days": row.vertical_days,
        "upper_price": row.upper_price,
        "lower_price": row.lower_price,
        "vertical_datetime": row.vertical_datetime,
        "touched_barrier": row.touched_barrier,
        "touched_datetime": row.touched_datetime,
        "touched_price": row.touched_price,
        "return_pct": row.return_pct,
        "label": row.label,
        "price_source": row.price_source,
        "event_time_basis": row.event_time_basis,
        "price_basis": row.price_basis,
        "calculation_params_json": row.calculation_params_json,
        "parameter_hash": row.parameter_hash,
        "status": row.status,
        "error_message": row.error_message,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _summary(rows: list[TripleBarrierResult], storage_counts: dict[str, int] | None = None) -> dict[str, int]:
    counts = storage_counts or {}
    return {
        "total": len(rows),
        "completed": sum(1 for row in rows if row.status == "completed"),
        "failed": sum(1 for row in rows if row.status == "failed"),
        "created": int(counts.get("created", 0)),
        "reused": int(counts.get("reused", 0)),
    }


def _display_stock_code(company_id: str) -> str:
    raw = str(company_id or "").strip().upper()
    digits = "".join(char for char in raw if char.isdigit())
    return f"A{digits.zfill(6)}" if digits else raw


def _kind_company_id(company_id: str) -> str:
    digits = "".join(char for char in str(company_id or "") if char.isdigit())
    return digits.zfill(6) if digits else ""


def _resolve_manifest(path: str | Path | None) -> tuple[Path, dict[str, Any]]:
    manifest_path = Path(path).expanduser().resolve() if path else DEFAULT_KIND_MANIFEST_PATH
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest_path, payload


def _resolve_shard_path(manifest_path: Path, shard: dict[str, Any]) -> Path:
    relative_path = str(shard.get("relative_path") or "")
    if relative_path:
        return (manifest_path.parent / relative_path).resolve()
    raw_path = str(shard.get("path") or "")
    return Path(raw_path).expanduser().resolve() if raw_path else (manifest_path.parent / f"{shard.get('year')}.sqlite").resolve()


def _load_disclosures_for_triple_barrier(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    company_id: str,
    market: str,
    disclosure_ids: list[str],
) -> list[TripleBarrierDisclosure]:
    table_name = str(manifest.get("table_name") or "disclosures")
    kind_company_id = _kind_company_id(company_id)
    selected_ids = {str(value) for value in disclosure_ids if str(value).strip()}
    rows: list[TripleBarrierDisclosure] = []
    for shard in list(manifest.get("shards") or []):
        shard_path = _resolve_shard_path(manifest_path, shard)
        if not shard_path.exists():
            continue
        clauses = ["company_id = ?"]
        params: list[Any] = [kind_company_id]
        if market and market != "전체":
            clauses.append("market = ?")
            params.append(market)
        if selected_ids:
            placeholders = ", ".join("?" for _ in selected_ids)
            clauses.append(f"acpt_no IN ({placeholders})")
            params.extend(sorted(selected_ids))
        with sqlite3.connect(shard_path) as connection:
            connection.row_factory = sqlite3.Row
            fetched = connection.execute(
                f"""
                SELECT company_name, disclosed_at, disclosed_date, acpt_no
                FROM {table_name}
                WHERE {" AND ".join(clauses)}
                ORDER BY disclosed_at ASC, acpt_no ASC
                """,
                params,
            ).fetchall()
        for row in fetched:
            rows.append(
                TripleBarrierDisclosure(
                    disclosure_id=str(row["acpt_no"] or ""),
                    ticker=_display_stock_code(company_id),
                    company_name=str(row["company_name"] or ""),
                    event_datetime=str(row["disclosed_at"] or row["disclosed_date"] or ""),
                    disclosed_date=str(row["disclosed_date"] or str(row["disclosed_at"] or "")[:10]),
                )
            )
    return rows


def _find_item_file(quanti_dir: Path, item: str) -> Path | None:
    candidates = {
        "open": ("adjOpen", "open"),
        "high": ("adjHigh", "high"),
        "low": ("adjLow", "low"),
        "close": ("adjClose", "close"),
        "volume": ("adjVolume", "volume"),
    }[item]
    for prefix in candidates:
        matches = sorted(quanti_dir.glob(f"{prefix}_*.parquet"))
        if matches:
            return matches[0]
    return None


def _load_prices_for_triple_barrier(quanti_dir: str | Path | None, company_id: str) -> list[TripleBarrierPrice]:
    resolved_quanti = Path(quanti_dir).expanduser().resolve() if quanti_dir else DEFAULT_QUANTIWISE_PARQUET_DIR
    stock_code = _display_stock_code(company_id)
    series_map: dict[str, pd.Series] = {}
    for item in ["open", "high", "low", "close", "volume"]:
        path = _find_item_file(resolved_quanti, item)
        if path is None:
            return []
        parquet_file = pq.ParquetFile(path)
        if stock_code not in parquet_file.schema_arrow.names:
            return []
        frame = parquet_file.read(columns=["date", stock_code]).to_pandas()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        series_map[item] = pd.to_numeric(frame.set_index("date")[stock_code], errors="coerce")
    combined = pd.DataFrame(series_map).dropna(subset=["open", "high", "low", "close"]).sort_index()
    return [
        TripleBarrierPrice(
            date=timestamp.strftime("%Y-%m-%d"),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume") or 0),
        )
        for timestamp, row in combined.iterrows()
    ]


def run_triple_barrier_analysis(
    *,
    manifest_path: str | Path | None = None,
    quanti_dir: str | Path | None = None,
    company_id: str,
    market: str = "전체",
    disclosure_group: str = "전체",
    disclosure_ids: list[str] | None = None,
    event_time_basis: str = "disclosed_date",
    price_basis: str = "intraday",
    upper_pct: float = 5,
    lower_pct: float = 3,
    vertical_days: int = 20,
) -> dict[str, Any]:
    resolved_manifest, manifest = _resolve_manifest(manifest_path)
    params = TripleBarrierParams(
        event_time_basis=event_time_basis,
        price_basis=price_basis,
        upper_pct=float(upper_pct),
        lower_pct=float(lower_pct),
        vertical_days=int(vertical_days),
        price_source="quantiwise",
    )
    disclosures = _load_disclosures_for_triple_barrier(
        manifest_path=resolved_manifest,
        manifest=manifest,
        company_id=company_id,
        market=market,
        disclosure_ids=disclosure_ids or [],
    )
    prices = _load_prices_for_triple_barrier(quanti_dir, company_id)
    rows = calculate_triple_barrier_rows(disclosures, prices, params, source_manifest_path=str(resolved_manifest))
    db_path = default_result_db_path(resolved_manifest)
    storage_counts = save_triple_barrier_results(db_path, rows)
    parameter_hash, _ = build_parameter_hash(params)
    stored_rows = load_triple_barrier_results(db_path, ticker=_display_stock_code(company_id), parameter_hash=parameter_hash)
    selected_ids = {str(value) for value in (disclosure_ids or []) if str(value).strip()}
    if selected_ids:
        stored_rows = [row for row in stored_rows if row.disclosure_id in selected_ids]
    return {
        "summary": _summary(rows, storage_counts),
        "result_db_path": str(db_path),
        "parameter_hash": parameter_hash,
        "rows": [result_to_dict(row) for row in stored_rows],
    }


def get_triple_barrier_results_payload(
    *,
    manifest_path: str | Path | None = None,
    company_id: str,
    parameter_hash: str = "",
) -> dict[str, Any]:
    resolved_manifest, _ = _resolve_manifest(manifest_path)
    db_path = default_result_db_path(resolved_manifest)
    rows = load_triple_barrier_results(db_path, ticker=_display_stock_code(company_id), parameter_hash=parameter_hash)
    summary = _summary(rows)
    summary.pop("created", None)
    summary.pop("reused", None)
    return {
        "summary": summary,
        "result_db_path": str(db_path),
        "rows": [result_to_dict(row) for row in rows],
    }
```

- [ ] **Step 4: Add FastAPI request model and routes**

Modify imports in `src/finiq/market_desk/web/routers/market_data.py`:

```python
from pydantic import BaseModel, Field
from finiq.market_desk.analytics.triple_barrier import (
    get_triple_barrier_results_payload,
    run_triple_barrier_analysis,
)
```

Add this model above `create_market_data_router`:

```python
class TripleBarrierRunRequest(BaseModel):
    manifest_path: str | None = None
    quanti_dir: str | None = None
    company_id: str
    market: str = "전체"
    disclosure_group: str = "전체"
    disclosure_ids: list[str] = Field(default_factory=list)
    event_time_basis: str = "disclosed_date"
    price_basis: str = "intraday"
    upper_pct: float = 5
    lower_pct: float = 3
    vertical_days: int = 20
```

Add these routes inside `create_market_data_router` after `get_ontology_company_panel`:

```python
    @router.post("/api/ontology/triple-barrier/run")
    async def post_triple_barrier_run(payload: TripleBarrierRunRequest):
        try:
            return await run_in_threadpool(
                run_triple_barrier_analysis,
                manifest_path=payload.manifest_path,
                quanti_dir=payload.quanti_dir or config.quanti_dir,
                company_id=payload.company_id,
                market=payload.market,
                disclosure_group=payload.disclosure_group,
                disclosure_ids=payload.disclosure_ids,
                event_time_basis=payload.event_time_basis,
                price_basis=payload.price_basis,
                upper_pct=payload.upper_pct,
                lower_pct=payload.lower_pct,
                vertical_days=payload.vertical_days,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get("/api/ontology/triple-barrier/results")
    async def get_triple_barrier_results(
        manifest_path: Optional[str] = None,
        company_id: str = "",
        parameter_hash: str = "",
    ):
        try:
            return await run_in_threadpool(
                get_triple_barrier_results_payload,
                manifest_path=manifest_path,
                company_id=company_id,
                parameter_hash=parameter_hash,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
```

- [ ] **Step 5: Run API tests to verify GREEN**

Run:

```bash
pytest tests/market_desk/test_ontology_graph.py::test_triple_barrier_api_runs_stores_and_reuses_results -v
pytest tests/market_desk/test_triple_barrier.py -v
```

Expected: both commands PASS.

- [ ] **Step 6: Commit**

```bash
git add src/finiq/market_desk/analytics/triple_barrier.py src/finiq/market_desk/web/routers/market_data.py tests/market_desk/test_ontology_graph.py tests/market_desk/test_triple_barrier.py
git commit -m "feat: expose triple barrier API"
```

---

### Task 4: API-Backed Disclosure Analysis UI

**Files:**
- Modify: `docs/ui-terminology.md`
- Modify: `frontend/finiq_GUI/apps/market-desk/src/app/graph/analysis/DisclosureAnalysisWorkspace.tsx`
- Modify: `tests/frontend/ontologyGraphWorkspace.test.mjs`

**Interfaces:**
- Consumes:
  - `POST /api/ontology/triple-barrier/run`
  - `GET /api/ontology/triple-barrier/results`
- Produces:
  - UI controls for event basis, price basis, upper/lower/vertical parameters, disclosure row selection, run status, and stored result table.

- [ ] **Step 1: Write failing frontend source test**

Append this test to `tests/frontend/ontologyGraphWorkspace.test.mjs`:

```javascript
test("disclosure analysis page runs and displays persisted triple barrier results", async () => {
  const [analysisSource, terminologySource] = await Promise.all([
    readFile(analysisWorkspacePath, "utf8"),
    readFile(terminologyPath, "utf8"),
  ]);

  assert.match(terminologySource, /Triple Barrier 실행/);
  assert.match(analysisSource, /apiPost/);
  assert.match(analysisSource, /\/api\/ontology\/triple-barrier\/run/);
  assert.match(analysisSource, /\/api\/ontology\/triple-barrier\/results/);
  assert.match(analysisSource, /event_time_basis/);
  assert.match(analysisSource, /price_basis/);
  assert.match(analysisSource, /upper_pct/);
  assert.match(analysisSource, /lower_pct/);
  assert.match(analysisSource, /vertical_days/);
  assert.match(analysisSource, /disclosure_ids/);
  for (const label of [
    "공시 ID",
    "종목코드",
    "종목명",
    "공시일",
    "이벤트 가격",
    "upper barrier 가격",
    "lower barrier 가격",
    "vertical barrier 날짜",
    "최초 도달 barrier",
    "최초 도달 날짜",
    "최초 도달 가격",
    "수익률",
    "label",
    "계산 상태",
    "에러 메시지",
  ]) {
    assert.match(analysisSource, new RegExp(label));
  }
  assert.doesNotMatch(analysisSource, /runDisclosureBacktest/);
});
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
node --test tests/frontend/ontologyGraphWorkspace.test.mjs
```

Expected: FAIL because `Triple Barrier 실행` and the new API calls are missing.

- [ ] **Step 3: Add UI terminology**

Add these rows under `## Ontology Workflow` in `docs/ui-terminology.md`:

```markdown
| Ontology triple barrier execution action | Triple Barrier 실행 | Button/action on `공시 분석` that calculates and stores Triple Barrier labels. |
| Ontology triple barrier event basis | 이벤트 기준일 | Selector for using disclosure date or disclosure timestamp as event time. |
| Ontology triple barrier price basis | 가격 기준 | Selector for close-based or intraday high/low-based barrier checks. |
| Ontology triple barrier result table | 결과 테이블 | Stored Triple Barrier label result table on `공시 분석`. |
```

- [ ] **Step 4: Replace frontend-only analysis with API-backed workspace**

In `frontend/finiq_GUI/apps/market-desk/src/app/graph/analysis/DisclosureAnalysisWorkspace.tsx`, change the imports:

```tsx
import { useCallback, useEffect, useMemo, useState } from "react";
import { FileText, Loader2, Search } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label } from "@finiq/ui";
import { apiGet, apiPost } from "@/api/client";
import { PageLoadingSpinner } from "@/components/ui/PageLoadingSpinner";
import { formatInteger } from "@/lib/format";
```

Remove:

```tsx
import { BACKTEST_METHODS, runDisclosureBacktest, type BacktestCandle, type BacktestMarker } from "@/lib/disclosureBacktests";
```

Add these types near the existing payload types:

```tsx
type AnalysisMarker = {
  time: string;
  group?: string;
  title?: string;
  disclosed_at?: string;
  acpt_no?: string;
};

type AnalysisCandle = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

type TripleBarrierRow = {
  id?: number | null;
  disclosure_id: string;
  ticker: string;
  company_name: string;
  event_datetime: string;
  event_price: number | null;
  upper_pct: number;
  lower_pct: number;
  vertical_days: number;
  upper_price: number | null;
  lower_price: number | null;
  vertical_datetime: string;
  touched_barrier: string;
  touched_datetime: string;
  touched_price: number | null;
  return_pct: number | null;
  label: number | null;
  status: string;
  error_message: string;
  parameter_hash: string;
};

type TripleBarrierPayload = {
  summary: {
    total: number;
    completed: number;
    failed: number;
    created?: number;
    reused?: number;
  };
  result_db_path: string;
  parameter_hash?: string;
  rows: TripleBarrierRow[];
};
```

Change `OntologyPanel.chart` to:

```tsx
  chart: {
    candles: AnalysisCandle[];
    markers: AnalysisMarker[];
  };
```

Add state inside `DisclosureAnalysisWorkspace`:

```tsx
  const [eventTimeBasis, setEventTimeBasis] = useState("disclosed_date");
  const [priceBasis, setPriceBasis] = useState("intraday");
  const [upperPct, setUpperPct] = useState("5");
  const [lowerPct, setLowerPct] = useState("3");
  const [verticalDays, setVerticalDays] = useState("20");
  const [selectedDisclosureIds, setSelectedDisclosureIds] = useState<string[]>([]);
  const [runningTripleBarrier, setRunningTripleBarrier] = useState(false);
  const [tripleBarrierResult, setTripleBarrierResult] = useState<TripleBarrierPayload | null>(null);
```

Remove `methodId`, `selectedMethod`, and `result` state/memo usage.

Add helpers inside the component:

```tsx
  const loadTripleBarrierResults = useCallback(async () => {
    if (!selectedCompany) {
      setTripleBarrierResult(null);
      return;
    }
    const query = new URLSearchParams({
      company_id: selectedCompany.stock_code,
    });
    const data = await apiGet<TripleBarrierPayload>(`/api/ontology/triple-barrier/results?${query.toString()}`);
    setTripleBarrierResult(data);
  }, [selectedCompany]);

  const runTripleBarrier = useCallback(async () => {
    if (!selectedCompany) return;
    setRunningTripleBarrier(true);
    setError("");
    try {
      const data = await apiPost<TripleBarrierPayload>("/api/ontology/triple-barrier/run", {
        company_id: selectedCompany.stock_code,
        market: "전체",
        disclosure_group: "전체",
        disclosure_ids: selectedDisclosureIds,
        event_time_basis: eventTimeBasis,
        price_basis: priceBasis,
        upper_pct: Number(upperPct),
        lower_pct: Number(lowerPct),
        vertical_days: Number(verticalDays),
      });
      setTripleBarrierResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Triple Barrier 실행에 실패했습니다.");
    } finally {
      setRunningTripleBarrier(false);
    }
  }, [eventTimeBasis, lowerPct, priceBasis, selectedCompany, selectedDisclosureIds, upperPct, verticalDays]);

  const toggleDisclosure = useCallback((disclosureId: string) => {
    setSelectedDisclosureIds((current) => (
      current.includes(disclosureId)
        ? current.filter((value) => value !== disclosureId)
        : [...current, disclosureId]
    ));
  }, []);
```

Add this effect:

```tsx
  useEffect(() => {
    setSelectedDisclosureIds([]);
    loadTripleBarrierResults().catch((err) => {
      setError(err instanceof Error ? err.message : "Triple Barrier 결과를 불러오지 못했습니다.");
    });
  }, [loadTripleBarrierResults]);
```

Replace the second section card content with controls and table that include the required labels. Use this structure:

```tsx
      <section>
        <Card className="rounded-lg dark:border-[#30363d] dark:bg-[#161b22]">
          <CardHeader>
            <CardTitle className="text-lg dark:text-white">Triple Barrier 실행</CardTitle>
            <CardDescription className="dark:text-slate-400">
              {selectedCompanyLabel} · 공시 이벤트 기준 라벨을 계산해 저장합니다.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {loadingPanel ? (
              <PageLoadingSpinner message="공시 목록을 준비하는 중입니다..." />
            ) : (
              <>
                <div className="grid gap-3 md:grid-cols-6">
                  <label className="space-y-1.5 text-sm">
                    <span className="font-medium text-slate-700 dark:text-slate-300">이벤트 기준일</span>
                    <select value={eventTimeBasis} onChange={(event) => setEventTimeBasis(event.target.value)} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-100">
                      <option value="disclosed_date">공시일</option>
                      <option value="disclosed_at">공시시각</option>
                    </select>
                  </label>
                  <label className="space-y-1.5 text-sm">
                    <span className="font-medium text-slate-700 dark:text-slate-300">가격 기준</span>
                    <select value={priceBasis} onChange={(event) => setPriceBasis(event.target.value)} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-100">
                      <option value="close">종가 기준</option>
                      <option value="intraday">장중 고가/저가 기준</option>
                    </select>
                  </label>
                  <label className="space-y-1.5 text-sm">
                    <span className="font-medium text-slate-700 dark:text-slate-300">Upper barrier</span>
                    <Input value={upperPct} onChange={(event) => setUpperPct(event.target.value)} type="number" step="0.1" className="h-9" />
                  </label>
                  <label className="space-y-1.5 text-sm">
                    <span className="font-medium text-slate-700 dark:text-slate-300">Lower barrier</span>
                    <Input value={lowerPct} onChange={(event) => setLowerPct(event.target.value)} type="number" step="0.1" className="h-9" />
                  </label>
                  <label className="space-y-1.5 text-sm">
                    <span className="font-medium text-slate-700 dark:text-slate-300">Vertical barrier</span>
                    <select value={verticalDays} onChange={(event) => setVerticalDays(event.target.value)} className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm dark:border-[#30363d] dark:bg-[#0d1117] dark:text-slate-100">
                      <option value="5">5거래일</option>
                      <option value="10">10거래일</option>
                      <option value="20">20거래일</option>
                    </select>
                  </label>
                  <div className="flex items-end">
                    <Button className="h-9 w-full" onClick={runTripleBarrier} disabled={!selectedCompany || runningTripleBarrier}>
                      {runningTripleBarrier ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                      Triple Barrier 실행
                    </Button>
                  </div>
                </div>

                <div className="rounded-lg border border-slate-200 dark:border-[#30363d]">
                  <div className="border-b border-slate-200 px-3 py-2 text-sm font-semibold dark:border-[#30363d] dark:text-slate-100">공시 목록 선택</div>
                  <div className="max-h-44 overflow-y-auto divide-y divide-slate-100 dark:divide-[#30363d]">
                    {(panel?.chart.markers ?? []).length ? panel?.chart.markers.map((marker) => {
                      const disclosureId = marker.acpt_no || `${marker.time}-${marker.title}`;
                      return (
                        <label key={disclosureId} className="flex items-center gap-2 px-3 py-2 text-sm dark:text-slate-200">
                          <input type="checkbox" checked={selectedDisclosureIds.includes(disclosureId)} onChange={() => toggleDisclosure(disclosureId)} />
                          <span className="min-w-[9rem] font-mono text-xs">{disclosureId}</span>
                          <span className="truncate">{marker.disclosed_at || marker.time} · {marker.title || "-"}</span>
                        </label>
                      );
                    }) : (
                      <p className="px-3 py-3 text-sm text-slate-500 dark:text-slate-400">분석할 공시 이벤트가 없습니다.</p>
                    )}
                  </div>
                </div>

                <div className="grid gap-2 sm:grid-cols-5">
                  {[
                    ["전체", tripleBarrierResult?.summary.total ?? 0],
                    ["완료", tripleBarrierResult?.summary.completed ?? 0],
                    ["실패", tripleBarrierResult?.summary.failed ?? 0],
                    ["신규 저장", tripleBarrierResult?.summary.created ?? 0],
                    ["중복 제외", tripleBarrierResult?.summary.reused ?? 0],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-lg border border-slate-200 px-3 py-2 dark:border-[#30363d]">
                      <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
                      <p className="mt-1 font-semibold tabular-nums text-slate-950 dark:text-slate-100">{formatInteger(Number(value))}</p>
                    </div>
                  ))}
                </div>

                <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-[#30363d]">
                  <table className="min-w-[1280px] text-left text-xs">
                    <thead className="bg-slate-50 text-slate-500 dark:bg-[#0d1117] dark:text-slate-400">
                      <tr>
                        {["공시 ID", "종목코드", "종목명", "공시일", "이벤트 가격", "upper barrier 가격", "lower barrier 가격", "vertical barrier 날짜", "최초 도달 barrier", "최초 도달 날짜", "최초 도달 가격", "수익률", "label", "계산 상태", "에러 메시지"].map((header) => (
                          <th key={header} className="border-b border-slate-200 px-3 py-2 dark:border-[#30363d]">{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-[#30363d]">
                      {(tripleBarrierResult?.rows ?? []).map((row) => (
                        <tr key={`${row.disclosure_id}-${row.parameter_hash}`} className="dark:text-slate-200">
                          <td className="px-3 py-2 font-mono">{row.disclosure_id}</td>
                          <td className="px-3 py-2">{row.ticker}</td>
                          <td className="px-3 py-2">{row.company_name}</td>
                          <td className="px-3 py-2">{row.event_datetime}</td>
                          <td className="px-3 py-2 tabular-nums">{row.event_price ?? "-"}</td>
                          <td className="px-3 py-2 tabular-nums">{row.upper_price ?? "-"}</td>
                          <td className="px-3 py-2 tabular-nums">{row.lower_price ?? "-"}</td>
                          <td className="px-3 py-2">{row.vertical_datetime || "-"}</td>
                          <td className="px-3 py-2">{row.touched_barrier}</td>
                          <td className="px-3 py-2">{row.touched_datetime || "-"}</td>
                          <td className="px-3 py-2 tabular-nums">{row.touched_price ?? "-"}</td>
                          <td className="px-3 py-2 tabular-nums">{row.return_pct ?? "-"}</td>
                          <td className="px-3 py-2 tabular-nums">{row.label ?? "-"}</td>
                          <td className="px-3 py-2">{row.status}</td>
                          <td className="px-3 py-2">{row.error_message || "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {tripleBarrierResult && !tripleBarrierResult.rows.length ? (
                    <p className="p-4 text-sm text-slate-500 dark:text-slate-400">저장된 결과가 없습니다.</p>
                  ) : null}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </section>
```

- [ ] **Step 5: Run frontend source test to verify GREEN**

Run:

```bash
node --test tests/frontend/ontologyGraphWorkspace.test.mjs
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/ui-terminology.md frontend/finiq_GUI/apps/market-desk/src/app/graph/analysis/DisclosureAnalysisWorkspace.tsx tests/frontend/ontologyGraphWorkspace.test.mjs
git commit -m "feat: connect triple barrier analysis UI"
```

---

### Task 5: Final Documentation and Verification

**Files:**
- Modify: `PLANS.md`

**Interfaces:**
- Consumes: completed backend and frontend work.
- Produces: project-required completion record.

- [ ] **Step 1: Update `PLANS.md`**

Append this entry to `PLANS.md`, adjusting only the verification command results to match the actual run output:

```markdown
## Triple Barrier Disclosure Analysis

- Purpose: Add real Triple Barrier Method execution to `공시 분석` so users can calculate, store, deduplicate, and reload disclosure-event labels by stock.
- Implementation summary: Added backend Triple Barrier calculation/storage/API support, connected the analysis page to the API, added disclosure selection and configurable barrier controls, and rendered stored result rows in the required table shape.
- Verification: `pytest tests/market_desk/test_triple_barrier.py -v`, `pytest tests/market_desk/test_ontology_graph.py::test_triple_barrier_api_runs_stores_and_reuses_results -v`, and `node --test tests/frontend/ontologyGraphWorkspace.test.mjs` passed.
```

- [ ] **Step 2: Run focused verification**

Run:

```bash
pytest tests/market_desk/test_triple_barrier.py -v
pytest tests/market_desk/test_ontology_graph.py::test_triple_barrier_api_runs_stores_and_reuses_results -v
node --test tests/frontend/ontologyGraphWorkspace.test.mjs
```

Expected: all commands PASS.

- [ ] **Step 3: Run broader impacted tests**

Run:

```bash
pytest tests/market_desk/test_ontology_graph.py -v
node --test tests/frontend/ontologyGraphWorkspace.test.mjs tests/frontend/navigation.test.mjs
```

Expected: all commands PASS.

- [ ] **Step 4: Inspect diff**

Run:

```bash
git diff --stat
git diff -- src/finiq/market_desk/analytics/triple_barrier.py src/finiq/market_desk/web/routers/market_data.py frontend/finiq_GUI/apps/market-desk/src/app/graph/analysis/DisclosureAnalysisWorkspace.tsx tests/market_desk/test_triple_barrier.py tests/market_desk/test_ontology_graph.py tests/frontend/ontologyGraphWorkspace.test.mjs docs/ui-terminology.md PLANS.md
```

Expected: diff only covers Triple Barrier implementation, tests, and required documentation.

- [ ] **Step 5: Commit**

```bash
git add PLANS.md
git commit -m "docs: record triple barrier verification"
```

---

## Self-Review Checklist

- Spec coverage: Tasks cover backend calculation, event time basis, price basis, barrier parameters, labels, SQLite persistence, duplicate prevention, API run/results, UI controls, result table columns, terminology, and `PLANS.md`.
- Type consistency: `TripleBarrierParams`, `TripleBarrierResult`, `run_triple_barrier_analysis`, and API payload names match across tasks.
- Verification coverage: focused Python tests cover calculation and storage, API tests cover execution and duplicate prevention, frontend source tests cover API wiring and table labels.
