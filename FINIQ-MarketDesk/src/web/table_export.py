"""Build SQLite disclosure tables from FINIQ classification JSON."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import sqlite3
from typing import Any

from data.facade import load_company_classification_file
from web.service import (
    _find_source_body_files,
    _parse_source_body_file,
    list_classification_files,
    resolve_default_classification,
)


TABLE_SCHEMA_VERSION = 1
DEFAULT_TABLE_NAME = "disclosures"
MANIFEST_FORMAT = "finiq_disclosure_table_manifest_v1"
SQLITE_FORMAT = "finiq_disclosure_table_sqlite_shard"


def _date_part(value: object) -> str:
    return str(value or "").strip().split(" ", 1)[0]


def _company_key(company: dict[str, Any]) -> str:
    return str(
        company.get("company_key") or company.get("company_id") or company.get("company_name") or ""
    ).strip()


def _normalize_table_name(value: object) -> str:
    table_name = str(value or DEFAULT_TABLE_NAME).strip()
    if not table_name:
        return DEFAULT_TABLE_NAME
    if not table_name.replace("_", "").isalnum() or table_name[0].isdigit():
        msg = "table_name must contain only letters, numbers, and underscores, and must not start with a digit"
        raise ValueError(msg)
    return table_name


def _default_output_path(classification_path: Path) -> Path:
    return classification_path.with_name(f"{classification_path.stem}.sqlite_manifest.json")


def _shard_directory(manifest_path: Path) -> Path:
    return manifest_path.with_name(f"{manifest_path.stem}_shards")


def _manifest_output_path(raw_path: str, classification_path: Path) -> Path:
    if not raw_path:
        return _default_output_path(classification_path).resolve()
    output_path = Path(raw_path).expanduser().resolve()
    if output_path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
        return output_path.with_suffix(".sqlite_manifest.json")
    if output_path.suffix:
        return output_path
    return output_path / _default_output_path(classification_path).name


def _source_has_body_files(path: Path) -> bool:
    return path.is_dir() and bool(_find_source_body_files(path))


def _resolve_source(raw_path: str, root_directory: str) -> tuple[str, Path]:
    root_path = Path(root_directory).expanduser().resolve() if root_directory else None

    if raw_path:
        candidate = Path(raw_path).expanduser().resolve()
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
                    return ("classification", Path(root_resolved).expanduser().resolve())
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


def _iter_disclosure_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for company in list(payload.get("companies") or []):
        company_key = _company_key(company)
        company_name = company.get("company_name")
        company_id = company.get("company_id")
        market = company.get("market")
        badges = list(company.get("badges") or [])
        for disclosure in list(company.get("disclosures") or []):
            disclosed_at = disclosure.get("disclosed_at")
            rows.append(
                {
                    "company_key": company_key,
                    "company_name": company_name,
                    "company_id": company_id,
                    "market": market,
                    "badges_json": json.dumps(badges, ensure_ascii=False),
                    "disclosed_at": disclosed_at,
                    "disclosed_date": _date_part(disclosed_at),
                    "title": disclosure.get("title"),
                    "acpt_no": disclosure.get("acpt_no") or disclosure.get("acptno"),
                    "doc_no": disclosure.get("doc_no"),
                    "submitter": disclosure.get("submitter"),
                }
            )
    return rows


def _iter_source_folder_rows(source_folder: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str, str]] = set()
    for body_path in _find_source_body_files(source_folder):
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
            rows.append(
                {
                    "company_key": record.get("company_key") or _company_key(record),
                    "company_name": record.get("company_name"),
                    "company_id": record.get("company_id"),
                    "market": record.get("market"),
                    "badges_json": json.dumps(list(record.get("badges") or []), ensure_ascii=False),
                    "disclosed_at": disclosed_at,
                    "disclosed_date": _date_part(disclosed_at),
                    "title": record.get("title"),
                    "acpt_no": record.get("acpt_no") or record.get("acptno"),
                    "doc_no": record.get("doc_no"),
                    "submitter": record.get("submitter"),
                }
            )
    return rows


def _row_year(row: dict[str, Any]) -> str:
    disclosed_date = str(row.get("disclosed_date") or "").strip()
    year = disclosed_date[:4]
    if len(year) == 4 and year.isdigit():
        return year
    return "unknown"


def _group_rows_by_year(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_row_year(row), []).append(row)
    return grouped


def _create_disclosure_table(connection: sqlite3.Connection, table_name: str) -> None:
    quoted_table = f'"{table_name}"'
    connection.execute(f"DROP TABLE IF EXISTS {quoted_table}")
    connection.execute(
        f"""
        CREATE TABLE {quoted_table} (
            id INTEGER PRIMARY KEY,
            company_key TEXT,
            company_name TEXT,
            company_id TEXT,
            market TEXT,
            badges_json TEXT NOT NULL DEFAULT '[]',
            disclosed_at TEXT,
            disclosed_date TEXT,
            title TEXT,
            acpt_no TEXT,
            doc_no TEXT,
            submitter TEXT
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
        str(row.get("company_key") or row.get("company_id") or row.get("company_name") or "").strip()
        for row in rows
        if str(row.get("company_key") or row.get("company_id") or row.get("company_name") or "").strip()
    }
    connection = sqlite3.connect(temporary_path)
    try:
        with connection:
            _create_disclosure_table(connection, table_name)
            connection.executemany(
                f"""
                INSERT INTO "{table_name}" (
                    company_key,
                    company_name,
                    company_id,
                    market,
                    badges_json,
                    disclosed_at,
                    disclosed_date,
                    title,
                    acpt_no,
                    doc_no,
                    submitter
                )
                VALUES (
                    :company_key,
                    :company_name,
                    :company_id,
                    :market,
                    :badges_json,
                    :disclosed_at,
                    :disclosed_date,
                    :title,
                    :acpt_no,
                    :doc_no,
                    :submitter
                )
                """,
                rows,
            )
            indexes = _create_indexes(connection, table_name)
            fts_enabled = _create_fts_table(connection, table_name)
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


def build_disclosure_table_payload(body: dict[str, Any]) -> dict[str, Any]:
    root_directory = str(body.get("root_directory") or "").strip()
    classification_path_raw = str(body.get("classification_path") or "").strip()
    source_type, source_path = _resolve_source(classification_path_raw, root_directory)

    output_path_raw = str(body.get("output_path") or "").strip()
    manifest_path = _manifest_output_path(output_path_raw, source_path)
    shard_root = _shard_directory(manifest_path)
    table_name = _normalize_table_name(body.get("table_name"))
    if source_type == "classification":
        payload = load_company_classification_file(source_path)
        rows = _iter_disclosure_rows(payload)
        companies = len(list(payload.get("companies") or []))
    else:
        rows = _iter_source_folder_rows(source_path)
        companies = len(
            {
                str(row.get("company_key") or row.get("company_id") or row.get("company_name") or "").strip()
                for row in rows
                if str(row.get("company_key") or row.get("company_id") or row.get("company_name") or "").strip()
            }
        )
    rows_by_year = _group_rows_by_year(rows)

    shards: list[dict[str, Any]] = []
    for year, shard_rows in sorted(rows_by_year.items()):
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

    manifest = {
        "format": MANIFEST_FORMAT,
        "schema_version": TABLE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_type": source_type,
        "source_path": str(source_path),
        "source_classification_path": str(source_path) if source_type == "classification" else "",
        "manifest_path": str(manifest_path),
        "shard_root": str(shard_root),
        "table_name": table_name,
        "summary": {
            "companies": companies,
            "disclosures": len(rows),
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
        "source_classification_path": str(source_path) if source_type == "classification" else "",
        "output_path": str(manifest_path),
        "manifest_path": str(manifest_path),
        "shard_root": str(shard_root),
        "table_name": table_name,
        "summary": {
            "companies": companies,
            "disclosures": len(rows),
            "shards": len(shards),
            "fts_enabled": all(shard["fts_enabled"] for shard in shards) if shards else False,
            "schema_version": TABLE_SCHEMA_VERSION,
        },
        "shards": shards,
    }
