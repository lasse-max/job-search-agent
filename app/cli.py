"""Command-line interface for the Stage 1 discovery agent."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from app.config import DATA_DIR, DEFAULT_DB_PATH, OUTPUT_DIR
from app.db import connect, init_db
from app.services.benchmark import (
    DEFAULT_EVALUATION_SET,
    DEFAULT_JD_CACHE_DIR,
    DEFAULT_LIVE_NOISE_PRECISION_SET,
    DEFAULT_LIVE_NOISE_SET,
    DEFAULT_REPORT_DIR,
    labelled_live_noise_count,
    refresh_jd_cache,
    run_benchmark,
    run_gate_recall_benchmark,
    run_live_noise_benchmark,
)
from app.services.export_csv import backup_sqlite, export_csvs
from app.services.ingest import run_scan
from app.services.live_noise import sample_live_noise_set
from app.services.llm_evaluator import provider_from_env
from app.services.manual_intake import add_text_intake, add_url_intake, read_text_input
from app.services.postgres_migration import migrate_sqlite_to_postgres
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
    scan_parser.add_argument("--database-url", help="Postgres URL; defaults to JOB_AGENT_DATABASE_URL")
    scan_parser.add_argument("--fixture", type=Path, help="Use a local adapter fixture")

    scan_all_parser = subparsers.add_parser("scan-all", help="Run all enabled source scans")
    scan_all_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    scan_all_parser.add_argument(
        "--database-url",
        help="Postgres URL; defaults to JOB_AGENT_DATABASE_URL",
    )

    migrate_parser = subparsers.add_parser(
        "migrate-postgres",
        help="One-way import from the local SQLite cache into Postgres",
    )
    migrate_parser.add_argument("--source", type=Path, default=DEFAULT_DB_PATH)
    migrate_parser.add_argument(
        "--database-url",
        help="Postgres URL; defaults to JOB_AGENT_DATABASE_URL",
    )
    migrate_parser.add_argument(
        "--report",
        type=Path,
        default=OUTPUT_DIR / "sqlite_to_postgres_migration_report.md",
    )
    migrate_parser.add_argument(
        "--owner-email",
        help="Optional single-user allow-list seed for Supabase Auth",
    )
    migrate_parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Rows per Postgres import batch",
    )
    migrate_parser.add_argument(
        "--replace-target",
        action="store_true",
        help="Clear import-owned Postgres tables before loading from SQLite",
    )

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
    benchmark_parser.add_argument(
        "--gate-recall-set",
        type=Path,
        default=DEFAULT_LIVE_NOISE_SET,
        help="Uniform live-noise labels used to check relevance-gate recall",
    )
    benchmark_parser.add_argument(
        "--precision-set",
        type=Path,
        default=DEFAULT_LIVE_NOISE_PRECISION_SET,
        help="Gate-passer live-noise labels used to measure digest precision",
    )
    benchmark_parser.add_argument(
        "--live-noise-set",
        type=Path,
        default=None,
        help="Deprecated alias for --precision-set",
    )
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
    benchmark_parser.add_argument(
        "--populate-llm-cache",
        action="store_true",
        help="Use ANTHROPIC_API_KEY once to populate llm_cache; default benchmark is cache-only",
    )

    sample_parser = subparsers.add_parser(
        "sample-live-noise",
        help="Sample cached live postings for human precision labels",
    )
    sample_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    sample_parser.add_argument(
        "--out",
        type=Path,
        default=DATA_DIR / "evaluation_set" / "live_noise_labels.yaml",
    )
    sample_parser.add_argument("--size", type=int, default=150)
    sample_parser.add_argument("--seed", type=int, default=7)
    sample_parser.add_argument(
        "--gate-passers",
        action="store_true",
        help="Sample only postings that pass the title/department relevance gate",
    )

    subparsers.add_parser("stage0-status", help="Show the current stage boundary")

    args = parser.parse_args(argv)

    if args.command == "stage0-status":
        print("Stage 0 audit is complete. Checkpoint B vertical slice is now in progress.")
        return 0

    if args.command == "scan":
        summary = run_scan(
            company_name=args.company,
            db_path=args.db,
            database_url=args.database_url,
            fixture_path=args.fixture,
        )
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
        result = run_scheduled_scan(
            db_path=args.db,
            database_url=args.database_url,
            send_digest=True,
        )
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
        if result.notification is not None:
            print(f"notification_status={result.notification.status}")
            print(f"notification_roles={result.notification.role_count}")
            print(f"notification_calibration_roles={result.notification.calibration_count}")
            print(f"notification_failures={result.notification.failure_count}")
            print(f"notification_html={result.notification.html_path}")
            if result.notification.error_summary:
                print(f"notification_error={result.notification.error_summary}")
        return 1 if result.failures else 0

    if args.command == "migrate-postgres":
        database_url = args.database_url or os.getenv("JOB_AGENT_DATABASE_URL") or ""
        if not database_url or database_url.startswith("sqlite"):
            print("Postgres URL required via --database-url or JOB_AGENT_DATABASE_URL")
            return 1
        report = migrate_sqlite_to_postgres(
            source_path=args.source,
            database_url=database_url,
            report_path=args.report,
            owner_email=args.owner_email or os.getenv("OWNER_EMAIL"),
            batch_size=args.batch_size,
            replace_target=args.replace_target,
        )
        print(f"report={args.report}")
        print(f"imported={report.imported}")
        print(f"skipped={report.skipped}")
        print(f"ambiguous={report.ambiguous}")
        return 1 if report.ambiguous else 0

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
        llm_provider = None
        if args.populate_llm_cache:
            llm_provider = provider_from_env()
            if llm_provider is None:
                print("ANTHROPIC_API_KEY is required for --populate-llm-cache")
                return 1
        run = run_benchmark(
            evaluation_set_path=args.evaluation_set,
            cache_dir=args.cache_dir,
            report_dir=args.out,
            llm_provider=llm_provider,
        )
        metrics = run.metrics
        print(f"roles={metrics.total_roles}")
        print(f"exact_recommendation_match={metrics.exact_recommendation_match_rate:.3f}")
        print(f"apply_consider_recall={metrics.apply_consider_recall:.3f}")
        print(f"digest_precision={metrics.digest_precision:.3f}")
        print(f"blocker_accuracy={metrics.blocker_accuracy:.3f}")
        print(f"fit_band_agreement={metrics.fit_band_agreement:.3f}")
        print(f"feasibility_correctness={metrics.feasibility_correctness:.3f}")
        print(f"report_markdown={run.markdown_path}")
        print(f"report_csv={run.csv_path}")
        gate_recall_passes = True
        if args.gate_recall_set.exists() and labelled_live_noise_count(args.gate_recall_set):
            gate_run = run_gate_recall_benchmark(
                live_noise_set_path=args.gate_recall_set,
                report_dir=args.out,
            )
            print(f"gate_recall_labelled={gate_run.metrics.labelled_roles}")
            print(f"gate_recall={gate_run.metrics.gate_recall:.3f}")
            print(f"gate_recall_report_markdown={gate_run.markdown_path}")
            print(f"gate_recall_report_csv={gate_run.csv_path}")
            gate_recall_passes = gate_run.metrics.recall_passes
        else:
            print("gate_recall_labelled=0")
            print("gate_recall=not_available")

        precision_set = args.live_noise_set or args.precision_set
        if precision_set.exists() and labelled_live_noise_count(precision_set):
            live_run = run_live_noise_benchmark(
                live_noise_set_path=precision_set,
                report_dir=args.out,
                label_set_purpose="gate_passer_precision",
                llm_provider=llm_provider,
            )
            print(f"live_noise_labelled={live_run.metrics.labelled_roles}")
            print(f"live_noise_recall={live_run.metrics.apply_consider_recall:.3f}")
            print(
                "live_noise_apply_consider_precision="
                f"{live_run.metrics.apply_consider_precision:.3f}"
            )
            print(
                "live_noise_all_surfaced_precision="
                f"{live_run.metrics.all_surfaced_precision:.3f}"
            )
            print(f"live_noise_precision_label_set={live_run.label_set_path}")
            print(
                "live_noise_precision_evaluator="
                f"{','.join(live_run.evaluator_versions) if live_run.evaluator_versions else 'not_available'}"
            )
            print(f"live_noise_report_markdown={live_run.markdown_path}")
            print(f"live_noise_report_csv={live_run.csv_path}")
            live_gate_passes = (
                live_run.metrics.passes
                if live_run.metrics.labelled_roles
                else True
            )
        else:
            print("live_noise_labelled=0")
            print("live_noise_recall=not_available")
            print("live_noise_apply_consider_precision=not_available")
            print("live_noise_all_surfaced_precision=not_available")
            live_gate_passes = True
        return 0 if metrics.recall_passes and gate_recall_passes and live_gate_passes else 1

    if args.command == "sample-live-noise":
        conn = connect(args.db)
        init_db(conn)
        result = sample_live_noise_set(
            conn,
            args.out,
            sample_size=args.size,
            seed=args.seed,
            gate_passers_only=args.gate_passers,
        )
        print(f"available={result.available_count}")
        print(f"sampled={result.sampled_count}")
        print(f"output={result.output_path}")
        return 0

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
