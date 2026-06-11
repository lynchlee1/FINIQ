from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from finiq.market_desk.web.discovery import (
    list_classification_files,
    list_price_source_files,
    resolve_default_classification,
    resolve_default_price_source,
)
from finiq.market_desk.web.service import (
    PRICE_SOURCE_QUANTI,
    build_company_list_export,
    build_insight_payload,
    list_integrated_providers,
    load_company_index_payload,
)


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

    @router.get("/api/integrated-data/providers")
    async def get_integrated_providers_route():
        return {"providers": list_integrated_providers()}

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
