from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from finiq.data_scraper.parse.domain.shareholder_meeting import parse_shareholder_meeting


GOLDEN_ROOT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "shareholder_meeting"
    / "golden"
)
MANIFEST = json.loads((GOLDEN_ROOT / "manifest.json").read_text(encoding="utf-8"))
CASES = MANIFEST["cases"]

TOP_LEVEL_KEYS = {
    "metadata",
    "mode",
    "disclosure_phase",
    "meeting_date",
    "agendas",
    "agenda_items",
    "agenda_records",
    "elections",
    "director_elections",
    "outside_director_elections",
    "auditor_elections",
    "audit_committee_elections",
    "entities",
    "relationships",
    "business_purpose_changes",
}
AGENDA_KEYS = {
    "agenda_ref",
    "number",
    "title",
    "resolution_type",
    "candidate",
    "result_raw",
    "status",
    "remarks",
    "source",
    "attributes",
    "evidence",
}
ENTITY_KEYS = {"entity_ref", "entity_type", "name", "attributes", "mentions"}
RELATIONSHIP_KEYS = {
    "source_ref",
    "target_ref",
    "relationship_type",
    "attributes",
    "evidence",
}
RELATIONSHIP_TYPES = {
    "includes",
    "candidate_for",
    "elected_as",
    "removed_from",
    "resigned_from",
    "subject_of",
    "proposed",
    "serves_at",
    "option_granted_by",
    "external_auditor_of",
    "electronic_voting_manager_for",
    "electronic_voting_system_provider_for",
    "shareholder_of",
    "transferor_of",
    "transferee_of",
    "proposed_allottee_of",
    "merger_target_of",
    "acquisition_target_of",
    "divestment_target_of",
}
ACTIVE_RESULT_TYPES = {
    "elected_as",
    "removed_from",
    "resigned_from",
    "option_granted_by",
}
RELATIONSHIP_ENDPOINTS = {
    "includes": ({"meeting"}, {"agenda"}),
    "candidate_for": ({"person"}, {"company"}),
    "elected_as": ({"person"}, {"company"}),
    "removed_from": ({"person"}, {"company"}),
    "resigned_from": ({"person"}, {"company"}),
    "subject_of": ({"person", "organization"}, {"agenda"}),
    "proposed": ({"person", "organization"}, {"agenda"}),
    "serves_at": ({"person"}, {"organization", "company"}),
    "option_granted_by": ({"person"}, {"company"}),
    "external_auditor_of": ({"organization"}, {"company"}),
    "electronic_voting_manager_for": ({"organization"}, {"meeting"}),
    "electronic_voting_system_provider_for": ({"organization"}, {"meeting"}),
    "shareholder_of": ({"person", "organization"}, {"company"}),
    "transferor_of": ({"person", "organization"}, {"company"}),
    "transferee_of": ({"person", "organization"}, {"company"}),
    "proposed_allottee_of": ({"person", "organization"}, {"company"}),
    "merger_target_of": ({"organization"}, {"company", "agenda"}),
    "acquisition_target_of": ({"organization"}, {"agenda"}),
    "divestment_target_of": ({"organization"}, {"agenda"}),
}


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _has_evidence(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    raw_text = value.get("raw_text")
    if isinstance(raw_text, str) and raw_text.strip():
        return True
    return (
        isinstance(value.get("table_index"), int)
        and value["table_index"] >= 0
        and isinstance(value.get("row_index"), int)
        and value["row_index"] >= 0
    )


def _ref_kind(
    ref: str,
    *,
    entity_kinds: dict[str, str],
    agenda_refs: set[str],
) -> str | None:
    if ref == "@meeting":
        return "meeting"
    if ref == "@reporting_company":
        return "company"
    if ref in agenda_refs:
        return "agenda"
    return entity_kinds.get(ref)


def _relation_discriminator(relation: dict[str, Any]) -> str:
    attributes = relation["attributes"]
    relationship_type = relation["relationship_type"]
    if relationship_type == "subject_of":
        return str(attributes.get("action") or "")
    if relationship_type == "serves_at":
        return str(attributes.get("position") or "")
    if relationship_type == "external_auditor_of":
        return str(attributes.get("state") or "")
    return str(attributes.get("office_type") or attributes.get("action") or "")


def _assert_output_invariants(result: dict[str, Any]) -> None:
    assert set(result) == TOP_LEVEL_KEYS
    assert isinstance(result["metadata"], dict)
    assert result["mode"] in {"NOTICE", "RESULT"}
    assert result["disclosure_phase"] in {"notice", "result", "unknown"}
    assert result["meeting_date"] is None or re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", result["meeting_date"]
    )

    list_keys = TOP_LEVEL_KEYS - {"metadata", "mode", "disclosure_phase", "meeting_date"}
    assert all(isinstance(result[key], list) for key in list_keys)
    assert result["agendas"] == result["agenda_items"]
    assert result["agendas"] == [row["title"] for row in result["agenda_records"]]
    assert result["elections"] == [
        *result["director_elections"],
        *result["outside_director_elections"],
        *result["auditor_elections"],
        *result["audit_committee_elections"],
    ]

    agenda_refs: set[str] = set()
    for index, agenda in enumerate(result["agenda_records"]):
        assert set(agenda) == AGENDA_KEYS
        assert agenda["agenda_ref"] == f"agenda:{index}"
        assert agenda["agenda_ref"] not in agenda_refs
        agenda_refs.add(agenda["agenda_ref"])
        assert agenda["title"]
        assert agenda["status"] in {
            None,
            "passed",
            "rejected",
            "unresolved",
            "withdrawn",
            "not_tabled",
        }
        assert agenda["source"] in {"structured_agenda_table", "legacy_labeled_cell"}
        assert isinstance(agenda["attributes"], dict)
        assert _has_evidence(agenda["evidence"])

    expected_election_types = {
        "director": result["director_elections"],
        "outside_director": result["outside_director_elections"],
        "auditor": result["auditor_elections"],
        "audit_committee_member": result["audit_committee_elections"],
    }
    for section_type, elections in expected_election_types.items():
        assert all(row["section_type"] == section_type for row in elections)
        assert all(_has_evidence(row["evidence"]) for row in elections)

    entity_kinds: dict[str, str] = {}
    entity_keys: set[tuple[str, str, str]] = set()
    counters = {"person": 0, "organization": 0}
    for entity in result["entities"]:
        assert set(entity) == ENTITY_KEYS
        entity_type = entity["entity_type"]
        assert entity_type in counters
        assert entity["entity_ref"] == f"{entity_type}:{counters[entity_type]}"
        counters[entity_type] += 1
        assert entity["entity_ref"] not in entity_kinds
        assert entity["entity_ref"] not in agenda_refs
        assert entity["entity_ref"] not in {"@meeting", "@reporting_company"}
        entity_kinds[entity["entity_ref"]] = entity_type
        assert entity["name"]
        assert isinstance(entity["attributes"], dict)
        assert entity["mentions"] and all(_has_evidence(item) for item in entity["mentions"])
        entity_key = (
            entity_type,
            re.sub(r"\s+", "", entity["name"]).casefold(),
            str(entity["attributes"].get("birth_month") or ""),
        )
        assert entity_key not in entity_keys
        entity_keys.add(entity_key)

    relationship_keys: set[tuple[str, str, str, str]] = set()
    for relation in result["relationships"]:
        assert set(relation) == RELATIONSHIP_KEYS
        relationship_type = relation["relationship_type"]
        assert relationship_type in RELATIONSHIP_TYPES
        assert relationship_type == relationship_type.lower()
        assert isinstance(relation["attributes"], dict)
        assert _has_evidence(relation["evidence"])
        source_kind = _ref_kind(
            relation["source_ref"],
            entity_kinds=entity_kinds,
            agenda_refs=agenda_refs,
        )
        target_kind = _ref_kind(
            relation["target_ref"],
            entity_kinds=entity_kinds,
            agenda_refs=agenda_refs,
        )
        expected_source_kinds, expected_target_kinds = RELATIONSHIP_ENDPOINTS[
            relationship_type
        ]
        assert source_kind in expected_source_kinds
        assert target_kind in expected_target_kinds
        relationship_key = (
            relation["source_ref"],
            relation["target_ref"],
            relationship_type,
            _relation_discriminator(relation),
        )
        assert relationship_key not in relationship_keys
        relationship_keys.add(relationship_key)
        if relationship_type in ACTIVE_RESULT_TYPES:
            assert result["disclosure_phase"] == "result"
            assert relation["attributes"].get("outcome") == "passed"

    for change in result["business_purpose_changes"]:
        assert {"category", "reason", "evidence"} <= set(change)
        assert _has_evidence(change["evidence"])
        if change["category"] == "사업목적 변경":
            assert {"before", "after"} <= set(change)
        else:
            assert "content" in change


def _entity_matches(entity: dict[str, Any], assertion: dict[str, Any]) -> bool:
    return entity["name"] == assertion["name"] and (
        "entity_type" not in assertion
        or entity["entity_type"] == assertion["entity_type"]
    )


def _relation_matches(
    relation: dict[str, Any],
    assertion: dict[str, Any],
    *,
    entities_by_ref: dict[str, dict[str, Any]],
    agendas_by_ref: dict[str, dict[str, Any]],
) -> bool:
    if relation["relationship_type"] != assertion["relationship_type"]:
        return False
    if "source_ref" in assertion and relation["source_ref"] != assertion["source_ref"]:
        return False
    if "target_ref" in assertion and relation["target_ref"] != assertion["target_ref"]:
        return False
    if "source_name" in assertion:
        source = entities_by_ref.get(relation["source_ref"])
        if source is None or source["name"] != assertion["source_name"]:
            return False
        if "source_type" in assertion and source["entity_type"] != assertion["source_type"]:
            return False
    if "target_name" in assertion or "target_type" in assertion:
        target = entities_by_ref.get(relation["target_ref"])
        if target is None:
            return False
        if "target_name" in assertion and target["name"] != assertion["target_name"]:
            return False
        if "target_type" in assertion and target["entity_type"] != assertion["target_type"]:
            return False
    if "target_title_contains" in assertion:
        target = agendas_by_ref.get(relation["target_ref"])
        if target is None or assertion["target_title_contains"] not in target["title"]:
            return False
    if not all(
        relation["attributes"].get(key) == value
        for key, value in assertion.get("attributes_subset", {}).items()
    ):
        return False
    return all(
        relation["evidence"].get(key) == value
        for key, value in assertion.get("evidence_subset", {}).items()
    )


def _assert_case_expectations(result: dict[str, Any], case: dict[str, Any]) -> None:
    assertions = case["assertions"]
    assert result["mode"] == assertions["mode"]
    assert result["disclosure_phase"] == assertions["disclosure_phase"]
    for agenda_assertion in assertions.get("agendas_include", []):
        matches = [
            agenda
            for agenda in result["agenda_records"]
            if (
                "number" not in agenda_assertion
                or agenda["number"] == agenda_assertion["number"]
            )
            and (
                "title_contains" not in agenda_assertion
                or agenda_assertion["title_contains"] in agenda["title"]
            )
            and (
                "status" not in agenda_assertion
                or agenda["status"] == agenda_assertion["status"]
            )
        ]
        assert matches, agenda_assertion

    for assertion in assertions["entities"]["include"]:
        assert any(_entity_matches(entity, assertion) for entity in result["entities"]), assertion
    for assertion in assertions["entities"]["exclude"]:
        assert not any(
            _entity_matches(entity, assertion) for entity in result["entities"]
        ), assertion

    entities_by_ref = {entity["entity_ref"]: entity for entity in result["entities"]}
    agendas_by_ref = {
        agenda["agenda_ref"]: agenda for agenda in result["agenda_records"]
    }
    for assertion in assertions["relationships"]["include"]:
        matches = [
            relation
            for relation in result["relationships"]
            if _relation_matches(
                relation,
                assertion,
                entities_by_ref=entities_by_ref,
                agendas_by_ref=agendas_by_ref,
            )
        ]
        assert len(matches) >= assertion.get("min_count", 1), assertion
    for assertion in assertions["relationships"]["exclude"]:
        assert not any(
            _relation_matches(
                relation,
                assertion,
                entities_by_ref=entities_by_ref,
                agendas_by_ref=agendas_by_ref,
            )
            for relation in result["relationships"]
        ), assertion


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["acpt_no"])
def test_shareholder_meeting_receipt_golden(case: dict[str, Any]) -> None:
    source = case["source"]
    external_path = GOLDEN_ROOT / source["external_fixture"]
    internal_path = GOLDEN_ROOT / source["internal_fixture"]
    external_html = external_path.read_bytes()
    internal_html = internal_path.read_bytes()

    assert _sha256(external_html) == source["external_sha256"]
    assert _sha256(internal_html) == source["internal_sha256"]
    first = parse_shareholder_meeting(external_html, internal_html)
    second = parse_shareholder_meeting(external_html, internal_html)
    first_bytes = _canonical_json_bytes(first)
    assert first_bytes == _canonical_json_bytes(second)
    assert _sha256(first_bytes) == case["canonical_output_sha256"]
    _assert_output_invariants(first)
    _assert_case_expectations(first, case)


def test_shareholder_meeting_golden_adjudication_artifact() -> None:
    artifact_path = GOLDEN_ROOT / MANIFEST["adjudication_artifact"]
    prompt_path = GOLDEN_ROOT / MANIFEST["adjudication_prompt"]
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert _sha256(artifact_path.read_bytes()) == MANIFEST[
        "adjudication_artifact_sha256"
    ]
    assert artifact["method"] == "Codex multi-agent document adjudication"
    assert artifact["performed_on"] == "2026-08-13"
    assert artifact["model_identity"] == "unavailable to repository"
    assert artifact["runtime_llm_dependency"] is False
    assert artifact["prompt_sha256"] == _sha256(prompt_path.read_bytes())
    assert {case["acpt_no"] for case in artifact["cases"]} == {
        case["acpt_no"] for case in CASES
    }
    for case in artifact["cases"]:
        assert case["positive_labels"]
        assert case["negative_boundaries"]
        assert case["rationale"].strip()
        assert isinstance(case["disagreements"], list)
        assert case["resolution"].strip()


def test_shareholder_meeting_golden_manifest_contract() -> None:
    assert len(CASES) == 34
    assert len({case["acpt_no"] for case in CASES}) == len(CASES)
    for case in CASES:
        acpt_no = case["acpt_no"]
        year = acpt_no[:4]
        assert re.fullmatch(r"20\d{12}", acpt_no)
        assert re.fullmatch(r"[0-9a-f]{64}", case["canonical_output_sha256"])
        source = case["source"]
        assert source["external_origin"] == (
            "database/04-external-html-download/shareholder_meeting/"
            f"{year}/{acpt_no}.html"
        )
        assert source["internal_origin"] == (
            "database/05-internal-html-download/shareholder_meeting/"
            f"{year}/{acpt_no}.html"
        )
        assert source["external_fixture"] == f"sources/{acpt_no}/external.html"
        assert source["internal_fixture"] == f"sources/{acpt_no}/internal.html"
        assert re.fullmatch(r"[0-9a-f]{64}", source["external_sha256"])
        assert re.fullmatch(r"[0-9a-f]{64}", source["internal_sha256"])
        for fixture_key in ("external_fixture", "internal_fixture"):
            fixture_path = (GOLDEN_ROOT / source[fixture_key]).resolve()
            fixture_path.relative_to(GOLDEN_ROOT.resolve())
            assert fixture_path.is_file()
        assertions = case["assertions"]
        assert set(assertions["entities"]) == {"include", "exclude"}
        assert set(assertions["relationships"]) == {"include", "exclude"}
