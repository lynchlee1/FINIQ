from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from web.app import AppConfig, KindWebServer


def _fetch(server_path: str, tmp_path: Path) -> tuple[int | None, str]:
    server = KindWebServer(
        "127.0.0.1",
        0,
        AppConfig(
            output_root=str(tmp_path),
            quanti_dir=str(tmp_path),
            host="127.0.0.1",
            port=0,
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    status = None
    payload = ""
    try:
        port = server.server_address[1]
        try:
            with urlopen(f"http://127.0.0.1:{port}{server_path}") as response:  # noqa: S310
                status = response.status
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            status = exc.code
            payload = exc.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    return status, payload


def _post(server_path: str, tmp_path: Path, body: dict[str, object]) -> tuple[int | None, str]:
    server = KindWebServer(
        "127.0.0.1",
        0,
        AppConfig(
            output_root=str(tmp_path),
            quanti_dir=str(tmp_path),
            host="127.0.0.1",
            port=0,
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    status = None
    payload = ""
    try:
        port = server.server_address[1]
        request = Request(
            f"http://127.0.0.1:{port}{server_path}",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request) as response:  # noqa: S310
                status = response.status
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            status = exc.code
            payload = exc.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    return status, payload


def test_index_route_is_api_only(tmp_path: Path) -> None:
    status, payload = _fetch("/", tmp_path)

    assert status == 404
    assert json.loads(payload) == {"error": "Not found"}


def test_config_api_is_available(tmp_path: Path) -> None:
    status, payload = _fetch("/api/config", tmp_path)

    assert status == 200
    config = json.loads(payload)
    assert config["output_root"] == str(tmp_path)
    assert config["quanti_dir"] == str(tmp_path)


def test_download_page_route_is_available(tmp_path: Path) -> None:
    status, payload = _fetch("/download", tmp_path)

    assert status == 200
    assert "<h1>KIND 다운로드</h1>" in payload


def test_download_options_api_is_available(tmp_path: Path) -> None:
    status, payload = _fetch("/api/download/options", tmp_path)

    assert status == 200
    parsed = json.loads(payload)
    assert "market_types" in parsed
    assert "securities_types" in parsed
    assert "disclosure_groups" in parsed


def test_download_preview_api_routes_to_handler(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "web.app.build_download_preview_payload",
        lambda body: {"echo_mode": body.get("mode")},
    )

    status, payload = _post("/api/download/preview", tmp_path, {"mode": "single"})

    assert status == 200
    assert json.loads(payload) == {"echo_mode": "single"}


def test_download_run_api_routes_to_handler(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "web.app.run_download_action",
        lambda body: {"status": "done", "mode": body.get("mode")},
    )

    status, payload = _post("/api/download/run", tmp_path, {"mode": "resume"})

    assert status == 200
    assert json.loads(payload) == {"status": "done", "mode": "resume"}


def test_disclosure_filter_api_routes_to_handler(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "web.app.filter_disclosures_payload",
        lambda body: {"echo_title": body.get("title_keyword")},
    )

    status, payload = _post("/api/disclosures/filter", tmp_path, {"title_keyword": "전환사채"})

    assert status == 200
    assert json.loads(payload) == {"echo_title": "전환사채"}


def test_disclosure_html_download_api_routes_to_handler(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "web.app.download_disclosure_html_payload",
        lambda body: {"saved_count": len(body.get("json", {}).get("disclosures", []))},
    )

    status, payload = _post(
        "/api/disclosures/html/download",
        tmp_path,
        {"json": {"disclosures": [{"acpt_no": "1"}]}},
    )

    assert status == 200
    assert json.loads(payload) == {"saved_count": 1}


def test_settings_can_be_saved_via_api(tmp_path: Path) -> None:
    settings_path = tmp_path / "appdata" / "kind-web-settings.json"
    server = KindWebServer(
        "127.0.0.1",
        0,
        AppConfig(
            output_root=str(tmp_path / "initial-root"),
            quanti_dir=str(tmp_path / "initial-price"),
            host="127.0.0.1",
            port=0,
            settings_path=str(settings_path),
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        body = json.dumps(
            {
                "output_root": str(tmp_path / "saved-root"),
                "price_root_directory": str(tmp_path / "saved-price-root"),
                "quanti_dir": str(tmp_path / "saved-price-root" / "by_item"),
                "selected_classification_path": str(tmp_path / "saved-root" / "saved.json"),
            }
        ).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{port}/api/settings",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        stored = json.loads(settings_path.read_text(encoding="utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert payload["output_root"] == str((tmp_path / "saved-root").resolve())
    assert stored["quanti_dir"] == str((tmp_path / "saved-price-root" / "by_item").resolve())
    assert stored["selected_classification_path"] == str((tmp_path / "saved-root" / "saved.json").resolve())
