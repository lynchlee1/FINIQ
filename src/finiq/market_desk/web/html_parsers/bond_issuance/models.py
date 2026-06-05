"""사채 발행 데이터 모델."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class BondIssuanceRecord:
    """사채 발행 공시 추출 데이터 모델(스키마).
    
    어떤 필드들이 최종적으로 추출되는지 직관적으로 확인할 수 있습니다.
    """
    기업명_발행사: str | Any | None
    회차: str | None
    종류: str | None
    기업명_행사대상: str | None
    상장구분: str | Any | None
    발행금액: int | None
    행사가액: int | None
    납입일: str | None
    만기일: str | None
    행사시작일: str | None
    행사종료일: str | None
    투자자: list[list[Any]]
    발행대상자세부엔티티: list[list[str]]

    def to_dict(self) -> dict[str, Any]:
        """추출된 데이터를 기존 파이프라인에서 기대하는 dict 키 형태로 매핑합니다."""
        return {
            "기업명(발행사)": self.기업명_발행사,
            "회차": self.회차,
            "종류": self.종류,
            "기업명(행사대상)": self.기업명_행사대상,
            "상장구분": self.상장구분,
            "발행금액": self.발행금액,
            "행사가액": self.행사가액,
            "납입일": self.납입일,
            "만기일": self.만기일,
            "행사시작일": self.행사시작일,
            "행사종료일": self.행사종료일,
            "투자자": self.투자자,
            "발행대상자세부엔티티": self.발행대상자세부엔티티,
        }
