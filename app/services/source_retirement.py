"""Explicit, report-first retirement; never delete posting or human history."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3

from app.config import load_watchlist
from app.models import utc_now
from app.postgres import PostgresConnection, is_postgres_connection
from app.source_policy import source_exclusion_reason, source_inventory


class RetirementPlanMismatch(ValueError):
    def __init__(self, current_report: dict) -> None:
        super().__init__("Retirement plan changed; review and approve the new plan hash")
        self.current_report = current_report


def connect_for_retirement(db_path: Path, *, apply: bool = False):
    url = os.getenv("JOB_AGENT_DATABASE_URL")
    if url:
        return PostgresConnection(url, read_only=not apply)
    mode = "rw" if apply else "ro"
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode={mode}", uri=True)
    conn.row_factory = sqlite3.Row
    if not apply:
        conn.execute("PRAGMA query_only = ON")
    return conn


def _owner_touched_postings(conn, source_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT jp.id, c.name AS company, jp.title,
                  orev.state AS review_state, orev.reviewed_at,
                  a.id AS application_id, a.stage AS application_stage,
                  CAST(a.applied_at AS TEXT) AS applied_at
           FROM job_postings jp
           JOIN companies c ON c.id = jp.company_id
           LEFT JOIN opportunity_reviews orev ON orev.job_posting_id = jp.id
           LEFT JOIN applications a ON a.source_posting_id = jp.id
           WHERE jp.source_id = ? AND (orev.state <> 'new' OR a.id IS NOT NULL)
           ORDER BY jp.id""", (source_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def retirement_plan(conn) -> dict:
    watchlist = load_watchlist()
    sources = []
    for source in source_inventory(conn):
        reason = source_exclusion_reason(source, watchlist)
        if reason is None:
            continue
        postings = conn.execute(
            "SELECT id FROM job_postings WHERE source_id = ? "
            "AND availability_state = 'open' ORDER BY id", (source["source_id"],),
        ).fetchall()
        if not postings:
            continue
        sources.append({
            **source, "reason": reason, "posting_ids": [row["id"] for row in postings],
            "owner_touched_postings": _owner_touched_postings(conn, source["source_id"]),
        })
    plan = {"schema_version": 2, "sources": sources,
            "posting_count": sum(len(source["posting_ids"]) for source in sources)}
    return {**plan, "plan_hash": _plan_hash(plan), "generated_at": utc_now()}


def write_retirement_report(conn, path: Path) -> dict:
    plan = retirement_plan(conn)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return plan


def apply_retirement_report(conn, report: dict, *, expected_plan_hash: str | None = None) -> int:
    if report.get("schema_version") != 2 or report.get("plan_hash") != _plan_hash(report):
        raise ValueError("Invalid retirement report; generate a new read-only report")
    try:
        # Serialize this short reconciliation with scans. Never hold this lock
        # while fetching feeds, running models, or asking the owner a question.
        if is_postgres_connection(conn):
            conn.execute("SET LOCAL lock_timeout = '5s'")
            conn.execute("LOCK TABLE companies, job_sources, job_postings, "
                         "opportunity_reviews, applications IN SHARE ROW EXCLUSIVE MODE")
        else:
            conn.execute("BEGIN IMMEDIATE")
        if expected_plan_hash is not None:
            # Repeat the exact approval check under the lock: owner review or
            # application edits between report generation and apply invalidate it.
            current_report = retirement_plan(conn)
            if (current_report["plan_hash"] != expected_plan_hash
                    or report["plan_hash"] != expected_plan_hash):
                raise RetirementPlanMismatch(current_report)
        current = {row["source_id"]: row for row in source_inventory(conn)}
        watchlist = load_watchlist()
        for source in report["sources"]:
            actual = current.get(source["source_id"])
            if actual is None or source_exclusion_reason(actual, watchlist) is None:
                raise ValueError("Source is missing or active again; regenerate retirement report")
            identity = ("company_id", "company", "source_type", "source_key")
            if any(actual[key] != source[key] for key in identity):
                raise ValueError("Source identity changed; regenerate retirement report")
            open_ids = {row["id"] for row in conn.execute(
                "SELECT id FROM job_postings WHERE source_id = ? AND availability_state = 'open'",
                (source["source_id"],),
            ).fetchall()}
            if not open_ids.issubset(set(source["posting_ids"])):
                raise ValueError("New postings appeared; regenerate retirement report")
            if _owner_touched_postings(conn, source["source_id"]) != source["owner_touched_postings"]:
                raise ValueError("Owner history changed; regenerate retirement report")
        closed = 0
        for source in report["sources"]:
            # Only confirmed inactive sources are closed. Reviews, snapshots,
            # evaluations, first-seen dates and missing-scan counts are untouched.
            result = conn.execute(
                "UPDATE job_postings SET availability_state = 'unavailable' "
                "WHERE source_id = ? AND availability_state = 'open'", (source["source_id"],),
            )
            closed += result.rowcount
            conn.execute("UPDATE job_sources SET health_status = 'disabled' "
                         "WHERE id = ? AND health_status <> 'disabled'",
                         (source["source_id"],))
        conn.commit()
        return closed
    except Exception:
        conn.rollback()
        raise


def _plan_hash(plan: dict) -> str:
    payload = {key: plan[key] for key in ("schema_version", "sources", "posting_count")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
