from __future__ import annotations

import json
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from finiq.market_desk.web.app import app
from finiq.market_desk.web.features.disclosures import external_html_compress
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
)
from finiq.market_desk.web.features.disclosures.external_html_compress import (
    compress_disclosure_external_html_payload,
    inspect_all_disclosure_external_html_compress_payload,
    inspect_disclosure_external_html_compress_payload,
    rebuild_invalid_disclosure_external_html_compress_payload,
)
from finiq.market_desk.web.features.disclosures.html_cleanup import (
    create_external_html_integrity_baseline_payload,
)
from finiq.market_desk.web.features.disclosures.html_common import (
    _source_json_fingerprint,
)
from finiq.market_desk.web.features.disclosures.filter_presets import (
    manage_filter_presets_payload,
)


def _publish_filtered_result(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    workflow_path = path.with_name("filter.json")
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow.pop("result", None)
    workflow.pop("pending", None)
    workflow.update(
        {
            "status": "completed",
            "result_file": path.name,
            "result_fingerprint": _source_json_fingerprint(payload),
        }
    )
    workflow["steps"]["database_query"]["status"] = "completed"
    workflow["steps"]["record"]["status"] = "completed"
    workflow_path.write_text(
        json.dumps(workflow, ensure_ascii=False), encoding="utf-8"
    )


def _compression_payload(
    tmp_path: Path, *, mode: str = "bond_issuance"
) -> dict[str, object]:
    data_root = tmp_path / "workspace"
    manage_filter_presets_payload(
        {
            "data_root": str(data_root),
            "action": "save",
            "preset": {"mode": mode, "condition_blocks": []},
        }
    )
    filtered_path = data_root / "03-filter" / mode / "filtered.json"
    filtered_path.parent.mkdir(parents=True, exist_ok=True)
    _publish_filtered_result(
        filtered_path,
        {
            "format": "kind_disclosure_filter_v1",
            "disclosures": [
                {
                    "acpt_no": "20250101000001",
                    "title": "테스트 공시",
                    "disclosed_at": "2025-01-01",
                }
            ],
        },
    )
    payload = apply_workspace_defaults(
        "external_html_compress",
        {"data_root": str(data_root), "mode": mode, "parallel_workers": 1},
    )
    input_directory = Path(str(payload["input_directory"]))
    (input_directory / "2025").mkdir(parents=True)
    html_path = input_directory / "2025" / "20250101000001.html"
    html_path.write_text(
        """
        <html><body>
          <input type="hidden" name="acptNo" value="20250101000001" />
          <select id="mainDoc">
            <option value="20250101000999|Y" selected="selected">본문</option>
          </select>
          <select id="attachedDoc"><option value="20250101000888">첨부</option></select>
        </body></html>
        """,
        encoding="utf-8",
    )
    (input_directory / "kind_disclosure_html_manifest.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v2",
                "disclosures": [
                    {
                        "acpt_no": "20250101000001",
                        "title": "테스트 공시",
                        "disclosed_at": "2025-01-01",
                        **external_html_compress._html_file_integrity(html_path),
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return payload


def test_external_html_compression_uses_and_creates_standard_output_directory(
    tmp_path: Path,
) -> None:
    payload = _compression_payload(tmp_path)
    output_directory = Path(str(payload["output_directory"]))
    assert not output_directory.exists()

    result = compress_disclosure_external_html_payload(
        {
            "data_root": payload["data_root"],
            "mode": payload["mode"],
            "parallel_workers": 1,
        }
    )

    assert result["output_directory"] == str(output_directory)
    assert (output_directory / "compressed-external-html.json").is_file()


def test_workspace_compression_uses_current_complete_filter_metadata(
    tmp_path: Path,
) -> None:
    payload = _compression_payload(tmp_path)
    filtered_path = (
        Path(str(payload["data_root"]))
        / "03-filter"
        / "bond_issuance"
        / "filtered.json"
    )
    filtered = json.loads(filtered_path.read_text(encoding="utf-8"))
    filtered["disclosures"][0].update(
        {
            "title": "현재 제목",
            "company_key": "company:123456",
            "company_cell_text": "현재 회사 표시값",
        }
    )
    _publish_filtered_result(filtered_path, filtered)
    manifest_path = (
        Path(str(payload["input_directory"]))
        / "kind_disclosure_html_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["disclosures"][0]["title"] = "오래된 제목"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    compress_disclosure_external_html_payload(payload)

    compressed_path = (
        Path(str(payload["output_directory"])) / "compressed-external-html.json"
    )
    record = json.loads(compressed_path.read_text(encoding="utf-8"))["records"][0]
    assert record["title"] == "현재 제목"
    assert record["metadata"]["company_key"] == "company:123456"
    assert record["metadata"]["company_cell_text"] == "현재 회사 표시값"
    assert inspect_disclosure_external_html_compress_payload(payload)["passed"] is True

    filtered["disclosures"][0]["title"] = "더 최신 제목"
    _publish_filtered_result(filtered_path, filtered)

    inspected = inspect_disclosure_external_html_compress_payload(payload)

    assert inspected["passed"] is False
    assert inspected["content_matches_source"] is False


def test_external_html_compression_uses_requested_progress_interval(
    tmp_path: Path,
) -> None:
    payload = _compression_payload(tmp_path)
    payload["progress_interval"] = 1
    progress_log: list[str] = []

    compress_disclosure_external_html_payload(
        payload,
        progress_callback=progress_log.append,
    )

    assert "외부 HTML 압축 중간 확인: 1/1건 처리." in progress_log


def test_workspace_compression_rejects_uncompleted_filter_workflow(
    tmp_path: Path,
) -> None:
    payload = _compression_payload(tmp_path)
    workflow_path = (
        Path(str(payload["data_root"]))
        / "03-filter"
        / "bond_issuance"
        / "filter.json"
    )
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["status"] = "ready"
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

    with pytest.raises(ValueError, match="filter workflow is not completed"):
        compress_disclosure_external_html_payload(payload)


def test_workspace_compression_rejects_changed_filtered_result(
    tmp_path: Path,
) -> None:
    payload = _compression_payload(tmp_path)
    filtered_path = (
        Path(str(payload["data_root"]))
        / "03-filter"
        / "bond_issuance"
        / "filtered.json"
    )
    filtered = json.loads(filtered_path.read_text(encoding="utf-8"))
    filtered["disclosures"][0]["title"] = "봉인 뒤에 바뀐 제목"
    filtered_path.write_text(json.dumps(filtered, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="result fingerprint does not match"):
        compress_disclosure_external_html_payload(payload)


def test_external_html_compression_cancel_preserves_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _compression_payload(tmp_path)
    output_directory = Path(str(payload["output_directory"]))
    output_directory.mkdir(parents=True)
    output_path = output_directory / "compressed-external-html.json"
    output_path.write_text('{"existing": true}', encoding="utf-8")
    processed = False
    original_compress = external_html_compress._compress_external_html_file

    def tracked_compress(args):
        nonlocal processed
        result = original_compress(args)
        processed = True
        return result

    monkeypatch.setattr(
        external_html_compress,
        "_compress_external_html_file",
        tracked_compress,
    )

    with pytest.raises(InterruptedError, match="compression cancelled"):
        compress_disclosure_external_html_payload(
            payload,
            cancel_check=lambda: processed,
        )

    assert output_path.read_text(encoding="utf-8") == '{"existing": true}'
    assert not list(output_directory.parent.glob(".finiq-external-html-compress-*"))


def test_external_html_compression_does_not_fall_back_to_input_directory(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "04-external-html-download" / "bond_issuance"

    with pytest.raises(ValueError, match="output_directory is required"):
        compress_disclosure_external_html_payload(
            {"input_directory": str(input_directory)}
        )

    assert not (input_directory / "compressed-external-html.json").exists()


def test_inspect_external_html_compression_checks_saved_json_content(tmp_path: Path) -> None:
    payload = _compression_payload(tmp_path)
    compress_disclosure_external_html_payload(payload)

    inspected = inspect_disclosure_external_html_compress_payload(payload)

    assert inspected["passed"] is True
    assert inspected["verified_records"] == 1
    assert inspected["content_matches_source"] is True

    compressed_path = Path(str(inspected["compressed_path"]))
    compressed = json.loads(compressed_path.read_text(encoding="utf-8"))
    compressed["records"][0]["title"] = "변조된 제목"
    compressed_path.write_text(json.dumps(compressed, ensure_ascii=False), encoding="utf-8")

    changed = inspect_disclosure_external_html_compress_payload(payload)

    assert changed["passed"] is False
    assert changed["content_matches_source"] is False
    assert "다릅니다" in changed["error"]


def test_inspect_external_html_compression_reports_missing_json(tmp_path: Path) -> None:
    payload = _compression_payload(tmp_path)

    inspected = inspect_disclosure_external_html_compress_payload(payload)

    assert inspected["passed"] is False
    assert inspected["missing_files"] == [
        str(Path(str(payload["output_directory"])) / "compressed-external-html.json")
    ]


def test_inspect_external_html_compression_skips_mode_without_source_html(
    tmp_path: Path,
) -> None:
    payload = _compression_payload(tmp_path)
    input_directory = Path(str(payload["input_directory"]))
    (input_directory / "2025" / "20250101000001.html").unlink()

    inspected = inspect_disclosure_external_html_compress_payload(payload)

    assert inspected["passed"] is True
    assert inspected["skipped"] is True
    assert inspected["expected_records"] == 0
    assert inspected["missing_files"] == []


def test_inspect_external_html_compression_rejects_orphaned_output(
    tmp_path: Path,
) -> None:
    payload = _compression_payload(tmp_path)
    compress_disclosure_external_html_payload(payload)
    input_directory = Path(str(payload["input_directory"]))
    (input_directory / "2025" / "20250101000001.html").unlink()

    inspected = inspect_disclosure_external_html_compress_payload(payload)

    assert inspected["passed"] is False
    assert inspected["skipped"] is False
    assert inspected["orphaned_output"] is True
    assert inspected["unexpected_records"] == 1
    assert Path(str(inspected["compressed_path"])).is_file()

    all_modes = inspect_all_disclosure_external_html_compress_payload(
        {"data_root": payload["data_root"], "parallel_workers": 1}
    )
    assert all_modes["failed_modes"] == ["bond_issuance"]
    assert all_modes["repairable_failed_modes"] == []


def test_compression_rejects_source_html_changed_after_manifest(
    tmp_path: Path,
) -> None:
    payload = _compression_payload(tmp_path)
    compress_disclosure_external_html_payload(payload)
    compressed_path = (
        Path(str(payload["output_directory"])) / "compressed-external-html.json"
    )
    saved_before = compressed_path.read_bytes()
    html_path = (
        Path(str(payload["input_directory"]))
        / "2025"
        / "20250101000001.html"
    )
    html_path.write_text(
        """
        <html><body>
          <input type="hidden" name="acptNo" value="20250101000001" />
          <select id="mainDoc">
            <option value="20250101000777|Y" selected="selected">바뀐 본문</option>
          </select>
          <select id="attachedDoc"><option value="20250101000888">첨부</option></select>
        </body></html>
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="manifest integrity"):
        compress_disclosure_external_html_payload(payload)

    inspected = inspect_disclosure_external_html_compress_payload(payload)
    assert inspected["passed"] is False
    assert "manifest integrity" in inspected["error"]
    assert compressed_path.read_bytes() == saved_before


def test_compression_rejects_missing_manifest_integrity_baseline(
    tmp_path: Path,
) -> None:
    payload = _compression_payload(tmp_path)
    manifest_path = (
        Path(str(payload["input_directory"]))
        / "kind_disclosure_html_manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["disclosures"][0].pop("source_sha256")
    manifest["disclosures"][0].pop("source_size_bytes")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="manifest integrity.*unverified"):
        compress_disclosure_external_html_payload(payload)

    assert not (
        Path(str(payload["output_directory"])) / "compressed-external-html.json"
    ).exists()


def test_inspect_external_html_compression_skips_missing_source_directory(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    manage_filter_presets_payload(
        {
            "data_root": str(data_root),
            "action": "save",
            "preset": {"mode": "bond_issuance", "condition_blocks": []},
        }
    )
    output_directory = (
        data_root / "04-external-html-download" / "bond_issuance"
    )

    inspected = inspect_all_disclosure_external_html_compress_payload(
        {"data_root": str(data_root), "parallel_workers": 1}
    )

    assert inspected["passed"] is True
    assert inspected["skipped_modes"] == ["bond_issuance"]
    assert inspected["repairable_failed_modes"] == []
    assert not output_directory.exists()
    assert not (data_root / "01-list").exists()
    assert not (data_root / "02-table").exists()
    assert not (data_root / "05-internal-html-download").exists()


def test_all_mode_inspection_rejects_wrong_filter_workflow_format(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    workflow_path = data_root / "03-filter" / "broken" / "filter.json"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(json.dumps({"format": "wrong"}), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid disclosure filter workflow JSON"):
        inspect_all_disclosure_external_html_compress_payload(
            {"data_root": str(data_root), "parallel_workers": 1}
        )


def test_inspect_external_html_compression_ignores_filter_targets_without_html(
    tmp_path: Path,
) -> None:
    payload = _compression_payload(tmp_path)
    compress_disclosure_external_html_payload(payload)
    filtered_path = (
        Path(str(payload["data_root"]))
        / "03-filter"
        / "bond_issuance"
        / "filtered.json"
    )
    filtered = json.loads(filtered_path.read_text(encoding="utf-8"))
    filtered["disclosures"].append(
        {
            "acpt_no": "20250102000002",
            "title": "아직 저장되지 않은 공시",
            "disclosed_at": "2025-01-02",
        }
    )
    _publish_filtered_result(filtered_path, filtered)

    inspected = inspect_disclosure_external_html_compress_payload(payload)

    assert inspected["passed"] is True
    assert inspected["expected_records"] == 1
    assert inspected["verified_records"] == 1


def test_inspect_and_rebuild_invalid_external_html_compression_modes(tmp_path: Path) -> None:
    payload = _compression_payload(tmp_path)
    valid_payload = _compression_payload(tmp_path, mode="rights_issuance")
    compress_disclosure_external_html_payload(payload)
    compress_disclosure_external_html_payload(valid_payload)
    valid_compressed_path = (
        Path(str(valid_payload["output_directory"])) / "compressed-external-html.json"
    )
    valid_compressed_inode = valid_compressed_path.stat().st_ino
    compressed_path = Path(str(payload["output_directory"])) / "compressed-external-html.json"
    compressed = json.loads(compressed_path.read_text(encoding="utf-8"))
    compressed["records"][0]["title"] = "변조된 제목"
    compressed_path.write_text(json.dumps(compressed, ensure_ascii=False), encoding="utf-8")

    inspected = inspect_all_disclosure_external_html_compress_payload(
        {"data_root": payload["data_root"], "parallel_workers": 1}
    )

    assert inspected["mode_count"] == 2
    assert inspected["failed_modes"] == ["bond_issuance"]
    assert inspected["repairable_failed_modes"] == ["bond_issuance"]
    assert inspected["results"][0]["passed"] is False

    rebuilt = rebuild_invalid_disclosure_external_html_compress_payload(
        {"data_root": payload["data_root"], "parallel_workers": 1}
    )
    reinspected = inspect_all_disclosure_external_html_compress_payload(
        {"data_root": payload["data_root"], "parallel_workers": 1}
    )

    assert rebuilt["passed"] is True
    assert rebuilt["target_mode_count"] == 1
    assert rebuilt["regenerated_mode_count"] == 1
    assert rebuilt["verification"]["passed"] is True
    assert valid_compressed_path.stat().st_ino == valid_compressed_inode
    assert reinspected["passed"] is True


def test_rebuild_only_modes_with_source_html_when_modes_are_mixed(tmp_path: Path) -> None:
    payload = _compression_payload(tmp_path)
    empty_payload = _compression_payload(tmp_path, mode="rights_issuance")
    compress_disclosure_external_html_payload(payload)
    compressed_path = Path(str(payload["output_directory"])) / "compressed-external-html.json"
    compressed = json.loads(compressed_path.read_text(encoding="utf-8"))
    compressed["records"][0]["title"] = "변조된 제목"
    compressed_path.write_text(json.dumps(compressed, ensure_ascii=False), encoding="utf-8")
    empty_input_directory = Path(str(empty_payload["input_directory"]))
    (empty_input_directory / "2025" / "20250101000001.html").unlink()

    inspected = inspect_all_disclosure_external_html_compress_payload(
        {"data_root": payload["data_root"], "parallel_workers": 1}
    )

    assert inspected["passed"] is False
    assert inspected["failed_modes"] == ["bond_issuance"]
    assert inspected["repairable_failed_modes"] == ["bond_issuance"]
    assert inspected["skipped_modes"] == ["rights_issuance"]

    rebuilt = rebuild_invalid_disclosure_external_html_compress_payload(
        {"data_root": payload["data_root"], "parallel_workers": 1}
    )

    assert rebuilt["passed"] is True
    assert rebuilt["target_mode_count"] == 1
    assert rebuilt["regenerated_mode_count"] == 1
    assert rebuilt["verification"]["skipped_modes"] == ["rights_issuance"]


def test_rebuild_invalid_compression_stops_before_next_mode_when_cancelled(
    tmp_path: Path, monkeypatch,
) -> None:
    inspection = {
        "passed": False,
        "failed_modes": ["bond_issuance", "rights_issuance"],
        "results": [
            {"mode": "bond_issuance", "repairable": True},
            {"mode": "rights_issuance", "repairable": True},
        ],
    }
    calls: list[dict[str, object]] = []
    cancelled = False
    supplied_cancel_check = None

    def fake_compress(body, progress_callback=None, cancel_check=None):
        nonlocal cancelled, supplied_cancel_check
        calls.append(body)
        supplied_cancel_check = cancel_check
        cancelled = True
        return {"format": "fake"}

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.external_html_compress.inspect_all_disclosure_external_html_compress_payload",
        lambda _body: inspection,
    )
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.external_html_compress.compress_disclosure_external_html_payload",
        fake_compress,
    )

    result = rebuild_invalid_disclosure_external_html_compress_payload(
        {
            "data_root": str(tmp_path / "workspace"),
            "progress_interval": 7,
        },
        cancel_check=lambda: cancelled,
    )

    assert [call["mode"] for call in calls] == ["bond_issuance"]
    assert calls[0]["progress_interval"] == 7
    assert supplied_cancel_check is not None
    assert supplied_cancel_check() is True
    assert result["cancelled"] is True
    assert result["passed"] is False
    assert result["verification"] is inspection


def test_repair_route_regenerates_invalid_compression_without_database(
    tmp_path: Path,
) -> None:
    payload = _compression_payload(tmp_path)
    valid_payload = _compression_payload(tmp_path, mode="rights_issuance")
    compress_disclosure_external_html_payload(payload)
    compress_disclosure_external_html_payload(valid_payload)
    valid_compressed_path = (
        Path(str(valid_payload["output_directory"])) / "compressed-external-html.json"
    )
    valid_compressed_inode = valid_compressed_path.stat().st_ino
    compressed_path = Path(str(payload["output_directory"])) / "compressed-external-html.json"
    compressed = json.loads(compressed_path.read_text(encoding="utf-8"))
    compressed["records"][0]["title"] = "변조된 제목"
    compressed_path.write_text(json.dumps(compressed, ensure_ascii=False), encoding="utf-8")

    client = TestClient(app)
    response = client.post(
        "/api/disclosures/external-html-download/compress/repair/start",
        json={"data_root": payload["data_root"], "parallel_workers": 1},
    )

    assert response.status_code == 200
    job_id = response.json()["job_id"]
    snapshot = None
    for _ in range(100):
        snapshot = client.get(f"/api/disclosures/html/jobs/{job_id}").json()
        if snapshot["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)

    assert snapshot is not None
    assert snapshot["status"] == "completed"
    assert snapshot["result"]["passed"] is True
    assert snapshot["result"]["target_mode_count"] == 1
    assert snapshot["result"]["verification"]["passed"] is True
    assert valid_compressed_path.stat().st_ino == valid_compressed_inode
    assert inspect_all_disclosure_external_html_compress_payload(
        {"data_root": payload["data_root"], "parallel_workers": 1}
    )["passed"] is True


def test_derived_mode_inspects_the_same_owner_html_and_compressed_file(
    tmp_path: Path, monkeypatch
) -> None:
    payload = _compression_payload(tmp_path)
    data_root = Path(str(payload["data_root"]))
    parent_filtered_path = data_root / "03-filter" / "bond_issuance" / "filtered.json"
    parent_filtered = json.loads(parent_filtered_path.read_text(encoding="utf-8"))
    second_disclosure = {
        "acpt_no": "20250102000002",
        "title": "두 번째 공시",
        "disclosed_at": "2025-01-02",
    }
    parent_filtered["disclosures"].append(second_disclosure)
    _publish_filtered_result(parent_filtered_path, parent_filtered)
    input_directory = Path(str(payload["input_directory"]))
    (input_directory / "2025" / "20250102000002.html").write_text(
        """
        <html><body>
          <input type="hidden" name="acptNo" value="20250102000002" />
          <select id="mainDoc">
            <option value="20250102000999|Y" selected="selected">본문</option>
          </select>
          <select id="attachedDoc"><option value="20250102000888">첨부</option></select>
        </body></html>
        """,
        encoding="utf-8",
    )
    create_external_html_integrity_baseline_payload(
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "output_directory": str(input_directory),
            "trust_existing_files": True,
        }
    )
    compress_disclosure_external_html_payload(payload)
    child_mode = "bond_issuance_kosdaq"
    child_filtered_path = (
        parent_filtered_path.parent
        / "subfilters"
        / child_mode
        / "filtered.json"
    )
    manage_filter_presets_payload(
        {
            "data_root": str(data_root),
            "action": "save",
            "preset": {
                "mode": child_mode,
                "parent_mode": "bond_issuance",
                "condition_blocks": [],
            },
        }
    )
    _publish_filtered_result(
        child_filtered_path,
        {
            "format": "kind_disclosure_filter_v1",
            "parent_mode": "bond_issuance",
            "parent_result_fingerprint": _source_json_fingerprint(parent_filtered),
            "disclosures": [second_disclosure],
        },
    )
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.external_html_compress._workspace_filter_presets",
        lambda _data_root: [
            {"id": "bond_issuance", "mode": "bond_issuance"},
            {
                "id": "bond_issuance/bond_issuance_kosdaq",
                "mode": child_mode,
                "parent_mode": "bond_issuance",
            },
        ],
    )

    inspected = inspect_all_disclosure_external_html_compress_payload(
        {"data_root": payload["data_root"], "parallel_workers": 1}
    )

    assert inspected["passed"] is True
    assert inspected["mode_count"] == 2
    assert inspected["expected_records"] == 3
    assert inspected["verified_records"] == 3
    assert inspected["repairable_failed_mode_count"] == 0
    assert all(result["passed"] for result in inspected["results"])

    compressed_path = (
        Path(str(payload["output_directory"])) / "compressed-external-html.json"
    )
    compressed = json.loads(compressed_path.read_text(encoding="utf-8"))
    compressed["records"] = [
        record
        for record in compressed["records"]
        if record["acpt_no"] != second_disclosure["acpt_no"]
    ]
    compressed_path.write_text(json.dumps(compressed, ensure_ascii=False), encoding="utf-8")
    derived_payload = apply_workspace_defaults(
        "external_html_compress",
        {
            "data_root": str(data_root),
            "mode": child_mode,
            "parent_mode": "bond_issuance",
            "parallel_workers": 1,
        },
        create_workspace=False,
    )

    derived_inspection = inspect_disclosure_external_html_compress_payload(
        derived_payload
    )

    assert derived_inspection["passed"] is False
    assert "missing derived targets" in derived_inspection["error"]
