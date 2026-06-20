"""Triple-barrier labeling helpers for market desk analytics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any


RESULT_TABLE = "triple_barrier_results"


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


def build_parameter_hash(params: TripleBarrierParams) -> tuple[str, str]:
    params_json = json.dumps(
        {
            "event_time_basis": params.event_time_basis,
            "lower_pct": _stable_number(params.lower_pct),
            "price_basis": params.price_basis,
            "price_source": params.price_source,
            "upper_pct": _stable_number(params.upper_pct),
            "vertical_days": int(params.vertical_days),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(params_json.encode("utf-8")).hexdigest(), params_json


def calculate_triple_barrier_rows(
    disclosures: list[TripleBarrierDisclosure],
    prices: list[TripleBarrierPrice],
    params: TripleBarrierParams,
    *,
    source_manifest_path: str,
) -> list[TripleBarrierResult]:
    sorted_prices = sorted(prices, key=lambda price: price.date)
    parameter_hash, params_json = build_parameter_hash(params)
    return [
        _calculate_disclosure_row(
            disclosure,
            sorted_prices,
            params,
            source_manifest_path=source_manifest_path,
            params_json=params_json,
            parameter_hash=parameter_hash,
        )
        for disclosure in disclosures
    ]


def _calculate_disclosure_row(
    disclosure: TripleBarrierDisclosure,
    prices: list[TripleBarrierPrice],
    params: TripleBarrierParams,
    *,
    source_manifest_path: str,
    params_json: str,
    parameter_hash: str,
) -> TripleBarrierResult:
    event_date = disclosure.event_datetime[:10] if params.event_time_basis == "disclosed_at" else disclosure.disclosed_date
    event_index = next((index for index, price in enumerate(prices) if price.date >= event_date), None)
    calculation_params_json = params_json

    if event_index is None:
        return _failed_row(
            disclosure,
            params,
            source_manifest_path=source_manifest_path,
            calculation_params_json=calculation_params_json,
            parameter_hash=parameter_hash,
            error_message=f"No price row found on or after event date {event_date}",
        )

    vertical_index = event_index + params.vertical_days
    if vertical_index >= len(prices):
        return _failed_row(
            disclosure,
            params,
            source_manifest_path=source_manifest_path,
            calculation_params_json=calculation_params_json,
            parameter_hash=parameter_hash,
            error_message=f"No price row found for vertical date {params.vertical_days} trading days after event",
        )

    event_price = prices[event_index].close
    upper_price = event_price * (1 + params.upper_pct / 100)
    lower_price = event_price * (1 - params.lower_pct / 100)

    for price in prices[event_index + 1 : vertical_index + 1]:
        if params.price_basis == "close":
            if price.close >= upper_price:
                return _success_row(
                    disclosure,
                    params,
                    source_manifest_path=source_manifest_path,
                    calculation_params_json=calculation_params_json,
                    parameter_hash=parameter_hash,
                    event_price=event_price,
                    upper_price=upper_price,
                    lower_price=lower_price,
                    vertical_datetime=prices[vertical_index].date,
                    touched_barrier="upper",
                    touched_datetime=price.date,
                    touched_price=price.close,
                    label=1,
                )
            if price.close <= lower_price:
                return _success_row(
                    disclosure,
                    params,
                    source_manifest_path=source_manifest_path,
                    calculation_params_json=calculation_params_json,
                    parameter_hash=parameter_hash,
                    event_price=event_price,
                    upper_price=upper_price,
                    lower_price=lower_price,
                    vertical_datetime=prices[vertical_index].date,
                    touched_barrier="lower",
                    touched_datetime=price.date,
                    touched_price=price.close,
                    label=-1,
                )
        else:
            if price.high >= upper_price:
                return _success_row(
                    disclosure,
                    params,
                    source_manifest_path=source_manifest_path,
                    calculation_params_json=calculation_params_json,
                    parameter_hash=parameter_hash,
                    event_price=event_price,
                    upper_price=upper_price,
                    lower_price=lower_price,
                    vertical_datetime=prices[vertical_index].date,
                    touched_barrier="upper",
                    touched_datetime=price.date,
                    touched_price=upper_price,
                    label=1,
                )
            if price.low <= lower_price:
                return _success_row(
                    disclosure,
                    params,
                    source_manifest_path=source_manifest_path,
                    calculation_params_json=calculation_params_json,
                    parameter_hash=parameter_hash,
                    event_price=event_price,
                    upper_price=upper_price,
                    lower_price=lower_price,
                    vertical_datetime=prices[vertical_index].date,
                    touched_barrier="lower",
                    touched_datetime=price.date,
                    touched_price=lower_price,
                    label=-1,
                )

    vertical_price = prices[vertical_index]
    return _success_row(
        disclosure,
        params,
        source_manifest_path=source_manifest_path,
        calculation_params_json=calculation_params_json,
        parameter_hash=parameter_hash,
        event_price=event_price,
        upper_price=upper_price,
        lower_price=lower_price,
        vertical_datetime=vertical_price.date,
        touched_barrier="vertical",
        touched_datetime=vertical_price.date,
        touched_price=vertical_price.close,
        label=0,
    )


def _stable_number(value: float) -> float | int:
    number = float(value)
    return int(number) if number.is_integer() else number


def _failed_row(
    disclosure: TripleBarrierDisclosure,
    params: TripleBarrierParams,
    *,
    source_manifest_path: str,
    calculation_params_json: str,
    parameter_hash: str,
    error_message: str,
) -> TripleBarrierResult:
    return TripleBarrierResult(
        source_manifest_path=source_manifest_path,
        disclosure_id=disclosure.disclosure_id,
        ticker=disclosure.ticker,
        company_name=disclosure.company_name,
        event_datetime=disclosure.event_datetime,
        event_price=None,
        upper_pct=params.upper_pct,
        lower_pct=params.lower_pct,
        vertical_days=params.vertical_days,
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
        calculation_params_json=calculation_params_json,
        parameter_hash=parameter_hash,
        status="failed",
        error_message=error_message,
    )


def _success_row(
    disclosure: TripleBarrierDisclosure,
    params: TripleBarrierParams,
    *,
    source_manifest_path: str,
    calculation_params_json: str,
    parameter_hash: str,
    event_price: float,
    upper_price: float,
    lower_price: float,
    vertical_datetime: str,
    touched_barrier: str,
    touched_datetime: str,
    touched_price: float,
    label: int,
) -> TripleBarrierResult:
    return TripleBarrierResult(
        source_manifest_path=source_manifest_path,
        disclosure_id=disclosure.disclosure_id,
        ticker=disclosure.ticker,
        company_name=disclosure.company_name,
        event_datetime=disclosure.event_datetime,
        event_price=event_price,
        upper_pct=params.upper_pct,
        lower_pct=params.lower_pct,
        vertical_days=params.vertical_days,
        upper_price=upper_price,
        lower_price=lower_price,
        vertical_datetime=vertical_datetime,
        touched_barrier=touched_barrier,
        touched_datetime=touched_datetime,
        touched_price=touched_price,
        return_pct=((touched_price - event_price) / event_price) * 100,
        label=label,
        price_source=params.price_source,
        event_time_basis=params.event_time_basis,
        price_basis=params.price_basis,
        calculation_params_json=calculation_params_json,
        parameter_hash=parameter_hash,
        status="completed",
    )


def default_result_db_path(manifest_path: str | Path) -> Path:
    return Path(manifest_path).expanduser().resolve().parent / "triple_barrier_results.sqlite"


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
                _sqlite_values(row, now_text),
            )
            if cursor.rowcount:
                created += 1
            else:
                reused += 1
    return {"created": created, "reused": reused}


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
            FROM {RESULT_TABLE}
            {where_sql}
            ORDER BY event_datetime ASC, disclosure_id ASC
            """,
            params,
        ).fetchall()
    return [_result_from_sqlite(row) for row in rows]


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sqlite_values(row: TripleBarrierResult, now_text: str) -> tuple[Any, ...]:
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
