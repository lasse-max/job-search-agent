"""Scheduled scan orchestration.

This module keeps scheduling concerns out of source adapters and ingest logic:
the GitHub workflow and local CLI both call the same `run_scheduled_scan` entry
point, which then delegates each company to `run_scan`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import DEFAULT_DB_PATH, load_enabled_company_configs
from app.models import CompanyConfig
from app.services.ingest import ScanSummary, run_scan


@dataclass(frozen=True)
class ScheduledScanResult:
    summaries: list[ScanSummary]
    skipped: list[str]
    failures: list[str]

    @property
    def status(self) -> str:
        if self.failures:
            return "failure"
        if any(summary.status == "degraded" for summary in self.summaries):
            return "degraded"
        return "success"


def run_scheduled_scan(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    companies: list[CompanyConfig] | None = None,
) -> ScheduledScanResult:
    summaries: list[ScanSummary] = []
    skipped: list[str] = []
    failures: list[str] = []

    for company in companies or load_enabled_company_configs():
        if company.ats_type == "manual":
            skipped.append(f"{company.name}: manual sources are intake-only")
            continue
        try:
            summary = run_scan(company_name=company.name, db_path=db_path)
        except Exception as exc:  # noqa: BLE001 - scheduler must continue and report all sources.
            failures.append(f"{company.name}: {type(exc).__name__}: {exc}")
            continue
        summaries.append(summary)
        if summary.status == "failure":
            failures.append(f"{company.name}: {summary.error_summary or 'scan failed'}")

    return ScheduledScanResult(summaries=summaries, skipped=skipped, failures=failures)
