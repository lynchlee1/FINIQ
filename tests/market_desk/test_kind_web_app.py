from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
import finiq.market_desk.web.app as web_app
import finiq.market_desk.web.features.disclosures.filter_presets as filter_presets
from finiq.market_desk.web.app import _normalize_file_dialog_mode, app, config
from finiq.config import AppConfig
from finiq.market_desk.web.jobs import JobManager, job_manager
from finiq.market_desk.web.features.downloads.kind_common import (
    configure_download_job_retention,
)


def _save_filter_workflow(
    data_root: Path,
    *,
    mode: str = "bond_issuance",
    condition_blocks: list[dict[str, object]] | None = None,
) -> None:
    filter_presets.manage_filter_presets_payload(
        {
            "data_root": str(data_root),
            "action": "save",
            "preset": {
                "mode": mode,
                "condition_blocks": condition_blocks or [],
            },
        }
    )


def _filter_result(
    *,
    source_disclosures: int,
    source_offset: int,
    disclosures: list[dict[str, object]],
    inspected_disclosures: int | None = None,
    complete: bool = True,
    condition_blocks: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    inspected = (
        source_disclosures - source_offset
        if inspected_disclosures is None
        else inspected_disclosures
    )
    return {
        "format": "kind_disclosure_filter_v1",
        "source_type": "sqlite_manifest",
        "source_sqlite_manifest_path": "/tmp/sqlite_manifest.json",
        "filters": {"filter_blocks": condition_blocks or []},
        "summary": {
            "source_disclosures": source_disclosures,
            "source_body_files": 0,
            "source_offset": source_offset,
            "target_disclosures": source_disclosures - source_offset,
            "inspected_disclosures": inspected,
            "matched_disclosures": len(disclosures),
            "returned_disclosures": len(disclosures),
            "duplicate_disclosures": 0,
            "unique_acpt_numbers": len(disclosures),
        },
        "integrity": {
            "complete": complete,
            "passed": complete,
            "search_target_disclosures": source_disclosures - source_offset,
            "search_result_disclosures": len(disclosures),
            "inspected_disclosures": inspected,
        },
        "unique_titles": [str(row.get("title") or "") for row in disclosures],
        "external_html_download_acpt_numbers": [
            str(row["acpt_no"]) for row in disclosures
        ],
        "disclosures": disclosures,
    }


def _complete_filter_workflow(
    data_root: Path,
    *,
    mode: str,
    disclosures: list[dict[str, object]],
    condition_blocks: list[dict[str, object]] | None = None,
    parent_mode: str | None = None,
) -> dict[str, object]:
    run = filter_presets.begin_filter_workflow_payload(
        {
            "data_root": str(data_root),
            "mode": mode,
            "parent_mode": parent_mode,
            "filter_blocks": condition_blocks or [],
        }
    )
    result = _filter_result(
        source_disclosures=len(disclosures),
        source_offset=0,
        disclosures=disclosures,
        condition_blocks=condition_blocks,
    )
    filter_presets.mark_filter_workflow_query_completed(
        data_root=str(data_root),
        mode=mode,
        parent_mode=parent_mode,
        run_id=str(run["run_id"]),
        summary=result["summary"],
    )
    return filter_presets.complete_filter_workflow_payload(
        data_root=str(data_root),
        mode=mode,
        parent_mode=parent_mode,
        run_id=str(run["run_id"]),
        result=result,
    )


def _external_workspace_body(
    tmp_path: Path, source_json: dict, **body: object
) -> dict[str, object]:
    data_root = tmp_path / "workspace"
    filtered_path = data_root / "03-filter" / "bond_issuance" / "filtered.json"
    filtered_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_source_json = dict(source_json)
    if isinstance(source_json.get("disclosures"), list):
        normalized_source_json["disclosures"] = [
            {
                **disclosure,
                "disclosed_at": disclosure.get("disclosed_at")
                or f"{str(disclosure.get('acpt_no') or '')[:4]}-01-01",
            }
            for disclosure in source_json["disclosures"]
            if isinstance(disclosure, dict)
        ]
    filtered_path.write_text(
        json.dumps({"format": "kind_disclosure_filter_v1", **normalized_source_json}),
        encoding="utf-8",
    )
    return {"data_root": str(data_root), "mode": "bond_issuance", **body}

def test_api_config(tmp_path: Path):
    # Setup mock config
    config.output_root = str(tmp_path)
    config.quanti_dir = str(tmp_path)
    
    client = TestClient(app)
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "output_root" in data
    assert "quanti_dir" in data
    assert data["parallel_worker_count"] >= 1

def test_api_settings(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    config.settings_path = str(settings_path)
    
    client = TestClient(app)
    response = client.post("/api/settings", json={
        "output_root": str(tmp_path / "new_root"),
    })
    assert response.status_code == 200
    data = response.json()
    assert data["output_root"] == str((tmp_path / "new_root").resolve())
    assert settings_path.exists()


def test_api_settings_preserves_manual_sqlite_output(tmp_path: Path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "settings_path", str(settings_path))
    monkeypatch.setattr(config, "output_root", str(tmp_path / "database"))

    client = TestClient(app)
    response = client.post("/api/settings", json={
        "sqlite_output_directory": str(tmp_path / "sqlite_output"),
    })

    assert response.status_code == 200
    data = response.json()
    expected = str((tmp_path / "sqlite_output").resolve())
    assert data["sqlite_output_directory"] == expected

    response = client.get("/api/config")

    assert response.status_code == 200
    assert response.json()["sqlite_output_directory"] == expected


def test_api_settings_persists_asset_excel_directories(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    config.settings_path = str(settings_path)

    source_directory = tmp_path / "quantiwise"
    output_directory = tmp_path / "quantiwise_parquet"
    merge_input_directory = tmp_path / "merge_input"
    merge_output_directory = tmp_path / "merge_output"

    client = TestClient(app)
    response = client.post("/api/settings", json={
        "asset_excel_source_directory": str(source_directory),
        "asset_excel_output_directory": str(output_directory),
        "asset_excel_merge_input_directory": str(merge_input_directory),
        "asset_excel_merge_output_directory": str(merge_output_directory),
        "asset_excel_merge_same_directory": True,
        "asset_excel_cleanup_merged_items": False,
        "asset_excel_duplicate_scan_recursive": True,
    })

    assert response.status_code == 200
    data = response.json()
    assert data["asset_excel_source_directory"] == str(source_directory.resolve())
    assert data["asset_excel_output_directory"] == str(output_directory.resolve())
    assert data["asset_excel_merge_input_directory"] == str(merge_input_directory.resolve())
    assert data["asset_excel_merge_output_directory"] == str(merge_output_directory.resolve())
    assert data["asset_excel_merge_same_directory"] is True
    assert data["asset_excel_cleanup_merged_items"] is False
    assert data["asset_excel_duplicate_scan_recursive"] is True

    response = client.get("/api/config")

    assert response.status_code == 200
    data = response.json()
    assert data["asset_excel_source_directory"] == str(source_directory.resolve())
    assert data["asset_excel_output_directory"] == str(output_directory.resolve())
    assert data["asset_excel_merge_input_directory"] == str(merge_input_directory.resolve())
    assert data["asset_excel_merge_output_directory"] == str(merge_output_directory.resolve())
    assert data["asset_excel_merge_same_directory"] is True
    assert data["asset_excel_cleanup_merged_items"] is False
    assert data["asset_excel_duplicate_scan_recursive"] is True


def test_api_settings_persists_asset_excel_account_mappings(tmp_path: Path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "settings_path", str(settings_path))
    monkeypatch.setattr(config, "asset_excel_account_mappings", [])
    mappings = [
        {
            "account_id": "A90001",
            "account_name": "customClose",
            "sheet_name": "종가",
        },
        {
            "account_id": "A90002",
            "account_name": "customOpen",
            "sheet_name": "시가",
        },
    ]

    client = TestClient(app)
    response = client.post("/api/settings", json={
        "asset_excel_account_mappings": mappings,
    })

    assert response.status_code == 200
    assert response.json()["asset_excel_account_mappings"] == mappings

    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json()["asset_excel_account_mappings"] == mappings

    response = client.get("/api/assets/excels/account-mappings")
    assert response.status_code == 200
    assert response.json()["items"] == mappings

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["asset_excel_account_mappings"] == mappings


def test_api_settings_does_not_discover_files(tmp_path: Path, monkeypatch):
    def fail_discovery(*args, **kwargs):
        raise AssertionError("settings save should not scan source directories")

    settings_path = tmp_path / "settings.json"
    config.settings_path = str(settings_path)
    monkeypatch.setattr(web_app, "list_classification_files", fail_discovery)
    monkeypatch.setattr(web_app, "list_price_source_files", fail_discovery)

    client = TestClient(app)
    response = client.post("/api/settings", json={
        "output_root": str(tmp_path / "large_root"),
    })

    assert response.status_code == 200
    assert response.json()["classification_files"] == []
    assert response.json()["price_files"] == []


def test_download_inspect_folder_route_returns_bad_request_on_validation_error(monkeypatch):
    def fail_inspection(_payload):
        raise ValueError("inspection failed")

    monkeypatch.setattr(
        "finiq.market_desk.web.routers.download.inspect_download_output_directory_payload",
        fail_inspection,
    )

    client = TestClient(app)
    response = client.post("/api/download/inspect-folder", json={"output_directory": "/tmp"})

    assert response.status_code == 400
    assert response.json()["detail"] == "inspection failed"


def test_api_classifications(tmp_path: Path):
    # Create a dummy classification file
    kind_dir = tmp_path / "classification"
    kind_dir.mkdir(parents=True)
    # The name must contain 'company_classification' to be found
    (kind_dir / "test.company_classification.sqlite").write_bytes(b"")
    
    config.output_root = str(tmp_path)
    
    client = TestClient(app)
    response = client.get("/api/classifications")
    assert response.status_code == 200
    data = response.json()
    assert any("test.company_classification.sqlite" in f["name"] for f in data["classification_files"])

def test_api_price_sources(tmp_path: Path):
    price_root = tmp_path / "price_root"
    price_root.mkdir()
    price_dir = price_root / "test_price_folder"
    price_dir.mkdir()
    # Must have a parquet file to be considered a price directory
    (price_dir / "item.parquet").write_bytes(b"")
    
    # Mock config - the default root is parent of quanti_dir
    config.quanti_dir = str(price_root / "database" / "by_item")
    (price_root / "database" / "by_item").parent.mkdir(parents=True)
    
    client = TestClient(app)
    # We pass root_directory explicitly to be sure
    response = client.get(f"/api/price-sources?root_directory={price_root}")
    assert response.status_code == 200
    data = response.json()
    assert any("test_price_folder" in f["name"] for f in data["price_files"])


def test_file_dialog_mode_normalizes_folder_aliases() -> None:
    assert _normalize_file_dialog_mode("dir") == "folder"
    assert _normalize_file_dialog_mode("folder") == "folder"
    assert _normalize_file_dialog_mode("directory") == "folder"
    assert _normalize_file_dialog_mode("file") == "file"
    assert _normalize_file_dialog_mode("save") == "save"


def test_file_dialog_returns_selected_path(monkeypatch) -> None:
    def fake_choose_path(*, mode: str, title: str, default_path: str = "") -> str:
        assert mode == "folder"
        assert title == "선택"
        assert default_path == "/tmp"
        return "/tmp/output"

    monkeypatch.setattr(web_app, "_choose_finder_path", fake_choose_path)

    client = TestClient(app)
    response = client.post(
        "/api/file-dialog",
        json={"mode": "folder", "title": "선택", "default_path": "/tmp"},
    )

    assert response.status_code == 200
    assert response.json() == {"path": "/tmp/output", "cancelled": False}


def test_job_manager_status_updates_do_not_deadlock() -> None:
    manager = JobManager()
    manager.create_job("job-1", "download")

    thread = threading.Thread(target=manager.start_job, args=("job-1",), daemon=True)
    thread.start()
    thread.join(timeout=1)

    assert not thread.is_alive()
    snapshot = manager.get_snapshot("job-1")
    assert snapshot is not None
    assert snapshot["status"] == "running"
    assert any("JOB start" in line for line in snapshot["progress_log"])


def test_job_manager_snapshot_reports_elapsed_and_progress_silence(monkeypatch) -> None:
    import finiq.market_desk.web.jobs as jobs_module

    manager = JobManager()
    job = manager.create_job("job-timing", "parse")
    job.created_at = 100.0
    job.updated_at = 112.5
    monkeypatch.setattr(jobs_module.time, "time", lambda: 125.0)

    snapshot = manager.get_snapshot("job-timing")

    assert snapshot is not None
    assert snapshot["server_time"] == 125.0
    assert snapshot["elapsed_seconds"] == 25.0
    assert snapshot["progress_idle_seconds"] == 12.5


def test_job_manager_purges_only_expired_terminal_jobs() -> None:
    manager = JobManager(retention_minutes=60)
    completed = manager.create_job("completed", "download")
    manager.complete_job("completed", {"saved": True})
    running = manager.create_job("running", "download")
    manager.start_job("running")
    completed.updated_at = 100.0
    running.updated_at = 100.0

    assert manager.purge_expired(now=3701.0) == 1
    assert manager.get_job("completed") is None
    assert manager.get_job("running") is running


def test_job_manager_releases_many_expired_results() -> None:
    manager = JobManager(retention_minutes=1)
    jobs = []
    for index in range(1_000):
        job_id = f"expired-{index}"
        jobs.append(manager.create_job(job_id, "download"))
        manager.complete_job(job_id, {"payload": "x" * 1_024})
    for job in jobs:
        job.updated_at = 0.0

    assert manager.purge_expired(now=61.0) == 1_000
    assert manager._jobs == {}


def test_api_settings_persists_job_retention_minutes(
    tmp_path: Path, monkeypatch
) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "settings_path", str(settings_path))
    original_retention = config.job_retention_minutes

    try:
        response = TestClient(app).post(
            "/api/settings", json={"job_retention_minutes": 15}
        )

        assert response.status_code == 200
        assert response.json()["job_retention_minutes"] == 15
        assert json.loads(settings_path.read_text(encoding="utf-8"))[
            "job_retention_minutes"
        ] == 15
    finally:
        config.job_retention_minutes = original_retention
        job_manager.set_retention_minutes(original_retention)
        configure_download_job_retention(original_retention)


def test_api_settings_rejects_non_positive_job_retention_minutes() -> None:
    response = TestClient(app).post(
        "/api/settings", json={"job_retention_minutes": 0}
    )

    assert response.status_code == 400
    assert "must be >= 1" in response.json()["detail"]


def test_filter_disclosures_stream_writes_transfer_file(tmp_path: Path, monkeypatch) -> None:
    def fake_filter_disclosures_payload(body, progress_callback=None, **_kwargs):
        if progress_callback:
            progress_callback({
                "source_type": "sqlite_manifest",
                "unit_label": "공시",
                "completed": 1,
                "total": 2,
                "records": 1,
            })
        return _filter_result(
            source_disclosures=2,
            source_offset=int(body["source_offset"]),
            disclosures=[
                {"acpt_no": "1", "title": "A", "disclosed_at": "2025-01-01"},
                {"acpt_no": "2", "title": "B", "disclosed_at": "2025-01-02"},
            ],
        )

    monkeypatch.setattr(web_app, "filter_disclosures_payload", fake_filter_disclosures_payload)

    client = TestClient(app)
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)
    transfer_dir = tmp_path / "filtered"
    with client.stream(
        "POST",
        "/api/disclosures/filter",
        headers={"Accept": "application/x-ndjson"},
        json={
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "filter_blocks": [],
            "external_html_transfer_path": str(transfer_dir),
        },
    ) as response:
        assert response.status_code == 200
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert any(event["type"] == "progress" and event["progress"]["completed"] == 1 for event in events)
    result = next(event["payload"] for event in events if event["type"] == "result")
    transfer = result["external_html_download_transfer"]
    transfer_path = Path(transfer["path"])
    assert transfer["acpt_numbers"] == 2
    assert transfer_path.is_file()
    assert transfer_path == (
        transfer_dir / "bond_issuance" / "filtered.json"
    ).resolve()
    assert result["mode"] == "bond_issuance"
    assert result["filter_workflow"]["status"] == "completed"
    workflow_path = data_root / "03-filter" / "bond_issuance" / "filter.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    assert workflow["result_file"] == "filtered.json"
    assert workflow["steps"]["database_query"]["status"] == "completed"
    assert workflow["steps"]["record"]["status"] == "completed"
    assert "source_path" not in workflow["steps"]["database_query"]
    assert "path" not in workflow["steps"]["record"]
    workflow_result = json.loads(
        (workflow_path.parent / workflow["result_file"]).read_text(encoding="utf-8")
    )
    assert "source_sqlite_manifest_path" not in workflow_result
    assert workflow_result["summary"]["source_disclosures"] == 2
    assert workflow_result["integrity"] == {
        "complete": True,
        "passed": True,
        "search_target_disclosures": 2,
        "search_result_disclosures": 2,
        "inspected_disclosures": 2,
    }


def test_filter_disclosures_runs_derived_filter_with_parent_membership(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "workspace"
    parent_disclosures = [
        {"acpt_no": "20260101000001", "title": "A"},
        {"acpt_no": "20260101000002", "title": "B"},
    ]
    _save_filter_workflow(data_root, mode="parent")
    _complete_filter_workflow(
        data_root, mode="parent", disclosures=parent_disclosures
    )
    filter_presets.manage_filter_presets_payload(
        {
            "data_root": str(data_root),
            "action": "save",
            "preset": {
                "mode": "child",
                "parent_mode": "parent",
                "condition_blocks": [],
            },
        }
    )

    def fake_filter(body, **_kwargs):
        assert body["acpt_numbers"] == [
            "20260101000002",
            "20260101000001",
        ]
        assert body["restrict_acpt_numbers"] is True
        return _filter_result(
            source_disclosures=1,
            source_offset=int(body["source_offset"]),
            disclosures=[parent_disclosures[0]],
        )

    monkeypatch.setattr(web_app, "filter_disclosures_payload", fake_filter)
    transfer_dir = tmp_path / "filtered"
    response = TestClient(app).post(
        "/api/disclosures/filter",
        json={
            "data_root": str(data_root),
            "mode": "child",
            "parent_mode": "parent",
            "filter_blocks": [],
            "external_html_transfer_path": str(transfer_dir),
        },
    )

    assert response.status_code == 200
    result = response.json()
    transfer_path = Path(result["external_html_download_transfer"]["path"])
    assert transfer_path == (
        transfer_dir / "parent" / "subfilters" / "child" / "filtered.json"
    ).resolve()
    transferred = json.loads(transfer_path.read_text(encoding="utf-8"))
    assert transferred["parent_mode"] == "parent"
    assert len(transferred["parent_result_fingerprint"]) == 64


def test_filter_disclosures_stream_reports_long_progress_silence(
    tmp_path: Path, monkeypatch
) -> None:
    import finiq.market_desk.web.routers.workflows as workflows_router

    def slow_filter_disclosures_payload(body, **_kwargs):
        time.sleep(0.15)
        return _filter_result(
            source_disclosures=0,
            source_offset=int(body["source_offset"]),
            disclosures=[],
        )

    monkeypatch.setattr(web_app, "filter_disclosures_payload", slow_filter_disclosures_payload)
    monkeypatch.setattr(workflows_router, "FILTER_STREAM_HEARTBEAT_SECONDS", 0.01)
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)

    with TestClient(app).stream(
        "POST",
        "/api/disclosures/filter",
        headers={"Accept": "application/x-ndjson"},
        json={
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "filter_blocks": [],
            "external_html_transfer_path": str(tmp_path / "filtered"),
        },
    ) as response:
        events = [json.loads(line) for line in response.iter_lines() if line]

    heartbeat = next(event for event in events if event["type"] == "heartbeat")
    assert heartbeat["elapsed_seconds"] >= 0.01
    assert heartbeat["progress_idle_seconds"] >= 0.01


def test_search_disclosure_titles_is_read_only(tmp_path: Path, monkeypatch) -> None:
    received: dict[str, object] = {}

    def fake_search(payload):
        received.update(payload)
        return {
            "format": "finiq_disclosure_title_search_v1",
            "summary": {
                "source_disclosures": 2,
                "matched_disclosures": 1,
                "matched_titles": 1,
            },
            "titles": [{"title": "전환사채발행결정", "disclosures": 1}],
        }

    monkeypatch.setattr(web_app, "search_disclosure_titles_payload", fake_search)
    data_root = tmp_path / "workspace"
    response = TestClient(app).post(
        "/api/disclosures/titles/search",
        json={
            "data_root": str(data_root),
            "filter_blocks": [{"field": "title"}],
        },
    )

    assert response.status_code == 200
    assert received == {
        "data_root": str(data_root),
        "filter_blocks": [{"field": "title"}],
    }
    assert response.json()["titles"] == [
        {"title": "전환사채발행결정", "disclosures": 1}
    ]
    assert not (data_root / "03-filter").exists()


def test_search_disclosure_titles_background_job_keeps_result(
    tmp_path: Path, monkeypatch
) -> None:
    def fake_search(payload, progress_callback=None, cancel_check=None):
        assert cancel_check is not None
        if progress_callback:
            progress_callback({
                "source_type": "sqlite_manifest",
                "unit_label": "공시",
                "completed": 2,
                "total": 2,
                "records": 1,
            })
        return {
            "format": "finiq_disclosure_title_search_v1",
            "summary": {
                "source_disclosures": 2,
                "matched_disclosures": 1,
                "matched_titles": 1,
            },
            "titles": [{"title": "전환사채발행결정", "disclosures": 1}],
        }

    monkeypatch.setitem(web_app.JOB_HANDLERS, "title_search", fake_search)
    data_root = tmp_path / "workspace"
    client = TestClient(app)
    started = client.post(
        "/api/disclosures/titles/search/start",
        json={"data_root": str(data_root), "filter_blocks": []},
    )

    assert started.status_code == 200
    job_id = started.json()["job_id"]
    snapshot = client.get(f"/api/disclosures/titles/jobs/{job_id}")
    assert snapshot.status_code == 200
    assert snapshot.json()["status"] == "completed"
    assert any(
        "제목 검색 2/2 · 일치 1건" in line
        for line in snapshot.json()["progress_log"]
    )
    assert snapshot.json()["result"]["titles"] == [
        {"title": "전환사채발행결정", "disclosures": 1}
    ]
    assert not data_root.exists()


def test_filter_workflow_preserves_result_and_processes_only_new_rows(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)
    workflow_path = data_root / "03-filter" / "bond_issuance" / "filter.json"

    first_run = filter_presets.begin_filter_workflow_payload(
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "filter_blocks": [],
        }
    )
    original_document = json.loads(workflow_path.read_text(encoding="utf-8"))
    assert original_document["status"] == "ready"
    assert first_run["source_offset"] == 0
    filter_presets.mark_filter_workflow_query_completed(
        data_root=data_root,
        mode="bond_issuance",
        run_id=first_run["run_id"],
        summary={},
    )
    first = _filter_result(
        source_disclosures=2,
        source_offset=0,
        disclosures=[
            {"acpt_no": "1", "title": "A", "disclosed_at": "2025-01-01"}
        ],
    )
    filter_presets.complete_filter_workflow_payload(
        data_root=data_root,
        mode="bond_issuance",
        run_id=first_run["run_id"],
        result=first,
    )

    completed_before_save = workflow_path.read_text(encoding="utf-8")
    _save_filter_workflow(data_root)
    assert workflow_path.read_text(encoding="utf-8") == completed_before_save

    second_run = filter_presets.begin_filter_workflow_payload(
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "filter_blocks": [],
        }
    )
    assert second_run["source_offset"] == 2
    assert second_run["source_expected_count"] == 2
    assert workflow_path.read_text(encoding="utf-8") == completed_before_save
    filter_presets.mark_filter_workflow_query_completed(
        data_root=data_root,
        mode="bond_issuance",
        run_id=second_run["run_id"],
        summary={},
    )
    second = _filter_result(
        source_disclosures=3,
        source_offset=2,
        disclosures=[
            {"acpt_no": "3", "title": "C", "disclosed_at": "2025-02-01"}
        ],
    )
    completed = filter_presets.complete_filter_workflow_payload(
        data_root=data_root,
        mode="bond_issuance",
        run_id=second_run["run_id"],
        result=second,
    )

    assert completed["result"]["summary"]["source_disclosures"] == 3
    assert completed["result"]["summary"]["inspected_disclosures"] == 3
    assert completed["result"]["integrity"]["search_target_disclosures"] == 3
    assert completed["result"]["integrity"]["search_result_disclosures"] == 2
    assert [row["acpt_no"] for row in completed["result"]["disclosures"]] == [
        "3",
        "1",
    ]


def test_filter_workflow_resumes_interrupted_rows_without_reprocessing(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)
    first_run = filter_presets.begin_filter_workflow_payload(
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "filter_blocks": [],
        }
    )
    partial = _filter_result(
        source_disclosures=4,
        source_offset=0,
        inspected_disclosures=2,
        complete=False,
        disclosures=[
            {"acpt_no": "1", "title": "A", "disclosed_at": "2025-01-01"}
        ],
    )
    interrupted = filter_presets.interrupt_filter_workflow_payload(
        data_root=data_root,
        mode="bond_issuance",
        run_id=first_run["run_id"],
        partial_result=partial,
    )
    assert interrupted is not None
    assert interrupted["status"] == "interrupted"

    resumed_run = filter_presets.begin_filter_workflow_payload(
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "filter_blocks": [],
        }
    )
    assert resumed_run["source_offset"] == 2
    assert resumed_run["source_expected_count"] == 4
    filter_presets.mark_filter_workflow_query_completed(
        data_root=data_root,
        mode="bond_issuance",
        run_id=resumed_run["run_id"],
        summary={},
    )
    remainder = _filter_result(
        source_disclosures=4,
        source_offset=2,
        disclosures=[
            {"acpt_no": "3", "title": "C", "disclosed_at": "2025-01-03"}
        ],
    )
    completed = filter_presets.complete_filter_workflow_payload(
        data_root=data_root,
        mode="bond_issuance",
        run_id=resumed_run["run_id"],
        result=remainder,
    )

    assert completed["status"] == "completed"
    assert completed["result"]["summary"]["inspected_disclosures"] == 4
    assert completed["result"]["integrity"]["search_result_disclosures"] == 2
    assert [row["acpt_no"] for row in completed["result"]["disclosures"]] == [
        "3",
        "1",
    ]


def test_filter_workflow_replaces_saved_result_after_source_count_change(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)
    first_run = filter_presets.begin_filter_workflow_payload(
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "filter_blocks": [],
        }
    )
    filter_presets.mark_filter_workflow_query_completed(
        data_root=data_root,
        mode="bond_issuance",
        run_id=first_run["run_id"],
        summary={},
    )
    filter_presets.complete_filter_workflow_payload(
        data_root=data_root,
        mode="bond_issuance",
        run_id=first_run["run_id"],
        result=_filter_result(
            source_disclosures=2,
            source_offset=0,
            disclosures=[
                {"acpt_no": "1", "title": "old", "disclosed_at": "2025-01-01"}
            ],
        ),
    )

    retry_run = filter_presets.begin_filter_workflow_payload(
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "filter_blocks": [],
        }
    )
    filter_presets.mark_filter_workflow_query_completed(
        data_root=data_root,
        mode="bond_issuance",
        run_id=retry_run["run_id"],
        summary={},
    )
    completed = filter_presets.complete_filter_workflow_payload(
        data_root=data_root,
        mode="bond_issuance",
        run_id=retry_run["run_id"],
        result=_filter_result(
            source_disclosures=3,
            source_offset=0,
            disclosures=[
                {"acpt_no": "2", "title": "new", "disclosed_at": "2025-01-02"}
            ],
        ),
    )

    assert completed["result"]["summary"]["source_disclosures"] == 3
    assert [row["acpt_no"] for row in completed["result"]["disclosures"]] == ["2"]


def test_interrupted_filter_retry_drops_saved_result_after_source_count_change(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)
    first_run = filter_presets.begin_filter_workflow_payload(
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "filter_blocks": [],
        }
    )
    filter_presets.mark_filter_workflow_query_completed(
        data_root=data_root,
        mode="bond_issuance",
        run_id=first_run["run_id"],
        summary={},
    )
    filter_presets.complete_filter_workflow_payload(
        data_root=data_root,
        mode="bond_issuance",
        run_id=first_run["run_id"],
        result=_filter_result(
            source_disclosures=2,
            source_offset=0,
            disclosures=[
                {"acpt_no": "1", "title": "old", "disclosed_at": "2025-01-01"}
            ],
        ),
    )

    retry_run = filter_presets.begin_filter_workflow_payload(
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "filter_blocks": [],
        }
    )
    interrupted = filter_presets.interrupt_filter_workflow_payload(
        data_root=data_root,
        mode="bond_issuance",
        run_id=retry_run["run_id"],
        partial_result=_filter_result(
            source_disclosures=3,
            source_offset=0,
            inspected_disclosures=1,
            complete=False,
            disclosures=[
                {"acpt_no": "2", "title": "new", "disclosed_at": "2025-01-02"}
            ],
        ),
    )

    assert interrupted is not None
    document = json.loads(
        (data_root / "03-filter" / "bond_issuance" / "filter.json").read_text()
    )
    assert "result_file" not in document
    assert document["pending_file"] == "filter.pending.json"
    pending = json.loads(
        (data_root / "03-filter" / "bond_issuance" / document["pending_file"]).read_text()
    )
    assert pending["result"]["summary"]["source_offset"] == 0
    assert [
        row["acpt_no"] for row in pending["result"]["disclosures"]
    ] == ["2"]


def test_filter_workflow_preserves_canonical_when_cancelled_before_first_row(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)
    workflow_path = data_root / "03-filter" / "bond_issuance" / "filter.json"
    original = workflow_path.read_text(encoding="utf-8")
    run = filter_presets.begin_filter_workflow_payload(
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "filter_blocks": [],
        }
    )
    partial = _filter_result(
        source_disclosures=4,
        source_offset=0,
        inspected_disclosures=0,
        complete=False,
        disclosures=[],
    )

    interrupted = filter_presets.interrupt_filter_workflow_payload(
        data_root=data_root,
        mode="bond_issuance",
        run_id=run["run_id"],
        partial_result=partial,
    )

    assert interrupted is None
    assert workflow_path.read_text(encoding="utf-8") == original
    assert list(workflow_path.parent.glob(".filter-run-*.json")) == []


def test_filter_workflow_count_validation_rejects_fractional_numbers() -> None:
    with pytest.raises(ValueError, match="must be an integer"):
        filter_presets._required_count(1.5, "count")


def test_filter_workflow_accepts_text_acpt_no() -> None:
    result = _filter_result(
        source_disclosures=1,
        source_offset=0,
        disclosures=[{"acpt_no": "20250101A00001"}],
    )

    validated = filter_presets._validate_filter_result(
        result,
        condition_blocks=[],
        require_complete=True,
    )

    assert validated["disclosures"][0]["acpt_no"] == "20250101A00001"


def test_filter_workflow_rejects_missing_acpt_no() -> None:
    result = _filter_result(
        source_disclosures=1,
        source_offset=0,
        disclosures=[{"acpt_no": ""}],
    )

    with pytest.raises(ValueError, match=r"disclosures\[0\]\.acpt_no is required"):
        filter_presets._validate_filter_result(
            result,
            condition_blocks=[],
            require_complete=True,
        )


@pytest.mark.parametrize(
    ("complete_value", "passed_value"),
    [
        (None, False),
        ("false", False),
        (False, None),
        (False, "false"),
        (True, False),
    ],
)
def test_filter_workflow_rejects_invalid_interrupted_integrity_flags(
    complete_value: object,
    passed_value: object,
) -> None:
    partial = _filter_result(
        source_disclosures=1,
        source_offset=0,
        inspected_disclosures=0,
        complete=False,
        disclosures=[],
    )
    partial["integrity"]["complete"] = complete_value
    partial["integrity"]["passed"] = passed_value

    with pytest.raises(ValueError, match="integrity flags must be false"):
        filter_presets._validate_filter_result(
            partial,
            condition_blocks=[],
            require_complete=False,
        )


def test_filter_disclosures_records_query_failure_in_workflow(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)

    def fail_filter(*_args, **_kwargs):
        raise ValueError("query failed")

    monkeypatch.setattr(web_app, "filter_disclosures_payload", fail_filter)

    response = TestClient(app).post(
        "/api/disclosures/filter",
        json={
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "filter_blocks": [],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "query failed"
    workflow = json.loads(
        (data_root / "03-filter" / "bond_issuance" / "filter.json").read_text(encoding="utf-8")
    )
    assert workflow["status"] == "failed"
    assert workflow["steps"]["database_query"]["status"] == "failed"
    assert workflow["steps"]["database_query"]["error"] == "query failed"
    assert workflow["steps"]["record"] == {"status": "pending"}


def test_filter_disclosures_requires_saved_workflow_conditions(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)

    response = TestClient(app).post(
        "/api/disclosures/filter",
        json={
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "filter_blocks": [{"field": "title", "operator": "contains", "value": "사채"}],
        },
    )

    assert response.status_code == 400
    assert "Save the filter conditions" in response.json()["detail"]
    workflow = json.loads(
        (data_root / "03-filter" / "bond_issuance" / "filter.json").read_text(encoding="utf-8")
    )
    assert workflow["status"] == "ready"


def test_filter_disclosures_requires_mode_folder(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        web_app,
        "filter_disclosures_payload",
        lambda *_args, **_kwargs: {
            "format": "kind_disclosure_filter_v1",
            "disclosures": [],
        },
    )

    response = TestClient(app).post(
        "/api/disclosures/filter",
        json={"external_html_transfer_path": str(tmp_path / "filtered")},
    )

    assert response.status_code == 400
    assert "mode" in response.json()["detail"]


def test_filter_disclosures_rejects_json_output_path_before_filtering(
    tmp_path: Path, monkeypatch
) -> None:
    called = False

    def fake_filter(*_args, **_kwargs):
        nonlocal called
        called = True
        return {"format": "kind_disclosure_filter_v1", "disclosures": []}

    monkeypatch.setattr(web_app, "filter_disclosures_payload", fake_filter)

    response = TestClient(app).post(
        "/api/disclosures/filter",
        json={
            "mode": "bond_issuance",
            "external_html_transfer_path": str(tmp_path / "filtered.json"),
        },
    )

    assert response.status_code == 400
    assert "directory" in response.json()["detail"]
    assert called is False


def test_disclosure_filter_workflows_ignore_obsolete_filter_result_json(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    source_path = data_root / "03-filter" / "bond_issuance_custom_filter.json"
    source_path.parent.mkdir(parents=True)
    filter_blocks = [
        {
            "connector": "",
            "open_count": 0,
            "not": False,
            "ignore_spaces": True,
            "clean_search": True,
            "field": "title",
            "operator": "contains",
            "value": "전환사채",
            "close_count": 0,
        }
    ]
    source_path.write_text(
        json.dumps(
            {
                "format": "kind_disclosure_filter_v1",
                "filters": {"filter_blocks": filter_blocks},
                "disclosures": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post("/api/disclosures/filter/presets", json={
        "data_root": str(data_root),
        "action": "list",
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "finiq_disclosure_filter_workflow_directory"
    assert payload["path"] == str(source_path.parent.resolve())
    assert payload["presets"] == []


def test_disclosure_filter_inspection_rejects_wrong_format_in_mode_folder(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    workflow_path = data_root / "03-filter" / "bond_issuance" / "filter.json"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(json.dumps({"format": "wrong"}), encoding="utf-8")
    client = TestClient(app)

    listed = client.post(
        "/api/disclosures/filter/presets",
        json={"data_root": str(data_root), "action": "list"},
    )
    inspected = client.post(
        "/api/disclosures/filter/presets",
        json={"data_root": str(data_root), "action": "inspect"},
    )

    assert listed.status_code == 200
    assert listed.json()["presets"] == []
    assert inspected.status_code == 400
    assert str(workflow_path) in inspected.json()["detail"]


def test_disclosure_filter_workflows_read_format_after_one_mib(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)
    workflow_path = data_root / "03-filter" / "bond_issuance" / "filter.json"
    document = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow_path.write_text(
        json.dumps({"padding": "x" * (1024 * 1024 + 1), **document}),
        encoding="utf-8",
    )

    payload = filter_presets.manage_filter_presets_payload(
        {"data_root": str(data_root), "action": "list"}
    )

    assert [preset["mode"] for preset in payload["presets"]] == ["bond_issuance"]


def test_disclosure_filter_is_saved_inside_its_mode_folder(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    preset = {
        "mode": "bond_issuance",
        "condition_blocks": [
            {"field": "title", "operator": "contains", "value": "전환사채"}
        ],
    }

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/filter/presets",
        json={"data_root": str(data_root), "action": "save", "preset": preset},
    )

    assert response.status_code == 200
    filter_path = data_root / "03-filter" / "bond_issuance" / "filter.json"
    assert response.json()["path"] == str((data_root / "03-filter").resolve())
    saved = response.json()["presets"][0]
    assert saved["name"] == preset["mode"]
    assert saved["mode"] == preset["mode"]
    assert saved["condition_blocks"] == preset["condition_blocks"]
    assert saved["status"] == "ready"
    document = json.loads(filter_path.read_text(encoding="utf-8"))
    assert document["format"] == "finiq_disclosure_filter_workflow"
    assert document["mode"] == "bond_issuance"
    assert document["status"] == "ready"
    assert document["steps"]["condition_input"]["status"] == "completed"
    assert document["steps"]["condition_input"]["filter_blocks"] == preset["condition_blocks"]
    assert document["steps"]["database_query"] == {"status": "pending"}
    assert document["steps"]["record"] == {"status": "pending"}


def test_completed_filter_result_is_split_from_workflow_metadata(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)
    disclosures = [{"acpt_no": "20260101000001", "title": "A"}]

    _complete_filter_workflow(
        data_root,
        mode="bond_issuance",
        disclosures=disclosures,
    )

    workflow_path = data_root / "03-filter" / "bond_issuance" / "filter.json"
    document = json.loads(workflow_path.read_text(encoding="utf-8"))
    assert "result" not in document
    assert document["result_file"] == "filtered.json"
    assert document["result_summary"]["returned_disclosures"] == 1
    result_path = workflow_path.with_name(document["result_file"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["disclosures"] == disclosures
    assert document["result_fingerprint"] == filter_presets._canonical_result_sha256(
        result
    )


def test_filter_list_does_not_read_split_result_sidecar(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)
    _complete_filter_workflow(
        data_root,
        mode="bond_issuance",
        disclosures=[{"acpt_no": "20260101000001", "title": "A"}],
    )
    original_read = filter_presets._read_json_object

    def reject_result_read(path: Path) -> dict[str, object]:
        if path.name == "filtered.json":
            raise AssertionError("list must not read result sidecars")
        return original_read(path)

    monkeypatch.setattr(filter_presets, "_read_json_object", reject_result_read)

    listed = filter_presets.manage_filter_presets_payload(
        {"data_root": str(data_root), "action": "list"}
    )

    assert listed["presets"][0]["result_summary"]["returned_disclosures"] == 1


def test_legacy_embedded_filter_result_migrates_to_split_storage(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)
    disclosures = [{"acpt_no": "20260101000001", "title": "A"}]
    _complete_filter_workflow(
        data_root,
        mode="bond_issuance",
        disclosures=disclosures,
    )
    workflow_path = data_root / "03-filter" / "bond_issuance" / "filter.json"
    document = json.loads(workflow_path.read_text(encoding="utf-8"))
    result_path = workflow_path.with_name(document["result_file"])
    legacy_result = json.loads(result_path.read_text(encoding="utf-8"))
    legacy_document = {
        key: value
        for key, value in document.items()
        if key not in {"result_file", "result_fingerprint", "result_summary"}
    }
    legacy_document["result"] = legacy_result
    legacy_document["pending"] = None
    workflow_path.write_text(json.dumps(legacy_document), encoding="utf-8")
    result_path.unlink()

    migrated = filter_presets.migrate_filter_workflow_storage(str(data_root))

    assert migrated["migrated"] == [str(workflow_path)]
    split_document = json.loads(workflow_path.read_text(encoding="utf-8"))
    assert "result" not in split_document
    loaded = filter_presets.load_filter_workflow_result_payload(
        data_root=str(data_root),
        mode="bond_issuance",
        condition_blocks=[],
    )
    assert loaded["disclosures"] == disclosures


def test_hashed_filter_result_migrates_to_canonical_filename(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)
    disclosures = [{"acpt_no": "20260101000001", "title": "A"}]
    _complete_filter_workflow(
        data_root,
        mode="bond_issuance",
        disclosures=disclosures,
    )
    workflow_path = data_root / "03-filter" / "bond_issuance" / "filter.json"
    document = json.loads(workflow_path.read_text(encoding="utf-8"))
    canonical_result_path = workflow_path.with_name("filtered.json")
    hashed_result_path = workflow_path.with_name(
        f"filter.result-{document['result_fingerprint']}.json"
    )
    canonical_result_path.rename(hashed_result_path)
    document["result_file"] = hashed_result_path.name
    workflow_path.write_text(json.dumps(document), encoding="utf-8")

    migrated = filter_presets.migrate_filter_workflow_storage(str(data_root))

    assert migrated["migrated"] == [str(workflow_path)]
    migrated_document = json.loads(workflow_path.read_text(encoding="utf-8"))
    assert migrated_document["result_file"] == "filtered.json"
    assert canonical_result_path.is_file()
    assert not hashed_result_path.exists()


def test_migration_removes_orphaned_result_from_ready_workflow(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root)
    workflow_path = data_root / "03-filter" / "bond_issuance" / "filter.json"
    orphaned_result_path = workflow_path.with_name("filtered.json")
    orphaned_result_path.write_text("{}", encoding="utf-8")

    migrated = filter_presets.migrate_filter_workflow_storage(str(data_root))

    assert migrated["migrated"] == [str(workflow_path)]
    assert not orphaned_result_path.exists()


def test_disclosure_filter_presets_serialize_concurrent_saves(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_root = tmp_path / "workspace"
    original_read = filter_presets._read_workflows
    active_reads = 0
    maximum_active_reads = 0
    counter_lock = threading.Lock()
    start = threading.Barrier(2)

    def slow_read(path: Path, **kwargs: object) -> list[dict[str, object]]:
        nonlocal active_reads, maximum_active_reads
        with counter_lock:
            active_reads += 1
            maximum_active_reads = max(maximum_active_reads, active_reads)
        try:
            time.sleep(0.05)
            return original_read(path, **kwargs)
        finally:
            with counter_lock:
                active_reads -= 1

    monkeypatch.setattr(filter_presets, "_read_workflows", slow_read)

    def save(mode: str) -> None:
        start.wait()
        filter_presets.manage_filter_presets_payload(
            {
                "data_root": str(data_root),
                "action": "save",
                "preset": {
                    "mode": mode,
                    "condition_blocks": [],
                },
            }
        )

    threads = [
        threading.Thread(target=save, args=(mode,))
        for mode in ("bond_issuance", "rights_issuance")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    saved = filter_presets.manage_filter_presets_payload(
        {"data_root": str(data_root), "action": "list"}
    )
    assert maximum_active_reads == 1
    assert [preset["mode"] for preset in saved["presets"]] == [
        "bond_issuance",
        "rights_issuance",
    ]


def test_disclosure_filter_presets_list_missing_workspace_directory_as_empty(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"

    response = TestClient(app).post(
        "/api/disclosures/filter/presets",
        json={"data_root": str(data_root), "action": "list"},
    )

    assert response.status_code == 200
    assert response.json()["presets"] == []
    assert not (data_root / "03-filter").exists()


def test_disclosure_filter_delete_removes_mode_filter_only(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    client = TestClient(app)
    save_response = client.post(
        "/api/disclosures/filter/presets",
        json={
            "data_root": str(data_root),
            "action": "save",
            "preset": {
                "mode": "rights_issuance",
                "condition_blocks": [],
            },
        },
    )
    assert save_response.status_code == 200

    delete_response = client.post(
        "/api/disclosures/filter/presets",
        json={"data_root": str(data_root), "action": "delete", "mode": "rights_issuance"},
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["presets"] == []
    assert not (data_root / "03-filter" / "rights_issuance" / "filter.json").exists()


def test_derived_filter_uses_completed_parent_and_nested_storage(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    parent_disclosures = [
        {"acpt_no": "20260101000001", "title": "A"},
        {"acpt_no": "20260101000002", "title": "B"},
    ]
    _save_filter_workflow(data_root, mode="parent")
    _complete_filter_workflow(
        data_root, mode="parent", disclosures=parent_disclosures
    )

    saved = filter_presets.manage_filter_presets_payload(
        {
            "data_root": str(data_root),
            "action": "save",
            "preset": {
                "mode": "child",
                "parent_mode": "parent",
                "condition_blocks": [],
            },
        }
    )

    child_path = (
        data_root
        / "03-filter"
        / "parent"
        / "subfilters"
        / "child"
        / "filter.json"
    )
    child = next(item for item in saved["presets"] if item["id"] == "parent/child")
    assert child["mode"] == "child"
    assert child["parent_mode"] == "parent"
    assert len(child["parent_result_fingerprint"]) == 64
    assert child_path.is_file()
    assert not (data_root / "03-filter" / "child").exists()

    run = filter_presets.begin_filter_workflow_payload(
        {
            "data_root": str(data_root),
            "mode": "child",
            "parent_mode": "parent",
            "filter_blocks": [],
        }
    )
    assert run["parent_acpt_numbers"] == [
        "20260101000002",
        "20260101000001",
    ]
    child_result = _filter_result(
        source_disclosures=1,
        source_offset=0,
        disclosures=[parent_disclosures[0]],
    )
    filter_presets.mark_filter_workflow_query_completed(
        data_root=str(data_root),
        mode="child",
        parent_mode="parent",
        run_id=run["run_id"],
        summary=child_result["summary"],
    )
    completed = filter_presets.complete_filter_workflow_payload(
        data_root=str(data_root),
        mode="child",
        parent_mode="parent",
        run_id=run["run_id"],
        result=child_result,
    )
    assert completed["result"]["parent_mode"] == "parent"
    assert (
        completed["result"]["parent_result_fingerprint"]
        == child["parent_result_fingerprint"]
    )

    deleted = filter_presets.manage_filter_presets_payload(
        {
            "data_root": str(data_root),
            "action": "delete",
            "mode": "child",
            "parent_mode": "parent",
        }
    )
    assert [item["id"] for item in deleted["presets"]] == ["parent"]
    assert not child_path.exists()
    assert (data_root / "03-filter" / "parent" / "filter.json").is_file()


def test_derived_filter_rejects_missing_incomplete_and_stale_parent(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    child_preset = {
        "mode": "child",
        "parent_mode": "parent",
        "condition_blocks": [],
    }
    with pytest.raises(ValueError, match="Parent filter workflow not found"):
        filter_presets.manage_filter_presets_payload(
            {
                "data_root": str(data_root),
                "action": "save",
                "preset": child_preset,
            }
        )

    _save_filter_workflow(data_root, mode="parent")
    with pytest.raises(ValueError, match="Parent filter workflow is not completed"):
        filter_presets.manage_filter_presets_payload(
            {
                "data_root": str(data_root),
                "action": "save",
                "preset": child_preset,
            }
        )

    _complete_filter_workflow(
        data_root,
        mode="parent",
        disclosures=[{"acpt_no": "20260101000001", "title": "A"}],
    )
    filter_presets.manage_filter_presets_payload(
        {"data_root": str(data_root), "action": "save", "preset": child_preset}
    )
    changed_conditions = [
        {"field": "title", "operator": "contains", "value": "changed"}
    ]
    filter_presets.manage_filter_presets_payload(
        {
            "data_root": str(data_root),
            "action": "save",
            "preset": {
                "mode": "parent",
                "condition_blocks": changed_conditions,
            },
        }
    )
    _complete_filter_workflow(
        data_root,
        mode="parent",
        disclosures=[{"acpt_no": "20260101000001", "title": "changed"}],
        condition_blocks=changed_conditions,
    )

    with pytest.raises(ValueError, match="stale because parent result changed"):
        filter_presets.begin_filter_workflow_payload(
            {
                "data_root": str(data_root),
                "mode": "child",
                "parent_mode": "parent",
                "filter_blocks": [],
            }
        )
    listed = filter_presets.manage_filter_presets_payload(
        {"data_root": str(data_root), "action": "list"}
    )
    stale_child = next(
        item for item in listed["presets"] if item["id"] == "parent/child"
    )
    assert stale_child["status"] == "failed"
    assert "stale because parent result changed" in stale_child["parent_error"]
    with pytest.raises(ValueError, match="stale because parent result changed"):
        filter_presets.manage_filter_presets_payload(
            {"data_root": str(data_root), "action": "inspect"}
        )


def test_parent_filter_delete_is_blocked_while_derived_filter_exists(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root, mode="parent")
    _complete_filter_workflow(
        data_root,
        mode="parent",
        disclosures=[{"acpt_no": "20260101000001", "title": "A"}],
    )
    filter_presets.manage_filter_presets_payload(
        {
            "data_root": str(data_root),
            "action": "save",
            "preset": {
                "mode": "child",
                "parent_mode": "parent",
                "condition_blocks": [],
            },
        }
    )
    parent_path = data_root / "03-filter" / "parent" / "filter.json"
    child_path = (
        data_root
        / "03-filter"
        / "parent"
        / "subfilters"
        / "child"
        / "filter.json"
    )

    with pytest.raises(ValueError, match="derived filters exist: parent"):
        filter_presets.manage_filter_presets_payload(
            {
                "data_root": str(data_root),
                "action": "delete",
                "mode": "parent",
            }
        )

    assert parent_path.is_file()
    assert child_path.is_file()


def test_filter_list_marks_orphaned_derived_filter_failed(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    _save_filter_workflow(data_root, mode="parent")
    _complete_filter_workflow(
        data_root,
        mode="parent",
        disclosures=[{"acpt_no": "20260101000001", "title": "A"}],
    )
    filter_presets.manage_filter_presets_payload(
        {
            "data_root": str(data_root),
            "action": "save",
            "preset": {
                "mode": "child",
                "parent_mode": "parent",
                "condition_blocks": [],
            },
        }
    )
    (data_root / "03-filter" / "parent" / "filter.json").unlink()

    listed = filter_presets.manage_filter_presets_payload(
        {"data_root": str(data_root), "action": "list"}
    )
    orphan = next(
        item for item in listed["presets"] if item["id"] == "parent/child"
    )
    assert orphan["status"] == "failed"
    assert orphan["parent_error"] == "Parent filter workflow not found: parent"
    with pytest.raises(ValueError, match="Parent filter workflow not found: parent"):
        filter_presets.manage_filter_presets_payload(
            {"data_root": str(data_root), "action": "inspect"}
        )


def test_disclosure_filter_presets_reject_invalid_workspace_json(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    presets_path = data_root / "03-filter" / "bond_issuance" / "filter.json"
    presets_path.parent.mkdir(parents=True)
    presets_path.write_text("[]", encoding="utf-8")

    response = TestClient(app).post(
        "/api/disclosures/filter/presets",
        json={"data_root": str(data_root), "action": "list"},
    )

    assert response.status_code == 400
    assert "filter.json" in response.json()["detail"]


def test_html_download_inspect_folder_route_deletes_unexpected_file(tmp_path: Path) -> None:
    output_directory = tmp_path / "viewer_html"
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "2024").mkdir()
    expected = output_directory / "2025" / "20250101000001.html"
    unexpected = output_directory / "2024" / "20240101000001.html"
    expected.write_text("<html></html>", encoding="utf-8")
    unexpected.write_text("<html></html>", encoding="utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/external-html-download/inspect-folder",
        json=_external_workspace_body(
            tmp_path,
            {"disclosures": [{"acpt_no": "20250101000001"}]},
            output_directory=str(output_directory),
            delete_confirmed=True,
            delete_confirmation_text="확인했습니다.",
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_count"] == 1
    assert payload["deleted_files"][0]["name"] == "2024/20240101000001.html"
    assert expected.exists()
    assert not unexpected.exists()


def test_html_download_inspect_folder_route_dry_run_reports_unexpected_file(tmp_path: Path) -> None:
    output_directory = tmp_path / "viewer_html"
    (output_directory / "2024").mkdir(parents=True)
    unexpected = output_directory / "2024" / "20240101000001.html"
    unexpected.write_text("<html></html>", encoding="utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/external-html-download/inspect-folder",
        json=_external_workspace_body(
            tmp_path,
            {"disclosures": [{"acpt_no": "20250101000001"}]},
            output_directory=str(output_directory),
            dry_run=True,
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted_count"] == 0
    assert payload["deletion_candidate_count"] == 1
    assert payload["deletion_candidates"][0]["name"] == "2024/20240101000001.html"
    assert unexpected.exists()


def test_html_download_check_existing_route_reports_existing_html(tmp_path: Path) -> None:
    output_directory = tmp_path / "viewer_html"
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "2025" / "20250101000001.html").write_text(
        "<html><body>" + ("valid " * 30) + "</body></html>", encoding="utf-8"
    )

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/external-html-download/check-existing",
        json=_external_workspace_body(
            tmp_path,
            {
                "disclosures": [
                    {"acpt_no": "20250101000001"},
                    {"acpt_no": "20250101000002"},
                ]
            },
            output_directory=str(output_directory),
        ),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "kind_disclosure_html_existing_check_v1"
    assert payload["has_existing"] is True
    assert payload["existing_target_html_count"] == 1
    assert payload["missing_target_html_count"] == 1
    assert payload["hash_verified_target_html_count"] == 0
    assert payload["hash_unverified_target_html_count"] == 1
    assert payload["hash_mismatch_target_html_count"] == 0


def test_external_html_check_existing_route_uses_workspace_default_output(
    tmp_path: Path,
) -> None:
    body = _external_workspace_body(
        tmp_path,
        {"disclosures": [{"acpt_no": "20250101000001"}]},
        output_directory="",
    )
    output_directory = (
        tmp_path
        / "workspace"
        / "04-external-html-download"
        / "bond_issuance"
        / "2025"
    )
    output_directory.mkdir(parents=True)
    (output_directory / "20250101000001.html").write_text(
        "<html><body>" + ("valid " * 30) + "</body></html>",
        encoding="utf-8",
    )

    response = TestClient(app).post(
        "/api/disclosures/external-html-download/check-existing",
        json=body,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["existing_target_html_count"] == 1
    assert payload["output_directory"] == str(output_directory.parent.resolve())


def test_external_html_trust_existing_route_creates_hash_baseline(
    tmp_path: Path,
) -> None:
    body = _external_workspace_body(
        tmp_path,
        {
            "disclosures": [
                {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"}
            ]
        },
        output_directory="",
        trust_existing_files=True,
    )
    output_directory = (
        tmp_path
        / "workspace"
        / "04-external-html-download"
        / "bond_issuance"
    )
    target = output_directory / "2025" / "20250101000001.html"
    target.parent.mkdir(parents=True)
    target.write_text("<html><body>trusted</body></html>", encoding="utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/external-html-download/trust-existing/start",
        json=body,
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    snapshot = None
    for _ in range(20):
        snapshot = client.get(f"/api/disclosures/html/jobs/{job_id}").json()
        if snapshot["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert snapshot is not None
    assert snapshot["status"] == "completed"
    assert snapshot["result"]["hashed_count"] == 1
    manifest = json.loads(
        (output_directory / "kind_disclosure_html_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(manifest["disclosures"][0]["source_sha256"]) == 64
    assert manifest["disclosures"][0]["source_size_bytes"] == target.stat().st_size


def test_internal_html_download_inspect_folder_route_uses_yearly_layout(tmp_path: Path) -> None:
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps({
            "format": "finiq_disclosure_external_html_docs_v1",
            "records": [{
                "acpt_no": "20250101000001",
                "selected_main_doc_no": "20250101000099",
                "metadata": {"disclosed_at": "2025-01-01"},
            }],
        }),
        encoding="utf-8",
    )
    output_directory = tmp_path / "content_html"
    (output_directory / "2024").mkdir(parents=True)
    (output_directory / "2024" / "20240101000001.html").write_text(
        "<html></html>", encoding="utf-8"
    )

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/internal-html-download/inspect-folder",
        json={
            "source_compressed_json_path": str(compressed_path),
            "output_directory": str(output_directory),
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "content"
    assert payload["requested_count"] == 1
    assert payload["deletion_candidate_count"] == 1
    assert payload["deletion_candidates"][0]["name"] == "2024/20240101000001.html"


def test_internal_html_download_inspect_folder_rejects_source_directory(tmp_path: Path) -> None:
    source_directory = tmp_path / "viewer_html"
    output_directory = tmp_path / "content_html"
    output_directory.mkdir()

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/internal-html-download/inspect-folder",
        json={
            "source_directory": str(source_directory),
            "output_directory": str(output_directory),
            "dry_run": True,
        },
    )

    assert response.status_code == 400
    assert "source_directory is not supported" in response.json()["detail"]


def test_internal_html_download_check_existing_route_uses_yearly_layout(tmp_path: Path) -> None:
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps({
            "format": "finiq_disclosure_external_html_docs_v1",
            "records": [{
                "acpt_no": "20250101000001",
                "selected_main_doc_no": "20250101000099",
                "metadata": {"disclosed_at": "2025-01-01"},
            }],
        }),
        encoding="utf-8",
    )
    output_directory = tmp_path / "content_html"
    output_year_directory = output_directory / "2025"
    output_year_directory.mkdir(parents=True)
    (output_year_directory / "20250101000001.html").write_text(
        "<html><body>" + ("valid " * 30) + "</body></html>", encoding="utf-8"
    )

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/internal-html-download/check-existing",
        json={
            "source_compressed_json_path": str(compressed_path),
            "output_directory": str(output_directory),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "kind_disclosure_html_existing_check_v1"
    assert payload["source_type"] == "content"
    assert payload["has_existing"] is True
    assert payload["existing_target_html_count"] == 1
    assert payload["missing_target_html_count"] == 0


def test_internal_html_download_check_existing_route_uses_compressed_json_year(
    tmp_path: Path,
) -> None:
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                        {
                            "acpt_no": "20250101000001",
                            "selected_main_doc_no": "20250101000999",
                            "metadata": {"disclosed_at": "2025-01-01"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_directory = tmp_path / "content_html"
    output_directory.mkdir()

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/internal-html-download/check-existing",
        json={
            "source_compressed_json_path": str(compressed_path),
            "output_directory": str(output_directory),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "content"
    assert payload["requested_count"] == 1


def test_internal_html_check_existing_route_uses_workspace_defaults(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    compressed_path = (
        data_root
        / "04-external-html-download"
        / "bond_issuance"
        / "compressed-external-html.json"
    )
    compressed_path.parent.mkdir(parents=True)
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                        {
                            "acpt_no": "20250101000001",
                            "selected_main_doc_no": "20250101000999",
                            "metadata": {"disclosed_at": "2025-01-01"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_directory = (
        data_root / "05-internal-html-download" / "bond_issuance" / "2025"
    )
    output_directory.mkdir(parents=True)
    (output_directory / "20250101000001.html").write_text(
        "<html><body>" + ("valid " * 30) + "</body></html>",
        encoding="utf-8",
    )

    response = TestClient(app).post(
        "/api/disclosures/internal-html-download/check-existing",
        json={
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "output_directory": "",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["existing_target_html_count"] == 1
    assert payload["output_directory"] == str(output_directory.parent.resolve())


def test_internal_html_download_check_existing_route_finds_yearly_output(
    tmp_path: Path,
) -> None:
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                        {
                            "acpt_no": "20250101000001",
                            "selected_main_doc_no": "20250101000999",
                            "metadata": {"disclosed_at": "2025-01-01"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_directory = tmp_path / "content_html"
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "2025" / "20250101000001.html").write_text(
        "<html><body>" + ("valid " * 30) + "</body></html>", encoding="utf-8"
    )

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/internal-html-download/check-existing",
        json={
            "source_compressed_json_path": str(compressed_path),
            "output_directory": str(output_directory),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["existing_target_html_count"] == 1
    assert payload["hash_verified_target_html_count"] == 0
    assert payload["hash_unverified_target_html_count"] == 1
    assert payload["hash_mismatch_target_html_count"] == 0


def test_internal_html_trust_existing_route_creates_hash_baseline(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    compressed_path = (
        data_root
        / "04-external-html-download"
        / "bond_issuance"
        / "compressed-external-html.json"
    )
    compressed_path.parent.mkdir(parents=True)
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                    {
                        "acpt_no": "20250101000001",
                        "selected_main_doc_no": "20250101000999",
                        "metadata": {"disclosed_at": "2025-01-01"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output_directory = data_root / "05-internal-html-download" / "bond_issuance"
    target = output_directory / "2025" / "20250101000001.html"
    target.parent.mkdir(parents=True)
    target.write_text("<html><body>trusted</body></html>", encoding="utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/internal-html-download/trust-existing/start",
        json={
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "output_directory": "",
            "trust_existing_files": True,
        },
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    snapshot = None
    for _ in range(20):
        snapshot = client.get(f"/api/disclosures/html/jobs/{job_id}").json()
        if snapshot["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert snapshot is not None
    assert snapshot["status"] == "completed"
    assert snapshot["result"]["hashed_count"] == 1
    manifest = json.loads(
        (output_directory / "kind_disclosure_html_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(manifest["disclosures"][0]["source_sha256"]) == 64
    assert manifest["disclosures"][0]["source_size_bytes"] == target.stat().st_size


def test_html_download_inspect_folder_route_rejects_high_risk_directory(
    tmp_path: Path,
) -> None:
    client = TestClient(app)
    response = client.post(
        "/api/disclosures/external-html-download/inspect-folder",
        json=_external_workspace_body(
            tmp_path,
            {"disclosures": [{"acpt_no": "20250101000001"}]},
            output_directory=str(Path(Path.cwd().anchor).resolve()),
            dry_run=True,
        ),
    )

    assert response.status_code == 400
    assert "high-risk output_directory" in response.json()["detail"]


def test_download_inspect_folder_start_route(tmp_path: Path, monkeypatch) -> None:
    def fake_inspect(payload, progress_callback=None, cancel_check=None):
        return {"format": "kind_download_folder_cleanup_v1", "dry_run": True, "deletion_candidates": []}

    monkeypatch.setattr(
        "finiq.market_desk.web.features.downloads.kind_jobs.inspect_download_output_directory_payload",
        fake_inspect,
    )

    client = TestClient(app)
    response = client.post(
        "/api/download/inspect-folder/start",
        json={
            "mode": "single",
            "output_directory": str(tmp_path),
            "start_date": "2026-01-01",
            "end_date": "2026-01-10",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] in {"queued", "running", "completed"}

    # Poll status
    job_id = data["job_id"]
    response = client.get(f"/api/download/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id


def test_html_section_inspect_route_rejects_file_without_canonical_toc(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    input_directory.mkdir()
    (input_directory / "20260421000111.html").write_text(
        "<html><head></head><body><p>목차 없는 문서</p></body></html>",
        encoding="utf-8",
    )
    (input_directory / "20260422000832.html").write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p>주요사항보고서</p></h2>
          <p>표지 내용</p>
          <h2 class="SECTION-2" id="toc_2"><p>전환사채권 발행결정</p></h2>
          <p>발행금액 250,000,000</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/html/sections/inspect",
        json={"input_directory": str(input_directory)},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "canonical SECTION heading is required"


def test_html_section_source_list_route_returns_one_page_with_toc_counts(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    input_directory.mkdir()
    for index in range(21):
        section_markup = "<h2 class='SECTION-1' id='toc_1'><p>목차</p></h2>"
        if index == 0:
            section_markup += "<h2 class='SECTION-2' id='toc_2'><p>본문</p></h2>"
        (input_directory / f"202604{index + 1:02d}000001.html").write_text(
            f"<html><head></head><body>{section_markup}</body></html>",
            encoding="utf-8",
        )

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/html/sections/list",
        json={"input_directory": str(input_directory), "page_size": 20},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == {
        "page": 1,
        "page_size": 20,
        "returned_files": 20,
        "has_next_page": True,
    }
    assert len(data["documents"]) == 20
    assert data["documents"][0]["section_count"] == 2
    assert data["documents"][1]["section_count"] == 1
    assert "sections" not in data["documents"][0]


def test_html_section_kinds_route_returns_unique_toc_sequence_counts(tmp_path: Path) -> None:
    input_directory = tmp_path / "kind_html_contents"
    input_directory.mkdir()
    for source_name in ["20260401000001.html", "20260402000001.html"]:
        (input_directory / source_name).write_text(
            """
            <html><head></head><body>
              <h2 class="SECTION-1" id="toc_1"><p>1</p></h2>
              <h2 class="SECTION-2" id="toc_2"><p>2</p></h2>
            </body></html>
            """,
            encoding="utf-8",
        )
    (input_directory / "20260403000001.html").write_text(
        "<html><head></head><body><h2 class='SECTION-1' id='toc_1'><p>1</p></h2></body></html>",
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/html/sections/kinds",
        json={"input_directory": str(input_directory)},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["format"] == "finiq_disclosure_html_section_kind_summary_v1"
    assert data["items"] == [
        {
            "signature": "toc_1 1 toc_2 2",
            "count": 2,
            "section_count": 2,
            "sections": [
                {"toc_id": "toc_1", "index": 1, "title": "1"},
                {"toc_id": "toc_2", "index": 2, "title": "2"},
            ],
            "sample_documents": [
                {
                    "source_file": str(input_directory / "20260401000001.html"),
                    "source_name": "20260401000001.html",
                    "source_relative_path": "20260401000001.html",
                },
                {
                    "source_file": str(input_directory / "20260402000001.html"),
                    "source_name": "20260402000001.html",
                    "source_relative_path": "20260402000001.html",
                },
            ],
        },
        {
            "signature": "toc_1 1",
            "count": 1,
            "section_count": 1,
            "sections": [{"toc_id": "toc_1", "index": 1, "title": "1"}],
            "sample_documents": [
                {
                    "source_file": str(input_directory / "20260403000001.html"),
                    "source_name": "20260403000001.html",
                    "source_relative_path": "20260403000001.html",
                }
            ],
        },
    ]


def test_html_section_source_route_opens_individual_disclosure() -> None:
    source_file = Path(__file__).parent / "fixtures" / "kind_bond_issuance_20260508000981.html"

    client = TestClient(app)
    response = client.get(
        "/api/disclosures/html/sections/source",
        params={
            "input_directory": str(source_file.parent),
            "source_name": source_file.name,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-disposition"].startswith("inline")
    assert "전환사채권 발행결정" in response.text


def test_html_section_source_route_opens_nested_individual_disclosure(tmp_path: Path) -> None:
    input_directory = tmp_path / "kind_html_contents"
    nested_directory = input_directory / "2025" / "shareholder_meeting"
    nested_directory.mkdir(parents=True)
    source_file = nested_directory / "20250101000001.html"
    source_file.write_text("<html><body>중첩 공시 원문</body></html>", encoding="utf-8")

    client = TestClient(app)
    response = client.get(
        "/api/disclosures/html/sections/source",
        params={
            "input_directory": str(input_directory),
            "source_name": "2025/shareholder_meeting/20250101000001.html",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "중첩 공시 원문" in response.text


def test_html_section_source_route_rejects_parent_traversal() -> None:
    fixture_directory = Path(__file__).parent / "fixtures"

    client = TestClient(app)
    response = client.get(
        "/api/disclosures/html/sections/source",
        params={
            "input_directory": str(fixture_directory),
            "source_name": "../test_kind_web_app.py",
        },
    )

    assert response.status_code == 404


def test_html_section_source_split_route_returns_selected_disclosure_sections(tmp_path: Path) -> None:
    input_directory = tmp_path / "kind_html_contents"
    input_directory.mkdir()
    source_file = input_directory / "20260422000832.html"
    source_file.write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p>주요사항보고서</p></h2>
          <p>표지 내용</p>
          <h2 class="SECTION-2" id="toc_2"><p>전환사채권 발행결정</p></h2>
          <p>발행금액 250,000,000</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/html/sections/source/split",
        json={"input_directory": str(input_directory), "source_name": source_file.name},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["document"]["source_name"] == "20260422000832.html"
    assert [(section["toc_id"], section["title"]) for section in data["sections"]] == [
        ("toc_1", "주요사항보고서"),
        ("toc_2", "전환사채권 발행결정"),
    ]
    assert "표지 내용" in data["sections"][0]["html"]
    assert "발행금액 250,000,000" in data["sections"][1]["html"]


def test_html_section_save_start_route_saves_all_explicitly_selected_toc_sections(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source_directory = input_directory / "2008"
    source_directory.mkdir(parents=True)
    (source_directory / "20260422000832.html").write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p>주요사항보고서</p></h2>
          <p>표지 내용</p>
          <h2 class="SECTION-2" id="toc_2"><p>전환사채권 발행결정</p></h2>
          <p>발행금액 250,000,000</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/html/sections/save/start",
        json={
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "section_save_rules": {
                "toc_1 주요사항보고서 toc_2 전환사채권 발행결정": [
                    "toc_1",
                    "toc_2",
                ]
            },
        },
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    snapshot = None
    for _ in range(20):
        status_response = client.get(f"/api/disclosures/html/jobs/{job_id}")
        assert status_response.status_code == 200
        snapshot = status_response.json()
        if snapshot["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert snapshot is not None
    assert snapshot["status"] == "completed"
    assert snapshot["result"]["summary"] == {
        "found_files": 1,
        "saved_files": 1,
        "skipped_files": 0,
        "expected_files": 1,
        "integrity_ok": True,
        "missing_files": 0,
    }
    section_html = (output_directory / "2008" / "20260422000832.html").read_text(encoding="utf-8")
    assert "주요사항보고서" in section_html
    assert "표지 내용" in section_html
    assert "전환사채권 발행결정" in section_html
    assert "발행금액 250,000,000" in section_html
    assert not (output_directory / "2008" / "20260422000832_1.html").exists()
    assert not (output_directory / "2008" / "20260422000832_2.html").exists()
    assert not (output_directory / "toc_1").exists()
    assert not (output_directory / "2008" / "toc_1").exists()


def test_html_section_save_start_route_applies_pattern_toc_selection(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source_directory = input_directory / "2008"
    source_directory.mkdir(parents=True)
    (source_directory / "20260422000832.html").write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p>주요사항보고서</p></h2>
          <p>표지 내용</p>
          <h2 class="SECTION-2" id="toc_2"><p>전환사채권 발행결정</p></h2>
          <p>발행금액 250,000,000</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/html/sections/save/start",
        json={
            "input_directory": str(input_directory),
            "output_directory": str(output_directory),
            "section_save_rules": {"toc_1 주요사항보고서 toc_2 전환사채권 발행결정": ["toc_1"]},
        },
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    snapshot = None
    for _ in range(20):
        status_response = client.get(f"/api/disclosures/html/jobs/{job_id}")
        assert status_response.status_code == 200
        snapshot = status_response.json()
        if snapshot["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert snapshot is not None
    assert snapshot["status"] == "completed"
    assert snapshot["result"]["summary"] == {
        "found_files": 1,
        "saved_files": 1,
        "skipped_files": 0,
        "expected_files": 1,
        "integrity_ok": True,
        "missing_files": 0,
    }
    section_html = (output_directory / "2008" / "20260422000832.html").read_text(encoding="utf-8")
    assert "주요사항보고서" in section_html
    assert "표지 내용" in section_html
    assert "전환사채권 발행결정" not in section_html
    assert "발행금액 250,000,000" not in section_html
    assert not (output_directory / "2008" / "20260422000832_1.html").exists()
    assert not (output_directory / "2008" / "20260422000832_2.html").exists()
    assert not (output_directory / "toc_1").exists()
    assert not (output_directory / "2008" / "toc_1").exists()


def test_html_section_inspect_start_route_lists_toc_sections(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    input_directory.mkdir()
    (input_directory / "20260422000832.html").write_text(
        """
        <html><head></head><body>
          <h2 class="SECTION-1" id="toc_1"><p>주요사항보고서</p></h2>
          <p>표지 내용</p>
          <h2 class="SECTION-2" id="toc_2"><p>전환사채권 발행결정</p></h2>
          <p>발행금액 250,000,000</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/html/sections/inspect/start",
        json={"input_directory": str(input_directory), "workers": 8},
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    snapshot = None
    for _ in range(20):
        status_response = client.get(f"/api/disclosures/html/jobs/{job_id}")
        assert status_response.status_code == 200
        snapshot = status_response.json()
        if snapshot["status"] in {"completed", "failed"}:
            break
        time.sleep(0.05)

    assert snapshot is not None
    assert snapshot["status"] == "completed"
    assert snapshot["result"]["summary"] == {
        "found_files": 1,
        "documents_with_sections": 1,
        "files_without_sections": 0,
        "failed_files": 0,
        "reported_problem_files": 0,
    }
    assert snapshot["result"]["documents"][0]["section_count"] == 2
