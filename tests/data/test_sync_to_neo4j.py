import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

# Inject mock neo4j module to sys.modules before importing the script
# This allows test to run even in environments where neo4j driver is not installed
mock_neo4j = MagicMock()
sys.modules["neo4j"] = mock_neo4j

# Add project root to path to allow importing from scripts folder
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.sync_to_neo4j import main

def test_sync_to_neo4j_script(tmp_path: Path):
    # Configure mock GraphDatabase
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session
    
    # We mock APOC query to return no APOC to trigger simpler queries
    def mock_run(query, *args, **kwargs):
        if "apoc.version" in query:
            raise Exception("APOC not installed")
        return MagicMock()
    mock_session.run.side_effect = mock_run

    # Set mock_neo4j behaviors
    mock_neo4j.GraphDatabase.driver.return_value = mock_driver

    # Mock file input
    graph_data = {
        "nodes": [
            {
                "id": "company_005930",
                "label": "삼성전자",
                "type": "Company",
                "group": "Company",
                "tags": ["Company"],
                "properties": {"stock_code": "005930"}
            }
        ],
        "edges": [
            {
                "id": "edge_1",
                "source": "company_005930",
                "target": "company_005930",
                "relation": "EXECUTED",
                "category": "EXECUTED",
                "weight": 1.0,
                "directed": True,
                "properties": {}
            }
        ]
    }
    
    mock_json_file = tmp_path / "mock_web_graph.json"
    mock_json_file.write_text(json.dumps(graph_data), encoding="utf-8")

    # Patch sys.argv
    test_args = [
        "sync_to_neo4j.py",
        "--input", str(mock_json_file),
        "--uri", "bolt://test-uri:7687",
        "--username", "neo4j_test",
        "--password", "pwd_test",
        "--batch-size", "10"
    ]
    
    with patch("sys.argv", test_args):
        main()
        
        # Verify connection was constructed with expected args
        mock_neo4j.GraphDatabase.driver.assert_called_once_with("bolt://test-uri:7687", auth=("neo4j_test", "pwd_test"))
        
        # Verify driver verification occurred
        mock_driver.verify_connectivity.assert_called_once()
        
        # Verify queries were run
        assert mock_session.run.call_count >= 3
        # Constraint creation query should have been executed
        constraint_calls = [
            call for call in mock_session.run.call_args_list 
            if "CREATE CONSTRAINT" in call[0][0]
        ]
        assert len(constraint_calls) == 1
        node_import_queries = [
            call[0][0]
            for call in mock_session.run.call_args_list
            if "MERGE (n:Entity {id: row.id})" in call[0][0]
        ]
        assert node_import_queries
        assert all("COALESCE(row.riskLevel" not in query for query in node_import_queries)
