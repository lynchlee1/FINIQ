"""Core engine for converting and merging Quantiwise datasets into wide-item Parquet."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ProgressCallback = Callable[[str], None]
EXCEL_ENGINE = "calamine"


def _emit(callback: ProgressCallback | None, message: str) -> None:
    if callback:
        callback(message)


def _excel_file(path: str | Path) -> pd.ExcelFile:
    return pd.ExcelFile(path, engine=EXCEL_ENGINE)


def _read_excel(path: str | Path | pd.ExcelFile, **kwargs: Any) -> pd.DataFrame:
    if isinstance(path, pd.ExcelFile):
        return pd.read_excel(path, **kwargs)
    return pd.read_excel(path, engine=EXCEL_ENGINE, **kwargs)


def convert_quanti_excel_to_parquet(
    source_path: str | Path,
    output_dir: str | Path,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Convert Quantiwise Excel files to wide-item Parquet files.

    Source path can be a single .xlsx file or a directory containing .xlsx files.
    Each sheet in the Excel files should be named after an item code (e.g., S100300).
    The sheets are expected to have dates in the first column and stock codes as column headers.
    """
    source = Path(source_path).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    by_item_dir = output / "by_item"
    by_item_dir.mkdir(parents=True, exist_ok=True)

    xlsx_files = []
    if source.is_file():
        if source.suffix.lower() == ".xlsx":
            xlsx_files.append(source)
    elif source.is_dir():
        xlsx_files.extend(sorted(source.glob("*.xlsx")))

    if not xlsx_files:
        msg = f"No .xlsx files found in {source}"
        raise ValueError(msg)

    item_files: dict[str, list[Path]] = {}
    _emit(progress_callback, f"Found {len(xlsx_files)} Excel files. Scanning sheets...")

    for xlsx_path in xlsx_files:
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        excel = _excel_file(xlsx_path)
        for sheet_name in excel.sheet_names:
            if cancel_check and cancel_check():
                raise RuntimeError("Job cancelled")
            item_code = str(sheet_name).strip().upper()
            if not item_code:
                raise ValueError(f"Excel sheet name is empty: {xlsx_path}")
            item_files.setdefault(item_code, []).append(xlsx_path)

    total_items = len(item_files)
    _emit(progress_callback, f"Identified {total_items} unique items across files.")

    results = []
    for index, (item_code, paths) in enumerate(item_files.items(), start=1):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        _emit(progress_callback, f"[{index}/{total_items}] Processing {item_code}...")
        item_df = pd.DataFrame()

        for xlsx_path in paths:
            if cancel_check and cancel_check():
                raise RuntimeError("Job cancelled")
            df = _read_excel(xlsx_path, sheet_name=item_code, index_col=0)
            df.index.name = "date"
            df.index = pd.to_datetime(df.index).date
            item_df = pd.concat([item_df, df])

        if item_df.empty:
            raise ValueError(f"Excel sheet contains no rows: {item_code}")

        # Merge duplicate dates by taking the last value (usually most recent or correction)
        item_df = item_df[~item_df.index.duplicated(keep="last")].sort_index()

        # Save to parquet
        parquet_path = by_item_dir / f"{item_code}.parquet"
        # Reset index to make 'date' a column
        save_df = item_df.reset_index()
        # Convert all stock code columns to float/appropriate type if needed
        # But mostly keeping them as is is fine for wide format.
        save_df.to_parquet(parquet_path, index=False, compression="snappy")
        results.append({"item_code": item_code, "path": str(parquet_path), "rows": len(item_df)})

    # Generate basic manifest
    manifest = {
        "format": "finiq_quanti_integrated_manifest_v1",
        "created_at": datetime.now().isoformat(),
        "source": str(source),
        "items": {r["item_code"]: {"rows": r["rows"]} for r in results},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "status": "completed",
        "items_processed": len(results),
        "output_dir": str(output),
    }


def merge_quanti_by_item_datasets(
    input_dirs: Iterable[str | Path],
    output_dir: str | Path,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Merge multiple by_item Parquet datasets into one."""
    inputs = [Path(p).expanduser().resolve() for p in input_dirs]
    output = Path(output_dir).expanduser().resolve()
    output_by_item = output / "by_item"
    output_by_item.mkdir(parents=True, exist_ok=True)

    item_map: dict[str, list[Path]] = {}
    for input_dir in inputs:
        by_item = input_dir if input_dir.name == "by_item" else input_dir / "by_item"
        if not by_item.is_dir():
            raise ValueError(f"Quantiwise input directory does not exist: {by_item}")

        for p in by_item.glob("*.parquet"):
            item_code = p.stem.upper()
            item_map.setdefault(item_code, []).append(p)

    total_items = len(item_map)
    _emit(progress_callback, f"Merging {total_items} items from {len(inputs)} datasets.")

    merged_items = []
    for index, (item_code, paths) in enumerate(item_map.items(), start=1):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        _emit(progress_callback, f"[{index}/{total_items}] Merging {item_code}...")
        combined_df = pd.DataFrame()
        for p in paths:
            if cancel_check and cancel_check():
                raise RuntimeError("Job cancelled")
            df = pd.read_parquet(p)
            if "date" not in df.columns:
                raise ValueError(f"Parquet input is missing date column: {p}")
            df = df.set_index("date")
            combined_df = pd.concat([combined_df, df])

        if combined_df.empty:
            raise ValueError(f"Parquet inputs contain no rows: {item_code}")

        # Resolve overlaps/duplicates
        # Sort and take last for duplicate index/column pairs if any,
        # but wide format might have different columns in different datasets.
        # We need to merge columns too.
        combined_df = combined_df.groupby(combined_df.index).last().sort_index()

        parquet_path = output_by_item / f"{item_code}.parquet"
        combined_df.reset_index().to_parquet(parquet_path, index=False, compression="snappy")
        merged_items.append({"item_code": item_code, "rows": len(combined_df)})

    manifest = {
        "format": "finiq_quanti_integrated_manifest_v1",
        "created_at": datetime.now().isoformat(),
        "inputs": [str(p) for p in inputs],
        "items": {m["item_code"]: {"rows": m["rows"]} for m in merged_items},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "status": "completed",
        "items_merged": len(merged_items),
        "output_dir": str(output),
    }
