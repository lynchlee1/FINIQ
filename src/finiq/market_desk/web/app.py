from __future__ import annotations

import inspect
import time
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from finiq.config import QUANTIWISE_EXCEL_DIR, init_config
from finiq.data.assets_excel import (
    cleanup_duplicate_asset_parquet_outputs,
    convert_asset_excels_to_wide_parquet,
    merge_asset_parquet_outputs,
)
from finiq.market_desk.web.features.disclosures.internal_html_download import download_disclosure_internal_html_payload
from finiq.market_desk.web.features.disclosures.external_html_download import download_disclosure_external_html_payload
from finiq.market_desk.web.features.disclosures.external_html_compress import compress_disclosure_external_html_payload
from finiq.market_desk.web.features.disclosures.html_cleanup import (
    create_external_html_integrity_baseline_payload,
    create_internal_html_integrity_baseline_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_common import parse_disclosure_html_payload
from finiq.market_desk.web.features.disclosures.html_sections import (
    inspect_disclosure_html_sections_payload,
    save_disclosure_html_sections_payload,
    summarize_disclosure_html_section_kinds_payload,
)
from finiq.market_desk.web.features.disclosure_workflow.automation import (
    run_disclosure_automation_payload,
)
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
)
from finiq.market_desk.web.features.market_data.discovery import (
    list_classification_files,
    list_price_source_files,
)
from finiq.market_desk.web.jobs import job_manager
from finiq.market_desk.web.routers.assets_excel import create_assets_excel_router
from finiq.market_desk.web.routers.config import (
    _choose_finder_path as _router_choose_finder_path,
)
from finiq.market_desk.web.routers.config import (
    _normalize_file_dialog_mode,
    create_config_router,
)
from finiq.market_desk.web.routers.download import create_download_router
from finiq.market_desk.web.routers.market_data import create_market_data_router
from finiq.market_desk.web.routers.workflows import create_workflows_router
from finiq.market_desk.web.features.market_data.service_integrated import (
    run_integrated_convert_payload,
    run_integrated_market_history_payload,
    run_integrated_merge_payload,
)
from finiq.market_desk.web.features.market_data.service_payloads import (
    filter_disclosures_payload,
    search_disclosure_titles_payload,
)
from finiq.market_desk.web.features.disclosures.table_export import build_disclosure_table_payload
from finiq.market_desk.web.features.downloads.kind_coordination import (
    KIND_NETWORK_JOB_LOCK,
)
from finiq.market_desk.web.features.downloads.kind_common import (
    configure_download_job_retention,
)
from finiq.market_desk.web.features.storage.partition import run_partition_storage_payload

app = FastAPI(title="FINIQ MarketDesk API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config = init_config()
job_manager.set_retention_minutes(config.job_retention_minutes)
configure_download_job_retention(config.job_retention_minutes)


def _choose_finder_path(*, mode: str, title: str, default_path: str = "") -> str:
    return _router_choose_finder_path(mode=mode, title=title, default_path=default_path)


JobProgressCallback = Callable[[str], None]
JobHandler = Callable[[dict[str, Any], JobProgressCallback], Any]


def _required_payload_path(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _run_asset_excel_convert_job(
    payload: dict[str, Any],
    progress_callback: JobProgressCallback,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    return convert_asset_excels_to_wide_parquet(
        _required_payload_path(payload, "source_directory"),
        _required_payload_path(payload, "output_directory"),
        selected_files=payload.get("selected_files") or None,
        account_mappings=payload.get("account_mappings")
        if "account_mappings" in payload
        else None,
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
        _required_payload_path(payload, "target_directory"),
        _required_payload_path(payload, "output_directory")
        if not payload.get("same_directory")
        else _required_payload_path(payload, "target_directory"),
        selected_files=payload.get("selected_files") or [],
        same_directory=bool(payload.get("same_directory")),
        cleanup_merged_items=bool(payload.get("cleanup_merged_items", True)),
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )


def _run_asset_parquet_duplicate_cleanup_job(
    payload: dict[str, Any],
    progress_callback: JobProgressCallback,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    return cleanup_duplicate_asset_parquet_outputs(
        _required_payload_path(payload, "target_directory"),
        dry_run=bool(payload.get("dry_run", True)),
        delete_confirmed=bool(payload.get("delete_confirmed")),
        delete_confirmation_text=str(payload.get("delete_confirmation_text") or ""),
        scan_recursive=bool(payload.get("scan_recursive")),
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )


JOB_HANDLERS: dict[str, JobHandler] = {
    "title_search": search_disclosure_titles_payload,
    "external_html_download": download_disclosure_external_html_payload,
    "external_html_compress": compress_disclosure_external_html_payload,
    "external_html_integrity_baseline": create_external_html_integrity_baseline_payload,
    "internal_html_download": download_disclosure_internal_html_payload,
    "internal_html_integrity_baseline": create_internal_html_integrity_baseline_payload,
    "parse": parse_disclosure_html_payload,
    "section_inspect": inspect_disclosure_html_sections_payload,
    "section_kinds": summarize_disclosure_html_section_kinds_payload,
    "section_save": save_disclosure_html_sections_payload,
    "integrated_convert": run_integrated_convert_payload,
    "integrated_merge": run_integrated_merge_payload,
    "integrated_market_history": run_integrated_market_history_payload,
    "table_build": build_disclosure_table_payload,
    "disclosure_automation": run_disclosure_automation_payload,
    "utility_partition": run_partition_storage_payload,
    "asset_excel_convert": _run_asset_excel_convert_job,
    "asset_excel_merge": _run_asset_excel_merge_job,
    "asset_parquet_duplicate_cleanup": _run_asset_parquet_duplicate_cleanup_job,
}


def _run_job_worker(job_id: str, kind: str, payload: dict[str, Any]):
    worker_started_at = time.monotonic()
    try:
        if not job_manager.start_job(job_id):
            return
        def progress_callback(message: object) -> None:
            if kind == "title_search" and isinstance(message, dict):
                job_manager.add_log(
                    job_id,
                    "제목 검색 "
                    f"{int(message.get('completed') or 0)}/"
                    f"{int(message.get('total') or 0)} · "
                    f"일치 {int(message.get('records') or 0)}건",
                )
                return
            job_manager.add_log(job_id, str(message))

        handler = JOB_HANDLERS.get(kind)
        if handler is None:
            raise ValueError(f"Unhandled job kind: {kind}")

        import inspect

        sig = inspect.signature(handler)
        kwargs = {"progress_callback": progress_callback}
        if "cancel_check" in sig.parameters:
            kwargs["cancel_check"] = lambda: job_manager.is_cancelled(job_id)

        if kind in {
            "external_html_download",
            "internal_html_download",
            "disclosure_automation",
        }:
            network_wait_started_at = time.monotonic()
            progress_callback(
                "다른 KIND 네트워크 작업이 끝날 때까지 대기합니다."
            )
            with KIND_NETWORK_JOB_LOCK:
                progress_callback(
                    "KIND 네트워크 작업 대기 완료: "
                    f"{time.monotonic() - network_wait_started_at:.1f}초. "
                    "실제 처리를 시작합니다."
                )
                result = handler(apply_workspace_defaults(kind, payload), **kwargs)
        else:
            handler_payload = (
                payload if kind == "title_search" else apply_workspace_defaults(kind, payload)
            )
            progress_callback(f"실제 처리 시작: kind={kind}")
            result = handler(handler_payload, **kwargs)

        if job_manager.is_cancelled(job_id) or (
            isinstance(result, dict) and result.get("cancelled") is True
        ):
            job_manager.cancel_job(job_id)
            return

        progress_callback(
            f"실제 처리 완료: kind={kind} · "
            f"총 {time.monotonic() - worker_started_at:.1f}초"
        )
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


def _search_disclosure_titles_payload(
    *args: Any, **kwargs: Any
) -> dict[str, Any]:
    return search_disclosure_titles_payload(*args, **kwargs)


app.include_router(
    create_config_router(
        config, choose_finder_path=lambda **kwargs: _choose_finder_path(**kwargs)
    )
)
app.include_router(create_market_data_router(config))
app.include_router(
    create_assets_excel_router(
        config=config,
        get_assets_dir=lambda: QUANTIWISE_EXCEL_DIR,
        run_job_worker=_run_job_worker,
    )
)
app.include_router(create_download_router(config))
app.include_router(
    create_workflows_router(
        filter_disclosures_payload=_filter_disclosures_payload,
        search_disclosure_titles_payload=_search_disclosure_titles_payload,
        run_job_worker=_run_job_worker,
    )
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.host, port=config.port)
