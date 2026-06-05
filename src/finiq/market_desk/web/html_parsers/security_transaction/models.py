"""발행증권 거래 공시 데이터 모델."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class SecurityTransactionRecord:
    """발행증권 거래 공시 추출 데이터 모델(스키마).
    추후 전용 필드가 추가될 예정입니다.
    """
    def to_dict(self) -> dict[str, Any]:
        return {}
