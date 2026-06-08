"""Utility actions for local data files."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any, Callable


ProgressCallback = Callable[[str], None] | None


def _year_from_filename(path: Path) -> str | None:
    prefix = path.name[:4]
    if len(prefix) == 4 and prefix.isdigit():
        return prefix
    return None


def _copy_file(source: Path, target: Path, *, overwrite: bool) -> str:
    if target.exists() and not overwrite:
        return "skipped_existing"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return "copied"


def _copy_flat_to_year_directories(
    source_directory: Path,
    output_directory: Path,
    *,
    overwrite: bool,
    progress_callback: ProgressCallback,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    files = sorted(path for path in source_directory.iterdir() if path.is_file())
    copied = 0
    skipped_existing = 0
    skipped_invalid_year = 0
    years: set[str] = set()

    for index, source_path in enumerate(files, start=1):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        year = _year_from_filename(source_path)
        if year is None:
            skipped_invalid_year += 1
            continue

        result = _copy_file(source_path, output_directory / year / source_path.name, overwrite=overwrite)
        years.add(year)
        if result == "copied":
            copied += 1
        else:
            skipped_existing += 1

        if progress_callback and (index == len(files) or index % 100 == 0):
            progress_callback(f"분할저장 변환 중: {index}/{len(files)}개 검사.")

    return {
        "mode": "split",
        "source_directory": str(source_directory),
        "output_directory": str(output_directory),
        "input_files": len(files),
        "copied_files": copied,
        "skipped_existing_files": skipped_existing,
        "skipped_invalid_year_files": skipped_invalid_year,
        "years": sorted(years),
    }


def _copy_year_directories_to_flat(
    source_directory: Path,
    output_directory: Path,
    *,
    overwrite: bool,
    progress_callback: ProgressCallback,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    year_directories = [
        path
        for path in sorted(source_directory.iterdir())
        if path.is_dir() and len(path.name) == 4 and path.name.isdigit()
    ]
    files = [
        path
        for year_directory in year_directories
        for path in sorted(year_directory.iterdir())
        if path.is_file()
    ]
    copied = 0
    skipped_existing = 0

    for index, source_path in enumerate(files, start=1):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        result = _copy_file(source_path, output_directory / source_path.name, overwrite=overwrite)
        if result == "copied":
            copied += 1
        else:
            skipped_existing += 1

        if progress_callback and (index == len(files) or index % 100 == 0):
            progress_callback(f"분할저장 해제 중: {index}/{len(files)}개 검사.")

    return {
        "mode": "flatten",
        "source_directory": str(source_directory),
        "output_directory": str(output_directory),
        "input_files": len(files),
        "copied_files": copied,
        "skipped_existing_files": skipped_existing,
        "skipped_invalid_year_files": 0,
        "years": [path.name for path in year_directories],
    }


def run_partition_storage_payload(
    payload: dict[str, Any],
    *,
    progress_callback: ProgressCallback = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    mode = str(payload.get("mode") or "").strip()
    if mode not in {"split", "flatten"}:
        raise ValueError("mode must be one of: split, flatten")

    source_raw = str(payload.get("source_directory") or "").strip()
    output_raw = str(payload.get("output_directory") or "").strip()
    if not source_raw:
        raise ValueError("source_directory is required")
    if not output_raw:
        raise ValueError("output_directory is required")

    source_directory = Path(source_raw).expanduser().resolve()
    output_directory = Path(output_raw).expanduser().resolve()
    if not source_directory.is_dir():
        raise ValueError(f"source_directory is not a directory: {source_directory}")

    overwrite = bool(payload.get("overwrite"))
    if progress_callback:
        progress_callback("분할저장 유틸리티 작업을 시작합니다.")

    if mode == "split":
        result = _copy_flat_to_year_directories(
            source_directory,
            output_directory,
            overwrite=overwrite,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
    else:
        result = _copy_year_directories_to_flat(
            source_directory,
            output_directory,
            overwrite=overwrite,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    if progress_callback:
        progress_callback(
            f"완료: {result['copied_files']}개 복사, "
            f"{result['skipped_existing_files']}개 기존 파일 건너뜀."
        )
    return result



__all__ = ["run_partition_storage_payload"]
