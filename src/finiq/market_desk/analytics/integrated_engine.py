"""Pluggable engine for integrated data construction supporting multiple Source of Truth (SoT) providers."""

from __future__ import annotations

import abc
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type

import pandas as pd

ProgressCallback = Callable[[str], None]


class BaseProvider(abc.ABC):
    """Abstract base class for data source providers."""

    @property
    @abc.abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for the provider (e.g., 'quantiwise', 'fdr')."""

    @property
    @abc.abstractmethod
    def display_name(self) -> str:
        """Human-readable name for the provider."""

    @property
    @abc.abstractmethod
    def required_fields(self) -> List[Dict[str, Any]]:
        """List of fields required by this provider for conversion.
        Each field is a dict with: id, label, type (text/folder/file), placeholder.
        """

    @abc.abstractmethod
    def convert(
        self,
        payload: Dict[str, Any],
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Convert source data to FINIQ standard wide-item Parquet."""

    @abc.abstractmethod
    def merge(
        self,
        payload: Dict[str, Any],
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Merge multiple datasets produced by this provider."""


class ProviderRegistry:
    """Registry to manage and access data providers."""

    _providers: Dict[str, BaseProvider] = {}

    @classmethod
    def register(cls, provider: BaseProvider) -> None:
        cls._providers[provider.provider_id] = provider

    @classmethod
    def get(cls, provider_id: str) -> BaseProvider:
        provider = cls._providers.get(provider_id)
        if not provider:
            raise ValueError(f"Provider not found: {provider_id}")
        return provider

    @classmethod
    def list_providers(cls) -> List[Dict[str, Any]]:
        return [
            {
                "id": p.provider_id,
                "name": p.display_name,
                "fields": p.required_fields,
            }
            for p in cls._providers.values()
        ]


# --- Quantiwise Provider Implementation ---

class QuantiwiseProvider(BaseProvider):
    @property
    def provider_id(self) -> str:
        return "quantiwise"

    @property
    def display_name(self) -> str:
        return "Quantiwise (Excel based)"

    @property
    def required_fields(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "source_directory",
                "label": "원천 데이터 폴더 (.xlsx)",
                "type": "folder",
                "placeholder": "Excel 파일들이 있는 폴더 선택",
            },
            {
                "id": "output_directory",
                "label": "출력 Parquet 폴더",
                "type": "folder",
                "placeholder": "변환된 Parquet이 저장될 폴더 선택",
            },
        ]

    def convert(
        self,
        payload: Dict[str, Any],
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        from finiq.market_desk.analytics.quanti_integrated import convert_quanti_excel_to_parquet
        return convert_quanti_excel_to_parquet(
            payload.get("source_directory", ""),
            payload.get("output_directory", ""),
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )

    def merge(
        self,
        payload: Dict[str, Any],
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        from finiq.market_desk.analytics.quanti_integrated import merge_quanti_by_item_datasets
        input_dirs = payload.get("input_directories")
        if not input_dirs:
            input_dirs = [payload.get("input_directory", "")]
        return merge_quanti_by_item_datasets(
            input_dirs,
            payload.get("output_directory", ""),
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )


# --- FinanceDataReader (FDR) Provider Implementation ---

class FDRProvider(BaseProvider):
    @property
    def provider_id(self) -> str:
        return "fdr"

    @property
    def display_name(self) -> str:
        return "FinanceDataReader (Online API)"

    @property
    def required_fields(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "start_year",
                "label": "시작 연도",
                "type": "text",
                "placeholder": "2020",
            },
            {
                "id": "output_directory",
                "label": "출력 Parquet 폴더",
                "type": "folder",
                "placeholder": "수집된 데이터가 저장될 폴더 선택",
            },
        ]

    def convert(
        self,
        payload: Dict[str, Any],
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        # Implementation for FDR fetching and wide-item conversion
        if progress_callback:
            progress_callback("FDR Provider conversion is not yet fully implemented in this prototype.")
        return {"status": "error", "message": "Not implemented"}

    def merge(
        self,
        payload: Dict[str, Any],
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        if progress_callback:
            progress_callback("FDR Provider merging is not yet implemented.")
        return {"status": "error", "message": "Not implemented"}


# Initialize and Register Providers
ProviderRegistry.register(QuantiwiseProvider())
ProviderRegistry.register(FDRProvider())
