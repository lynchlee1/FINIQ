"""Helpers for browsing and exporting downloaded KIND result folders."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from typing import Any

from parse import disclosure_file_rows, html_to_json, pagination_info
from storage.result_files import sorted_result_page_paths


def find_result_folders(root_directory: str | Path) -> list[Path]:
    """Return all folders under *root_directory* that contain downloaded body files."""
    root = Path(root_directory).resolve()
    if not root.is_dir():
        return []
    folders = {body_path.parent.resolve() for body_path in root.rglob("*_post_page_*.body")}
    return sorted(folders)


def _resolve_folder_parallelism(parallelism: int | None, item_count: int) -> int:
    if item_count <= 1:
        return max(1, item_count)
    requested = parallelism if parallelism is not None else (os.cpu_count() or 1)
    return max(1, min(int(requested), item_count))


def load_workflow_input(folder: str | Path) -> dict[str, Any] | None:
    """Load the saved workflow input JSON for one downloaded result folder."""
    input_path = Path(folder).resolve() / "kind_workflow.input.json"
    if not input_path.exists():
        return None
    return json.loads(input_path.read_text(encoding="utf-8"))


def detect_pagination(folder: str | Path) -> dict[str, Any] | None:
    """Infer pagination summary from the latest downloaded body file in *folder*."""
    target = Path(folder).resolve()
    body_files = sorted_result_page_paths(target)
    if not body_files:
        return None
    latest = body_files[-1]
    info = pagination_info(latest.read_bytes())
    if info is None:
        return None
    info["downloaded_pages"] = len(body_files)
    info["latest_file"] = latest.name
    return info


def load_folder_simpletable_rows(folder: str | Path) -> list[list[str]]:
    """Load all downloaded body files in *folder* as a flat simple-table grid."""
    target = Path(folder).resolve()
    rows: list[list[str]] = []
    for body_path in sorted_result_page_paths(target):
        parsed = html_to_json(body_path.read_bytes(), mode="simpletable")
        current_rows = parsed.get("simpletable", [])
        if isinstance(current_rows, list):
            rows.extend(current_rows)
    return rows


def load_folder_disclosure_rows(folder: str | Path) -> list[dict[str, Any]]:
    """Load parsed disclosure records from all downloaded body files in *folder*."""
    target = Path(folder).resolve()
    disclosures: list[dict[str, Any]] = []
    for body_path in sorted_result_page_paths(target):
        disclosures.extend(disclosure_file_rows(body_path))
    return disclosures


def extract_unique_disclosure_titles(
    disclosure_rows: list[dict[str, Any]],
) -> list[str]:
    """Return disclosure titles once each, preserving the first-seen order."""
    unique_titles: list[str] = []
    seen_titles: set[str] = set()
    for row in disclosure_rows:
        title = " ".join(str(row.get("title") or "").split())
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        unique_titles.append(title)
    return unique_titles


def _build_result_folder_record(task: tuple[str, str]) -> dict[str, Any]:
    folder_str, root_str = task
    folder = Path(folder_str)
    root = Path(root_str)
    body_files = sorted_result_page_paths(folder)
    saved_input = load_workflow_input(folder) or {}
    pagination = detect_pagination(folder) or {}
    relative_folder = folder.relative_to(root) if folder != root else Path(".")
    return {
        "folder_path": str(folder),
        "folder_name": "." if relative_folder == Path(".") else str(relative_folder),
        "body_files": len(body_files),
        "downloaded_pages": pagination.get("downloaded_pages"),
        "total_pages": pagination.get("total_pages"),
        "total_items": pagination.get("total_items"),
        "start_date": saved_input.get("start_date"),
        "end_date": saved_input.get("end_date"),
        "page_size": saved_input.get("page_size"),
        "latest_file": pagination.get("latest_file"),
    }


def build_result_folder_records(
    root_directory: str | Path,
    *,
    parallelism: int | None = None,
) -> list[dict[str, Any]]:
    """Build table-friendly summary rows for discovered result folders."""
    root = Path(root_directory).resolve()
    folders = find_result_folders(root)
    if not folders:
        return []

    worker_count = _resolve_folder_parallelism(parallelism, len(folders))
    tasks = [(str(folder), str(root)) for folder in folders]
    if worker_count == 1:
        return [_build_result_folder_record(task) for task in tasks]
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="kind-data-folder") as executor:
        return list(executor.map(_build_result_folder_record, tasks))


def find_latest_result_folder(root_directory: str | Path) -> Path | None:
    """Return the most recent downloaded result folder under *root_directory*."""
    records = build_result_folder_records(root_directory)
    if not records:
        return None

    def _sort_key(record: dict[str, Any]) -> tuple[str, str]:
        end_date = str(record.get("end_date") or "")
        folder_name = str(record.get("folder_name") or "")
        return (end_date, folder_name)

    latest = max(records, key=_sort_key)
    return Path(str(latest["folder_path"]))
