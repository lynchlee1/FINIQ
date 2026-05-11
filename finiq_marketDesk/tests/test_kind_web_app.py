from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from finiq_marketDesk.web.app import AppConfig, KindWebServer, _apply_saved_settings


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


def _post(
    server_path: str,
    tmp_path: Path,
    body: dict[str, object],
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int | None, str]:
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
            headers={"Content-Type": "application/json", **(headers or {})},
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
    assert config["download_output_directory"] == str(tmp_path)
    assert config["html_output_directory"] == str(tmp_path / "viewer_html")
    assert config["html_transfer_directory"] == str(tmp_path / ".finiq" / "transfers")


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
        "finiq_marketDesk.web.app.build_download_preview_payload",
        lambda body: {"echo_mode": body.get("mode")},
    )

    status, payload = _post("/api/download/preview", tmp_path, {"mode": "single"})

    assert status == 200
    assert json.loads(payload) == {"echo_mode": "single"}


def test_download_run_api_routes_to_handler(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "finiq_marketDesk.web.app.run_download_action",
        lambda body: {"status": "done", "mode": body.get("mode")},
    )

    status, payload = _post("/api/download/run", tmp_path, {"mode": "resume"})

    assert status == 200
    assert json.loads(payload) == {"status": "done", "mode": "resume"}


def test_disclosure_filter_api_routes_to_handler(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "finiq_marketDesk.web.app.filter_disclosures_payload",
        lambda body: {"echo_title": body.get("title_keyword")},
    )

    status, payload = _post("/api/disclosures/filter", tmp_path, {"title_keyword": "전환사채"})

    assert status == 200
    assert json.loads(payload) == {"echo_title": "전환사채"}


def test_disclosure_filter_stream_returns_result_event(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "finiq_marketDesk.web.app.filter_disclosures_payload",
        lambda body, progress_callback=None: {"echo_title": body.get("title_keyword")},
    )

    status, payload = _post(
        "/api/disclosures/filter",
        tmp_path,
        {"title_keyword": "전환사채"},
        headers={"Accept": "application/x-ndjson"},
    )

    assert status == 200
    events = [json.loads(line) for line in payload.splitlines()]
    assert events[-1] == {"type": "result", "payload": {"echo_title": "전환사채"}}


def test_disclosure_filter_stream_returns_error_event_on_unexpected_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def raise_unexpected_error(body: dict[str, object], progress_callback=None) -> dict[str, object]:
        raise RuntimeError("boom")

    monkeypatch.setattr("finiq_marketDesk.web.app.filter_disclosures_payload", raise_unexpected_error)

    status, payload = _post(
        "/api/disclosures/filter",
        tmp_path,
        {},
        headers={"Accept": "application/x-ndjson"},
    )

    assert status == 200
    events = [json.loads(line) for line in payload.splitlines()]
    assert events[-1] == {"type": "error", "error": "필터 실행 중 오류가 발생했습니다: boom"}


def test_disclosure_filter_api_transfer_file_stores_table_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "finiq_marketDesk.web.app.filter_disclosures_payload",
        lambda body: {
            "format": "kind_disclosure_filter_v1",
            "summary": {"matched_disclosures": 1, "returned_disclosures": 1},
            "filters": {"filter_blocks": []},
            "disclosures": [
                {
                    "disclosed_at": "2025-01-02 09:00:00",
                    "disclosed_date": "2025-01-02",
                    "company_name": "테스트전자",
                    "company_id": "005930",
                    "market": "코스닥",
                    "title": "전환사채발행결정",
                    "acpt_no": "20250102000001",
                    "doc_no": "",
                    "submitter": "테스트전자",
                }
            ],
            "unique_titles": ["전환사채발행결정"],
            "html_download_acpt_numbers": ["20250102000001"],
        },
    )
    transfer_path = tmp_path / "filtered.json"

    status, payload = _post(
        "/api/disclosures/filter",
        tmp_path,
        {"html_transfer_path": str(transfer_path)},
    )

    assert status == 200
    response_payload = json.loads(payload)
    assert response_payload["html_download_transfer"]["path"] == str(transfer_path)
    transfer_payload = json.loads(transfer_path.read_text(encoding="utf-8"))
    assert transfer_payload["table"]["columns"] == [
        "disclosed_at",
        "disclosed_date",
        "company_name",
        "company_id",
        "market",
        "title",
        "title_attr",
        "title_base",
        "title_display",
        "title_flags",
        "title_flags_json",
        "is_correction_report",
        "has_later_correction",
        "acpt_no",
        "doc_no",
        "submitter",
        "row_no",
        "source_file",
        "source_page",
    ]
    assert transfer_payload["table"]["rows"][0]["title"] == "전환사채발행결정"
    assert transfer_payload["disclosures"][0]["acpt_no"] == "20250102000001"
    assert transfer_payload["unique_titles"] == ["전환사채발행결정"]
    assert transfer_payload["acptNumbers"] == ["20250102000001"]


def test_disclosure_html_download_api_routes_to_handler(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "finiq_marketDesk.web.app.download_disclosure_html_payload",
        lambda body: {"saved_count": len(body.get("json", {}).get("disclosures", []))},
    )

    status, payload = _post(
        "/api/disclosures/html/download",
        tmp_path,
        {"json": {"disclosures": [{"acpt_no": "1"}]}},
    )

    assert status == 200
    assert json.loads(payload) == {"saved_count": 1}


def test_disclosure_html_parse_api_routes_to_handler(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "finiq_marketDesk.web.app.parse_disclosure_html_payload",
        lambda body: {"mode": body.get("mode"), "parsed": True},
    )

    status, payload = _post(
        "/api/disclosures/html/parse",
        tmp_path,
        {"input_directory": str(tmp_path), "mode": "bond_issuance"},
    )

    assert status == 200
    assert json.loads(payload) == {"mode": "bond_issuance", "parsed": True}


def test_settings_can_be_saved_via_api(tmp_path: Path) -> None:
    settings_path = tmp_path / "appdata" / "appdata.json"
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
                "download_output_directory": str(tmp_path / "download-output"),
                "html_transfer_directory": str(tmp_path / "transfers"),
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
    assert stored["download_output_directory"] == str((tmp_path / "download-output").resolve())
    assert stored["html_transfer_directory"] == str((tmp_path / "transfers").resolve())


def test_settings_partial_update_preserves_existing_paths(tmp_path: Path) -> None:
    settings_path = tmp_path / "appdata" / "appdata.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps(
            {
                "output_root": str(tmp_path / "root"),
                "quanti_dir": str(tmp_path / "price" / "by_item"),
                "price_root_directory": str(tmp_path / "price"),
                "selected_classification_path": str(tmp_path / "root" / "kind.company_classification.json"),
                "html_output_directory": str(tmp_path / "html-old"),
            }
        ),
        encoding="utf-8",
    )
    server = KindWebServer(
        "127.0.0.1",
        0,
        AppConfig(
            output_root=str(tmp_path / "root"),
            quanti_dir=str(tmp_path / "price" / "by_item"),
            host="127.0.0.1",
            port=0,
            settings_path=str(settings_path),
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        body = json.dumps({"download_output_directory": str(tmp_path / "download-new")}).encode("utf-8")
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

    assert payload["download_output_directory"] == str((tmp_path / "download-new").resolve())
    assert stored["html_output_directory"] == str((tmp_path / "html-old").resolve())
    assert stored["download_output_directory"] == str((tmp_path / "download-new").resolve())


def test_legacy_settings_file_is_loaded_when_appdata_json_is_missing(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    classification = root / "kind.company_classification.json"
    classification.write_text("{}", encoding="utf-8")
    price_root = tmp_path / "price"
    price_root.mkdir()
    price_dir = price_root / "by_item"
    price_dir.mkdir()
    (price_dir / "000001.parquet").write_text("", encoding="utf-8")
    settings_path = tmp_path / "appdata" / "appdata.json"
    legacy_path = settings_path.with_name("kind-web-settings.json")
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(
        json.dumps(
            {
                "output_root": str(root),
                "quanti_dir": str(price_dir),
                "price_root_directory": str(price_root),
                "selected_classification_path": str(classification),
            }
        ),
        encoding="utf-8",
    )

    config = _apply_saved_settings(
        AppConfig(
            output_root=str(tmp_path / "fallback-root"),
            quanti_dir=str(tmp_path / "fallback-price"),
            host="127.0.0.1",
            port=0,
            settings_path=str(settings_path),
        )
    )

    assert config.settings_path == str(settings_path)
    assert config.output_root == str(root.resolve())
    assert config.quanti_dir == str(price_dir.resolve())


def test_saved_paths_are_preserved_without_directory_validation(tmp_path: Path) -> None:
    settings_path = tmp_path / "appdata" / "appdata.json"
    settings_path.parent.mkdir(parents=True)
    missing_root = tmp_path / "missing-root"
    missing_price = tmp_path / "missing-price"
    settings_path.write_text(
        json.dumps(
            {
                "output_root": str(missing_root),
                "quanti_dir": str(missing_price / "by_item"),
                "price_root_directory": str(missing_price),
                "selected_classification_path": str(missing_root / "manual.json"),
            }
        ),
        encoding="utf-8",
    )

    config = _apply_saved_settings(
        AppConfig(
            output_root=str(tmp_path / "fallback-root"),
            quanti_dir=str(tmp_path / "fallback-price"),
            host="127.0.0.1",
            port=0,
            settings_path=str(settings_path),
        )
    )

    assert config.output_root == str(missing_root.resolve())
    assert config.quanti_dir == str((missing_price / "by_item").resolve())
    assert config.price_root_directory == str(missing_price.resolve())
    assert config.selected_classification_path == str((missing_root / "manual.json").resolve())
