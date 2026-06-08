from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finiq.market_desk.web.app import app, config


@pytest.fixture(autouse=True)
def restore_config():
    original = {key: getattr(config, key) for key in config.__slots__}
    yield
    for key, value in original.items():
        setattr(config, key, value)


def test_partial_update_persistence(tmp_path: Path):
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

    assert val == str(keep_path.resolve())
