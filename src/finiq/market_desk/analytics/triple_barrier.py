"""Triple-barrier labeling helpers for market desk analytics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from finiq.market_desk.analytics.ontology_graph import (
    DEFAULT_KIND_MANIFEST_PATH,
    DEFAULT_QUANTIWISE_PARQUET_DIR,
    kind_company_id_candidates,
    load_kind_category_disclosures,
    selected_disclosure_groups,
)
from finiq.market_desk.analytics.disclosure_groups import (
    DEFAULT_DISCLOSURE_GROUP_RULES,
    classify_disclosure_group,
)


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


def _validate_params(params: TripleBarrierParams) -> None:
    if params.event_time_basis not in {"disclosed_date", "disclosed_at"}:
        raise ValueError("event_time_basis must be disclosed_date or disclosed_at")
    if params.price_basis not in {"close", "intraday"}:
        raise ValueError("price_basis must be close or intraday")
    if params.upper_pct <= 0:
        raise ValueError("upper_pct must be greater than 0")
    if params.lower_pct <= 0:
        raise ValueError("lower_pct must be greater than 0")
    if params.vertical_days <= 0:
        raise ValueError("vertical_days must be greater than 0")


def calculate_triple_barrier_rows(
    disclosures: list[TripleBarrierDisclosure],
    prices: list[TripleBarrierPrice],
    params: TripleBarrierParams,
    *,
    source_manifest_path: str,
) -> list[TripleBarrierResult]:
    _validate_params(params)
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
            touches_upper = price.high >= upper_price
            touches_lower = price.low <= lower_price
            if touches_upper and touches_lower:
                return _failed_row(
                    disclosure,
                    params,
                    source_manifest_path=source_manifest_path,
                    calculation_params_json=calculation_params_json,
                    parameter_hash=parameter_hash,
                    error_message=(
                        f"Upper and lower barriers touched in the same price row {price.date}; "
                        "intraday sequence is unavailable"
                    ),
                )
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
        disclosure_group=disclosure_group,
        disclosure_ids=disclosure_ids or [],
    )
    prices = _load_prices_for_triple_barrier(quanti_dir, company_id)
    rows = calculate_triple_barrier_rows(disclosures, prices, params, source_manifest_path=str(resolved_manifest))
    db_path = default_result_db_path(resolved_manifest)
    storage_counts = save_triple_barrier_results(db_path, rows)
    parameter_hash, _ = build_parameter_hash(params)
    stored_rows = load_triple_barrier_results(db_path, ticker=_display_stock_code(company_id), parameter_hash=parameter_hash)
    run_disclosure_ids = {row.disclosure_id for row in rows}
    stored_rows = [row for row in stored_rows if row.disclosure_id in run_disclosure_ids]
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
    return {
        "summary": {
            "total": len(rows),
            "completed": sum(1 for row in rows if row.status == "completed"),
            "failed": sum(1 for row in rows if row.status == "failed"),
        },
        "result_db_path": str(db_path),
        "rows": [result_to_dict(row) for row in rows],
    }


def _summary(rows: list[TripleBarrierResult], storage_counts: dict[str, int]) -> dict[str, int]:
    return {
        "total": len(rows),
        "completed": sum(1 for row in rows if row.status == "completed"),
        "failed": sum(1 for row in rows if row.status == "failed"),
        "created": int(storage_counts.get("created", 0)),
        "reused": int(storage_counts.get("reused", 0)),
    }


def _resolve_manifest(path: str | Path | None) -> tuple[Path, dict[str, Any]]:
    manifest_path = Path(path).expanduser().resolve() if path else DEFAULT_KIND_MANIFEST_PATH
    return manifest_path, json.loads(manifest_path.read_text(encoding="utf-8"))


def _resolve_shard_path(manifest_path: Path, shard: dict[str, Any]) -> Path:
    raw_path = str(shard.get("path") or "").strip()
    if raw_path:
        path = Path(raw_path)
        if path.is_absolute() and path.exists():
            return path
    relative_path = str(shard.get("relative_path") or "").strip()
    if relative_path:
        return (manifest_path.parent / relative_path).resolve()
    return (manifest_path.parent / f"{shard.get('year')}.sqlite").resolve()


def _load_disclosures_for_triple_barrier(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    company_id: str,
    market: str,
    disclosure_group: str,
    disclosure_ids: list[str],
) -> list[TripleBarrierDisclosure]:
    table_name = str(manifest.get("table_name") or "disclosures")
    selected_ids = {str(value) for value in disclosure_ids if str(value).strip()}
    selected_group_names = selected_disclosure_groups(disclosure_group)
    rows: list[TripleBarrierDisclosure] = []
    for shard in list(manifest.get("shards") or []):
        shard_path = _resolve_shard_path(manifest_path, shard)
        if not shard_path.exists():
            raise FileNotFoundError(f"KIND SQLite shard not found: {shard_path}")
        company_id_candidates = kind_company_id_candidates(company_id)
        if not company_id_candidates:
            return rows
        placeholders = ", ".join("?" for _ in company_id_candidates)
        clauses = [f"company_id IN ({placeholders})"]
        params: list[Any] = company_id_candidates
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
                SELECT company_name, disclosed_at, disclosed_date, acpt_no, title
                FROM {table_name}
                WHERE {" AND ".join(clauses)}
                ORDER BY disclosed_at ASC, acpt_no ASC
                """,
                params,
            ).fetchall()
        for row in fetched:
            group_name = classify_disclosure_group(str(row["title"] or ""), DEFAULT_DISCLOSURE_GROUP_RULES)
            if selected_group_names is not None and group_name not in selected_group_names:
                continue
            rows.append(
                TripleBarrierDisclosure(
                    disclosure_id=str(row["acpt_no"] or ""),
                    ticker=_display_stock_code(company_id),
                    company_name=str(row["company_name"] or ""),
                    event_datetime=str(row["disclosed_at"] or row["disclosed_date"] or ""),
                    disclosed_date=str(row["disclosed_date"] or str(row["disclosed_at"] or "")[:10]),
                )
            )
    if selected_group_names is not None:
        rows.extend(
            _category_disclosures_for_triple_barrier(
                company_id=company_id,
                market=market,
                disclosure_group=disclosure_group,
                selected_ids=selected_ids,
            )
        )
    return _dedupe_disclosures(rows)


def _category_disclosures_for_triple_barrier(
    *,
    company_id: str,
    market: str,
    disclosure_group: str,
    selected_ids: set[str],
) -> list[TripleBarrierDisclosure]:
    category_rows = load_kind_category_disclosures(
        company_id=company_id,
        start_date=date(1900, 1, 1),
        end_date=date.max,
        disclosure_group=disclosure_group,
        market=market,
    )
    disclosures: list[TripleBarrierDisclosure] = []
    for row in category_rows:
        disclosure_id = str(row.get("acpt_no") or "")
        if selected_ids and disclosure_id not in selected_ids:
            continue
        disclosed_at = str(row.get("disclosed_at") or row.get("disclosed_date") or "")
        disclosed_date = str(row.get("disclosed_date") or disclosed_at[:10])
        disclosures.append(
            TripleBarrierDisclosure(
                disclosure_id=disclosure_id,
                ticker=_display_stock_code(company_id),
                company_name=str(row.get("company_name") or ""),
                event_datetime=disclosed_at,
                disclosed_date=disclosed_date,
            )
        )
    return disclosures


def _dedupe_disclosures(disclosures: list[TripleBarrierDisclosure]) -> list[TripleBarrierDisclosure]:
    by_id: dict[str, TripleBarrierDisclosure] = {}
    for disclosure in disclosures:
        by_id[disclosure.disclosure_id] = disclosure
    return sorted(by_id.values(), key=lambda disclosure: (disclosure.event_datetime, disclosure.disclosure_id))


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


def _display_stock_code(company_id: str) -> str:
    raw = str(company_id or "").strip().upper()
    if raw.startswith("A"):
        return raw
    return f"A{raw.zfill(6)}" if raw.isdigit() else raw


def _kind_company_id(company_id: str) -> str:
    raw = str(company_id or "").strip()
    return raw.zfill(6) if raw.isdigit() else raw
