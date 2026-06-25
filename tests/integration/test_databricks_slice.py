from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from app.config import load_candidate_profile, load_location_policy, load_scoring_policy
from app.db import wake_due_snoozes
from app.services.evaluate import DETERMINISTIC_FALLBACK_VERSION
from app.services.digest import write_digest
from app.services.llm_evaluator import PROMPT_VERSION
from app.services.ingest import run_scan
from app.services.review import approve_review, dismiss_review, snooze_review


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "fixtures" / "greenhouse" / "databricks_jobs.json"


class DatabricksSliceTest(unittest.TestCase):
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
                [
                    "excluded_title_department_function",
                    "location_filter_us_requires_tier1_sponsorship_exceptional_role",
                ],
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

    def test_evaluation_records_real_config_versions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"

            run_scan(db_path=db_path, fixture_path=FIXTURE)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT profile_version_id, location_policy_version_id, prompt_version,
                       model_version, evaluation_json
                FROM role_evaluations
                ORDER BY id
                LIMIT 1
                """
            ).fetchone()
            evaluation = json.loads(row["evaluation_json"])

            self.assertEqual(row["profile_version_id"], load_candidate_profile().version)
            self.assertEqual(row["location_policy_version_id"], load_location_policy().version)
            self.assertEqual(row["prompt_version"], "deterministic_fallback")
            self.assertEqual(row["model_version"], DETERMINISTIC_FALLBACK_VERSION)
            self.assertEqual(
                evaluation["provenance"]["candidate_profile_version"],
                load_candidate_profile().version,
            )
            self.assertEqual(
                evaluation["provenance"]["location_policy_version"],
                load_location_policy().version,
            )
            self.assertEqual(
                evaluation["provenance"]["scoring_policy_version"],
                load_scoring_policy().version,
            )
            self.assertEqual(evaluation["provenance"]["prompt_version"], "deterministic_fallback")
            self.assertEqual(
                evaluation["provenance"]["model_version"],
                DETERMINISTIC_FALLBACK_VERSION,
            )
            self.assertNotEqual(evaluation["provenance"]["prompt_version"], PROMPT_VERSION)
            self.assertEqual(
                evaluation["provenance"]["scoring_policy_version"],
                load_scoring_policy().version,
            )

    def test_under_volume_feed_is_degraded_and_does_not_count_absences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"
            partial_fixture = Path(directory) / "partial.json"
            payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
            payload["jobs"] = payload["jobs"][:1]
            partial_fixture.write_text(json.dumps(payload), encoding="utf-8")

            run_scan(db_path=db_path, fixture_path=FIXTURE)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            source = conn.execute("SELECT id FROM job_sources").fetchone()
            conn.execute(
                "UPDATE job_sources SET expected_volume_min = 5 WHERE id = ?",
                (source["id"],),
            )
            conn.commit()

            degraded = run_scan(db_path=db_path, fixture_path=partial_fixture)

            self.assertEqual(degraded.status, "degraded")
            self.assertIn("expected_volume_degraded", degraded.error_summary or "")

            source = conn.execute("SELECT * FROM job_sources").fetchone()
            run = conn.execute("SELECT * FROM source_runs ORDER BY id DESC LIMIT 1").fetchone()
            missing_counts = [
                row[0]
                for row in conn.execute(
                    "SELECT missing_successful_scan_count FROM job_postings ORDER BY id"
                )
            ]

            self.assertEqual(source["health_status"], "degraded")
            self.assertEqual(run["status"], "degraded")
            self.assertEqual(missing_counts, [0, 0, 0])

            _, text_path, _ = write_digest(conn, Path(directory) / "output")
            digest = text_path.read_text(encoding="utf-8")
            self.assertIn("degraded - Databricks", digest)
            self.assertIn("expected_volume_degraded", digest)

            run_scan(db_path=db_path, fixture_path=partial_fixture)
            run_scan(db_path=db_path, fixture_path=partial_fixture)
            source = conn.execute("SELECT * FROM job_sources").fetchone()
            self.assertEqual(source["expected_volume_min"], 1)

            recovered = run_scan(db_path=db_path, fixture_path=partial_fixture)
            source = conn.execute("SELECT * FROM job_sources").fetchone()
            self.assertEqual(recovered.status, "success")
            self.assertEqual(source["health_status"], "healthy")

    def test_cosmetic_metadata_change_preserves_review_and_evaluation_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"
            cosmetic_fixture = Path(directory) / "cosmetic.json"

            run_scan(db_path=db_path, fixture_path=FIXTURE)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            job = conn.execute("SELECT id FROM job_postings ORDER BY id LIMIT 1").fetchone()
            dismiss_review(conn, int(job["id"]), "human decision should stay put")
            before_review = _review_row(conn, int(job["id"]))
            before_evaluation_count = _count(conn, "role_evaluations")

            payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
            payload["jobs"][0]["updated_at"] = "2026-06-24T11:00:00-04:00"
            payload["jobs"][0]["metadata"] = [{"name": "cosmetic", "value": "ignored"}]
            cosmetic_fixture.write_text(json.dumps(payload), encoding="utf-8")

            cosmetic = run_scan(db_path=db_path, fixture_path=cosmetic_fixture)
            after_review = _review_row(conn, int(job["id"]))

            self.assertEqual(cosmetic.changed_count, 0)
            self.assertEqual(cosmetic.evaluated_count, 0)
            self.assertEqual(_count(conn, "role_evaluations"), before_evaluation_count)
            self.assertEqual(after_review["state"], "dismissed")
            self.assertEqual(after_review["decision_reason"], before_review["decision_reason"])
            self.assertEqual(after_review["reviewed_at"], before_review["reviewed_at"])

    def test_material_change_reopens_approved_and_dismissed_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"
            changed_fixture = Path(directory) / "changed.json"

            run_scan(db_path=db_path, fixture_path=FIXTURE)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            job_rows = conn.execute(
                "SELECT id, source_job_id FROM job_postings ORDER BY id LIMIT 2"
            ).fetchall()
            approve_review(conn, int(job_rows[0]["id"]))
            dismiss_review(conn, int(job_rows[1]["id"]), "already reviewed")
            before_evaluation_count = _count(conn, "role_evaluations")

            payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
            for job in payload["jobs"][:2]:
                job["content"] += "<p>Materially updated scope.</p>"
            changed_fixture.write_text(json.dumps(payload), encoding="utf-8")

            changed = run_scan(db_path=db_path, fixture_path=changed_fixture)

            self.assertEqual(changed.changed_count, 2)
            self.assertEqual(changed.evaluated_count, 2)
            self.assertEqual(_count(conn, "role_evaluations"), before_evaluation_count + 2)
            states = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT orev.state
                    FROM opportunity_reviews orev
                    WHERE orev.job_posting_id IN (?, ?)
                    ORDER BY orev.job_posting_id
                    """,
                    (int(job_rows[0]["id"]), int(job_rows[1]["id"])),
                )
            ]
            self.assertEqual(states, ["new", "new"])

    def test_snoozed_role_resurfaces_after_snooze_until_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"

            run_scan(db_path=db_path, fixture_path=FIXTURE)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            job = conn.execute("SELECT id FROM job_postings ORDER BY id LIMIT 1").fetchone()
            snooze_review(conn, int(job["id"]), "2026-07-01")

            changed = wake_due_snoozes(conn, "2026-07-02")
            conn.commit()
            state = conn.execute(
                "SELECT state, snooze_until FROM opportunity_reviews WHERE job_posting_id = ?",
                (int(job["id"]),),
            ).fetchone()

            self.assertEqual(changed, 1)
            self.assertEqual(state["state"], "new")
            self.assertIsNone(state["snooze_until"])


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _review_row(conn: sqlite3.Connection, job_id: int) -> sqlite3.Row:
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
