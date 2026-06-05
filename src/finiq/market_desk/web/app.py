from __future__ import annotations

import asyncio
import os
import uuid
import json
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, List, Dict, Union

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from finiq.config import ASSETS_DIR, init_config
from finiq.data.assets_excel import (
    DEFAULT_ASSET_PARQUET_DIR,
    convert_asset_excels_to_wide_parquet,
    inspect_asset_excel_conversion,
    inspect_asset_excel_output,
    list_asset_excel_files,
    read_asset_excel,
    read_asset_excel_interpreted,
)
from finiq.market_desk.web.jobs import job_manager
from finiq.market_desk.web.discovery import (
    list_classification_files,
    list_price_source_files,
    resolve_default_classification,
    resolve_default_price_source,
)
from finiq.market_desk.web.service import (
    PRICE_SOURCE_QUANTI,
    build_company_list_export,
    filter_disclosures_payload,
    build_insight_payload,
    list_integrated_providers,
    load_company_index_payload,
    run_integrated_convert_payload,
    run_integrated_market_history_payload,
    run_integrated_merge_payload,
)
from finiq.market_desk.web.routers.config import (
    _choose_finder_path as _router_choose_finder_path,
    _normalize_file_dialog_mode,
    create_config_router,
)
from finiq.market_desk.web.download import (
    build_download_options_payload,
    build_download_preview_payload,
    build_download_status_payload,
    cancel_download_job,
    get_download_job,
    inspect_download_output_directory_payload,
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
from finiq.market_desk.web.utility import run_partition_storage_payload

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


def _choose_finder_path(*, mode: str, title: str, default_path: str = "") -> str:
    return _router_choose_finder_path(mode=mode, title=title, default_path=default_path)


app.include_router(create_config_router(config, choose_finder_path=lambda **kwargs: _choose_finder_path(**kwargs)))

# --- Async Job Management ---

JobProgressCallback = Callable[[str], None]
JobHandler = Callable[[dict[str, Any], JobProgressCallback], Any]


def _run_asset_excel_convert_job(payload: dict[str, Any], progress_callback: JobProgressCallback) -> dict[str, Any]:
    return convert_asset_excels_to_wide_parquet(
        ASSETS_DIR,
        payload.get("output_directory") or DEFAULT_ASSET_PARQUET_DIR,
        selected_files=payload.get("selected_files") or None,
        conflict_policy=str(payload.get("conflict_policy") or "error"),
        write_mode=str(payload.get("write_mode") or "update"),
        progress_callback=progress_callback,
    )


JOB_HANDLERS: dict[str, JobHandler] = {
    "download": download_disclosure_html_payload,
    "external_compress": compress_disclosure_external_html_payload,
    "content_download": download_disclosure_html_contents_payload,
    "content_merge": merge_disclosure_content_html_payload,
    "parse": parse_disclosure_html_payload,
    "integrated_convert": run_integrated_convert_payload,
    "integrated_merge": run_integrated_merge_payload,
    "integrated_market_history": run_integrated_market_history_payload,
    "table_build": build_disclosure_table_payload,
    "utility_partition": run_partition_storage_payload,
    "asset_excel_convert": _run_asset_excel_convert_job,
}


def _run_job_worker(job_id: str, kind: str, payload: dict[str, Any]):
    try:
        job_manager.start_job(job_id)
        progress_callback = lambda m: job_manager.add_log(job_id, m)
        handler = JOB_HANDLERS.get(kind)
        if handler is None:
            raise ValueError(f"Unhandled job kind: {kind}")

        result = handler(payload, progress_callback=progress_callback)
        job_manager.complete_job(job_id, result)
    except Exception as exc:
        job_manager.fail_job(job_id, str(exc))

# --- Helper Functions ---

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

class AssetExcelConvertRequest(BaseModel):
    output_directory: Optional[str] = None
    selected_files: List[str] = []
    conflict_policy: str = "error"
    write_mode: str = "update"

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

@app.get("/api/assets/excels")
async def get_asset_excels():
    return {
        "root_directory": str(ASSETS_DIR.resolve()),
        "excel_files": list_asset_excel_files(ASSETS_DIR),
    }

@app.get("/api/assets/excels/output")
async def get_asset_excel_output(output_directory: Optional[str] = None):
    return inspect_asset_excel_output(output_directory or DEFAULT_ASSET_PARQUET_DIR)

@app.post("/api/assets/excels/preview-conversion")
async def preview_asset_excel_conversion(request: AssetExcelConvertRequest):
    try:
        return await asyncio.to_thread(
            inspect_asset_excel_conversion,
            ASSETS_DIR,
            request.output_directory or DEFAULT_ASSET_PARQUET_DIR,
            selected_files=request.selected_files or None,
            conflict_policy=request.conflict_policy,
            write_mode=request.write_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/api/assets/excels/convert-wide-parquet")
async def convert_asset_excels(request: AssetExcelConvertRequest):
    try:
        return await asyncio.to_thread(
            convert_asset_excels_to_wide_parquet,
            ASSETS_DIR,
            request.output_directory or DEFAULT_ASSET_PARQUET_DIR,
            selected_files=request.selected_files or None,
            conflict_policy=request.conflict_policy,
            write_mode=request.write_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.post("/api/assets/excels/convert-wide-parquet/start")
async def start_convert_asset_excels(request: AssetExcelConvertRequest, background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex
    job_manager.create_job(job_id, "asset_excel_convert")
    background_tasks.add_task(
        _run_job_worker,
        job_id,
        "asset_excel_convert",
        request.model_dump(),
    )
    return job_manager.get_snapshot(job_id)

@app.get("/api/assets/excels/jobs/{job_id}")
async def get_asset_excel_job_status(job_id: str):
    snapshot = job_manager.get_snapshot(job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Job not found")
    return snapshot

@app.get("/api/assets/excels/{file_name:path}")
async def get_asset_excel(
    file_name: str,
    sheet_name: Optional[str] = None,
    row_limit: Optional[int] = 100,
    interpreted: bool = False,
):
    try:
        if interpreted:
            if sheet_name is None:
                raise ValueError("sheet_name is required for interpreted preview")
            return read_asset_excel_interpreted(
                file_name,
                sheet_name=sheet_name,
                row_limit=row_limit,
                root_directory=ASSETS_DIR,
            )
        return read_asset_excel(
            file_name,
            sheet_name=sheet_name,
            row_limit=row_limit,
            root_directory=ASSETS_DIR,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (IsADirectoryError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/api/companies")
async def get_companies(
    classification_path: Optional[str] = None,
    keyword: Optional[str] = None,
    market: str = "전체"
):
    path = ""
    if classification_path and Path(classification_path).exists():
        path = classification_path
    elif config.selected_classification_path and Path(config.selected_classification_path).exists():
        path = config.selected_classification_path
    else:
        path = resolve_default_classification(config.output_root) or ""

    if not path or not Path(path).exists():
        return {"summary": {}, "markets": ["전체"], "companies": []}

    try:
        return load_company_index_payload(path, keyword=keyword, market=market)
    except Exception:
        return {"summary": {}, "markets": ["전체"], "companies": []}

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
    path = classification_path
    if not Path(path).exists():
        path = config.selected_classification_path or resolve_default_classification(config.output_root) or ""
        
    if not path or not Path(path).exists():
        return {
            "company": {"company_name": "알 수 없음" if company_key != "demo" else "FINIQ (데모)", "market": "", "disclosure_count": 0, "badges": []},
            "chart": {"candles": [], "markers": [], "groups": []},
            "timeline": [],
            "display_frequency_label": display_frequency,
            "range_start": "",
            "range_end": "",
            "visible_range_end": "",
            "manual_start": start_date or "",
            "manual_end": end_date or "",
            "stock_code": stock_code or "",
            "inferred_stock_code": "",
            "messages": ["분류 파일을 찾을 수 없습니다."],
        }

    try:
        return build_insight_payload(
            path,
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
    path = classification_path
    if not Path(path).exists():
        path = config.selected_classification_path or resolve_default_classification(config.output_root) or ""
        
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Classification file not found")

    try:
        payload = build_company_list_export(path, keyword=keyword, market=market)
        filename = f"{Path(path).stem}.company_list.xlsx"
        temp_path = Path(f"/tmp/{filename}")
        temp_path.write_bytes(payload)
        return FileResponse(temp_path, filename=filename, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

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

@app.post("/api/download/inspect-folder")
async def download_inspect_folder_route(payload: dict[str, Any]):
    return inspect_download_output_directory_payload(payload)

@app.post("/api/download/run/start")
async def download_start_route(payload: dict[str, Any]):
    return start_download_job(payload)

@app.post("/api/download/run/cancel")
async def download_cancel_route(payload: dict[str, Any]):
    try:
        return cancel_download_job(str(payload.get("job_id") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

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

@app.get("/api/utility/jobs/{job_id}")
async def get_utility_job_status(job_id: str):
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

@app.post("/api/utility/partition-storage/start")
async def start_partition_storage(payload: dict[str, Any], background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex
    job_manager.create_job(job_id, "utility_partition")
    background_tasks.add_task(_run_job_worker, job_id, "utility_partition", payload)
    return job_manager.get_snapshot(job_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.host, port=config.port)
