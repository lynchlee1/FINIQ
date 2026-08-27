import json
from pathlib import Path
from datetime import date
import pytest

from finiq.data.ontology_builder import (
    build_ontology_graph,
    classify_investor_type,
    normalize_company_id,
    normalize_entity_name,
    parse_date_safe,
    export_ontology_to_web_json,
)
from finiq.data.graph_models import EdgeTypes

def test_normalize_company_id():
    assert normalize_company_id("22180") == "022180"
    assert normalize_company_id("005930") == "005930"
    assert normalize_company_id("AB12C") == "AB12C"
    assert normalize_company_id("") == ""
    assert normalize_company_id(None) == ""

def test_normalize_entity_name():
    assert normalize_entity_name("(주)썬메이트홀딩스") == "썬메이트홀딩스"
    assert normalize_entity_name("더블엠인베스트먼트(주)") == "더블엠인베스트먼트"
    assert normalize_entity_name("주식회사 카카오") == "카카오"
    assert normalize_entity_name("  (주) 네이버  ") == "네이버"

def test_parse_date_safe():
    assert parse_date_safe("2026-04-30") == date(2026, 4, 30)
    assert parse_date_safe("2026-04-30 17:32") == date(2026, 4, 30)
    assert parse_date_safe("2026년 04월 30일") == date(2026, 4, 30)
    with pytest.raises(ValueError, match="Invalid ontology event date"):
        parse_date_safe("invalid")
    with pytest.raises(ValueError, match="Ontology event date is required"):
        parse_date_safe(None)


def test_build_ontology_graph_rejects_unreadable_sources(tmp_path: Path):
    missing_path = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError, match="does not exist"):
        build_ontology_graph(rights_issuance_path=missing_path)

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="Failed to read rights issuance parsed source"):
        build_ontology_graph(rights_issuance_path=invalid_path)


def test_ontology_query_rejects_unreadable_graph(tmp_path: Path, monkeypatch):
    import finiq.config
    from finiq.data.ontology_query import OntologyGraphQueryService

    missing_path = tmp_path / "missing.json"
    service = OntologyGraphQueryService(graph_json_path=missing_path)
    with pytest.raises(FileNotFoundError):
        service.load_index(force=True)

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("not-json", encoding="utf-8")
    service = OntologyGraphQueryService(graph_json_path=invalid_path)
    with pytest.raises(json.JSONDecodeError):
        service.load_index(force=True)

    fallback_path = tmp_path / "tmp" / "ontology_graph.json"
    fallback_path.parent.mkdir()
    fallback_path.write_text('{"nodes": [], "edges": []}', encoding="utf-8")
    monkeypatch.setattr(finiq.config, "PROJECT_ROOT", tmp_path)
    OntologyGraphQueryService._instance = None
    service = OntologyGraphQueryService()
    assert service.graph_json_path == tmp_path / "resources" / "ontology_graph.json"
    with pytest.raises(FileNotFoundError):
        service.load_index()

def test_classify_investor_type():
    assert classify_investor_type("홍길동") == "Person"
    assert classify_investor_type("김철수") == "Person"
    assert classify_investor_type("주식회사 에스에이치홀딩스") == "Company"
    assert classify_investor_type("(주)썬메이트홀딩스") == "Company"
    assert classify_investor_type("더블엠인베스트먼트(주)") == "Company"
    assert classify_investor_type("㈜한투오") == "Company"
    assert classify_investor_type("라아인베스트먼트㈜") == "Company"
    assert classify_investor_type("아이티씨홀딩스(유)") == "Company"
    assert classify_investor_type("MANY MERIT ENTERPRISES LTD.") == "Company"
    assert classify_investor_type("Thiel Crescendo Investments LLC") == "Company"
    assert classify_investor_type("D.E Shaw Valence Portfolios, L.L.C.") == "Company"
    assert classify_investor_type("GE CAPITAL EQUITY HOLDINGS, INC.") == "Company"
    assert classify_investor_type("CAI Global Master Fund, L.P.") == "Organization"
    assert classify_investor_type(
        "아주 좋은 벤처펀드 2.0 (업무집행조합원 아주아이비투자 주식회사)"
    ) == "Organization"
    assert classify_investor_type(
        "삼성증권 주식회사 (본건 펀드 1의 신탁업자 지위에서)"
    ) == "Organization"
    assert (
        classify_investor_type("인수자는 삼성전자 주식회사입니다")
        == "Organization"
    )
    assert classify_investor_type("김 철 순") == "Person"
    assert classify_investor_type("PAG") == "Organization"
    assert classify_investor_type("신기술투자조합 1호") == "Organization"
    assert classify_investor_type("국민연금공단") == "Organization"

def test_build_ontology_graph(tmp_path: Path):
    # Prepare Mock Rights Issuance Files
    rights_parsed = tmp_path / "parsed-rights_issuance.json"
    rights_filtered = tmp_path / "filtered-rights.json"
    
    rights_parsed_data = {
        "records": [
            {
                "acpt_no": "20260430001640",
                "title": "유상증자 결정",
                "증자유형": "유상증자",
                "신주의 종류와 수": [
                    ["보통주식", 100000],
                    ["기타주식", 0]
                ],
                "발행목적": [
                    ["운영자금", 500000000]
                ],
                "발행가액": [
                    ["보통주식", 5000]
                ],
                "증자방식": "제3자배정증자",
                "납입일": "2026년 05월 15일",
                "발행대상자": [
                    ["(주)썬메이트홀딩스", 100000],
                    ["홍길동", 5000],
                    ["소액투자1", 1000],
                    ["소액투자2", 2000],
                    ["소액투자3", 3000],
                    ["소액투자4", 4000],
                    ["소액투자5", 5000]
                ]
            }
        ]
    }
    
    rights_filtered_data = {
        "disclosures": [
            {
                "acpt_no": "20260430001640",
                "company_id": "22180",
                "company_name": "지구홀딩스",
                "market": "코스닥",
                "disclosed_date": "2026-04-30"
            }
        ]
    }
    
    rights_parsed.write_text(json.dumps(rights_parsed_data), encoding="utf-8")
    rights_filtered.write_text(json.dumps(rights_filtered_data), encoding="utf-8")

    # Prepare Mock Bond Issuance Files
    bond_parsed = tmp_path / "parsed-bond_issuance.json"
    bond_filtered = tmp_path / "filtered-bond.json"
    
    bond_parsed_data = {
        "records": [
            {
                "acpt_no": "20260501000123",
                "corp_name": "액티투오",
                "회차": "3",
                "종류": "BW",
                "발행금액": 1000000000,
                "발행목적": [
                    ["시설자금", 1000000000]
                ],
                "투자자": [
                    ["더블엠인베스트먼트(주)", 1000000000],
                    ["홍길동", 5000000]
                ]
            }
        ]
    }
    
    # We include 더블엠인베스트먼트 in the disclosures list to verify Entity Resolution!
    bond_filtered_data = {
        "disclosures": [
            {
                "acpt_no": "20260501000123",
                "company_id": "005930",
                "company_name": "액티투오",
                "market": "코스피",
                "disclosed_date": "2026-05-01"
            },
            {
                "acpt_no": "20260501000999",
                "company_id": "999999",
                "company_name": "더블엠인베스트먼트",
                "market": "코스닥",
                "disclosed_date": "2026-05-01"
            }
        ]
    }
    
    bond_parsed.write_text(json.dumps(bond_parsed_data), encoding="utf-8")
    bond_filtered.write_text(json.dumps(bond_filtered_data), encoding="utf-8")

    # Prepare Mock Shareholder Meeting File
    sh_meeting_filtered = tmp_path / "filtered-sh.json"
    sh_meeting_data = {
        "disclosures": [
            {
                "acpt_no": "20260430002086",
                "company_id": "26178",
                "company_name": "차백신연구소",
                "market": "코스닥",
                "disclosed_date": "2026-04-30",
                "title": "임시주주총회결과"
            }
        ]
    }
    sh_meeting_filtered.write_text(json.dumps(sh_meeting_data), encoding="utf-8")

    sh_meeting_parsed = tmp_path / "parsed-sh.json"
    sh_meeting_parsed_data = {
        "records": [
                {
                    "acpt_no": "20260430002086",
                    "disclosure_phase": "result",
                    "meeting_date": "2026-04-30",
                "agenda_records": [
                    {
                        "agenda_ref": "agenda:0",
                        "title": "제1호 의안: 이사 선임의 건",
                        "status": "passed",
                    }
                ],
                "entities": [
                    {
                        "entity_ref": "person:gang",
                        "entity_type": "person",
                        "name": "강감찬",
                    }
                ],
                "relationships": [
                    {
                        "source_ref": "@meeting",
                        "target_ref": "agenda:0",
                        "relationship_type": "includes",
                        "attributes": {},
                        "evidence": {"raw_text": "제1호 의안: 이사 선임의 건"},
                    },
                    {
                        "source_ref": "person:gang",
                        "target_ref": "@reporting_company",
                        "relationship_type": "elected_as",
                        "attributes": {
                            "office_type": "director",
                            "outcome": "passed",
                        },
                        "evidence": {"raw_text": "강감찬 사내이사 선임"},
                    },
                ],
            }
        ]
    }
    sh_meeting_parsed.write_text(json.dumps(sh_meeting_parsed_data), encoding="utf-8")

    # Build graph
    nodes, edges, metadata = build_ontology_graph(
        rights_issuance_path=rights_parsed,
        rights_filtered_path=rights_filtered,
        bond_issuance_path=bond_parsed,
        bond_filtered_path=bond_filtered,
        shareholder_meeting_filtered_path=sh_meeting_filtered,
        shareholder_meeting_parsed_path=sh_meeting_parsed,
    )

    # 1. Verify Company Nodes
    assert "company_022180" in nodes
    assert nodes["company_022180"].name == "지구홀딩스"
    assert nodes["company_022180"].stock_code == "022180"
    
    assert "company_005930" in nodes
    assert nodes["company_005930"].name == "액티투오"
    
    assert "company_026178" in nodes
    assert nodes["company_026178"].name == "차백신연구소"

    # 2. Verify Entity Resolution (더블엠인베스트먼트(주) merged with company_999999)
    assert "company_999999" in nodes
    assert nodes["company_999999"].name == "더블엠인베스트먼트(주)"
    
    # 3. Verify Homonym Disambiguation (홍길동 scoped to company 022180)
    assert "person_022180_홍길동" in nodes
    assert nodes["person_022180_홍길동"].properties["scoped_company"] == "022180"

    # 4. Verify Unlisted Company Investor (썬메이트홀딩스)
    assert "company_inv_썬메이트홀딩스" in nodes
    
    # 5. Verify Shareholder Meeting Parsed details
    assert "agenda_20260430002086_0" in nodes
    assert nodes["agenda_20260430002086_0"].title == "제1호 의안: 이사 선임의 건"
    
    assert "person_026178_강감찬" in nodes
    assert nodes["person_026178_강감찬"].name == "강감찬"
    
    director_edges = [e for e in edges if e.edge_type == EdgeTypes.ELECTED_AS]
    assert len(director_edges) == 1
    assert director_edges[0].source_id == "person_026178_강감찬"
    assert director_edges[0].target_id == "company_026178"
    
    # 6. Export to Web JSON
    out_web_json = tmp_path / "web_ontology.json"
    export_ontology_to_web_json(nodes, edges, out_web_json, metadata)
    
    assert out_web_json.exists()
    web_data = json.loads(out_web_json.read_text(encoding="utf-8"))
    assert "metadata" in web_data
    assert web_data["metadata"]["total_nodes"] > 0
    assert "nodes" in web_data
    assert "edges" in web_data
    
    # Verify that edges contain explainability evidence
    for edge in web_data["edges"]:
        # Verify evidence block exists
        assert "evidence" in edge["properties"]
        evidence = edge["properties"]["evidence"]
        assert "document_title" in evidence
        assert "acpt_no" in evidence
        assert "source_file" in evidence

    # 6. Verify OntologyGraphQueryService & Collapsing minor investors
    from finiq.data.ontology_query import OntologyGraphQueryService
    
    query_service = OntologyGraphQueryService(graph_json_path=out_web_json)
    assert query_service.load_index(force=True) is True
    
    # Traversal at depth 3 without collapsing
    subgraph_no_collapse = query_service.get_neighborhood(
        company_id="022180", depth=3, collapse_minor_threshold=0
    )
    # Counts are high because all minor investors are present
    assert len(subgraph_no_collapse["nodes"]) >= 8

    # Traversal at depth 3 with collapsing (threshold = 2 minor investors)
    subgraph_collapsed = query_service.get_neighborhood(
        company_id="022180", depth=3, collapse_minor_threshold=2
    )
    
    # Verify minor investors are collapsed
    sub_node_ids = {node["id"] for node in subgraph_collapsed["nodes"]}
    # Top 3 minor investors + 썬메이트홀딩스 + 홍길동 should be kept, rest collapsed
    assert "collapsed_investors_security_20260430001640_보통주식" in sub_node_ids
    # Virtual node has properties containing count and total weight
    collapsed_node = next(n for n in subgraph_collapsed["nodes"] if n["id"] == "collapsed_investors_security_20260430001640_보통주식")
    assert collapsed_node["properties"]["is_collapsed"] is True
    assert collapsed_node["properties"]["count"] == 4 # 4 minor investors collapsed

    # 7. Verify Temporal Filtering (As-of Date)
    # Rights issuance is disclosed_date 2026-04-30. If we query as-of 2026-04-29, we should not see the event.
    subgraph_past = query_service.get_neighborhood(
        company_id="022180", depth=3, as_of_date="2026-04-29"
    )
    # We should only find the company node because edges with date >= 2026-04-30 were filtered out
    assert len(subgraph_past["edges"]) == 0
    assert len(subgraph_past["nodes"]) == 1
    assert subgraph_past["nodes"][0]["id"] == "company_022180"

    # 8. Verify Connection Path Finder
    # Path: company_022180 -> issuance_event_20260430001640 -> security_20260430001640_보통주식 -> person_022180_홍길동
    paths = query_service.find_connection_paths(
        source_id="company_022180", target_id="person_022180_홍길동", max_depth=4
    )
    assert len(paths) > 0
    first_path = paths[0]
    path_nodes = [n["id"] for n in first_path["nodes"]]
    assert "company_022180" in path_nodes
    assert "person_022180_홍길동" in path_nodes

    # 9. Verify Control Chain Traversal
    # Trace backward for company_005930 (액티투오) -> Event -> Security -> investor (company_999999)
    chain = query_service.get_control_chain(company_id="005930")
    chain_node_ids = {node["id"] for node in chain["nodes"]}
    assert "company_005930" in chain_node_ids
    assert "company_999999" in chain_node_ids # Controlling investor resolved node
    assert any(e["relation"] == EdgeTypes.ACQUIRED for e in chain["edges"])

    # 10. Verify Homonym Query Lookup (list of matching nodes returned)
    subgraph_homonym = query_service.get_neighborhood(investor_name="홍길동", depth=1)
    homonym_node_ids = {node["id"] for node in subgraph_homonym["nodes"]}
    assert "person_022180_홍길동" in homonym_node_ids
    assert "person_005930_홍길동" in homonym_node_ids

    # 11. Verify make_relative_path helper
    from finiq.data.ontology_builder import make_relative_path
    from finiq.config import PROJECT_ROOT
    abs_sample_path = PROJECT_ROOT / "resources" / "KIND" / "test.json"
    rel_sample_path = make_relative_path(abs_sample_path)
    assert rel_sample_path == "resources/KIND/test.json"

    # 12. Verify Investor Search & Disambiguation context
    search_results = query_service.search_investors_disambiguation(query_name="홍길동")
    assert len(search_results) == 2
    res_ids = {r["id"] for r in search_results}
    assert "person_022180_홍길동" in res_ids
    assert "person_005930_홍길동" in res_ids

    # Check that each result contains rich connection context
    for res in search_results:
        assert "connections" in res
        assert len(res["connections"]) > 0
        connection = res["connections"][0]
        assert "relation" in connection
        assert "company_context" in connection
        if res["id"] == "person_022180_홍길동":
            assert connection["company_context"] == "지구홀딩스"
        elif res["id"] == "person_005930_홍길동":
            assert connection["company_context"] == "액티투오"

    # Verify empty/whitespace queries return empty results
    assert query_service.search_investors_disambiguation("") == []
    assert query_service.search_investors_disambiguation("   ") == []


def test_build_ontology_graph_skips_null_pair_rows(tmp_path: Path):
    rights_parsed = tmp_path / "parsed-rights_issuance.json"
    rights_filtered = tmp_path / "filtered-rights.json"
    bond_parsed = tmp_path / "parsed-bond_issuance.json"
    bond_filtered = tmp_path / "filtered-bond.json"
    rights_parsed.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20260430001640",
                        "title": "유상증자 결정",
                        "증자유형": "유상증자",
                        "신주의 종류와 수": None,
                        "발행목적": None,
                        "발행가액": "-",
                        "발행대상자": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    rights_filtered.write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20260430001640",
                        "company_id": "22180",
                        "company_name": "지구홀딩스",
                        "market": "코스닥",
                        "disclosed_date": "2026-04-30",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    bond_parsed.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20260501000123",
                        "corp_name": "액티투오",
                        "회차": "3",
                        "종류": "BW",
                        "발행금액": 1000000000,
                        "발행목적": None,
                        "투자자": None,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    bond_filtered.write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20260501000123",
                        "company_id": "005930",
                        "company_name": "액티투오",
                        "market": "코스피",
                        "disclosed_date": "2026-05-01",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    nodes, edges, _metadata = build_ontology_graph(
        rights_issuance_path=rights_parsed,
        rights_filtered_path=rights_filtered,
        bond_issuance_path=bond_parsed,
        bond_filtered_path=bond_filtered,
    )

    assert "company_022180" in nodes
    assert "company_005930" in nodes
    assert all(edge.edge_type != EdgeTypes.ACQUIRED for edge in edges)
    assert all(edge.edge_type != EdgeTypes.FOR_PURPOSE for edge in edges)


def test_shareholder_meeting_rejects_alternate_filtered_fields(tmp_path):
    import json
    from finiq.data.ontology_builder import build_ontology_graph, export_ontology_to_web_json

    # Create temporary files
    filtered_path = tmp_path / "shareholder_meeting_filtered.json"
    parsed_path = tmp_path / "shareholder_meeting_parsed.json"

    # Legacy aliases do not substitute for the current filtered schema.
    filtered_data = {
        "disclosures": [
            {
                "acpt_no": "2026000001",
                "company_key": "022180",
                "submitter": "NoTitleCo",
                "disclosed_at": "2026-01-01",
            }
        ]
    }
    with open(filtered_path, "w", encoding="utf-8") as f:
        json.dump(filtered_data, f)

    parsed_data = {
        "records": [
            {
                "acpt_no": "2026000001",
                "title": "정기주주총회결과",
                "meeting_date": "2026-01-02",
                "source_file": "/legacy/2026000001.html",
                "agenda_records": [],
                "entities": [],
                "relationships": [],
            }
        ]
    }
    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump(parsed_data, f)

    # Build ontology graph
    nodes, edges, metadata = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    out_web_json = tmp_path / "ontology_web.json"
    export_ontology_to_web_json(nodes, edges, out_web_json, metadata)

    with open(out_web_json, "r", encoding="utf-8") as f:
        web_data = json.load(f)

    assert not any(
        node["id"] == "shareholder_meeting_2026000001"
        for node in web_data["nodes"]
    )


def test_shareholder_alternate_company_fields_do_not_rebind_organizations(
    tmp_path: Path,
) -> None:
    filtered_path = tmp_path / "shareholder-filtered.json"
    parsed_path = tmp_path / "shareholder-parsed.json"
    filtered_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20260000000001",
                        "company_id": "111111",
                        "company_name": "정상회사",
                        "disclosed_date": "2026-01-01",
                        "title": "정기주주총회결과",
                    },
                    {
                        "acpt_no": "20260000000002",
                        "company_key": "222222",
                        "submitter": "대체필드회사",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    parsed_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20260000000001",
                        "disclosure_phase": "result",
                        "meeting_date": "2026-01-02",
                        "agenda_records": [],
                        "entities": [
                            {
                                "entity_ref": "organization:0",
                                "entity_type": "organization",
                                "name": "대체필드회사",
                            }
                        ],
                        "relationships": [],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    nodes, _, _ = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    assert "org_대체필드회사" in nodes
    assert "company_222222" not in nodes


def test_shareholder_meeting_semantic_entities_and_relationships(tmp_path: Path):
    filtered_path = tmp_path / "shareholder-filtered.json"
    parsed_path = tmp_path / "shareholder-parsed.json"
    filtered_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20260327002490",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2026-03-27",
                        "title": "정기주주총회결과",
                        "source_file": "/data/20260327002490.html",
                    },
                    {
                        "acpt_no": "20260327009999",
                        "company_id": "654321",
                        "company_name": "비시드파트너스",
                        "disclosed_date": "2026-03-27",
                        "title": "정기주주총회결과",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    parsed_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20260327002490",
                        "disclosure_phase": "result",
                        "meeting_date": "2026년 03월 26일",
                        "agenda_records": [
                            {
                                "agenda_ref": "agenda:0",
                                "number": "4-4",
                                "title": "사외이사 박준구 선임의 건",
                                "status": "passed",
                            },
                            {
                                "agenda_ref": "agenda:1",
                                "number": "6",
                                "title": "주식매수선택권 부여의 건",
                                "status": "passed",
                            },
                        ],
                        "entities": [
                            {
                                "entity_ref": "person:park",
                                "entity_type": "person",
                                "name": "박준구",
                                "attributes": {"birth_month": "1964년 02월"},
                                "mentions": [{"section": "사외이사선임 세부내역", "row_index": 2}],
                            },
                            {
                                "entity_ref": "person:lee",
                                "entity_type": "person",
                                "name": "이수민",
                                "attributes": {},
                                "mentions": [],
                            },
                            {
                                "entity_ref": "org:employer",
                                "entity_type": "organization",
                                "name": "비시드파트너스(주)",
                                "attributes": {},
                                "mentions": [],
                            },
                            {
                                "entity_ref": "org:unlisted-employer",
                                "entity_type": "organization",
                                "name": "외부연구원",
                                "attributes": {},
                                "mentions": [],
                            },
                            {
                                "entity_ref": "org:proposer",
                                "entity_type": "organization",
                                "name": "유진이엔티㈜",
                                "attributes": {},
                                "mentions": [],
                            },
                            {
                                "entity_ref": "org:auditor",
                                "entity_type": "organization",
                                "name": "삼일회계법인",
                                "attributes": {},
                                "mentions": [],
                            },
                            {
                                "entity_ref": "org:former-auditor",
                                "entity_type": "organization",
                                "name": "삼정회계법인",
                                "attributes": {},
                                "mentions": [],
                            },
                            {
                                "entity_ref": "org:voting-manager",
                                "entity_type": "organization",
                                "name": "KB국민은행",
                                "attributes": {},
                                "mentions": [],
                            },
                        ],
                        "relationships": [
                            {
                                "source_ref": "@meeting",
                                "target_ref": "agenda:0",
                                "relationship_type": "includes",
                                "attributes": {},
                                "evidence": {
                                    "table_index": 4,
                                    "row_index": 2,
                                    "raw_text": "사외이사 박준구 선임의 건",
                                },
                            },
                            {
                                "source_ref": "@meeting",
                                "target_ref": "agenda:1",
                                "relationship_type": "includes",
                                "attributes": {},
                                "evidence": {
                                    "table_index": 4,
                                    "row_index": 3,
                                    "raw_text": "주식매수선택권 부여의 건",
                                },
                            },
                            {
                                "source_ref": "person:park",
                                "target_ref": "@reporting_company",
                                "relationship_type": "candidate_for",
                                "attributes": {"office_type": "outside_director", "outcome": "passed"},
                                "evidence": {
                                    "table_index": 4,
                                    "row_index": 2,
                                    "raw_text": "박준구 사외이사 후보",
                                },
                            },
                            {
                                "source_ref": "person:park",
                                "target_ref": "@reporting_company",
                                "relationship_type": "elected_as",
                                "attributes": {"office_type": "outside_director", "outcome": "passed"},
                                "evidence": {
                                    "table_index": 4,
                                    "row_index": 2,
                                    "raw_text": "박준구 사외이사 선임",
                                },
                            },
                            {
                                "source_ref": "person:park",
                                "target_ref": "agenda:0",
                                "relationship_type": "subject_of",
                                "attributes": {"action": "appointment"},
                                "evidence": {
                                    "table_index": 4,
                                    "row_index": 2,
                                    "raw_text": "사외이사 박준구 선임의 건",
                                },
                            },
                            {
                                "source_ref": "org:proposer",
                                "target_ref": "agenda:0",
                                "relationship_type": "proposed",
                                "attributes": {},
                                "evidence": {
                                    "field": "remarks",
                                    "raw_text": "유진이엔티 제안",
                                },
                            },
                            {
                                "source_ref": "person:park",
                                "target_ref": "org:employer",
                                "relationship_type": "serves_at",
                                "attributes": {"position": "대표이사", "is_current": True},
                                "evidence": {
                                    "field": "other_company",
                                    "raw_text": "비시드파트너스 대표이사",
                                },
                            },
                            {
                                "source_ref": "person:park",
                                "target_ref": "org:unlisted-employer",
                                "relationship_type": "serves_at",
                                "attributes": {"position": "고문", "is_current": True},
                                "evidence": {
                                    "field": "other_company",
                                    "raw_text": "외부연구원 고문",
                                },
                            },
                            {
                                "source_ref": "person:park",
                                "target_ref": "@reporting_company",
                                "relationship_type": "serves_at",
                                "attributes": {
                                    "position": "대표이사",
                                    "is_current": True,
                                },
                                "evidence": {
                                    "field": "major_career",
                                    "raw_text": "현) 차백신연구소 대표이사",
                                },
                            },
                            {
                                "source_ref": "person:lee",
                                "target_ref": "@reporting_company",
                                "relationship_type": "option_granted_by",
                                "attributes": {"outcome": "passed"},
                                "evidence": {
                                    "field": "agenda",
                                    "raw_text": "이수민 주식매수선택권 부여",
                                },
                            },
                            {
                                "source_ref": "org:auditor",
                                "target_ref": "@reporting_company",
                                "relationship_type": "external_auditor_of",
                                "attributes": {"state": "current", "action": "appointed"},
                                "evidence": {
                                    "field": "기타 투자판단에 참고할 사항",
                                    "raw_text": "삼일회계법인 선임",
                                },
                            },
                            {
                                "source_ref": "org:former-auditor",
                                "target_ref": "@reporting_company",
                                "relationship_type": "external_auditor_of",
                                "attributes": {"state": "former", "action": "replaced"},
                                "evidence": {
                                    "field": "기타 투자판단에 참고할 사항",
                                    "raw_text": "삼정회계법인에서 변경",
                                },
                            },
                            {
                                "source_ref": "org:voting-manager",
                                "target_ref": "@meeting",
                                "relationship_type": "electronic_voting_manager_for",
                                "attributes": {
                                    "delegation_status": "planned",
                                    "services": ["electronic_voting"],
                                },
                                "evidence": {
                                    "field": "기타 투자판단에 참고할 사항",
                                    "raw_text": "KB국민은행에 관리업무 위탁",
                                },
                            },
                            {
                                "source_ref": "org:voting-manager",
                                "target_ref": "@meeting",
                                "relationship_type": "electronic_voting_system_provider_for",
                                "attributes": {"services": ["electronic_voting_system"]},
                                "evidence": {
                                    "field": "기타 투자판단에 참고할 사항",
                                    "raw_text": "KB국민은행 전자투표시스템",
                                },
                            },
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    nodes, edges, _ = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    meeting = nodes["shareholder_meeting_20260327002490"]
    assert meeting.event_date == date(2026, 3, 26)
    assert meeting.properties["disclosure_phase"] == "result"
    assert nodes["agenda_20260327002490_0"].status == "passed"
    assert "person_026178_박준구_196402" in nodes
    assert nodes["person_026178_박준구_196402"].properties["mentions"][0]["row_index"] == 2
    assert "person_026178_이수민" in nodes
    assert "company_654321" in nodes
    assert "org_외부연구원" in nodes
    assert "org_유진이엔티" in nodes

    semantic_types = {
        edge.edge_type
        for edge in edges
        if edge.properties.get("acpt_no") == "20260327002490"
    }
    assert {
        EdgeTypes.CANDIDATE_FOR,
        EdgeTypes.ELECTED_AS,
        EdgeTypes.SUBJECT_OF,
        EdgeTypes.SERVES_AT,
        EdgeTypes.EXTERNAL_AUDITOR_OF,
    } <= semantic_types
    assert "ELECTRONIC_VOTING_MANAGER_FOR" not in semantic_types
    assert "ELECTRONIC_VOTING_SYSTEM_PROVIDER_FOR" not in semantic_types
    includes = [
        edge
        for edge in edges
        if edge.edge_type == EdgeTypes.INCLUDES
        and edge.source_id == "shareholder_meeting_20260327002490"
    ]
    assert {edge.target_id for edge in includes} == {
        "agenda_20260327002490_0",
        "agenda_20260327002490_1",
    }
    serves_at = [edge for edge in edges if edge.edge_type == EdgeTypes.SERVES_AT]
    assert {edge.target_id for edge in serves_at} == {
        "company_026178",
        "company_654321",
        "org_외부연구원",
    }
    elected = next(edge for edge in edges if edge.edge_type == EdgeTypes.ELECTED_AS)
    assert elected.is_active is True
    assert elected.start_date == date(2026, 3, 26)
    assert elected.properties["evidence"]["details"]["table_index"] == 4
    assert elected.properties["evidence"]["details"]["row_index"] == 2
    external_auditors = [
        edge for edge in edges if edge.edge_type == EdgeTypes.EXTERNAL_AUDITOR_OF
    ]
    assert {edge.properties["state"]: edge.is_active for edge in external_auditors} == {
        "current": True,
        "former": False,
    }
    assert all(edge.start_date is None for edge in external_auditors)


def test_shareholder_meeting_notice_never_creates_active_office_relation(tmp_path: Path):
    filtered_path = tmp_path / "shareholder-filtered.json"
    parsed_path = tmp_path / "shareholder-parsed.json"
    filtered_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20260311000932",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2026-03-11",
                        "title": "정기주주총회소집결의",
                    },
                    {
                        "acpt_no": "20260311000933",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2026-03-11",
                        "title": "임시주주총회소집공고",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    parsed_path.write_text(
        json.dumps(
            {
                "records": [
                            {
                                "acpt_no": "20260311000932",
                                "disclosure_phase": "notice",
                                "meeting_date": "2026-03-27",
                            "agenda_records": [],
                            "entities": [
                            {
                                "entity_ref": "person:choi",
                                "entity_type": "person",
                                "name": "최종학",
                                "attributes": {"birth_month": "1967년 02월"},
                                "mentions": [],
                            }
                        ],
                        "relationships": [
                            {
                                "source_ref": "person:choi",
                                "target_ref": "@reporting_company",
                                "relationship_type": "candidate_for",
                                "attributes": {"office_type": "outside_director"},
                                "evidence": {
                                    "field": "후보자",
                                    "raw_text": "최종학 사외이사 후보",
                                },
                            },
                            {
                                "source_ref": "person:choi",
                                "target_ref": "@reporting_company",
                                "relationship_type": "elected_as",
                                "attributes": {"outcome": "passed"},
                                "evidence": {},
                            },
                        ],
                    },
                        {
                            "acpt_no": "20260311000933",
                            "meeting_date": "2026-03-28",
                            "elections": [{"name": "유호선", "section_type": "outside_director"}],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    nodes, edges, _ = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    assert "person_026178_최종학_196702" in nodes
    assert any(edge.edge_type == EdgeTypes.CANDIDATE_FOR for edge in edges)
    assert not any(
        edge.edge_type in {
            EdgeTypes.ELECTED_AS,
            EdgeTypes.DIRECTOR_OF,
            EdgeTypes.AUDITOR_OF,
            EdgeTypes.AUDIT_COMMITTEE_MEMBER_OF,
        }
        for edge in edges
    )
    assert "person_026178_유호선" not in nodes


def test_shareholder_missing_semantic_schema_does_not_reinterpret_raw_fields(
    tmp_path: Path,
) -> None:
    filtered_path = tmp_path / "shareholder-filtered.json"
    parsed_path = tmp_path / "shareholder-parsed.json"
    filtered_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20260109000651",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2026-01-09",
                        "title": "임시주주총회결과",
                    },
                    {
                        "acpt_no": "20260109000653",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2026-01-09",
                        "title": "임시주주총회결과",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    parsed_path.write_text(
        json.dumps(
            {
                "records": [
                        {
                            "acpt_no": "20260109000651",
                            "meeting_date": "2026-01-20",
                            "agendas": ["감사 선임의 건"],
                        "elections": [
                            {"name": "이은녕", "birth_month": "1963년 08월", "section_type": "auditor"},
                            {
                                "name": "이은석",
                                "birth_month": "1968년 03월",
                                "section_type": "audit_committee_member",
                            },
                        ],
                    },
                        {
                            "acpt_no": "20260109000653",
                            "meeting_date": "2026-01-20",
                            "agenda_records": [
                            {
                                "agenda_ref": "agenda:0",
                                "title": "감사 선임의 건",
                            }
                        ],
                        "entities": [
                            {
                                "entity_ref": "person:auditor",
                                "entity_type": "person",
                                "name": "이은녕",
                            }
                        ],
                        "elections": [
                            {
                                "name": "이은녕",
                                "birth_month": "1963년 08월",
                                "section_type": "auditor",
                            }
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    nodes, edges, _ = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    assert "company_026178" in nodes
    assert "shareholder_meeting_20260109000651" in nodes
    assert "shareholder_meeting_20260109000653" in nodes
    assert "agenda_20260109000651_0" not in nodes
    assert "agenda_20260109000653_0" not in nodes
    assert "person_026178_이은녕_196308" not in nodes
    assert "person_026178_이은석_196803" not in nodes
    assert {edge.edge_type for edge in edges} == {EdgeTypes.HELD}
    assert len(edges) == 2


def test_shareholder_phase_is_not_inferred_from_title(tmp_path: Path) -> None:
    filtered_path = tmp_path / "shareholder-filtered.json"
    parsed_path = tmp_path / "shareholder-parsed.json"
    filtered_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20260109000652",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2026-01-09",
                        "title": "임시주주총회결과",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    parsed_path.write_text(
        json.dumps(
            {
                "records": [
                        {
                            "acpt_no": "20260109000652",
                            "meeting_date": "2026-01-20",
                            "agenda_records": [],
                        "entities": [
                            {
                                "entity_ref": "person:auditor",
                                "entity_type": "person",
                                "name": "이은녕",
                            }
                        ],
                        "relationships": [
                            {
                                "source_ref": "person:auditor",
                                "target_ref": "@reporting_company",
                                "relationship_type": "candidate_for",
                                "attributes": {"office_type": "auditor"},
                                "evidence": {"raw_text": "이은녕 감사 후보"},
                            },
                            {
                                "source_ref": "person:auditor",
                                "target_ref": "@reporting_company",
                                "relationship_type": "elected_as",
                                "attributes": {
                                    "office_type": "auditor",
                                    "outcome": "passed",
                                },
                                "evidence": {"raw_text": "이은녕 감사 선임"},
                            },
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    nodes, edges, _ = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    meeting = nodes["shareholder_meeting_20260109000652"]
    assert meeting.properties["disclosure_phase"] == ""
    assert "person_026178_이은녕" in nodes
    assert any(edge.edge_type == EdgeTypes.CANDIDATE_FOR for edge in edges)
    assert not any(edge.edge_type == EdgeTypes.ELECTED_AS for edge in edges)


def test_shareholder_transaction_relationships_resolve_without_invented_dates(
    tmp_path: Path,
) -> None:
    filtered_path = tmp_path / "shareholder-filtered.json"
    parsed_path = tmp_path / "shareholder-parsed.json"
    filtered_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20260316000503",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2026-03-16",
                        "title": "정기주주총회소집결의",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    parsed_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20260316000503",
                        "disclosure_phase": "notice",
                        "meeting_date": "2026-03-31",
                        "agenda_records": [
                            {
                                "agenda_ref": "agenda:0",
                                "number": "1",
                                "title": "GeneVision 지분 인수의 건",
                            }
                        ],
                        "entities": [
                            {
                                "entity_ref": "person:seller",
                                "entity_type": "person",
                                "name": "강지연",
                                "attributes": {},
                                "mentions": [],
                            },
                            {
                                "entity_ref": "org:buyer",
                                "entity_type": "organization",
                                "name": "㈜와비사비홀딩스",
                                "attributes": {},
                                "mentions": [],
                            },
                            {
                                "entity_ref": "org:target",
                                "entity_type": "organization",
                                "name": "GeneVision",
                                "attributes": {},
                                "mentions": [],
                            },
                        ],
                        "relationships": [
                            {
                                "source_ref": "@meeting",
                                "target_ref": "agenda:0",
                                "relationship_type": "includes",
                                "attributes": {},
                                "evidence": {"raw_text": "GeneVision 지분 인수의 건"},
                            },
                            {
                                "source_ref": "person:seller",
                                "target_ref": "@reporting_company",
                                "relationship_type": "transferor_of",
                                "attributes": {"disclosure_phase": "notice"},
                                "evidence": {"raw_text": "강지연이 주식매매계약을 체결"},
                            },
                            {
                                "source_ref": "person:seller",
                                "target_ref": "@reporting_company",
                                "relationship_type": "shareholder_of",
                                "attributes": {"maximum": True, "is_current": True},
                                "evidence": {"raw_text": "최대주주인 강지연"},
                            },
                            {
                                "source_ref": "org:buyer",
                                "target_ref": "@reporting_company",
                                "relationship_type": "transferee_of",
                                "attributes": {"disclosure_phase": "notice"},
                                "evidence": {"raw_text": "㈜와비사비홀딩스와 주식매매계약"},
                            },
                            {
                                "source_ref": "org:target",
                                "target_ref": "agenda:0",
                                "relationship_type": "acquisition_target_of",
                                "attributes": {"disclosure_phase": "notice"},
                                "evidence": {"raw_text": "GeneVision 지분 인수의 건"},
                            },
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _, edges, _ = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    transaction_edges = {
        edge.edge_type: edge
        for edge in edges
        if edge.edge_type
        in {
            EdgeTypes.TRANSFEROR_OF,
            EdgeTypes.TRANSFEREE_OF,
            EdgeTypes.SHAREHOLDER_OF,
            EdgeTypes.ACQUISITION_TARGET_OF,
        }
    }
    assert set(transaction_edges) == {
        EdgeTypes.TRANSFEROR_OF,
        EdgeTypes.TRANSFEREE_OF,
        EdgeTypes.SHAREHOLDER_OF,
        EdgeTypes.ACQUISITION_TARGET_OF,
    }
    assert all(edge.start_date is None for edge in transaction_edges.values())
    assert transaction_edges[EdgeTypes.SHAREHOLDER_OF].is_active is True
    assert transaction_edges[EdgeTypes.ACQUISITION_TARGET_OF].target_id == (
        "agenda_20260316000503_0"
    )


def test_shareholder_semantic_boundary_rejects_bad_refs_and_missing_evidence(
    tmp_path: Path,
) -> None:
    filtered_path = tmp_path / "shareholder-filtered.json"
    parsed_path = tmp_path / "shareholder-parsed.json"
    filtered_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20260401000001",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2026-04-01",
                        "title": "정기주주총회결과",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    parsed_path.write_text(
        json.dumps(
            {
                "records": [
                        {
                            "acpt_no": "20260401000001",
                            "disclosure_phase": "result",
                            "meeting_date": "2026-04-01",
                        "agenda_records": [
                            {"agenda_ref": "agenda:valid", "title": "이사 선임의 건"},
                            {"agenda_ref": "agenda:duplicate", "title": "중복 의안 1"},
                            {"agenda_ref": "agenda:duplicate", "title": "중복 의안 2"},
                            {"agenda_ref": "shared:ref", "title": "교차 충돌 의안"},
                            {"agenda_ref": "@meeting", "title": "예약어 의안"},
                        ],
                        "entities": [
                            {
                                "entity_ref": "person:valid",
                                "entity_type": "person",
                                "name": "김유효",
                            },
                            {
                                "entity_ref": "person:duplicate",
                                "entity_type": "person",
                                "name": "중복일",
                            },
                            {
                                "entity_ref": "person:duplicate",
                                "entity_type": "person",
                                "name": "중복이",
                            },
                            {
                                "entity_ref": "shared:ref",
                                "entity_type": "organization",
                                "name": "충돌법인",
                            },
                            {
                                "entity_ref": "@reporting_company",
                                "entity_type": "organization",
                                "name": "예약감사법인",
                            },
                        ],
                        "relationships": [
                            {
                                "source_ref": "@meeting",
                                "target_ref": "agenda:valid",
                                "relationship_type": "includes",
                                "attributes": {},
                                "evidence": {"table_index": 1, "row_index": 0},
                            },
                            {
                                "source_ref": "person:valid",
                                "target_ref": "@reporting_company",
                                "relationship_type": "candidate_for",
                                "attributes": {},
                                "evidence": {"raw_text": "김유효 이사 후보"},
                            },
                            {
                                "source_ref": "person:valid",
                                "target_ref": "agenda:valid",
                                "relationship_type": "subject_of",
                                "attributes": {},
                                "evidence": {"field": "후보자"},
                            },
                            {
                                "source_ref": "person:valid",
                                "target_ref": "@reporting_company",
                                "relationship_type": "candidate_for",
                                "attributes": {},
                                "evidence": {},
                            },
                            {
                                "source_ref": "person:valid",
                                "target_ref": "@reporting_company",
                                "relationship_type": "candidate_for",
                                "attributes": {},
                                "evidence": {"table_index": 2},
                            },
                            {
                                "source_ref": "person:valid",
                                "target_ref": "@reporting_company",
                                "relationship_type": "candidate_for",
                                "attributes": {},
                                "evidence": {"raw_text": "   ", "field": " "},
                            },
                            {
                                "source_ref": "@meeting",
                                "target_ref": "agenda:duplicate",
                                "relationship_type": "includes",
                                "attributes": {},
                                "evidence": {"raw_text": "중복 의안"},
                            },
                            {
                                "source_ref": "person:duplicate",
                                "target_ref": "@reporting_company",
                                "relationship_type": "candidate_for",
                                "attributes": {},
                                "evidence": {"raw_text": "중복 후보"},
                            },
                            {
                                "source_ref": "shared:ref",
                                "target_ref": "agenda:valid",
                                "relationship_type": "proposed",
                                "attributes": {},
                                "evidence": {"raw_text": "교차 충돌"},
                            },
                            {
                                "source_ref": "@reporting_company",
                                "target_ref": "@reporting_company",
                                "relationship_type": "external_auditor_of",
                                "attributes": {},
                                "evidence": {"raw_text": "예약어 충돌"},
                            },
                            {
                                "source_ref": "@meeting",
                                "target_ref": "@meeting",
                                "relationship_type": "includes",
                                "attributes": {},
                                "evidence": {"raw_text": "예약어 의안"},
                            },
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    nodes, edges, _ = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    semantic_edges = [
        edge for edge in edges if edge.properties.get("acpt_no") == "20260401000001"
    ]
    assert [edge.edge_type for edge in semantic_edges].count(EdgeTypes.INCLUDES) == 0
    assert [edge.edge_type for edge in semantic_edges].count(EdgeTypes.CANDIDATE_FOR) == 1
    assert [edge.edge_type for edge in semantic_edges].count(EdgeTypes.SUBJECT_OF) == 0
    assert len(semantic_edges) == 1
    assert "person_026178_중복일" not in nodes
    assert "person_026178_중복이" not in nodes
    assert "org_충돌법인" not in nodes
    assert "org_예약감사법인" not in nodes


def test_shareholder_semantic_boundary_enforces_endpoint_kinds(tmp_path: Path) -> None:
    filtered_path = tmp_path / "shareholder-filtered.json"
    parsed_path = tmp_path / "shareholder-parsed.json"

    def relationship(
        source_ref: str,
        target_ref: str,
        relationship_type: str,
        attributes: dict | None = None,
    ) -> dict:
        return {
            "source_ref": source_ref,
            "target_ref": target_ref,
            "relationship_type": relationship_type,
            "attributes": attributes or {},
            "evidence": {"raw_text": f"{relationship_type} 근거"},
        }

    approved = {"outcome": "passed"}
    valid_relationships = [
        relationship("@meeting", "agenda:0", "includes"),
        relationship("person:p", "@reporting_company", "candidate_for"),
        relationship("person:p", "@reporting_company", "elected_as", approved),
        relationship("person:p", "@reporting_company", "removed_from", approved),
        relationship("person:p", "@reporting_company", "resigned_from", approved),
        relationship("person:p", "agenda:0", "subject_of"),
        relationship("person:p", "org:o", "serves_at"),
        relationship("org:o", "@reporting_company", "external_auditor_of"),
        relationship("person:p", "@reporting_company", "transferor_of"),
        relationship("org:o", "@reporting_company", "transferee_of"),
        relationship("org:o", "@reporting_company", "proposed_allottee_of"),
        relationship("org:o", "@reporting_company", "merger_target_of"),
        relationship("org:o", "agenda:0", "acquisition_target_of"),
        relationship("org:o", "agenda:0", "divestment_target_of"),
        relationship("person:p", "@reporting_company", "shareholder_of"),
    ]
    invalid_relationships = [
        relationship("@reporting_company", "agenda:0", "includes"),
        relationship("org:o", "@reporting_company", "candidate_for"),
        relationship("org:o", "@reporting_company", "elected_as", approved),
        relationship("org:o", "@reporting_company", "removed_from", approved),
        relationship("org:o", "@reporting_company", "resigned_from", approved),
        relationship("@meeting", "agenda:0", "subject_of"),
        relationship("@meeting", "agenda:0", "proposed"),
        relationship("org:o", "org:o", "serves_at"),
        relationship("org:o", "@reporting_company", "option_granted_by", approved),
        relationship("person:p", "@reporting_company", "external_auditor_of"),
        relationship("org:o", "@meeting", "electronic_voting_manager_for"),
        relationship("org:o", "@meeting", "electronic_voting_system_provider_for"),
        relationship("person:p", "@meeting", "electronic_voting_manager_for"),
        relationship("person:p", "@meeting", "electronic_voting_system_provider_for"),
        relationship("@meeting", "@reporting_company", "transferor_of"),
        relationship("@meeting", "@reporting_company", "transferee_of"),
        relationship("@meeting", "@reporting_company", "proposed_allottee_of"),
        relationship("person:p", "agenda:0", "merger_target_of"),
        relationship("org:o", "agenda:0", "merger_target_of"),
        relationship("org:o", "@reporting_company", "acquisition_target_of"),
        relationship("org:o", "@reporting_company", "divestment_target_of"),
        relationship("org:o", "@meeting", "acquisition_target_of"),
        relationship("org:o", "person:p", "divestment_target_of"),
        relationship("@meeting", "@reporting_company", "shareholder_of"),
    ]
    filtered_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20260401000002",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2026-04-01",
                        "title": "정기주주총회결과",
                    },
                    {
                        "acpt_no": "20260401000003",
                        "company_id": "654321",
                        "company_name": "비시드파트너스",
                        "disclosed_date": "2026-04-01",
                        "title": "정기주주총회결과",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    parsed_path.write_text(
        json.dumps(
            {
                "records": [
                        {
                            "acpt_no": "20260401000002",
                            "disclosure_phase": "result",
                            "meeting_date": "2026-04-01",
                        "agenda_records": [{"agenda_ref": "agenda:0", "title": "의안"}],
                        "entities": [
                            {
                                "entity_ref": "person:p",
                                "entity_type": "person",
                                "name": "김유효",
                            },
                            {
                                "entity_ref": "org:o",
                                "entity_type": "organization",
                                "name": "비시드파트너스(주)",
                            },
                        ],
                        "relationships": valid_relationships + invalid_relationships,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _, edges, _ = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    semantic_edges = [
        edge for edge in edges if edge.properties.get("acpt_no") == "20260401000002"
    ]
    expected_types = {
        EdgeTypes.INCLUDES,
        EdgeTypes.CANDIDATE_FOR,
        EdgeTypes.ELECTED_AS,
        EdgeTypes.REMOVED_FROM,
        EdgeTypes.RESIGNED_FROM,
        EdgeTypes.SUBJECT_OF,
        EdgeTypes.SERVES_AT,
        EdgeTypes.EXTERNAL_AUDITOR_OF,
        EdgeTypes.TRANSFEROR_OF,
        EdgeTypes.TRANSFEREE_OF,
        EdgeTypes.PROPOSED_ALLOTTEE_OF,
        EdgeTypes.MERGER_TARGET_OF,
        EdgeTypes.ACQUISITION_TARGET_OF,
        EdgeTypes.DIVESTMENT_TARGET_OF,
        EdgeTypes.SHAREHOLDER_OF,
    }
    assert {edge.edge_type for edge in semantic_edges} == expected_types
    assert len(semantic_edges) == len(expected_types)
    serves_at = next(edge for edge in semantic_edges if edge.edge_type == EdgeTypes.SERVES_AT)
    assert serves_at.target_id == "company_654321"
    transaction_targets = {
        edge.edge_type: edge.target_id
        for edge in semantic_edges
        if edge.edge_type
        in {
            EdgeTypes.MERGER_TARGET_OF,
            EdgeTypes.ACQUISITION_TARGET_OF,
            EdgeTypes.DIVESTMENT_TARGET_OF,
        }
    }
    assert transaction_targets == {
        EdgeTypes.MERGER_TARGET_OF: "company_026178",
        EdgeTypes.ACQUISITION_TARGET_OF: "agenda_20260401000002_0",
        EdgeTypes.DIVESTMENT_TARGET_OF: "agenda_20260401000002_0",
    }


def test_shareholder_termination_edges_require_passed_result_and_end_at_meeting(
    tmp_path: Path,
) -> None:
    filtered_path = tmp_path / "shareholder-filtered.json"
    parsed_path = tmp_path / "shareholder-parsed.json"
    filtered_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20260401000101",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2026-04-01",
                        "title": "임시주주총회결과",
                    },
                    {
                        "acpt_no": "20260401000102",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2026-04-01",
                        "title": "임시주주총회소집결의",
                    },
                    {
                        "acpt_no": "20260401000103",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2026-04-01",
                        "title": "임시주주총회결과",
                    },
                    *[
                        {
                            "acpt_no": f"2026040100010{suffix}",
                            "company_id": "26178",
                            "company_name": "차백신연구소",
                            "disclosed_date": "2026-04-01",
                            "title": "임시주주총회결과",
                        }
                        for suffix in range(4, 8)
                    ],
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def record(
        acpt_no: str,
        phase: str,
        outcome: str,
        *,
        attribute_name: str = "outcome",
    ) -> dict:
        return {
            "acpt_no": acpt_no,
            "disclosure_phase": phase,
            "meeting_date": "2026년 03월 31일",
            "agenda_records": [],
            "entities": [
                {
                    "entity_ref": "person:director",
                    "entity_type": "person",
                    "name": f"임원{acpt_no[-1]}",
                }
            ],
            "relationships": [
                {
                    "source_ref": "person:director",
                    "target_ref": "@reporting_company",
                    "relationship_type": relationship_type,
                    "attributes": {attribute_name: outcome},
                    "evidence": {"raw_text": f"{relationship_type} 근거"},
                }
                for relationship_type in ("removed_from", "resigned_from")
            ],
        }

    parsed_path.write_text(
        json.dumps(
            {
                "records": [
                    record("20260401000101", "result", "passed"),
                    record("20260401000102", "notice", "passed"),
                    record("20260401000103", "result", "rejected"),
                    record(
                        "20260401000104",
                        "result",
                        "passed",
                        attribute_name="status",
                    ),
                    record(
                        "20260401000105",
                        "result",
                        "passed",
                        attribute_name="result",
                    ),
                    record("20260401000106", "result", "approved"),
                    record("20260401000107", "result", "가결"),
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _, edges, _ = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    termination_edges = [
        edge
        for edge in edges
        if edge.edge_type in {EdgeTypes.REMOVED_FROM, EdgeTypes.RESIGNED_FROM}
    ]
    assert {edge.edge_type for edge in termination_edges} == {
        EdgeTypes.REMOVED_FROM,
        EdgeTypes.RESIGNED_FROM,
    }
    assert {edge.properties["acpt_no"] for edge in termination_edges} == {
        "20260401000101"
    }
    assert all(edge.start_date is None for edge in termination_edges)
    assert all(edge.end_date == date(2026, 3, 31) for edge in termination_edges)
    assert all(edge.is_active is False for edge in termination_edges)


def test_shareholder_termination_does_not_infer_missing_birth_identity(
    tmp_path: Path,
) -> None:
    filtered_path = tmp_path / "shareholder-filtered.json"
    parsed_path = tmp_path / "shareholder-parsed.json"

    def disclosure(acpt_no: str, meeting_date: str) -> dict:
        return {
            "acpt_no": acpt_no,
            "company_id": "26178",
            "company_name": "차백신연구소",
            "disclosed_date": meeting_date,
            "title": "임시주주총회결과",
        }

    def semantic_record(
        acpt_no: str,
        meeting_date: str,
        name: str,
        birth_month: str,
        relationship_type: str,
    ) -> dict:
        attributes = {"office_type": "director", "outcome": "passed"}
        person_attributes = {"birth_month": birth_month} if birth_month else {}
        return {
            "acpt_no": acpt_no,
            "disclosure_phase": "result",
            "meeting_date": meeting_date,
            "agenda_records": [],
            "entities": [
                {
                    "entity_ref": "person:director",
                    "entity_type": "person",
                    "name": name,
                    "attributes": person_attributes,
                }
            ],
            "relationships": [
                {
                    "source_ref": "person:director",
                    "target_ref": "@reporting_company",
                    "relationship_type": relationship_type,
                    "attributes": attributes,
                    "evidence": {"raw_text": f"{name} {relationship_type}"},
                }
            ],
        }

    disclosures = [
        disclosure("20220331000101", "2022-03-31"),
        disclosure("20190329000101", "2019-03-29"),
        disclosure("20200330000101", "2020-03-30"),
        disclosure("20220331000102", "2022-03-31"),
        disclosure("20220331000201", "2022-03-31"),
        disclosure("20180330000201", "2018-03-30"),
        disclosure("20190329000201", "2019-03-29"),
    ]
    records = [
        semantic_record(
            "20220331000101", "2022년 03월 31일", "홍길동", "", "removed_from"
        ),
        semantic_record(
            "20190329000101",
            "2019년 03월 29일",
            "홍길동",
            "1980년 01월",
            "elected_as",
        ),
        semantic_record(
            "20200330000101",
            "2020년 03월 30일",
            "홍길동",
            "1980년 01월",
            "elected_as",
        ),
        semantic_record(
            "20220331000102",
            "2022년 03월 31일",
            "홍길동",
            "1980년 01월",
            "elected_as",
        ),
        semantic_record(
            "20220331000201", "2022년 03월 31일", "김동명", "", "resigned_from"
        ),
        semantic_record(
            "20180330000201",
            "2018년 03월 30일",
            "김동명",
            "1970년 02월",
            "elected_as",
        ),
        semantic_record(
            "20190329000201",
            "2019년 03월 29일",
            "김동명",
            "1980년 02월",
            "elected_as",
        ),
    ]
    filtered_path.write_text(
        json.dumps({"disclosures": disclosures}, ensure_ascii=False),
        encoding="utf-8",
    )
    parsed_path.write_text(
        json.dumps({"records": records}, ensure_ascii=False),
        encoding="utf-8",
    )

    nodes, edges, _ = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    assert "person_026178_홍길동_198001" in nodes
    assert "person_026178_홍길동" in nodes
    birthless_termination = next(
        edge
        for edge in edges
        if edge.properties.get("acpt_no") == "20220331000101"
        and edge.edge_type == EdgeTypes.REMOVED_FROM
    )
    assert birthless_termination.source_id == "person_026178_홍길동"

    prior_unique_appointments = [
        edge
        for edge in edges
        if edge.properties.get("acpt_no") in {"20190329000101", "20200330000101"}
        and edge.edge_type in {EdgeTypes.DIRECTOR_OF, EdgeTypes.ELECTED_AS}
    ]
    assert len(prior_unique_appointments) == 2
    assert all(edge.end_date is None for edge in prior_unique_appointments)
    assert all(edge.is_active is True for edge in prior_unique_appointments)

    same_day_appointment = next(
        edge
        for edge in edges
        if edge.properties.get("acpt_no") == "20220331000102"
        and edge.edge_type == EdgeTypes.ELECTED_AS
    )
    assert same_day_appointment.end_date is None
    assert same_day_appointment.is_active is True

    assert {
        "person_026178_김동명",
        "person_026178_김동명_197002",
        "person_026178_김동명_198002",
    } <= nodes.keys()
    ambiguous_termination = next(
        edge
        for edge in edges
        if edge.properties.get("acpt_no") == "20220331000201"
        and edge.edge_type == EdgeTypes.RESIGNED_FROM
    )
    assert ambiguous_termination.source_id == "person_026178_김동명"
    ambiguous_appointments = [
        edge
        for edge in edges
        if edge.properties.get("acpt_no") in {"20180330000201", "20190329000201"}
        and edge.edge_type == EdgeTypes.ELECTED_AS
    ]
    assert len(ambiguous_appointments) == 2
    assert all(edge.end_date is None for edge in ambiguous_appointments)
    assert all(edge.is_active is True for edge in ambiguous_appointments)


def test_shareholder_termination_requires_exact_person_and_office_identity(
    tmp_path: Path,
) -> None:
    filtered_path = tmp_path / "shareholder-filtered.json"
    parsed_path = tmp_path / "shareholder-parsed.json"
    filtered_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20200330000701",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2020-03-30",
                        "title": "정기주주총회결과",
                    },
                    {
                        "acpt_no": "20220331000701",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2022-03-31",
                        "title": "임시주주총회결과",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    parsed_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20200330000701",
                        "disclosure_phase": "result",
                        "meeting_date": "2020년 03월 30일",
                        "agenda_records": [],
                        "entities": [
                            {
                                "entity_ref": "person:known",
                                "entity_type": "person",
                                "name": "복수직책",
                                "attributes": {"birth_month": "1980년 01월"},
                            }
                        ],
                        "relationships": [
                            {
                                "source_ref": "person:known",
                                "target_ref": "@reporting_company",
                                "relationship_type": "elected_as",
                                "attributes": {
                                    "office_type": "director",
                                    "outcome": "passed",
                                },
                                "evidence": {"raw_text": "복수직책 이사 선임"},
                            }
                        ],
                    },
                    {
                        "acpt_no": "20220331000701",
                        "disclosure_phase": "result",
                        "meeting_date": "2022년 03월 31일",
                        "agenda_records": [
                            {
                                "agenda_ref": "agenda:director",
                                "title": "이사 복수직책 해임의 건",
                                "status": "passed",
                            },
                            {
                                "agenda_ref": "agenda:auditor",
                                "title": "감사 복수직책 해임의 건",
                                "status": "passed",
                            },
                        ],
                        "entities": [
                            {
                                "entity_ref": "person:birthless",
                                "entity_type": "person",
                                "name": "복수직책",
                                "attributes": {},
                            }
                        ],
                        "relationships": [
                            {
                                "source_ref": "person:birthless",
                                "target_ref": "@reporting_company",
                                "relationship_type": "removed_from",
                                "attributes": {
                                    "office_type": "director",
                                    "outcome": "passed",
                                },
                                "evidence": {"raw_text": "복수직책 이사 해임"},
                            },
                            {
                                "source_ref": "person:birthless",
                                "target_ref": "@reporting_company",
                                "relationship_type": "removed_from",
                                "attributes": {
                                    "office_type": "auditor",
                                    "outcome": "passed",
                                },
                                "evidence": {"raw_text": "복수직책 감사 해임"},
                            },
                            {
                                "source_ref": "person:birthless",
                                "target_ref": "agenda:director",
                                "relationship_type": "subject_of",
                                "attributes": {
                                    "action": "removal",
                                    "office_types": ["director"],
                                },
                                "evidence": {"raw_text": "복수직책 이사 해임"},
                            },
                            {
                                "source_ref": "person:birthless",
                                "target_ref": "agenda:auditor",
                                "relationship_type": "subject_of",
                                "attributes": {
                                    "action": "removal",
                                    "office_types": ["auditor"],
                                },
                                "evidence": {"raw_text": "복수직책 감사 해임"},
                            },
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    nodes, edges, _ = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    born_id = "person_026178_복수직책_198001"
    birthless_id = "person_026178_복수직책"
    assert {born_id, birthless_id} <= nodes.keys()
    terminations = {
        edge.properties["office_type"]: edge
        for edge in edges
        if edge.edge_type == EdgeTypes.REMOVED_FROM
        and edge.properties.get("acpt_no") == "20220331000701"
    }
    assert terminations["director"].source_id == birthless_id
    assert terminations["auditor"].source_id == birthless_id
    subjects = [
        edge
        for edge in edges
        if edge.edge_type == EdgeTypes.SUBJECT_OF
        and edge.properties.get("acpt_no") == "20220331000701"
    ]
    assert len(subjects) == 2
    assert all(edge.source_id == birthless_id for edge in subjects)
    appointment = next(
        edge
        for edge in edges
        if edge.edge_type == EdgeTypes.ELECTED_AS
        and edge.properties.get("acpt_no") == "20200330000701"
    )
    assert appointment.source_id == born_id
    assert appointment.end_date is None
    assert appointment.is_active is True


def test_shareholder_termination_reconciliation_excludes_same_day_and_future_identity(
    tmp_path: Path,
) -> None:
    filtered_path = tmp_path / "shareholder-filtered.json"
    parsed_path = tmp_path / "shareholder-parsed.json"

    def disclosure(acpt_no: str, disclosed_date: str, title: str) -> dict:
        return {
            "acpt_no": acpt_no,
            "company_id": "26178",
            "company_name": "차백신연구소",
            "disclosed_date": disclosed_date,
            "title": title,
        }

    def record(
        acpt_no: str,
        meeting_date: str,
        name: str,
        birth_month: str,
        relationship_type: str,
        phase: str = "result",
    ) -> dict:
        return {
            "acpt_no": acpt_no,
            "disclosure_phase": phase,
            "meeting_date": meeting_date,
            "agenda_records": [],
            "entities": [
                {
                    "entity_ref": "person:subject",
                    "entity_type": "person",
                    "name": name,
                    "attributes": (
                        {"birth_month": birth_month} if birth_month else {}
                    ),
                }
            ],
            "relationships": [
                {
                    "source_ref": "person:subject",
                    "target_ref": "@reporting_company",
                    "relationship_type": relationship_type,
                    "attributes": {
                        "office_type": "director",
                        "outcome": "passed",
                    },
                    "evidence": {"raw_text": f"{name} {relationship_type}"},
                }
            ],
        }

    filtered_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    disclosure("20200330000301", "2020-03-30", "정기주주총회결과"),
                    disclosure("20220331000301", "2022-03-31", "임시주주총회결과"),
                    disclosure("20230330000301", "2023-03-30", "정기주주총회소집결의"),
                    disclosure("20220331000401", "2022-03-31", "임시주주총회결과"),
                    disclosure("20230330000401", "2023-03-30", "정기주주총회결과"),
                    disclosure("20220331000601", "2022-03-31", "임시주주총회결과"),
                    disclosure("20220331000602", "2022-03-31", "임시주주총회결과"),
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    parsed_path.write_text(
        json.dumps(
            {
                "records": [
                    record(
                        "20200330000301",
                        "2020년 03월 30일",
                        "미래후보",
                        "",
                        "elected_as",
                    ),
                    record(
                        "20220331000301",
                        "2022년 03월 31일",
                        "미래후보",
                        "",
                        "removed_from",
                    ),
                    record(
                        "20230330000301",
                        "2023년 03월 30일",
                        "미래후보",
                        "1975년 05월",
                        "candidate_for",
                        "notice",
                    ),
                    record(
                        "20220331000401",
                        "2022년 03월 31일",
                        "미래선임",
                        "",
                        "resigned_from",
                    ),
                    record(
                        "20230330000401",
                        "2023년 03월 30일",
                        "미래선임",
                        "1980년 08월",
                        "elected_as",
                    ),
                    record(
                        "20220331000601",
                        "2022년 03월 31일",
                        "동일일교체",
                        "",
                        "removed_from",
                    ),
                    record(
                        "20220331000602",
                        "2022년 03월 31일",
                        "동일일교체",
                        "1980년 01월",
                        "elected_as",
                    ),
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    nodes, edges, _ = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    assert {
        "person_026178_미래후보",
        "person_026178_미래후보_197505",
        "person_026178_미래선임",
        "person_026178_미래선임_198008",
        "person_026178_동일일교체",
        "person_026178_동일일교체_198001",
    } <= nodes.keys()
    prior_birthless_appointment = next(
        edge
        for edge in edges
        if edge.properties.get("acpt_no") == "20200330000301"
        and edge.edge_type == EdgeTypes.ELECTED_AS
    )
    prior_birthless_termination = next(
        edge
        for edge in edges
        if edge.properties.get("acpt_no") == "20220331000301"
        and edge.edge_type == EdgeTypes.REMOVED_FROM
    )
    assert prior_birthless_appointment.source_id == "person_026178_미래후보"
    assert prior_birthless_termination.source_id == "person_026178_미래후보"
    assert prior_birthless_appointment.end_date == date(2022, 3, 31)
    assert prior_birthless_appointment.is_active is False

    future_only_termination = next(
        edge
        for edge in edges
        if edge.properties.get("acpt_no") == "20220331000401"
        and edge.edge_type == EdgeTypes.RESIGNED_FROM
    )
    future_appointment = next(
        edge
        for edge in edges
        if edge.properties.get("acpt_no") == "20230330000401"
        and edge.edge_type == EdgeTypes.ELECTED_AS
    )
    assert future_only_termination.source_id == "person_026178_미래선임"
    assert future_appointment.source_id == "person_026178_미래선임_198008"
    assert future_appointment.end_date is None
    assert future_appointment.is_active is True

    same_day_termination = next(
        edge
        for edge in edges
        if edge.properties.get("acpt_no") == "20220331000601"
        and edge.edge_type == EdgeTypes.REMOVED_FROM
    )
    same_day_appointment = next(
        edge
        for edge in edges
        if edge.properties.get("acpt_no") == "20220331000602"
        and edge.edge_type == EdgeTypes.ELECTED_AS
    )
    assert same_day_termination.source_id == "person_026178_동일일교체"
    assert same_day_appointment.source_id == "person_026178_동일일교체_198001"
    assert same_day_appointment.end_date is None
    assert same_day_appointment.is_active is True


def test_shareholder_lifecycle_edges_require_explicit_meeting_date(
    tmp_path: Path,
) -> None:
    filtered_path = tmp_path / "shareholder-filtered.json"
    parsed_path = tmp_path / "shareholder-parsed.json"
    filtered_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20200330000501",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2020-03-30",
                        "title": "정기주주총회결과",
                    },
                    {
                        "acpt_no": "20220401000501",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2022-04-01",
                        "title": "임시주주총회결과",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    parsed_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "acpt_no": "20200330000501",
                        "disclosure_phase": "result",
                        "meeting_date": "2020년 03월 30일",
                        "agenda_records": [],
                        "entities": [
                            {
                                "entity_ref": "person:director",
                                "entity_type": "person",
                                "name": "무일종료일",
                                "attributes": {"birth_month": "1970년 01월"},
                            }
                        ],
                        "relationships": [
                            {
                                "source_ref": "person:director",
                                "target_ref": "@reporting_company",
                                "relationship_type": "elected_as",
                                "attributes": {
                                    "office_type": "director",
                                    "outcome": "passed",
                                },
                                "evidence": {"raw_text": "무일종료일 선임"},
                            }
                        ],
                    },
                    {
                        "acpt_no": "20220401000501",
                        "disclosure_phase": "result",
                        "agenda_records": [],
                        "entities": [
                            {
                                "entity_ref": "person:director",
                                "entity_type": "person",
                                "name": "무일종료일",
                                "attributes": {"birth_month": "1970년 01월"},
                            },
                            {
                                "entity_ref": "org:voting",
                                "entity_type": "organization",
                                "name": "예탁결제원",
                            },
                        ],
                        "relationships": [
                            {
                                "source_ref": "person:director",
                                "target_ref": "@reporting_company",
                                "relationship_type": "removed_from",
                                "attributes": {
                                    "office_type": "director",
                                    "outcome": "passed",
                                },
                                "evidence": {"raw_text": "무일종료일 해임"},
                            },
                            {
                                "source_ref": "org:voting",
                                "target_ref": "@meeting",
                                "relationship_type": "electronic_voting_manager_for",
                                "attributes": {},
                                "evidence": {"raw_text": "전자투표 관리업무 위탁"},
                            },
                            {
                                "source_ref": "org:voting",
                                "target_ref": "@meeting",
                                "relationship_type": "electronic_voting_system_provider_for",
                                "attributes": {},
                                "evidence": {"raw_text": "전자투표 시스템 제공"},
                            },
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    _, edges, _ = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    appointment = next(
        edge
        for edge in edges
        if edge.properties.get("acpt_no") == "20200330000501"
        and edge.edge_type == EdgeTypes.ELECTED_AS
    )
    assert appointment.end_date is None
    assert appointment.is_active is True
    missing_date_edges = [
        edge
        for edge in edges
        if edge.properties.get("acpt_no") == "20220401000501"
    ]
    assert missing_date_edges == []


def test_shareholder_meeting_skips_superseded_correction_records(tmp_path: Path) -> None:
    filtered_path = tmp_path / "shareholder-filtered.json"
    parsed_path = tmp_path / "shareholder-parsed.json"
    filtered_path.write_text(
        json.dumps(
            {
                "disclosures": [
                    {
                        "acpt_no": "20260301000001",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2026-03-01",
                        "title": "정기주주총회결과",
                        "has_later_correction": "true",
                    },
                    {
                        "acpt_no": "20260302000001",
                        "company_id": "26178",
                        "company_name": "차백신연구소",
                        "disclosed_date": "2026-03-02",
                        "title": "정정 정기주주총회결과",
                        "has_later_correction": "0",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    parsed_path.write_text(
        json.dumps(
            {
                "records": [
                        {
                            "acpt_no": "20260301000001",
                            "disclosure_phase": "result",
                            "meeting_date": "2026-03-01",
                        "agenda_records": [],
                        "entities": [
                            {
                                "entity_ref": "person:old",
                                "entity_type": "person",
                                "name": "구후보",
                            }
                        ],
                        "relationships": [
                            {
                                "source_ref": "person:old",
                                "target_ref": "@reporting_company",
                                "relationship_type": "elected_as",
                                "attributes": {"outcome": "passed"},
                                "evidence": {
                                    "field": "구 공시 후보자",
                                    "raw_text": "구후보 선임",
                                },
                            }
                        ],
                    },
                        {
                            "acpt_no": "20260302000001",
                            "disclosure_phase": "result",
                            "meeting_date": "2026-03-02",
                        "agenda_records": [],
                        "entities": [
                            {
                                "entity_ref": "person:new",
                                "entity_type": "person",
                                "name": "신후보",
                            }
                        ],
                        "relationships": [
                            {
                                "source_ref": "person:new",
                                "target_ref": "@reporting_company",
                                "relationship_type": "elected_as",
                                "attributes": {"outcome": "passed"},
                                "evidence": {
                                    "field": "정정 공시 후보자",
                                    "raw_text": "신후보 선임",
                                },
                            }
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    nodes, edges, metadata = build_ontology_graph(
        shareholder_meeting_filtered_path=filtered_path,
        shareholder_meeting_parsed_path=parsed_path,
    )

    coverage = metadata["source_coverage"]["shareholder_meeting"]
    assert coverage["processed_count"] == 1
    assert coverage["skipped_count"] == 1
    assert "shareholder_meeting_20260301000001" not in nodes
    assert "person_026178_구후보" not in nodes
    assert "shareholder_meeting_20260302000001" in nodes
    assert "person_026178_신후보" in nodes
    elected_edges = [edge for edge in edges if edge.edge_type == EdgeTypes.ELECTED_AS]
    assert len(elected_edges) == 1
    assert elected_edges[0].source_id == "person_026178_신후보"
    assert elected_edges[0].is_active is True
