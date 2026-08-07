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
                "agendas": [
                    "제1호 의안: 이사 선임의 건"
                ],
                "elections": [
                    {
                        "candidate_name": "강감찬",
                        "role": "사내이사",
                        "is_outside": False
                    }
                ]
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
    
    director_edges = [e for e in edges if e.edge_type == EdgeTypes.DIRECTOR_OF]
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



def test_shareholder_meeting_no_title(tmp_path):
    import json
    from finiq.data.ontology_builder import build_ontology_graph, export_ontology_to_web_json

    # Create temporary files
    filtered_path = tmp_path / "shareholder_meeting_filtered.json"
    parsed_path = tmp_path / "shareholder_meeting_parsed.json"

    # Filtered disclosure with NO title key
    filtered_data = {
        "disclosures": [
            {
                "acpt_no": "2026000001",
                "company_id": "022180",
                "company_name": "NoTitleCo",
                "disclosed_date": "2026-01-01"
            }
        ]
    }
    with open(filtered_path, "w", encoding="utf-8") as f:
        json.dump(filtered_data, f)

    # Empty parsed details
    parsed_data = {"records": []}
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

    # Verify nodes and labels
    web_nodes = web_data["nodes"]
    assert any(n["id"] == "shareholder_meeting_2026000001" for n in web_nodes)
    meeting_node = next(n for n in web_nodes if n["id"] == "shareholder_meeting_2026000001")
    assert meeting_node["label"] == "주주총회"
    assert meeting_node["properties"]["meeting_type"] == "주주총회"
