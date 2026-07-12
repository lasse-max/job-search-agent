from __future__ import annotations

import csv
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

from app.adapters import get_adapter
from app.cli import main
from app.db import init_db
from app.models import CompanyConfig, RoleEvaluation
from app.services.manual_intake import (
    ManualExtractionError,
    add_text_intake,
    add_url_intake,
    process_manual_intake_queue,
)
from app.services.ingest import ScanSummary
from app.services.scheduled_scan import BackfillPlan, ScheduledScanResult, run_scheduled_scan


JOB_TEXT = """Company: ExampleCo
Title: Strategic Operations Manager
Location: Munich, Germany
Department: Strategy & Operations
Employment Type: Full-time

Lead strategy and operations programs for cross-functional stakeholders.
Own executive rhythm, customer operations, transformation work, and program delivery.
Fluent in German required for customer and regional stakeholder engagement.
"""


def _current_manual_evaluation() -> RoleEvaluation:
    return RoleEvaluation(
        role_fit_score=82,
        confidence=0.88,
        dimensions={
            "role_family_fit": 85,
            "evidence_strength": 80,
            "scope_seniority": 82,
            "gap_manageability": 82,
        },
        feasibility={"state": "viable", "reason": "EU-authorized"},
        strategic_priority={"tier": "1", "reason": "manual owner-selected role"},
        recommendation="apply_now",
        provenance={
            "model_version": "fake-claude",
            "evaluator_version": "hybrid_claude_v4",
            "fallback_quality": "false",
        },
        summary="Strong strategy and operations fit.",
    )


class OperabilityTest(unittest.TestCase):
    def test_manual_text_queue_uses_existing_evaluator_and_enters_shortlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            init_db(conn)
            conn.execute(
                """
                INSERT INTO manual_intake_submissions (
                  owner_email, intake_mode, source_url, jd_text, company, title,
                  location, note, destination, propose_watchlist, status, created_at, updated_at
                ) VALUES (?, 'text', ?, ?, ?, ?, ?, ?, 'to_apply', 1, 'queued', ?, ?)
                """,
                (
                    "owner@example.com",
                    "https://example.com/manual-role",
                    JOB_TEXT,
                    "ExampleCo",
                    "Strategic Operations Manager",
                    "Munich, Germany",
                    "referral",
                    "2026-07-12T08:00:00+00:00",
                    "2026-07-12T08:00:00+00:00",
                ),
            )
            conn.commit()
            conn.close()

            with patch(
                "app.services.manual_intake.evaluate_role",
                return_value=_current_manual_evaluation(),
            ) as evaluator:
                summary = process_manual_intake_queue(db_path=db_path)

            self.assertEqual(summary.completed, 1)
            evaluator.assert_called_once()
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            submission = conn.execute("SELECT * FROM manual_intake_submissions").fetchone()
            posting = conn.execute("SELECT * FROM job_postings").fetchone()
            review = conn.execute("SELECT * FROM opportunity_reviews").fetchone()
            evaluation = conn.execute("SELECT * FROM role_evaluations").fetchone()
            self.assertEqual(submission["status"], "completed")
            self.assertEqual(submission["job_posting_id"], posting["id"])
            self.assertEqual(review["state"], "interested")
            self.assertEqual(review["decision_reason"], "referral")
            self.assertEqual(posting["source_url"], "https://example.com/manual-role")
            self.assertTrue(evaluation["model_version"].endswith("|hybrid_claude_v4"))

    def test_manual_url_queue_requests_text_without_failing_other_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            init_db(conn)
            conn.execute(
                """
                INSERT INTO manual_intake_submissions (
                  owner_email, intake_mode, source_url, company, title, destination,
                  propose_watchlist, status, created_at, updated_at
                ) VALUES ('owner@example.com', 'url', 'https://example.com/walled',
                          'ExampleCo', 'Walled Role', 'potential_matches', 0,
                          'queued', '2026-07-12T08:00:00+00:00', '2026-07-12T08:00:00+00:00')
                """
            )
            conn.commit()
            conn.close()

            with patch(
                "app.services.manual_intake.fetch_url_text",
                side_effect=ManualExtractionError("url_extraction_too_short"),
            ):
                summary = process_manual_intake_queue(db_path=db_path)

            self.assertEqual(summary.needs_text, 1)
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT status, error_summary FROM manual_intake_submissions"
            ).fetchone()
            self.assertEqual(row, ("needs_text", "url_extraction_too_short"))

    def test_manual_intake_preserves_existing_company_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            init_db(conn)
            conn.execute(
                """
                INSERT INTO companies (name, tier, enabled, warm_path, notes)
                VALUES ('ExampleCo', 1, 0, 1, 'owner configuration')
                """
            )
            conn.commit()
            conn.close()

            with patch(
                "app.services.manual_intake.evaluate_role",
                return_value=_current_manual_evaluation(),
            ):
                add_text_intake(JOB_TEXT, db_path=db_path)

            conn = sqlite3.connect(db_path)
            company = conn.execute(
                "SELECT tier, enabled, warm_path, notes FROM companies WHERE name = 'ExampleCo'"
            ).fetchone()
            self.assertEqual(company, (1, 0, 1, "owner configuration"))

    def test_manual_text_queue_can_enter_applied_tracker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            init_db(conn)
            conn.execute(
                """
                INSERT INTO manual_intake_submissions (
                  owner_email, intake_mode, jd_text, company, title, location,
                  note, destination, propose_watchlist, status, created_at, updated_at
                ) VALUES (?, 'text', ?, ?, ?, ?, ?, 'applied', 0, 'queued', ?, ?)
                """,
                (
                    "owner@example.com",
                    JOB_TEXT,
                    "ExampleCo",
                    "Strategic Operations Manager",
                    "Munich, Germany",
                    "Already applied via referral",
                    "2026-07-12T08:00:00+00:00",
                    "2026-07-12T08:00:00+00:00",
                ),
            )
            conn.commit()
            conn.close()

            with patch(
                "app.services.manual_intake.evaluate_role",
                return_value=_current_manual_evaluation(),
            ):
                summary = process_manual_intake_queue(db_path=db_path)

            self.assertEqual(summary.completed, 1)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            application = conn.execute("SELECT * FROM applications").fetchone()
            self.assertEqual(application["stage"], "applied")
            self.assertEqual(application["notes"], "Already applied via referral")
            snapshot = json.loads(application["eval_snapshot_json"])
            self.assertTrue(snapshot["model_version"].endswith("|hybrid_claude_v4"))

    def test_review_cli_drives_all_requested_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            job_id = _add_job(db_path)

            list_output = _run_cli(["review", "list", "--db", str(db_path)])
            self.assertIn(f"{job_id}: [new]", list_output)

            show_output = _run_cli(["review", "show", str(job_id), "--db", str(db_path)])
            self.assertIn("ExampleCo - Strategic Operations Manager", show_output)
            self.assertIn("Review: new", show_output)

            _run_cli(["review", "approve", str(job_id), "--db", str(db_path)])
            approved = _review_row(db_path, job_id)
            self.assertEqual(approved["state"], "approved")
            self.assertIsNotNone(approved["reviewed_at"])

            _run_cli(["review", "reopen", str(job_id), "--db", str(db_path)])
            reopened = _review_row(db_path, job_id)
            self.assertEqual(reopened["state"], "new")
            self.assertIsNone(reopened["reviewed_at"])

            _run_cli(
                [
                    "review",
                    "dismiss",
                    str(job_id),
                    "--reason",
                    "not the right scope",
                    "--db",
                    str(db_path),
                ]
            )
            dismissed = _review_row(db_path, job_id)
            self.assertEqual(dismissed["state"], "dismissed")
            self.assertEqual(dismissed["decision_reason"], "not the right scope")

            _run_cli(["review", "reopen", str(job_id), "--db", str(db_path)])
            _run_cli(
                [
                    "review",
                    "snooze",
                    str(job_id),
                    "--until",
                    "2026-07-01",
                    "--db",
                    str(db_path),
                ]
            )
            snoozed = _review_row(db_path, job_id)
            self.assertEqual(snoozed["state"], "snoozed")
            self.assertEqual(snoozed["snooze_until"], "2026-07-01")

            _run_cli(["review", "reopen", str(job_id), "--db", str(db_path)])
            final = _review_row(db_path, job_id)
            self.assertEqual(final["state"], "new")
            self.assertIsNone(final["decision_reason"])
            self.assertIsNone(final["snooze_until"])

    def test_add_text_stores_evaluates_and_enters_review_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            text_path = Path(directory) / "jd.txt"
            text_path.write_text(JOB_TEXT, encoding="utf-8")

            output = _run_cli(["add-text", str(text_path), "--db", str(db_path)])
            self.assertIn("Stored manual role", output)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            self.assertEqual(_count(conn, "job_postings"), 1)
            self.assertEqual(_count(conn, "role_evaluations"), 1)
            self.assertEqual(_count(conn, "opportunity_reviews"), 1)
            review = conn.execute("SELECT state FROM opportunity_reviews").fetchone()
            self.assertEqual(review["state"], "new")

    def test_add_url_success_uses_same_manual_intake_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            url = "https://example.com/jobs/strategic-ops"

            with patch(
                "app.services.manual_intake.fetch_url_text",
                return_value=JOB_TEXT,
            ):
                result = add_url_intake(url, db_path=db_path)

            self.assertEqual(result.status, "stored")
            self.assertEqual(result.evaluated_count, 1)
            row = _posting_row(db_path, result.job_id)
            self.assertEqual(row["source_type"], "manual")
            self.assertEqual(row["source_url"], url)

    def test_add_url_failure_preserves_url_and_requests_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            url = "https://example.com/jobs/no-extract"

            with patch(
                "app.services.manual_intake.fetch_url_text",
                side_effect=ManualExtractionError("url_fetch_failed"),
            ):
                result = add_url_intake(url, db_path=db_path)

            self.assertEqual(result.status, "needs_text")
            self.assertIsNone(result.job_id)
            self.assertIn("paste the JD", result.message)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM manual_intake_requests").fetchone()
            self.assertEqual(row["url"], url)
            self.assertEqual(row["status"], "needs_text")
            self.assertEqual(_count(conn, "job_postings"), 0)

    def test_add_url_rejects_non_http_schemes_before_fetching(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"

            with patch("app.services.manual_intake.fetch_url_text") as fetch:
                with self.assertRaises(ValueError):
                    add_url_intake("file:///tmp/job.html", db_path=db_path)

            fetch.assert_not_called()

    def test_exports_and_backup_are_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            output_dir = Path(directory) / "exports"
            backup_path = Path(directory) / "backup.sqlite"
            job_id = _add_job(db_path)

            _run_cli(["review", "approve", str(job_id), "--db", str(db_path)])
            _run_cli(["export", "--out", str(output_dir), "--db", str(db_path)])
            _run_cli(["backup", str(backup_path), "--db", str(db_path)])

            expected_files = {
                "opportunities": output_dir / "opportunities.csv",
                "approved_roles": output_dir / "approved_roles.csv",
                "source_coverage": output_dir / "source_coverage.csv",
                "source_runs": output_dir / "source_runs.csv",
            }
            self.assertTrue(all(path.exists() for path in expected_files.values()))

            opportunities = _read_csv(expected_files["opportunities"])
            approved = _read_csv(expected_files["approved_roles"])
            coverage = _read_csv(expected_files["source_coverage"])

            self.assertEqual(opportunities[0]["review_state"], "approved")
            self.assertEqual(opportunities[0]["reviewed_at"] != "", True)
            self.assertEqual(approved[0]["job_id"], str(job_id))
            self.assertEqual(coverage[0]["source_type"], "manual")

            backup = sqlite3.connect(backup_path)
            self.assertEqual(_count(backup, "job_postings"), 1)

    def test_scheduler_skips_manual_sources_and_manual_adapter_is_intake_only(self) -> None:
        manual_company = CompanyConfig(
            name="ManualCo",
            tier=3,
            enabled=True,
            ats_type="manual",
            source_key="manualco",
            careers_url="manual:text",
            target_locations=["Manual / Unknown"],
            target_role_family_notes="Manual intake",
            warm_path=False,
        )

        result = run_scheduled_scan(companies=[manual_company])

        self.assertEqual(result.status, "success")
        self.assertEqual(result.summaries, [])
        self.assertEqual(result.skipped, ["ManualCo: manual sources are intake-only"])
        with self.assertRaisesRegex(ValueError, "intake-only"):
            get_adapter("manual")

    def test_scan_all_surfaces_degraded_without_failing_command(self) -> None:
        degraded_summary = ScanSummary(
            company="Databricks",
            source_type="greenhouse",
            source_key="databricks",
            status="degraded",
            fetched_count=1,
            new_count=0,
            changed_count=0,
            evaluated_count=0,
            digest_count=0,
            digest_html=Path("output/latest_digest.html"),
            digest_text=Path("output/latest_digest.txt"),
            error_summary="expected_volume_degraded",
        )
        result = ScheduledScanResult(
            summaries=[degraded_summary],
            skipped=[],
            failures=[],
        )

        with patch("app.cli.run_scheduled_scan", return_value=result):
            output = _run_cli(["scan-all"])

        self.assertIn("status=degraded", output)
        self.assertIn("source_error=Databricks: expected_volume_degraded", output)

    def test_scan_workflow_runs_daily_and_supports_manual_dispatch(self) -> None:
        workflow = Path(".github/workflows/scan.yml").read_text(encoding="utf-8")

        self.assertIn('cron: "0 6 * * *"', workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("full_stale_backfill:", workflow)
        self.assertIn("STALE_EVALUATION_BACKFILL_LIMIT:", workflow)
        self.assertIn("inputs.full_stale_backfill", workflow)
        self.assertIn("job-agent scan-all", workflow)
        self.assertIn("ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}", workflow)
        self.assertIn("ANTHROPIC_MODEL: claude-haiku-4-5", workflow)
        self.assertIn("RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}", workflow)
        self.assertIn(
            "DIGEST_RECIPIENT_EMAIL: ${{ secrets.DIGEST_RECIPIENT_EMAIL }}",
            workflow,
        )
        self.assertIn('MONTHLY_MODEL_SPEND_CAP_USD: "15"', workflow)
        self.assertNotIn("echo ${{ secrets.", workflow)

    def test_full_backfill_reports_items_eta_and_spend_before_scan(self) -> None:
        result = ScheduledScanResult(summaries=[], skipped=[], failures=[])
        plan = BackfillPlan(
            item_count=42,
            estimated_seconds=840,
            projected_spend_usd=0.168,
            max_age_days=21,
        )
        with (
            patch.dict("os.environ", {"STALE_EVALUATION_BACKFILL_LIMIT": "10000"}),
            patch("app.cli.plan_stale_backfill", return_value=plan) as planner,
            patch("app.cli.run_scheduled_scan", return_value=result),
        ):
            output = _run_cli(["scan-all"])

        planner.assert_called_once()
        self.assertIn(
            "backfill_plan_items=42 max_age_days=21 eta=0h14m projected_spend_usd=0.17",
            output,
        )

    def test_sample_live_noise_cli_writes_label_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            output_path = Path(directory) / "live_noise.yaml"
            _add_job(db_path)

            output = _run_cli(
                [
                    "sample-live-noise",
                    "--db",
                    str(db_path),
                    "--out",
                    str(output_path),
                    "--size",
                    "1",
                ]
            )

            self.assertIn("sampled=1", output)
            data = yaml.safe_load(output_path.read_text(encoding="utf-8"))
            self.assertEqual(data["version"], "live_noise_labels_v1")
            self.assertEqual(len(data["live_noise_set"]), 1)
            item = data["live_noise_set"][0]
            self.assertEqual(item["company"], "ExampleCo")
            self.assertEqual(item["expected_recommendation"], None)

    def test_sample_live_noise_cli_can_sample_gate_passers_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "agent.sqlite"
            output_path = Path(directory) / "precision.yaml"
            _add_job(db_path)
            add_text_intake(
                """Company: SalesCo
Title: Account Executive
Location: Munich, Germany
Department: Sales

Quota-carrying sales role.
""",
                db_path=db_path,
                source_url="https://example.com/sales",
            )

            output = _run_cli(
                [
                    "sample-live-noise",
                    "--gate-passers",
                    "--db",
                    str(db_path),
                    "--out",
                    str(output_path),
                    "--size",
                    "10",
                ]
            )

            self.assertIn("sampled=1", output)
            data = yaml.safe_load(output_path.read_text(encoding="utf-8"))
            self.assertEqual(data["set_purpose"], "gate_passer_precision")
            self.assertEqual(len(data["live_noise_set"]), 1)
            self.assertEqual(data["live_noise_set"][0]["role_title"], "Strategic Operations Manager")


def _add_job(db_path: Path) -> int:
    result = add_text_intake(JOB_TEXT, db_path=db_path, source_url="https://example.com/job")
    assert result.job_id is not None
    return result.job_id


def _run_cli(argv: list[str]) -> str:
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        code = main(argv)
    assert code == 0, stdout.getvalue()
    return stdout.getvalue()


def _review_row(db_path: Path, job_id: int) -> sqlite3.Row:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT *
        FROM opportunity_reviews
        WHERE job_posting_id = ?
        """,
        (job_id,),
    ).fetchone()
    assert row is not None
    return row


def _posting_row(db_path: Path, job_id: int | None) -> sqlite3.Row:
    assert job_id is not None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT jp.*, js.source_type
        FROM job_postings jp
        JOIN job_sources js ON js.id = jp.source_id
        WHERE jp.id = ?
        """,
        (job_id,),
    ).fetchone()
    assert row is not None
    return row


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
