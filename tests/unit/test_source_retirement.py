from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app.config import load_company_config
from app.db import (
    get_digest_rows, init_db, stale_open_posting_ids_for_evaluator,
    upsert_company, upsert_postings, upsert_source,
)
from app.models import JobPosting
from app.services.export_csv import export_csvs
from app.services.live_noise import _candidate_rows
from app.services.review import list_reviews, reopen_review, show_review
from app.services.scheduled_scan import plan_stale_backfill_for_connection
from app.services.source_retirement import (
    apply_retirement_report, connect_for_retirement, retirement_plan, write_retirement_report,
)


class SourceRetirementTest(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.addCleanup(self.conn.close)

    def seed(self, name="Databricks", *, source_type=None, source_key=None,
             health="healthy", enabled=True, key="one") -> tuple[int, int]:
        company = load_company_config(name)
        company = replace(company, enabled=enabled, ats_type=source_type or company.ats_type,
                          source_key=source_key or company.source_key)
        company_id = upsert_company(self.conn, company)
        source_id = upsert_source(self.conn, company_id, company)
        self.conn.execute("UPDATE job_sources SET health_status = ? WHERE id = ?", (health, source_id))
        result = upsert_postings(self.conn, company_id, source_id, [JobPosting(
            company=company.name, title="Strategy & Operations Manager", locations=["London"],
            department="Strategy and Operations", employment_type="Full time",
            description_text="Lead strategic planning and business operations programs.",
            source_type=company.ats_type, source_url="https://example.com/job/" + key,
            source_job_id=key, source_posted_at="2026-09-28", raw_payload_hash=key,
            canonical_key=key,
        )], "2026-09-28")
        job_id = result.new_posting_ids[0]
        self.conn.execute(
            """INSERT INTO role_evaluations (job_posting_id, profile_version_id,
                location_policy_version_id, prompt_version, model_version, input_hash,
                evaluation_json, created_at) VALUES (?, 'old', 'old', 'old', 'old', ?, '{}', ?)""",
            (job_id, key, "2026-09-28"),
        )
        self.conn.commit()
        return source_id, job_id

    def test_every_live_python_path_excludes_inactive_sources_before_retirement(self) -> None:
        cases = [
            ({"health": "disabled"}, False), ({"health": "retired"}, False),
            ({"health": "Retired"}, False),
            ({"enabled": False}, False), ({"name": "Deliveroo"}, False),
            ({"name": "Mistral AI", "source_type": "lever", "source_key": "mistral"}, False),
            ({"health": "failing"}, True), ({"health": "degraded"}, True),
            ({}, True),
            ({"name": "Deliveroo", "source_type": "manual", "source_key": "manual",
              "enabled": False}, True),
        ]
        for kwargs, visible in cases:
            with self.subTest(kwargs=kwargs):
                conn = self.conn
                self.conn = sqlite3.connect(":memory:")
                self.conn.row_factory = sqlite3.Row
                init_db(self.conn)
                try:
                    source_id, job_id = self.seed(**kwargs)
                    self.assertEqual(bool(get_digest_rows(self.conn, include_older=True)), visible)
                    self.assertEqual(bool(list_reviews(self.conn)), visible)
                    self.assertEqual(show_review(self.conn, job_id) is not None, visible)
                    self.assertEqual(bool(_candidate_rows(self.conn)), visible)
                    self.assertEqual(bool(stale_open_posting_ids_for_evaluator(
                        self.conn, source_id, evaluator_version="hybrid_claude_v4", limit=10,
                        recency_cutoff="2026-09-01",
                    )), visible)
                    with tempfile.TemporaryDirectory() as directory:
                        files = export_csvs(self.conn, Path(directory))
                        content = files["opportunities"].read_text()
                        self.assertEqual("Strategy & Operations Manager" in content, visible)
                        self.assertIn(kwargs.get("name", "Databricks"),
                                      files["source_coverage"].read_text())
                    if not visible:
                        with self.assertRaises(ValueError):
                            reopen_review(self.conn, job_id)
                finally:
                    self.conn.close()
                    self.conn = conn

    def test_report_is_read_only_and_apply_is_idempotent_preserving_history(self) -> None:
        source_id, job_id = self.seed(name="Deliveroo")
        active_source, active_job = self.seed()
        self.conn.execute("UPDATE opportunity_reviews SET state='approved', "
                          "decision_reason='keep history', reviewed_at='2026-09-28' WHERE job_posting_id=?",
                          (job_id,))
        self.conn.commit()
        reviews = [tuple(row) for row in self.conn.execute("SELECT * FROM opportunity_reviews")]
        evaluations = [tuple(row) for row in self.conn.execute("SELECT * FROM role_evaluations")]
        changes = self.conn.total_changes
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            plan = write_retirement_report(self.conn, path)
            self.assertEqual(json.loads(path.read_text()), plan)
        self.assertEqual(self.conn.total_changes, changes)
        self.assertEqual(plan["posting_count"], 1)
        self.assertEqual(plan["sources"][0]["source_id"], source_id)
        self.assertEqual(apply_retirement_report(self.conn, plan), 1)
        self.assertEqual(apply_retirement_report(self.conn, plan), 0)
        self.assertEqual(self.conn.execute("SELECT availability_state FROM job_postings WHERE id=?",
                                          (job_id,)).fetchone()[0], "unavailable")
        self.assertEqual(self.conn.execute("SELECT availability_state FROM job_postings WHERE id=?",
                                          (active_job,)).fetchone()[0], "open")
        self.assertEqual(self.conn.execute("SELECT health_status FROM job_sources WHERE id=?",
                                          (active_source,)).fetchone()[0], "healthy")
        self.assertEqual([tuple(row) for row in self.conn.execute("SELECT * FROM opportunity_reviews")],
                         reviews)
        self.assertEqual([tuple(row) for row in self.conn.execute("SELECT * FROM role_evaluations")],
                         evaluations)

    def test_reenabled_or_newly_changed_plan_is_rejected_without_partial_retirement(self) -> None:
        self.seed(name="Deliveroo")
        plan = retirement_plan(self.conn)
        with patch("app.services.source_retirement.load_watchlist", return_value=[{
            "name": "Deliveroo", "enabled": True, "ats_type": "ashby", "source_key": "deliveroo",
        }]):
            with self.assertRaisesRegex(ValueError, "active again"):
                apply_retirement_report(self.conn, plan)
        self.seed(name="Deliveroo", key="two")
        with self.assertRaisesRegex(ValueError, "New postings"):
            apply_retirement_report(self.conn, plan)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM job_postings "
                                          "WHERE availability_state='open'").fetchone()[0], 2)
        plan["posting_count"] += 1
        with self.assertRaisesRegex(ValueError, "Invalid retirement"):
            apply_retirement_report(self.conn, plan)

    def test_preflight_reports_excluded_candidates_and_never_selects_them(self) -> None:
        self.seed()
        _, inactive_job = self.seed(name="Deliveroo")
        with patch("app.db.recency_cutoff_date", return_value="2026-09-01"):
            plan = plan_stale_backfill_for_connection(self.conn)
        self.assertEqual(plan.item_count, 1)
        self.assertEqual(plan.selected_inactive_count, 0)
        self.assertEqual(plan.excluded_inactive_candidate_count, 1)
        self.assertEqual(plan.excluded_inactive_gate_passer_count, 1)
        self.assertEqual(plan.excluded_sources[0]["company"], "Deliveroo")
        self.assertEqual(self.conn.execute("SELECT availability_state FROM job_postings WHERE id=?",
                                          (inactive_job,)).fetchone()[0], "open")
        self.conn.execute("UPDATE job_sources SET health_status='disabled'")
        with patch("app.db.recency_cutoff_date", return_value="2026-09-01"):
            disabled_plan = plan_stale_backfill_for_connection(self.conn)
        self.assertEqual(disabled_plan.item_count, 0)
        self.assertEqual(disabled_plan.excluded_inactive_candidate_count, 2)

    def test_default_report_connection_cannot_write_or_create_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {}, clear=True):
            path = Path(directory) / "existing.sqlite"
            with sqlite3.connect(path) as setup:
                setup.execute("CREATE TABLE sample (id INTEGER)")
            conn = connect_for_retirement(path)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute("INSERT INTO sample VALUES (1)")
            finally:
                conn.close()
            with self.assertRaises(sqlite3.OperationalError):
                connect_for_retirement(Path(directory) / "missing.sqlite")

    def test_manual_and_automatic_sources_do_not_retire_each_other(self) -> None:
        automatic_source, _ = self.seed()
        manual_source, _ = self.seed(source_type="manual", source_key="manual", key="manual")
        self.assertEqual(len(get_digest_rows(self.conn, include_older=True)), 2)
        company = load_company_config("Databricks")
        company_id = upsert_company(self.conn, company)
        upsert_source(self.conn, company_id, company)
        health = {row["id"]: row["health_status"] for row in self.conn.execute("SELECT * FROM job_sources")}
        self.assertEqual(health, {automatic_source: "healthy", manual_source: "healthy"})
        self.assertEqual(len(get_digest_rows(self.conn, include_older=True)), 2)
        self.assertEqual(retirement_plan(self.conn)["posting_count"], 0)
