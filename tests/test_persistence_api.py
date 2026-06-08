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


def test_persistence(tmp_path: Path):
    config.settings_path = str(tmp_path / "settings.json")
    client = TestClient(app)

    resp = client.get("/api/config")
    assert resp.status_code == 200

    test_path = tmp_path / "test-persistence-path.json"
    resp = client.post("/api/settings", json={"html_parse_result_path": str(test_path)})
    assert resp.status_code == 200
    assert resp.json().get("html_parse_result_path") == str(test_path.resolve())

    resp = client.get("/api/config")
    assert resp.status_code == 200
    verified_config = resp.json()
    assert verified_config.get("html_parse_result_path") == str(test_path.resolve())
