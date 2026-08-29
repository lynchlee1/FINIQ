from __future__ import annotations

import json
import queue
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from finiq.market_desk.web.features.disclosures.html_cleanup import (
    check_disclosure_html_output_directory_payload,
    clean_disclosure_html_output_directory_payload,
    create_external_html_integrity_baseline_payload,
    inspect_all_disclosure_external_html_payload,
    inspect_all_disclosure_internal_html_payload,
    write_disclosure_html_manifest_payload,
)
from finiq.market_desk.web.features.disclosures.filter_presets import (
    begin_filter_workflow_payload,
    complete_filter_workflow_payload,
    fail_filter_workflow_payload,
    interrupt_filter_workflow_payload,
    manage_filter_presets_payload,
    mark_filter_workflow_query_completed,
)
from finiq.market_desk.web.features.disclosures.html_common import (
    cancel_disclosure_html_download,
    resolve_disclosure_html_file,
)
from finiq.market_desk.web.features.disclosures.external_html_compress import (
    inspect_all_disclosure_external_html_compress_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_changes import (
    build_parse_change_log_payload,
    resolve_parse_change_log_output_directory,
)
from finiq.market_desk.web.features.disclosures.html_parse_common import (
    cancel_disclosure_html_parse,
    inspect_disclosure_html_parse_payload,
    list_parser_methods_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_export import (
    build_parse_export_xlsx,
)
from finiq.market_desk.web.features.disclosures.html_parse_preview import (
    build_parse_filter_candidates_payload,
    build_parse_preview_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_summary import (
    build_bond_parse_summary_payload,
)
from finiq.market_desk.web.features.disclosures.disclosure_graph import (
    build_disclosure_graph_payload,
    load_disclosure_graph_payload,
)
from finiq.market_desk.web.features.disclosures.html_sections import (
    inspect_disclosure_html_sections_payload,
    list_disclosure_html_section_sources_payload,
    split_disclosure_html_section_source_payload,
    summarize_disclosure_html_section_kinds_payload,
)
from finiq.market_desk.web.jobs import job_manager
from finiq.market_desk.web.features.disclosures.table_export import (
    build_disclosure_table_payload,
    inspect_disclosure_table_payload,
)
from finiq.market_desk.web.features.disclosure_workflow.automation import (
    build_automation_plan_payload,
    inspect_disclosure_workspace_payload,
)
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
    atomic_write_json,
    manage_disclosure_stage_links_payload,
    prepare_disclosure_workspace_payload,
    validate_workspace_mode,
)
from finiq.market_desk.web.features.market_data.service_records import FilterCancelled

FilterDisclosuresPayload = Callable[..., dict[str, Any]]
SearchDisclosureTitlesPayload = Callable[..., dict[str, Any]]
RunJobWorker = Callable[[str, str, dict[str, Any]], None]
FILTER_STREAM_HEARTBEAT_SECONDS = 10.0


def _filter_output_directory(value: object) -> str:
    output_text = str(value or "").strip()
    if not output_text:
        raise ValueError("filter output directory is required")
    output_root = Path(output_text).expanduser().resolve()
    if output_root.suffix.lower() == ".json" or (
        output_root.exists() and not output_root.is_dir()
    ):
        raise ValueError("filter output path must be a directory")
    return str(output_root)


def _write_transfer_file(
    payload: dict[str, Any], *, output_directory: str, mode: object,
    parent_mode: object = None,
) -> dict[str, Any]:
    normalized_mode = validate_workspace_mode(mode)
    output_root = Path(_filter_output_directory(output_directory))
    if parent_mode is not None and str(parent_mode).strip():
        normalized_parent = validate_workspace_mode(parent_mode)
        if normalized_parent == normalized_mode:
            raise ValueError("parent_mode must be different from mode")
        transfer_path = (
            output_root
            / normalized_parent
            / "subfilters"
            / normalized_mode
            / "filtered.json"
        )
    else:
        transfer_path = output_root / normalized_mode / "filtered.json"

    payload["mode"] = normalized_mode
    acpt_numbers = payload.get("external_html_download_acpt_numbers")
    if not isinstance(acpt_numbers, list):
        raise ValueError(
            "external_html_download_acpt_numbers must be a list"
        )
    atomic_write_json(transfer_path, payload)
    return {
        "format": payload.get("format", ""),
        "path": str(transfer_path),
        "acpt_numbers": len(acpt_numbers),
    }


def _attach_external_html_download_transfer(
    payload: dict[str, Any], *, output_directory: str, mode: object,
    parent_mode: object = None,
) -> dict[str, Any]:
    if payload.get("format") == "kind_disclosure_filter_v1":
        payload["external_html_download_transfer"] = _write_transfer_file(
            payload,
            output_directory=output_directory,
            mode=mode,
            parent_mode=parent_mode,
        )
    return payload


def _finish_filter_workflow(
    payload: dict[str, Any], *, body: dict[str, Any], workflow_run: dict[str, Any]
) -> dict[str, Any]:
    mark_filter_workflow_query_completed(
        data_root=body.get("data_root"),
        mode=workflow_run["mode"],
        run_id=workflow_run["run_id"],
        summary=payload.get("summary"),
        parent_mode=workflow_run.get("parent_mode"),
    )
    completed_workflow = complete_filter_workflow_payload(
        data_root=body.get("data_root"),
        mode=workflow_run["mode"],
        run_id=workflow_run["run_id"],
        result=payload,
        parent_mode=workflow_run.get("parent_mode"),
    )
    merged_result = completed_workflow.pop("result")
    _attach_external_html_download_transfer(
        merged_result,
        output_directory=str(body.get("external_html_transfer_path") or "").strip(),
        mode=body.get("mode"),
        parent_mode=body.get("parent_mode"),
    )
    transfer = merged_result.get("external_html_download_transfer")
    if not isinstance(transfer, dict):
        raise ValueError("filter workflow did not record a result file")
    merged_result["filter_workflow"] = completed_workflow
    return merged_result


def _fail_filter_workflow(
    *, body: dict[str, Any], workflow_run: dict[str, Any], error: Exception
) -> None:
    if isinstance(error, FilterCancelled):
        interrupt_filter_workflow_payload(
            data_root=body.get("data_root"),
            mode=workflow_run["mode"],
            run_id=workflow_run["run_id"],
            partial_result=error.partial_payload,
            parent_mode=workflow_run.get("parent_mode"),
        )
        return
    fail_filter_workflow_payload(
        data_root=body.get("data_root"),
        mode=workflow_run["mode"],
        run_id=workflow_run["run_id"],
        error=error,
        parent_mode=workflow_run.get("parent_mode"),
    )


def _load_filter_preset_file(source_json_path: str) -> dict[str, Any]:
    source_path = Path(source_json_path).expanduser().resolve()
    if source_path.name != "filter.json":
        raise ValueError("모드 폴더의 filter.json 파일을 선택하세요.")
    if not source_path.is_file():
        raise ValueError(f"필터 JSON 파일을 찾을 수 없습니다: {source_path}")
    mode = validate_workspace_mode(source_path.parent.name)
    if (
        source_path.parent.parent.name == "subfilters"
        and source_path.parents[3].name != "03-filter"
    ):
        raise ValueError("파생 필터는 한 단계만 지원합니다.")
    parent_mode = (
        validate_workspace_mode(source_path.parents[2].name)
        if source_path.parent.parent.name == "subfilters"
        else None
    )

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("format") != "finiq_disclosure_filter_workflow"
        or payload.get("mode") != mode
    ):
        raise ValueError("필터 JSON 형식이 올바르지 않습니다.")
    steps = payload.get("steps")
    condition_input = steps.get("condition_input") if isinstance(steps, dict) else None
    filter_blocks = (
        condition_input.get("filter_blocks")
        if isinstance(condition_input, dict)
        else None
    )
    if not isinstance(filter_blocks, list):
        raise ValueError("필터 JSON에 steps.condition_input.filter_blocks가 없습니다.")
    result = {
        "format": "kind_disclosure_filter_preset_v1",
        "source_json_path": str(source_path),
        "name": mode,
        "mode": mode,
        "condition_blocks": filter_blocks,
    }
    if parent_mode is not None:
        if payload.get("parent_mode") != parent_mode:
            raise ValueError(
                "필터 JSON의 parent_mode와 폴더가 일치하지 않습니다."
            )
        result["id"] = f"{parent_mode}/{mode}"
        result["parent_mode"] = parent_mode
    else:
        result["id"] = mode
    return result


def _job_snapshot(job_id: str) -> dict[str, Any]:
    snapshot = job_manager.get_snapshot(job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Job not found")
    return snapshot


def _start_background_job(
    *,
    kind: str,
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
    run_job_worker: RunJobWorker,
) -> dict[str, Any]:
    requested_job_id = str(payload.pop("job_id", "") or "").strip()
    try:
        job_id = uuid.UUID(requested_job_id).hex if requested_job_id else uuid.uuid4().hex
    except ValueError as exc:
        raise ValueError("job_id must be a UUID") from exc
    if job_manager.get_job(job_id) is not None:
        raise ValueError(f"job already exists: {job_id}")
    job_manager.create_job(job_id, kind)
    background_tasks.add_task(run_job_worker, job_id, kind, payload)
    return job_manager.get_snapshot(job_id)


def create_workflows_router(
    *,
    filter_disclosures_payload: FilterDisclosuresPayload,
    search_disclosure_titles_payload: SearchDisclosureTitlesPayload,
    run_job_worker: RunJobWorker,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/disclosures/titles/search")
    async def search_disclosure_titles(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(search_disclosure_titles_payload, payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/titles/search/start")
    async def start_disclosure_title_search(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="title_search",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.get("/api/disclosures/titles/jobs/{job_id}")
    async def get_disclosure_title_search_job(job_id: str):
        return _job_snapshot(job_id)

    @router.post("/api/disclosures/titles/search/cancel")
    async def cancel_disclosure_title_search(payload: dict[str, Any]):
        job_id = str(payload.get("job_id") or "").strip()
        if not job_id:
            raise HTTPException(status_code=400, detail="Missing job_id")
        if not job_manager.cancel_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return {"status": "success", "job_id": job_id}

    @router.post("/api/disclosures/filter")
    async def filter_disclosures(request: Request):
        try:
            body = apply_workspace_defaults("filter", await request.json())
            body["mode"] = validate_workspace_mode(body.get("mode"))
            body["include_external_html_download_acpt_numbers"] = True
            body["external_html_transfer_path"] = _filter_output_directory(
                body.get("external_html_transfer_path")
            )
            workflow_run = begin_filter_workflow_payload(body)
            if "parent_acpt_numbers" in workflow_run:
                body["acpt_numbers"] = workflow_run["parent_acpt_numbers"]
                body["restrict_acpt_numbers"] = True
            body["source_offset"] = workflow_run["source_offset"]
            body["source_expected_count"] = workflow_run[
                "source_expected_count"
            ]
            body["source_expected_fingerprint"] = workflow_run[
                "source_expected_fingerprint"
            ]
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        accept = request.headers.get("Accept", "")
        if "application/x-ndjson" in accept:

            def generate():
                cancel_event = threading.Event()
                events: queue.Queue[dict[str, Any]] = queue.Queue()
                stream_started_at = time.monotonic()
                last_progress_at = stream_started_at
                last_heartbeat_at = stream_started_at

                def run_filter() -> None:
                    try:
                        payload = filter_disclosures_payload(
                            body,
                            progress_callback=lambda progress: events.put(
                                {"type": "progress", "progress": progress}
                            ),
                            cancel_check=cancel_event.is_set,
                        )
                        payload = _finish_filter_workflow(
                            payload,
                            body=body,
                            workflow_run=workflow_run,
                        )
                        events.put({"type": "result", "payload": payload})
                    except Exception as e:
                        _fail_filter_workflow(
                            body=body,
                            workflow_run=workflow_run,
                            error=e,
                        )
                        events.put({"type": "error", "error": str(e)})

                thread = threading.Thread(target=run_filter, daemon=True)
                thread.start()
                try:
                    while thread.is_alive() or not events.empty():
                        try:
                            event = events.get(timeout=0.1)
                        except queue.Empty:
                            now = time.monotonic()
                            if (
                                thread.is_alive()
                                and now - last_progress_at >= FILTER_STREAM_HEARTBEAT_SECONDS
                                and now - last_heartbeat_at >= FILTER_STREAM_HEARTBEAT_SECONDS
                            ):
                                yield json.dumps(
                                    {
                                        "type": "heartbeat",
                                        "elapsed_seconds": now - stream_started_at,
                                        "progress_idle_seconds": now - last_progress_at,
                                    },
                                    ensure_ascii=False,
                                ) + "\n"
                                last_heartbeat_at = now
                            continue
                        if event.get("type") == "progress":
                            last_progress_at = time.monotonic()
                            last_heartbeat_at = last_progress_at
                        yield json.dumps(event, ensure_ascii=False) + "\n"
                finally:
                    cancel_event.set()

            return StreamingResponse(generate(), media_type="application/x-ndjson")
        try:
            payload = filter_disclosures_payload(body)
            return _finish_filter_workflow(
                payload,
                body=body,
                workflow_run=workflow_run,
            )
        except Exception as exc:
            _fail_filter_workflow(
                body=body,
                workflow_run=workflow_run,
                error=exc,
            )
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/filter/preset")
    async def load_disclosure_filter_preset(payload: dict[str, Any]):
        source_json_path = str(payload.get("source_json_path") or "").strip()
        if not source_json_path:
            raise HTTPException(status_code=400, detail="필터 JSON 경로를 선택하세요.")
        try:
            return _load_filter_preset_file(source_json_path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/filter/presets")
    async def manage_disclosure_filter_presets(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(manage_filter_presets_payload, payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/table/build")
    async def build_disclosure_table(payload: dict[str, Any]):
        return build_disclosure_table_payload(
            apply_workspace_defaults("table_build", payload)
        )

    @router.post("/api/disclosures/table/build/start")
    async def start_build_disclosure_table(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="table_build",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/table/inspect")
    async def inspect_disclosure_table(payload: dict[str, Any]):
        return await run_in_threadpool(
            inspect_disclosure_table_payload,
            apply_workspace_defaults("table_build", payload),
        )

    @router.post("/api/disclosures/workspace/prepare")
    async def prepare_disclosure_workspace(payload: dict[str, Any]):
        try:
            return prepare_disclosure_workspace_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/workspace/stage-links")
    async def manage_disclosure_stage_links(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(
                manage_disclosure_stage_links_payload, payload
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosure-workflows/plan")
    async def build_disclosure_automation_plan(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(build_automation_plan_payload, payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosure-workflows/inspect")
    async def inspect_disclosure_workspace(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(
                inspect_disclosure_workspace_payload, payload
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosure-workflows/run/start")
    async def start_disclosure_automation(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        try:
            build_automation_plan_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return _start_background_job(
            kind="disclosure_automation",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.get("/api/disclosure-workflows/jobs/{job_id}")
    async def get_disclosure_automation_job(job_id: str):
        return _job_snapshot(job_id)

    @router.post("/api/disclosure-workflows/run/cancel")
    async def cancel_disclosure_automation(payload: dict[str, Any]):
        job_id = str(payload.get("job_id") or "").strip()
        if not job_id:
            raise HTTPException(status_code=400, detail="Missing job_id")
        if not job_manager.cancel_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return {"status": "success", "job_id": job_id}

    @router.post("/api/disclosures/table/build/cancel")
    async def cancel_build_disclosure_table(payload: dict[str, Any]):
        job_id = str(payload.get("job_id") or "").strip()
        if not job_id:
            raise HTTPException(status_code=400, detail="Missing job_id")
        if not job_manager.cancel_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return {"status": "success", "job_id": job_id}

    @router.get("/api/disclosures/table/jobs/{job_id}")
    async def get_table_job_status(job_id: str):
        return _job_snapshot(job_id)

    @router.get("/api/disclosures/html/jobs/{job_id}")
    async def get_html_job_status(job_id: str):
        return _job_snapshot(job_id)

    @router.get("/api/integrated-data/jobs/{job_id}")
    async def get_integrated_job_status(job_id: str):
        return _job_snapshot(job_id)

    @router.post("/api/integrated-data/cancel")
    async def cancel_integrated_job(payload: dict[str, Any]):
        job_id = str(payload.get("job_id") or "").strip()
        if not job_id:
            raise HTTPException(status_code=400, detail="Missing job_id")
        if not job_manager.cancel_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return {"status": "success", "job_id": job_id}

    @router.get("/api/utility/jobs/{job_id}")
    async def get_utility_job_status(job_id: str):
        return _job_snapshot(job_id)

    @router.post("/api/utility/cancel")
    async def cancel_utility_job(payload: dict[str, Any]):
        job_id = str(payload.get("job_id") or "").strip()
        if not job_id:
            raise HTTPException(status_code=400, detail="Missing job_id")
        if not job_manager.cancel_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return {"status": "success", "job_id": job_id}

    @router.post("/api/disclosures/external-html-download/start")
    async def start_external_html_download(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="external_html_download",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/external-html-download/cancel")
    async def cancel_external_html_download_route(payload: dict[str, Any]):
        return cancel_disclosure_html_download(str(payload.get("cancel_token") or ""))

    @router.post("/api/disclosures/external-html-download/inspect-folder")
    def inspect_external_html_download_folder(payload: dict[str, Any]):
        try:
            return clean_disclosure_html_output_directory_payload(
                apply_workspace_defaults("external_html_download", payload)
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/external-html-download/check-existing")
    def check_external_html_download_folder(payload: dict[str, Any]):
        try:
            return inspect_all_disclosure_external_html_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/external-html-download/trust-existing/start")
    async def start_external_html_integrity_baseline(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="external_html_integrity_baseline",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/external-html-download/redownload/start")
    async def start_missing_external_html_redownload(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="external_html_redownload",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/external-html-download/compress/start")
    async def start_external_html_compress(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="external_html_compress",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/external-html-download/compress/check-existing")
    def check_external_html_compress(payload: dict[str, Any]):
        try:
            return inspect_all_disclosure_external_html_compress_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/external-html-download/compress/repair/start")
    async def start_invalid_external_html_compress_repair(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="external_html_compress_repair",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/internal-html-download/start")
    async def start_internal_html_download(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="internal_html_download",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/internal-html-download/cancel")
    async def cancel_internal_html_download_route(payload: dict[str, Any]):
        return cancel_disclosure_html_download(str(payload.get("cancel_token") or ""))

    @router.post("/api/disclosures/internal-html-download/inspect-folder")
    def inspect_internal_html_download_folder(payload: dict[str, Any]):
        try:
            return clean_disclosure_html_output_directory_payload(
                apply_workspace_defaults("internal_html_download", payload)
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/internal-html-download/check-existing")
    def check_internal_html_download_folder(payload: dict[str, Any]):
        try:
            return inspect_all_disclosure_internal_html_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/internal-html-download/redownload/start")
    async def start_missing_internal_html_redownload(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="internal_html_redownload",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/internal-html-download/trust-existing/start")
    async def start_internal_html_integrity_baseline(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="internal_html_integrity_baseline",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/html/manifest/write")
    async def write_html_manifest(payload: dict[str, Any]):
        try:
            return write_disclosure_html_manifest_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/parse/start")
    async def start_html_parse(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="parse",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.get("/api/disclosures/html/parse/methods")
    async def list_html_parser_methods():
        return list_parser_methods_payload()

    @router.post("/api/disclosures/html/sections/save/start")
    async def start_html_section_save(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="section_save",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/html/sections/inspect/start")
    async def start_html_section_inspect(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="section_inspect",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/html/sections/kinds/start")
    async def start_html_section_kinds(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="section_kinds",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/html/sections/inspect")
    async def inspect_html_sections(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(
                inspect_disclosure_html_sections_payload,
                apply_workspace_defaults("section_inspect", payload),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/sections/list")
    async def list_html_section_sources(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(
                list_disclosure_html_section_sources_payload,
                apply_workspace_defaults("section_list", payload),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/sections/kinds")
    async def summarize_html_section_kinds(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(
                summarize_disclosure_html_section_kinds_payload,
                apply_workspace_defaults("section_kinds", payload),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/cancel")
    async def cancel_html_job(payload: dict[str, Any]):
        job_id = str(payload.get("job_id") or "").strip()
        if not job_id:
            raise HTTPException(status_code=400, detail="Missing job_id")
        if not job_manager.cancel_job(job_id, reserve_missing=True):
            raise HTTPException(status_code=404, detail="Job not found")
        return {"status": "success", "job_id": job_id}

    @router.get("/api/disclosures/html/sections/source")
    async def open_html_section_source(
        input_directory: str,
        source_name: str = "",
        acpt_no: str = "",
    ):
        input_path = Path(input_directory).expanduser().resolve()
        if acpt_no:
            source_file = resolve_disclosure_html_file(input_path, acpt_no)
        else:
            source_file = (input_path / source_name).resolve()
            try:
                source_file.relative_to(input_path)
            except ValueError:
                source_file = None
            if (
                source_file is not None
                and (source_file.suffix.lower() != ".html" or not source_file.is_file())
            ):
                source_file = None
        if source_file is None:
            raise HTTPException(status_code=404, detail="HTML source file not found")
        return FileResponse(
            source_file,
            filename=source_file.name,
            media_type="text/html; charset=utf-8",
            content_disposition_type="inline",
        )

    @router.post("/api/disclosures/html/sections/source/split")
    async def split_html_section_source(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(
                split_disclosure_html_section_source_payload, payload
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/parse/cancel")
    async def cancel_html_parse_route(payload: dict[str, Any]):
        return cancel_disclosure_html_parse(str(payload.get("cancel_token") or ""))

    @router.post("/api/disclosures/html/parse/bond-summary")
    async def bond_parse_summary_route(payload: dict[str, Any]):
        return build_bond_parse_summary_payload(payload)

    @router.post("/api/disclosures/graph/build")
    async def build_disclosure_graph_route(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(build_disclosure_graph_payload, payload)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/graph/load")
    async def load_disclosure_graph_route(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(load_disclosure_graph_payload, payload)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/parse/preview")
    async def parse_preview_route(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(
                build_parse_preview_payload,
                apply_workspace_defaults("parse", payload),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/parse/inspect")
    async def inspect_html_parse_route(payload: dict[str, Any]):
        return await run_in_threadpool(
            inspect_disclosure_html_parse_payload,
            apply_workspace_defaults("parse", payload),
        )

    @router.post("/api/disclosures/html/parse/filter-candidates")
    async def parse_filter_candidates_route(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(
                build_parse_filter_candidates_payload,
                apply_workspace_defaults("parse", payload),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/parse/change-log")
    async def parse_change_log_route(payload: dict[str, Any]):
        return build_parse_change_log_payload(payload)

    @router.get("/api/disclosures/html/parse/export.xlsx")
    async def export_parse_results(
        mode: str,
        background_tasks: BackgroundTasks,
        output_path: str = "",
        data_root: str = "",
        parent_mode: str = "",
        latest_only: bool = False,
    ):
        output_directory = resolve_parse_change_log_output_directory(
            {
                "output_path": output_path,
                "data_root": data_root,
                "mode": mode,
                "parent_mode": parent_mode,
            }
        )
        payload = build_parse_export_xlsx(
            str(output_directory), mode, latest_only=latest_only
        )
        filename = f"{output_directory.stem}_export.xlsx"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            temp_path = Path(tmp.name)
            tmp.write(payload)
        background_tasks.add_task(temp_path.unlink, missing_ok=True)
        return FileResponse(
            temp_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            background=background_tasks,
        )

    @router.post("/api/integrated-data/convert/start")
    async def start_integrated_convert(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="integrated_convert",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/integrated-data/merge/start")
    async def start_integrated_merge(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="integrated_merge",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/integrated-data/market-history/start")
    async def start_integrated_market_history(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="integrated_market_history",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/utility/partition-storage/start")
    async def start_partition_storage(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="utility_partition",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    return router
