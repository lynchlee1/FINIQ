from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import finiq.config as finiq_config
import finiq.market_desk.web.app as web_app
from finiq.market_desk.web.app import app
from finiq.market_desk.web.app import config as app_config
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
    disclosure_workspace_settings,
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
    assert table["output_path"] == str(workspace.table)
    filtered = apply_workspace_defaults(
        "filter", {"data_root": str(workspace.root), "mode": "bond_issuance"}
    )
    assert "classification_path" not in filtered
    assert (
        _manifest_output_path(table["output_path"], workspace.list).parent
        == workspace.table
    )
    assert filtered["html_transfer_path"] == str(workspace.filtered)
    external = apply_workspace_defaults("download", {"data_root": str(workspace.root)})
    assert external["output_directory"] == str(workspace.external)
    internal = apply_workspace_defaults(
        "content_download", {"data_root": str(workspace.root)}
    )
    assert internal["source_directory"] == str(workspace.external)
    assert internal["output_directory"] == str(workspace.internal)
    sections = apply_workspace_defaults(
        "section_save", {"data_root": str(workspace.root)}
    )
    assert sections["input_directory"] == str(workspace.internal)
    assert sections["output_directory"] == str(workspace.sections)
    converted = apply_workspace_defaults(
        "parse", {"data_root": str(workspace.root), "mode": "bond_issuance"}
    )
    assert "skip_errors" not in converted
    assert converted["input_directory"] == str(workspace.sections)
    assert converted["output_directory"] == str(
        workspace.converted / "bond_issuance"
    )
    assert converted["filtered_metadata_path"] == str(
        workspace.filtered / "bond_issuance" / "filtered.json"
    )
    assert converted["compressed_metadata_path"] == str(
        workspace.external / "compressed-external-html.json"
    )


def test_workspace_defaults_preserve_explicit_stage_paths(tmp_path: Path) -> None:
    workspace = resolve_disclosure_workspace(tmp_path / "workspace")
    explicit = tmp_path / "explicit"
    payload = apply_workspace_defaults(
        "parse",
        {
            "data_root": str(workspace.root),
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

    filtered = apply_workspace_defaults(
        "filter",
        {
            "data_root": str(workspace.root),
            "mode": "bond_issuance",
            "classification_path": str(explicit / "table"),
            "html_transfer_path": str(explicit / "filter-results"),
        },
    )
    assert filtered["classification_path"] == str(explicit / "table")
    assert filtered["html_transfer_path"] == str(explicit / "filter-results")

    downloaded = apply_workspace_defaults(
        "kind_download",
        {
            "data_root": str(workspace.root),
            "output_directory": str(explicit / "list"),
        },
    )
    assert downloaded["output_directory"] == str(workspace.list)

    separate_download = apply_workspace_defaults(
        "kind_download",
        {
            "data_root": str(workspace.root),
            "separate_output_directory": True,
            "output_directory": str(explicit / "list"),
        },
    )
    assert separate_download["output_directory"] == str(explicit / "list")

    table = apply_workspace_defaults(
        "table_build",
        {
            "data_root": str(workspace.root),
            "classification_path": str(explicit / "classification.json"),
            "root_directory": str(explicit / "list"),
            "output_path": str(explicit / "table"),
        },
    )
    assert table["classification_path"] == str(explicit / "classification.json")
    assert table["root_directory"] == str(explicit / "list")
    assert table["output_path"] == str(explicit / "table")

    external = apply_workspace_defaults(
        "download",
        {
            "data_root": str(workspace.root),
            "json": {"disclosures": []},
            "payload": {"disclosures": []},
            "source_json_path": str(explicit / "filtered.json"),
            "output_directory": str(explicit / "external"),
        },
    )
    assert "json" not in external
    assert "payload" not in external
    assert "source_json_path" not in external
    assert external["output_directory"] == str(explicit / "external")

    compressed = apply_workspace_defaults(
        "external_compress",
        {
            "data_root": str(workspace.root),
            "input_directory": str(explicit / "external"),
            "output_directory": str(explicit / "compressed"),
        },
    )
    assert compressed["input_directory"] == str(explicit / "external")
    assert compressed["output_directory"] == str(explicit / "compressed")

    internal = apply_workspace_defaults(
        "content_download",
        {
            "data_root": str(workspace.root),
            "source_compressed_json_path": str(explicit / "compressed.json"),
            "output_directory": str(explicit / "internal"),
        },
    )
    assert "source_directory" not in internal
    assert internal["source_compressed_json_path"] == str(explicit / "compressed.json")
    assert internal["output_directory"] == str(explicit / "internal")

    sections = apply_workspace_defaults(
        "section_save",
        {
            "data_root": str(workspace.root),
            "input_directory": str(explicit / "internal"),
            "output_directory": str(explicit / "sections"),
        },
    )
    assert sections["input_directory"] == str(explicit / "internal")
    assert sections["output_directory"] == str(explicit / "sections")


def test_workspace_prepare_api(tmp_path: Path) -> None:
    client = TestClient(app)

    response = client.post(
        "/api/disclosures/workspace/prepare",
        json={"data_root": str(tmp_path / "workspace"), "modes": ["bond_issuance"]},
    )

    assert response.status_code == 200
    assert response.json()["format"] == "finiq_disclosure_workspace_v1"
    assert Path(response.json()["paths"]["internal"]).name == "05-internal"


def test_workspace_prepare_preserves_existing_modes(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    prepare_disclosure_workspace_payload(
        {"data_root": str(data_root), "modes": ["bond_issuance"]}
    )

    result = prepare_disclosure_workspace_payload(
        {"data_root": str(data_root), "modes": ["rights_issuance"]}
    )

    assert result["modes"] == ["bond_issuance", "rights_issuance"]
    assert set(result["paths"]["converted"]) == {
        "bond_issuance",
        "rights_issuance",
    }


def test_workspace_prepare_does_not_overwrite_unowned_manifest(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    data_root.mkdir()
    manifest_path = data_root / "disclosure-workspace.json"
    original = {"format": "unrelated", "records": [1]}
    manifest_path.write_text(json.dumps(original), encoding="utf-8")

    with pytest.raises(ValueError, match="not a FINIQ disclosure workspace"):
        prepare_disclosure_workspace_payload(
            {"data_root": str(data_root), "modes": ["bond_issuance"]}
        )

    assert json.loads(manifest_path.read_text(encoding="utf-8")) == original


def test_existing_filter_route_uses_workspace_stage_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "resources"
    captured: dict[str, object] = {}

    def fake_filter(payload: dict[str, object], **_kwargs: object) -> dict[str, object]:
        captured.update(payload)
        return {
            "format": "kind_disclosure_filter_v1",
            "disclosures": [],
            "html_download_acpt_numbers": [],
        }

    monkeypatch.setattr(web_app, "filter_disclosures_payload", fake_filter)

    response = TestClient(app).post(
        "/api/disclosures/filter",
        json={"data_root": str(data_root), "mode": "bond_issuance"},
    )

    assert response.status_code == 200
    assert captured["data_root"] == str(data_root)
    assert captured["mode"] == "bond_issuance"
    assert "classification_path" not in captured
    assert captured["html_transfer_path"] == str(data_root / "03-filter")
    assert (
        data_root / "03-filter" / "bond_issuance" / "filtered.json"
    ).is_file()


def test_workspace_settings_map_existing_workflows(tmp_path: Path) -> None:
    data_root = tmp_path / "resources"

    settings = disclosure_workspace_settings(data_root, mode="bond_issuance")

    assert settings == {
        "download_output_directory": str(data_root / "01-list"),
        "sqlite_source_path": str(data_root / "01-list"),
        "sqlite_output_directory": str(data_root / "02-table"),
        "sqlite_manifest_path": str(data_root / "02-table"),
        "html_transfer_directory": str(data_root / "03-filter"),
        "html_output_directory": str(data_root / "04-external"),
        "html_external_compress_input_directory": str(data_root / "04-external"),
        "html_external_compress_output_directory": str(data_root / "04-external"),
        "html_content_compressed_json_path": str(
            data_root / "04-external" / "compressed-external-html.json"
        ),
        "html_content_output_directory": str(data_root / "05-internal"),
        "html_merge_output_path": str(data_root / "05-internal" / "merged"),
        "html_section_split_output_directory": str(data_root / "06-sections"),
        "html_parse_output_directory": str(
            data_root / "07-converted" / "bond_issuance"
        ),
        "html_parse_result_path": str(
            data_root
            / "07-converted"
            / "bond_issuance"
            / "parsed-bond_issuance.json"
        ),
    }


def test_init_config_uses_workspace_paths_when_only_root_is_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "resources"
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"output_root": str(data_root)}), encoding="utf-8"
    )
    monkeypatch.setattr(
        finiq_config, "get_default_settings_path", lambda: settings_path
    )

    loaded = finiq_config.init_config()

    expected = disclosure_workspace_settings(data_root, mode="bond_issuance")
    assert {key: getattr(loaded, key) for key in expected} == expected
    assert loaded.disclosure_separate_output_directory is False
    assert loaded.job_retention_minutes == 60


def test_separate_output_directory_setting_is_shared_and_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_path = tmp_path / "settings.json"
    data_root = tmp_path / "database"
    monkeypatch.setattr(app_config, "settings_path", str(settings_path))
    monkeypatch.setattr(app_config, "output_root", str(data_root))
    monkeypatch.setattr(app_config, "disclosure_separate_output_directory", False)

    response = TestClient(app).post(
        "/api/settings",
        json={"disclosure_separate_output_directory": True},
    )

    assert response.status_code == 200
    assert response.json()["disclosure_separate_output_directory"] is True
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["disclosure_separate_output_directory"] is True


def test_init_config_preserves_saved_stage_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "database"
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "output_root": str(data_root),
                "download_output_directory": str(tmp_path / "legacy-list"),
                "sqlite_output_directory": str(tmp_path / "legacy-table"),
                "html_output_directory": str(tmp_path / "legacy-external"),
                "html_content_output_directory": str(tmp_path / "legacy-internal"),
                "html_section_split_output_directory": str(tmp_path / "legacy-sections"),
                "html_parse_output_directory": str(tmp_path / "legacy-converted"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        finiq_config, "get_default_settings_path", lambda: settings_path
    )

    loaded = finiq_config.init_config()

    assert loaded.download_output_directory == str(tmp_path / "legacy-list")
    assert loaded.sqlite_output_directory == str(tmp_path / "legacy-table")
    assert loaded.html_output_directory == str(tmp_path / "legacy-external")
    assert loaded.html_content_output_directory == str(tmp_path / "legacy-internal")
    assert loaded.html_section_split_output_directory == str(tmp_path / "legacy-sections")
    assert loaded.html_parse_output_directory == str(tmp_path / "legacy-converted")


def test_init_config_migrates_legacy_default_kind_root_to_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"output_root": str(finiq_config.KIND_DATA_DIR)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        finiq_config, "get_default_settings_path", lambda: settings_path
    )

    loaded = finiq_config.init_config()

    assert loaded.output_root == str(finiq_config.RESOURCES_DIR)
    expected = disclosure_workspace_settings(
        finiq_config.RESOURCES_DIR, mode="bond_issuance"
    )
    assert {key: getattr(loaded, key) for key in expected} == expected


def test_saving_only_output_root_updates_paths_without_preparing_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_path = tmp_path / "settings.json"
    data_root = tmp_path / "resources"
    monkeypatch.setattr(app_config, "settings_path", str(settings_path))
    monkeypatch.setattr(app_config, "html_parse_mode", "bond_issuance")
    for key in disclosure_workspace_settings(
        tmp_path / "old", mode="bond_issuance"
    ):
        monkeypatch.setattr(app_config, key, "legacy")

    response = TestClient(app).post(
        "/api/settings", json={"output_root": str(data_root)}
    )

    assert response.status_code == 200
    expected = disclosure_workspace_settings(data_root, mode="bond_issuance")
    assert {key: response.json()[key] for key in expected} == expected
    assert not data_root.exists()
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert {key: saved[key] for key in expected} == expected


def test_saving_high_risk_output_root_defers_validation_until_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(app_config, "settings_path", str(settings_path))
    monkeypatch.setattr(app_config, "output_root", str(tmp_path / "old-root"))
    monkeypatch.setattr(app_config, "html_parse_mode", "bond_issuance")
    expected = finiq_config.build_disclosure_workspace_path_settings(
        finiq_config.PROJECT_ROOT, mode="bond_issuance"
    )
    for key in expected:
        monkeypatch.setattr(app_config, key, "legacy")

    response = TestClient(app).post(
        "/api/settings", json={"output_root": str(finiq_config.PROJECT_ROOT)}
    )

    assert response.status_code == 200
    assert response.json()["output_root"] == str(finiq_config.PROJECT_ROOT.resolve())
    assert {key: response.json()[key] for key in expected} == expected


def test_config_api_returns_saved_stage_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "resources"
    monkeypatch.setattr(app_config, "output_root", str(data_root))
    monkeypatch.setattr(app_config, "html_parse_mode", "bond_issuance")
    expected = disclosure_workspace_settings(data_root, mode="bond_issuance")
    for key in expected:
        monkeypatch.setattr(app_config, key, str(tmp_path / "legacy" / key))

    response = TestClient(app).get("/api/config")

    assert response.status_code == 200
    assert {key: response.json()[key] for key in expected} == {
        key: str(tmp_path / "legacy" / key) for key in expected
    }


def test_changing_parse_mode_updates_only_mode_workspace_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "resources"
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(app_config, "settings_path", str(settings_path))
    monkeypatch.setattr(app_config, "output_root", str(data_root))
    monkeypatch.setattr(app_config, "html_parse_mode", "bond_issuance")
    monkeypatch.setattr(app_config, "html_parse_output_directory", "old-parse")
    monkeypatch.setattr(app_config, "html_parse_result_path", "old-result")
    monkeypatch.setattr(app_config, "download_output_directory", "custom-download")

    response = TestClient(app).post(
        "/api/settings", json={"html_parse_mode": "rights_issuance"}
    )

    expected = disclosure_workspace_settings(data_root, mode="rights_issuance")
    assert response.status_code == 200
    assert response.json()["html_parse_output_directory"] == expected[
        "html_parse_output_directory"
    ]
    assert response.json()["html_parse_result_path"] == expected[
        "html_parse_result_path"
    ]
    assert response.json()["download_output_directory"] == "custom-download"
    assert not data_root.exists()


def test_root_save_preserves_explicit_stage_path_in_same_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_path = tmp_path / "settings.json"
    data_root = tmp_path / "resources"
    custom_external = tmp_path / "custom-external"
    monkeypatch.setattr(app_config, "settings_path", str(settings_path))
    monkeypatch.setattr(app_config, "html_parse_mode", "bond_issuance")

    response = TestClient(app).post(
        "/api/settings",
        json={
            "output_root": str(data_root),
            "html_output_directory": str(custom_external),
        },
    )

    expected = disclosure_workspace_settings(data_root, mode="bond_issuance")
    assert response.status_code == 200
    assert response.json()["download_output_directory"] == expected[
        "download_output_directory"
    ]
    assert response.json()["html_output_directory"] == str(custom_external)


def test_saving_individual_stage_path_preserves_manual_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_path = tmp_path / "settings.json"
    data_root = tmp_path / "database"
    monkeypatch.setattr(app_config, "settings_path", str(settings_path))
    monkeypatch.setattr(app_config, "output_root", str(data_root))
    monkeypatch.setattr(app_config, "html_parse_mode", "bond_issuance")

    response = TestClient(app).post(
        "/api/settings",
        json={"html_output_directory": str(tmp_path / "custom-external")},
    )

    custom_external = str(tmp_path / "custom-external")
    assert response.status_code == 200
    assert response.json()["html_output_directory"] == custom_external
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["html_output_directory"] == custom_external


def test_blank_output_root_is_rejected_without_mutating_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_root = str(tmp_path / "original")
    monkeypatch.setattr(app_config, "output_root", original_root)

    response = TestClient(app).post("/api/settings", json={"output_root": ""})

    assert response.status_code == 400
    assert app_config.output_root == original_root


def test_settings_write_failure_rolls_back_in_memory_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_path = str(tmp_path / "original-table")
    monkeypatch.setattr(app_config, "sqlite_output_directory", original_path)

    def fail_save(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(
        "finiq.market_desk.web.routers.config.save_settings", fail_save
    )

    response = TestClient(app).post(
        "/api/settings",
        json={"sqlite_output_directory": str(tmp_path / "new-table")},
    )

    assert response.status_code == 500
    assert app_config.sqlite_output_directory == original_path
