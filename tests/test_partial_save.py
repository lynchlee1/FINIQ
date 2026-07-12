from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finiq.config import build_disclosure_workspace_path_settings
from finiq.market_desk.web.app import app, config


@pytest.fixture(autouse=True)
def restore_config():
    original = {key: getattr(config, key) for key in config.__slots__}
    yield
    for key, value in original.items():
        setattr(config, key, value)


def test_output_root_update_rebases_canonical_workflow_paths(tmp_path: Path):
    config.settings_path = str(tmp_path / "settings.json")
    keep_path = tmp_path / "keep-me.json"
    client = TestClient(app)

    response = client.post("/api/settings", json={"html_parse_result_path": str(keep_path)})
    assert response.status_code == 200

    payload = {
        "output_root": "/tmp/main-output",
        "selected_classification_path": "/tmp/main-class.json",
        "price_root_directory": "/tmp/main-price",
        "quanti_dir": "/tmp/main-quanti"
    }
    response = client.post("/api/settings", json=payload)
    assert response.status_code == 200

    resp = client.get("/api/config")
    assert resp.status_code == 200
    payload = resp.json()
    val = payload.get("html_parse_result_path")

    expected = build_disclosure_workspace_path_settings(
        "/tmp/main-output", mode=config.html_parse_mode
    )
    assert val == expected["html_parse_result_path"]
