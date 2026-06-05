from __future__ import annotations

import json
from pathlib import Path
from finiq.config import save_settings, load_settings, SAVED_SETTINGS_KEYS

def test_settings_save_and_load(tmp_path: Path):
    settings_path = tmp_path / "appdata.json"
    payload = {"html_parse_result_path": "/tmp/my-result.json"}
    
    # Save using the refactored utility
    save_settings(settings_path, payload)
    
    # Load using the refactored utility
    loaded = load_settings(settings_path)
    
    assert Path(loaded["html_parse_result_path"]).resolve() == Path("/tmp/my-result.json").resolve()
    
    # Verify file content
    content = json.loads(settings_path.read_text(encoding="utf-8"))
    assert content["html_parse_result_path"] == "/tmp/my-result.json"
