"""Parsing helpers and parsed-artifact access for downloaded KIND result files.

This module owns responsibilities after download completes:

- inspect downloaded ``*.body`` folders
- parse/export them into JSON artifacts
- build/load company-classification artifacts consumed by the insight layer

It intentionally does not own download orchestration or chart/insight processing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from finiq.data_scraper.storage.classification_store import (
    company_classification_artifact_complete,
    load_company_classification_artifact,
    load_company_classification_company as load_company_classification_company_artifact,
    load_company_classification_index as load_company_classification_index_artifact,
)
from .explorer import (
    build_result_folder_records,
    detect_pagination,
    extract_unique_disclosure_titles,
    find_latest_result_folder,
    find_result_folders,
    load_folder_disclosure_rows,
    load_folder_simpletable_rows,
    load_workflow_input,
)
from finiq.data_scraper.workflow import (
    KindCompanyClassificationIntegrityError,
    KindCompanyClassificationIntegrityReport,
    KindCompanyClassificationResult,
    KindModeBatchResult,
    diagnose_kind_company_classification_integrity,
    export_kind_company_classification,
    export_kind_mode_batch,
    export_kind_mode_folder,
    export_kind_mode_folders,
)

_DEFAULT_EMPTY_CLASSIFICATION = {
    "summary": {
        "source_folders": 0,
        "body_files": 0,
        "companies": 0,
        "disclosures": 0,
    },
    "companies": [],
}


from finiq.data.common import company_classification_path, find_company_classification_files


def _iter_body_files(root_directory: Path) -> list[Path]:
    return sorted(root_directory.rglob("*_post_page_*.body"))


def company_classification_is_stale(
    root_directory: str | Path,
    *,
    output_path: str | Path | None = None,
) -> bool:
    """Return True when the company-classification JSON should be regenerated."""
    root = Path(root_directory).resolve()
    destination = (
        Path(output_path).resolve()
        if output_path is not None
        else company_classification_path(root)
    )
    body_files = _iter_body_files(root)
    if not body_files:
        return False
    if not company_classification_artifact_complete(destination):
        return True

    destination_mtime = destination.stat().st_mtime
    return any(body_path.stat().st_mtime > destination_mtime for body_path in body_files)


def load_company_classification(
    root_directory: str | Path,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Load or regenerate the company-classified disclosure payload for one root."""
    root = Path(root_directory).resolve()
    if not root.is_dir():
        msg = f"Not a directory: {root}"
        raise NotADirectoryError(msg)

    destination = company_classification_path(root)
    if force_refresh or company_classification_is_stale(root, output_path=destination):
        export_kind_company_classification(root, output_path=destination, compact=False)

    if not company_classification_artifact_complete(destination):
        return {
            "summary": dict(_DEFAULT_EMPTY_CLASSIFICATION["summary"]),
            "companies": list(_DEFAULT_EMPTY_CLASSIFICATION["companies"]),
        }
    return load_company_classification_artifact(destination)


def load_company_classification_index(
    root_directory: str | Path,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Load or regenerate company-classification index metadata."""
    root = Path(root_directory).resolve()
    if not root.is_dir():
        msg = f"Not a directory: {root}"
        raise NotADirectoryError(msg)

    destination = company_classification_path(root)
    if force_refresh or company_classification_is_stale(root, output_path=destination):
        export_kind_company_classification(root, output_path=destination, compact=False)

    if not company_classification_artifact_complete(destination):
        return {
            "summary": dict(_DEFAULT_EMPTY_CLASSIFICATION["summary"]),
            "companies": list(_DEFAULT_EMPTY_CLASSIFICATION["companies"]),
            "shards": [],
        }
    return load_company_classification_index_artifact(destination)


def load_company_classification_company(
    root_directory: str | Path,
    company_key: str,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Load one company disclosure bundle, regenerating the parsed artifact when needed."""
    root = Path(root_directory).resolve()
    if not root.is_dir():
        msg = f"Not a directory: {root}"
        raise NotADirectoryError(msg)

    destination = company_classification_path(root)
    if force_refresh or company_classification_is_stale(root, output_path=destination):
        export_kind_company_classification(root, output_path=destination, compact=False)

    if not company_classification_artifact_complete(destination):
        msg = f"Classification artifact not found: {destination}"
        raise FileNotFoundError(msg)
    return load_company_classification_company_artifact(destination, company_key)


def load_company_classification_file(file_path: str | Path) -> dict[str, Any]:
    """Load a prebuilt company-classification artifact."""
    target = Path(file_path).resolve()
    if not company_classification_artifact_complete(target):
        msg = f"Classification artifact not found or incomplete: {target}"
        raise FileNotFoundError(msg)
    return load_company_classification_artifact(target)


def load_company_classification_index_file(file_path: str | Path) -> dict[str, Any]:
    """Load only the metadata/index portion of a prebuilt classification artifact."""
    target = Path(file_path).resolve()
    if not company_classification_artifact_complete(target):
        msg = f"Classification artifact not found or incomplete: {target}"
        raise FileNotFoundError(msg)
    return load_company_classification_index_artifact(target)


def load_company_classification_company_file(
    file_path: str | Path,
    company_key: str,
) -> dict[str, Any]:
    """Load one company disclosure bundle from a prebuilt classification artifact."""
    target = Path(file_path).resolve()
    if not company_classification_artifact_complete(target):
        msg = f"Classification artifact not found or incomplete: {target}"
        raise FileNotFoundError(msg)
    return load_company_classification_company_artifact(target, company_key)


__all__ = [
    "KindCompanyClassificationIntegrityError",
    "KindCompanyClassificationIntegrityReport",
    "KindCompanyClassificationResult",
    "KindModeBatchResult",
    "build_result_folder_records",
    "company_classification_is_stale",
    "company_classification_path",
    "detect_pagination",
    "diagnose_kind_company_classification_integrity",
    "export_kind_company_classification",
    "export_kind_mode_batch",
    "export_kind_mode_folder",
    "export_kind_mode_folders",
    "extract_unique_disclosure_titles",
    "find_company_classification_files",
    "find_latest_result_folder",
    "find_result_folders",
    "load_company_classification",
    "load_company_classification_company",
    "load_company_classification_company_file",
    "load_company_classification_file",
    "load_company_classification_index",
    "load_company_classification_index_file",
    "load_folder_disclosure_rows",
    "load_folder_simpletable_rows",
    "load_workflow_input",
]
