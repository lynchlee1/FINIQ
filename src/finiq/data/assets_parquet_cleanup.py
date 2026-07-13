"""Duplicate cleanup helpers for generated Quantiwise asset Parquet files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

import pandas as pd


def _asset_parquet_delete_confirmed(
    delete_confirmed: bool,
    delete_confirmation_text_input: str,
    delete_confirmation_text: str,
) -> bool:
    return delete_confirmed and str(delete_confirmation_text_input or "").strip() == delete_confirmation_text


def _duplicate_base_file_name(file_name: str) -> str | None:
    match = re.match(r"^(?P<base>.+)__\d+(?P<suffix>\.parquet)$", file_name, re.IGNORECASE)
    return f"{match.group('base')}{match.group('suffix')}" if match else None


def _duplicate_suffix_index(file_name: str) -> int:
    match = re.search(r"__(\d+)\.parquet$", file_name, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def _comparison_frame(
    path: Path,
    account_output_payload: Callable[[Path], dict[str, Any]],
) -> tuple[dict[str, Any], pd.DataFrame]:
    payload = account_output_payload(path)
    frame = pd.read_parquet(path)
    if "date" not in frame.columns:
        raise ValueError("Missing date column")
    raw_dates = frame["date"]
    parsed_dates = pd.to_datetime(raw_dates, errors="coerce")
    populated_date_mask = raw_dates.notna() & raw_dates.astype(str).str.strip().ne("")
    if (populated_date_mask & parsed_dates.isna()).any():
        raise ValueError("Invalid date value")
    frame["date"] = parsed_dates.dt.date
    frame = frame.dropna(subset=["date"]).set_index("date")
    if frame.index.duplicated().any():
        raise ValueError("Duplicate date axis")
    frame.columns = [str(column) for column in frame.columns]
    if frame.columns.duplicated().any():
        raise ValueError("Duplicate code axis")
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
    delete_confirmation_text_input: str = "",
    scan_recursive: bool = False,
    progress_callback: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    emit: Callable[[Callable[[str], None] | None, str], None],
    account_output_payload: Callable[[Path], dict[str, Any]],
    account_name_from_output_stem: Callable[[str], str],
    non_account_parquet_files: set[str],
    delete_confirmation_text: str,
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

    emit(progress_callback, "중복 검사 시작")
    emit(progress_callback, f"병합 대상 경로: {target}")
    emit(progress_callback, f"내부까지 검사: {'On' if scan_recursive else 'Off'}")
    emit(progress_callback, f"검사 폴더: {len(scan_directories)}개")

    items_by_account: dict[str, list[dict[str, Any]]] = {}
    load_errors: list[dict[str, str]] = []
    for directory in scan_directories:
        for path in sorted(directory.glob("*.parquet")):
            if cancel_check and cancel_check():
                raise RuntimeError("Job cancelled")
            if path.name in non_account_parquet_files:
                continue
            try:
                payload, frame = _comparison_frame(path, account_output_payload)
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
            account_name = str(payload.get("account_name") or account_name_from_output_stem(path.stem))
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
        emit(progress_callback, f"중복 후보 검사: 계정={account_name}, 파일 {len(items)}개")
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

    if not dry_run and deletion_candidates and not _asset_parquet_delete_confirmed(
        delete_confirmed,
        delete_confirmation_text_input,
        delete_confirmation_text,
    ):
        raise ValueError(f'파일 삭제 전 "{delete_confirmation_text}" 입력과 삭제 허가가 필요합니다.')

    deleted_files: list[dict[str, str]] = []
    if not dry_run:
        for item in deletion_candidates:
            path = Path(item["path"])
            if path.exists():
                path.unlink()
            deleted_files.append(item)

    emit(
        progress_callback,
        (
            "중복 검사 완료: "
            f"삭제 후보 {len(deletion_candidates)}개, "
            f"포함 불가 {len(mismatched_duplicates)}개"
        ),
    )
    if not dry_run:
        emit(progress_callback, f"중복 삭제 완료: {len(deleted_files)}개")

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
