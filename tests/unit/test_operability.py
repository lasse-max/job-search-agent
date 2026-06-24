from __future__ import annotations

import csv
import io
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app.adapters import get_adapter
from app.cli import main
from app.models import CompanyConfig
from app.services.manual_intake import (
    ManualExtractionError,
    add_text_intake,
    add_url_intake,
)
from app.services.scheduled_scan import run_scheduled_scan


JOB_TEXT = """Company: ExampleCo
Title: Strategic Operations Manager
Location: Munich, Germany
Department: Strategy & Operations
Employment Type: Full-time

Lead strategy and operations programs for cross-functional stakeholders.
Own executive rhythm, customer operations, transformation work, and program delivery.
Fluent in German required for customer and regional stakeholder engagement.
"""


class OperabilityTest(unittest.TestCase):
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

    def test_scan_workflow_runs_every_six_hours_and_supports_manual_dispatch(self) -> None:
        workflow = Path(".github/workflows/scan.yml").read_text(encoding="utf-8")

        self.assertIn('cron: "0 */6 * * *"', workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("job-agent scan-all", workflow)


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
