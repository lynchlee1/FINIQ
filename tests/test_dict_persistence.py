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


def test_dict_persistence(tmp_path: Path):
    config.settings_path = str(tmp_path / "settings.json")
    payload = {
        "integrated_data_values": {
            "source_directory": "/tmp/source",
            "output_directory": "/tmp/output"
        }
    }
    client = TestClient(app)

    response = client.post("/api/settings", json=payload)
    assert response.status_code == 200
    resp = client.get("/api/config")
    assert resp.status_code == 200
    payload = resp.json()
    val = payload.get("integrated_data_values")

    assert val and val.get("source_directory") == "/tmp/source"
