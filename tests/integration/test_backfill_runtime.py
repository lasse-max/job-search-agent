from __future__ import annotations

from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app.adapters import get_adapter
from app.cli import main
from app.config import load_company_config
from app.db import init_db, upsert_company, upsert_postings, upsert_source
from app.services.evaluate import HYBRID_EVALUATOR_VERSION, input_hash
from app.services.ingest import run_scan
from app.services.llm_evaluator import ModelSpendTracker
from app.services.notifications import deliver_digest
from app.services.scan_budget import ScanBudget
from app.services.scheduled_scan import run_scheduled_scan
from tests.integration.test_databricks_slice import (
    FakeEmailProvider, SuccessfulProvider, _fixture_job,
)


class FakeClock:
    now = 0.0

    def __call__(self):
        return self.now


class PaidProvider(SuccessfulProvider):
    def __init__(self, *, clock=None, crash_after=None):
        super().__init__()
        self.clock = clock
        self.crash_after = crash_after
        self.ids: list[str] = []

    def evaluate(self, request):
        if self.calls == self.crash_after:
            raise RuntimeError("mid-company crash after two paid evaluations")
        self.ids.append(request.row["source_job_id"])
        result = super().evaluate(request)
        if self.clock:
            self.clock.now += 135 * 60
        return result


class BackfillRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.db_path = self.root / "scan.sqlite"
        self.ledger = self.root / "spend.json"
        self.company = load_company_config("Databricks")
        self.adapter = get_adapter("greenhouse")
        now = datetime.now(timezone.utc)
        jobs = []
        for index in range(5):
            job = _fixture_job(
                job_id=9900000000 + index, title=f"Strategic Operations Lead {index}",
                location="London, United Kingdom", department="Business Operations",
                content=f"<p>Lead strategic planning and business operations for program {index}.</p>",
            )
            job["first_published"] = (now - timedelta(days=index + 1)).isoformat()
            jobs.append(job)
        self.fixture = self.root / "jobs.json"
        self.fixture.write_text(json.dumps({"jobs": jobs, "meta": {"total": len(jobs)}}))
        self.fetched = self.adapter.fetch_from_file(self.company.source_key, str(self.fixture))
        with self.connection() as conn:
            init_db(conn)
            company_id = upsert_company(conn, self.company)
            self.source_id = upsert_source(conn, company_id, self.company, seed_expected_volume=False)
            upsert_postings(conn, company_id, self.source_id,
                            self.adapter.normalize(self.fetched, self.company), now.isoformat())
            for row in conn.execute("SELECT * FROM job_postings").fetchall():
                conn.execute(
                    "INSERT INTO role_evaluations (job_posting_id, profile_version_id, "
                    "location_policy_version_id, prompt_version, model_version, input_hash, "
                    "evaluation_json, created_at) VALUES (?, 'old', 'old', 'old', 'old', ?, '{}', ?)",
                    (row["id"], input_hash(row), now.isoformat()),
                )
        self.expected_ids = [str(9900000000 + index) for index in range(5)]

    def connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        return conn

    @contextmanager
    def scanning(self, provider):
        with (
            patch.dict("os.environ", {"MODEL_SPEND_LEDGER_PATH": str(self.ledger),
                                      "MONTHLY_MODEL_SPEND_CAP_USD": "30",
                                      "STALE_EVALUATION_BACKFILL_LIMIT": "10000"}),
            patch("app.services.ingest.get_adapter", return_value=self.adapter),
            patch.object(self.adapter, "fetch", return_value=self.fetched),
            patch("app.services.ingest._degraded_reason", return_value=None),
            patch("app.services.evaluate.provider_from_env", return_value=provider),
            patch("app.services.ingest._safe_write_digest",
                  return_value=(self.root / "digest.html", self.root / "digest.txt", 0, None)),
        ):
            yield

    def current_evaluations(self):
        with self.connection() as conn:
            return conn.execute(
                "SELECT jp.source_job_id FROM role_evaluations re "
                "JOIN job_postings jp ON jp.id=re.job_posting_id "
                "WHERE re.model_version LIKE ? ORDER BY re.id",
                (f"%|{HYBRID_EVALUATOR_VERSION}",),
            ).fetchall()

    def test_budget_stops_cleanly_saves_spend_warns_and_resumes_without_duplicates(self):
        clock = FakeClock()
        budget = ScanBudget.start(clock=clock)
        provider = PaidProvider(clock=clock)
        email = FakeEmailProvider()
        with self.scanning(provider), patch(
            "app.services.scheduled_scan.deliver_digest",
            side_effect=lambda conn, **kwargs: deliver_digest(
                conn, output_dir=self.root / "output", provider=email,
                recipient="owner@example.com", **kwargs,
            ),
        ):
            result = run_scheduled_scan(db_path=self.db_path, companies=[self.company],
                                        budget=budget, send_digest=True)
        self.assertEqual(result.status, "degraded")
        self.assertEqual(result.failures, [])
        self.assertEqual(provider.ids, self.expected_ids[:2])
        self.assertEqual(len(self.current_evaluations()), 2)
        self.assertAlmostEqual(ModelSpendTracker(self.ledger).current_month_spend(), 0.002)
        self.assertEqual(result.backfill_warning,
                         "backfill stopped at wall-clock budget: 2 evaluated, 3 remaining")
        self.assertEqual(result.notification.status, "sent")
        self.assertIn(result.backfill_warning, email.messages[0].text_body)
        self.assertIn("wall-clock budget", email.messages[0].html_body)
        with self.connection() as conn:
            self.assertEqual(conn.execute("SELECT health_status FROM job_sources").fetchone()[0],
                             "degraded")
            self.assertEqual(conn.execute("SELECT status FROM source_runs").fetchone()[0], "degraded")
        output = io.StringIO()
        with patch("app.cli.run_scheduled_scan", return_value=result), redirect_stdout(output):
            self.assertEqual(main(["scan-all", "--db", str(self.db_path)]), 0)
        self.assertIn("::warning title=Evaluation time budget", output.getvalue())
        resumed = PaidProvider()
        with self.scanning(resumed):
            summary = run_scan(db_path=self.db_path)
        self.assertEqual(summary.status, "success", summary.error_summary)
        self.assertEqual(resumed.ids, self.expected_ids[2:])
        self.assertEqual(len(self.current_evaluations()), 5)
        self.assertAlmostEqual(ModelSpendTracker(self.ledger).current_month_spend(), 0.005)
        again = PaidProvider()
        with self.scanning(again):
            run_scan(db_path=self.db_path)
        self.assertEqual(again.ids, [])

    def test_mid_company_crash_keeps_completed_paid_evaluations_and_retry_only_does_rest(self):
        provider = PaidProvider(crash_after=2)
        with self.scanning(provider):
            result = run_scan(db_path=self.db_path)
        self.assertEqual(result.status, "failure")
        self.assertEqual(result.evaluated_count, 2)
        self.assertEqual([row[0] for row in self.current_evaluations()], self.expected_ids[:2])
        self.assertAlmostEqual(ModelSpendTracker(self.ledger).current_month_spend(), 0.002)
        resumed = PaidProvider()
        with self.scanning(resumed):
            result = run_scan(db_path=self.db_path)
        self.assertEqual(result.status, "success", result.error_summary)
        self.assertEqual(resumed.ids, self.expected_ids[2:])
        self.assertEqual(len(self.current_evaluations()), 5)
        self.assertAlmostEqual(ModelSpendTracker(self.ledger).current_month_spend(), 0.005)

    def test_scheduler_passes_one_deadline_to_every_source(self):
        budget = ScanBudget.start(clock=FakeClock())
        with (patch("app.services.scheduled_scan.run_scan") as scan,
              patch("app.services.scheduled_scan.process_manual_intake_queue")):
            run_scheduled_scan(companies=[self.company, load_company_config("OpenAI")], budget=budget)
        self.assertEqual(scan.call_count, 2)
        self.assertTrue(all(call.kwargs["budget"] is budget for call in scan.call_args_list))

    def test_quiet_heartbeat_includes_run_budget_warning_without_source_failure(self):
        email = FakeEmailProvider()
        warning = "backfill stopped at wall-clock budget: 0 evaluated, 5 remaining"
        with self.connection() as conn:
            result = deliver_digest(conn, output_dir=self.root / "heartbeat", provider=email,
                                    recipient="owner@example.com", run_warning=warning)
        self.assertEqual(result.status, "sent")
        self.assertEqual(result.role_count, 0)
        self.assertEqual(result.failure_count, 1)
        self.assertIn("No new roles today", email.messages[0].text_body)
        self.assertIn(warning, email.messages[0].text_body)
        self.assertIn(warning, email.messages[0].html_body)

    def test_deferred_new_and_materially_changed_roles_older_than_backfill_window_resume(self):
        payload = json.loads(self.fixture.read_text())
        now = datetime.now(timezone.utc)
        changed = payload["jobs"][2]
        changed["first_published"] = (now - timedelta(days=18)).isoformat()
        changed["content"] += "<p>Lead the executive operating cadence.</p>"
        new_job = dict(payload["jobs"][3])
        new_job.update({"id": 9900000005, "title": "Strategic Operations Lead 5",
                        "first_published": (now - timedelta(days=19)).isoformat(),
                        "content": "<p>Lead strategic planning and business operations for program 5.</p>"})
        payload["jobs"].append(new_job)
        self.fixture.write_text(json.dumps(payload))
        self.fetched = self.adapter.fetch_from_file(self.company.source_key, str(self.fixture))
        clock = FakeClock()
        with self.scanning(PaidProvider(clock=clock)):
            result = run_scan(db_path=self.db_path, budget=ScanBudget.start(clock=clock))
        self.assertEqual(result.status, "degraded", result.error_summary)
        resumed = PaidProvider()
        with self.scanning(resumed):
            result = run_scan(db_path=self.db_path)
        self.assertEqual(result.status, "success", result.error_summary)
        self.assertEqual(resumed.ids, ["9900000003", "9900000004", "9900000002", "9900000005"])
        self.assertEqual(len(self.current_evaluations()), 6)


if __name__ == "__main__":
    unittest.main()
