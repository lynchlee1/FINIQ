"""Stage 09 disclosure relationship graph helpers."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from finiq.data.ontology_builder import (
    build_ontology_graph,
    export_ontology_to_web_json,
)
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    resolve_disclosure_workspace,
)
from finiq.market_desk.web.features.disclosures.filter_presets import (
    load_completed_filter_workflow_payload,
)

GRAPH_FORMAT = "finiq_disclosure_graph_v1"
GRAPH_OUTPUT_DIRECTORY = "09-disclosure-graph"
GRAPH_OUTPUT_FILENAME = "disclosure-graph.json"


def _workspace_root(body: dict[str, Any]) -> Path:
    value = str(body.get("data_root") or "").strip()
    if not value:
        raise ValueError("data_root is required")
    data_root = Path(value).expanduser().resolve()
    if not data_root.is_dir():
        raise ValueError(f"작업공간 디렉토리를 찾을 수 없습니다: {data_root}")
    return data_root


def _source_paths(data_root: Path) -> tuple[dict[str, Path | None], list[str]]:
    workspace = resolve_disclosure_workspace(data_root)
    source_pairs = {
        "rights_issuance": (
            workspace.converted
            / "rights_issuance"
            / "parsed-rights_issuance.json",
            workspace.filtered / "rights_issuance" / "filtered.json",
        ),
        "bond_issuance": (
            workspace.converted
            / "bond_issuance"
            / "parsed-bond_issuance.json",
            workspace.filtered / "bond_issuance" / "filtered.json",
        ),
        "shareholder_meeting": (
            workspace.converted
            / "shareholder_meeting"
            / "parsed-shareholder_meeting.json",
            workspace.filtered / "shareholder_meeting" / "filtered.json",
        ),
    }

    resolved: dict[str, Path | None] = {}
    source_modes: list[str] = []
    for mode, (parsed_path, filtered_path) in source_pairs.items():
        parsed_exists = parsed_path.is_file()
        filtered_exists = filtered_path.is_file()
        if parsed_exists != filtered_exists:
            missing_path = filtered_path if parsed_exists else parsed_path
            raise ValueError(
                f"{mode} 입력이 완전하지 않습니다. 누락 파일: {missing_path}"
            )
        if filtered_exists:
            load_completed_filter_workflow_payload(
                data_root=data_root,
                mode=mode,
            )
        resolved[f"{mode}_parsed"] = parsed_path if parsed_exists else None
        resolved[f"{mode}_filtered"] = filtered_path if filtered_exists else None
        if parsed_exists:
            source_modes.append(mode)

    if not source_modes:
        raise ValueError(
            "그래프를 생성할 수 있는 03단계 필터 결과와 07단계 파싱 결과가 없습니다."
        )
    return resolved, source_modes


def _graph_output_path(data_root: Path) -> Path:
    return data_root / GRAPH_OUTPUT_DIRECTORY / GRAPH_OUTPUT_FILENAME


def _persisted_graph_path_key(value: object, *, location: str = "graph") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if str(key) in {"path", "source_file", "source_url"} or str(key).endswith(
                "_path"
            ):
                return child_location
            found = _persisted_graph_path_key(child, location=child_location)
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _persisted_graph_path_key(
                child,
                location=f"{location}[{index}]",
            )
            if found is not None:
                return found
    return None


def build_disclosure_graph_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Build and atomically save the stage 09 graph document."""
    data_root = _workspace_root(body)
    sources, source_modes = _source_paths(data_root)
    nodes, edges, metadata = build_ontology_graph(
        rights_issuance_path=sources["rights_issuance_parsed"],
        rights_filtered_path=sources["rights_issuance_filtered"],
        bond_issuance_path=sources["bond_issuance_parsed"],
        bond_filtered_path=sources["bond_issuance_filtered"],
        shareholder_meeting_parsed_path=sources["shareholder_meeting_parsed"],
        shareholder_meeting_filtered_path=sources["shareholder_meeting_filtered"],
    )

    output_path = _graph_output_path(data_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        f".{output_path.name}.part-{uuid.uuid4().hex}"
    )
    try:
        export_ontology_to_web_json(nodes, edges, temporary_path, metadata)
        os.replace(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return {
        "format": "finiq_disclosure_graph_build_v1",
        "output_path": str(output_path),
        "source_modes": source_modes,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
    }


def load_disclosure_graph_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Load and validate the saved stage 09 graph document."""
    output_path = _graph_output_path(_workspace_root(body))
    if not output_path.is_file():
        raise FileNotFoundError(f"공시 관계 그래프를 찾을 수 없습니다: {output_path}")
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"공시 관계 그래프 JSON을 읽을 수 없습니다: {output_path}") from exc
    if not isinstance(payload, dict) or payload.get("format") != GRAPH_FORMAT:
        raise ValueError("공시 관계 그래프 데이터 형식이 올바르지 않습니다.")
    if not isinstance(payload.get("nodes"), list) or not isinstance(
        payload.get("edges"), list
    ):
        raise ValueError("공시 관계 그래프의 nodes와 edges는 배열이어야 합니다.")
    if not isinstance(payload.get("metadata"), dict):
        raise ValueError("공시 관계 그래프의 metadata는 객체여야 합니다.")
    persisted_path = _persisted_graph_path_key(payload)
    if persisted_path is not None:
        raise ValueError(
            "구형 공시 관계 그래프에 경로 metadata가 남아 있습니다. "
            f"09단계 그래프만 다시 생성하세요: {persisted_path}"
        )
    return payload
