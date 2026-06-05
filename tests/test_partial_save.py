import httpx
import json
import pytest

BASE_URL = "http://127.0.0.1:8765"

def test_partial_update_persistence():
    # 1. Set a field that is NOT on the main page
    print("Setting html_parse_result_path...")
    try:
        httpx.post(f"{BASE_URL}/api/settings", json={"html_parse_result_path": "/tmp/keep-me.json"})
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        pytest.skip(f"Local server is not running: {e}")
        return
        
    # 2. Simulate main page save (partial update)
    print("Simulating main page save...")
    payload = {
        "output_root": "/tmp/main-output",
        "selected_classification_path": "/tmp/main-class.json",
        "price_root_directory": "/tmp/main-price",
        "quanti_dir": "/tmp/main-quanti"
    }
    httpx.post(f"{BASE_URL}/api/settings", json=payload)
    
    # 3. Check if html_parse_result_path survived
    resp = httpx.get(f"{BASE_URL}/api/config")
    config = resp.json()
    val = config.get("html_parse_result_path")
    print(f"html_parse_result_path after main save: {val}")
    
    if val == "/private/tmp/keep-me.json":
        print("Persistence survived partial update! PASSED")
    else:
        print(f"Persistence LOST! FAILED (Expected /private/tmp/keep-me.json, got {val})")
        assert val == "/private/tmp/keep-me.json"

if __name__ == "__main__":
    test_partial_update_persistence()

