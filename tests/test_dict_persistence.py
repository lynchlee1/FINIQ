import httpx
import json
import pytest

BASE_URL = "http://127.0.0.1:8765"

def test_dict_persistence():
    print("Setting integrated_data_values...")
    payload = {
        "integrated_data_values": {
            "source_directory": "/tmp/source",
            "output_directory": "/tmp/output"
        }
    }
    try:
        httpx.post(f"{BASE_URL}/api/settings", json=payload)
        resp = httpx.get(f"{BASE_URL}/api/config")
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        pytest.skip(f"Local server is not running: {e}")
        return

    config = resp.json()
    val = config.get("integrated_data_values")
    print(f"integrated_data_values: {val}")
    
    if val and val.get("source_directory") == "/tmp/source":
        print("Dict persistence PASSED")
    else:
        print(f"Dict persistence FAILED: {val}")
        assert val and val.get("source_directory") == "/tmp/source"

if __name__ == "__main__":
    test_dict_persistence()

