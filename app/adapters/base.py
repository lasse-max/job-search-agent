"""Shared adapter contract for source connectors."""

from __future__ import annotations

from typing import Protocol

from app.models import CompanyConfig, FetchResult, JobPosting, SourceHealth


class SourceAdapter(Protocol):
    source_type: str

    def fetch(self, source_key: str) -> FetchResult:
        """Fetch raw source data."""

    def normalize(self, result: FetchResult, company: CompanyConfig) -> list[JobPosting]:
        """Convert source payloads into canonical postings."""

    def health_check(self, result: FetchResult) -> SourceHealth:
        """Distinguish valid zero-job responses from failures."""
