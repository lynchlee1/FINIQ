"""Storage helpers for company-classification index, replacing JSON shards with SQLite for scalability."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .result_files import sorted_result_page_paths

CLASSIFICATION_INDEX_FORMAT = "company_classification_index_v2"
CLASSIFICATION_PARTIAL_FORMAT = "company_classification_partial_v3"
DEFAULT_CLASSIFICATION_SHARD_COMPANIES = 200

def _company_key(company: dict[str, Any]) -> str:
    company_id = str(company.get("company_id") or "").strip()
    if not company_id:
        raise ValueError("company_id is required for classification records")
    return company_id

def _company_disclosure_bounds(company: dict[str, Any]) -> tuple[str | None, str | None]:
    disclosed_values = [
        str(disclosure.get("disclosed_at") or "").strip()
        for disclosure in list(company.get("disclosures") or [])
        if str(disclosure.get("disclosed_at") or "").strip()
    ]
    if not disclosed_values:
        return None, None
    return min(disclosed_values), max(disclosed_values)

def _build_company_index_entry(
    company: dict[str, Any],
    *,
    shard: str | None = None,
) -> dict[str, Any]:
    first_disclosed_at, last_disclosed_at = _company_disclosure_bounds(company)
    return {
        "company_key": _company_key(company),
        "company_name": company.get("company_name"),
        "company_id": company.get("company_id"),
        "market": company.get("market"),
        "badges": list(company.get("badges") or []),
        "disclosure_count": len(company.get("disclosures") or []),
        "first_disclosed_at": first_disclosed_at,
        "last_disclosed_at": last_disclosed_at,
        "shard": shard,
    }

def company_classification_partial_path(folder: str | Path) -> Path:
    target = Path(folder).resolve()
    return target / "kind.company_classification.partial.json"

def folder_partial_signature(folder: str | Path) -> dict[str, Any]:
    target = Path(folder).resolve()
    files = []
    for body_path in sorted_result_page_paths(target):
        stat = body_path.stat()
        files.append(
            {
                "name": body_path.name,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    return {"files": files}

def _write_json(path: Path, payload: dict[str, Any], *, compact: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    if compact:
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)

def load_folder_partial_cache(
    folder: str | Path,
    *,
    require_validated: bool,
) -> dict[str, Any] | None:
    cache_path = company_classification_partial_path(folder)
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if payload.get("format") != CLASSIFICATION_PARTIAL_FORMAT:
        return None
    if payload.get("signature") != folder_partial_signature(folder):
        return None
    if require_validated and not bool(payload.get("validated")):
        return None
    return payload

def write_folder_partial_cache(
    folder: str | Path,
    *,
    validated: bool,
    body_files: int,
    parsed_disclosures: int,
    classified_disclosures: int,
    unlinked_disclosures: int,
    intra_folder_duplicates: int,
    companies: list[dict[str, Any]],
) -> Path:
    cache_path = company_classification_partial_path(folder)
    payload = {
        "format": CLASSIFICATION_PARTIAL_FORMAT,
        "validated": validated,
        "signature": folder_partial_signature(folder),
        "body_files": body_files,
        "parsed_disclosures": parsed_disclosures,
        "classified_disclosures": classified_disclosures,
        "unlinked_disclosures": unlinked_disclosures,
        "intra_folder_duplicates": intra_folder_duplicates,
        "companies": companies,
    }
    _write_json(cache_path, payload, compact=True)
    return cache_path


# --- SQLite Implementations ---

def _init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            company_key TEXT PRIMARY KEY,
            company_name TEXT,
            company_id TEXT,
            market TEXT,
            disclosure_count INTEGER,
            first_disclosed_at TEXT,
            last_disclosed_at TEXT,
            raw_json TEXT
        )
    """)
    conn.commit()

def _sqlite_path(index_path: str | Path) -> Path:
    target = Path(index_path).resolve()
    if target.suffix.lower() != ".sqlite":
        raise ValueError("classification path must use the .sqlite extension")
    return target

def write_company_classification_artifact(
    index_path: str | Path,
    payload: dict[str, Any],
    *,
    compact: bool,
) -> Path:
    target_sqlite = _sqlite_path(index_path)
    target_sqlite.parent.mkdir(parents=True, exist_ok=True)

    companies = list(payload.get("companies") or [])
    
    with sqlite3.connect(target_sqlite) as conn:
        _init_db(conn)
        
        # Save Metadata
        summary_str = json.dumps(payload.get("summary") or {})
        conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", ("format", CLASSIFICATION_INDEX_FORMAT))
        conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", ("summary", summary_str))
        
        # Save Companies
        conn.execute("DELETE FROM companies")  # clear existing
        
        insert_records = []
        for company in companies:
            c_key = _company_key(company)
            c_name = company.get("company_name")
            c_id = company.get("company_id")
            market = company.get("market")
            d_count = len(company.get("disclosures") or [])
            fd_at, ld_at = _company_disclosure_bounds(company)
            
            # Using separators to act similar to compact JSON
            raw = json.dumps(company, ensure_ascii=False, separators=(",", ":") if compact else None)
            
            insert_records.append((c_key, c_name, c_id, market, d_count, fd_at, ld_at, raw))
            
        conn.executemany("""
            INSERT INTO companies 
            (company_key, company_name, company_id, market, disclosure_count, first_disclosed_at, last_disclosed_at, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, insert_records)
        conn.commit()
    
    return target_sqlite

def load_company_classification_artifact(index_path: str | Path) -> dict[str, Any]:
    target_sqlite = _sqlite_path(index_path)
    if not target_sqlite.exists():
        return {}
        
    with sqlite3.connect(target_sqlite) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key='summary'")
        summary_row = cursor.fetchone()
        summary = json.loads(summary_row[0]) if summary_row else {}
        
        cursor.execute("SELECT raw_json FROM companies")
        companies = [json.loads(row[0]) for row in cursor.fetchall()]
        
    return {
        "format": CLASSIFICATION_INDEX_FORMAT,
        "summary": summary,
        "companies": companies,
    }

def load_company_classification_index(index_path: str | Path) -> dict[str, Any]:
    target_sqlite = _sqlite_path(index_path)
    if not target_sqlite.exists():
        return {}

    with sqlite3.connect(target_sqlite) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM metadata WHERE key='summary'")
        summary_row = cursor.fetchone()
        summary = json.loads(summary_row[0]) if summary_row else {}
        
        cursor.execute("""
            SELECT raw_json FROM companies
        """)
        companies_out = []
        for row in cursor.fetchall():
            c_dict = json.loads(row[0])
            # SQLite replaces the shard logic, so shard=None
            companies_out.append(_build_company_index_entry(c_dict, shard=None))
            
    return {
        "format": CLASSIFICATION_INDEX_FORMAT,
        "summary": summary,
        "companies": companies_out,
        "shards": [],
    }

def load_company_classification_company(
    index_path: str | Path,
    company_key: str,
) -> dict[str, Any]:
    target_sqlite = _sqlite_path(index_path)
    normalized_key = str(company_key).strip()
    if not normalized_key:
        raise ValueError("company_key must not be empty")

    if not target_sqlite.exists():
        raise KeyError(f"Company not found in classification index: {normalized_key}")
        
    with sqlite3.connect(target_sqlite) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT raw_json FROM companies WHERE company_key = ?", (normalized_key,))
        row = cursor.fetchone()
        if not row:
            raise KeyError(f"Company not found in classification index: {normalized_key}")
        return json.loads(row[0])

def company_classification_artifact_complete(index_path: str | Path) -> bool:
    target_sqlite = _sqlite_path(index_path)
    return target_sqlite.is_file()

__all__ = [
    "CLASSIFICATION_INDEX_FORMAT",
    "CLASSIFICATION_PARTIAL_FORMAT",
    "DEFAULT_CLASSIFICATION_SHARD_COMPANIES",
    "company_classification_artifact_complete",
    "company_classification_partial_path",
    "folder_partial_signature",
    "load_company_classification_artifact",
    "load_company_classification_company",
    "load_company_classification_index",
    "load_folder_partial_cache",
    "write_company_classification_artifact",
    "write_folder_partial_cache",
]
