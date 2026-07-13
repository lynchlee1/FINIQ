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


def test_html_parse_output_directory_persists(tmp_path: Path):
    config.settings_path = str(tmp_path / "settings.json")
    client = TestClient(app)
    output_directory = tmp_path / "parse_output"

    resp = client.post("/api/settings", json={"html_parse_output_directory": str(output_directory)})

    assert resp.status_code == 200
    assert resp.json()["html_parse_output_directory"] == str(output_directory.resolve())

    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["html_parse_output_directory"] == str(output_directory.resolve())


def test_html_download_settings_persist(tmp_path: Path):
    config.settings_path = str(tmp_path / "settings.json")
    client = TestClient(app)

    payload = {
        "html_merge_output_path": str(tmp_path / "merged"),
        "html_content_compressed_json_path": str(tmp_path / "compressed.json"),
        "html_external_compress_input_directory": str(tmp_path / "html"),
        "html_external_compress_output_directory": str(tmp_path / "compressed"),
    }

    resp = client.post("/api/settings", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    for key, value in payload.items():
        assert data[key] == str(Path(value).resolve())

    resp = client.get("/api/config")

    assert resp.status_code == 200
    data = resp.json()
    for key, value in payload.items():
        assert data[key] == str(Path(value).resolve())


def test_html_section_split_output_directory_persists(tmp_path: Path):
    config.settings_path = str(tmp_path / "settings.json")
    client = TestClient(app)

    output_directory = tmp_path / "sections"
    resp = client.post("/api/settings", json={"html_section_split_output_directory": str(output_directory)})

    assert resp.status_code == 200
    assert resp.json()["html_section_split_output_directory"] == str(output_directory.resolve())

    resp = client.get("/api/config")

    assert resp.status_code == 200
    assert resp.json()["html_section_split_output_directory"] == str(output_directory.resolve())
