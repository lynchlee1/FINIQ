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
    STAGE_LINK_FILENAME,
    apply_workspace_defaults,
    disclosure_workspace_settings,
    manage_disclosure_stage_links_payload,
    prepare_disclosure_workspace_payload,
    resolve_disclosure_workspace,
)
from finiq.market_desk.web.features.disclosures.table_export import (
    _manifest_output_path,
)
from finiq.market_desk.web.features.disclosures.filter_presets import (
    manage_filter_presets_payload,
)
from finiq.market_desk.web.features.disclosures.html_sections import (
    save_disclosure_html_sections_payload,
)


def test_stage_link_uses_visible_filename() -> None:
    assert STAGE_LINK_FILENAME == "finiq-stage-link.json"


def _write_stage_link(data_root: Path, stage_name: str, target_root: Path) -> None:
    local_stage = data_root / stage_name
    local_stage.mkdir(parents=True, exist_ok=True)
    (local_stage / STAGE_LINK_FILENAME).write_text(
        json.dumps(
            {
                "format": "finiq_stage_link_v1",
                "schema_version": 1,
                "target_workspace": str(target_root),
            }
        ),
        encoding="utf-8",
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
        "04-external-html-download",
        "04-external-html-download/bond_issuance",
        "04-external-html-download/rights_issuance",
        "04-external-html-compress",
        "04-external-html-compress/bond_issuance",
        "04-external-html-compress/rights_issuance",
        "05-internal-html-download",
        "05-internal-html-download/bond_issuance",
        "05-internal-html-download/rights_issuance",
        "06-sections",
        "06-sections/bond_issuance",
        "06-sections/rights_issuance",
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
    assert result["paths"]["internal"]["bond_issuance"] == str(
        data_root / "05-internal-html-download" / "bond_issuance"
    )


def test_workspace_rejects_unsafe_mode_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="mode"):
        prepare_disclosure_workspace_payload(
            {"data_root": str(tmp_path / "workspace"), "modes": ["../escape"]}
        )


def test_workspace_resolves_each_linked_stage_to_same_stage_in_target_workspace(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "local-workspace"
    target_root = tmp_path / "hdd-workspace"
    for stage_name in ("01-list", "04-external-html-download"):
        local_stage = data_root / stage_name
        local_stage.mkdir(parents=True)
        (target_root / stage_name).mkdir(parents=True)
        (local_stage / STAGE_LINK_FILENAME).write_text(
            json.dumps(
                {
                    "format": "finiq_stage_link_v1",
                    "schema_version": 1,
                    "target_workspace": str(target_root),
                }
            ),
            encoding="utf-8",
        )

    workspace = resolve_disclosure_workspace(data_root)

    assert workspace.root == data_root.resolve()
    assert workspace.list == (target_root / "01-list").resolve()
    assert workspace.external == (
        target_root / "04-external-html-download"
    ).resolve()
    assert workspace.table == data_root.resolve() / "02-table"


def test_workspace_resolves_relative_stage_link_target_from_data_root(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "local-workspace"
    target_root = tmp_path / "hdd-workspace"
    local_stage = data_root / "06-sections"
    local_stage.mkdir(parents=True)
    (target_root / "06-sections").mkdir(parents=True)
    (local_stage / STAGE_LINK_FILENAME).write_text(
        json.dumps(
            {
                "format": "finiq_stage_link_v1",
                "schema_version": 1,
                "target_workspace": "../hdd-workspace",
            }
        ),
        encoding="utf-8",
    )

    workspace = resolve_disclosure_workspace(data_root)

    assert workspace.sections == (target_root / "06-sections").resolve()


def test_manage_stage_links_resolves_relative_target_from_data_root(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "local-workspace"
    target_root = data_root / "hdd-workspace"
    target_root.mkdir(parents=True)

    result = manage_disclosure_stage_links_payload(
        {
            "data_root": str(data_root),
            "action": "set",
            "stage": "01-list",
            "target_workspace": "hdd-workspace",
        }
    )

    list_status = next(
        item for item in result["stages"] if item["stage"] == "01-list"
    )
    assert list_status["target_workspace"] == str(target_root)
    assert list_status["resolved_directory"] == str(target_root / "01-list")
    assert resolve_disclosure_workspace(data_root).list == target_root / "01-list"


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"format": "wrong", "schema_version": 1, "target_workspace": "x"}, "format"),
        ({"format": "finiq_stage_link_v1", "schema_version": 2, "target_workspace": "x"}, "schema version"),
        ({"format": "finiq_stage_link_v1", "schema_version": 1}, "target_workspace"),
    ],
)
def test_workspace_rejects_invalid_stage_link(
    tmp_path: Path, payload: dict[str, object], error: str
) -> None:
    local_stage = tmp_path / "workspace" / "01-list"
    local_stage.mkdir(parents=True)
    (local_stage / STAGE_LINK_FILENAME).write_text(
        json.dumps(payload), encoding="utf-8"
    )

    workspace = resolve_disclosure_workspace(tmp_path / "workspace")

    with pytest.raises(ValueError, match=error):
        _ = workspace.list


def test_workspace_link_shadows_existing_local_data(tmp_path: Path) -> None:
    data_root = tmp_path / "local-workspace"
    target_root = tmp_path / "hdd-workspace"
    local_stage = data_root / "01-list"
    local_stage.mkdir(parents=True)
    (target_root / "01-list").mkdir(parents=True)
    (local_stage / "local-data.body").write_text("data", encoding="utf-8")
    (local_stage / STAGE_LINK_FILENAME).write_text(
        json.dumps(
            {
                "format": "finiq_stage_link_v1",
                "schema_version": 1,
                "target_workspace": str(target_root),
            }
        ),
        encoding="utf-8",
    )

    workspace = resolve_disclosure_workspace(data_root)

    assert workspace.list == (target_root / "01-list").resolve()
    assert (local_stage / "local-data.body").read_text(encoding="utf-8") == "data"


def test_workspace_rejects_chained_stage_link(tmp_path: Path) -> None:
    data_root = tmp_path / "local-workspace"
    target_root = tmp_path / "hdd-workspace"
    payload = {
        "format": "finiq_stage_link_v1",
        "schema_version": 1,
        "target_workspace": str(target_root),
    }
    for root in (data_root, target_root):
        stage = root / "01-list"
        stage.mkdir(parents=True)
        (stage / STAGE_LINK_FILENAME).write_text(
            json.dumps(payload), encoding="utf-8"
        )

    workspace = resolve_disclosure_workspace(data_root)

    with pytest.raises(ValueError, match="Chained"):
        _ = workspace.list


def test_section_steps_ignore_broken_unrelated_stage_links(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    missing_target = tmp_path / "missing-target"
    for stage_name in ("01-list", "04-external-html-download"):
        _write_stage_link(data_root, stage_name, missing_target)

    inspected = apply_workspace_defaults(
        "section_inspect",
        {"data_root": str(data_root), "mode": "bond_issuance"},
    )
    saved = apply_workspace_defaults(
        "section_save",
        {"data_root": str(data_root), "mode": "bond_issuance"},
    )

    assert inspected["input_directory"] == str(
        data_root / "05-internal-html-download" / "bond_issuance"
    )
    assert saved["input_directory"] == inspected["input_directory"]
    assert saved["output_directory"] == str(
        data_root / "06-sections" / "bond_issuance"
    )


def test_internal_download_ignores_broken_unrelated_stage_links(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    missing_target = tmp_path / "missing-target"
    for stage_name in ("01-list", "04-external-html-download"):
        _write_stage_link(data_root, stage_name, missing_target)

    payload = apply_workspace_defaults(
        "internal_html_download",
        {"data_root": str(data_root), "mode": "bond_issuance"},
    )

    assert payload["source_compressed_json_path"] == str(
        data_root
        / "04-external-html-compress"
        / "bond_issuance"
        / "compressed-external-html.json"
    )
    assert payload["output_directory"] == str(
        data_root / "05-internal-html-download" / "bond_issuance"
    )


def test_section_steps_validate_only_their_required_stage_links(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    missing_target = tmp_path / "missing-target"
    _write_stage_link(data_root, "05-internal-html-download", missing_target)

    with pytest.raises(ValueError, match="target workspace does not exist"):
        apply_workspace_defaults(
            "section_inspect",
            {"data_root": str(data_root), "mode": "bond_issuance"},
        )

    (data_root / "05-internal-html-download" / STAGE_LINK_FILENAME).unlink()
    _write_stage_link(data_root, "06-sections", missing_target)

    inspected = apply_workspace_defaults(
        "section_inspect",
        {"data_root": str(data_root), "mode": "bond_issuance"},
    )
    assert inspected["input_directory"] == str(
        data_root / "05-internal-html-download" / "bond_issuance"
    )
    with pytest.raises(ValueError, match="target workspace does not exist"):
        apply_workspace_defaults(
            "section_save",
            {"data_root": str(data_root), "mode": "bond_issuance"},
        )


def test_manage_stage_links_add_change_and_remove(tmp_path: Path) -> None:
    data_root = tmp_path / "local-workspace"
    first_target = tmp_path / "first-target"
    second_target = tmp_path / "second-target"
    for target in (first_target, second_target):
        (target / "03-filter").mkdir(parents=True)

    linked = manage_disclosure_stage_links_payload(
        {
            "data_root": str(data_root),
            "action": "set",
            "stage": "03-filter",
            "target_workspace": str(first_target),
        }
    )
    filter_status = next(
        item for item in linked["stages"] if item["stage"] == "03-filter"
    )
    assert filter_status == {
        "stage": "03-filter",
        "linked": True,
        "valid": True,
        "local_directory": str(data_root / "03-filter"),
        "target_workspace": str(first_target),
        "resolved_directory": str(first_target / "03-filter"),
        "error": None,
    }

    changed = manage_disclosure_stage_links_payload(
        {
            "data_root": str(data_root),
            "action": "set",
            "stage": "03-filter",
            "target_workspace": str(second_target),
        }
    )
    filter_status = next(
        item for item in changed["stages"] if item["stage"] == "03-filter"
    )
    assert filter_status["target_workspace"] == str(second_target)
    assert resolve_disclosure_workspace(data_root).filtered == second_target / "03-filter"

    removed = manage_disclosure_stage_links_payload(
        {"data_root": str(data_root), "action": "remove", "stage": "03-filter"}
    )
    filter_status = next(
        item for item in removed["stages"] if item["stage"] == "03-filter"
    )
    assert filter_status["linked"] is False
    assert resolve_disclosure_workspace(data_root).filtered == data_root / "03-filter"


def test_manage_stage_links_lists_missing_target_for_change_or_removal(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "local-workspace"
    target_root = tmp_path / "missing-target"
    local_stage = data_root / "03-filter"
    local_stage.mkdir(parents=True)
    (local_stage / STAGE_LINK_FILENAME).write_text(
        json.dumps(
            {
                "format": "finiq_stage_link_v1",
                "schema_version": 1,
                "target_workspace": str(target_root),
            }
        ),
        encoding="utf-8",
    )

    listed = manage_disclosure_stage_links_payload(
        {"data_root": str(data_root), "action": "list"}
    )

    filter_status = next(
        item for item in listed["stages"] if item["stage"] == "03-filter"
    )
    assert filter_status["linked"] is True
    assert filter_status["valid"] is False
    assert filter_status["target_workspace"] == str(target_root)
    assert "does not exist" in filter_status["error"]

    removed = manage_disclosure_stage_links_payload(
        {"data_root": str(data_root), "action": "remove", "stage": "03-filter"}
    )
    filter_status = next(
        item for item in removed["stages"] if item["stage"] == "03-filter"
    )
    assert filter_status["linked"] is False


def test_stage_links_resolve_each_stage_to_its_own_workspace(tmp_path: Path) -> None:
    data_root = tmp_path / "local-workspace"
    list_target = tmp_path / "list-database"
    table_target = tmp_path / "table-database"
    list_target.mkdir()
    table_target.mkdir()

    manage_disclosure_stage_links_payload(
        {
            "data_root": str(data_root),
            "action": "set",
            "stage": "01-list",
            "target_workspace": str(list_target),
        }
    )
    manage_disclosure_stage_links_payload(
        {
            "data_root": str(data_root),
            "action": "set",
            "stage": "02-table",
            "target_workspace": str(table_target),
        }
    )

    workspace = resolve_disclosure_workspace(data_root)

    assert workspace.list == list_target / "01-list"
    assert workspace.table == table_target / "02-table"


def test_manage_stage_links_preserves_local_data_and_rejects_chained_target(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "local-workspace"
    target_root = tmp_path / "target-workspace"
    local_stage = data_root / "04-external-html-download"
    target_stage = target_root / "04-external-html-download"
    local_stage.mkdir(parents=True)
    target_root.mkdir(parents=True)
    (local_stage / "existing.json").write_text("{}", encoding="utf-8")

    result = manage_disclosure_stage_links_payload(
        {
            "data_root": str(data_root),
            "action": "set",
            "stage": "04-external-html-download",
            "target_workspace": str(target_root),
        }
    )

    assert target_stage.is_dir()
    assert (local_stage / "existing.json").is_file()
    external = next(
        item for item in result["stages"] if item["stage"] == "04-external-html-download"
    )
    assert external["resolved_directory"] == str(target_stage)
    assert resolve_disclosure_workspace(data_root).external == target_stage

    manage_disclosure_stage_links_payload(
        {
            "data_root": str(data_root),
            "action": "remove",
            "stage": "04-external-html-download",
        }
    )
    assert resolve_disclosure_workspace(data_root).external == local_stage
    assert (local_stage / "existing.json").is_file()

    (target_stage / STAGE_LINK_FILENAME).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Chained"):
        manage_disclosure_stage_links_payload(
            {
                "data_root": str(data_root),
                "action": "set",
                "stage": "04-external-html-download",
                "target_workspace": str(target_root),
            }
        )


def test_workspace_stage_links_api(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    target_root = tmp_path / "hdd-workspace"
    (target_root / "06-sections").mkdir(parents=True)
    client = TestClient(app)

    response = client.post(
        "/api/disclosures/workspace/stage-links",
        json={
            "data_root": str(data_root),
            "action": "set",
            "stage": "06-sections",
            "target_workspace": str(target_root),
        },
    )

    assert response.status_code == 200
    sections = next(
        item for item in response.json()["stages"] if item["stage"] == "06-sections"
    )
    assert sections["resolved_directory"] == str(target_root / "06-sections")


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
        _manifest_output_path(table["output_path"]).parent
        == workspace.table
    )
    assert filtered["external_html_transfer_path"] == str(workspace.filtered)
    external = apply_workspace_defaults(
        "external_html_download",
        {"data_root": str(workspace.root), "mode": "bond_issuance"},
    )
    assert external["output_directory"] == str(
        workspace.external / "bond_issuance"
    )
    compressed = apply_workspace_defaults(
        "external_html_compress",
        {"data_root": str(workspace.root), "mode": "bond_issuance"},
    )
    assert compressed["input_directory"] == str(
        workspace.external / "bond_issuance"
    )
    assert compressed["output_directory"] == str(
        workspace.external_compress / "bond_issuance"
    )
    internal = apply_workspace_defaults(
        "internal_html_download",
        {"data_root": str(workspace.root), "mode": "bond_issuance"},
    )
    assert internal["source_compressed_json_path"] == str(
        workspace.external_compress / "bond_issuance" / "compressed-external-html.json"
    )
    assert internal["output_directory"] == str(
        workspace.internal / "bond_issuance"
    )
    rights_internal = apply_workspace_defaults(
        "internal_html_download",
        {"data_root": str(workspace.root), "mode": "rights_issuance"},
    )
    assert rights_internal["output_directory"] == str(
        workspace.internal / "rights_issuance"
    )
    assert rights_internal["output_directory"] != internal["output_directory"]
    sections = apply_workspace_defaults(
        "section_save",
        {"data_root": str(workspace.root), "mode": "bond_issuance"},
    )
    assert sections["input_directory"] == str(
        workspace.internal / "bond_issuance"
    )
    assert sections["output_directory"] == str(
        workspace.sections / "bond_issuance"
    )
    rights_sections = apply_workspace_defaults(
        "section_save",
        {"data_root": str(workspace.root), "mode": "rights_issuance"},
    )
    assert rights_sections["output_directory"] == str(
        workspace.sections / "rights_issuance"
    )
    assert rights_sections["output_directory"] != sections["output_directory"]
    converted = apply_workspace_defaults(
        "parse", {"data_root": str(workspace.root), "mode": "bond_issuance"}
    )
    assert "skip_errors" not in converted
    assert converted["input_directory"] == str(
        workspace.sections / "bond_issuance"
    )
    assert converted["output_directory"] == str(
        workspace.converted / "bond_issuance"
    )
    assert converted["filtered_metadata_path"] == str(
        workspace.filtered / "bond_issuance" / "filtered.json"
    )
    assert converted["compressed_metadata_path"] == str(
        workspace.external_compress / "bond_issuance" / "compressed-external-html.json"
    )


def test_workspace_section_save_writes_under_mode_not_year_root(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    prepare_disclosure_workspace_payload(
        {
            "data_root": str(data_root),
            "modes": ["bond_issuance", "rights_issuance"],
        }
    )
    html = (
        "<html><head></head><body>"
        "<h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>1</p></h2>"
        "<p>본문</p></body></html>"
    )
    source_name = "20260101000001.html"
    for mode in ("bond_issuance", "rights_issuance"):
        source = (
            data_root / "05-internal-html-download" / mode / "2026" / source_name
        )
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(html, encoding="utf-8")
        result = save_disclosure_html_sections_payload(
            apply_workspace_defaults(
                "section_save",
                {"data_root": str(data_root), "mode": mode},
            )
        )
        saved = data_root / "06-sections" / mode / "2026" / source_name
        assert result["summary"]["saved_files"] == 1
        assert result["output_directory"] == str(data_root / "06-sections" / mode)
        assert saved.is_file()
        assert "본문" in saved.read_text(encoding="utf-8")
    assert not (data_root / "06-sections" / "2026").exists()


def test_workspace_section_save_rejects_stage_root_output(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    prepare_disclosure_workspace_payload(
        {"data_root": str(data_root), "modes": ["bond_issuance"]}
    )
    source = (
        data_root
        / "05-internal-html-download"
        / "bond_issuance"
        / "2026"
        / "20260101000001.html"
    )
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "<html><head></head><body>"
        "<h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>1</p></h2>"
        "<p>본문</p></body></html>",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="owner mode directory"):
        save_disclosure_html_sections_payload(
            {
                "data_root": str(data_root),
                "mode": "bond_issuance",
                "input_directory": str(
                    data_root / "05-internal-html-download" / "bond_issuance"
                ),
                "output_directory": str(data_root / "06-sections"),
            }
        )

    assert not (
        data_root / "06-sections" / "bond_issuance" / "2026" / source.name
    ).exists()


def test_workspace_section_save_rejects_previous_mode_output(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    prepare_disclosure_workspace_payload(
        {
            "data_root": str(data_root),
            "modes": ["bond_issuance", "shareholder_meeting"],
        }
    )
    html = (
        "<html><head></head><body>"
        "<h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>1</p></h2>"
        "<p>본문</p></body></html>"
    )
    bond_source = (
        data_root
        / "05-internal-html-download"
        / "bond_issuance"
        / "2026"
        / "20260101000001.html"
    )
    meeting_source = (
        data_root
        / "05-internal-html-download"
        / "shareholder_meeting"
        / "2026"
        / "20260101000002.html"
    )
    for source in (bond_source, meeting_source):
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(html, encoding="utf-8")

    save_disclosure_html_sections_payload(
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "input_directory": str(bond_source.parent.parent),
            "output_directory": str(
                data_root / "06-sections" / "bond_issuance"
            ),
        }
    )
    with pytest.raises(ValueError, match="owner mode directory"):
        save_disclosure_html_sections_payload(
            {
                "data_root": str(data_root),
                "mode": "shareholder_meeting",
                "input_directory": str(meeting_source.parent.parent),
                "output_directory": str(
                    data_root / "06-sections" / "bond_issuance"
                ),
            }
        )

    meeting_saved = (
        data_root
        / "06-sections"
        / "shareholder_meeting"
        / "2026"
        / meeting_source.name
    )
    assert not meeting_saved.exists()
    assert (
        data_root / "06-sections" / "bond_issuance" / "2026" / bond_source.name
    ).is_file()
    assert not (
        data_root / "06-sections" / "bond_issuance" / "2026" / meeting_source.name
    ).exists()


def test_section_save_rejects_year_directly_under_sections_stage_without_mode(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "05-internal-html-download"
    source = input_directory / "2026" / "20260101000001.html"
    source.parent.mkdir(parents=True)
    source.write_text(
        "<html><head></head><body>"
        "<h2 class='SECTION-1' id='toc_1'><p class='SECTION-1'>1</p></h2>"
        "<p>본문</p></body></html>",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="06-sections"):
        save_disclosure_html_sections_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(tmp_path / "06-sections"),
            }
        )
    assert not (tmp_path / "06-sections" / "2026").exists()


def test_workspace_parse_rejects_stage_root_input(tmp_path: Path) -> None:
    workspace = resolve_disclosure_workspace(tmp_path / "workspace", create=True)
    with pytest.raises(ValueError, match="owner mode directory"):
        apply_workspace_defaults(
            "parse",
            {
                "data_root": str(workspace.root),
                "mode": "bond_issuance",
                "input_directory": str(workspace.sections),
            },
        )


def test_workspace_defaults_use_parent_html_for_derived_filter(tmp_path: Path) -> None:
    workspace = resolve_disclosure_workspace(tmp_path / "workspace", create=True)
    identity = {
        "data_root": str(workspace.root),
        "mode": "child",
        "parent_mode": "parent",
    }

    external = apply_workspace_defaults("external_html_download", identity)
    internal = apply_workspace_defaults("internal_html_download", identity)
    parsed = apply_workspace_defaults("parse", identity)

    assert external["output_directory"] == str(workspace.external / "parent")
    assert internal["output_directory"] == str(workspace.internal / "parent")
    assert internal["source_compressed_json_path"] == str(
        workspace.external_compress / "parent" / "compressed-external-html.json"
    )
    assert parsed["filtered_metadata_path"] == str(
        workspace.filtered / "parent" / "subfilters" / "child" / "filtered.json"
    )
    assert parsed["compressed_metadata_path"] == str(
        workspace.external_compress / "parent" / "compressed-external-html.json"
    )
    assert parsed["input_directory"] == str(workspace.sections / "parent")
    assert parsed["output_directory"] == str(
        workspace.converted / "parent" / "subfilters" / "child"
    )
    sections = apply_workspace_defaults("section_save", identity)
    assert sections["input_directory"] == str(workspace.internal / "parent")
    assert sections["output_directory"] == str(workspace.sections / "parent")


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

    with pytest.raises(ValueError, match="classification_path is not supported"):
        apply_workspace_defaults(
            "filter",
            {
                "data_root": str(workspace.root),
                "mode": "bond_issuance",
                "classification_path": str(explicit / "table"),
            },
        )

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
        "external_html_download",
        {
            "data_root": str(workspace.root),
            "mode": "bond_issuance",
            "output_directory": str(explicit / "external"),
        },
    )
    assert external["output_directory"] == str(explicit / "external")

    compressed = apply_workspace_defaults(
        "external_html_compress",
        {
            "data_root": str(workspace.root),
            "mode": "bond_issuance",
            "input_directory": str(explicit / "external"),
            "output_directory": str(explicit / "compressed"),
        },
    )
    assert compressed["input_directory"] == str(explicit / "external")
    assert compressed["output_directory"] == str(explicit / "compressed")

    internal = apply_workspace_defaults(
        "internal_html_download",
        {
            "data_root": str(workspace.root),
            "mode": "bond_issuance",
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


def test_workspace_links_override_explicit_stage_paths(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    target_root = tmp_path / "target"
    explicit = tmp_path / "explicit"
    target_root.mkdir()
    for stage in (
        "01-list",
        "02-table",
        "03-filter",
            "04-external-html-download",
            "04-external-html-compress",
        "05-internal-html-download",
        "06-sections",
        "07-converted",
    ):
        manage_disclosure_stage_links_payload(
            {
                "data_root": str(data_root),
                "action": "set",
                "stage": stage,
                "target_workspace": str(target_root),
            }
        )

    downloaded = apply_workspace_defaults(
        "kind_download",
        {
            "data_root": str(data_root),
            "separate_output_directory": True,
            "output_directory": str(explicit / "list"),
        },
    )
    assert downloaded["output_directory"] == str(target_root / "01-list")

    table = apply_workspace_defaults(
        "table_build",
        {
            "data_root": str(data_root),
            "root_directory": str(explicit / "list"),
            "output_path": str(explicit / "table"),
        },
    )
    assert table["root_directory"] == str(target_root / "01-list")
    assert table["output_path"] == str(target_root / "02-table")

    filtered = apply_workspace_defaults(
        "filter",
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "external_html_transfer_path": str(explicit / "filter"),
        },
    )
    assert filtered["external_html_transfer_path"] == str(target_root / "03-filter")

    external = apply_workspace_defaults(
        "external_html_download",
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "output_directory": str(explicit / "external"),
        },
    )
    assert external["output_directory"] == str(
        target_root / "04-external-html-download" / "bond_issuance"
    )

    internal = apply_workspace_defaults(
        "internal_html_download",
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "source_compressed_json_path": str(explicit / "compressed.json"),
            "output_directory": str(explicit / "internal"),
        },
    )
    assert internal["source_compressed_json_path"] == str(
        target_root
            / "04-external-html-compress"
        / "bond_issuance"
        / "compressed-external-html.json"
    )
    assert internal["output_directory"] == str(
        target_root / "05-internal-html-download" / "bond_issuance"
    )

    sections = apply_workspace_defaults(
        "section_save",
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "input_directory": str(explicit / "internal"),
            "output_directory": str(explicit / "sections"),
        },
    )
    assert sections["input_directory"] == str(
        target_root / "05-internal-html-download" / "bond_issuance"
    )
    assert sections["output_directory"] == str(
        target_root / "06-sections" / "bond_issuance"
    )

    parsed = apply_workspace_defaults(
        "parse",
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "input_directory": str(explicit / "sections"),
            "output_directory": str(explicit / "converted"),
            "filtered_metadata_path": str(explicit / "filtered.json"),
            "compressed_metadata_path": str(explicit / "compressed.json"),
        },
    )
    assert parsed["input_directory"] == str(
        target_root / "06-sections" / "bond_issuance"
    )
    assert parsed["output_directory"] == str(
        target_root / "07-converted" / "bond_issuance"
    )
    assert parsed["filtered_metadata_path"] == str(
        target_root / "03-filter" / "bond_issuance" / "filtered.json"
    )
    assert parsed["compressed_metadata_path"] == str(
        target_root
        / "04-external-html-compress"
        / "bond_issuance"
        / "compressed-external-html.json"
    )


def test_external_html_save_and_compress_storage_links_are_independent(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    target_root = tmp_path / "target"
    target_root.mkdir()
    manage_disclosure_stage_links_payload(
        {
            "data_root": str(data_root),
            "action": "set",
            "stage": "04-external-html-compress",
            "target_workspace": str(target_root),
        }
    )

    compressed = apply_workspace_defaults(
        "external_html_compress",
        {"data_root": str(data_root), "mode": "bond_issuance"},
    )

    assert compressed["input_directory"] == str(
        data_root / "04-external-html-download" / "bond_issuance"
    )
    assert compressed["output_directory"] == str(
        target_root / "04-external-html-compress" / "bond_issuance"
    )


def test_workspace_prepare_api(tmp_path: Path) -> None:
    client = TestClient(app)

    response = client.post(
        "/api/disclosures/workspace/prepare",
        json={"data_root": str(tmp_path / "workspace"), "modes": ["bond_issuance"]},
    )

    assert response.status_code == 200
    assert response.json()["format"] == "finiq_disclosure_workspace_v1"
    assert response.json()["paths"]["internal"]["bond_issuance"] == str(
        tmp_path / "workspace" / "05-internal-html-download" / "bond_issuance"
    )


def test_workspace_prepare_preserves_existing_modes(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    prepare_disclosure_workspace_payload(
        {"data_root": str(data_root), "modes": ["bond_issuance"]}
    )

    result = prepare_disclosure_workspace_payload(
        {"data_root": str(data_root), "modes": ["rights_issuance"]}
    )

    assert result["modes"] == ["bond_issuance", "rights_issuance"]
    assert set(result["paths"]["external"]) == {
        "bond_issuance",
        "rights_issuance",
    }
    assert set(result["paths"]["internal"]) == {
        "bond_issuance",
        "rights_issuance",
    }
    assert result["paths"]["sections_root"] == str(data_root / "06-sections")
    assert set(result["paths"]["sections"]) == {
        "bond_issuance",
        "rights_issuance",
    }
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
            "source_type": "sqlite_manifest",
            "source_fingerprint": "0" * 64,
            "source_sqlite_manifest_path": str(
                data_root / "02-table" / "sqlite_manifest.json"
            ),
            "filters": {"filter_blocks": []},
            "summary": {
                "source_disclosures": 0,
                "source_body_files": 0,
                "source_offset": 0,
                "target_disclosures": 0,
                "inspected_disclosures": 0,
                "matched_disclosures": 0,
                "returned_disclosures": 0,
                "duplicate_disclosures": 0,
                "unique_acpt_numbers": 0,
            },
            "integrity": {
                "complete": True,
                "passed": True,
                "search_target_disclosures": 0,
                "search_result_disclosures": 0,
                "inspected_disclosures": 0,
            },
            "unique_titles": [],
            "disclosures": [],
            "external_html_download_acpt_numbers": [],
        }

    monkeypatch.setattr(web_app, "filter_disclosures_payload", fake_filter)
    manage_filter_presets_payload(
        {
            "data_root": str(data_root),
            "action": "save",
            "preset": {
                "mode": "bond_issuance",
                "condition_blocks": [],
            },
        }
    )

    response = TestClient(app).post(
        "/api/disclosures/filter",
        json={
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "filter_blocks": [],
        },
    )

    assert response.status_code == 200
    assert captured["data_root"] == str(data_root)
    assert captured["mode"] == "bond_issuance"
    assert "classification_path" not in captured
    assert captured["external_html_transfer_path"] == str(data_root / "03-filter")
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
        "external_html_transfer_directory": str(data_root / "03-filter"),
        "external_html_output_directory": str(data_root / "04-external-html-download" / "bond_issuance"),
        "external_html_compress_input_directory": str(data_root / "04-external-html-download" / "bond_issuance"),
        "external_html_compress_output_directory": str(data_root / "04-external-html-compress" / "bond_issuance"),
        "external_html_compressed_json_path": str(
            data_root / "04-external-html-compress" / "bond_issuance" / "compressed-external-html.json"
        ),
        "internal_html_output_directory": str(
            data_root / "05-internal-html-download" / "bond_issuance"
        ),
        "html_section_split_output_directory": str(
            data_root / "06-sections" / "bond_issuance"
        ),
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


def test_workspace_settings_use_linked_stage_directories(tmp_path: Path) -> None:
    data_root = tmp_path / "local-workspace"
    target_root = tmp_path / "hdd-workspace"
    for stage_name in ("01-list", "05-internal-html-download"):
        local_stage = data_root / stage_name
        local_stage.mkdir(parents=True)
        (target_root / stage_name).mkdir(parents=True)
        (local_stage / STAGE_LINK_FILENAME).write_text(
            json.dumps(
                {
                    "format": "finiq_stage_link_v1",
                    "schema_version": 1,
                    "target_workspace": str(target_root),
                }
            ),
            encoding="utf-8",
        )

    settings = disclosure_workspace_settings(data_root, mode="bond_issuance")

    assert settings["download_output_directory"] == str(target_root / "01-list")
    assert settings["sqlite_source_path"] == str(target_root / "01-list")
    assert settings["sqlite_output_directory"] == str(data_root / "02-table")
    assert settings["internal_html_output_directory"] == str(
        target_root / "05-internal-html-download" / "bond_issuance"
    )


def test_prepare_workspace_creates_mode_in_linked_stage(tmp_path: Path) -> None:
    data_root = tmp_path / "local-workspace"
    target_root = tmp_path / "hdd-workspace"
    local_stage = data_root / "07-converted"
    local_stage.mkdir(parents=True)
    (target_root / "07-converted").mkdir(parents=True)
    (local_stage / STAGE_LINK_FILENAME).write_text(
        json.dumps(
            {
                "format": "finiq_stage_link_v1",
                "schema_version": 1,
                "target_workspace": str(target_root),
            }
        ),
        encoding="utf-8",
    )

    result = prepare_disclosure_workspace_payload(
        {"data_root": str(data_root), "modes": ["bond_issuance"]}
    )

    assert (target_root / "07-converted" / "bond_issuance").is_dir()
    assert not (data_root / "07-converted" / "bond_issuance").exists()
    assert result["paths"]["converted"]["bond_issuance"] == str(
        target_root / "07-converted" / "bond_issuance"
    )


def test_init_config_does_not_invent_mode_or_workspace_paths(
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

    assert loaded.output_root == str(data_root.resolve())
    assert loaded.html_parse_mode == ""
    for key in disclosure_workspace_settings(data_root, mode="bond_issuance"):
        assert getattr(loaded, key) == ""
    assert loaded.disclosure_separate_output_directory is False
    assert loaded.job_retention_minutes == 60


def test_init_config_loads_kind_proxy_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "kind_proxy_urls": [
                    "http://127.0.0.1:25001",
                    "http://localhost:25002",
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        finiq_config, "get_default_settings_path", lambda: settings_path
    )

    loaded = finiq_config.init_config()

    assert loaded.kind_proxy_urls == [
        "http://127.0.0.1:25001",
        "http://localhost:25002",
    ]


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
                "external_html_output_directory": str(tmp_path / "legacy-external"),
                "internal_html_output_directory": str(tmp_path / "legacy-internal"),
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
    assert loaded.external_html_output_directory == str(tmp_path / "legacy-external")
    assert loaded.internal_html_output_directory == str(tmp_path / "legacy-internal")
    assert loaded.html_section_split_output_directory == str(tmp_path / "legacy-sections")
    assert loaded.html_parse_output_directory == str(tmp_path / "legacy-converted")


def test_init_config_preserves_saved_legacy_standard_internal_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "database"
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "output_root": str(data_root),
                "html_parse_mode": "rights_issuance",
                "html_parser_method": "rights_issuance",
                "internal_html_output_directory": str(
                    data_root / "05-internal-html-download"
                ),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        finiq_config, "get_default_settings_path", lambda: settings_path
    )

    loaded = finiq_config.init_config()

    assert loaded.html_parser_method == "rights_issuance"

    assert loaded.internal_html_output_directory == str(
        data_root.resolve() / "05-internal-html-download"
    )


def test_init_config_preserves_saved_kind_root_without_migration(
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

    assert loaded.output_root == str(finiq_config.KIND_DATA_DIR)
    assert loaded.html_parse_mode == ""


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


def test_config_api_loads_when_sections_stage_link_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "resources"
    sections_stage = data_root / "06-sections"
    sections_stage.mkdir(parents=True)
    (sections_stage / STAGE_LINK_FILENAME).write_text(
        json.dumps(
            {
                "format": "finiq_stage_link_v1",
                "schema_version": 1,
                "target_workspace": str(tmp_path / "missing-target"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_config, "output_root", str(data_root))
    monkeypatch.setattr(app_config, "html_parse_mode", "bond_issuance")
    monkeypatch.setattr(
        app_config,
        "html_section_split_output_directory",
        str(sections_stage),
    )

    response = TestClient(app).get("/api/config")

    assert response.status_code == 200
    assert response.json()["html_section_split_output_directory"] == str(
        sections_stage / "bond_issuance"
    )


def test_config_api_prefers_linked_stage_over_saved_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "resources"
    target_root = tmp_path / "compressed-target"
    target_root.mkdir()
    manage_disclosure_stage_links_payload(
        {
            "data_root": str(data_root),
            "action": "set",
            "stage": "04-external-html-compress",
            "target_workspace": str(target_root),
        }
    )
    monkeypatch.setattr(app_config, "output_root", str(data_root))
    monkeypatch.setattr(app_config, "html_parse_mode", "bond_issuance")
    monkeypatch.setattr(
        app_config,
        "external_html_compress_output_directory",
        str(tmp_path / "stale-compress"),
    )
    monkeypatch.setattr(
        app_config,
        "external_html_compressed_json_path",
        str(tmp_path / "stale-compressed.json"),
    )

    response = TestClient(app).get("/api/config")

    expected_directory = (
        target_root / "04-external-html-compress" / "bond_issuance"
    )
    assert response.status_code == 200
    assert response.json()["external_html_compress_output_directory"] == str(
        expected_directory
    )
    assert response.json()["external_html_compressed_json_path"] == str(
        expected_directory / "compressed-external-html.json"
    )


def test_changing_parse_mode_updates_mode_workspace_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "resources"
    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr(app_config, "settings_path", str(settings_path))
    monkeypatch.setattr(app_config, "output_root", str(data_root))
    monkeypatch.setattr(app_config, "html_parse_mode", "bond_issuance")
    monkeypatch.setattr(app_config, "html_parse_output_directory", "old-parse")
    monkeypatch.setattr(app_config, "html_parse_result_path", "old-result")
    monkeypatch.setattr(app_config, "external_html_output_directory", "old-external")
    monkeypatch.setattr(app_config, "internal_html_output_directory", "old-internal")
    monkeypatch.setattr(
        app_config, "external_html_compress_input_directory", "old-compress-input"
    )
    monkeypatch.setattr(
        app_config, "external_html_compress_output_directory", "old-compress-output"
    )
    monkeypatch.setattr(
        app_config, "external_html_compressed_json_path", "old-compressed-json"
    )
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
    for key in (
        "external_html_output_directory",
        "external_html_compress_input_directory",
        "external_html_compress_output_directory",
        "external_html_compressed_json_path",
        "internal_html_output_directory",
    ):
        assert response.json()[key] == expected[key]
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
            "external_html_output_directory": str(custom_external),
        },
    )

    expected = disclosure_workspace_settings(data_root, mode="bond_issuance")
    assert response.status_code == 200
    assert response.json()["download_output_directory"] == expected[
        "download_output_directory"
    ]
    assert response.json()["external_html_output_directory"] == str(custom_external)


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
        json={"external_html_output_directory": str(tmp_path / "custom-external")},
    )

    custom_external = str(tmp_path / "custom-external")
    assert response.status_code == 200
    assert response.json()["external_html_output_directory"] == custom_external
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["external_html_output_directory"] == custom_external


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
