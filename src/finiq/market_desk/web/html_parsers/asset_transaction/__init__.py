"""유무형자산 거래 공시 파서 엔트리포인트."""
from __future__ import annotations
from pathlib import Path
from typing import Any

from ..common import build_base_record
from .models import AssetTransactionRecord
from .extractor import AssetTransactionExtractor

MODE = "asset_transaction"

def parse_asset_transaction(html_text: str | bytes, *, file_path: str | Path) -> dict[str, Any]:
    """자산 거래 HTML을 공통 v1 아키텍처 레코드로 파싱한다."""
    record = build_base_record(html_text, file_path=file_path, mode=MODE)
    
    extractor = AssetTransactionExtractor(record.get("raw_tables", []))
    schema_record = AssetTransactionRecord()
    record.update(schema_record.to_dict())
    
    return record
