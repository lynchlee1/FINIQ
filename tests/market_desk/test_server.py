from __future__ import annotations

import json
from fastapi.testclient import TestClient
from finiq.market_desk.web.app import app

def test_settings_api_endpoint():
    client = TestClient(app)
    payload = {"html_parse_result_path": "/test/path/my-file.json"}
    
    response = client.post("/api/settings", json=payload)
    
    # The API returns the updated config, which should include the new path
    assert response.status_code == 200
    data = response.json()
    assert data["html_parse_result_path"].endswith("my-file.json")
