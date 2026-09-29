from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sqlite3
import unittest
from urllib.parse import urlparse
from uuid import uuid4

from app.config import load_company_config
from app.db import (
    current_evaluation_policy_version, get_digest_rows, init_db, pending_material_posting_ids,
    record_evaluation_skip, stale_open_posting_ids_for_evaluator, upsert_company,
    upsert_postings, upsert_source,
)
from app.recency import (
    normalize_timestamp, posting_freshness_label, posting_is_recent,
    recency_cutoff_date, utc_timestamp_sql,
)
from app.services.material import material_hash_for_row
from app.postgres import PostgresConnection
from tests.unit.test_db import _posting


class TimestampNormalizationTest(unittest.TestCase):
    @unittest.skipUnless(os.getenv("JOB_AGENT_TEST_POSTGRES_URL"), "local Postgres test URL not set")
    def test_postgres_queries_and_read_view_normalize_offsets_in_non_utc_session(self):
        database_url = os.environ["JOB_AGENT_TEST_POSTGRES_URL"]
        if urlparse(database_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
            self.fail("Timestamp integration tests require a disposable localhost database")
        conn = PostgresConnection(database_url)
        schema = f"test_recency_{uuid4().hex}"
        conn.execute(f"CREATE SCHEMA {schema}")
        conn.execute(f"SET search_path TO {schema}")
        conn.execute("SET TIME ZONE 'Australia/Perth'")

        def cleanup():
            conn.rollback()
            conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            conn.commit()
            conn.close()

        self.addCleanup(cleanup)
        conn, source_id, ids = self._seed(conn)
        expected = [ids[name] for name in ("newer", "older", "fallback", "naive", "date", "boundary")]
        self.assertEqual(stale_open_posting_ids_for_evaluator(
            conn, source_id, evaluator_version="new-evaluator", limit=1,
            recency_cutoff="2026-09-15",
        ), expected[:1])
        self.assertEqual(stale_open_posting_ids_for_evaluator(
            conn, source_id, evaluator_version="new-evaluator", limit=100,
            recency_cutoff="2026-09-15",
        ), expected)
        digest_ids = [row["job_id"] for row in get_digest_rows(conn, recency_cutoff="2026-09-15")]
        self.assertEqual(digest_ids[:4], expected[:4])
        self.assertEqual(set(digest_ids), set(expected))
        self.assertEqual(pending_material_posting_ids(
            conn, source_id, recency_cutoff="2026-09-15",
        ), expected)
        conn.execute("UPDATE role_evaluations SET model_version = 'test|hybrid_claude_v4'")
        migration = Path(__file__).resolve().parents[2] / "migrations/010_stage15_active_source_reads.sql"
        for statement in re.findall(r"CREATE OR REPLACE VIEW\b.*?;", migration.read_text(), re.DOTALL):
            conn.executescript(statement)
        view_rows = conn.execute(
            "SELECT job_id, effective_at FROM current_opportunity_evaluations "
            "WHERE effective_at >= CAST(? AS TIMESTAMP WITH TIME ZONE) "
            "ORDER BY effective_at DESC, job_id DESC LIMIT ?",
            ("2026-09-15T00:00:00Z", 100),
        ).fetchall()
        self.assertEqual([row["job_id"] for row in view_rows], expected)
        self.assertEqual(
            normalize_timestamp(next(row["effective_at"] for row in view_rows
                                     if row["job_id"] == ids["boundary"])),
            datetime(2026, 9, 15, tzinfo=timezone.utc),
        )
        self.assertTrue(conn.execute(
            "SELECT 'security_invoker=true' = ANY(reloptions) AS invoker "
            "FROM pg_class WHERE oid = 'current_opportunity_evaluations'::regclass"
        ).fetchone()["invoker"])

    def test_python_filters_and_chips_use_the_utc_day_not_source_local_date(self):
        now = datetime(2026, 10, 6, tzinfo=timezone.utc)
        for posted, first_seen, recent, label in (
            ("2026-09-14T23:30:00-04:00", "2026-10-06", True, "posted 21d ago"),
            ("2026-09-14T20:00:00-04:00", "2026-10-06", True, "posted 21d ago"),
            ("2026-09-15T00:30:00+01:00", "2026-10-06", False, "posted 22d ago"),
            (None, "2026-09-14T23:30:00-04:00", True, "first seen 21d ago"),
            ("2026-09-15", "2026-10-06", True, "posted 21d ago"),
            ("2026-09-15T00:00:00", "2026-10-06", True, "posted 21d ago"),
            ("invalid", "2026-10-06", False, "posted date unknown"),
        ):
            with self.subTest(posted=posted, first_seen=first_seen):
                row = {"posted_at": posted, "first_seen_at": first_seen}
                self.assertEqual(posting_is_recent(row, now=now), recent)
                self.assertEqual(posting_freshness_label(row, now=now), label)
        self.assertEqual(
            normalize_timestamp("2026-09-14T20:00:00-04:00"),
            datetime(2026, 9, 15, tzinfo=timezone.utc),
        )
        self.assertEqual(
            recency_cutoff_date(now=datetime.fromisoformat("2026-10-05T20:00:00-04:00")),
            "2026-09-15",
        )

    def test_database_normalizes_before_cutoff_sort_and_limit_without_rewriting_history(self):
        conn, source_id, ids = self._seed()
        changes = conn.total_changes
        conn.execute("PRAGMA query_only = ON")
        self.assertEqual(stale_open_posting_ids_for_evaluator(
            conn, source_id, evaluator_version="new-evaluator", limit=1,
            recency_cutoff="2026-09-15",
        ), [ids["newer"]])
        expected = [ids[name] for name in ("newer", "older", "fallback", "naive", "date", "boundary")]
        self.assertEqual(stale_open_posting_ids_for_evaluator(
            conn, source_id, evaluator_version="new-evaluator", limit=100,
            recency_cutoff="2026-09-15",
        ), expected)
        conn.execute("PRAGMA query_only = OFF")
        self.assertEqual(
            {row["job_id"] for row in get_digest_rows(conn, recency_cutoff="2026-09-15")},
            set(expected),
        )
        self.assertEqual(len(get_digest_rows(conn, include_older=True)), 7)
        self.assertEqual(conn.total_changes, changes)
        self.assertEqual(conn.execute("SELECT posted_at FROM job_postings WHERE id = ?",
                                      (ids["boundary"],)).fetchone()[0],
                         "2026-09-14T20:00:00-04:00")

    def test_pending_material_only_resumes_changed_or_unscored_21_day_rows(self):
        conn, source_id, ids = self._seed()
        rows = conn.execute("SELECT * FROM job_postings").fetchall()
        for row in rows:
            conn.execute("UPDATE role_evaluations SET input_hash = ? WHERE job_posting_id = ?",
                         (material_hash_for_row(row), row["id"]))
        conn.execute("DELETE FROM role_evaluations WHERE job_posting_id = ?", (ids["fallback"],))
        conn.execute("UPDATE job_postings SET description_text = 'Changed scope' WHERE id = ?",
                     (ids["boundary"],))
        self.assertEqual(pending_material_posting_ids(
            conn, source_id, recency_cutoff="2026-09-15",
        ), [ids["fallback"], ids["boundary"]])
        changed = conn.execute("SELECT * FROM job_postings WHERE id = ?", (ids["boundary"],)).fetchone()
        record_evaluation_skip(conn, ids["boundary"], material_hash_for_row(changed), "off_location",
                               evaluator_version=current_evaluation_policy_version("new-evaluator"))
        self.assertEqual(pending_material_posting_ids(
            conn, source_id, recency_cutoff="2026-09-15",
        ), [ids["fallback"]])

    def test_completed_old_policy_skips_use_14_day_backfill_not_21_day_resume(self):
        conn, source_id, ids = self._seed()
        conn.execute("DELETE FROM role_evaluations")
        rows = conn.execute("SELECT * FROM job_postings").fetchall()
        for row in rows:
            conn.execute("UPDATE job_postings SET posted_at = ? WHERE id = ?",
                         ("2026-09-11T12:00:00Z", row["id"]))
        conn.execute("UPDATE job_postings SET posted_at = ? WHERE id = ?",
                     ("2026-09-15T00:00:00Z", ids["newer"]))
        conn.execute("UPDATE job_postings SET posted_at = ? WHERE id = ?",
                     ("2026-09-07T00:00:00Z", ids["naive"]))
        decisions = {
            "older": ("excluded_title_department_function", "old-policy"),
            "newer": ("excluded_title_department_function", "old-policy"),
            "boundary": ("excluded_title_department_function", "old-policy"),
            "outside": ("llm_evaluation_dropped: LLMProviderError: retry", None),
            "fallback": ("stale_evaluation_backfill_deferred_no_current_evaluator", None),
            "date": ("posting_older_than_14_days", None),
        }
        for row in rows:
            decision = decisions.get(row["source_job_id"])
            if decision:
                reason, version = decision
                record_evaluation_skip(conn, row["id"], material_hash_for_row(row), reason,
                                       evaluator_version=version)
        conn.execute("UPDATE job_postings SET description_text = 'New material' WHERE id = ?",
                     (ids["boundary"],))

        # September 29: completed 18-day-old decisions stay out, while an old
        # decision at 14 days is selected by the separately capped stale path.
        self.assertEqual(pending_material_posting_ids(
            conn, source_id, recency_cutoff="2026-09-08",
        ), [ids["fallback"], ids["outside"], ids["boundary"]])
        self.assertEqual(stale_open_posting_ids_for_evaluator(
            conn, source_id, evaluator_version="new-evaluator", limit=25,
            recency_cutoff="2026-09-15",
        ), [ids["newer"]])

    def test_postgres_read_views_use_the_same_normalizer_and_preserve_rls(self):
        root = Path(__file__).resolve().parents[2]
        expression = utc_timestamp_sql("COALESCE(jp.posted_at, jp.first_seen_at)", postgres=True)
        views = []
        for filename in ("001_stage15_core.sql", "010_stage15_active_source_reads.sql"):
            source = (root / "migrations" / filename).read_text()
            view = re.search(
                r"CREATE (?:OR REPLACE )?VIEW current_opportunity_evaluations\s+"
                r"WITH \(security_invoker = true\) AS\s+(.*?);", source, re.DOTALL,
            )
            self.assertIsNotNone(view)
            views.append(" ".join(view.group(1).split()))
            self.assertIn(f"{expression} AS effective_at", views[-1])
        self.assertEqual(views[0], views[1])

    def _seed(self, conn=None):
        if conn is None:
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            self.addCleanup(conn.close)
        init_db(conn)
        company = load_company_config("Databricks")
        company_id = upsert_company(conn, company)
        source_id = upsert_source(conn, company_id, company)
        dates = (
            ("older", "2026-09-15T12:00:00+00:00", "2026-09-15T12:00:00+00:00"),
            ("newer", "2026-09-15T09:00:00-04:00", "2026-09-15T09:00:00-04:00"),
            ("boundary", "2026-09-14T20:00:00-04:00", "2026-09-14T20:00:00-04:00"),
            ("outside", "2026-09-15T00:30:00+01:00", "2026-09-15T00:30:00+01:00"),
            ("fallback", None, "2026-09-14T23:30:00-04:00"),
            ("date", "2026-09-15", "2026-09-15"),
            ("naive", "2026-09-15T01:00:00", "2026-09-15T01:00:00"),
        )
        ids = {}
        for key, posted, seen in dates:
            result = upsert_postings(conn, company_id, source_id, [replace(
                _posting(key, ["London"], title=f"Role {key}"), source_posted_at=posted,
            )], seen, count_absences=False)
            ids[key] = result.new_posting_ids[0]
            conn.execute(
                "INSERT INTO role_evaluations (job_posting_id, profile_version_id, "
                "location_policy_version_id, prompt_version, model_version, input_hash, "
                "evaluation_json, created_at) VALUES (?, 'old', 'old', 'old', 'old', ?, '{}', ?)",
                (ids[key], f"old-{key}", seen),
            )
        conn.commit()
        return conn, source_id, ids
