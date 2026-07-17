from __future__ import annotations

from pathlib import Path
import time
from typing import Any

import pytest

import finiq.market_desk.web.features.downloads.kind_runner as download_module
from finiq.market_desk.web.features.downloads.kind_common import _detect_pagination


def test_detect_pagination_rejects_latest_page_when_it_is_corrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "001_post_page_00001.body"
    latest = tmp_path / "002_post_page_00002.body"
    first.write_bytes(b"valid")
    latest.write_bytes(b"corrupt")
    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_common.pagination_info",
        lambda content: {"total_pages": 2, "total_items": 150}
        if content == b"valid"
        else None,
    )

    with pytest.raises(ValueError, match="pagination not found"):
        _detect_pagination(tmp_path)


def test_detect_pagination_sorts_four_digit_pages_numerically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page_999 = tmp_path / "999_post_page_00999.body"
    page_1000 = tmp_path / "1000_post_page_01000.body"
    page_999.write_bytes(b"page-999")
    page_1000.write_bytes(b"page-1000")
    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_common.pagination_info",
        lambda content: {
            "total_pages": 1000,
            "total_items": 100_000,
            "marker": content.decode(),
        },
    )

    result = _detect_pagination(tmp_path)

    assert result is not None
    assert result["latest_file"] == page_1000.name
    assert result["marker"] == "page-1000"


def test_run_yearly_returns_promptly_when_parallel_worker_fails(tmp_path, monkeypatch) -> None:
    def fake_run_yearly_task(
        task: dict[str, Any],
        *,
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
