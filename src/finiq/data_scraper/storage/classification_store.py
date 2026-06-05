"""Storage helpers for company-classification index, replacing JSON shards with SQLite for scalability."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .result_files import KIND_REPAIR_OVERLAY_DIRNAME, sorted_result_page_paths

CLASSIFICATION_INDEX_FORMAT = "company_classification_index_v2"
CLASSIFICATION_PARTIAL_FORMAT = "company_classification_partial_v1"
DEFAULT_CLASSIFICATION_SHARD_COMPANIES = 200

def _company_key(company: dict[str, Any]) -> str:
    return str(company.get("company_id") or company.get("company_name") or "").strip()

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

def _normalize_company_index_entry(company: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_key": str(company.get("company_key") or _company_key(company)),
        "company_name": company.get("company_name"),
        "company_id": company.get("company_id"),
        "market": company.get("market"),
        "badges": list(company.get("badges") or []),
        "disclosure_count": int(company.get("disclosure_count") or 0),
        "first_disclosed_at": company.get("first_disclosed_at"),
        "last_disclosed_at": company.get("last_disclosed_at"),
        "shard": company.get("shard"),
    }

def company_classification_shard_dir(index_path: str | Path) -> Path:
    # Kept for backward compatibility signatures if needed, but not actively used in SQLite logic
    target = Path(index_path).resolve()
    return target.parent / f"{target.stem}.shards"

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
    repair_root = target / KIND_REPAIR_OVERLAY_DIRNAME
    if repair_root.exists():
        for extra_path in sorted(repair_root.rglob("*")):
            if not extra_path.is_file():
                continue
            stat = extra_path.stat()
            files.append(
                {
                    "name": str(extra_path.relative_to(target)),
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
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
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
    # If the caller provides a JSON path, we map it to .sqlite
    if target.suffix == ".json":
        return target.with_suffix(".sqlite")
    return target

def write_company_classification_artifact(
    index_path: str | Path,
    payload: dict[str, Any],
    *,
    compact: bool,
    shard_company_count: int = DEFAULT_CLASSIFICATION_SHARD_COMPANIES,
) -> Path:
    target_sqlite = _sqlite_path(index_path)
    target_sqlite.parent.mkdir(parents=True, exist_ok=True)
    
    # Remove existing shards directory if it exists (cleanup old architecture)
    old_target = Path(index_path).resolve()
    shard_dir = company_classification_shard_dir(old_target)
    if shard_dir.exists():
        for existing_path in shard_dir.glob("*.json"):
            existing_path.unlink()
        try:
            shard_dir.rmdir()
        except OSError:
            pass

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
        # Fallback to legacy JSON format loading if SQLite doesn't exist
        old_target = Path(index_path).resolve()
        if old_target.exists():
            payload = json.loads(old_target.read_text(encoding="utf-8"))
            companies = []
            for shard_entry in payload.get("shards") or []:
                relative_file = str(shard_entry.get("file") or "").strip()
                if not relative_file: continue
                shard_path = (old_target.parent / relative_file).resolve()
                if shard_path.exists():
                    shard_payload = json.loads(shard_path.read_text(encoding="utf-8"))
                    companies.extend(list(shard_payload.get("companies") or []))
            return {
                "summary": dict(payload.get("summary") or {}),
                "companies": companies,
            }
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
        old_target = Path(index_path).resolve()
        if old_target.exists():
            payload = json.loads(old_target.read_text(encoding="utf-8"))
            return {
                "summary": dict(payload.get("summary") or {}),
                "companies": [
                    _normalize_company_index_entry(company)
                    for company in list(payload.get("companies") or [])
                ],
                "shards": list(payload.get("shards") or []),
            }
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
        old_target = Path(index_path).resolve()
        if old_target.exists():
            payload = json.loads(old_target.read_text(encoding="utf-8"))
            # simplified legacy loading loop
            for shard_entry in payload.get("shards") or []:
                shard_path = (old_target.parent / str(shard_entry.get("file"))).resolve()
                if shard_path.exists():
                    shard_payload = json.loads(shard_path.read_text(encoding="utf-8"))
                    for c in shard_payload.get("companies", []):
                        if _company_key(c) == normalized_key:
                            return c
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
    if target_sqlite.exists():
        return True
        
    old_target = Path(index_path).resolve()
    if not old_target.exists() or not old_target.is_file():
        return False
    try:
        payload = json.loads(old_target.read_text(encoding="utf-8"))
        if payload.get("format") != CLASSIFICATION_INDEX_FORMAT:
            return True
        for shard_entry in payload.get("shards", []):
            shard_path = (old_target.parent / str(shard_entry.get("file"))).resolve()
            if not shard_path.exists(): return False
        return True
    except Exception:
        return False

__all__ = [
    "CLASSIFICATION_INDEX_FORMAT",
    "CLASSIFICATION_PARTIAL_FORMAT",
    "DEFAULT_CLASSIFICATION_SHARD_COMPANIES",
    "company_classification_artifact_complete",
    "company_classification_partial_path",
    "company_classification_shard_dir",
    "folder_partial_signature",
    "load_company_classification_artifact",
    "load_company_classification_company",
    "load_company_classification_index",
    "load_folder_partial_cache",
    "write_company_classification_artifact",
    "write_folder_partial_cache",
]
