from __future__ import annotations

import json
from pathlib import Path
from fastapi.testclient import TestClient
from finiq.market_desk.web.app import app, config
from finiq.config import AppConfig

def test_api_config(tmp_path: Path):
    # Setup mock config
    config.output_root = str(tmp_path)
    config.quanti_dir = str(tmp_path)
    
    client = TestClient(app)
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "output_root" in data
    assert "quanti_dir" in data

def test_api_settings(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    config.settings_path = str(settings_path)
    
    client = TestClient(app)
    response = client.post("/api/settings", json={
        "output_root": str(tmp_path / "new_root"),
    })
    assert response.status_code == 200
    data = response.json()
    assert data["output_root"] == str((tmp_path / "new_root").resolve())
    assert settings_path.exists()

def test_api_classifications(tmp_path: Path):
    # Create a dummy classification file
    kind_dir = tmp_path / "classification"
    kind_dir.mkdir(parents=True)
    # The name must contain 'company_classification' to be found
    (kind_dir / "test.company_classification.json").write_text("[]")
    
    config.output_root = str(tmp_path)
    
    client = TestClient(app)
    response = client.get("/api/classifications")
    assert response.status_code == 200
    data = response.json()
    assert any("test.company_classification.json" in f["name"] for f in data["classification_files"])

def test_api_price_sources(tmp_path: Path):
    price_root = tmp_path / "price_root"
    price_root.mkdir()
    price_dir = price_root / "test_price_folder"
    price_dir.mkdir()
    # Must have a parquet file to be considered a price directory
    (price_dir / "item.parquet").write_bytes(b"")
    
    # Mock config - the default root is parent of quanti_dir
    config.quanti_dir = str(price_root / "database" / "by_item")
    (price_root / "database" / "by_item").parent.mkdir(parents=True)
    
    client = TestClient(app)
    # We pass root_directory explicitly to be sure
    response = client.get(f"/api/price-sources?root_directory={price_root}")
    assert response.status_code == 200
    data = response.json()
    assert any("test_price_folder" in f["name"] for f in data["price_files"])
