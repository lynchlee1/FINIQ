"""자산 거래 공시 파서 추출 로직."""
from __future__ import annotations
from typing import Any

class AssetTransactionExtractor:
    """자산 거래 공시의 실제 필드별 추출 로직을 모아둔 클래스.
    현재는 공통 파싱 레코드만 사용하므로 로직이 비어 있습니다.
    """
    def __init__(self, raw_tables: list[dict[str, Any]]):
        self.raw_tables = raw_tables
