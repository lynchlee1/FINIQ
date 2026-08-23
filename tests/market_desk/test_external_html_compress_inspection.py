from __future__ import annotations

import json
from pathlib import Path
import time

from fastapi.testclient import TestClient

from finiq.market_desk.web.app import app
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
)
from finiq.market_desk.web.features.disclosures.external_html_compress import (
    compress_disclosure_external_html_payload,
    inspect_all_disclosure_external_html_compress_payload,
    inspect_disclosure_external_html_compress_payload,
    rebuild_invalid_disclosure_external_html_compress_payload,
)
from finiq.market_desk.web.features.disclosures.filter_presets import (
    manage_filter_presets_payload,
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
    filtered_path.write_text(
        json.dumps(
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
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    payload = apply_workspace_defaults(
        "external_html_compress",
        {"data_root": str(data_root), "mode": mode, "parallel_workers": 1},
    )
    output_directory = Path(str(payload["output_directory"]))
    (output_directory / "2025").mkdir(parents=True)
    (output_directory / "kind_disclosure_html_manifest.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "disclosures": [
                    {
                        "acpt_no": "20250101000001",
                        "title": "테스트 공시",
                        "disclosed_at": "2025-01-01",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (output_directory / "2025" / "20250101000001.html").write_text(
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
    return payload


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
    filtered_path.write_text(
        json.dumps(filtered, ensure_ascii=False), encoding="utf-8"
    )

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
    compress_disclosure_external_html_payload(payload)
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.external_html_compress._workspace_filter_presets",
        lambda _data_root: [
            {"id": "bond_issuance", "mode": "bond_issuance"},
            {
                "id": "bond_issuance/bond_issuance_kosdaq",
                "mode": "bond_issuance_kosdaq",
                "parent_mode": "bond_issuance",
            },
        ],
    )

    inspected = inspect_all_disclosure_external_html_compress_payload(
        {"data_root": payload["data_root"], "parallel_workers": 1}
    )

    assert inspected["passed"] is True
    assert inspected["mode_count"] == 2
    assert inspected["expected_records"] == 2
    assert inspected["verified_records"] == 2
    assert inspected["repairable_failed_mode_count"] == 0
    assert all(result["passed"] for result in inspected["results"])
