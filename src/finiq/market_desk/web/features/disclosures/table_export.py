"""Build SQLite disclosure tables from canonical KIND result folders."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from finiq.concurrency import resolve_worker_count
from finiq.data_scraper.storage.result_files import result_page_number
from finiq.data_scraper.workflow import validate_kind_workflow_input_snapshot
from finiq.market_desk.sqlite_generation import sqlite_generation_locked
from finiq.market_desk.web.features.market_data.service_sources import (
    _load_sqlite_manifest,
    _parse_source_body_page_file,
    _sqlite_manifest_content_fingerprints,
    _validate_sqlite_manifest_content_fingerprint,
    _validate_sqlite_manifest_counts,
)

TABLE_SCHEMA_VERSION = 3
DEFAULT_TABLE_NAME = "disclosures"
MANIFEST_FORMAT = "finiq_disclosure_table_manifest_v1"
MANIFEST_FILENAME = "sqlite_manifest.json"
SQLITE_FORMAT = "finiq_disclosure_table_sqlite_shard"


@dataclass(frozen=True)
class _SourceInventory:
    source_path: Path
    source_folders: tuple[Path, ...]
    body_paths: tuple[Path, ...]
    body_paths_by_folder: dict[Path, tuple[Path, ...]]
    page_number_by_path: dict[Path, int]
    page_count_by_folder: dict[Path, int]


def _date_part(value: object) -> str:
    return str(value or "").strip().split(" ", 1)[0]


def _validated_disclosed_date(value: object) -> str:
    disclosed_date = _date_part(value)
    try:
        parsed = date.fromisoformat(disclosed_date)
    except ValueError as exc:
        raise ValueError(
            "disclosed_at must begin with a valid YYYY-MM-DD calendar date: "
            f"{value!r}"
        ) from exc
    if parsed.isoformat() != disclosed_date:
        raise ValueError(
            "disclosed_at must begin with a valid YYYY-MM-DD calendar date: "
            f"{value!r}"
        )
    return disclosed_date


def _normalize_table_name(value: object) -> str:
    table_name = str(value or DEFAULT_TABLE_NAME).strip()
    if not table_name:
        return DEFAULT_TABLE_NAME
    if not table_name.replace("_", "").isalnum() or table_name[0].isdigit():
        msg = "table_name must contain only letters, numbers, and underscores, and must not start with a digit"
        raise ValueError(msg)
    return table_name


def _shard_directory(manifest_path: Path) -> Path:
    return manifest_path.parent


def _manifest_output_path(raw_path: str) -> Path:
    if not raw_path:
        raise ValueError("output_path is required")
    output_path = Path(raw_path).expanduser().resolve()
    if output_path.suffix:
        return output_path.with_name(MANIFEST_FILENAME)
    return output_path / MANIFEST_FILENAME


def _build_source_inventory(
    root_directory: str,
    *,
    cancel_check: Callable[[], bool] | None,
) -> _SourceInventory:
    if not root_directory:
        raise ValueError("root_directory is required")
    source_path = Path(root_directory).expanduser().resolve()
    if not source_path.is_dir():
        raise FileNotFoundError(f"KIND source directory not found: {source_path}")

    metadata_folders: set[Path] = set()
    body_paths_by_folder: dict[Path, list[Path]] = {}
    page_number_by_path: dict[Path, int] = {}
    for directory, directory_names, filenames in os.walk(source_path):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        directory_names[:] = [
            name for name in directory_names if not name.startswith(".")
        ]
        folder = Path(directory).resolve()
        if "kind_workflow.input.json" in filenames:
            metadata_folders.add(folder)
        for filename in filenames:
            if "_post_page_" not in filename or not filename.endswith(".body"):
                continue
            body_path = folder / filename
            page_number_by_path[body_path] = result_page_number(body_path)
            body_paths_by_folder.setdefault(folder, []).append(body_path)

    if not body_paths_by_folder:
        raise ValueError(f"KIND body files not found: {source_path}")

    source_folders = tuple(sorted(metadata_folders | set(body_paths_by_folder)))
    body_paths: list[Path] = []
    sorted_body_paths_by_folder: dict[Path, tuple[Path, ...]] = {}
    page_count_by_folder: dict[Path, int] = {}
    for folder in source_folders:
        folder_paths = sorted(
            body_paths_by_folder.get(folder, []),
            key=lambda path: (page_number_by_path[path], path.name),
        )
        body_paths.extend(folder_paths)
        sorted_body_paths_by_folder[folder] = tuple(folder_paths)
        page_count_by_folder[folder] = len(folder_paths)
    return _SourceInventory(
        source_path=source_path,
        source_folders=source_folders,
        body_paths=tuple(body_paths),
        body_paths_by_folder=sorted_body_paths_by_folder,
        page_number_by_path=page_number_by_path,
        page_count_by_folder=page_count_by_folder,
    )


def _row_year(row: dict[str, Any]) -> str:
    disclosed_date = str(row.get("disclosed_date") or "").strip()
    year = disclosed_date[:4]
    if len(year) == 4 and year.isdigit():
        return year
    raise ValueError(f"disclosed_date must begin with a four-digit year: {disclosed_date!r}")


def _collect_source_folder_rows_by_year(
    inventory: _SourceInventory,
    cancel_check: Callable[[], bool] | None = None,
    worker_count: int = 1,
) -> tuple[
    dict[str, list[dict[str, Any]]],
    int,
    int,
    int,
    int,
    int,
    list[dict[str, Any]],
]:
    rows_by_year: dict[str, list[dict[str, Any]]] = {}
    seen_acpt_nos: set[str] = set()
    company_keys: set[str] = set()
    pages: list[dict[str, Any]] = []
    row_count = 0
    source_row_count = 0
    duplicate_row_count = 0
    unlinked_disclosure_count = 0
    source_folder = inventory.source_path
    body_paths = inventory.body_paths
    source_pagination: dict[Path, tuple[int, int]] = {}
    source_rows_by_folder: dict[Path, int] = {}

    def iter_page_records():
        if worker_count <= 1 or len(body_paths) <= 1:
            for body_path in body_paths:
                yield body_path, _read_source_page_records(
                    body_path,
                    source_page=inventory.page_number_by_path[body_path],
                    cancel_check=cancel_check,
                )
            return

        batch_size = worker_count * 2
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="kind-table-source",
        ) as executor:
            for offset in range(0, len(body_paths), batch_size):
                batch = body_paths[offset : offset + batch_size]
                records_batch = executor.map(
                    lambda path: _read_source_page_records(
                        path,
                        source_page=inventory.page_number_by_path[path],
                        cancel_check=cancel_check,
                    ),
                    batch,
                )
                yield from zip(batch, records_batch)

    for body_path, (records, paging) in iter_page_records():
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        _validate_source_page_pagination(
            body_path,
            paging,
            page_number_by_path=inventory.page_number_by_path,
            page_count_by_folder=inventory.page_count_by_folder,
            source_pagination=source_pagination,
        )
        page_source_rows = 0
        page_written_rows = 0
        page_duplicate_rows = 0
        for record in records:
            source_row_count += 1
            page_source_rows += 1
            acpt_no = str(record.get("acpt_no") or "").strip()
            if acpt_no in seen_acpt_nos:
                duplicate_row_count += 1
                page_duplicate_rows += 1
                continue
            seen_acpt_nos.add(acpt_no)
            disclosed_at = record.get("disclosed_at")
            disclosed_date = _validated_disclosed_date(disclosed_at)
            row = {
                "row_no": record.get("row_no"),
                "company_key": record.get("company_key"),
                "company_name": record.get("company_name"),
                "company_id": record.get("company_id"),
                "company_cell_text": record.get("company_cell_text"),
                "market": record.get("market"),
                "badges_json": json.dumps(
                    list(record.get("badges") or []), ensure_ascii=False
                ),
                "disclosed_at": disclosed_at,
                "disclosed_date": disclosed_date,
                "title": record.get("title"),
                "title_attr": record.get("title_attr"),
                "title_base": record.get("title_base"),
                "title_display": record.get("title_display"),
                "title_flags_json": json.dumps(
                    list(record.get("title_flags") or []), ensure_ascii=False
                ),
                "is_correction_report": 1 if record.get("is_correction_report") else 0,
                "has_later_correction": 1 if record.get("has_later_correction") else 0,
                "acpt_no": acpt_no,
                "doc_no": record.get("doc_no"),
                "submitter": record.get("submitter"),
                "source_file": record.get("source_file"),
                "source_page": record.get("source_page"),
            }
            company_key = str(row.get("company_key") or "").strip()
            if company_key:
                company_keys.add(company_key)
            else:
                unlinked_disclosure_count += 1
            rows_by_year.setdefault(_row_year(row), []).append(row)
            row_count += 1
            page_written_rows += 1
        folder = body_path.parent.resolve()
        source_rows_by_folder[folder] = (
            source_rows_by_folder.get(folder, 0) + page_source_rows
        )
        page_number = inventory.page_number_by_path[body_path]
        pages.append(
            {
                "source_file": body_path.relative_to(source_folder).as_posix(),
                "source_page": page_number,
                "source_rows": page_source_rows,
                "written_rows": page_written_rows,
                "duplicate_rows": page_duplicate_rows,
            }
        )
    _validate_source_folder_row_totals(
        source_pagination,
        source_rows_by_folder=source_rows_by_folder,
    )
    return (
        rows_by_year,
        len(company_keys),
        row_count,
        source_row_count,
        duplicate_row_count,
        unlinked_disclosure_count,
        pages,
    )


def _inspect_source_folder_counts(
    inventory: _SourceInventory,
    *,
    worker_count: int,
) -> tuple[
    dict[str, tuple[int, int]],
    int,
    int,
    int,
    int,
    int,
    list[dict[str, Any]],
]:
    """Count source rows without retaining disclosure records in memory."""
    shard_counts: dict[str, tuple[int, int]] = {}
    seen_acpt_nos: set[str] = set()
    company_keys: set[str] = set()
    pages: list[dict[str, Any]] = []
    row_count = 0
    source_row_count = 0
    duplicate_row_count = 0
    unlinked_disclosure_count = 0
    source_folder = inventory.source_path
    body_paths = inventory.body_paths
    source_pagination: dict[Path, tuple[int, int]] = {}
    source_rows_by_folder: dict[Path, int] = {}

    def iter_page_records():
        if worker_count <= 1 or len(body_paths) <= 1:
            for body_path in body_paths:
                yield body_path, _read_source_page_records(
                    body_path,
                    source_page=inventory.page_number_by_path[body_path],
                    cancel_check=None,
                )
            return

        batch_size = worker_count * 2
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="kind-table-inspect-source",
        ) as executor:
            for offset in range(0, len(body_paths), batch_size):
                batch = body_paths[offset : offset + batch_size]
                records_batch = executor.map(
                    lambda path: _read_source_page_records(
                        path,
                        source_page=inventory.page_number_by_path[path],
                        cancel_check=None,
                    ),
                    batch,
                )
                yield from zip(batch, records_batch)

    for body_path, (records, paging) in iter_page_records():
        _validate_source_page_pagination(
            body_path,
            paging,
            page_number_by_path=inventory.page_number_by_path,
            page_count_by_folder=inventory.page_count_by_folder,
            source_pagination=source_pagination,
        )
        page_source_rows = 0
        page_written_rows = 0
        page_duplicate_rows = 0
        for record in records:
            source_row_count += 1
            page_source_rows += 1
            acpt_no = str(record.get("acpt_no") or "").strip()
            if acpt_no in seen_acpt_nos:
                duplicate_row_count += 1
                page_duplicate_rows += 1
                continue
            seen_acpt_nos.add(acpt_no)

            company_key = str(record.get("company_key") or "").strip()
            if company_key:
                company_keys.add(company_key)
            else:
                unlinked_disclosure_count += 1

            year = _row_year(
                {
                    "disclosed_date": _validated_disclosed_date(
                        record.get("disclosed_at")
                    )
                }
            )
            disclosures, unlinked = shard_counts.get(year, (0, 0))
            shard_counts[year] = (
                disclosures + 1,
                unlinked + (0 if company_key else 1),
            )
            row_count += 1
            page_written_rows += 1

        folder = body_path.parent.resolve()
        source_rows_by_folder[folder] = (
            source_rows_by_folder.get(folder, 0) + page_source_rows
        )
        pages.append(
            {
                "source_file": body_path.relative_to(source_folder).as_posix(),
                "source_page": inventory.page_number_by_path[body_path],
                "source_rows": page_source_rows,
                "written_rows": page_written_rows,
                "duplicate_rows": page_duplicate_rows,
            }
        )

    _validate_source_folder_row_totals(
        source_pagination,
        source_rows_by_folder=source_rows_by_folder,
    )
    return (
        shard_counts,
        len(company_keys),
        row_count,
        source_row_count,
        duplicate_row_count,
        unlinked_disclosure_count,
        pages,
    )


def _read_source_page_records(
    body_path: Path,
    *,
    source_page: int,
    cancel_check: Callable[[], bool] | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if cancel_check and cancel_check():
        raise RuntimeError("Job cancelled")
    records, paging = _parse_source_body_page_file(body_path, source_page)
    if paging is None:
        raise ValueError(f"{body_path}: 페이지네이션 정보를 찾지 못했습니다.")
    if any(not str(record.get("acpt_no") or "").strip() for record in records):
        raise ValueError(f"acpt_no is required for every disclosure: {body_path}")
    return records, paging


def _validate_source_page_pagination(
    body_path: Path,
    paging: dict[str, int],
    *,
    page_number_by_path: dict[Path, int],
    page_count_by_folder: dict[Path, int],
    source_pagination: dict[Path, tuple[int, int]],
) -> None:
    folder = body_path.parent.resolve()
    filename_page = page_number_by_path[body_path]
    current_page = int(paging["current_page"])
    total_pages = int(paging["total_pages"])
    total_items = int(paging["total_items"])
    if current_page != filename_page:
        raise ValueError(
            f"{body_path}: 파일명 페이지={filename_page}, "
            f"BODY 페이지={current_page}로 서로 다릅니다."
        )
    expected_page_count = page_count_by_folder[folder]
    if total_pages != expected_page_count:
        raise ValueError(
            f"{folder}: BODY의 전체 페이지 수 {total_pages}와 "
            f"저장된 페이지 수 {expected_page_count}가 다릅니다."
        )
    expected_pagination = source_pagination.setdefault(
        folder,
        (total_pages, total_items),
    )
    if expected_pagination != (total_pages, total_items):
        raise ValueError(
            f"{folder}: BODY 페이지 사이의 전체 페이지 수 또는 "
            "전체 공시 건수가 다릅니다."
        )


def _validate_source_folder_row_totals(
    source_pagination: dict[Path, tuple[int, int]],
    *,
    source_rows_by_folder: dict[Path, int],
) -> None:
    for folder, (_total_pages, total_items) in source_pagination.items():
        source_rows = source_rows_by_folder.get(folder, 0)
        if source_rows != total_items:
            raise ValueError(
                f"{folder}: BODY의 전체 공시 건수 {total_items}건과 "
                f"실제 공시 행 수 {source_rows}건이 다릅니다."
            )


def _validate_source_inventory(
    inventory: _SourceInventory,
    *,
    cancel_check: Callable[[], bool] | None,
) -> None:
    for folder in inventory.source_folders:
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        metadata_path = folder / "kind_workflow.input.json"
        if not metadata_path.is_file():
            raise ValueError(f"{folder}: kind_workflow.input.json metadata is missing")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            validate_kind_workflow_input_snapshot(metadata)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise ValueError(
                f"{folder}: kind_workflow.input.json metadata is invalid: {error}"
            ) from error

        page_paths = inventory.body_paths_by_folder[folder]
        if not page_paths:
            raise ValueError(
                f"{folder}: kind_workflow.input.json이 있지만 공시 결과 페이지가 없습니다."
            )
        page_numbers: dict[int, int] = {}
        for path in page_paths:
            page_number = inventory.page_number_by_path[path]
            page_numbers[page_number] = page_numbers.get(page_number, 0) + 1
        duplicate_pages = sorted(
            page_number
            for page_number, count in page_numbers.items()
            if page_number >= 1 and count > 1
        )
        if duplicate_pages:
            duplicate_text = ", ".join(str(page) for page in duplicate_pages)
            raise ValueError(f"{folder}: 중복되는 페이지 번호 {duplicate_text}이 있습니다.")
        actual_pages = sorted(page_numbers)
        expected_pages = list(range(1, len(page_paths) + 1))
        if actual_pages != expected_pages:
            raise ValueError(
                f"{folder}: 페이지 번호가 1부터 연속적이지 않습니다. "
                f"확인된 페이지: {actual_pages}"
            )


def _resolve_shard_workers(value: object, shard_count: int) -> int:
    return resolve_worker_count(
        value,
        item_count=shard_count,
        field_name="table_workers",
    )


def _create_disclosure_table(connection: sqlite3.Connection, table_name: str) -> None:
    quoted_table = f'"{table_name}"'
    connection.execute(f"DROP TABLE IF EXISTS {quoted_table}")
    connection.execute(
        f"""
        CREATE TABLE {quoted_table} (
            id INTEGER PRIMARY KEY,
            row_no TEXT,
            company_key TEXT,
            company_name TEXT,
            company_id TEXT,
            company_cell_text TEXT,
            market TEXT,
            badges_json TEXT NOT NULL DEFAULT '[]',
            disclosed_at TEXT,
            disclosed_date TEXT,
            title TEXT,
            title_attr TEXT,
            title_base TEXT,
            title_display TEXT,
            title_flags_json TEXT NOT NULL DEFAULT '[]',
            is_correction_report INTEGER NOT NULL DEFAULT 0,
            has_later_correction INTEGER NOT NULL DEFAULT 0,
            acpt_no TEXT,
            doc_no TEXT,
            submitter TEXT,
            source_file TEXT,
            source_page INTEGER
        )
        """
    )


def _create_indexes(connection: sqlite3.Connection, table_name: str) -> list[str]:
    quoted_table = f'"{table_name}"'
    index_specs = {
        f"idx_{table_name}_date": "disclosed_date DESC",
        f"idx_{table_name}_company": "company_name",
        f"idx_{table_name}_company_id": "company_id",
        f"idx_{table_name}_acpt_no": "acpt_no",
        f"idx_{table_name}_market": "market",
        f"idx_{table_name}_title": "title",
    }
    created: list[str] = []
    for index_name, columns in index_specs.items():
        connection.execute(f'CREATE INDEX "{index_name}" ON {quoted_table} ({columns})')
        created.append(index_name)
    return created


def _create_fts_table(connection: sqlite3.Connection, table_name: str) -> bool:
    fts_table = f"{table_name}_fts"
    quoted_table = f'"{table_name}"'
    connection.execute(f'DROP TABLE IF EXISTS "{fts_table}"')
    connection.execute(
        f"""
        CREATE VIRTUAL TABLE "{fts_table}" USING fts5(
            title,
            company_name,
            submitter,
            content='{table_name}',
            content_rowid='id'
        )
        """
    )
    connection.execute(
        f"""
        INSERT INTO "{fts_table}"(rowid, title, company_name, submitter)
        SELECT id, title, company_name, submitter FROM {quoted_table}
        """
    )
    return True


def _write_metadata(
    connection: sqlite3.Connection,
    *,
    source_path: Path,
    source_type: str,
    table_name: str,
    companies: int,
    disclosures: int,
    unlinked_disclosures: int,
    fts_enabled: bool,
    shard_year: str,
) -> None:
    connection.execute("DROP TABLE IF EXISTS table_metadata")
    connection.execute(
        """
        CREATE TABLE table_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    metadata = {
        "format": "finiq_disclosure_table_sqlite",
        "shard_format": SQLITE_FORMAT,
        "schema_version": str(TABLE_SCHEMA_VERSION),
        "source_path": str(source_path),
        "source_type": source_type,
        "table_name": table_name,
        "shard_year": shard_year,
        "companies": str(companies),
        "disclosures": str(disclosures),
        "unlinked_disclosures": str(unlinked_disclosures),
        "fts_enabled": "true" if fts_enabled else "false",
    }
    connection.executemany(
        "INSERT INTO table_metadata(key, value) VALUES (?, ?)",
        sorted(metadata.items()),
    )


def _write_sqlite_shard(
    *,
    shard_path: Path,
    rows: list[dict[str, Any]],
    source_path: Path,
    source_type: str,
    table_name: str,
    shard_year: str,
) -> dict[str, Any]:
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = shard_path.with_suffix(f"{shard_path.suffix}.tmp")
    if temporary_path.exists():
        temporary_path.unlink()

    company_keys = {
        str(row.get("company_key") or "").strip()
        for row in rows
        if str(row.get("company_key") or "").strip()
    }
    unlinked_disclosures = sum(
        not str(row.get("company_key") or "").strip() for row in rows
    )
    connection = sqlite3.connect(temporary_path)
    try:
        with connection:
            _create_disclosure_table(connection, table_name)
            connection.executemany(
                f"""
                INSERT INTO "{table_name}" (
                    row_no,
                    company_key,
                    company_name,
                    company_id,
                    company_cell_text,
                    market,
                    badges_json,
                    disclosed_at,
                    disclosed_date,
                    title,
                    title_attr,
                    title_base,
                    title_display,
                    title_flags_json,
                    is_correction_report,
                    has_later_correction,
                    acpt_no,
                    doc_no,
                    submitter,
                    source_file,
                    source_page
                )
                VALUES (
                    :row_no,
                    :company_key,
                    :company_name,
                    :company_id,
                    :company_cell_text,
                    :market,
                    :badges_json,
                    :disclosed_at,
                    :disclosed_date,
                    :title,
                    :title_attr,
                    :title_base,
                    :title_display,
                    :title_flags_json,
                    :is_correction_report,
                    :has_later_correction,
                    :acpt_no,
                    :doc_no,
                    :submitter,
                    :source_file,
                    :source_page
                )
                """,
                rows,
            )
            indexes = _create_indexes(connection, table_name)
            fts_enabled = _create_fts_table(connection, table_name)
            inserted_count = int(
                connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            )
            if inserted_count != len(rows):
                msg = (
                    "SQLite 파일의 행 수가 다릅니다: "
                    f"파일={shard_path}, 저장={inserted_count}, 예상={len(rows)}"
                )
                raise ValueError(msg)
            _write_metadata(
                connection,
                source_path=source_path,
                source_type=source_type,
                table_name=table_name,
                companies=len(company_keys),
                disclosures=len(rows),
                unlinked_disclosures=unlinked_disclosures,
                fts_enabled=fts_enabled,
                shard_year=shard_year,
            )
    finally:
        connection.close()

    temporary_path.replace(shard_path)
    return {
        "year": shard_year,
        "relative_path": shard_path.name,
        "companies": len(company_keys),
        "disclosures": len(rows),
        "unlinked_disclosures": unlinked_disclosures,
        "indexes": indexes,
        "fts_enabled": fts_enabled,
    }


def _write_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    temporary_path = manifest_path.with_suffix(f"{manifest_path.suffix}.tmp")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(manifest_path)


@sqlite_generation_locked
def _publish_sqlite_generation(
    *,
    manifest_path: Path,
    staged_root: Path,
    shards: list[dict[str, Any]],
) -> list[str]:
    shard_root = manifest_path.parent
    shard_names = [str(shard.get("relative_path") or "") for shard in shards]
    if any(
        not name or Path(name).name != name or not name.endswith(".sqlite")
        for name in shard_names
    ):
        raise ValueError("staged SQLite shard paths must be SQLite file names")
    staged_manifest = staged_root / MANIFEST_FILENAME
    staged_shards = [staged_root / name for name in shard_names]
    if not staged_manifest.is_file() or any(
        not path.is_file() for path in staged_shards
    ):
        raise ValueError("staged SQLite generation is incomplete")

    previous_paths = sorted(
        path
        for path in shard_root.glob("[0-9][0-9][0-9][0-9].sqlite")
        if path.is_file()
    )
    if manifest_path.is_file():
        previous_paths.append(manifest_path)

    backup_root = Path(
        tempfile.mkdtemp(
            dir=shard_root,
            prefix=".finiq-table-backup-",
        )
    )
    moved_previous: list[tuple[Path, Path]] = []
    published: list[Path] = []
    try:
        for previous in previous_paths:
            backup = backup_root / previous.name
            os.replace(previous, backup)
            moved_previous.append((previous, backup))
        for staged in staged_shards:
            target = shard_root / staged.name
            os.replace(staged, target)
            published.append(target)
        os.replace(staged_manifest, manifest_path)
        published.append(manifest_path)
    except Exception:
        for target in reversed(published):
            target.unlink(missing_ok=True)
        for target, backup in reversed(moved_previous):
            if backup.exists():
                os.replace(backup, target)
        try:
            shutil.rmtree(backup_root)
        except OSError:
            pass
        raise

    try:
        shutil.rmtree(backup_root)
    except OSError as exc:
        return [
            "SQLite 결과 게시에는 성공했지만 이전 세대 백업을 정리하지 "
            f"못했습니다: {backup_root} ({exc})"
        ]
    return []


def _raise_if_cancelled(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check and cancel_check():
        raise RuntimeError("Job cancelled")


def _write_sqlite_shards(
    *,
    rows_by_year: dict[str, list[dict[str, Any]]],
    shard_root: Path,
    source_path: Path,
    source_type: str,
    table_name: str,
    worker_count: int,
    progress_callback: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    shard_items = sorted(rows_by_year.items())
    total_shards = len(shard_items)
    if worker_count <= 1:
        shards: list[dict[str, Any]] = []
        for i, (year, shard_rows) in enumerate(shard_items, 1):
            _raise_if_cancelled(cancel_check)
            if progress_callback:
                progress_callback(
                    f"[{i}/{total_shards}] {year}년 SQLite 파일 생성 중... ({len(shard_rows)}건)"
                )
            shard_path = shard_root / f"{year}.sqlite"
            shards.append(
                _write_sqlite_shard(
                    shard_path=shard_path,
                    rows=shard_rows,
                    source_path=source_path,
                    source_type=source_type,
                    table_name=table_name,
                    shard_year=year,
                )
            )
        return shards

    if progress_callback:
        progress_callback(
            f"연도별 SQLite 파일을 병렬로 생성합니다. worker 수={worker_count}"
        )

    shards_by_year: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(
        max_workers=worker_count, thread_name_prefix="kind-table-shard"
    ) as executor:
        pending = {}
        try:
            for i, (year, shard_rows) in enumerate(shard_items, 1):
                _raise_if_cancelled(cancel_check)
                if progress_callback:
                    progress_callback(
                        f"[{i}/{total_shards}] {year}년 SQLite 파일 생성 대기... ({len(shard_rows)}건)"
                    )
                shard_path = shard_root / f"{year}.sqlite"
                future = executor.submit(
                    _write_sqlite_shard,
                    shard_path=shard_path,
                    rows=shard_rows,
                    source_path=source_path,
                    source_type=source_type,
                    table_name=table_name,
                    shard_year=year,
                )
                pending[future] = year

            completed = 0
            while pending:
                _raise_if_cancelled(cancel_check)
                done, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
                if not done:
                    continue
                for future in done:
                    year = pending.pop(future)
                    result = future.result()
                    shards_by_year[year] = result
                    completed += 1
                    if progress_callback:
                        progress_callback(
                            f"[{completed}/{total_shards}] {year}년 SQLite 파일 생성 완료 ({result['disclosures']}건)"
                        )
        except RuntimeError as exc:
            if str(exc) == "Job cancelled":
                for future in pending:
                    future.cancel()
            raise

    _raise_if_cancelled(cancel_check)
    return [shards_by_year[year] for year, _ in shard_items]


def build_disclosure_table_payload(
    body: dict[str, Any],
    progress_callback: Callable[[str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if progress_callback:
        progress_callback("작업 설정 및 경로를 파악합니다...")
    root_directory = str(body.get("root_directory") or "").strip()
    if str(body.get("classification_path") or "").strip():
        raise ValueError("classification_path is not supported; use root_directory")
    source_inventory = _build_source_inventory(
        root_directory,
        cancel_check=cancel_check,
    )
    source_path = source_inventory.source_path
    source_type = "source_folder"

    output_path_raw = str(body.get("output_path") or "").strip()
    manifest_path = _manifest_output_path(output_path_raw)
    shard_root = _shard_directory(manifest_path)
    table_name = _normalize_table_name(body.get("table_name"))

    if progress_callback:
        progress_callback("공시 메타데이터를 로드합니다...")

    metadata_started_at = time.monotonic()
    source_body_paths = source_inventory.body_paths
    _validate_source_inventory(
        source_inventory,
        cancel_check=cancel_check,
    )
    source_workers = resolve_worker_count(
        body.get("table_workers"),
        item_count=len(source_body_paths),
        field_name="table_workers",
    )
    if progress_callback:
        progress_callback(
            f"다운로드한 원본 페이지를 병렬로 읽습니다. worker 수={source_workers}"
        )
    (
        rows_by_year,
        companies,
        row_count,
        source_row_count,
        duplicate_row_count,
        unlinked_disclosure_count,
        pages,
    ) = _collect_source_folder_rows_by_year(
        source_inventory,
        cancel_check=cancel_check,
        worker_count=source_workers,
    )
    if source_row_count != row_count + duplicate_row_count:
        msg = (
            "SQLite export did not account for every source disclosure row: "
            f"source={source_path}, source_rows={source_row_count}, "
            f"written={row_count}, duplicates={duplicate_row_count}"
        )
        raise ValueError(msg)
    shard_workers = _resolve_shard_workers(
        body.get("table_workers"), len(rows_by_year)
    )

    if progress_callback:
        progress_callback(
            f"데이터 분류 완료: {time.monotonic() - metadata_started_at:.1f}초 "
            f"(회사: {companies}개, 연도별 SQLite 파일: {len(rows_by_year)}개, "
            f"worker 수: {shard_workers}). SQLite 파일 생성을 시작합니다..."
        )

    shard_started_at = time.monotonic()
    shard_root.mkdir(parents=True, exist_ok=True)
    staged_root = Path(
        tempfile.mkdtemp(
            dir=shard_root,
            prefix=".finiq-table-build-",
        )
    )
    cleanup_warnings: list[str] = []
    published = False
    try:
        shards = _write_sqlite_shards(
            rows_by_year=rows_by_year,
            shard_root=staged_root,
            source_path=source_path,
            source_type=source_type,
            table_name=table_name,
            worker_count=shard_workers,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

        _raise_if_cancelled(cancel_check)
        if progress_callback:
            progress_callback(
                f"SQLite 파일 생성 완료: {time.monotonic() - shard_started_at:.1f}초. "
                "변환 기록 파일을 저장합니다..."
            )

        manifest = {
            "format": MANIFEST_FORMAT,
            "schema_version": TABLE_SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_type": source_type,
            "table_name": table_name,
            "summary": {
                "companies": companies,
                "source_rows": source_row_count,
                "duplicate_rows": duplicate_row_count,
                "disclosures": row_count,
                "unlinked_disclosures": unlinked_disclosure_count,
                "shards": len(shards),
            },
            "pages": pages,
            "shards": shards,
        }
        manifest["content_fingerprint"] = _sqlite_manifest_content_fingerprints(
            staged_root / MANIFEST_FILENAME,
            manifest,
        )[0]
        _write_manifest(staged_root / MANIFEST_FILENAME, manifest)
        _raise_if_cancelled(cancel_check)
        cleanup_warnings.extend(
            _publish_sqlite_generation(
                manifest_path=manifest_path,
                staged_root=staged_root,
                shards=shards,
            )
            or []
        )
        published = True
    finally:
        if staged_root.exists():
            try:
                shutil.rmtree(staged_root)
            except OSError as exc:
                if published:
                    cleanup_warnings.append(
                        "SQLite 결과 게시에는 성공했지만 준비 디렉터리를 정리하지 "
                        f"못했습니다: {staged_root} ({exc})"
                    )
                elif progress_callback:
                    progress_callback(
                        "SQLite 준비 디렉터리 정리 실패: "
                        f"{staged_root} ({exc})"
                    )
    return {
        "format": "finiq_disclosure_table_build_v1",
        "manifest_format": MANIFEST_FORMAT,
        "source_type": source_type,
        "source_path": str(source_path),
        "source_classification_path": "",
        "output_path": str(manifest_path),
        "manifest_path": str(manifest_path),
        "shard_root": str(shard_root),
        "table_name": table_name,
        "summary": {
            "companies": companies,
            "source_rows": source_row_count,
            "duplicate_rows": duplicate_row_count,
            "disclosures": row_count,
            "unlinked_disclosures": unlinked_disclosure_count,
            "shards": len(shards),
            "fts_enabled": all(shard["fts_enabled"] for shard in shards)
            if shards
            else False,
            "schema_version": TABLE_SCHEMA_VERSION,
        },
        "pages": pages,
        "shards": shards,
        "cleanup_warnings": cleanup_warnings,
    }


@sqlite_generation_locked
def inspect_disclosure_table_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Compare the current source pages, manifest, and SQLite shard contents."""
    root_directory = str(body.get("root_directory") or "").strip()
    output_path_raw = str(body.get("output_path") or "").strip()
    manifest_path = _manifest_output_path(output_path_raw)

    try:
        source_inventory = _build_source_inventory(
            root_directory,
            cancel_check=None,
        )
        source_path = source_inventory.source_path
        _validate_source_inventory(source_inventory, cancel_check=None)
        manifest = _load_sqlite_manifest(manifest_path)
        _validate_sqlite_manifest_counts(
            manifest_path,
            manifest,
            filter_workers=body.get("table_workers"),
        )
        actual_content_fingerprint = _sqlite_manifest_content_fingerprints(
            manifest_path,
            manifest,
        )[0]
        _validate_sqlite_manifest_content_fingerprint(
            manifest_path,
            manifest,
            actual_fingerprint=actual_content_fingerprint,
        )

        source_body_paths = source_inventory.body_paths
        source_workers = resolve_worker_count(
            body.get("table_workers"),
            item_count=len(source_body_paths),
            field_name="table_workers",
        )
        (
            shard_counts,
            companies,
            row_count,
            source_row_count,
            duplicate_row_count,
            unlinked_disclosure_count,
            pages,
        ) = _inspect_source_folder_counts(
            source_inventory,
            worker_count=source_workers,
        )

        expected_summary = {
            "companies": companies,
            "source_rows": source_row_count,
            "duplicate_rows": duplicate_row_count,
            "disclosures": row_count,
            "unlinked_disclosures": unlinked_disclosure_count,
            "shards": len(shard_counts),
        }
        actual_summary = manifest.get("summary")
        if actual_summary != expected_summary:
            raise ValueError("다운로드한 원본 데이터의 건수와 변환 기록의 요약이 다릅니다.")
        if manifest.get("pages") != pages:
            raise ValueError("다운로드한 원본 데이터와 변환 기록에 적힌 페이지별 건수가 다릅니다.")

        expected_shards = [
            {
                "year": year,
                "disclosures": disclosures,
                "unlinked_disclosures": unlinked_disclosures,
            }
            for year, (disclosures, unlinked_disclosures) in sorted(
                shard_counts.items()
            )
        ]
        actual_shards = [
            {
                "year": str(shard.get("year") or ""),
                "disclosures": int(shard.get("disclosures") or 0),
                "unlinked_disclosures": int(
                    shard.get("unlinked_disclosures") or 0
                ),
            }
            for shard in manifest.get("shards") or []
        ]
        if actual_shards != expected_shards:
            raise ValueError("다운로드한 원본 데이터의 연도별 건수와 SQLite 파일 구성이 다릅니다.")
    except Exception as error:
        return {
            "format": "finiq_disclosure_table_inspection_v1",
            "confirmed": False,
            "reason": str(error),
            "manifest_path": str(manifest_path),
        }

    return {
        "format": "finiq_disclosure_table_inspection_v1",
        "confirmed": True,
        "reason": "다운로드한 원본 데이터와 변환 기록, 연도별 SQLite 파일의 내용이 모두 일치합니다.",
        "manifest_path": str(manifest_path),
        "summary": expected_summary,
    }
