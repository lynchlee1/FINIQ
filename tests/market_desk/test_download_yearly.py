from __future__ import annotations

from pathlib import Path
import time
from typing import Any

import pytest

import finiq.market_desk.web.features.downloads.kind_runner as download_module


def test_run_resume_starts_from_first_missing_page(tmp_path, monkeypatch) -> None:
    for page_number in (1, 2, 4):
        (tmp_path / f"{page_number:03d}_post_page_{page_number:05d}.body").write_bytes(
            b"saved"
        )

    saved_input = {
        "request_headers": {},
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "page_size": 100,
        "wait_seconds_between_requests": 0,
        "timeout": 1,
    }
    received_start_pages: list[int] = []

    monkeypatch.setattr(
        download_module,
        "_detect_pagination",
        lambda _path: {"total_pages": 4, "downloaded_pages": 3},
    )
    monkeypatch.setattr(
        download_module,
        "_load_workflow_input",
        lambda _path: saved_input,
    )
    monkeypatch.setattr(
        download_module,
        "_download_integrity_status",
        lambda _path, _page_size: {"total_pages": 4, "downloaded_pages": 3},
    )

    def fake_validate(page_path: Path, *, expected_page_size: int) -> dict[str, int]:
        if not page_path.is_file():
            raise ValueError("missing page")
        return {"current_page": int(page_path.name[:3])}

    def fake_download_pages(**kwargs: Any) -> None:
        received_start_pages.append(int(kwargs["start_page"]))

    monkeypatch.setattr(download_module, "validate_downloaded_result_page", fake_validate)
    monkeypatch.setattr(download_module, "download_pages", fake_download_pages)

    download_module._run_resume(
        {
            "output_directory": str(tmp_path),
            "parallel_strategy": "pages",
            "worker_count": 2,
        }
    )

    assert received_start_pages == [3]


def test_run_yearly_returns_promptly_when_parallel_worker_fails(tmp_path, monkeypatch) -> None:
    def fake_run_yearly_task(
        task: dict[str, Any],
        *,
        resume_yearly: bool,
        progress_callback: Any | None = None,
        cancel_check: Any | None = None,
    ) -> dict[str, Any]:
        if task["start_date"].startswith("2025"):
            raise RuntimeError("network failed")
        time.sleep(1.0)
        return {
            "output_directory": task["output_directory"],
            "download_status": {
                "total_pages": 0,
                "downloaded_pages": 0,
                "missing_pages": [],
                "invalid_pages": [],
            },
        }

    monkeypatch.setattr(download_module, "_run_yearly_task", fake_run_yearly_task)
    monkeypatch.setattr(download_module, "_as_worker_count", lambda payload: 2)

    started_at = time.monotonic()
    with pytest.raises(ValueError, match="20250101_20251231 download failed: network failed"):
        download_module._run_yearly(
            {
                "output_directory": str(tmp_path),
                "start_date": "2025-01-01",
                "end_date": "2026-01-01",
                "page_size": 100,
                "wait_seconds": 0,
                "timeout": 1,
                "worker_count": 2,
            }
        )

    assert time.monotonic() - started_at < 0.5


def test_run_yearly_pages_strategy_processes_years_sequentially(
    tmp_path, monkeypatch
) -> None:
    received_tasks: list[dict[str, Any]] = []

    def fake_run_yearly_task(
        task: dict[str, Any],
        *,
        resume_yearly: bool,
        progress_callback: Any | None = None,
        cancel_check: Any | None = None,
    ) -> dict[str, Any]:
        received_tasks.append(task)
        return {
            "output_directory": task["output_directory"],
            "download_status": {
                "total_pages": 1,
                "downloaded_pages": 1,
                "missing_pages": [],
            },
        }

    monkeypatch.setattr(download_module, "_run_yearly_task", fake_run_yearly_task)
    monkeypatch.setattr(download_module, "_as_worker_count", lambda payload: 3)

    result = download_module._run_yearly(
        {
            "output_directory": str(tmp_path),
            "start_date": "2024-01-01",
            "end_date": "2025-12-31",
            "page_size": 100,
            "wait_seconds": 0,
            "timeout": 1,
            "worker_count": 3,
            "parallel_strategy": "pages",
        }
    )

    assert result["worker_count"] == 1
    assert result["parallel_strategy"] == "pages"
    assert [task["start_date"] for task in received_tasks] == [
        "2024-01-01",
        "2025-01-01",
    ]
    assert all(task["worker_count"] == 3 for task in received_tasks)
    assert all(task["parallel_strategy"] == "pages" for task in received_tasks)
