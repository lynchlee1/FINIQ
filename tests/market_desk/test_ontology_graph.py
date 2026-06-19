from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sqlite3

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from finiq.config import AppConfig
from finiq.market_desk.analytics.ontology_graph import (
    build_ontology_company_panel,
    build_ontology_status,
    search_ontology_companies,
)
from finiq.market_desk.web.routers.market_data import create_market_data_router


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
                source_file TEXT,
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
                "schema_version": 2,
                "table_name": "disclosures",
                "summary": {"companies": 2, "disclosures": 3, "shards": 1},
                "shards": [
                    {
                        "year": "2025",
                        "relative_path": "2025.sqlite",
                        "companies": 2,
                        "disclosures": 3,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest_path


def _write_quanti_parquet(root: Path, *, include_volume: bool = True) -> Path:
    quanti_dir = root / "Quantiwise" / "parquetCalamine"
    quanti_dir.mkdir(parents=True)
    dates = pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"])
    values = {
        "open": [100, 110, 115],
        "high": [112, 116, 118],
        "low": [98, 108, 113],
        "close": [111, 114, 117],
        "volume": [1000, 1200, 900],
    }
    for account, account_values in values.items():
        if account == "volume" and not include_volume:
            continue
        frame = pd.DataFrame({"date": dates, "A005930": account_values})
        frame.to_parquet(quanti_dir / f"{account}_20250102_20250106_fixture.parquet", index=False)
    pd.DataFrame({"code": ["A005930"], "name": ["테스트전자"]}).to_parquet(
        quanti_dir / "code_name_mapping.parquet",
        index=False,
    )
    return quanti_dir


def test_ontology_status_reports_manifest_and_quanti_coverage(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)

    payload = build_ontology_status(manifest_path=manifest_path, quanti_dir=quanti_dir)

    assert payload["kind"]["summary"]["disclosures"] == 3
    assert payload["kind"]["shard_years"] == ["2025"]
    assert payload["quantiwise"]["available_items"] == ["close", "high", "low", "open", "volume"]
    assert payload["quantiwise"]["mapped_companies"] == 1
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
            "company_id": "005930",
            "company_name": "테스트전자",
            "market": "코스피",
            "disclosure_count": 2,
            "first_disclosed_date": "2025-01-02",
            "last_disclosed_date": "2025-01-02",
            "has_price_data": True,
        }
    ]


def test_build_ontology_company_panel_aligns_disclosures_to_price_candles(tmp_path: Path) -> None:
    manifest_path = _write_disclosure_shard(tmp_path)
    quanti_dir = _write_quanti_parquet(tmp_path)

    payload = build_ontology_company_panel(
        manifest_path=manifest_path,
        quanti_dir=quanti_dir,
        company_id="005930",
        start_date=date(2025, 1, 2),
        end_date=date(2025, 1, 6),
        display_frequency_label="일봉",
    )

    assert payload["company"]["company_name"] == "테스트전자"
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
    assert companies.json()["companies"][0]["company_id"] == "005930"

    panel = client.get(
        "/api/ontology/company-panel",
        params={
            "manifest_path": str(manifest_path),
            "quanti_dir": str(quanti_dir),
            "company_id": "005930",
            "start_date": "2025-01-02",
            "end_date": "2025-01-06",
            "display_frequency": "일봉",
        },
    )
    assert panel.status_code == 200
    assert len(panel.json()["chart"]["candles"]) == 3
