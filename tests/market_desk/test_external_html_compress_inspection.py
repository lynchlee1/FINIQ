from __future__ import annotations

import json
from pathlib import Path

from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
)
from finiq.market_desk.web.features.disclosures.external_html_compress import (
    compress_all_disclosure_external_html_payload,
    compress_disclosure_external_html_payload,
    inspect_all_disclosure_external_html_compress_payload,
    inspect_disclosure_external_html_compress_payload,
)
from finiq.market_desk.web.features.disclosures.filter_presets import (
    manage_filter_presets_payload,
)


def _compression_payload(tmp_path: Path) -> dict[str, object]:
    data_root = tmp_path / "workspace"
    manage_filter_presets_payload(
        {
            "data_root": str(data_root),
            "action": "save",
            "preset": {"mode": "bond_issuance", "condition_blocks": []},
        }
    )
    filtered_path = data_root / "03-filter" / "bond_issuance" / "filtered.json"
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
        {"data_root": str(data_root), "mode": "bond_issuance", "parallel_workers": 1},
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


def test_inspect_and_rebuild_all_external_html_compression_modes(tmp_path: Path) -> None:
    payload = _compression_payload(tmp_path)
    compress_disclosure_external_html_payload(payload)
    compressed_path = Path(str(payload["output_directory"])) / "compressed-external-html.json"
    compressed = json.loads(compressed_path.read_text(encoding="utf-8"))
    compressed["records"][0]["title"] = "변조된 제목"
    compressed_path.write_text(json.dumps(compressed, ensure_ascii=False), encoding="utf-8")

    inspected = inspect_all_disclosure_external_html_compress_payload(
        {"data_root": payload["data_root"], "parallel_workers": 1}
    )

    assert inspected["mode_count"] == 1
    assert inspected["failed_modes"] == ["bond_issuance"]
    assert inspected["results"][0]["passed"] is False

    rebuilt = compress_all_disclosure_external_html_payload(
        {"data_root": payload["data_root"], "parallel_workers": 1}
    )
    reinspected = inspect_all_disclosure_external_html_compress_payload(
        {"data_root": payload["data_root"], "parallel_workers": 1}
    )

    assert rebuilt["passed"] is True
    assert rebuilt["regenerated_mode_count"] == 1
    assert reinspected["passed"] is True
