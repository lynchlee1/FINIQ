"""Build SQLite disclosure tables from FINIQ classification JSON."""

from __future__ import annotations

import json
import os
import sqlite3
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from finiq.market_desk.data.facade import load_company_classification_file
from finiq.market_desk.web.features.market_data.discovery import (
    list_classification_files,
    resolve_default_classification,
)
from finiq.market_desk.web.features.market_data.service_sources import (
    _find_source_body_files,
    _parse_source_body_file,
)

TABLE_SCHEMA_VERSION = 2
DEFAULT_TABLE_NAME = "disclosures"
MANIFEST_FORMAT = "finiq_disclosure_table_manifest_v1"
SQLITE_FORMAT = "finiq_disclosure_table_sqlite_shard"


def _date_part(value: object) -> str:
    return str(value or "").strip().split(" ", 1)[0]


def _company_key(company: dict[str, Any]) -> str:
    return str(
        company.get("company_key")
        or company.get("company_id")
        or company.get("company_name")
        or ""
    ).strip()


def _summary_disclosure_count(payload: dict[str, Any]) -> int | None:
    summary = payload.get("summary")
    if not isinstance(summary, dict) or summary.get("disclosures") is None:
        return None
    return int(summary.get("disclosures") or 0)


def _company_disclosures(
    company: dict[str, Any], company_index: int
) -> list[dict[str, Any]]:
    disclosures = company.get("disclosures")
    if disclosures is None:
        return []
    if not isinstance(disclosures, list):
        msg = f"companies[{company_index}].disclosures must be a list"
        raise ValueError(msg)
    for disclosure_index, disclosure in enumerate(disclosures):
        if not isinstance(disclosure, dict):
            msg = f"companies[{company_index}].disclosures[{disclosure_index}] must be an object"
            raise ValueError(msg)
    return disclosures


def _normalize_table_name(value: object) -> str:
    table_name = str(value or DEFAULT_TABLE_NAME).strip()
    if not table_name:
        return DEFAULT_TABLE_NAME
    if not table_name.replace("_", "").isalnum() or table_name[0].isdigit():
        msg = "table_name must contain only letters, numbers, and underscores, and must not start with a digit"
        raise ValueError(msg)
    return table_name


def _default_output_path(classification_path: Path) -> Path:
    return classification_path.with_name(
        f"{classification_path.stem}.sqlite_manifest.json"
    )


def _shard_directory(manifest_path: Path) -> Path:
    if manifest_path.parent.name.endswith("_shards"):
        return manifest_path.parent
    return manifest_path.with_name(f"{manifest_path.stem}_shards")


def _manifest_path_inside_shard_directory(manifest_path: Path) -> Path:
    if manifest_path.parent.name.endswith("_shards"):
        return manifest_path
    shard_root = manifest_path.with_name(f"{manifest_path.stem}_shards")
    return shard_root / manifest_path.name


def _manifest_output_path(raw_path: str, classification_path: Path) -> Path:
    if not raw_path:
        return _manifest_path_inside_shard_directory(
            _default_output_path(classification_path)
        ).resolve()
    output_path = _normalize_workspace_resource_path(
        Path(raw_path).expanduser(), allow_missing_leaf=True
    ).resolve()
    if output_path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
        return _manifest_path_inside_shard_directory(
            output_path.with_suffix(".sqlite_manifest.json")
        )
    if output_path.suffix:
        return _manifest_path_inside_shard_directory(output_path)
    return _manifest_path_inside_shard_directory(
        output_path / _default_output_path(classification_path).name
    )


def _source_has_body_files(path: Path) -> bool:
    return path.is_dir() and bool(_find_source_body_files(path))


def _workspace_resource_bases() -> list[Path]:
    bases = [
        Path.cwd(),
        Path.cwd().parent,
        Path(__file__).resolve().parents[3],
        Path(__file__).resolve().parents[2],
    ]
    unique_bases: list[Path] = []
    seen: set[Path] = set()
    for base in bases:
        resolved = base.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_bases.append(resolved)
    return unique_bases


def _normalize_workspace_resource_path(
    path: Path, *, allow_missing_leaf: bool = False
) -> Path:
    candidate = path.resolve()
    if candidate.exists() or "resources" not in candidate.parts:
        return candidate

    resource_index = candidate.parts.index("resources")
    relative_parts = candidate.parts[resource_index + 1 :]
    for base in _workspace_resource_bases():
        resource_path = (base / "resources" / Path(*relative_parts)).resolve()
        if resource_path.exists():
            return resource_path
        if allow_missing_leaf and resource_path.parent.exists():
            return resource_path
    return candidate


def _resolve_source(raw_path: str, root_directory: str) -> tuple[str, Path]:
    root_path = (
        _normalize_workspace_resource_path(Path(root_directory).expanduser())
        if root_directory
        else None
    )

    if raw_path:
        candidate = _normalize_workspace_resource_path(Path(raw_path).expanduser())
        if candidate.is_file():
            return ("classification", candidate)
        if candidate.is_dir():
            resolved = resolve_default_classification(candidate)
            if resolved:
                return ("classification", Path(resolved).expanduser().resolve())
            files = list_classification_files(candidate)
            if files:
                return ("classification", Path(files[0]["path"]).expanduser().resolve())
            if _source_has_body_files(candidate):
                return ("source_folder", candidate)
            if root_path is not None:
                if _source_has_body_files(root_path):
                    return ("source_folder", root_path)
                root_resolved = resolve_default_classification(root_path)
                if root_resolved:
                    return (
                        "classification",
                        Path(root_resolved).expanduser().resolve(),
                    )
            msg = f"classification JSON or KIND body files not found in directory: {candidate}"
            raise FileNotFoundError(msg)
        if root_path is not None:
            if _source_has_body_files(root_path):
                return ("source_folder", root_path)
            root_resolved = resolve_default_classification(root_path)
            if root_resolved:
                return ("classification", Path(root_resolved).expanduser().resolve())
        msg = f"classification JSON or KIND body folder not found: {candidate}"
        raise FileNotFoundError(msg)

    if root_path is None:
        msg = "classification_path or root_directory is required"
        raise ValueError(msg)
    resolved = resolve_default_classification(root_path)
    if resolved:
        return ("classification", Path(resolved).expanduser().resolve())
    if _source_has_body_files(root_path):
        return ("source_folder", root_path)
    msg = "classification JSON or KIND body files not found"
    raise ValueError(msg)


def _validate_classification_disclosure_counts(
    payload: dict[str, Any],
    row_count: int,
    source_path: Path,
) -> None:
    companies = list(payload.get("companies") or [])
    actual_disclosures = sum(
        len(_company_disclosures(company, company_index))
        for company_index, company in enumerate(companies)
    )
    if row_count != actual_disclosures:
        msg = (
            "SQLite export did not inspect every classification disclosure: "
            f"source={source_path}, inspected={row_count}, expected={actual_disclosures}"
        )
        raise ValueError(msg)

    summary_disclosures = _summary_disclosure_count(payload)
    if summary_disclosures is not None and summary_disclosures != actual_disclosures:
        msg = (
            "Classification disclosure summary does not match loaded disclosures: "
            f"source={source_path}, summary={summary_disclosures}, loaded={actual_disclosures}"
        )
        raise ValueError(msg)


def _row_year(row: dict[str, Any]) -> str:
    disclosed_date = str(row.get("disclosed_date") or "").strip()
    year = disclosed_date[:4]
    if len(year) == 4 and year.isdigit():
        return year
    return "unknown"


def _collect_classification_rows_by_year(
    payload: dict[str, Any],
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], int, int]:
    rows_by_year: dict[str, list[dict[str, Any]]] = {}
    row_count = 0
    companies = list(payload.get("companies") or [])
    for company_index, company in enumerate(companies):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        company_key = _company_key(company)
        company_name = company.get("company_name")
        company_id = company.get("company_id")
        market = company.get("market")
        badges = list(company.get("badges") or [])
        badges_json = json.dumps(badges, ensure_ascii=False)
        for disclosure in _company_disclosures(company, company_index):
            if cancel_check and cancel_check():
                raise RuntimeError("Job cancelled")
            disclosed_at = disclosure.get("disclosed_at")
            row = {
                "row_no": disclosure.get("row_no"),
                "company_key": company_key,
                "company_name": company_name,
                "company_id": company_id,
                "market": market,
                "badges_json": badges_json,
                "disclosed_at": disclosed_at,
                "disclosed_date": _date_part(disclosed_at),
                "title": disclosure.get("title"),
                "title_attr": disclosure.get("title_attr"),
                "title_base": disclosure.get("title_base")
                or disclosure.get("title_attr"),
                "title_display": disclosure.get("title_display")
                or disclosure.get("title"),
                "title_flags_json": json.dumps(
                    list(disclosure.get("title_flags") or []), ensure_ascii=False
                ),
                "is_correction_report": 1
                if disclosure.get("is_correction_report")
                else 0,
                "has_later_correction": 1
                if disclosure.get("has_later_correction")
                else 0,
                "acpt_no": disclosure.get("acpt_no") or disclosure.get("acptno"),
                "doc_no": disclosure.get("doc_no"),
                "submitter": disclosure.get("submitter"),
                "source_file": disclosure.get("source_file"),
                "source_page": disclosure.get("source_page"),
            }
            rows_by_year.setdefault(_row_year(row), []).append(row)
            row_count += 1
    return rows_by_year, len(companies), row_count


def _collect_source_folder_rows_by_year(
    source_folder: Path,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], int, int]:
    rows_by_year: dict[str, list[dict[str, Any]]] = {}
    seen_keys: set[tuple[str, str, str, str]] = set()
    company_keys: set[str] = set()
    row_count = 0
    for body_path in _find_source_body_files(source_folder):
        if cancel_check and cancel_check():
            raise RuntimeError("Job cancelled")
        for record in _parse_source_body_file(body_path):
            key = (
                str(record.get("acpt_no") or ""),
                str(record.get("company_id") or ""),
                str(record.get("disclosed_at") or ""),
                str(record.get("title") or ""),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            disclosed_at = record.get("disclosed_at")
            row = {
                "row_no": record.get("row_no"),
                "company_key": record.get("company_key") or _company_key(record),
                "company_name": record.get("company_name"),
                "company_id": record.get("company_id"),
                "market": record.get("market"),
                "badges_json": json.dumps(
                    list(record.get("badges") or []), ensure_ascii=False
                ),
                "disclosed_at": disclosed_at,
                "disclosed_date": _date_part(disclosed_at),
                "title": record.get("title"),
                "title_attr": record.get("title_attr"),
                "title_base": record.get("title_base") or record.get("title_attr"),
                "title_display": record.get("title_display") or record.get("title"),
                "title_flags_json": json.dumps(
                    list(record.get("title_flags") or []), ensure_ascii=False
                ),
                "is_correction_report": 1 if record.get("is_correction_report") else 0,
                "has_later_correction": 1 if record.get("has_later_correction") else 0,
                "acpt_no": record.get("acpt_no") or record.get("acptno"),
                "doc_no": record.get("doc_no"),
                "submitter": record.get("submitter"),
                "source_file": record.get("source_file"),
                "source_page": record.get("source_page"),
            }
            company_key = str(
                row.get("company_key")
                or row.get("company_id")
                or row.get("company_name")
                or ""
            ).strip()
            if company_key:
                company_keys.add(company_key)
            rows_by_year.setdefault(_row_year(row), []).append(row)
            row_count += 1
    return rows_by_year, len(company_keys), row_count


def _resolve_shard_workers(value: object, shard_count: int) -> int:
    if shard_count <= 1:
        return 1
    cpu_limit = os.cpu_count() or 1
    try:
        requested = int(value or cpu_limit)
    except (TypeError, ValueError):
        requested = cpu_limit
    if requested <= 1:
        return 1
    return max(1, min(requested, shard_count, cpu_limit))


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
    try:
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
    except sqlite3.OperationalError:
        return False
    return True


def _write_metadata(
    connection: sqlite3.Connection,
    *,
    classification_path: Path,
    source_type: str,
    table_name: str,
    companies: int,
    disclosures: int,
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
        "source_classification_path": str(classification_path),
        "source_type": source_type,
        "table_name": table_name,
        "shard_year": shard_year,
        "companies": str(companies),
        "disclosures": str(disclosures),
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
    classification_path: Path,
    source_type: str,
    table_name: str,
    shard_year: str,
) -> dict[str, Any]:
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = shard_path.with_suffix(f"{shard_path.suffix}.tmp")
    if temporary_path.exists():
        temporary_path.unlink()

    company_keys = {
        str(
            row.get("company_key")
            or row.get("company_id")
            or row.get("company_name")
            or ""
        ).strip()
        for row in rows
        if str(
            row.get("company_key")
            or row.get("company_id")
            or row.get("company_name")
            or ""
        ).strip()
    }
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
                classification_path=classification_path,
                source_type=source_type,
                table_name=table_name,
                companies=len(company_keys),
                disclosures=len(rows),
                fts_enabled=fts_enabled,
                shard_year=shard_year,
            )
    finally:
        connection.close()

    temporary_path.replace(shard_path)
    return {
        "year": shard_year,
        "path": str(shard_path),
        "relative_path": shard_path.name,
        "companies": len(company_keys),
        "disclosures": len(rows),
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
                    classification_path=source_path,
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
                    classification_path=source_path,
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
    classification_path_raw = str(body.get("classification_path") or "").strip()
    source_type, source_path = _resolve_source(classification_path_raw, root_directory)

    output_path_raw = str(body.get("output_path") or "").strip()
    manifest_path = _manifest_output_path(output_path_raw, source_path)
    shard_root = _shard_directory(manifest_path)
    table_name = _normalize_table_name(body.get("table_name"))

    if progress_callback:
        progress_callback("공시 메타데이터를 로드합니다...")

    if source_type == "classification":
        payload = load_company_classification_file(source_path)
        rows_by_year, companies, row_count = _collect_classification_rows_by_year(
            payload, cancel_check=cancel_check
        )
        _validate_classification_disclosure_counts(payload, row_count, source_path)
    else:
        rows_by_year, companies, row_count = _collect_source_folder_rows_by_year(
            source_path, cancel_check=cancel_check
        )
    shard_workers = _resolve_shard_workers(
        body.get("table_workers") or body.get("shard_workers"), len(rows_by_year)
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
        "source_path": str(source_path),
        "source_classification_path": str(source_path)
        if source_type == "classification"
        else "",
        "manifest_path": str(manifest_path),
        "shard_root": str(shard_root),
        "table_name": table_name,
        "summary": {
            "companies": companies,
            "disclosures": row_count,
            "shards": len(shards),
        },
        "shards": shards,
    }
    _write_manifest(manifest_path, manifest)
    return {
        "format": "finiq_disclosure_table_build_v1",
        "manifest_format": MANIFEST_FORMAT,
        "source_type": source_type,
        "source_path": str(source_path),
        "source_classification_path": str(source_path)
        if source_type == "classification"
        else "",
        "output_path": str(manifest_path),
        "manifest_path": str(manifest_path),
        "shard_root": str(shard_root),
        "table_name": table_name,
        "summary": {
            "companies": companies,
            "disclosures": row_count,
            "shards": len(shards),
            "fts_enabled": all(shard["fts_enabled"] for shard in shards)
            if shards
            else False,
            "schema_version": TABLE_SCHEMA_VERSION,
        },
        "shards": shards,
    }
