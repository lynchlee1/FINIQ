from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response

from finiq.market_desk.web.download import (
    build_download_options_payload,
    build_download_preview_payload,
    build_download_status_payload,
    cancel_download_job,
    get_download_job,
    inspect_download_output_directory_payload,
    run_download_action,
    start_download_job,
    start_inspect_folder_job,
)


def create_download_router(config: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/api/download/options")
    async def get_download_options_route(response: Response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return build_download_options_payload(
            default_output_directory=config.download_output_directory or config.output_root
        )

    @router.post("/api/download/preview")
    async def download_preview(payload: dict[str, Any]):
        return build_download_preview_payload(payload)

    @router.post("/api/download/status")
    async def download_status_route(payload: dict[str, Any]):
        return build_download_status_payload(payload)

    @router.post("/api/download/inspect-folder")
    async def download_inspect_folder_route(payload: dict[str, Any]):
        try:
            return inspect_download_output_directory_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/download/inspect-folder/start")
    async def download_inspect_folder_start_route(payload: dict[str, Any]):
        try:
            return start_inspect_folder_job(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/download/run/start")
    async def download_start_route(payload: dict[str, Any]):
        return start_download_job(payload)

    @router.post("/api/download/run/cancel")
    async def download_cancel_route(payload: dict[str, Any]):
        try:
            return cancel_download_job(str(payload.get("job_id") or ""))
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @router.get("/api/download/jobs/{job_id}")
    async def get_download_job_status_route(job_id: str):
        try:
            return get_download_job(job_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @router.post("/api/download/run")
    async def download_run(payload: dict[str, Any]):
        return run_download_action(payload)

    return router
