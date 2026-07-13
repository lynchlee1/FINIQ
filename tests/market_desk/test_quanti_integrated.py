from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from finiq.market_desk.analytics import quanti_integrated


def test_convert_quanti_excel_propagates_workbook_read_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_workbook_read(path: str | Path) -> None:
        raise ValueError("broken workbook")

    source = tmp_path / "broken.xlsx"
    source.write_bytes(b"not-an-excel-workbook")
    output = tmp_path / "output"
    monkeypatch.setattr(quanti_integrated, "_excel_file", fail_workbook_read)

    with pytest.raises(ValueError, match="broken workbook"):
        quanti_integrated.convert_quanti_excel_to_parquet(source, output)

    assert not (output / "manifest.json").exists()


def test_merge_quanti_datasets_rejects_missing_date_column(tmp_path: Path) -> None:
    input_dir = tmp_path / "input" / "by_item"
    input_dir.mkdir(parents=True)
    pd.DataFrame({"A005930": [1.0]}).to_parquet(input_dir / "SAMPLE.parquet")
    output = tmp_path / "output"

    with pytest.raises(ValueError, match="missing date column"):
        quanti_integrated.merge_quanti_by_item_datasets([input_dir.parent], output)

    assert not (output / "manifest.json").exists()


def test_merge_quanti_datasets_rejects_missing_input_directory(tmp_path: Path) -> None:
    output = tmp_path / "output"

    with pytest.raises(ValueError, match="input directory does not exist"):
        quanti_integrated.merge_quanti_by_item_datasets(
            [tmp_path / "missing"], output
        )

    assert not (output / "manifest.json").exists()
