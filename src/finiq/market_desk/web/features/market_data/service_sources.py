"""SQLite manifest and source-folder disclosure readers."""

from __future__ import annotations

from finiq.data_scraper.parse import disclosure_file_rows
from finiq.data_scraper.storage.result_files import result_page_number
from finiq.market_desk.web.features.market_data.service_records import *


def _looks_like_sqlite_manifest(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return payload.get("format") == "finiq_disclosure_table_manifest_v1"


def _resolve_sqlite_manifest_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser().resolve()
    if candidate.is_dir():
        raise ValueError(
            f"SQLite manifest path must be the sqlite_manifest.json file: {candidate}"
        )
    if not candidate.is_file():
        raise FileNotFoundError(f"SQLite manifest path not found: {candidate}")
    if candidate.name != "sqlite_manifest.json":
        msg = f"SQLite manifest must be named sqlite_manifest.json: {candidate}"
        raise ValueError(msg)
    if not _looks_like_sqlite_manifest(candidate):
        msg = f"Not a FINIQ disclosure SQLite manifest: {candidate}"
        raise ValueError(msg)
    return candidate


def _load_sqlite_manifest(manifest_path: Path) -> dict[str, Any]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("format") != "finiq_disclosure_table_manifest_v1":
        msg = f"Not a FINIQ disclosure SQLite manifest: {manifest_path}"
        raise ValueError(msg)
    return payload


def _sqlite_manifest_total_disclosures(manifest: dict[str, Any]) -> int:
    summary_count = manifest.get("summary", {}).get("disclosures")
    if summary_count is None:
        raise ValueError("SQLite manifest summary.disclosures is required")
    return int(summary_count)


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
        company_id = _clean_text(row.get("company_id"))
        if not company_id:
            raise ValueError(f"company_id is required: {file_path}")
        row["company_key"] = company_id
        row["source_file"] = str(file_path)
        row["source_page"] = _result_page_number(file_path)
        rows.append(row)
    return rows


__all__ = [name for name in globals() if not name.startswith("__")]
