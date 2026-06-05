"""Domain-specific parsers for KIND disclosures."""

from .shareholder_meeting import parse_shareholder_meeting

__all__ = [
    "parse_shareholder_meeting",
]
