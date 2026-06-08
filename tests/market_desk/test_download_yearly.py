from __future__ import annotations

import time
from typing import Any

import pytest

import finiq.market_desk.web.download as download_module


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
