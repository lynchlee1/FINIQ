"""SQLite manifest and source-folder disclosure readers."""

from __future__ import annotations

from finiq.concurrency import bounded_as_completed
from finiq.data_scraper.parse import disclosure_file_rows
from finiq.data_scraper.storage.result_files import (
    effective_result_page_paths,
    result_page_number,
)
from finiq.market_desk.web.features.market_data.service_records import *


def _looks_like_sqlite_manifest(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return payload.get("format") == "finiq_disclosure_table_manifest_v1"


def _resolve_sqlite_manifest_path(path: str | Path) -> Path | None:
    candidate = Path(path).expanduser().resolve()
    if candidate.is_file():
        if not _looks_like_sqlite_manifest(candidate):
            if candidate.name == "sqlite_manifest.json":
                msg = f"Not a FINIQ disclosure SQLite manifest: {candidate}"
                raise ValueError(msg)
            return None
        if candidate.name != "sqlite_manifest.json":
            msg = f"SQLite manifest must be named sqlite_manifest.json: {candidate}"
            raise ValueError(msg)
        return candidate
    if not candidate.is_dir():
        if candidate.name == "sqlite_manifest.json":
            raise FileNotFoundError(f"SQLite manifest not found: {candidate}")
        return None
    manifest_path = candidate / "sqlite_manifest.json"
    if not manifest_path.is_file():
        return None
    if not _looks_like_sqlite_manifest(manifest_path):
        msg = f"Not a FINIQ disclosure SQLite manifest: {manifest_path}"
        raise ValueError(msg)
    return manifest_path


def _load_sqlite_manifest(manifest_path: Path) -> dict[str, Any]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("format") != "finiq_disclosure_table_manifest_v1":
        msg = f"Not a FINIQ disclosure SQLite manifest: {manifest_path}"
        raise ValueError(msg)
    return payload


def _sqlite_manifest_total_disclosures(manifest: dict[str, Any]) -> int:
    summary_count = manifest.get("summary", {}).get("disclosures")
    if summary_count is not None:
        return int(summary_count)
    return sum(
        int(shard.get("disclosures") or 0)
        for shard in list(manifest.get("shards") or [])
    )


def _quoted_sqlite_identifier(value: str) -> str:
    return f'"{value.replace(chr(34), chr(34) + chr(34))}"'


def _resolve_sqlite_shard_path(manifest_path: Path, shard: dict[str, Any]) -> Path:
    manifest_parent = manifest_path.parent
    shard_path = Path(str(shard.get("path") or "")).expanduser()
    if not shard_path.is_absolute():
        shard_path = (manifest_parent / shard_path).resolve()
    return shard_path


def _validate_sqlite_manifest_counts(
    manifest_path: Path, manifest: dict[str, Any]
) -> None:
    table_name = (
        str(manifest.get("table_name") or "disclosures").strip() or "disclosures"
    )
    quoted_table = _quoted_sqlite_identifier(table_name)
    shard_total = 0
    for shard in list(manifest.get("shards") or []):
        shard_path = _resolve_sqlite_shard_path(manifest_path, shard)
        if not shard_path.is_file():
            msg = f"SQLite shard not found: {shard_path}"
            raise ValueError(msg)
        expected = int(shard.get("disclosures") or 0)
        connection = sqlite3.connect(shard_path)
        try:
            actual = int(
                connection.execute(f"SELECT COUNT(*) FROM {quoted_table}").fetchone()[0]
            )
        finally:
            connection.close()
        if actual != expected:
            msg = (
                "SQLite shard disclosure count mismatch: "
                f"shard={shard_path}, manifest={expected}, rows={actual}"
            )
            raise ValueError(msg)
        shard_total += expected

    summary_total = manifest.get("summary", {}).get("disclosures")
    if summary_total is not None and int(summary_total) != shard_total:
        msg = (
            "SQLite manifest disclosure summary does not match shard totals: "
            f"manifest={manifest_path}, summary={int(summary_total)}, shards={shard_total}"
        )
        raise ValueError(msg)

    if manifest.get("source_type") == "source_folder":
        summary = manifest.get("summary", {})
        source_rows = summary.get("source_rows")
        duplicate_rows = summary.get("duplicate_rows")
        if source_rows is None or duplicate_rows is None:
            msg = f"SQLite manifest is missing source row counts: {manifest_path}"
            raise ValueError(msg)
        pages = manifest.get("pages")
        if not isinstance(pages, list) or not pages:
            msg = f"SQLite manifest is missing page row counts: {manifest_path}"
            raise ValueError(msg)
        page_source_rows = 0
        page_written_rows = 0
        page_duplicate_rows = 0
        for page in pages:
            if not isinstance(page, dict):
                raise ValueError(f"SQLite manifest has an invalid page record: {manifest_path}")
            current_source_rows = int(page.get("source_rows") or 0)
            current_written_rows = int(page.get("written_rows") or 0)
            current_duplicate_rows = int(page.get("duplicate_rows") or 0)
            if current_source_rows != current_written_rows + current_duplicate_rows:
                msg = (
                    "SQLite manifest page did not account for every source row: "
                    f"manifest={manifest_path}, page={page.get('source_page')}, "
                    f"source_rows={current_source_rows}, rows={current_written_rows}, "
                    f"duplicates={current_duplicate_rows}"
                )
                raise ValueError(msg)
            page_source_rows += current_source_rows
            page_written_rows += current_written_rows
            page_duplicate_rows += current_duplicate_rows
        if (
            page_source_rows != int(source_rows)
            or page_written_rows != shard_total
            or page_duplicate_rows != int(duplicate_rows)
        ):
            msg = (
                "SQLite manifest did not account for every source disclosure row: "
                "page totals do not match the disclosure summary, "
                f"manifest={manifest_path}"
            )
            raise ValueError(msg)
        if int(source_rows) != shard_total + int(duplicate_rows):
            msg = (
                "SQLite manifest did not account for every source disclosure row: "
                f"manifest={manifest_path}, source_rows={int(source_rows)}, "
                f"rows={shard_total}, duplicates={int(duplicate_rows)}"
            )
            raise ValueError(msg)


def _sqlite_table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in connection.execute(
            f"PRAGMA table_info({_quoted_sqlite_identifier(table_name)})"
        ).fetchall()
    }


def _sqlite_select_column(columns: set[str], column_name: str) -> str:
    quoted_column = _quoted_sqlite_identifier(column_name)
    if column_name not in columns:
        raise ValueError(f"SQLite table is missing required column: {column_name}")
    return quoted_column


def _iter_sqlite_manifest_disclosure_records(
    manifest_path: Path,
    manifest: dict[str, Any],
) -> Any:
    table_name = (
        str(manifest.get("table_name") or "disclosures").strip() or "disclosures"
    )
    quoted_table = _quoted_sqlite_identifier(table_name)
    for shard in sorted(
        list(manifest.get("shards") or []), key=lambda item: str(item.get("year") or "")
    ):
        shard_path = _resolve_sqlite_shard_path(manifest_path, shard)
        if not shard_path.is_file():
            msg = f"SQLite shard not found: {shard_path}"
            raise ValueError(msg)
        connection = sqlite3.connect(shard_path)
        connection.row_factory = sqlite3.Row
        try:
            columns = _sqlite_table_columns(connection, table_name)
            selected_columns = ",\n                    ".join(
                _sqlite_select_column(columns, column_name)
                for column_name in [
                    "row_no",
                    "company_key",
                    "company_name",
                    "company_id",
                    "market",
                    "disclosed_at",
                    "disclosed_date",
                    "title",
                    "title_attr",
                    "title_base",
                    "title_display",
                    "title_flags_json",
                    "is_correction_report",
                    "has_later_correction",
                    "acpt_no",
                    "doc_no",
                    "submitter",
                    "source_file",
                    "source_page",
                ]
            )
            cursor = connection.execute(
                f"""
                SELECT
                    {selected_columns}
                FROM {quoted_table}
                """
            )
            for row in cursor:
                record = dict(row)
                record["title_flags"] = list(
                    json.loads(str(record.get("title_flags_json") or "[]"))
                )
                yield _prepare_filter_record(record)
        finally:
            connection.close()


def _parse_source_body_file(file_path: Path) -> list[dict[str, Any]]:
    try:
        parsed_rows = disclosure_file_rows(file_path)
    except ValueError as exc:
        raise ValueError(f"{exc}: {file_path}") from exc

    rows: list[dict[str, Any]] = []
    for parsed_row in parsed_rows:
        row = dict(parsed_row)
        row["company_key"] = _clean_text(
            row.get("company_id") or row.get("company_name")
        )
        row["source_file"] = str(file_path)
        row["source_page"] = _result_page_number(file_path)
        rows.append(row)
    return rows


def _find_source_body_files(root: Path) -> list[Path]:
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
        for _folder, path in sorted(
            (
                (folder, path)
                for folder in source_folders
                for path in effective_result_page_paths(folder)
            ),
            key=lambda item: (
                str(item[0].relative_to(resolved_root)),
                result_page_number(item[1]),
                item[1].name,
            ),
        )
    ]


def _ensure_safe_source_root_directory(root: Path) -> None:
    risky_directories = {
        Path(root.anchor).resolve(),
        Path.home().resolve(),
        PROJECT_ROOT.resolve(),
    }
    risky_directories.update(PROJECT_ROOT.resolve().parents)
    if root in risky_directories:
        msg = f"Refusing to recursively inspect high-risk root_directory: {root}"
        raise ValueError(msg)


def _source_cache_key(root: Path, body_paths: list[Path]) -> tuple[str, int, int, int]:
    latest_modified_ns = 0
    total_size = 0
    for body_path in body_paths:
        stat_result = body_path.stat()
        latest_modified_ns = max(latest_modified_ns, stat_result.st_mtime_ns)
        total_size += stat_result.st_size
    return (str(root), len(body_paths), latest_modified_ns, total_size)


@lru_cache(maxsize=4)
def _parse_source_body_files_cached(
    root_path: str,
    body_count: int,
    latest_modified_ns: int,
    total_size: int,
    workers: int,
) -> tuple[tuple[dict[str, Any], ...], int]:
    root = Path(root_path)
    body_paths = _find_source_body_files(root)
    if not body_paths:
        return ((), 0)

    worker_count = _resolve_filter_workers(workers, len(body_paths))
    parsed_by_path: dict[Path, list[dict[str, Any]]] = {}
    if worker_count == 1:
        for body_path in body_paths:
            parsed_by_path[body_path] = _parse_source_body_file(body_path)
    else:
        with ThreadPoolExecutor(
            max_workers=worker_count, thread_name_prefix="kind-filter"
        ) as executor:
            completed = bounded_as_completed(
                executor,
                body_paths,
                lambda body_path: executor.submit(
                    _parse_source_body_file, body_path
                ),
                max_pending=worker_count * 2,
            )
            for future, body_path in completed:
                parsed_by_path[body_path] = future.result()

    records: list[dict[str, Any]] = []
    for body_path in body_paths:
        for record in parsed_by_path.get(body_path, []):
            records.append(_prepare_filter_record(record))
    return (tuple(records), len(body_paths))


def _iter_source_disclosure_records(
    root_directory: str | Path,
    *,
    progress_callback: ProgressCallback | None = None,
    progress_interval: int = 1000,
    workers: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    root = Path(root_directory).expanduser().resolve()
    if not root.is_dir():
        msg = f"root_directory is not a directory: {root}"
        raise ValueError(msg)
    _ensure_safe_source_root_directory(root)
    body_paths = _find_source_body_files(root)
    folders: dict[Path, list[Path]] = {}
    for body_path in body_paths:
        folders.setdefault(body_path.parent, []).append(body_path)
    records_tuple, body_file_count = _parse_source_body_files_cached(
        *_source_cache_key(root, body_paths),
        _resolve_filter_workers(workers, len(body_paths)),
    )
    records = list(records_tuple)
    for index, folder_path in enumerate(sorted(folders), start=1):
        _emit_progress(
            progress_callback,
            source_type="source_folder",
            unit_label="폴더",
            completed=index,
            total=len(folders),
            records=len(records),
            progress_interval=progress_interval,
        )
    return (records, body_file_count)




__all__ = [name for name in globals() if not name.startswith("__")]
