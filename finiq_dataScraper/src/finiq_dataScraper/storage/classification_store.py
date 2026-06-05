"""Storage helpers for company-classification index, shards, and partial caches."""

from __future__ import annotations

import json
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
    shard: str | None,
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


def write_company_classification_artifact(
    index_path: str | Path,
    payload: dict[str, Any],
    *,
    compact: bool,
    shard_company_count: int = DEFAULT_CLASSIFICATION_SHARD_COMPANIES,
) -> Path:
    target = Path(index_path).resolve()
    companies = list(payload.get("companies") or [])
    shard_dir = company_classification_shard_dir(target)
    shard_dir.mkdir(parents=True, exist_ok=True)
    for existing_path in shard_dir.glob("*.json"):
        existing_path.unlink()

    index_companies: list[dict[str, Any]] = []
    shard_entries: list[dict[str, Any]] = []
    for shard_number, start in enumerate(range(0, len(companies), max(1, shard_company_count))):
        shard_companies = companies[start : start + max(1, shard_company_count)]
        shard_file = f"companies-{shard_number:05d}.json"
        shard_path = shard_dir / shard_file
        relative_shard_path = str((shard_dir / shard_file).relative_to(target.parent))
        _write_json(
            shard_path,
            {"companies": shard_companies},
            compact=compact,
        )
        shard_entries.append(
            {
                "file": relative_shard_path,
                "companies": len(shard_companies),
                "disclosures": sum(len(company.get("disclosures") or []) for company in shard_companies),
            }
        )
        for company in shard_companies:
            index_companies.append(_build_company_index_entry(company, shard=relative_shard_path))

    index_payload = {
        "format": CLASSIFICATION_INDEX_FORMAT,
        "summary": dict(payload.get("summary") or {}),
        "shards": shard_entries,
        "companies": index_companies,
    }
    _write_json(target, index_payload, compact=compact)
    return target


def load_company_classification_artifact(index_path: str | Path) -> dict[str, Any]:
    target = Path(index_path).resolve()
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("format") != CLASSIFICATION_INDEX_FORMAT:
        return payload

    companies: list[dict[str, Any]] = []
    for shard_entry in payload.get("shards") or []:
        relative_file = str(shard_entry.get("file") or "").strip()
        if not relative_file:
            continue
        shard_path = (target.parent / relative_file).resolve()
        shard_payload = json.loads(shard_path.read_text(encoding="utf-8"))
        companies.extend(list(shard_payload.get("companies") or []))
    return {
        "summary": dict(payload.get("summary") or {}),
        "companies": companies,
    }


def load_company_classification_index(index_path: str | Path) -> dict[str, Any]:
    target = Path(index_path).resolve()
    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("format") == CLASSIFICATION_INDEX_FORMAT:
        return {
            "summary": dict(payload.get("summary") or {}),
            "companies": [
                _normalize_company_index_entry(company)
                for company in list(payload.get("companies") or [])
            ],
            "shards": list(payload.get("shards") or []),
        }

    companies = [
        _build_company_index_entry(company, shard=None)
        for company in list(payload.get("companies") or [])
    ]
    return {
        "summary": dict(payload.get("summary") or {}),
        "companies": companies,
        "shards": [],
    }


def load_company_classification_company(
    index_path: str | Path,
    company_key: str,
) -> dict[str, Any]:
    target = Path(index_path).resolve()
    normalized_key = str(company_key).strip()
    if not normalized_key:
        msg = "company_key must not be empty"
        raise ValueError(msg)

    payload = json.loads(target.read_text(encoding="utf-8"))
    if payload.get("format") != CLASSIFICATION_INDEX_FORMAT:
        for company in list(payload.get("companies") or []):
            if _company_key(company) == normalized_key:
                return company
        msg = f"Company not found in classification payload: {normalized_key}"
        raise KeyError(msg)

    company_entry = next(
        (
            company
            for company in list(payload.get("companies") or [])
            if _company_key(company) == normalized_key
        ),
        None,
    )
    if company_entry is None:
        msg = f"Company not found in classification index: {normalized_key}"
        raise KeyError(msg)

    relative_shard_path = str(company_entry.get("shard") or "").strip()
    if not relative_shard_path:
        msg = f"Shard path missing for company: {normalized_key}"
        raise KeyError(msg)
    shard_path = (target.parent / relative_shard_path).resolve()
    shard_payload = json.loads(shard_path.read_text(encoding="utf-8"))
    for company in list(shard_payload.get("companies") or []):
        if _company_key(company) == normalized_key:
            return company

    msg = f"Company shard entry not found: {normalized_key}"
    raise KeyError(msg)


def company_classification_artifact_complete(index_path: str | Path) -> bool:
    target = Path(index_path).resolve()
    if not target.exists() or not target.is_file():
        return False
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return False
    if payload.get("format") != CLASSIFICATION_INDEX_FORMAT:
        return True
    shard_entries = list(payload.get("shards") or [])
    if not shard_entries:
        return True
    for shard_entry in shard_entries:
        relative_file = str(shard_entry.get("file") or "").strip()
        if not relative_file:
            return False
        shard_path = (target.parent / relative_file).resolve()
        if not shard_path.exists() or not shard_path.is_file():
            return False
    return True


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
