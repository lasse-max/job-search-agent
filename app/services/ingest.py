"""End-to-end ingestion orchestration for Checkpoint B."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from app.adapters import get_adapter
from app.config import DEFAULT_DB_PATH, OUTPUT_DIR, load_company_config
from app.db import (
    connect_runtime_database,
    current_evaluation_policy_version,
    get_expected_volume_min,
    get_postings_by_ids,
    init_db,
    persist_evaluation,
    recover_expected_volume_min_after_degraded,
    record_evaluation_skip,
    record_source_run,
    set_source_health,
    stale_open_posting_ids_for_evaluator,
    update_expected_volume_min,
    upsert_company,
    upsert_source,
    upsert_postings,
)
from app.models import utc_now
from app.services.digest import write_digest
from app.services.evaluate import (
    HYBRID_EVALUATOR_VERSION,
    evaluate_role,
    input_hash,
    relevance_decision,
)
from app.services.llm_evaluator import LLMProviderError, ModelSpendCapExceeded

DEFAULT_STALE_EVALUATION_BACKFILL_LIMIT = 25


def stale_evaluation_backfill_limit() -> int:
    raw = os.getenv(
        "STALE_EVALUATION_BACKFILL_LIMIT",
        str(DEFAULT_STALE_EVALUATION_BACKFILL_LIMIT),
    )
    try:
        return max(0, int(raw))
    except ValueError as exc:
        raise ValueError("STALE_EVALUATION_BACKFILL_LIMIT must be an integer") from exc


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
    database_url: str | None = None,
    fixture_path: Path | None = None,
) -> ScanSummary:
    company = load_company_config(company_name)
    if not company.enabled:
        raise ValueError(f"Company is not enabled for automated scanning: {company.name}")

    adapter = get_adapter(company.ats_type)
    conn = connect_runtime_database(db_path, database_url=database_url)
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
        fresh_candidate_ids = upsert_result.new_posting_ids + upsert_result.changed_posting_ids
        stale_candidate_ids = stale_open_posting_ids_for_evaluator(
            conn,
            source_id,
            evaluator_version=HYBRID_EVALUATOR_VERSION,
            limit=stale_evaluation_backfill_limit(),
        )
        evaluation_policy_version = current_evaluation_policy_version(
            HYBRID_EVALUATOR_VERSION
        )
        candidate_ids = _ordered_unique_ids(fresh_candidate_ids + stale_candidate_ids)
        stale_only_candidate_ids = set(stale_candidate_ids).difference(fresh_candidate_ids)
        evaluated_count = 0
        fresh_attempted_evaluation_count = 0
        dropped_evaluation_count = 0
        dropped_evaluation_errors: list[str] = []
        dropped_evaluation_rows = []
        fallback_evaluation_count = 0
        rows_by_id = {int(row["id"]): row for row in get_postings_by_ids(conn, candidate_ids)}
        for candidate_id in candidate_ids:
            row = rows_by_id.get(candidate_id)
            if row is None:
                continue
            stale_backfill = candidate_id in stale_only_candidate_ids
            row_hash = input_hash(row)
            relevance = relevance_decision(row, company)
            if not relevance.should_evaluate:
                record_evaluation_skip(
                    conn,
                    int(row["id"]),
                    row_hash,
                    relevance.reason,
                    evaluator_version=evaluation_policy_version,
                )
                continue
            if not stale_backfill:
                fresh_attempted_evaluation_count += 1
            try:
                evaluation = _evaluate_role_with_retry(row, company)
            except ModelSpendCapExceeded as exc:
                reason = _evaluation_drop_reason(exc)
                record_evaluation_skip(conn, int(row["id"]), row_hash, reason)
                if stale_backfill:
                    break
                dropped_evaluation_count += 1
                dropped_evaluation_errors.append(reason)
                dropped_evaluation_rows.append((row, row_hash, reason))
                continue
            except LLMProviderError as exc:
                reason = _evaluation_drop_reason(exc)
                record_evaluation_skip(conn, int(row["id"]), row_hash, reason)
                if stale_backfill:
                    continue
                dropped_evaluation_count += 1
                dropped_evaluation_errors.append(reason)
                dropped_evaluation_rows.append((row, row_hash, reason))
                continue
            if stale_backfill and _is_fallback_evaluation(evaluation):
                record_evaluation_skip(
                    conn,
                    int(row["id"]),
                    row_hash,
                    "stale_evaluation_backfill_deferred_no_current_evaluator",
                )
                continue
            if persist_evaluation(conn, int(row["id"]), row_hash, evaluation):
                evaluated_count += 1

        if (
            fresh_attempted_evaluation_count > 0
            and dropped_evaluation_count == fresh_attempted_evaluation_count
        ):
            fallback_evaluation_count = dropped_evaluation_count
            for row, row_hash, _reason in dropped_evaluation_rows:
                evaluation = evaluate_role(row, company, use_env_provider=False)
                if persist_evaluation(conn, int(row["id"]), row_hash, evaluation):
                    evaluated_count += 1
            dropped_evaluation_count = 0
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

    evaluation_warning = _evaluation_warning(
        dropped_evaluation_count,
        dropped_evaluation_errors,
        fallback_evaluation_count,
    )
    source_warning = _join_errors(degraded_reason, evaluation_warning)
    source_status = "degraded" if source_warning else "success"
    _record_run(
        conn,
        source_id,
        started_at=started_at,
        finished_at=finished_at,
        status=source_status,
        http_status=result.http_status,
        fetched_count=health.fetched_count,
        new_count=len(upsert_result.new_posting_ids),
        changed_count=len(upsert_result.changed_posting_ids),
        error_summary=source_warning,
        health_status="degraded" if source_warning else "healthy",
        last_success_at=None if source_warning else finished_at,
    )
    if degraded_reason:
        recover_expected_volume_min_after_degraded(conn, source_id)
    conn.commit()
    html_path, text_path, digest_count, digest_error = _safe_write_digest(conn)
    return ScanSummary(
        company=company.name,
        source_type=adapter.source_type,
        source_key=company.source_key,
        status="failure" if digest_error else source_status,
        fetched_count=health.fetched_count,
        new_count=len(upsert_result.new_posting_ids),
        changed_count=len(upsert_result.changed_posting_ids),
        evaluated_count=evaluated_count,
        digest_count=digest_count,
        digest_html=html_path,
        digest_text=text_path,
        error_summary=_join_errors(source_warning, digest_error),
    )


def _evaluate_role_with_retry(row, company):
    try:
        return evaluate_role(row, company)
    except LLMProviderError as exc:
        if not exc.retryable_output:
            raise
        return evaluate_role(row, company)


def _ordered_unique_ids(ids: list[int]) -> list[int]:
    return list(dict.fromkeys(ids))


def _is_fallback_evaluation(evaluation) -> bool:
    provenance = evaluation.provenance
    return str(provenance.get("fallback_quality")).lower() == "true"


def _evaluation_drop_reason(exc: LLMProviderError | ModelSpendCapExceeded) -> str:
    return f"llm_evaluation_dropped: {type(exc).__name__}: {exc}"


def _evaluation_warning(
    dropped_count: int,
    errors: list[str],
    fallback_count: int,
) -> str | None:
    if dropped_count <= 0 and fallback_count <= 0:
        return None
    first_error = errors[0] if errors else "unknown"
    parts = []
    if dropped_count:
        parts.append(f"llm_evaluation_dropped_roles={dropped_count}")
    if fallback_count:
        parts.append(f"llm_evaluation_fallback_roles={fallback_count}")
    return f"{', '.join(parts)}: {first_error}"


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
