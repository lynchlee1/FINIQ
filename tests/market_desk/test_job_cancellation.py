from __future__ import annotations

import time
import pytest
import pandas as pd
from pathlib import Path
from fastapi.testclient import TestClient

from finiq.market_desk.web.app import app, _run_job_worker
from finiq.market_desk.web.jobs import JobManager, job_manager
from finiq.data.assets_excel import (
    convert_asset_excels_to_wide_parquet,
    default_account_mappings,
)

def test_job_manager_cancel_and_is_cancelled():
    job_id = "test-job-1"
    job_manager.create_job(job_id, "test_kind")
    assert job_manager.get_job(job_id).status == "queued"
    assert not job_manager.is_cancelled(job_id)

    job_manager.cancel_job(job_id)
    assert job_manager.get_job(job_id).status == "cancelled"
    assert job_manager.is_cancelled(job_id)

def test_start_job_cancelled_prevention():
    job_id = "test-job-2"
    job_manager.create_job(job_id, "test_kind")
    job_manager.cancel_job(job_id)
    
    # start_job should return False because it is cancelled
    started = job_manager.start_job(job_id)
    assert not started
    assert job_manager.get_job(job_id).status == "cancelled"


def test_job_manager_reserves_cancellation_before_job_creation():
    manager = JobManager()
    job_id = "33333333333343338333333333333333"

    assert manager.cancel_job(job_id, reserve_missing=True) is True
    job = manager.create_job(job_id, "section_inspect")

    assert job.status == "cancelled"
    assert manager.start_job(job_id) is False


def test_html_cancel_route_reserves_client_generated_job_id():
    job_id = "44444444444444448444444444444444"

    response = TestClient(app).post(
        "/api/disclosures/html/cancel",
        json={"job_id": job_id},
    )
    job = job_manager.create_job(job_id, "section_inspect")

    assert response.status_code == 200
    assert job.status == "cancelled"

def test_cancel_endpoints():
    client = TestClient(app)
    
    # 1. table build cancel route
    job_id = "table-cancel-test"
    job_manager.create_job(job_id, "table_build")
    response = client.post("/api/disclosures/table/build/cancel", json={"job_id": job_id})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert job_manager.is_cancelled(job_id)

    # 2. integrated cancel route
    job_id = "integrated-cancel-test"
    job_manager.create_job(job_id, "integrated_convert")
    response = client.post("/api/integrated-data/cancel", json={"job_id": job_id})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert job_manager.is_cancelled(job_id)

    # 3. utility cancel route
    job_id = "utility-cancel-test"
    job_manager.create_job(job_id, "utility_partition")
    response = client.post("/api/utility/cancel", json={"job_id": job_id})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert job_manager.is_cancelled(job_id)

    # 4. assets excel cancel route
    job_id = "assets-cancel-test"
    job_manager.create_job(job_id, "asset_excel_convert")
    response = client.post("/api/assets/excels/cancel", json={"job_id": job_id})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert job_manager.is_cancelled(job_id)

def test_queued_cancel_race_condition():
    # Simulate a background task running _run_job_worker on a pre-cancelled job
    job_id = "race-test-job"
    job_manager.create_job(job_id, "table_build")
    # Cancel the job while it is still queued
    job_manager.cancel_job(job_id)
    
    # Try running the worker
    # Since start_job returns False, the handler shouldn't run, and status should stay cancelled
    _run_job_worker(job_id, "table_build", {})
    
    assert job_manager.get_job(job_id).status == "cancelled"
    assert job_manager.get_job(job_id).error is None

def test_assets_excel_cancel_callback_abort(tmp_path):
    source_dir = tmp_path / "assets"
    output_dir = tmp_path / "merged"
    source_dir.mkdir()
    
    # Write a simple dummy sheet
    excel_path = source_dir / "sample.xlsx"
    pd.DataFrame(
        [
            ["Time Series (Company)"],
            ["D A T E", "종가"],
            [pd.Timestamp("2020-01-01"), 100],
        ]
    ).to_excel(excel_path, sheet_name="종가", header=False, index=False)
    
    # Define a cancel_check that returns True to simulate user clicking Cancel immediately
    def cancel_check():
        return True

    # Running conversion with cancel_check returning True should abort with RuntimeError
    with pytest.raises(RuntimeError, match="Job cancelled"):
        convert_asset_excels_to_wide_parquet(
            source_directory=source_dir,
            output_directory=output_dir,
            account_mappings=default_account_mappings(),
            cancel_check=cancel_check,
        )

def test_complete_and_fail_do_not_overwrite_cancelled():
    job_id = "test-job-complete-overwrite"
    job_manager.create_job(job_id, "test_kind")
    job_manager.cancel_job(job_id)
    assert job_manager.get_job(job_id).status == "cancelled"

    # Try completing the job
    job_manager.complete_job(job_id, {"result": "ok"})
    # Status should remain cancelled, and result should not be updated
    assert job_manager.get_job(job_id).status == "cancelled"
    assert job_manager.get_job(job_id).result is None

    # Try failing the job
    job_manager.fail_job(job_id, "some error")
    # Status should remain cancelled, and error should not be updated
    assert job_manager.get_job(job_id).status == "cancelled"
    assert job_manager.get_job(job_id).error is None

def test_cancel_endpoints_validation():
    client = TestClient(app)
    
    # Test 400 (empty job_id)
    response = client.post("/api/disclosures/table/build/cancel", json={"job_id": ""})
    assert response.status_code == 400
    assert response.json()["detail"] == "Missing job_id"

    response = client.post("/api/disclosures/table/build/cancel", json={})
    assert response.status_code == 400
    assert response.json()["detail"] == "Missing job_id"

    # Test 404 (non-existent job_id)
    response = client.post("/api/disclosures/table/build/cancel", json={"job_id": "non-existent-job-id-123"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"
