from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finiq.market_desk.web.app import app
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
    prepare_disclosure_workspace_payload,
    resolve_disclosure_workspace,
)
from finiq.market_desk.web.features.disclosures.table_export import (
    _manifest_output_path,
)


def test_prepare_disclosure_workspace_creates_stage_roots_and_modes(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"

    result = prepare_disclosure_workspace_payload(
        {"data_root": str(data_root), "modes": ["bond_issuance", "rights_issuance"]}
    )

    expected_directories = {
        "01-list",
        "02-table",
        "03-filter",
        "04-external",
        "05-internal",
        "06-sections",
        "07-converted",
        "07-converted/bond_issuance",
        "07-converted/rights_issuance",
    }
    assert {
        str(path.relative_to(data_root))
        for path in data_root.rglob("*")
        if path.is_dir()
    } == expected_directories
    manifest = json.loads(
        (data_root / "disclosure-workspace.json").read_text(encoding="utf-8")
    )
    assert manifest["format"] == "finiq_disclosure_workspace_v1"
    assert manifest["modes"] == ["bond_issuance", "rights_issuance"]
    assert result["paths"]["list"] == str(data_root / "01-list")
    assert result["paths"]["converted"]["bond_issuance"] == str(
        data_root / "07-converted" / "bond_issuance"
    )


def test_workspace_rejects_unsafe_mode_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="mode"):
        prepare_disclosure_workspace_payload(
            {"data_root": str(tmp_path / "workspace"), "modes": ["../escape"]}
        )


def test_workspace_defaults_cover_all_seven_stages(tmp_path: Path) -> None:
    workspace = resolve_disclosure_workspace(tmp_path / "workspace", create=True)

    assert apply_workspace_defaults("kind_download", {"data_root": str(workspace.root)})[
        "output_directory"
    ] == str(workspace.list)
    table = apply_workspace_defaults(
        "table_build", {"data_root": str(workspace.root)}
    )
    assert table["root_directory"] == str(workspace.list)
    assert table["output_path"] == str(workspace.table / "disclosures.sqlite_manifest.json")
    filtered = apply_workspace_defaults(
        "filter", {"data_root": str(workspace.root)}
    )
    assert filtered["classification_path"] == str(
        workspace.table
        / "disclosures.sqlite_manifest_shards"
        / "disclosures.sqlite_manifest.json"
    )
    assert str(_manifest_output_path(table["output_path"], workspace.list)) == filtered[
        "classification_path"
    ]
    assert filtered["html_transfer_path"] == str(workspace.filtered / "filtered.json")
    external = apply_workspace_defaults("download", {"data_root": str(workspace.root)})
    assert external["output_directory"] == str(workspace.external)
    assert external["output_split_by_year"] is True
    internal = apply_workspace_defaults(
        "content_download", {"data_root": str(workspace.root)}
    )
    assert internal["source_directory"] == str(workspace.external)
    assert internal["output_directory"] == str(workspace.internal)
    assert internal["output_split_by_year"] is True
    sections = apply_workspace_defaults(
        "section_save", {"data_root": str(workspace.root)}
    )
    assert sections["input_directory"] == str(workspace.internal)
    assert sections["output_directory"] == str(workspace.sections)
    converted = apply_workspace_defaults(
        "parse", {"data_root": str(workspace.root), "mode": "bond_issuance"}
    )
    assert converted["input_directory"] == str(workspace.sections)
    assert converted["output_directory"] == str(
        workspace.converted / "bond_issuance"
    )
    assert converted["filtered_metadata_path"] == str(
        workspace.filtered / "filtered.json"
    )
    assert converted["compressed_metadata_path"] == str(
        workspace.external / "compressed-external-html.json"
    )


def test_workspace_defaults_preserve_explicit_paths(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    payload = apply_workspace_defaults(
        "parse",
        {
            "data_root": str(tmp_path / "workspace"),
            "mode": "bond_issuance",
            "input_directory": str(explicit / "input"),
            "output_directory": str(explicit / "output"),
            "filtered_metadata_path": str(explicit / "filtered.json"),
            "compressed_metadata_path": str(explicit / "compressed.json"),
        },
    )

    assert payload["input_directory"] == str(explicit / "input")
    assert payload["output_directory"] == str(explicit / "output")
    assert payload["filtered_metadata_path"] == str(explicit / "filtered.json")
    assert payload["compressed_metadata_path"] == str(explicit / "compressed.json")


def test_workspace_prepare_api(tmp_path: Path) -> None:
    client = TestClient(app)

    response = client.post(
        "/api/disclosures/workspace/prepare",
        json={"data_root": str(tmp_path / "workspace"), "modes": ["bond_issuance"]},
    )

    assert response.status_code == 200
    assert response.json()["format"] == "finiq_disclosure_workspace_v1"
    assert Path(response.json()["paths"]["internal"]).name == "05-internal"
