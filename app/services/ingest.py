"""End-to-end ingestion orchestration for Checkpoint B."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.adapters.greenhouse import GreenhouseAdapter
from app.config import DEFAULT_DB_PATH, OUTPUT_DIR, load_company_config
from app.db import (
    connect,
    init_db,
    persist_evaluation,
    record_source_run,
    set_source_health,
    upsert_company,
    upsert_postings,
    upsert_source,
    get_postings_by_ids,
)
from app.models import utc_now
from app.services.digest import write_digest
from app.services.evaluate import evaluate_role, input_hash, should_evaluate


@dataclass(frozen=True)
class ScanSummary:
    company: str
    source_type: str
    source_key: str
    status: str
    fetched_count: int
    new_count: int
    changed_count: int
    evaluated_count: int
    digest_count: int
    digest_html: Path
    digest_text: Path
    error_summary: str | None = None


def run_scan(
    *,
    company_name: str = "Databricks",
    db_path: Path = DEFAULT_DB_PATH,
    fixture_path: Path | None = None,
) -> ScanSummary:
    company = load_company_config(company_name)
    if company.ats_type != "greenhouse":
        raise ValueError("Checkpoint B currently supports the Greenhouse Databricks slice only")

    adapter = GreenhouseAdapter()
    conn = connect(db_path)
    init_db(conn)
    started_at = utc_now()
    company_id = upsert_company(conn, company)
    source_id = upsert_source(conn, company_id, company)

    if fixture_path:
        result = adapter.fetch_from_file(company.source_key, str(fixture_path))
    else:
        result = adapter.fetch(company.source_key)

    health = adapter.health_check(result)
    if health.status != "healthy":
        finished_at = utc_now()
        set_source_health(conn, source_id, health.status, None)
        record_source_run(
            conn,
            source_id,
            started_at=started_at,
            finished_at=finished_at,
            status="failure",
            http_status=result.http_status,
            fetched_count=0,
            new_count=0,
            changed_count=0,
            error_summary=health.error_summary,
        )
        conn.commit()
        html_path, text_path, digest_count = write_digest(conn, OUTPUT_DIR)
        return ScanSummary(
            company=company.name,
            source_type=adapter.source_type,
            source_key=company.source_key,
            status="failure",
            fetched_count=0,
            new_count=0,
            changed_count=0,
            evaluated_count=0,
            digest_count=digest_count,
            digest_html=html_path,
            digest_text=text_path,
            error_summary=health.error_summary,
        )

    postings = adapter.normalize(result, company)
    seen_at = utc_now()
    upsert_result = upsert_postings(conn, company_id, source_id, postings, seen_at)
    candidate_ids = upsert_result.new_posting_ids + upsert_result.changed_posting_ids
    evaluated_count = 0
    for row in get_postings_by_ids(conn, candidate_ids):
        if not should_evaluate(row, company):
            continue
        evaluation = evaluate_role(row, company)
        if persist_evaluation(conn, int(row["id"]), input_hash(row), evaluation):
            evaluated_count += 1

    finished_at = utc_now()
    set_source_health(conn, source_id, "healthy", finished_at)
    record_source_run(
        conn,
        source_id,
        started_at=started_at,
        finished_at=finished_at,
        status="success",
        http_status=result.http_status,
        fetched_count=health.fetched_count,
        new_count=len(upsert_result.new_posting_ids),
        changed_count=len(upsert_result.changed_posting_ids),
        error_summary=None,
    )
    html_path, text_path, digest_count = write_digest(conn, OUTPUT_DIR)
    conn.commit()
    return ScanSummary(
        company=company.name,
        source_type=adapter.source_type,
        source_key=company.source_key,
        status="success",
        fetched_count=health.fetched_count,
        new_count=len(upsert_result.new_posting_ids),
        changed_count=len(upsert_result.changed_posting_ids),
        evaluated_count=evaluated_count,
        digest_count=digest_count,
        digest_html=html_path,
        digest_text=text_path,
    )
