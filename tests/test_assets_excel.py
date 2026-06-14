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
    read_asset_excel_sheets,
)


def _write_quanti_sheet(
    writer,
    sheet_name: str,
    rows: list[list[object]],
    *,
    codes: list[str] | None = None,
    names: list[str] | None = None,
    item_labels: list[str] | None = None,
):
    resolved_codes = codes or ["A005930", "A000660"]
    resolved_names = names or ["삼성전자", "SK하이닉스"]
    labels = item_labels or [sheet_name, sheet_name]
    prefix = [
        ["     Refresh     ", "Last Update : 2026-04-30"],
        [0],
        ["Time Series (Company)"],
        ["Frequency", "D", "Ascending", 0],
        ["Period(From)", 20200101],
        ["Period(To)", 20200102],
        [],
        ["Code", *resolved_codes],
        ["Name", *resolved_names],
        ["Item Code", *["SAMPLE" for _ in resolved_codes]],
        ["Unit", *["Local" for _ in resolved_codes]],
        ["Base Date"],
        [],
        ["D A T E", *labels],
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


def test_read_asset_excel_sheets_does_not_load_rows(tmp_path):
    excel_path = tmp_path / "sample.xlsx"
    with pd.ExcelWriter(excel_path) as writer:
        pd.DataFrame([{"value": 1}]).to_excel(writer, index=False, sheet_name="first")
        pd.DataFrame([{"value": 2}]).to_excel(writer, index=False, sheet_name="second")

    payload = read_asset_excel_sheets("sample.xlsx", root_directory=tmp_path)

    assert payload == {
        "file_name": "sample.xlsx",
        "relative_path": "sample.xlsx",
        "sheet_names": ["first", "second"],
        "sheet_count": 2,
    }
    assert "rows" not in payload


def test_read_asset_excel_quanti_preview_uses_date_code_matrix(tmp_path):
    excel_path = tmp_path / "quanti.xlsx"
    with pd.ExcelWriter(excel_path) as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [
                [pd.Timestamp("2020-01-01"), 100, 200],
                [pd.Timestamp("2020-01-02"), 101, 201],
            ],
        )

    payload = read_asset_excel("quanti.xlsx", sheet_name="종가", row_limit=20, root_directory=tmp_path)

    assert payload["preview_type"] == "quanti_matrix"
    assert payload["account_name"] == "stock_price"
    assert payload["status"] == "mapped"
    assert payload["metadata"] == {"period_from": "20200101", "period_to": "20200102"}
    assert payload["columns"] == ["date", "A005930", "A000660"]
    assert payload["preview_columns"] == ["date", "A005930", "A000660"]
    assert payload["rows"] == [
        {"date": "2020-01-01", "A005930": 100, "A000660": 200},
        {"date": "2020-01-02", "A005930": 101, "A000660": 201},
    ]
    assert "     Refresh     " not in payload["columns"]


def test_read_asset_excel_rejects_path_outside_assets(tmp_path):
    outside_path = tmp_path.parent / "outside.xlsx"
    pd.DataFrame([{"value": 1}]).to_excel(outside_path, index=False)

    try:
        read_asset_excel(outside_path, root_directory=tmp_path)
    except ValueError as exc:
        assert "under Quantiwise directory" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_asset_excel_api(tmp_path, monkeypatch):
    excel_path = tmp_path / "api.xlsx"
    with pd.ExcelWriter(excel_path) as writer:
        pd.DataFrame([{"name": "FINIQ"}]).to_excel(writer, index=False, sheet_name="data")
        pd.DataFrame([{"name": "ALT"}]).to_excel(writer, index=False, sheet_name="other")
    monkeypatch.setattr(app_module, "QUANTIWISE_EXCEL_DIR", tmp_path)

    client = TestClient(app_module.app)

    list_response = client.get("/api/assets/excels")
    assert list_response.status_code == 200
    assert list_response.json()["root_directory"] == str(tmp_path.resolve())
    assert list_response.json()["default_output_directory"]
    assert list_response.json()["excel_files"][0]["relative_path"] == "api.xlsx"

    sheets_response = client.get("/api/assets/excels/api.xlsx/sheets")
    assert sheets_response.status_code == 200
    assert sheets_response.json()["sheet_names"] == ["data", "other"]
    assert "rows" not in sheets_response.json()

    read_response = client.get("/api/assets/excels/api.xlsx", params={"sheet_name": "data"})
    assert read_response.status_code == 200
    assert read_response.json()["rows"] == [{"name": "FINIQ"}]

    stale_sheet_response = client.get("/api/assets/excels/api.xlsx", params={"sheet_name": "Sheet1"})
    assert stale_sheet_response.status_code == 400
    assert "Worksheet named 'Sheet1' not found" in stale_sheet_response.json()["detail"]


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
    monkeypatch.setattr(app_module, "QUANTIWISE_EXCEL_DIR", tmp_path)

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
    assert (output_dir / "code_name_mapping.parquet").exists()
    assert payload["code_name_mapping"]["rows"] == 2
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

    mapping = pd.read_parquet(output_dir / "code_name_mapping.parquet")
    assert mapping[["code", "name"]].to_dict("records") == [
        {"code": "A000660", "name": "SK하이닉스"},
        {"code": "A005930", "name": "삼성전자"},
    ]


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
            codes=["A035420", "A051910"],
            names=["NAVER", "LG화학"],
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
    mapping = pd.read_parquet(output_dir / "code_name_mapping.parquet")
    assert mapping[["code", "name"]].to_dict("records") == [
        {"code": "A000660", "name": "SK하이닉스"},
        {"code": "A005930", "name": "삼성전자"},
        {"code": "A035420", "name": "NAVER"},
        {"code": "A051910", "name": "LG화학"},
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
    assert preview["code_name_mapping"]["rows"] == 2
    assert output["manifest_exists"] is True
    assert output["code_name_mapping_exists"] is True
    assert output["parquet_files"] == ["stock_price.parquet"]


def test_inspect_asset_excel_conversion_skips_bad_quanti_sheet(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    excel_path = source_dir / "bad.xlsx"
    pd.DataFrame([{"not": "quanti"}]).to_excel(excel_path, sheet_name="종가", index=False)

    preview = inspect_asset_excel_conversion(source_dir, output_dir)

    assert preview["skipped"] == [
        {
            "file_name": "bad.xlsx",
            "relative_path": "bad.xlsx",
            "sheet_name": "종가",
            "reason": "Unsupported sheet format: bad.xlsx / 종가",
            "status": "format_error",
        }
    ]
    assert preview["sheets"][0]["status"] == "format_error"


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


def test_convert_asset_excels_always_rejects_conflicts_even_if_policy_is_requested(tmp_path):
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


def test_trading_halt_flag_like_sheet_reads_three_times(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    excel_path = source_dir / "halt.xlsx"
    with pd.ExcelWriter(excel_path) as writer:
        _write_quanti_sheet(
            writer,
            "거래정지여부",
            [
                [pd.Timestamp("2020-01-01"), "정상", "정지"],
                [pd.Timestamp("2020-01-02"), "정지", "정상"],
            ],
            item_labels=["거래정지여부(정지/정상)", "거래정지여부(정지/정상)"],
        )

    for _ in range(3):
        payload = read_asset_excel_interpreted(
            "halt.xlsx",
            sheet_name="거래정지여부",
            root_directory=source_dir,
        )
        assert payload["account_name"] == "trading_halt_flag"
        assert payload["status"] == "mapped"
        assert payload["columns"] == ["date", "A005930", "A000660"]
        assert payload["rows"][0] == {
            "date": "2020-01-01",
            "A005930": "정상",
            "A000660": "정지",
        }

    result = convert_asset_excels_to_wide_parquet(source_dir, output_dir)
    halt = pd.read_parquet(output_dir / "trading_halt_flag.parquet")
    mapping = pd.read_parquet(output_dir / "code_name_mapping.parquet")

    assert result["accounts"]["trading_halt_flag"]["rows"] == 2
    assert halt["A005930"].tolist() == ["정상", "정지"]
    assert mapping[["code", "name"]].to_dict("records") == [
        {"code": "A000660", "name": "SK하이닉스"},
        {"code": "A005930", "name": "삼성전자"},
    ]


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
