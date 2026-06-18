"""Excel readers for Quantiwise Excel files stored under project resources."""

from __future__ import annotations

import math
import os
import re
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
import hashlib
from numbers import Number
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from finiq.config import QUANTIWISE_EXCEL_DIR, RESOURCES_DIR

EXCEL_SUFFIXES = {".xlsx", ".xlsm"}
EXCEL_ENGINE = "calamine"
DEFAULT_ASSET_PARQUET_DIR = RESOURCES_DIR / "assets_merged"
CODE_NAME_MAPPING_FILE = "code_name_mapping.parquet"
ACCOUNT_MAPPING_FILE = "account_mapping.parquet"
NON_ACCOUNT_PARQUET_FILES = {CODE_NAME_MAPPING_FILE, ACCOUNT_MAPPING_FILE}
ASSET_PARQUET_DELETE_CONFIRMATION_TEXT = "확인했습니다."
REQUIRED_ACCOUNT_METADATA_KEYS = {
    "account_id",
    "account_name",
    "date_start",
    "date_end",
    "rows",
    "columns",
    "non_null_cells",
    "total_cells",
    "missing_ratio",
}
ProgressCallback = Callable[[str], None]
SourceInfo = dict[str, Any]
CodeNameMapping = dict[str, str]
AccountMapping = dict[str, str]
AccountMappingInput = Mapping[str, Any]


def _excel_file(path: str | Path) -> pd.ExcelFile:
    return pd.ExcelFile(path, engine=EXCEL_ENGINE)


def _read_excel(xlsx_path: str | Path | pd.ExcelFile, **kwargs: Any) -> pd.DataFrame:
    if isinstance(xlsx_path, pd.ExcelFile):
        return pd.read_excel(xlsx_path, **kwargs)
    return pd.read_excel(xlsx_path, engine=EXCEL_ENGINE, **kwargs)

SHEET_ACCOUNT_KEYS = {
    "종가": "close",
    "시가": "open",
    "고가": "high",
    "저가": "low",
    "수정종가": "adjustedClose",
    "수정시가": "adjustedOpen",
    "수정고가": "adjustedHigh",
    "수정저가": "adjustedLow",
    "거래량": "volume",
    "거래량(NXT)": "nxtVolume",
    "거래대금": "tradingValue",
    "거래대금(NXT)": "nxtTradingValue",
    "저가(NXT)": "nxtLow",
    "고가(NXT)": "nxtHigh",
    "시가(NXT)": "nxtOpen",
    "종가(NXT)": "nxtClose",
    "거래정지사유": "tradingHaltReason",
    "거래정지여부": "tradingHaltFlag",
    "거래정지구분": "tradingHaltCategory",
    "관리감리구분": "managementSupervisionCategory",
    "지수산정주식수": "indexConstituentShares",
    "최대주주명": "majorShareholderName",
    "최대주주보유보통주주식수": "majorShareholderCommonShares",
    "최대주주보유보통주지분율": "majorShareholderCommonOwnershipRatio",
    "대차거래잔고수량": "stockLendingBalanceVolume",
    "대차거래상환량": "stockLendingRepaymentVolume",
    "대차거래체결량": "stockLendingTransactionVolume",
    "차입공매도잔고수량": "borrowedShortSellingBalanceVolume",
    "차입공매도수량": "borrowedShortSellingVolume",
}

ACCOUNT_REGISTRY = {
    account_name: {
        "account_id": f"S{index:05d}",
        "account_name": account_name,
        "sheet_name": sheet_name,
    }
    for index, (sheet_name, account_name) in enumerate(SHEET_ACCOUNT_KEYS.items(), start=1)
}


def default_account_mappings() -> list[AccountMapping]:
    return [dict(mapping) for mapping in ACCOUNT_REGISTRY.values()]


def _normalize_account_mappings(account_mappings: list[AccountMappingInput] | None = None) -> list[AccountMapping]:
    if account_mappings is None:
        return default_account_mappings()

    rows: list[AccountMapping] = []
    seen_sheets: set[str] = set()
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for index, mapping in enumerate(account_mappings, start=1):
        sheet_name = _normalize_label(mapping.get("sheet_name"))
        account_name = _normalize_label(mapping.get("account_name"))
        account_id = _normalize_label(mapping.get("account_id"))
        if not sheet_name:
            raise ValueError(f"account_mappings[{index}].sheet_name is required")
        if not account_id:
            raise ValueError(f"account_mappings[{index}].account_id is required")
        if not account_name:
            raise ValueError(f"account_mappings[{index}].account_name is required")
        if "_" in account_id:
            raise ValueError(f"account_mappings[{index}].account_id cannot contain underscore")
        if "_" in account_name:
            raise ValueError(f"account_mappings[{index}].account_name cannot contain underscore")
        if sheet_name in seen_sheets:
            raise ValueError(f"Duplicate account mapping sheet_name: {sheet_name}")
        if account_id in seen_ids:
            raise ValueError(f"Duplicate account mapping account_id: {account_id}")
        if account_name in seen_names:
            raise ValueError(f"Duplicate account mapping account_name: {account_name}")
        seen_sheets.add(sheet_name)
        seen_ids.add(account_id)
        seen_names.add(account_name)
        rows.append(
            {
                "account_id": account_id,
                "account_name": account_name,
                "sheet_name": sheet_name,
            }
        )
    return rows


def _account_mapping_by_sheet(account_mappings: list[AccountMappingInput] | None = None) -> dict[str, AccountMapping]:
    return {
        mapping["sheet_name"]: mapping
        for mapping in _normalize_account_mappings(account_mappings)
    }


def _account_mapping_by_name(account_mappings: list[AccountMappingInput] | None = None) -> dict[str, AccountMapping]:
    return {
        mapping["account_name"]: mapping
        for mapping in _normalize_account_mappings(account_mappings)
    }


def _resolve_asset_excel_path(file_name: str | Path, root_directory: str | Path = QUANTIWISE_EXCEL_DIR) -> Path:
    root = Path(root_directory).expanduser().resolve()
    requested = Path(file_name)
    target = (root / requested).resolve() if not requested.is_absolute() else requested.resolve()

    if target != root and root not in target.parents:
        msg = f"Excel file must be under Quantiwise directory: {file_name}"
        raise ValueError(msg)
    if target.suffix.lower() not in EXCEL_SUFFIXES:
        msg = f"Unsupported Excel file type: {target.suffix}"
        raise ValueError(msg)
    if not target.exists():
        msg = f"Excel file not found: {target}"
        raise FileNotFoundError(msg)
    if not target.is_file():
        msg = f"Excel path is not a file: {target}"
        raise IsADirectoryError(msg)
    return target


def _emit(callback: ProgressCallback | None, message: str) -> None:
    if callback:
        callback(message)


def _date_range_label(index: pd.Index) -> str:
    if len(index) == 0:
        return "-"
    return f"{index.min().isoformat()}~{index.max().isoformat()}"


def _safe_output_token(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).strip()
    chars = [
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in normalized
    ]
    token = "_".join("".join(chars).split("_"))
    return token or "sheet"


def _compact_date(value: str) -> str:
    return str(value or "").replace("-", "") or "nodate"


def _company_list_hash(company_codes: Iterable[object]) -> str:
    company_text = "".join(_normalize_label(company_code) for company_code in company_codes)
    return hashlib.sha256(company_text.encode("utf-8")).hexdigest()


def _sheet_output_stem(
    account_name: str,
    date_start: str,
    date_end: str,
    company_codes: Iterable[object],
) -> str:
    return "_".join(
        [
            _safe_output_token(account_name),
            _compact_date(date_start),
            _compact_date(date_end),
            _company_list_hash(company_codes),
        ]
    )


def _normalize_label(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return unicodedata.normalize("NFC", str(value or "")).strip()


def _account_name_for_sheet(sheet_name: str, account_mappings: list[AccountMappingInput] | None = None) -> str | None:
    mapping = _account_mapping_by_sheet(account_mappings).get(_normalize_label(sheet_name))
    return mapping["account_name"] if mapping else None


def _account_mapping_for_name(
    account_name: str,
    account_mappings: list[AccountMappingInput] | None = None,
) -> AccountMapping:
    return _account_mapping_by_name(account_mappings).get(
        account_name,
        {
            "account_id": "",
            "account_name": account_name,
            "sheet_name": "",
        },
    )


def list_asset_excel_files(root_directory: str | Path = QUANTIWISE_EXCEL_DIR) -> list[dict[str, Any]]:
    """Return Excel files found below *root_directory*."""
    root = Path(root_directory).expanduser().resolve()
    if not root.is_dir():
        return []

    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in EXCEL_SUFFIXES or not path.is_file():
            continue
        files.append(
            {
                "file_name": path.name,
                "relative_path": str(path.relative_to(root)),
                "stem": path.stem,
                "size_bytes": path.stat().st_size,
            }
        )
    return files


def _selected_asset_excel_paths(
    root_directory: str | Path,
    selected_files: list[str] | None = None,
) -> list[Path]:
    root = Path(root_directory).expanduser().resolve()
    if selected_files:
        return [
            _resolve_asset_excel_path(file_name, root_directory=root)
            for file_name in selected_files
        ]
    return [
        file_path
        for file_path in sorted(root.rglob("*"))
        if file_path.is_file() and file_path.suffix.lower() in EXCEL_SUFFIXES
    ]


def _string_metadata(metadata: Mapping[str, Any]) -> dict[bytes, bytes]:
    return {
        str(key).encode("utf-8"): str(value).encode("utf-8")
        for key, value in metadata.items()
    }


def _write_parquet_with_metadata(frame: pd.DataFrame, path: Path, metadata: Mapping[str, Any]) -> None:
    table = pa.Table.from_pandas(frame, preserve_index=False)
    existing_metadata = dict(table.schema.metadata or {})
    table = table.replace_schema_metadata({**existing_metadata, **_string_metadata(metadata)})
    pq.write_table(table, path, compression="snappy")


def _account_footer_metadata(
    *,
    account_id: str,
    account_name: str,
    date_start: str,
    date_end: str,
    rows: int,
    columns: int,
    quality: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "account_id": account_id,
        "account_name": account_name,
        "date_start": date_start,
        "date_end": date_end,
        "rows": int(rows),
        "columns": int(columns),
        "non_null_cells": int(quality.get("non_null_cells") or 0),
        "total_cells": int(quality.get("total_cells") or 0),
        "missing_ratio": float(quality.get("missing_ratio") or 0),
    }


def _read_account_footer_metadata(path: Path) -> dict[str, str]:
    raw_metadata = pq.read_metadata(path).metadata or {}
    metadata = {
        key.decode("utf-8"): value.decode("utf-8")
        for key, value in raw_metadata.items()
        if key.decode("utf-8") in REQUIRED_ACCOUNT_METADATA_KEYS
    }
    missing = sorted(REQUIRED_ACCOUNT_METADATA_KEYS - set(metadata))
    if missing:
        raise ValueError(f"Missing Quantiwise Parquet footer metadata in {path.name}: {', '.join(missing)}")
    return metadata


def _account_output_payload(path: Path) -> dict[str, Any]:
    metadata = _read_account_footer_metadata(path)
    return {
        "path": str(path),
        "output_file": path.name,
        "account_id": metadata["account_id"],
        "account_name": metadata["account_name"],
        "rows": int(metadata["rows"]),
        "columns": int(metadata["columns"]),
        "date_start": metadata["date_start"],
        "date_end": metadata["date_end"],
        "quality": {
            "non_null_cells": int(metadata["non_null_cells"]),
            "total_cells": int(metadata["total_cells"]),
            "missing_ratio": float(metadata["missing_ratio"]),
        },
    }


def inspect_asset_excel_output(output_directory: str | Path = DEFAULT_ASSET_PARQUET_DIR) -> dict[str, Any]:
    output = Path(output_directory).expanduser().resolve()
    parquet_files = [
        path
        for path in sorted(output.glob("*.parquet")) if path.name not in NON_ACCOUNT_PARQUET_FILES
    ] if output.is_dir() else []
    code_name_mapping_path = output / CODE_NAME_MAPPING_FILE
    output_rows = {
        path.stem: _account_output_payload(path)
        for path in parquet_files
    }
    return {
        "output_directory": str(output),
        "exists": output.exists(),
        "parquet_files": [path.name for path in parquet_files],
        "account_count": len(parquet_files),
        "code_name_mapping_path": str(code_name_mapping_path),
        "code_name_mapping_exists": code_name_mapping_path.exists(),
        "code_name_mapping_rows": len(pd.read_parquet(code_name_mapping_path)) if code_name_mapping_path.exists() else 0,
        "outputs": output_rows,
    }


def _resolve_asset_parquet_path(file_name: str | Path, output_directory: str | Path = DEFAULT_ASSET_PARQUET_DIR) -> Path:
    root = Path(output_directory).expanduser().resolve()
    requested = Path(file_name)
    target = (root / requested).resolve() if not requested.is_absolute() else requested.resolve()

    if target != root and root not in target.parents:
        msg = f"Parquet file must be under data path: {file_name}"
        raise ValueError(msg)
    if target.suffix.lower() != ".parquet":
        msg = f"Unsupported Parquet file type: {target.suffix}"
        raise ValueError(msg)
    if target.name in NON_ACCOUNT_PARQUET_FILES:
        msg = f"Unsupported Quantiwise result preview file: {target.name}"
        raise ValueError(msg)
    if not target.exists():
        msg = f"Parquet file not found: {target}"
        raise FileNotFoundError(msg)
    if not target.is_file():
        msg = f"Parquet path is not a file: {target}"
        raise IsADirectoryError(msg)
    return target


def read_asset_parquet_preview(
    file_name: str | Path,
    *,
    output_directory: str | Path = DEFAULT_ASSET_PARQUET_DIR,
    row_limit: int | None = 20,
    column_limit: int | None = 12,
) -> dict[str, Any]:
    """Read one generated Quantiwise Sheet Parquet as JSON-friendly preview rows."""
    target = _resolve_asset_parquet_path(file_name, output_directory=output_directory)
    output = Path(output_directory).expanduser().resolve()
    frame = pd.read_parquet(target)
    columns = [str(column) for column in frame.columns]
    frame.columns = columns

    preview_columns = columns[: max(1, int(column_limit))] if column_limit is not None else columns
    preview = frame.loc[:, [column for column in preview_columns if column in frame.columns]]
    if row_limit is not None:
        preview = preview.head(max(0, int(row_limit)))

    output_meta = _account_output_payload(target)
    return {
        "file_name": target.name,
        "relative_path": str(target.relative_to(output)),
        "preview_type": "quanti_parquet",
        "account_id": output_meta["account_id"],
        "account_name": output_meta["account_name"],
        "status": "mapped",
        "metadata": {
            "period_from": _compact_date(output_meta["date_start"]),
            "period_to": _compact_date(output_meta["date_end"]),
        },
        "columns": columns,
        "preview_columns": list(preview.columns),
        "rows": _json_rows(preview),
        "date_start": output_meta["date_start"],
        "date_end": output_meta["date_end"],
        "row_count": len(frame),
        "preview_row_count": len(preview),
    }


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    return value


def _json_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in frame.to_dict("records")
    ]


def _preview_cell_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _values_match(left: Any, right: Any) -> bool:
    if pd.isna(left) and pd.isna(right):
        return True
    if pd.isna(left) or pd.isna(right):
        return False
    if isinstance(left, Number) and isinstance(right, Number):
        return math.isclose(float(left), float(right), rel_tol=0, abs_tol=1e-12)
    return _normalize_label(left) == _normalize_label(right)


def read_asset_excel(
    file_name: str | Path,
    *,
    sheet_name: str | int | None = None,
    row_limit: int | None = 100,
    root_directory: str | Path = QUANTIWISE_EXCEL_DIR,
) -> dict[str, Any]:
    """Read one Excel sheet from an assets Excel file as JSON-friendly rows."""
    target = _resolve_asset_excel_path(file_name, root_directory=root_directory)
    excel = _excel_file(target)
    selected_sheet: str | int = excel.sheet_names[0] if sheet_name is None else sheet_name
    selected_sheet_name = excel.sheet_names[selected_sheet] if isinstance(selected_sheet, int) else str(selected_sheet)

    nrows = max(0, int(row_limit)) if row_limit is not None else None
    quanti_preview = _read_quanti_preview_sheet(
        target,
        selected_sheet_name,
        row_limit=nrows,
        source_directory=Path(root_directory).expanduser().resolve(),
        sheet_names=excel.sheet_names,
    )
    if quanti_preview is not None:
        return quanti_preview

    frame = _read_excel(target, sheet_name=selected_sheet, dtype=object, nrows=nrows)

    columns = [str(column) for column in frame.columns]
    frame.columns = columns
    rows = _json_rows(frame)

    return {
        "file_name": target.name,
        "relative_path": str(target.relative_to(Path(root_directory).expanduser().resolve())),
        "sheet_name": selected_sheet_name,
        "sheet_names": list(excel.sheet_names),
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
    }


def read_asset_excel_sheets(
    file_name: str | Path,
    *,
    root_directory: str | Path = QUANTIWISE_EXCEL_DIR,
) -> dict[str, Any]:
    """Read workbook sheet names without loading any sheet body rows."""
    target = _resolve_asset_excel_path(file_name, root_directory=root_directory)
    excel = _excel_file(target)
    sheet_names = list(excel.sheet_names)
    return {
        "file_name": target.name,
        "relative_path": str(target.relative_to(Path(root_directory).expanduser().resolve())),
        "sheet_names": sheet_names,
        "sheet_count": len(sheet_names),
    }


def _sheet_summary_payload(
    xlsx_path: Path,
    sheet_name: str,
    *,
    source_directory: Path | None = None,
    account_name: str | None = None,
    account_mappings: list[AccountMappingInput] | None = None,
    frame: pd.DataFrame | None = None,
    reason: str = "",
) -> dict[str, Any]:
    resolved_account_name = _account_name_for_sheet(sheet_name, account_mappings) if account_name is None else account_name
    status = "mapped"
    if resolved_account_name is None:
        status = "unmapped"
        reason = reason or ("No account-name mapping" if account_mappings is not None else "Unmapped sheet name")
    elif frame is None:
        status = "format_error"
    payload = {
        "file_name": xlsx_path.name,
        "sheet_name": sheet_name,
        "account_name": resolved_account_name,
        "mapped": status == "mapped",
        "status": status,
        "date_start": "",
        "date_end": "",
        "rows": 0,
        "columns": 0,
        "reason": reason,
    }
    if source_directory is not None:
        payload["relative_path"] = str(xlsx_path.relative_to(source_directory))
    if frame is None:
        return payload
    payload.update(
        {
            "date_start": frame.index.min().isoformat() if len(frame.index) else "",
            "date_end": frame.index.max().isoformat() if len(frame.index) else "",
            "rows": len(frame),
            "columns": len(frame.columns),
        }
    )
    return payload


def _sheet_preview_summary(xlsx_path: Path, sheet_name: str) -> dict[str, Any]:
    account_name = _account_name_for_sheet(sheet_name)
    if account_name is None:
        return _sheet_summary_payload(xlsx_path, sheet_name, account_name=account_name)
    try:
        frame = _read_quanti_wide_sheet(xlsx_path, sheet_name)
    except ValueError as exc:
        return _sheet_summary_payload(xlsx_path, sheet_name, account_name=account_name, reason=str(exc))
    return _sheet_summary_payload(xlsx_path, sheet_name, account_name=account_name, frame=frame)


def _code_name_mappings_from_sheet(
    raw_frame: pd.DataFrame,
    xlsx_path: Path | pd.ExcelFile,
    sheet_name: str,
    code_row: int,
    name_row: int | None,
    code_count: int,
) -> list[CodeNameMapping]:
    excel_source = getattr(xlsx_path, "io", None) or getattr(xlsx_path, "_io", None)
    excel_name = Path(str(excel_source)).name if isinstance(xlsx_path, pd.ExcelFile) else xlsx_path.name
    codes = [_normalize_label(value) for value in raw_frame.iloc[code_row, 1 : code_count + 1].tolist()]
    names = (
        [_normalize_label(value) for value in raw_frame.iloc[name_row, 1 : code_count + 1].tolist()]
        if name_row is not None
        else [""] * len(codes)
    )
    return [
        {
            "code": code,
            "name": name,
            "file_name": excel_name,
            "sheet_name": sheet_name,
        }
        for code, name in zip(codes, names, strict=False)
        if code
    ]


def read_asset_excel_interpreted(
    file_name: str | Path,
    *,
    sheet_name: str,
    row_limit: int | None = 20,
    column_limit: int | None = 12,
    root_directory: str | Path = QUANTIWISE_EXCEL_DIR,
) -> dict[str, Any]:
    """Read one supported assets sheet using the conversion parser."""
    target = _resolve_asset_excel_path(file_name, root_directory=root_directory)
    account_name = _account_name_for_sheet(sheet_name)
    if account_name is None:
        msg = f"No account-name mapping: {sheet_name}"
        raise ValueError(msg)

    frame = _read_quanti_wide_sheet(target, sheet_name)
    column_names = [str(column) for column in frame.columns]
    preview = frame.reset_index()
    preview.columns = [str(column) for column in preview.columns]
    if column_limit is not None:
        preview = preview.iloc[:, : max(1, int(column_limit) + 1)]
    if row_limit is not None:
        preview = preview.head(max(0, int(row_limit)))

    summary = _sheet_summary_payload(
        target,
        sheet_name,
        source_directory=Path(root_directory).expanduser().resolve(),
        account_name=account_name,
        frame=frame,
    )
    return {
        **summary,
        "columns": ["date", *column_names],
        "preview_columns": list(preview.columns),
        "rows": _json_rows(preview),
        "row_count": len(frame),
        "preview_row_count": len(preview),
    }


def _find_marker_row(frame: pd.DataFrame, marker: str) -> int | None:
    for row_index, value in enumerate(frame.iloc[:, 0].tolist()):
        if _normalize_label(value) == marker:
            return row_index
    return None


def _metadata_value(raw_frame: pd.DataFrame, marker: str) -> str:
    row_index = _find_marker_row(raw_frame, marker)
    if row_index is None:
        return ""
    for value in raw_frame.iloc[row_index, 1:].tolist():
        text = _preview_cell_text(value)
        if text:
            return text
    return ""


def _read_quanti_preview_sheet(
    xlsx_path: Path,
    sheet_name: str,
    *,
    row_limit: int | None,
    source_directory: Path,
    sheet_names: list[str],
    column_limit: int = 12,
) -> dict[str, Any] | None:
    raw_row_limit = None if row_limit is None else max(30, int(row_limit) + 20)
    raw_frame = _read_excel(
        xlsx_path,
        sheet_name=sheet_name,
        header=None,
        dtype=object,
        nrows=raw_row_limit,
    )
    code_row = _find_marker_row(raw_frame, "Code")
    name_row = _find_marker_row(raw_frame, "Name")
    date_header_row = _find_marker_row(raw_frame, "D A T E")
    if code_row is None or date_header_row is None:
        return None

    codes = [_normalize_label(value) for value in raw_frame.iloc[code_row, 1:].tolist()]
    valid_positions = [index for index, code in enumerate(codes) if code]
    if not valid_positions:
        return None

    account_name = _account_name_for_sheet(sheet_name)
    names = (
        [_normalize_label(value) for value in raw_frame.iloc[name_row, 1:].tolist()]
        if name_row is not None
        else []
    )
    data_columns = [0, *[position + 1 for position in valid_positions]]
    data = raw_frame.iloc[date_header_row + 1 :, data_columns].copy()
    dates = pd.to_datetime(data.iloc[:, 0], errors="coerce").dt.date
    preview_codes = [codes[position] for position in valid_positions]
    values = data.iloc[:, 1:].copy()
    values.columns = preview_codes
    values.insert(0, "date", dates)
    values = values.dropna(subset=["date"])
    if row_limit is not None:
        values = values.head(max(0, int(row_limit)))
    values = values.where(pd.notna(values), None)

    columns = ["date", *preview_codes]
    preview_columns = columns[: max(1, int(column_limit))]
    preview_frame = values.loc[:, [column for column in preview_columns if column in values.columns]]
    code_name_rows = [
        {
            "code": codes[position],
            "name": names[position] if position < len(names) else "",
        }
        for position in valid_positions
    ]

    return {
        "file_name": xlsx_path.name,
        "relative_path": str(xlsx_path.relative_to(source_directory)),
        "sheet_name": sheet_name,
        "sheet_names": list(sheet_names),
        "preview_type": "quanti_matrix",
        "account_name": account_name,
        "status": "mapped" if account_name else "unmapped",
        "metadata": {
            "period_from": _metadata_value(raw_frame, "Period(From)"),
            "period_to": _metadata_value(raw_frame, "Period(To)"),
        },
        "columns": columns,
        "preview_columns": list(preview_frame.columns),
        "rows": _json_rows(preview_frame),
        "row_count": len(values),
        "preview_row_count": len(preview_frame),
        "code_name_rows": code_name_rows,
    }


def _read_quanti_wide_sheet_with_mapping(
    xlsx_path: Path | pd.ExcelFile,
    sheet_name: str,
) -> tuple[pd.DataFrame, list[CodeNameMapping]]:
    raw_frame = _read_excel(xlsx_path, sheet_name=sheet_name, header=None, dtype=object)
    code_row = _find_marker_row(raw_frame, "Code")
    name_row = _find_marker_row(raw_frame, "Name")
    date_header_row = _find_marker_row(raw_frame, "D A T E")
    if code_row is None or date_header_row is None:
        excel_source = getattr(xlsx_path, "io", None) or getattr(xlsx_path, "_io", None)
        excel_name = Path(str(excel_source)).name if isinstance(xlsx_path, pd.ExcelFile) else xlsx_path.name
        msg = f"Unsupported sheet format: {excel_name} / {sheet_name}"
        raise ValueError(msg)

    codes = [_normalize_label(value) for value in raw_frame.iloc[code_row, 1:].tolist()]
    data = raw_frame.iloc[date_header_row + 1 :, : len(codes) + 1].copy()
    dates = pd.to_datetime(data.iloc[:, 0], errors="coerce").dt.date
    values = data.iloc[:, 1:].copy()
    values.columns = codes
    values.insert(0, "date", dates)
    values = values.dropna(subset=["date"])
    values = values.loc[:, ["date", *[column for column in codes if column]]]
    values = values.set_index("date")
    values = values.where(pd.notna(values), None)

    if values.columns.duplicated().any():
        values = values.T.groupby(level=0).last().T
    if values.index.duplicated().any():
        values = values.groupby(level=0).last()
    mappings = _code_name_mappings_from_sheet(raw_frame, xlsx_path, sheet_name, code_row, name_row, len(codes))
    return values, mappings


def _read_quanti_wide_sheet(xlsx_path: Path | pd.ExcelFile, sheet_name: str) -> pd.DataFrame:
    frame, _ = _read_quanti_wide_sheet_with_mapping(xlsx_path, sheet_name)
    return frame


def _find_conflicts(
    existing: pd.DataFrame,
    incoming: pd.DataFrame,
    *,
    incoming_source: SourceInfo,
    max_conflicts: int = 20,
) -> list[dict[str, str]]:
    common_dates = existing.index.intersection(incoming.index)
    common_columns = existing.columns.intersection(incoming.columns)
    conflicts: list[dict[str, str]] = []
    if common_dates.empty or common_columns.empty:
        return conflicts

    existing_values = existing.loc[common_dates, common_columns]
    incoming_values = incoming.loc[common_dates, common_columns]
    candidate_mask = existing_values.notna() & incoming_values.notna() & ~existing_values.eq(incoming_values)
    for row_date, column in candidate_mask.stack()[lambda series: series].index:
        existing_value = existing_values.at[row_date, column]
        incoming_value = incoming_values.at[row_date, column]
        if _values_match(existing_value, incoming_value):
            continue
        conflicts.append(
            {
                "date": row_date.isoformat() if hasattr(row_date, "isoformat") else str(row_date),
                "code": str(column),
                "existing_value": str(existing_value),
                "incoming_value": str(incoming_value),
                "incoming_file": incoming_source["file_name"],
                "incoming_sheet": incoming_source["sheet_name"],
            }
        )
        if len(conflicts) >= max_conflicts:
            return conflicts
    return conflicts


def _account_quality_payload(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "non_null_cells": 0,
            "total_cells": 0,
            "missing_ratio": 0,
        }
    total_cells = int(frame.shape[0] * frame.shape[1])
    non_null_cells = int(frame.notna().sum().sum())
    return {
        "non_null_cells": non_null_cells,
        "total_cells": total_cells,
        "missing_ratio": round(1 - (non_null_cells / total_cells), 6) if total_cells else 0,
    }


def _merge_account_frames(
    account_name: str,
    frames: list[tuple[pd.DataFrame, SourceInfo]],
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    _validate_rectangular_merge(account_name, frames)
    merged = pd.DataFrame()
    conflicts: list[dict[str, str]] = []
    def sort_key(item: tuple[pd.DataFrame, SourceInfo]) -> Any:
        min_date = item[0].index.min()
        return date.min if pd.isna(min_date) else min_date

    sorted_frames = sorted(frames, key=sort_key)
    for frame, source in sorted_frames:
        if merged.empty:
            merged = frame.copy()
            continue

        frame_conflicts = _find_conflicts(merged, frame, incoming_source=source)
        if frame_conflicts:
            conflicts.extend(frame_conflicts)
            sample = frame_conflicts[0]
            msg = (
                f"Conflicting overlapping values for {account_name}: "
                f"{sample['code']} on {sample['date']} "
                f"({sample['existing_value']} != {sample['incoming_value']})"
            )
            raise ValueError(msg)
        else:
            merged = merged.combine_first(frame)

    return merged.sort_index(), conflicts


def _frame_date_range(frame: pd.DataFrame) -> tuple[date, date] | None:
    if frame.empty or len(frame.index) == 0:
        return None
    start = frame.index.min()
    end = frame.index.max()
    if pd.isna(start) or pd.isna(end):
        return None
    return start, end


def _date_ranges_are_connected(ranges: list[tuple[date, date]]) -> bool:
    if not ranges:
        return True
    current_start, current_end = sorted(ranges)[0]
    for next_start, next_end in sorted(ranges)[1:]:
        if next_start > current_end + timedelta(days=1):
            return False
        current_end = max(current_end, next_end)
    return True


def _validate_rectangular_merge(
    account_name: str,
    frames: list[tuple[pd.DataFrame, SourceInfo]],
) -> None:
    active_frames = [(frame, source) for frame, source in frames if len(frame.index) and len(frame.columns)]
    if len(active_frames) <= 1:
        return

    date_ranges = [
        date_range
        for frame, _source in active_frames
        if (date_range := _frame_date_range(frame)) is not None
    ]
    if not _date_ranges_are_connected(date_ranges):
        msg = (
            f"Cannot merge {account_name}: date ranges are not connected. "
            "Date ranges must overlap or touch with a one-day boundary."
        )
        raise ValueError(msg)

    all_codes: set[str] = set()
    codes_by_date: dict[date, set[str]] = {}
    for frame, _source in active_frames:
        frame_codes = {str(column) for column in frame.columns}
        all_codes.update(frame_codes)
        for row_date in set(frame.index):
            codes_by_date.setdefault(row_date, set()).update(frame_codes)

    for row_date in sorted(codes_by_date):
        missing_codes = sorted(all_codes - codes_by_date[row_date])
        if missing_codes:
            sample = ", ".join(missing_codes[:3])
            suffix = "..." if len(missing_codes) > 3 else ""
            msg = (
                f"Cannot merge {account_name}: merge would create a partially filled table. "
                f"Missing structural cells on {row_date.isoformat()} for codes {sample}{suffix}."
            )
            raise ValueError(msg)


def _code_name_mapping_frame(mappings: list[CodeNameMapping]) -> pd.DataFrame:
    rows: dict[tuple[str, str], dict[str, str]] = {}
    for mapping in mappings:
        code = _normalize_label(mapping.get("code"))
        name = _normalize_label(mapping.get("name"))
        if not code:
            continue
        key = (code, name)
        row = rows.setdefault(
            key,
            {
                "code": code,
                "name": name,
            },
        )

    payload = [
        {
            "code": row["code"],
            "name": row["name"],
        }
        for row in rows.values()
    ]
    return pd.DataFrame(payload, columns=["code", "name"]).sort_values(
        ["code", "name"],
        ignore_index=True,
    )


def _existing_code_name_mappings(output_directory: Path) -> list[CodeNameMapping]:
    mapping_path = output_directory / CODE_NAME_MAPPING_FILE
    if not mapping_path.exists():
        return []
    frame = pd.read_parquet(mapping_path)
    if "code" not in frame.columns:
        return []
    mappings: list[CodeNameMapping] = []
    for row in frame.to_dict("records"):
        code = _normalize_label(row.get("code"))
        if not code:
            continue
        mappings.append(
            {
                "code": code,
                "name": _normalize_label(row.get("name")),
            }
        )
    return mappings


def _existing_account_frames(
    account_name: str,
    output_directory: Path,
    output_info: dict[str, Any] | None = None,
    *,
    source_type: str = "existing_output",
    selected_paths: list[Path] | None = None,
) -> list[tuple[pd.DataFrame, SourceInfo]]:
    if selected_paths is None:
        parquet_paths = [output_directory / f"{account_name}.parquet"]
        parquet_paths.extend(
            path
            for path in sorted(output_directory.glob(f"{account_name}_*.parquet"))
            if path.name not in NON_ACCOUNT_PARQUET_FILES
        )
    else:
        parquet_paths = selected_paths
    frames: list[tuple[pd.DataFrame, SourceInfo]] = []
    for parquet_path in [path for path in parquet_paths if path.exists()]:
        file_meta = _account_output_payload(parquet_path)
        frame = pd.read_parquet(parquet_path)
        if "date" not in frame.columns:
            continue
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
        frame = frame.dropna(subset=["date"]).set_index("date")
        source_info = {
            "file_name": parquet_path.name,
            "account_id": file_meta["account_id"],
            "account_name": file_meta["account_name"],
            "date_start": file_meta["date_start"],
            "date_end": file_meta["date_end"],
            "rows": file_meta["rows"],
            "columns": file_meta["columns"],
            "source_directory": str(output_directory),
            "source_type": source_type,
        }
        frames.append((frame, source_info))
    return frames


def _parquet_account_names(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(
        {
            _account_name_from_output_stem(path.stem)
            for path in sorted(directory.glob("*.parquet"))
            if path.name not in NON_ACCOUNT_PARQUET_FILES
        }
    )


def _account_name_from_output_stem(stem: str) -> str:
    match = re.match(r"^(?P<account>.+)_\d{8}_\d{8}(?:_[0-9a-f]{64})?(?:(?:__|_)\d+)?$", stem)
    if match:
        return match.group("account")
    return stem


def _selected_asset_parquet_paths(directory: Path, selected_files: list[str] | None) -> list[Path]:
    selected = [str(item or "").strip() for item in (selected_files or []) if str(item or "").strip()]
    if len(selected) < 2 or len(selected) % 2:
        raise ValueError("selected_files must contain 2 files per account")
    if len(set(selected)) != len(selected):
        raise ValueError("selected_files must contain different files")

    paths: list[Path] = []
    for file_name in selected:
        path = (directory / file_name).expanduser().resolve()
        if directory not in path.parents:
            raise ValueError(f"Selected file must be under target_directory: {file_name}")
        if path.name in NON_ACCOUNT_PARQUET_FILES or path.suffix != ".parquet":
            raise ValueError(f"Selected file must be an account Parquet file: {file_name}")
        if not path.is_file():
            raise ValueError(f"Selected file not found: {file_name}")
        paths.append(path)

    files_by_account: dict[str, list[str]] = {}
    for path in paths:
        files_by_account.setdefault(_account_name_from_output_stem(path.stem), []).append(path.name)
    invalid_accounts = {
        account_name: file_names
        for account_name, file_names in files_by_account.items()
        if len(file_names) != 2
    }
    if invalid_accounts:
        details = ", ".join(
            f"{account_name}={len(file_names)}"
            for account_name, file_names in sorted(invalid_accounts.items())
        )
        raise ValueError(f"selected_files must contain exactly 2 files for each account: {details}")
    return paths


def validate_asset_parquet_merge_selection(
    target_directory: str | Path,
    selected_files: list[str] | None,
) -> list[str]:
    target = Path(str(target_directory or "").strip()).expanduser().resolve()
    return [path.name for path in _selected_asset_parquet_paths(target, selected_files)]


def _available_archive_path(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}__{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _asset_parquet_delete_confirmed(delete_confirmed: bool, delete_confirmation_text: str) -> bool:
    return delete_confirmed and str(delete_confirmation_text or "").strip() == ASSET_PARQUET_DELETE_CONFIRMATION_TEXT


def _duplicate_base_file_name(file_name: str) -> str | None:
    match = re.match(r"^(?P<base>.+)__\d+(?P<suffix>\.parquet)$", file_name, re.IGNORECASE)
    return f"{match.group('base')}{match.group('suffix')}" if match else None


def _duplicate_suffix_index(file_name: str) -> int:
    match = re.search(r"__(\d+)\.parquet$", file_name, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _comparison_frame(path: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    payload = _account_output_payload(path)
    frame = pd.read_parquet(path)
    if "date" not in frame.columns:
        raise ValueError("Missing date column")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
    frame = frame.dropna(subset=["date"]).set_index("date")
    frame.columns = [str(column) for column in frame.columns]
    return payload, frame.sort_index()


def _frame_non_null_cells(frame: pd.DataFrame) -> int:
    return int(frame.notna().sum().sum())


def _date_range_contains(outer: dict[str, Any], inner: dict[str, Any]) -> bool:
    outer_start = str(outer.get("date_start") or "")
    outer_end = str(outer.get("date_end") or "")
    inner_start = str(inner.get("date_start") or "")
    inner_end = str(inner.get("date_end") or "")
    return bool(outer_start and outer_end and inner_start and inner_end and outer_start <= inner_start and inner_end <= outer_end)


def _file_preference_key(item: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(item["non_null_cells"]),
        len(item["frame"].index),
        len(item["frame"].columns),
        -_duplicate_suffix_index(item["path"].name),
    )


def _preferred_duplicate_item(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_key = _file_preference_key(left)
    right_key = _file_preference_key(right)
    if left_key != right_key:
        return left if left_key > right_key else right
    return left if str(left["path"]) < str(right["path"]) else right


def _axis_can_contain(candidate: dict[str, Any], keeper: dict[str, Any]) -> bool:
    if int(keeper["payload"].get("columns") or 0) < int(candidate["payload"].get("columns") or 0):
        return False
    if int(keeper["payload"].get("rows") or 0) < int(candidate["payload"].get("rows") or 0):
        return False
    if not _date_range_contains(keeper["payload"], candidate["payload"]):
        return False
    return True


def _subset_relation(candidate: pd.DataFrame, keeper: pd.DataFrame) -> tuple[bool, bool, str, dict[str, int]]:
    missing_dates = candidate.index.difference(keeper.index)
    missing_columns = candidate.columns.difference(keeper.columns)
    if len(missing_dates) or len(missing_columns):
        stats = {
            "missing_dates": len(missing_dates),
            "missing_columns": len(missing_columns),
            "missing_values": 0,
            "conflicting_values": 0,
            "extra_dates": max(0, len(keeper.index.difference(candidate.index))),
            "extra_columns": max(0, len(keeper.columns.difference(candidate.columns))),
            "extra_non_null_cells": max(0, _frame_non_null_cells(keeper) - _frame_non_null_cells(candidate)),
        }
        return False, False, "date 또는 종목코드 축이 포함되지 않음", stats

    keeper_aligned = keeper.loc[candidate.index, candidate.columns]
    candidate_non_null = candidate.notna()
    keeper_non_null = keeper_aligned.notna()
    missing_value_mask = candidate_non_null & ~keeper_non_null
    conflict_mask = candidate_non_null & keeper_non_null & ~candidate.eq(keeper_aligned)
    missing_values = int(missing_value_mask.to_numpy().sum())
    conflicting_values = int(conflict_mask.to_numpy().sum())
    extra_non_null_cells = max(0, _frame_non_null_cells(keeper) - _frame_non_null_cells(candidate))
    stats = {
        "missing_dates": 0,
        "missing_columns": 0,
        "missing_values": missing_values,
        "conflicting_values": conflicting_values,
        "extra_dates": max(0, len(keeper.index.difference(candidate.index))),
        "extra_columns": max(0, len(keeper.columns.difference(candidate.columns))),
        "extra_non_null_cells": extra_non_null_cells,
    }
    if missing_values or conflicting_values:
        return False, False, "내부 값이 포함 관계가 아님", stats
    exact = (
        len(candidate.index) == len(keeper.index)
        and len(candidate.columns) == len(keeper.columns)
        and extra_non_null_cells == 0
    )
    if exact:
        return True, False, "동일한 Parquet 내용", stats
    return True, True, "더 완전한 같은 계정 Parquet에 포함됨", stats


def cleanup_duplicate_asset_parquet_outputs(
    target_directory: str | Path,
    *,
    dry_run: bool = True,
    delete_confirmed: bool = False,
    delete_confirmation_text: str = "",
    scan_recursive: bool = False,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Inspect or delete same-account Parquet files covered by a more complete file."""
    target = Path(str(target_directory or "").strip()).expanduser().resolve()
    if not str(target_directory or "").strip():
        raise ValueError("target_directory is required")
    if not target.is_dir():
        raise ValueError(f"target_directory is not a directory: {target}")

    scan_directories = [target]
    if scan_recursive:
        scan_directories.extend(path for path in sorted(target.rglob("*")) if path.is_dir())

    _emit(progress_callback, "중복 검사 시작")
    _emit(progress_callback, f"병합 대상 경로: {target}")
    _emit(progress_callback, f"내부까지 검사: {'On' if scan_recursive else 'Off'}")
    _emit(progress_callback, f"검사 폴더: {len(scan_directories)}개")

    items_by_account: dict[str, list[dict[str, Any]]] = {}
    load_errors: list[dict[str, str]] = []
    for directory in scan_directories:
        for path in sorted(directory.glob("*.parquet")):
            if cancel_check and cancel_check():
                raise RuntimeError("Job cancelled")
            if path.name in NON_ACCOUNT_PARQUET_FILES:
                continue
            try:
                payload, frame = _comparison_frame(path)
            except Exception as exc:
                load_errors.append(
                    {
                        "path": str(path),
                        "file_name": path.name,
                        "parent_directory": str(directory),
                        "reason": f"읽기 실패: {exc}",
                    }
                )
                continue
            account_name = str(payload.get("account_name") or _account_name_from_output_stem(path.stem))
            items_by_account.setdefault(account_name, []).append(
                {
                    "path": path,
                    "payload": payload,
                    "frame": frame,
                    "non_null_cells": _frame_non_null_cells(frame),
                }
            )

    deletion_candidates: list[dict[str, str]] = []
    mismatched_duplicates: list[dict[str, str]] = []
    duplicate_group_count = 0
    candidate_by_path: dict[Path, dict[str, str]] = {}
    mismatch_seen: set[tuple[Path, Path, str]] = set()
    for account_name, items in sorted(items_by_account.items()):
        if len(items) < 2:
            continue
        duplicate_group_count += 1
        _emit(progress_callback, f"중복 후보 검사: 계정={account_name}, 파일 {len(items)}개")
        for index, candidate in enumerate(items):
            for keeper in items[index + 1:]:
                if cancel_check and cancel_check():
                    raise RuntimeError("Job cancelled")
                relation_inputs = []
                if _axis_can_contain(candidate, keeper):
                    relation_inputs.append((candidate, keeper))
                if _axis_can_contain(keeper, candidate):
                    relation_inputs.append((keeper, candidate))
                if not relation_inputs:
                    continue
                relations = [
                    (subset_item, superset_item, *_subset_relation(subset_item["frame"], superset_item["frame"]))
                    for subset_item, superset_item in relation_inputs
                ]
                has_subset_relation = any(relation[2] for relation in relations)
                for subset_item, superset_item, is_subset, is_strict, reason, stats in relations:
                    if not is_subset:
                        if has_subset_relation:
                            continue
                        same_base_name = (
                            _duplicate_base_file_name(subset_item["path"].name) or subset_item["path"].name
                        ) == (
                            _duplicate_base_file_name(superset_item["path"].name) or superset_item["path"].name
                        )
                        should_report = (
                            same_base_name
                            or int(stats.get("missing_values") or 0) > 0
                            or int(stats.get("conflicting_values") or 0) > 0
                        )
                        key = (subset_item["path"], superset_item["path"], reason)
                        if should_report and key not in mismatch_seen:
                            mismatch_seen.add(key)
                            mismatched_duplicates.append(
                                {
                                    "path": str(subset_item["path"]),
                                    "file_name": subset_item["path"].name,
                                    "canonical_path": str(superset_item["path"]),
                                    "canonical_file": superset_item["path"].name,
                                    "parent_directory": str(subset_item["path"].parent),
                                    "account_name": account_name,
                                    "reason": reason,
                                    **{key: str(value) for key, value in stats.items()},
                                }
                        )
                        continue
                    if not is_strict:
                        preferred = _preferred_duplicate_item(subset_item, superset_item)
                        removable = superset_item if preferred is subset_item else subset_item
                        kept = subset_item if removable is superset_item else superset_item
                        if removable["path"] == kept["path"]:
                            continue
                        subset_item = removable
                        superset_item = kept
                        reason = "동일한 Parquet 내용"
                    row = {
                        "path": str(subset_item["path"]),
                        "file_name": subset_item["path"].name,
                        "canonical_path": str(superset_item["path"]),
                        "canonical_file": superset_item["path"].name,
                        "parent_directory": str(subset_item["path"].parent),
                        "account_name": account_name,
                        "reason": reason,
                        **{key: str(value) for key, value in stats.items()},
                    }
                    existing = candidate_by_path.get(subset_item["path"])
                    if existing is None or _file_preference_key(superset_item) > (
                        int(existing.get("keeper_non_null_cells") or 0),
                        int(existing.get("keeper_rows") or 0),
                        int(existing.get("keeper_columns") or 0),
                        -_duplicate_suffix_index(existing.get("canonical_file") or ""),
                    ):
                        row["keeper_non_null_cells"] = str(superset_item["non_null_cells"])
                        row["keeper_rows"] = str(len(superset_item["frame"].index))
                        row["keeper_columns"] = str(len(superset_item["frame"].columns))
                        candidate_by_path[subset_item["path"]] = row

    deletion_candidates = sorted(candidate_by_path.values(), key=lambda item: item["path"])
    mismatched_duplicates.extend(load_errors)

    if not dry_run and deletion_candidates and not _asset_parquet_delete_confirmed(delete_confirmed, delete_confirmation_text):
        raise ValueError(f'파일 삭제 전 "{ASSET_PARQUET_DELETE_CONFIRMATION_TEXT}" 입력과 삭제 허가가 필요합니다.')

    deleted_files: list[dict[str, str]] = []
    if not dry_run:
        for item in deletion_candidates:
            path = Path(item["path"])
            if path.exists():
                path.unlink()
            deleted_files.append(item)

    _emit(
        progress_callback,
        (
            "중복 검사 완료: "
            f"삭제 후보 {len(deletion_candidates)}개, "
            f"포함 불가 {len(mismatched_duplicates)}개"
        ),
    )
    if not dry_run:
        _emit(progress_callback, f"중복 삭제 완료: {len(deleted_files)}개")

    return {
        "status": "completed",
        "format": "quantiwise_parquet_duplicate_cleanup_v1",
        "operation": "parquet_duplicate_cleanup",
        "target_directory": str(target),
        "dry_run": dry_run,
        "scan_recursive": scan_recursive,
        "duplicate_group_count": duplicate_group_count,
        "deletion_candidate_count": len(deletion_candidates),
        "deleted_count": len(deleted_files),
        "deletion_candidates": deletion_candidates,
        "deleted_files": deleted_files,
        "mismatched_duplicates": mismatched_duplicates,
    }


def _asset_excel_scan_workers(file_count: int) -> int:
    if file_count <= 1:
        return 1
    return max(1, min(4, file_count, os.cpu_count() or 1))


def _scan_asset_excel_frames(
    source_directory: str | Path,
    *,
    selected_files: list[str] | None = None,
    account_mappings: list[AccountMappingInput] | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[
    list[tuple[str, pd.DataFrame, SourceInfo]],
    dict[str, list[SourceInfo]],
    list[dict[str, str]],
    list[dict[str, Any]],
    list[CodeNameMapping],
]:
    source = Path(source_directory).expanduser().resolve()
    xlsx_files = _selected_asset_excel_paths(source, selected_files)
    if not xlsx_files:
        msg = f"No Excel files found in {source}"
        raise ValueError(msg)

    sources_by_account: dict[str, list[SourceInfo]] = {}
    scanned_sheets: list[tuple[str, pd.DataFrame, SourceInfo]] = []
    skipped: list[dict[str, str]] = []
    sheet_summaries: list[dict[str, Any]] = []
    code_name_mappings: list[CodeNameMapping] = []

    def scan_file(file_index: int, xlsx_path: Path) -> tuple[
        list[tuple[str, pd.DataFrame, SourceInfo]],
        dict[str, list[SourceInfo]],
        list[dict[str, str]],
        list[dict[str, Any]],
        list[CodeNameMapping],
    ]:
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        file_sheets: list[tuple[str, pd.DataFrame, SourceInfo]] = []
        file_sources_by_account: dict[str, list[SourceInfo]] = {}
        file_skipped: list[dict[str, str]] = []
        file_sheet_summaries: list[dict[str, Any]] = []
        file_code_name_mappings: list[CodeNameMapping] = []
        _emit(progress_callback, f"[파일 {file_index}/{len(xlsx_files)}] {xlsx_path.name} 스캔 중...")
        excel = _excel_file(xlsx_path)
        _emit(progress_callback, f"[파일 {file_index}/{len(xlsx_files)}] Sheet {len(excel.sheet_names)}개 발견")
        for sheet_index, sheet_name in enumerate(excel.sheet_names, start=1):
            if cancel_check and cancel_check():
                raise RuntimeError("Job cancelled")
            _emit(progress_callback, f"[Sheet {sheet_index}/{len(excel.sheet_names)}] {xlsx_path.name} / {sheet_name}")
            account_name = _account_name_for_sheet(sheet_name, account_mappings)
            if account_name is None:
                summary = _sheet_summary_payload(
                    xlsx_path,
                    sheet_name,
                    source_directory=source,
                    account_name=account_name,
                    account_mappings=account_mappings,
                )
                file_skipped.append(
                    {
                        "file_name": xlsx_path.name,
                        "relative_path": str(xlsx_path.relative_to(source)),
                        "sheet_name": sheet_name,
                        "reason": summary["reason"],
                        "status": summary["status"],
                    }
                )
                file_sheet_summaries.append(summary)
                _emit(progress_callback, f"  건너뜀: {summary['reason']}")
                continue
            try:
                frame, mappings = _read_quanti_wide_sheet_with_mapping(excel, sheet_name)
            except ValueError as exc:
                summary = _sheet_summary_payload(
                    xlsx_path,
                    sheet_name,
                    source_directory=source,
                    account_name=account_name,
                    account_mappings=account_mappings,
                    reason=str(exc),
                )
                file_skipped.append(
                    {
                        "file_name": xlsx_path.name,
                        "relative_path": str(xlsx_path.relative_to(source)),
                        "sheet_name": sheet_name,
                        "reason": summary["reason"],
                        "status": summary["status"],
                    }
                )
                file_sheet_summaries.append(summary)
                _emit(progress_callback, f"  건너뜀: {summary['reason']}")
                continue
            file_code_name_mappings.extend(mappings)
            relative_path = str(xlsx_path.relative_to(source))
            date_start = frame.index.min().isoformat() if len(frame.index) else ""
            date_end = frame.index.max().isoformat() if len(frame.index) else ""
            output_stem = _sheet_output_stem(account_name, date_start, date_end, frame.columns)
            account_mapping = _account_mapping_for_name(account_name, account_mappings)
            source_info = {
                "file_name": xlsx_path.name,
                "relative_path": relative_path,
                "sheet_name": sheet_name,
                "account_name": account_name,
                "account_id": account_mapping["account_id"],
                "output_stem": output_stem,
                "date_start": date_start,
                "date_end": date_end,
                "rows": len(frame),
                "columns": len(frame.columns),
            }
            file_sheets.append((output_stem, frame, source_info))
            file_sources_by_account.setdefault(account_name, []).append(source_info)
            summary = _sheet_summary_payload(
                xlsx_path,
                sheet_name,
                source_directory=source,
                account_name=account_name,
                account_mappings=account_mappings,
                frame=frame,
            )
            summary["output_file"] = f"{output_stem}.parquet"
            file_sheet_summaries.append(summary)
            _emit(
                progress_callback,
                (
                    f"  매핑 완료: 계정={account_name}, "
                    f"행={len(frame)}, 코드={len(frame.columns)}, 날짜={_date_range_label(frame.index)}"
                ),
            )
        return file_sheets, file_sources_by_account, file_skipped, file_sheet_summaries, file_code_name_mappings

    scan_workers = _asset_excel_scan_workers(len(xlsx_files))
    _emit(progress_callback, f"Excel 스캔 워커: {scan_workers}개")
    if scan_workers == 1:
        file_results = [scan_file(file_index, xlsx_path) for file_index, xlsx_path in enumerate(xlsx_files, start=1)]
    else:
        file_results = []
        with ThreadPoolExecutor(max_workers=scan_workers, thread_name_prefix="quanti-excel-scan") as executor:
            futures = [
                executor.submit(scan_file, file_index, xlsx_path)
                for file_index, xlsx_path in enumerate(xlsx_files, start=1)
            ]
            for future in futures:
                file_results.append(future.result())

    used_stems: dict[str, int] = {}
    for file_sheets, file_sources_by_account, file_skipped, file_sheet_summaries, file_code_name_mappings in file_results:
        for output_stem, frame, source_info in file_sheets:
            duplicate_index = used_stems.get(output_stem, 0)
            used_stems[output_stem] = duplicate_index + 1
            resolved_stem = output_stem if duplicate_index == 0 else f"{output_stem}__{duplicate_index + 1}"
            source_info["output_stem"] = resolved_stem
            source_info["output_file"] = f"{resolved_stem}.parquet"
            scanned_sheets.append((resolved_stem, frame, source_info))
            account_name = str(source_info["account_name"])
            sources_by_account.setdefault(account_name, []).append(source_info)
            for summary in file_sheet_summaries:
                if (
                    summary.get("relative_path") == source_info.get("relative_path")
                    and summary.get("sheet_name") == source_info.get("sheet_name")
                ):
                    summary["output_file"] = source_info["output_file"]
        skipped.extend(file_skipped)
        sheet_summaries.extend(file_sheet_summaries)
        code_name_mappings.extend(file_code_name_mappings)
    return scanned_sheets, sources_by_account, skipped, sheet_summaries, code_name_mappings


def _write_sheet_parquet_temp(
    frame: pd.DataFrame,
    parquet_path: Path,
    *,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    save_frame = frame.reset_index()
    quality = _account_quality_payload(frame)
    _write_parquet_with_metadata(
        save_frame,
        parquet_path,
        {
            **metadata,
            "rows": len(frame),
            "columns": len(frame.columns),
            "non_null_cells": quality["non_null_cells"],
            "total_cells": quality["total_cells"],
            "missing_ratio": quality["missing_ratio"],
        },
    )
    return quality


def _existing_output_stem_counts(output_directory: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not output_directory.is_dir():
        return counts
    for path in output_directory.glob("*.parquet"):
        if path.name in NON_ACCOUNT_PARQUET_FILES:
            continue
        match = re.match(r"^(?P<base>.+?)(?:__(?P<index>\d+))?$", path.stem)
        if not match:
            continue
        base = match.group("base")
        count = int(match.group("index") or "1")
        counts[base] = max(counts.get(base, 0), count)
    return counts


def _scan_and_write_asset_excel_parquet(
    source_directory: str | Path,
    temp_output: Path,
    final_output: Path,
    *,
    selected_files: list[str] | None = None,
    account_mappings: list[AccountMappingInput] | None = None,
    resume_failed_only: bool = False,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, list[SourceInfo]],
    list[dict[str, str]],
    list[dict[str, Any]],
    list[CodeNameMapping],
    list[dict[str, str]],
]:
    source = Path(source_directory).expanduser().resolve()
    xlsx_files = _selected_asset_excel_paths(source, selected_files)
    if not xlsx_files:
        msg = f"No Excel files found in {source}"
        raise ValueError(msg)

    completed_output_files = {
        path.name
        for path in final_output.glob("*.parquet")
        if resume_failed_only and path.name not in NON_ACCOUNT_PARQUET_FILES
    } if final_output.is_dir() else set()

    def scan_file(file_index: int, xlsx_path: Path) -> tuple[
        list[dict[str, Any]],
        list[dict[str, str]],
        list[dict[str, Any]],
        list[CodeNameMapping],
        list[dict[str, str]],
    ]:
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        file_outputs: list[dict[str, Any]] = []
        file_skipped: list[dict[str, str]] = []
        file_sheet_summaries: list[dict[str, Any]] = []
        file_code_name_mappings: list[CodeNameMapping] = []
        file_resume_skipped: list[dict[str, str]] = []
        _emit(progress_callback, f"[파일 {file_index}/{len(xlsx_files)}] {xlsx_path.name} 스캔 중...")
        excel = _excel_file(xlsx_path)
        _emit(progress_callback, f"[파일 {file_index}/{len(xlsx_files)}] Sheet {len(excel.sheet_names)}개 발견")
        for sheet_index, sheet_name in enumerate(excel.sheet_names, start=1):
            if cancel_check and cancel_check():
                raise RuntimeError("Job cancelled")
            _emit(progress_callback, f"[Sheet {sheet_index}/{len(excel.sheet_names)}] {xlsx_path.name} / {sheet_name}")
            account_name = _account_name_for_sheet(sheet_name, account_mappings)
            if account_name is None:
                summary = _sheet_summary_payload(
                    xlsx_path,
                    sheet_name,
                    source_directory=source,
                    account_name=account_name,
                    account_mappings=account_mappings,
                )
                file_skipped.append(
                    {
                        "file_name": xlsx_path.name,
                        "relative_path": str(xlsx_path.relative_to(source)),
                        "sheet_name": sheet_name,
                        "reason": summary["reason"],
                        "status": summary["status"],
                    }
                )
                file_sheet_summaries.append(summary)
                _emit(progress_callback, f"  건너뜀: {summary['reason']}")
                continue
            try:
                frame, mappings = _read_quanti_wide_sheet_with_mapping(excel, sheet_name)
            except ValueError as exc:
                summary = _sheet_summary_payload(
                    xlsx_path,
                    sheet_name,
                    source_directory=source,
                    account_name=account_name,
                    account_mappings=account_mappings,
                    reason=str(exc),
                )
                file_skipped.append(
                    {
                        "file_name": xlsx_path.name,
                        "relative_path": str(xlsx_path.relative_to(source)),
                        "sheet_name": sheet_name,
                        "reason": summary["reason"],
                        "status": summary["status"],
                    }
                )
                file_sheet_summaries.append(summary)
                _emit(progress_callback, f"  건너뜀: {summary['reason']}")
                continue

            file_code_name_mappings.extend(mappings)
            relative_path = str(xlsx_path.relative_to(source))
            date_start = frame.index.min().isoformat() if len(frame.index) else ""
            date_end = frame.index.max().isoformat() if len(frame.index) else ""
            output_stem = _sheet_output_stem(account_name, date_start, date_end, frame.columns)
            account_mapping = _account_mapping_for_name(account_name, account_mappings)
            source_info = {
                "file_name": xlsx_path.name,
                "relative_path": relative_path,
                "sheet_name": sheet_name,
                "account_name": account_name,
                "account_id": account_mapping["account_id"],
                "output_stem": output_stem,
                "date_start": date_start,
                "date_end": date_end,
                "rows": len(frame),
                "columns": len(frame.columns),
            }
            completed_output_file = ""
            if resume_failed_only and f"{output_stem}.parquet" in completed_output_files:
                completed_output_file = f"{output_stem}.parquet"
            if completed_output_file:
                summary = _sheet_summary_payload(
                    xlsx_path,
                    sheet_name,
                    source_directory=source,
                    account_name=account_name,
                    account_mappings=account_mappings,
                    frame=frame,
                )
                summary["output_file"] = completed_output_file
                file_sheet_summaries.append(summary)
                file_resume_skipped.append(
                    {
                        "file_name": xlsx_path.name,
                        "relative_path": relative_path,
                        "sheet_name": sheet_name,
                        "output_file": completed_output_file,
                        "reason": "이미 변환 완료",
                    }
                )
                _emit(progress_callback, f"  이어하기 건너뜀: 이미 변환 완료 ({completed_output_file})")
                del frame
                continue

            temp_path = temp_output / f"pending_{file_index}_{sheet_index}_{_safe_output_token(output_stem)}.parquet"
            quality = _write_sheet_parquet_temp(
                frame,
                temp_path,
                metadata={
                    "account_id": account_mapping["account_id"],
                    "account_name": account_name,
                    "date_start": date_start,
                    "date_end": date_end,
                },
            )
            summary = _sheet_summary_payload(
                xlsx_path,
                sheet_name,
                source_directory=source,
                account_name=account_name,
                account_mappings=account_mappings,
                frame=frame,
            )
            summary["output_file"] = f"{output_stem}.parquet"
            file_outputs.append(
                {
                    "output_stem": output_stem,
                    "temp_path": temp_path,
                    "source_info": source_info,
                    "quality": quality,
                }
            )
            file_sheet_summaries.append(summary)
            _emit(
                progress_callback,
                (
                    f"  매핑 완료: 계정={account_name}, "
                    f"행={len(frame)}, 코드={len(frame.columns)}, 날짜={_date_range_label(frame.index)}"
                ),
            )
            _emit(progress_callback, f"  임시 저장: {temp_path.name}")
            del frame
        return file_outputs, file_skipped, file_sheet_summaries, file_code_name_mappings, file_resume_skipped

    scan_workers = _asset_excel_scan_workers(len(xlsx_files))
    _emit(progress_callback, f"Excel 스캔 워커: {scan_workers}개")
    if scan_workers == 1:
        file_results = [scan_file(file_index, xlsx_path) for file_index, xlsx_path in enumerate(xlsx_files, start=1)]
    else:
        file_results = []
        with ThreadPoolExecutor(max_workers=scan_workers, thread_name_prefix="quanti-excel-scan") as executor:
            futures = [
                executor.submit(scan_file, file_index, xlsx_path)
                for file_index, xlsx_path in enumerate(xlsx_files, start=1)
            ]
            for future in futures:
                file_results.append(future.result())

    outputs: dict[str, Any] = {}
    sources_by_account: dict[str, list[SourceInfo]] = {}
    skipped: list[dict[str, str]] = []
    sheet_summaries: list[dict[str, Any]] = []
    code_name_mappings: list[CodeNameMapping] = []
    resume_skipped: list[dict[str, str]] = []
    temp_outputs: list[dict[str, Any]] = []
    used_stems: dict[str, int] = _existing_output_stem_counts(final_output) if resume_failed_only else {}

    for file_outputs, file_skipped, file_sheet_summaries, file_code_name_mappings, file_resume_skipped in file_results:
        temp_outputs.extend(file_outputs)
        skipped.extend(file_skipped)
        sheet_summaries.extend(file_sheet_summaries)
        code_name_mappings.extend(file_code_name_mappings)
        resume_skipped.extend(file_resume_skipped)

    total_outputs = len(temp_outputs)
    mapped_sheet_count = sum(1 for sheet in sheet_summaries if sheet.get("status") == "mapped")
    mapped_accounts = {
        str(item["source_info"].get("account_name"))
        for item in temp_outputs
        if item.get("source_info", {}).get("account_name")
    }
    _emit(
        progress_callback,
        (
            "스캔 완료: "
            f"Sheet {len(sheet_summaries)}개, 정상 {mapped_sheet_count}개, "
            f"건너뜀 {len(skipped)}개"
            f"{f', 이어하기 건너뜀 {len(resume_skipped)}개' if resume_failed_only else ''}, "
            f"계정 {len(mapped_accounts)}개"
        ),
    )
    if cancel_check and cancel_check():
        raise RuntimeError("Job cancelled")
    for sheet_index, output_item in enumerate(sorted(temp_outputs, key=lambda item: str(item["output_stem"])), start=1):
        output_stem = str(output_item["output_stem"])
        duplicate_index = used_stems.get(output_stem, 0)
        used_stems[output_stem] = duplicate_index + 1
        resolved_stem = output_stem if duplicate_index == 0 else f"{output_stem}__{duplicate_index + 1}"
        source_info = output_item["source_info"]
        source_info["output_stem"] = resolved_stem
        source_info["output_file"] = f"{resolved_stem}.parquet"
        account_name = str(source_info["account_name"])
        sources_by_account.setdefault(account_name, []).append(source_info)
        for summary in sheet_summaries:
            if (
                summary.get("relative_path") == source_info.get("relative_path")
                and summary.get("sheet_name") == source_info.get("sheet_name")
            ):
                summary["output_file"] = source_info["output_file"]

        final_path = final_output / source_info["output_file"]
        _emit(
            progress_callback,
            (
                f"[저장 {sheet_index}/{total_outputs}] {final_path.name}: "
                f"계정={source_info.get('account_name')}, "
                f"행={source_info.get('rows')}, 코드={source_info.get('columns')}, "
                f"날짜={source_info.get('date_start')}~{source_info.get('date_end')}"
            ),
        )
        shutil.move(str(output_item["temp_path"]), final_path)
        outputs[resolved_stem] = {
            "path": str(final_path),
            "output_file": final_path.name,
            "account_id": source_info.get("account_id", ""),
            "account_name": source_info.get("account_name", ""),
            "rows": source_info.get("rows", 0),
            "columns": source_info.get("columns", 0),
            "date_start": source_info.get("date_start", ""),
            "date_end": source_info.get("date_end", ""),
            "quality": output_item["quality"],
        }

    return dict(sorted(outputs.items())), sources_by_account, skipped, sheet_summaries, code_name_mappings, resume_skipped


def convert_asset_excels_to_wide_parquet(
    source_directory: str | Path = QUANTIWISE_EXCEL_DIR,
    output_directory: str | Path = DEFAULT_ASSET_PARQUET_DIR,
    *,
    selected_files: list[str] | None = None,
    account_mappings: list[AccountMappingInput] | None = None,
    write_mode: str = "replace",
    resume_failed_only: bool = False,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Merge assets Excel sheets by account name and save each account as wide Parquet."""
    source = Path(source_directory).expanduser().resolve()
    output = Path(output_directory).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    normalized_mode = str(write_mode or "replace").strip().lower()
    if normalized_mode not in {"update", "replace"}:
        msg = f"Unsupported write mode: {write_mode}"
        raise ValueError(msg)

    _emit(progress_callback, "Quantiwise 변환 시작")
    _emit(progress_callback, f"원본 데이터 경로: {source}")
    _emit(progress_callback, f"데이터 경로: {output}")
    _emit(progress_callback, f"저장 방식: {normalized_mode}")
    _emit(progress_callback, f"이어하기: {'실패분만' if resume_failed_only else '아니오'}")
    if selected_files:
        _emit(progress_callback, f"선택 파일: {len(selected_files)}개")
    else:
        _emit(progress_callback, "선택 파일: 전체 Excel")

    output_info = inspect_asset_excel_output(output)
    existing_account_count = int(output_info.get("account_count") or len(output_info.get("parquet_files") or []))
    if existing_account_count:
        _emit(progress_callback, f"기존 출력 감지: Parquet {existing_account_count}개")
    else:
        _emit(progress_callback, "기존 출력 감지: 없음")
    with tempfile.TemporaryDirectory(prefix=".quanti_parquet_write_", dir=output) as temp_output_name:
        temp_output = Path(temp_output_name)
        _emit(progress_callback, f"임시 데이터 경로: {temp_output}")
        _emit(progress_callback, "Sheet 단위 생성: Sheet를 읽는 즉시 임시 Parquet로 저장")
        outputs, sources_by_account, skipped, sheet_summaries, code_name_mappings, resume_skipped = _scan_and_write_asset_excel_parquet(
            source,
            temp_output,
            output,
            selected_files=selected_files,
            account_mappings=account_mappings,
            resume_failed_only=resume_failed_only,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    if resume_failed_only:
        code_name_mappings = [*_existing_code_name_mappings(output), *code_name_mappings]

    code_name_mapping = _code_name_mapping_frame(code_name_mappings)
    code_name_mapping_path = output / CODE_NAME_MAPPING_FILE
    code_name_mapping.to_parquet(code_name_mapping_path, index=False, compression="snappy")
    _emit(progress_callback, f"코드-종목명 매핑 저장: {code_name_mapping_path.name} ({len(code_name_mapping)}행)")
    _emit(
        progress_callback,
        f"Quantiwise 변환 완료: Sheet Parquet {len(outputs)}개, 건너뛴 Sheet {len(skipped)}개, 데이터 경로 {output}",
    )
    if resume_failed_only:
        _emit(progress_callback, f"이어하기 건너뜀: {len(resume_skipped)}개")
    for item in skipped:
        _emit(
            progress_callback,
            "건너뛴 Sheet 상세: "
            f"{item.get('relative_path') or item.get('file_name')} / {item.get('sheet_name')} - {item.get('reason')}",
        )

    return {
        "status": "completed",
        "output_directory": str(output),
        "sheets_processed": len(outputs),
        "accounts_processed": len(sources_by_account),
        "write_mode": normalized_mode,
        "resume_failed_only": resume_failed_only,
        "conflict_policy": "error",
        "code_name_mapping": {
            "path": str(code_name_mapping_path),
            "rows": len(code_name_mapping),
        },
        "outputs": outputs,
        "conflicts": {},
        "skipped": skipped,
        "resume_skipped": resume_skipped,
        "sheets": sheet_summaries,
    }


def merge_asset_parquet_outputs(
    target_directory: str | Path,
    output_directory: str | Path = DEFAULT_ASSET_PARQUET_DIR,
    *,
    selected_files: list[str] | None = None,
    same_directory: bool = False,
    cleanup_merged_items: bool = True,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Merge selected generated Quantiwise Parquet files in two-file account groups."""
    def required_path(value: str | Path, field_name: str) -> Path:
        resolved = str(value or "").strip()
        if not resolved:
            raise ValueError(f"{field_name} is required")
        return Path(resolved).expanduser().resolve()

    target = required_path(target_directory, "target_directory")
    output = target if same_directory else required_path(output_directory, "output_directory")
    selected_paths = _selected_asset_parquet_paths(target, selected_files)
    cleanup_destinations: list[tuple[Path, Path]] = []
    if cleanup_merged_items:
        merged_dir = target / "merged"
        cleanup_destinations = [
            (path, _available_archive_path(merged_dir / path.name))
            for path in selected_paths
        ]
    output.mkdir(parents=True, exist_ok=True)

    target_accounts = sorted({_account_name_from_output_stem(path.stem) for path in selected_paths})
    if not target_accounts:
        msg = f"No account Parquet files found in {target}"
        raise ValueError(msg)

    frames_by_account: dict[str, list[tuple[pd.DataFrame, SourceInfo]]] = {}
    sources_by_account: dict[str, list[SourceInfo]] = {}
    _emit(progress_callback, f"Selected merge files: {', '.join(path.name for path in selected_paths)}")
    for account_name in sorted(target_accounts):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        account_paths = [
            path
            for path in selected_paths
            if _account_name_from_output_stem(path.stem) == account_name
        ]
        loaded_frames = _existing_account_frames(
            account_name,
            target,
            None,
            source_type="target_parquet",
            selected_paths=account_paths,
        )
        for frame, source_info in loaded_frames:
            frames_by_account.setdefault(account_name, []).append((frame, source_info))
            sources_by_account.setdefault(account_name, []).append(source_info)

    code_name_mapping = _code_name_mapping_frame(_existing_code_name_mappings(target))
    code_name_mapping_path = output / CODE_NAME_MAPPING_FILE
    code_name_mapping.to_parquet(code_name_mapping_path, index=False, compression="snappy")

    accounts: dict[str, Any] = {}
    conflicts_by_account: dict[str, list[dict[str, str]]] = {}
    final_output_replacements: list[tuple[Path, Path]] = []
    for account_name, frames in sorted(frames_by_account.items()):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        _emit(progress_callback, f"Merging {account_name}...")
        merged, conflicts = _merge_account_frames(account_name, frames)
        if conflicts:
            conflicts_by_account[account_name] = conflicts
        date_start = merged.index.min().isoformat() if len(merged.index) else ""
        date_end = merged.index.max().isoformat() if len(merged.index) else ""
        parquet_path = output / f"{_sheet_output_stem(account_name, date_start, date_end, merged.columns)}.parquet"
        account_sources = sources_by_account.get(account_name, [])
        source_meta = account_sources[0] if account_sources else {}
        account_id = str(source_meta.get("account_id") or "")
        quality = _account_quality_payload(merged)
        write_path = parquet_path
        if parquet_path in selected_paths:
            with tempfile.NamedTemporaryFile(
                prefix=f".{parquet_path.stem}.",
                suffix=".parquet",
                dir=output,
                delete=False,
            ) as temporary_file:
                write_path = Path(temporary_file.name)
            final_output_replacements.append((write_path, parquet_path))
        _write_parquet_with_metadata(
            merged.reset_index(),
            write_path,
            _account_footer_metadata(
                account_id=account_id,
                account_name=account_name,
                date_start=date_start,
                date_end=date_end,
                rows=len(merged),
                columns=len(merged.columns),
                quality=quality,
            ),
        )
        accounts[account_name] = {
            "path": str(parquet_path),
            "output_file": parquet_path.name,
            "account_id": account_id,
            "account_name": account_name,
            "rows": len(merged),
            "columns": len(merged.columns),
            "date_start": date_start,
            "date_end": date_end,
            "quality": quality,
        }

    moved_files: list[dict[str, str]] = []
    if cleanup_destinations:
        cleanup_destinations[0][1].parent.mkdir(parents=True, exist_ok=True)
        for path, destination in cleanup_destinations:
            shutil.move(str(path), str(destination))
            moved_files.append({"from": str(path), "to": str(destination)})
    for source_path, destination_path in final_output_replacements:
        shutil.move(str(source_path), str(destination_path))

    return {
        "status": "completed",
        "operation": "merge_parquet",
        "target_directory": str(target),
        "selected_files": [path.name for path in selected_paths],
        "output_directory": str(output),
        "same_directory": same_directory,
        "cleanup_merged_items": cleanup_merged_items,
        "moved_files": moved_files,
        "accounts_processed": len(accounts),
        "conflict_policy": "error",
        "code_name_mapping": {
            "path": str(code_name_mapping_path),
            "rows": len(code_name_mapping),
        },
        "accounts": accounts,
        "conflicts": conflicts_by_account,
    }


def inspect_asset_excel_conversion(
    source_directory: str | Path = QUANTIWISE_EXCEL_DIR,
    output_directory: str | Path = DEFAULT_ASSET_PARQUET_DIR,
    *,
    selected_files: list[str] | None = None,
    account_mappings: list[AccountMappingInput] | None = None,
    write_mode: str = "replace",
) -> dict[str, Any]:
    source = Path(source_directory).expanduser().resolve()
    output = Path(output_directory).expanduser().resolve()
    scanned_sheets, sources_by_account, skipped, sheet_summaries, code_name_mappings = _scan_asset_excel_frames(
        source,
        selected_files=selected_files,
        account_mappings=account_mappings,
    )
    output_info = inspect_asset_excel_output(output)
    normalized_mode = str(write_mode or "replace").strip().lower()

    outputs = {
        output_stem: {
            "output_file": f"{output_stem}.parquet",
            "account_id": source_info.get("account_id", ""),
            "account_name": source_info.get("account_name", ""),
            "rows": len(frame),
            "columns": len(frame.columns),
            "source_count": 1,
            "will_update_existing": False,
            "quality": _account_quality_payload(frame),
        }
        for output_stem, frame, source_info in sorted(scanned_sheets, key=lambda item: item[0])
    }

    return {
        "status": "preview",
        "source_directory": str(source),
        "output_directory": str(output),
        "write_mode": normalized_mode,
        "conflict_policy": "error",
        "selected_files": selected_files or [],
        "code_name_mapping": {
            "path": str(output / CODE_NAME_MAPPING_FILE),
            "rows": len(_code_name_mapping_frame(code_name_mappings)),
        },
        "files": list_asset_excel_files(source),
        "sheets": sheet_summaries,
        "outputs": outputs,
        "skipped": skipped,
        "conflicts": {},
        "output": output_info,
    }


__all__ = [
    "DEFAULT_ASSET_PARQUET_DIR",
    "cleanup_duplicate_asset_parquet_outputs",
    "convert_asset_excels_to_wide_parquet",
    "default_account_mappings",
    "inspect_asset_excel_conversion",
    "inspect_asset_excel_output",
    "list_asset_excel_files",
    "merge_asset_parquet_outputs",
    "validate_asset_parquet_merge_selection",
    "read_asset_excel",
    "read_asset_excel_interpreted",
    "read_asset_parquet_preview",
    "read_asset_excel_sheets",
]
