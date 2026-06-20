from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from finiq.market_desk.analytics.triple_barrier import (
    TripleBarrierDisclosure,
    TripleBarrierParams,
    TripleBarrierPrice,
    build_parameter_hash,
    calculate_triple_barrier_rows,
    load_triple_barrier_results,
    save_triple_barrier_results,
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


def test_intraday_mode_fails_when_same_bar_touches_both_barriers() -> None:
    params = TripleBarrierParams(
        event_time_basis="disclosed_date",
        price_basis="intraday",
        upper_pct=5,
        lower_pct=3,
        vertical_days=2,
        price_source="quantiwise",
    )
    prices = [
        TripleBarrierPrice(date="2025-01-02", open=100, high=101, low=99, close=100, volume=1000),
        TripleBarrierPrice(date="2025-01-03", open=100, high=106, low=96, close=101, volume=1100),
        TripleBarrierPrice(date="2025-01-06", open=101, high=102, low=100, close=101, volume=1200),
    ]

    rows = calculate_triple_barrier_rows([_disclosure()], prices, params, source_manifest_path="/kind/manifest.json")

    row = rows[0]
    assert row.status == "failed"
    assert row.touched_barrier == "error"
    assert row.label is None
    assert "same price row" in row.error_message


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


def test_invalid_params_raise_value_error() -> None:
    params = TripleBarrierParams(
        event_time_basis="disclosed_date",
        price_basis="intraday",
        upper_pct=0,
        lower_pct=3,
        vertical_days=3,
        price_source="quantiwise",
    )

    with pytest.raises(ValueError, match="upper_pct"):
        calculate_triple_barrier_rows([_disclosure()], _prices(), params, source_manifest_path="/kind/manifest.json")


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
