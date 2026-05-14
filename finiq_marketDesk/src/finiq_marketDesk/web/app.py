"""Serve the custom KIND market web UI."""

from __future__ import annotations

import argparse
from collections import deque
import errno
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time
from typing import Any
from uuid import uuid4
from urllib.parse import parse_qs, urlparse

from finiq_marketDesk.web.service import (
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
from finiq_marketDesk.web.download import (
    build_download_options_payload,
    build_download_preview_payload,
    build_download_status_payload,
    get_download_job,
    render_download_page,
    run_download_action,
    start_download_job,
)
from finiq_marketDesk.web.disclosure_html import cancel_disclosure_html_download, download_disclosure_html_payload
from finiq_marketDesk.web.disclosure_html_parse import (
    build_bond_parse_summary_payload,
    build_parse_change_log_payload,
    cancel_disclosure_html_parse,
    parse_disclosure_html_payload,
)
from finiq_marketDesk.web.table_export import build_disclosure_table_payload


@dataclass(slots=True)
class AppConfig:
    output_root: str
    quanti_dir: str
    host: str
    port: int
    settings_path: str = ""
    price_root_directory: str = ""
    selected_classification_path: str = ""
    sqlite_source_path: str = ""
    download_output_directory: str = ""
    sqlite_manifest_path: str = ""
    html_output_directory: str = ""
    html_transfer_directory: str = ""
    html_parse_result_path: str = ""
    html_parse_mode: str = ""


@dataclass(slots=True)
class HtmlJob:
    id: str
    kind: str
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    progress_log: deque[str] = field(default_factory=lambda: deque(maxlen=100))
    result: dict[str, Any] | None = None
    error: str | None = None


_HTML_JOBS: dict[str, HtmlJob] = {}
_HTML_JOBS_LOCK = threading.Lock()


SAVED_SETTINGS_KEYS = (
    "output_root",
    "quanti_dir",
    "price_root_directory",
    "selected_classification_path",
    "sqlite_source_path",
    "download_output_directory",
    "sqlite_manifest_path",
    "html_output_directory",
    "html_transfer_directory",
    "html_parse_result_path",
    "html_parse_mode",
)


def _default_settings_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "finiq_dataScraper" / "appdata.json"


def _legacy_settings_path(settings_path: str | Path) -> Path:
    return Path(settings_path).with_name("kind-web-settings.json")


def _normalize_saved_path(value: str) -> str:
    return str(Path(value).expanduser().resolve())


def _html_job_log_limit(payload: dict[str, Any]) -> int:
    value = payload.get("log_limit")
    if value in ("", None):
        return 120
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 120
    return max(20, min(parsed, 500))


def _html_job_snapshot(job: HtmlJob) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "kind": job.kind,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "progress_log": list(job.progress_log),
        "result": job.result,
        "error": job.error,
    }


def _update_html_job(job_id: str, **updates: Any) -> None:
    with _HTML_JOBS_LOCK:
        job = _HTML_JOBS[job_id]
        for key, value in updates.items():
            setattr(job, key, value)
        job.updated_at = time.time()


def _append_html_job_progress(job_id: str, message: str) -> None:
    with _HTML_JOBS_LOCK:
        job = _HTML_JOBS[job_id]
        timestamp = time.strftime("%H:%M:%S")
        job.progress_log.append(f"[{timestamp}] {message}")
        job.updated_at = time.time()


def _start_html_job(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if kind not in {"download", "parse"}:
        raise ValueError("html job kind must be download or parse")
    job_id = uuid4().hex
    job = HtmlJob(id=job_id, kind=kind, progress_log=deque(maxlen=_html_job_log_limit(payload)))
    with _HTML_JOBS_LOCK:
        _HTML_JOBS[job_id] = job

    def _worker() -> None:
        try:
            _update_html_job(job_id, status="running")
            _append_html_job_progress(job_id, f"JOB start kind={kind} id={job_id}")
            if kind == "download":
                result = download_disclosure_html_payload(
                    payload,
                    progress_callback=lambda message: _append_html_job_progress(job_id, message),
                )
            else:
                result = parse_disclosure_html_payload(
                    payload,
                    progress_callback=lambda message: _append_html_job_progress(job_id, message),
                )
            _update_html_job(job_id, status="completed", result=result)
            _append_html_job_progress(job_id, f"JOB completed kind={kind} id={job_id}")
        except Exception as exc:  # pragma: no cover - runtime path
            _update_html_job(job_id, status="failed", error=str(exc))
            _append_html_job_progress(job_id, f"JOB failed error={exc}")

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return get_html_job(job_id)


def get_html_job(job_id: str) -> dict[str, Any]:
    with _HTML_JOBS_LOCK:
        job = _HTML_JOBS.get(job_id)
        if job is None:
            raise ValueError(f"html job not found: {job_id}")
        return _html_job_snapshot(job)


def _load_saved_settings(settings_path: str | Path) -> dict[str, str]:
    path = Path(settings_path)
    if not path.exists() and path.name == "appdata.json":
        legacy_path = _legacy_settings_path(path)
        if legacy_path.exists():
            path = legacy_path
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    settings: dict[str, str] = {}
    for key in SAVED_SETTINGS_KEYS:
        value = payload.get(key)
        if not value or not isinstance(value, str):
            continue
        if key == "html_parse_mode":
            settings[key] = value
        else:
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
    quanti_dir = saved.get("quanti_dir", config.quanti_dir)
    price_root_directory = saved.get(
        "price_root_directory",
        config.price_root_directory or str(Path(quanti_dir).resolve().parent),
    )
    selected_classification_path = saved.get(
        "selected_classification_path",
        config.selected_classification_path or resolve_default_classification(output_root) or "",
    )

    return AppConfig(
        output_root=output_root,
        quanti_dir=quanti_dir,
        host=config.host,
        port=config.port,
        settings_path=settings_path,
        price_root_directory=price_root_directory,
        selected_classification_path=selected_classification_path,
        sqlite_source_path=saved.get("sqlite_source_path", config.sqlite_source_path),
        download_output_directory=saved.get("download_output_directory", config.download_output_directory),
        sqlite_manifest_path=saved.get("sqlite_manifest_path", config.sqlite_manifest_path),
        html_output_directory=saved.get("html_output_directory", config.html_output_directory),
        html_transfer_directory=saved.get("html_transfer_directory", config.html_transfer_directory),
        html_parse_result_path=saved.get("html_parse_result_path", config.html_parse_result_path),
        html_parse_mode=saved.get("html_parse_mode", config.html_parse_mode),
    )


def _first_query_value(query: dict[str, list[str]], key: str, default: str = "") -> str:
    values = query.get(key)
    if not values:
        return default
    return values[0]


def _build_disclosure_html_transfer_payload(payload: dict[str, Any]) -> dict[str, Any]:
    acpt_numbers: list[str] = []
    seen: set[str] = set()
    disclosures = [
        dict(disclosure)
        for disclosure in list(payload.get("disclosures") or [])
        if isinstance(disclosure, dict)
    ]
    source_acpt_numbers = payload.get("html_download_acpt_numbers")
    if isinstance(source_acpt_numbers, list):
        candidates = source_acpt_numbers
    else:
        candidates = [
            disclosure.get("acpt_no") or disclosure.get("acptno") for disclosure in disclosures
        ]
    for candidate in candidates:
        acpt_no = str(candidate or "").strip()
        if not acpt_no or acpt_no in seen:
            continue
        seen.add(acpt_no)
        acpt_numbers.append(acpt_no)
    return {
        "format": "kind_disclosure_filter_transfer_v1",
        "source_format": payload.get("format") or "",
        "source_classification_path": payload.get("source_classification_path") or "",
        "source_root_directory": payload.get("source_root_directory") or "",
        "filters": payload.get("filters") or {},
        "summary": {
            **(payload.get("summary") or {}),
            "transferred_acpt_numbers": len(acpt_numbers),
            "transferred_rows": len(disclosures),
        },
        "unique_titles": payload.get("unique_titles") or [],
        "table": {
            "columns": [
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
            ],
            "rows": disclosures,
        },
        "disclosures": disclosures,
        "acptNumbers": acpt_numbers,
    }


def _write_disclosure_html_transfer_file(
    output_root: str | Path,
    payload: dict[str, Any],
    *,
    requested_path: str = "",
) -> dict[str, Any]:
    transfer_payload = _build_disclosure_html_transfer_payload(payload)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if requested_path:
        transfer_path = Path(requested_path).expanduser().resolve()
        if transfer_path.suffix.lower() != ".json":
            transfer_path = transfer_path / f"filtered-disclosures-{timestamp}-{uuid4().hex[:8]}.json"
    else:
        transfer_dir = Path(output_root).expanduser().resolve() / ".finiq" / "transfers"
        transfer_path = transfer_dir / f"filtered-disclosures-{timestamp}-{uuid4().hex[:8]}.json"
    transfer_path.parent.mkdir(parents=True, exist_ok=True)
    transfer_path.write_text(json.dumps(transfer_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "format": transfer_payload["format"],
        "path": str(transfer_path),
        "acpt_numbers": len(transfer_payload["acptNumbers"]),
    }


def _file_dialog_default_parts(raw_path: str) -> tuple[str, str]:
    if not raw_path:
        return (str(Path.home()), "")
    path = Path(raw_path).expanduser()
    default_name = path.name if path.suffix else ""
    directory = path.parent if path.suffix else path
    while not directory.exists() and directory != directory.parent:
        directory = directory.parent
    if not directory.exists():
        directory = Path.home()
    return (str(directory.resolve()), default_name)


def _choose_finder_path(*, mode: str, title: str, default_path: str = "") -> str:
    if sys.platform != "darwin":
        msg = "Finder path selection is only available on macOS."
        raise RuntimeError(msg)
    if mode not in {"file", "folder", "save"}:
        msg = "mode must be one of: file, folder, save"
        raise ValueError(msg)

    default_directory, default_name = _file_dialog_default_parts(default_path)
    script = r'''
on run argv
  set dialogTitle to item 1 of argv
  set modeName to item 2 of argv
  set defaultDirectory to item 3 of argv
  set defaultName to item 4 of argv
  set defaultLocation to POSIX file defaultDirectory

  if modeName is "folder" then
    set chosenPath to choose folder with prompt dialogTitle default location defaultLocation
  else if modeName is "save" then
    if defaultName is "" then
      set defaultName to "untitled"
    end if
    set chosenPath to choose file name with prompt dialogTitle default name defaultName default location defaultLocation
  else
    set chosenPath to choose file with prompt dialogTitle default location defaultLocation
  end if

  return POSIX path of chosenPath
end run
'''
    result = subprocess.run(
        ["osascript", "-e", script, title, mode, default_directory, default_name],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "User canceled" in stderr or "사용자가 취소" in stderr:
            return ""
        raise RuntimeError(stderr or "Finder path selection failed")
    return result.stdout.strip()


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
        if parsed.path.startswith("/api/disclosures/html/jobs/"):
            self._handle_disclosure_html_job(parsed.path)
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
        if parsed.path == "/api/disclosures/html/parse/export.xlsx":
            self._handle_disclosure_html_parse_export_xlsx(parsed.query)
            return
        self._respond_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/settings":
            self._handle_save_settings()
            return
        if parsed.path == "/api/file-dialog":
            self._handle_file_dialog()
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
        if parsed.path == "/api/disclosures/html/download/start":
            self._handle_disclosure_html_download_start()
            return
        if parsed.path == "/api/disclosures/html/download/cancel":
            self._handle_disclosure_html_download_cancel()
            return
        if parsed.path == "/api/disclosures/html/parse":
            self._handle_disclosure_html_parse()
            return
        if parsed.path == "/api/disclosures/html/parse/start":
            self._handle_disclosure_html_parse_start()
            return
        if parsed.path == "/api/disclosures/html/parse/bond-summary":
            self._handle_disclosure_html_parse_bond_summary()
            return
        if parsed.path == "/api/disclosures/html/parse/change-log":
            self._handle_disclosure_html_parse_change_log()
            return
        if parsed.path == "/api/disclosures/html/parse/cancel":
            self._handle_disclosure_html_parse_cancel()
            return
        self._respond_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _build_config_payload(self) -> dict[str, Any]:
        price_root_directory = self.server.config.price_root_directory or str(
            Path(self.server.config.quanti_dir).resolve().parent
        )
        output_root = self.server.config.output_root
        classification_files = list_classification_files(self.server.config.output_root)
        selected_classification_path = self.server.config.selected_classification_path or resolve_default_classification(
            self.server.config.output_root
        )
        selected_price_path = resolve_default_price_source(
            price_root_directory,
            self.server.config.quanti_dir,
        )
        return {
            "output_root": output_root,
            "quanti_dir": self.server.config.quanti_dir,
            "price_root_directory": price_root_directory,
            "download_output_directory": self.server.config.download_output_directory or output_root,
            "sqlite_manifest_path": self.server.config.sqlite_manifest_path,
            "html_output_directory": self.server.config.html_output_directory or f"{output_root}/viewer_html",
            "html_transfer_directory": self.server.config.html_transfer_directory or f"{output_root}/.finiq/transfers",
            "html_parse_result_path": self.server.config.html_parse_result_path,
            "html_parse_mode": self.server.config.html_parse_mode,
            "price_files": list_price_source_files(price_root_directory),
            "selected_price_path": selected_price_path,
            "classification_files": classification_files,
            "selected_classification_path": selected_classification_path,
            "sqlite_source_path": self.server.config.sqlite_source_path,
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

        settings_path = self.server.config.settings_path or str(_default_settings_path())
        saved = _load_saved_settings(settings_path)
        output_root = str(Path(payload.get("output_root") or self.server.config.output_root).expanduser().resolve())
        quanti_dir = str(Path(payload.get("quanti_dir") or self.server.config.quanti_dir).expanduser().resolve())
        price_root_directory = str(Path(
            payload.get("price_root_directory")
            or self.server.config.price_root_directory
            or Path(quanti_dir).resolve().parent
        ).expanduser().resolve())
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

        # Update remaining attributes from payload
        for attr in SAVED_SETTINGS_KEYS:
            if attr in payload and attr not in (
                "output_root",
                "quanti_dir",
                "price_root_directory",
                "selected_classification_path",
            ):
                value = payload.get(attr)
                # html_parse_mode is a string, others are paths
                if attr == "html_parse_mode":
                    setattr(self.server.config, attr, str(value or ""))
                else:
                    setattr(self.server.config, attr, str(Path(str(value or "")).expanduser().resolve()) if value else "")

        next_settings = {
            **saved,
            "output_root": output_root,
            "quanti_dir": quanti_dir,
            "price_root_directory": price_root_directory,
            "selected_classification_path": selected_classification_path,
        }
        for attr in SAVED_SETTINGS_KEYS:
            value = getattr(self.server.config, attr)
            if value:
                next_settings[attr] = value
            else:
                next_settings.pop(attr, None)

        _write_saved_settings(settings_path, next_settings)
        self._respond_json(HTTPStatus.OK, self._build_config_payload())

    def _handle_file_dialog(self) -> None:
        try:
            payload = self._read_json_body()
            path = _choose_finder_path(
                mode=str(payload.get("mode") or "file").strip(),
                title=str(payload.get("title") or "경로 선택").strip(),
                default_path=str(payload.get("default_path") or "").strip(),
            )
        except (RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, {"path": path, "cancelled": not bool(path)})

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

    def _handle_disclosure_html_parse_export_xlsx(self, raw_query: str) -> None:
        from finiq_marketDesk.web.disclosure_html_parse import build_parse_export_xlsx
        query = parse_qs(raw_query)
        output_path = _first_query_value(query, "output_path")
        mode = _first_query_value(query, "mode")
        latest_only = _first_query_value(query, "latest_only", "false").lower() == "true"
        if not output_path:
            self.send_error(HTTPStatus.BAD_REQUEST, "output_path is required")
            return
        try:
            payload = build_parse_export_xlsx(output_path, mode, latest_only=latest_only)
        except Exception as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        filename = f"{Path(output_path).stem}_export.xlsx"
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
            default_output_directory=self.server.config.download_output_directory or self.server.config.output_root,
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
            if payload.get("format") == "kind_disclosure_filter_v1":
                payload["html_download_transfer"] = _write_disclosure_html_transfer_file(
                    self.server.config.output_root,
                    payload,
                    requested_path=str(body.get("html_transfer_path") or "").strip(),
                )
                payload.pop("html_download_acpt_numbers", None)
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
            content = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8") + b"\n"
            self.wfile.write(content)
            self.wfile.flush()

        def write_error_event(message: str) -> None:
            try:
                write_event({"type": "error", "error": message})
            except (BrokenPipeError, ConnectionResetError):
                return

        try:
            write_event({"type": "progress", "progress": {"message": "필터 데이터를 읽는 중입니다."}})
            payload = filter_disclosures_payload(
                body,
                progress_callback=lambda progress: write_event({"type": "progress", "progress": progress}),
            )
            if payload.get("format") == "kind_disclosure_filter_v1":
                write_event({"type": "progress", "progress": {"message": "HTML 저장용 접수번호 파일을 저장하는 중입니다."}})
                payload["html_download_transfer"] = _write_disclosure_html_transfer_file(
                    self.server.config.output_root,
                    payload,
                    requested_path=str(body.get("html_transfer_path") or "").strip(),
                )
                payload.pop("html_download_acpt_numbers", None)
            write_event({"type": "result", "payload": payload})
        except (BrokenPipeError, ConnectionResetError):
            return
        except (OSError, ValueError) as exc:
            write_error_event(str(exc))
        except Exception as exc:  # noqa: BLE001
            write_error_event(f"필터 실행 중 오류가 발생했습니다: {exc}")

    def _handle_disclosure_html_download(self) -> None:
        try:
            body = self._read_json_body()
            payload = download_disclosure_html_payload(body)
        except (OSError, ValueError) as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_disclosure_html_download_start(self) -> None:
        try:
            body = self._read_json_body()
            payload = _start_html_job("download", body)
        except (OSError, ValueError) as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_disclosure_html_download_cancel(self) -> None:
        try:
            body = self._read_json_body()
            payload = cancel_disclosure_html_download(str(body.get("cancel_token") or ""))
        except (OSError, ValueError) as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_disclosure_html_job(self, path: str) -> None:
        job_id = path.rsplit("/", 1)[-1]
        try:
            payload = get_html_job(job_id)
        except ValueError as exc:
            self._respond_json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_disclosure_html_parse(self) -> None:
        try:
            body = self._read_json_body()
            payload = parse_disclosure_html_payload(body)
        except (OSError, ValueError) as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_disclosure_html_parse_start(self) -> None:
        try:
            body = self._read_json_body()
            payload = _start_html_job("parse", body)
        except (OSError, ValueError) as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_disclosure_html_parse_cancel(self) -> None:
        try:
            body = self._read_json_body()
            payload = cancel_disclosure_html_parse(str(body.get("cancel_token") or ""))
        except (OSError, ValueError) as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_disclosure_html_parse_bond_summary(self) -> None:
        try:
            body = self._read_json_body()
            payload = build_bond_parse_summary_payload(body)
        except (OSError, ValueError) as exc:
            self._respond_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._respond_json(HTTPStatus.OK, payload)

    def _handle_disclosure_html_parse_change_log(self) -> None:
        try:
            body = self._read_json_body()
            payload = build_parse_change_log_payload(body)
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
                    sqlite_source_path=config.sqlite_source_path,
                    download_output_directory=config.download_output_directory,
                    sqlite_manifest_path=config.sqlite_manifest_path,
                    html_output_directory=config.html_output_directory,
                    html_transfer_directory=config.html_transfer_directory,
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
