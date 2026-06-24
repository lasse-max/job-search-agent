from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
import unittest

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
            self.assertEqual(
                conn.execute("SELECT status FROM source_runs ORDER BY id DESC LIMIT 1").fetchone()[0],
                "failure",
            )


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
