"""Shared adapter contract for source connectors."""

from __future__ import annotations

from typing import Any, Protocol

from app.models import CompanyConfig, FetchResult, JobPosting, SourceHealth


class SourceAdapter(Protocol):
    source_type: str
    parser_version: str

    def fetch(self, source_key: str) -> FetchResult:
        """Fetch raw source data."""

    def fetch_from_file(self, source_key: str, fixture_path: str) -> FetchResult:
        """Fetch raw source data from a saved fixture."""

    def identity(self, raw_job: dict[str, Any]) -> str:
        """Return the source-specific stable posting id."""

    def normalize(self, result: FetchResult, company: CompanyConfig) -> list[JobPosting]:
        """Convert source payloads into canonical postings."""

    def health_check(self, result: FetchResult) -> SourceHealth:
        """Distinguish valid zero-job responses from failures."""
