"""Excel readers for Quantiwise Excel files stored under project resources."""

from __future__ import annotations

import json
import math
from numbers import Number
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from finiq.config import QUANTIWISE_EXCEL_DIR, RESOURCES_DIR

EXCEL_SUFFIXES = {".xlsx", ".xlsm"}
ASSET_PARQUET_FORMAT = "finiq_asset_wide_parquet_v1"
DEFAULT_ASSET_PARQUET_DIR = RESOURCES_DIR / "assets_merged"
CODE_NAME_MAPPING_FILE = "code_name_mapping.parquet"
ProgressCallback = Callable[[str], None]
SourceInfo = dict[str, Any]
CodeNameMapping = dict[str, str]

SHEET_ACCOUNT_NAMES = {
    "종가": "stock_price",
    "시가": "open_price",
    "고가": "high_price",
    "저가": "low_price",
    "수정종가": "adjusted_stock_price",
    "수정시가": "adjusted_open_price",
    "수정고가": "adjusted_high_price",
    "수정저가": "adjusted_low_price",
    "거래량": "volume",
    "거래량(NXT)": "nxt_volume",
    "거래대금": "trading_value",
    "거래대금(NXT)": "nxt_trading_value",
    "저가(NXT)": "nxt_low_price",
    "고가(NXT)": "nxt_high_price",
    "시가(NXT)": "nxt_open_price",
    "종가(NXT)": "nxt_stock_price",
    "거래정지사유": "trading_halt_reason",
    "거래정지여부": "trading_halt_flag",
    "거래정지구분": "trading_halt_category",
    "관리감리구분": "management_supervision_category",
    "지수산정주식수": "index_constituent_shares",
    "최대주주명": "major_shareholder_name",
    "최대주주보유보통주주식수": "major_shareholder_common_shares",
    "최대주주보유보통주지분율": "major_shareholder_common_ownership_ratio",
    "대차거래잔고수량": "stock_lending_balance_volume",
    "대차거래상환량": "stock_lending_repayment_volume",
    "대차거래체결량": "stock_lending_transaction_volume",
    "차입공매도잔고수량": "borrowed_short_selling_balance_volume",
    "차입공매도수량": "borrowed_short_selling_volume",
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


def _normalize_label(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return unicodedata.normalize("NFC", str(value or "")).strip()


def _account_name_for_sheet(sheet_name: str) -> str | None:
    return SHEET_ACCOUNT_NAMES.get(_normalize_label(sheet_name))


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


def inspect_asset_excel_output(output_directory: str | Path = DEFAULT_ASSET_PARQUET_DIR) -> dict[str, Any]:
    output = Path(output_directory).expanduser().resolve()
    manifest_path = output / "manifest.json"
    parquet_files = [
        path
        for path in sorted(output.glob("*.parquet")) if path.name != CODE_NAME_MAPPING_FILE
    ] if output.is_dir() else []
    code_name_mapping_path = output / CODE_NAME_MAPPING_FILE
    manifest: dict[str, Any] | None = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = None
    return {
        "output_directory": str(output),
        "exists": output.exists(),
        "manifest_path": str(manifest_path),
        "manifest_exists": manifest_path.exists(),
        "parquet_files": [path.name for path in parquet_files],
        "account_count": len(parquet_files),
        "code_name_mapping_path": str(code_name_mapping_path),
        "code_name_mapping_exists": code_name_mapping_path.exists(),
        "code_name_mapping_rows": manifest.get("code_name_mapping", {}).get("rows", 0) if manifest else 0,
        "format": manifest.get("format") if manifest else "",
        "accounts": manifest.get("accounts", {}) if manifest else {},
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
    excel = pd.ExcelFile(target)
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

    frame = pd.read_excel(target, sheet_name=selected_sheet, dtype=object, nrows=nrows)

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
    excel = pd.ExcelFile(target)
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
    frame: pd.DataFrame | None = None,
    reason: str = "",
) -> dict[str, Any]:
    resolved_account_name = _account_name_for_sheet(sheet_name) if account_name is None else account_name
    status = "mapped"
    if resolved_account_name is None:
        status = "unmapped"
        reason = reason or "No account-name mapping"
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
    raw_frame = pd.read_excel(
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
    raw_frame = pd.read_excel(xlsx_path, sheet_name=sheet_name, header=None, dtype=object)
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

    for column in common_columns:
        existing_series = existing.loc[common_dates, column]
        incoming_series = incoming.loc[common_dates, column]
        candidate_dates = common_dates[existing_series.notna() & incoming_series.notna()]
        for row_date in candidate_dates:
            existing_value = existing_series.loc[row_date]
            incoming_value = incoming_series.loc[row_date]
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


def _account_quality_payload(frame: pd.DataFrame, sample_limit: int = 3) -> dict[str, Any]:
    if frame.empty:
        return {
            "non_null_cells": 0,
            "total_cells": 0,
            "missing_ratio": 0,
            "sample_rows": [],
        }
    total_cells = int(frame.shape[0] * frame.shape[1])
    non_null_cells = int(frame.notna().sum().sum())
    preview = frame.tail(max(0, int(sample_limit))).reset_index()
    preview.columns = [str(column) for column in preview.columns]
    return {
        "non_null_cells": non_null_cells,
        "total_cells": total_cells,
        "missing_ratio": round(1 - (non_null_cells / total_cells), 6) if total_cells else 0,
        "sample_rows": _json_rows(preview),
    }


def _merge_account_frames(
    account_name: str,
    frames: list[tuple[pd.DataFrame, SourceInfo]],
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
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


def _code_name_mapping_frame(mappings: list[CodeNameMapping]) -> pd.DataFrame:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
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
                "source_files": set(),
                "source_sheets": set(),
            },
        )
        if mapping.get("file_name"):
            row["source_files"].add(str(mapping["file_name"]))
        if mapping.get("sheet_name"):
            row["source_sheets"].add(str(mapping["sheet_name"]))

    payload = [
        {
            "code": row["code"],
            "name": row["name"],
            "source_files": ", ".join(sorted(row["source_files"])),
            "source_sheets": ", ".join(sorted(row["source_sheets"])),
        }
        for row in rows.values()
    ]
    return pd.DataFrame(payload, columns=["code", "name", "source_files", "source_sheets"]).sort_values(
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
                "file_name": CODE_NAME_MAPPING_FILE,
                "sheet_name": "__existing_mapping__",
            }
        )
    return mappings


def _existing_account_frame(
    account_name: str,
    output_directory: Path,
    output_info: dict[str, Any],
    *,
    source_type: str = "existing_output",
) -> tuple[pd.DataFrame, SourceInfo] | None:
    parquet_path = output_directory / f"{account_name}.parquet"
    if not parquet_path.exists():
        return None
    frame = pd.read_parquet(parquet_path)
    if "date" not in frame.columns:
        return None
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
    frame = frame.dropna(subset=["date"]).set_index("date")
    account_meta = output_info.get("accounts", {}).get(account_name, {})
    source_info = {
        "file_name": parquet_path.name,
        "sheet_name": "__existing_parquet__",
        "date_start": frame.index.min().isoformat() if len(frame.index) else "",
        "date_end": frame.index.max().isoformat() if len(frame.index) else "",
        "date_index": _date_index_payload(frame.index),
        "date_segments": account_meta.get("date_segments") or _single_date_segment_payload(frame.index),
        "rows": len(frame),
        "columns": len(frame.columns),
        "source_directory": str(output_directory),
        "source_type": source_type,
    }
    return frame, source_info


def _parquet_account_names(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return [
        path.stem
        for path in sorted(directory.glob("*.parquet"))
        if path.name != CODE_NAME_MAPPING_FILE
    ]


def _scan_asset_excel_frames(
    source_directory: str | Path,
    *,
    selected_files: list[str] | None = None,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[
    dict[str, list[tuple[pd.DataFrame, SourceInfo]]],
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

    frames_by_account: dict[str, list[tuple[pd.DataFrame, SourceInfo]]] = {}
    sources_by_account: dict[str, list[SourceInfo]] = {}
    skipped: list[dict[str, str]] = []
    sheet_summaries: list[dict[str, Any]] = []
    code_name_mappings: list[CodeNameMapping] = []

    for file_index, xlsx_path in enumerate(xlsx_files, start=1):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        _emit(progress_callback, f"[파일 {file_index}/{len(xlsx_files)}] {xlsx_path.name} 스캔 중...")
        excel = pd.ExcelFile(xlsx_path)
        for sheet_index, sheet_name in enumerate(excel.sheet_names, start=1):
            if cancel_check and cancel_check():
                raise RuntimeError("Job cancelled")
            _emit(progress_callback, f"[Sheet {sheet_index}/{len(excel.sheet_names)}] {xlsx_path.name} / {sheet_name}")
            account_name = _account_name_for_sheet(sheet_name)
            if account_name is None:
                summary = _sheet_summary_payload(
                    xlsx_path,
                    sheet_name,
                    source_directory=source,
                    account_name=account_name,
                )
                skipped.append(
                    {
                        "file_name": xlsx_path.name,
                        "relative_path": str(xlsx_path.relative_to(source)),
                        "sheet_name": sheet_name,
                        "reason": summary["reason"],
                        "status": summary["status"],
                    }
                )
                sheet_summaries.append(summary)
                continue
            try:
                frame, mappings = _read_quanti_wide_sheet_with_mapping(excel, sheet_name)
            except ValueError as exc:
                summary = _sheet_summary_payload(
                    xlsx_path,
                    sheet_name,
                    source_directory=source,
                    account_name=account_name,
                    reason=str(exc),
                )
                skipped.append(
                    {
                        "file_name": xlsx_path.name,
                        "relative_path": str(xlsx_path.relative_to(source)),
                        "sheet_name": sheet_name,
                        "reason": summary["reason"],
                        "status": summary["status"],
                    }
                )
                sheet_summaries.append(summary)
                continue
            code_name_mappings.extend(mappings)
            source_info = {
                "file_name": xlsx_path.name,
                "relative_path": str(xlsx_path.relative_to(source)),
                "sheet_name": sheet_name,
                "date_start": frame.index.min().isoformat() if len(frame.index) else "",
                "date_end": frame.index.max().isoformat() if len(frame.index) else "",
                "date_index": _date_index_payload(frame.index),
                "date_segments": _single_date_segment_payload(frame.index),
                "rows": len(frame),
                "columns": len(frame.columns),
            }
            frames_by_account.setdefault(account_name, []).append((frame, source_info))
            sources_by_account.setdefault(account_name, []).append(source_info)
            sheet_summaries.append(
                _sheet_summary_payload(
                    xlsx_path,
                    sheet_name,
                    source_directory=source,
                    account_name=account_name,
                    frame=frame,
                )
            )
    return frames_by_account, sources_by_account, skipped, sheet_summaries, code_name_mappings


def _date_index_payload(index: pd.Index) -> list[str]:
    return [
        value.isoformat() if hasattr(value, "isoformat") else str(value)
        for value in index
    ]


def _single_date_segment_payload(index: pd.Index) -> list[dict[str, Any]]:
    values = sorted(index)
    if not values:
        return []
    return [
        {
            "start": values[0].isoformat(),
            "end": values[-1].isoformat(),
            "count": len(values),
        }
    ]


def _ranges_are_continuous(previous_end: date, next_start: date) -> bool:
    if next_start <= previous_end + timedelta(days=1):
        return True
    missing_dates = [
        previous_end + timedelta(days=offset)
        for offset in range(1, (next_start - previous_end).days)
    ]
    return bool(missing_dates) and all(value.weekday() >= 5 for value in missing_dates)


def _merged_date_segments_payload(index: pd.Index, sources: list[SourceInfo]) -> list[dict[str, Any]]:
    ranges: list[tuple[date, date]] = []
    for source in sources:
        for segment in source.get("date_segments", []):
            ranges.append(
                (
                    date.fromisoformat(str(segment["start"])),
                    date.fromisoformat(str(segment["end"])),
                )
            )
    if not ranges:
        return []

    merged_ranges: list[tuple[date, date]] = []
    for start, end in sorted(ranges):
        if not merged_ranges:
            merged_ranges.append((start, end))
            continue
        previous_start, previous_end = merged_ranges[-1]
        if _ranges_are_continuous(previous_end, start):
            merged_ranges[-1] = (previous_start, max(previous_end, end))
        else:
            merged_ranges.append((start, end))

    date_values = set(index)
    return [
        {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "count": sum(1 for value in date_values if start <= value <= end),
        }
        for start, end in merged_ranges
    ]


def convert_asset_excels_to_wide_parquet(
    source_directory: str | Path = QUANTIWISE_EXCEL_DIR,
    output_directory: str | Path = DEFAULT_ASSET_PARQUET_DIR,
    *,
    selected_files: list[str] | None = None,
    write_mode: str = "replace",
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

    frames_by_account, sources_by_account, skipped, sheet_summaries, code_name_mappings = _scan_asset_excel_frames(
        source,
        selected_files=selected_files,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )
    output_info = inspect_asset_excel_output(output)
    updated_accounts: list[str] = []
    if normalized_mode == "update" and output_info["parquet_files"]:
        code_name_mappings = [*_existing_code_name_mappings(output), *code_name_mappings]
        for account_name in sorted(set(frames_by_account) | set(output_info.get("accounts", {}))):
            existing = _existing_account_frame(account_name, output, output_info)
            if existing is None:
                continue
            frame, source_info = existing
            frames_by_account.setdefault(account_name, []).insert(0, (frame, source_info))
            sources_by_account.setdefault(account_name, []).insert(0, source_info)
            updated_accounts.append(account_name)

    merged_by_account: dict[str, pd.DataFrame] = {}
    conflicts_by_account: dict[str, list[dict[str, str]]] = {}
    for account_name, frames in sorted(frames_by_account.items()):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        _emit(progress_callback, f"Merging {account_name}...")
        merged, conflicts = _merge_account_frames(account_name, frames)
        merged_by_account[account_name] = merged
        if conflicts:
            conflicts_by_account[account_name] = conflicts

    accounts: dict[str, Any] = {}
    for account_name, merged in sorted(merged_by_account.items()):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        _emit(progress_callback, f"Saving {account_name}.parquet...")
        parquet_path = output / f"{account_name}.parquet"
        merged.reset_index().to_parquet(parquet_path, index=False, compression="snappy")
        accounts[account_name] = {
            "path": str(parquet_path),
            "rows": len(merged),
            "columns": len(merged.columns),
            "date_start": merged.index.min().isoformat() if len(merged.index) else "",
            "date_end": merged.index.max().isoformat() if len(merged.index) else "",
            "date_index": _date_index_payload(merged.index),
            "date_segments": _merged_date_segments_payload(
                merged.index,
                sources_by_account.get(account_name, []),
            ),
            "sources": sources_by_account.get(account_name, []),
            "quality": _account_quality_payload(merged),
        }

    code_name_mapping = _code_name_mapping_frame(code_name_mappings)
    code_name_mapping_path = output / CODE_NAME_MAPPING_FILE
    code_name_mapping.to_parquet(code_name_mapping_path, index=False, compression="snappy")

    manifest = {
        "format": ASSET_PARQUET_FORMAT,
        "source_directory": str(source),
        "output_directory": str(output),
        "write_mode": normalized_mode,
        "conflict_policy": "error",
        "selected_files": selected_files or [],
        "code_name_mapping": {
            "path": str(code_name_mapping_path),
            "rows": len(code_name_mapping),
        },
        "accounts": accounts,
        "conflicts": conflicts_by_account,
        "skipped": skipped,
        "sheets": sheet_summaries,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "status": "completed",
        "output_directory": str(output),
        "manifest_path": str(manifest_path),
        "accounts_processed": len(accounts),
        "write_mode": normalized_mode,
        "conflict_policy": "error",
        "code_name_mapping": {
            "path": str(code_name_mapping_path),
            "rows": len(code_name_mapping),
        },
        "updated_accounts": updated_accounts,
        "accounts": accounts,
        "conflicts": conflicts_by_account,
        "skipped": skipped,
        "sheets": sheet_summaries,
    }


def merge_asset_parquet_outputs(
    base_directory: str | Path,
    incoming_directory: str | Path,
    output_directory: str | Path = DEFAULT_ASSET_PARQUET_DIR,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Merge two generated Quantiwise Parquet output directories."""
    base = Path(base_directory).expanduser().resolve()
    incoming = Path(incoming_directory).expanduser().resolve()
    output = Path(output_directory).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    base_info = inspect_asset_excel_output(base)
    incoming_info = inspect_asset_excel_output(incoming)
    base_accounts = _parquet_account_names(base)
    incoming_accounts = _parquet_account_names(incoming)
    if not base_accounts:
        msg = f"No account Parquet files found in {base}"
        raise ValueError(msg)
    if not incoming_accounts:
        msg = f"No account Parquet files found in {incoming}"
        raise ValueError(msg)

    frames_by_account: dict[str, list[tuple[pd.DataFrame, SourceInfo]]] = {}
    sources_by_account: dict[str, list[SourceInfo]] = {}
    for source_dir, output_info, account_names, source_type in (
        (base, base_info, base_accounts, "base_parquet"),
        (incoming, incoming_info, incoming_accounts, "incoming_parquet"),
    ):
        for account_name in sorted(account_names):
            if cancel_check and cancel_check():
                raise RuntimeError("Job cancelled")
            _emit(progress_callback, f"Reading {source_dir.name}/{account_name}.parquet...")
            loaded = _existing_account_frame(
                account_name,
                source_dir,
                output_info,
                source_type=source_type,
            )
            if loaded is None:
                continue
            frame, source_info = loaded
            frames_by_account.setdefault(account_name, []).append((frame, source_info))
            sources_by_account.setdefault(account_name, []).append(source_info)

    code_name_mapping = _code_name_mapping_frame([
        *_existing_code_name_mappings(base),
        *_existing_code_name_mappings(incoming),
    ])
    code_name_mapping_path = output / CODE_NAME_MAPPING_FILE
    code_name_mapping.to_parquet(code_name_mapping_path, index=False, compression="snappy")

    accounts: dict[str, Any] = {}
    conflicts_by_account: dict[str, list[dict[str, str]]] = {}
    for account_name, frames in sorted(frames_by_account.items()):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        _emit(progress_callback, f"Merging {account_name}...")
        merged, conflicts = _merge_account_frames(account_name, frames)
        if conflicts:
            conflicts_by_account[account_name] = conflicts
        parquet_path = output / f"{account_name}.parquet"
        merged.reset_index().to_parquet(parquet_path, index=False, compression="snappy")
        accounts[account_name] = {
            "path": str(parquet_path),
            "rows": len(merged),
            "columns": len(merged.columns),
            "date_start": merged.index.min().isoformat() if len(merged.index) else "",
            "date_end": merged.index.max().isoformat() if len(merged.index) else "",
            "date_index": _date_index_payload(merged.index),
            "date_segments": _merged_date_segments_payload(
                merged.index,
                sources_by_account.get(account_name, []),
            ),
            "sources": sources_by_account.get(account_name, []),
            "quality": _account_quality_payload(merged),
        }

    manifest = {
        "format": ASSET_PARQUET_FORMAT,
        "operation": "merge_parquet",
        "base_directory": str(base),
        "incoming_directory": str(incoming),
        "output_directory": str(output),
        "conflict_policy": "error",
        "code_name_mapping": {
            "path": str(code_name_mapping_path),
            "rows": len(code_name_mapping),
        },
        "accounts": accounts,
        "conflicts": conflicts_by_account,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "status": "completed",
        "operation": "merge_parquet",
        "base_directory": str(base),
        "incoming_directory": str(incoming),
        "output_directory": str(output),
        "manifest_path": str(manifest_path),
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
    write_mode: str = "replace",
) -> dict[str, Any]:
    source = Path(source_directory).expanduser().resolve()
    output = Path(output_directory).expanduser().resolve()
    frames_by_account, sources_by_account, skipped, sheet_summaries, code_name_mappings = _scan_asset_excel_frames(
        source,
        selected_files=selected_files,
    )
    output_info = inspect_asset_excel_output(output)
    normalized_mode = str(write_mode or "replace").strip().lower()

    if normalized_mode == "update" and output_info["parquet_files"]:
        code_name_mappings = [*_existing_code_name_mappings(output), *code_name_mappings]
        for account_name in sorted(set(frames_by_account) | set(output_info.get("accounts", {}))):
            existing = _existing_account_frame(account_name, output, output_info)
            if existing is None:
                continue
            frame, source_info = existing
            frames_by_account.setdefault(account_name, []).insert(0, (frame, source_info))
            sources_by_account.setdefault(account_name, []).insert(0, source_info)

    accounts: dict[str, Any] = {}
    conflicts_by_account: dict[str, list[dict[str, str]]] = {}
    for account_name, frames in sorted(frames_by_account.items()):
        try:
            merged, conflicts = _merge_account_frames(account_name, frames)
        except ValueError as exc:
            merged, conflicts = pd.DataFrame(), [{"message": str(exc)}]
        if conflicts:
            conflicts_by_account[account_name] = conflicts
        accounts[account_name] = {
            "output_file": f"{account_name}.parquet",
            "rows": len(merged) if not merged.empty else sum(len(frame) for frame, _ in frames),
            "columns": len(merged.columns) if not merged.empty else max((len(frame.columns) for frame, _ in frames), default=0),
            "source_count": len(frames),
            "date_segments": _merged_date_segments_payload(
                merged.index if not merged.empty else pd.Index([]),
                sources_by_account.get(account_name, []),
            ),
            "will_update_existing": any(
                source.get("source_type") == "existing_output"
                for _, source in frames
            ),
            "quality": _account_quality_payload(merged),
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
        "accounts": accounts,
        "skipped": skipped,
        "conflicts": conflicts_by_account,
        "output": output_info,
    }


__all__ = [
    "DEFAULT_ASSET_PARQUET_DIR",
    "SHEET_ACCOUNT_NAMES",
    "convert_asset_excels_to_wide_parquet",
    "inspect_asset_excel_conversion",
    "inspect_asset_excel_output",
    "list_asset_excel_files",
    "merge_asset_parquet_outputs",
    "read_asset_excel",
    "read_asset_excel_interpreted",
    "read_asset_excel_sheets",
]
