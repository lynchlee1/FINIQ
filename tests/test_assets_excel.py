from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

import finiq.market_desk.web.app as app_module
from finiq.data.assets_excel import (
    convert_asset_excels_to_wide_parquet,
    inspect_asset_excel_conversion,
    inspect_asset_excel_output,
    list_asset_excel_files,
    read_asset_excel,
    read_asset_excel_interpreted,
)


def _write_quanti_sheet(writer, sheet_name: str, rows: list[list[object]]):
    prefix = [
        ["     Refresh     ", "Last Update : 2026-04-30"],
        [0],
        ["Time Series (Company)"],
        ["Frequency", "D", "Ascending", 0],
        ["Period(From)", 20200101],
        ["Period(To)", 20200102],
        [],
        ["Code", "A005930", "A000660"],
        ["Name", "삼성전자", "SK하이닉스"],
        ["Item Code", "SAMPLE", "SAMPLE"],
        ["Unit", "Local", "Local"],
        ["Base Date"],
        [],
        ["D A T E", sheet_name, sheet_name],
    ]
    pd.DataFrame(prefix + rows).to_excel(writer, sheet_name=sheet_name, header=False, index=False)


def test_list_and_read_asset_excel(tmp_path):
    excel_path = tmp_path / "sample.xlsx"
    pd.DataFrame(
        [
            {"code": "005930", "price": 1000},
            {"code": "000660", "price": 2000},
        ]
    ).to_excel(excel_path, index=False, sheet_name="prices")

    files = list_asset_excel_files(tmp_path)

    assert files == [
        {
            "file_name": "sample.xlsx",
            "relative_path": "sample.xlsx",
            "stem": "sample",
            "size_bytes": excel_path.stat().st_size,
        }
    ]

    payload = read_asset_excel("sample.xlsx", sheet_name="prices", root_directory=tmp_path)

    assert payload["file_name"] == "sample.xlsx"
    assert payload["sheet_names"] == ["prices"]
    assert payload["columns"] == ["code", "price"]
    assert payload["rows"] == [
        {"code": "005930", "price": 1000},
        {"code": "000660", "price": 2000},
    ]


def test_read_asset_excel_rejects_path_outside_assets(tmp_path):
    outside_path = tmp_path.parent / "outside.xlsx"
    pd.DataFrame([{"value": 1}]).to_excel(outside_path, index=False)

    try:
        read_asset_excel(outside_path, root_directory=tmp_path)
    except ValueError as exc:
        assert "under assets directory" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_asset_excel_api(tmp_path, monkeypatch):
    excel_path = tmp_path / "api.xlsx"
    pd.DataFrame([{"name": "FINIQ"}]).to_excel(excel_path, index=False, sheet_name="data")
    monkeypatch.setattr(app_module, "ASSETS_DIR", tmp_path)

    client = TestClient(app_module.app)

    list_response = client.get("/api/assets/excels")
    assert list_response.status_code == 200
    assert list_response.json()["excel_files"][0]["relative_path"] == "api.xlsx"

    read_response = client.get("/api/assets/excels/api.xlsx", params={"sheet_name": "data"})
    assert read_response.status_code == 200
    assert read_response.json()["rows"] == [{"name": "FINIQ"}]


def test_asset_excel_interpreted_preview_api(tmp_path, monkeypatch):
    excel_path = tmp_path / "api.xlsx"
    with pd.ExcelWriter(excel_path) as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [
                [pd.Timestamp("2020-01-01"), 100, 200],
                [pd.Timestamp("2020-01-02"), None, 201],
            ],
        )
    monkeypatch.setattr(app_module, "ASSETS_DIR", tmp_path)

    payload = read_asset_excel_interpreted("api.xlsx", sheet_name="종가", root_directory=tmp_path)

    assert payload["account_name"] == "stock_price"
    assert payload["status"] == "mapped"
    assert payload["columns"] == ["date", "A005930", "A000660"]
    assert payload["rows"][0]["date"] == "2020-01-01"

    client = TestClient(app_module.app)
    response = client.get(
        "/api/assets/excels/api.xlsx",
        params={"sheet_name": "종가", "interpreted": "true"},
    )

    assert response.status_code == 200
    assert response.json()["account_name"] == "stock_price"


def test_convert_asset_excels_to_wide_parquet_by_account_name(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [
                [pd.Timestamp("2020-01-01"), 100, 200],
                [pd.Timestamp("2020-01-02"), 101, 201],
            ],
        )
    with pd.ExcelWriter(source_dir / "source-b.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "거래량",
            [
                [pd.Timestamp("2020-01-01"), 1000, 2000],
                [pd.Timestamp("2020-01-02"), 1001, 2001],
            ],
        )

    payload = convert_asset_excels_to_wide_parquet(source_dir, output_dir)

    assert payload["accounts_processed"] == 2
    assert (output_dir / "stock_price.parquet").exists()
    assert (output_dir / "volume.parquet").exists()
    assert payload["accounts"]["stock_price"]["date_index"] == ["2020-01-01", "2020-01-02"]
    assert payload["accounts"]["stock_price"]["date_segments"] == [
        {"start": "2020-01-01", "end": "2020-01-02", "count": 2}
    ]
    assert payload["accounts"]["stock_price"]["sources"][0]["date_index"] == [
        "2020-01-01",
        "2020-01-02",
    ]

    stock_price = pd.read_parquet(output_dir / "stock_price.parquet")
    volume = pd.read_parquet(output_dir / "volume.parquet")

    assert stock_price.columns.tolist() == ["date", "A005930", "A000660"]
    assert volume.columns.tolist() == ["date", "A005930", "A000660"]
    assert stock_price["A005930"].tolist() == [100, 101]
    assert volume["A000660"].tolist() == [2000, 2001]


def test_convert_asset_excels_uses_selected_files(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )
    with pd.ExcelWriter(source_dir / "source-b.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "거래량",
            [[pd.Timestamp("2020-01-01"), 1000, 2000]],
        )

    payload = convert_asset_excels_to_wide_parquet(
        source_dir,
        output_dir,
        selected_files=["source-b.xlsx"],
    )

    assert payload["accounts_processed"] == 1
    assert "volume" in payload["accounts"]
    assert "stock_price" not in payload["accounts"]
    assert not (output_dir / "stock_price.parquet").exists()


def test_convert_asset_excels_updates_existing_output(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-03"), 100, 200]],
        )
    convert_asset_excels_to_wide_parquet(source_dir, output_dir)

    with pd.ExcelWriter(source_dir / "source-b.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-06"), 101, 201]],
        )

    payload = convert_asset_excels_to_wide_parquet(
        source_dir,
        output_dir,
        selected_files=["source-b.xlsx"],
        write_mode="update",
    )

    stock_price = pd.read_parquet(output_dir / "stock_price.parquet")
    assert stock_price["date"].astype(str).tolist() == ["2020-01-03", "2020-01-06"]
    assert payload["updated_accounts"] == ["stock_price"]
    assert payload["accounts"]["stock_price"]["date_segments"] == [
        {"start": "2020-01-03", "end": "2020-01-06", "count": 2},
    ]


def test_inspect_asset_excel_conversion_reports_mapping_and_existing_output(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )
    convert_asset_excels_to_wide_parquet(source_dir, output_dir)

    preview = inspect_asset_excel_conversion(
        source_dir,
        output_dir,
        selected_files=["source-a.xlsx"],
    )
    output = inspect_asset_excel_output(output_dir)

    assert preview["sheets"][0]["account_name"] == "stock_price"
    assert preview["sheets"][0]["status"] == "mapped"
    assert preview["accounts"]["stock_price"]["will_update_existing"] is True
    assert preview["accounts"]["stock_price"]["quality"]["sample_rows"]
    assert output["manifest_exists"] is True
    assert output["parquet_files"] == ["stock_price.parquet"]


def test_convert_asset_excels_rejects_conflicting_overlaps(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )
    with pd.ExcelWriter(source_dir / "source-b.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 999, 200]],
        )

    try:
        convert_asset_excels_to_wide_parquet(source_dir, output_dir)
    except ValueError as exc:
        assert "Conflicting overlapping values" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_convert_asset_excels_can_prefer_latest_for_conflicting_overlaps(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )
    with pd.ExcelWriter(source_dir / "source-b.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 999, 200]],
        )

    payload = convert_asset_excels_to_wide_parquet(
        source_dir,
        output_dir,
        conflict_policy="prefer_latest",
    )

    stock_price = pd.read_parquet(output_dir / "stock_price.parquet")
    assert payload["conflicts"]["stock_price"][0]["code"] == "A005930"
    assert stock_price["A005930"].tolist() == [999]


def test_convert_asset_excels_allows_one_day_adjacent_ranges(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )
    with pd.ExcelWriter(source_dir / "source-b.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-02"), 101, 201]],
        )

    payload = convert_asset_excels_to_wide_parquet(source_dir, output_dir)

    assert payload["accounts"]["stock_price"]["date_index"] == ["2020-01-01", "2020-01-02"]


def test_convert_asset_excels_treats_weekend_gap_as_continuous(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-03"), 100, 200]],
        )
    with pd.ExcelWriter(source_dir / "source-b.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-06"), 101, 201]],
        )

    payload = convert_asset_excels_to_wide_parquet(source_dir, output_dir)

    assert payload["accounts"]["stock_price"]["date_index"] == ["2020-01-03", "2020-01-06"]
    assert payload["accounts"]["stock_price"]["date_segments"] == [
        {"start": "2020-01-03", "end": "2020-01-06", "count": 2},
    ]


def test_convert_asset_excels_stores_multiple_date_segments(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )
    with pd.ExcelWriter(source_dir / "source-b.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-04"), 101, 201]],
        )

    payload = convert_asset_excels_to_wide_parquet(source_dir, output_dir)

    assert payload["accounts"]["stock_price"]["date_index"] == ["2020-01-01", "2020-01-04"]
    assert payload["accounts"]["stock_price"]["date_segments"] == [
        {"start": "2020-01-01", "end": "2020-01-01", "count": 1},
        {"start": "2020-01-04", "end": "2020-01-04", "count": 1},
    ]


def test_convert_asset_excels_keeps_one_sheet_as_one_date_segment(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [
                [pd.Timestamp("2020-01-03"), 100, 200],
                [pd.Timestamp("2020-01-06"), 101, 201],
            ],
        )

    payload = convert_asset_excels_to_wide_parquet(source_dir, output_dir)

    assert payload["accounts"]["stock_price"]["date_index"] == ["2020-01-03", "2020-01-06"]
    assert payload["accounts"]["stock_price"]["date_segments"] == [
        {"start": "2020-01-03", "end": "2020-01-06", "count": 2},
    ]
    assert payload["accounts"]["stock_price"]["sources"][0]["date_segments"] == [
        {"start": "2020-01-03", "end": "2020-01-06", "count": 2},
    ]
