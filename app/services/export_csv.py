"""Readable CSV exports and SQLite backup for Stage 1 operability."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path


EXPORT_FILENAMES = {
    "opportunities": "opportunities.csv",
    "approved_roles": "approved_roles.csv",
    "source_coverage": "source_coverage.csv",
    "source_runs": "source_runs.csv",
}


def export_csvs(conn: sqlite3.Connection, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    exports = {
        "opportunities": _opportunity_rows(conn),
        "approved_roles": _opportunity_rows(conn, review_state="approved"),
        "source_coverage": _source_coverage_rows(conn),
        "source_runs": _source_run_rows(conn),
    }
    written: dict[str, Path] = {}
    for name, rows in exports.items():
        path = output_dir / EXPORT_FILENAMES[name]
        _write_csv(path, rows)
        written[name] = path
    return written


def backup_sqlite(conn: sqlite3.Connection, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup_conn = sqlite3.connect(destination)
    try:
        conn.backup(backup_conn)
    finally:
        backup_conn.close()
    return destination


def _opportunity_rows(
    conn: sqlite3.Connection,
    *,
    review_state: str | None = None,
) -> list[dict[str, object]]:
    where_clause = "WHERE orev.state = ?" if review_state else ""
    params: tuple[str, ...] = (review_state,) if review_state else ()
    rows = conn.execute(
        f"""
        SELECT
          jp.id AS job_id,
          c.name AS company,
          c.tier AS company_tier,
          jp.title,
          jp.locations_json,
          jp.department,
          jp.employment_type,
          jp.source_url,
          jp.posted_at,
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
        {where_clause}
        ORDER BY c.tier, jp.first_seen_at DESC, jp.id
        """,
        params,
    ).fetchall()

    exported: list[dict[str, object]] = []
    for row in rows:
        evaluation = _json_mapping(row["evaluation_json"])
        feasibility = evaluation.get("feasibility") or {}
        if not isinstance(feasibility, dict):
            feasibility = {}
        exported.append(
            {
                "job_id": row["job_id"],
                "company": row["company"],
                "company_tier": row["company_tier"],
                "title": row["title"],
                "locations": "; ".join(json.loads(row["locations_json"])),
                "department": row["department"] or "",
                "employment_type": row["employment_type"] or "",
                "source_url": row["source_url"],
                "posted_at": row["posted_at"] or "",
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
                "availability_state": row["availability_state"],
                "review_state": row["review_state"],
                "decision_reason": row["decision_reason"] or "",
                "reviewed_at": row["reviewed_at"] or "",
                "snooze_until": row["snooze_until"] or "",
                "role_fit_score": evaluation.get("role_fit_score", ""),
                "recommendation": evaluation.get("recommendation", ""),
                "feasibility_state": feasibility.get("state", ""),
            }
        )
    return exported


def _source_coverage_rows(conn: sqlite3.Connection) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT
          c.name AS company,
          c.tier AS company_tier,
          c.enabled,
          js.source_type,
          js.source_key,
          js.source_url,
          js.parser_version,
          js.health_status,
          js.last_success_at,
          (
            SELECT COUNT(*)
            FROM job_postings jp
            WHERE jp.source_id = js.id AND jp.availability_state = 'open'
          ) AS open_postings,
          (
            SELECT sr.status
            FROM source_runs sr
            WHERE sr.job_source_id = js.id
            ORDER BY sr.id DESC
            LIMIT 1
          ) AS latest_run_status,
          (
            SELECT sr.error_summary
            FROM source_runs sr
            WHERE sr.job_source_id = js.id
            ORDER BY sr.id DESC
            LIMIT 1
          ) AS latest_error
        FROM job_sources js
        JOIN companies c ON c.id = js.company_id
        ORDER BY c.tier, c.name, js.source_type
        """
    ).fetchall()
    return [
        {
            "company": row["company"],
            "company_tier": row["company_tier"],
            "enabled": row["enabled"],
            "source_type": row["source_type"],
            "source_key": row["source_key"],
            "source_url": row["source_url"],
            "parser_version": row["parser_version"],
            "health_status": row["health_status"],
            "last_success_at": row["last_success_at"] or "",
            "open_postings": row["open_postings"],
            "latest_run_status": row["latest_run_status"] or "",
            "latest_error": row["latest_error"] or "",
        }
        for row in rows
    ]


def _source_run_rows(conn: sqlite3.Connection) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT
          sr.id AS run_id,
          c.name AS company,
          js.source_type,
          js.source_key,
          sr.started_at,
          sr.finished_at,
          sr.status,
          sr.http_status,
          sr.fetched_count,
          sr.new_count,
          sr.changed_count,
          sr.retry_count,
          sr.error_summary
        FROM source_runs sr
        JOIN job_sources js ON js.id = sr.job_source_id
        JOIN companies c ON c.id = js.company_id
        ORDER BY sr.id
        """
    ).fetchall()
    return [
        {
            "run_id": row["run_id"],
            "company": row["company"],
            "source_type": row["source_type"],
            "source_key": row["source_key"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "status": row["status"],
            "http_status": row["http_status"] if row["http_status"] is not None else "",
            "fetched_count": row["fetched_count"],
            "new_count": row["new_count"],
            "changed_count": row["changed_count"],
            "retry_count": row["retry_count"],
            "error_summary": row["error_summary"] or "",
        }
        for row in rows
    ]


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _json_mapping(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        return {}
    return parsed
