from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finiq.data.graph_models import Agenda, Company, EdgeTypes, GraphEdge, Person
from finiq.market_desk.web.app import app
from finiq.market_desk.web.features.disclosures.disclosure_graph import (
    _project_entity_relationships,
    build_disclosure_graph_payload,
    load_disclosure_graph_payload,
)
from tests.market_desk.filter_workflow_fixtures import (
    publish_completed_filter_result,
)


def _write_rights_sources(data_root: Path) -> None:
    parsed_path = (
        data_root
        / "07-converted"
        / "rights_issuance"
        / "parsed-rights_issuance.json"
    )
    parsed_path.parent.mkdir(parents=True)
    publish_completed_filter_result(
        data_root,
        mode="rights_issuance",
        payload={
            "disclosures": [
                {
                    "acpt_no": "20260430001640",
                    "company_id": "005930",
                    "company_name": "테스트전자",
                    "market": "코스피",
                    "disclosed_at": "2026-04-30 09:00",
                    "disclosed_date": "2026-04-30",
                }
            ]
        },
    )
    parsed_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20260430001640",
                        "title": "유상증자결정",
                        "증자유형": "유상증자",
                        "신주의 종류와 수": [["보통주식", 1000]],
                        "발행목적": [["운영자금", 5_000_000]],
                        "발행가액": [["보통주식", 5000]],
                        "증자방식": "제3자배정증자",
                        "납입일": "2026년 05월 15일",
                        "발행대상자": [["테스트투자자", 1000]],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_build_disclosure_graph_payload_writes_stage_09_graph(tmp_path: Path) -> None:
    _write_rights_sources(tmp_path)

    result = build_disclosure_graph_payload({"data_root": str(tmp_path)})

    output_path = tmp_path / "09-disclosure-graph" / "disclosure-graph.json"
    assert result == {
        "format": "finiq_disclosure_graph_build_v2",
        "output_path": str(output_path),
        "source_modes": ["rights_issuance"],
        "total_nodes": result["total_nodes"],
        "total_edges": result["total_edges"],
    }
    assert result["total_nodes"] > 0
    assert result["total_edges"] > 0

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["format"] == "finiq_disclosure_graph_v2"
    assert saved["metadata"]["total_nodes"] == result["total_nodes"]
    assert saved["nodes"]
    assert saved["edges"]
    assert {node["type"] for node in saved["nodes"]} <= {
        "Company",
        "Person",
        "Organization",
    }
    node_ids = {node["id"] for node in saved["nodes"]}
    assert all(
        edge["source"] in node_ids and edge["target"] in node_ids
        for edge in saved["edges"]
    )
    acquired_edge = next(
        edge for edge in saved["edges"] if edge["relation"] == "ACQUIRED"
    )
    assert acquired_edge["source"] == "org_테스트투자자"
    assert acquired_edge["target"] == "company_005930"
    assert acquired_edge["properties"]["evidence"]["acpt_no"] == "20260430001640"
    assert acquired_edge["properties"]["disclosure_target_id"].startswith("security_")
    assert "statements" not in saved
    assert "entity_analysis" not in saved

    def path_keys(value: object) -> list[str]:
        if isinstance(value, dict):
            return [
                *[
                    str(key)
                    for key in value
                    if str(key) in {"path", "source_file", "source_url"}
                    or str(key).endswith("_path")
                ],
                *[
                    key
                    for child in value.values()
                    for key in path_keys(child)
                ],
            ]
        if isinstance(value, list):
            return [key for child in value for key in path_keys(child)]
        return []

    assert path_keys(saved) == []


def test_entity_projection_maps_agenda_relationship_to_reporting_company() -> None:
    nodes = {
        "company_1": Company(id="company_1", name="보고회사"),
        "person_1": Person(id="person_1", name="관계자"),
        "agenda_1": Agenda(id="agenda_1", title="관계 안건"),
    }
    edges = [
        GraphEdge(
            id="edge_1",
            source_id="person_1",
            target_id="agenda_1",
            edge_type=EdgeTypes.SUBJECT_OF,
            properties={"reporting_company_id": "company_1"},
        )
    ]

    entity_nodes, entity_edges = _project_entity_relationships(nodes, edges)

    assert set(entity_nodes) == {"company_1", "person_1"}
    assert len(entity_edges) == 1
    assert entity_edges[0].target_id == "company_1"
    assert entity_edges[0].properties["disclosure_target_id"] == "agenda_1"


def test_build_disclosure_graph_reads_linked_filter_and_converted_stages(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "local-workspace"
    target_root = tmp_path / "hdd-workspace"
    _write_rights_sources(target_root)
    for stage_name in ("03-filter", "07-converted"):
        local_stage = data_root / stage_name
        local_stage.mkdir(parents=True)
        (local_stage / "finiq-stage-link.json").write_text(
            json.dumps(
                {
                    "format": "finiq_stage_link_v1",
                    "schema_version": 1,
                    "target_workspace": str(target_root),
                }
            ),
            encoding="utf-8",
        )

    result = build_disclosure_graph_payload({"data_root": str(data_root)})

    assert result["source_modes"] == ["rights_issuance"]
    assert (data_root / "09-disclosure-graph" / "disclosure-graph.json").is_file()


def test_build_disclosure_graph_payload_rejects_incomplete_mode(
    tmp_path: Path,
) -> None:
    parsed_path = (
        tmp_path
        / "07-converted"
        / "bond_issuance"
        / "parsed-bond_issuance.json"
    )
    parsed_path.parent.mkdir(parents=True)
    parsed_path.write_text('{"records": []}', encoding="utf-8")

    with pytest.raises(ValueError, match="bond_issuance.*입력이 완전하지 않습니다"):
        build_disclosure_graph_payload({"data_root": str(tmp_path)})


def test_build_disclosure_graph_rejects_failed_filter_workflow(
    tmp_path: Path,
) -> None:
    _write_rights_sources(tmp_path)
    workflow_path = tmp_path / "03-filter" / "rights_issuance" / "filter.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["status"] = "failed"
    workflow["steps"]["record"] = {
        "status": "failed",
        "error": "publish failed",
    }
    workflow_path.write_text(json.dumps(workflow), encoding="utf-8")

    with pytest.raises(ValueError, match="Filter workflow is not completed"):
        build_disclosure_graph_payload({"data_root": str(tmp_path)})

    assert not (
        tmp_path / "09-disclosure-graph" / "disclosure-graph.json"
    ).exists()


def test_load_disclosure_graph_payload_returns_saved_document(tmp_path: Path) -> None:
    _write_rights_sources(tmp_path)
    build_disclosure_graph_payload({"data_root": str(tmp_path)})

    payload = load_disclosure_graph_payload({"data_root": str(tmp_path)})

    assert payload["format"] == "finiq_disclosure_graph_v2"
    assert payload["nodes"]
    assert payload["edges"]


def test_project_example_workspace_contains_only_entity_relationships() -> None:
    project_root = Path(__file__).resolve().parents[2]

    payload = load_disclosure_graph_payload(
        {"data_root": str(project_root / "examples" / "disclosure-graph-workspace")}
    )

    assert payload["metadata"]["sample"] is True
    assert {node["type"] for node in payload["nodes"]} <= {
        "Company",
        "Person",
        "Organization",
    }
    node_ids = {node["id"] for node in payload["nodes"]}
    assert all(
        edge["source"] in node_ids and edge["target"] in node_ids
        for edge in payload["edges"]
    )
    assert all(edge["properties"].get("evidence") for edge in payload["edges"])


def test_load_disclosure_graph_payload_rejects_legacy_path_metadata(
    tmp_path: Path,
) -> None:
    _write_rights_sources(tmp_path)
    build_disclosure_graph_payload({"data_root": str(tmp_path)})
    output_path = tmp_path / "09-disclosure-graph" / "disclosure-graph.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    payload["metadata"]["source_path"] = "/legacy/parsed.json"
    output_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="09단계 그래프만 다시 생성"):
        load_disclosure_graph_payload({"data_root": str(tmp_path)})


def test_disclosure_graph_routes_use_workspace_contract(tmp_path: Path) -> None:
    _write_rights_sources(tmp_path)
    client = TestClient(app)

    build_response = client.post(
        "/api/disclosures/graph/build", json={"data_root": str(tmp_path)}
    )
    load_response = client.post(
        "/api/disclosures/graph/load", json={"data_root": str(tmp_path)}
    )

    assert build_response.status_code == 200
    assert build_response.json()["source_modes"] == ["rights_issuance"]
    assert load_response.status_code == 200
    assert load_response.json()["format"] == "finiq_disclosure_graph_v2"
