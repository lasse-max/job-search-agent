"""Source adapter package."""

from __future__ import annotations

from app.adapters.ashby import AshbyAdapter
from app.adapters.base import SourceAdapter
from app.adapters.greenhouse import GreenhouseAdapter
from app.adapters.lever import LeverAdapter
from app.adapters.manual import ManualAdapter


def get_adapter(ats_type: str) -> SourceAdapter:
    if ats_type == GreenhouseAdapter.source_type:
        return GreenhouseAdapter()
    if ats_type == AshbyAdapter.source_type:
        return AshbyAdapter()
    if ats_type == LeverAdapter.source_type:
        return LeverAdapter()
    raise ValueError(f"Unsupported ATS adapter: {ats_type}")


def is_adapter_supported(ats_type: str) -> bool:
    return ats_type in {
        GreenhouseAdapter.source_type,
        AshbyAdapter.source_type,
        LeverAdapter.source_type,
        ManualAdapter.source_type,
    }


def source_endpoint(ats_type: str, source_key: str) -> str:
    if ats_type == GreenhouseAdapter.source_type:
        return GreenhouseAdapter().endpoint(source_key)
    if ats_type == AshbyAdapter.source_type:
        return AshbyAdapter().endpoint(source_key)
    if ats_type == LeverAdapter.source_type:
        return LeverAdapter().endpoint(source_key)
    if ats_type == ManualAdapter.source_type:
        return ManualAdapter().endpoint(source_key)
    raise ValueError(f"Unsupported ATS source metadata: {ats_type}")


def parser_version(ats_type: str) -> str:
    if ats_type == GreenhouseAdapter.source_type:
        return GreenhouseAdapter.parser_version
    if ats_type == AshbyAdapter.source_type:
        return AshbyAdapter.parser_version
    if ats_type == LeverAdapter.source_type:
        return LeverAdapter.parser_version
    if ats_type == ManualAdapter.source_type:
        return ManualAdapter.parser_version
    raise ValueError(f"Unsupported ATS parser metadata: {ats_type}")
