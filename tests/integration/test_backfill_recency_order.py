from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app.adapters import get_adapter
from app.config import load_company_config, load_recency_policy
from app.db import (
    get_digest_rows, init_db, stale_open_posting_ids_for_evaluator,
    upsert_company, upsert_postings, upsert_source,
)
from app.services.evaluate import HYBRID_EVALUATOR_VERSION
from app.services.ingest import run_scan
from app.services.material import material_hash_for_row
from app.recency import posting_timestamp
from app.services.scheduled_scan import plan_stale_backfill_for_connection
from tests.integration.test_databricks_slice import SuccessfulProvider, _fixture_job


class RecordingProvider(SuccessfulProvider):
    def __init__(self) -> None:
        super().__init__()
        self.source_ids: list[str] = []

    def evaluate(self, request):
        self.source_ids.append(str(request.row["source_job_id"]))
        return super().evaluate(request)


class BackfillRecencyOrderTest(unittest.TestCase):
    def test_daily_trickle_keeps_mixed_offsets_in_utc_order_after_loading_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path, fixture, adapter, _, _ = self._seed(Path(directory))
            day = datetime.now(timezone.utc).date().isoformat()
            timestamps = {
                "9800000000": f"{day}T12:00:00+00:00",
                "9800000001": f"{day}T09:00:00-04:00",
            }
            payload = json.loads(fixture.read_text())
            conn = sqlite3.connect(db_path)
            for job in payload["jobs"]:
                timestamp = timestamps.get(str(job["id"]))
                if timestamp:
                    job["first_published"] = timestamp
                    job["updated_at"] = timestamp
                    conn.execute("UPDATE job_postings SET posted_at = ? WHERE source_job_id = ?",
                                 (timestamp, str(job["id"])))
            conn.commit()
            conn.close()
            fixture.write_text(json.dumps(payload))
            provider = RecordingProvider()
            result = self._scan(db_path, fixture, adapter, provider, limit=2)
            self.assertEqual(result.status, "success", result.error_summary)
            self.assertEqual(provider.source_ids, ["9800000001", "9800000000"])

    def test_daily_and_full_backfill_score_only_fresh_roles_in_actual_freshest_order(self):
        for limit in (25, 10_000):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as directory:
                db_path, fixture, adapter, rows, old_source_ids = self._seed(Path(directory))
                expected = sorted(
                    [row for row in rows if row["source_job_id"] not in old_source_ids],
                    key=lambda row: (posting_timestamp(row), row["id"]),
                    reverse=True,
                )[:limit]
                provider = RecordingProvider()
                result = self._scan(db_path, fixture, adapter, provider, limit)

                self.assertEqual(result.status, "success", result.error_summary)
                self.assertEqual(result.new_count, 0)
                self.assertEqual(result.changed_count, 0)
                self.assertEqual(result.evaluated_count, min(limit, 30))
                self.assertEqual(provider.source_ids, [row["source_job_id"] for row in expected])
                self.assertTrue(old_source_ids.isdisjoint(provider.source_ids))
                # The null posted-date role must use its own first-seen time, not
                # insertion ID, scan time, or the older evaluation timestamp.
                self.assertIn("9800000029", provider.source_ids)

                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                self.addCleanup(conn.close)
                current = get_digest_rows(conn, evaluator_version=HYBRID_EVALUATOR_VERSION)
                visible_source_ids = {row["source_job_id"] for row in current}
                self.assertTrue(old_source_ids.issubset(visible_source_ids))
                old_counts = conn.execute(
                    "SELECT jp.source_job_id, COUNT(re.id) AS count FROM job_postings jp "
                    "JOIN role_evaluations re ON re.job_posting_id=jp.id "
                    "GROUP BY jp.id"
                ).fetchall()
                self.assertEqual(
                    {row["source_job_id"]: row["count"] for row in old_counts
                     if row["source_job_id"] in old_source_ids},
                    dict.fromkeys(old_source_ids, 1),
                )

    def test_new_and_materially_changed_roles_keep_the_21_day_initial_evaluation_window(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path, fixture, adapter, _, old_source_ids = self._seed(Path(directory))
            payload = json.loads(fixture.read_text())
            changed = next(job for job in payload["jobs"] if str(job["id"]) == "9800000030")
            changed["content"] += "<p>New responsibility: lead the executive operating cadence.</p>"
            new_job = self._job(40, days_old=18)
            payload["jobs"].append(new_job)
            fixture.write_text(json.dumps(payload))
            provider = RecordingProvider()
            result = self._scan(db_path, fixture, adapter, provider, limit=25)

            self.assertEqual(result.status, "success", result.error_summary)
            self.assertEqual(result.new_count, 1)
            self.assertEqual(result.changed_count, 1)
            self.assertIn("9800000030", provider.source_ids)
            self.assertIn("9800000040", provider.source_ids)
            self.assertTrue((old_source_ids - {"9800000030"}).isdisjoint(provider.source_ids))
            self.assertEqual(provider.source_ids[-2:], ["9800000030", "9800000040"])

    def test_backfill_config_changes_selector_and_preflight_without_changing_browse_window(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path, _, _, rows, _ = self._seed(Path(directory))
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            self.addCleanup(conn.close)
            source_id = rows[0]["source_id"]
            baseline = load_recency_policy()
            for days, expected_count in ((14, 30), (7, 16)):
                with (
                    self.subTest(backfill_days=days),
                    patch("app.recency.load_recency_policy",
                          return_value=replace(baseline, backfill_max_age_days=days)),
                    patch("app.services.scheduled_scan.load_recency_policy",
                          return_value=replace(baseline, backfill_max_age_days=days)),
                ):
                    selected = stale_open_posting_ids_for_evaluator(
                        conn, source_id, evaluator_version=HYBRID_EVALUATOR_VERSION, limit=10_000,
                    )
                    plan = plan_stale_backfill_for_connection(conn)
                    self.assertEqual(len(selected), expected_count)
                    self.assertEqual(plan.item_count, expected_count)
                    self.assertEqual(plan.max_age_days, days)
                    self.assertEqual(len(get_digest_rows(
                        conn, evaluator_version=HYBRID_EVALUATOR_VERSION,
                    )), 33)

    def _seed(self, directory: Path):
        fixture = directory / "jobs.json"
        db_path = directory / "backfill.sqlite"
        jobs = [self._job(index, days_old=index // 2, hours=index % 2) for index in range(28)]
        # Include the 14-day boundary and a fresh first-seen fallback, plus roles
        # that are browse-fresh but too old for a version/policy-only backfill.
        jobs.extend([
            self._job(28, days_old=14), self._job(29, days_old=2, missing_posted=True),
            self._job(30, days_old=15), self._job(31, days_old=20),
            self._job(32, days_old=20, missing_posted=True),
        ])
        random.Random(31).shuffle(jobs)
        fixture.write_text(json.dumps({"jobs": jobs, "meta": {"total": len(jobs)}}))
        company = load_company_config("Databricks")
        adapter = get_adapter("greenhouse")
        fetched = adapter.fetch_from_file(company.source_key, str(fixture))
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        init_db(conn)
        company_id = upsert_company(conn, company)
        source_id = upsert_source(conn, company_id, company, seed_expected_volume=False)
        upsert_postings(conn, company_id, source_id, adapter.normalize(fetched, company), self._stamp(0))
        for index, age in ((29, 2), (32, 20)):
            conn.execute("UPDATE job_postings SET first_seen_at=? WHERE source_job_id=?",
                         (self._stamp(age), str(9800000000 + index)))
        rows = conn.execute("SELECT * FROM job_postings ORDER BY id").fetchall()
        evaluation_json = json.dumps({
            "recommendation": "apply_now", "role_fit_score": 85,
            "provenance": {"is_fallback": "false", "fallback_quality": "false"},
        })
        for row in rows:
            conn.execute(
                "INSERT INTO role_evaluations (job_posting_id, profile_version_id, "
                "location_policy_version_id, prompt_version, model_version, input_hash, "
                "evaluation_json, created_at) VALUES (?, 'old', 'old', 'old', ?, ?, ?, ?)",
                (row["id"], f"fake-claude|old-policy|{HYBRID_EVALUATOR_VERSION}",
                 material_hash_for_row(row), evaluation_json, self._stamp(row["id"])),
            )
        conn.commit()
        conn.close()
        old_source_ids = {str(9800000000 + index) for index in (30, 31, 32)}
        return db_path, fixture, adapter, rows, old_source_ids

    def _scan(self, db_path, fixture, adapter, provider, limit):
        fetched = adapter.fetch_from_file("databricks", str(fixture))
        with (
            patch.dict("os.environ", {"STALE_EVALUATION_BACKFILL_LIMIT": str(limit)}),
            patch("app.services.ingest.get_adapter", return_value=adapter),
            patch.object(adapter, "fetch", return_value=fetched),
            patch("app.services.ingest._degraded_reason", return_value=None),
            patch("app.services.evaluate.provider_from_env", return_value=provider),
            patch("app.services.ingest._safe_write_digest",
                  return_value=(Path("unused.html"), Path("unused.txt"), 0, None)),
        ):
            return run_scan(db_path=db_path)

    def _job(self, index, *, days_old, hours=0, missing_posted=False):
        job = _fixture_job(
            job_id=9800000000 + index, title=f"Strategic Operations Lead {index:02d}",
            location="London, United Kingdom", department="Business Operations",
            content=f"<p>Lead strategic planning and business operations for program {index}.</p>",
        )
        job["first_published"] = None if missing_posted else self._stamp(days_old, hours=hours)
        job["updated_at"] = job["first_published"]
        return job

    @staticmethod
    def _stamp(days, *, hours=0):
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return (today - timedelta(days=days, hours=hours)).isoformat()


if __name__ == "__main__":
    unittest.main()
