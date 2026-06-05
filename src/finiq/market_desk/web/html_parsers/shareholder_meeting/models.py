"""주주총회 공시 데이터 모델."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class ShareholderMeetingRecord:
    """주주총회 데이터 구조.
    주주총회 세부 필드 추출은 `finiq.data_scraper`에서 수행합니다.
    """
    def to_dict(self) -> dict[str, Any]:
        return {}
