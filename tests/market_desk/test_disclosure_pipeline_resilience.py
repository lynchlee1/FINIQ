from __future__ import annotations

import json
from pathlib import Path

import pytest

from finiq.market_desk.web.features.disclosures.html_cleanup import (
    check_disclosure_html_output_directory_payload,
    create_external_html_integrity_baseline_payload,
    create_internal_html_integrity_baseline_payload,
)
from finiq.market_desk.web.features.disclosures.internal_html_download import (
    download_disclosure_internal_htmls,
    download_disclosure_internal_html_payload,
)
from finiq.market_desk.web.features.disclosures.external_html_download import (
    download_disclosure_external_html_payload,
)
from finiq.market_desk.web.features.disclosures.external_html_compress import (
    compress_disclosure_external_html_payload,
)


def _valid_html(label: str = "valid") -> str:
    return f"<html><body>{label * 30}</body></html>"


def _external_workspace_body(
    tmp_path: Path, source_json: dict, **body: object
) -> dict[str, object]:
    data_root = tmp_path / "workspace"
    filtered_path = data_root / "03-filter" / "bond_issuance" / "filtered.json"
    filtered_path.parent.mkdir(parents=True, exist_ok=True)
    filtered_path.write_text(
        json.dumps({"format": "kind_disclosure_filter_v1", **source_json}),
        encoding="utf-8",
    )
    return {"data_root": str(data_root), "mode": "bond_issuance", **body}


def _internal_html_body(
    tmp_path: Path, acpt_numbers: list[str], **body: object
) -> dict[str, object]:
    source_path = tmp_path / "compressed-external-html.json"
    source_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                    {
                        "acpt_no": acpt_no,
                        "selected_main_doc_no": f"{acpt_no}99",
                        "metadata": {"disclosed_at": "2025-01-01"},
                    }
                    for acpt_no in acpt_numbers
                ],
            }
        ),
        encoding="utf-8",
    )
    return {
        "source_compressed_json_path": str(source_path),
        "output_directory": str(tmp_path / "internal"),
        **body,
    }


def test_external_html_resume_redownloads_invalid_existing_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_directory = tmp_path / "external"
    (output_directory / "2025").mkdir(parents=True)
    target = output_directory / "2025" / "20250101000001.html"
    target.write_text("broken", encoding="utf-8")

    inspection = check_disclosure_html_output_directory_payload(
        _external_workspace_body(
            tmp_path,
            {
                "disclosures": [
                    {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"}
                ]
            },
            output_directory=str(output_directory),
        )
    )
    assert inspection["existing_target_html_count"] == 0
    assert inspection["missing_target_html_count"] == 1
    assert inspection["invalid_target_html_count"] == 1
    assert inspection["auxiliary_file_count"] == 0

    def fake_download(**kwargs: object) -> list[Path]:
        assert kwargs["acpt_numbers"] == ["20250101000001"]
        target.write_text(_valid_html(), encoding="utf-8")
        return [target]

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls",
        fake_download,
    )

    result = download_disclosure_external_html_payload(
        _external_workspace_body(
            tmp_path,
            {
                "disclosures": [
                    {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"}
                ]
            },
            output_directory=str(output_directory),
            skip_existing=True,
        )
    )

    assert result["saved_count"] == 1
    assert target.read_text("utf-8") == _valid_html()


def test_external_html_integrity_baseline_requires_explicit_trust(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "external"
    target = output_directory / "2025" / "20250101000001.html"
    target.parent.mkdir(parents=True)
    target.write_text(_valid_html(), encoding="utf-8")
    body = _external_workspace_body(
        tmp_path,
        {
            "disclosures": [
                {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"}
            ]
        },
        output_directory=str(output_directory),
    )

    with pytest.raises(ValueError, match="신뢰 확인"):
        create_external_html_integrity_baseline_payload(body)

    assert not (output_directory / "kind_disclosure_html_manifest.json").exists()


def test_external_html_hash_mismatch_redownloads_only_changed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_directory = tmp_path / "external"
    first = output_directory / "2025" / "20250101000001.html"
    second = output_directory / "2025" / "20250101000002.html"
    first.parent.mkdir(parents=True)
    first.write_text(_valid_html("first"), encoding="utf-8")
    second.write_text(_valid_html("second"), encoding="utf-8")
    source = {
        "disclosures": [
            {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"},
            {"acpt_no": "20250101000002", "disclosed_at": "2025-01-02"},
        ]
    }
    body = _external_workspace_body(
        tmp_path,
        source,
        output_directory=str(output_directory),
    )
    baseline = create_external_html_integrity_baseline_payload(
        {**body, "trust_existing_files": True}
    )
    assert baseline["hashed_count"] == 2

    second.write_text(_valid_html("changed"), encoding="utf-8")
    inspection = check_disclosure_html_output_directory_payload(body)
    assert inspection["hash_verified_target_html_count"] == 1
    assert inspection["hash_mismatch_target_html_count"] == 1

    calls: list[list[str]] = []

    def fake_download(**kwargs: object) -> list[Path]:
        acpt_numbers = list(kwargs["acpt_numbers"])
        calls.append(acpt_numbers)
        paths: list[Path] = []
        for acpt_no in acpt_numbers:
            path = Path(kwargs["output_directory"]) / f"{acpt_no}.html"
            path.write_text(_valid_html("redownloaded"), encoding="utf-8")
            paths.append(path)
        return paths

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls",
        fake_download,
    )
    result = download_disclosure_external_html_payload(
        {**body, "skip_existing": True}
    )

    assert calls == [["20250101000002"]]
    assert result["saved_count"] == 2
    verified = check_disclosure_html_output_directory_payload(body)
    assert verified["hash_verified_target_html_count"] == 2
    assert verified["hash_mismatch_target_html_count"] == 0


def test_external_html_resume_rejects_existing_file_without_hash_baseline(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "external"
    target = output_directory / "2025" / "20250101000001.html"
    target.parent.mkdir(parents=True)
    target.write_text(_valid_html(), encoding="utf-8")

    with pytest.raises(ValueError, match="기준 해시가 없는"):
        download_disclosure_external_html_payload(
            _external_workspace_body(
                tmp_path,
                {
                    "disclosures": [
                        {
                            "acpt_no": "20250101000001",
                            "disclosed_at": "2025-01-01",
                        }
                    ]
                },
                output_directory=str(output_directory),
                skip_existing=True,
            )
        )


def test_internal_html_integrity_baseline_requires_explicit_trust(
    tmp_path: Path,
) -> None:
    body = _internal_html_body(tmp_path, ["20250101000001"])
    output_directory = Path(str(body["output_directory"]))
    target = output_directory / "2025" / "20250101000001.html"
    target.parent.mkdir(parents=True)
    target.write_text(_valid_html(), encoding="utf-8")

    with pytest.raises(ValueError, match="신뢰 확인"):
        create_internal_html_integrity_baseline_payload(body)

    assert not (output_directory / "kind_disclosure_html_manifest.json").exists()


def test_internal_html_hash_mismatch_redownloads_only_changed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acpt_numbers = ["20250101000001", "20250101000002"]
    body = _internal_html_body(tmp_path, acpt_numbers)
    output_directory = Path(str(body["output_directory"]))
    first = output_directory / "2025" / f"{acpt_numbers[0]}.html"
    second = output_directory / "2025" / f"{acpt_numbers[1]}.html"
    first.parent.mkdir(parents=True)
    first.write_text(_valid_html("first"), encoding="utf-8")
    second.write_text(_valid_html("second"), encoding="utf-8")

    baseline = create_internal_html_integrity_baseline_payload(
        {**body, "trust_existing_files": True}
    )
    assert baseline["hashed_count"] == 2

    second.write_text(_valid_html("changed"), encoding="utf-8")
    inspection = check_disclosure_html_output_directory_payload(body)
    assert inspection["hash_verified_target_html_count"] == 1
    assert inspection["hash_mismatch_target_html_count"] == 1

    calls: list[list[str]] = []

    def fake_download(**kwargs: object) -> list[Path]:
        targets = list(kwargs["targets"])
        calls.append([target["acpt_no"] for target in targets])
        paths: list[Path] = []
        for target in targets:
            path = Path(kwargs["output_directory"]) / f"{target['acpt_no']}.html"
            path.write_text(_valid_html("redownloaded"), encoding="utf-8")
            paths.append(path)
        return paths

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        fake_download,
    )
    result = download_disclosure_internal_html_payload(
        {**body, "skip_existing": True}
    )

    assert calls == [["20250101000002"]]
    assert result["saved_count"] == 2
    verified = check_disclosure_html_output_directory_payload(body)
    assert verified["hash_verified_target_html_count"] == 2
    assert verified["hash_mismatch_target_html_count"] == 0


def test_internal_html_resume_rejects_existing_file_without_hash_baseline(
    tmp_path: Path,
) -> None:
    body = _internal_html_body(tmp_path, ["20250101000001"])
    output_directory = Path(str(body["output_directory"]))
    target = output_directory / "2025" / "20250101000001.html"
    target.parent.mkdir(parents=True)
    target.write_text(_valid_html(), encoding="utf-8")

    with pytest.raises(ValueError, match="기준 해시가 없는"):
        download_disclosure_internal_html_payload(
            {**body, "skip_existing": True}
        )


def test_internal_html_download_rejects_invalid_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._fetch_internal_html",
        lambda *args, **kwargs: b"invalid",
    )

    with pytest.raises(ValueError, match="invalid HTML"):
        download_disclosure_internal_htmls(
            output_directory=tmp_path,
            request_headers={},
            targets=[{"acpt_no": "20250101000001", "doc_no": "1"}],
            max_requests_per_minute=100,
        )

    assert not (tmp_path / "20250101000001.html").exists()


def test_download_payload_reports_parent_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls",
        lambda **kwargs: [],
    )

    result = download_disclosure_external_html_payload(
        _external_workspace_body(
            tmp_path,
            {
                "disclosures": [
                    {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"}
                ]
            },
            output_directory=str(tmp_path / "external"),
        ),
        cancel_check=lambda: True,
    )

    assert result["cancelled"] is True
    assert result["missing_acpt_numbers"] == ["20250101000001"]
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["disclosures"] == []


def test_internal_html_download_cancellation_manifest_lists_only_saved_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps({
            "format": "finiq_disclosure_external_html_docs_v1",
            "records": [{
                "acpt_no": "20250101000001",
                "selected_main_doc_no": "1",
                "metadata": {"disclosed_at": "2025-01-01"},
            }],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        lambda **kwargs: [],
    )

    result = download_disclosure_internal_html_payload(
        {
            "output_directory": str(tmp_path / "content"),
            "source_compressed_json_path": str(compressed_path),
        },
        cancel_check=lambda: True,
    )

    assert result["cancelled"] is True
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["disclosures"] == []


def test_external_html_compression_rejects_receipt_number_mismatching_filename(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "external"
    (input_directory / "2025").mkdir(parents=True)
    (input_directory / "kind_disclosure_html_manifest.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "disclosures": [
                    {"acpt_no": "20250101000001", "title": "KIND 제목"}
                ],
            }
        ),
        encoding="utf-8",
    )
    (input_directory / "2025" / "20250101000001.html").write_text(
        """
        <html><body>
          <input type="hidden" name="acptNo" value="20250101000002" />
          <select id="mainDoc">
            <option value="20250101000999|Y" selected="selected">본문</option>
          </select>
        </body></html>
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match input filename"):
        compress_disclosure_external_html_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(tmp_path / "compressed"),
            }
        )

    assert not (tmp_path / "compressed" / "compressed-external-html.json").exists()
