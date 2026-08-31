from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import requests

from finiq.market_desk.web.features.disclosures.html_common import (
    _render_internal_html_source_unavailable_marker,
    _source_json_fingerprint,
)
from finiq.market_desk.web.features.disclosures.html_cleanup import (
    check_disclosure_html_output_directory_payload,
    clean_disclosure_html_output_directory_payload,
    create_external_html_integrity_baseline_payload,
    create_internal_html_integrity_baseline_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_common import (
    _build_parse_request,
    _collect_html_files,
    _derived_allowed_acpt_numbers,
    _parse_metadata_paths,
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


def _selected_main_doc(doc_no: str) -> dict[str, object]:
    return {
        "selected_main_doc_no": doc_no,
        "docs": [
            {
                "select_id": "mainDoc",
                "doc_no": doc_no,
                "selected": True,
            }
        ],
    }


def _publish_filter_result(
    data_root: Path,
    *,
    mode: str,
    payload: dict[str, object],
    parent_mode: str | None = None,
) -> Path:
    mode_directory = (
        data_root / "03-filter" / mode
        if parent_mode is None
        else data_root / "03-filter" / parent_mode / "subfilters" / mode
    )
    mode_directory.mkdir(parents=True, exist_ok=True)
    filtered_path = mode_directory / "filtered.json"
    filtered_path.write_text(json.dumps(payload), encoding="utf-8")
    workflow = {
        "format": "finiq_disclosure_filter_workflow",
        "mode": mode,
        "parent_mode": parent_mode,
        "status": "completed",
        "result_file": filtered_path.name,
        "result_fingerprint": _source_json_fingerprint(payload),
    }
    if parent_mode is not None:
        workflow["parent_result_fingerprint"] = payload[
            "parent_result_fingerprint"
        ]
    (mode_directory / "filter.json").write_text(
        json.dumps(workflow), encoding="utf-8"
    )
    return filtered_path


def _external_workspace_body(
    tmp_path: Path, source_json: dict, **body: object
) -> dict[str, object]:
    data_root = tmp_path / "workspace"
    _publish_filter_result(
        data_root,
        mode="bond_issuance",
        payload={"format": "kind_disclosure_filter_v1", **source_json},
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
                        **_selected_main_doc(f"{acpt_no}99"),
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


def _write_derived_filter(
    data_root: Path,
    *,
    parent_mode: str = "parent",
    mode: str = "child",
    parent_disclosures: list[dict[str, str]],
    child_disclosures: list[dict[str, str]],
) -> None:
    parent_payload = {
        "format": "kind_disclosure_filter_v1",
        "disclosures": parent_disclosures,
    }
    _publish_filter_result(
        data_root,
        mode=parent_mode,
        payload=parent_payload,
    )
    _publish_filter_result(
        data_root,
        mode=mode,
        parent_mode=parent_mode,
        payload={
            "format": "kind_disclosure_filter_v1",
            "parent_mode": parent_mode,
            "parent_result_fingerprint": _source_json_fingerprint(parent_payload),
            "disclosures": child_disclosures,
        },
    )


def test_derived_external_html_strictly_reuses_parent_without_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "workspace"
    parent_disclosures = [
        {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"},
        {"acpt_no": "20250101000002", "disclosed_at": "2025-01-02"},
    ]
    _write_derived_filter(
        data_root,
        parent_disclosures=parent_disclosures,
        child_disclosures=[parent_disclosures[1]],
    )
    parent_output = data_root / "04-external-html-download" / "parent"
    for disclosure in parent_disclosures:
        target = parent_output / "2025" / f"{disclosure['acpt_no']}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_valid_html(disclosure["acpt_no"]), encoding="utf-8")
    create_external_html_integrity_baseline_payload(
        {
            "data_root": str(data_root),
            "mode": "parent",
            "output_directory": str(parent_output),
            "trust_existing_files": True,
        }
    )
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls",
        lambda **_kwargs: pytest.fail("derived external HTML must not download"),
    )

    result = download_disclosure_external_html_payload(
        {
            "data_root": str(data_root),
            "mode": "child",
            "parent_mode": "parent",
            "output_directory": str(parent_output),
        }
    )

    assert result["reused_parent_html"] is True
    assert result["network_fetch_count"] == 0
    assert result["acpt_numbers"] == ["20250101000002"]
    assert not (data_root / "04-external-html-download" / "child").exists()

    checked = check_disclosure_html_output_directory_payload(
        {
            "data_root": str(data_root),
            "mode": "child",
            "parent_mode": "parent",
            "output_directory": str(parent_output),
        }
    )
    cleaned = clean_disclosure_html_output_directory_payload(
        {
            "data_root": str(data_root),
            "mode": "child",
            "parent_mode": "parent",
            "output_directory": str(parent_output),
            "delete_confirmed": True,
            "delete_confirmation_text": "확인했습니다.",
        }
    )
    assert checked["unexpected_file_count"] == 0
    assert checked["deletion_candidate_count"] == 0
    assert cleaned["deleted_count"] == 0
    assert cleaned["deletion_candidates"] == []
    assert (parent_output / "2025" / "20250101000001.html").is_file()


def test_derived_external_html_inspection_reports_missing_parent_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "workspace"
    parent_disclosures = [
        {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"},
        {"acpt_no": "20250101000002", "disclosed_at": "2025-01-02"},
    ]
    _write_derived_filter(
        data_root,
        parent_disclosures=parent_disclosures,
        child_disclosures=parent_disclosures,
    )
    parent_output = data_root / "04-external-html-download" / "parent"
    present = parent_output / "2025" / "20250101000001.html"
    present.parent.mkdir(parents=True, exist_ok=True)
    present.write_text(_valid_html("20250101000001"), encoding="utf-8")
    create_external_html_integrity_baseline_payload(
        {
            "data_root": str(data_root),
            "mode": "parent",
            "output_directory": str(parent_output),
            "trust_existing_files": True,
        }
    )
    body = {
        "data_root": str(data_root),
        "mode": "child",
        "parent_mode": "parent",
        "output_directory": str(parent_output),
    }

    checked = check_disclosure_html_output_directory_payload(body)

    assert checked["requested_count"] == 2
    assert checked["existing_target_html_count"] == 1
    assert checked["missing_target_html_count"] == 1
    assert checked["missing_target_acpt_numbers"] == ["20250101000002"]
    assert checked["invalid_target_html_count"] == 0
    assert checked["hash_mismatch_target_html_count"] == 0
    assert checked["deletion_candidate_count"] == 0
    assert checked["unexpected_file_count"] == 0
    assert checked["download_required_target_html_count"] == 1

    cleaned = clean_disclosure_html_output_directory_payload(
        {
            **body,
            "delete_confirmed": True,
            "delete_confirmation_text": "확인했습니다.",
        }
    )
    assert cleaned["deleted_count"] == 0
    assert present.is_file()

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls",
        lambda **_kwargs: pytest.fail("derived external HTML must not download"),
    )
    with pytest.raises(ValueError, match="cannot be reused"):
        download_disclosure_external_html_payload(body)


def test_derived_external_html_compression_reuses_parent_file_without_rewrite(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    parent_disclosures = [
        {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"},
        {"acpt_no": "20250101000002", "disclosed_at": "2025-01-02"},
    ]
    _write_derived_filter(
        data_root,
        parent_disclosures=parent_disclosures,
        child_disclosures=[parent_disclosures[1]],
    )
    parent_output = data_root / "04-external-html-download" / "parent"
    for disclosure in parent_disclosures:
        target = parent_output / "2025" / f"{disclosure['acpt_no']}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_valid_html(disclosure["acpt_no"]), encoding="utf-8")
    create_external_html_integrity_baseline_payload(
        {
            "data_root": str(data_root),
            "mode": "parent",
            "output_directory": str(parent_output),
            "trust_existing_files": True,
        }
    )
    compressed_path = (
        data_root
        / "04-external-html-compress"
        / "parent"
        / "compressed-external-html.json"
    )
    compressed_path.parent.mkdir(parents=True, exist_ok=True)
    integrity_by_acpt_no = {
        item["acpt_no"]: {
            "source_sha256": item["source_sha256"],
            "source_size_bytes": item["source_size_bytes"],
        }
        for item in json.loads(
            (parent_output / "kind_disclosure_html_manifest.json").read_text(
                encoding="utf-8"
            )
        )["disclosures"]
    }
    compressed_payload = {
        "format": "finiq_disclosure_external_html_docs_v1",
        "records": [
            {
                "acpt_no": disclosure["acpt_no"],
                **_selected_main_doc(f"{disclosure['acpt_no']}99"),
                "metadata": disclosure,
                **integrity_by_acpt_no[disclosure["acpt_no"]],
            }
            for disclosure in parent_disclosures
        ],
    }
    compressed_path.write_text(json.dumps(compressed_payload), encoding="utf-8")
    original_bytes = compressed_path.read_bytes()

    result = compress_disclosure_external_html_payload(
        {
            "data_root": str(data_root),
            "mode": "child",
            "parent_mode": "parent",
            "input_directory": str(parent_output),
            "output_directory": str(compressed_path.parent),
        }
    )

    assert result["reused_parent_compressed_html"] is True
    assert result["summary"] == {
        "found_files": 1,
        "compressed_files": 1,
        "written_files": 0,
    }
    assert compressed_path.read_bytes() == original_bytes


def test_derived_parse_selects_child_membership_before_limit(tmp_path: Path) -> None:
    input_directory = tmp_path / "sections"
    year_directory = input_directory / "2025"
    year_directory.mkdir(parents=True)
    parent_only = year_directory / "20250101000001.html"
    child = year_directory / "20250101000002.html"
    parent_only.write_text(_valid_html("parent"), encoding="utf-8")
    child.write_text(_valid_html("child"), encoding="utf-8")
    data_root = tmp_path / "workspace"
    parent_disclosure = {
        "acpt_no": parent_only.stem,
        "disclosed_at": "2025-01-01 09:00",
    }
    child_disclosure = {
        "acpt_no": child.stem,
        "disclosed_at": "2025-01-02 09:00",
    }
    _write_derived_filter(
        data_root,
        parent_mode="bond_issuance",
        mode="child",
        parent_disclosures=[parent_disclosure, child_disclosure],
        child_disclosures=[child_disclosure],
    )
    filtered_path = (
        data_root
        / "03-filter"
        / "bond_issuance"
        / "subfilters"
        / "child"
        / "filtered.json"
    )
    compressed_path = tmp_path / "workspace" / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "records": [
                    {
                        "acpt_no": parent_only.stem,
                        "selected_main_doc_no": "",
                        "metadata": None,
                    },
                    {
                        "acpt_no": child.stem,
                        **_selected_main_doc("doc-child"),
                        "metadata": {"disclosed_at": "2025-01-02 09:00"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    request = _build_parse_request(
        {
            "data_root": str(data_root),
            "mode": "child",
            "parent_mode": "bond_issuance",
            "parser_method": "bond_issuance",
            "input_directory": str(input_directory),
            "output_directory": str(tmp_path / "parsed"),
            "filtered_metadata_path": str(filtered_path),
            "compressed_metadata_path": str(compressed_path),
            "limit": 1,
            "skip_errors": False,
        }
    )

    assert request.mode == "child"
    assert request.parser_method == "bond_issuance"
    assert request.html_files == [child.resolve()]
    assert parent_only.resolve() not in request.html_files


def test_derived_preview_selects_child_membership_before_scan(tmp_path: Path) -> None:
    input_directory = tmp_path / "sections"
    year_directory = input_directory / "2025"
    year_directory.mkdir(parents=True)
    parent_only = year_directory / "20250101000001.html"
    child = year_directory / "20250101000002.html"
    parent_only.write_text(_valid_html("parent"), encoding="utf-8")
    child.write_text(_valid_html("child"), encoding="utf-8")
    data_root = tmp_path / "workspace"
    parent_disclosure = {
        "acpt_no": parent_only.stem,
        "disclosed_at": "2025-01-01 09:00",
    }
    child_disclosure = {
        "acpt_no": child.stem,
        "disclosed_at": "2025-01-02 09:00",
    }
    _write_derived_filter(
        data_root,
        parent_mode="bond_issuance",
        mode="child",
        parent_disclosures=[parent_disclosure, child_disclosure],
        child_disclosures=[child_disclosure],
    )
    body = {
        "data_root": str(data_root),
        "mode": "child",
        "parent_mode": "bond_issuance",
        "parser_method": "bond_issuance",
        "input_directory": str(input_directory),
        "filtered_metadata_path": str(
            data_root
            / "03-filter"
            / "bond_issuance"
            / "subfilters"
            / "child"
            / "filtered.json"
        ),
    }
    filtered_metadata_path, _compressed = _parse_metadata_paths(body)
    allowed_acpt_numbers = _derived_allowed_acpt_numbers(
        body,
        mode="child",
        filtered_metadata_path=filtered_metadata_path,
    )
    html_files = _collect_html_files(
        input_directory,
        allowed_acpt_numbers=allowed_acpt_numbers,
    )

    assert allowed_acpt_numbers == {child.stem}
    assert html_files == [child.resolve()]
    assert parent_only.resolve() not in html_files


def test_derived_external_html_rejects_corrupt_parent_file(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    disclosure = {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"}
    _write_derived_filter(
        data_root,
        parent_disclosures=[disclosure],
        child_disclosures=[disclosure],
    )
    parent_output = data_root / "04-external-html-download" / "parent"
    target = parent_output / "2025" / "20250101000001.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_valid_html(), encoding="utf-8")
    create_external_html_integrity_baseline_payload(
        {
            "data_root": str(data_root),
            "mode": "parent",
            "output_directory": str(parent_output),
            "trust_existing_files": True,
        }
    )
    target.write_text(_valid_html("changed"), encoding="utf-8")

    inspect_body = {
        "data_root": str(data_root),
        "mode": "child",
        "parent_mode": "parent",
        "output_directory": str(parent_output),
    }
    checked = check_disclosure_html_output_directory_payload(inspect_body)
    assert checked["hash_mismatch_target_html_count"] == 1
    assert checked["missing_target_html_count"] == 0
    assert checked["deletion_candidate_count"] == 0

    with pytest.raises(ValueError, match="cannot be reused"):
        download_disclosure_external_html_payload(inspect_body)


def test_derived_internal_html_strictly_reuses_parent_without_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "workspace"
    parent_disclosures = [
        {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"},
        {"acpt_no": "20250101000002", "disclosed_at": "2025-01-02"},
    ]
    _write_derived_filter(
        data_root,
        parent_disclosures=parent_disclosures,
        child_disclosures=[parent_disclosures[1]],
    )
    compressed_path = (
        data_root
        / "04-external-html-compress"
        / "parent"
        / "compressed-external-html.json"
    )
    compressed_path.parent.mkdir(parents=True, exist_ok=True)
    compressed_payload = {
        "format": "finiq_disclosure_external_html_docs_v1",
        "records": [
            {
                "acpt_no": disclosure["acpt_no"],
                **_selected_main_doc(f"doc-{index}"),
                "metadata": {"disclosed_at": disclosure["disclosed_at"]},
            }
            for index, disclosure in enumerate(parent_disclosures)
        ],
    }
    compressed_path.write_text(json.dumps(compressed_payload), encoding="utf-8")
    parent_output = data_root / "05-internal-html-download" / "parent"
    for disclosure in parent_disclosures:
        target = parent_output / "2025" / f"{disclosure['acpt_no']}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_valid_html(disclosure["acpt_no"]), encoding="utf-8")
    create_internal_html_integrity_baseline_payload(
        {
            "source_compressed_json_path": str(compressed_path),
            "output_directory": str(parent_output),
            "trust_existing_files": True,
        }
    )
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        lambda **_kwargs: pytest.fail("derived internal HTML must not download"),
    )

    compressed_payload["records"][1]["selected_main_doc_no"] = ""
    compressed_path.write_text(json.dumps(compressed_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="selected main docNo"):
        download_disclosure_internal_html_payload(
            {
                "data_root": str(data_root),
                "mode": "child",
                "parent_mode": "parent",
                "source_compressed_json_path": str(compressed_path),
                "output_directory": str(parent_output),
            }
        )
    compressed_payload["records"][1]["selected_main_doc_no"] = "doc-1"
    compressed_path.write_text(json.dumps(compressed_payload), encoding="utf-8")

    result = download_disclosure_internal_html_payload(
        {
            "data_root": str(data_root),
            "mode": "child",
            "parent_mode": "parent",
            "source_compressed_json_path": str(compressed_path),
            "output_directory": str(parent_output),
        }
    )

    assert result["reused_parent_html"] is True
    assert result["network_fetch_count"] == 0
    assert result["acpt_numbers"] == ["20250101000002"]
    assert not (data_root / "05-internal-html-download" / "child").exists()


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
            path = Path(kwargs["target_output_directories"][acpt_no]) / f"{acpt_no}.html"
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


def test_external_html_invalid_response_preserves_previous_file_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_directory = tmp_path / "external"
    target = output_directory / "2025" / "20250101000001.html"
    target.parent.mkdir(parents=True)
    previous = _valid_html("previous").encode()
    target.write_bytes(previous)
    body = _external_workspace_body(
        tmp_path,
        {
            "disclosures": [
                {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"}
            ]
        },
        output_directory=str(output_directory),
    )
    baseline = create_external_html_integrity_baseline_payload(
        {**body, "trust_existing_files": True}
    )
    manifest_path = Path(str(baseline["manifest_path"]))
    previous_manifest = manifest_path.read_bytes()

    response = requests.Response()
    response.status_code = 200
    response._content = b"not html"
    response.url = "https://kind.invalid"
    monkeypatch.setattr(
        "finiq.data_scraper.core.client._request_disclosure_viewer_page",
        lambda *_args, **_kwargs: response,
    )

    with pytest.raises(ValueError, match="membership.*missing"):
        download_disclosure_external_html_payload(
            {**body, "skip_existing": False, "max_retries": 0}
        )

    assert target.read_bytes() == previous
    assert manifest_path.read_bytes() == previous_manifest


def test_external_html_baseline_survives_filtered_json_rerun(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "external"
    target = output_directory / "2025" / "20250101000001.html"
    target.parent.mkdir(parents=True)
    target.write_text(_valid_html(), encoding="utf-8")
    saved = {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"}
    create_external_html_integrity_baseline_payload(
        {
            **_external_workspace_body(
                tmp_path,
                {"disclosures": [saved]},
                output_directory=str(output_directory),
            ),
            "trust_existing_files": True,
        }
    )

    # Re-running the filter adds a target and rewrites unrelated summary fields.
    rerun_body = _external_workspace_body(
        tmp_path,
        {
            "summary": {"total": 2},
            "disclosures": [
                saved,
                {"acpt_no": "20250201000002", "disclosed_at": "2025-02-01"},
            ],
        },
        output_directory=str(output_directory),
    )
    inspection = check_disclosure_html_output_directory_payload(rerun_body)

    assert inspection["hash_unverified_target_html_count"] == 0
    assert inspection["hash_verified_target_html_count"] == 1
    assert inspection["missing_target_html_count"] == 1


def test_external_html_legacy_v1_manifest_still_verifies(tmp_path: Path) -> None:
    output_directory = tmp_path / "external"
    target = output_directory / "2025" / "20250101000001.html"
    target.parent.mkdir(parents=True)
    content = _valid_html().encode("utf-8")
    target.write_bytes(content)
    source_json = {
        "format": "kind_disclosure_filter_v1",
        "disclosures": [{"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"}],
    }
    body = _external_workspace_body(
        tmp_path,
        {"disclosures": source_json["disclosures"]},
        output_directory=str(output_directory),
    )
    (output_directory / "kind_disclosure_html_manifest.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "source_fingerprint": _source_json_fingerprint(source_json),
                "disclosures": [
                    {
                        "acpt_no": "20250101000001",
                        "disclosed_at": "2025-01-01",
                        "source_sha256": hashlib.sha256(content).hexdigest(),
                        "source_size_bytes": len(content),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    inspection = check_disclosure_html_output_directory_payload(body)

    assert inspection["hash_verified_target_html_count"] == 1
    assert inspection["hash_unverified_target_html_count"] == 0


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


def test_external_html_repair_redownloads_existing_file_without_hash_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_directory = tmp_path / "external"
    target = output_directory / "2025" / "20250101000001.html"
    target.parent.mkdir(parents=True)
    target.write_text(_valid_html("unverified"), encoding="utf-8")
    calls: list[list[str]] = []

    def fake_download(**kwargs: object) -> list[Path]:
        acpt_numbers = list(kwargs["acpt_numbers"])
        calls.append(acpt_numbers)
        target.write_text(_valid_html("redownloaded"), encoding="utf-8")
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
                    {
                        "acpt_no": "20250101000001",
                        "disclosed_at": "2025-01-01",
                    }
                ]
            },
            output_directory=str(output_directory),
            skip_existing=True,
        ),
        redownload_unverified_existing=True,
    )

    assert calls == [["20250101000001"]]
    assert result["saved_count"] == 1
    inspection = check_disclosure_html_output_directory_payload(
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
        )
    )
    assert inspection["hash_verified_target_html_count"] == 1
    assert inspection["hash_unverified_target_html_count"] == 0


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


def test_internal_html_integrity_baseline_rejects_changed_selected_document(
    tmp_path: Path,
) -> None:
    acpt_no = "20250101000001"
    body = _internal_html_body(tmp_path, [acpt_no])
    output_directory = Path(str(body["output_directory"]))
    target = output_directory / "2025" / f"{acpt_no}.html"
    target.parent.mkdir(parents=True)
    target.write_text(_valid_html("old document"), encoding="utf-8")
    baseline = create_internal_html_integrity_baseline_payload(
        {**body, "trust_existing_files": True}
    )
    manifest_path = Path(str(baseline["manifest_path"]))
    previous_manifest = manifest_path.read_bytes()

    source_path = Path(str(body["source_compressed_json_path"]))
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["records"][0].update(_selected_main_doc("changed-doc"))
    source_path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(ValueError, match="selected_main_doc_no.*changed"):
        create_internal_html_integrity_baseline_payload(
            {**body, "trust_existing_files": True}
        )

    assert manifest_path.read_bytes() == previous_manifest


def test_internal_html_integrity_baseline_rejects_placeholder_without_provenance(
    tmp_path: Path,
) -> None:
    acpt_no = "20250101000001"
    doc_no = f"{acpt_no}99"
    body = _internal_html_body(tmp_path, [acpt_no])
    output_directory = Path(str(body["output_directory"]))
    target = output_directory / "2025" / f"{acpt_no}.html"
    target.parent.mkdir(parents=True)
    target.write_bytes(
        _render_internal_html_source_unavailable_marker(
            acpt_no=acpt_no,
            doc_no=doc_no,
            reason="content_path_missing",
        )
    )

    with pytest.raises(ValueError, match="source-unavailable.*provenance"):
        create_internal_html_integrity_baseline_payload(
            {**body, "trust_existing_files": True}
        )

    assert not (output_directory / "kind_disclosure_html_manifest.json").exists()


def test_internal_html_integrity_baseline_rejects_stale_placeholder_document(
    tmp_path: Path,
) -> None:
    acpt_no = "20250101000001"
    body = _internal_html_body(tmp_path, [acpt_no])
    output_directory = Path(str(body["output_directory"]))
    target = output_directory / "2025" / f"{acpt_no}.html"
    target.parent.mkdir(parents=True)
    target.write_bytes(
        _render_internal_html_source_unavailable_marker(
            acpt_no=acpt_no,
            doc_no="stale-doc",
            reason="content_path_missing",
        )
    )

    with pytest.raises(ValueError, match="placeholder doc_no does not match"):
        create_internal_html_integrity_baseline_payload(
            {**body, "trust_existing_files": True}
        )


@pytest.mark.parametrize(
    ("damage", "expected_error"),
    [
        ("missing_selected", "selected main docNo not found"),
        ("multiple_selected", "exactly one selected mainDoc"),
        ("mismatched_selected", "selected_main_doc_no does not match"),
    ],
)
def test_internal_html_inspection_enforces_selected_document_contract(
    tmp_path: Path,
    damage: str,
    expected_error: str,
) -> None:
    body = _internal_html_body(tmp_path, ["20250101000001"])
    source_path = Path(str(body["source_compressed_json_path"]))
    source = json.loads(source_path.read_text(encoding="utf-8"))
    record = source["records"][0]
    if damage == "missing_selected":
        record.pop("selected_main_doc_no")
    elif damage == "multiple_selected":
        record["docs"].append(
            {
                "select_id": "mainDoc",
                "doc_no": "another-doc",
                "selected": True,
            }
        )
    else:
        record["selected_main_doc_no"] = "mismatched-doc"
    source_path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(ValueError, match=expected_error):
        check_disclosure_html_output_directory_payload(body)


def test_internal_html_repair_redownloads_existing_file_without_hash_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _internal_html_body(tmp_path, ["20250101000001"])
    output_directory = Path(str(body["output_directory"]))
    target = output_directory / "2025" / "20250101000001.html"
    target.parent.mkdir(parents=True)
    target.write_text(_valid_html("unverified"), encoding="utf-8")
    calls: list[list[str]] = []

    def fake_download(**kwargs: object) -> list[Path]:
        targets = list(kwargs["targets"])
        calls.append([item["acpt_no"] for item in targets])
        target.write_text(_valid_html("redownloaded"), encoding="utf-8")
        return [target]

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        fake_download,
    )

    result = download_disclosure_internal_html_payload(
        {**body, "skip_existing": True},
        redownload_unverified_existing=True,
    )

    assert calls == [["20250101000001"]]
    assert result["saved_count"] == 1
    inspection = check_disclosure_html_output_directory_payload(body)
    assert inspection["hash_verified_target_html_count"] == 1
    assert inspection["hash_unverified_target_html_count"] == 0


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
            path = Path(
                kwargs["target_output_directories"][target["acpt_no"]]
            ) / f"{target['acpt_no']}.html"
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


def test_internal_html_inspection_rejects_legacy_invalid_html_placeholder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acpt_no = "20250101000001"
    doc_no = f"{acpt_no}99"
    body = _internal_html_body(tmp_path, [acpt_no])
    output_directory = Path(str(body["output_directory"]))
    target = output_directory / "2025" / f"{acpt_no}.html"
    target.parent.mkdir(parents=True)
    target.write_text(_valid_html(), encoding="utf-8")
    baseline = create_internal_html_integrity_baseline_payload(
        {**body, "trust_existing_files": True}
    )

    legacy_placeholder = _render_internal_html_source_unavailable_marker(
        acpt_no=acpt_no,
        doc_no=doc_no,
        reason="invalid_html",
    )
    target.write_bytes(legacy_placeholder)
    manifest_path = Path(str(baseline["manifest_path"]))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["disclosures"][0].update(
        {
            "source_sha256": hashlib.sha256(legacy_placeholder).hexdigest(),
            "source_size_bytes": len(legacy_placeholder),
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    inspection = check_disclosure_html_output_directory_payload(body)

    assert inspection["invalid_target_acpt_numbers"] == [acpt_no]
    assert inspection["download_required_target_html_count"] == 1
    assert inspection["hash_mismatch_target_html_count"] == 0

    replacement = _valid_html("replacement").encode()
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._fetch_internal_html",
        lambda *_args, **_kwargs: replacement,
    )
    result = download_disclosure_internal_html_payload(
        {**body, "max_requests_per_minute": 100}
    )

    assert target.read_bytes() == replacement
    assert result["source_unavailable_count"] == 0

    target.write_bytes(legacy_placeholder)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["disclosures"][0].update(
        {
            "source_sha256": hashlib.sha256(legacy_placeholder).hexdigest(),
            "source_size_bytes": len(legacy_placeholder),
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def empty_body(*_args: object, **_kwargs: object) -> bytes:
        from finiq.market_desk.web.features.disclosures import internal_html_download

        raise internal_html_download._EmptyBodyError("empty body")

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._fetch_internal_html",
        empty_body,
    )
    empty_result = download_disclosure_internal_html_payload(
        {**body, "max_requests_per_minute": 100}
    )

    saved_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert empty_result["source_unavailable_count"] == 1
    assert saved_manifest["disclosures"][0]["source_unavailable"] == {
        "doc_no": doc_no,
        "reason": "empty_body",
    }


@pytest.mark.parametrize("source_type", ["external", "internal"])
def test_existing_html_structure_and_hash_share_one_file_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_type: str,
) -> None:
    acpt_no = "20250101000001"
    if source_type == "external":
        output_directory = tmp_path / "external"
        body = _external_workspace_body(
            tmp_path,
            {
                "disclosures": [
                    {"acpt_no": acpt_no, "disclosed_at": "2025-01-01"}
                ]
            },
            output_directory=str(output_directory),
        )
        create_baseline = create_external_html_integrity_baseline_payload
    else:
        body = _internal_html_body(tmp_path, [acpt_no])
        output_directory = Path(str(body["output_directory"]))
        create_baseline = create_internal_html_integrity_baseline_payload

    target = output_directory / "2025" / f"{acpt_no}.html"
    target.parent.mkdir(parents=True)
    target.write_text(_valid_html(), encoding="utf-8")
    create_baseline({**body, "trust_existing_files": True})

    original_open = Path.open
    target_reads = 0

    def counted_open(path: Path, *args: object, **kwargs: object):
        nonlocal target_reads
        mode = str(args[0]) if args else str(kwargs.get("mode") or "r")
        if path == target and "r" in mode:
            target_reads += 1
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counted_open)

    inspection = check_disclosure_html_output_directory_payload(body)

    assert inspection["hash_verified_target_html_count"] == 1
    assert target_reads == 1


@pytest.mark.parametrize("source_type", ["external", "internal"])
def test_html_integrity_baseline_progress_reports_only_valid_targets(
    tmp_path: Path,
    source_type: str,
) -> None:
    acpt_numbers = ["20250101000001", "20250101000002"]
    if source_type == "external":
        output_directory = tmp_path / "external"
        body = _external_workspace_body(
            tmp_path,
            {
                "disclosures": [
                    {"acpt_no": acpt_no, "disclosed_at": "2025-01-01"}
                    for acpt_no in acpt_numbers
                ]
            },
            output_directory=str(output_directory),
        )
        create_baseline = create_external_html_integrity_baseline_payload
        target_label = "외부"
    else:
        body = _internal_html_body(tmp_path, acpt_numbers)
        output_directory = Path(str(body["output_directory"]))
        create_baseline = create_internal_html_integrity_baseline_payload
        target_label = "내부"

    target = output_directory / "2025" / f"{acpt_numbers[0]}.html"
    target.parent.mkdir(parents=True)
    target.write_text(_valid_html(), encoding="utf-8")
    progress: list[str] = []

    result = create_baseline(
        {**body, "trust_existing_files": True},
        progress_callback=progress.append,
    )

    assert result["hashed_count"] == 1
    assert (
        f"현재 {target_label} HTML 1건의 기준 해시를 생성합니다." in progress
    )
    assert not any("HTML 2건의 기준 해시를 생성합니다." in line for line in progress)


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


def test_internal_html_invalid_response_preserves_previous_file_and_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _internal_html_body(tmp_path, ["20250101000001"])
    output_directory = Path(str(body["output_directory"]))
    target = output_directory / "2025" / "20250101000001.html"
    target.parent.mkdir(parents=True)
    previous = _valid_html("previous").encode()
    target.write_bytes(previous)
    baseline = create_internal_html_integrity_baseline_payload(
        {**body, "trust_existing_files": True}
    )
    manifest_path = Path(str(baseline["manifest_path"]))
    previous_manifest = manifest_path.read_bytes()
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._fetch_internal_html",
        lambda *_args, **_kwargs: b"not html",
    )

    with pytest.raises(ValueError, match="Downloaded internal response is invalid HTML"):
        download_disclosure_internal_html_payload(
            {**body, "skip_existing": False}
        )

    assert target.read_bytes() == previous
    assert manifest_path.read_bytes() == previous_manifest


def test_internal_html_revalidation_rejects_invalid_response_without_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = _internal_html_body(tmp_path, ["20250101000001"])
    output_directory = Path(str(body["output_directory"]))
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._fetch_internal_html",
        lambda *_args, **_kwargs: b"not html",
    )

    with pytest.raises(ValueError, match="Downloaded internal response is invalid HTML"):
        download_disclosure_internal_html_payload(
            {**body, "skip_existing": False},
            redownload_unverified_existing=True,
        )

    assert not (output_directory / "2025" / "20250101000001.html").exists()
    assert not (output_directory / "kind_disclosure_html_manifest.json").exists()


def test_internal_html_revalidation_uses_explicit_direct_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from finiq.market_desk.web.features.disclosures import internal_html_download

    body = _internal_html_body(tmp_path, ["20250101000001"])
    monkeypatch.setattr(
        internal_html_download,
        "download_disclosure_internal_htmls",
        lambda **_kwargs: [],
    )

    observed_trust_env: list[bool] = []

    def assert_direct_session(session: requests.Session, **_kwargs: object) -> bytes:
        observed_trust_env.append(session.trust_env)
        raise internal_html_download._EmptyBodyError("empty body")

    monkeypatch.setattr(
        internal_html_download,
        "_fetch_internal_html",
        assert_direct_session,
    )
    monkeypatch.setattr(
        internal_html_download,
        "wait_for_html_download_request_slot",
        lambda *_args, **_kwargs: False,
    )

    result = download_disclosure_internal_html_payload(body)

    assert result["source_unavailable_count"] == 1
    assert observed_trust_env == [False]


def test_internal_html_download_accepts_legacy_html_fragment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._fetch_internal_html",
        lambda *args, **kwargs: (
            b'<P class="section-1">Legacy disclosure</P>'
            b"<TABLE><TR><TD>content</TD></TR></TABLE>"
        ),
    )

    saved = download_disclosure_internal_htmls(
        output_directory=tmp_path,
        request_headers={},
        targets=[{"acpt_no": "19970415M00003", "doc_no": "19970415M00003"}],
        max_requests_per_minute=100,
    )

    assert [path.name for path in saved] == ["19970415M00003.html"]


def test_internal_html_download_accepts_kind_table_fragment_with_broken_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._fetch_internal_html",
        lambda *args, **kwargs: (
            b"IGHT'>&gt;2016"
            b'<TABLE class="TABLE"><TR><TD class="TD">content</TD></TR></TABLE>'
        ),
    )

    saved = download_disclosure_internal_htmls(
        output_directory=tmp_path,
        request_headers={},
        targets=[{"acpt_no": "20160330002146", "doc_no": "20160330007821"}],
        max_requests_per_minute=100,
    )

    assert [path.name for path in saved] == ["20160330002146.html"]


def test_internal_html_integrity_baseline_accepts_legacy_html_fragment(
    tmp_path: Path,
) -> None:
    acpt_no = "19970415M00003"
    body = _internal_html_body(tmp_path, [acpt_no])
    output_directory = Path(str(body["output_directory"]))
    target = output_directory / "2025" / f"{acpt_no}.html"
    target.parent.mkdir(parents=True)
    target.write_bytes(
        b'<P class="section-1">Legacy disclosure</P>'
        b"<TABLE><TR><TD>content</TD></TR></TABLE>"
    )

    result = create_internal_html_integrity_baseline_payload(
        {**body, "trust_existing_files": True}
    )

    assert result["hashed_count"] == 1
    inspection = check_disclosure_html_output_directory_payload(body)
    assert inspection["hash_verified_target_html_count"] == 1
    assert inspection["invalid_target_html_count"] == 0


def test_internal_html_integrity_accepts_kind_table_fragment_with_broken_prefix(
    tmp_path: Path,
) -> None:
    acpt_no = "20160330002146"
    body = _internal_html_body(tmp_path, [acpt_no])
    output_directory = Path(str(body["output_directory"]))
    target = output_directory / "2025" / f"{acpt_no}.html"
    target.parent.mkdir(parents=True)
    target.write_bytes(
        b"IGHT'>&gt;2016"
        b'<TABLE class="TABLE"><TR><TD class="TD">content</TD></TR></TABLE>'
    )

    result = create_internal_html_integrity_baseline_payload(
        {**body, "trust_existing_files": True}
    )

    assert result["hashed_count"] == 1
    inspection = check_disclosure_html_output_directory_payload(body)
    assert inspection["hash_verified_target_html_count"] == 1
    assert inspection["invalid_target_html_count"] == 0


def test_internal_html_download_retries_transient_proxy_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = 0

    def fake_fetch(*args: object, **kwargs: object) -> bytes:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise requests.exceptions.ProxyError("temporary proxy failure")
        return _valid_html().encode("utf-8")

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._fetch_internal_html",
        fake_fetch,
    )

    saved = download_disclosure_internal_htmls(
        output_directory=tmp_path,
        request_headers={},
        targets=[{"acpt_no": "20250101000001", "doc_no": "1"}],
        max_requests_per_minute=100,
        max_retries=1,
    )

    assert attempts == 2
    assert [path.name for path in saved] == ["20250101000001.html"]


def test_internal_html_failure_does_not_stop_following_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_fetch(*args: object, **kwargs: object) -> bytes:
        if kwargs["acpt_no"] == "20250101000001":
            raise requests.exceptions.ProxyError("persistent proxy failure")
        return _valid_html().encode("utf-8")

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._fetch_internal_html",
        fake_fetch,
    )

    with pytest.raises(requests.exceptions.ProxyError):
        download_disclosure_internal_htmls(
            output_directory=tmp_path,
            request_headers={},
            targets=[
                {"acpt_no": "20250101000001", "doc_no": "1"},
                {"acpt_no": "20250101000002", "doc_no": "2"},
            ],
            max_requests_per_minute=100,
            max_retries=0,
            max_workers=1,
        )

    assert (tmp_path / "20250101000002.html").is_file()


def test_internal_html_download_runs_targets_in_parallel_and_preserves_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    barrier = threading.Barrier(2)

    def fake_fetch(*_args: object, **_kwargs: object) -> bytes:
        barrier.wait(timeout=2)
        return _valid_html().encode("utf-8")

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._fetch_internal_html",
        fake_fetch,
    )
    targets = [
        {"acpt_no": "20250101000002", "doc_no": "2"},
        {"acpt_no": "20250101000001", "doc_no": "1"},
    ]

    saved = download_disclosure_internal_htmls(
        output_directory=tmp_path,
        request_headers={},
        targets=targets,
        max_requests_per_minute=100,
        max_workers=2,
    )

    assert [path.stem for path in saved] == [
        "20250101000002",
        "20250101000001",
    ]


def test_external_html_payload_passes_configured_kind_proxies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_download(**kwargs: object) -> list[Path]:
        captured.update(kwargs)
        paths = []
        for acpt_no in list(kwargs["acpt_numbers"]):
            path = Path(
                kwargs["target_output_directories"][acpt_no]
            ) / f"{acpt_no}.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_valid_html(), encoding="utf-8")
            paths.append(path)
        return paths

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls",
        fake_download,
    )
    download_disclosure_external_html_payload(
        _external_workspace_body(
            tmp_path,
            {
                "disclosures": [
                    {"acpt_no": "20250101000001", "disclosed_at": "2025-01-01"},
                    {"acpt_no": "20250101000002", "disclosed_at": "2025-01-02"},
                ]
            },
            output_directory=str(tmp_path / "external"),
            skip_existing=False,
            kind_proxy_urls=["http://127.0.0.1:25001"],
        )
    )

    assert captured["kind_proxy_urls"] == ["http://127.0.0.1:25001"]


def test_external_html_download_rejects_changed_filtered_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = _external_workspace_body(
        tmp_path,
        {
            "disclosures": [
                {
                    "acpt_no": "20250101000001",
                    "disclosed_at": "2025-01-01",
                }
            ]
        },
        output_directory=str(tmp_path / "external"),
    )
    filtered_path = (
        Path(str(body["data_root"]))
        / "03-filter"
        / "bond_issuance"
        / "filtered.json"
    )
    filtered = json.loads(filtered_path.read_text(encoding="utf-8"))
    filtered["disclosures"][0]["title"] = "봉인 뒤에 추가된 제목"
    filtered_path.write_text(json.dumps(filtered), encoding="utf-8")
    download_called = False

    def fake_download(**_kwargs: object) -> list[Path]:
        nonlocal download_called
        download_called = True
        return []

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.external_html_download.download_disclosure_external_htmls",
        fake_download,
    )

    with pytest.raises(ValueError, match="result fingerprint does not match"):
        download_disclosure_external_html_payload(body)

    assert download_called is False


def test_internal_html_payload_passes_configured_kind_proxies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_download(**kwargs: object) -> list[Path]:
        captured.update(kwargs)
        paths = []
        for target in list(kwargs["targets"]):
            path = Path(
                kwargs["target_output_directories"][target["acpt_no"]]
            ) / f"{target['acpt_no']}.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_valid_html(), encoding="utf-8")
            paths.append(path)
        return paths

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        fake_download,
    )
    download_disclosure_internal_html_payload(
        _internal_html_body(
            tmp_path,
            ["20250101000001", "20250101000002"],
            skip_existing=False,
            kind_proxy_urls=["http://127.0.0.1:25001"],
        )
    )

    assert captured["kind_proxy_urls"] == ["http://127.0.0.1:25001"]


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


def test_internal_html_download_cancellation_writes_partial_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compressed_path = tmp_path / "compressed-external-html.json"
    compressed_path.write_text(
        json.dumps({
            "format": "finiq_disclosure_external_html_docs_v1",
            "records": [{
                "acpt_no": "20250101000001",
                **_selected_main_doc("1"),
                "metadata": {"disclosed_at": "2025-01-01"},
            }],
        }),
        encoding="utf-8",
    )

    def fake_download(**kwargs: object) -> list[Path]:
        target = list(kwargs["targets"])[0]
        path = Path(
            kwargs["target_output_directories"][target["acpt_no"]]
        ) / f"{target['acpt_no']}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_valid_html(), encoding="utf-8")
        return [path]

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        fake_download,
    )

    result = download_disclosure_internal_html_payload(
        {
            "output_directory": str(tmp_path / "content"),
            "source_compressed_json_path": str(compressed_path),
        },
        cancel_check=lambda: True,
    )

    assert result["cancelled"] is True
    manifest_path = Path(result["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [item["acpt_no"] for item in manifest["disclosures"]] == [
        "20250101000001"
    ]
    assert manifest["disclosures"][0]["source_sha256"]

    inspection = check_disclosure_html_output_directory_payload(
        {
            "output_directory": str(tmp_path / "content"),
            "source_compressed_json_path": str(compressed_path),
        }
    )
    assert inspection["hash_verified_target_html_count"] == 1
    assert inspection["hash_unverified_target_html_count"] == 0


def test_internal_html_partial_failure_preserves_previous_manifest_before_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acpt_numbers = ["20250101000001", "20250101000002"]

    def fake_download(**kwargs: object) -> list[Path]:
        acpt_no = acpt_numbers[0]
        path = Path(kwargs["target_output_directories"][acpt_no]) / f"{acpt_no}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_valid_html(), encoding="utf-8")
        return [path]

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.download_disclosure_internal_htmls",
        fake_download,
    )

    def fail_revalidation(*_args: object, **_kwargs: object) -> bytes:
        raise OSError("network unavailable")

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download._fetch_internal_html",
        fail_revalidation,
    )
    body = _internal_html_body(
        tmp_path,
        acpt_numbers,
        skip_existing=False,
    )
    manifest_path = (
        Path(str(body["output_directory"]))
        / "kind_disclosure_html_manifest.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    previous_manifest = {
        "format": "finiq_disclosure_html_manifest_v2",
        "disclosures": [],
    }
    manifest_path.write_text(json.dumps(previous_manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="membership.*missing="):
        download_disclosure_internal_html_payload(body)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest == previous_manifest


def test_all_internal_html_inspection_passes_empty_owner_and_derived_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from finiq.market_desk.web.features.disclosures import html_cleanup

    data_root = tmp_path / "workspace"
    _write_derived_filter(
        data_root,
        parent_disclosures=[],
        child_disclosures=[],
    )
    monkeypatch.setattr(
        html_cleanup,
        "manage_filter_presets_payload",
        lambda _payload: {
            "presets": [
                {"id": "parent", "mode": "parent", "status": "completed"},
                {
                    "id": "parent/child",
                    "mode": "child",
                    "parent_mode": "parent",
                    "status": "completed",
                },
            ]
        },
    )

    result = html_cleanup.inspect_all_disclosure_internal_html_payload(
        {"data_root": str(data_root)}
    )

    assert result["passed"] is True
    assert result["failed_modes"] == []
    assert [item["passed"] for item in result["results"]] == [True, True]
    assert [item["empty_filter_result"] for item in result["results"]] == [True, True]


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
                    {
                        "acpt_no": "20250101000001",
                        "title": "KIND 제목",
                        "disclosed_at": "2025-01-01",
                    }
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
          <select id="attachedDoc">
            <option value="20250101000888">첨부</option>
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
