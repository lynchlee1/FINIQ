from __future__ import annotations

import json
import threading

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import finiq.data.assets_excel as assets_excel_module
import finiq.market_desk.web.app as app_module
from finiq.data.assets_excel import (
    convert_asset_excels_to_wide_parquet,
    inspect_asset_excel_conversion,
    inspect_asset_excel_output,
    list_asset_excel_files,
    merge_asset_parquet_outputs,
    read_asset_excel,
    read_asset_excel_interpreted,
    read_asset_parquet_preview,
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


def _output_for_sheet(payload: dict, sheet_name: str, relative_path: str | None = None) -> dict:
    matches = [
        item
        for item in payload["outputs"].values()
        if item["sheet_name"] == sheet_name and (relative_path is None or item["relative_path"] == relative_path)
    ]
    assert len(matches) == 1
    return matches[0]


def _read_output_sheet(payload: dict, output_dir, sheet_name: str, relative_path: str | None = None) -> pd.DataFrame:
    item = _output_for_sheet(payload, sheet_name, relative_path)
    return pd.read_parquet(output_dir / item["output_file"])


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
    assert payload["account_name"] == "close"
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
    monkeypatch.setattr(app_module.config, "asset_excel_account_mappings", [])

    client = TestClient(app_module.app)

    missing_source_response = client.get("/api/assets/excels")
    assert missing_source_response.status_code == 400
    assert missing_source_response.json()["detail"] == "source_directory is required"

    list_response = client.get("/api/assets/excels", params={"source_directory": str(tmp_path)})
    assert list_response.status_code == 200
    assert list_response.json()["root_directory"] == str(tmp_path.resolve())
    assert "default_output_directory" not in list_response.json()
    assert list_response.json()["excel_files"][0]["relative_path"] == "api.xlsx"

    mappings_response = client.get("/api/assets/excels/account-mappings")
    assert mappings_response.status_code == 200
    assert mappings_response.json()["items"][0] == {
        "account_id": "S00001",
        "account_name": "close",
        "legacy_account_name": "stock_price",
        "sheet_name": "종가",
    }

    sheets_response = client.get("/api/assets/excels/api.xlsx/sheets", params={"source_directory": str(tmp_path)})
    assert sheets_response.status_code == 200
    assert sheets_response.json()["sheet_names"] == ["data", "other"]
    assert "rows" not in sheets_response.json()

    read_response = client.get(
        "/api/assets/excels/api.xlsx",
        params={"sheet_name": "data", "source_directory": str(tmp_path)},
    )
    assert read_response.status_code == 200
    assert read_response.json()["rows"] == [{"name": "FINIQ"}]

    stale_sheet_response = client.get(
        "/api/assets/excels/api.xlsx",
        params={"sheet_name": "Sheet1", "source_directory": str(tmp_path)},
    )
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

    assert payload["account_name"] == "close"
    assert payload["status"] == "mapped"
    assert payload["columns"] == ["date", "A005930", "A000660"]
    assert payload["rows"][0]["date"] == "2020-01-01"

    client = TestClient(app_module.app)
    response = client.get(
        "/api/assets/excels/api.xlsx",
        params={"sheet_name": "종가", "interpreted": "true", "source_directory": str(tmp_path)},
    )

    assert response.status_code == 200
    assert response.json()["account_name"] == "close"


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
    assert payload["sheets_processed"] == 2
    stock_output = _output_for_sheet(payload, "종가")
    volume_output = _output_for_sheet(payload, "거래량")
    assert stock_output["output_file"] == "close_20200101_20200102.parquet"
    assert volume_output["output_file"] == "volume_20200101_20200102.parquet"
    assert stock_output["account_id"] == "S00001"
    assert stock_output["account_name"] == "close"
    assert stock_output["legacy_account_name"] == "stock_price"
    assert (output_dir / stock_output["output_file"]).exists()
    assert (output_dir / volume_output["output_file"]).exists()
    assert (output_dir / "code_name_mapping.parquet").exists()
    assert (output_dir / "account_mapping.parquet").exists()
    assert payload["code_name_mapping"]["rows"] == 2
    assert payload["account_mapping"]["items"][0] == {
        "account_id": "S00001",
        "account_name": "close",
        "legacy_account_name": "stock_price",
        "sheet_name": "종가",
    }
    assert stock_output["date_segments"] == [
        {"start": "2020-01-01", "end": "2020-01-02"}
    ]
    assert "date_index" not in stock_output
    assert "date_index" not in stock_output["sources"][0]
    assert "sample_rows" not in stock_output["quality"]

    stock_price = _read_output_sheet(payload, output_dir, "종가")
    volume = _read_output_sheet(payload, output_dir, "거래량")

    assert stock_price.columns.tolist() == ["date", "A005930", "A000660"]
    assert volume.columns.tolist() == ["date", "A005930", "A000660"]
    assert stock_price["A005930"].tolist() == [100, 101]
    assert volume["A000660"].tolist() == [2000, 2001]
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest_output = next(item for item in manifest["outputs"].values() if item["sheet_name"] == "종가")
    assert "date_index" not in manifest_output
    assert "date_index" not in manifest_output["sources"][0]
    assert "sample_rows" not in manifest_output["quality"]

    mapping = pd.read_parquet(output_dir / "code_name_mapping.parquet")
    assert mapping[["code", "name"]].to_dict("records") == [
        {"code": "A000660", "name": "SK하이닉스"},
        {"code": "A005930", "name": "삼성전자"},
    ]


def test_convert_asset_excels_uses_custom_account_mappings(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )

    mappings = [
        {
            "account_id": "A90001",
            "account_name": "customClose",
            "legacy_account_name": "stock_price",
            "sheet_name": "종가",
        }
    ]
    preview = inspect_asset_excel_conversion(source_dir, output_dir, account_mappings=mappings)
    payload = convert_asset_excels_to_wide_parquet(source_dir, output_dir, account_mappings=mappings)

    preview_output = _output_for_sheet(preview, "종가")
    output = _output_for_sheet(payload, "종가")
    assert preview_output["account_id"] == "A90001"
    assert preview_output["account_name"] == "customClose"
    assert output["output_file"] == "customClose_20200101_20200101.parquet"
    assert output["account_id"] == "A90001"
    assert output["account_name"] == "customClose"
    assert payload["account_mapping"]["items"] == mappings


def test_custom_account_mappings_reject_underscores_in_id_and_name(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )

    with pytest.raises(ValueError, match="account_id cannot contain underscore"):
        inspect_asset_excel_conversion(
            source_dir,
            output_dir,
            account_mappings=[
                {
                    "account_id": "A_90001",
                    "account_name": "customClose",
                    "legacy_account_name": "stock_price",
                    "sheet_name": "종가",
                }
            ],
        )

    with pytest.raises(ValueError, match="account_name cannot contain underscore"):
        convert_asset_excels_to_wide_parquet(
            source_dir,
            output_dir,
            account_mappings=[
                {
                    "account_id": "A90001",
                    "account_name": "custom_close",
                    "legacy_account_name": "stock_price",
                    "sheet_name": "종가",
                }
            ],
        )


def test_custom_account_mappings_reject_duplicate_account_names(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )
        _write_quanti_sheet(
            writer,
            "시가",
            [[pd.Timestamp("2020-01-01"), 90, 190]],
        )

    with pytest.raises(ValueError, match="Duplicate account mapping account_name: customClose"):
        inspect_asset_excel_conversion(
            source_dir,
            output_dir,
            account_mappings=[
                {
                    "account_id": "A90001",
                    "account_name": "customClose",
                    "legacy_account_name": "stock_price",
                    "sheet_name": "종가",
                },
                {
                    "account_id": "A90002",
                    "account_name": "customClose",
                    "legacy_account_name": "stock_open",
                    "sheet_name": "시가",
                },
            ],
        )


def test_inspect_asset_excel_conversion_treats_deleted_account_mapping_as_unmapped(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )

    preview = inspect_asset_excel_conversion(source_dir, output_dir, account_mappings=[])

    assert preview["outputs"] == {}
    assert preview["skipped"] == [
        {
            "file_name": "source-a.xlsx",
            "relative_path": "source-a.xlsx",
            "sheet_name": "종가",
            "reason": "No account-name mapping",
            "status": "unmapped",
        }
    ]
    assert preview["sheets"][0]["status"] == "unmapped"


def test_read_asset_parquet_preview_matches_quanti_preview_shape(tmp_path):
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

    payload = convert_asset_excels_to_wide_parquet(source_dir, output_dir)
    output = _output_for_sheet(payload, "종가")
    preview = read_asset_parquet_preview(output["output_file"], output_directory=output_dir)

    assert preview["preview_type"] == "quanti_parquet"
    assert preview["sheet_name"] == "종가"
    assert preview["account_name"] == "close"
    assert preview["metadata"] == {"period_from": "20200101", "period_to": "20200102"}
    assert preview["columns"] == ["date", "A005930", "A000660"]
    assert preview["preview_columns"] == ["date", "A005930", "A000660"]
    assert preview["rows"] == [
        {"date": "2020-01-01", "A005930": 100, "A000660": 200},
        {"date": "2020-01-02", "A005930": 101, "A000660": 201},
    ]


def test_asset_parquet_preview_api(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )
    payload = convert_asset_excels_to_wide_parquet(source_dir, output_dir)
    output = _output_for_sheet(payload, "종가")

    client = TestClient(app_module.app)
    response = client.get(
        "/api/assets/parquet/preview",
        params={
            "output_directory": str(output_dir),
            "file_name": output["output_file"],
        },
    )

    assert response.status_code == 200
    assert response.json()["rows"] == [{"date": "2020-01-01", "A005930": 100, "A000660": 200}]


def test_asset_excel_apis_require_explicit_output_directory(tmp_path):
    source_dir = tmp_path / "assets"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )

    client = TestClient(app_module.app)

    output_response = client.get("/api/assets/excels/output")
    assert output_response.status_code == 400
    assert output_response.json()["detail"] == "output_directory is required"

    preview_response = client.post(
        "/api/assets/excels/preview-conversion",
        json={"source_directory": str(source_dir), "output_directory": ""},
    )
    assert preview_response.status_code == 400
    assert preview_response.json()["detail"] == "output_directory is required"

    start_response = client.post(
        "/api/assets/excels/convert-wide-parquet/start",
        json={"source_directory": str(source_dir), "output_directory": ""},
    )
    assert start_response.status_code == 400
    assert start_response.json()["detail"] == "output_directory is required"

    merge_start_response = client.post(
        "/api/assets/parquet/merge/start",
        json={
            "base_directory": str(tmp_path / "base"),
            "incoming_directory": str(tmp_path / "incoming"),
            "output_directory": "",
        },
    )
    assert merge_start_response.status_code == 400
    assert merge_start_response.json()["detail"] == "output_directory is required"

    direct_merge_output = tmp_path / "direct-merge-output"
    merge_response = client.post(
        "/api/assets/parquet/merge",
        json={
            "base_directory": "",
            "incoming_directory": str(tmp_path / "incoming"),
            "output_directory": str(direct_merge_output),
        },
    )
    assert merge_response.status_code == 400
    assert merge_response.json()["detail"] == "base_directory is required"
    assert not direct_merge_output.exists()

    merge_response = client.post(
        "/api/assets/parquet/merge",
        json={
            "base_directory": str(tmp_path / "base"),
            "incoming_directory": "",
            "output_directory": str(direct_merge_output),
        },
    )
    assert merge_response.status_code == 400
    assert merge_response.json()["detail"] == "incoming_directory is required"
    assert not direct_merge_output.exists()


def test_convert_asset_excels_reports_detailed_progress_log(tmp_path):
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

    progress_log: list[str] = []

    convert_asset_excels_to_wide_parquet(
        source_dir,
        output_dir,
        progress_callback=progress_log.append,
    )

    assert "Quantiwise 변환 시작" in progress_log
    assert any("원본 데이터 경로:" in line for line in progress_log)
    assert any("임시 데이터 경로:" in line for line in progress_log)
    assert any("매핑 완료: 계정=close, 행=2, 코드=2, 날짜=2020-01-01~2020-01-02" in line for line in progress_log)
    assert any("임시 저장:" in line and "close_20200101_20200102" in line for line in progress_log)
    assert any("스캔 완료: Sheet 1개, 정상 1개, 건너뜀 0개, 계정 1개" in line for line in progress_log)
    assert any("Sheet 단위 생성:" in line for line in progress_log)
    assert any("[저장 1/1]" in line and "계정=close" in line and "Sheet=종가" in line for line in progress_log)
    assert any("코드-종목명 매핑 저장: code_name_mapping.parquet (2행)" in line for line in progress_log)
    assert any("manifest 저장:" in line for line in progress_log)
    assert any("Quantiwise 변환 완료: Sheet Parquet 1개, 건너뛴 Sheet 0개" in line for line in progress_log)


def test_convert_asset_excels_reports_skipped_sheet_details(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )
        _write_quanti_sheet(
            writer,
            "알수없는시트",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )

    progress_log: list[str] = []

    payload = convert_asset_excels_to_wide_parquet(
        source_dir,
        output_dir,
        progress_callback=progress_log.append,
    )

    assert payload["skipped"] == [
        {
            "file_name": "source-a.xlsx",
            "relative_path": "source-a.xlsx",
            "sheet_name": "알수없는시트",
            "reason": "Unmapped sheet name",
            "status": "unmapped",
        }
    ]
    assert any(
        "건너뛴 Sheet 상세: source-a.xlsx / 알수없는시트 - Unmapped sheet name" in line
        for line in progress_log
    )


def test_convert_asset_excels_cancel_during_streaming_save_leaves_no_final_outputs(tmp_path, monkeypatch):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
        )
        _write_quanti_sheet(
            writer,
            "거래량",
            [[pd.Timestamp("2020-01-01"), 1000, 2000]],
        )

    should_cancel = False
    lock = threading.Lock()
    real_write_sheet_parquet_temp = assets_excel_module._write_sheet_parquet_temp

    def cancelling_write(*args, **kwargs):
        nonlocal should_cancel
        result = real_write_sheet_parquet_temp(*args, **kwargs)
        with lock:
            should_cancel = True
        return result

    def cancel_check() -> bool:
        with lock:
            return should_cancel

    monkeypatch.setattr(assets_excel_module, "_asset_excel_scan_workers", lambda file_count: 1)
    monkeypatch.setattr(assets_excel_module, "_write_sheet_parquet_temp", cancelling_write)

    with pytest.raises(RuntimeError, match="Job cancelled"):
        convert_asset_excels_to_wide_parquet(
            source_dir,
            output_dir,
            progress_callback=lambda message: None,
            cancel_check=cancel_check,
        )

    assert not list(output_dir.glob("*.parquet"))
    assert not (output_dir / "manifest.json").exists()
    assert not any(path.name.startswith(".quanti_parquet_write_") for path in output_dir.iterdir())


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
    assert "close" not in payload["accounts"]
    assert not (output_dir / "stock_price.parquet").exists()


def test_convert_asset_excels_resume_failed_only_skips_completed_outputs(tmp_path):
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
            [[pd.Timestamp("2020-01-02"), 1000, 2000]],
        )

    initial = convert_asset_excels_to_wide_parquet(
        source_dir,
        output_dir,
        selected_files=["source-a.xlsx"],
    )
    completed_output = _output_for_sheet(initial, "종가")["output_file"]

    payload = convert_asset_excels_to_wide_parquet(
        source_dir,
        output_dir,
        resume_failed_only=True,
    )

    assert payload["resume_failed_only"] is True
    assert payload["resume_skipped"] == [
        {
            "file_name": "source-a.xlsx",
            "relative_path": "source-a.xlsx",
            "sheet_name": "종가",
            "output_file": completed_output,
            "reason": "이미 변환 완료",
        }
    ]
    assert payload["sheets_processed"] == 2
    assert _output_for_sheet(payload, "종가")["output_file"] == completed_output
    assert _output_for_sheet(payload, "거래량")["output_file"] == "volume_20200102_20200102.parquet"
    assert _read_output_sheet(payload, output_dir, "종가")["A005930"].tolist() == [100]
    assert _read_output_sheet(payload, output_dir, "거래량")["A000660"].tolist() == [2000]


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

    stock_price = _read_output_sheet(payload, output_dir, "종가", "source-b.xlsx")
    assert stock_price["date"].astype(str).tolist() == ["2020-01-06"]
    assert payload["updated_accounts"] == []
    assert _output_for_sheet(payload, "종가", "source-b.xlsx")["date_segments"] == [
        {"start": "2020-01-06", "end": "2020-01-06"},
    ]
    assert any(path.name.startswith("close_20200103_20200103") for path in output_dir.glob("*.parquet"))
    mapping = pd.read_parquet(output_dir / "code_name_mapping.parquet")
    assert mapping[["code", "name"]].to_dict("records") == [
        {"code": "A035420", "name": "NAVER"},
        {"code": "A051910", "name": "LG화학"},
    ]


def test_convert_asset_excels_defaults_to_replace_without_existing_merge(tmp_path):
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
    )

    stock_price = _read_output_sheet(payload, output_dir, "종가", "source-b.xlsx")
    assert stock_price["date"].astype(str).tolist() == ["2020-01-06"]
    assert payload["write_mode"] == "replace"
    assert payload["updated_accounts"] == []


def test_merge_asset_parquet_outputs_combines_generated_parquet(tmp_path):
    first_source = tmp_path / "first-assets"
    second_source = tmp_path / "second-assets"
    first_output = tmp_path / "first-parquet"
    second_output = tmp_path / "second-parquet"
    merged_output = tmp_path / "merged-parquet"
    first_source.mkdir()
    second_source.mkdir()
    with pd.ExcelWriter(first_source / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-03"), 100, 200]],
        )
    with pd.ExcelWriter(second_source / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-06"), 101, 201]],
            codes=["A035420", "A051910"],
            names=["NAVER", "LG화학"],
        )
    convert_asset_excels_to_wide_parquet(first_source, first_output)
    convert_asset_excels_to_wide_parquet(second_source, second_output)

    payload = merge_asset_parquet_outputs(first_output, second_output, merged_output)

    merged_file = next(path for path in merged_output.glob("*.parquet") if path.name != "code_name_mapping.parquet")
    stock_price = pd.read_parquet(merged_file)
    assert payload["operation"] == "merge_parquet"
    assert payload["accounts_processed"] == 1
    assert stock_price["date"].astype(str).tolist() == ["2020-01-03", "2020-01-06"]
    assert stock_price.columns.tolist() == ["date", "A005930", "A000660", "A035420", "A051910"]
    mapping = pd.read_parquet(merged_output / "code_name_mapping.parquet")
    assert mapping[["code", "name"]].to_dict("records") == [
        {"code": "A000660", "name": "SK하이닉스"},
        {"code": "A005930", "name": "삼성전자"},
        {"code": "A035420", "name": "NAVER"},
        {"code": "A051910", "name": "LG화학"},
    ]


def test_merge_asset_parquet_outputs_rejects_blank_inputs_before_output_created(tmp_path):
    output_dir = tmp_path / "merged"

    with pytest.raises(ValueError, match="base_directory is required"):
        merge_asset_parquet_outputs("", tmp_path / "incoming", output_dir)
    assert not output_dir.exists()

    with pytest.raises(ValueError, match="incoming_directory is required"):
        merge_asset_parquet_outputs(tmp_path / "base", "", output_dir)
    assert not output_dir.exists()


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

    assert preview["sheets"][0]["account_name"] == "close"
    assert preview["sheets"][0]["status"] == "mapped"
    preview_output = _output_for_sheet(preview, "종가")
    assert preview_output["will_update_existing"] is False
    assert "sample_rows" not in preview_output["quality"]
    assert preview["code_name_mapping"]["rows"] == 2
    assert output["manifest_exists"] is True
    assert output["code_name_mapping_exists"] is True
    assert output["parquet_files"] == [preview_output["output_file"]]


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


def test_convert_asset_excels_keeps_overlapping_sheets_separate(tmp_path):
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

    payload = convert_asset_excels_to_wide_parquet(source_dir, output_dir)

    first = _read_output_sheet(payload, output_dir, "종가", "source-a.xlsx")
    second = _read_output_sheet(payload, output_dir, "종가", "source-b.xlsx")
    assert first["A005930"].tolist() == [100]
    assert second["A005930"].tolist() == [999]
    assert payload["conflicts"] == {}


def test_convert_asset_excels_does_not_merge_conflicts_even_if_policy_is_requested(tmp_path):
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

    payload = convert_asset_excels_to_wide_parquet(source_dir, output_dir)

    assert len(payload["outputs"]) == 2
    assert _read_output_sheet(payload, output_dir, "종가", "source-a.xlsx")["A005930"].tolist() == [100]
    assert _read_output_sheet(payload, output_dir, "종가", "source-b.xlsx")["A005930"].tolist() == [999]


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
        assert payload["account_name"] == "tradingHaltFlag"
        assert payload["status"] == "mapped"
        assert payload["columns"] == ["date", "A005930", "A000660"]
        assert payload["rows"][0] == {
            "date": "2020-01-01",
            "A005930": "정상",
            "A000660": "정지",
        }

    result = convert_asset_excels_to_wide_parquet(source_dir, output_dir)
    halt = _read_output_sheet(result, output_dir, "거래정지여부")
    mapping = pd.read_parquet(output_dir / "code_name_mapping.parquet")

    assert _output_for_sheet(result, "거래정지여부")["rows"] == 2
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

    assert _output_for_sheet(payload, "종가", "source-a.xlsx")["date_segments"] == [
        {"start": "2020-01-01", "end": "2020-01-01"},
    ]
    assert _output_for_sheet(payload, "종가", "source-b.xlsx")["date_segments"] == [
        {"start": "2020-01-02", "end": "2020-01-02"},
    ]


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

    assert _output_for_sheet(payload, "종가", "source-a.xlsx")["date_segments"] == [
        {"start": "2020-01-03", "end": "2020-01-03"},
    ]
    assert _output_for_sheet(payload, "종가", "source-b.xlsx")["date_segments"] == [
        {"start": "2020-01-06", "end": "2020-01-06"},
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

    assert _output_for_sheet(payload, "종가", "source-a.xlsx")["date_segments"] == [
        {"start": "2020-01-01", "end": "2020-01-01"},
    ]
    assert _output_for_sheet(payload, "종가", "source-b.xlsx")["date_segments"] == [
        {"start": "2020-01-04", "end": "2020-01-04"},
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

    output = _output_for_sheet(payload, "종가")
    assert output["date_segments"] == [
        {"start": "2020-01-03", "end": "2020-01-06"},
    ]
    assert output["sources"][0]["date_segments"] == [
        {"start": "2020-01-03", "end": "2020-01-06"},
    ]
