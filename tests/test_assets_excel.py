from __future__ import annotations

import hashlib
import shutil
import threading
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import finiq.data.assets_excel as assets_excel_module
import finiq.market_desk.web.app as app_module
from finiq.data.assets_excel import (
    cleanup_duplicate_asset_parquet_outputs,
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
    summaries = [
        item
        for item in payload["sheets"]
        if item["sheet_name"] == sheet_name and (relative_path is None or item.get("relative_path") == relative_path)
    ]
    assert len(summaries) == 1
    output_file = summaries[0]["output_file"]
    matches = [item for item in payload["outputs"].values() if item["output_file"] == output_file]
    assert len(matches) == 1
    return matches[0]


def _expected_output_file(account_name: str, date_start: str, date_end: str, codes: list[str]) -> str:
    companies_hash = hashlib.sha256("".join(codes).encode("utf-8")).hexdigest()
    return f"{account_name}_{date_start.replace('-', '')}_{date_end.replace('-', '')}_{companies_hash}.parquet"


def _read_output_sheet(payload: dict, output_dir, sheet_name: str, relative_path: str | None = None) -> pd.DataFrame:
    item = _output_for_sheet(payload, sheet_name, relative_path)
    return pd.read_parquet(output_dir / item["output_file"])


def _write_account_parquet(output_dir, file_name: str, dates: list[str], values_by_code: dict[str, list[object]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = {"date": [pd.Timestamp(value) for value in dates], **values_by_code}
    frame = pd.DataFrame(rows)
    account_name = assets_excel_module._account_name_from_output_stem(Path(file_name).stem)
    account_mapping = assets_excel_module._account_mapping_for_name(account_name)
    value_frame = frame.loc[:, [column for column in frame.columns if column != "date"]]
    quality = assets_excel_module._account_quality_payload(value_frame)
    assets_excel_module._write_parquet_with_metadata(
        frame,
        output_dir / file_name,
        assets_excel_module._account_footer_metadata(
            account_id=account_mapping["account_id"],
            account_name=account_name,
            date_start=dates[0],
            date_end=dates[-1],
            rows=len(frame),
            columns=len(value_frame.columns),
            quality=quality,
        ),
    )


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


def test_asset_excel_reader_uses_calamine_engine(tmp_path):
    excel_path = tmp_path / "sample.xlsx"
    pd.DataFrame([{"value": 1}]).to_excel(excel_path, index=False, sheet_name="data")

    excel = assets_excel_module._excel_file(excel_path)
    payload = read_asset_excel("sample.xlsx", sheet_name="data", root_directory=tmp_path)

    assert assets_excel_module.EXCEL_ENGINE == "calamine"
    assert excel.engine == "calamine"
    assert payload["rows"] == [{"value": 1}]


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
    assert stock_output["output_file"] == _expected_output_file("close", "2020-01-01", "2020-01-02", ["A005930", "A000660"])
    assert volume_output["output_file"] == _expected_output_file("volume", "2020-01-01", "2020-01-02", ["A005930", "A000660"])
    assert stock_output["account_id"] == "S00001"
    assert stock_output["account_name"] == "close"
    assert stock_output["date_start"] == "2020-01-01"
    assert stock_output["date_end"] == "2020-01-02"
    assert (output_dir / stock_output["output_file"]).exists()
    assert (output_dir / volume_output["output_file"]).exists()
    assert (output_dir / "code_name_mapping.parquet").exists()
    assert not (output_dir / "account_mapping.parquet").exists()
    assert not (output_dir / "manifest.json").exists()
    assert payload["code_name_mapping"]["rows"] == 2
    assert set(stock_output) >= {"account_id", "account_name", "date_start", "date_end", "quality"}
    assert "legacy_account_name" not in stock_output
    assert "sheet_name" not in stock_output
    assert "sources" not in stock_output
    assert "date_segments" not in stock_output
    assert "sample_rows" not in stock_output["quality"]

    stock_price = _read_output_sheet(payload, output_dir, "종가")
    volume = _read_output_sheet(payload, output_dir, "거래량")

    assert stock_price.columns.tolist() == ["date", "A005930", "A000660"]
    assert volume.columns.tolist() == ["date", "A005930", "A000660"]
    assert stock_price["A005930"].tolist() == [100, 101]
    assert volume["A000660"].tolist() == [2000, 2001]
    footer = assets_excel_module._read_account_footer_metadata(output_dir / stock_output["output_file"])
    assert set(footer) == assets_excel_module.REQUIRED_ACCOUNT_METADATA_KEYS
    assert footer["account_id"] == "S00001"
    assert footer["account_name"] == "close"
    assert footer["date_start"] == "2020-01-01"
    assert footer["date_end"] == "2020-01-02"
    mapping = pd.read_parquet(output_dir / "code_name_mapping.parquet")
    assert mapping.columns.tolist() == ["code", "name"]
    assert mapping[["code", "name"]].to_dict("records") == [
        {"code": "A000660", "name": "SK하이닉스"},
        {"code": "A005930", "name": "삼성전자"},
    ]


def test_convert_asset_excels_hashes_ordered_company_list_in_output_name(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    with pd.ExcelWriter(source_dir / "source-a.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 100, 200]],
            codes=["A005930", "A000660"],
            names=["삼성전자", "SK하이닉스"],
        )
    with pd.ExcelWriter(source_dir / "source-b.xlsx") as writer:
        _write_quanti_sheet(
            writer,
            "종가",
            [[pd.Timestamp("2020-01-01"), 300, 400]],
            codes=["A035420", "A051910"],
            names=["NAVER", "LG화학"],
        )

    payload = convert_asset_excels_to_wide_parquet(source_dir, output_dir)

    first_file = _expected_output_file("close", "2020-01-01", "2020-01-01", ["A005930", "A000660"])
    second_file = _expected_output_file("close", "2020-01-01", "2020-01-01", ["A035420", "A051910"])
    assert _output_for_sheet(payload, "종가", "source-a.xlsx")["output_file"] == first_file
    assert _output_for_sheet(payload, "종가", "source-b.xlsx")["output_file"] == second_file
    assert first_file != second_file
    assert not any(output["output_file"].endswith("__2.parquet") for output in payload["outputs"].values())


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
            "sheet_name": "종가",
        }
    ]
    preview = inspect_asset_excel_conversion(source_dir, output_dir, account_mappings=mappings)
    payload = convert_asset_excels_to_wide_parquet(source_dir, output_dir, account_mappings=mappings)

    preview_output = _output_for_sheet(preview, "종가")
    output = _output_for_sheet(payload, "종가")
    assert preview_output["account_id"] == "A90001"
    assert preview_output["account_name"] == "customClose"
    assert output["output_file"] == _expected_output_file("customClose", "2020-01-01", "2020-01-01", ["A005930", "A000660"])
    assert output["account_id"] == "A90001"
    assert output["account_name"] == "customClose"
    assert "account_mapping" not in payload
    assert not (output_dir / "account_mapping.parquet").exists()


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
                    "sheet_name": "종가",
                },
                {
                    "account_id": "A90002",
                    "account_name": "customClose",
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
    assert "sheet_name" not in preview
    assert preview["account_id"] == "S00001"
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
            "target_directory": str(tmp_path / "target"),
            "output_directory": "",
        },
    )
    assert merge_start_response.status_code == 400
    assert merge_start_response.json()["detail"] == "output_directory is required"

    direct_merge_output = tmp_path / "direct-merge-output"
    merge_response = client.post(
        "/api/assets/parquet/merge",
        json={
            "target_directory": "",
            "output_directory": str(direct_merge_output),
        },
    )
    assert merge_response.status_code == 400
    assert merge_response.json()["detail"] == "target_directory is required"
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
    assert any("[저장 1/1]" in line and "계정=close" in line for line in progress_log)
    assert any("코드-종목명 매핑 저장: code_name_mapping.parquet (2행)" in line for line in progress_log)
    assert not any("manifest 저장:" in line for line in progress_log)
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
    assert payload["selected_files"] == ["source-b.xlsx"]
    assert [item["account_name"] for item in payload["outputs"].values()] == ["volume"]
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
    assert payload["sheets_processed"] == 1
    assert _output_for_sheet(payload, "거래량")["output_file"] == _expected_output_file("volume", "2020-01-02", "2020-01-02", ["A005930", "A000660"])
    assert pd.read_parquet(output_dir / completed_output)["A005930"].tolist() == [100]
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
    assert "updated_accounts" not in payload
    assert _output_for_sheet(payload, "종가", "source-b.xlsx")["date_start"] == "2020-01-06"
    assert _output_for_sheet(payload, "종가", "source-b.xlsx")["date_end"] == "2020-01-06"
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
    assert "updated_accounts" not in payload


def test_merge_asset_parquet_outputs_combines_generated_parquet(tmp_path):
    first_source = tmp_path / "first-assets"
    second_source = tmp_path / "second-assets"
    target_output = tmp_path / "target-parquet"
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
            [[pd.Timestamp("2020-01-04"), 101, 201]],
        )
    first_payload = convert_asset_excels_to_wide_parquet(first_source, target_output)
    second_payload = convert_asset_excels_to_wide_parquet(second_source, second_output)
    for path in second_output.glob("*.parquet"):
        if path.name != "code_name_mapping.parquet":
            shutil.copy2(path, target_output / path.name)
    first_file = _output_for_sheet(first_payload, "종가")["output_file"]
    second_file = _output_for_sheet(second_payload, "종가")["output_file"]
    expected_merged_file = _expected_output_file("close", "2020-01-03", "2020-01-04", ["A005930", "A000660"])

    payload = merge_asset_parquet_outputs(
        target_output,
        merged_output,
        selected_files=[first_file, second_file],
    )

    merged_file = next(path for path in merged_output.glob("*.parquet") if path.name != "code_name_mapping.parquet")
    stock_price = pd.read_parquet(merged_file)
    assert payload["operation"] == "merge_parquet"
    assert payload["accounts_processed"] == 1
    assert merged_file.name == expected_merged_file
    assert payload["accounts"]["close"]["output_file"] == expected_merged_file
    assert stock_price["date"].astype(str).tolist() == ["2020-01-03", "2020-01-04"]
    assert stock_price.columns.tolist() == ["date", "A005930", "A000660"]
    mapping = pd.read_parquet(merged_output / "code_name_mapping.parquet")
    assert mapping[["code", "name"]].to_dict("records") == [
        {"code": "A000660", "name": "SK하이닉스"},
        {"code": "A005930", "name": "삼성전자"},
    ]


def test_inspect_parquet_output_reads_footer_metadata(tmp_path):
    output_dir = tmp_path / "parquet"
    _write_account_parquet(
        output_dir,
        "close_20200103_20200104.parquet",
        ["2020-01-03", "2020-01-04"],
        {"A005930": [100, None], "A000660": [200, 201]},
    )

    output = inspect_asset_excel_output(output_dir)
    row = output["outputs"]["close_20200103_20200104"]

    assert row["account_id"] == "S00001"
    assert row["account_name"] == "close"
    assert row["rows"] == 2
    assert row["columns"] == 2
    assert row["quality"]["missing_ratio"] == 0.25
    assert row["quality"]["non_null_cells"] == 3
    assert row["quality"]["total_cells"] == 4
    assert row["date_start"] == "2020-01-03"
    assert row["date_end"] == "2020-01-04"


def test_inspect_parquet_output_ignores_legacy_account_mapping_file(tmp_path):
    output_dir = tmp_path / "parquet"
    _write_account_parquet(
        output_dir,
        "close_20200103_20200104.parquet",
        ["2020-01-03", "2020-01-04"],
        {"A005930": [100, 101]},
    )
    pd.DataFrame(
        [
            {
                "account_id": "S00001",
                "account_name": "close",
                "sheet_name": "종가",
            }
        ]
    ).to_parquet(output_dir / "account_mapping.parquet", index=False)

    output = inspect_asset_excel_output(output_dir)

    assert output["parquet_files"] == ["close_20200103_20200104.parquet"]
    assert output["account_count"] == 1
    assert list(output["outputs"]) == ["close_20200103_20200104"]


def test_inspect_parquet_output_rejects_missing_footer_metadata(tmp_path):
    output_dir = tmp_path / "parquet"
    output_dir.mkdir()
    pd.DataFrame(
        {
            "date": [pd.Timestamp("2020-01-03")],
            "A005930": [100],
        }
    ).to_parquet(output_dir / "close_20200103_20200103.parquet", index=False)

    with pytest.raises(ValueError, match="Missing Quantiwise Parquet footer metadata"):
        inspect_asset_excel_output(output_dir)


def test_inspect_merged_parquet_output_reports_table_metadata(tmp_path):
    target_output = tmp_path / "target-parquet"
    merged_output = tmp_path / "merged-parquet"
    _write_account_parquet(
        target_output,
        "close_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output,
        "close_20200104_20200104.parquet",
        ["2020-01-04"],
        {"A005930": [101]},
    )

    merge_asset_parquet_outputs(
        target_output,
        merged_output,
        selected_files=["close_20200103_20200103.parquet", "close_20200104_20200104.parquet"],
    )

    output = inspect_asset_excel_output(merged_output)
    expected_file = _expected_output_file("close", "2020-01-03", "2020-01-04", ["A005930"])
    expected_stem = Path(expected_file).stem
    row = output["outputs"][expected_stem]

    assert row["output_file"] == expected_file
    assert row["account_id"] == "S00001"
    assert row["account_name"] == "close"
    assert row["rows"] == 2
    assert row["columns"] == 1
    assert row["quality"]["missing_ratio"] == 0
    assert row["quality"]["non_null_cells"] == 2
    assert row["quality"]["total_cells"] == 2
    assert row["date_start"] == "2020-01-03"
    assert row["date_end"] == "2020-01-04"

    preview = read_asset_parquet_preview(
        expected_file,
        output_directory=merged_output,
    )
    assert preview["account_id"] == "S00001"
    assert preview["account_name"] == "close"
    assert preview["date_start"] == "2020-01-03"
    assert preview["date_end"] == "2020-01-04"


def test_merge_asset_parquet_outputs_allows_same_dates_extending_codes(tmp_path):
    target_output = tmp_path / "target-parquet"
    merged_output = tmp_path / "merged-parquet"
    _write_account_parquet(
        target_output,
        "close_20200103_20200104.parquet",
        ["2020-01-03", "2020-01-04"],
        {"A005930": [100, 101]},
    )
    _write_account_parquet(
        target_output,
        "close_20200103_20200104_2.parquet",
        ["2020-01-03", "2020-01-04"],
        {"A000660": [200, 201]},
    )

    payload = merge_asset_parquet_outputs(
        target_output,
        merged_output,
        selected_files=["close_20200103_20200104.parquet", "close_20200103_20200104_2.parquet"],
    )

    expected_file = _expected_output_file("close", "2020-01-03", "2020-01-04", ["A005930", "A000660"])
    stock_price = pd.read_parquet(merged_output / expected_file)
    assert payload["accounts_processed"] == 1
    assert stock_price.columns.tolist() == ["date", "A005930", "A000660"]
    assert stock_price["A005930"].tolist() == [100, 101]
    assert stock_price["A000660"].tolist() == [200, 201]


def test_merge_asset_parquet_outputs_groups_duplicate_suffix_files(tmp_path):
    target_output = tmp_path / "target-parquet"
    merged_output = tmp_path / "merged-parquet"
    _write_account_parquet(
        target_output,
        "close_20200103_20200104.parquet",
        ["2020-01-03", "2020-01-04"],
        {"A005930": [100, 101]},
    )
    _write_account_parquet(
        target_output,
        "close_20200103_20200104__2.parquet",
        ["2020-01-03", "2020-01-04"],
        {"A000660": [200, 201]},
    )

    payload = merge_asset_parquet_outputs(
        target_output,
        merged_output,
        selected_files=["close_20200103_20200104.parquet", "close_20200103_20200104__2.parquet"],
    )

    expected_file = _expected_output_file("close", "2020-01-03", "2020-01-04", ["A005930", "A000660"])
    stock_price = pd.read_parquet(merged_output / expected_file)
    assert payload["accounts_processed"] == 1
    assert sorted(payload["accounts"]) == ["close"]
    assert stock_price.columns.tolist() == ["date", "A005930", "A000660"]


def test_merge_asset_parquet_outputs_accepts_multiple_two_file_account_groups(tmp_path):
    target_output = tmp_path / "target-parquet"
    merged_output = tmp_path / "merged-parquet"
    _write_account_parquet(
        target_output,
        "close_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output,
        "close_20200104_20200104.parquet",
        ["2020-01-04"],
        {"A005930": [101]},
    )
    _write_account_parquet(
        target_output,
        "adjHigh_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [120]},
    )
    _write_account_parquet(
        target_output,
        "adjHigh_20200104_20200104.parquet",
        ["2020-01-04"],
        {"A005930": [121]},
    )

    payload = merge_asset_parquet_outputs(
        target_output,
        merged_output,
        selected_files=[
            "close_20200103_20200103.parquet",
            "close_20200104_20200104.parquet",
            "adjHigh_20200103_20200103.parquet",
            "adjHigh_20200104_20200104.parquet",
        ],
    )

    close_file = _expected_output_file("close", "2020-01-03", "2020-01-04", ["A005930"])
    adj_high_file = _expected_output_file("adjHigh", "2020-01-03", "2020-01-04", ["A005930"])
    close = pd.read_parquet(merged_output / close_file)
    adj_high = pd.read_parquet(merged_output / adj_high_file)
    assert payload["accounts_processed"] == 2
    assert sorted(payload["accounts"]) == ["adjHigh", "close"]
    assert close["A005930"].tolist() == [100, 101]
    assert adj_high["A005930"].tolist() == [120, 121]


def test_merge_asset_parquet_outputs_rejects_cross_account_pair(tmp_path):
    target_output = tmp_path / "target-parquet"
    merged_output = tmp_path / "merged-parquet"
    _write_account_parquet(
        target_output,
        "close_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output,
        "adjHigh_20200104_20200104.parquet",
        ["2020-01-04"],
        {"A005930": [121]},
    )

    with pytest.raises(ValueError, match="exactly 2 files for each account"):
        merge_asset_parquet_outputs(
            target_output,
            merged_output,
            selected_files=["close_20200103_20200103.parquet", "adjHigh_20200104_20200104.parquet"],
        )


def test_merge_asset_parquet_outputs_rejects_partial_rectangle(tmp_path):
    target_output = tmp_path / "target-parquet"
    merged_output = tmp_path / "merged-parquet"
    _write_account_parquet(
        target_output,
        "close_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output,
        "close_20200104_20200104.parquet",
        ["2020-01-04"],
        {"A000660": [201]},
    )

    with pytest.raises(ValueError, match="partially filled table"):
        merge_asset_parquet_outputs(
            target_output,
            merged_output,
            selected_files=["close_20200103_20200103.parquet", "close_20200104_20200104.parquet"],
        )


def test_merge_asset_parquet_outputs_rejects_disconnected_date_ranges(tmp_path):
    target_output = tmp_path / "target-parquet"
    merged_output = tmp_path / "merged-parquet"
    _write_account_parquet(
        target_output,
        "close_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output,
        "close_20200105_20200105.parquet",
        ["2020-01-05"],
        {"A005930": [102]},
    )

    with pytest.raises(ValueError, match="date ranges are not connected"):
        merge_asset_parquet_outputs(
            target_output,
            merged_output,
            selected_files=["close_20200103_20200103.parquet", "close_20200105_20200105.parquet"],
        )


def test_merge_asset_parquet_outputs_reads_only_selected_files_for_same_account(tmp_path):
    target_output = tmp_path / "target-parquet"
    merged_output = tmp_path / "merged-parquet"
    _write_account_parquet(
        target_output,
        "close_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output,
        "close_20200104_20200104.parquet",
        ["2020-01-04"],
        {"A005930": [101]},
    )
    _write_account_parquet(
        target_output,
        "close_20200105_20200105.parquet",
        ["2020-01-05"],
        {"A005930": [102]},
    )

    merge_asset_parquet_outputs(
        target_output,
        merged_output,
        selected_files=["close_20200103_20200103.parquet", "close_20200104_20200104.parquet"],
    )

    expected_file = _expected_output_file("close", "2020-01-03", "2020-01-04", ["A005930"])
    stock_price = pd.read_parquet(merged_output / expected_file)
    assert stock_price["date"].astype(str).tolist() == ["2020-01-03", "2020-01-04"]
    assert stock_price["A005930"].tolist() == [100, 101]


def test_merge_asset_parquet_outputs_reads_only_selected_parquet_files(tmp_path, monkeypatch):
    target_output = tmp_path / "target-parquet"
    merged_output = tmp_path / "merged-parquet"
    _write_account_parquet(
        target_output,
        "close_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output,
        "close_20200104_20200104.parquet",
        ["2020-01-04"],
        {"A005930": [101]},
    )
    _write_account_parquet(
        target_output,
        "adjHigh_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [120]},
    )
    progress_log: list[str] = []
    read_paths: list[str] = []
    real_read_parquet = pd.read_parquet

    def tracked_read_parquet(path, *args, **kwargs):
        read_paths.append(Path(path).name)
        return real_read_parquet(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", tracked_read_parquet)

    payload = merge_asset_parquet_outputs(
        target_output,
        merged_output,
        selected_files=["close_20200103_20200103.parquet", "close_20200104_20200104.parquet"],
        progress_callback=progress_log.append,
    )

    assert payload["selected_files"] == ["close_20200103_20200103.parquet", "close_20200104_20200104.parquet"]
    assert payload["accounts_processed"] == 1
    assert "adjHigh_20200103_20200103.parquet" not in read_paths
    assert read_paths == [
        "close_20200103_20200103.parquet",
        "close_20200104_20200104.parquet",
    ]
    assert progress_log == [
        "Selected merge files: close_20200103_20200103.parquet, close_20200104_20200104.parquet",
        "Merging close...",
    ]


def test_merge_asset_parquet_outputs_same_directory_and_cleanup_after_success(tmp_path):
    target_output = tmp_path / "target-parquet"
    ignored_output = tmp_path / "ignored-parquet"
    _write_account_parquet(
        target_output,
        "close_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output,
        "close_20200104_20200104.parquet",
        ["2020-01-04"],
        {"A005930": [101]},
    )

    payload = merge_asset_parquet_outputs(
        target_output,
        ignored_output,
        selected_files=["close_20200103_20200103.parquet", "close_20200104_20200104.parquet"],
        same_directory=True,
        cleanup_merged_items=True,
    )

    merged_file = target_output / _expected_output_file("close", "2020-01-03", "2020-01-04", ["A005930"])
    archived_first = target_output / "merged" / "close_20200103_20200103.parquet"
    archived_second = target_output / "merged" / "close_20200104_20200104.parquet"
    assert payload["output_directory"] == str(target_output.resolve())
    assert not ignored_output.exists()
    assert merged_file.exists()
    assert archived_first.exists()
    assert archived_second.exists()
    assert not (target_output / "close_20200103_20200103.parquet").exists()
    assert not (target_output / "close_20200104_20200104.parquet").exists()


def test_merge_asset_parquet_outputs_cleanup_keeps_existing_archives(tmp_path):
    target_output = tmp_path / "target-parquet"
    ignored_output = tmp_path / "ignored-parquet"
    _write_account_parquet(
        target_output,
        "close_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output,
        "close_20200104_20200104.parquet",
        ["2020-01-04"],
        {"A005930": [101]},
    )
    _write_account_parquet(
        target_output / "merged",
        "close_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [90]},
    )

    payload = merge_asset_parquet_outputs(
        target_output,
        ignored_output,
        selected_files=["close_20200103_20200103.parquet", "close_20200104_20200104.parquet"],
        same_directory=True,
        cleanup_merged_items=True,
    )

    archived_first = target_output / "merged" / "close_20200103_20200103.parquet"
    archived_first_retry = target_output / "merged" / "close_20200103_20200103__2.parquet"
    archived_second = target_output / "merged" / "close_20200104_20200104.parquet"
    assert archived_first.exists()
    assert pd.read_parquet(archived_first)["A005930"].tolist() == [90]
    assert archived_first_retry.exists()
    assert archived_second.exists()
    assert payload["moved_files"][0]["to"] == str(archived_first_retry)


def test_cleanup_duplicate_asset_parquet_outputs_deletes_identical_suffix_files(tmp_path):
    target_output = tmp_path / "target-parquet"
    canonical_file = "close_20200103_20200103.parquet"
    duplicate_file = "close_20200103_20200103__2.parquet"
    mismatched_file = "close_20200103_20200103__3.parquet"
    _write_account_parquet(
        target_output / "merged",
        canonical_file,
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output / "merged",
        duplicate_file,
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output / "merged",
        mismatched_file,
        ["2020-01-03"],
        {"A005930": [101]},
    )

    dry_run = cleanup_duplicate_asset_parquet_outputs(target_output, dry_run=True, scan_recursive=True)

    assert dry_run["deletion_candidate_count"] == 1
    assert dry_run["deletion_candidates"][0]["file_name"] == duplicate_file
    assert any(item["file_name"] == mismatched_file for item in dry_run["mismatched_duplicates"])
    assert (target_output / "merged" / duplicate_file).exists()

    payload = cleanup_duplicate_asset_parquet_outputs(
        target_output,
        dry_run=False,
        delete_confirmed=True,
        delete_confirmation_text="확인했습니다.",
        scan_recursive=True,
    )

    assert payload["deleted_count"] == 1
    assert not (target_output / "merged" / duplicate_file).exists()
    assert (target_output / "merged" / canonical_file).exists()
    assert (target_output / "merged" / mismatched_file).exists()


def test_cleanup_duplicate_asset_parquet_outputs_does_not_scan_subfolders_by_default(tmp_path):
    target_output = tmp_path / "target-parquet"
    _write_account_parquet(
        target_output / "nested" / "merged",
        "close_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output / "nested" / "merged",
        "close_20200103_20200103__2.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )

    dry_run = cleanup_duplicate_asset_parquet_outputs(target_output, dry_run=True)

    assert dry_run["scan_recursive"] is False
    assert dry_run["deletion_candidate_count"] == 0

    recursive_dry_run = cleanup_duplicate_asset_parquet_outputs(target_output, dry_run=True, scan_recursive=True)
    assert recursive_dry_run["scan_recursive"] is True
    assert recursive_dry_run["deletion_candidate_count"] == 1


def test_cleanup_duplicate_asset_parquet_outputs_deletes_strict_subset_across_date_ranges(tmp_path):
    target_output = tmp_path / "target-parquet"
    subset_file = "close_20200103_20200103.parquet"
    superset_file = "close_20200103_20200104.parquet"
    other_account_file = "open_20200103_20200104.parquet"
    _write_account_parquet(
        target_output,
        subset_file,
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output,
        superset_file,
        ["2020-01-03", "2020-01-04"],
        {"A005930": [100, 101], "A000660": [200, 201]},
    )
    _write_account_parquet(
        target_output,
        other_account_file,
        ["2020-01-03", "2020-01-04"],
        {"A005930": [100, 101], "A000660": [200, 201]},
    )

    dry_run = cleanup_duplicate_asset_parquet_outputs(target_output, dry_run=True)

    assert dry_run["deletion_candidate_count"] == 1
    assert dry_run["deletion_candidates"][0]["file_name"] == subset_file
    assert dry_run["deletion_candidates"][0]["canonical_file"] == superset_file
    assert dry_run["deletion_candidates"][0]["reason"] == "더 완전한 같은 계정 Parquet에 포함됨"
    assert dry_run["deletion_candidates"][0]["account_name"] == "close"

    payload = cleanup_duplicate_asset_parquet_outputs(
        target_output,
        dry_run=False,
        delete_confirmed=True,
        delete_confirmation_text="확인했습니다.",
    )

    assert payload["deleted_count"] == 1
    assert not (target_output / subset_file).exists()
    assert (target_output / superset_file).exists()
    assert (target_output / other_account_file).exists()


def test_cleanup_duplicate_asset_parquet_outputs_deletes_strict_subset_across_codes(tmp_path):
    target_output = tmp_path / "target-parquet"
    subset_file = f"close_20200103_20200104_{'a' * 64}.parquet"
    superset_file = f"close_20200103_20200104_{'b' * 64}.parquet"
    _write_account_parquet(
        target_output,
        subset_file,
        ["2020-01-03", "2020-01-04"],
        {"A005930": [100, 101]},
    )
    _write_account_parquet(
        target_output,
        superset_file,
        ["2020-01-03", "2020-01-04"],
        {"A005930": [100, 101], "A000660": [200, 201]},
    )

    dry_run = cleanup_duplicate_asset_parquet_outputs(target_output, dry_run=True)

    assert dry_run["deletion_candidate_count"] == 1
    assert dry_run["deletion_candidates"][0]["file_name"] == subset_file
    assert dry_run["deletion_candidates"][0]["canonical_file"] == superset_file
    assert dry_run["deletion_candidates"][0]["extra_columns"] == "1"


def test_cleanup_duplicate_asset_parquet_outputs_keeps_overlapping_conflicts(tmp_path):
    target_output = tmp_path / "target-parquet"
    first_file = "close_20200103_20200103.parquet"
    second_file = "close_20200103_20200104.parquet"
    _write_account_parquet(
        target_output,
        first_file,
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output,
        second_file,
        ["2020-01-03", "2020-01-04"],
        {"A005930": [999, 101]},
    )

    dry_run = cleanup_duplicate_asset_parquet_outputs(target_output, dry_run=True)

    assert dry_run["deletion_candidate_count"] == 0
    assert any(int(item["conflicting_values"]) == 1 for item in dry_run["mismatched_duplicates"])
    assert (target_output / first_file).exists()
    assert (target_output / second_file).exists()


def test_cleanup_duplicate_asset_parquet_outputs_requires_delete_confirmation(tmp_path):
    target_output = tmp_path / "target-parquet"
    _write_account_parquet(
        target_output,
        "close_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output,
        "close_20200103_20200103__2.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )

    with pytest.raises(ValueError, match='"확인했습니다." 입력과 삭제 허가가 필요합니다'):
        cleanup_duplicate_asset_parquet_outputs(target_output, dry_run=False)

    assert (target_output / "close_20200103_20200103__2.parquet").exists()


def test_merge_asset_parquet_outputs_same_directory_keeps_result_when_name_matches_source(tmp_path):
    target_output = tmp_path / "target-parquet"
    ignored_output = tmp_path / "ignored-parquet"
    expected_file = _expected_output_file("close", "2020-01-03", "2020-01-04", ["A005930", "A000660"])
    duplicate_file = f"{Path(expected_file).stem}__2.parquet"
    _write_account_parquet(
        target_output,
        expected_file,
        ["2020-01-03", "2020-01-04"],
        {"A005930": [100, 101], "A000660": [200, 201]},
    )
    _write_account_parquet(
        target_output,
        duplicate_file,
        ["2020-01-03", "2020-01-04"],
        {"A005930": [None, None], "A000660": [None, None]},
    )

    merge_asset_parquet_outputs(
        target_output,
        ignored_output,
        selected_files=[expected_file, duplicate_file],
        same_directory=True,
        cleanup_merged_items=True,
    )

    stock_price = pd.read_parquet(target_output / expected_file)
    assert stock_price.columns.tolist() == ["date", "A005930", "A000660"]
    assert (target_output / "merged" / expected_file).exists()
    assert (target_output / "merged" / duplicate_file).exists()


def test_merge_asset_parquet_outputs_cleanup_waits_for_success(tmp_path):
    target_output = tmp_path / "target-parquet"
    merged_output = tmp_path / "merged-parquet"
    _write_account_parquet(
        target_output,
        "close_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output,
        "close_20200104_20200104.parquet",
        ["2020-01-04"],
        {"A000660": [201]},
    )

    with pytest.raises(ValueError, match="partially filled table"):
        merge_asset_parquet_outputs(
            target_output,
            merged_output,
            selected_files=["close_20200103_20200103.parquet", "close_20200104_20200104.parquet"],
            cleanup_merged_items=True,
        )

    assert not (target_output / "merged").exists()
    assert (target_output / "close_20200103_20200103.parquet").exists()
    assert (target_output / "close_20200104_20200104.parquet").exists()


def test_merge_asset_parquet_outputs_cleans_temp_outputs_on_cancel(tmp_path):
    target_output = tmp_path / "target-parquet"
    merged_output = tmp_path / "merged-parquet"
    _write_account_parquet(
        target_output,
        "close_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [100]},
    )
    _write_account_parquet(
        target_output,
        "close_20200104_20200104.parquet",
        ["2020-01-04"],
        {"A005930": [101]},
    )
    _write_account_parquet(
        target_output,
        "volume_20200103_20200103.parquet",
        ["2020-01-03"],
        {"A005930": [1000]},
    )
    _write_account_parquet(
        target_output,
        "volume_20200104_20200104.parquet",
        ["2020-01-04"],
        {"A005930": [1001]},
    )
    should_cancel = False

    def progress_callback(message: str) -> None:
        nonlocal should_cancel
        if message == "Merging close...":
            should_cancel = True

    with pytest.raises(RuntimeError, match="Job cancelled"):
        merge_asset_parquet_outputs(
            target_output,
            merged_output,
            selected_files=[
                "close_20200103_20200103.parquet",
                "close_20200104_20200104.parquet",
                "volume_20200103_20200103.parquet",
                "volume_20200104_20200104.parquet",
            ],
            progress_callback=progress_callback,
            cancel_check=lambda: should_cancel,
        )

    assert not list(merged_output.glob("*.parquet"))
    assert not any(path.name.startswith(".quanti_parquet_merge_") for path in merged_output.iterdir())
    assert not (target_output / "merged").exists()
    assert (target_output / "close_20200103_20200103.parquet").exists()
    assert (target_output / "close_20200104_20200104.parquet").exists()


def test_merge_asset_parquet_outputs_rejects_blank_inputs_before_output_created(tmp_path):
    output_dir = tmp_path / "merged"

    with pytest.raises(ValueError, match="target_directory is required"):
        merge_asset_parquet_outputs("", output_dir)
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
    assert output["code_name_mapping_exists"] is True
    assert output["parquet_files"] == [preview_output["output_file"]]


def test_read_asset_parquet_preview_derives_account_from_duplicate_suffix(tmp_path):
    output_dir = tmp_path / "merged"
    _write_account_parquet(
        output_dir,
        "close_20200103_20200104__2.parquet",
        ["2020-01-03", "2020-01-04"],
        {"A005930": [100, 101]},
    )

    payload = read_asset_parquet_preview(
        "close_20200103_20200104__2.parquet",
        output_directory=output_dir,
    )

    assert payload["account_name"] == "close"
    assert payload["account_id"] == "S00001"
    assert "sheet_name" not in payload


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

    assert _output_for_sheet(payload, "종가", "source-a.xlsx")["date_start"] == "2020-01-01"
    assert _output_for_sheet(payload, "종가", "source-a.xlsx")["date_end"] == "2020-01-01"
    assert _output_for_sheet(payload, "종가", "source-b.xlsx")["date_start"] == "2020-01-02"
    assert _output_for_sheet(payload, "종가", "source-b.xlsx")["date_end"] == "2020-01-02"


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

    assert _output_for_sheet(payload, "종가", "source-a.xlsx")["date_start"] == "2020-01-03"
    assert _output_for_sheet(payload, "종가", "source-a.xlsx")["date_end"] == "2020-01-03"
    assert _output_for_sheet(payload, "종가", "source-b.xlsx")["date_start"] == "2020-01-06"
    assert _output_for_sheet(payload, "종가", "source-b.xlsx")["date_end"] == "2020-01-06"


def test_convert_asset_excels_stores_date_range_for_disjoint_outputs(tmp_path):
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

    assert _output_for_sheet(payload, "종가", "source-a.xlsx")["date_start"] == "2020-01-01"
    assert _output_for_sheet(payload, "종가", "source-a.xlsx")["date_end"] == "2020-01-01"
    assert _output_for_sheet(payload, "종가", "source-b.xlsx")["date_start"] == "2020-01-04"
    assert _output_for_sheet(payload, "종가", "source-b.xlsx")["date_end"] == "2020-01-04"


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
    assert output["date_start"] == "2020-01-03"
    assert output["date_end"] == "2020-01-06"
    assert "date_segments" not in output
    assert "sources" not in output
