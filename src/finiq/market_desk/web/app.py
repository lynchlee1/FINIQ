from __future__ import annotations

import inspect
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from finiq.config import QUANTIWISE_EXCEL_DIR, init_config
from finiq.data.assets_excel import DEFAULT_ASSET_PARQUET_DIR, convert_asset_excels_to_wide_parquet, merge_asset_parquet_outputs
from finiq.market_desk.web.discovery import list_classification_files, list_price_source_files
from finiq.market_desk.web.disclosure_html import (
    compress_disclosure_external_html_payload,
    download_disclosure_html_contents_payload,
    download_disclosure_html_payload,
    merge_disclosure_content_html_payload,
)
from finiq.market_desk.web.disclosure_html_parse import parse_disclosure_html_payload
from finiq.market_desk.web.jobs import job_manager
from finiq.market_desk.web.routers.assets_excel import create_assets_excel_router
from finiq.market_desk.web.routers.config import (
    _choose_finder_path as _router_choose_finder_path,
    _normalize_file_dialog_mode,
    create_config_router,
)
from finiq.market_desk.web.routers.download import create_download_router
from finiq.market_desk.web.routers.market_data import create_market_data_router
from finiq.market_desk.web.routers.workflows import create_workflows_router
from finiq.market_desk.web.service import (
    filter_disclosures_payload,
    run_integrated_convert_payload,
    run_integrated_market_history_payload,
    run_integrated_merge_payload,
)
from finiq.market_desk.web.table_export import build_disclosure_table_payload
from finiq.market_desk.web.utility import run_partition_storage_payload

app = FastAPI(title="FINIQ MarketDesk API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config = init_config()


def _choose_finder_path(*, mode: str, title: str, default_path: str = "") -> str:
    return _router_choose_finder_path(mode=mode, title=title, default_path=default_path)


JobProgressCallback = Callable[[str], None]
JobHandler = Callable[[dict[str, Any], JobProgressCallback], Any]


def _run_asset_excel_convert_job(
    payload: dict[str, Any],
    progress_callback: JobProgressCallback,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    return convert_asset_excels_to_wide_parquet(
        payload.get("source_directory") or QUANTIWISE_EXCEL_DIR,
        payload.get("output_directory") or DEFAULT_ASSET_PARQUET_DIR,
        selected_files=payload.get("selected_files") or None,
        write_mode=str(payload.get("write_mode") or "update"),
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )


def _run_asset_excel_merge_job(
    payload: dict[str, Any],
    progress_callback: JobProgressCallback,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    return merge_asset_parquet_outputs(
        payload.get("base_directory") or "",
        payload.get("incoming_directory") or "",
        payload.get("output_directory") or DEFAULT_ASSET_PARQUET_DIR,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
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
    "asset_excel_merge": _run_asset_excel_merge_job,
}


def _run_job_worker(job_id: str, kind: str, payload: dict[str, Any]):
    try:
        if not job_manager.start_job(job_id):
            return
        progress_callback = lambda m: job_manager.add_log(job_id, m)
        handler = JOB_HANDLERS.get(kind)
        if handler is None:
            raise ValueError(f"Unhandled job kind: {kind}")

        import inspect
        sig = inspect.signature(handler)
        kwargs = {"progress_callback": progress_callback}
        if "cancel_check" in sig.parameters:
            kwargs["cancel_check"] = lambda: job_manager.is_cancelled(job_id)

        result = handler(payload, **kwargs)

        if job_manager.is_cancelled(job_id) or (isinstance(result, dict) and result.get("cancelled") is True):
            job_manager.cancel_job(job_id)
            return

        job_manager.complete_job(job_id, result)
    except Exception as exc:
        if job_manager.is_cancelled(job_id):
            return
        job_manager.fail_job(job_id, str(exc))



def _filter_disclosures_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
    sig = inspect.signature(filter_disclosures_payload)
    if "cancel_check" not in sig.parameters and not any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in sig.parameters.values()
    ):
        kwargs.pop("cancel_check", None)
    return filter_disclosures_payload(*args, **kwargs)


app.include_router(create_config_router(config, choose_finder_path=lambda **kwargs: _choose_finder_path(**kwargs)))
app.include_router(create_market_data_router(config))
app.include_router(create_assets_excel_router(get_assets_dir=lambda: QUANTIWISE_EXCEL_DIR, run_job_worker=_run_job_worker))
app.include_router(create_download_router(config))
app.include_router(
    create_workflows_router(
        config=config,
        filter_disclosures_payload=_filter_disclosures_payload,
        run_job_worker=_run_job_worker,
    )
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.host, port=config.port)
