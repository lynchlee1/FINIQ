from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from finiq.market_desk.web.app import app, config
from finiq.market_desk.web.features.downloads import kind_common
from finiq.market_desk.web.jobs import job_manager


def _wait_for_kind_terminal(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/api/download/jobs/{job_id}")
        assert response.status_code == 200
        snapshot = response.json()
        if snapshot["status"] in {"completed", "failed", "cancelled"}:
            return snapshot
        time.sleep(0.01)
    raise AssertionError("KIND download job did not reach a terminal state")


def test_job_retention_setting_expires_both_job_api_types(
    tmp_path: Path, monkeypatch
) -> None:
    original_retention = config.job_retention_minutes
    monkeypatch.setattr(config, "settings_path", str(tmp_path / "settings.json"))
    monkeypatch.setattr(config, "job_retention_minutes", original_retention)
    client = TestClient(app)
    generic_job_id = ""
    kind_job_id = ""

    try:
        setting_response = client.post(
            "/api/settings", json={"job_retention_minutes": 1}
        )
        assert setting_response.status_code == 200
        assert setting_response.json()["job_retention_minutes"] == 1

        generic_response = client.post(
            "/api/disclosures/html/download/start",
            json={
                "data_root": str(tmp_path),
                "separate_output_directory": True,
                "output_directory": str(tmp_path / "external"),
                "json": {},
            },
        )
        assert generic_response.status_code == 200
        generic_job_id = generic_response.json()["job_id"]
        generic_snapshot = client.get(
            f"/api/disclosures/html/jobs/{generic_job_id}"
        ).json()
        assert generic_snapshot["status"] == "failed"

        kind_response = client.post(
            "/api/download/run/start",
            json={
                "data_root": str(tmp_path),
                "separate_output_directory": True,
                "output_directory": str(tmp_path / "list"),
                "mode": "single",
                "start_date": "invalid",
                "end_date": "invalid",
            },
        )
        assert kind_response.status_code == 200
        kind_job_id = kind_response.json()["job_id"]
        assert _wait_for_kind_terminal(client, kind_job_id)["status"] == "failed"

        expired_at = time.time() - 61
        generic_job = job_manager.get_job(generic_job_id)
        assert generic_job is not None
        generic_job.updated_at = expired_at
        with kind_common._DOWNLOAD_JOBS_LOCK:
            kind_common._DOWNLOAD_JOBS[kind_job_id].updated_at = expired_at

        assert (
            client.get(f"/api/disclosures/html/jobs/{generic_job_id}").status_code
            == 404
        )
        assert client.get(f"/api/download/jobs/{kind_job_id}").status_code == 404
    finally:
        if generic_job_id:
            with job_manager._lock:
                job_manager._jobs.pop(generic_job_id, None)
        if kind_job_id:
            with kind_common._DOWNLOAD_JOBS_LOCK:
                kind_common._DOWNLOAD_JOBS.pop(kind_job_id, None)
                kind_common._CANCELLED_DOWNLOAD_JOBS.discard(kind_job_id)
        job_manager.set_retention_minutes(original_retention)
        kind_common.configure_download_job_retention(original_retention)
