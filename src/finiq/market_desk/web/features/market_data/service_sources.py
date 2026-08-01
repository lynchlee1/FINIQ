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
    *,
    offset: int = 0,
) -> Any:
    if offset < 0:
        raise ValueError("SQLite disclosure offset must be >= 0")
    table_name = (
        str(manifest.get("table_name") or "disclosures").strip() or "disclosures"
    )
    quoted_table = _quoted_sqlite_identifier(table_name)
    remaining_offset = offset
    for shard in sorted(
        list(manifest.get("shards") or []), key=lambda item: str(item.get("year") or "")
    ):
        shard_disclosures = int(shard.get("disclosures") or 0)
        if remaining_offset >= shard_disclosures:
            remaining_offset -= shard_disclosures
            continue
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
                ORDER BY id
                LIMIT -1 OFFSET ?
                """,
                (remaining_offset,),
            )
            remaining_offset = 0
            for row in cursor:
                record = dict(row)
                record["title_flags"] = list(
                    json.loads(str(record.get("title_flags_json") or "[]"))
                )
                yield _prepare_filter_record(record)
        finally:
            connection.close()


def _sqlite_title_filter_expression(
    filter_blocks: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    if not filter_blocks:
        return "1 = 1", []

    sql_parts: list[str] = []
    parameters: list[str] = []
    parenthesis_depth = 0
    for index, block in enumerate(filter_blocks):
        if index > 0:
            sql_parts.append(str(block["connector"]))
        open_count = int(block["open_count"])
        close_count = int(block["close_count"])
        if open_count:
            sql_parts.append("(" * open_count)
            parenthesis_depth += open_count

        field = str(block["field"])
        quoted_field = _quoted_sqlite_identifier(field)
        actual = f"TRIM(COALESCE(CAST({quoted_field} AS TEXT), ''))"
        expected = str(block["value"]).strip()
        if block["clean_search"]:
            actual = f"finiq_clean_search({actual})"
            expected = _clean_search_text(expected)
        if block["ignore_spaces"]:
            actual = f"finiq_remove_spaces({actual})"
            expected = _remove_whitespace(expected)

        folded_actual = f"finiq_casefold({actual})"
        folded_expected = expected.casefold()
        operator = str(block["operator"])
        if operator == "contains":
            predicate = f"INSTR({folded_actual}, ?) > 0"
            parameters.append(folded_expected)
        elif operator == "not_contains":
            predicate = f"INSTR({folded_actual}, ?) = 0"
            parameters.append(folded_expected)
        elif operator == "exact_match":
            predicate = f"{actual} = ?"
            parameters.append(expected)
        elif operator == "equals":
            predicate = f"{folded_actual} = ?"
            parameters.append(folded_expected)
        elif operator == "not_equals":
            predicate = f"{folded_actual} != ?"
            parameters.append(folded_expected)
        elif operator == "starts_with":
            predicate = f"SUBSTR({folded_actual}, 1, LENGTH(?)) = ?"
            parameters.extend([folded_expected, folded_expected])
        elif operator == "ends_with":
            predicate = f"SUBSTR({folded_actual}, -LENGTH(?)) = ?"
            parameters.extend([folded_expected, folded_expected])
        elif operator == "in":
            values = [item.casefold() for item in _split_operator_values(expected)]
            if values:
                predicate = f"{folded_actual} IN ({', '.join('?' for _ in values)})"
                parameters.extend(values)
            else:
                predicate = "0 = 1"
        elif operator in {
            "before",
            "after",
            "on_or_before",
            "on_or_after",
        }:
            comparison = {
                "before": "<",
                "after": ">",
                "on_or_before": "<=",
                "on_or_after": ">=",
            }[operator]
            predicate = f"({actual} != '' AND {actual} {comparison} ?)"
            parameters.append(expected)
        elif operator == "between":
            values = _split_operator_values(expected)
            if len(values) < 2:
                raise ValueError("between operator requires two values")
            predicate = f"({actual} != '' AND {actual} BETWEEN ? AND ?)"
            parameters.extend(values[:2])
        elif operator == "exists":
            predicate = f"{actual} != ''"
        elif operator == "empty":
            predicate = f"{actual} = ''"
        else:
            raise ValueError(f"Unsupported filter operator: {operator}")

        if block["not"]:
            predicate = f"NOT ({predicate})"
        sql_parts.append(predicate)
        if close_count:
            parenthesis_depth -= close_count
            if parenthesis_depth < 0:
                raise ValueError("Unmatched closing parenthesis in filter blocks")
            sql_parts.append(")" * close_count)

    if parenthesis_depth:
        raise ValueError("Unmatched opening parenthesis in filter blocks")
    return " ".join(sql_parts), parameters


def _query_sqlite_shard_titles(
    shard_path: Path,
    table_name: str,
    where_sql: str,
    parameters: list[str],
    cancel_check: CancelCheck | None,
) -> tuple[int, list[tuple[str, int]]]:
    if cancel_check is not None and cancel_check():
        raise FilterCancelled("title search cancelled")
    connection = sqlite3.connect(shard_path)
    try:
        columns = _sqlite_table_columns(connection, table_name)
        for column_name in _FILTER_FIELDS | {"id"}:
            _sqlite_select_column(columns, column_name)
        connection.create_function(
            "finiq_casefold", 1, lambda value: str(value or "").casefold()
        )
        connection.create_function(
            "finiq_clean_search", 1, lambda value: _clean_search_text(str(value or ""))
        )
        connection.create_function(
            "finiq_remove_spaces", 1, lambda value: _remove_whitespace(str(value or ""))
        )
        if cancel_check is not None:
            connection.set_progress_handler(lambda: int(cancel_check()), 1000)
        quoted_table = _quoted_sqlite_identifier(table_name)
        rows = connection.execute(
            f"""
            SELECT title, COUNT(DISTINCT acpt_no) AS disclosure_count, MIN(id)
            FROM {quoted_table}
            WHERE {where_sql}
            GROUP BY title
            ORDER BY MIN(id)
            """,
            parameters,
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if cancel_check is not None and cancel_check():
            raise FilterCancelled("title search cancelled") from exc
        raise
    finally:
        connection.close()

    matched_disclosures = sum(int(row[1]) for row in rows)
    titles = [
        (str(row[0]).strip(), int(row[1]))
        for row in rows
        if str(row[0] or "").strip()
    ]
    return matched_disclosures, titles


def _search_sqlite_manifest_titles(
    manifest_path: Path,
    manifest: dict[str, Any],
    *,
    filter_blocks: list[dict[str, Any]],
    filter_workers: int,
    progress_callback: ProgressCallback | None,
    cancel_check: CancelCheck | None,
) -> tuple[int, dict[str, int]]:
    table_name = (
        str(manifest.get("table_name") or "disclosures").strip() or "disclosures"
    )
    where_sql, parameters = _sqlite_title_filter_expression(filter_blocks)
    shards = sorted(
        list(manifest.get("shards") or []), key=lambda item: str(item.get("year") or "")
    )
    worker_count = _resolve_filter_workers(filter_workers, len(shards))

    def query_shard(shard: dict[str, Any]) -> tuple[int, list[tuple[str, int]]]:
        shard_path = _resolve_sqlite_shard_path(manifest_path, shard)
        if not shard_path.is_file():
            raise ValueError(f"SQLite shard not found: {shard_path}")
        return _query_sqlite_shard_titles(
            shard_path,
            table_name,
            where_sql,
            parameters,
            cancel_check,
        )

    matched_disclosures = 0
    inspected_disclosures = 0
    title_counts: dict[str, int] = {}
    with ThreadPoolExecutor(
        max_workers=worker_count, thread_name_prefix="disclosure-title-search"
    ) as executor:
        results = executor.map(query_shard, shards)
        for shard, (shard_matched, shard_titles) in zip(shards, results):
            if cancel_check is not None and cancel_check():
                raise FilterCancelled("title search cancelled")
            matched_disclosures += shard_matched
            inspected_disclosures += int(shard.get("disclosures") or 0)
            for title, count in shard_titles:
                title_counts[title] = title_counts.get(title, 0) + count
            _emit_progress(
                progress_callback,
                source_type="sqlite_manifest",
                unit_label="공시",
                completed=inspected_disclosures,
                total=_sqlite_manifest_total_disclosures(manifest),
                records=matched_disclosures,
                force=True,
            )
    return matched_disclosures, title_counts


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
