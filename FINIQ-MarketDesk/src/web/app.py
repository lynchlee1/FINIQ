"""Serve the custom KIND market web UI."""

from __future__ import annotations

import argparse
import errno
import json
import os
import sys
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from web.service import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_QUANTI_DIR,
    DISPLAY_FREQUENCY_OPTIONS,
    INSIGHT_RANGE_OPTIONS,
    PRICE_SOURCE_FDR,
    PRICE_SOURCE_LABELS,
    PRICE_SOURCE_QUANTI,
    build_company_list_export,
    filter_disclosures_payload,
    build_insight_payload,
    list_classification_files,
    list_price_source_files,
    load_company_index_payload,
    resolve_default_classification,
    resolve_default_price_source,
)
from web.download import (
    build_download_options_payload,
    build_download_preview_payload,
    build_download_status_payload,
    get_download_job,
    render_download_page,
    run_download_action,
    start_download_job,
)
from web.disclosure_html import download_disclosure_html_payload
from web.table_export import build_disclosure_table_payload


@dataclass(slots=True)
class AppConfig:
    output_root: str
    quanti_dir: str
    host: str
    port: int
    settings_path: str = ""
    price_root_directory: str = ""
    selected_classification_path: str = ""


def _default_settings_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "FINIQ-DataScraper" / "kind-web-settings.json"


def _normalize_saved_path(value: str) -> str:
    return str(Path(value).expanduser().resolve())


def _load_saved_settings(settings_path: str | Path) -> dict[str, str]:
    path = Path(settings_path)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    settings: dict[str, str] = {}
    for key in ("output_root", "quanti_dir", "price_root_directory", "selected_classification_path"):
        value = payload.get(key)
        if not value or not isinstance(value, str):
            continue
        settings[key] = _normalize_saved_path(value)
    return settings


def _write_saved_settings(settings_path: str | Path, payload: dict[str, str]) -> None:
    path = Path(settings_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _apply_saved_settings(config: AppConfig) -> AppConfig:
    settings_path = config.settings_path or str(_default_settings_path())
    saved = _load_saved_settings(settings_path)
    output_root = saved.get("output_root", config.output_root)
    if not Path(output_root).exists() or not list_classification_files(output_root):
        output_root = config.output_root

    quanti_dir = saved.get("quanti_dir", config.quanti_dir)
    resolved_quanti_dir = Path(quanti_dir)
    quanti_by_item = resolved_quanti_dir / "by_item" if (resolved_quanti_dir / "by_item").is_dir() else resolved_quanti_dir
    if not quanti_by_item.exists() or not any(quanti_by_item.glob("*.parquet")):
        quanti_dir = config.quanti_dir

    price_root_directory = saved.get(
        "price_root_directory",
        config.price_root_directory or str(Path(quanti_dir).resolve().parent),
    )
    if not Path(price_root_directory).exists() or not list_price_source_files(price_root_directory):
        price_root_directory = str(Path(quanti_dir).resolve().parent)

    selected_classification_path = saved.get(
        "selected_classification_path",
        config.selected_classification_path,
    )
    if selected_classification_path:
        selected_path = Path(selected_classification_path).resolve()
        output_root_path = Path(output_root).resolve()
        if not selected_path.is_file() or output_root_path not in selected_path.parents:
            selected_classification_path = resolve_default_classification(output_root) or ""
    else:
        selected_classification_path = resolve_default_classification(output_root) or ""

    return AppConfig(
        output_root=output_root,
        quanti_dir=quanti_dir,
        host=config.host,
        port=config.port,
        settings_path=settings_path,
        price_root_directory=price_root_directory,
        selected_classification_path=selected_classification_path,
    )


def _first_query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key)
    if not values:
        return default
    return values[0]


class KindWebHandler(BaseHTTPRequestHandler):
    server: "KindWebServer"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/download":
            self._handle_download_page()
            return
        if parsed.path == "/api/config":
            self._handle_config()
            return
        if parsed.path == "/api/download/options":
            self._handle_download_options()
            return
        if parsed.path.startswith("/api/download/jobs/"):
            self._handle_download_job(parsed.path)
            return
        if parsed.path == "/api/classifications":
            self._handle_classifications(parsed.query)
            return
        if parsed.path == "/api/price-sources":
            self._handle_price_sources(parsed.query)
            return
        if parsed.path == "/api/companies":
            self._handle_companies(parsed.query)
            return
        if parsed.path == "/api/insight":
            self._handle_insight(parsed.query)
            return
        if parsed.path == "/api/company-list.xlsx":
            self._handle_company_export(parsed.query)
            return
        self._respond_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/settings":
            self._handle_save_settings()
            return
        if parsed.path == "/api/download/preview":
            self._handle_download_preview()
            return
        if parsed.path == "/api/download/status":
            self._handle_download_status()
            return
        if parsed.path == "/api/download/run/start":
            self._handle_download_start()
            return
        if parsed.path == "/api/download/run":
            self._handle_download_run()
            return
        if parsed.path == "/api/disclosures/filter":
            self._handle_disclosure_filter()
            return
        if parsed.path == "/api/disclosures/table/build":
            self._handle_disclosure_table_build()
            return
        if parsed.path == "/api/disclosures/html/download":
            self._handle_disclosure_html_download()
            return
        self._respond_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _build_config_payload(self) -> dict[str, Any]:
        price_root_directory = self.server.config.price_root_directory or str(
            Path(self.server.config.quanti_dir).resolve().parent
        )
        classification_files = list_classification_files(self.server.config.output_root)
        selected_classification_path = self.server.config.selected_classification_path or resolve_default_classification(
            self.server.config.output_root
        )
        selected_price_path = resolve_default_price_source(
            price_root_directory,
            self.server.config.quanti_dir,
        )
        return {
            "output_root": self.server.config.output_root,
            "quanti_dir": self.server.config.quanti_dir,
            "price_root_directory": price_root_directory,
            "price_files": list_price_source_files(price_root_directory),
            "selected_price_path": selected_price_path,
            "classification_files": classification_files,
            "selected_classification_path": selected_classification_path,
            "range_options": list(INSIGHT_RANGE_OPTIONS),
            "display_frequency_options": list(DISPLAY_FREQUENCY_OPTIONS),
            "price_sources": [
                {"key": PRICE_SOURCE_QUANTI, "label": PRICE_SOURCE_LABELS[PRICE_SOURCE_QUANTI]},
                {"key": PRICE_SOURCE_FDR, "label": PRICE_SOURCE_LABELS[PRICE_SOURCE_FDR]},
            ],
        }

    def _handle_config(self) -> None:
        self._respond_json(HTTPStatus.OK, self._build_config_payload())

    def _handle_classifications(self, raw_query: str) -> None:
        query = parse_qs(raw_query)
        root_directory = _first_query_value(query, "root_directory", self.server.config.output_root)
        files = list_classification_files(root_directory)
        self._respond_json(
            HTTPStatus.OK,
            {
                "root_directory": str(Path(root_directory).resolve()),
                "classification_files": files,
                "selected_classification_path": resolve_default_classification(root_directory),
            },
        )

    def _handle_price_sources(self, raw_query: str) -> None:
        query = parse_qs(raw_query)
        root_directory = _first_query_value(
            query,
            "root_directory",
            str(Path(self.server.config.quanti_dir).resolve().parent),
        )
        selected_path = _first_query_value(query, "selected_path")
        self._respond_json(
            HTTPStatus.OK,
            {
                "price_root_directory": str(Path(root_directory).resolve()),
                "price_files": list_price_source_files(root_directory),
                "selected_price_path": resolve_default_price_source(root_directory, selected_path),
            },
        )

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        if content_length <= 0:
            return {}
        raw_body = self.rfile.read(content_length)
        if not raw_body:
            return {}
        payload = json.loads(raw_body.decode("utf-8"))
        if not isinstance(payload, dict):
            msg = "JSON object body is required"
            raise ValueError(msg)
        return payload

    def _handle_save_settings(self) -> None:
        try:
            payload = self._read_json_body()
        except ValueError as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        output_root = str(
            Path(payload.get("output_root") or self.server.config.output_root).expanduser().resolve()
        )
        quanti_dir = str(
            Path(payload.get("quanti_dir") or self.server.config.quanti_dir).expanduser().resolve()
        )
        price_root_directory = str(
            Path(
                payload.get("price_root_directory")
                or self.server.config.price_root_directory
                or Path(quanti_dir).resolve().parent
            ).expanduser().resolve()
        )
        selected_classification_raw = (
            payload.get("selected_classification_path")
            or self.server.config.selected_classification_path
            or resolve_default_classification(output_root)
            or ""
        )
        selected_classification_path = (
            str(Path(selected_classification_raw).expanduser().resolve())
            if selected_classification_raw
            else ""
        )

        self.server.config.output_root = output_root
        self.server.config.quanti_dir = quanti_dir
        self.server.config.price_root_directory = price_root_directory
        self.server.config.selected_classification_path = selected_classification_path
        _write_saved_settings(
            self.server.config.settings_path or _default_settings_path(),
            {
                "output_root": output_root,
                "quanti_dir": quanti_dir,
                "price_root_directory": price_root_directory,
                "selected_classification_path": selected_classification_path,
            },
        )
        self._respond_json(HTTPStatus.OK, self._build_config_payload())

    def _handle_companies(self, raw_query: str) -> None:
        query = parse_qs(raw_query)
        classification_path = _first_query_value(query, "classification_path")
        if not classification_path:
            classification_path = resolve_default_classification(self.server.config.output_root) or ""
        if not classification_path:
            self._respond_json(HTTPStatus.OK, {"summary": {}, "markets": ["전체"], "companies": []})
            return
        payload = load_company_index_payload(
            classification_path,
            keyword=_first_query_value(query, "keyword"),
            market=_first_query_value(query, "market", "전체"),
        )
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_insight(self, raw_query: str) -> None:
        query = parse_qs(raw_query)
        classification_path = _first_query_value(query, "classification_path")
        company_key = _first_query_value(query, "company_key")
        if not classification_path or not company_key:
            self._respond_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "classification_path and company_key are required"},
            )
            return
        try:
            payload = build_insight_payload(
                classification_path,
                company_key,
                start_date_iso=_first_query_value(query, "start_date") or None,
                end_date_iso=_first_query_value(query, "end_date") or None,
                range_label=_first_query_value(query, "range_label", "검색기간"),
                display_frequency_label=_first_query_value(query, "display_frequency", "자동"),
                price_source=_first_query_value(query, "price_source", PRICE_SOURCE_QUANTI),
                quanti_dir=_first_query_value(query, "quanti_dir", self.server.config.quanti_dir),
                stock_code_override=_first_query_value(query, "stock_code"),
            )
        except Exception as exc:  # pragma: no cover - runtime path
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_company_export(self, raw_query: str) -> None:
        query = parse_qs(raw_query)
        classification_path = _first_query_value(query, "classification_path")
        if not classification_path:
            self.send_error(HTTPStatus.BAD_REQUEST, "classification_path is required")
            return
        payload = build_company_list_export(
            classification_path,
            keyword=_first_query_value(query, "keyword"),
            market=_first_query_value(query, "market", "전체"),
        )
        filename = f"{Path(classification_path).stem}.company_list.xlsx"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(payload)

    def _handle_download_page(self) -> None:
        self._respond_bytes(
            HTTPStatus.OK,
            render_download_page(),
            content_type="text/html; charset=utf-8",
        )

    def _handle_download_options(self) -> None:
        payload = build_download_options_payload(
            default_output_directory=self.server.config.output_root,
        )
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_download_preview(self) -> None:
        try:
            body = self._read_json_body()
            payload = build_download_preview_payload(body)
        except ValueError as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_download_status(self) -> None:
        try:
            body = self._read_json_body()
            payload = build_download_status_payload(body)
        except ValueError as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_download_start(self) -> None:
        try:
            body = self._read_json_body()
            payload = start_download_job(body)
        except ValueError as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_download_job(self, path: str) -> None:
        job_id = path.rsplit("/", 1)[-1]
        try:
            payload = get_download_job(job_id)
        except ValueError as exc:
            self._respond_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_download_run(self) -> None:
        try:
            body = self._read_json_body()
            payload = run_download_action(body)
        except ValueError as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_disclosure_filter(self) -> None:
        try:
            body = self._read_json_body()
        except (FileNotFoundError, IsADirectoryError, ValueError) as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if "application/x-ndjson" in self.headers.get("Accept", ""):
            self._stream_disclosure_filter(body)
            return
        try:
            payload = filter_disclosures_payload(body)
        except (FileNotFoundError, IsADirectoryError, ValueError) as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _stream_disclosure_filter(self, body: dict[str, Any]) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        def write_event(payload: dict[str, Any]) -> None:
            content = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
            self.wfile.write(content)
            self.wfile.flush()

        try:
            payload = filter_disclosures_payload(
                body,
                progress_callback=lambda progress: write_event({"type": "progress", "progress": progress}),
            )
            write_event({"type": "result", "payload": payload})
        except (BrokenPipeError, ConnectionResetError):
            return
        except (FileNotFoundError, IsADirectoryError, ValueError) as exc:
            write_event({"type": "error", "error": str(exc)})

    def _handle_disclosure_html_download(self) -> None:
        try:
            body = self._read_json_body()
            payload = download_disclosure_html_payload(body)
        except (OSError, ValueError) as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_disclosure_table_build(self) -> None:
        try:
            body = self._read_json_body()
            payload = build_disclosure_table_payload(body)
        except (OSError, ValueError) as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _respond_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._respond_bytes(status, content, content_type="application/json; charset=utf-8")

    def _respond_bytes(
        self,
        status: HTTPStatus,
        payload: bytes,
        *,
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)


class KindWebServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(self, host: str, port: int, config: AppConfig) -> None:
        super().__init__((host, port), KindWebHandler)
        self.config = config


def _create_server(config: AppConfig, *, max_port_tries: int = 20) -> tuple[KindWebServer, int, bool]:
    requested_port = config.port
    last_error: OSError | None = None
    for offset in range(max_port_tries + 1):
        candidate_port = requested_port + offset
        try:
            server = KindWebServer(
                config.host,
                candidate_port,
                AppConfig(
                    output_root=config.output_root,
                    quanti_dir=config.quanti_dir,
                    host=config.host,
                    port=candidate_port,
                    settings_path=config.settings_path,
                    price_root_directory=config.price_root_directory,
                    selected_classification_path=config.selected_classification_path,
                ),
            )
            return server, candidate_port, candidate_port != requested_port
        except OSError as exc:
            last_error = exc
            if exc.errno != errno.EADDRINUSE:
                raise
    if last_error is not None:
        raise last_error
    msg = "Unable to create web server"
    raise RuntimeError(msg)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the KIND market web UI")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind")
    parser.add_argument(
        "--root",
        default=DEFAULT_OUTPUT_ROOT,
        help="Root directory containing company classification JSON files",
    )
    parser.add_argument(
        "--quanti-dir",
        default=DEFAULT_QUANTI_DIR,
        help="Price parquet by_item directory path (default: resources/database/by_item)",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    config = AppConfig(
        output_root=str(Path(args.root).resolve()),
        quanti_dir=str(Path(args.quanti_dir).resolve()),
        host=args.host,
        port=args.port,
        settings_path=str(_default_settings_path()),
        price_root_directory=str(Path(args.quanti_dir).resolve().parent),
    )
    config = _apply_saved_settings(config)
    try:
        server, bound_port, used_fallback_port = _create_server(config)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            msg = (
                f"Port {args.port} is already in use. "
                "Close the existing process or rerun with --port <other-port>."
            )
            raise SystemExit(msg) from exc
        raise

    if used_fallback_port:
        print(  # noqa: T201
            f"Port {args.port} is busy, switched to http://{args.host}:{bound_port}"
        )
    else:
        print(f"KIND web UI listening on http://{args.host}:{bound_port}")  # noqa: T201
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - manual stop
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
