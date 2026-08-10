"""Build SQLite disclosure tables from canonical KIND result folders."""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from finiq.concurrency import bounded_as_completed, resolve_worker_count
from finiq.data_scraper.storage.result_files import (
    result_page_number,
    sorted_result_page_paths,
)
from finiq.data_scraper.workflow import validate_kind_workflow_input_snapshot
from finiq.market_desk.web.features.market_data.service_sources import (
    _parse_source_body_file,
)

TABLE_SCHEMA_VERSION = 3
DEFAULT_TABLE_NAME = "disclosures"
MANIFEST_FORMAT = "finiq_disclosure_table_manifest_v1"
MANIFEST_FILENAME = "sqlite_manifest.json"
SQLITE_FORMAT = "finiq_disclosure_table_sqlite_shard"


def _date_part(value: object) -> str:
    return str(value or "").strip().split(" ", 1)[0]


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


def _source_has_body_files(path: Path) -> bool:
    return path.is_dir() and bool(_find_original_source_body_files(path))


def _find_original_source_body_files(root: Path) -> list[Path]:
    resolved_root = root.resolve()
    source_folders = {
        path.parent.resolve()
        for path in resolved_root.rglob("*_post_page_*.body")
        if not any(
            part.startswith(".")
            for part in path.relative_to(resolved_root).parts[:-1]
        )
    }
    return [
        path
        for folder in sorted(source_folders)
        for path in sorted_result_page_paths(folder)
    ]


def _resolve_source(root_directory: str) -> Path:
    if not root_directory:
        raise ValueError("root_directory is required")
    source_path = Path(root_directory).expanduser().resolve()
    if not source_path.is_dir():
        raise FileNotFoundError(f"KIND source directory not found: {source_path}")
    if not _source_has_body_files(source_path):
        raise ValueError(f"KIND body files not found: {source_path}")
    return source_path


def _row_year(row: dict[str, Any]) -> str:
    disclosed_date = str(row.get("disclosed_date") or "").strip()
    year = disclosed_date[:4]
    if len(year) == 4 and year.isdigit():
        return year
    raise ValueError(f"disclosed_date must begin with a four-digit year: {disclosed_date!r}")


def _collect_source_folder_rows_by_year(
    source_folder: Path,
    body_paths: list[Path],
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
    indexed_records: list[list[dict[str, Any]] | None] = [None] * len(body_paths)
    if worker_count <= 1 or len(body_paths) <= 1:
        for index, body_path in enumerate(body_paths):
            indexed_records[index] = _read_source_page_records(
                body_path,
                cancel_check=cancel_check,
            )
    else:
        errors: list[Exception | None] = [None] * len(body_paths)
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="kind-table-source",
        ) as executor:
            completed = bounded_as_completed(
                executor,
                enumerate(body_paths),
                lambda item: executor.submit(
                    _read_source_page_records,
                    item[1],
                    cancel_check=cancel_check,
                ),
                max_pending=worker_count * 2,
            )
            for future, (index, _body_path) in completed:
                if cancel_check and cancel_check():
                    raise RuntimeError("Job cancelled")
                try:
                    indexed_records[index] = future.result()
                except Exception as error:
                    errors[index] = error
        first_error = next((error for error in errors if error is not None), None)
        if first_error is not None:
            raise first_error

    for body_path, records in zip(body_paths, indexed_records):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        page_source_rows = 0
        page_written_rows = 0
        page_duplicate_rows = 0
        if records is None:
            raise RuntimeError(f"Source page parsing did not return a result: {body_path}")
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
                "disclosed_date": _date_part(disclosed_at),
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
        page_number = result_page_number(body_path)
        pages.append(
            {
                "source_file": body_path.relative_to(source_folder).as_posix(),
                "source_page": page_number,
                "source_rows": page_source_rows,
                "written_rows": page_written_rows,
                "duplicate_rows": page_duplicate_rows,
            }
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


def _read_source_page_records(
    body_path: Path,
    *,
    cancel_check: Callable[[], bool] | None,
) -> list[dict[str, Any]]:
    if cancel_check and cancel_check():
        raise RuntimeError("Job cancelled")
    records = _parse_source_body_file(body_path)
    if any(not str(record.get("acpt_no") or "").strip() for record in records):
        raise ValueError(f"acpt_no is required for every disclosure: {body_path}")
    return records


def _validate_source_page_ranges(
    source_folder: Path,
    *,
    cancel_check: Callable[[], bool] | None,
) -> None:
    source_folders = {
        path.parent.resolve()
        for path in source_folder.rglob("kind_workflow.input.json")
        if not any(
            part.startswith(".")
            for part in path.relative_to(source_folder).parts[:-1]
        )
    }
    source_folders.update(
        path.parent.resolve()
        for path in source_folder.rglob("*_post_page_*.body")
        if not any(
            part.startswith(".")
            for part in path.relative_to(source_folder).parts[:-1]
        )
    )
    for folder in sorted(source_folders):
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

        page_paths = sorted_result_page_paths(folder)
        if not any(result_page_number(path) >= 1 for path in page_paths):
            raise ValueError(
                f"{folder}: kind_workflow.input.json이 있지만 공시 결과 페이지가 없습니다."
            )
        page_numbers: dict[int, int] = {}
        for path in page_paths:
            page_number = result_page_number(path)
            page_numbers[page_number] = page_numbers.get(page_number, 0) + 1
        duplicate_pages = sorted(
            page_number
            for page_number, count in page_numbers.items()
            if page_number >= 1 and count > 1
        )
        if duplicate_pages:
            duplicate_text = ", ".join(str(page) for page in duplicate_pages)
            raise ValueError(f"{folder}: 중복되는 페이지 번호 {duplicate_text}이 있습니다.")


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
                    "SQLite shard row count mismatch: "
                    f"shard={shard_path}, inserted={inserted_count}, expected={len(rows)}"
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
                    f"[{i}/{total_shards}] {year}년 샤드 생성 중... ({len(shard_rows)} 건)"
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
        progress_callback(f"연도 샤드 병렬 생성을 사용합니다. workers={worker_count}")

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
                        f"[{i}/{total_shards}] {year}년 샤드 생성 예약... ({len(shard_rows)} 건)"
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
                            f"[{completed}/{total_shards}] {year}년 샤드 생성 완료 ({result['disclosures']} 건)"
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
    source_path = _resolve_source(root_directory)
    source_type = "source_folder"

    output_path_raw = str(body.get("output_path") or "").strip()
    manifest_path = _manifest_output_path(output_path_raw)
    shard_root = _shard_directory(manifest_path)
    table_name = _normalize_table_name(body.get("table_name"))

    if progress_callback:
        progress_callback("공시 메타데이터를 로드합니다...")

    source_body_paths = _find_original_source_body_files(source_path)
    _validate_source_page_ranges(
        source_path,
        cancel_check=cancel_check,
    )
    source_workers = resolve_worker_count(
        body.get("table_workers"),
        item_count=len(source_body_paths),
        field_name="table_workers",
    )
    if progress_callback:
        progress_callback(
            f"원본 BODY 페이지 병렬 파싱을 시작합니다. workers={source_workers}"
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
        source_path,
        source_body_paths,
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
            f"데이터 분류 완료 (회사: {companies}개, 연도 샤드: {len(rows_by_year)}개, workers: {shard_workers}). 샤드 생성을 시작합니다..."
        )

    shards = _write_sqlite_shards(
        rows_by_year=rows_by_year,
        shard_root=shard_root,
        source_path=source_path,
        source_type=source_type,
        table_name=table_name,
        worker_count=shard_workers,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )

    _raise_if_cancelled(cancel_check)
    if progress_callback:
        progress_callback("매니페스트 파일을 기록합니다...")

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
    _write_manifest(manifest_path, manifest)
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
    }
