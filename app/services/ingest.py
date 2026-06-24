"""End-to-end ingestion orchestration for Checkpoint B."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.adapters import get_adapter
from app.config import DEFAULT_DB_PATH, OUTPUT_DIR, load_company_config
from app.db import (
    connect,
    get_expected_volume_min,
    init_db,
    persist_evaluation,
    recover_expected_volume_min_after_degraded,
    record_evaluation_skip,
    record_source_run,
    set_source_health,
    update_expected_volume_min,
    upsert_company,
    upsert_postings,
    upsert_source,
    get_postings_by_ids,
)
from app.models import utc_now
from app.services.digest import write_digest
from app.services.evaluate import evaluate_role, input_hash, relevance_decision


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
    if not company.enabled:
        raise ValueError(f"Company is not enabled for automated scanning: {company.name}")

    adapter = get_adapter(company.ats_type)
    conn = connect(db_path)
    init_db(conn)
    started_at = utc_now()
    company_id = upsert_company(conn, company)
    source_id = upsert_source(
        conn,
        company_id,
        company,
        seed_expected_volume=fixture_path is None,
    )
    conn.commit()

    if fixture_path:
        result = adapter.fetch_from_file(company.source_key, str(fixture_path))
    else:
        result = adapter.fetch(company.source_key)

    health = adapter.health_check(result)
    if health.status != "healthy":
        finished_at = utc_now()
        _record_run(
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
            health_status=health.status,
            last_success_at=None,
        )
        conn.commit()
        html_path, text_path, digest_count, digest_error = _safe_write_digest(conn)
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
            error_summary=_join_errors(health.error_summary, digest_error),
        )

    try:
        postings = adapter.normalize(result, company)
        seen_at = utc_now()
        degraded_reason = _degraded_reason(
            fetched_count=health.fetched_count,
            expected_volume_min=get_expected_volume_min(conn, source_id),
        )
        upsert_result = upsert_postings(
            conn,
            company_id,
            source_id,
            postings,
            seen_at,
            count_absences=degraded_reason is None,
        )
        candidate_ids = upsert_result.new_posting_ids + upsert_result.changed_posting_ids
        evaluated_count = 0
        for row in get_postings_by_ids(conn, candidate_ids):
            row_hash = input_hash(row)
            relevance = relevance_decision(row, company)
            if not relevance.should_evaluate:
                record_evaluation_skip(conn, int(row["id"]), row_hash, relevance.reason)
                continue
            evaluation = evaluate_role(row, company)
            if persist_evaluation(conn, int(row["id"]), row_hash, evaluation):
                evaluated_count += 1
    except Exception as exc:  # noqa: BLE001 - fail loud with durable source health.
        conn.rollback()
        finished_at = utc_now()
        error_summary = f"{type(exc).__name__}: {exc}"
        _record_run(
            conn,
            source_id,
            started_at=started_at,
            finished_at=finished_at,
            status="failure",
            http_status=result.http_status,
            fetched_count=health.fetched_count,
            new_count=0,
            changed_count=0,
            error_summary=error_summary,
            health_status="failing",
            last_success_at=None,
        )
        conn.commit()
        html_path, text_path, digest_count, digest_error = _safe_write_digest(conn)
        return ScanSummary(
            company=company.name,
            source_type=adapter.source_type,
            source_key=company.source_key,
            status="failure",
            fetched_count=health.fetched_count,
            new_count=0,
            changed_count=0,
            evaluated_count=0,
            digest_count=digest_count,
            digest_html=html_path,
            digest_text=text_path,
            error_summary=_join_errors(error_summary, digest_error),
        )

    finished_at = utc_now()
    degraded_reason = _degraded_reason(
        fetched_count=health.fetched_count,
        expected_volume_min=get_expected_volume_min(conn, source_id),
    )
    if degraded_reason is None and fixture_path is None:
        update_expected_volume_min(conn, source_id, health.fetched_count)

    _record_run(
        conn,
        source_id,
        started_at=started_at,
        finished_at=finished_at,
        status="degraded" if degraded_reason else "success",
        http_status=result.http_status,
        fetched_count=health.fetched_count,
        new_count=len(upsert_result.new_posting_ids),
        changed_count=len(upsert_result.changed_posting_ids),
        error_summary=degraded_reason,
        health_status="degraded" if degraded_reason else "healthy",
        last_success_at=None if degraded_reason else finished_at,
    )
    if degraded_reason:
        recover_expected_volume_min_after_degraded(conn, source_id)
    conn.commit()
    html_path, text_path, digest_count, digest_error = _safe_write_digest(conn)
    return ScanSummary(
        company=company.name,
        source_type=adapter.source_type,
        source_key=company.source_key,
        status="failure" if digest_error else "degraded" if degraded_reason else "success",
        fetched_count=health.fetched_count,
        new_count=len(upsert_result.new_posting_ids),
        changed_count=len(upsert_result.changed_posting_ids),
        evaluated_count=evaluated_count,
        digest_count=digest_count,
        digest_html=html_path,
        digest_text=text_path,
        error_summary=_join_errors(degraded_reason, digest_error),
    )


def _record_run(
    conn,
    source_id: int,
    *,
    started_at: str,
    finished_at: str,
    status: str,
    http_status: int | None,
    fetched_count: int,
    new_count: int,
    changed_count: int,
    error_summary: str | None,
    health_status: str,
    last_success_at: str | None,
) -> None:
    set_source_health(conn, source_id, health_status, last_success_at)
    record_source_run(
        conn,
        source_id,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        http_status=http_status,
        fetched_count=fetched_count,
        new_count=new_count,
        changed_count=changed_count,
        error_summary=error_summary,
    )


def _safe_write_digest(conn) -> tuple[Path, Path, int, str | None]:
    html_path = OUTPUT_DIR / "latest_digest.html"
    text_path = OUTPUT_DIR / "latest_digest.txt"
    try:
        written_html, written_text, digest_count = write_digest(conn, OUTPUT_DIR)
        return written_html, written_text, digest_count, None
    except Exception as exc:  # noqa: BLE001 - fail loudly without rolling back scan state.
        return html_path, text_path, 0, f"digest_render_failed: {type(exc).__name__}: {exc}"


def _join_errors(primary: str | None, secondary: str | None) -> str | None:
    if primary and secondary:
        return f"{primary}; {secondary}"
    return primary or secondary


def _degraded_reason(*, fetched_count: int, expected_volume_min: int | None) -> str | None:
    if expected_volume_min is None or expected_volume_min <= 0:
        return None
    if fetched_count >= expected_volume_min:
        return None
    return (
        "expected_volume_degraded: "
        f"fetched {fetched_count} below expected minimum {expected_volume_min}"
    )
