import httpx
import json

BASE_URL = "http://127.0.0.1:8765"

def test_persistence():
    # 1. Get initial config
    print("Fetching initial config...")
    try:
        resp = httpx.get(f"{BASE_URL}/api/config")
        if resp.status_code != 200:
            print(f"Error: {resp.status_code}")
            return
        initial_config = resp.json()
        print(f"Initial html_parse_result_path: {initial_config.get('html_parse_result_path')}")
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    # 2. Update a setting
    test_path = "/tmp/test-persistence-path.json"
    print(f"Updating html_parse_result_path to: {test_path}")
    resp = httpx.post(
        f"{BASE_URL}/api/settings",
        json={"html_parse_result_path": test_path}
    )
    if resp.status_code != 200:
        print(f"Error updating: {resp.status_code} {resp.text}")
        return
    
    updated_config = resp.json()
    print(f"Updated html_parse_result_path from response: {updated_config.get('html_parse_result_path')}")

    # 3. Verify config again
    resp = httpx.get(f"{BASE_URL}/api/config")
    verified_config = resp.json()
    print(f"Verified html_parse_result_path from GET: {verified_config.get('html_parse_result_path')}")

    if verified_config.get('html_parse_result_path') == test_path:
        print("Persistence test PASSED (in-memory)")
    else:
        print("Persistence test FAILED (in-memory)")

if __name__ == "__main__":
    test_persistence()
