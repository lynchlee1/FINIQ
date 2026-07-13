from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from fastapi.testclient import TestClient
import finiq.market_desk.web.app as web_app
from finiq.market_desk.web.app import _normalize_file_dialog_mode, app, config
from finiq.config import AppConfig
from finiq.market_desk.web.jobs import JobManager, job_manager
from finiq.market_desk.web.features.downloads.kind_common import (
    configure_download_job_retention,
)

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
    (kind_dir / "test.company_classification.json").write_text("[]")
    
    config.output_root = str(tmp_path)
    
    client = TestClient(app)
    response = client.get("/api/classifications")
    assert response.status_code == 200
    data = response.json()
    assert any("test.company_classification.json" in f["name"] for f in data["classification_files"])

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
    def fake_filter_disclosures_payload(body, progress_callback=None):
        if progress_callback:
            progress_callback({
                "source_type": "sqlite_manifest",
                "unit_label": "공시",
                "completed": 1,
                "total": 2,
                "records": 1,
            })
        return {
            "format": "kind_disclosure_filter_v1",
            "summary": {"matched_disclosures": 2, "returned_disclosures": 2},
            "html_download_acpt_numbers": ["1", "2"],
            "disclosures": [],
        }

    monkeypatch.setattr(web_app, "filter_disclosures_payload", fake_filter_disclosures_payload)

    client = TestClient(app)
    transfer_dir = tmp_path / "filtered"
    with client.stream(
        "POST",
        "/api/disclosures/filter",
        headers={"Accept": "application/x-ndjson"},
        json={"html_transfer_path": str(transfer_dir)},
    ) as response:
        assert response.status_code == 200
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert any(event["type"] == "progress" and event["progress"]["completed"] == 1 for event in events)
    result = next(event["payload"] for event in events if event["type"] == "result")
    transfer = result["html_download_transfer"]
    transfer_path = Path(transfer["path"])
    assert transfer["acpt_numbers"] == 2
    assert transfer_path.is_file()
    assert transfer_path.parent == transfer_dir.resolve()


def test_load_disclosure_filter_preset_reads_result_json_filters(tmp_path: Path) -> None:
    source_path = tmp_path / "filtered-disclosures.json"
    filter_blocks = [
        {
            "field": "title",
            "operator": "contains",
            "value": "전환사채",
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
    response = client.post(
        "/api/disclosures/filter/preset",
        json={"source_json_path": str(source_path)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "kind_disclosure_filter_preset_v1"
    assert payload["name"] == "filtered-disclosures"
    assert payload["source_json_path"] == str(source_path.resolve())
    assert payload["condition_blocks"] == filter_blocks


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
        "/api/disclosures/html/download/inspect-folder",
        json={
            "output_directory": str(output_directory),
            "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
            "delete_confirmed": True,
            "delete_confirmation_text": "확인했습니다.",
        },
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
        "/api/disclosures/html/download/inspect-folder",
        json={
            "output_directory": str(output_directory),
            "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
            "dry_run": True,
        },
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
        "/api/disclosures/html/download/check-existing",
        json={
            "output_directory": str(output_directory),
            "json": {
                "disclosures": [
                    {"acpt_no": "20250101000001"},
                    {"acpt_no": "20250101000002"},
                ]
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "kind_disclosure_html_existing_check_v1"
    assert payload["has_existing"] is True
    assert payload["existing_target_html_count"] == 1
    assert payload["missing_target_html_count"] == 1


def test_html_content_download_inspect_folder_route_uses_yearly_layout(tmp_path: Path) -> None:
    source_directory = tmp_path / "viewer_html"
    source_year_directory = source_directory / "2025"
    source_year_directory.mkdir(parents=True)
    (source_year_directory / "20250101000001.html").write_text(
        """
        <html><body>
          <select id="mainDoc">
            <option value="20250101000099|Y" selected="selected">본문</option>
          </select>
        </body></html>
        """,
        encoding="utf-8",
    )
    output_directory = tmp_path / "content_html"
    (output_directory / "2024").mkdir(parents=True)
    (output_directory / "2024" / "20240101000001.html").write_text(
        "<html></html>", encoding="utf-8"
    )

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/html/content-download/inspect-folder",
        json={
            "source_directory": str(source_directory),
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


def test_html_content_download_inspect_folder_uses_fast_source_scan(tmp_path: Path) -> None:
    source_directory = tmp_path / "viewer_html"
    (source_directory / "2025").mkdir(parents=True)
    (source_directory / "2025" / "20250101000001.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    output_directory = tmp_path / "content_html"
    output_directory.mkdir()

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/html/content-download/inspect-folder",
        json={
            "source_directory": str(source_directory),
            "output_directory": str(output_directory),
            "dry_run": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "content"
    assert payload["requested_count"] == 1
    assert payload["deletion_candidate_count"] == 0


def test_html_content_download_check_existing_route_uses_yearly_layout(tmp_path: Path) -> None:
    source_directory = tmp_path / "viewer_html"
    source_year_directory = source_directory / "2025"
    source_year_directory.mkdir(parents=True)
    (source_year_directory / "20250101000001.html").write_text(
        """
        <html><body>
          <select id="mainDoc">
            <option value="20250101000099|Y" selected="selected">본문</option>
          </select>
        </body></html>
        """,
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
        "/api/disclosures/html/content-download/check-existing",
        json={
            "source_directory": str(source_directory),
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


def test_html_content_download_check_existing_route_uses_compressed_json_year(
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
                        "year": "2025",
                        "selected_main_doc_no": "20250101000999",
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
        "/api/disclosures/html/content-download/check-existing",
        json={
            "source_compressed_json_path": str(compressed_path),
            "output_directory": str(output_directory),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "content"
    assert payload["requested_count"] == 1


def test_html_content_download_check_existing_route_finds_yearly_output(
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
                        "year": "2025",
                        "selected_main_doc_no": "20250101000999",
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
        "/api/disclosures/html/content-download/check-existing",
        json={
            "source_compressed_json_path": str(compressed_path),
            "output_directory": str(output_directory),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["existing_target_html_count"] == 1


def test_html_download_inspect_folder_route_rejects_high_risk_directory() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/disclosures/html/download/inspect-folder",
        json={
            "output_directory": str(Path(Path.cwd().anchor).resolve()),
            "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
            "dry_run": True,
        },
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


def test_html_section_inspect_route_returns_document_toc_and_problem_files(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    input_directory.mkdir()
    (input_directory / "20260421000111.html").write_text(
        "<html><body><p>목차 없는 문서</p></body></html>",
        encoding="utf-8",
    )
    (input_directory / "20260422000832.html").write_text(
        """
        <html><body>
          <h2 id="toc_1"><p>주요사항보고서</p></h2>
          <p>표지 내용</p>
          <h2 id="toc_2"><p>전환사채권 발행결정</p></h2>
          <p>발행금액 250,000,000</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/html/sections/inspect",
        json={"input_directory": str(input_directory), "report_limit": 10},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == {
        "found_files": 2,
        "documents_with_sections": 1,
        "files_without_sections": 1,
        "failed_files": 0,
        "reported_problem_files": 1,
    }
    assert data["documents"][0]["source_name"] == "20260422000832.html"
    assert [section["toc_id"] for section in data["documents"][0]["sections"]] == ["toc_1", "toc_2"]
    assert data["problem_files"] == [
        {
            "kind": "no_sections",
            "source_file": str(input_directory / "20260421000111.html"),
            "error": "",
        }
    ]


def test_html_section_source_list_route_returns_one_page_with_toc_counts(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    input_directory.mkdir()
    for index in range(21):
        section_markup = "<h2 id='toc_1'><p>목차</p></h2>"
        if index == 0:
            section_markup += "<h2 id='toc_2'><p>본문</p></h2>"
        (input_directory / f"202604{index + 1:02d}000001.html").write_text(
            f"<html><body>{section_markup}</body></html>",
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
            <html><body>
              <h2 id="toc_1"><p>1</p></h2>
              <h2 id="toc_2"><p>2</p></h2>
            </body></html>
            """,
            encoding="utf-8",
        )
    (input_directory / "20260403000001.html").write_text(
        "<html><body><h2 id='toc_1'><p>1</p></h2></body></html>",
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
        <html><body>
          <h2 id="toc_1"><p>주요사항보고서</p></h2>
          <p>표지 내용</p>
          <h2 id="toc_2"><p>전환사채권 발행결정</p></h2>
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


def test_html_section_save_start_route_saves_all_toc_sections(tmp_path: Path) -> None:
    input_directory = tmp_path / "content_html"
    output_directory = tmp_path / "section_html"
    source_directory = input_directory / "2008"
    source_directory.mkdir(parents=True)
    (source_directory / "20260422000832.html").write_text(
        """
        <html><body>
          <h2 id="toc_1"><p>주요사항보고서</p></h2>
          <p>표지 내용</p>
          <h2 id="toc_2"><p>전환사채권 발행결정</p></h2>
          <p>발행금액 250,000,000</p>
        </body></html>
        """,
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/html/sections/save/start",
        json={"input_directory": str(input_directory), "output_directory": str(output_directory)},
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
        <html><body>
          <h2 id="toc_1"><p>주요사항보고서</p></h2>
          <p>표지 내용</p>
          <h2 id="toc_2"><p>전환사채권 발행결정</p></h2>
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
        <html><body>
          <h2 id="toc_1"><p>주요사항보고서</p></h2>
          <p>표지 내용</p>
          <h2 id="toc_2"><p>전환사채권 발행결정</p></h2>
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
