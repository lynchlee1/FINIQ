from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from finiq.data.assets_excel import (
    convert_asset_excels_to_wide_parquet,
    default_account_mappings,
    inspect_asset_excel_conversion,
    inspect_asset_excel_output,
    list_asset_excel_files,
    merge_asset_parquet_outputs,
    read_asset_excel,
    read_asset_excel_interpreted,
    read_asset_parquet_preview,
    read_asset_excel_sheets,
)
from finiq.market_desk.web.jobs import job_manager


class AssetAccountMappingRequest(BaseModel):
    account_id: str = ""
    account_name: str = ""
    legacy_account_name: str = ""
    sheet_name: str = ""


class AssetExcelConvertRequest(BaseModel):
    source_directory: Optional[str] = None
    output_directory: Optional[str] = None
    selected_files: list[str] = []
    account_mappings: Optional[list[AssetAccountMappingRequest]] = None
    write_mode: str = "replace"


class AssetParquetMergeRequest(BaseModel):
    base_directory: str
    incoming_directory: str
    output_directory: Optional[str] = None


def create_assets_excel_router(
    *,
    get_assets_dir: Callable[[], Path],
    run_job_worker: Callable[[str, str, dict], None],
) -> APIRouter:
    router = APIRouter()

    def _required_path(value: Optional[str], field_name: str) -> str:
        resolved = str(value or "").strip()
        if not resolved:
            raise HTTPException(status_code=400, detail=f"{field_name} is required")
        return resolved

    def _assets_dir(source_directory: Optional[str] = None) -> Path:
        return Path(_required_path(source_directory, "source_directory")).expanduser().resolve()

    @router.get("/api/assets/excels")
    async def get_asset_excels(source_directory: Optional[str] = None):
        assets_dir = _assets_dir(source_directory)
        return {
            "root_directory": str(assets_dir.resolve()),
            "excel_files": list_asset_excel_files(assets_dir),
        }

    @router.get("/api/assets/excels/output")
    async def get_asset_excel_output(output_directory: Optional[str] = None):
        return inspect_asset_excel_output(_required_path(output_directory, "output_directory"))

    @router.get("/api/assets/excels/account-mappings")
    async def get_asset_excel_account_mappings():
        return {"items": default_account_mappings()}

    @router.get("/api/assets/parquet/preview")
    async def get_asset_parquet_preview(
        file_name: str,
        output_directory: Optional[str] = None,
        row_limit: Optional[int] = 20,
    ):
        try:
            return await asyncio.to_thread(
                read_asset_parquet_preview,
                file_name,
                output_directory=_required_path(output_directory, "output_directory"),
                row_limit=row_limit,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (IsADirectoryError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/assets/excels/preview-conversion")
    async def preview_asset_excel_conversion(request: AssetExcelConvertRequest):
        try:
            return await asyncio.to_thread(
                inspect_asset_excel_conversion,
                _assets_dir(request.source_directory),
                _required_path(request.output_directory, "output_directory"),
                selected_files=request.selected_files or None,
                account_mappings=[
                    mapping.model_dump()
                    for mapping in request.account_mappings
                ] if request.account_mappings is not None else None,
                write_mode=request.write_mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/assets/excels/convert-wide-parquet")
    async def convert_asset_excels(request: AssetExcelConvertRequest):
        try:
            return await asyncio.to_thread(
                convert_asset_excels_to_wide_parquet,
                _assets_dir(request.source_directory),
                _required_path(request.output_directory, "output_directory"),
                selected_files=request.selected_files or None,
                account_mappings=[
                    mapping.model_dump()
                    for mapping in request.account_mappings
                ] if request.account_mappings is not None else None,
                write_mode=request.write_mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/assets/excels/convert-wide-parquet/start")
    async def start_convert_asset_excels(request: AssetExcelConvertRequest, background_tasks: BackgroundTasks):
        _assets_dir(request.source_directory)
        _required_path(request.output_directory, "output_directory")
        job_id = uuid.uuid4().hex
        job_manager.create_job(job_id, "asset_excel_convert")
        background_tasks.add_task(
            run_job_worker,
            job_id,
            "asset_excel_convert",
            request.model_dump(),
        )
        return job_manager.get_snapshot(job_id)

    @router.post("/api/assets/parquet/merge")
    async def merge_asset_parquet_outputs_route(request: AssetParquetMergeRequest):
        try:
            return await asyncio.to_thread(
                merge_asset_parquet_outputs,
                _required_path(request.base_directory, "base_directory"),
                _required_path(request.incoming_directory, "incoming_directory"),
                _required_path(request.output_directory, "output_directory"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/assets/parquet/merge/start")
    async def start_merge_asset_parquet_outputs(request: AssetParquetMergeRequest, background_tasks: BackgroundTasks):
        _required_path(request.base_directory, "base_directory")
        _required_path(request.incoming_directory, "incoming_directory")
        _required_path(request.output_directory, "output_directory")
        job_id = uuid.uuid4().hex
        job_manager.create_job(job_id, "asset_excel_merge")
        background_tasks.add_task(
            run_job_worker,
            job_id,
            "asset_excel_merge",
            request.model_dump(),
        )
        return job_manager.get_snapshot(job_id)

    @router.post("/api/assets/excels/cancel")
    async def cancel_asset_excel_job(payload: dict[str, Any]):
        job_id = str(payload.get("job_id") or "").strip()
        if not job_id:
            raise HTTPException(status_code=400, detail="Missing job_id")
        if not job_manager.cancel_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return {"status": "success", "job_id": job_id}

    @router.get("/api/assets/excels/jobs/{job_id}")
    async def get_asset_excel_job_status(job_id: str):
        snapshot = job_manager.get_snapshot(job_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="Job not found")
        return snapshot


    @router.get("/api/assets/excels/{file_name:path}/sheets")
    async def get_asset_excel_sheets(file_name: str, source_directory: Optional[str] = None):
        try:
            return read_asset_excel_sheets(
                file_name,
                root_directory=_assets_dir(source_directory),
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (IsADirectoryError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))


    @router.get("/api/assets/excels/{file_name:path}")
    async def get_asset_excel(
        file_name: str,
        sheet_name: Optional[str] = None,
        source_directory: Optional[str] = None,
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
                    root_directory=_assets_dir(source_directory),
                )
            return read_asset_excel(
                file_name,
                sheet_name=sheet_name,
                row_limit=row_limit,
                root_directory=_assets_dir(source_directory),
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (IsADirectoryError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return router
