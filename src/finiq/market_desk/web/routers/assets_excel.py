from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

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


class AssetExcelConvertRequest(BaseModel):
    output_directory: Optional[str] = None
    selected_files: list[str] = []
    conflict_policy: str = "error"
    write_mode: str = "update"


def create_assets_excel_router(
    *,
    get_assets_dir: Callable[[], Path],
    run_job_worker: Callable[[str, str, dict], None],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/assets/excels")
    async def get_asset_excels():
        assets_dir = get_assets_dir()
        return {
            "root_directory": str(assets_dir.resolve()),
            "excel_files": list_asset_excel_files(assets_dir),
        }

    @router.get("/api/assets/excels/output")
    async def get_asset_excel_output(output_directory: Optional[str] = None):
        return inspect_asset_excel_output(output_directory or DEFAULT_ASSET_PARQUET_DIR)

    @router.post("/api/assets/excels/preview-conversion")
    async def preview_asset_excel_conversion(request: AssetExcelConvertRequest):
        try:
            return await asyncio.to_thread(
                inspect_asset_excel_conversion,
                get_assets_dir(),
                request.output_directory or DEFAULT_ASSET_PARQUET_DIR,
                selected_files=request.selected_files or None,
                conflict_policy=request.conflict_policy,
                write_mode=request.write_mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/assets/excels/convert-wide-parquet")
    async def convert_asset_excels(request: AssetExcelConvertRequest):
        try:
            return await asyncio.to_thread(
                convert_asset_excels_to_wide_parquet,
                get_assets_dir(),
                request.output_directory or DEFAULT_ASSET_PARQUET_DIR,
                selected_files=request.selected_files or None,
                conflict_policy=request.conflict_policy,
                write_mode=request.write_mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/assets/excels/convert-wide-parquet/start")
    async def start_convert_asset_excels(request: AssetExcelConvertRequest, background_tasks: BackgroundTasks):
        job_id = uuid.uuid4().hex
        job_manager.create_job(job_id, "asset_excel_convert")
        background_tasks.add_task(
            run_job_worker,
            job_id,
            "asset_excel_convert",
            request.model_dump(),
        )
        return job_manager.get_snapshot(job_id)

    @router.get("/api/assets/excels/jobs/{job_id}")
    async def get_asset_excel_job_status(job_id: str):
        snapshot = job_manager.get_snapshot(job_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="Job not found")
        return snapshot

    @router.get("/api/assets/excels/{file_name:path}")
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
                    root_directory=get_assets_dir(),
                )
            return read_asset_excel(
                file_name,
                sheet_name=sheet_name,
                row_limit=row_limit,
                root_directory=get_assets_dir(),
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (IsADirectoryError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return router
