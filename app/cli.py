"""Command-line interface for the Checkpoint B vertical slice."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from app.config import DEFAULT_DB_PATH
from app.db import connect, get_digest_rows, init_db
from app.services.ingest import run_scan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Run a configured source scan")
    scan_parser.add_argument("--company", default="Databricks")
    scan_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    scan_parser.add_argument("--fixture", type=Path, help="Use a local adapter fixture")

    review_parser = subparsers.add_parser("review", help="Inspect new evaluated opportunities")
    review_subparsers = review_parser.add_subparsers(dest="review_command", required=True)
    review_list = review_subparsers.add_parser("list", help="List evaluated new opportunities")
    review_list.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    review_show = review_subparsers.add_parser("show", help="Show one evaluated opportunity")
    review_show.add_argument("job_id", type=int)
    review_show.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    subparsers.add_parser("stage0-status", help="Show the current stage boundary")

    args = parser.parse_args(argv)

    if args.command == "stage0-status":
        print("Stage 0 audit is complete. Checkpoint B vertical slice is now in progress.")
        return 0

    if args.command == "scan":
        summary = run_scan(company_name=args.company, db_path=args.db, fixture_path=args.fixture)
        print(f"status={summary.status}")
        print(f"company={summary.company}")
        print(f"source={summary.source_type}:{summary.source_key}")
        print(f"fetched={summary.fetched_count}")
        print(f"new={summary.new_count}")
        print(f"changed={summary.changed_count}")
        print(f"evaluated={summary.evaluated_count}")
        print(f"digest_roles={summary.digest_count}")
        print(f"digest_html={summary.digest_html}")
        print(f"digest_text={summary.digest_text}")
        if summary.error_summary:
            print(f"error={summary.error_summary}")
            return 1
        return 0

    if args.command == "review":
        conn = connect(args.db)
        init_db(conn)
        if args.review_command == "list":
            return _review_list(conn)
        if args.review_command == "show":
            return _review_show(conn, args.job_id)

    parser.error("unknown command")
    return 2


def _review_list(conn: sqlite3.Connection) -> int:
    rows = get_digest_rows(conn)
    if not rows:
        print("No evaluated new opportunities.")
        return 0
    for row in rows:
        evaluation = json.loads(row["evaluation_json"])
        locations = ", ".join(json.loads(row["locations_json"]))
        print(
            f"{row['job_id']}: {row['company']} - {row['title']} | {locations} | "
            f"fit={evaluation['role_fit_score']} | {evaluation['recommendation']}"
        )
    return 0


def _review_show(conn: sqlite3.Connection, job_id: int) -> int:
    row = conn.execute(
        """
        SELECT
          jp.id AS job_id,
          c.name AS company,
          jp.title,
          jp.locations_json,
          jp.department,
          jp.source_url,
          re.evaluation_json
        FROM job_postings jp
        JOIN companies c ON c.id = jp.company_id
        LEFT JOIN role_evaluations re ON re.job_posting_id = jp.id
        WHERE jp.id = ?
        ORDER BY re.id DESC
        LIMIT 1
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        print(f"Job not found: {job_id}")
        return 1
    print(f"{row['company']} - {row['title']}")
    print(f"Location: {', '.join(json.loads(row['locations_json']))}")
    print(f"Department: {row['department'] or ''}")
    print(f"Source: {row['source_url']}")
    if row["evaluation_json"]:
        print(json.dumps(json.loads(row["evaluation_json"]), indent=2))
    else:
        print("No evaluation for this posting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
