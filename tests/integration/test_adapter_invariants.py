from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
import tempfile
from pathlib import Path
import unittest

from app.adapters import parser_version, source_endpoint
from app.config import load_company_config
from app.services.ingest import run_scan


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AdapterInvariantCase:
    company_name: str
    source_type: str
    valid_fixture: Path
    malformed_fixture: Path
    zero_fixture: Path
    missing_source_job_id: str
    expected_count: int
    expected_evaluated: int


CASES = (
    AdapterInvariantCase(
        company_name="Databricks",
        source_type="greenhouse",
        valid_fixture=ROOT / "data" / "fixtures" / "greenhouse" / "databricks_jobs.json",
        malformed_fixture=ROOT / "data" / "fixtures" / "greenhouse" / "malformed_jobs.json",
        zero_fixture=ROOT / "data" / "fixtures" / "greenhouse" / "zero_jobs.json",
        missing_source_job_id="8396801002",
        expected_count=3,
        expected_evaluated=3,
    ),
    AdapterInvariantCase(
        company_name="Airwallex",
        source_type="ashby",
        valid_fixture=ROOT / "data" / "fixtures" / "ashby" / "airwallex_jobs.json",
        malformed_fixture=ROOT / "data" / "fixtures" / "ashby" / "malformed_jobs.json",
        zero_fixture=ROOT / "data" / "fixtures" / "ashby" / "zero_jobs.json",
        missing_source_job_id="aac30c34-833c-4904-8c02-c4ea4abdb013",
        expected_count=3,
        expected_evaluated=3,
    ),
    AdapterInvariantCase(
        company_name="Mistral AI",
        source_type="lever",
        valid_fixture=ROOT / "data" / "fixtures" / "lever" / "mistral_jobs.json",
        malformed_fixture=ROOT / "data" / "fixtures" / "lever" / "malformed_jobs.json",
        zero_fixture=ROOT / "data" / "fixtures" / "lever" / "zero_jobs.json",
        missing_source_job_id="bfcc2d05-141a-49d3-aa4d-20d743ede9d9",
        expected_count=3,
        expected_evaluated=3,
    ),
)


class AdapterInvariantTest(unittest.TestCase):
    def test_scan_replay_is_idempotent_for_all_adapters(self) -> None:
        for case in CASES:
            with self.subTest(adapter=case.source_type):
                with tempfile.TemporaryDirectory() as directory:
                    db_path = Path(directory) / "slice.sqlite"

                    first = run_scan(
                        company_name=case.company_name,
                        db_path=db_path,
                        fixture_path=case.valid_fixture,
                    )
                    second = run_scan(
                        company_name=case.company_name,
                        db_path=db_path,
                        fixture_path=case.valid_fixture,
                    )

                    self.assertEqual(first.status, "success")
                    self.assertEqual(first.fetched_count, case.expected_count)
                    self.assertEqual(first.new_count, case.expected_count)
                    self.assertEqual(first.changed_count, 0)
                    self.assertEqual(first.evaluated_count, case.expected_evaluated)
                    self.assertEqual(second.new_count, 0)
                    self.assertEqual(second.changed_count, 0)
                    self.assertEqual(second.evaluated_count, 0)

                    conn = sqlite3.connect(db_path)
                    conn.row_factory = sqlite3.Row
                    source = conn.execute("SELECT * FROM job_sources").fetchone()
                    company = load_company_config(case.company_name)

                    self.assertEqual(_count(conn, "job_postings"), case.expected_count)
                    self.assertEqual(_count(conn, "role_evaluations"), case.expected_evaluated)
                    self.assertEqual(_count(conn, "opportunity_reviews"), case.expected_count)
                    self.assertEqual(_count(conn, "source_runs"), 2)
                    self.assertEqual(source["source_type"], case.source_type)
                    self.assertEqual(source["source_url"], source_endpoint(case.source_type, company.source_key))
                    self.assertEqual(source["parser_version"], parser_version(case.source_type))

    def test_absence_requires_two_successful_scans_for_all_adapters(self) -> None:
        for case in CASES:
            with self.subTest(adapter=case.source_type):
                with tempfile.TemporaryDirectory() as directory:
                    db_path = Path(directory) / "slice.sqlite"
                    partial_fixture = _write_partial_fixture(case, Path(directory))

                    run_scan(
                        company_name=case.company_name,
                        db_path=db_path,
                        fixture_path=case.valid_fixture,
                    )
                    run_scan(
                        company_name=case.company_name,
                        db_path=db_path,
                        fixture_path=partial_fixture,
                    )

                    conn = sqlite3.connect(db_path)
                    conn.row_factory = sqlite3.Row
                    row = _posting_row(conn, case.missing_source_job_id)
                    self.assertEqual(row["availability_state"], "open")
                    self.assertEqual(row["missing_successful_scan_count"], 1)

                    run_scan(
                        company_name=case.company_name,
                        db_path=db_path,
                        fixture_path=partial_fixture,
                    )
                    row = _posting_row(conn, case.missing_source_job_id)
                    self.assertEqual(row["availability_state"], "unavailable")
                    self.assertEqual(row["missing_successful_scan_count"], 2)

    def test_failing_connector_does_not_count_as_absence_for_all_adapters(self) -> None:
        for case in CASES:
            with self.subTest(adapter=case.source_type):
                with tempfile.TemporaryDirectory() as directory:
                    db_path = Path(directory) / "slice.sqlite"

                    run_scan(
                        company_name=case.company_name,
                        db_path=db_path,
                        fixture_path=case.valid_fixture,
                    )
                    failed = run_scan(
                        company_name=case.company_name,
                        db_path=db_path,
                        fixture_path=case.malformed_fixture,
                    )

                    self.assertEqual(failed.status, "failure")
                    conn = sqlite3.connect(db_path)
                    rows = conn.execute(
                        "SELECT missing_successful_scan_count FROM job_postings ORDER BY id"
                    ).fetchall()
                    latest_status = conn.execute(
                        "SELECT status FROM source_runs ORDER BY id DESC LIMIT 1"
                    ).fetchone()[0]

                    self.assertEqual(
                        [row[0] for row in rows],
                        [0] * case.expected_count,
                    )
                    self.assertEqual(latest_status, "failure")

    def test_zero_job_response_is_successful_absence_signal_for_all_adapters(self) -> None:
        for case in CASES:
            with self.subTest(adapter=case.source_type):
                with tempfile.TemporaryDirectory() as directory:
                    db_path = Path(directory) / "slice.sqlite"

                    run_scan(
                        company_name=case.company_name,
                        db_path=db_path,
                        fixture_path=case.valid_fixture,
                    )
                    zero = run_scan(
                        company_name=case.company_name,
                        db_path=db_path,
                        fixture_path=case.zero_fixture,
                    )

                    self.assertEqual(zero.status, "success")
                    self.assertEqual(zero.fetched_count, 0)

                    conn = sqlite3.connect(db_path)
                    rows = conn.execute(
                        "SELECT missing_successful_scan_count FROM job_postings ORDER BY id"
                    ).fetchall()
                    self.assertEqual([row[0] for row in rows], [1] * case.expected_count)


def _write_partial_fixture(case: AdapterInvariantCase, directory: Path) -> Path:
    payload = json.loads(case.valid_fixture.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        partial_payload = [
            job for job in payload if str(job.get("id")) != case.missing_source_job_id
        ]
    else:
        partial_payload = dict(payload)
        partial_payload["jobs"] = [
            job
            for job in partial_payload["jobs"]
            if str(job.get("id")) != case.missing_source_job_id
        ]

    partial_fixture = directory / f"{case.source_type}_partial.json"
    partial_fixture.write_text(json.dumps(partial_payload), encoding="utf-8")
    return partial_fixture


def _posting_row(conn: sqlite3.Connection, source_job_id: str) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT availability_state, missing_successful_scan_count
        FROM job_postings
        WHERE source_job_id = ?
        """,
        (source_job_id,),
    ).fetchone()
    assert row is not None
    return row


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
