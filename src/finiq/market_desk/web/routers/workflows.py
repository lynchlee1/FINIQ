from __future__ import annotations

import json
import queue
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from finiq.market_desk.web.features.disclosures.html_cleanup import (
    check_disclosure_html_output_directory_payload,
    clean_disclosure_html_output_directory_payload,
    write_disclosure_html_manifest_payload,
)
from finiq.market_desk.web.features.disclosures.html_common import (
    cancel_disclosure_html_download,
    resolve_disclosure_html_file,
)
from finiq.market_desk.web.features.disclosures.html_parse_changes import (
    build_parse_change_log_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_common import cancel_disclosure_html_parse
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
from finiq.market_desk.web.features.disclosures.html_sections import (
    inspect_disclosure_html_sections_payload,
    list_disclosure_html_section_sources_payload,
    split_disclosure_html_section_source_payload,
    summarize_disclosure_html_section_kinds_payload,
)
from finiq.market_desk.web.jobs import job_manager
from finiq.market_desk.web.features.disclosures.table_export import build_disclosure_table_payload
from finiq.market_desk.web.features.disclosure_workflow.dart_link import (
    build_dart_links_payload,
)
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
    atomic_write_json,
    prepare_disclosure_workspace_payload,
)

FilterDisclosuresPayload = Callable[..., dict[str, Any]]
RunJobWorker = Callable[[str, str, dict[str, Any]], None]


def _write_transfer_file(
    config: Any, payload: dict[str, Any], requested_path: str = ""
) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if requested_path:
        transfer_path = Path(requested_path).expanduser().resolve()
        if transfer_path.suffix.lower() != ".json":
            transfer_path = (
                transfer_path
                / f"filtered-disclosures-{timestamp}-{uuid.uuid4().hex[:8]}.json"
            )
    else:
        transfer_dir = (
            Path(config.output_root).expanduser().resolve() / ".finiq" / "transfers"
        )
        transfer_path = (
            transfer_dir
            / f"filtered-disclosures-{timestamp}-{uuid.uuid4().hex[:8]}.json"
        )

    atomic_write_json(transfer_path, payload)
    return {
        "format": payload.get("format", ""),
        "path": str(transfer_path),
        "acpt_numbers": len(
            payload.get("html_download_acpt_numbers")
            or payload.get("acptNumbers")
            or []
        ),
    }


def _attach_html_download_transfer(
    config: Any, payload: dict[str, Any], requested_path: str = ""
) -> dict[str, Any]:
    if payload.get("format") == "kind_disclosure_filter_v1":
        payload["html_download_transfer"] = _write_transfer_file(
            config, payload, requested_path=requested_path
        )
    return payload


def _load_filter_preset_file(source_json_path: str) -> dict[str, Any]:
    source_path = Path(source_json_path).expanduser().resolve()
    if source_path.suffix.lower() != ".json":
        raise ValueError("필터 결과 JSON 파일을 선택하세요.")
    if not source_path.is_file():
        raise ValueError(f"필터 결과 JSON 파일을 찾을 수 없습니다: {source_path}")

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("필터 결과 JSON 형식이 올바르지 않습니다.")
    filters = payload.get("filters")
    filter_blocks = filters.get("filter_blocks") if isinstance(filters, dict) else None
    if not isinstance(filter_blocks, list):
        raise ValueError("필터 결과 JSON에 filters.filter_blocks가 없습니다.")
    return {
        "format": "kind_disclosure_filter_preset_v1",
        "source_json_path": str(source_path),
        "name": source_path.stem,
        "condition_blocks": filter_blocks,
    }


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
    job_id = uuid.uuid4().hex
    job_manager.create_job(job_id, kind)
    background_tasks.add_task(run_job_worker, job_id, kind, payload)
    return job_manager.get_snapshot(job_id)


def create_workflows_router(
    *,
    config: Any,
    filter_disclosures_payload: FilterDisclosuresPayload,
    run_job_worker: RunJobWorker,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/disclosures/filter")
    async def filter_disclosures(request: Request):
        body = apply_workspace_defaults("filter", await request.json())
        accept = request.headers.get("Accept", "")
        if "application/x-ndjson" in accept:

            def generate():
                cancel_event = threading.Event()
                events: queue.Queue[dict[str, Any]] = queue.Queue()

                def run_filter() -> None:
                    try:
                        payload = filter_disclosures_payload(
                            body,
                            progress_callback=lambda progress: events.put(
                                {"type": "progress", "progress": progress}
                            ),
                            cancel_check=cancel_event.is_set,
                        )
                        _attach_html_download_transfer(
                            config,
                            payload,
                            requested_path=str(
                                body.get("html_transfer_path") or ""
                            ).strip(),
                        )
                        events.put({"type": "result", "payload": payload})
                    except Exception as e:
                        events.put({"type": "error", "error": str(e)})

                thread = threading.Thread(target=run_filter, daemon=True)
                thread.start()
                try:
                    while thread.is_alive() or not events.empty():
                        try:
                            event = events.get(timeout=0.1)
                        except queue.Empty:
                            continue
                        yield json.dumps(event, ensure_ascii=False) + "\n"
                finally:
                    cancel_event.set()

            return StreamingResponse(generate(), media_type="application/x-ndjson")
        try:
            payload = filter_disclosures_payload(body)
            _attach_html_download_transfer(
                config,
                payload,
                requested_path=str(body.get("html_transfer_path") or "").strip(),
            )
            return payload
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/filter/preset")
    async def load_disclosure_filter_preset(payload: dict[str, Any]):
        source_json_path = str(payload.get("source_json_path") or "").strip()
        if not source_json_path:
            raise HTTPException(status_code=400, detail="필터 결과 JSON 경로를 선택하세요.")
        try:
            return _load_filter_preset_file(source_json_path)
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

    @router.post("/api/disclosures/workspace/prepare")
    async def prepare_disclosure_workspace(payload: dict[str, Any]):
        try:
            return prepare_disclosure_workspace_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/dart-links/build")
    async def build_dart_links(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(build_dart_links_payload, payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/dart-links/build/start")
    async def start_dart_links_build(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="dart_link",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.get("/api/disclosures/dart-links/jobs/{job_id}")
    async def get_dart_links_job_status(job_id: str):
        return _job_snapshot(job_id)

    @router.post("/api/disclosures/dart-links/cancel")
    async def cancel_dart_links_job(payload: dict[str, Any]):
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

    @router.post("/api/disclosures/html/download/start")
    async def start_html_download(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="download",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/html/download/cancel")
    async def cancel_html_download_route(payload: dict[str, Any]):
        return cancel_disclosure_html_download(str(payload.get("cancel_token") or ""))

    @router.post("/api/disclosures/html/download/inspect-folder")
    def inspect_html_download_folder(payload: dict[str, Any]):
        try:
            return clean_disclosure_html_output_directory_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/download/check-existing")
    def check_html_download_folder(payload: dict[str, Any]):
        try:
            return check_disclosure_html_output_directory_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/download/compress/start")
    async def start_html_external_compress(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="external_compress",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/html/content-download/start")
    async def start_html_content_download(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="content_download",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

    @router.post("/api/disclosures/html/content-download/cancel")
    async def cancel_html_content_download_route(payload: dict[str, Any]):
        return cancel_disclosure_html_download(str(payload.get("cancel_token") or ""))

    @router.post("/api/disclosures/html/content-download/inspect-folder")
    def inspect_html_content_download_folder(payload: dict[str, Any]):
        try:
            return clean_disclosure_html_output_directory_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/content-download/check-existing")
    def check_html_content_download_folder(payload: dict[str, Any]):
        try:
            return check_disclosure_html_output_directory_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/manifest/write")
    async def write_html_manifest(payload: dict[str, Any]):
        try:
            return write_disclosure_html_manifest_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/content-download/merge/start")
    async def start_html_content_merge(
        payload: dict[str, Any], background_tasks: BackgroundTasks
    ):
        return _start_background_job(
            kind="content_merge",
            payload=payload,
            background_tasks=background_tasks,
            run_job_worker=run_job_worker,
        )

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
        if not job_manager.cancel_job(job_id):
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

    @router.post("/api/disclosures/html/parse/preview")
    async def parse_preview_route(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(build_parse_preview_payload, payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/parse/filter-candidates")
    async def parse_filter_candidates_route(payload: dict[str, Any]):
        try:
            return await run_in_threadpool(build_parse_filter_candidates_payload, payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/disclosures/html/parse/change-log")
    async def parse_change_log_route(payload: dict[str, Any]):
        return build_parse_change_log_payload(payload)

    @router.get("/api/disclosures/html/parse/export.xlsx")
    async def export_parse_results(
        output_path: str,
        mode: str,
        background_tasks: BackgroundTasks,
        latest_only: bool = False,
    ):
        payload = build_parse_export_xlsx(output_path, mode, latest_only=latest_only)
        filename = f"{Path(output_path).stem}_export.xlsx"
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
