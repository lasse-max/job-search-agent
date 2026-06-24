from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from app.services.ingest import run_scan


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "fixtures" / "greenhouse" / "databricks_jobs.json"
MALFORMED = ROOT / "data" / "fixtures" / "greenhouse" / "malformed_jobs.json"


class DatabricksSliceTest(unittest.TestCase):
    def test_scan_replay_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"

            first = run_scan(db_path=db_path, fixture_path=FIXTURE)
            second = run_scan(db_path=db_path, fixture_path=FIXTURE)

            self.assertEqual(first.status, "success")
            self.assertEqual(first.fetched_count, 3)
            self.assertEqual(first.new_count, 3)
            self.assertEqual(first.changed_count, 0)
            self.assertEqual(first.evaluated_count, 3)
            self.assertEqual(second.new_count, 0)
            self.assertEqual(second.changed_count, 0)
            self.assertEqual(second.evaluated_count, 0)

            conn = sqlite3.connect(db_path)
            self.assertEqual(_count(conn, "job_postings"), 3)
            self.assertEqual(_count(conn, "role_evaluations"), 3)
            self.assertEqual(_count(conn, "opportunity_reviews"), 3)
            self.assertEqual(_count(conn, "source_runs"), 2)

    def test_absence_requires_two_successful_scans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"
            partial_fixture = Path(directory) / "partial.json"
            payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
            payload["jobs"] = payload["jobs"][:2]
            partial_fixture.write_text(json.dumps(payload), encoding="utf-8")

            run_scan(db_path=db_path, fixture_path=FIXTURE)
            run_scan(db_path=db_path, fixture_path=partial_fixture)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT availability_state, missing_successful_scan_count
                FROM job_postings
                WHERE source_job_id = '8396801002'
                """
            ).fetchone()
            self.assertEqual(row["availability_state"], "open")
            self.assertEqual(row["missing_successful_scan_count"], 1)

            run_scan(db_path=db_path, fixture_path=partial_fixture)
            row = conn.execute(
                """
                SELECT availability_state, missing_successful_scan_count
                FROM job_postings
                WHERE source_job_id = '8396801002'
                """
            ).fetchone()
            self.assertEqual(row["availability_state"], "unavailable")
            self.assertEqual(row["missing_successful_scan_count"], 2)

    def test_failing_connector_does_not_count_as_absence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"

            run_scan(db_path=db_path, fixture_path=FIXTURE)
            failed = run_scan(db_path=db_path, fixture_path=MALFORMED)

            self.assertEqual(failed.status, "failure")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT missing_successful_scan_count FROM job_postings ORDER BY id"
            ).fetchall()
            self.assertEqual([row["missing_successful_scan_count"] for row in rows], [0, 0, 0])
            latest_status = conn.execute(
                "SELECT status FROM source_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
            self.assertEqual(
                latest_status,
                "failure",
            )

    def test_relevance_skips_are_logged_with_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"
            mixed_fixture = Path(directory) / "mixed.json"
            payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
            payload["jobs"].extend(
                [
                    _fixture_job(
                        job_id=9100001001,
                        title="Account Executive",
                        location="London, United Kingdom",
                        department="Sales",
                        content="<p>Quota-carrying sales role.</p>",
                    ),
                    _fixture_job(
                        job_id=9100001002,
                        title="Strategic Operations Lead",
                        location="New York, United States",
                        department="Business Operations",
                        content="<p>Strategy and operations role outside target locations.</p>",
                    ),
                ]
            )
            mixed_fixture.write_text(json.dumps(payload), encoding="utf-8")

            summary = run_scan(db_path=db_path, fixture_path=mixed_fixture)

            self.assertEqual(summary.status, "success")
            self.assertEqual(summary.fetched_count, 5)
            self.assertEqual(summary.evaluated_count, 3)

            conn = sqlite3.connect(db_path)
            reasons = [
                row[0]
                for row in conn.execute("SELECT reason FROM evaluation_skips ORDER BY reason")
            ]
            self.assertEqual(
                reasons,
                ["no_primary_or_stretch_family_signal", "non_target_location"],
            )

    def test_exception_after_fetch_records_failed_source_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"

            with patch(
                "app.adapters.greenhouse.GreenhouseAdapter.normalize",
                side_effect=RuntimeError("normalizer exploded"),
            ):
                failed = run_scan(db_path=db_path, fixture_path=FIXTURE)

            self.assertEqual(failed.status, "failure")
            self.assertIn("RuntimeError: normalizer exploded", failed.error_summary or "")

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            run = conn.execute("SELECT * FROM source_runs ORDER BY id DESC LIMIT 1").fetchone()
            source = conn.execute("SELECT * FROM job_sources ORDER BY id DESC LIMIT 1").fetchone()

            self.assertEqual(run["status"], "failure")
            self.assertEqual(run["fetched_count"], 3)
            self.assertIn("normalizer exploded", run["error_summary"])
            self.assertEqual(source["health_status"], "failing")
            self.assertEqual(_count(conn, "job_postings"), 0)

    def test_digest_failure_does_not_roll_back_successful_scan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"

            with patch(
                "app.services.ingest.write_digest",
                side_effect=RuntimeError("template exploded"),
            ):
                failed = run_scan(db_path=db_path, fixture_path=FIXTURE)

            self.assertEqual(failed.status, "failure")
            self.assertIn("digest_render_failed", failed.error_summary or "")

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            run = conn.execute("SELECT * FROM source_runs ORDER BY id DESC LIMIT 1").fetchone()
            source = conn.execute("SELECT * FROM job_sources ORDER BY id DESC LIMIT 1").fetchone()

            self.assertEqual(run["status"], "success")
            self.assertIsNone(run["error_summary"])
            self.assertEqual(source["health_status"], "healthy")
            self.assertEqual(_count(conn, "job_postings"), 3)
            self.assertEqual(_count(conn, "role_evaluations"), 3)


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _fixture_job(
    *,
    job_id: int,
    title: str,
    location: str,
    department: str,
    content: str,
) -> dict[str, object]:
    return {
        "absolute_url": (
            "https://databricks.com/company/careers/open-positions/"
            f"job?gh_jid={job_id}"
        ),
        "internal_job_id": job_id,
        "location": {"name": location},
        "metadata": [],
        "id": job_id,
        "updated_at": "2026-06-22T10:00:00-04:00",
        "requisition_id": f"REQ-{job_id}",
        "title": title,
        "company_name": "Databricks",
        "first_published": "2026-06-22T09:00:00-04:00",
        "language": "en",
        "application_deadline": None,
        "content": content,
        "departments": [{"name": department}],
        "offices": [{"name": location}],
    }


if __name__ == "__main__":
    unittest.main()
