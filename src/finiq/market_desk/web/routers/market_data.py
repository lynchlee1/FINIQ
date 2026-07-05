from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from threading import Event
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from finiq.market_desk.analytics.ontology_graph import (
    OntologyRequestCancelled,
    build_ontology_company_panel,
    build_ontology_status,
    search_ontology_companies,
)
from finiq.market_desk.analytics.triple_barrier import (
    get_triple_barrier_results_payload,
    run_triple_barrier_analysis,
)
from finiq.market_desk.web.features.market_data.discovery import (
    list_classification_files,
    list_price_source_files,
    resolve_default_classification,
    resolve_default_price_source,
)
from finiq.market_desk.web.features.market_data.service_common import PRICE_SOURCE_QUANTI
from finiq.market_desk.web.features.market_data.service_integrated import (
    build_company_list_export,
)
from finiq.market_desk.web.features.market_data.service_insight import (
    build_insight_payload,
)
from finiq.market_desk.web.features.market_data.service_payloads import (
    load_company_index_payload,
)


async def _watch_client_disconnect(request: Request, cancel_event: Event, done_event: Event) -> None:
    while not done_event.is_set() and not cancel_event.is_set():
        if await request.is_disconnected():
            cancel_event.set()
            return
        await asyncio.sleep(0.1)


class TripleBarrierRunRequest(BaseModel):
    manifest_path: str | None = None
    quanti_dir: str | None = None
    company_id: str
    market: str = "전체"
    disclosure_group: str = "전체"
    disclosure_ids: list[str] = Field(default_factory=list)
    event_time_basis: str = "disclosed_date"
    price_basis: str = "intraday"
    upper_pct: float = 5
    lower_pct: float = 3
    vertical_days: int = 20


def create_market_data_router(config: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/api/classifications")
    async def get_classifications(root_directory: Optional[str] = None):
        root = root_directory or config.output_root
        files = list_classification_files(root)
        return {
            "root_directory": str(Path(root).resolve()),
            "classification_files": files,
            "selected_classification_path": resolve_default_classification(root),
        }

    @router.get("/api/price-sources")
    async def get_price_sources(root_directory: Optional[str] = None, selected_path: Optional[str] = None):
        root = root_directory or str(Path(config.quanti_dir).resolve().parent)
        return {
            "price_root_directory": str(Path(root).resolve()),
            "price_files": list_price_source_files(root),
            "selected_price_path": resolve_default_price_source(root, selected_path or ""),
        }

    @router.get("/api/ontology/status")
    async def get_ontology_status(
        manifest_path: Optional[str] = None,
        quanti_dir: Optional[str] = None,
    ):
        try:
            return build_ontology_status(
                manifest_path=manifest_path,
                quanti_dir=quanti_dir,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get("/api/ontology/companies")
    async def get_ontology_companies(
        manifest_path: Optional[str] = None,
        quanti_dir: Optional[str] = None,
        keyword: str = "",
        market: str = "전체",
        limit: int = 30,
    ):
        try:
            return search_ontology_companies(
                manifest_path=manifest_path,
                quanti_dir=quanti_dir,
                keyword=keyword,
                market=market,
                limit=limit,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get("/api/ontology/company-panel")
    async def get_ontology_company_panel(
        request: Request,
        company_id: str,
        manifest_path: Optional[str] = None,
        quanti_dir: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        title_keyword: str = "",
        market: str = "전체",
        display_frequency: str = "자동",
        disclosure_group: str = "전체",
    ):
        cancel_event = Event()
        done_event = Event()
        watch_task = asyncio.create_task(_watch_client_disconnect(request, cancel_event, done_event))
        try:
            return await run_in_threadpool(
                build_ontology_company_panel,
                manifest_path=manifest_path,
                quanti_dir=quanti_dir,
                company_id=company_id,
                start_date=start_date,
                end_date=end_date,
                title_keyword=title_keyword,
                market=market,
                display_frequency_label=display_frequency,
                disclosure_group=disclosure_group,
                cancellation_check=cancel_event.is_set,
            )
        except OntologyRequestCancelled:
            raise HTTPException(status_code=499, detail="Client disconnected")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        finally:
            done_event.set()
            watch_task.cancel()

    @router.post("/api/ontology/triple-barrier/run")
    async def post_triple_barrier_run(payload: TripleBarrierRunRequest):
        try:
            return await run_in_threadpool(
                run_triple_barrier_analysis,
                manifest_path=payload.manifest_path,
                quanti_dir=payload.quanti_dir or None,
                company_id=payload.company_id,
                market=payload.market,
                disclosure_group=payload.disclosure_group,
                disclosure_ids=payload.disclosure_ids,
                event_time_basis=payload.event_time_basis,
                price_basis=payload.price_basis,
                upper_pct=payload.upper_pct,
                lower_pct=payload.lower_pct,
                vertical_days=payload.vertical_days,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get("/api/ontology/triple-barrier/results")
    async def get_triple_barrier_results(
        manifest_path: Optional[str] = None,
        company_id: str = "",
        parameter_hash: str = "",
    ):
        try:
            return await run_in_threadpool(
                get_triple_barrier_results_payload,
                manifest_path=manifest_path,
                company_id=company_id,
                parameter_hash=parameter_hash,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @router.get("/api/companies")
    async def get_companies(
        classification_path: Optional[str] = None,
        keyword: Optional[str] = None,
        market: str = "전체",
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

    @router.get("/api/insight")
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

    @router.get("/api/company-list.xlsx")
    async def export_companies(
        classification_path: str,
        background_tasks: BackgroundTasks,
        keyword: Optional[str] = None,
        market: str = "전체",
    ):
        path = classification_path
        if not Path(path).exists():
            path = config.selected_classification_path or resolve_default_classification(config.output_root) or ""

        if not path or not Path(path).exists():
            raise HTTPException(status_code=404, detail="Classification file not found")

        try:
            payload = build_company_list_export(path, keyword=keyword, market=market)
            filename = f"{Path(path).stem}.company_list.xlsx"
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
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    return router
