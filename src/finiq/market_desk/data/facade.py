"""Load prebuilt classification artifacts for the visualization layer.

Data collection/parsing/export is owned by finiq.data_scraper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from finiq.data.common import company_classification_path, find_company_classification_files
from finiq.data_scraper.data.facade import (
    load_company_classification_company_file,
    load_company_classification_file,
    load_company_classification_index_file,
)
from finiq.data_scraper.storage.classification_store import company_classification_artifact_complete

_DEFAULT_EMPTY_CLASSIFICATION = {
    "summary": {
        "source_folders": 0,
        "body_files": 0,
        "companies": 0,
        "disclosures": 0,
    },
    "companies": [],
}


def company_classification_is_stale(
    root_directory: str | Path,
    *,
    output_path: str | Path | None = None,
) -> bool:
    """Return True when the classification artifact is missing."""
    destination = (
        Path(output_path).resolve()
        if output_path is not None
        else company_classification_path(root_directory)
    )
    return not company_classification_artifact_complete(destination)


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
            "force_refresh is not supported in finiq.market_desk. "
            "Generate artifacts in finiq.data_scraper."
        )
        raise RuntimeError(msg)

    destination = company_classification_path(root)
    if not company_classification_artifact_complete(destination):
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
            "force_refresh is not supported in finiq.market_desk. "
            "Generate artifacts in finiq.data_scraper."
        )
        raise RuntimeError(msg)

    destination = company_classification_path(root)
    if not company_classification_artifact_complete(destination):
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
    """Load one company disclosure bundle from a prebuilt classification artifact."""
    root = Path(root_directory).resolve()
    if not root.is_dir():
        msg = f"Not a directory: {root}"
        raise NotADirectoryError(msg)
    if force_refresh:
        msg = (
            "force_refresh is not supported in finiq.market_desk. "
            "Generate artifacts in finiq.data_scraper."
        )
        raise RuntimeError(msg)

    destination = company_classification_path(root)
    return load_company_classification_company_file(destination, company_key)


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
