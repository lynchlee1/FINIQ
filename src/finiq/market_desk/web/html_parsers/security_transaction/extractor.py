"""발행증권 거래 공시 파서 추출 로직."""
from __future__ import annotations
from typing import Any

class SecurityTransactionExtractor:
    """발행증권 거래 공시의 추출 로직 클래스."""
    def __init__(self, raw_tables: list[dict[str, Any]]):
        self.raw_tables = raw_tables
