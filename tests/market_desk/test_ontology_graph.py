from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sqlite3
import threading

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from finiq.config import AppConfig
from finiq.market_desk.analytics import ontology_graph
from finiq.market_desk.analytics import triple_barrier
from finiq.market_desk.analytics.ontology_graph import (
    OntologyRequestCancelled,
    build_ontology_company_panel,
    build_ontology_status,
    search_ontology_companies,
)
from finiq.market_desk.sqlite_generation import SQLITE_GENERATION_LOCK
from finiq.market_desk.web.routers import market_data as market_data_router
from finiq.market_desk.web.routers.market_data import create_market_data_router


def test_analytics_manifest_readers_wait_for_generation_publication(
    tmp_path: Path,
) -> None:
    missing_manifest = tmp_path / "missing-manifest.json"
    missing_quanti = tmp_path / "missing-quanti"
    callbacks = [
        lambda: build_ontology_status(
            manifest_path=missing_manifest,
            quanti_dir=missing_quanti,
        ),
        lambda: search_ontology_companies(
            manifest_path=missing_manifest,
            quanti_dir=missing_quanti,
        ),
        lambda: build_ontology_company_panel(
            manifest_path=missing_manifest,
            quanti_dir=missing_quanti,
            company_id="005930",
        ),
        lambda: triple_barrier.run_triple_barrier_analysis(
            manifest_path=missing_manifest,
            quanti_dir=missing_quanti,
            company_id="005930",
        ),
        lambda: triple_barrier.get_triple_barrier_results_payload(
            manifest_path=missing_manifest,
            company_id="005930",
        ),
    ]

    for callback in callbacks:
        started = threading.Event()
        finished = threading.Event()

        def read_manifest() -> None:
            started.set()
            try:
                callback()
            except (OSError, ValueError):
                pass
            finally:
                finished.set()

        with SQLITE_GENERATION_LOCK:
            reader = threading.Thread(target=read_manifest)
            reader.start()
            assert started.wait(timeout=5)
            assert not finished.wait(timeout=0.05)
        reader.join(timeout=5)
        assert not reader.is_alive()
        assert finished.is_set()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_json_number_rejects_nonfinite_values(value: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        ontology_graph._json_number(value)


def _write_disclosure_shard(root: Path) -> Path:
    shard_root = root / "KIND_DISCTABLE_FULL.sqlite_manifest_shards"
    shard_root.mkdir(parents=True)
    shard_path = shard_root / "2025.sqlite"
    connection = sqlite3.connect(shard_path)
    try:
        connection.execute(
            """
            CREATE TABLE disclosures (
                id INTEGER PRIMARY KEY,
                row_no TEXT,
                company_key TEXT,
                company_name TEXT,
                company_id TEXT,
                market TEXT,
                badges_json TEXT NOT NULL DEFAULT '[]',
                disclosed_at TEXT,
                disclosed_date TEXT,
                title TEXT,
                title_attr TEXT,
                title_base TEXT,
                title_display TEXT,
                title_flags_json TEXT NOT NULL DEFAULT '[]',
                is_correction_report INTEGER NOT NULL DEFAULT 0,
                has_later_correction INTEGER NOT NULL DEFAULT 0,
                acpt_no TEXT,
                doc_no TEXT,
                submitter TEXT,
                source_page INTEGER
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO disclosures (
                company_key, company_name, company_id, market, disclosed_at,
                disclosed_date, title, title_display, acpt_no, doc_no, submitter
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "005930",
                    "테스트전자",
                    "005930",
                    "코스피",
                    "2024-12-30 09:10",
                    "2024-12-30",
                    "사업보고서",
                    "사업보고서",
                    "20241230000001",
                    "",
                    "테스트전자",
                ),
                (
                    "005930",
                    "테스트전자",
                    "005930",
                    "코스피",
                    "2025-01-02 09:10",
                    "2025-01-02",
                    "주주총회소집결의",
                    "주주총회소집결의",
                    "20250102000001",
                    "",
                    "테스트전자",
                ),
                (
                    "005930",
                    "테스트전자",
                    "005930",
                    "코스피",
                    "2025-01-02 16:10",
                    "2025-01-02",
                    "전환사채권발행결정",
                    "전환사채권발행결정",
                    "20250102000002",
                    "",
                    "테스트전자",
                ),
                (
                    "000660",
                    "다른반도체",
                    "000660",
                    "코스피",
                    "2025-01-03 09:00",
                    "2025-01-03",
                    "단일판매ㆍ공급계약체결",
                    "단일판매ㆍ공급계약체결",
                    "20250103000001",
                    "",
                    "다른반도체",
                ),
                (
                    "06409",
                    "인크레더블버즈",
                    "06409",
                    "코스닥",
                    "2025-01-02 09:10",
                    "2025-01-02",
                    "유상증자결정",
                    "유상증자결정",
                    "20250102006409",
                    "",
                    "인크레더블버즈",
                ),
            ],
        )
        connection.commit()
    finally:
        connection.close()

    manifest_path = shard_root / "KIND_DISCTABLE_FULL.sqlite_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_table_manifest_v1",
                "schema_version": 4,
                "table_name": "disclosures",
                "summary": {"companies": 2, "disclosures": 4, "shards": 1},
                "shards": [
                    {
                        "year": "2025",
                        "companies": 2,
                        "disclosures": 4,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest_path


def _write_quanti_parquet(root: Path, *, include_volume: bool = True, include_adjusted: bool = False) -> Path:
    quanti_dir = root / "Quantiwise" / "parquetCalamine"
    quanti_dir.mkdir(parents=True)
    dates = pd.to_datetime(["2024-12-30", "2025-01-02", "2025-01-03", "2025-01-06"])
    values = {
        "open": [90, 100, 110, 115],
        "high": [95, 112, 116, 118],
        "low": [88, 98, 108, 113],
        "close": [94, 111, 114, 117],
        "volume": [800, 1000, 1200, 900],
    }
    adjusted_values = {
        "adjOpen": [9, 10, 11, 12],
        "adjHigh": [10, 12, 13, 14],
        "adjLow": [8, 9, 10, 11],
        "adjClose": [9, 11, 12, 13],
        "adjVolume": [8000, 10000, 12000, 9000],
    }
    for account, account_values in values.items():
        if account == "volume" and not include_volume:
            continue
        frame = pd.DataFrame({"date": dates, "A005930": account_values, "A123456": account_values, "A064090": account_values})
        frame.to_parquet(quanti_dir / f"{account}_20250102_20250106_fixture.parquet", index=False)
    if include_adjusted:
        for account, account_values in adjusted_values.items():
            frame = pd.DataFrame({"date": dates, "A005930": account_values, "A123456": account_values, "A064090": account_values})
            frame.to_parquet(quanti_dir / f"{account}_20250102_20250106_fixture.parquet", index=False)
    pd.DataFrame(
        {"code": ["A005930", "A123456", "A064090"], "name": ["테스트전자", "매핑전용", "인크레더블버즈"]}
    ).to_parquet(
        quanti_dir / "code_name_mapping.parquet",
        index=False,
    )
    return quanti_dir


def test_ontology_status_reports_manifest_and_quanti_coverage(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)

    payload = build_ontology_status(manifest_path=manifest_path, quanti_dir=quanti_dir)

    assert payload["kind"]["summary"]["disclosures"] == 4
    assert payload["kind"]["shard_years"] == ["2025"]
    assert payload["quantiwise"]["available_items"] == ["close", "high", "low", "open", "volume"]
    assert payload["quantiwise"]["mapped_companies"] == 3
    assert set(payload["disclosure_groups"]) >= {"shareholder_meeting", "bond_issuance", "rights_issuance"}
    assert payload["messages"] == []


def test_search_ontology_companies_returns_counts_and_price_availability(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)

    payload = search_ontology_companies(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        keyword="테스트",
        market="코스피",
    )

    assert payload["companies"] == [
        {
            "company_id": "A005930",
            "stock_code": "A005930",
            "company_name": "테스트전자",
            "market": "코스피",
            "disclosure_count": 3,
            "first_disclosed_date": "2024-12-30",
            "last_disclosed_date": "2025-01-02",
            "has_price_data": True,
        }
    ]


def test_search_ontology_companies_returns_quanti_mapping_matches_without_kind_rows(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)

    by_code = search_ontology_companies(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        keyword="A123456",
    )
    by_name = search_ontology_companies(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        keyword="매핑전용",
    )

    expected = {
        "company_id": "A123456",
        "stock_code": "A123456",
        "company_name": "매핑전용",
        "market": "",
        "disclosure_count": 0,
        "first_disclosed_date": "",
        "last_disclosed_date": "",
        "has_price_data": True,
    }
    assert by_code["companies"] == [expected]
    assert by_name["companies"] == [expected]


def test_search_ontology_companies_applies_market_filter_to_mapping_only_rows(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)

    payload = search_ontology_companies(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        keyword="매핑전용",
        market="코스피",
    )

    assert payload["companies"] == []
    assert payload["total"] == 0


def test_ontology_queries_reject_missing_manifest_shards(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    (manifest_path.parent / f"{manifest['shards'][0]['year']}.sqlite").unlink()

    with pytest.raises(FileNotFoundError, match="KIND SQLite shard not found"):
        search_ontology_companies(
            manifest_path=manifest_path,
            quanti_dir=quanti_dir,
        )
    with pytest.raises(FileNotFoundError, match="KIND SQLite shard not found"):
        build_ontology_company_panel(
            manifest_path=manifest_path,
            quanti_dir=quanti_dir,
            company_id="A005930",
        )
    with pytest.raises(FileNotFoundError, match="KIND SQLite shard not found"):
        triple_barrier._load_disclosures_for_triple_barrier(
            manifest_path=manifest_path,
            manifest=manifest,
            company_id="A005930",
            market="전체",
            disclosure_group="전체",
            disclosure_ids=[],
        )


def test_build_ontology_company_panel_uses_quanti_mapping_name_without_kind_rows(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)

    payload = build_ontology_company_panel(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        company_id="A123456",
        display_frequency_label="일봉",
    )

    assert payload["company"]["company_id"] == "A123456"
    assert payload["company"]["stock_code"] == "A123456"
    assert payload["company"]["company_name"] == "매핑전용"
    assert payload["company"]["market"] == ""


def test_build_ontology_company_panel_aligns_disclosures_to_price_candles(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)

    payload = build_ontology_company_panel(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        company_id="A005930",
        start_date=date(2025, 1, 2),
        end_date=date(2025, 1, 6),
        display_frequency_label="일봉",
    )

    assert payload["company"]["company_name"] == "테스트전자"
    assert payload["company"]["company_id"] == "A005930"
    assert payload["company"]["stock_code"] == "A005930"
    assert [candle["time"] for candle in payload["chart"]["candles"]] == [
        "2025-01-02",
        "2025-01-03",
        "2025-01-06",
    ]
    marker_by_acpt_no = {marker["acpt_no"]: marker for marker in payload["chart"]["markers"]}
    assert marker_by_acpt_no["20250102000001"]["time"] == "2025-01-02"
    assert marker_by_acpt_no["20250102000002"]["time"] == "2025-01-03"
    assert payload["summary"]["visible_disclosures"] == 2
    assert payload["summary"]["after_close_disclosures"] == 1
    assert payload["messages"] == []


def test_build_ontology_company_panel_prefers_adjusted_quanti_prices(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path, include_adjusted=True)

    payload = build_ontology_company_panel(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        company_id="A005930",
        start_date=date(2025, 1, 2),
        end_date=date(2025, 1, 6),
        display_frequency_label="일봉",
    )

    assert payload["chart"]["candles"][0]["open"] == 10
    assert payload["chart"]["candles"][0]["high"] == 12
    assert payload["chart"]["candles"][0]["low"] == 9
    assert payload["chart"]["candles"][0]["close"] == 11
    assert payload["chart"]["candles"][0]["volume"] == 10000


def test_build_ontology_company_panel_loads_category_json_disclosures_without_sqlite_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)
    kind_category_dir = tmp_path / "KIND"
    category_dir = kind_category_dir / "bond_issuance"
    category_dir.mkdir(parents=True)
    (category_dir / "filtered.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "company_id": "123456",
                        "company_name": "매핑전용",
                        "market": "코스피",
                        "disclosed_at": "2025-01-02 09:10",
                        "disclosed_date": "2025-01-02",
                        "title": "전환사채권발행결정",
                        "title_display": "전환사채권발행결정",
                        "has_later_correction": False,
                        "acpt_no": "20250102009999",
                        "doc_no": "",
                        "submitter": "매핑전용",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ontology_graph, "DEFAULT_KIND_CATEGORY_DIR", kind_category_dir)

    payload = build_ontology_company_panel(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        company_id="A123456",
        start_date=date(2025, 1, 2),
        end_date=date(2025, 1, 6),
        display_frequency_label="일봉",
        disclosure_group="bond_issuance",
    )

    assert payload["chart"]["markers"][0]["acpt_no"] == "20250102009999"
    assert payload["timeline"][0]["acpt_no"] == "20250102009999"
    assert payload["summary"]["visible_disclosures"] == 1


def test_build_ontology_company_panel_matches_short_kind_company_ids(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)

    payload = build_ontology_company_panel(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        company_id="A064090",
        start_date=date(2025, 1, 2),
        end_date=date(2025, 1, 6),
        display_frequency_label="일봉",
    )

    assert payload["company"]["company_name"] == "인크레더블버즈"
    assert payload["chart"]["markers"][0]["acpt_no"] == "20250102006409"
    assert payload["summary"]["visible_disclosures"] == 1


def test_build_ontology_company_panel_filters_by_disclosure_group(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)

    payload = build_ontology_company_panel(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        company_id="A005930",
        start_date=date(2025, 1, 2),
        end_date=date(2025, 1, 6),
        display_frequency_label="일봉",
        disclosure_group="shareholder_meeting",
    )

    assert payload["selected_disclosure_group"] == "shareholder_meeting"
    assert [marker["group"] for marker in payload["chart"]["markers"]] == ["주주총회"]
    assert [item["group"] for item in payload["timeline"]] == ["주주총회"]
    assert payload["summary"]["visible_candles"] == 3
    assert payload["summary"]["visible_disclosures"] == 1
    assert payload["summary"]["top_groups"] == [{"name": "주주총회", "count": 1}]


def test_build_ontology_company_panel_reports_final_report_status(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)
    shard_path = tmp_path / "KIND_DISCTABLE_FULL.sqlite_manifest_shards" / "2025.sqlite"
    connection = sqlite3.connect(shard_path)
    try:
        connection.execute(
            """
            INSERT INTO disclosures (
                company_key, company_name, company_id, market, disclosed_at,
                disclosed_date, title, title_display, is_correction_report,
                has_later_correction, acpt_no, doc_no, submitter
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "005930",
                "테스트전자",
                "005930",
                "코스피",
                "2025-01-03 09:10",
                "2025-01-03",
                "[정정]전환사채권발행결정",
                "[정정]전환사채권발행결정",
                1,
                1,
                "20250103000099",
                "",
                "테스트전자",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    payload = build_ontology_company_panel(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        company_id="A005930",
        start_date=date(2025, 1, 2),
        end_date=date(2025, 1, 6),
        display_frequency_label="일봉",
    )

    markers_by_acpt_no = {marker["acpt_no"]: marker for marker in payload["chart"]["markers"]}
    timeline_by_acpt_no = {item["acpt_no"]: item for item in payload["timeline"]}
    assert markers_by_acpt_no["20250103000099"]["final_report"] == "N"
    assert timeline_by_acpt_no["20250103000099"]["final_report"] == "N"
    assert markers_by_acpt_no["20250102000001"]["final_report"] == "Y"
    assert timeline_by_acpt_no["20250102000001"]["final_report"] == "Y"


def test_build_ontology_company_panel_defaults_to_full_available_range(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)

    payload = build_ontology_company_panel(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        company_id="A005930",
        display_frequency_label="일봉",
    )

    assert payload["range_start"] == "2024-12-30"
    assert payload["range_end"] == "2025-01-06"
    assert [candle["time"] for candle in payload["chart"]["candles"]] == [
        "2024-12-30",
        "2025-01-02",
        "2025-01-03",
        "2025-01-06",
    ]
    assert payload["summary"]["visible_disclosures"] == 3


def test_build_ontology_company_panel_supports_multi_day_frequency_options(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)

    five_day = build_ontology_company_panel(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        company_id="A005930",
        display_frequency_label="5일봉",
    )
    twenty_day = build_ontology_company_panel(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        company_id="A005930",
        display_frequency_label="20일봉",
    )

    assert five_day["display_frequency"] == "5day"
    assert twenty_day["display_frequency"] == "20day"
    assert [candle["time"] for candle in five_day["chart"]["candles"]] == ["2025-01-06"]
    assert [candle["time"] for candle in twenty_day["chart"]["candles"]] == ["2025-01-06"]
    assert five_day["chart"]["candles"][0]["open"] == 90
    assert five_day["chart"]["candles"][0]["close"] == 117
    assert five_day["chart"]["candles"][0]["volume"] == 3900


def test_build_ontology_company_panel_returns_json_safe_timeline_for_unmatched_markers(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)
    shard_path = tmp_path / "KIND_DISCTABLE_FULL.sqlite_manifest_shards" / "2025.sqlite"
    connection = sqlite3.connect(shard_path)
    try:
        connection.execute(
            """
            INSERT INTO disclosures (
                company_key, company_name, company_id, market, disclosed_at,
                disclosed_date, title, title_display, acpt_no, doc_no, submitter
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "005930",
                "테스트전자",
                "005930",
                "코스피",
                "2025-01-06 16:10",
                "2025-01-06",
                "주요사항보고서",
                "주요사항보고서",
                "20250106000099",
                "",
                "테스트전자",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    payload = build_ontology_company_panel(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        company_id="005930",
        start_date=date(2025, 1, 2),
        end_date=date(2025, 1, 6),
        display_frequency_label="일봉",
    )

    assert any(
        item["acpt_no"] == "20250106000099" and item["trade_day"] == ""
        for item in payload["timeline"]
    )
    json.dumps(payload, allow_nan=False)


def test_build_ontology_company_panel_reports_missing_price_items_without_fallback(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path, include_volume=False)

    payload = build_ontology_company_panel(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        company_id="005930",
        start_date=date(2025, 1, 2),
        end_date=date(2025, 1, 6),
    )

    assert payload["chart"]["candles"] == []
    assert payload["chart"]["markers"] == []
    assert payload["messages"] == ["Quantiwise item is missing: volume"]


def test_build_ontology_company_panel_stops_when_cancelled(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)

    with pytest.raises(OntologyRequestCancelled):
        build_ontology_company_panel(
            manifest_path=manifest_path,
            quanti_dir=quanti_dir,
            company_id="005930",
            start_date=date(2025, 1, 2),
            end_date=date(2025, 1, 6),
            cancellation_check=lambda: True,
        )


def test_ontology_api_routes_return_real_data_payloads(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)
    app = FastAPI()
    app.include_router(
        create_market_data_router(
            AppConfig(output_root=str(tmp_path), quanti_dir=str(quanti_dir)),
        )
    )
    client = TestClient(app)

    status = client.get(
        "/api/ontology/status",
        params={"manifest_path": str(manifest_path), "quanti_dir": str(quanti_dir)},
    )
    assert status.status_code == 200
    assert status.json()["kind"]["summary"]["companies"] == 2

    companies = client.get(
        "/api/ontology/companies",
        params={
            "manifest_path": str(manifest_path),
            "quanti_dir": str(quanti_dir),
            "keyword": "테스트",
        },
    )
    assert companies.status_code == 200
    assert companies.json()["companies"][0]["company_id"] == "A005930"

    panel = client.get(
        "/api/ontology/company-panel",
        params={
            "manifest_path": str(manifest_path),
            "quanti_dir": str(quanti_dir),
            "company_id": "A005930",
            "start_date": "2025-01-02",
            "end_date": "2025-01-06",
            "display_frequency": "일봉",
            "disclosure_group": "shareholder_meeting",
        },
    )
    assert panel.status_code == 200
    assert len(panel.json()["chart"]["candles"]) == 3
    assert panel.json()["selected_disclosure_group"] == "shareholder_meeting"
    assert [marker["group"] for marker in panel.json()["chart"]["markers"]] == ["주주총회"]


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


def test_triple_barrier_api_matches_short_kind_company_ids(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)
    api = FastAPI()
    api.include_router(
        create_market_data_router(
            AppConfig(output_root=str(tmp_path), quanti_dir=str(quanti_dir)),
        )
    )
    client = TestClient(api)

    response = client.post(
        "/api/ontology/triple-barrier/run",
        json={
            "manifest_path": str(manifest_path),
            "quanti_dir": str(quanti_dir),
            "company_id": "A064090",
            "market": "전체",
            "disclosure_group": "전체",
            "disclosure_ids": ["20250102006409"],
            "event_time_basis": "disclosed_date",
            "price_basis": "intraday",
            "upper_pct": 5,
            "lower_pct": 3,
            "vertical_days": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total"] == 1
    assert payload["summary"]["completed"] == 1
    assert payload["rows"][0]["ticker"] == "A064090"
    assert payload["rows"][0]["disclosure_id"] == "20250102006409"


def test_triple_barrier_api_filters_by_disclosure_group(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)
    api = FastAPI()
    api.include_router(
        create_market_data_router(
            AppConfig(output_root=str(tmp_path), quanti_dir=str(quanti_dir)),
        )
    )
    client = TestClient(api)

    full_response = client.post(
        "/api/ontology/triple-barrier/run",
        json={
            "manifest_path": str(manifest_path),
            "quanti_dir": str(quanti_dir),
            "company_id": "A005930",
            "market": "전체",
            "disclosure_group": "전체",
            "disclosure_ids": [],
            "event_time_basis": "disclosed_date",
            "price_basis": "intraday",
            "upper_pct": 5,
            "lower_pct": 3,
            "vertical_days": 2,
        },
    )
    response = client.post(
        "/api/ontology/triple-barrier/run",
        json={
            "manifest_path": str(manifest_path),
            "quanti_dir": str(quanti_dir),
            "company_id": "A005930",
            "market": "전체",
            "disclosure_group": "shareholder_meeting",
            "disclosure_ids": [],
            "event_time_basis": "disclosed_date",
            "price_basis": "intraday",
            "upper_pct": 5,
            "lower_pct": 3,
            "vertical_days": 2,
        },
    )

    assert full_response.status_code == 200
    assert full_response.json()["summary"]["total"] == 3
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total"] == 1
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["disclosure_id"] == "20250102000001"


def test_triple_barrier_api_loads_category_json_disclosures_without_sqlite_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)
    kind_category_dir = tmp_path / "KIND"
    category_dir = kind_category_dir / "bond_issuance"
    category_dir.mkdir(parents=True)
    (category_dir / "filtered.json").write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "company_id": "123456",
                        "company_name": "매핑전용",
                        "market": "코스피",
                        "disclosed_at": "2025-01-02 09:10",
                        "disclosed_date": "2025-01-02",
                        "title": "전환사채권발행결정",
                        "title_display": "전환사채권발행결정",
                        "has_later_correction": False,
                        "acpt_no": "20250102009999",
                        "doc_no": "",
                        "submitter": "매핑전용",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(ontology_graph, "DEFAULT_KIND_CATEGORY_DIR", kind_category_dir)
    api = FastAPI()
    api.include_router(
        create_market_data_router(
            AppConfig(output_root=str(tmp_path), quanti_dir=str(quanti_dir)),
        )
    )
    client = TestClient(api)

    response = client.post(
        "/api/ontology/triple-barrier/run",
        json={
            "manifest_path": str(manifest_path),
            "quanti_dir": str(quanti_dir),
            "company_id": "A123456",
            "market": "코스피",
            "disclosure_group": "bond_issuance",
            "disclosure_ids": [],
            "event_time_basis": "disclosed_date",
            "price_basis": "intraday",
            "upper_pct": 5,
            "lower_pct": 3,
            "vertical_days": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total"] == 1
    assert payload["rows"][0]["disclosure_id"] == "20250102009999"
    assert payload["rows"][0]["ticker"] == "A123456"


def test_triple_barrier_api_omits_config_quanti_dir_when_payload_uses_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run_triple_barrier_analysis(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "summary": {"total": 0, "completed": 0, "failed": 0, "created": 0, "reused": 0},
            "result_db_path": "",
            "parameter_hash": "",
            "rows": [],
        }

    monkeypatch.setattr(market_data_router, "run_triple_barrier_analysis", fake_run_triple_barrier_analysis)
    api = FastAPI()
    api.include_router(
        create_market_data_router(
            AppConfig(output_root=str(tmp_path), quanti_dir=str(tmp_path / "legacy-by-item")),
        )
    )
    client = TestClient(api)

    response = client.post(
        "/api/ontology/triple-barrier/run",
        json={
            "company_id": "A064090",
            "market": "전체",
            "disclosure_group": "bond_issuance",
            "disclosure_ids": [],
            "event_time_basis": "disclosed_date",
            "price_basis": "intraday",
            "upper_pct": 5,
            "lower_pct": 3,
            "vertical_days": 20,
        },
    )

    assert response.status_code == 200
    assert captured["quanti_dir"] is None


def test_ontology_network_api_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Mock output file content
    graph_data = {
        "nodes": [
            {
                "id": "company_005930",
                "label": "삼성전자",
                "type": "Company",
                "group": "Company",
                "tags": ["Company"],
                "properties": {"stock_code": "005930", "name": "삼성전자"}
            }
        ],
        "edges": []
    }

    mock_json_file = tmp_path / "ontology_graph.json"
    import json
    mock_json_file.write_text(json.dumps(graph_data), encoding="utf-8")

    # Patch the graph_json_path of OntologyGraphQueryService
    from finiq.data.ontology_query import OntologyGraphQueryService
    # Ensure the class points to our mock JSON file
    query_service = OntologyGraphQueryService(graph_json_path=mock_json_file)
    query_service.load_index(force=True)

    # Mock service instance
    monkeypatch.setattr("finiq.data.ontology_query.OntologyGraphQueryService", lambda *args, **kwargs: query_service)

    api = FastAPI()
    api.include_router(
        create_market_data_router(
            AppConfig(output_root=str(tmp_path), quanti_dir=str(tmp_path)),
        )
    )
    client = TestClient(api)

    response = client.get("/api/ontology/network", params={"company_id": "005930"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["id"] == "company_005930"

    # Verify paths endpoint
    response = client.get("/api/ontology/paths", params={"source_id": "company_005930", "target_id": "company_005930"})
    assert response.status_code == 200
    paths = response.json()
    assert len(paths) == 1
    assert paths[0]["nodes"][0]["id"] == "company_005930"

    # Verify control-chain endpoint
    response = client.get("/api/ontology/control-chain", params={"company_id": "005930"})
    assert response.status_code == 200
    chain = response.json()
    assert "nodes" in chain
    assert "edges" in chain
    assert len(chain["nodes"]) == 1
    assert chain["nodes"][0]["id"] == "company_005930"

    # Verify metadata endpoint
    response = client.get("/api/ontology/metadata")
    assert response.status_code == 200
    meta = response.json()
    assert isinstance(meta, dict)

    # Verify search endpoint
    response = client.get("/api/ontology/search", params={"query_name": "홍길동"})
    assert response.status_code == 200
    search_res = response.json()
    assert isinstance(search_res, list)
