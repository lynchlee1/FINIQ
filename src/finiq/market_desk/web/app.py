from __future__ import annotations

import asyncio
import os
import uuid
import json
import queue
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, List, Dict, Union

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from finiq.config import init_config, save_settings, normalize_path
from finiq.market_desk.web.jobs import job_manager
from finiq.market_desk.web.service import (
    DISPLAY_FREQUENCY_OPTIONS,
    INSIGHT_RANGE_OPTIONS,
    PRICE_SOURCE_FDR,
    PRICE_SOURCE_LABELS,
    PRICE_SOURCE_QUANTI,
    build_company_list_export,
    filter_disclosures_payload,
    build_insight_payload,
    list_classification_files,
    list_integrated_providers,
    list_price_source_files,
    load_company_index_payload,
    resolve_default_classification,
    resolve_default_price_source,
    run_integrated_convert_payload,
    run_integrated_market_history_payload,
    run_integrated_merge_payload,
)
from finiq.market_desk.web.download import (
    build_download_options_payload,
    build_download_preview_payload,
    build_download_status_payload,
    get_download_job,
    run_download_action,
    start_download_job,
)
from finiq.market_desk.web.disclosure_html import (
    cancel_disclosure_html_download,
    clean_disclosure_html_output_directory_payload,
    compress_disclosure_external_html_payload,
    download_disclosure_html_contents_payload,
    download_disclosure_html_payload,
    merge_disclosure_content_html_payload,
)
from finiq.market_desk.web.disclosure_html_parse import (
    build_bond_parse_summary_payload,
    build_parse_change_log_payload,
    build_parse_export_xlsx,
    cancel_disclosure_html_parse,
    parse_disclosure_html_payload,
)
from finiq.market_desk.web.table_export import build_disclosure_table_payload

app = FastAPI(title="FINIQ MarketDesk API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global config instance
config = init_config()

# --- Async Job Management ---

def _run_job_worker(job_id: str, kind: str, payload: dict[str, Any]):
    try:
        job_manager.start_job(job_id)
        progress_callback = lambda m: job_manager.add_log(job_id, m)
        
        if kind == "download":
            result = download_disclosure_html_payload(payload, progress_callback=progress_callback)
        elif kind == "external_compress":
            result = compress_disclosure_external_html_payload(payload, progress_callback=progress_callback)
        elif kind == "content_download":
            result = download_disclosure_html_contents_payload(payload, progress_callback=progress_callback)
        elif kind == "content_merge":
            result = merge_disclosure_content_html_payload(payload, progress_callback=progress_callback)
        elif kind == "parse":
            result = parse_disclosure_html_payload(payload, progress_callback=progress_callback)
        elif kind == "integrated_convert":
            result = run_integrated_convert_payload(payload, progress_callback=progress_callback)
        elif kind == "integrated_merge":
            result = run_integrated_merge_payload(payload, progress_callback=progress_callback)
        elif kind == "integrated_market_history":
            result = run_integrated_market_history_payload(payload, progress_callback=progress_callback)
        elif kind == "table_build":
            result = build_disclosure_table_payload(payload, progress_callback=progress_callback)
        else:
            raise ValueError(f"Unhandled job kind: {kind}")

        job_manager.complete_job(job_id, result)
    except Exception as exc:
        job_manager.fail_job(job_id, str(exc))

# --- Helper Functions ---

def _normalize_file_dialog_mode(mode: str) -> str:
    normalized = str(mode or "file").strip().lower()
    if normalized in {"dir", "folder", "directory"}:
        return "folder"
    if normalized in {"file", "save"}:
        return normalized
    raise HTTPException(status_code=400, detail=f"Unsupported file dialog mode: {mode}")


def _choose_finder_path(*, mode: str, title: str, default_path: str = "") -> str:
    if sys.platform != "darwin":
        raise HTTPException(status_code=400, detail="Finder path selection is only available on macOS.")
    normalized_mode = _normalize_file_dialog_mode(mode)
    
    path = Path(default_path).expanduser()
    default_directory = path.parent if path.suffix else path
    while not default_directory.exists() and default_directory != default_directory.parent:
        default_directory = default_directory.parent
    if not default_directory.exists():
        default_directory = Path.home()
    
    default_name = path.name if path.suffix else ""
    
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
        ["osascript", "-e", script, title, normalized_mode, str(default_directory), default_name],
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "User canceled" in stderr or "사용자가 취소" in stderr:
            return ""
        raise HTTPException(status_code=500, detail=stderr or "Finder path selection failed")
    return result.stdout.strip()

def _write_transfer_file(payload: dict[str, Any], requested_path: str = "") -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if requested_path:
        transfer_path = Path(requested_path).expanduser().resolve()
        if transfer_path.suffix.lower() != ".json":
            transfer_path = transfer_path / f"filtered-disclosures-{timestamp}-{uuid.uuid4().hex[:8]}.json"
    else:
        transfer_dir = Path(config.output_root).expanduser().resolve() / ".finiq" / "transfers"
        transfer_path = transfer_dir / f"filtered-disclosures-{timestamp}-{uuid.uuid4().hex[:8]}.json"
    
    transfer_path.parent.mkdir(parents=True, exist_ok=True)
    transfer_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "format": payload.get("format", ""),
        "path": str(transfer_path),
        "acpt_numbers": len(payload.get("html_download_acpt_numbers") or payload.get("acptNumbers") or []),
    }


def _attach_html_download_transfer(payload: dict[str, Any], requested_path: str = "") -> dict[str, Any]:
    if payload.get("format") == "kind_disclosure_filter_v1":
        payload["html_download_transfer"] = _write_transfer_file(payload, requested_path=requested_path)
    return payload

# --- API Routes ---

def _config_payload(*, include_discovery: bool = False) -> dict[str, Any]:
    price_root = config.price_root_directory or str(Path(config.quanti_dir).expanduser().parent)
    payload = {
        "output_root": config.output_root,
        "quanti_dir": config.quanti_dir,
        "price_root_directory": price_root,
        "download_output_directory": config.download_output_directory or config.output_root,
        "sqlite_manifest_path": config.sqlite_manifest_path,
        "html_output_directory": config.html_output_directory or f"{config.output_root}/viewer_html",
        "html_content_output_directory": config.html_content_output_directory or f"{config.output_root}/viewer_html_contents",
        "html_transfer_directory": config.html_transfer_directory or f"{config.output_root}/.finiq/transfers",
        "html_parse_result_path": config.html_parse_result_path,
        "html_parse_mode": config.html_parse_mode,
        "price_files": [],
        "selected_price_path": config.quanti_dir,
        "classification_files": [],
        "selected_classification_path": config.selected_classification_path,
        "sqlite_source_path": config.sqlite_source_path,
        "integrated_merge_input_path": config.integrated_merge_input_path,
        "integrated_merge_output_path": config.integrated_merge_output_path,
        "integrated_history_item_registry_path": config.integrated_history_item_registry_path,
        "integrated_history_output_path": config.integrated_history_output_path,
        "html_download_source_path": config.html_download_source_path,
        "integrated_data_values": config.integrated_data_values,
        "change_log_date_thresholds": config.change_log_date_thresholds,
        "change_log_numeric_thresholds": config.change_log_numeric_thresholds,
        "condition_presets": config.condition_presets,
        "range_options": list(INSIGHT_RANGE_OPTIONS),
        "display_frequency_options": list(DISPLAY_FREQUENCY_OPTIONS),
        "price_sources": [
            {"key": PRICE_SOURCE_QUANTI, "label": PRICE_SOURCE_LABELS[PRICE_SOURCE_QUANTI]},
            {"key": PRICE_SOURCE_FDR, "label": PRICE_SOURCE_LABELS[PRICE_SOURCE_FDR]},
        ],
    }

    if include_discovery:
        payload["price_files"] = list_price_source_files(price_root)
        payload["selected_price_path"] = resolve_default_price_source(price_root, config.quanti_dir)
        payload["classification_files"] = list_classification_files(config.output_root)
        payload["selected_classification_path"] = config.selected_classification_path or resolve_default_classification(config.output_root)

    return payload

@app.get("/api/config")
async def get_config(response: Response, include_discovery: bool = False):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return _config_payload(include_discovery=include_discovery)

class SettingsUpdate(BaseModel):
    output_root: Optional[str] = None
    quanti_dir: Optional[str] = None
    price_root_directory: Optional[str] = None
    selected_classification_path: Optional[str] = None
    sqlite_source_path: Optional[str] = None
    download_output_directory: Optional[str] = None
    sqlite_manifest_path: Optional[str] = None
    html_output_directory: Optional[str] = None
    html_content_output_directory: Optional[str] = None
    html_transfer_directory: Optional[str] = None
    html_parse_result_path: Optional[str] = None
    html_parse_mode: Optional[str] = None
    integrated_merge_input_path: Optional[str] = None
    integrated_merge_output_path: Optional[str] = None
    integrated_history_item_registry_path: Optional[str] = None
    integrated_history_output_path: Optional[str] = None
    html_download_source_path: Optional[str] = None
    integrated_data_values: Optional[dict[str, str]] = None
    change_log_date_thresholds: Optional[dict[str, float]] = None
    change_log_numeric_thresholds: Optional[dict[str, float]] = None
    condition_presets: Optional[list[dict[str, Any]]] = None

@app.post("/api/settings")
async def save_app_settings(update: SettingsUpdate):
    global config
    payload = update.model_dump(exclude_unset=True)
    current_settings = {}
    for key in config.__slots__:
        val = getattr(config, key)
        if isinstance(val, (str, int, float, bool, dict)):
            current_settings[key] = val

    for key, value in payload.items():
        if value is None: continue
        if key == "html_parse_mode":
            normalized = str(value)
        elif key in ("integrated_data_values", "change_log_date_thresholds", "change_log_numeric_thresholds", "condition_presets") and isinstance(value, (dict, list)):
            normalized = value
        else:
            normalized = normalize_path(str(value))
        setattr(config, key, normalized)
        current_settings[key] = normalized
    
    save_settings(config.settings_path, current_settings)
    return _config_payload()

class FileDialogRequest(BaseModel):
    mode: str = "file"
    title: str = "경로 선택"
    default_path: str = ""

@app.post("/api/file-dialog")
async def file_dialog(req: FileDialogRequest):
    path = await asyncio.to_thread(
        _choose_finder_path,
        mode=req.mode,
        title=req.title,
        default_path=req.default_path,
    )
    return {"path": path, "cancelled": not bool(path)}

@app.get("/api/classifications")
async def get_classifications(root_directory: Optional[str] = None):
    root = root_directory or config.output_root
    files = list_classification_files(root)
    return {
        "root_directory": str(Path(root).resolve()),
        "classification_files": files,
        "selected_classification_path": resolve_default_classification(root),
    }

@app.get("/api/price-sources")
async def get_price_sources(root_directory: Optional[str] = None, selected_path: Optional[str] = None):
    root = root_directory or str(Path(config.quanti_dir).resolve().parent)
    return {
        "price_root_directory": str(Path(root).resolve()),
        "price_files": list_price_source_files(root),
        "selected_price_path": resolve_default_price_source(root, selected_path or ""),
    }

@app.get("/api/integrated-data/providers")
async def get_integrated_providers_route():
    return {"providers": list_integrated_providers()}

@app.get("/api/companies")
async def get_companies(
    classification_path: Optional[str] = None,
    keyword: Optional[str] = None,
    market: str = "전체"
):
    path = classification_path or config.selected_classification_path or resolve_default_classification(config.output_root) or ""
    if not path:
        return {"summary": {}, "markets": ["전체"], "companies": []}
    return load_company_index_payload(path, keyword=keyword, market=market)

@app.get("/api/insight")
async def get_insight(
    classification_path: str,
    company_key: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    range_label: str = "검색기간",
    display_frequency: str = "자동",
    price_source: str = PRICE_SOURCE_QUANTI,
    quanti_dir: Optional[str] = None,
    stock_code: Optional[str] = None,
):
    try:
        return build_insight_payload(
            classification_path,
            company_key,
            start_date_iso=start_date,
            end_date_iso=end_date,
            range_label=range_label,
            display_frequency_label=display_frequency,
            price_source=price_source,
            quanti_dir=quanti_dir or config.quanti_dir,
            stock_code_override=stock_code,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/api/company-list.xlsx")
async def export_companies(
    classification_path: str,
    keyword: Optional[str] = None,
    market: str = "전체"
):
    payload = build_company_list_export(classification_path, keyword=keyword, market=market)
    filename = f"{Path(classification_path).stem}.company_list.xlsx"
    temp_path = Path(f"/tmp/{filename}")
    temp_path.write_bytes(payload)
    return FileResponse(temp_path, filename=filename, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.get("/api/download/options")
async def get_download_options_route(response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return build_download_options_payload(
        default_output_directory=config.download_output_directory or config.output_root
    )

@app.post("/api/download/preview")
async def download_preview(payload: dict[str, Any]):
    return build_download_preview_payload(payload)

@app.post("/api/download/status")
async def download_status_route(payload: dict[str, Any]):
    return build_download_status_payload(payload)

@app.post("/api/download/run/start")
async def download_start_route(payload: dict[str, Any]):
    return start_download_job(payload)

@app.get("/api/download/jobs/{job_id}")
async def get_download_job_status_route(job_id: str):
    try:
        return get_download_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/api/download/run")
async def download_run(payload: dict[str, Any]):
    return run_download_action(payload)

@app.post("/api/disclosures/filter")
async def filter_disclosures(request: Request):
    body = await request.json()
    accept = request.headers.get("Accept", "")
    if "application/x-ndjson" in accept:
        def generate():
            events: queue.Queue[dict[str, Any]] = queue.Queue()

            def run_filter() -> None:
                try:
                    payload = filter_disclosures_payload(
                        body,
                        progress_callback=lambda progress: events.put({"type": "progress", "progress": progress}),
                    )
                    _attach_html_download_transfer(
                        payload,
                        requested_path=str(body.get("html_transfer_path") or "").strip(),
                    )
                    events.put({"type": "result", "payload": payload})
                except Exception as e:
                    events.put({"type": "error", "error": str(e)})

            thread = threading.Thread(target=run_filter, daemon=True)
            thread.start()
            while thread.is_alive() or not events.empty():
                try:
                    event = events.get(timeout=0.1)
                except queue.Empty:
                    continue
                yield json.dumps(event, ensure_ascii=False) + "\n"
        return StreamingResponse(generate(), media_type="application/x-ndjson")
    try:
        payload = filter_disclosures_payload(body)
        _attach_html_download_transfer(payload, requested_path=str(body.get("html_transfer_path") or "").strip())
        return payload
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/api/disclosures/table/build")
async def build_disclosure_table(payload: dict[str, Any]):
    return build_disclosure_table_payload(payload)

@app.post("/api/disclosures/table/build/start")
async def start_build_disclosure_table(payload: dict[str, Any], background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex
    job_manager.create_job(job_id, "table_build")
    background_tasks.add_task(_run_job_worker, job_id, "table_build", payload)
    return job_manager.get_snapshot(job_id)

@app.get("/api/disclosures/table/jobs/{job_id}")
async def get_table_job_status(job_id: str):
    snapshot = job_manager.get_snapshot(job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Job not found")
    return snapshot

@app.get("/api/disclosures/html/jobs/{job_id}")
async def get_html_job_status(job_id: str):
    snapshot = job_manager.get_snapshot(job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Job not found")
    return snapshot

@app.get("/api/integrated-data/jobs/{job_id}")
async def get_integrated_job_status(job_id: str):
    snapshot = job_manager.get_snapshot(job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Job not found")
    return snapshot

@app.post("/api/disclosures/html/download/start")
async def start_html_download(payload: dict[str, Any], background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex
    job_manager.create_job(job_id, "download")
    background_tasks.add_task(_run_job_worker, job_id, "download", payload)
    return job_manager.get_snapshot(job_id)

@app.post("/api/disclosures/html/download/cancel")
async def cancel_html_download_route(payload: dict[str, Any]):
    return cancel_disclosure_html_download(str(payload.get("cancel_token") or ""))

@app.post("/api/disclosures/html/download/inspect-folder")
async def inspect_html_download_folder(payload: dict[str, Any]):
    try:
        return clean_disclosure_html_output_directory_payload(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/api/disclosures/html/download/compress/start")
async def start_html_external_compress(payload: dict[str, Any], background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex
    job_manager.create_job(job_id, "external_compress")
    background_tasks.add_task(_run_job_worker, job_id, "external_compress", payload)
    return job_manager.get_snapshot(job_id)

@app.post("/api/disclosures/html/content-download/start")
async def start_html_content_download(payload: dict[str, Any], background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex
    job_manager.create_job(job_id, "content_download")
    background_tasks.add_task(_run_job_worker, job_id, "content_download", payload)
    return job_manager.get_snapshot(job_id)

@app.post("/api/disclosures/html/content-download/cancel")
async def cancel_html_content_download_route(payload: dict[str, Any]):
    return cancel_disclosure_html_download(str(payload.get("cancel_token") or ""))

@app.post("/api/disclosures/html/content-download/inspect-folder")
async def inspect_html_content_download_folder(payload: dict[str, Any]):
    try:
        return clean_disclosure_html_output_directory_payload(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/api/disclosures/html/content-download/merge/start")
async def start_html_content_merge(payload: dict[str, Any], background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex
    job_manager.create_job(job_id, "content_merge")
    background_tasks.add_task(_run_job_worker, job_id, "content_merge", payload)
    return job_manager.get_snapshot(job_id)

@app.post("/api/disclosures/html/parse/start")
async def start_html_parse(payload: dict[str, Any], background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex
    job_manager.create_job(job_id, "parse")
    background_tasks.add_task(_run_job_worker, job_id, "parse", payload)
    return job_manager.get_snapshot(job_id)

@app.post("/api/disclosures/html/parse/cancel")
async def cancel_html_parse_route(payload: dict[str, Any]):
    return cancel_disclosure_html_parse(str(payload.get("cancel_token") or ""))

@app.post("/api/disclosures/html/parse/bond-summary")
async def bond_parse_summary_route(payload: dict[str, Any]):
    return build_bond_parse_summary_payload(payload)

@app.post("/api/disclosures/html/parse/change-log")
async def parse_change_log_route(payload: dict[str, Any]):
    return build_parse_change_log_payload(payload)

@app.get("/api/disclosures/html/parse/export.xlsx")
async def export_parse_results(output_path: str, mode: str, latest_only: bool = False):
    payload = build_parse_export_xlsx(output_path, mode, latest_only=latest_only)
    filename = f"{Path(output_path).stem}_export.xlsx"
    temp_path = Path(f"/tmp/{filename}")
    temp_path.write_bytes(payload)
    return FileResponse(temp_path, filename=filename, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.post("/api/integrated-data/convert/start")
async def start_integrated_convert(payload: dict[str, Any], background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex
    job_manager.create_job(job_id, "integrated_convert")
    background_tasks.add_task(_run_job_worker, job_id, "integrated_convert", payload)
    return job_manager.get_snapshot(job_id)

@app.post("/api/integrated-data/merge/start")
async def start_integrated_merge(payload: dict[str, Any], background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex
    job_manager.create_job(job_id, "integrated_merge")
    background_tasks.add_task(_run_job_worker, job_id, "integrated_merge", payload)
    return job_manager.get_snapshot(job_id)

@app.post("/api/integrated-data/market-history/start")
async def start_integrated_market_history(payload: dict[str, Any], background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex
    job_manager.create_job(job_id, "integrated_market_history")
    background_tasks.add_task(_run_job_worker, job_id, "integrated_market_history", payload)
    return job_manager.get_snapshot(job_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.host, port=config.port)
