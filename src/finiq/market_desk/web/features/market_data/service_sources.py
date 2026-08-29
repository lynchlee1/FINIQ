"""SQLite manifest and source-folder disclosure readers."""

from __future__ import annotations

import hashlib

from finiq.data_scraper.parse import (
    disclosure_file_rows,
    disclosure_rows,
    pagination_info,
)
from finiq.data_scraper.storage.result_files import result_page_number
from finiq.market_desk.sqlite_generation import sqlite_generation_locked
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
    relative_path = str(shard.get("relative_path") or "").strip()
    if not relative_path:
        raise ValueError("SQLite manifest shard.relative_path is required")
    shard_path = Path(relative_path)
    if shard_path.is_absolute() or len(shard_path.parts) != 1:
        raise ValueError("SQLite manifest shard.relative_path must be a file name")
    return (manifest_path.parent / shard_path).resolve()


def _validate_sqlite_manifest_counts(
    manifest_path: Path,
    manifest: dict[str, Any],
    *,
    filter_workers: object = None,
) -> None:
    if manifest.get("schema_version") != 3:
        raise ValueError(
            f"SQLite manifest schema_version must be 3: {manifest_path}"
        )
    table_name = (
        str(manifest.get("table_name") or "disclosures").strip() or "disclosures"
    )
    quoted_table = _quoted_sqlite_identifier(table_name)
    shards = list(manifest.get("shards") or [])
    worker_count = _resolve_filter_workers(filter_workers, len(shards))

    def validate_shard(shard: dict[str, Any]) -> tuple[int, int]:
        shard_path = _resolve_sqlite_shard_path(manifest_path, shard)
        if not shard_path.is_file():
            msg = f"연도별 SQLite 파일을 찾을 수 없습니다: {shard_path}"
            raise ValueError(msg)
        expected = int(shard.get("disclosures") or 0)
        expected_unlinked_value = shard.get("unlinked_disclosures")
        if expected_unlinked_value is None:
            raise ValueError(
                f"SQLite manifest shard.unlinked_disclosures is required: {shard_path}"
            )
        expected_unlinked = int(expected_unlinked_value)
        connection = sqlite3.connect(shard_path)
        try:
            row = connection.execute(
                f"""
                SELECT COUNT(*),
                       SUM(CASE WHEN company_key IS NULL THEN 1 ELSE 0 END)
                FROM {quoted_table}
                """
            ).fetchone()
            actual = int(row[0])
            actual_unlinked = int(row[1] or 0)
        finally:
            connection.close()
        if actual != expected:
            msg = (
                "연도별 SQLite 파일의 공시 건수가 다릅니다: "
                f"파일={shard_path}, 변환 기록={expected}, 실제 행={actual}"
            )
            raise ValueError(msg)
        if actual_unlinked != expected_unlinked:
            msg = (
                "연도별 SQLite 파일의 회사 미연결 공시 건수가 다릅니다: "
                f"파일={shard_path}, 변환 기록={expected_unlinked}, "
                f"실제 행={actual_unlinked}"
            )
            raise ValueError(msg)
        return expected, expected_unlinked

    if worker_count == 1:
        shard_counts = list(map(validate_shard, shards))
    else:
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="sqlite-manifest-check",
        ) as executor:
            shard_counts = list(executor.map(validate_shard, shards))
    shard_total = sum(disclosures for disclosures, _unlinked in shard_counts)
    shard_unlinked_total = sum(unlinked for _disclosures, unlinked in shard_counts)

    summary_total = manifest.get("summary", {}).get("disclosures")
    if summary_total is not None and int(summary_total) != shard_total:
        msg = (
            "SQLite manifest disclosure summary does not match shard totals: "
            f"manifest={manifest_path}, summary={int(summary_total)}, shards={shard_total}"
        )
        raise ValueError(msg)
    summary_unlinked = manifest.get("summary", {}).get("unlinked_disclosures")
    if summary_unlinked is None:
        raise ValueError(
            f"SQLite manifest summary.unlinked_disclosures is required: {manifest_path}"
        )
    if int(summary_unlinked) != shard_unlinked_total:
        msg = (
            "SQLite manifest unlinked disclosure summary does not match shard totals: "
            f"manifest={manifest_path}, summary={int(summary_unlinked)}, "
            f"shards={shard_unlinked_total}"
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
    prepare: bool = True,
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
            msg = f"연도별 SQLite 파일을 찾을 수 없습니다: {shard_path}"
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
                    "company_cell_text",
                    "market",
                    "badges_json",
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
                parsed_badges = json.loads(str(record.get("badges_json") or "[]"))
                record["badges"] = (
                    [str(item) for item in parsed_badges]
                    if isinstance(parsed_badges, list)
                    else []
                )
                yield _prepare_filter_record(record) if prepare else record
        finally:
            connection.close()


_SQLITE_CONTENT_FINGERPRINT_FIELDS = (
    "row_no",
    "company_key",
    "company_name",
    "company_id",
    "company_cell_text",
    "market",
    "badges_json",
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
)


def _sqlite_manifest_content_fingerprints(
    manifest_path: Path,
    manifest: dict[str, Any],
    *,
    prefix_count: int | None = None,
) -> tuple[str, str | None]:
    """Hash canonical SQLite row content and an optional leading row prefix."""
    if prefix_count is not None and prefix_count < 0:
        raise ValueError("SQLite fingerprint prefix count must be >= 0")

    digest = hashlib.sha256()
    prefix_fingerprint = digest.hexdigest() if prefix_count == 0 else None
    row_count = 0
    for record in _iter_sqlite_manifest_disclosure_records(
        manifest_path,
        manifest,
        prepare=False,
    ):
        canonical = json.dumps(
            [record.get(field) for field in _SQLITE_CONTENT_FINGERPRINT_FIELDS],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        digest.update(canonical)
        digest.update(b"\n")
        row_count += 1
        if row_count == prefix_count:
            prefix_fingerprint = digest.hexdigest()

    if prefix_count is not None and prefix_count > row_count:
        prefix_fingerprint = None
    return digest.hexdigest(), prefix_fingerprint


def _validate_sqlite_manifest_content_fingerprint(
    manifest_path: Path,
    manifest: dict[str, Any],
    *,
    actual_fingerprint: str,
) -> None:
    expected_fingerprint = str(manifest.get("content_fingerprint") or "").strip()
    if (
        len(expected_fingerprint) != 64
        or any(
            character not in "0123456789abcdef"
            for character in expected_fingerprint
        )
    ):
        raise ValueError(
            f"SQLite manifest content_fingerprint is invalid: {manifest_path}"
        )
    if actual_fingerprint != expected_fingerprint:
        raise ValueError(
            "SQLite manifest content fingerprint does not match the actual shards: "
            f"{manifest_path}"
        )


def _sqlite_badges_predicate(
    quoted_column: str,
    *,
    operator: str,
    expected: str,
    folded_expected: str,
    clean_search: bool,
    ignore_spaces: bool,
) -> tuple[str, list[str]]:
    badge_text = "TRIM(COALESCE(CAST(badge_row.value AS TEXT), ''))"
    if clean_search:
        badge_text = f"finiq_clean_search({badge_text})"
    if ignore_spaces:
        badge_text = f"finiq_remove_spaces({badge_text})"
    folded_badge = f"finiq_casefold({badge_text})"
    json_source = f"COALESCE({quoted_column}, '[]')"

    def exists_badge(inner_sql: str, parameters: list[str]) -> tuple[str, list[str]]:
        return (
            f"EXISTS (SELECT 1 FROM json_each({json_source}) AS badge_row WHERE {inner_sql})",
            parameters,
        )

    if operator == "contains":
        return exists_badge(f"INSTR({folded_badge}, ?) > 0", [folded_expected])
    if operator == "not_contains":
        sql, parameters = exists_badge(f"INSTR({folded_badge}, ?) > 0", [folded_expected])
        return f"NOT {sql}", parameters
    if operator == "exact_match":
        return exists_badge(f"{badge_text} = ?", [expected])
    if operator == "equals":
        return exists_badge(f"{folded_badge} = ?", [folded_expected])
    if operator == "not_equals":
        sql, parameters = exists_badge(f"{folded_badge} = ?", [folded_expected])
        return f"NOT {sql}", parameters
    if operator == "starts_with":
        return exists_badge(
            f"SUBSTR({folded_badge}, 1, LENGTH(?)) = ?",
            [folded_expected, folded_expected],
        )
    if operator == "ends_with":
        return exists_badge(
            f"SUBSTR({folded_badge}, -LENGTH(?)) = ?",
            [folded_expected, folded_expected],
        )
    if operator == "in":
        values = [item.casefold() for item in _split_operator_values(expected)]
        if not values:
            return "0 = 1", []
        placeholders = ", ".join("?" for _ in values)
        return exists_badge(f"{folded_badge} IN ({placeholders})", values)
    if operator in {"before", "after", "on_or_before", "on_or_after"}:
        comparison = {
            "before": "<",
            "after": ">",
            "on_or_before": "<=",
            "on_or_after": ">=",
        }[operator]
        return exists_badge(f"({badge_text} != '' AND {badge_text} {comparison} ?)", [expected])
    if operator == "between":
        values = _split_operator_values(expected)
        if len(values) < 2:
            raise ValueError("between operator requires two values")
        return exists_badge(
            f"({badge_text} != '' AND {badge_text} BETWEEN ? AND ?)",
            values[:2],
        )
    if operator == "exists":
        return exists_badge(f"{badge_text} != ''", [])
    if operator == "empty":
        sql, parameters = exists_badge(f"{badge_text} != ''", [])
        return f"NOT {sql}", parameters
    raise ValueError(f"Unsupported filter operator: {operator}")


def _sqlite_title_filter_expression(
    filter_blocks: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    if not filter_blocks:
        return "1 = 1", []

    tokens: list[object] = []
    for index, block in enumerate(filter_blocks):
        parameters: list[str] = []
        if index > 0:
            tokens.append(str(block["connector"]))
        open_count = int(block["open_count"])
        close_count = int(block["close_count"])
        for _ in range(open_count):
            tokens.append("(")

        field = str(block["field"])
        quoted_field = _quoted_sqlite_identifier(_filter_sql_column(field))
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
        if field == "badges":
            predicate, parameters = _sqlite_badges_predicate(
                quoted_field,
                operator=operator,
                expected=expected,
                folded_expected=folded_expected,
                clean_search=bool(block["clean_search"]),
                ignore_spaces=bool(block["ignore_spaces"]),
            )
        elif operator == "contains":
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
        tokens.append((predicate, parameters))
        for _ in range(close_count):
            tokens.append(")")

    return _parse_sql_boolean_tokens(tokens)


def _parse_sql_boolean_tokens(tokens: list[object]) -> tuple[str, list[str]]:
    position = 0

    def peek() -> object | None:
        return tokens[position] if position < len(tokens) else None

    def consume() -> object:
        nonlocal position
        if position >= len(tokens):
            raise ValueError("Unexpected end of filter blocks")
        token = tokens[position]
        position += 1
        return token

    def combine(
        left: tuple[str, list[str]],
        operator: str,
        right: tuple[str, list[str]],
    ) -> tuple[str, list[str]]:
        left_sql, left_parameters = left
        right_sql, right_parameters = right
        sql = f"(({left_sql}) {operator} ({right_sql}))"
        return sql, [*left_parameters, *right_parameters]

    def parse_factor() -> tuple[str, list[str]]:
        token = peek()
        if token == "(":
            consume()
            result = parse_or()
            if peek() != ")":
                raise ValueError("Missing closing parenthesis in filter blocks")
            consume()
            return result
        if token == ")":
            raise ValueError("Unexpected closing parenthesis in filter blocks")
        if isinstance(token, str):
            raise ValueError(f"Unexpected operator in filter blocks: {token}")
        value = consume()
        if not isinstance(value, tuple):
            raise ValueError("Invalid predicate in filter blocks")
        return value

    def parse_and() -> tuple[str, list[str]]:
        result = parse_factor()
        while peek() == "AND":
            consume()
            result = combine(result, "AND", parse_factor())
        return result

    def parse_or() -> tuple[str, list[str]]:
        result = parse_and()
        while peek() == "OR":
            consume()
            result = combine(result, "OR", parse_and())
        return result

    result = parse_or()
    if position != len(tokens):
        raise ValueError(f"Unexpected token in filter blocks: {tokens[position]}")
    return result


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
        for column_name in {_filter_sql_column(field) for field in _FILTER_FIELDS} | {"id"}:
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
            raise ValueError(
                f"연도별 SQLite 파일을 찾을 수 없습니다: {shard_path}"
            )
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
    parsed_rows = disclosure_file_rows(file_path)

    return _source_body_rows(file_path, parsed_rows, _result_page_number(file_path))


def _parse_source_body_page_file(
    file_path: Path,
    source_page: int,
) -> tuple[list[dict[str, Any]], dict[str, int] | None]:
    body_bytes = file_path.read_bytes()
    try:
        parsed_rows = disclosure_rows(body_bytes)
    except ValueError as exc:
        raise ValueError(f"{exc}: {file_path}") from exc
    return (
        _source_body_rows(file_path, parsed_rows, source_page),
        pagination_info(body_bytes),
    )


def _source_body_rows(
    file_path: Path,
    parsed_rows: list[dict[str, Any]],
    source_page: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for parsed_row in parsed_rows:
        row = dict(parsed_row)
        company_id = _clean_text(row.get("company_id"))
        row["company_id"] = company_id or None
        row["company_key"] = company_id or None
        row["source_file"] = str(file_path)
        row["source_page"] = source_page
        rows.append(row)
    return rows


__all__ = [name for name in globals() if not name.startswith("__")]
