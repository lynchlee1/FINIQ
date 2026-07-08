"""유무상증자 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RightsIssuanceRecord:
    """유무상증자 공시 추출 데이터 모델(스키마).

    어떤 필드들이 최종적으로 추출되는지 직관적으로 확인할 수 있습니다.
    """

    증자유형: str
    신주의_종류와_수: list[list[Any]]
    증자_전_발행주식총수: list[list[Any]]
    발행목적: list[list[Any]] | str
    발행가액: list[list[Any]] | str
    기준주가: list[list[Any]] | str
    증자방식: str | None
    납입일: str | None
    신주권교부예정일: str | None
    상장예정일: str | None
    발행대상자: list[list[Any]] | str
    유상증자: dict[str, Any] | None
    무상증자: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        """추출된 데이터를 기존 파이프라인에서 기대하는 dict 키 형태로 매핑합니다."""
        return {
            "증자유형": self.증자유형,
            "신주의 종류와 수": self.신주의_종류와_수,
            "증자 전 발행주식총수": self.증자_전_발행주식총수,
            "발행목적": self.발행목적,
            "발행가액": self.발행가액,
            "기준주가": self.기준주가,
            "증자방식": self.증자방식,
            "납입일": self.납입일,
            "신주권교부예정일": self.신주권교부예정일,
            "상장예정일": self.상장예정일,
            "발행대상자": self.발행대상자,
            "유상증자": self.유상증자,
            "무상증자": self.무상증자,
        }
