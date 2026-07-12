"""Scheduled scan orchestration.

This module keeps scheduling concerns out of source adapters and ingest logic:
the GitHub workflow and local CLI both call the same `run_scheduled_scan` entry
point, which then delegates each company to `run_scan`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import DEFAULT_DB_PATH, load_enabled_company_configs, load_recency_policy
from app.db import (
    connect_runtime_database,
    get_postings_by_ids,
    init_db,
    stale_open_posting_ids_for_evaluator,
)
from app.models import CompanyConfig
from app.services.evaluate import HYBRID_EVALUATOR_VERSION, relevance_decision
from app.services.ingest import ScanSummary, run_scan
from app.services.manual_intake import ManualIntakeQueueSummary, process_manual_intake_queue
from app.services.notifications import DigestDeliveryResult, deliver_digest


@dataclass(frozen=True)
class ScheduledScanResult:
    summaries: list[ScanSummary]
    skipped: list[str]
    failures: list[str]
    notification: DigestDeliveryResult | None = None
    manual_intake: ManualIntakeQueueSummary | None = None

    @property
    def status(self) -> str:
        if self.failures:
            return "failure"
        if any(summary.status == "degraded" for summary in self.summaries):
            return "degraded"
        return "success"


@dataclass(frozen=True)
class BackfillPlan:
    item_count: int
    estimated_seconds: int
    projected_spend_usd: float
    max_age_days: int


def plan_stale_backfill(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    database_url: str | None = None,
    companies: list[CompanyConfig] | None = None,
) -> BackfillPlan:
    policy = load_recency_policy()
    conn = connect_runtime_database(db_path, database_url=database_url)
    item_ids: set[int] = set()
    try:
        for company in companies or load_enabled_company_configs():
            if company.ats_type == "manual":
                continue
            source = conn.execute(
                """
                SELECT js.id
                FROM job_sources js
                JOIN companies c ON c.id = js.company_id
                WHERE c.name = ? AND js.source_type = ? AND js.source_key = ?
                """,
                (company.name, company.ats_type, company.source_key),
            ).fetchone()
            if source is None:
                continue
            candidate_ids = stale_open_posting_ids_for_evaluator(
                conn,
                int(source["id"]),
                evaluator_version=HYBRID_EVALUATOR_VERSION,
                limit=100_000,
            )
            rows = get_postings_by_ids(conn, candidate_ids)
            item_ids.update(
                int(row["id"])
                for row in rows
                if relevance_decision(row, company).should_evaluate
            )
    finally:
        conn.close()
    count = len(item_ids)
    return BackfillPlan(
        item_count=count,
        estimated_seconds=count * policy.estimated_seconds_per_evaluation,
        projected_spend_usd=count * policy.estimated_cost_per_evaluation_usd,
        max_age_days=policy.max_age_days,
    )


def run_scheduled_scan(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    database_url: str | None = None,
    companies: list[CompanyConfig] | None = None,
    send_digest: bool = False,
) -> ScheduledScanResult:
    summaries: list[ScanSummary] = []
    skipped: list[str] = []
    failures: list[str] = []

    for company in companies or load_enabled_company_configs():
        if company.ats_type == "manual":
            skipped.append(f"{company.name}: manual sources are intake-only")
            continue
        try:
            summary = run_scan(
                company_name=company.name,
                db_path=db_path,
                database_url=database_url,
            )
        except Exception as exc:  # noqa: BLE001 - scheduler must continue and report all sources.
            failures.append(f"{company.name}: {type(exc).__name__}: {exc}")
            continue
        summaries.append(summary)
        if summary.status == "failure":
            failures.append(f"{company.name}: {summary.error_summary or 'scan failed'}")

    manual_intake = None
    try:
        manual_intake = process_manual_intake_queue(
            db_path=db_path,
            database_url=database_url,
        )
    except Exception as exc:  # noqa: BLE001 - queue infrastructure must fail loud.
        failures.append(f"manual intake queue: {type(exc).__name__}: {exc}")

    notification = None
    if send_digest:
        conn = connect_runtime_database(db_path, database_url=database_url)
        init_db(conn)
        notification = deliver_digest(conn)
        if notification.status == "failed":
            failures.append(notification.error_summary or "digest email failed")

    return ScheduledScanResult(
        summaries=summaries,
        skipped=skipped,
        failures=failures,
        notification=notification,
        manual_intake=manual_intake,
    )
