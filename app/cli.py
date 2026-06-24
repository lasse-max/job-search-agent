"""Command-line interface for the Stage 1 discovery agent."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from app.config import DEFAULT_DB_PATH, OUTPUT_DIR
from app.db import connect, init_db
from app.services.benchmark import (
    DEFAULT_EVALUATION_SET,
    DEFAULT_JD_CACHE_DIR,
    DEFAULT_REPORT_DIR,
    refresh_jd_cache,
    run_benchmark,
)
from app.services.export_csv import backup_sqlite, export_csvs
from app.services.ingest import run_scan
from app.services.manual_intake import add_text_intake, add_url_intake, read_text_input
from app.services.review import (
    approve_review,
    dismiss_review,
    evaluation_summary,
    list_reviews,
    reopen_review,
    show_review,
    snooze_review,
)
from app.services.scheduled_scan import run_scheduled_scan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Run a configured source scan")
    scan_parser.add_argument("--company", default="Databricks")
    scan_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    scan_parser.add_argument("--fixture", type=Path, help="Use a local adapter fixture")

    scan_all_parser = subparsers.add_parser("scan-all", help="Run all enabled source scans")
    scan_all_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    review_parser = subparsers.add_parser("review", help="Inspect new evaluated opportunities")
    review_subparsers = review_parser.add_subparsers(dest="review_command", required=True)
    review_list = review_subparsers.add_parser("list", help="List evaluated new opportunities")
    review_list.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    review_show = review_subparsers.add_parser("show", help="Show one evaluated opportunity")
    review_show.add_argument("job_id", type=int)
    review_show.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    review_approve = review_subparsers.add_parser("approve", help="Approve one opportunity")
    review_approve.add_argument("job_id", type=int)
    review_approve.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    review_dismiss = review_subparsers.add_parser("dismiss", help="Dismiss one opportunity")
    review_dismiss.add_argument("job_id", type=int)
    review_dismiss.add_argument("--reason", required=True)
    review_dismiss.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    review_snooze = review_subparsers.add_parser("snooze", help="Snooze one opportunity")
    review_snooze.add_argument("job_id", type=int)
    review_snooze.add_argument("--until", required=True)
    review_snooze.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    review_reopen = review_subparsers.add_parser("reopen", help="Reopen one opportunity")
    review_reopen.add_argument("job_id", type=int)
    review_reopen.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    add_url_parser = subparsers.add_parser("add-url", help="Add a role from a job URL")
    add_url_parser.add_argument("url")
    add_url_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    add_text_parser = subparsers.add_parser("add-text", help="Add a role from pasted JD text")
    add_text_parser.add_argument("path", nargs="?", default="-")
    add_text_parser.add_argument("--url", help="Original source URL for the pasted JD")
    add_text_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    export_parser = subparsers.add_parser("export", help="Write readable CSV exports")
    export_parser.add_argument("--out", type=Path, default=OUTPUT_DIR / "exports")
    export_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    backup_parser = subparsers.add_parser("backup", help="Write a SQLite backup copy")
    backup_parser.add_argument("destination", type=Path)
    backup_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)

    benchmark_parser = subparsers.add_parser("benchmark", help="Run offline evaluator benchmark")
    benchmark_parser.add_argument("--evaluation-set", type=Path, default=DEFAULT_EVALUATION_SET)
    benchmark_parser.add_argument("--cache-dir", type=Path, default=DEFAULT_JD_CACHE_DIR)
    benchmark_parser.add_argument("--out", type=Path, default=DEFAULT_REPORT_DIR)
    benchmark_parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Fetch/update cached JD snapshots before running the offline benchmark",
    )
    benchmark_parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Re-fetch cache files even when they already exist",
    )

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

    if args.command == "scan-all":
        result = run_scheduled_scan(db_path=args.db)
        print(f"status={result.status}")
        print(f"scanned={len(result.summaries)}")
        print(f"skipped={len(result.skipped)}")
        for skipped in result.skipped:
            print(f"skip={skipped}")
        for summary in result.summaries:
            print(
                f"source={summary.company} {summary.status} fetched={summary.fetched_count} "
                f"new={summary.new_count} changed={summary.changed_count}"
            )
            if summary.error_summary:
                print(f"source_error={summary.company}: {summary.error_summary}")
        for failure in result.failures:
            print(f"failure={failure}")
        return 1 if result.failures else 0

    if args.command == "review":
        conn = connect(args.db)
        init_db(conn)
        try:
            if args.review_command == "list":
                return _review_list(conn)
            if args.review_command == "show":
                return _review_show(conn, args.job_id)
            if args.review_command == "approve":
                update = approve_review(conn, args.job_id)
                print(f"approved job_id={update.job_id}")
                return 0
            if args.review_command == "dismiss":
                update = dismiss_review(conn, args.job_id, args.reason)
                print(f"dismissed job_id={update.job_id} reason={update.decision_reason}")
                return 0
            if args.review_command == "snooze":
                update = snooze_review(conn, args.job_id, args.until)
                print(f"snoozed job_id={update.job_id} until={update.snooze_until}")
                return 0
            if args.review_command == "reopen":
                update = reopen_review(conn, args.job_id)
                print(f"reopened job_id={update.job_id}")
                return 0
        except ValueError as exc:
            print(str(exc))
            return 1

    if args.command == "add-url":
        try:
            result = add_url_intake(args.url, db_path=args.db)
        except ValueError as exc:
            print(str(exc))
            return 1
        print(result.message)
        if result.job_id is not None:
            print(f"job_id={result.job_id}")
            print(f"evaluated={result.evaluated_count}")
        return 0 if result.status == "stored" else 1

    if args.command == "add-text":
        try:
            result = add_text_intake(
                read_text_input(args.path),
                db_path=args.db,
                source_url=args.url,
            )
        except ValueError as exc:
            print(str(exc))
            return 1
        print(result.message)
        print(f"job_id={result.job_id}")
        print(f"evaluated={result.evaluated_count}")
        return 0

    if args.command == "export":
        conn = connect(args.db)
        init_db(conn)
        written = export_csvs(conn, args.out)
        for name, path in written.items():
            print(f"{name}={path}")
        return 0

    if args.command == "backup":
        conn = connect(args.db)
        init_db(conn)
        path = backup_sqlite(conn, args.destination)
        print(f"backup={path}")
        return 0

    if args.command == "benchmark":
        if args.refresh_cache:
            written = refresh_jd_cache(
                evaluation_set_path=args.evaluation_set,
                cache_dir=args.cache_dir,
                force=args.force_refresh,
            )
            print(f"cache_written={len(written)}")
        run = run_benchmark(
            evaluation_set_path=args.evaluation_set,
            cache_dir=args.cache_dir,
            report_dir=args.out,
        )
        metrics = run.metrics
        print(f"roles={metrics.total_roles}")
        print(f"apply_consider_recall={metrics.apply_consider_recall:.3f}")
        print(f"digest_precision={metrics.digest_precision:.3f}")
        print(f"blocker_accuracy={metrics.blocker_accuracy:.3f}")
        print(f"fit_band_agreement={metrics.fit_band_agreement:.3f}")
        print(f"feasibility_correctness={metrics.feasibility_correctness:.3f}")
        print(f"report_markdown={run.markdown_path}")
        print(f"report_csv={run.csv_path}")
        return 0 if metrics.recall_passes else 1

    parser.error("unknown command")
    return 2


def _review_list(conn: sqlite3.Connection) -> int:
    rows = list_reviews(conn)
    if not rows:
        print("No opportunities in the review queue.")
        return 0
    for row in rows:
        evaluation = evaluation_summary(row)
        locations = ", ".join(json.loads(row["locations_json"]))
        print(
            f"{row['job_id']}: [{row['review_state']}] {row['company']} - "
            f"{row['title']} | {locations} | fit={evaluation.get('role_fit_score', '')} | "
            f"{evaluation.get('recommendation', '')}"
        )
    return 0


def _review_show(conn: sqlite3.Connection, job_id: int) -> int:
    row = show_review(conn, job_id)
    if row is None:
        print(f"Job not found: {job_id}")
        return 1
    print(f"{row['company']} - {row['title']}")
    print(f"Review: {row['review_state']}")
    if row["decision_reason"]:
        print(f"Reason: {row['decision_reason']}")
    if row["snooze_until"]:
        print(f"Snoozed until: {row['snooze_until']}")
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
