from __future__ import annotations

import json
import sqlite3
import tempfile
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from app.adapters import get_adapter
from app.config import load_candidate_profile, load_location_policy, load_scoring_policy
from app.db import current_evaluation_policy_version, wake_due_snoozes
from app.services.evaluate import DETERMINISTIC_FALLBACK_VERSION, HYBRID_EVALUATOR_VERSION
from app.services.digest import write_digest
from app.services.llm_evaluator import (
    LLMEvaluationOutput,
    LLMEvaluationResult,
    LLMProviderError,
    LLMRoleRequest,
    PROMPT_VERSION,
)
from app.services.ingest import run_scan
from app.services.notifications import EmailMessage, EmailSendResult, deliver_digest
from app.services.review import approve_review, dismiss_review, snooze_review


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "fixtures" / "greenhouse" / "databricks_jobs.json"


class DatabricksSliceTest(unittest.TestCase):
    def test_live_scan_stores_but_never_scores_postings_outside_recency_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"
            old_fixture = Path(directory) / "old.json"
            payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
            for job in payload["jobs"]:
                job["first_published"] = "2025-01-01T09:00:00+00:00"
            old_fixture.write_text(json.dumps(payload), encoding="utf-8")
            adapter = get_adapter("greenhouse")
            fetch_result = adapter.fetch_from_file("databricks", str(old_fixture))

            with (
                patch("app.services.ingest.get_adapter", return_value=adapter),
                patch.object(adapter, "fetch", return_value=fetch_result),
                patch("app.services.ingest._degraded_reason", return_value=None),
            ):
                summary = run_scan(db_path=db_path)

            self.assertEqual(summary.status, "success")
            self.assertEqual(summary.fetched_count, 3)
            self.assertEqual(summary.evaluated_count, 0)
            conn = sqlite3.connect(db_path)
            self.assertEqual(_count(conn, "job_postings"), 3)
            self.assertEqual(_count(conn, "role_evaluations"), 0)
            reasons = {
                row[0] for row in conn.execute("SELECT reason FROM evaluation_skips")
            }
            self.assertEqual(reasons, {"posting_older_than_21_days"})

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

    def test_one_malformed_llm_role_is_dropped_and_digest_still_sends(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"
            output_dir = Path(directory) / "output"
            llm_provider = DropOneRoleProvider(source_job_id="8516118002")

            with patch("app.services.evaluate.provider_from_env", return_value=llm_provider):
                summary = run_scan(db_path=db_path, fixture_path=FIXTURE)

            self.assertEqual(summary.status, "degraded")
            self.assertIn("llm_evaluation_dropped_roles=1", summary.error_summary or "")
            self.assertEqual(llm_provider.calls_by_source["8516118002"], 2)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            evaluations = conn.execute(
                "SELECT evaluation_json FROM role_evaluations ORDER BY id"
            ).fetchall()
            skip = conn.execute("SELECT reason FROM evaluation_skips").fetchone()
            run = conn.execute("SELECT * FROM source_runs ORDER BY id DESC LIMIT 1").fetchone()

            self.assertEqual(len(evaluations), 2)
            self.assertIsNotNone(skip)
            self.assertIn("claude_tool_input_validation_failed", skip["reason"])
            self.assertEqual(run["status"], "degraded")
            for row in evaluations:
                payload = json.loads(row["evaluation_json"])
                self.assertEqual(payload["provenance"]["fallback_quality"], "false")

            email_provider = FakeEmailProvider()
            notification = deliver_digest(
                conn,
                output_dir=output_dir,
                provider=email_provider,
                recipient="owner@example.com",
            )

            self.assertEqual(notification.status, "sent")
            self.assertEqual(notification.role_count, 2)
            self.assertEqual(len(email_provider.messages), 1)

    def test_all_malformed_llm_roles_send_degraded_capped_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"
            output_dir = Path(directory) / "output"
            llm_provider = FailAllRolesProvider()

            with patch("app.services.evaluate.provider_from_env", return_value=llm_provider):
                summary = run_scan(db_path=db_path, fixture_path=FIXTURE)

            self.assertEqual(summary.status, "degraded")
            self.assertIn("llm_evaluation_fallback_roles=3", summary.error_summary or "")

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            source = conn.execute("SELECT * FROM job_sources ORDER BY id DESC LIMIT 1").fetchone()
            run = conn.execute("SELECT * FROM source_runs ORDER BY id DESC LIMIT 1").fetchone()

            self.assertEqual(_count(conn, "role_evaluations"), 3)
            self.assertEqual(source["health_status"], "degraded")
            self.assertEqual(run["status"], "degraded")
            self.assertEqual(llm_provider.call_count, 6)

            email_provider = FakeEmailProvider()
            notification = deliver_digest(
                conn,
                output_dir=output_dir,
                provider=email_provider,
                recipient="owner@example.com",
            )

            self.assertEqual(notification.status, "sent")
            self.assertEqual(notification.role_count, 2)
            self.assertEqual(notification.failure_count, 1)
            self.assertIn("DEGRADED", notification.subject)
            self.assertEqual(len(email_provider.messages), 1)
            self.assertIn("DEGRADED", email_provider.messages[0].text_body)
            self.assertIn("Deployment Strategist", email_provider.messages[0].text_body)
            self.assertIn("Source failures", email_provider.messages[0].text_body)

            with patch(
                "app.services.evaluate.provider_from_env",
                return_value=SuccessfulProvider(),
            ):
                recovered = run_scan(db_path=db_path, fixture_path=FIXTURE)

            self.assertEqual(recovered.evaluated_count, 3)
            self.assertEqual(_count(conn, "role_evaluations"), 6)
            current_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM role_evaluations
                WHERE model_version = ?
                """,
                (f"fake-claude|{HYBRID_EVALUATOR_VERSION}",),
            ).fetchone()[0]
            self.assertEqual(current_count, 3)

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

    def test_stale_evaluator_version_open_postings_are_reevaluated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"
            provider = SuccessfulProvider()

            with patch("app.services.evaluate.provider_from_env", return_value=provider):
                run_scan(db_path=db_path, fixture_path=FIXTURE)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute(
                "UPDATE role_evaluations SET model_version = 'fake-claude|hybrid_claude_v1'"
            )
            conn.commit()
            before_count = _count(conn, "role_evaluations")

            with patch("app.services.evaluate.provider_from_env", return_value=provider):
                refreshed = run_scan(db_path=db_path, fixture_path=FIXTURE)

            current_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM role_evaluations
                WHERE model_version = ?
                """,
                (f"fake-claude|{HYBRID_EVALUATOR_VERSION}",),
            ).fetchone()[0]

            self.assertEqual(refreshed.changed_count, 0)
            self.assertEqual(refreshed.evaluated_count, 3)
            self.assertEqual(_count(conn, "role_evaluations"), before_count + 3)
            self.assertEqual(current_count, 3)

    def test_stale_gate_skips_advance_backfill_beyond_batch_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"
            fixture_path = Path(directory) / "thirty-jobs.json"
            jobs = [
                _fixture_job(
                    job_id=9200000000 + index,
                    title=f"Strategic Operations Lead {index:02d}",
                    location="London, United Kingdom",
                    department="Business Operations",
                    content=(
                        "<p>Lead strategy and operations programs and executive cadence "
                        f"for business unit {index:02d}.</p>"
                    ),
                )
                for index in range(30)
            ]
            fixture_path.write_text(
                json.dumps({"jobs": jobs, "meta": {"total": len(jobs)}}),
                encoding="utf-8",
            )
            provider = SuccessfulProvider()

            with patch("app.services.evaluate.provider_from_env", return_value=provider):
                initial = run_scan(db_path=db_path, fixture_path=fixture_path)
            self.assertEqual(initial.evaluated_count, 30)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute(
                "UPDATE role_evaluations SET model_version = 'fake-claude|hybrid_claude_v1'"
            )
            conn.commit()

            for index, job in enumerate(jobs[:25]):
                job["title"] = f"Account Executive {index:02d}"
                job["departments"] = [{"name": "Sales"}]
                job["content"] = "<p>Own a quota and close enterprise sales deals.</p>"
            fixture_path.write_text(
                json.dumps({"jobs": jobs, "meta": {"total": len(jobs)}}),
                encoding="utf-8",
            )

            with patch("app.services.evaluate.provider_from_env", return_value=provider):
                gate_batch = run_scan(db_path=db_path, fixture_path=fixture_path)

            versioned_skips = conn.execute(
                """
                SELECT COUNT(*)
                FROM evaluation_skips
                WHERE evaluator_version = ?
                """,
                (current_evaluation_policy_version(HYBRID_EVALUATOR_VERSION),),
            ).fetchone()[0]
            self.assertEqual(gate_batch.evaluated_count, 0)
            self.assertEqual(versioned_skips, 25)

            with patch("app.services.evaluate.provider_from_env", return_value=provider):
                progressed = run_scan(db_path=db_path, fixture_path=fixture_path)

            current_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM role_evaluations
                WHERE model_version = ?
                """,
                (f"fake-claude|{HYBRID_EVALUATOR_VERSION}",),
            ).fetchone()[0]
            self.assertEqual(progressed.changed_count, 0)
            self.assertEqual(progressed.evaluated_count, 5)
            self.assertEqual(current_count, 5)

    def test_config_opt_out_skip_is_reconsidered_after_policy_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"
            base_profile = load_candidate_profile()
            opted_out_profile = replace(
                base_profile,
                version="candidate_profile_optout_test_v1",
                employer_opt_outs={
                    **base_profile.employer_opt_outs,
                    "Databricks": "Test owner opt-out.",
                },
            )
            active_profile = replace(
                base_profile,
                version="candidate_profile_optout_test_v2",
                employer_opt_outs={
                    company: reason
                    for company, reason in base_profile.employer_opt_outs.items()
                    if company != "Databricks"
                },
            )

            with (
                patch(
                    "app.services.evaluate.load_candidate_profile",
                    return_value=opted_out_profile,
                ),
                patch(
                    "app.db.load_candidate_profile",
                    return_value=opted_out_profile,
                ),
            ):
                opted_out = run_scan(db_path=db_path, fixture_path=FIXTURE)

            self.assertEqual(opted_out.evaluated_count, 0)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            self.assertEqual(_count(conn, "role_evaluations"), 0)
            self.assertEqual(_count(conn, "evaluation_skips"), 3)

            provider = SuccessfulProvider()
            with (
                patch(
                    "app.services.evaluate.load_candidate_profile",
                    return_value=active_profile,
                ),
                patch(
                    "app.db.load_candidate_profile",
                    return_value=active_profile,
                ),
                patch("app.services.evaluate.provider_from_env", return_value=provider),
            ):
                reconsidered = run_scan(db_path=db_path, fixture_path=FIXTURE)

            self.assertEqual(reconsidered.changed_count, 0)
            self.assertEqual(reconsidered.evaluated_count, 3)
            self.assertEqual(provider.calls, 3)
            self.assertEqual(_count(conn, "role_evaluations"), 3)

    def test_stale_backfill_discards_fallback_when_no_current_evaluator_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "slice.sqlite"
            provider = SuccessfulProvider()

            with patch("app.services.evaluate.provider_from_env", return_value=provider):
                run_scan(db_path=db_path, fixture_path=FIXTURE)

            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute(
                "UPDATE role_evaluations SET model_version = 'fake-claude|hybrid_claude_v1'"
            )
            conn.commit()
            before_count = _count(conn, "role_evaluations")

            with patch("app.services.evaluate.provider_from_env", return_value=None):
                refreshed = run_scan(db_path=db_path, fixture_path=FIXTURE)

            model_versions = [
                row["model_version"]
                for row in conn.execute(
                    "SELECT model_version FROM role_evaluations ORDER BY id"
                ).fetchall()
            ]
            skip_reasons = [
                row["reason"]
                for row in conn.execute("SELECT reason FROM evaluation_skips ORDER BY id").fetchall()
            ]

            self.assertEqual(refreshed.changed_count, 0)
            self.assertEqual(refreshed.evaluated_count, 0)
            self.assertEqual(_count(conn, "role_evaluations"), before_count)
            self.assertEqual(model_versions, ["fake-claude|hybrid_claude_v1"] * 3)
            self.assertNotIn(DETERMINISTIC_FALLBACK_VERSION, model_versions)
            self.assertEqual(
                skip_reasons,
                ["stale_evaluation_backfill_deferred_no_current_evaluator"] * 3,
            )

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


class DropOneRoleProvider:
    model_version = "fake-claude"

    def __init__(self, *, source_job_id: str) -> None:
        self.source_job_id = source_job_id
        self.calls_by_source: dict[str, int] = {}

    def evaluate(self, request: LLMRoleRequest) -> LLMEvaluationResult:
        source_job_id = str(request.row["source_job_id"])
        self.calls_by_source[source_job_id] = self.calls_by_source.get(source_job_id, 0) + 1
        if source_job_id == self.source_job_id:
            raise LLMProviderError(
                "claude_tool_input_validation_failed: alignments input should be a valid list",
                retryable_output=True,
            )
        return LLMEvaluationResult(
            output=_valid_llm_output(),
            model_version=self.model_version,
            prompt_version="test_prompt_v1",
            cost_usd=0.001,
        )


class FailAllRolesProvider:
    model_version = "fake-claude"

    def __init__(self) -> None:
        self.call_count = 0

    def evaluate(self, request: LLMRoleRequest) -> LLMEvaluationResult:
        self.call_count += 1
        raise LLMProviderError(
            "claude_tool_input_validation_failed: alignments input should be a valid list",
            retryable_output=True,
        )


class SuccessfulProvider:
    model_version = "fake-claude"

    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, request: LLMRoleRequest) -> LLMEvaluationResult:
        self.calls += 1
        return LLMEvaluationResult(
            output=_valid_llm_output(),
            model_version=self.model_version,
            prompt_version="test_prompt_v1",
            cost_usd=0.001,
        )


class FakeEmailProvider:
    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailSendResult:
        self.messages.append(message)
        return EmailSendResult(status="sent", provider_message_id="fake-message-id")


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


def _valid_llm_output() -> LLMEvaluationOutput:
    return LLMEvaluationOutput.model_validate(
        {
            "role_family_fit": 82,
            "evidence_strength": 76,
            "scope_seniority": 75,
            "gap_manageability": 70,
            "confidence": 0.8,
            "advisory_recommendation": "consider",
            "estimated_level": "L5",
            "level_confidence": 75,
            "level_rationale": "Senior IC scope maps to the target L5 band.",
            "alignments": [
                {
                    "job_requirement": "Lead strategic customer deployment work",
                    "candidate_evidence": "Google transformation and operations evidence",
                    "evidence_strength": "strong",
                }
            ],
            "gaps": [
                {
                    "gap": "Limited direct Databricks domain evidence",
                    "severity": "medium",
                    "mitigation": "Position adjacent platform operations experience",
                }
            ],
            "hard_blockers": [],
            "uncertainties": ["Live regression fixture."],
            "summary": "Good strategic deployment match.",
        }
    )


if __name__ == "__main__":
    unittest.main()
