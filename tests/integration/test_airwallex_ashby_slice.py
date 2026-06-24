from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
import unittest

from app.services.ingest import run_scan


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "fixtures" / "ashby" / "airwallex_jobs.json"
ZERO = ROOT / "data" / "fixtures" / "ashby" / "zero_jobs.json"
MALFORMED = ROOT / "data" / "fixtures" / "ashby" / "malformed_jobs.json"
MISSING_SOURCE_JOB_ID = "aac30c34-833c-4904-8c02-c4ea4abdb013"


class AirwallexAshbySliceTest(unittest.TestCase):
    def test_scan_replay_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"

            first = run_scan(company_name="Airwallex", db_path=db_path, fixture_path=FIXTURE)
            second = run_scan(company_name="Airwallex", db_path=db_path, fixture_path=FIXTURE)

            self.assertEqual(first.status, "success")
            self.assertEqual(first.fetched_count, 3)
            self.assertEqual(first.new_count, 3)
            self.assertEqual(first.changed_count, 0)
            self.assertEqual(first.evaluated_count, 3)
            self.assertEqual(second.new_count, 0)
            self.assertEqual(second.changed_count, 0)
            self.assertEqual(second.evaluated_count, 0)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            source = conn.execute("SELECT * FROM job_sources").fetchone()

            self.assertEqual(_count(conn, "job_postings"), 3)
            self.assertEqual(_count(conn, "role_evaluations"), 3)
            self.assertEqual(_count(conn, "opportunity_reviews"), 3)
            self.assertEqual(_count(conn, "source_runs"), 2)
            self.assertEqual(source["source_type"], "ashby")
            self.assertEqual(source["parser_version"], "ashby_v1")
            self.assertEqual(
                source["source_url"],
                "https://api.ashbyhq.com/posting-api/job-board/airwallex"
                "?includeCompensation=false",
            )

    def test_absence_requires_two_successful_scans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"
            partial_fixture = Path(directory) / "partial.json"
            payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
            payload["jobs"] = [
                job for job in payload["jobs"] if job["id"] != MISSING_SOURCE_JOB_ID
            ]
            partial_fixture.write_text(json.dumps(payload), encoding="utf-8")

            run_scan(company_name="Airwallex", db_path=db_path, fixture_path=FIXTURE)
            run_scan(company_name="Airwallex", db_path=db_path, fixture_path=partial_fixture)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT availability_state, missing_successful_scan_count
                FROM job_postings
                WHERE source_job_id = ?
                """,
                (MISSING_SOURCE_JOB_ID,),
            ).fetchone()
            self.assertEqual(row["availability_state"], "open")
            self.assertEqual(row["missing_successful_scan_count"], 1)

            run_scan(company_name="Airwallex", db_path=db_path, fixture_path=partial_fixture)
            row = conn.execute(
                """
                SELECT availability_state, missing_successful_scan_count
                FROM job_postings
                WHERE source_job_id = ?
                """,
                (MISSING_SOURCE_JOB_ID,),
            ).fetchone()
            self.assertEqual(row["availability_state"], "unavailable")
            self.assertEqual(row["missing_successful_scan_count"], 2)

    def test_zero_job_response_is_successful_absence_signal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"

            run_scan(company_name="Airwallex", db_path=db_path, fixture_path=FIXTURE)
            zero = run_scan(company_name="Airwallex", db_path=db_path, fixture_path=ZERO)

            self.assertEqual(zero.status, "success")
            self.assertEqual(zero.fetched_count, 0)

            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT missing_successful_scan_count FROM job_postings ORDER BY id"
            ).fetchall()
            self.assertEqual([row[0] for row in rows], [1, 1, 1])

    def test_failing_connector_does_not_count_as_absence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"

            run_scan(company_name="Airwallex", db_path=db_path, fixture_path=FIXTURE)
            failed = run_scan(company_name="Airwallex", db_path=db_path, fixture_path=MALFORMED)

            self.assertEqual(failed.status, "failure")
            self.assertIn("jobs array", failed.error_summary or "")

            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT missing_successful_scan_count FROM job_postings ORDER BY id"
            ).fetchall()
            latest_status = conn.execute(
                "SELECT status FROM source_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
            self.assertEqual([row[0] for row in rows], [0, 0, 0])
            self.assertEqual(latest_status, "failure")


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
