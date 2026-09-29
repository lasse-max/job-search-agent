from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import yaml

from app.config import load_company_config
from app.db import init_db, upsert_company, upsert_source, upsert_postings
from app.models import JobPosting
from app.services.source_retirement import connect_for_retirement, retirement_plan
from scripts.retire_sources import main, run_retirement


class ObservedConnection:
    """Record actual SQLite writes before the real connection is closed."""

    def __init__(self, conn):
        self.conn = conn
        self.changes = None

    def __getattr__(self, name):
        return getattr(self.conn, name)

    def close(self):
        self.changes = self.conn.total_changes
        self.conn.close()


class RetirementWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "retirement.sqlite"
        self.report_path = Path(directory.name) / "report.json"
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        init_db(self.conn)
        company = load_company_config("Deliveroo")
        company_id = upsert_company(self.conn, company)
        self.source_id = upsert_source(self.conn, company_id, company)
        result = upsert_postings(self.conn, company_id, self.source_id, [JobPosting(
            company=company.name, title="Operations Manager", locations=["London"],
            department="Operations", employment_type="Full time", description_text="Operations",
            source_type=company.ats_type, source_url="https://example.com/job",
            source_job_id="one", source_posted_at="2026-09-28", raw_payload_hash="one",
            canonical_key="one",
        )], "2026-09-28")
        self.job_id = result.new_posting_ids[0]
        self.conn.commit()
        self.plan = retirement_plan(self.conn)
        self.connections = []

    def connect(self, path, *, apply=False):
        observed = ObservedConnection(connect_for_retirement(path, apply=apply))
        self.connections.append((apply, observed))
        return observed

    def run_approved(self, approved_hash):
        output = StringIO()
        with patch.dict("os.environ", {}, clear=True), redirect_stdout(output), patch(
            "scripts.retire_sources.connect_for_retirement", side_effect=self.connect,
        ):
            result = run_retirement(approved_hash, db_path=self.db_path,
                                    report_path=self.report_path)
        return result, output.getvalue()

    def test_mismatch_is_read_only_and_prints_new_hash(self) -> None:
        for wrong_hash in ("wrong", self.plan["plan_hash"].upper(), self.plan["plan_hash"] + " "):
            with self.subTest(wrong_hash=wrong_hash):
                self.connections.clear()
                result, output = self.run_approved(wrong_hash)
                self.assertEqual(result, 1)
                self.assertIn(self.plan["plan_hash"], output)
                self.assertIn("database_writes=0", output)
                self.assertEqual([apply for apply, _ in self.connections], [False])
                self.assertEqual([conn.changes for _, conn in self.connections], [0])
        self.assertEqual(self.conn.execute("SELECT availability_state FROM job_postings").fetchone()[0],
                         "open")
        self.assertEqual(json.loads(self.report_path.read_text())["plan_hash"], self.plan["plan_hash"])

    def test_match_applies_and_old_hash_rerun_refuses_with_zero_actual_writes(self) -> None:
        result, output = self.run_approved(self.plan["plan_hash"])
        self.assertEqual(result, 0, output)
        self.assertIn("retirement_applied=1", output)
        self.assertEqual([apply for apply, _ in self.connections], [False, True])
        self.assertEqual([conn.changes for _, conn in self.connections], [0, 2])
        self.assertEqual(self.conn.execute("SELECT availability_state FROM job_postings").fetchone()[0],
                         "unavailable")
        self.connections.clear()
        result, output = self.run_approved(self.plan["plan_hash"])
        self.assertEqual(result, 1, output)
        self.assertIn("database_writes=0", output)
        fresh_report = json.loads(self.report_path.read_text())
        self.assertEqual(fresh_report["posting_count"], 0)
        self.assertNotEqual(fresh_report["plan_hash"], self.plan["plan_hash"])
        self.assertIn(fresh_report["plan_hash"], output)
        self.assertEqual([conn.changes for _, conn in self.connections], [0])

    def test_plan_change_between_read_and_apply_refuses_without_writes(self) -> None:
        original_connect = self.connect

        def owner_edit_before_apply(path, *, apply=False):
            if apply:
                self.conn.execute("UPDATE opportunity_reviews SET state='interested', "
                                  "reviewed_at='2026-09-29' WHERE job_posting_id=?", (self.job_id,))
                self.conn.commit()
            return original_connect(path, apply=apply)

        self.connect = owner_edit_before_apply
        result, output = self.run_approved(self.plan["plan_hash"])
        self.assertEqual(result, 1, output)
        self.assertIn("plan changed before apply", output)
        self.assertIn("database_writes=0", output)
        self.assertEqual([conn.changes for _, conn in self.connections], [0, 0])
        fresh_report = json.loads(self.report_path.read_text())
        self.assertNotEqual(fresh_report["plan_hash"], self.plan["plan_hash"])
        self.assertIn(fresh_report["plan_hash"], output)
        self.assertEqual(self.conn.execute("SELECT availability_state FROM job_postings").fetchone()[0],
                         "open")

    def test_missing_production_connection_fails_without_connecting(self) -> None:
        with patch.dict("os.environ", {}, clear=True), patch(
            "scripts.retire_sources.connect_for_retirement",
        ) as connect, redirect_stdout(StringIO()):
            self.assertEqual(main(["--retirement-plan-hash", self.plan["plan_hash"]]), 1)
        connect.assert_not_called()

    def test_dispatch_requires_hash_and_serializes_with_scans_on_main(self) -> None:
        root = Path(__file__).resolve().parents[2]
        workflow = yaml.safe_load((root / ".github/workflows/retire-sources.yml").read_text())
        triggers = workflow.get("on", workflow.get(True))
        self.assertEqual(set(triggers), {"workflow_dispatch"})
        inputs = triggers["workflow_dispatch"]["inputs"]
        self.assertEqual(set(inputs), {"retirement_plan_hash"})
        self.assertIs(inputs["retirement_plan_hash"]["required"], True)
        self.assertEqual(inputs["retirement_plan_hash"]["type"], "string")
        self.assertEqual(workflow["concurrency"], {
            "group": "scheduled-scan", "cancel-in-progress": False,
        })
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        job = workflow["jobs"]["retire"]
        self.assertEqual(job["if"], "${{ github.ref == 'refs/heads/main' }}")
        self.assertLessEqual(job["timeout-minutes"], 10)
        apply = next(step for step in job["steps"] if "RETIREMENT_PLAN_HASH" in step.get("env", {}))
        self.assertEqual(apply["env"]["RETIREMENT_PLAN_HASH"], "${{ inputs.retirement_plan_hash }}")
        self.assertEqual(apply["run"],
                         'python scripts/retire_sources.py --retirement-plan-hash "$RETIREMENT_PLAN_HASH"')
        artifact = next(step for step in job["steps"] if step.get("uses") == "actions/upload-artifact@v4")
        self.assertEqual(artifact["if"], "always()")
        self.assertEqual(artifact["with"]["path"], "output/source_retirement.json")
