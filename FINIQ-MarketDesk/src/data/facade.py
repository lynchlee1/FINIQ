"""Load prebuilt classification artifacts for the visualization layer.

Data collection/parsing/export is owned by FINIQ-DataScraper.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CLASSIFICATION_INDEX_FORMAT = "company_classification_index_v2"

_DEFAULT_EMPTY_CLASSIFICATION = {
    "summary": {
        "source_folders": 0,
        "body_files": 0,
        "companies": 0,
        "disclosures": 0,
    },
    "companies": [],
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        msg = f"Classification JSON not found: {path}"
        raise FileNotFoundError(msg)
    if not path.is_file():
        msg = f"Classification JSON is not a file: {path}"
        raise IsADirectoryError(msg)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"Classification JSON must contain an object root: {path}"
        raise ValueError(msg)
    return payload


def _company_key(company: dict[str, Any]) -> str:
    return str(
        company.get("company_key") or company.get("company_id") or company.get("company_name") or ""
    ).strip()


def _company_disclosure_bounds(company: dict[str, Any]) -> tuple[str | None, str | None]:
    disclosed_values = [
        str(disclosure.get("disclosed_at") or "").strip()
        for disclosure in list(company.get("disclosures") or [])
        if str(disclosure.get("disclosed_at") or "").strip()
    ]
    if not disclosed_values:
        return None, None
    return min(disclosed_values), max(disclosed_values)


def _build_company_index_entry(company: dict[str, Any], *, shard: str | None) -> dict[str, Any]:
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


def _load_companies_from_shards(index_path: Path, index_payload: dict[str, Any]) -> list[dict[str, Any]]:
    companies: list[dict[str, Any]] = []
    for shard_entry in index_payload.get("shards") or []:
        relative_file = str(shard_entry.get("file") or "").strip()
        if not relative_file:
            continue
        shard_path = (index_path.parent / relative_file).resolve()
        shard_payload = _load_json(shard_path)
        companies.extend(list(shard_payload.get("companies") or []))
    return companies


def company_classification_path(root_directory: str | Path) -> Path:
    """Return the default company-classification JSON path for *root_directory*."""
    return Path(root_directory).resolve() / "kind.company_classification.json"


def find_company_classification_files(root_directory: str | Path) -> list[Path]:
    """Return prebuilt company-classification JSON files under *root_directory*."""
    root = Path(root_directory).resolve()
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.rglob("*.json")
        if "company_classification" in path.name
        and not path.name.endswith(".partial.json")
    )


def company_classification_is_stale(
    root_directory: str | Path,
    *,
    output_path: str | Path | None = None,
) -> bool:
    """Return True when the classification file is missing."""
    destination = (
        Path(output_path).resolve()
        if output_path is not None
        else company_classification_path(root_directory)
    )
    return not destination.exists()


def load_company_classification(
    root_directory: str | Path,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Load a prebuilt company-classification payload for one root folder."""
    root = Path(root_directory).resolve()
    if not root.is_dir():
        msg = f"Not a directory: {root}"
        raise NotADirectoryError(msg)
    if force_refresh:
        msg = (
            "force_refresh is not supported in FINIQ-MarketDesk. "
            "Generate artifacts in FINIQ-DataScraper."
        )
        raise RuntimeError(msg)

    destination = company_classification_path(root)
    if not destination.exists():
        return {
            "summary": dict(_DEFAULT_EMPTY_CLASSIFICATION["summary"]),
            "companies": list(_DEFAULT_EMPTY_CLASSIFICATION["companies"]),
        }
    return load_company_classification_file(destination)


def load_company_classification_index(
    root_directory: str | Path,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Load a prebuilt company-classification index payload for one root folder."""
    root = Path(root_directory).resolve()
    if not root.is_dir():
        msg = f"Not a directory: {root}"
        raise NotADirectoryError(msg)
    if force_refresh:
        msg = (
            "force_refresh is not supported in FINIQ-MarketDesk. "
            "Generate artifacts in FINIQ-DataScraper."
        )
        raise RuntimeError(msg)

    destination = company_classification_path(root)
    if not destination.exists():
        return {
            "summary": dict(_DEFAULT_EMPTY_CLASSIFICATION["summary"]),
            "companies": list(_DEFAULT_EMPTY_CLASSIFICATION["companies"]),
            "shards": [],
        }
    return load_company_classification_index_file(destination)


def load_company_classification_company(
    root_directory: str | Path,
    company_key: str,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Load one company disclosure bundle from a prebuilt classification file."""
    root = Path(root_directory).resolve()
    if not root.is_dir():
        msg = f"Not a directory: {root}"
        raise NotADirectoryError(msg)
    if force_refresh:
        msg = (
            "force_refresh is not supported in FINIQ-MarketDesk. "
            "Generate artifacts in FINIQ-DataScraper."
        )
        raise RuntimeError(msg)

    destination = company_classification_path(root)
    return load_company_classification_company_file(destination, company_key)


def load_company_classification_file(file_path: str | Path) -> dict[str, Any]:
    """Load a prebuilt company-classification JSON file."""
    target = Path(file_path).resolve()
    payload = _load_json(target)
    if payload.get("format") != CLASSIFICATION_INDEX_FORMAT:
        return payload
    return {
        "summary": dict(payload.get("summary") or {}),
        "companies": _load_companies_from_shards(target, payload),
    }


def load_company_classification_index_file(file_path: str | Path) -> dict[str, Any]:
    """Load only the metadata/index portion of a prebuilt classification file."""
    target = Path(file_path).resolve()
    payload = _load_json(target)
    if payload.get("format") == CLASSIFICATION_INDEX_FORMAT:
        return {
            "summary": dict(payload.get("summary") or {}),
            "companies": [
                _normalize_company_index_entry(company)
                for company in list(payload.get("companies") or [])
            ],
            "shards": list(payload.get("shards") or []),
        }
    return {
        "summary": dict(payload.get("summary") or {}),
        "companies": [
            _build_company_index_entry(company, shard=None)
            for company in list(payload.get("companies") or [])
        ],
        "shards": [],
    }


def load_company_classification_company_file(
    file_path: str | Path,
    company_key: str,
) -> dict[str, Any]:
    """Load one company disclosure bundle from a prebuilt classification file."""
    target = Path(file_path).resolve()
    payload = _load_json(target)
    normalized_key = str(company_key).strip()
    if not normalized_key:
        msg = "company_key must not be empty"
        raise ValueError(msg)

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
    shard_payload = _load_json(shard_path)
    for company in list(shard_payload.get("companies") or []):
        if _company_key(company) == normalized_key:
            return company
    msg = f"Company shard entry not found: {normalized_key}"
    raise KeyError(msg)


__all__ = [
    "company_classification_is_stale",
    "company_classification_path",
    "find_company_classification_files",
    "load_company_classification",
    "load_company_classification_company",
    "load_company_classification_company_file",
    "load_company_classification_file",
    "load_company_classification_index",
    "load_company_classification_index_file",
]
