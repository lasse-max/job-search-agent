"""Review queue state transitions for evaluated opportunities."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date

from app.models import ReviewState, utc_now


@dataclass(frozen=True)
class ReviewUpdate:
    job_id: int
    state: ReviewState
    decision_reason: str | None
    reviewed_at: str | None
    snooze_until: str | None


def list_reviews(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
          jp.id AS job_id,
          c.name AS company,
          c.tier AS company_tier,
          jp.title,
          jp.locations_json,
          jp.source_url,
          jp.first_seen_at,
          jp.availability_state,
          orev.state AS review_state,
          orev.decision_reason,
          orev.reviewed_at,
          orev.snooze_until,
          re.evaluation_json
        FROM job_postings jp
        JOIN companies c ON c.id = jp.company_id
        JOIN opportunity_reviews orev ON orev.job_posting_id = jp.id
        LEFT JOIN role_evaluations re ON re.job_posting_id = jp.id
          AND re.id = (
            SELECT MAX(id) FROM role_evaluations latest
            WHERE latest.job_posting_id = jp.id
          )
        ORDER BY
          CASE orev.state
            WHEN 'new' THEN 1
            WHEN 'snoozed' THEN 2
            WHEN 'approved' THEN 3
            WHEN 'dismissed' THEN 4
            ELSE 5
          END,
          c.tier,
          jp.first_seen_at DESC,
          jp.id
        """
    ).fetchall()


def show_review(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT
          jp.id AS job_id,
          c.name AS company,
          c.tier AS company_tier,
          jp.title,
          jp.locations_json,
          jp.department,
          jp.employment_type,
          jp.description_text,
          jp.source_url,
          jp.first_seen_at,
          jp.last_seen_at,
          jp.availability_state,
          orev.state AS review_state,
          orev.decision_reason,
          orev.reviewed_at,
          orev.snooze_until,
          re.evaluation_json
        FROM job_postings jp
        JOIN companies c ON c.id = jp.company_id
        JOIN opportunity_reviews orev ON orev.job_posting_id = jp.id
        LEFT JOIN role_evaluations re ON re.job_posting_id = jp.id
          AND re.id = (
            SELECT MAX(id) FROM role_evaluations latest
            WHERE latest.job_posting_id = jp.id
          )
        WHERE jp.id = ?
        """,
        (job_id,),
    ).fetchone()


def approve_review(conn: sqlite3.Connection, job_id: int) -> ReviewUpdate:
    return _set_review(conn, job_id, "approved", decision_reason=None, snooze_until=None)


def dismiss_review(conn: sqlite3.Connection, job_id: int, reason: str) -> ReviewUpdate:
    cleaned_reason = reason.strip()
    if not cleaned_reason:
        raise ValueError("dismiss requires a non-empty reason")
    return _set_review(
        conn,
        job_id,
        "dismissed",
        decision_reason=cleaned_reason,
        snooze_until=None,
    )


def snooze_review(conn: sqlite3.Connection, job_id: int, until: str) -> ReviewUpdate:
    parsed_until = _validate_date(until)
    return _set_review(
        conn,
        job_id,
        "snoozed",
        decision_reason=None,
        snooze_until=parsed_until,
    )


def reopen_review(conn: sqlite3.Connection, job_id: int) -> ReviewUpdate:
    _ensure_review_exists(conn, job_id)
    conn.execute(
        """
        UPDATE opportunity_reviews
        SET state = 'new',
            decision_reason = NULL,
            reviewed_at = NULL,
            snooze_until = NULL
        WHERE job_posting_id = ?
        """,
        (job_id,),
    )
    conn.commit()
    return ReviewUpdate(
        job_id=job_id,
        state="new",
        decision_reason=None,
        reviewed_at=None,
        snooze_until=None,
    )


def evaluation_summary(row: sqlite3.Row) -> dict[str, object]:
    if not row["evaluation_json"]:
        return {}
    return json.loads(row["evaluation_json"])


def _set_review(
    conn: sqlite3.Connection,
    job_id: int,
    state: ReviewState,
    *,
    decision_reason: str | None,
    snooze_until: str | None,
) -> ReviewUpdate:
    _ensure_review_exists(conn, job_id)
    reviewed_at = utc_now()
    conn.execute(
        """
        UPDATE opportunity_reviews
        SET state = ?,
            decision_reason = ?,
            reviewed_at = ?,
            snooze_until = ?
        WHERE job_posting_id = ?
        """,
        (state, decision_reason, reviewed_at, snooze_until, job_id),
    )
    conn.commit()
    return ReviewUpdate(
        job_id=job_id,
        state=state,
        decision_reason=decision_reason,
        reviewed_at=reviewed_at,
        snooze_until=snooze_until,
    )


def _ensure_review_exists(conn: sqlite3.Connection, job_id: int) -> None:
    row = conn.execute(
        """
        SELECT 1
        FROM opportunity_reviews
        WHERE job_posting_id = ?
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Job not found in review queue: {job_id}")


def _validate_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("snooze date must be YYYY-MM-DD") from exc
    return value
